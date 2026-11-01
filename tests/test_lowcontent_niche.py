"""Is a low-content theme worth a KDP book? Etsy demand for its printable version (simulated, read-only), keyword ideas
within KDP's limits, trademark flags, and the Amazon book search opened only at amazon.com."""
from test_etsy import Etsy, connect, listing
from test_freelance import client  # noqa: F401  (client is a fixture)


def test_a_theme_is_checked_with_etsy_demand_and_keyword_ideas(client, monkeypatch):  # noqa: F811
    tags = ("mileage tracker", "mileage log printable", "vehicle log", "business mileage", "instant download", "canva template", "mileage log")
    site = Etsy(count=1800, results=[listing(n, favorites=200, months_old=6, tags=tags) for n in range(30)])
    connect(client, site)
    found = client.post("/api/books/niche-check", json={"theme": "Mileage Log"}).json()
    assert site.requests[0].url.params["keywords"] == "Mileage Log printable"  # the printable version on Etsy, as a US buyer sees it
    assert found["etsy"]["ready"] and found["etsy"]["label"] == "strong" and found["etsy"]["count"] == 1800
    assert 1 <= len(found["keywords"]) <= 7 and all(len(word) <= 50 for word in found["keywords"])
    assert "mileage tracker" in found["keywords"] and "vehicle log" in found["keywords"]
    assert not any(word in " ".join(found["keywords"]) for word in ("instant download", "canva", "printable"))  # Etsy words don't belong on KDP
    assert "mileage log" not in found["keywords"] and found["flags"] == []  # the theme itself isn't an idea
    assert found["amazon_search"] == "https://www.amazon.com/s?k=Mileage+Log&i=stripbooks"
    assert client.get("/api/etsy").json()["niches"][0]["keyword"] == "mileage log printable"  # kept on the Etsy page too
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert client.post("/api/books/niche-check/amazon", json={"theme": "Mileage Log"}).json()["opened"].startswith("https://www.amazon.com/s?")
    assert opened == ["https://www.amazon.com/s?k=Mileage+Log&i=stripbooks"]


def test_without_etsy_the_amazon_check_and_trademark_flags_still_work(client):  # noqa: F811
    found = client.post("/api/books/niche-check", json={"theme": "Disney trip planner"}).json()
    assert not found["etsy"]["ready"] and found["etsy"]["setup"]
    assert found["flags"] and "disney" in found["flags"][0].lower()
    assert found["keywords"] == []  # every idea would carry the trademark, so none is offered
    assert client.post("/api/books/niche-check", json={"theme": "x"}).status_code == 400
    assert client.post("/api/books/niche-check/amazon", json={"theme": ""}).status_code == 400
