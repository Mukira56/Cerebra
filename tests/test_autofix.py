"""Auto-fix: failed tasks go to the Assistant by itself, hard ones to the Council, with the owner's grant and a per-task Stop.
Scripted fixture models only; no real CLI runs."""
import json
import re
import sys
import time

import pytest

from ai_hq.agents import AgentResult
from fakes import FixtureRegistry
from test_product_api import calculator, client, enable_agents  # noqa: F401  (client is a fixture)

pytestmark = pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")

SOLUTION = {"summary": "The coder keeps importing a misspelled module. Fix the import and the operator.",
            "solution": {"title": "Correct calculator.py", "description": "Return a + b in add().", "why": "It is the root cause", "steps": ["Edit add()", "Run the tests"]},
            "tasks": [{"title": "Fix add", "description": "Return a + b in calculator.py.", "executor": "codex", "requirements": ["Keep add(a, b)"], "acceptance_criteria": ["test_add passes"]}]}


class Team(FixtureRegistry):
    """The coder fails `failures` times; Support retries the task it is told about; the Council agrees SOLUTION."""
    def __init__(self, failures=1):
        super().__init__()
        self.failures, self.access, self.support_prompts, self.council_prompts = failures, [], [], []

    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            self.access.append(self.full_access)
            if self.failures:
                self.failures -= 1
                self.requests.append((name, request))
                return AgentResult(False, "Traceback: ModuleNotFoundError: No module named 'calcualtor'", error="agent exited with code 1: ModuleNotFoundError")
        return super().execute(name, request, cancel_event)

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        if prompt.startswith("You are Cerebra Support"):
            self.support_prompts.append(prompt)
            latest = prompt.rsplit("\n\nYou:", 1)[0]
            latest = latest[latest.rfind("\n\nCerebra ("):]
            if latest.startswith("\n\nCerebra (action results)"):
                return AgentResult(True, "The retry is running. Waiting for its tests and review.")
            task = re.search(r"task ([0-9a-f]{8})", latest, re.I).group(1)
            fix = "Council's way: " if "COUNCIL SOLUTION" in latest else ""
            return AgentResult(True, "Found it.\n```cerebra-actions\n" + json.dumps([{"action": "retry_task", "task": task,
                               "instructions": fix + "The import is misspelled; in calculator.py make add return a + b, then run the tests."}]) + "\n```")
        self.council_prompts.append(prompt)
        if "closing turn" in prompt or "has written the conclusion" in prompt:
            return AgentResult(True, f"Done.\n```cerebra-council\n{json.dumps(SOLUTION)}\n```")
        return AgentResult(True, f"{name}: the root cause is the misspelled import.\nSTATUS: AGREED")


def setup(client, tmp_path, failures=1, **policy):
    enable_agents(client)
    client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True})
    supervisor = client.app.state.supervisor
    supervisor.registry = Team(failures)
    supervisor._refresh_registry()
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
    if policy:
        response = client.put("/api/auto-fix", json=policy)
        assert response.status_code == 200, response.text
    return task["id"]


def settle(client, task_id, rounds=60):
    """Let the fix chat, the Council and the supervisor run until nothing changes."""
    supervisor, autofix = client.app.state.supervisor, client.app.state.autofix
    for _ in range(rounds):
        busy = client.app.state.chats._busy or client.app.state.council._running
        if not busy:
            autofix.scan()
            supervisor.run_until_idle()
            if not (client.app.state.chats._busy or client.app.state.council._running):
                state = client.get(f"/api/tasks/{task_id}").json()
                if state["state"] not in {"FAILED", "BLOCKED"} or (state["results"].get("auto_fix") or {}).get("status") in {"gave_up", "stopped"}:
                    return state
        time.sleep(0.1)
    return client.get(f"/api/tasks/{task_id}").json()


def test_a_failed_task_is_fixed_by_the_assistant_with_the_owners_full_access(client, tmp_path):
    task_id = setup(client, tmp_path)
    assert client.app.state.autofix.scan() == []  # off by default: nothing starts
    client.put("/api/auto-fix", json={"enabled": True, "full_access": True})
    listed = client.get("/api/auto-fix/tasks").json()
    assert [(item["id"], item["selected"]) for item in listed] == [(task_id, False)]  # switching it on starts only ticked tasks
    assert client.app.state.autofix.scan() == []
    assert client.post("/api/auto-fix/tasks", json={"task_ids": [task_id], "enabled": True}).status_code == 200  # the fix starts at once
    assert client.get(f"/api/tasks/{task_id}").json()["results"]["auto_fix"]["chosen"] is True
    task = settle(client, task_id)
    assert task["state"] == "AWAITING_APPROVAL" and task["results"]["auto_fix"]["attempts"] == 1
    assert task["results"]["origin"] == "user" and task["results"]["instructions_from"] == "support"  # true origin kept
    assert client.app.state.supervisor.registry.access == [True, True]  # the fix run kept the owner's Full access
    chat = client.get(f"/api/chats/{task['results']['auto_fix']['chat']}").json()
    assert chat["messages"][0]["role"] == "auto" and "AUTO-FIX" in chat["messages"][0]["content"]
    assert any("Full access for this implement run: the owner's Auto-fix permission" in event["message"] for event in task["events"])


def test_without_the_grant_fix_runs_stay_project_only(client, tmp_path):
    task_id = setup(client, tmp_path, enabled=True, scope="all")
    task = settle(client, task_id)
    assert task["state"] == "AWAITING_APPROVAL" and client.app.state.supervisor.registry.access == [True, False]


def test_full_access_grant_needs_full_access_and_revoking_applies_to_the_next_run(client, tmp_path):
    task_id = setup(client, tmp_path)
    client.post("/api/permissions/full-access", json={"enabled": False})
    assert client.put("/api/auto-fix", json={"enabled": True, "full_access": True}).status_code == 400
    client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True})
    assert client.put("/api/auto-fix", json={"enabled": True, "full_access": True, "scope": "all"}).json()["full_access_effective"] is True
    client.put("/api/auto-fix", json={"full_access": False})  # revoked before the fix runs
    settle(client, task_id)
    assert client.app.state.supervisor.registry.access == [True, False]


def test_stop_auto_fix_for_a_task(client, tmp_path):
    task_id = setup(client, tmp_path, failures=5)
    response = client.post(f"/api/tasks/{task_id}/auto-fix", json={"enabled": False})
    assert response.status_code == 200 and response.json()["stopped"] is True
    client.put("/api/auto-fix", json={"enabled": True, "council_after": 0, "scope": "all"})  # every failed task, except one the owner stopped
    assert client.app.state.autofix.scan() == []
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["state"] == "FAILED" and not client.app.state.supervisor.registry.support_prompts
    assert client.post(f"/api/tasks/{task_id}/auto-fix", json={"enabled": True}).json()["attempts"] == 0
    assert client.app.state.autofix.scan() == [task_id]  # allowed again: it starts on the current failure


def test_attempts_are_limited_and_the_task_is_handed_back(client, tmp_path):
    task_id = setup(client, tmp_path, failures=10, enabled=True, max_attempts=2, council_after=0, scope="all")
    task = settle(client, task_id)
    assert task["state"] == "FAILED" and task["results"]["auto_fix"]["status"] == "gave_up" and task["results"]["auto_fix"]["attempts"] == 2
    assert any("needs you" in event["message"] for event in task["events"])


def test_hard_failures_go_to_the_council_and_the_assistant_applies_its_solution(client, tmp_path):
    task_id = setup(client, tmp_path, failures=2, enabled=True, council_after=1, max_attempts=4, scope="all")
    task = settle(client, task_id)
    fix = task["results"]["auto_fix"]
    assert task["state"] == "AWAITING_APPROVAL" and fix["attempts"] == 2 and fix.get("council")
    meeting = client.get(f"/api/council/{fix['council']}").json()
    assert meeting["status"] == "done" and meeting["fix_task"] == task_id and "keeps failing" in meeting["topic"]
    chat = client.get(f"/api/chats/{fix['chat']}").json()
    sent = [message["content"] for message in chat["messages"] if message["role"] == "auto"]
    assert len(sent) == 2 and sent[1].startswith("COUNCIL SOLUTION") and "Correct calculator.py" in sent[1] and "Plan item id:" in sent[1]
    coding = [request for name, request in client.app.state.supervisor.registry.requests if getattr(request, "role", "") == "implement"]
    assert "Council's way" in coding[-1].description  # the last run carried out the Council's solution


def test_support_can_ask_the_council_itself(client, tmp_path):
    task_id = setup(client, tmp_path)
    run = client.app.state.chats.executor
    result = run({"action": "ask_council", "task": task_id[:8], "question": "The import keeps failing; is the module layout wrong?"})
    assert result["affected"]["task_id"] == task_id and result["next_state"] == "council"
    for _ in range(200):
        if not client.app.state.council._running:
            break
        time.sleep(0.05)
    meeting = client.get(f"/api/council/{result['affected']['council_id']}").json()
    assert meeting["status"] == "done" and "module layout" in meeting["topic"]
