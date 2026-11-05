"""The Etsy listing check: weak tags and titles are named, rule breaks stay rule breaks, and a tag repeating the title is fine."""
from ai_hq import etsy
from ai_hq.etsyaudit import audit
from ai_hq.models import EtsyListing, EtsyNiche
from test_freelance import client  # noqa: F401  (client is a fixture)

TAGS = ["wedding planner", "bridal shower gift", "engagement present", "budget tracker pdf", "guest list template", "seating chart sheet",
        "vendor contact log", "day of timeline", "digital download", "printable checklist", "bride to be organizer", "honeymoon packing", "rsvp tracker page"]
GOOD = {"title": "Wedding Planner Printable, Budget Tracker and Guest List", "tags": TAGS, "description": "A planner.", "price": 8.5}


def test_a_well_built_listing_scores_full_marks_even_when_a_tag_repeats_the_title():
    result = audit(GOOD, "wedding planner printable")
    assert result["score"] == 100 and result["label"] == "strong" and result["fix"] == [] and result["improve"] == []
    assert result["reach"] >= 20 and str(result["reach"]) in result["summary"]


def test_the_researched_keyword_must_be_in_the_title_and_near_the_start():
    assert "isn't in the title" in audit(GOOD, "bridal shower game")["improve"][0]
    late = {**GOOD, "title": "Beautiful Modern Minimal Elegant Organizer Bundle for Brides, Wedding Planner Printable"}
    assert "to the start of the title" in audit(late, "wedding planner printable")["improve"][0]
    assert audit({**GOOD, "title": late["title"]})["improve"] == []  # no niche, nothing to compare with


def test_plurals_count_as_the_same_keyword():
    assert audit(GOOD, "wedding planners printables")["improve"] == []


def test_single_word_tags_and_tags_that_add_nothing_are_named():
    tags = [*TAGS[:11], "wedding", "planner wedding"]
    improve = audit({**GOOD, "tags": tags})["improve"]
    assert improve == ["Tag 12 (“wedding”) is a single word: phrases match more searches", "Tag 13 (“planner wedding”) adds nothing to tag 1: use different words"]


def test_a_stuffed_title_is_called_out():
    stuffed = {**GOOD, "title": "Planner Printable, Wedding Planner, Budget Planner, Bride"}
    assert audit(stuffed)["improve"] == ["The title says “planner” 3 times: say it once and use the space for something new"]


def test_rule_breaks_come_from_the_listing_check_and_block_the_label():
    result = audit({**GOOD, "title": "Disney Wedding Planner", "price": 0})
    assert result["label"] == "fix" and len(result["fix"]) == 2 and result["score"] == 50
    assert audit({"title": "", "tags": [], "price": 0})["label"] == "fix"


def test_a_saved_listing_is_graded_against_its_own_niche(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(EtsyNiche(id="n1", keyword="mileage log", data={}))
        session.flush()
        session.add(EtsyListing(id="l1", niche_id="n1", title="Wedding Planner Printable", tags=TAGS, description="A planner.", price=8.5, checks=[]))
        session.add(EtsyListing(id="l2", niche_id=None, title="Wedding Planner Printable", tags=TAGS, description="A planner.", price=8.5, checks=[]))
    found = {item["id"]: item for item in client.get("/api/etsy/listings").json()}
    assert "“mileage log” isn't in the title" in found["l1"]["audit"]["improve"][0]
    assert found["l2"]["audit"]["improve"] == []
    assert etsy.listing_public(EtsyListing(id="x", title="t", tags=[], price=1.0))["audit"]["label"] == "fix"  # not saved: still safe to show
