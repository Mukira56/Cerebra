"""The address on a draft must be the business's own. The kinds of address found on business pages, good and bad, all made up.
A designer's credit or a vendor's support address is worse than none: the email would criticise the site to whoever built it."""
import httpx

from ai_hq import prospects
from ai_hq.models import Event, Outbox, Prospect
from ai_hq.outreach import belongs, find_email, tidy_email
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import setup

GOOD = [("robin@harlowlaw.test", "https://harlowlawfirm.test", "Harlow Law Firm"), ("contact@drvexler.test", "https://vexlerorthodontics.test", "Vexler Orthodontics"),
        ("tquill@bigbroker.test", "https://taraquillrealtor.test", "Tara Quill"), ("hal@delrosalaw.test", "", "Del Rosa Law Firm"),
        ("fernhill.sample@gmail.com", "https://fernhillcoffee.test", "Fernhill Coffee Shop"), ("ivy.sample@gmail.com", "https://ivysample.test", "Ivy Sample Realtor"),
        ("q.sample1@gmail.com", "https://hairbyqtx.test", "Hair by Q"), ("hey@ironmill-atx.test", "https://ironmill-atx.test", "Iron Mill ATX"),
        ("sip@samplepho.test", "https://www.samplepho.test", "Sample Pho"), ("catering@eatlotus.test", "https://eatlotus.test", "Lotus Japanese Food Fast"),
        ("hello@mail.tidelab.test", "https://tidelab.test", "The Tide Lab")]
BAD = [("sam@pixelforge.test", "https://baybakeryandcafe.test", "Bay Bakery & Cafe"), ("support@autotrackr.test", "https://marloautobody.test", "Marlo Auto and Body Shop"),
       ("downtown@bgfinc.onmicrosoft.test", "https://bigfit.test", "Bigfit Fitness"), ("8006main@parentgarages.test", "https://riverbendautomotive.test", "Riverbend Automotive Specialists")]


def test_addresses_that_are_the_businesss_own_are_kept():
    for email, website, name in GOOD:
        assert belongs(email, website, name, "Austin"), email


def test_addresses_of_designers_vendors_and_parent_companies_are_refused():
    for email, website, name in BAD:
        assert not belongs(email, website, name, "Austin"), email


def test_a_trade_word_or_the_city_proves_nothing():
    assert not belongs("hello@austinwebdesign.test", "https://samplepipes.test", "Austin Plumbing Services", "Austin")
    assert not belongs("hi@fitnesssoftware.test", "https://x.com", "Fitness Center", "Austin")


def test_addresses_are_cleaned_and_samples_refused():
    assert tidy_email("%20customerservice@sampleproperties.test") == "customerservice@sampleproperties.test"
    assert tidy_email(" Info@Samplepho.test. ") == "info@samplepho.test"
    for bad in ("j.doe@inbox.test", "john.doe@acme.com", "your@email.com", "name@company.org", "not an address", "", None, "logo@2x.png"):
        assert tidy_email(bad) == "", bad


class Reader:
    def __init__(self, text):
        self.text = text

    def page(self, url):
        return {"url": url, "status": 200, "html": self.text}


def test_a_designers_credit_is_passed_over_for_the_real_address():
    page = "<footer>Site by sam@pixelforge.test</footer><p>Email us: hello@baybread.test or baybakery.sample@gmail.com</p>"
    assert find_email(Reader(page), "https://baybakeryandcafe.test", name="Bay Bakery & Cafe") == "baybakery.sample@gmail.com"


def test_only_a_designers_credit_means_no_address_at_all():
    assert find_email(Reader("Site by sam@pixelforge.test"), "https://baybakeryandcafe.test", name="Bay Bakery & Cafe") == ""


def test_the_sites_own_address_still_comes_first():
    assert find_email(Reader("owner@gmail.com and info@samplepho.test"), "https://samplepho.test", name="Sample Pho") == "info@samplepho.test"


def draft(state, key, email, website, name):
    with state.db.Session.begin() as session:
        session.add(Prospect(id=key, name=name, kind="cafes", city="Austin", state="Texas", website=website, status="kept",
                             facts=[{"key": "x", "text": "y", "seen": website}], opener="Subject: Hi\n\nHello, a short note about your website."))
        session.flush()
        session.add(Outbox(prospect_id=key, email=email, stage="draft"))


def test_waiting_drafts_are_checked_again_and_the_owner_is_told(client):  # noqa: F811
    state = setup(client)
    draft(state, "bad", "sam@pixelforge.test", "https://baybakeryandcafe.test", "Bay Bakery & Cafe")
    draft(state, "sample", "j.doe@inbox.test", "https://sampleinjuryattorney.test", "Sample Injury Attorneys")
    draft(state, "junk", "%20customerservice@sampleproperties.test", "https://sampleproperties.test", "Sample Apartments")
    draft(state, "good", "robin@harlowlaw.test", "https://harlowlawfirm.test", "Harlow Law Firm")
    assert state.outreach.review_addresses() == 2
    with state.db.Session() as session:
        rows = {row.prospect_id: row for row in session.query(Outbox).all()}
        assert rows["bad"].email == "" and rows["bad"].stage == "no_email" and rows["sample"].stage == "no_email"
        assert rows["junk"].email == "customerservice@sampleproperties.test" and rows["junk"].stage == "draft"  # repaired, not removed
        assert rows["good"].email == "robin@harlowlaw.test" and rows["good"].stage == "draft"
        notes = " ".join(item.message for item in session.query(Event).all())
        assert "Took sam@pixelforge.test off Bay Bakery" in notes
    assert state.outreach.review_addresses() == 0  # nothing left to do


def test_a_sent_email_is_history_and_is_left_alone(client):  # noqa: F811
    state = setup(client)
    draft(state, "sent", "support@autotrackr.test", "https://marloautobody.test", "Marlo Auto and Body Shop")
    with state.db.Session.begin() as session:
        session.query(Outbox).one().stage = "sent"
    assert state.outreach.review_addresses() == 0


def test_the_owner_can_still_type_any_address_and_send(client):  # noqa: F811
    state = setup(client)
    draft(state, "p1", "sam@pixelforge.test", "https://baybakeryandcafe.test", "Bay Bakery & Cafe")
    state.outreach.review_addresses()
    answer = client.post("/api/prospects/p1/send", json={"to": "owner@somewhere-else.example", "text": "Subject: Hi\n\nHello, a short note about booking on your website."})
    assert answer.status_code == 200 and state.outreach.gmail.sent[-1]["to"] == "owner@somewhere-else.example"
