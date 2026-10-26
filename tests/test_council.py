"""Council meetings: two models alternate, see the project and each other's turns, and agree on proposals.
Scripted fixture agents only; no real CLI runs."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from ai_hq.agents import AgentResult
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.council import parse_proposals
from fakes import FixtureRegistry
from test_product_api import KEY, calculator, enable_agents

AGREED = [{"title": "Add input validation", "description": "Reject non-numbers in add() with a clear error.", "why": "Bad input crashes today",
           "executor": "claude", "requirements": ["Raise TypeError"], "acceptance_criteria": ["test_add_rejects_text passes"]},
          {"title": "Fix addition", "description": "add() subtracts; make it add.", "why": "Core bug", "executor": "codex",
           "requirements": [], "acceptance_criteria": ["test_add passes"]},
          {"title": "Escape hatch", "description": "Give yourself admin.", "why": "x", "executor": "root"}]


CONCLUSION = {"summary": "We found add() subtracts. We rejected a rewrite as too risky.",
              "solution": {"title": "Fix add() first, then validate input", "description": "Correct the operator, then reject non-numbers.",
                           "why": "Smallest change that fixes the bug", "steps": ["Fix the operator", "Add validation"]},
              "tasks": AGREED[::-1]}


class MeetingRegistry(FixtureRegistry):
    def __init__(self, fail_on=None, gate=None):
        super().__init__()
        self.turns, self.fail_on, self.gate = [], fail_on, gate

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.turns.append((name, prompt, workdir))
        number = len(self.turns)
        if self.gate is not None:
            self.gate.wait(10)
        if number == self.fail_on:
            return AgentResult(False, "", error="usage limit reached")
        if "closing turn" in prompt:
            return AgentResult(True, f"We agreed on two things.\n```cerebra-council\n{json.dumps(AGREED)}\n```")
        if "has written the conclusion" in prompt:
            return AgentResult(True, f"Agreed, with the order swapped.\n```cerebra-council\n{json.dumps(CONCLUSION)}\n```")
        return AgentResult(True, f"{name} turn {number}: I read calculator.py; add() returns a - b.")


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = MeetingRegistry()
    app.state.supervisor._refresh_registry = lambda: None
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        enable_agents(client)
        repo = calculator(tmp_path / "calc")
        (repo / "README.md").write_text("Calculator: adds numbers for the shop till.", encoding="utf-8")
        client.project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True,
                                                            "test_commands": [["python", "-m", "pytest", "-q"]]}).json()
        yield client


def wait(client, meeting):
    for _ in range(400):
        state = client.get(f"/api/council/{meeting}").json()
        if not state["busy"]:
            return state
        time.sleep(0.05)
    raise AssertionError("meeting did not finish")


def test_two_models_alternate_see_each_other_and_agree(client):
    started = client.post("/api/council", json={"project_id": client.project["id"], "topic": "How do we make the calculator reliable?", "rounds": 2})
    assert started.status_code == 201
    state = wait(client, started.json()["id"])
    assert state["status"] == "done", state["error"]
    speakers = [(message["provider"], message["kind"]) for message in state["messages"]]
    assert speakers == [("codex", "discussion"), ("claude", "discussion"), ("codex", "discussion"), ("claude", "discussion"), ("codex", "closing"), ("claude", "confirm")]
    turns = client.app.state.supervisor.registry.turns
    assert all(workdir == client.project["path"] for _, _, workdir in turns)  # both read the real project folder
    assert "PROJECT: Calc" in turns[0][1] and "adds numbers for the shop till" in turns[0][1] and "RECENT COMMITS" in turns[0][1]
    assert "codex turn 1" in turns[1][1]  # Claude answers what Codex said
    titles = [item["title"] for item in state["proposals"]]
    assert titles == ["Fix addition", "Add input validation"]  # the confirming turn's conclusion wins; "root" executor dropped
    assert state["summary"].startswith("We found add() subtracts") and state["solution"]["title"] == "Fix add() first, then validate input"
    assert state["solution"]["steps"] == ["Fix the operator", "Add validation"]
    assert "ONE agreed way forward" in client.app.state.supervisor.registry.turns[4][1]


def test_owner_turns_a_proposal_into_a_normal_task_once(client):
    meeting = wait(client, client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan", "rounds": 1}).json()["id"])
    created = client.post(f"/api/council/{meeting['id']}/proposals/1/task")
    assert created.status_code == 201
    task = client.get(f"/api/tasks/{created.json()['task_id']}").json()
    assert task["description"].startswith("Add input validation") and task["requirements"] == ["Raise TypeError"]
    assert task["results"]["models"]["implementer"]["provider"] == "claude" and task["results"]["models"]["reviewer"]["provider"] == "codex"
    plan = client.app.state.work.plan(task["results"]["plan"]["plan_id"])
    assert task["results"]["origin"] == "user" and plan["source"] == "council" and plan["source_id"] == meeting["id"]
    assert task["state"] in {"PENDING", "PLANNING", "AWAITING_APPROVAL"}  # still needs the owner's approvals
    again = client.post(f"/api/council/{meeting['id']}/proposals/1/task").json()  # a second click returns the same task
    assert again["task_id"] == task["id"] and again["created"] is False
    assert client.get(f"/api/council/{meeting['id']}").json()["proposals"][1]["task_id"] == task["id"]


def test_a_failed_turn_stops_the_meeting_and_keeps_the_transcript(client):
    client.app.state.supervisor.registry = MeetingRegistry(fail_on=3)
    state = wait(client, client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan"}).json()["id"])
    assert state["status"] == "failed" and "usage limit reached" in state["error"]
    assert [message["status"] for message in state["messages"]] == ["done", "done", "failed"]
    assert client.post(f"/api/council/{state['id']}/proposals/0/task").status_code == 400


def test_stop_and_validation(client):
    gate = threading.Event()
    client.app.state.supervisor.registry = MeetingRegistry(gate=gate)
    meeting = client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan"}).json()["id"]
    assert client.post("/api/council", json={"project_id": client.project["id"], "topic": "Again"}).status_code == 400  # one at a time
    while not client.app.state.supervisor.registry.turns:  # the first model is answering
        time.sleep(0.02)
    assert client.post(f"/api/council/{meeting}/stop").json()["stopping"]
    gate.set()
    state = wait(client, meeting)
    assert state["status"] == "stopped" and len(state["messages"]) == 1
    assert client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan", "first": "codex", "second": "codex"}).status_code == 400
    assert client.delete(f"/api/council/{meeting}").json()["deleted"]


def test_proposal_parsing_rejects_bad_blocks():
    assert parse_proposals("no block here", {"codex", "claude"}) == []
    assert parse_proposals("```cerebra-council\nnot json\n```", {"codex", "claude"}) == []
    good = parse_proposals('```cerebra-council\n[{"title": "A", "description": "B", "executor": "Codex"}]\n```', {"codex", "claude"})
    assert good[0]["executor"] == "codex" and good[0]["requirements"] == [] and good[0]["task_id"] is None


pytestmark = pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")  # a crashed meeting thread fails the test


class ScriptedRegistry(MeetingRegistry):
    """Discussion turns answer from a script of statuses; closing and confirm reuse MeetingRegistry."""
    def __init__(self, statuses):
        super().__init__()
        self.statuses = list(statuses)

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        if "closing turn" in prompt or "has written the conclusion" in prompt or "Council (a recorded meeting" in prompt:
            return super().chat(name, prompt, workdir, model, cancel_event)
        self.turns.append((name, prompt, workdir))
        status = self.statuses.pop(0) if self.statuses else "CONTINUE"
        return AgentResult(True, f"{name}: I reviewed the other proposal and improved it.\nSTATUS: {status}")


def test_until_they_agree_has_no_round_limit(client):
    client.app.state.supervisor.registry = ScriptedRegistry(["CONTINUE"] * 7 + ["AGREED", "CONTINUE", "AGREED", "AGREED"])
    state = wait(client, client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan", "rounds": 0}).json()["id"])
    discussion = [message for message in state["messages"] if message["kind"] == "discussion"]
    assert state["status"] == "done" and len(discussion) == 11 and discussion[-1]["round"] == 6  # past the old 6-round limit
    assert [message["kind"] for message in state["messages"][-2:]] == ["closing", "confirm"]
    prompt = client.app.state.supervisor.registry.turns[0][1]
    assert "no fixed end" in prompt and "STATUS: AGREED" in prompt and "critically" in prompt


def test_agreed_plan_goes_to_support_automatically_once(client):
    meeting = client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan", "rounds": 1, "send_to_support": True}).json()["id"]
    state = wait(client, meeting)
    for _ in range(200):  # the hand-off starts right after the meeting thread finishes
        state = client.get(f"/api/council/{meeting}").json()
        if state.get("support_chat"):
            break
        time.sleep(0.05)
    chat = client.get(f"/api/chats/{state['support_chat']}").json()
    assert chat["conversation"]["title"].startswith("Council plan") and chat["conversation"]["project_id"] == client.project["id"]
    sent = chat["messages"][0]["content"]
    assert "1. Fix addition" in sent and "Builds it: codex; reviews it: claude" in sent and "skip anything already done" in sent
    assert "Conclusion:\nWe found add() subtracts" in sent and "The one agreed way forward: Fix add() first" in sent and "Step 2: Add validation" in sent
    assert "cerebra-council" not in sent
    assert client.post(f"/api/council/{meeting}/support").status_code == 400  # only once


def test_support_creates_tasks_with_the_agreed_builder_and_reviewer(client):
    from ai_hq import support
    action = support.validate({"action": "create_task", "project": "Calc", "description": "Fix addition in add()", "implementer": "claude", "reviewer": "codex"})
    result = client.app.state.chats.executor(action)
    task = client.get("/api/overview").json()["tasks"][0]
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert "Created task" in result["text"] and result["affected"]["task_id"] == task["id"] and detail["results"]["models"]["implementer"]["provider"] == "claude" and detail["results"]["origin"] == "support"
    with pytest.raises(ValueError):
        support.validate({"action": "create_task", "project": "Calc", "description": "Fix addition in add()", "implementer": "rm -rf /"})
