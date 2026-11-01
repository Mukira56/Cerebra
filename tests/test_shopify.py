"""Shopify stores, up to five, each through its own Dev Dashboard app: a refused app isn't kept, the 24-hour token is
asked for again when it runs out, a draft product (never active) goes to the chosen store after confirmation, and orders
from every store count as sales without tax. Simulated."""
import json

import httpx

from ai_hq import shopify as shopify_module
from test_shops import another_job, external
from test_commerce import client  # noqa: F401  (client is a fixture)

APPS = {"client-id-north-0001": "north-store.myshopify.com", "client-id-south-0002": "south-store.myshopify.com"}


class Site:
    def __init__(self):
        self.tokens, self.calls, self.products = 0, [], []

    def __call__(self, request):
        host, path = request.url.host, request.url.path
        if path == "/admin/oauth/access_token":
            form = dict(item.split("=", 1) for item in request.content.decode().split("&"))
            assert form["grant_type"] == "client_credentials"
            if APPS.get(form["client_id"]) != host or form["client_secret"] != "fixture-secret-123":
                return httpx.Response(400, json={"error": "shop_not_permitted", "error_description": "Client credentials cannot be performed on this shop."})
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"shpat_{host[:5]}_{self.tokens}", "scope": "write_products,read_orders", "expires_in": 86399})
        assert path == f"/admin/api/{shopify_module.API_VERSION}/graphql.json"
        assert request.headers["X-Shopify-Access-Token"].startswith(f"shpat_{host[:5]}")
        body = json.loads(request.content)
        self.calls.append((host, body["query"].split("(", 1)[0].split("{", 1)[0].strip() or "shop"))
        if "shop {" in body["query"]:
            return httpx.Response(200, json={"data": {"shop": {"name": host.split("-")[0].title() + " Prints", "currencyCode": "USD"}}})
        if "productCreate" in body["query"]:
            product = body["variables"]["product"]
            assert product["status"] == "DRAFT"  # never published by Cerebra
            self.products.append((host, product))
            return httpx.Response(200, json={"data": {"productCreate": {"product": {"id": "gid://shopify/Product/1", "handle": "x", "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/9"}]}}, "userErrors": []}}})
        if "productVariantsBulkUpdate" in body["query"]:
            self.products.append((host, body["variables"]["variants"][0]))
            return httpx.Response(200, json={"data": {"productVariantsBulkUpdate": {"userErrors": []}}})
        if "orders(" in body["query"]:
            money = lambda amount: {"shopMoney": {"amount": amount, "currencyCode": "USD"}}  # noqa: E731
            nodes = [{"id": f"gid://shopify/Order/{host[:5]}1", "name": "#1001", "createdAt": "2026-10-30T10:00:00Z", "cancelledAt": None, "displayFinancialStatus": "PAID",
                      "currentTotalPriceSet": money("27.00"), "currentTotalTaxSet": money("2.00")},
                     {"id": f"gid://shopify/Order/{host[:5]}2", "name": "#1002", "createdAt": "2026-10-31T10:00:00Z", "cancelledAt": "2026-10-31T12:00:00Z",
                      "displayFinancialStatus": "VOIDED", "currentTotalPriceSet": money("10.00"), "currentTotalTaxSet": money("0")}]
            return httpx.Response(200, json={"data": {"orders": {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}})
        return httpx.Response(404)


def connect(client):  # noqa: F811
    site = Site()
    client.app.state.shopify.client = httpx.Client(transport=httpx.MockTransport(site))
    return site


def add(client, address, client_id, secret="fixture-secret-123"):  # noqa: F811
    return client.post("/api/business/shopify/stores", json={"domain": address, "client_id": client_id, "client_secret": secret})


def test_stores_connect_through_their_own_app_and_a_refused_one_is_not_kept(client):  # noqa: F811
    site = connect(client)
    first = add(client, "https://North-Store.myshopify.com/admin", "client-id-north-0001")
    assert first.status_code == 200 and first.json()["stores"][0]["name"] == "North Prints" and first.json()["stores"][0]["domain"] == "north-store.myshopify.com"
    assert add(client, "north-store", "client-id-north-0001").json()["detail"].endswith("already connected")
    wrong = add(client, "south-store", "client-id-north-0001")  # an app from another organization
    assert wrong.status_code == 400 and "same Shopify organization" in wrong.json()["detail"]
    assert add(client, "evil.example.com", "client-id-south-0002").status_code == 400  # only myshopify.com addresses
    assert add(client, "south-store", "client-id-south-0002").status_code == 200
    assert [item["domain"] for item in client.get("/api/business/shopify").json()["stores"]] == ["north-store.myshopify.com", "south-store.myshopify.com"]
    tokens = site.tokens
    store = client.app.state.shopify.stores()[0]
    client.app.state.shopify._update(store["id"], expires_at=0)  # the 24-hour token ran out
    assert client.post(f"/api/business/shopify/stores/{store['id']}/check").status_code == 200 and site.tokens == tokens + 1
    assert client.delete(f"/api/business/shopify/stores/{store['id']}").status_code == 200
    assert [item["domain"] for item in client.app.state.shopify.stores()] == ["south-store.myshopify.com"]


def test_at_most_five_stores(client):  # noqa: F811
    connect(client)
    client.app.state.shopify._save([{"id": f"s{n}", "domain": f"s{n}.myshopify.com"} for n in range(5)])
    full = add(client, "north-store", "client-id-north-0001")
    assert full.status_code == 400 and "Up to 5" in full.json()["detail"]


def test_a_draft_product_goes_to_the_chosen_store_and_orders_count_as_sales(client):  # noqa: F811
    site = connect(client)
    add(client, "north-store", "client-id-north-0001"); add(client, "south-store", "client-id-south-0002")
    south = client.app.state.shopify.stores()[1]["id"]
    fields = {"title": "Undated weekly planner", "description": "A clean weekly planner.\nPrintable <PDF>.", "price": 4.5, "tags": ["planner"]}
    assert external(client, "job", action="shopify_draft", fields=fields).status_code == 400  # not confirmed
    made = external(client, "job", action="shopify_draft", fields=fields, confirmed=True, shop=south)
    assert made.status_code == 200 and "South Prints" in made.json()["message"] and "isn't published" in made.json()["message"]
    (host, product), (_host, variant) = site.products
    assert host == "south-store.myshopify.com" and product["descriptionHtml"] == "<p>A clean weekly planner.</p><p>Printable &lt;PDF&gt;.</p>"
    assert variant == {"id": "gid://shopify/ProductVariant/9", "price": "4.50"}
    assert external(client, "job", action="shopify_draft", fields=fields, confirmed=True, shop=south).json()["product_id"] == "gid://shopify/Product/1"
    assert len(site.products) == 2  # the same confirmed draft is never made twice
    assert external(client, another_job(client, "job2"), action="shopify_draft", fields={**fields, "status": "ACTIVE"}, confirmed=True).status_code == 400
    imported = client.post("/api/money/channels/shopify/import")
    assert imported.status_code == 200 and imported.json()["added"] == 2  # one paid order from each store; the voided one doesn't count
    shop = client.get("/api/money").json()["channels"]["shopify"]
    assert shop["connected"] and shop["count"] == 2 and shop["totals"] == {"USD": 50.0}  # 27 - 2 tax, twice
