"""Phase 4: profiles, gigs and case studies written by the owner's model from facts only, within each platform's limits."""
import json

from ai_hq import pitches
from ai_hq.agents import AgentResult
from ai_hq.models import Project, Task
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents


class Answer(FixtureRegistry):
    def __init__(self, answer):
        super().__init__()
        self.answer, self.prompts = answer, []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        return AgentResult(True, self.answer if isinstance(self.answer, str) else json.dumps(self.answer))


def write(client, kind, answer, task_id=None):  # noqa: F811
    model = Answer(answer)
    client.app.state.supervisor.registry = model
    client.app.state.pitch_writer.start(kind, task_id, wait=True)
    key = f"case:{task_id}" if kind == "case" else kind
    data = client.get("/api/pitches").json()
    return (data["cases"][task_id] if kind == "case" else data["kinds"][kind]), model


def test_profiles_need_the_owners_ai_switched_on(client):  # noqa: F811
    response = client.post("/api/pitches/write", json={"kind": "upwork"})
    assert response.status_code == 400 and "Switch AI agents on" in response.json()["detail"]
    enable_agents(client)
    assert client.post("/api/pitches/write", json={"kind": "myspace"}).status_code == 400


def test_an_upwork_profile_stays_inside_upworks_limits_and_uses_only_facts(client):  # noqa: F811
    enable_agents(client)
    client.put("/api/money/settings", json={"business_name": "Mukira Studio", "services": [{"name": "Business website", "price": 600}]})
    title = "Full-stack web developer building fast websites, web apps and AI tools for small businesses everywhere"
    piece, model = write(client, "upwork", {"title": title, "overview": "I build websites that turn visitors into customers."})
    assert piece["status"] == "ready" and len(piece["data"]["title"]) <= 70 and title.startswith(piece["data"]["title"])  # cut at a word
    prompt = model.prompts[-1]
    assert "Never invent clients, employers, years of experience" in prompt and "Business website: USD 600.00" in prompt and "at most 70 characters" in prompt


def test_a_fiverr_gig_has_an_i_will_title_three_packages_and_clean_tags(client):  # noqa: F811
    enable_agents(client)
    gig, _ = write(client, "fiverr", {"title": "build a fast business website", "description": "x" * 1500,
                                      "packages": [{"name": "Basic", "price": 150, "days": 3, "includes": "1 page"}, {"name": "Standard", "price": 400, "days": 7, "includes": "5 pages"},
                                                   {"name": "Premium", "price": 900, "days": 14, "includes": "10 pages and booking"}],
                                      "tags": ["website", "wordpress", "a-very-long-tag-that-is-too-long", "landing page", "small business", "extra"],
                                      "faq": [{"q": "Do you host it?", "a": "I can set up hosting in your name."}]})
    data = gig["data"]
    assert data["title"] == "I will build a fast business website" and len(data["description"]) <= 1200
    assert [item["price"] for item in data["packages"]] == [150, 400, 900] and len(data["tags"]) == 5 and all(len(tag) <= 20 for tag in data["tags"])


def test_case_studies_are_only_for_finished_work_and_become_draft_posts(client, tmp_path):  # noqa: F811
    enable_agents(client)
    with client.app.state.db.Session.begin() as session:
        session.add(Project(id="p1", name="Clinic site", path=str(tmp_path), default_branch="main", test_commands=[]))
        session.add(Task(id="t1", project_id="p1", description="Build a booking website for a dental clinic", state="COMPLETED", results={"changed_paths": ["index.html", "booking.js"]}))
        session.add(Task(id="t2", project_id="p1", description="Unfinished thing", state="FAILED"))
    finished = client.get("/api/pitches").json()["finished"]
    assert [item["id"] for item in finished] == ["t1"]
    case, model = write(client, "case", {"title": "Online booking for a dental clinic", "problem": "Patients could only book by phone.",
                                         "solution": "Built a responsive site with a booking form.", "skills": ["HTML", "JavaScript"],
                                         "post": "Built online booking for a dental clinic so patients no longer have to call."}, task_id="t1")
    assert case["status"] == "ready" and case["data"]["title"].startswith("Online booking") and "booking.js" in model.prompts[-1]
    assert "Never invent clients, results" in model.prompts[-1]
    draft = client.post("/api/pitches/case-post", json={"task_id": "t1"}).json()
    assert draft["status"] == "draft" and draft["origin"] == "ai" and "dental clinic" in draft["text"]  # still needs approval
    client.app.state.supervisor.registry = Answer("{}")
    assert client.post("/api/pitches/write", json={"kind": "case", "task_id": "t2"}).status_code == 404  # not finished


def test_the_owner_can_edit_a_piece_and_bad_answers_show_as_failed(client):  # noqa: F811
    enable_agents(client)
    write(client, "linkedin", {"headline": "Web developer", "about": "I build websites."})
    edited = client.put("/api/pitches/piece", json={"key": "linkedin", "data": {"headline": "Web & AI developer for small businesses"}}).json()
    assert edited["data"]["headline"] == "Web & AI developer for small businesses" and edited["edited"]
    failed, _ = write(client, "freelancer", "Sorry, I can't help with that.")
    assert failed["status"] == "failed" and failed["error"]
    assert pitches.parse('{"headline": "Hi", "summary": "There"}', "freelancer") == {"headline": "Hi", "summary": "There"}


def test_cerebras_own_test_projects_never_count_as_the_owners_work(client, tmp_path):  # noqa: F811
    from ai_hq import freelance
    with client.app.state.db.Session.begin() as session:
        for identifier, name, path in (("own", "Portfolio", tmp_path / "projects" / "0139d42"), ("demo", "Live validation", tmp_path / "projects" / "demo-29a4f655"),
                                       ("ready", "Cerebra readiness check", tmp_path / "readiness" / "project")):
            session.add(Project(id=identifier, name=name, path=str(path), default_branch="main", test_commands=[]))
            session.add(Task(id=f"t-{identifier}", project_id=identifier, description=f"Work on {name}", state="COMPLETED"))
    assert [item["project"] for item in client.get("/api/pitches").json()["finished"]] == ["Portfolio"]
    with client.app.state.db.Session() as session:
        facts = freelance.context(session)
    # The owner (2026-10-30): applications never present projects built in Cerebra, their own portfolio site among them.
    assert "Portfolio" not in facts and "Live validation" not in facts and "readiness" not in facts
