"""Keeping Cerebra quick with thousands of records: stale job posts are set aside, the list of what waits for the owner
reads only the leads that can need them, and the newest release is asked for once every few minutes."""
from datetime import datetime, timedelta, timezone

from ai_hq import chief, freelance
from ai_hq.models import FreelanceLead
from test_freelance import client  # noqa: F401  (client is a fixture)


def lead(number, status="new", age=0, **values):
    stamp = (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()
    return FreelanceLead(id=f"upwork:{number}", source="upwork", title=f"Job {number}", url=f"https://example.com/{number}", description="Build it",
                         status=status, score=values.pop("score", 50), created_at=stamp, updated_at=stamp, **values)


def test_untouched_job_posts_are_set_aside_after_three_weeks_but_nothing_with_a_proposal(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add_all([lead(1, age=30), lead(2, age=5), lead(3, age=30, proposal={"status": "ready", "text": "Hi"}), lead(4, "saved", age=40)])
    with client.app.state.db.Session.begin() as session:
        assert freelance.expire(session) == 1
    with client.app.state.db.Session() as session:
        states = {row.id: (row.status, bool((row.extra or {}).get("expired"))) for row in session.query(FreelanceLead)}
    assert states == {"upwork:1": ("hidden", True), "upwork:2": ("new", False), "upwork:3": ("new", False), "upwork:4": ("saved", False)}


def test_what_waits_for_the_owner_skips_ordinary_open_leads(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add_all([lead(n) for n in range(10, 60)])  # ordinary open leads: nothing for the owner to decide
        session.add(lead(1, "awarded"))
        session.add(lead(2, "saved", proposal={"status": "ready", "text": "Hello"}))
    with client.app.state.db.Session() as session:
        kinds = sorted(item["kind"] for item in chief.calls(session) if item["kind"] in {"award", "proposal", "rare"})
    assert kinds == ["award", "proposal"]


def test_the_newest_release_is_asked_for_once_every_few_minutes():
    from ai_hq.updater import PublicGitHub
    github, asked = PublicGitHub(), []
    github._release = lambda tag=None: asked.append(tag) or {"tagName": "v9.0.0"}
    assert github.release()["tagName"] == "v9.0.0" and github.release()["tagName"] == "v9.0.0" and asked == [None]
    github.release("v1.0.0")
    assert asked == [None, "v1.0.0"]  # a specific version is always asked for


def test_long_runs_started_by_a_button_go_to_the_background(client):  # noqa: F811
    import threading
    gate, finished = threading.Event(), threading.Event()
    robot = client.app.state.jobs

    def slow(count=10):
        gate.wait(10)
        finished.set()
        return {"written": 2, "problems": []}
    robot.write_ahead = slow
    first = client.post("/api/jobs/write", json={"count": 3}).json()
    assert first["background"] and "next 3 applications" in first["message"]
    assert "already running" in client.post("/api/jobs/write", json={"count": 3}).json()["message"]  # not started twice
    gate.set()
    assert finished.wait(10)
    for _ in range(100):
        if "Wrote 2 applications" in (robot.status.get("message") or ""):
            break
        threading.Event().wait(0.05)
    assert "Wrote 2 applications" in robot.status["message"]  # the page's status line shows how it ended
