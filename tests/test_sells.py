"""What sells (Etsy phase 3): each Etsy order's items traced back through the draft Cerebra made to its listing and
niche, refunds and cancellations taken out on the next import, and sales of other listings shown apart. Simulated."""
from ai_hq.models import EtsyListing, EtsyNiche, Metadata
from test_channels import Shops, connect, money, receipt, use
from test_money import client  # noqa: F401  (client is a fixture)


def item(transaction, listing, title, price, quantity=1):
    return {"transaction_id": transaction, "listing_id": listing, "title": title, "price": money(price), "quantity": quantity}


def made_in_cerebra(client):  # noqa: F811
    """Two niches with a listing each, both sent to Etsy as drafts that became listings 501 and 502."""
    with client.app.state.db.Session.begin() as session:
        session.add_all([EtsyNiche(id="n-planner", keyword="weekly planner printable", score=70, label="strong"),
                         EtsyNiche(id="n-chore", keyword="kids chore chart", score=50, label="test")])
        session.flush()
        session.add_all([EtsyListing(id="l1", niche_id="n-planner", title="Weekly planner", job_id="job-a"),
                         EtsyListing(id="l2", niche_id="n-chore", title="Chore chart", job_id="job-b")])
        for key, job, listing in (("a", "job-a", 501), ("b", "job-b", 502)):
            session.add(Metadata(key=f"business_operation_{key}", value={"job_id": job, "action": "etsy_draft", "status": "succeeded",
                                                                         "result": {"listing_id": listing}}))


def test_sales_are_traced_to_the_niches_that_earn(client):  # noqa: F811
    connect(client)
    made_in_cerebra(client)
    shops = Shops()
    first, second, refunded, mine = receipt(11, 9), receipt(12, 13.5), receipt(13, 4.5, refunds=[4.5]), receipt(14, 20)
    first["transactions"] = [item(1, 501, "Weekly planner", 4.5, 2)]
    second["transactions"] = [item(2, 501, "Weekly planner", 4.5), item(3, 502, "Chore chart", 9)]
    refunded["transactions"] = [item(4, 502, "Chore chart", 4.5)]
    mine["transactions"] = [item(5, 999, "Hand-drawn wall art", 20)]
    shops.receipts = [first, second, refunded, mine]
    use(client, shops)
    assert client.post("/api/money/channels/etsy/import").status_code == 200
    sells = client.get("/api/etsy").json()["performance"]
    assert sells["orders"] == 3  # the fully refunded order doesn't count
    planner, chore = sells["niches"]
    assert (planner["keyword"], planner["units"], planner["revenue"], planner["orders"], planner["listings"]) == ("weekly planner printable", 3, {"USD": 13.5}, 2, 1)
    assert (chore["keyword"], chore["units"], chore["revenue"]) == ("kids chore chart", 1, {"USD": 9.0})
    assert sells["listings"][0]["title"] == "Hand-drawn wall art" and not sells["listings"][0]["made_here"]  # best seller overall, made outside Cerebra
    assert sells["outside"]["units"] == 1 and sells["outside"]["revenue"] == {"USD": 20.0}

    second["status"] = "canceled"  # cancelled after the first import
    assert client.post("/api/money/channels/etsy/import").status_code == 200
    sells = client.get("/api/etsy").json()["performance"]
    assert [(item["keyword"], item["units"]) for item in sells["niches"]] == [("weekly planner printable", 2)]


def test_no_orders_yet(client):  # noqa: F811
    assert client.get("/api/etsy").json()["performance"] == {"orders": 0, "niches": [], "listings": [], "outside": {"units": 0, "revenue": {}}}
