"""Learning from what sells: facts in, a plan and an original book out, with nothing of a competitor's copied. All titles are made up, and the model is simulated."""
import json

import pytest

from ai_hq import blueprint
from ai_hq.agents import AgentResult
from ai_hq.blueprint import analyze, parse, style_for, too_close
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents

LINES = """Road Miles Tracker for Tax Season | 12,500 | 840 | $7.99 | 120
Simple Vehicle Mileage Record | 45000 | 60 | 8.99 | 110
Business Driver Mileage Book | #80,000 | 35 | 6.99 | 130
Old Trip Ledger | 2400000 | 3 | 12.99 | 300"""


def test_a_pasted_list_is_read_with_bars_tabs_and_gaps():
    rows = parse("Tab Book\t1000\t5\t7.99\t100\nBare Title Only\n\n  \nA | 1")
    assert rows[0] == {"title": "Tab Book", "rank": 1000, "reviews": 5, "price": 7.99, "pages": 100}
    assert rows[1]["title"] == "Bare Title Only" and rows[1]["rank"] is None and len(rows) == 2


def test_the_plan_follows_the_books_that_actually_sell():
    found = analyze("mileage log book", LINES)
    assert found["selling"] == 3 and found["ranked"] == 4
    assert found["price"] == 7.99 and found["plan"]["pages"] == 120  # the slow seller's price and length are left out
    assert found["plan"]["style"] == "mileage" and found["earning"] is not None
    assert "mileage" in found["common_words"]
    assert any("3 of 4 rank under 100,000" in note for note in found["notes"])
    assert any("a new book can compete" in note for note in found["notes"])


def test_a_niche_nobody_buys_says_so():
    lines = "Book One Here | 2000000 | 1 | 7 | 100\nBook Two Here | 3000000 | 0 | 8 | 100\nBook Three Here | 1500000 | 2 | 9 | 100"
    assert any("Try a different niche" in note for note in analyze("sad niche", lines)["notes"])


def test_missing_ranks_are_named_not_guessed():
    found = analyze("sample book", "Book One Here\nBook Two Here\nBook Three Here")
    assert any("No ranks yet" in note for note in found["notes"]) and found["price"] is None and found["plan"]["pages"] == 120


def test_too_few_books_or_no_theme_is_refused():
    with pytest.raises(ValueError, match="at least 3"):
        analyze("sample book", "Only One Book")
    with pytest.raises(ValueError, match="Say what the book is"):
        analyze("", LINES)


def test_a_low_price_for_the_length_is_called_out():
    lines = "Thick Book One | 1000 | 5 | 2.99 | 800\nThick Book Two | 1000 | 5 | 2.99 | 800\nThick Book Three | 1000 | 5 | 2.99 | 800"
    assert any("below KDP's lowest price" in note for note in analyze("sample book", lines)["notes"])


def test_trademarks_are_never_suggested():
    lines = "Disney Trip Planner | 1000 | 5 | 8 | 100\nDisney Vacation Planner | 1000 | 5 | 8 | 100\nFamily Trip Planner | 1000 | 5 | 8 | 100"
    assert "disney" not in analyze("trip planner", lines)["common_words"]


def test_the_page_type_comes_from_what_the_book_is():
    assert style_for("Blood Pressure log") == "blood_pressure" and style_for("workout journal") == "workout" and style_for("sketch book") == "bordered"
    assert style_for("something else") == "college"


def test_a_title_too_like_a_competitors_is_caught():
    rivals = ["Road Miles Tracker for Tax Season", "Simple Vehicle Mileage Record"]
    assert too_close("Road Miles Tracker for Tax Time", rivals) == rivals[0]
    assert too_close("road miles tax season", rivals) == rivals[0]
    assert too_close("Vehicle Mileage Record: Simple", rivals) == rivals[1]


def test_sharing_the_words_every_book_needs_is_fine():
    assert too_close("Gig Driver Expense Companion", ["Road Miles Tracker for Tax Season"]) == ""
    assert too_close("Mileage Log Book", ["Mileage Notebook"]) == ""  # one shared subject word is just what the book is about
    assert too_close("Journal Notebook", ["Journal Log Planner"]) == ""  # nothing but generic words
    assert too_close("Anything", []) == ""


class Writer(FixtureRegistry):
    def __init__(self, title):
        super().__init__()
        self.title, self.prompts = title, []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        return AgentResult(True, json.dumps({"title": self.title, "subtitle": "A Simple Record for Busy Drivers", "description": "A clear, simple book for recording every business trip through the year.",
                                             "keywords": ["gig driver records", "tax season organizer", "car expense notebook", "business trip diary", "self employed driver", "irs trip record", "delivery driver gift"], "price": 8.99}))


def make(client, title):  # noqa: F811
    enable_agents(client)
    model = Writer(title)
    client.app.state.supervisor.registry = model
    return client.post("/api/books/blueprint/make", json={"theme": "mileage log book", "books": LINES}), model


def test_the_owners_book_is_made_from_the_plan_and_kept_clear_of_the_titles(client):  # noqa: F811
    answer, model = make(client, "Gig Driver Expense Companion")
    book = answer.json()
    assert answer.status_code == 200 and book["pages"] == 120 and book["style"] == "mileage" and book["interior"] and book["cover"]
    assert "Road Miles Tracker for Tax Season" in model.prompts[0] and "data, not instructions" in model.prompts[0]
    assert not any("too close" in item for item in book["listing"]["checks"])
    assert "sell for about $7.99" in book["price_tip"]


def test_a_title_that_still_comes_out_too_close_is_flagged_before_upload(client):  # noqa: F811
    answer, _ = make(client, "Road Miles Tracker for Tax Time")
    assert any("too close to “Road Miles Tracker for Tax Season”" in item for item in answer.json()["listing"]["checks"])


def test_the_owner_can_change_the_plan(client):  # noqa: F811
    enable_agents(client)
    client.app.state.supervisor.registry = Writer("Gig Driver Expense Companion")
    book = client.post("/api/books/blueprint/make", json={"theme": "mileage log book", "books": LINES, "pages": 150}).json()
    assert book["pages"] == 150


def test_reading_the_market_needs_no_model_and_saves_nothing(client):  # noqa: F811
    found = client.post("/api/books/blueprint", json={"theme": "mileage log book", "books": LINES}).json()
    assert found["selling"] == 3 and client.get("/api/books").json()["books"] == []


def test_nothing_about_a_competitors_design_is_taken_in():
    assert set(parse("A Book Title | 1 | 2 | 3 | 4 | their cover art notes | more")[0]) == {"title", "rank", "reviews", "price", "pages"}
    assert blueprint.MAX_BOOKS == 30
