"""Why real tasks failed on the owner's laptop (26 October), and the fixes. Scripted fixture models only.

1. Tested work was thrown away: the reviewer couldn't run node in its own sandbox, kept filing findings about that,
   the coder had nothing left to change, and "no meaningful progress" failed a task whose tests all passed.
2. One slow `claude --help` (over 10 s on this laptop) marked Claude unusable until Cerebra restarted.
"""
import sys

from ai_hq import autopilot
from ai_hq.agents import AgentResult, ClaudeAdapter
from ai_hq.processes import ProcessResult
from fakes import FixtureRegistry
from test_supervisor import git, hq, pending_approval, ready  # noqa: F401  (hq is a fixture)

SANDBOX_FINDING = {"severity": "medium", "path": "calculator.py", "line": 2,
                   "message": "node is unavailable on PATH in this review environment; the test summary can't be attested"}


class SandboxedReviewer(FixtureRegistry):
    """The coder does the work; the reviewer can't run anything itself and says so every time."""
    def execute(self, name, request, cancel_event=None):
        if request.role == "review":
            self.requests.append((name, request))
            return AgentResult(True, "Static review only.", [dict(SANDBOX_FINDING)])
        return super().execute(name, request, cancel_event)


def test_passing_work_with_disputed_findings_goes_to_the_owner_not_to_failed(hq):
    supervisor, _, repo, db, _ = hq
    supervisor.registry = SandboxedReviewer()
    task_id = ready(hq)
    supervisor.run_until_idle()
    supervisor.resolve_approval(pending_approval(db, task_id, "review_findings").id, True)  # as Away mode or the Assistant would
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL", task.results.get("error")
    assert task.results["disputed_findings"][0]["message"] == SANDBOX_FINDING["message"]
    merge = pending_approval(db, task_id, "merge")
    assert merge.payload["disputed_findings"] and all(result["passed"] for result in task.test_results[-1:])
    reviews = [request for name, request in supervisor.registry.requests if getattr(request, "role", "") == "review"]
    assert "These results are authoritative" in reviews[0].description and "not a defect" in reviews[0].description
    with db.Session.begin() as session:  # Away mode with automatic merging still leaves disputed work to the owner
        autopilot.save(session, True, 8, auto_merge=True)
    supervisor.auto_approve()
    assert supervisor.get(task_id).state == "AWAITING_APPROVAL" and pending_approval(db, task_id, "merge").id == merge.id
    supervisor.resolve_approval(merge.id, True)
    assert supervisor.get(task_id).state == "COMPLETED"
    assert "return a + b" in (repo / "calculator.py").read_text()


def test_a_slow_cli_check_is_retried_instead_of_disabling_the_provider():
    flags = "--print --output-format --tools --permission-mode --no-session-persistence --safe-mode --setting-sources --strict-mcp-config --mcp-config --disallowedTools --allowedTools"

    class SlowOnce:
        def __init__(self):
            self.calls, self.timeouts = 0, []
        def run(self, args, cwd, timeout):
            self.calls += 1
            self.timeouts.append(timeout)
            if self.calls <= 2:  # the first check times out
                return ProcessResult(-1, "", "", timed_out=True)
            return ProcessResult(0, flags if "--help" in args else "2.1.302 (Claude Code)", "")

    runner = SlowOnce()
    adapter = ClaudeAdapter(runner, sys.executable)
    assert adapter.probe()["available"] is False and adapter._capability is None  # not remembered
    assert adapter.probe()["available"] is True and adapter._capability is not None
    assert min(runner.timeouts) >= 60
