"""Prospector: local businesses from OpenStreetMap, chains left out, each kept only with a fact seen on its own site.
OpenStreetMap and the businesses' websites are simulated; nothing real is fetched and nobody is contacted."""
import httpx
import pytest

from ai_hq import prospects
from test_freelance import client  # noqa: F401  (client is a fixture)

MODERN = '<html><head><meta name="viewport" content="width=device-width"></head><body><a href="/book">Book an appointment</a><form></form>© 2026</body></html>'
OLD = "<html><body><p>Smile Dental, family dentistry since 1990.</p><p>Call us!</p><p>Copyright 2016</p></body></html>"


def osm(request):
    if request.url.host == "nominatim.openstreetmap.org":
        assert request.url.params["countrycodes"] == "us" and "Cerebra" in request.headers["User-Agent"]
        return httpx.Response(200, json=[{"osm_type": "relation", "osm_id": 113314, "display_name": "Austin, Travis County, Texas, United States"}])
    if request.url.host == "overpass-api.de":
        from urllib.parse import parse_qs
        query = parse_qs(request.content.decode())["data"][0]
        assert "area(3600113314)" in query and '["amenity"="dentist"]' in query and "Cerebra" in request.headers["User-Agent"]
        elements = [
            {"type": "node", "id": 1, "tags": {"name": "Smile Dental", "website": "http://smile-dental.example", "phone": "+1 512 555 0100", "addr:street": "Main St"}},
            {"type": "node", "id": 2, "tags": {"name": "Modern Teeth", "website": "modern-teeth.example"}},
            {"type": "node", "id": 3, "tags": {"name": "Hill Family Dentistry"}},  # no website
            {"type": "way", "id": 4, "tags": {"name": "Aspen Dental", "brand": "Aspen Dental", "website": "https://aspen.example"}},
            *({"type": "node", "id": 10 + number, "tags": {"name": "Bright Now! Dental", "website": "https://brightnow.example"}} for number in range(3)),
            {"type": "node", "id": 20, "tags": {"name": "Router Dental", "website": "http://192.168.1.1"}},
        ]
        return httpx.Response(200, json={"elements": elements})
    raise AssertionError(f"unexpected {request.url}")


def site(request):
    host = request.url.host
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    if host == "smile-dental.example":
        return httpx.Response(200, text=OLD)
    if host == "modern-teeth.example":
        return httpx.Response(200, text=MODERN)
    raise AssertionError(f"read {request.url}")


def finder(client):  # noqa: F811
    resolve = lambda host: host.endswith(".example")  # noqa: E731 - the simulated web: only these are public
    reader = prospects.Reader(httpx.Client(transport=httpx.MockTransport(site)), resolve=resolve)
    return prospects.Finder(client.app.state.db, httpx.Client(transport=httpx.MockTransport(osm)), reader, pause=0)


def test_a_search_leaves_out_chains_and_keeps_only_businesses_with_a_reason(client):  # noqa: F811
    result = finder(client).search("dentists", "Austin", "Texas")
    assert result["found"] == 8 and result["chains"] == 4 and result["new"] == 4  # Aspen (brand) and Bright Now! (3 locations) left out
    assert result["kept"] == 1 and result["without_site"] == 1 and result["unreadable"] == 1
    with client.app.state.db.Session() as session:
        listed = {item["name"]: item for item in prospects.overview(session)["prospects"]}
    smile = listed["Smile Dental"]
    keys = {fact["key"] for fact in smile["facts"]}
    assert keys >= {"no_https", "no_mobile", "no_booking", "outdated", "no_contact"} and all(fact["seen"] == "http://smile-dental.example" for fact in smile["facts"])
    hill = listed["Hill Family Dentistry"]  # the map lists no website: to check by hand, never claimed as "no website"
    assert hill["status"] == "new" and hill["facts"] == [] and "Search for it" in hill["notes"]
    assert "Modern Teeth" not in listed  # a modern site with booking: no reason to contact them
    assert "Router Dental" not in listed  # a private address is never read


def test_the_same_business_is_found_once(client):  # noqa: F811
    search = finder(client)
    search.search("dentists", "Austin", "Texas")
    assert search.search("dentists", "Austin", "Texas")["new"] == 0


def test_private_addresses_and_robots_rules_are_respected():
    assert not prospects.public_address("localhost") and not prospects.public_address("127.0.0.1")
    assert prospects.normal_site("example.com/home") == "https://example.com/home"
    assert prospects.normal_site("javascript:alert(1)") == "" and prospects.normal_site("https://user:pw@example.com") == ""
    closed = prospects.Reader(httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="User-agent: *\nDisallow: /\n"))),
                              resolve=lambda host: True)
    with pytest.raises(prospects.Blocked, match="robots.txt"):
        closed.page("https://closed.example/")
    hops = prospects.Reader(httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="") if request.url.path == "/robots.txt" else httpx.Response(302, headers={"location": "http://10.0.0.5/admin"}))),
        resolve=lambda host: host.endswith(".example"))
    with pytest.raises(prospects.Blocked, match="isn't a public website"):
        hops.page("https://redirects.example/")  # a redirect into the owner's network is refused too


def test_facts_are_only_what_the_page_shows():
    assert prospects.facts_from({"url": "https://ok.example", "status": 200, "html": MODERN, "seconds": 0.4}, year=2026) == []
    assert prospects.facts_from({"url": "https://ok.example", "status": 200, "html": MODERN, "seconds": 9.5}, year=2026) == []  # speed from here proves nothing
    assert prospects.facts_from({"url": "https://x.example", "status": 500, "html": "", "seconds": 1}, year=2026)[0]["key"] == "broken"


def test_the_page_runs_searches_and_tracks_each_prospect(client):  # noqa: F811
    client.app.state.prospector = finder(client)
    import ai_hq.api  # noqa: F401
    # The route uses the app's own prospector; swap its clients for the simulated ones.
    real = client.app.state.prospector
    assert client.post("/api/prospects/search", json={"kind": "spaceships", "city": "Austin", "state": "Texas"}).status_code == 400
    assert client.post("/api/prospects/search", json={"kind": "dentists", "city": "", "state": "Texas"}).status_code == 400
    with client.app.state.db.Session() as session:
        assert prospects.overview(session)["attribution"].startswith("Business listings © OpenStreetMap")
    real.search("dentists", "Austin", "Texas")
    state = client.get("/api/prospects").json()
    kept = next(item for item in state["prospects"] if item["name"] == "Smile Dental")
    assert state["counts"]["kept"] == 1 and state["counts"]["new"] == 1 and state["searches"][0]["city"] == "Austin"
    updated = client.patch(f"/api/prospects/{kept['id']}", json={"status": "contacted", "notes": "Called, left a message"}).json()
    assert updated["status"] == "contacted" and client.get("/api/prospects").json()["counts"]["contacted"] == 1
    assert client.patch(f"/api/prospects/{kept['id']}", json={"status": "spammed"}).status_code == 400


def test_booking_or_contact_on_another_page_counts_and_a_blocked_reader_claims_nothing():
    linked = '<meta name="viewport" content="x"><a href="/request-appointment">Visit</a><a href="/contact-us">Contact</a>'
    assert prospects.facts_from({"url": "https://ok.example", "status": 200, "html": linked, "seconds": 1}, year=2026) == []
    with pytest.raises(prospects.Blocked, match="nothing is claimed"):
        prospects.facts_from({"url": "https://shy.example", "status": 403, "html": "", "seconds": 1}, year=2026)


def test_other_ways_of_saying_book_online_count():
    for words in ("Reserve an appointment", "Make your appointment", "Book your visit", "Appointment request"):
        page = {"url": "https://ok.example", "status": 200, "html": f'<meta name="viewport" content="x"><form></form><p>{words}</p>', "seconds": 1}
        assert prospects.facts_from(page, year=2026) == [], words
