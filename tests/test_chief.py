"""Chief of Staff: one scheduler for the money-making workers with every run on the record, the owner's goals, and the
training set for Cerebra's own model."""
import json
from datetime import datetime, timedelta, timezone

from ai_hq import chief
from ai_hq.models import ChiefJob, FreelanceLead, SocialPost
from test_freelance import client  # noqa: F401  (client is a fixture)


def make(client, *workers):  # noqa: F811
    registry = chief.Registry()
    for key, run, minutes in workers:
        registry.add(key, key.replace("_", " ").title(), "test worker", run, minutes)
    scheduler = chief.Scheduler(client.app.state.db, registry)
    scheduler.seed()
    return registry, scheduler


def later(minutes):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def test_the_apps_money_workers_run_under_the_scheduler(client):  # noqa: F811
    assert set(client.app.state.registry.workers) >= {"auto_apply", "win_watch", "won_work"}
    jobs = {job["id"]: job for job in client.get("/api/chief").json()["jobs"]}
    assert jobs["auto_apply"]["outward"] and jobs["auto_apply"]["every_minutes"] == 10 and jobs["win_watch"]["enabled"]


def test_due_jobs_run_once_on_time_and_every_run_is_recorded(client):  # noqa: F811
    calls = []
    _, scheduler = make(client, ("finder", lambda: calls.append(1) or {"found": 3, "sources": {"freelancer": 2}}, 30))
    assert scheduler.tick() == 0 and calls == []  # not due yet
    assert scheduler.tick(later(31)) == 1 and calls == [1]
    assert scheduler.tick(later(20)) == 0 and scheduler.tick(later(31)) == 1  # the next run moved 30 minutes on from the last one
    with client.app.state.db.Session() as session:
        run = chief.runs(session, job_id="finder")[0]
        assert run["status"] == "ok" and run["result"] == "found 3 · sources: freelancer 2" and run["by"] == "schedule"


def test_a_failing_worker_is_recorded_and_never_stops_the_others(client):  # noqa: F811
    ran = []

    def broken():
        raise RuntimeError("Source down; token=sk-live-123456789012345678901234")
    _, scheduler = make(client, ("broken", broken, 10), ("steady", lambda: ran.append(1) or {"skipped": "off"}, 10))
    assert scheduler.tick(later(11)) == 2 and ran == [1]
    with client.app.state.db.Session() as session:
        results = {run["job_id"]: run for run in chief.runs(session)}
        assert results["broken"]["status"] == "failed" and "Source down" in results["broken"]["result"]
        assert "sk-live-1234" not in results["broken"]["result"]  # secrets are redacted from the record
        assert results["steady"]["status"] == "skipped" and results["steady"]["result"] == "Skipped: off"
    events = client.get("/api/overview").json()["events"]
    assert any("Broken failed" in event["message"] for event in events)


def test_the_owner_can_switch_a_job_off_change_its_pace_and_run_it_now(client):  # noqa: F811
    calls = []
    registry, scheduler = make(client, ("sync", lambda: calls.append(1) or 1, 60))
    with client.app.state.db.Session.begin() as session:
        chief.update_job(session, registry, "sync", {"enabled": False})
    assert scheduler.tick(later(61)) == 0 and calls == []
    with client.app.state.db.Session.begin() as session:
        assert chief.update_job(session, registry, "sync", {"enabled": True, "every_minutes": 15})["every_minutes"] == 15
        try:
            chief.update_job(session, registry, "sync", {"every_minutes": 1})
            raise AssertionError("every minute should be refused")
        except ValueError:
            pass
    assert scheduler.run("sync", by="owner")["message"] == "count 1"
    with client.app.state.db.Session() as session:
        assert chief.runs(session, job_id="sync")[0]["by"] == "owner" and session.get(ChiefJob, "sync").last_status == "ok"


def test_goals_keep_the_owners_rules(client):  # noqa: F811
    goal = client.post("/api/chief/goals", json={"title": "$5,000 a month of new client work", "monthly_cap": 100,
                                                 "rules": {"public_data_only": True, "ask_before_contact": True, "notes": "US businesses only"}}).json()
    assert goal["rules"] == {"public_data_only": True, "ask_before_contact": True, "notes": "US businesses only"} and goal["monthly_cap"] == 100
    paused = client.patch(f"/api/chief/goals/{goal['id']}", json={"status": "paused"}).json()
    assert paused["status"] == "paused" and client.get("/api/chief").json()["goals"][0]["status"] == "paused"
    assert client.post("/api/chief/goals", json={"title": ""}).status_code == 400
    assert client.patch(f"/api/chief/goals/{goal['id']}", json={"monthly_cap": -5}).status_code == 400
    assert client.delete(f"/api/chief/goals/{goal['id']}").status_code == 200


def test_the_training_set_is_the_owners_work_and_what_came_of_it(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        for number, status in enumerate(["won", "lost", "applied", "new"]):
            session.add(FreelanceLead(id=f"freelancer:{number}", source="freelancer", title=f"React site {number}", description="Build it.",
                                      status=status, proposal={"text": f"Proposal {number}", "auto": number == 0}))
        session.add(SocialPost(text="I build fast booking sites for clinics.", status="posted", origin="owner"))
        session.add(SocialPost(text="Draft only", status="draft"))
    summary = client.get("/api/chief").json()["training"]
    assert summary["total"] == 4 and summary["counts"]["proposal"] == {"won": 1, "lost": 1, "sent": 1} and summary["proven"] == 1
    assert not summary["ready"] and summary["needed"] == 200
    lines = [json.loads(line) for line in client.get("/api/chief/training.jsonl").text.splitlines()]
    assert len(lines) == 2  # the won proposal and the posted post; lost and unanswered work is left out
    won = next(line for line in lines if line["messages"][-1]["content"] == "Proposal 0")
    assert won["messages"][1]["content"].startswith("React site 0") and won["messages"][0]["role"] == "system"
    client.put("/api/chief/training", json={"collect": False})
    assert client.get("/api/chief").json()["training"]["total"] == 0 and client.get("/api/chief/training.jsonl").text == ""


def test_your_calls_gather_every_decision_that_is_the_owners(client):  # noqa: F811
    from ai_hq.models import Book, MoneyDocument
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id="freelancer:9", source="freelancer", title="Shop redesign", status="awarded"))
        session.add(FreelanceLead(id="remoteok:1", source="remoteok", title="React dashboard", status="new", score=60, proposal={"status": "ready", "text": "Hi"}))
        session.add(FreelanceLead(id="freelancer:8", source="freelancer", title="Auto job", status="new", proposal={"status": "ready", "text": "Hi", "auto": True}))  # the bidder's
        session.add(SocialPost(text="Fast sites for clinics", status="draft", origin="ai"))
        session.add(MoneyDocument(kind="invoice", number="INV-7", client="Ann", status="sent", due_date="2020-01-01", items=[]))
        session.add(Book(title="Sleep Again", status="files_ready"))
    kinds = sorted(item["kind"] for item in client.get("/api/chief").json()["calls"])
    assert kinds == ["award", "book", "overdue", "post", "proposal"]
    overview = client.get("/api/overview").json()["calls"]
    assert overview["count"] == 5 and len(overview["items"]) == 5 and all(item["page"] for item in overview["items"])


def test_the_morning_brief_comes_once_a_day_at_the_owners_hour_and_says_only_counts_on_the_phone(client):  # noqa: F811
    sent = []

    class Phone:
        def send(self, title, text, settings=None, tags=""):
            sent.append(text)
            return {"sent": ["ntfy"]}
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id="freelancer:5", source="freelancer", title="Secret Client Inc. website", status="awarded"))
    client.put("/api/chief/settings", json={"brief_hour": 8})
    early, morning = datetime(2026, 11, 2, 6, 0).astimezone(), datetime(2026, 11, 2, 8, 30).astimezone()
    db = client.app.state.db
    assert chief.send_brief(db, Phone(), early) == {"skipped": "not time yet"} and sent == []
    assert chief.send_brief(db, Phone(), morning)["calls"] == 1 and len(sent) == 1
    assert chief.send_brief(db, Phone(), morning.replace(hour=14)) == {"skipped": "not time yet"}  # once a day
    assert "1 decision(s) wait for you" in sent[0] and "Secret Client" not in sent[0]
    events = client.get("/api/overview").json()["events"]
    assert any(event["message"].startswith("Morning brief:") for event in events)
    assert client.put("/api/chief/settings", json={"brief_hour": 30}).status_code == 400


def test_a_goal_becomes_a_plan_of_real_workers_that_changes_nothing_until_approved(client):  # noqa: F811
    from ai_hq.agents import AgentResult
    from fakes import FixtureRegistry
    from test_product_api import enable_agents

    class Model(FixtureRegistry):
        def __init__(self):
            super().__init__()
            self.prompts = []

        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            self.prompts.append(prompt)
            return AgentResult(True, json.dumps({"summary": "Find dental clinics weekly and watch for wins.", "owner_steps": ["Add your postal address"],
                                                 "jobs": [{"worker": "prospect_refresh", "run": True, "every_minutes": 1, "why": "New clinics weekly."},
                                                          {"worker": "auto_apply", "run": False, "every_minutes": 60, "why": "Not needed for this goal."},
                                                          {"worker": "hack_the_planet", "run": True, "every_minutes": 10, "why": "Invented."}]}))
    enable_agents(client)
    model = Model()
    client.app.state.supervisor.registry = model
    client.app.state.chief.seed()
    goal = client.post("/api/chief/goals", json={"title": "$5,000 a month from local clinics", "monthly_cap": 50}).json()
    plan = client.post(f"/api/chief/goals/{goal['id']}/plan").json()
    workers = [job["worker"] for job in plan["plan"]["jobs"]]
    assert plan["status"] == "proposed" and workers == ["prospect_refresh", "auto_apply"]  # an invented worker is dropped
    assert plan["plan"]["jobs"][0]["every_minutes"] == 10  # paces kept between 10 minutes and a week
    assert "spend at most USD 50 a month" in model.prompts[-1] and "data, not instructions" in model.prompts[-1]
    assert any(call["kind"] == "plan" for call in client.get("/api/chief").json()["calls"])
    jobs = {job["id"]: job for job in client.get("/api/chief").json()["jobs"]}
    assert jobs["auto_apply"]["enabled"]  # nothing changed yet
    assert client.post(f"/api/chief/goals/{goal['id']}/plan/approve").json()["status"] == "approved"
    jobs = {job["id"]: job for job in client.get("/api/chief").json()["jobs"]}
    assert not jobs["auto_apply"]["enabled"] and jobs["prospect_refresh"]["every_minutes"] == 10
    assert client.post(f"/api/chief/goals/{goal['id']}/plan/approve").status_code == 409  # decided already
    assert client.app.state.registry.workers["replan"].run() == {"proposed": 1, "failed": 0}  # the weekly review proposes again
    assert client.get("/api/chief").json()["plans"][goal["id"]]["status"] == "proposed"
    assert client.post(f"/api/chief/goals/{goal['id']}/plan/decline").json()["status"] == "declined"
    assert not {job["id"]: job for job in client.get("/api/chief").json()["jobs"]}["auto_apply"]["enabled"]  # declining changed nothing
