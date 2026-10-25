"""Out-of-usage failover, handoff, waiting for usage, pause on close and resuming at review. Fixture agents only."""
from datetime import datetime, timedelta, timezone

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
