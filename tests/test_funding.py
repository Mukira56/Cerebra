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
    client.put("/api/funding/facts", json={"company": True, "website": "mukira.example", "founded_year": date.today().year, "us_owned": True, "product": True})
    state = client.get("/api/funding").json()
    ready = {item["key"] for item in state["programs"] if item["ready"]}
    assert {"google_cloud", "microsoft", "nvidia", "nsf_sbir", "ycombinator"} <= ready
    assert state["facts"]["website"] == "https://mukira.example"
    assert not any(item["key"] in {"tef", "google_africa"} for item in state["programs"])  # US programs only
    aws = next(item for item in state["programs"] if item["key"] == "aws_activate")
    assert aws["missing"] == ["an AWS account on a paid plan"]
    assert state["programs"][0]["ready"] and not state["programs"][-1]["ready"]  # ready ones first
    opens = [item["open"] for item in state["programs"] if item["ready"]]
    assert opens == sorted(opens, reverse=True)  # among ready ones, open calls come before a closed yearly one


def test_a_won_job_counts_as_paying_customers(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id="freelancer:1", source="freelancer", title="Website", status="won"))
    assert client.get("/api/funding").json()["evidence"]["paying_customers"] is True


def test_the_owner_records_applications_and_bad_facts_are_refused(client):  # noqa: F811
    assert client.put("/api/funding/programs/nsf_sbir", json={"status": "applied", "note": "Project Pitch submitted on seedfund.nsf.gov"}).json()["status"] == "applied"
    assert next(item for item in client.get("/api/funding").json()["programs"] if item["key"] == "nsf_sbir")["applied"]["note"] == "Project Pitch submitted on seedfund.nsf.gov"
    assert client.put("/api/funding/programs/nope", json={"status": "applied"}).status_code == 404
    assert client.put("/api/funding/programs/nsf_sbir", json={"status": "won the lottery"}).status_code == 400
    assert client.put("/api/funding/facts", json={"founded_year": 1800}).status_code == 400


def test_an_application_is_drafted_from_records_with_gaps_marked_to_fill(client):  # noqa: F811
    import json
    from ai_hq.agents import AgentResult
    from fakes import FixtureRegistry
    from test_product_api import enable_agents

    class Model(FixtureRegistry):
        def __init__(self):
            super().__init__()
            self.prompts = []

        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            self.prompts.append(prompt)
            return AgentResult(True, json.dumps({"answers": ["We build websites for clinics.", "Clinics without online booking.",
                                                             "Hosting Cerebra's own model.\nTO FILL: how many users you expect", "One job won so far."]}))
    enable_agents(client)
    model = Model()
    client.app.state.supervisor.registry = model
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id="freelancer:2", source="freelancer", title="Website", status="won"))
    client.put("/api/funding/facts", json={"company": True, "company_country": "Kenya", "website": "mukira.example"})
    draft = client.post("/api/funding/programs/microsoft/draft").json()
    assert [item["question"] for item in draft["answers"]] == ["What does your company build, in one or two sentences?", "Who uses it, and what problem does it solve for them?",
                                                              "What will you use the credits for?", "Where are you now: product, users, revenue?"]
    assert draft["to_fill"] == 1 and draft["answers"][2]["answer"].endswith("TO FILL: how many users you expect")
    prompt = model.prompts[-1]
    assert "Freelance jobs won: 1" in prompt and "Registered company: yes, in Kenya" in prompt and "Never invent users" in prompt
    edited = client.put("/api/funding/programs/microsoft/draft", json={"answers": ["Mine", "Two"]}).json()
    assert [item["answer"] for item in edited["answers"]] == ["Mine", "Two", "", ""]
    assert client.get("/api/funding").json()["drafts"]["microsoft"]["answers"][0]["answer"] == "Mine"
    assert client.post("/api/funding/programs/nope/draft").status_code == 404
