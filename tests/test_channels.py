"""Etsy orders as sales and Printify orders as costs on the Money page, from simulated accounts (no real calls)."""
import time

import httpx

from ai_hq import commerce, vault
from test_money import client  # noqa: F401  (client is a fixture)

DAY = 1767225600  # 2026-01-01


def connect(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        commerce.store(session, {
            "etsy": {"api_key": vault.protect("keystring"), "shared_secret": vault.protect("secret"), "access_token": vault.protect("123.token"),
                     "refresh_token": vault.protect("refresh"), "expires_at": time.time() + 3600, "shop_id": "99", "checked_at": "x"},
            "printify": {"api_key": vault.protect("printify-token"), "shop_id": "7", "checked_at": "x"}})


def money(value, currency="USD"):
    return {"amount": int(round(value * 100)), "divisor": 100, "currency_code": currency}


def receipt(number, subtotal, shipping=0.0, status="paid", refunds=(), tax=3.0):
    return {"receipt_id": number, "status": status, "is_paid": status != "open", "created_timestamp": DAY, "subtotal": money(subtotal),
            "total_shipping_cost": money(shipping), "total_tax_cost": money(tax), "grandtotal": money(subtotal + shipping + tax),
            "refunds": [{"amount": money(value)} for value in refunds]}


class Shops:
    def __init__(self):
        self.receipts = [receipt(1, 25, 5), receipt(2, 40, refunds=[10]), receipt(3, 30, status="canceled"), receipt(4, 15, status="open")]
        self.orders = [{"id": "o1", "status": "fulfilled", "created_at": "2026-01-02 10:00:00+00:00", "total_price": 1250, "total_shipping": 450, "total_tax": 0},
                       {"id": "o2", "status": "canceled", "created_at": "2026-01-03", "total_price": 900, "total_shipping": 400, "total_tax": 0}]
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        assert request.method == "GET"  # read-only
        if request.url.host == "api.etsy.com":
            assert request.headers["Authorization"] == "Bearer 123.token" and request.url.path == "/v3/application/shops/99/receipts"
            offset = int(request.url.params["offset"])
            return httpx.Response(200, json={"count": len(self.receipts), "results": self.receipts[offset:offset + 100]})
        assert request.headers["Authorization"] == "Bearer printify-token" and request.url.path == "/v1/shops/7/orders.json"
        return httpx.Response(200, json={"current_page": 1, "last_page": 1, "data": self.orders})


def use(client, handler):  # noqa: F811
    client.app.state.commerce.client = httpx.Client(transport=httpx.MockTransport(handler))


def test_etsy_sales_count_takings_after_discounts_and_refunds_without_tax(client):  # noqa: F811
    connect(client)
    shops = Shops(); use(client, shops)
    result = client.post("/api/money/channels/etsy/import").json()
    assert result["added"] == 2  # cancelled and unpaid orders don't count
    data = client.get("/api/money").json()
    etsy = data["channels"]["etsy"]
    assert etsy["connected"] and etsy["count"] == 2 and etsy["totals"] == {"USD": 60.0}  # 25 + 5 shipping, 40 - 10 refunded; tax left out
    notes = sorted(entry["note"] for entry in data["channels"]["recent"])
    assert notes == ["Etsy order 1", "Etsy order 2 (partly refunded)"]
    shops.receipts[0]["status"] = "fully refunded"  # refunded since
    again = client.post("/api/money/channels/etsy/import").json()
    assert (again["added"], again["changed"], again["removed"]) == (0, 0, 1)
    assert client.get("/api/money").json()["channels"]["etsy"]["totals"] == {"USD": 30.0}


def test_printify_orders_are_costs_and_both_reach_the_summary(client):  # noqa: F811
    from ai_hq import money
    connect(client)
    shops = Shops(); use(client, shops)
    client.post("/api/money/channels/etsy/import"); client.post("/api/money/channels/printify/import")
    data = client.get("/api/money").json()
    assert data["channels"]["printify"]["totals"] == {"USD": 17.0}  # the cancelled order isn't a cost
    with client.app.state.db.Session() as session:
        figures = money.summary(session, today="2026-01-15")["by_currency"]["USD"]
    assert figures["earned_month"] == 60 and figures["spent_month"] == 17
    assert client.post("/api/money/channels/printify/import").json()["added"] == 0  # importing again changes nothing


def test_etsy_without_the_new_permission_asks_to_authorize_again(client):  # noqa: F811
    connect(client)
    use(client, lambda request: httpx.Response(403, json={"error": "insufficient scope"}))
    response = client.post("/api/money/channels/etsy/import")
    assert response.status_code == 400 and "Authorize Etsy again" in response.json()["detail"]


def test_not_connected_marketplaces_say_what_to_do(client):  # noqa: F811
    response = client.post("/api/money/channels/etsy/import")
    assert response.status_code == 400 and "Business connections" in response.json()["detail"]
    assert client.post("/api/money/channels/amazon/import").status_code == 404
    data = client.get("/api/money").json()["channels"]
    assert not data["etsy"]["connected"] and not data["printify"]["connected"]
