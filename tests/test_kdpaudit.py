"""The keyword audit: wasted boxes are named, real rule breaks are told apart from advice, and topics aren't mistaken for claims."""
from ai_hq.books import book_public
from ai_hq.kdpaudit import audit, words
from ai_hq.models import Book

TITLE, SUBTITLE = "Daily Gratitude Journal", "A Five Minute Practice for Women"
GOOD = ["mindfulness gift for mom", "self care diary prompts", "morning reflection notebook", "positive thinking workbook",
        "anxiety relief writing exercises", "christian devotional for her", "wellness planner for busy moms"]


def test_a_well_used_listing_scores_full_marks():
    result = audit(TITLE, SUBTITLE, GOOD)
    assert result["score"] == 100 and result["label"] == "strong" and result["fix"] == [] and result["improve"] == []
    assert result["reach"] >= 15 and result["used"] == sum(len(item) for item in GOOD)


def test_plurals_and_filler_words_do_not_count_as_new():
    assert words("The Planners for Moms") == words("planner mom") == {"planner", "mom"}
    assert words("glass") == {"glass"}  # not a plural


def test_each_kind_of_waste_is_named_with_its_box():
    boxes = [*GOOD[:3], "journal", "gratitude journals for women", "self care diary prompts for you", GOOD[6]]
    improve = audit(TITLE, SUBTITLE, boxes)["improve"]
    assert len(improve) == 3
    assert "Box 4 (“journal”) is a single word" in improve[0]
    assert "Box 5 (“gratitude journals for women”) only repeats your title" in improve[1]
    assert "Box 6 (“self care diary prompts for you”) adds nothing to box 2" in improve[2]


def test_empty_boxes_lower_the_score_but_block_nothing():
    result = audit(TITLE, SUBTITLE, GOOD[:5])
    assert result["fix"] == [] and result["score"] == 84 and result["label"] == "good"
    assert [item[:9] for item in result["improve"]] == ["Box 6 is ", "Box 7 is "]
    assert audit(TITLE, SUBTITLE, [])["label"] == "weak" and audit("", "", None)["reach"] == 0


def test_rule_breaks_are_fixes_wherever_they_are():
    long_box = "x" * 51
    assert audit(TITLE, SUBTITLE, [*GOOD[:6], long_box])["fix"] == ["Box 7 is 51 characters; the limit is 50"]
    assert audit(TITLE, SUBTITLE, [*GOOD, "one more phrase here"])["fix"] == ["8 keywords, but KDP has 7 boxes"]
    claim = audit("The Bestseller Journal", SUBTITLE, GOOD)
    assert claim["label"] == "fix" and claim["fix"] == ["Remove words KDP doesn't allow: bestseller"]
    assert audit(TITLE, "A Disney Fan Diary", GOOD)["fix"] == ["Remove trademarked names: disney"]
    assert "free" in audit(TITLE, SUBTITLE, ["free printable journal", *GOOD[:6]])["fix"][0]


def test_free_as_a_topic_is_not_a_price_claim():
    assert audit("Gluten Free Meal Planner", "Stress-Free Weekly Menus", ["sugar free dessert log", *GOOD[:6]])["fix"] == []


def test_the_score_never_goes_below_zero():
    assert audit("Free Disney Kindle Bestseller", "", ["a"] * 9)["score"] == 0


def test_a_book_with_a_listing_shows_its_audit_and_one_without_does_not():
    made = book_public(Book(id="b1", title=TITLE, subtitle=SUBTITLE, extra={"listing": {"title": TITLE, "subtitle": SUBTITLE, "keywords": GOOD}}))
    assert made["audit"]["score"] == 100
    assert book_public(Book(id="b2", title="Plain", extra={}))["audit"] is None


def test_an_ebook_outline_shows_its_audit():
    from ai_hq import ebooks
    from ai_hq.models import Book as Row
    row = Row(id="e1", title=TITLE, extra={"outline": {"title": TITLE, "subtitle": SUBTITLE, "keywords": GOOD, "chapters": [], "price": 4.99}})
    assert ebooks.public(row)["audit"]["score"] == 100
    assert ebooks.public(Row(id="e2", title="x", extra={}))["audit"] is None


def test_the_notebook_check_agrees_about_free_as_a_topic():
    from ai_hq import notebooks
    listing = {"title": "Gluten Free Meal Planner", "subtitle": "", "description": "A planner for gluten free weekly meals and simple shopping lists.", "keywords": GOOD}
    assert notebooks.check(listing) == []
    assert "free" in " ".join(notebooks.check({**listing, "title": "Free Meal Planner"}))
