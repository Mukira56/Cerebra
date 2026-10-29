"""Stripe payment links for the owner's invoices, against a simulated Stripe (no real API calls, no real money)."""
import json
from urllib.parse import parse_qs

import httpx
import pytest

from test_money import client, new, step  # noqa: F401  (client is a fixture)

KEY_TEXT = "rk_test_" + "a" * 30


class FakeStripe:
    """Just enough of Stripe's API: prices, payment links (honouring idempotency keys) and checkout sessions."""
    def __init__(self):
        self.calls, self.prices, self.links, self.sessions, self.seen = [], {}, {}, [], {}

    def __call__(self, request):
        self.calls.append(request)
        assert request.headers["Authorization"] == "Bearer " + KEY_TEXT
        path, form = request.url.path, {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        key = request.headers.get("Idempotency-Key")
        if key and key in self.seen:
            return httpx.Response(200, json=self.seen[key])
        if request.method == "POST" and path == "/v1/prices":
            body = {"id": f"price_{len(self.prices) + 1}", **form}
            self.prices[body["id"]] = body
        elif request.method == "POST" and path == "/v1/payment_links":
            number = len(self.links) + 1
            body = {"id": f"plink_{number}", "url": f"https://buy.stripe.com/test_{number}", "livemode": False, "active": True, "form": form}
            self.links[body["id"]] = body
        elif request.method == "POST" and path.startswith("/v1/payment_links/"):
            body = self.links[path.rsplit("/", 1)[1]]
            body["active"] = form.get("active") != "false"
        elif request.method == "GET" and path == "/v1/payment_links":
            body = {"data": list(self.links.values())[:1]}
        elif request.method == "GET" and path == "/v1/checkout/sessions":
            wanted = request.url.params.get("payment_link")
            body = {"data": [item for item in self.sessions if not wanted or item["payment_link"] == wanted]}
        else:
            return httpx.Response(404, json={"error": {"message": "Unknown path"}})
        if key:
            self.seen[key] = body
        return httpx.Response(200, json=body)

    def pay(self, link_id, amount, paid=True):
        self.sessions.append({"id": f"cs_{len(self.sessions) + 1}", "payment_link": link_id, "status": "complete" if paid else "open",
                              "payment_status": "paid" if paid else "unpaid", "amount_total": amount, "created": 1767225600})


@pytest.fixture
def stripe(client):  # noqa: F811
    fake = FakeStripe()
    client.app.state.payments.client = httpx.Client(transport=httpx.MockTransport(fake))
    assert client.put("/api/money/stripe", json={"key": KEY_TEXT}).status_code == 200
    checked = client.post("/api/money/stripe/check").json()
    assert checked["connected"] and checked["mode"] == "test"
    return fake


def test_the_key_is_protected_and_never_returned(client):  # noqa: F811
    assert client.put("/api/money/stripe", json={"key": "pk_live_publishable"}).status_code == 400
    client.put("/api/money/stripe", json={"key": KEY_TEXT})
    overview = client.get("/api/money").json()
    assert overview["stripe"]["configured"] and KEY_TEXT not in json.dumps(overview)
    assert KEY_TEXT not in json.dumps(client.get("/api/business/connections").json())
    with client.app.state.db.Session() as session:
        from ai_hq.models import Metadata
        assert KEY_TEXT not in json.dumps(session.get(Metadata, "business_connections").value)  # stored encrypted
    client.delete("/api/money/stripe")
    assert not client.get("/api/money").json()["stripe"]["configured"]


def test_a_payment_link_needs_confirmation_and_is_created_once(client, stripe):  # noqa: F811
    invoice = new(client, "invoice")
    link = client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True})
    assert link.status_code == 400  # a draft can't be paid
    invoice = step(client, invoice, "issue")
    assert client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={}).status_code == 400  # not confirmed
    first = client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True}).json()
    again = client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True}).json()
    assert first["url"] == again["url"] == "https://buy.stripe.com/test_1" and len(stripe.links) == 1
    price = stripe.prices["price_1"]
    assert price["unit_amount"] == "90000" and price["currency"] == "usd" and "INV-0001" in price["product_data[name]"]
    assert client.get("/api/money").json()["documents"][0]["payment_url"] == first["url"]


def test_stripe_payments_mark_the_invoice_paid_once_and_switch_the_link_off(client, stripe):  # noqa: F811
    invoice = step(client, new(client, "invoice"), "issue")
    client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True})
    stripe.pay("plink_1", 90000, paid=False)  # abandoned checkout
    assert client.post("/api/money/stripe/sync").json()["new_payments"] == 0
    stripe.pay("plink_1", 90000)
    assert client.post("/api/money/stripe/sync").json()["new_payments"] == 1
    assert client.post("/api/money/stripe/sync").json()["new_payments"] == 0  # recorded once
    doc = client.get("/api/money").json()["documents"][0]
    assert doc["status"] == "paid" and doc["payments"][0]["method"] == "Stripe" and doc["payments"][0]["reference"] == "cs_2"
    assert stripe.links["plink_1"]["active"] is False
    assert doc["payments"][0]["date"] == "2026-01-01" and doc["payments"][0]["amount"] == 900  # dated and sized by Stripe


def test_a_part_payment_gets_a_new_link_for_the_rest(client, stripe):  # noqa: F811
    invoice = step(client, new(client, "invoice"), "issue")
    client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True})
    step(client, invoice, "payments", amount=400, method="M-Pesa")
    second = client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True}).json()
    assert second["url"] == "https://buy.stripe.com/test_2" and stripe.prices["price_2"]["unit_amount"] == "50000"
    assert stripe.links["plink_1"]["active"] is False  # the old amount can't be paid any more


def test_stripe_errors_explain_the_permission_and_never_show_the_key(client):  # noqa: F811
    def refuse(request):
        return httpx.Response(403, json={"error": {"message": "The provided key does not have the required permissions for this endpoint."}})
    client.app.state.payments.client = httpx.Client(transport=httpx.MockTransport(refuse))
    client.put("/api/money/stripe", json={"key": KEY_TEXT})
    response = client.post("/api/money/stripe/check")
    assert response.status_code == 400 and "permissions" in response.json()["detail"] and KEY_TEXT not in response.text
    assert not client.get("/api/money").json()["stripe"]["connected"]


def test_zero_decimal_currencies():
    from ai_hq.payments import major, minor
    assert minor(1500, "UGX") == 1500 and minor(12.34, "usd") == 1234 and minor(2500, "KES") == 250000
    assert major(1500, "JPY") == 1500 and major(1234, "USD") == 12.34


def test_stripe_is_not_asked_again_about_finished_invoices_or_long_paused_products(client, stripe):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    from ai_hq.models import Product
    invoice = step(client, new(client, "invoice"), "issue")
    client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True})
    stripe.pay("plink_1", 90000)
    client.post("/api/money/stripe/sync")  # paid: the link is switched off
    before = len(stripe.calls)
    client.post("/api/money/stripe/sync")
    assert len(stripe.calls) == before  # nothing left to ask about
    item = client.post("/api/money/products", json={"name": "Template", "price": 10, "download_url": "https://drive.google.com/x"}).json()
    client.post(f"/api/money/products/{item['id']}/stripe-link", json={"confirmed": True})
    client.post(f"/api/money/products/{item['id']}/selling", json={"active": False})
    before = len(stripe.calls); client.post("/api/money/stripe/sync")
    assert len(stripe.calls) == before + 1  # just paused: late checkouts are still collected
    with client.app.state.db.Session.begin() as session:
        row = session.get(Product, item["id"])
        row.stripe = {**row.stripe, "paused_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()}
    before = len(stripe.calls); client.post("/api/money/stripe/sync")
    assert len(stripe.calls) == before


def test_money_news_reaches_the_phone_without_client_names_or_amounts(client, stripe):  # noqa: F811
    notifier = client.app.state.notifier
    client.put("/api/business/notifications", json={"ntfy_enabled": True})
    notifier.pending_messages()  # first run sets the starting point
    invoice = step(client, new(client, "invoice"), "issue")
    client.post(f"/api/money/documents/{invoice['id']}/stripe-link", json={"confirmed": True})
    stripe.pay("plink_1", 90000)
    client.post("/api/money/stripe/sync")
    _, messages = notifier.pending_messages()
    assert [title for title, _, _ in messages] == ["Cerebra · payment received"]
    text = " ".join(title + " " + body for title, body, _ in messages)
    assert "INV-0001" in text and "Ama" not in text and "900" not in text
    assert notifier.pending_messages()[1] == []  # told once
