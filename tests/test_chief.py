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
