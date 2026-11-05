"""Finding the website of a business the map lists without one. A wrong match means emailing a stranger, so most tests here are refusals.
Every website is simulated."""
import httpx

from ai_hq import prospects
from ai_hq.models import Event, Prospect
from ai_hq.prospects import NOT_FOUND, WebsiteFinder, guesses, same_business
from test_freelance import client  # noqa: F401  (client is a fixture)

OLD_SITE = """<html><head><title>Mizu Noodle</title></head><body><table><tr><td>Mizu Noodle</td></tr></table>
<p>Austin, TX. Best noodles. Email us: hello@mizunoodle.com</p><p>Call us!</p>© 2015</body></html>"""


def row(**fields):
    base = {"name": "Mizu Noodle", "city": "Austin", "state": "Texas", "phone": "", "address": ""}
    return Prospect(**{**base, **fields})


def page(text, status=200):
    return {"url": "https://x.com", "status": status, "html": text}


def test_the_likely_addresses_for_a_name():
    assert guesses("Mizu Noodle", "Austin") == ["https://mizunoodle.com", "https://mizu-noodle.com", "https://mizunoodleaustin.com"]
    assert guesses("Ames & Salter", "") == ["https://amesandsalter.com", "https://amessalter.com", "https://ames-salter.com"]
    assert guesses("Lark's Automotive", "")[0] == "https://larksautomotive.com"
    assert guesses("Dana Sample, MD", "")[0] == "https://danasample.com"
    assert guesses("Calm Pilates Austin", "Austin") == ["https://calmpilatesaustin.com", "https://calm-pilates-austin.com"]  # the city isn't added twice


def test_one_word_names_are_never_guessed():
    for name in ("LINE", "Avenue", "The Avenue", "Avenue LLC", "", "Avenue & Co"):
        assert guesses(name, "Austin") == [], name


def test_the_full_name_and_the_city_with_its_state_prove_it():
    assert same_business(row(), page("<h1>Mizu Noodle</h1><p>6519 N Lamar, Austin, TX 78752</p>"))
    assert same_business(row(), page("<h1>MIZU NOODLE</h1><p>Proudly serving Austin Texas</p>"))


def test_a_phone_or_street_proves_it_even_if_the_page_is_written_differently():
    assert same_business(row(phone="+1 512-555-0142"), page("<h1>Mizu Noodle</h1> Call (512) 555-0142"))
    assert same_business(row(address="9909 North Lamar Boulevard"), page("<h1>Mizu Noodle</h1> 9909 N Lamar Blvd"))
    assert same_business(row(address="101 East Cesar Chavez Street"), page("<h1>Mizu Noodle</h1> 101 E. Cesar Chavez St."))


def test_the_same_name_in_another_state_is_refused():
    assert not same_business(row(), page("<h1>Mizu Noodle</h1><p>Portland, OR</p>"))
    assert not same_business(row(), page("<h1>Mizu Noodle</h1><p>Austin, MN 55912</p>"))  # there's an Austin in Minnesota
    assert not same_business(row(phone="512-555-0142", address="9909 North Lamar"), page("<h1>Mizu Noodle</h1> 206-555-0100 44 Pine St"))


def test_a_parked_or_unrelated_page_is_refused():
    assert not same_business(row(), page("<title>mizunoodle.com is for sale</title> Buy this domain"))
    assert not same_business(row(), page("<h1>Austin, TX restaurants</h1> Our favorite noodle"))  # the place but not the name
    assert not same_business(row(), page("<h1>Mizu</h1> and some noodle in Austin, TX"))  # the words, not the name
    assert not same_business(row(), page("<h1>Mizu Noodle</h1> Austin, TX", status=404))


def test_words_hidden_in_scripts_do_not_count():
    assert not same_business(row(), page("<h1>Mizu Noodle</h1><script>var city='Austin, TX'</script><style>.a{content:'Austin, TX'}</style>"))


class Sites:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def __call__(self, request):
        self.asked.append(request.url.host)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        found = self.pages.get(request.url.host)
        if found is None:
            return httpx.Response(404, text="nothing here")
        if isinstance(found, Exception):
            raise found
        return httpx.Response(200, text=found)


def finder(client, pages, online=True):  # noqa: F811
    sites = Sites(pages)
    state = client.app.state
    state.prospector.reader = prospects.Reader(httpx.Client(transport=httpx.MockTransport(sites)), resolve=lambda host: online)
    state.prospector.pause = 0
    return WebsiteFinder(state.db, state.prospector), sites


def add(client, key, **fields):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(Prospect(id=key, kind="restaurants", city="Austin", state="Texas", status="new", notes="OpenStreetMap lists no website for them.", **fields))


def get(client, key):  # noqa: F811
    with client.app.state.db.Session() as session:
        return session.get(Prospect, key)


def test_a_found_site_becomes_a_business_worth_contacting_with_its_email(client):  # noqa: F811
    robot, _ = finder(client, {"mizunoodle.com": OLD_SITE})
    add(client, "p1", name="Mizu Noodle")
    assert robot.tick() == {"checked": 1, "found": 1, "worth_contacting": 1}
    found = get(client, "p1")
    assert found.website.startswith("https://mizunoodle.com") and found.status == "kept" and found.facts and found.notes == ""
    listed = next(item for item in client.get("/api/prospects").json()["prospects"] if item["id"] == "p1")
    assert listed["email"] == "hello@mizunoodle.com"
    with client.app.state.db.Session() as session:
        assert any("Found Mizu Noodle's website" in item.message for item in session.query(Event).all())


def test_a_modern_site_with_nothing_to_offer_is_dropped_like_any_other(client):  # noqa: F811
    modern = "<html><head><meta name='viewport' content='x'></head><body>Mizu Noodle, Austin, TX. Book an appointment<form></form>© 2026</body></html>"
    robot, _ = finder(client, {"mizunoodle.com": modern})
    add(client, "p1", name="Mizu Noodle")
    assert robot.tick()["worth_contacting"] == 0
    assert get(client, "p1").status == "dropped" and get(client, "p1").website


def test_no_site_is_remembered_and_never_tried_again(client):  # noqa: F811
    robot, sites = finder(client, {})
    add(client, "p1", name="Mizu Noodle")
    assert robot.tick() == {"checked": 1, "found": 0, "worth_contacting": 0}
    assert get(client, "p1").status == "new" and get(client, "p1").notes == NOT_FOUND and get(client, "p1").website == ""
    sites.asked.clear()
    assert robot.tick() == {"skipped": "every business has been looked up"} and sites.asked == []


def test_a_wrong_business_at_the_address_is_left_alone(client):  # noqa: F811
    robot, _ = finder(client, {"mizunoodle.com": "<h1>Mizu Noodle</h1> Portland, OR", "mizu-noodle.com": "<h1>Mizu Noodle</h1> Austin, TX"})
    add(client, "p1", name="Mizu Noodle")
    robot.tick()
    assert get(client, "p1").website.startswith("https://mizu-noodle.com")  # the first was someone else, so the next was tried


def test_one_word_names_are_marked_without_reading_anything(client):  # noqa: F811
    robot, sites = finder(client, {"line.com": "<h1>LINE</h1> Austin, TX"})
    add(client, "p1", name="LINE")
    robot.tick()
    assert get(client, "p1").website == "" and "line.com" not in sites.asked


def test_a_site_that_times_out_does_not_stop_the_others(client):  # noqa: F811
    robot, _ = finder(client, {"mizunoodle.com": httpx.ConnectTimeout("slow"), "mizu-noodle.com": OLD_SITE})
    add(client, "p1", name="Mizu Noodle")
    assert robot.tick()["found"] == 1


def test_with_no_internet_nothing_is_marked(client):  # noqa: F811
    robot, sites = finder(client, {}, online=False)
    add(client, "p1", name="Mizu Noodle")
    assert robot.tick() == {"skipped": "no internet right now"} and sites.asked == []
    assert NOT_FOUND not in get(client, "p1").notes


def test_robots_rules_are_respected(client):  # noqa: F811
    robot, _ = finder(client, {"mizunoodle.com": OLD_SITE})

    def closed(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("read a page it was asked not to")

    client.app.state.prospector.reader = prospects.Reader(httpx.Client(transport=httpx.MockTransport(closed)), resolve=lambda host: True)
    add(client, "p1", name="Mizu Noodle")
    assert robot.tick()["found"] == 0


def test_only_the_limit_is_read_each_run_and_kept_businesses_are_left_alone(client):  # noqa: F811
    robot, _ = finder(client, {})
    for number in range(4):
        add(client, f"p{number}", name=f"Some Place {number}")
    with client.app.state.db.Session.begin() as session:
        session.add(Prospect(id="k1", name="Has A Site", kind="restaurants", city="Austin", state="Texas", status="kept", website="https://hasasite.com"))
    assert robot.tick(limit=3)["checked"] == 3
    assert robot.tick(limit=3)["checked"] == 1
    assert get(client, "k1").notes == ""


def test_the_job_never_sends_anything(client):  # noqa: F811
    job = next(item for item in client.get("/api/chief").json()["jobs"] if item["id"] == "prospect_websites")
    assert job["outward"] is False


def outreach_on(client):  # noqa: F811
    from test_outreach import setup
    state = setup(client)
    client.put("/api/outreach", json={"enabled": True, "mode": "draft", "per_day": 1, "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["restaurants"]}).raise_for_status()
    return state


def test_outreach_being_on_is_enough_with_the_job_left_off(client):  # noqa: F811
    state = outreach_on(client)
    assert not next(item for item in client.get("/api/chief").json()["jobs"] if item["id"] == "prospect_websites")["enabled"]
    finder(client, {"mizunoodle.com": OLD_SITE})
    add(client, "p1", name="Mizu Noodle")
    state.outreach.tick()
    assert get(client, "p1").website.startswith("https://mizunoodle.com")


def test_each_run_reads_only_a_few(client):  # noqa: F811
    state = outreach_on(client)
    finder(client, {})
    for number in range(5):
        add(client, f"p{number}", name=f"Some Place {number}")
    state.outreach.research()
    assert sum(NOT_FOUND in get(client, f"p{number}").notes for number in range(5)) == 3


def test_with_outreach_off_nothing_is_read(client):  # noqa: F811
    from test_outreach import setup
    state = setup(client)
    _, sites = finder(client, {})
    add(client, "p1", name="Mizu Noodle")
    state.outreach.tick()
    assert sites.asked == [] and NOT_FOUND not in get(client, "p1").notes


def test_a_problem_reading_the_web_never_stops_the_run(client):  # noqa: F811
    state = outreach_on(client)

    class Broken:
        def tick(self, limit):
            raise OSError("no network")

    state.outreach.website_finder = Broken()
    assert state.outreach.tick().get("state") != "error"


def test_a_fresh_customers_emails_are_found_with_the_job_left_off(client):  # noqa: F811
    state = outreach_on(client)
    assert not next(item for item in client.get("/api/chief").json()["jobs"] if item["id"] == "prospect_emails")["enabled"]
    with state.db.Session.begin() as session:
        session.add(Prospect(id="p1", name="Smile Dental", kind="dentists", city="Austin", state="Texas", website="http://smile-dental.example", status="kept",
                             facts=[{"key": "no_booking", "text": "No online booking", "seen": "http://smile-dental.example"}]))
    state.outreach.research()
    assert next(item for item in client.get("/api/prospects").json()["prospects"] if item["id"] == "p1")["email"] == "hello@smile-dental.example"
