"""Picking a Printify product from its catalog instead of typing IDs: search, print providers and in-stock variants,
all read-only (GET) and simulated; the catalog is read once and searched locally."""
import httpx

from test_commerce import client, configure  # noqa: F401  (client is a fixture)

BLUEPRINTS = [{"id": 6, "title": "Unisex Heavy Cotton Tee", "brand": "Gildan", "model": "5000"},
              {"id": 12, "title": "Unisex Jersey Short Sleeve Tee", "brand": "Bella+Canvas", "model": "3001"},
              {"id": 68, "title": "Ceramic Mug 11oz", "brand": "Generic brand", "model": ""}]


class Catalog:
    def __init__(self):
        self.paths = []

    def __call__(self, request):
        assert request.method == "GET" and request.headers["Authorization"] == "Bearer fixture-printify"  # read-only
        self.paths.append(request.url.path)
        if request.url.path == "/v1/catalog/blueprints.json":
            return httpx.Response(200, json=BLUEPRINTS)
        if request.url.path == "/v1/catalog/blueprints/12/print_providers.json":
            return httpx.Response(200, json=[{"id": 29, "title": "Monster Digital"}, {"id": 99, "title": "Printify Choice"}])
        if request.url.path == "/v1/catalog/blueprints/12/print_providers/29/variants.json":
            return httpx.Response(200, json={"id": 12, "title": "Unisex Jersey Short Sleeve Tee", "variants": [
                {"id": 18100, "title": "Black / S", "options": {"color": "Black", "size": "S"}, "placeholders": [{"position": "front"}, {"position": "back"}]},
                {"id": 18101, "title": "Black / M", "options": {"color": "Black", "size": "M"}, "placeholders": [{"position": "front"}]}]})
        return httpx.Response(404, json={})


def test_a_product_is_found_and_its_providers_and_variants_listed(client):  # noqa: F811
    configure(client, "printify", api_key="fixture-printify", shop_id="123")
    site = Catalog()
    client.app.state.commerce.client = httpx.Client(transport=httpx.MockTransport(site))
    tees = client.get("/api/business/printify/catalog", params={"query": "unisex TEE"}).json()
    assert [item["id"] for item in tees] == [6, 12]
    assert [item["id"] for item in client.get("/api/business/printify/catalog", params={"query": "mug 11oz"}).json()] == [68]
    assert site.paths.count("/v1/catalog/blueprints.json") == 1  # read once, searched here
    assert client.get("/api/business/printify/catalog", params={"query": " "}).status_code == 400
    providers = client.get("/api/business/printify/catalog/12/providers").json()
    assert providers == [{"id": 29, "title": "Monster Digital"}, {"id": 99, "title": "Printify Choice"}]
    variants = client.get("/api/business/printify/catalog/12/providers/29/variants").json()
    assert [(item["id"], item["title"], item["positions"]) for item in variants["variants"]] == [(18100, "Black / S", ["back", "front"]), (18101, "Black / M", ["front"])]


def test_the_catalog_needs_the_printify_connection(client):  # noqa: F811
    assert "API key" in client.get("/api/business/printify/catalog", params={"query": "tee"}).json()["detail"]
