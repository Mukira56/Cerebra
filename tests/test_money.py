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


def test_reminders_get_firmer_as_an_invoice_gets_later_and_are_sent_by_the_owner(client):
    from datetime import date, timedelta
    from urllib.parse import unquote
    from ai_hq import money
    client.put("/api/money/settings", json={"business_name": "Mukira Studio", "payment_instructions": "M-Pesa till 123456"})
    invoice = step(client, new(client, "invoice"), "issue")
    client.patch(f"/api/money/documents/{invoice['id']}", json={"payment_url": "https://buy.stripe.com/test_1"})
    step(client, invoice, "payments", amount=100)
    text = client.get(f"/api/money/documents/{invoice['id']}/reminder").json()
    assert text["tone"] == "friendly" and "USD 800.00" in text["subject"] and "https://buy.stripe.com/test_1" in text["body"]
    assert "M-Pesa till 123456" in text["body"] and text["body"].startswith("Hello Ama's Bakery,") and text["body"].endswith("Mukira Studio")
    assert text["to"] == "ama@example.com" and unquote(text["mailto"]).startswith("mailto:ama@example.com?subject=Invoice INV-0001")
    tones = []
    for late in (3, 12, 45):
        with client.app.state.db.Session.begin() as session:
            session.get(money.MoneyDocument, invoice["id"]).due_date = (date.today() - timedelta(days=late)).isoformat()
        reply = client.get(f"/api/money/documents/{invoice['id']}/reminder").json()
        tones.append((reply["tone"], reply["days_late"]))
    assert tones == [("friendly", 3), ("firm", 12), ("final", 45)]
    assert client.post(f"/api/money/documents/{invoice['id']}/reminder", json={"action": "open"}).json() == {"opened": True}
    assert client.app.state.opened[-1].startswith("mailto:ama@example.com?subject=Final%20reminder")  # the owner's email app, never sent by Cerebra
    marked = client.post(f"/api/money/documents/{invoice['id']}/reminder", json={"action": "sent", "tone": "final"}).json()
    assert marked["provider"]["reminders"][0]["tone"] == "final"
    assert client.get(f"/api/money/documents/{invoice['id']}/reminder").json()["sent"][0]["tone"] == "final"
    draft = new(client, "invoice")
    assert client.get(f"/api/money/documents/{draft['id']}/reminder").status_code == 400  # not issued yet


def test_saved_services_and_their_checks(client):
    saved = client.put("/api/money/settings", json={"services": [{"name": "5-page website", "price": 600}, {"name": " Logo  design ", "price": "150"}]}).json()
    assert saved["services"] == [{"name": "5-page website", "price": 600.0}, {"name": "Logo design", "price": 150.0}]
    assert client.put("/api/money/settings", json={"services": [{"name": "", "price": 5}]}).status_code == 400
    assert client.put("/api/money/settings", json={"services": [{"name": "X", "price": -1}]}).status_code == 400
    assert client.get("/api/money").json()["settings"]["services"][1]["name"] == "Logo design"


def make_plan(api, **fields):
    from ai_hq import money
    with api.app.state.db.Session.begin() as session:
        return money.plan_public(money.save_plan(session, None, {"client": "Kip Plumbing", "client_email": "kip@example.com", "every": "month",
            "items": [{"description": "Website care plan: updates, backups, hosting checks", "quantity": 1, "unit_price": 50}], **fields}))


def stored_plan(api, plan_id):  # read directly: opening the Money page would bill up to today's real date
    from ai_hq import money
    from ai_hq.models import RecurringPlan
    with api.app.state.db.Session() as session:
        return money.plan_public(session.get(RecurringPlan, plan_id))


def run(api, today):
    from ai_hq import money
    with api.app.state.db.Session.begin() as session:
        return [(doc.status, doc.number, doc.notes.rsplit(" ", 1)[-1].rstrip(".")) for doc in money.run_plans(session, today=today)]


def test_a_recurring_plan_bills_each_period_once_and_catches_up(client):
    plan = make_plan(client, next_date="2026-01-31")
    assert plan["total"] == 50 and plan["monthly"] == 50
    assert run(client, "2026-01-30") == []  # not due yet
    # The laptop was off: by mid-March three periods are due, each dated on its own period (the 31st becomes the 28th).
    assert run(client, "2026-03-15") == [("draft", "", "2026-01-31"), ("draft", "", "2026-02-28")]
    assert run(client, "2026-03-15") == []  # each period once
    assert run(client, "2026-03-28") == [("draft", "", "2026-03-28")]
    stored = stored_plan(client, plan["id"])
    assert stored["next_date"] == "2026-04-28" and [entry["date"] for entry in stored["made"]] == ["2026-01-31", "2026-02-28", "2026-03-28"]


def test_a_plan_can_issue_automatically_pause_and_be_deleted(client):
    plan = make_plan(client, client="Ama's Bakery", every="quarter", next_date="2026-01-10", auto_issue=True,
                     items=[{"description": "Quarterly SEO report", "quantity": 1, "unit_price": 120}])
    assert plan["monthly"] == 40
    assert run(client, "2026-01-10") == [("sent", "INV-0001", "2026-01-10")]
    assert stored_plan(client, plan["id"])["next_date"] == "2026-04-10"
    client.patch(f"/api/money/plans/{plan['id']}", json={"active": False})
    assert run(client, "2027-01-01") == []  # paused
    assert client.post("/api/money/plans", json={"client": "X", "every": "weekly", "items": [{"description": "A", "unit_price": 1}]}).status_code == 400
    assert client.post("/api/money/plans", json={"client": "X", "items": []}).status_code == 400
    assert client.delete(f"/api/money/plans/{plan['id']}").json() == {"deleted": True}
    assert any(doc["client"] == "Ama's Bakery" and doc["number"] == "INV-0001" for doc in client.get("/api/money").json()["documents"])  # its invoices stay


def test_a_plan_starting_today_bills_straight_away(client):
    from ai_hq import money
    created = client.post("/api/money/plans", json={"client": "Kip Plumbing", "items": [{"description": "Care plan", "unit_price": 50}]}).json()
    docs = [doc for doc in client.get("/api/money").json()["documents"] if doc["provider"].get("plan") == created["id"]]
    assert len(docs) == 1 and docs[0]["status"] == "draft" and money._today() in docs[0]["notes"]


def test_the_year_export_lists_everything_once_and_is_safe_in_excel(client, tmp_path):
    import csv
    from ai_hq.models import BusinessJob, BusinessRecord, ChannelEntry, Product
    with client.app.state.db.Session.begin() as session:
        session.add(BusinessJob(id="job1", title="Plumber website", kind="service_site", client="Kip Plumbing", output_dir=str(tmp_path / "job1")))
        session.add(BusinessRecord(job_id="job1", scope={"price": 600, "client": "Kip Plumbing"}))
        session.add(Product(id="prod1", name="Bakery template", price=29, currency="USD", sales=[{"id": "cs_9", "amount": 29.0, "date": "2026-02-02", "email": "b@example.com"}]))
        session.add(ChannelEntry(id="etsy:5", source="etsy", kind="sale", amount=30, currency="USD", date="2026-03-03", note="Etsy order 5"))
        session.add(ChannelEntry(id="printify:o1", source="printify", kind="cost", amount=17, currency="USD", date="2026-03-04", note="Printify order o1"))
        session.add(ChannelEntry(id="etsy:4", source="etsy", kind="sale", amount=99, currency="USD", date="2025-12-30", note="Etsy order 4"))  # other year
    sneaky = step(client, new(client, "invoice", client="=HYPERLINK(\"http://evil\")"), "issue")
    step(client, sneaky, "payments", amount=900, method="bank")
    job_invoice = step(client, step(client, client.post("/api/money/documents/from-job/job1").json(), "issue"), "accept")
    step(client, step(client, job_invoice, "issue"), "payments", amount=600, method="M-Pesa")
    result = client.post("/api/money/export", json={"year": 2026}).json()
    with open(result["path"], encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    kinds = sorted((row["What"], float(row["Amount"]), row["Type"]) for row in rows)
    assert kinds == sorted([("invoice payment", 900, "income"), ("invoice payment", 600, "income"), ("product sale (Stripe)", 29, "income"),
                            ("etsy order", 30, "income"), ("printify order", 17, "cost")])
    assert len(rows) == 5 and result["rows"] == 5  # the job's invoice payment is listed once, the 2025 order not at all
    assert next(row for row in rows if row["What"] == "invoice payment")["Client or buyer"].startswith("'=")  # not a formula
    assert client.app.state.opened[-1] == str(tmp_path / "business" / "Quotes and invoices")
    again = client.post("/api/money/export", json={"year": 2026}).json()
    assert again["path"] != result["path"]  # never overwrites
    assert client.post("/api/money/export", json={"year": "soon"}).status_code == 400


def test_a_job_invoice_in_another_currency_counts_in_that_currency_once(client, tmp_path):
    from ai_hq.models import BusinessJob, BusinessRecord
    with client.app.state.db.Session.begin() as session:
        session.add(BusinessJob(id="job2", title="Salon site", kind="website", client="Wanjiku Salon", output_dir=str(tmp_path / "job2")))
        session.add(BusinessRecord(job_id="job2", scope={"price": 40000, "currency": "KES", "client": "Wanjiku Salon"}))
    invoice = step(client, step(client, step(client, client.post("/api/money/documents/from-job/job2").json(), "issue"), "accept"), "issue")
    assert invoice["currency"] == "KES"
    step(client, invoice, "payments", amount=40000, method="M-Pesa")
    money_by = client.get("/api/money").json()["summary"]["by_currency"]
    assert money_by["KES"]["earned_month"] == 40000 and money_by["USD"]["earned_month"] == 0  # not counted as 40,000 dollars
    ledger = client.get("/api/business/jobs/job2/delivery").json()["money"]["entries"]
    assert [entry["amount"] for entry in ledger] == [40000] and ledger[0]["invoice"] == invoice["id"]  # the job still shows it


def test_ledger_copies_from_before_the_mark_are_not_counted_twice(client, tmp_path):
    from ai_hq.models import BusinessJob, BusinessRecord
    with client.app.state.db.Session.begin() as session:
        session.add(BusinessJob(id="job3", title="Old site", kind="website", client="Old client", output_dir=str(tmp_path / "job3")))
        session.add(BusinessRecord(job_id="job3", scope={"price": 300, "client": "Old client"}))
    invoice = step(client, step(client, step(client, client.post("/api/money/documents/from-job/job3").json(), "issue"), "accept"), "issue")
    step(client, invoice, "payments", amount=300)
    with client.app.state.db.Session.begin() as session:  # as 0.36-0.42 wrote it: no "invoice" mark, plus a payment recorded by hand
        record = session.get(BusinessRecord, "job3")
        record.ledger = [{key: value for key, value in item.items() if key != "invoice"} for item in record.ledger] + [
            {"id": "x1", "kind": "payment", "amount": 50, "hours": 0, "date": invoice["issued_at"], "note": "Tip in cash"}]
    assert client.get("/api/money").json()["summary"]["by_currency"]["USD"]["earned_month"] == 350
