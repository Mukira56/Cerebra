"""Phase 3: posts to the owner's X, Facebook Page and Instagram, through simulated official APIs (no real accounts)."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_hq import social
from ai_hq.agents import AgentResult
from ai_hq.api import create_app
from ai_hq.config import Settings
from fakes import FixtureRegistry
from test_product_api import KEY, enable_agents

X_KEYS = {"consumer_key": "consumerKEY123456", "consumer_secret": "consumerSECRET123456", "access_token": "12345-accessTOKEN123456", "access_secret": "accessSECRET123456"}
PAGE_TOKEN = "EAAPageToken1234567890abcdef"


class Platforms:
    def __init__(self):
        self.calls, self.broken = [], set()

    def __call__(self, request):
        self.calls.append(request)
        if request.url.host in self.broken:
            return httpx.Response(500, json={"title": "Internal error"})
        if request.url.host == "api.x.com":
            assert request.headers["Authorization"].startswith('OAuth oauth_consumer_key="consumerKEY123456"') and "oauth_signature=" in request.headers["Authorization"]
            if request.url.path == "/2/users/me":
                return httpx.Response(200, json={"data": {"id": "1", "username": "mukira_dev"}})
            return httpx.Response(201, json={"data": {"id": f"tw{len(self.calls)}", "text": json.loads(request.content)["text"]}})
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()} if request.method == "POST" else dict(request.url.params)
        assert form.get("access_token") == PAGE_TOKEN
        if request.url.path == "/987654":
            return httpx.Response(200, json={"name": "Mukira Studio"})
        if request.url.path == "/987654/feed":
            return httpx.Response(200, json={"id": f"987654_{len(self.calls)}"})
        if request.url.path == "/1784":
            return httpx.Response(200, json={"username": "mukira.studio"})
        if request.url.path == "/1784/media":
            assert form["image_url"].startswith("https://") and form["caption"]
            return httpx.Response(200, json={"id": "container9"})
        if request.url.path == "/1784/media_publish":
            assert form["creation_id"] == "container9"
            return httpx.Response(200, json={"id": "ig_post_1"})
        return httpx.Response(404, json={"error": {"message": "unknown"}})


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.platforms = Platforms()
    app.state.publisher.client = httpx.Client(transport=httpx.MockTransport(app.state.platforms))
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def connect_all(client):
    assert "@mukira_dev" in client.put("/api/social/accounts/x", json=X_KEYS).json()["message"]
    assert "Mukira Studio" in client.put("/api/social/accounts/facebook", json={"page_id": "987654", "page_token": PAGE_TOKEN}).json()["message"]
    assert "@mukira.studio" in client.put("/api/social/accounts/instagram", json={"ig_user_id": "1784"}).json()["message"]


def new_post(client, **fields):
    response = client.post("/api/social/posts", json={"text": "Just shipped a booking site for a dental clinic: patients book online in 30 seconds.", "channels": ["x", "facebook"], **fields})
    assert response.status_code == 201, response.text
    return response.json()


def due(client):
    return client.app.state.publisher.publish_due()


def test_oauth_signature_matches_xs_documented_example():
    keys = {"consumer_key": "xvz1evFS4wEEPTGEFPHBog", "consumer_secret": "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
            "access_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "access_secret": "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE"}
    header = social.oauth_header("POST", "https://api.twitter.com/1.1/statuses/update.json", keys, nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
                                 stamp=1318622958, extra={"status": "Hello Ladies + Gentlemen, a signed OAuth request!", "include_entities": "true"})
    assert 'oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"' in header


def test_posts_are_checked_before_they_can_be_approved(client):
    assert social.x_length("Hi", "https://example.com/a/very/long/path/that/goes/on") == 2 + 1 + 23
    assert client.post("/api/social/posts", json={"text": "x" * 281, "channels": ["x"]}).status_code == 400
    assert client.post("/api/social/posts", json={"text": "Nice", "channels": ["instagram"]}).status_code == 400  # needs a picture
    assert client.post("/api/social/posts", json={"text": "Nice", "channels": ["facebook"], "link": "http://insecure"}).status_code == 400
    assert client.post("/api/social/posts", json={"text": "Nice", "channels": []}).status_code == 400


def test_drafts_never_post_and_approved_posts_go_out_on_time(client):
    connect_all(client)
    draft = new_post(client)
    assert due(client) == [] and len(client.app.state.platforms.calls) == 3  # only the three connection checks
    later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    client.post(f"/api/social/posts/{draft['id']}/approve", json={"when": later})
    assert due(client) == []  # not time yet
    with client.app.state.db.Session.begin() as session:
        session.get(social.SocialPost, draft["id"]).scheduled_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    result = due(client)
    assert result[0]["posted"] == ["x", "facebook"] and not result[0]["failed"]
    post = client.get("/api/social").json()["posts"][0]
    assert post["status"] == "posted" and post["results"]["x"]["url"].startswith("https://x.com/i/web/status/") and post["results"]["x"]["cost"] == 0.015
    assert post["results"]["facebook"]["id"].startswith("987654_")
    assert due(client) == []  # never twice
    assert client.get("/api/social").json()["spent_this_month"] == 0.015


def test_the_monthly_x_budget_and_daily_limit_hold(client):
    connect_all(client)
    client.put("/api/social/settings", json={"monthly_cap": 0.25, "per_day": 2})
    with_link = new_post(client, channels=["x"], link="https://mukira.dev/work/clinic")
    client.post(f"/api/social/posts/{with_link['id']}/post-now")
    assert client.get("/api/social").json()["spent_this_month"] == 0.2  # a post with a link costs more
    second = new_post(client, channels=["x"], link="https://mukira.dev/work/two")
    result = client.post(f"/api/social/posts/{second['id']}/post-now").json()["results"][0]
    assert result["waiting"] == ["x"]
    waiting = next(post for post in client.get("/api/social").json()["posts"] if post["id"] == second["id"])
    assert waiting["status"] == "approved" and "monthly X budget" in waiting["results"]["x"]["waiting"]
    for _ in range(2):
        client.post(f"/api/social/posts/{new_post(client, channels=['facebook'])['id']}/post-now")
    third = client.post(f"/api/social/posts/{new_post(client, channels=['facebook'])['id']}/post-now").json()["results"][0]
    assert third["waiting"] == ["facebook"]  # 2 a day on the Page: the rest goes out tomorrow


def test_a_failure_is_never_retried_by_itself(client):
    connect_all(client)
    platforms = client.app.state.platforms
    platforms.broken.add("graph.facebook.com")
    post = new_post(client)
    result = client.post(f"/api/social/posts/{post['id']}/post-now").json()["results"][0]
    assert result["posted"] == ["x"] and result["failed"] == ["facebook"]
    stored = next(item for item in client.get("/api/social").json()["posts"] if item["id"] == post["id"])
    assert stored["status"] == "partial" and "Facebook refused it" in stored["results"]["facebook"]["error"]
    calls = len(platforms.calls)
    assert due(client) == [] and len(platforms.calls) == calls  # no automatic retry
    platforms.broken.clear()
    retried = client.post(f"/api/social/posts/{post['id']}/retry").json()["results"][0]
    assert retried["posted"] == ["facebook"]  # X wasn't posted again
    assert sum(1 for request in platforms.calls if request.url.path == "/2/tweets") == 1


def test_instagram_publishes_in_two_steps_with_a_picture(client):
    connect_all(client)
    post = new_post(client, channels=["instagram"], image_url="https://mukira.dev/img/clinic.png")
    result = client.post(f"/api/social/posts/{post['id']}/post-now").json()["results"][0]
    assert result["posted"] == ["instagram"]
    paths = [request.url.path for request in client.app.state.platforms.calls]
    assert paths[-2:] == ["/1784/media", "/1784/media_publish"]


def test_tokens_are_protected_and_editing_an_approved_post_needs_approval_again(client):
    connect_all(client)
    overview = json.dumps(client.get("/api/social").json()) + json.dumps(client.get("/api/business/connections").json())
    assert all(secret not in overview for secret in [*X_KEYS.values(), PAGE_TOKEN])
    post = new_post(client)
    client.post(f"/api/social/posts/{post['id']}/approve", json={})
    edited = client.patch(f"/api/social/posts/{post['id']}", json={"text": "Changed my mind about the wording."}).json()
    assert edited["status"] == "draft"
    assert client.put("/api/social/accounts/instagram", json={"ig_user_id": "abc"}).status_code == 400
    client.delete("/api/social/accounts/facebook")
    accounts = client.get("/api/social").json()["accounts"]
    assert not accounts["facebook"]["connected"] and not accounts["instagram"]["connected"]  # Instagram posts through the Page


class PostWriter(FixtureRegistry):
    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompt = prompt
        return AgentResult(True, json.dumps([{"text": "Tip: a booking button above the fold doubles enquiries for clinics I build for."}, {"text": "x" * 400}]))


def test_the_owners_model_drafts_posts_that_still_need_approval(client):
    assert client.post("/api/social/write", json={"count": 3}).status_code == 400  # agents off
    enable_agents(client)
    writer = PostWriter()
    client.app.state.supervisor.registry = writer
    client.app.state.post_writer.start(3, ["x"], wait=True)
    posts = client.get("/api/social").json()["posts"]
    assert [post["status"] for post in posts] == ["draft"] and posts[0]["origin"] == "ai"  # the too-long one was skipped, not cut
    assert "never invent clients, results" in writer.prompt and client.get("/api/social").json()["writer"]["count"] == 1


def test_a_post_for_an_unconnected_channel_cant_be_approved(client):
    post = new_post(client, channels=["x"])
    refused = client.post(f"/api/social/posts/{post['id']}/approve", json={})
    assert refused.status_code == 400 and "Connect X first" in refused.json()["detail"]
