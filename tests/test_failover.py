"""Out-of-usage failover, handoff, waiting for usage, pause on close and resuming at review. Fixture agents only."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_hq.agents import AgentResult
from ai_hq.models import Event, Task
from ai_hq import manage
from fakes import FixtureRegistry
from test_supervisor import consent, git, hq, pending_approval, proposed, ready  # noqa: F401  (hq is a fixture)

LIMIT = "rate_limited: agent exited with code 1: You've hit your usage limit. Try again later."


class LimitedRegistry(FixtureRegistry):
    """Providers in `exhausted` fail as if their usage ran out; the others behave normally."""
    def __init__(self, exhausted=()):
        super().__init__()
        self.exhausted = set(exhausted)

    def execute(self, name, request, cancel_event=None):
        if name in self.exhausted:
            self.requests.append((name, request))
            return AgentResult(False, "Started: reading calculator.py, the addition looks wrong", error=LIMIT)
        return super().execute(name, request, cancel_event)


def events(db, task_id, kind):
    with db.Session() as session:
        return [row.message for row in session.query(Event).filter(Event.task_id == task_id, Event.kind == kind)]


def come_back(supervisor, task_id, registry):
    """Usage is available again: clear the cool-down and make the retry due now."""
    registry.exhausted.clear()
    supervisor._unavailable.clear()
    with supervisor.db.Session.begin() as session:
        task = session.get(Task, task_id)
        task.results = {**task.results, "retry_after": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}


def test_codex_out_of_usage_claude_takes_over_and_review_waits_for_independence(hq):
    supervisor, _, repo, db, _ = hq
    supervisor.registry = registry = LimitedRegistry({"codex"})
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    # Claude took over the coding with a handoff note, finished it, and the tests ran.
    implement = [(name, request) for name, request in registry.requests if request.role == "implement"]
    assert [name for name, _ in implement] == ["codex", "claude"]
    assert "HANDOFF: codex was doing this step" in implement[1][1].description and "reading calculator.py" in implement[1][1].description
    assert task.results["models"]["implementer"]["provider"] == "claude" and task.results["handoffs"][0]["to"] == "claude"
    assert any("takes over" in message for message in events(db, task_id, "failover"))
    # The reviewer must be Codex (independent of the new coder), which is still out of usage: the task waits.
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "waiting_for_usage" and task.results["resume_stage"] == "review"
    assert task.reviewer == "codex"
    come_back(supervisor, task_id, registry)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL" and pending_approval(db, task_id, "merge")
    implement_after = [name for name, request in registry.requests if request.role == "implement"]
    assert implement_after == ["codex", "claude"]  # resumed straight at tests + review, no re-coding
    assert [name for name, request in registry.requests if request.role == "review"][-1] == "codex"


def test_planner_out_of_usage_is_replaced(hq):
    supervisor, _, _, db, _ = hq
    supervisor.registry = registry = LimitedRegistry({"claude"})
    task_id = ready(hq)
    supervisor.run_until_idle()
    plans = [name for name, request in registry.requests if request.role == "plan"]
    assert plans[:2] == ["claude", "codex"]
    assert supervisor.get(task_id).results["models"]["planner"]["provider"] == "codex"


def test_no_model_with_usage_pauses_and_retries_automatically(hq):
    supervisor, _, _, db, _ = hq
    supervisor.registry = registry = LimitedRegistry({"codex", "claude"})
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "waiting_for_usage" and task.results["retry_after"]
    assert "try again automatically" in events(db, task_id, "state")[-1]
    assert supervisor.tick() is False  # not due yet: nothing is retried early
    come_back(supervisor, task_id, registry)
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "AWAITING_APPROVAL"


def test_pause_during_review_resumes_at_review_without_recoding(hq):
    supervisor, _, _, db, _ = hq
    supervisor.registry = registry = LimitedRegistry({"claude"})  # the reviewer (Claude) is out of usage, so the run stops at review
    task_id = ready(hq, planner="codex")
    supervisor.run_until_idle()
    assert supervisor.get(task_id).results["resume_stage"] == "review"
    registry.exhausted.clear(); supervisor._unavailable.clear()
    supervisor.resume(task_id); supervisor.start(task_id)
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "AWAITING_APPROVAL"
    assert [request.role for _, request in registry.requests].count("implement") == 1


def test_closing_pauses_running_tasks_and_lists_them(hq):
    supervisor, project_id, _, db, settings = hq
    task = proposed(hq)
    supervisor.approve_plan(task.id)
    with db.Session.begin() as session:
        stored = session.get(Task, task.id)
        stored.state, stored.results = "REVIEWING", {**stored.results, "candidate_commit": "abc123"}
    status = manage.status(settings)
    assert status["active_tasks"] == 1 and status["tasks"][0]["id"] == task.id
    assert manage.pause_after_stop(settings) == 1
    stored = supervisor.get(task.id)
    assert stored.state == "BLOCKED" and stored.pause_requested and stored.results["blocked_reason"] == "paused_on_close"
    assert stored.results["resume_stage"] == "review" and "Paused because Cerebra was closed" in events(db, task.id, "state")[-1]
    assert manage.status(settings)["active_tasks"] == 0


def test_work_paused_by_a_restart_continues_by_itself(hq):
    from test_supervisor import ready
    supervisor, _, _, db, settings = hq
    task_id = ready(hq)  # approved, consented and queued
    assert manage.pause_after_stop(settings) == 1  # Cerebra closes (an update, a reboot)
    assert supervisor.get(task_id).results["blocked_reason"] == "paused_on_close"
    assert supervisor.resume_after_restart() == [task_id]  # Cerebra starts again
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL" and task.results["restart_resumes"] == 1
    assert "continuing this task automatically" in " ".join(events(db, task_id, "state"))


def test_a_task_that_keeps_stopping_cerebra_is_not_resumed_forever(hq):
    from test_supervisor import ready
    supervisor, _, _, db, settings = hq
    task_id = ready(hq)
    manage.pause_after_stop(settings)
    with db.Session.begin() as session:
        stored = session.get(Task, task_id)
        stored.results = {**stored.results, "restart_resumes": supervisor.MAX_RESTART_RESUMES}
    assert supervisor.resume_after_restart() == [] and supervisor.get(task_id).state == "BLOCKED"


class FileWriter(FixtureRegistry):
    """Each coding run writes a file: its own (parallel work) or a shared one (overlapping work)."""
    def __init__(self, shared=False):
        super().__init__()
        self.shared = shared

    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            self.requests.append((name, request))
            target = "shared.txt" if self.shared else f"{request.task_id[:8]}.txt"
            (Path(request.workdir) / target).write_text(f"written by {request.task_id}\n", encoding="utf-8")
            return AgentResult(True, "Wrote the file.")
        if request.role == "review":
            self.requests.append((name, request))
            return AgentResult(True, "Reviewed: nothing to fix.", [])
        return super().execute(name, request, cancel_event)


def two_finished_tasks(hq, shared=False):
    supervisor, project_id, repo, db, _ = hq
    supervisor.registry = FileWriter(shared)
    with db.Session.begin() as session:
        from ai_hq.models import Project
        session.get(Project, project_id).test_commands = [[sys.executable, "-c", "pass"]]
    ids = []
    for text in ("Write the first file", "Write the second file"):
        task = supervisor.propose(project_id, text, allowed_paths=["."])
        supervisor.approve_plan(task.id); consent(hq, task.id); ids.append(task.id)
    supervisor.run_until_idle()
    assert [supervisor.get(task_id).state for task_id in ids] == ["AWAITING_APPROVAL", "AWAITING_APPROVAL"], [supervisor.get(task_id).results.get("error") for task_id in ids]
    supervisor.resolve_approval(pending_approval(db, ids[0]).id, True)
    assert supervisor.get(ids[0]).state == "COMPLETED"
    return ids


def test_a_task_whose_project_moved_on_is_caught_up_retested_and_merged(hq):
    supervisor, _, repo, db, _ = hq
    first, second = two_finished_tasks(hq)
    supervisor.resolve_approval(pending_approval(db, second).id, True)  # the project moved on since it started
    task = supervisor.get(second)
    assert task.state == "READY" and task.results["catch_ups"] == 1 and "moved on" in " ".join(events(db, second, "state"))
    supervisor.run_until_idle()  # tests and review again, on the latest code
    supervisor.resolve_approval(pending_approval(db, second).id, True)
    assert supervisor.get(second).state == "COMPLETED"
    assert (repo / f"{first[:8]}.txt").is_file() and (repo / f"{second[:8]}.txt").is_file()
    coding = [request for name, request in supervisor.registry.requests if getattr(request, "role", "") == "implement"]
    assert len(coding) == 2  # no AI run was spent on catching up


def test_overlapping_changes_pause_with_the_files_named(hq):
    supervisor, _, repo, db, _ = hq
    first, second = two_finished_tasks(hq, shared=True)
    supervisor.resolve_approval(pending_approval(db, second).id, True)
    task = supervisor.get(second)
    assert task.state == "BLOCKED" and "shared.txt" in task.results["error"] and "Try again" in task.results["error"]
    from ai_hq import autofix
    assert autofix.problem(task) is None  # Auto-fix doesn't rerun the coder on old code; the owner decides
    assert (repo / "shared.txt").read_text(encoding="utf-8") == f"written by {first}\n"  # the merged work is untouched


def test_try_again_after_overlapping_changes_redoes_the_work_on_the_latest_code(hq):
    supervisor, _, repo, db, _ = hq
    first, second = two_finished_tasks(hq, shared=True)
    supervisor.resolve_approval(pending_approval(db, second).id, True)  # overlap: paused
    supervisor.registry.shared = False  # the redo writes its own file on top of the latest code
    supervisor.try_again(second)
    supervisor.run_until_idle()
    supervisor.resolve_approval(pending_approval(db, second).id, True)
    task = supervisor.get(second)
    assert task.state == "COMPLETED" and task.results["previous_attempt_commit"]
    assert (repo / "shared.txt").read_text(encoding="utf-8") == f"written by {first}\n" and (repo / f"{second[:8]}.txt").is_file()
    coding = [request for name, request in supervisor.registry.requests if getattr(request, "role", "") == "implement"]
    assert "Redo this task on the project's latest code" in coding[-1].description


def test_uncommitted_changes_in_the_project_wait_then_set_aside_and_merge(hq):
    from ai_hq import autofix
    supervisor, _, repo, db, _ = hq
    task_id = ready(hq)
    supervisor.run_until_idle()
    (repo / "calculator.py").write_text("def add(a, b):\n    return a - b  # the owner's own edit\n", encoding="utf-8")
    supervisor.resolve_approval(pending_approval(db, task_id).id, True)
    task = supervisor.get(task_id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "repository_has_changes"
    assert "calculator.py" in task.results["error"] and autofix.problem(task) is None  # named, and Auto-fix leaves it alone
    supervisor.set_aside_and_merge(task_id)
    assert supervisor.get(task_id).state == "COMPLETED" and "return a + b" in (repo / "calculator.py").read_text()
    stash = git(repo, "stash", "list")
    assert supervisor.get(task_id).results["set_aside"]
    assert f"Cerebra set these aside before merging task {task_id[:8]}" in stash  # nothing lost


def test_a_merge_blocked_by_an_older_version_can_be_set_aside_too(hq):
    supervisor, _, repo, db, _ = hq
    task_id = ready(hq)
    supervisor.run_until_idle()
    (repo / "notes.txt").write_text("owner's scratch notes", encoding="utf-8")
    approval = pending_approval(db, task_id)
    with db.Session.begin() as session:  # what versions before 0.32 recorded
        from ai_hq.models import Approval
        session.get(Approval, approval.id).status = "approved"
        stored = session.get(Task, task_id)
        stored.state = "BLOCKED"
        stored.results = {**stored.results, "error": "Integration blocked: Integration refused: registered repository has user changes", "blocked_reason": None}
    supervisor.set_aside_and_merge(task_id)
    assert supervisor.get(task_id).state == "COMPLETED" and not (repo / "notes.txt").exists()
