"""The daily number covers emails written, because each one uses the owner's model. Models and Gmail are simulated."""
from datetime import datetime, timedelta, timezone

import httpx

from ai_hq.models import Outbox, Prospect
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import setup


def businesses(state, count, opener=""):
    with state.db.Session.begin() as session:
        for number in range(count):
            key = f"p{number}"
            site = f"http://{key}.example"
            session.add(Prospect(id=key, name=f"Business {key}", kind="dentists", city="Austin", state="Texas", website=site, status="kept", opener=opener,
                                 facts=[{"key": "no_booking", "text": "No online booking", "seen": site}]))
            session.flush()
            session.add(Outbox(prospect_id=key, email=f"hello@{key}.example", stage="draft", created_at="2026-01-01T00:00:00+00:00"))  # found long ago


def draft_mode(client, per_day):  # noqa: F811
    client.put("/api/outreach", json={"enabled": True, "mode": "draft", "per_day": per_day, "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]}).raise_for_status()


def written(state):
    with state.db.Session() as session:
        return session.query(Prospect).filter(Prospect.opener != "").count()


def test_a_limit_of_one_means_one_however_many_addresses_are_waiting(client):  # noqa: F811
    state = setup(client)
    businesses(state, 5)
    draft_mode(client, 1)
    for _ in range(4):
        state.outreach.tick()
    assert written(state) == 1


def test_the_daily_number_is_reached_and_not_passed(client):  # noqa: F811
    state = setup(client)
    businesses(state, 6)
    draft_mode(client, 4)
    for _ in range(5):
        state.outreach.tick()
    assert written(state) == 4


def test_the_next_day_it_carries_on(client):  # noqa: F811
    state = setup(client)
    businesses(state, 3)
    draft_mode(client, 1)
    state.outreach.tick()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with state.db.Session.begin() as session:
        for row in session.query(Prospect).filter(Prospect.opener != "").all():
            row.updated_at = yesterday
    state.outreach.tick()
    assert written(state) == 2


def test_losing_the_internet_is_said_plainly_and_is_not_a_crash(client):  # noqa: F811
    state = setup(client)
    businesses(state, 1)
    draft_mode(client, 1)
    state.outreach.research = lambda: (_ for _ in ()).throw(httpx.ConnectError("getaddrinfo failed"))
    result = state.outreach.tick()
    assert result["state"] == "error" and "tries again on the next run" in result["message"]
