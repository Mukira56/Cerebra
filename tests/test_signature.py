"""Outreach is signed by a person. The app's own name never appears, and a real business name is left alone. Names here are made up."""
from ai_hq import owner
from ai_hq.models import Outbox, Prospect
from ai_hq.prospects import footer
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import setup


def business(client, name):  # noqa: F811
    client.put("/api/money/settings", json={"business_name": name, "email": "sam@sample.test", "address": "PO Box 100, Austin, TX 78701"}).raise_for_status()


def person(state, name="Sam Sample"):
    with state.db.Session.begin() as session:
        owner.save(session, {"name": name})


def signature(state):
    with state.db.Session() as session:
        return footer(session)[0].splitlines()


def test_the_apps_name_gives_way_to_the_persons(client):  # noqa: F811
    state = setup(client)
    person(state)
    for name in ("Cerebra", "cerebra", " CEREBRA "):
        business(client, name)
        assert signature(state)[0] == "Sam Sample", name


def test_a_real_business_name_is_kept(client):  # noqa: F811
    state = setup(client)
    person(state)
    for name in ("Sample Studio", "Cerebra Labs Design"):
        business(client, name)
        assert signature(state)[0] == name


def test_with_no_personal_name_the_app_name_still_never_appears(client):  # noqa: F811
    state = setup(client)
    business(client, "Cerebra")
    assert "cerebra" not in " ".join(signature(state)).lower() and "sam@sample.test" in signature(state)


def test_the_law_still_has_what_it_needs(client):  # noqa: F811
    state = setup(client)
    person(state)
    business(client, "Cerebra")
    text = "\n".join(signature(state))
    assert "PO Box 100" in text and "no thanks" in text


def draft(state, opener, stage="draft"):
    with state.db.Session.begin() as session:
        session.add(Prospect(id="p1", name="Sample Cafe", kind="cafes", city="Austin", state="Texas", website="https://samplecafe.test", status="kept", opener=opener))
        session.flush()
        session.add(Outbox(prospect_id="p1", email="hi@samplecafe.test", stage=stage))


OLD = "Subject: Hi\n\nHello, I built Cerebra Forms last year.\n\n\u2014\nCerebra\nsam@sample.test\nPO Box 100"


def opener(state):
    with state.db.Session() as session:
        return session.get(Prospect, "p1").opener


def test_waiting_drafts_get_the_right_signature_and_nothing_else_changes(client):  # noqa: F811
    state = setup(client)
    person(state)
    business(client, "Cerebra")
    draft(state, OLD)
    state.outreach.review_addresses()
    text = opener(state)
    assert "\nSam Sample\nsam@sample.test" in text and "I built Cerebra Forms last year." in text  # only the signature line


def test_a_sent_email_is_history(client):  # noqa: F811
    state = setup(client)
    person(state)
    business(client, "Cerebra")
    draft(state, OLD, stage="sent")
    state.outreach.review_addresses()
    assert opener(state) == OLD
