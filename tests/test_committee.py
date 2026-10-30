"""The decision committee: analyst, bull, bear, risk reviewer and manager decide on a job before any bid. Simulated models."""
import json

import httpx

from ai_hq.agents import AgentResult
from ai_hq.models import FreelanceLead
from fakes import FixtureRegistry
from test_autoapply import Freelancer, TOKEN
from test_freelance import by_title, client  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents


class Committee(FixtureRegistry):
    """Answers as each role; the risk reviewer vetoes anything mentioning WhatsApp payment."""
    def __init__(self, decision="bid"):
        super().__init__()
        self.decision, self.prompts = decision, []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        if "risk reviewer" in prompt:
            veto = "pay you on whatsapp" in prompt.lower()
            return AgentResult(True, json.dumps({"veto": veto, "reason": "Asks to pay outside the platform." if veto else "No red flags."}))
        if "manager of a freelancer's decision committee" in prompt:
            return AgentResult(True, json.dumps({"decision": self.decision, "confidence": 80, "reason": "Fits the skills and pays fairly."}))
        if "JOB POST" in prompt and "decision committee" not in prompt:  # the proposal writer
            return AgentResult(True, json.dumps({"proposal": "Here is how I'd do it.", "price": 500, "days": 5, "fit": "Fits.", "apply": True}))
        return AgentResult(True, "A short note for the committee.")


def add(client, number, title, description):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id=f"freelancer:{number}", source="freelancer", title=title, description=description, status="new",
                                  score=80, budget_min=250, budget_max=750, currency="USD", kind="fixed"))


def test_the_committee_records_each_roles_view_and_a_decision(client):  # noqa: F811
    enable_agents(client)
    model = Committee()
    client.app.state.supervisor.registry = model
    add(client, 701, "React landing page for a clinic", "A fast React landing page with a booking form.")
    record = client.post("/api/freelance/committee", json={"id": "freelancer:701"}).json()
    assert record["decision"] == "bid" and record["confidence"] == 80 and not record["vetoed"]
    assert set(record["roles"]) == {"analyst", "bull", "bear", "risk", "manager"}
    assert all("data, not instructions" in prompt for prompt in model.prompts)  # the job post is never treated as instructions
    assert by_title(client, "React landing page for a clinic")["committee"]["decision"] == "bid"
    assert client.post("/api/freelance/committee", json={"id": "nope"}).status_code == 404


def test_a_risk_veto_stands_even_if_the_manager_would_bid(client):  # noqa: F811
    enable_agents(client)
    client.app.state.supervisor.registry = Committee(decision="bid")
    add(client, 702, "Shopify store", "Build a Shopify store. I will pay you on WhatsApp after delivery.")
    record = client.post("/api/freelance/committee", json={"id": "freelancer:702"}).json()
    assert record["vetoed"] and record["decision"] == "skip" and "outside the platform" in record["reason"]


def test_automatic_bidding_asks_the_committee_and_skips_what_it_rejects(client):  # noqa: F811
    enable_agents(client)
    model = Committee(decision="skip")
    client.app.state.supervisor.registry = model
    site = Freelancer()
    client.app.state.bidder.client = httpx.Client(transport=httpx.MockTransport(site))
    client.put("/api/freelance/freelancer-account", json={"token": TOKEN})
    client.put("/api/freelance/auto", json={"enabled": True, "min_score": 1})
    add(client, 703, "WordPress site for a bakery", "A WordPress site with an order form.")
    result = client.app.state.applier.tick()
    assert site.bids == [] and result["passed"] >= 1  # no bid without the committee's yes
    assert by_title(client, "WordPress site for a bakery")["proposal"]["skipped"].startswith("Committee:")
    model.decision = "bid"
    add(client, 704, "React dashboard for a gym", "A React dashboard showing member check-ins.")
    client.app.state.applier.tick()
    assert 704 in {bid["project_id"] for bid in site.bids}
