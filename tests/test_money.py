"""Money center: quotes, invoices, payments and what the owner has earned and is owed. No real payment service."""
import pytest
from fastapi.testclient import TestClient

from ai_hq.api import create_app
from ai_hq.config import Settings
from test_product_api import KEY


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.opened = []
    app.state.open_document = app.state.opened.append  # never opens a browser in tests
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        client.put("/api/business/settings", json={"output_root": str(tmp_path / "business"), "currency": "USD"})
        yield client


def new(api, kind="quote", **fields):
    response = api.post("/api/money/documents", json={"kind": kind, "client": "Ama's Bakery", "client_email": "ama@example.com",
                                                          "items": [{"description": "Bakery website: 4 pages", "quantity": 1, "unit_price": 800},
                                                                    {"description": "Logo in SVG", "quantity": 2, "unit_price": 50}], **fields})
    assert response.status_code == 201, response.text
    return response.json()


def step(client, doc, name, **payload):
    response = client.post(f"/api/money/documents/{doc['id']}/{name}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def figures(client):
    data = client.get("/api/money").json()
    return data["summary"]["by_currency"]["USD"]


def test_a_quote_becomes_a_deposit_then_a_balance_invoice_and_is_paid(client):
    client.put("/api/money/settings", json={"business_name": "Mukira Studio", "payment_terms_days": 7})
    quote = new(client)
    assert quote["status"] == "draft" and quote["number"] == "" and quote["total"] == 900
    quote = step(client, quote, "issue")
    assert quote["number"] == "Q-0001" and quote["status"] == "sent" and quote["due_date"]
    assert figures(client)["pipeline"] == 900
    assert client.patch(f"/api/money/documents/{quote['id']}", json={"items": []}).status_code == 400  # issued: frozen
    deposit = step(client, quote, "accept", deposit_percent=50)
    assert deposit["kind"] == "invoice" and deposit["status"] == "draft" and deposit["total"] == 450
    assert figures(client)["won_unbilled"] == 450 and figures(client)["pipeline"] == 0
    deposit = step(client, deposit, "issue")
    assert deposit["number"] == "INV-0001" and figures(client)["owed"] == 450
    deposit = step(client, deposit, "payments", amount=450, method="M-Pesa")
    assert deposit["status"] == "paid" and figures(client)["earned_month"] == 450 and figures(client)["owed"] == 0
    rest = client.post(f"/api/money/documents/{quote['id']}/balance").json()
    assert rest["total"] == 450 and "Balance for quote Q-0001" in rest["items"][0]["description"]
    rest = step(client, rest, "issue")
    assert rest["number"] == "INV-0002"
    step(client, rest, "payments", amount=200)
    assert step(client, rest, "payments", amount=250)["status"] == "paid"
    assert figures(client) | {} and figures(client)["earned_month"] == 900
    assert client.post(f"/api/money/documents/{quote['id']}/balance").status_code == 400  # all invoiced


def test_overdue_invoices_and_voiding_keep_numbers(client):
    from ai_hq import money
    invoice = step(client, new(client, "invoice"), "issue")
    with client.app.state.db.Session.begin() as session:
        session.get(money.MoneyDocument, invoice["id"]).due_date = "2000-01-01"
    assert figures(client)["overdue_count"] == 1 and figures(client)["overdue"] == 900
    voided = client.delete(f"/api/money/documents/{invoice['id']}").json()
    assert voided["status"] == "void" and voided["number"] == "INV-0001"
    draft = new(client, "invoice")
    assert client.delete(f"/api/money/documents/{draft['id']}").json() == {"deleted": True}
    assert step(client, new(client, "invoice"), "issue")["number"] == "INV-0002"  # never reused


def test_checks_on_what_the_owner_enters(client):
    bad = client.post("/api/money/documents", json={"kind": "invoice", "client": "X", "items": [{"description": "", "unit_price": 5}]})
    assert bad.status_code == 400
    assert client.post("/api/money/documents", json={"kind": "invoice", "client": "", "items": [{"description": "A", "unit_price": 5}]}).status_code == 400
    assert client.post("/api/money/documents", json={"kind": "invoice", "client": "X", "items": [{"description": "A", "unit_price": -5}]}).status_code == 400
    doc = new(client, "invoice")
    assert client.patch(f"/api/money/documents/{doc['id']}", json={"payment_url": "javascript:alert(1)"}).status_code == 400
    assert client.post(f"/api/money/documents/{doc['id']}/payments", json={"amount": 10}).status_code == 400  # not issued yet
    assert client.put("/api/money/settings", json={"email": "not an email"}).status_code == 400


def test_the_printable_page_escapes_everything_and_is_saved_in_the_business_folder(client, tmp_path):
    doc = new(client, "invoice", client="<script>alert(1)</script>", notes="Thanks!\nSee you soon")
    client.patch(f"/api/money/documents/{doc['id']}", json={"payment_url": "https://buy.stripe.com/test_123"})
    page = client.get(f"/api/money/documents/{doc['id']}/page").json()["html"]
    assert "<script>alert" not in page and "&lt;script&gt;" in page and "DRAFT" in page and "https://buy.stripe.com/test_123" in page
    saved = client.post(f"/api/money/documents/{doc['id']}/save").json()["path"]
    assert saved.startswith(str(tmp_path / "business")) and client.app.state.opened == [saved]


def test_a_business_job_quote_and_its_payments_reach_the_job_ledger(client, tmp_path):
    from ai_hq.models import BusinessJob, BusinessRecord
    with client.app.state.db.Session.begin() as session:
        session.add(BusinessJob(id="job1", title="Plumber website", kind="service_site", client="Kip Plumbing", output_dir=str(tmp_path / "job1")))
        session.add(BusinessRecord(job_id="job1", scope={"price": 600, "pages": ["Home", "Quote"], "features": ["Quote form"], "client": "Kip Plumbing", "exclusions": ["Hosting"]}))
    quote = client.post("/api/money/documents/from-job/job1").json()
    assert quote["client"] == "Kip Plumbing" and quote["total"] == 600 and quote["job_id"] == "job1" and "Hosting" in quote["notes"]
    invoice = step(client, step(client, step(client, quote, "issue"), "accept"), "issue")
    step(client, invoice, "payments", amount=600)
    job = client.get("/api/business/jobs/job1/delivery").json()
    assert [entry["amount"] for entry in job["money"]["entries"]] == [600]
    assert figures(client)["earned_month"] == 600  # counted once, from the job's ledger


def test_the_in_app_preview_is_sandboxed(client):
    doc = new(client, "invoice")
    response = client.get(f"/api/money/documents/{doc['id']}/print")
    assert response.status_code == 200 and "Invoice (draft)" in response.text
    policy = response.headers["Content-Security-Policy"]
    assert policy.startswith("sandbox") and "script-src" not in policy and "default-src 'none'" in policy and "form-action 'none'" in policy


def test_the_overview_shows_the_money_at_a_glance(client):
    invoice = step(client, new(client, "invoice"), "issue")
    step(client, invoice, "payments", amount=100)
    glance = client.get("/api/overview").json()["money"]
    assert glance["currency"] == "USD" and glance["by_currency"]["USD"]["earned_month"] == 100 and glance["by_currency"]["USD"]["owed"] == 800
