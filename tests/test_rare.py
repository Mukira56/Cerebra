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
