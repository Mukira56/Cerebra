"""KDP low-content interiors: ruled, dot-grid, graph and bordered pages drawn by code, with no fonts and no AI."""
import re

import pytest

from ai_hq import interiors
from test_freelance import client  # noqa: F401  (client is a fixture)


def streams(data):
    return re.findall(rb"stream\n(.*?)\nendstream", data, re.S)


def test_a_notebook_is_the_trim_size_with_the_gutter_on_the_binding_side_and_no_fonts():
    data, info = interiors.build("college", "6x9", 121)
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert info["pages"] == 122 and b"/Count 122" in data and data.count(b"/Type /Page ") == 122  # an even page count
    assert b"/MediaBox [0 0 432 648]" in data and b"/TrimBox [0 0 432 648]" in data  # 6 x 9 inches, no bleed
    assert b"/Font" not in data and b" Tj" not in data  # nothing KDP could find unembedded
    right_hand, left_hand = streams(data)
    first_x = lambda stream: float(re.search(rb"(\d+(?:\.\d+)?) [\d.]+ m", stream).group(1))
    assert first_x(right_hand) == pytest.approx(0.375 * 72) and first_x(left_hand) == pytest.approx(0.5 * 72)  # wide margin on the binding side
    assert interiors.build("college", "6x9", 400)[1]["gutter"] == 0.625  # thicker books get a wider gutter (KDP's table)
    xref = int(data.rsplit(b"startxref\n", 1)[1].split()[0])
    assert data[xref:xref + 4] == b"xref"  # a reader can find every object


def test_every_style_draws_and_kdp_limits_are_kept():
    for style in interiors.STYLES:
        data, info = interiors.build(style, "8.5x11", 24)
        assert info["pages"] == 24 and len(streams(data)[0]) > 20
    with pytest.raises(ValueError, match="24 to"):
        interiors.build("college", "6x9", 10)
    with pytest.raises(ValueError, match="590"):
        interiors.build("college", "8.5x11", 600)  # letter size has a lower maximum
    with pytest.raises(ValueError, match="trim size"):
        interiors.build("college", "4x6", 100)
    with pytest.raises(ValueError, match="Choose one of"):
        interiors.build("hexagons", "6x9", 100)


def test_the_books_page_makes_the_file_in_cerebras_folder_and_opens_it(client):  # noqa: F811
    state = client.get("/api/books/interiors").json()
    assert "college" in state["styles"] and "6x9" in state["trims"] and state["files"] == []
    made = client.post("/api/books/interiors", json={"style": "dot", "trim": "6x9", "pages": 120}).json()
    assert made["file"] == "dot-6x9-120p-white.pdf" and any("AI-generated content: No" in line for line in made["kdp"])
    path = client.app.state.settings.data_dir / "books" / "interiors" / made["file"]
    assert path.read_bytes().startswith(b"%PDF") and client.get("/api/books/interiors").json()["files"][0]["file"] == made["file"]
    assert client.post("/api/books/interiors", json={"style": "dot", "trim": "6x9", "pages": 5}).status_code == 400
    client.post("/api/books/interiors/open", json={})
    assert client.app.state.opened[-1].endswith("interiors")


def test_a_notebook_listing_is_checked_against_kdp_limits():
    from ai_hq import notebooks
    good = {"title": "Gratitude Journal for Women", "subtitle": "120 College-Ruled Pages, 6 x 9 in", "description": "A simple daily gratitude journal with lined pages.",
            "keywords": [f"gratitude phrase {n}" for n in range(7)]}
    assert notebooks.check(good) == []
    bad = {**good, "title": "#1 Bestseller Disney Journal", "keywords": ["kindle notebook"], "description": "Short."}
    problems = " | ".join(notebooks.check(bad))
    assert "#1" in problems and "bestseller" in problems and "kindle" in problems and "disney" in problems
    assert "1 of 7 keywords" in problems and "30–4000 characters" in problems
    info = {"pages": 120, "trim": "6x9"}
    priced = notebooks.parse('{"title": "T", "description": "' + "x" * 40 + '", "keywords": [], "price": 1.0}', info)
    assert priced["price"] >= 5.99 and priced["price"] >= notebooks.books.print_royalty(5.99, 120, "6x9")["minimum_price"]  # never below printing


def test_a_theme_becomes_a_book_ready_to_upload_that_waits_in_your_calls(client):  # noqa: F811
    import json
    from ai_hq import chief
    from fakes import FixtureRegistry
    from ai_hq.agents import AgentResult
    from test_product_api import enable_agents

    class Writer(FixtureRegistry):
        def __init__(self):
            super().__init__()
            self.prompts = []

        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            self.prompts.append(prompt)
            return AgentResult(True, json.dumps({"title": "Gratitude Journal for Women", "subtitle": "120 College-Ruled Pages, 6 x 9 in",
                                                 "description": "A calm daily gratitude journal. Lined pages for three things each day.",
                                                 "keywords": [f"daily gratitude phrase {n}" for n in range(9)], "price": 8.99}))
    assert "Switch AI agents on" in client.post("/api/books/notebooks", json={"theme": "gratitude journal for women"}).json()["detail"]
    enable_agents(client)
    model = Writer()
    client.app.state.supervisor.registry = model
    book = client.post("/api/books/notebooks", json={"theme": "gratitude journal for women", "style": "college", "trim": "6x9", "pages": 120}).json()
    assert book["status"] == "files_ready" and book["kind"] == "low_content" and book["interior"] == "college-6x9-120p-white.pdf"
    assert len(book["listing"]["keywords"]) == 7 and book["listing"]["checks"] == [] and book["prices"]["paperback"] == 8.99
    assert book["royalty"]["royalty"] > 0 and "data, not instructions" in model.prompts[-1]
    assert "At $9.99 KDP pays 60%" in book["price_tip"] and "$3.55" in book["price_tip"] and "$2.06" in book["price_tip"]  # 120 pages, 6 x 9
    with client.app.state.db.Session() as session:
        assert any(item["kind"] == "book" and "Gratitude Journal" in item["detail"] for item in chief.calls(session))
    folder = client.app.state.settings.data_dir / "books" / "interiors"
    assert book["cover"] == "college-6x9-120p-white-cover-navy.pdf" and (folder / book["cover"]).is_file()  # the cover comes with it
    assert "Pages and cover: No" in book["ai_question"]
    again = client.post(f"/api/books/{book['id']}/cover", json={"palette": "sky", "author": "Pine Hill Press"})
    assert again.status_code == 200 and again.json()["file"] == "college-6x9-120p-white-cover-sky.pdf" and (folder / again.json()["file"]).is_file()
    shown = next(item for item in client.get("/api/books").json()["books"] if item["id"] == book["id"])
    assert shown["cover"] == again.json()["file"] and shown["cover_palette"] == "sky" and shown["pen_name"] == "Pine Hill Press"
    assert client.post(f"/api/books/{book['id']}/cover", json={"palette": "rainbow"}).status_code == 400
    assert client.post("/api/books/nope/cover", json={}).status_code == 404
    assert client.post("/api/books/notebooks", json={"theme": "x"}).status_code == 400
    assert client.post("/api/books/notebooks", json={"theme": "nurse notebook", "pages": 5}).status_code == 400  # no model asked for a book KDP won't print


def test_logbooks_and_the_planner_print_headings_as_strokes_with_no_font():
    from ai_hq import strokefont
    for style in ("mileage", "reading", "workout", "blood_pressure", "weekly"):
        data, info = interiors.build(style, "6x9", 120)
        assert b"/Font" not in data and b" Tj" not in data and b"BT" not in data  # headings are lines, so KDP's font check can't fail
        right_hand, left_hand = streams(data)
        assert right_hand.count(b" re S") >= 1 and right_hand.count(b" l") > 100 and right_hand != left_hand  # gutter side differs
    mileage = streams(interiors.build("mileage", "6x9", 24)[0])[0].decode()
    assert strokefont.draw("MILEAGE LOG", 0, 0, 9).split(" ")[0] != "" and "1 J 1 j" in mileage
    assert strokefont.width("Date", 6) == strokefont.width("DATE", 6) > 0 and strokefont.width("", 6) == 0
    assert set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 /:-") <= set(strokefont.GLYPHS)  # every heading character is drawn
    for _title, columns in interiors.TABLES.values():
        assert all(set(name) <= set(strokefont.GLYPHS) for name, _share in columns)


def test_a_cover_is_kdps_full_wrap_size_with_no_font_and_a_spine_title_only_when_kdp_allows():
    from ai_hq import books, covers
    data, info = covers.build("Mileage Log Book for Taxes", "Vehicle Odometer Tracker & Expense Record", "Pine Hill Press", "6x9", 120, "white", "navy")
    size = books.cover_size("6x9", 120, "white")
    assert (info["width"], info["height"], info["spine"]) == (size["width"], size["height"], size["spine"]) and info["spine"] == pytest.approx(120 * 0.002252, abs=1e-4)
    assert f"/MediaBox [0 0 {size['width'] * 72:.2f}".rstrip("0").encode() in data and b"/Count 1" in data  # one page: bleed, back, spine, front, bleed
    assert b"/Font" not in data and b" Tj" not in data and b"/Image" not in data  # no font to embed, no picture
    assert b" cm" in data  # the spine title, turned to read from top to bottom
    thin = covers.build("Pocket Notes", "", "", "5x8", 60, "white", "forest")[0]
    assert b" cm" not in thin  # under 79 pages KDP allows no spine text
    with pytest.raises(ValueError, match="palette"):
        covers.build("Notes", trim="6x9", pages=100, palette="neon")
    with pytest.raises(ValueError, match="title"):
        covers.build("", trim="6x9", pages=100)
    with pytest.raises(ValueError, match="24 to"):
        covers.build("Notes", trim="6x9", pages=10)


def test_a_book_becomes_an_etsy_printable_with_its_listing_on_the_etsy_page(client):  # noqa: F811
    from ai_hq.models import Book
    with client.app.state.db.Session.begin() as session:
        session.add(Book(id="b1", title="Mileage Log Book for Taxes: 120 Pages", subtitle="Vehicle Odometer Tracker", status="files_ready", trim="6x9",
                         paper="white", pages=120, formats=["paperback"],
                         extra={"kind": "low_content", "style": "mileage", "listing": {"description": "Track every business mile for tax time.",
                                                                                        "keywords": ["mileage tracker", "vehicle mileage log book", "irs mileage log"]}}))
        session.add(Book(id="b2", title="A Novel", status="planned", trim="6x9", paper="white", pages=200, formats=["paperback"], extra={}))
    made = client.post("/api/books/b1/etsy", json={"pages": 3})
    assert made.status_code == 200, made.text
    made = made.json()
    folder = client.app.state.settings.data_dir / "books" / "interiors"
    data = (folder / made["file"]).read_bytes()
    assert made["file"] == "mileage-printable-letter-3p.pdf" and b"/Count 3" in data and b"/MediaBox [0 0 612 792]" in data and b"/Font" not in data
    right_hand, left_hand = streams(data)
    assert right_hand == left_hand  # printed at home: even margins, no binding side
    assert made["title"].startswith("Mileage Log Book for Taxes Printable") and len(made["title"]) <= 140 and "120 Pages" not in made["title"]
    assert len(made["tags"]) == 13 and all(len(tag) <= 20 for tag in made["tags"]) and "mileage tracker" in made["tags"]
    assert "digital download: nothing is shipped" in made["description"] and "US Letter" in made["description"] and made["checks"] == []
    assert made["price"] == 4.5 and client.get("/api/etsy/listings").json()[0]["title"] == made["title"]  # waits on the Etsy page
    shown = next(item for item in client.get("/api/books").json()["books"] if item["id"] == "b1")
    assert shown["etsy_listing"] == made["id"] and shown["etsy_printable"] == made["file"]
    assert "Only notebooks" in client.post("/api/books/b2/etsy", json={}).json()["detail"]
    assert client.post("/api/books/nope/etsy", json={}).status_code == 404
    assert client.post("/api/books/b1/etsy", json={"pages": 40}).status_code == 400


def test_every_proven_idea_is_a_book_kdp_will_print(client):  # noqa: F811
    from ai_hq import books
    ideas = client.get("/api/books/interiors").json()["ideas"]
    assert len(ideas) >= 6 and len({idea["style"] for idea in ideas}) == len(ideas)  # one of each kind
    for idea in ideas:
        assert idea["style"] in interiors.STYLES and books.check_format(idea["trim"], idea["pages"]) is None and idea["why"]
        interiors.build(idea["style"], idea["trim"], idea["pages"])  # draws without error
