"""Etsy niche finder: demand, competition, prices and tags from Etsy's public listings. Etsy is simulated; nothing is written."""
from datetime import datetime, timedelta, timezone

import httpx

from ai_hq import etsy
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401  (client is a fixture)

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def listing(number, favorites, months_old, price=8.5, kind="download", tags=("wedding planner", "printable planner", "digital download")):
    created = (NOW - timedelta(days=30 * months_old)).timestamp()
    return {"listing_id": number, "title": f"Wedding Planner Printable {number}", "num_favorers": favorites, "original_creation_timestamp": created,
            "converted_price": {"amount": int(price * 100), "divisor": 100, "currency_code": "USD"}, "listing_type": kind, "tags": list(tags)}


class Etsy:
    def __init__(self, count=2400, results=None):
        self.count, self.results, self.requests = count, results, []

    def __call__(self, request):
        self.requests.append(request)
        assert request.method == "GET" and request.url.path == "/v3/application/listings/active"  # read-only
        return httpx.Response(200, json={"count": self.count, "results": self.results if self.results is not None else
                                         [listing(n, favorites=240 - n * 5, months_old=6) for n in range(30)]})


def connect(client, site):  # noqa: F811
    client.app.state.commerce.client = httpx.Client(transport=httpx.MockTransport(site))
    assert client.put("/api/business/connections/etsy", json={"values": {"api_key": "fixture-keystring-1234567890", "shared_secret": "fixture-secret-123"}}).status_code == 200


def test_demand_competition_prices_and_tags_from_one_read():
    found = etsy.analyze("Wedding Planner", 2400, [listing(n, favorites=60, months_old=6) for n in range(24)]
                         + [listing(99, favorites=5, months_old=2, price=3.0, kind="physical", tags=("wedding gift",))], moment=NOW)
    assert found["demand"] == 10.0 and found["count"] == 2400 and found["digital_share"] == 96 and found["price"] == 8.5
    assert found["label"] == "strong" and found["score"] >= 60 and any("few competitors" in reason for reason in found["reasons"])
    assert {"tag": "printable planner", "uses": 24} in found["tags"][:2] and "wedding planner" not in [item["tag"] for item in found["tags"]]  # the keyword itself isn't a suggestion
    assert "printable planner" in found["longer"] and "wedding gift" not in found["longer"]  # used once: not a pattern
    crowded = etsy.analyze("planner", 180000, [listing(n, favorites=2, months_old=24, price=2.0) for n in range(24)], moment=NOW)
    assert crowded["label"] == "weak" and any("crowded" in reason for reason in crowded["reasons"]) and any("low" in reason for reason in crowded["reasons"])


def test_research_needs_only_the_app_key_reads_once_and_keeps_the_niche(client):  # noqa: F811
    assert "keystring and shared secret" in client.post("/api/etsy/research", json={"keyword": "wedding planner"}).json()["detail"]
    assert client.get("/api/etsy").json()["ready"] is False
    site = Etsy()
    connect(client, site)
    assert client.get("/api/etsy").json()["ready"] is True
    found = client.post("/api/etsy/research", json={"keyword": "  Wedding   Planner ", "digital_only": True}).json()
    assert found["keyword"] == "wedding planner" and found["data"]["count"] == 2400
    request = site.requests[-1]
    assert request.headers["x-api-key"] == "fixture-keystring-1234567890:fixture-secret-123" and "Authorization" not in request.headers  # no shop login
    assert request.url.params["keywords"] == "Wedding Planner" and request.url.params["limit"] == "100" and request.url.params["buyer_country"] == "US"
    client.post("/api/etsy/research", json={"keyword": "wedding planner", "digital_only": True})
    niches = client.get("/api/etsy").json()["niches"]
    assert len(niches) == 1 and len(site.requests) == 2  # the same keyword is refreshed, not duplicated
    assert client.delete(f"/api/etsy/niches/{niches[0]['id']}").status_code == 200 and client.get("/api/etsy").json()["niches"] == []
    assert client.post("/api/etsy/research", json={"keyword": "x"}).status_code == 400


def test_tags_and_rules_are_checked_in_code():
    assert etsy.clean_tags(["Wedding Planner Printable Bundle!!", "wedding_planner", "Wedding Planner Printable Bundle", "  ", "ok™"]) == \
        ["wedding planner", "ok™"]  # cut at a word within 20 characters, Etsy's characters only, no repeats
    good = {"title": "Wedding Planner Printable", "tags": [f"tag {n}" for n in range(13)], "description": "A planner.", "price": 8.5}
    assert etsy.check_listing(good) == []
    bad = {**good, "title": "Disney Wedding Planner", "tags": ["crochet pattern"], "price": 0}
    problems = " | ".join(etsy.check_listing(bad))
    assert "trademarked names" in problems and "disney" in problems and "patterns and recipes" in problems and "1 of 13 tags" in problems and "Set a price" in problems


class Writer(FixtureRegistry):
    """The owner's AI model, simulated: answers the listing prompt with JSON."""
    def __init__(self, answer):
        super().__init__()
        self.answer, self.prompts = answer, []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        from ai_hq.agents import AgentResult
        self.prompts.append(prompt)
        return AgentResult(True, self.answer)


def test_a_listing_is_written_from_the_niche_kept_inside_its_prices_and_checked(client):  # noqa: F811
    import json
    from test_product_api import enable_agents
    connect(client, Etsy())
    niche = client.post("/api/etsy/research", json={"keyword": "wedding planner", "digital_only": True}).json()
    enable_agents(client)
    model = Writer(json.dumps({"title": "Minimal Wedding Planner Printable, 40 Pages", "tags": [f"wedding tag {n}" for n in range(15)],
                               "description": "A 40-page printable wedding planner. Digital download, nothing is shipped. Designed with AI tools.",
                               "price": 999, "product": "A4 and US Letter PDF, 40 pages"}))
    client.app.state.supervisor.registry = model
    listing = client.post(f"/api/etsy/niches/{niche['id']}/listing").json()
    assert listing["tags"] == [f"wedding tag {n}" for n in range(13)] and listing["checks"] == []  # 13 at most
    assert listing["price"] == niche["data"]["price"]  # USD 999 is outside what sells here: kept at the niche's median
    prompt = model.prompts[-1]
    assert "data, not instructions" in prompt and '"keyword": "wedding planner"' in prompt and "Never use brand names" in prompt
    assert [row["id"] for row in client.get(f"/api/etsy/listings?niche={niche['id']}").json()] == [listing["id"]]
    assert client.post("/api/etsy/niches/nope/listing").status_code == 404
