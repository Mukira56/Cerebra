"""Digital products: clean packages, a Stripe link that delivers the download, and sales in the owner's earnings."""
import zipfile
from pathlib import Path

from test_money import client  # noqa: F401  (client is a fixture)
from test_payments import FakeStripe, stripe  # noqa: F401  (stripe is a fixture)


def product(client, **fields):  # noqa: F811
    response = client.post("/api/money/products", json={"name": "Bakery website template", "price": 29, "description": "A 4-page site", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_package_never_contains_secrets_history_or_installed_packages(client, tmp_path):  # noqa: F811
    from ai_hq.models import Project
    source = tmp_path / "site"
    for name, text in {"index.html": "<h1>Hi</h1>", "css/site.css": "h1{}", ".env": "SECRET=1", "apps/web/.env.local": "DB=x", ".env.example": "DB=",
                       ".git/config": "[core]", "node_modules/x/index.js": "", "data/app.sqlite3": "", "certs/server.key": "k"}.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(text, encoding="utf-8")
    with client.app.state.db.Session.begin() as session:
        session.add(Project(id="p1", name="Site", path=str(source), default_branch="main", test_commands=[]))
    item = product(client)
    info = client.post(f"/api/money/products/{item['id']}/package", json={"kind": "project", "id": "p1"}).json()
    names = sorted(zipfile.ZipFile(info["zip"]).namelist())
    assert names == [".env.example", "css/site.css", "index.html"] and info["files"] == 3
    assert Path(info["zip"]).parent == tmp_path / "business" / "Products" and client.app.state.opened[-1] == str(Path(info["zip"]).parent)
    again = client.post(f"/api/money/products/{item['id']}/package", json={"kind": "project", "id": "p1"}).json()
    assert again["zip"] != info["zip"]  # never overwrites
    assert client.post(f"/api/money/products/{item['id']}/package", json={"kind": "project", "id": "nope"}).status_code == 404


def test_selling_with_stripe_delivers_the_download_and_counts_each_sale_once(client, stripe):  # noqa: F811
    item = product(client)
    assert client.patch(f"/api/money/products/{item['id']}", json={"download_url": "http://insecure"}).status_code == 400
    client.patch(f"/api/money/products/{item['id']}", json={"download_url": "https://drive.google.com/file/d/abc/view"})
    assert client.post(f"/api/money/products/{item['id']}/stripe-link", json={}).status_code == 400  # not confirmed
    link = client.post(f"/api/money/products/{item['id']}/stripe-link", json={"confirmed": True}).json()
    assert link["url"] == "https://buy.stripe.com/test_1"
    form = stripe.links["plink_1"]["form"]
    assert "https://drive.google.com/file/d/abc/view" in form["after_completion[hosted_confirmation][custom_message]"]
    assert stripe.prices["price_1"]["unit_amount"] == "2900"
    assert client.patch(f"/api/money/products/{item['id']}", json={"price": 10}).status_code == 400  # live link has the old price
    stripe.pay("plink_1", 2900)
    stripe.sessions[-1]["customer_details"] = {"email": "buyer@example.com"}
    stripe.pay("plink_1", 2900, paid=False)
    result = client.post("/api/money/stripe/sync").json()
    assert result["new_sales"] == 1 and client.post("/api/money/stripe/sync").json()["new_sales"] == 0
    listed = client.get("/api/money").json()
    sold = listed["products"][0]
    assert sold["sold"] == 1 and sold["revenue"] == 29 and sold["sales"][0]["email"] == "buyer@example.com" and sold["selling"]
    assert sold["sales"][0]["date"] == "2026-01-01" and sold["sales"][0]["amount"] == 29  # dated and sized by Stripe
    paused = client.post(f"/api/money/products/{item['id']}/selling", json={"active": False}).json()
    assert paused["status"] == "paused" and stripe.links["plink_1"]["active"] is False
    assert client.delete(f"/api/money/products/{item['id']}").status_code == 400  # has sales: kept for the record
    resumed = client.post(f"/api/money/products/{item['id']}/selling", json={"active": True}).json()
    assert resumed["selling"] and stripe.links["plink_1"]["active"] is True


def test_product_sales_count_as_earnings(client):  # noqa: F811
    from ai_hq import money
    from ai_hq.models import Product
    item = product(client)
    today = money._today()
    with client.app.state.db.Session.begin() as session:
        session.get(Product, item["id"]).sales = [{"id": "cs_1", "amount": 29.0, "date": today, "email": ""}]
    figures = client.get("/api/money").json()["summary"]["by_currency"]["USD"]
    assert figures["earned_month"] == 29 and figures["earned_year"] == 29


def test_unsold_drafts_can_be_deleted_and_prices_must_be_real(client):  # noqa: F811
    assert client.post("/api/money/products", json={"name": "Free thing", "price": 0}).status_code == 400
    assert client.post("/api/money/products", json={"name": "", "price": 5}).status_code == 400
    item = product(client)
    assert client.delete(f"/api/money/products/{item['id']}").json() == {"deleted": True}
    assert client.get("/api/money").json()["products"] == []


def test_a_product_without_a_download_sells_a_service_and_collects_the_phone(client, stripe):  # noqa: F811
    item = product(client, name="Website deposit (50%)", price=300, description="Books your 5-page website")
    assert client.get("/api/money").json()["products"][0]["service"] is True
    link = client.post(f"/api/money/products/{item['id']}/stripe-link", json={"confirmed": True}).json()
    form = stripe.links["plink_1"]["form"]
    assert link["url"] == "https://buy.stripe.com/test_1" and form["phone_number_collection[enabled]"] == "true"
    assert "I'll contact you" in form["after_completion[hosted_confirmation][custom_message]"] and "Download" not in form["after_completion[hosted_confirmation][custom_message]"]
    stripe.pay("plink_1", 30000)
    stripe.sessions[-1]["customer_details"] = {"email": "client@example.com", "phone": "+254700000000"}
    client.post("/api/money/stripe/sync")
    sale = client.get("/api/money").json()["products"][0]["sales"][0]
    assert sale["email"] == "client@example.com" and sale["phone"] == "+254700000000" and sale["amount"] == 300
