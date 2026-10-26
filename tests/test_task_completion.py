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
from test_product_api import client  # noqa: F401  (fixture)

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


def test_try_again_reruns_a_failed_task_with_its_last_error(client, tmp_path):  # noqa: F811  (client fixture)
    from test_assistant_control import failed_task
    task_id, _ = failed_task(client, tmp_path)
    assert client.post(f"/api/tasks/{task_id}/retry").status_code == 200
    supervisor = client.app.state.supervisor
    supervisor.run_until_idle()
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["state"] == "AWAITING_APPROVAL" and task["results"]["origin"] == "user" and not task["results"].get("instructions_from")
    coding = [request for name, request in supervisor.registry.requests if getattr(request, "role", "") == "implement"]
    assert "Try again from where it stopped" in coding[-1].description and "calcualtor" in coding[-1].description


def test_the_refreshing_task_list_leaves_out_diffs_and_test_output(client, tmp_path):  # noqa: F811
    from test_assistant_control import failed_task
    task_id, _ = failed_task(client, tmp_path)
    client.post(f"/api/tasks/{task_id}/retry"); client.app.state.supervisor.run_until_idle()
    listed = next(task for task in client.get("/api/overview").json()["tasks"] if task["id"] == task_id)
    full = client.get(f"/api/tasks/{task_id}").json()
    assert full["results"]["diff"] and "diff" not in listed["results"]
    assert full["test_results"][-1]["stdout"] and set(listed["test_results"][-1]) == {"command", "passed", "exit_code"}
    assert listed["results"]["models"] == full["results"]["models"] and listed["results"]["origin"] == "user"


def test_tests_that_write_files_are_named_in_the_message(hq):
    supervisor, project_id, _, db, _ = hq
    from ai_hq.models import Project
    with db.Session.begin() as session:
        session.get(Project, project_id).test_commands = [[sys.executable, "-c", "open('report-output.txt', 'w').write('x')"]]
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "BLOCKED" and "report-output.txt" in task.results["error"] and ".gitignore" in task.results["error"]


REAL_OFFLINE = ('{"stop_reason":"stop_sequence","total_cost_usd":0,"terminal_reason":"api_error","is_error":true,"num_turns":1,"subtype":"success",'
                '"result":"API Error: Can\'t reach the API server \u2014 check your internet or DNS (ENOTFOUND)","type":"result"}')


def test_cli_failures_show_the_readable_sentence_and_offline_is_labelled():
    from ai_hq.agents import OFFLINE_MARKERS, failure_detail
    detail = failure_detail("some log line\n" + REAL_OFFLINE)
    assert detail.startswith("API Error: Can't reach the API server") and any(marker in detail.lower() for marker in OFFLINE_MARKERS)
    assert failure_detail('{"type":"turn.failed","error":{"message":"stream disconnected before completion"}}') == "stream disconnected before completion"
    assert failure_detail("plain stderr text") == "plain stderr text"


class OfflineCoder(FixtureRegistry):
    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            self.requests.append((name, request))
            return AgentResult(False, REAL_OFFLINE, error="offline: agent exited with code 1: API Error: Can't reach the API server (ENOTFOUND)")
        return super().execute(name, request, cancel_event)


def test_an_internet_outage_waits_and_retries_instead_of_failing(hq):
    from ai_hq import autofix
    supervisor = hq[0]
    supervisor.registry = OfflineCoder()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "waiting_for_network" and task.results["retry_after"]
    assert "couldn't reach its servers" in task.results["error"] and autofix.problem(task) is None  # Auto-fix doesn't spend attempts on it
    supervisor.registry = FixtureRegistry()  # the connection is back
    with hq[3].Session.begin() as session:
        from ai_hq.models import Task
        stored = session.get(Task, task_id)
        stored.results = {**stored.results, "retry_after": "2000-01-01T00:00:00+00:00"}
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "AWAITING_APPROVAL"
