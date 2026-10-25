"""The Assistant reads failure evidence, retries with fix instructions, and controls Cerebra within its permissions."""
import sys

import pytest

from ai_hq import support
from ai_hq.agents import AgentResult
from fakes import FixtureRegistry
from test_product_api import calculator, client, enable_agents  # noqa: F401  (client is a fixture)


class FlakyCoder(FixtureRegistry):
    """The first coding run fails like a real crash; later runs do the work."""
    def __init__(self):
        super().__init__()
        self.failures = 1

    def execute(self, name, request, cancel_event=None):
        if request.role == "implement" and self.failures:
            self.failures -= 1
            self.requests.append((name, request))
            return AgentResult(False, "Traceback: ModuleNotFoundError: No module named 'calcualtor'", error="agent exited with code 1: ModuleNotFoundError: No module named 'calcualtor'")
        return super().execute(name, request, cancel_event)


def failed_task(client, tmp_path):
    enable_agents(client)
    supervisor = client.app.state.supervisor
    supervisor.registry = FlakyCoder()
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True,
                                                  "test_commands": [[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition", "allowed_paths": ["calculator.py"]}).json()
    client.post(f"/api/tasks/{task['id']}/approve-plan", json={})
    client.post(f"/api/tasks/{task['id']}/start", json={})
    consent = next(row for row in client.get(f"/api/tasks/{task['id']}").json()["approvals"] if row["kind"] == "live_execution")
    client.post(f"/api/approvals/{consent['id']}", json={"approve": True}); client.post(f"/api/tasks/{task['id']}/start", json={})
    supervisor.run_until_idle()
    assert client.get(f"/api/tasks/{task['id']}").json()["state"] == "FAILED"
    return task["id"], project


def test_failure_logs_retry_with_instructions_and_finish(client, tmp_path):
    task_id, project = failed_task(client, tmp_path)
    with client.app.state.db.Session() as session:
        evidence = support.failure_logs(session, client.app.state.settings.data_dir)
    assert task_id[:8] in evidence and "No module named 'calcualtor'" in evidence and "Log tail" in evidence
    client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True})
    run = client.app.state.chats.executor
    _, actions, problems = support.parse('```cerebra-actions\n[{"action": "retry_task", "task": "%s", "instructions": "The import is misspelled: in calculator.py keep the module name calculator and fix add to return a + b."}]\n```' % task_id[:8])
    assert not problems and "retrying" in run(actions[0])
    supervisor = client.app.state.supervisor
    supervisor.run_until_idle()
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["state"] == "AWAITING_APPROVAL" and task["results"]["origin"] == "support"
    coding = [request for name, request in supervisor.registry.requests if request.role == "implement"]
    assert "FIX INSTRUCTIONS from the assistant" in coding[-1].description and "misspelled" in coding[-1].description
    assert any(event["kind"] == "retry" for event in task["events"])


def test_answering_approvals_needs_the_users_permission(client, tmp_path):
    task_id, _ = failed_task(client, tmp_path)
    run = client.app.state.chats.executor
    run({"action": "retry_task", "task": task_id[:8], "instructions": "Fix add in calculator.py to return a + b, then run the tests."})
    client.app.state.supervisor.run_until_idle()
    merge = {"action": "answer_approval", "task": task_id[:8], "kind": "merge", "approve": True}
    with pytest.raises(ValueError, match="don't let the Assistant answer approvals"):
        run(merge)
    assert client.put("/api/support", json={"allow_approvals": True}).json()["allow_approvals"] is True
    assert client.get("/api/support").json()["act_automatically"] is False  # the other setting is kept
    assert "Approved" in run(merge)
    assert client.get(f"/api/tasks/{task_id}").json()["state"] == "COMPLETED"
    with pytest.raises(ValueError, match="no pending merge"):
        run(merge)


def test_settings_actions_are_limited_to_safe_values(client, tmp_path):
    repo = calculator(tmp_path / "calc")
    client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]})
    _, actions, problems = support.parse('```cerebra-actions\n[{"action": "set_test_commands", "project": "Calc", "test_commands": [["npm", "test"]]},'
                                         '{"action": "set_test_commands", "project": "Calc", "test_commands": [["powershell", "-c", "rm -r C:/"]]},'
                                         '{"action": "set_default_models", "implementer": "catalog:claude:opus", "planner": "auto"}]\n```')
    assert len(actions) == 2 and "standard runners" in problems[0]
    run = client.app.state.chats.executor
    assert "npm test" in run(actions[0])
    assert client.get("/api/overview").json()["projects"][0]["test_commands"] == [["npm", "test"]]
    assert "implementer catalog:claude:opus" in run(actions[1])
    for unsafe in ({"action": "answer_approval", "task": "abcdef12", "kind": "full_access"}, {"action": "enable_full_access"}, {"action": "retry_task", "task": "abcdef12", "instructions": "x"}):
        with pytest.raises(ValueError):
            support.validate(unsafe)
