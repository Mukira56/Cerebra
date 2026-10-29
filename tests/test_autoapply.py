"""Phase 4b: bidding by itself on Freelancer.com, noticing wins (Freelancer.com and Gmail), and starting the work.
Simulated Freelancer.com, Gmail and model only: no real account, email or AI usage."""
import json

import httpx
from sqlalchemy import select

from ai_hq.agents import AgentResult
from ai_hq.models import Approval, BusinessJob, Task
from fakes import FixtureRegistry
from test_freelance import by_title, client  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents

TOKEN = "freelancer-oauth-token-for-tests-1234567890"


class Model(FixtureRegistry):
    """Writes a proposal for every lead, judging homework a poor fit; asks a high price to check the budget clamp."""
    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        if "JOB POST" not in prompt:
            return super().chat(name, prompt, workdir, model, cancel_event)
        apply = "thesis" not in prompt.lower()
        return AgentResult(True, json.dumps({"proposal": "Here is how I would do it...", "price": 5000, "days": 0, "fit": "Fits." if apply else "Academic cheating.", "apply": apply}))


class Freelancer:
    def __init__(self):
        self.bids, self.awarded, self.calls = [], set(), []

    def __call__(self, request):
        self.calls.append(request)
        assert request.headers["Freelancer-OAuth-V1"] == TOKEN
        if request.url.path == "/api/users/0.1/self/":
            return httpx.Response(200, json={"status": "success", "result": {"id": 42, "username": "mukira"}})
        if request.url.path == "/api/projects/0.1/bids/" and request.method == "POST":
            body = json.loads(request.content)
            self.bids.append(body)
            return httpx.Response(200, json={"status": "success", "result": {"id": 9000 + len(self.bids)}})
        if request.url.path == "/api/projects/0.1/bids/" and request.method == "GET":
            wanted = request.url.params.get_list("bids[]")
            return httpx.Response(200, json={"status": "success", "result": {"bids": [{"id": int(item), "award_status": "awarded" if int(item) in self.awarded else "pending"} for item in wanted]}})
        if request.method == "PUT" and request.url.path.startswith("/api/projects/0.1/bids/"):
            assert request.url.params["action"] == "accept"
            return httpx.Response(200, json={"status": "success", "result": {}})
        return httpx.Response(404, json={"status": "error", "message": "unknown"})


def setup(client, **rules):  # noqa: F811
    enable_agents(client)
    client.app.state.supervisor.registry = Model()
    site = Freelancer()
    client.app.state.bidder.client = httpx.Client(transport=httpx.MockTransport(site))
    client.post("/api/freelance/check")
    if rules.get("connect", True):
        client.put("/api/freelance/freelancer-account", json={"token": TOKEN})
    client.put("/api/freelance/auto", json={"enabled": True, **{key: value for key, value in rules.items() if key != "connect"}})
    return site


def test_nothing_is_sent_until_the_owner_switches_it_on_and_connects(client):  # noqa: F811
    assert client.app.state.applier.tick() == {"skipped": "off"}
    setup(client, connect=False)
    assert client.app.state.applier.tick() == {"skipped": "not connected"}


def test_matches_get_tailored_bids_inside_their_budget_and_poor_fits_are_passed_over(client):  # noqa: F811
    site = setup(client, min_score=1, per_day=15)
    result = client.app.state.applier.tick()
    titles = {bid["project_id"] for bid in site.bids}
    assert result["sent"] == len(site.bids) >= 1 and 3 not in titles  # project 3 is the thesis: the model said no
    bakery = next(bid for bid in site.bids if bid["project_id"] == 1)
    assert bakery["amount"] == 750 and bakery["period"] == 7  # asked 5,000: kept inside the 250-750 budget; no days given: a week
    thesis = by_title(client, "thesis")
    assert thesis["proposal"]["skipped"] == "Academic cheating." and thesis["status"] == "new"
    assert by_title(client, "React landing")["status"] == "applied" and by_title(client, "React landing")["proposal"]["auto"]
    assert client.app.state.applier.tick()["sent"] == 0  # each lead once


def test_the_daily_number_of_bids_holds(client):  # noqa: F811
    site = setup(client, min_score=1, per_day=1)
    client.app.state.applier.tick()
    assert len(site.bids) == 1 and client.app.state.applier.tick() == {"skipped": "daily limit"}


def test_awards_are_noticed_and_accepting_one_starts_the_work(client):  # noqa: F811
    site = setup(client, min_score=1)
    client.app.state.applier.tick()
    lead = by_title(client, "React landing")
    site.awarded.add(lead["proposal"]["bid_id"])
    client.app.state.watcher.check_freelancer()
    assert by_title(client, "React landing")["status"] == "awarded"  # the client chose you; accepting is a commitment
    started = []
    client.app.state.watcher.start_work = lambda lead_id: started.append(lead_id) or "job-1"
    client.app.state.watcher.start_won()
    assert started == []  # not accepted yet, and accepting by itself is off
    client.post("/api/freelance/accept-award", json={"id": lead["id"]})
    assert by_title(client, "React landing")["status"] == "won" and started == [lead["id"]]
    assert any(request.method == "PUT" for request in site.calls)


class Mailbox:
    def __init__(self, messages):
        self.messages = {str(index): message for index, message in enumerate(messages)}
        self.searches = []

    def search(self, query, limit=20):
        self.searches.append(query)
        return list(self.messages)

    def message(self, identifier):
        return {"id": identifier, "date": "Thu, 29 Oct 2026", "snippet": "", **self.messages[identifier]}


def test_emails_tell_cerebra_what_was_won_once_and_newsletters_are_ignored(client):  # noqa: F811
    upwork = client.post("/api/freelance/leads", json={"title": "WordPress website for a dental clinic", "platform": "Upwork", "description": "We need a WordPress website with booking."}).json()
    client.patch(f"/api/freelance/leads/{upwork['id']}", json={"status": "applied"})
    mailbox = Mailbox([
        {"from": "Upwork <donotreply@upwork.com>", "subject": "Your contract has started: WordPress website for a dental clinic", "body": "Congratulations, the client hired you."},
        {"from": "Fiverr <noreply@e.fiverr.com>", "subject": "You've received a new order from lindaj", "body": "Logo design for a bakery, 3 days."},
        {"from": "Upwork <donotreply@upwork.com>", "subject": "Jobs for you this week", "body": "New order of jobs matching your profile"},
        {"from": "someone@gmail.com", "subject": "You have been hired", "body": "Not from a platform"}])
    watcher = client.app.state.watcher
    watcher.mailbox = mailbox
    assert watcher.check_mail() == 2
    assert by_title(client, "dental clinic")["status"] == "won"
    fiverr = by_title(client, "new order from lindaj")
    assert fiverr["status"] == "won" and fiverr["source_label"] == "Fiverr"  # a job Cerebra never saw becomes a lead
    assert "from:(upwork.com OR fiverr.com OR freelancer.com)" in mailbox.searches[0]
    assert watcher.check_mail() == 0  # each email once
    assert not any("Jobs for you" in lead["title"] for lead in client.get("/api/freelance?hidden=true").json()["leads"])


def test_a_won_job_becomes_work_cerebra_plans_and_starts_itself_but_never_delivers(client, tmp_path):  # noqa: F811
    enable_agents(client)
    client.put("/api/business/settings", json={"output_root": str(tmp_path / "business")})
    won = client.post("/api/freelance/leads", json={"title": "Landing page for a yoga studio", "platform": "Upwork", "description": "A one-page website with class times and a contact form."}).json()
    client.patch(f"/api/freelance/leads/{won['id']}", json={"status": "won"})
    watcher = client.app.state.watcher
    assert watcher.start_won() == 1
    with client.app.state.db.Session() as session:
        job = session.scalars(select(BusinessJob)).first()
        task = session.get(Task, job.task_id)
        assert job.kind == "website" and task.results["freelance_lead"] == won["id"] and "CLIENT'S JOB POST" in job.brief
    assert watcher.start_won() == 0  # work starts once
    for _ in range(3):
        client.app.state.keep_won_work()
        client.app.state.supervisor.run_until_idle()
    with client.app.state.db.Session() as session:
        task = session.get(Task, job.task_id)
        merges = session.scalars(select(Approval).where(Approval.task_id == task.id, Approval.kind == "merge")).all()
        assert task.approved and task.state != "COMPLETED"  # planned and run by itself; delivery (the merge) waits for the owner
        assert all(approval.status.lower() == "pending" for approval in merges)
