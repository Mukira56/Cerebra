"""Support chat: workspace brief, validated actions, and running them by click or automatically. Fixture agents only."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from ai_hq import support
from ai_hq.agents import AgentResult
from ai_hq.api import create_app
from ai_hq.config import Settings
from fakes import FixtureRegistry
from test_product_api import KEY, calculator, enable_agents

ANSWER = """Here's the plan.

```cerebra-actions
[{"action": "create_project", "name": "Booking site", "test_commands": [["npm", "test"]]},
 {"action": "create_task", "project": "Booking site", "description": "Build the booking calendar page", "requirements": ["Week view"]},
 {"action": "create_project", "name": "Evil", "test_commands": [["powershell", "-c", "Remove-Item C:/ -Recurse"]]},
 {"action": "run_shell", "command": "whoami"}]
```"""


class SupportRegistry(FixtureRegistry):
    def __init__(self, answer):
        super().__init__()
        self.answer, self.prompts = answer, []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        return AgentResult(True, self.answer)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = SupportRegistry(ANSWER)
    app.state.supervisor._refresh_registry = lambda: None
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def ask(client, text, conversation=None):
    conversation = conversation or client.post("/api/chats", json={"profile": "codex"}).json()["id"]
    assert client.post(f"/api/chats/{conversation}/messages", json={"text": text}).status_code == 202
    deadline = time.monotonic() + 180  # automatic actions create projects in Git; slow on a loaded machine
    while time.monotonic() < deadline:
        state = client.get(f"/api/chats/{conversation}").json()
        if not state["busy"]:
            return conversation, state
        time.sleep(0.05)
    raise AssertionError("no answer")


def test_parse_keeps_only_valid_actions():
    visible, actions, problems = support.parse(ANSWER)
    assert visible == "Here's the plan." and [a["action"] for a in actions] == ["create_project", "create_task"]
    assert len(problems) == 2 and any("standard runners" in p for p in problems)
    assert support.parse("```cerebra-actions\nnot json```")[2] == ["An action block was not valid JSON and was ignored."]
    with pytest.raises(ValueError):
        support.validate({"action": "start_task", "task": "../../etc"})


def test_brief_reports_real_status_and_failures(client, tmp_path):
    enable_agents(client)
    repo = calculator(tmp_path / "estate")
    project = client.post("/api/projects", json={"name": "EstatePilot", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition"}).json()
    client.app.state.supervisor._fail(task["id"], "Codex exited with code 1: rate limited")
    _, state = ask(client, "Where are we in estatepilot and why has it failed?")
    prompt = client.app.state.supervisor.registry.prompts[-1]
    assert "EstatePilot" in prompt and task["id"][:8] in prompt and "rate limited" in prompt and "FAILED" in prompt
    assert "Cerebra Support" in prompt and state["messages"][1]["content"].startswith("Here's the plan.")


def test_proposed_actions_run_on_click_through_the_supervisor(client):
    _, state = ask(client, "Build me a booking site")
    actions = state["messages"][1]["actions"]
    assert [a["status"] for a in actions] == ["proposed", "proposed"] and "Ignored an action" in state["messages"][1]["content"]
    assert not client.get("/api/overview").json()["projects"]  # nothing happens until the user clicks
    done = client.post(f"/api/chats/actions/{actions[0]['id']}", json={"run": True}).json()
    assert done["status"] == "done" and "Created the project Booking site" in done["result"]
    task = client.post(f"/api/chats/actions/{actions[1]['id']}", json={"run": True}).json()
    assert task["status"] == "done" and "Created task" in task["result"]
    overview = client.get("/api/overview").json()
    assert [p["name"] for p in overview["projects"]] == ["Booking site"] and overview["projects"][0]["test_commands"] == [["npm", "test"]]
    assert overview["tasks"][0]["state"] == "AWAITING_APPROVAL"  # the plan gate is unchanged
    assert client.post(f"/api/chats/actions/{actions[0]['id']}", json={"run": True}).status_code == 400  # runs once


def test_act_automatically_runs_actions_without_a_click(client):
    assert client.put("/api/support", json={"act_automatically": True}).json()["act_automatically"]
    _, state = ask(client, "Build me a booking site")
    assert [a["status"] for a in state["messages"][1]["actions"]] == ["done", "done"]
    assert len(client.get("/api/overview").json()["tasks"]) == 1


def test_failed_action_is_reported_not_raised(client):
    client.app.state.supervisor.registry.answer = '```cerebra-actions\n[{"action": "start_task", "task": "abcdef12"}]\n```'
    _, state = ask(client, "start it")
    action = state["messages"][1]["actions"][0]
    result = client.post(f"/api/chats/actions/{action['id']}", json={"run": True}).json()
    assert result["status"] == "failed" and "No single task" in result["result"]


def test_no_limit_settings(client, tmp_path):
    import sys
    from ai_hq.processes import ProcessRunner
    saved = client.patch("/api/settings", json={"agent_timeout": 0, "test_timeout": 0, "max_retries": -1}).json()
    assert (saved["agent_timeout"], saved["test_timeout"], saved["max_retries"]) == (0, 0, -1)
    supervisor = client.app.state.supervisor
    assert supervisor.settings.agent_timeout == 0
    assert ProcessRunner().run([sys.executable, "-c", "print('ok')"], tmp_path, None).stdout.strip() == "ok"
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition"}).json()
    assert task["max_retries"] == -1 and "until the work passes" in json.dumps(task["plan"])
    assert client.patch("/api/settings", json={"max_retries": -2}).status_code == 422


def test_a_reply_never_stays_stuck_on_thinking(client):
    """If an answer can no longer arrive (no answer is running), reading the chat repairs it instead of spinning forever."""
    from ai_hq.models import ChatMessage, uid
    conversation = client.post("/api/chats", json={"profile": "codex"}).json()["id"]
    with client.app.state.db.Session.begin() as session:
        session.add(ChatMessage(id=uid(), conversation_id=conversation, role="assistant", status="pending", provider="codex"))
    state = client.get(f"/api/chats/{conversation}").json()
    assert not state["busy"] and state["messages"][0]["status"] == "failed" and "interrupted" in state["messages"][0]["error"]
