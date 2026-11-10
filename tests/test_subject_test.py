"""Testing a second subject line on company pitches: each company always gets the same one, the one used is recorded, and
a winner is named only on enough evidence. Companies and Gmail are simulated."""
from types import SimpleNamespace

from ai_hq import partners
from ai_hq.models import PartnerCompany
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_partners import PITCH, prepared


def test_half_the_companies_get_the_second_subject_and_always_the_same_one():
    rules = {**partners.DEFAULTS, **PITCH, "subject_b": "A free sample for {company}"}
    companies = [SimpleNamespace(id=f"c{n}", kind="", name=f"Co {n}") for n in range(200)]
    picks = [partners.variant(rules, company) for company in companies]
    assert set(picks) == {"A", "B"} and 70 < picks.count("B") < 130
    assert [partners.variant(rules, company) for company in companies] == picks  # stable: the reviewed email is the sent one
    assert partners.template(rules, companies[picks.index("B")])[0] == "A free sample for {company}"
    assert partners.variant({**rules, "subject_b": ""}, companies[0]) == ""


def test_the_second_subject_is_checked_when_saved(client):  # noqa: F811
    prepared(client)
    same = client.put("/api/partners", json={"subject_b": PITCH["subject"]})
    assert same.status_code == 400 and "same as the first" in same.json()["detail"]
    assert client.put("/api/partners", json={"subject_b": "Hi [name]"}).status_code == 400
    assert client.put("/api/partners", json={"subject_b": "A free sample for {company}"}).status_code == 200


def test_replies_are_counted_per_subject_and_a_winner_needs_evidence(client):  # noqa: F811
    prepared(client)
    client.put("/api/partners", json={"subject_b": "A free sample for {company}"}).raise_for_status()
    with client.app.state.db.Session.begin() as session:
        for n in range(80):
            key = "A" if n < 40 else "B"
            replied = (key == "B" and n % 4 == 0) or (key == "A" and n == 0)
            session.add(PartnerCompany(name=f"Co {n}", domain=f"co{n}.example", status="replied" if replied else "sent",
                                       sent=[{"at": "2026-11-01T10:00:00+00:00", "subject": "x", "body": "x", "variant": key}],
                                       reply={"verdict": "offered"} if replied and n % 8 == 0 else {}))
    test = client.get("/api/partners").json()["subject_test"]
    a, b = test["variants"]
    assert (a["sent"], a["replies"], b["sent"], b["replies"]) == (40, 1, 40, 10) and b["offers"] == 5
    assert test["winner"] == "B" and "Subject B gets more replies" in test["verdict"]
    with client.app.state.db.Session() as session:
        few = partners.subject_test(session, {**partners.settings(session)})
    assert few["winner"] == "B"
    with client.app.state.db.Session.begin() as session:
        for row in session.query(PartnerCompany).filter(PartnerCompany.name.in_([f"Co {n}" for n in range(15, 40)])):
            session.delete(row)
    assert client.get("/api/partners").json()["subject_test"]["winner"] == ""  # A has 15 pitches: not enough yet


def test_the_subject_used_is_recorded_when_the_pitch_goes_out(client):  # noqa: F811
    _, robot = prepared(client)
    client.put("/api/partners", json={"subject_b": "A free sample for {company}"}).raise_for_status()
    client.put("/api/partners", json={"enabled": True, "per_day": 5}).raise_for_status()
    robot.tick()
    with client.app.state.db.Session() as session:
        rows = [row for row in session.query(PartnerCompany).all() if row.sent]
        assert rows and all(row.sent[0]["variant"] in {"A", "B"} for row in rows)
        assert all(row.sent[0]["subject"].startswith("A free sample") == (row.sent[0]["variant"] == "B") for row in rows)
