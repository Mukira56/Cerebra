"""Several Etsy shops: added by signing in to the same Etsy app, never the same shop twice, at most five, a draft goes to the
shop chosen, the same item never goes to two shops, and orders are imported from every shop. Simulated."""
import time
from urllib.parse import parse_qs, urlparse

import httpx

from ai_hq import commerce, vault
from ai_hq.models import BusinessJob, Task
from test_commerce import client  # noqa: F401  (client is a fixture)

SHOPS = {"111": (5001, "BlueBirdPrints"), "222": (5002, "PlannerNook"), "333": (5003, "WallArtHaus")}


def first_shop(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        commerce.store(session, {"etsy": {"api_key": vault.protect("fixture-etsy-key"), "shared_secret": vault.protect("fixture-shared"),
                                          "redirect_uri": "https://my-site.invalid/callback", "shop_id": "5001", "shop_name": "BlueBirdPrints",
                                          "checked_at": "2026-11-01T00:00:00+00:00", "access_token": vault.protect("111.fixture-access"),
                                          "refresh_token": vault.protect("r"), "expires_at": time.time() + 3600}})


class Etsy:
    def __init__(self):
        self.next_user, self.calls = "222", []

    def __call__(self, request):
        self.calls.append((request.method, request.url.path, request.headers.get("Authorization", "")))
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": f"{self.next_user}.fixture-access", "refresh_token": "fixture-refresh", "expires_in": 3600})
        if request.url.path.startswith("/v3/application/users/"):
            shop_id, name = SHOPS[request.url.path.split("/")[4]]
            return httpx.Response(200, json={"shop_id": shop_id, "shop_name": name})
        if request.url.path.endswith("/listings"):
            return httpx.Response(200, json={"listing_id": 700 + len(self.calls), "state": "draft"})
        if request.url.path.endswith("/receipts"):
            shop = request.url.path.split("/")[4]
            return httpx.Response(200, json={"count": 1, "results": [{"receipt_id": int(shop) * 10, "grandtotal": {"amount": 1000, "divisor": 100, "currency_code": "USD"},
                                                                      "create_timestamp": 1761955200, "status": "paid"}]})
        return httpx.Response(404, json={"error": "unknown"})


def connect(client):  # noqa: F811
    site = Etsy()
    client.app.state.commerce.client.close()
    client.app.state.commerce.client = httpx.Client(transport=httpx.MockTransport(site))
    return site


def another_job(client, job_id):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        folder = session.get(BusinessJob, "job").output_dir
        session.add(Task(id="t-" + job_id, project_id="project", description="Another product", state="COMPLETED")); session.flush()
        session.add(BusinessJob(id=job_id, title="Another product", kind="svg", brief="Another product.", output_dir=folder, project_id="project", task_id="t-" + job_id))
    return job_id


def external(client, job, **payload):  # noqa: F811
    return client.post(f"/api/business/jobs/{job}/external", json=payload)


def add_shop(client, site, user):  # noqa: F811
    site.next_user = user
    state = parse_qs(urlparse(client.app.state.commerce.authorize_etsy(add=True)).query)["state"][0]
    return client.post("/api/business/connections/etsy/finish", json={"redirected_url": f"https://my-site.invalid/callback?code=fixture-code&state={state}"})


def test_another_shop_is_added_by_signing_in_and_never_twice_and_at_most_five(client):  # noqa: F811
    first_shop(client)
    site = connect(client)
    added = add_shop(client, site, "222")
    assert added.status_code == 200 and "PlannerNook" in added.json()["message"]
    assert [item["shop_name"] for item in client.get("/api/business/connections").json()["etsy"]["shops"]] == ["BlueBirdPrints", "PlannerNook"]
    again = add_shop(client, site, "222")
    assert again.status_code == 400 and "already connected" in again.json()["detail"]
    mine = add_shop(client, site, "111")  # the first shop signing in again
    assert mine.status_code == 400 and "already connected" in mine.json()["detail"]
    with client.app.state.db.Session.begin() as session:
        value = commerce.load(session)
        value[commerce.SHOPS] += [{"id": f"x{n}", "shop_id": str(9000 + n), "shop_name": f"S{n}"} for n in range(3)]
        commerce.store(session, value)
    full = client.post("/api/business/connections/etsy/authorize?add=true")
    assert full.status_code == 400 and "Up to 5" in full.json()["detail"]
    planner = client.get("/api/business/connections").json()["etsy"]["shops"][1]["id"]
    assert client.delete(f"/api/business/connections/etsy/shops/{planner}").status_code == 200
    assert "PlannerNook" not in [item["shop_name"] for item in client.app.state.commerce.etsy_shops()]
    assert vault.unprotect(client.app.state.commerce.shop("main")["access_token"]) == "111.fixture-access"  # the first shop is untouched


def test_a_draft_goes_to_the_chosen_shop_and_the_same_item_never_to_two(client):  # noqa: F811
    first_shop(client)
    site = connect(client)
    add_shop(client, site, "222")
    planner = client.app.state.commerce.etsy_shops()[1]["id"]
    job = "job"
    fields = {"quantity": 999, "title": "Undated weekly planner, printable PDF", "description": "A clean weekly planner.", "price": 4.5,
              "who_made": "i_did", "when_made": "made_to_order", "taxonomy_id": 1, "type": "download"}
    made = external(client, job, action="etsy_draft", fields=fields, confirmed=True, original_confirmed=True, shop=planner)
    assert made.status_code == 200 and "PlannerNook" in made.json()["message"]
    assert site.calls[-1][1] == "/v3/application/shops/5002/listings" and site.calls[-1][2] == "Bearer 222.fixture-access"
    copy = external(client, job, action="etsy_draft", fields=fields, confirmed=True, original_confirmed=True)  # the same job, the first shop
    assert copy.status_code == 400 and "another of your Etsy shops" in copy.json()["detail"]
    other = another_job(client, "job2")
    retitled = external(client, other, action="etsy_draft", fields={**fields, "title": "UNDATED weekly planner - printable PDF"}, confirmed=True, original_confirmed=True)
    assert retitled.status_code == 400  # the same item under another job: same words, same title
    fresh = external(client, other, action="etsy_draft", fields={**fields, "title": "Monthly budget tracker, printable PDF"}, confirmed=True, original_confirmed=True)
    assert fresh.status_code == 200 and site.calls[-1][1] == "/v3/application/shops/5001/listings"


def test_orders_are_imported_from_every_shop(client):  # noqa: F811
    first_shop(client)
    site = connect(client)
    add_shop(client, site, "222")
    counts = client.post("/api/money/channels/etsy/import")
    assert counts.status_code == 200, counts.text
    receipts = sorted(path for _method, path, _auth in site.calls if path.endswith("/receipts"))
    assert receipts == ["/v3/application/shops/5001/receipts", "/v3/application/shops/5002/receipts"]


def test_every_guide_link_opens_a_fixed_official_page(client, monkeypatch):  # noqa: F811
    import re
    from pathlib import Path
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    guides = (Path(__file__).parents[1] / "ai_hq" / "static" / "guides.js").read_text(encoding="utf-8")
    for key in ("freelancer:", "shopify:", "5. Add more shops (up to 5), each selling different products"):
        assert key in guides
    ids = set(re.findall(r'\["[^"\]]+", "([a-z0-9_]+)"\]', guides))
    assert {"freelancer_develop", "shopify_dev", "shopify_cc_docs"} <= ids
    for identifier in ids:
        assert client.post(f"/api/open-link/{identifier}").status_code == 200, identifier
    assert all(url.startswith("https://") for url in opened) and len(opened) == len(ids)
