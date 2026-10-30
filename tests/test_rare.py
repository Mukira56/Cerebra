"""Rare chances: a strong match with few bids so far and a real budget is flagged as soon as it's found, waits in Your
calls and pings the owner's phone (counts only). Job sources are simulated; nothing is sent anywhere."""
from ai_hq import chief, notify
from ai_hq.models import Metadata, now
from test_freelance import by_title, client  # noqa: F401  (client is a fixture)


def phone_on(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(Metadata(key=notify.KEY, value={**notify.DEFAULT, "ntfy_enabled": True, "ntfy_topic": "cerebra-test-topic"}))
        session.add(Metadata(key=notify.CURSOR, value={"at": now()}))


def test_a_strong_match_with_few_bids_is_a_rare_chance(client):  # noqa: F811
    phone_on(client)
    client.post("/api/freelance/check")
    bakery, tea = by_title(client, "React landing page for my bakery"), by_title(client, "Logo for a tea brand")
    assert bakery["rare"] and not tea["rare"]  # 6 bids and USD 750 against 120 bids
    with client.app.state.db.Session() as session:
        waiting = [item for item in chief.calls(session) if item["kind"] == "rare"]
    assert len(waiting) == 1 and "bakery" in waiting[0]["detail"] and waiting[0]["page"] == "freelance"
    _, messages = client.app.state.notifier.pending_messages()
    rare = [message for message in messages if "rare chance" in message[0]]
    assert len(rare) == 1 and "score" in rare[0][1] and "bakery" not in rare[0][1].lower()  # counts only: no job details through a public server


def test_rare_chance_alerts_follow_the_owners_thresholds(client):  # noqa: F811
    client.put("/api/freelance/auto", json={"alert_bids": 5})  # fewer than 5 bids: the bakery's 6 no longer count
    client.post("/api/freelance/check")
    assert not by_title(client, "React landing page for my bakery")["rare"]
    assert client.put("/api/freelance/auto", json={"alert_usd": 0}).status_code == 400
    client.put("/api/freelance/auto", json={"alert": False})
    assert client.get("/api/freelance/auto").json()["settings"]["alert"] is False


def test_scores_age_so_an_old_crowded_job_sinks_within_the_hour(client):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    from ai_hq.models import FreelanceLead
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    with client.app.state.db.Session.begin() as session:  # scored when it was fresh, with few bids
        session.add(FreelanceLead(id="freelancer:77", source="freelancer", title="React dashboard for a gym", description="A React dashboard.", status="new",
                                  score=80, reasons=["posted 1 h ago"], budget_min=300, budget_max=900, currency="USD", kind="fixed", posted_at=old,
                                  extra={"bids": 140}))
    client.post("/api/freelance/check")
    lead = by_title(client, "React dashboard for a gym")
    assert lead["score"] < 50 and "posted 5 days ago" in lead["reasons"] and "140 bids already" in lead["reasons"]


def test_the_morning_brief_puts_what_cant_wait_first_and_picks_todays_jobs(client):  # noqa: F811
    from ai_hq.models import FreelanceLead
    client.post("/api/freelance/check")  # the bakery job is a rare chance
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id="remotive:9", source="remotive", title="Next.js shop for a florist", description="A Next.js shop.", status="new", score=95,
                                  reasons=["matches next.js", "posted 3 h ago"], extra={"committee": {"decision": "skip"}}))  # the committee said no
        session.add(FreelanceLead(id="remotive:10", source="remotive", title="Vue admin for a school", description="A Vue admin panel.", status="new", score=60,
                                  reasons=["matches vue", "posted 2 h ago"], proposal={"status": "ready", "text": "Hi"}))
    with client.app.state.db.Session() as session:
        content = chief.brief(session)
    titles = [item["title"] for item in content["today"]]
    assert "bakery" in titles[0] and titles[1] == "Vue admin for a school" and "Next.js shop for a florist" not in titles
    assert content["today"][1]["ready"] and "posted 2 h ago" in content["today"][1]["why"]
    assert [item["kind"] for item in content["first"]] == ["rare"]
    assert "Top pick today: score" in content["phone"] and "bakery" not in content["phone"].lower() and "Vue" not in content["phone"]


def test_the_overview_shows_todays_jobs_and_what_stands_between_the_owner_and_earning(client):  # noqa: F811
    client.post("/api/freelance/check")
    earn = client.get("/api/overview").json()["earn"]
    assert "bakery" in earn["today"][0]["title"] and earn["today"][0]["rare"]
    gaps = [gap["key"] for gap in earn["gaps"]]
    assert gaps == ["freelancer", "phone", "models", "gmail", "stripe"] and all(gap["page"] and gap["why"] for gap in earn["gaps"])  # skills are set by default
    client.put("/api/business/notifications", json={"ntfy_enabled": True})
    assert "phone" not in [gap["key"] for gap in client.get("/api/overview").json()["earn"]["gaps"]]


def test_a_search_that_finds_nothing_strong_leaves_the_activity_log_alone(client):  # noqa: F811
    client.app.state.sources.broken = {"www.freelancer.com"}  # only weak jobs elsewhere: a plumber, a salaried role…
    client.put("/api/freelance/auto", json={"alert": False})
    client.post("/api/freelance/check")
    events = [event["message"] for event in client.get("/api/overview").json()["events"]]
    assert not any(message.startswith("Found ") for message in events)


def test_an_application_with_no_reply_gets_one_follow_up_then_a_nudge_to_close_it(client):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    from ai_hq.models import FreelanceLead
    client.post("/api/freelance/check")
    lead = by_title(client, "React landing page for my bakery")
    assert client.patch(f"/api/freelance/leads/{lead['id']}", json={"status": "applied"}).json()["applied_at"]

    def waiting():
        with client.app.state.db.Session() as session:
            return [item for item in chief.calls(session) if item["kind"] == "followup"]

    def age(key, days):
        with client.app.state.db.Session.begin() as session:
            row = session.get(FreelanceLead, lead["id"])
            row.extra = {**row.extra, key: (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}

    assert waiting() == []  # just applied: nothing to do yet
    age("applied_at", 6)
    assert [item["title"] for item in waiting()] == ["No reply yet: follow up"] and "6 days since you applied" in waiting()[0]["detail"]
    client.patch(f"/api/freelance/leads/{lead['id']}", json={"followed_up": True})
    assert waiting() == []  # followed up today: wait a week
    age("followed_up_at", 8)
    assert [item["title"] for item in waiting()] == ["Still no reply: close it?"]
    client.patch(f"/api/freelance/leads/{lead['id']}", json={"status": "lost"})
    assert waiting() == []
