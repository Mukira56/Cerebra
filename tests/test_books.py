"""Books, Phase 1: KDP's numbers and maths (checked against KDP's own worked examples), niches scored only from evidence,
and books with their formats and prices."""
import pytest

from ai_hq import books
from test_freelance import client  # noqa: F401  (client is a fixture)


def test_printing_costs_match_kdps_own_examples():
    assert books.print_cost(300, "6x9") == 4.60  # KDP: 1.00 + 300 x 0.012
    assert books.print_cost(100, "6x9") == 2.30 and books.print_cost(108, "6x9") == 2.30  # short books: fixed cost only
    assert books.print_cost(110, "6x9") == 2.32
    assert books.print_cost(300, "7x10") == 6.10  # large trim: 0.017 a page
    assert books.print_cost(300, "6x9", "hardcover") == 9.25  # KDP: 5.65 + 300 x 0.012
    assert books.print_cost(90, "7x10", "hardcover") == 7.49
    assert books.trim_class("6.14x9.21") == "large" and books.trim_class("6x9") == "regular"


def test_print_royalty_tiers_and_the_minimum_price():
    low = books.print_royalty(9.98, 300, "6x9")
    assert low["rate"] == 0.50 and low["royalty"] == 0.39  # the 9.98 cliff
    high = books.print_royalty(9.99, 300, "6x9")
    assert high["rate"] == 0.60 and high["royalty"] == 1.39
    assert books.print_royalty(12.99, 120, "6x9")["royalty"] == round(0.6 * 12.99 - 2.44, 2)
    assert low["minimum_price"] == 9.20 and not books.print_royalty(9.0, 300, "6x9")["allowed"]
    assert books.print_royalty(20, 500, "7x10")["minimum_price"] == 15.84  # 9.50 to print: only covered at 60%


def test_kindle_royalty_bands():
    assert books.ebook_royalty(2.99, 1)["royalty"] == 1.99  # 70% of (2.99 - 0.15 delivery)
    assert books.ebook_royalty(12.99, 2)["rate"] == 0.70  # the 70% band reaches 12.99 since July 2026
    launch = books.ebook_royalty(0.99, 1)
    assert launch["rate"] == 0.35 and launch["royalty"] == 0.35 and launch["allowed"]
    assert not books.ebook_royalty(0.99, 5)["allowed"]  # files of 3 MB or more can't go below 1.99


def test_spine_cover_and_margins():
    assert books.spine_width(150, "white") == 0.3378 and books.spine_width(150, "cream") == 0.375
    cover = books.cover_size("6x9", 150)
    assert cover == {"width": 12.5878, "height": 9.25, "spine": 0.3378, "spine_text": True}
    assert not books.cover_size("6x9", 78)["spine_text"] and books.cover_size("6x9", 80)["spine_text"]
    assert books.inside_margin(120) == 0.375 and books.inside_margin(151) == 0.5 and books.inside_margin(828) == 0.875


def test_formats_kdp_cannot_print_are_refused():
    assert books.check_format("6x9", 20) and books.check_format("8.5x11", 600)  # too short; letter size stops at 590
    assert books.check_format("5x8", 120, binding="hardcover")  # no 5 x 8 hardcover
    assert books.check_format("6x9", 60, binding="hardcover")  # hardcovers start at 75 pages
    assert books.check_format("6x9", 120) is None
    assert books.estimate_pages(25000) % 2 == 0 and 90 <= books.estimate_pages(25000) <= 120


def test_a_niche_is_scored_only_from_what_was_checked(client):  # noqa: F811
    bare = client.post("/api/books/niches", json={"area": "Sleep after menopause"}).json()
    assert "sales not checked" in " ".join(bare["reasons"]) and "search trend not checked" in bare["reasons"]
    proven = client.post("/api/books/niches", json={
        "area": "Sleep after menopause", "reader": "Women 45-60 waking at 3 am", "problem": "Can't stay asleep", "trend": "flat",
        "competitors": "The Menopause Sleep Fix | 18,200 | 64 | 14.99 | 4.99\nSleep Again | 45,000 | 210 | 13.99 | 3.99\nOld Book | 2,100,000 | 3 | 9.99 |"}).json()
    assert proven["score"] > bare["score"] + 30 and proven["competitors"][0] == {
        "title": "The Menopause Sleep Fix", "bsr": 18200, "reviews": 64, "paperback": 14.99, "kindle": 4.99}
    assert any("2 of 3 competing books rank under 100,000" in reason for reason in proven["reasons"])
    fad = client.patch(f"/api/books/niches/{proven['id']}", json={"trend": "fad"}).json()
    assert fad["score"] == proven["score"] - 30 and "probably a fad" in " ".join(fad["reasons"])


def test_books_show_every_formats_earnings_and_enforce_kdps_rules(client):  # noqa: F811
    niche = client.post("/api/books/niches", json={"area": "Budgeting on one income"}).json()
    book = client.post("/api/books/items", json={"niche_id": niche["id"], "title": "One Income, No Stress", "pen_name": "Ann Rivers",
                                                  "pages": 140, "prices": {"paperback": "12.99", "kindle": 4.99, "hardcover": 22.99},
                                                  "formats": ["paperback", "kindle", "hardcover"]}).json()
    earnings = book["earnings"]
    assert earnings["paperback"]["royalty"] == round(0.6 * 12.99 - (1 + 140 * 0.012), 2)
    assert earnings["kindle"]["rate"] == 0.70 and earnings["hardcover"]["printing"] == round(5.65 + 140 * 0.012, 2)
    assert earnings["cover"]["spine"] == round(140 * 0.002252, 4)
    assert client.post("/api/books/items", json={"title": "Too short", "pages": 12}).status_code == 400
    assert client.patch(f"/api/books/items/{book['id']}", json={"asins": {"kindle": "not-an-asin"}}).status_code == 400
    published = client.patch(f"/api/books/items/{book['id']}", json={"status": "published", "asins": {"kindle": "B0ABCDEFGH", "paperback": "9798765432109"}}).json()
    assert published["asins"]["kindle"] == "B0ABCDEFGH" and published["published_at"]
    assert client.delete(f"/api/books/items/{book['id']}").status_code == 400  # published books are retired, not deleted
    assert client.delete(f"/api/books/niches/{niche['id']}").status_code == 400
    state = client.get("/api/books").json()
    assert state["today"] == {"published": 1, "cap": 3} and state["sources"]["print_cost"].startswith("https://kdp.amazon.com/")
    assert client.get("/api/overview").json()["books"]["published"] == 1


def test_the_start_publishing_checklist_and_pen_names(client):  # noqa: F811
    saved = client.put("/api/books/settings", json={"done": ["tax", "nonsense"], "pen_names": ["Ann Rivers", "Ann Rivers", " "], "default_trim": "5.5x8.5"}).json()
    assert saved["done"] == ["tax"] and saved["pen_names"] == ["Ann Rivers"] and saved["default_trim"] == "5.5x8.5"
    items = {item["key"]: item for item in client.get("/api/books").json()["checklist"]}
    assert items["tax"]["done"] and "W-9" in items["tax"]["how"] and "W-8BEN" not in items["tax"]["how"] and not items["kdp_account"]["done"]
    assert client.put("/api/books/settings", json={"default_trim": "9x12"}).status_code == 400


def test_the_calculator_reports_a_size_kdp_will_not_print():
    assert "needs 24 to 828 pages" in books.calculate({"trim": "6x9", "pages": 10})["problem"]
    with pytest.raises(KeyError):
        books.print_cost(100, "9x12")


def test_kdps_daily_limit_on_new_titles_holds(client):  # noqa: F811
    client.put("/api/books/settings", json={"daily_cap": 1})
    first, second = (client.post("/api/books/items", json={"title": f"Book {number}", "pages": 100}).json() for number in (1, 2))
    assert client.patch(f"/api/books/items/{first['id']}", json={"status": "published"}).status_code == 200
    refused = client.patch(f"/api/books/items/{second['id']}", json={"status": "published"})
    assert refused.status_code == 400 and "tomorrow" in refused.json()["detail"]
