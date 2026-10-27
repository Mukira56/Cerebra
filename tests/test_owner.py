"""About you: the owner's details reach Support, the Council and coding runs (only while sharing is on).
The owner asked Support to finish their portfolio "with my GitHub, LinkedIn and email", and Cerebra had none of them."""
import time

import pytest

from ai_hq import owner
from ai_hq.agents import AgentResult
from fakes import FixtureRegistry
from test_product_api import calculator, client, enable_agents  # noqa: F401  (client is a fixture)

ME = {"name": "Godfrey Mukira", "headline": "Software engineer", "email": "me@example.com", "github": "Mukira56",
      "linkedin": "https://www.linkedin.com/in/example", "bio": "I build AI tools.", "preferences": "Dark themes, plain words."}


class Capture(FixtureRegistry):
    def __init__(self):
        super().__init__()
        self.prompts = []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        return AgentResult(True, "Noted.")


def test_saving_validates_and_sharing_can_be_turned_off(client):  # noqa: F811
    assert client.put("/api/owner", json={"email": "not an email"}).status_code == 400
    assert client.put("/api/owner", json={"github": "bad name!"}).status_code == 400
    assert client.put("/api/owner", json={"bio": "x" * 1600}).status_code == 400
    saved = client.put("/api/owner", json=ME).json()
    assert saved["github"] == "Mukira56" and saved["share"] is True and client.get("/api/owner").json()["name"] == "Godfrey Mukira"
    with client.app.state.db.Session() as session:
        text = owner.brief(session)
    assert "Godfrey Mukira" in text and "Mukira56" in text and "never invent" in text
    client.put("/api/owner", json={"share": False})
    with client.app.state.db.Session() as session:
        assert owner.brief(session) == ""
    assert client.get("/api/owner").json()["github"] == "Mukira56"  # kept, just not shared


def test_support_the_council_and_coding_runs_receive_the_details(client, tmp_path):  # noqa: F811
    enable_agents(client)
    client.put("/api/owner", json=ME)
    registry = Capture()
    client.app.state.supervisor.registry = registry
    conversation = client.post("/api/chats", json={"profile": "codex"}).json()["id"]
    client.post(f"/api/chats/{conversation}/messages", json={"text": "Finish my portfolio with my real details"})
    for _ in range(200):
        if not client.get(f"/api/chats/{conversation}").json()["busy"]:
            break
        time.sleep(0.05)
    assert "ABOUT THE OWNER" in registry.prompts[-1] and "https://www.linkedin.com/in/example" in registry.prompts[-1]
    from ai_hq.council import project_scope
    from ai_hq.models import Project
    repo = calculator(tmp_path / "site")
    project = client.post("/api/projects", json={"name": "Site", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    with client.app.state.db.Session() as session:
        assert "Godfrey Mukira" in project_scope(session.get(Project, project["id"]), session, "About page")
    supervisor = client.app.state.supervisor
    task = supervisor.propose(project["id"], "Write an About section", allowed_paths=["calculator.py"])
    supervisor.approve_plan(task.id); supervisor.start(task.id)
    consent = next(row for row in client.get(f"/api/tasks/{task.id}").json()["approvals"] if row["kind"] == "live_execution")
    client.post(f"/api/approvals/{consent['id']}", json={"approve": True})
    supervisor.run_until_idle()
    coding = [request for name, request in registry.requests if getattr(request, "role", "") == "implement"]
    assert coding and "Mukira56" in coding[0].description and "Dark themes" in coding[0].description
    reviews = [request for name, request in registry.requests if getattr(request, "role", "") == "review"]
    assert reviews and "ABOUT THE OWNER" not in reviews[0].description  # the reviewer doesn't need it
