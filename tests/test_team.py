"""Who does the work: the owner switches a task's planner, coder or reviewer between Codex and Claude models,
and the work continues from where it stopped (straight away when it was waiting for usage)."""
import pytest

from ai_hq.agents import AgentResult
from fakes import FixtureRegistry
from test_supervisor import hq, proposed, ready  # noqa: F401  (hq is a fixture)
from test_product_api import calculator, client, enable_agents  # noqa: F401


class CodexOutOfUsage(FixtureRegistry):
    """Codex has no usage left; Claude works."""
    def execute(self, name, request, cancel_event=None):
        if name == "codex":
            self.requests.append((name, request))
            return AgentResult(False, "", error="rate_limited: You've hit your usage limit. Try again in 3 hours.")
        return super().execute(name, request, cancel_event)


def models(supervisor, task_id):
    task = supervisor.get(task_id)
    return {role: value["provider"] for role, value in task.results["models"].items()}, task


def test_switching_the_coder_keeps_the_review_independent(hq):
    supervisor = hq[0]
    task = proposed(hq)
    before, stored = models(supervisor, task.id)
    new = "codex" if before["implementer"] == "claude" else "claude"
    supervisor.reassign(task.id, "implementer", "switch")
    after, stored = models(supervisor, task.id)
    assert after["implementer"] == new == stored.assigned_agent and after["reviewer"] != new and stored.reviewer == after["reviewer"]
    assert stored.results["handoffs"][-1]["reason"] == "chosen by the owner"
    with pytest.raises(ValueError, match="different AI company"):
        supervisor.reassign(task.id, "reviewer", f"catalog:{new}:")
    supervisor.reassign(task.id, "planner", "switch")
    assert models(supervisor, task.id)[0]["planner"] != before["planner"]


class Outage(FixtureRegistry):
    """Providers in `out` have no usage left; the rest work."""
    def __init__(self, out):
        super().__init__()
        self.out = set(out)

    def execute(self, name, request, cancel_event=None):
        self.requests.append((name, request))
        if name in self.out:
            return AgentResult(False, "", error="rate_limited: You've hit your usage limit. Try again in 3 hours.")
        result = super().execute(name, request, cancel_event)
        self.requests.pop()  # FixtureRegistry records it too
        return result


def test_codex_out_of_usage_owner_moves_everything_to_claude_and_it_finishes(hq):
    from test_supervisor import consent
    supervisor = hq[0]
    task = proposed(hq)
    for role in ("implementer", "planner"):
        supervisor.reassign(task.id, role, "catalog:codex:")  # Codex plans and codes, Claude reviews
    supervisor.registry = Outage({"codex", "claude"})  # nobody has usage: the task waits
    supervisor.approve_plan(task.id); consent(hq, task.id)
    supervisor.run_until_idle()
    assert supervisor.get(task.id).results["blocked_reason"] == "waiting_for_usage"
    supervisor.registry = Outage({"codex"})  # Claude's usage is back; Codex's isn't
    supervisor._unavailable["codex"] = float("inf")
    supervisor.reassign(task.id, "planner", "catalog:claude:")
    supervisor.reassign(task.id, "implementer", "catalog:claude:")  # the reviewer moves to Codex, which is out
    from ai_hq.models import Event
    with hq[3].Session() as session:
        said = [event.message for event in session.query(Event).filter(Event.task_id == task.id, Event.kind == "models")]
    assert any("Codex is out of usage, so the review waits" in message for message in said), said
    supervisor.reassign(task.id, "reviewer", "catalog:claude:", allow_same_company=True)  # the owner accepts Claude reviewing Claude
    supervisor.run_until_idle()
    finished = supervisor.get(task.id)
    assert finished.state == "AWAITING_APPROVAL", finished.results.get("error")
    assert finished.assigned_agent == finished.reviewer == "claude" and finished.results["same_company_review"] is True
    assert {name for name, request in supervisor.registry.requests if getattr(request, "role", "") in {"implement", "review"}} == {"claude"}


def test_the_team_route_and_its_refusals(client, tmp_path):  # noqa: F811
    enable_agents(client)
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix addition", "allowed_paths": ["calculator.py"]}).json()
    coder = client.get(f"/api/tasks/{task['id']}").json()["results"]["models"]["implementer"]["provider"]
    response = client.post(f"/api/tasks/{task['id']}/team", json={"role": "reviewer", "choice": f"catalog:{coder}:"})
    assert response.status_code == 400 and "different AI company" in response.json()["detail"]
    updated = client.post(f"/api/tasks/{task['id']}/team", json={"role": "implementer", "choice": "switch"}).json()
    assert updated["results"]["models"]["implementer"]["provider"] != coder
    assert any("You made" in event["message"] for event in client.get(f"/api/tasks/{task['id']}").json()["events"])
    assert client.post(f"/api/tasks/{task['id']}/team", json={"role": "boss", "choice": "switch"}).status_code == 422
    client.post(f"/api/tasks/{task['id']}/cancel")
    assert client.post(f"/api/tasks/{task['id']}/team", json={"role": "planner", "choice": "switch"}).status_code == 400
