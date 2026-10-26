"""Phase A: plans survive handoff unchanged, every path makes exactly one linked task, and Support acts on real results.
Scripted fixture models only; no real CLI runs."""
import json
import threading
import time

import pytest

from ai_hq.agents import AgentResult
from ai_hq.models import ActionRecord, Dependency, PlanItem, Task
from test_council import AGREED, client, wait  # noqa: F401  (fixture)

pytestmark = pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")

PLAN = {"summary": "Fix add() first, then validate input.",
        "solution": {"title": "Fix then validate", "description": "Correct the operator, then reject non-numbers.", "why": "Smallest safe change", "steps": ["Fix", "Validate"]},
        "tasks": [{"title": "Fix addition", "description": "add() subtracts; make it add.", "executor": "codex", "requirements": ["Keep the signature add(a, b)"],
                   "acceptance_criteria": ["test_add passes"]},
                  {"title": "Add input validation", "description": "Reject non-numbers with TypeError.", "executor": "claude",
                   "requirements": ["Raise TypeError for text", "No new dependencies"], "acceptance_criteria": ["test_add_rejects_text passes"], "depends_on": [1]}]}


class PlanRegistry:
    """Council turns end with PLAN; Support turns follow a script that depends on the results Cerebra feeds back."""
    def __init__(self, base):
        self.base, self.support_prompts = base, []

    def __getattr__(self, name):
        return getattr(self.base, name)

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        if prompt.startswith("You are Cerebra Support"):
            return self.support(prompt)
        if "closing turn" in prompt or "has written the conclusion" in prompt:
            return AgentResult(True, f"Done.\n```cerebra-council\n{json.dumps(PLAN)}\n```")
        return AgentResult(True, f"{name}: reviewed and improved.\nSTATUS: AGREED")

    def support(self, prompt):
        self.support_prompts.append(prompt)
        body = prompt.rsplit("\n\nYou:", 1)[0]
        latest = body[max(body.rfind("\n\nUser: "), body.rfind("\n\nCerebra (action results): ")):]
        if not latest.startswith("\n\nCerebra (action results): "):
            items = [line.split(":")[-1].strip() for line in latest.splitlines() if line.strip().startswith("Plan item id:")]
            return AgentResult(True, "Creating the tasks.\n```cerebra-actions\n" + json.dumps([{"action": "create_plan_task", "item": item} for item in items]) + "\n```")
        results = json.loads(latest.split("ACTION RESULTS (recorded by Cerebra; authoritative):\n")[-1].split("\nContinue with")[0])
        created = [item["affected"]["task_id"] for item in results if item.get("affected", {}).get("task_id") and item["action"] == "create_plan_task"]
        if created:
            return AgentResult(True, "Approving the plans.\n```cerebra-actions\n" + json.dumps([{"action": "approve_plan", "task": task} for task in created]) + "\n```")
        return AgentResult(True, "Both tasks are planned and waiting for the agents' run approval. Nothing more to do now.")


@pytest.fixture
def planned(client):
    registry = PlanRegistry(client.app.state.supervisor.registry)
    client.app.state.supervisor.registry = registry
    client.registry = registry
    return client


def meeting(client, send=False):
    return wait(client, client.post("/api/council", json={"project_id": client.project["id"], "topic": "Plan", "rounds": 1, "send_to_support": send}).json()["id"])


def items_of(client, meeting_id):
    plan_id = client.get(f"/api/council/{meeting_id}").json()["plan_id"]
    return client.app.state.work.plan(plan_id)["items"]


def test_requirements_criteria_roles_and_dependencies_survive_unchanged(planned):
    state = meeting(planned)
    items = items_of(planned, state["id"])
    assert [item["requirements"] for item in items] == [["Keep the signature add(a, b)"], ["Raise TypeError for text", "No new dependencies"]]
    assert items[1]["acceptance_criteria"] == ["test_add_rejects_text passes"] and items[1]["depends_on"] == [items[0]["id"]]
    assert (items[0]["implementer"], items[0]["reviewer"], items[1]["implementer"]) == ("codex", "claude", "claude")
    task_id = planned.post(f"/api/council/{state['id']}/proposals/1/task").json()["task_id"]
    task = planned.get(f"/api/tasks/{task_id}").json()
    assert task["requirements"] == items[1]["requirements"] and task["acceptance_criteria"] == items[1]["acceptance_criteria"]
    with planned.app.state.db.Session() as session:  # the dependency was created first and linked
        first = session.get(PlanItem, items[0]["id"]).task_id
        assert first and session.get(Dependency, (task_id, first)) is not None


def test_owner_click_and_support_handoff_make_one_linked_task(planned):
    state = meeting(planned)
    clicked = planned.post(f"/api/council/{state['id']}/proposals/0/task").json()["task_id"]
    planned.put("/api/support", json={"act_automatically": True})
    planned.post(f"/api/council/{state['id']}/support")
    chat_id = planned.get(f"/api/council/{state['id']}").json()["support_chat"]
    for _ in range(400):
        chat = planned.get(f"/api/chats/{chat_id}").json()
        if not chat["busy"] and len(chat["messages"]) >= 4:
            break
        time.sleep(0.05)
    sent = chat["messages"][0]["content"]
    assert "Requirement: Raise TypeError for text" in sent and "Plan item id:" in sent and "Starts after: task 1" in sent
    items = items_of(planned, state["id"])
    assert items[0]["task_id"] == clicked  # Support's create_plan_task returned the owner's task
    with planned.app.state.db.Session() as session:
        linked = [task for task in session.query(Task).all() if (task.results or {}).get("plan")]
        assert sorted(task.id for task in linked) == sorted(item["task_id"] for item in items) and len(linked) == 2


def test_concurrent_requests_and_retries_create_one_task(planned):
    items = items_of(planned, meeting(planned)["id"])
    work, results = planned.app.state.work, []
    threads = [threading.Thread(target=lambda: results.append(work.item_task(items[0]["id"], "support")[0])) for _ in range(8)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(30)
    assert len(set(results)) == 1 and len(results) == 8


def test_restart_between_creating_and_linking_reuses_the_task(planned):
    items = items_of(planned, meeting(planned)["id"])
    supervisor, work = planned.app.state.supervisor, planned.app.state.work
    orphan = supervisor.propose(planned.project["id"], "Fix addition: add() subtracts; make it add.")  # created, then "crashed" before linking
    with planned.app.state.db.Session.begin() as session:
        stored = session.get(Task, orphan.id)
        stored.results = {**stored.results, "plan": {"plan_id": items[0]["plan_id"], "item_id": items[0]["id"], "version": 1}}
    task_id, created = work.item_task(items[0]["id"], "support")
    assert (task_id, created) == (orphan.id, False)


def test_support_uses_the_real_ids_it_is_given_and_every_action_is_recorded(planned):
    state = meeting(planned)
    planned.put("/api/support", json={"act_automatically": True})
    planned.post(f"/api/council/{state['id']}/support")
    chat_id = planned.get(f"/api/council/{state['id']}").json()["support_chat"]
    for _ in range(400):
        chat = planned.get(f"/api/chats/{chat_id}").json()
        if not chat["busy"]:
            break
        time.sleep(0.05)
    roles = [message["role"] for message in chat["messages"]]
    assert roles == ["user", "assistant", "cerebra", "assistant", "cerebra", "assistant"]  # act -> results -> act -> results -> done
    items = items_of(planned, state["id"])
    for item in items:  # approve_plan used the ids Cerebra reported, so both plans are approved
        assert planned.get(f"/api/tasks/{item['task_id']}").json()["approved"]
    with planned.app.state.db.Session() as session:
        records = session.query(ActionRecord).order_by(ActionRecord.created_at).all()
        assert [record.kind for record in records] == ["create_plan_task", "create_plan_task", "approve_plan", "approve_plan"]
        assert all(record.status == "done" and record.affected.get("task_id") for record in records)
        assert {record.affected["task_id"] for record in records} == {item["task_id"] for item in items}


def test_stop_ends_the_action_loop(planned):
    state = meeting(planned)
    planned.put("/api/support", json={"act_automatically": True})
    original = planned.registry.support
    def slow(prompt):
        time.sleep(0.5)
        return original(prompt)
    planned.registry.support = slow
    planned.post(f"/api/council/{state['id']}/support")
    chat_id = planned.get(f"/api/council/{state['id']}").json()["support_chat"]
    planned.post(f"/api/chats/{chat_id}/stop")
    for _ in range(400):
        chat = planned.get(f"/api/chats/{chat_id}").json()
        if not chat["busy"]:
            break
        time.sleep(0.05)
    assert [message["role"] for message in chat["messages"]].count("cerebra") <= 1  # no further rounds after Stop
