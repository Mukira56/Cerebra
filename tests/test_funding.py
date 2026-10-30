"""Funding: each program with its official page and check date, and what the owner still needs for it, from their own facts
and Cerebra's records. Cerebra never applies: the owner records where each application stands."""
from datetime import date

from ai_hq import funding
from ai_hq.models import FreelanceLead
from test_freelance import client  # noqa: F401  (client is a fixture)


def test_every_program_names_its_official_page_and_when_it_was_checked():
    for program in funding.PROGRAMS:
        assert program["url"].startswith("https://") and program["gives"] and program["window"]
        assert set(program["needs"]) <= set(funding.NEEDS)
    assert any(program["equity"] for program in funding.PROGRAMS) and funding.CHECKED == "2026-10-30"


def test_readiness_says_what_is_missing_in_plain_words(client):  # noqa: F811
    state = client.get("/api/funding").json()
    google = next(item for item in state["programs"] if item["key"] == "google_cloud")
    assert not google["ready"] and google["missing"] == ["a registered company", "a working company website", "a company founded in the last 10 years"]
    client.put("/api/funding/facts", json={"company": True, "website": "mukira.example", "founded_year": date.today().year, "african": True, "product": True})
    state = client.get("/api/funding").json()
    ready = {item["key"] for item in state["programs"] if item["ready"]}
    assert {"google_cloud", "microsoft", "nvidia", "tef", "ycombinator"} <= ready
    assert state["facts"]["website"] == "https://mukira.example"
    africa = next(item for item in state["programs"] if item["key"] == "google_africa")
    assert africa["missing"] == ["paying customers"]  # checked against Cerebra's records, not the owner's word
    aws = next(item for item in state["programs"] if item["key"] == "aws_activate")
    assert aws["missing"] == ["an AWS account on a paid plan"]
    assert state["programs"][0]["ready"] and not state["programs"][-1]["ready"]  # ready ones first
    first_closed = next(index for index, item in enumerate(state["programs"]) if item["ready"] and not item["open"])
    assert all(item["open"] for item in state["programs"][:first_closed])  # among ready ones, open calls come before a closed yearly one


def test_a_won_job_counts_as_paying_customers(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id="freelancer:1", source="freelancer", title="Website", status="won"))
    assert client.get("/api/funding").json()["evidence"]["paying_customers"] is True


def test_the_owner_records_applications_and_bad_facts_are_refused(client):  # noqa: F811
    assert client.put("/api/funding/programs/tef", json={"status": "applied", "note": "Submitted on TEFConnect"}).json()["status"] == "applied"
    assert next(item for item in client.get("/api/funding").json()["programs"] if item["key"] == "tef")["applied"]["note"] == "Submitted on TEFConnect"
    assert client.put("/api/funding/programs/nope", json={"status": "applied"}).status_code == 404
    assert client.put("/api/funding/programs/tef", json={"status": "won the lottery"}).status_code == 400
    assert client.put("/api/funding/facts", json={"founded_year": 1800}).status_code == 400
