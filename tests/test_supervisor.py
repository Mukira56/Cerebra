import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy import select

from ai_hq.agents import AgentResult
from ai_hq.config import Settings
from ai_hq.db import Database
from ai_hq.models import Agent, Approval, Event, Finding, Project, Review, Run, Task, Worktree
from ai_hq.supervisor import Supervisor, TRANSITIONS
from ai_hq.processes import ProcessResult
from fakes import FixtureRegistry


def git(directory, *args):
    result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


@pytest.fixture
def hq(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "demo@example.invalid")
    git(repo, "config", "user.name", "AI HQ Test")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n*.pyc\n", encoding="utf-8")
    (repo / ".ai-hq-demo.json").write_text(json.dumps({"kind": "calculator-addition-v1"}), encoding="utf-8")
    (repo / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo / "test_calculator.py").write_text("from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_negative():\n    assert add(-2, -4) == -6\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Isolated test baseline")
    settings = Settings(data_dir=tmp_path / "data", test_timeout=20, live_enabled=True, cli_confinement_accepted=True)
    db = Database(settings.db_path)
    db.init()
    with db.Session.begin() as session:
        project = Project(name="Test fixture", path=str(repo), default_branch="main", protected_branches=["main"], test_commands=[[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]])
        session.add(project)
        session.flush()
        project_id = project.id
    supervisor = Supervisor(db, settings, registry=FixtureRegistry())
    yield supervisor, project_id, repo, db, settings
    supervisor.shutdown()
    db.close()


def proposed(hq, **kwargs):
    supervisor, project_id, *_ = hq
    return supervisor.propose(project_id, "Fix the calculator addition demonstration", allowed_paths=["calculator.py"], **kwargs)


def consent(hq, task_id):
    """Start asks once for agent consent; approve it and start again, as the dashboard does."""
    supervisor, db = hq[0], hq[3]
    supervisor.start(task_id)
    supervisor.resolve_approval(pending_approval(db, task_id, "live_execution").id, True)
    supervisor.start(task_id)


def ready(hq, **kwargs):
    supervisor = hq[0]
    task = proposed(hq, **kwargs)
    supervisor.approve_plan(task.id)
    consent(hq, task.id)
    return task.id


def pending_approval(db, task_id, kind="merge"):
    with db.Session() as session:
        return session.scalars(select(Approval).where(Approval.task_id == task_id, Approval.kind == kind, Approval.status == "pending")).one()


def test_end_to_end_actual_tests_independent_review_and_merge_approval(hq):
    supervisor, _, repo, db, _ = hq
    baseline = git(repo, "rev-parse", "HEAD")
    task_id = ready(hq)
    assert supervisor.run_until_idle() == 1
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL"
    assert task.results["verified"]
    assert task.test_results[-1]["passed"] is True
    assert "2 passed" in task.test_results[-1]["stdout"]
    assert git(repo, "rev-parse", "HEAD") == baseline
    assert "a - b" in (repo / "calculator.py").read_text()
    with db.Session() as session:
        runs = session.scalars(select(Run).where(Run.task_id == task_id)).all()
        assert [(r.agent, r.role) for r in runs] == [("claude", "plan"), ("codex", "implement"), ("claude", "review")]
        assert not any(r.simulated for r in runs)
        trees = session.scalars(select(Worktree).where(Worktree.task_id == task_id)).all()
        assert len({t.path for t in trees}) == 3
        assert not session.scalars(select(Review).where(Review.task_id == task_id)).one().simulated
    merged = supervisor.resolve_approval(pending_approval(db, task_id).id, True)
    assert merged.state == "COMPLETED"
    assert "a + b" in (repo / "calculator.py").read_text()
    assert git(repo, "rev-parse", "HEAD") != baseline


def test_reverse_roles_route_to_independent_opposite_reviewer(hq):
    supervisor, _, _, db, _ = hq
    task_id = ready(hq, implementer="claude")
    supervisor.run_until_idle()
    with db.Session() as session:
        runs = session.scalars(select(Run).where(Run.task_id == task_id)).all()
        assert [(r.agent, r.role) for r in runs] == [("claude", "plan"), ("claude", "implement"), ("codex", "review")]


def test_reviewer_must_be_a_different_provider(hq):
    with pytest.raises(ValueError, match="different AI provider"):
        proposed(hq, implementer="codex", reviewer="codex")


def test_chosen_models_reach_the_agents(hq):
    from ai_hq.profiles import add_profile
    supervisor, _, _, db, _ = hq
    with db.Session.begin() as session:
        add_profile(session, "claude", "opus", "Claude Opus")
    task_id = ready(hq, reviewer="claude-opus")
    supervisor.run_until_idle()
    models = {request.role: (name, request.model) for name, request in supervisor.registry.requests}
    assert models["review"] == ("claude", "opus")
    # Planner and coder default to Auto: the supervisor's rules picked a Claude planner and a Codex coder.
    assert models["plan"][0] == "claude" and models["plan"][1] in {"sonnet", "opus"} and models["implement"][0] == "codex"
    assert supervisor.get(task_id).results["models"]["reviewer"]["profile"] == "claude-opus"


def test_plan_approval_is_mandatory_and_transitions_validated(hq):
    supervisor, _, _, db, _ = hq
    task = proposed(hq)
    assert task.state == "AWAITING_APPROVAL" and task.plan
    with pytest.raises(ValueError, match="Approve the plan"):
        supervisor.start(task.id)
    with db.Session.begin() as session:
        stored = session.get(Task, task.id)
        with pytest.raises(ValueError, match="Invalid task transition"):
            supervisor._state(session, stored, "RUNNING", "Invalid")
    supervisor.approve_plan(task.id)
    assert supervisor.get(task.id).state == "READY"


def test_actual_test_failures_drive_validated_repair_and_rerun(hq):
    supervisor, project_id, _, db, _ = hq
    task = supervisor.propose(project_id, "Fix calculator addition [demo:needs-repair]", allowed_paths=["calculator.py"])
    supervisor.approve_plan(task.id)
    consent(hq, task.id)
    supervisor.run_until_idle()
    stored = supervisor.get(task.id)
    assert stored.state == "AWAITING_APPROVAL"
    assert stored.retry_count == 1
    assert [r["passed"] for r in stored.test_results] == [False, True]
    with db.Session() as session:
        # Failing tests alone drive repair; unproven model findings are never auto-validated.
        findings = session.scalars(select(Finding).join(Review, Finding.review_id == Review.id).where(Review.task_id == task.id)).all()
        assert not any(f.validated for f in findings)
        assert len(session.scalars(select(Review).where(Review.task_id == task.id)).all()) == 2


class FailingAgentRegistry(FixtureRegistry):
    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            return AgentResult(False, "[SIMULATED] fixture failure", error="fixture process failed")
        return super().execute(name, request, cancel_event)


def test_agent_failure_is_persistent_and_visible(hq):
    supervisor, _, _, db, _ = hq
    supervisor.registry = FailingAgentRegistry()
    task_id = ready(hq)
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "FAILED"
    assert "fixture process failed" in supervisor.get(task_id).results["error"]
    with db.Session() as session:
        run = session.scalars(select(Run).where(Run.task_id == task_id, Run.role == "implement")).one()
        assert run.status == "failed" and run.finished_at


class WrongAgentRegistry(FixtureRegistry):
    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            # Change source each time so the retry-limit check is exercised separately from stagnation.
            (Path(request.workdir) / "calculator.py").write_text(f"def add(a, b):\n    return a - b - {request.attempt + 1}\n", encoding="utf-8")
            return AgentResult(True, "[SIMULATED] Incorrect fixture implementation")
        return super().execute(name, request, cancel_event)


def test_repair_limit_stops_persistent_failures(hq):
    supervisor = hq[0]
    supervisor.registry = WrongAgentRegistry()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "FAILED"
    assert task.retry_count == 3
    assert len(task.test_results) == 4
    assert "retry limit" in task.results["error"]


class StagnantAgentRegistry(WrongAgentRegistry):
    def execute(self, name, request, cancel_event=None):
        request.attempt = 0
        return super().execute(name, request, cancel_event)


def test_no_meaningful_progress_stops_before_retry_limit(hq):
    supervisor = hq[0]
    supervisor.registry = StagnantAgentRegistry()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "FAILED"
    assert task.retry_count == 1
    assert "No meaningful progress" in task.results["error"]


def test_missing_test_commands_blocks_execution(hq):
    supervisor, project_id, _, db, _ = hq
    with db.Session.begin() as session:
        session.get(Project, project_id).test_commands = []
    task_id = ready(hq)
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "BLOCKED"
    assert "No verification commands" in supervisor.get(task_id).results["error"]


def test_recovery_preserves_records_and_requires_explicit_resume(hq):
    supervisor, _, _, db, settings = hq
    task_id = ready(hq)
    with db.Session.begin() as session:
        task = session.get(Task, task_id)
        task.state = "RUNNING"
        session.add(Run(task_id=task_id, agent="codex", role="implement", status="running", output="retained history"))
    restarted = Supervisor(db, settings, registry=FixtureRegistry())
    restarted.recover()
    task = restarted.get(task_id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "interrupted_restart"
    assert restarted.tick() is False
    with db.Session() as session:
        run = session.scalars(select(Run).where(Run.task_id == task_id, Run.output == "retained history")).one()
        assert run.status == "interrupted"
    assert restarted.resume(task_id).state == "READY"
    restarted.start(task_id)
    restarted.run_until_idle()
    assert restarted.get(task_id).state == "AWAITING_APPROVAL"


def test_pause_resume_and_cancel_keep_approval_and_history(hq):
    supervisor = hq[0]
    task = proposed(hq)
    assert supervisor.pause(task.id).state == "BLOCKED"
    assert supervisor.resume(task.id).state == "AWAITING_APPROVAL"
    supervisor.approve_plan(task.id)
    consent(hq, task.id)
    assert supervisor.pause(task.id).pause_requested
    assert supervisor.tick() is False
    assert supervisor.resume(task.id).state == "READY"
    assert supervisor.cancel(task.id).state == "CANCELLED"
    assert supervisor.tick() is False
    with pytest.raises(ValueError):
        supervisor.start(task.id)


class WaitingAgentRegistry(FixtureRegistry):
    started = None
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
    def execute(self, name, request, cancel_event=None):
        self.started.set()
        assert cancel_event.wait(10), "Expected the supervisor to propagate cancellation"
        return AgentResult(False, "[SIMULATED] Stopped", error="cancelled")


def test_active_cancellation_propagates_to_adapter(hq):
    supervisor = hq[0]
    supervisor.registry = WaitingAgentRegistry()
    task_id = ready(hq)
    worker = threading.Thread(target=supervisor.tick)
    worker.start()
    assert supervisor.registry.started.wait(60)  # the baseline test run comes first
    supervisor.cancel(task_id)
    worker.join(10)
    assert not worker.is_alive()
    assert supervisor.get(task_id).state == "CANCELLED"


def test_dependency_waits_for_approved_integration(hq):
    supervisor, _, _, db, _ = hq
    first = ready(hq)
    second = ready(hq, dependencies=[first])
    supervisor.run_until_idle()
    assert supervisor.get(first).state == "AWAITING_APPROVAL"
    assert supervisor.get(second).state == "BLOCKED"
    with db.Session() as session:
        assert not session.scalars(select(Run).where(Run.task_id == second)).all()
    supervisor.resolve_approval(pending_approval(db, first).id, True)
    supervisor.run_until_idle()
    # The second identical objective has nothing left to change, so it fails transparently.
    assert supervisor.get(second).state == "FAILED"
    assert "No meaningful progress" in supervisor.get(second).results["error"]


def test_candidate_edit_after_review_invalidates_merge_approval(hq):
    supervisor, _, repo, db, _ = hq
    baseline = git(repo, "rev-parse", "HEAD")
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    (Path(task.worktree_path) / "calculator.py").write_text("def add(a, b):\n    return 999\n", encoding="utf-8")
    result = supervisor.resolve_approval(pending_approval(db, task_id).id, True)
    assert result.state == "BLOCKED" and "stale" in result.results["error"]
    assert git(repo, "rev-parse", "HEAD") == baseline


def test_unknown_review_claim_requires_human_triage(hq):
    supervisor, _, _, db, _ = hq
    original = supervisor.registry.execute
    def execute(name, request, cancel_event=None):
        if request.role == "review":
            return AgentResult(True, "[SIMULATED] Unverified finding", [{"severity": "high", "path": "calculator.py", "line": 2, "message": "Unproven security concern", "evidence": "return a + b"}])
        return original(name, request, cancel_event)
    supervisor.registry.execute = execute
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL" and task.retry_count == 0
    assert task.review_findings[0]["validated"] is False
    triage = pending_approval(db, task_id, "review_findings")
    supervisor.resolve_approval(triage.id, False)
    assert pending_approval(db, task_id).kind == "merge"


@pytest.mark.parametrize("scope", [["../outside"], ["C:/Windows"], [".git/config"], ["-bad"]])
def test_unauthorized_scope_is_rejected(hq, scope):
    with pytest.raises(ValueError):
        hq[0].propose(hq[1], "calculator addition", allowed_paths=scope)


def test_live_execution_never_runs_without_explicit_configuration(hq):
    supervisor = hq[0]
    hq[4].live_enabled = False
    task = proposed(hq)
    supervisor.approve_plan(task.id)
    with pytest.raises(ValueError, match="AI agents are switched off"):
        supervisor.start(task.id)


def test_retired_demo_tasks_cannot_start(hq):
    supervisor, _, _, db, _ = hq
    task = proposed(hq)
    supervisor.approve_plan(task.id)
    with db.Session.begin() as session:
        session.get(Task, task.id).mode = "mock"
    with pytest.raises(ValueError, match="retired simulated demo"):
        supervisor.start(task.id)


def test_agent_that_changes_nothing_is_not_falsely_completed(hq):
    supervisor, project_id, *_ = hq
    task = supervisor.propose(project_id, "Build an entire booking website", allowed_paths=["."])
    supervisor.approve_plan(task.id)
    consent(hq, task.id)
    supervisor.run_until_idle()
    assert supervisor.get(task.id).state == "FAILED"
    assert "only the calculator" in supervisor.get(task.id).results["error"]


def test_agent_output_and_error_are_redacted_before_persistence(hq):
    supervisor, _, _, db, _ = hq
    supervisor.registry.execute = lambda *args, **kwargs: AgentResult(False, "password=supersecretvalue", error="api_key=anothersecretvalue")
    task_id = ready(hq)
    supervisor.run_until_idle()
    with db.Session() as session:
        run = session.scalars(select(Run).where(Run.task_id == task_id)).first()
        events = session.scalars(select(Event).where(Event.task_id == task_id)).all()
        combined = str(supervisor.get(task_id).results) + run.output + run.error + str([e.message for e in events])
        assert "supersecretvalue" not in combined and "anothersecretvalue" not in combined
        assert "[REDACTED]" in combined


class SelfCommittingRegistry(FixtureRegistry):
    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            root = Path(request.workdir)
            (root / "unauthorized.txt").write_text("An unauthorized committed change", encoding="utf-8")
            git(root, "add", "unauthorized.txt")
            git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Self committed change")
        return super().execute(name, request, cancel_event)


def test_agent_self_commits_cannot_bypass_authorized_paths(hq):
    supervisor, _, repo, db, _ = hq
    baseline = git(repo, "rev-parse", "HEAD")
    supervisor.registry = SelfCommittingRegistry()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "FAILED" and "unauthorized path" in task.results["error"]
    assert git(repo, "rev-parse", "HEAD") == baseline
    assert not (repo / "unauthorized.txt").exists()
    with db.Session() as session:
        assert not session.scalars(select(Approval).where(Approval.task_id == task_id, Approval.kind == "merge")).all()


@pytest.mark.parametrize("timed_out,truncated", [(True, False), (False, True)])
def test_timeout_and_truncated_test_output_never_count_as_passed(hq, timed_out, truncated):
    supervisor = hq[0]
    class VerificationRunner:
        def run(self, *args, **kwargs):
            return ProcessResult(0, "incomplete verification output", "", timed_out=timed_out, output_truncated=truncated)
    supervisor.runner = VerificationRunner()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "FAILED" and task.test_results
    assert task.test_results[0]["passed"] is False
    assert task.test_results[0]["timed_out"] is timed_out
    assert task.test_results[0]["output_truncated"] is truncated


def test_target_branch_switch_after_review_invalidates_approval(hq):
    supervisor, _, repo, db, _ = hq
    task_id = ready(hq)
    supervisor.run_until_idle()
    approval = pending_approval(db, task_id)
    assert approval.payload["base_branch"] == "main"
    git(repo, "switch", "-c", "different-target")
    task = supervisor.resolve_approval(approval.id, True)
    assert task.state == "BLOCKED" and "target branch differs" in task.results["error"]
    assert "a - b" in (repo / "calculator.py").read_text()


def test_live_workflow_gets_claude_architecture_after_consent_without_changing_plan(hq):
    supervisor, _, _, db, settings = hq
    settings.live_enabled = True
    supervisor.registry = FixtureRegistry()
    task = proposed(hq)
    original_plan = task.plan
    original_requirements = task.requirements
    supervisor.approve_plan(task.id)
    supervisor.start(task.id)
    with db.Session() as session:
        assert not session.scalars(select(Run).where(Run.task_id == task.id)).all()
    supervisor.resolve_approval(pending_approval(db, task.id, "live_execution").id, True)
    supervisor.start(task.id)
    supervisor.run_until_idle()
    stored = supervisor.get(task.id)
    assert stored.state == "AWAITING_APPROVAL"
    assert stored.plan == original_plan and stored.requirements == original_requirements
    architecture = stored.results["architecture"]
    assert architecture["agent"] == "claude" and architecture["baseline"] == stored.base_commit
    assert Path(architecture["artifact"]).is_file()
    assert "secretplanneroutput" not in Path(architecture["artifact"]).read_text()
    with db.Session() as session:
        runs = session.scalars(select(Run).where(Run.task_id == task.id).order_by(Run.started_at)).all()
        assert [(r.agent, r.role) for r in runs] == [("claude", "plan"), ("codex", "implement"), ("claude", "review")]
        trees = session.scalars(select(Worktree).where(Worktree.task_id == task.id)).all()
        assert len({t.path for t in trees}) == 3
        claude = session.get(Agent, "claude").status
        codex = session.get(Agent, "codex").status
        assert claude["authentication"] == codex["authentication"] == "verified_by_execution"
        assert claude["last_live_role"] == "review" and codex["last_live_role"] == "implement"
        assert claude["last_live_task"] == codex["last_live_task"] == task.id
        assert claude["last_live_success_at"] and codex["last_live_success_at"]


def test_planner_cannot_modify_snapshot_or_dispatch_implementation(hq):
    supervisor, _, _, db, settings = hq
    settings.live_enabled = True
    supervisor.registry = FixtureRegistry(planner_modifies=True)
    task = proposed(hq)
    supervisor.approve_plan(task.id)
    supervisor.start(task.id)
    supervisor.resolve_approval(pending_approval(db, task.id, "live_execution").id, True)
    supervisor.start(task.id)
    supervisor.run_until_idle()
    stored = supervisor.get(task.id)
    assert stored.state == "FAILED" and "planner modified" in stored.results["error"]
    with db.Session() as session:
        runs = session.scalars(select(Run).where(Run.task_id == task.id)).all()
        assert [r.role for r in runs] == ["plan"]


def test_forged_queue_cannot_dispatch_live_without_per_task_consent(hq):
    supervisor, _, _, db, settings = hq
    settings.live_enabled = True
    supervisor.registry = FixtureRegistry()
    task = proposed(hq)
    supervisor.approve_plan(task.id)
    with db.Session.begin() as session:
        stored = session.get(Task, task.id)
        stored.results = {**stored.results, "queued": True}
    supervisor.run_until_idle()
    assert supervisor.get(task.id).state == "FAILED"
    assert "live execution consent" in supervisor.get(task.id).results["error"]
    with db.Session() as session:
        assert not session.scalars(select(Run).where(Run.task_id == task.id)).all()


def test_architecture_extracts_claude_result_without_replacing_raw_run_output():
    envelope = json.dumps({"type": "result", "result": "Keep the approved calculator interface and verify addition.", "usage": {"output_tokens": 12}})
    assert Supervisor._architecture_text(envelope) == "Keep the approved calculator interface and verify addition."
    assert Supervisor._architecture_text("Fixture plain advisory") == "Fixture plain advisory"
    assert '"usage"' in envelope


def test_live_auth_failure_updates_generic_status_without_persisting_secret(hq):
    supervisor, _, _, db, settings = hq
    settings.live_enabled = True
    supervisor.registry = FixtureRegistry()
    supervisor.registry.execute = lambda *args, **kwargs: AgentResult(False, "password=providersecret", error="authentication_error: not logged in", simulated=False)
    task = proposed(hq)
    supervisor.approve_plan(task.id)
    supervisor.start(task.id)
    supervisor.resolve_approval(pending_approval(db, task.id, "live_execution").id, True)
    supervisor.run_until_idle()
    with db.Session() as session:
        status = session.get(Agent, "claude").status
        assert status["authentication"] == "error" and status["last_error_at"]
        assert "providersecret" not in str(status)
        assert "last_live_success_at" not in status
    # Both providers report a sign-in problem: the task waits for a usable model instead of failing.
    task = supervisor.get(task.id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "waiting_for_usage" and "providersecret" not in str(task.results)
