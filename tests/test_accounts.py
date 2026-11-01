"""Several Freelancer.com accounts, each one person's own: added with a name and confirmation, one bid per project from one
account, automatic bids spread by each account's daily number, and wins checked with the account that bid. Simulated."""
import json

import httpx

from ai_hq import commerce
from ai_hq.models import FreelanceLead
from test_autoapply import Model
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents

USERS = {"token-for-the-owner-1234567890": (42, "mukira"), "token-for-the-teammate-123456789": (77, "amina_dev"),
         "another-token-same-owner-1234567": (42, "mukira")}


class Site:
    """Freelancer.com answering for whichever account's token is used."""
    def __init__(self):
        self.bids, self.reads = [], []

    def __call__(self, request):
        user = USERS.get(request.headers["Freelancer-OAuth-V1"])
        if user is None:
            return httpx.Response(401, json={"status": "error", "message": "Invalid token"})
        if request.url.path == "/api/users/0.1/self/":
            return httpx.Response(200, json={"status": "success", "result": {"id": user[0], "username": user[1]}})
        if request.url.path == "/api/projects/0.1/bids/" and request.method == "POST":
            body = json.loads(request.content)
            assert body["bidder_id"] == user[0]  # a bid goes out as the account whose token sent it
            self.bids.append({**body, "from": user[1]})
            return httpx.Response(200, json={"status": "success", "result": {"id": 9000 + len(self.bids)}})
        if request.url.path == "/api/projects/0.1/bids/" and request.method == "GET":
            self.reads.append((user[1], request.url.params.get_list("bids[]")))
            return httpx.Response(200, json={"status": "success", "result": {"bids": []}})
        return httpx.Response(404, json={"status": "error", "message": "unknown"})


def connect(client):  # noqa: F811
    site = Site()
    client.app.state.bidder.client = httpx.Client(transport=httpx.MockTransport(site))
    return site


def lead(client, number, title):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(FreelanceLead(id=f"freelancer:{number}", source="freelancer", title=title, status="new", score=90,  # its own post: not a re-post
                                  description=f"Project {number}: a React site for a {['bakery', 'clinic', 'gym', 'school'][number % 4]} with booking and a contact form.",
                                  budget_min=250, budget_max=750, currency="USD", kind="fixed",
                                  proposal={"status": "ready", "text": "Here is how I'd do it.", "price": 500, "days": 7}))


def test_a_second_account_is_another_persons_named_and_confirmed_and_never_a_duplicate(client):  # noqa: F811
    connect(client)
    first = client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-owner-1234567890"}).json()
    assert first["connected"] and first["accounts"][0]["username"] == "mukira"
    refused = client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-teammate-123456789"})
    assert refused.status_code == 400 and "belong to another person" in refused.json()["detail"]
    added = client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-teammate-123456789", "holder": "Amina Odhiambo", "owner_confirmed": True}).json()
    assert [(item["username"], item["holder"]) for item in added["accounts"]] == [("mukira", ""), ("amina_dev", "Amina Odhiambo")]
    twice = client.put("/api/freelance/freelancer-account", json={"token": "another-token-same-owner-1234567", "holder": "Me again", "owner_confirmed": True})
    assert twice.status_code == 400 and "already connected" in twice.json()["detail"]
    assert len(client.get("/api/freelance").json()["freelancer_account"]["accounts"]) == 2  # the refused one wasn't kept
    bad = client.put("/api/freelance/freelancer-account", json={"token": "a-token-freelancer-refuses-123", "holder": "Kim", "owner_confirmed": True})
    assert bad.status_code == 400 and len(client.app.state.bidder.accounts()) == 2
    teammate = added["accounts"][1]["id"]
    assert client.delete(f"/api/freelance/freelancer-account?account={teammate}").status_code == 200
    assert [item["username"] for item in client.app.state.bidder.accounts()] == ["mukira"]


def test_an_account_connected_before_is_kept_as_the_first(client):  # noqa: F811
    from ai_hq import vault
    with client.app.state.db.Session.begin() as session:
        value = commerce.load(session)
        value["freelancer_account"] = {"token": vault.protect("token-for-the-owner-1234567890"), "user_id": 42, "username": "mukira"}
        commerce.store(session, value)
    status = client.app.state.bidder.status()
    assert status["connected"] and status["accounts"] == [{"id": "main", "username": "mukira", "holder": "", "connected": True, "checked_at": ""}]


def test_one_bid_per_project_from_the_chosen_account(client):  # noqa: F811
    site = connect(client)
    client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-owner-1234567890"})
    teammate = client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-teammate-123456789", "holder": "Amina", "owner_confirmed": True}).json()["accounts"][1]["id"]
    lead(client, 501, "React landing page")
    sent = client.post("/api/freelance/bid", json={"id": "freelancer:501", "confirmed": True, "account": teammate}).json()
    assert "amina_dev" in sent["message"] and site.bids[-1]["from"] == "amina_dev"
    again = client.post("/api/freelance/bid", json={"id": "freelancer:501", "confirmed": True})
    assert again.status_code == 400 and "one bid per project" in again.json()["detail"] and len(site.bids) == 1


def test_automatic_bids_use_each_accounts_own_daily_number_and_wins_are_checked_per_account(client, tmp_path):  # noqa: F811
    enable_agents(client)
    client.app.state.supervisor.registry = Model()
    site = connect(client)
    client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-owner-1234567890"})
    client.put("/api/freelance/freelancer-account", json={"token": "token-for-the-teammate-123456789", "holder": "Amina", "owner_confirmed": True})
    client.put("/api/freelance/auto", json={"enabled": True, "per_day": 1, "committee": False, "ahead": False, "min_score": 1})
    for number in (601, 602, 603):
        lead(client, number, f"React dashboard {number}")
        with client.app.state.db.Session.begin() as session:
            session.get(FreelanceLead, f"freelancer:{number}").proposal = {}
    client.app.state.applier.tick()
    assert sorted(bid["from"] for bid in site.bids) == ["amina_dev", "mukira"]  # one each: two accounts, one bid a day each
    client.app.state.watcher.check_freelancer()
    assert sorted(user for user, _ids in site.reads) == ["amina_dev", "mukira"]  # each account asks about its own bids
