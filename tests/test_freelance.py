"""Freelance leads: found on public sources (simulated here, no real network), scored against what the owner sells."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_hq import freelance
from ai_hq.api import create_app
from ai_hq.config import Settings
from test_product_api import KEY

NOW = datetime.now(timezone.utc)


def ago(hours):
    return int((NOW - timedelta(hours=hours)).timestamp())


class Sources:
    """Freelancer.com, Remote OK, Remotive, Himalayas and HN as they answer, in miniature."""
    def __init__(self):
        self.calls, self.broken = [], set()

    def __call__(self, request):
        self.calls.append(request)
        assert request.method == "GET" and "Cerebra" in request.headers["User-Agent"]  # read-only, and says who is asking
        host = request.url.host
        if host in self.broken:
            return httpx.Response(503)
        if host == "www.freelancer.com":
            return httpx.Response(200, json={"result": {"projects": [
                {"id": 1, "title": "Build a React landing page for my bakery", "seo_url": "react/bakery-landing", "description": "Need a fast landing page in React with a contact form.",
                 "budget": {"minimum": 250, "maximum": 750}, "currency": {"code": "USD", "exchange_rate": 1.0}, "type": "fixed", "time_submitted": ago(2),
                 "bid_stats": {"bid_count": 6}, "jobs": [{"name": "React.js"}]},
                {"id": 2, "title": "Logo for a tea brand", "seo_url": "logo/tea", "description": "Branding and logo design.", "budget": {"minimum": 600, "maximum": 1500},
                 "currency": {"code": "INR", "exchange_rate": 0.012}, "type": "fixed", "time_submitted": ago(5), "bid_stats": {"bid_count": 120}},
                {"id": 3, "title": "Write my thesis chapter on machine learning", "seo_url": "ml/thesis", "description": "Academic writing.",
                 "budget": {"minimum": 100, "maximum": 300}, "currency": {"code": "USD", "exchange_rate": 1.0}, "type": "fixed", "time_submitted": ago(1), "bid_stats": {"bid_count": 3}}]}})
        if host == "remoteok.com":
            return httpx.Response(200, json=[{"legal": "Please link back to Remote OK"},
                                             {"id": "r1", "position": "Senior Python Developer", "company": "Acme", "url": "https://remoteok.com/remote-jobs/r1",
                                              "description": "<p>Full-time role building Django APIs.</p>", "tags": ["python", "django", "full time"], "epoch": ago(3),
                                              "salary_min": 90000, "salary_max": 120000}])
        if host == "remotive.com":
            return httpx.Response(200, json={"jobs": [{"id": 77, "title": "Freelance Shopify Developer", "company_name": "Shopco", "url": "https://remotive.com/remote-jobs/77",
                                                       "description": "Contract work on a Shopify store and e-commerce theme.", "job_type": "contract", "tags": ["shopify"],
                                                       "publication_date": (NOW - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%S")}]})
        if host == "himalayas.app":
            return httpx.Response(200, json={"jobs": [{"guid": "h1", "title": "Plumber", "companyName": "Pipes", "applicationLink": "https://himalayas.app/h1",
                                                       "description": "Fix pipes.", "employmentType": "Full Time", "pubDate": ago(4)}]})
        if host == "hn.algolia.com":
            if request.url.path.startswith("/api/v1/items/"):
                return httpx.Response(200, json={"children": [
                    {"id": 900, "author": "startupjane", "created_at_i": ago(30), "text": "SEEKING FREELANCER | Remote<p>Need a Next.js developer for a two-week dashboard project."},
                    {"id": 901, "author": "dev", "created_at_i": ago(30), "text": "SEEKING WORK | Remote<p>I build React apps."}]})
            if "author_whoishiring" in str(request.url):
                return httpx.Response(200, json={"hits": []})
            return httpx.Response(200, json={"hits": [{"title": "Ask HN: Freelancer? Seeking freelancer? (October 2026)", "objectID": "555"}]})
        return httpx.Response(404)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.sources = Sources()
    app.state.finder.client = httpx.Client(transport=httpx.MockTransport(app.state.sources), headers={"User-Agent": freelance.USER_AGENT})
    app.state.opened = []
    app.state.open_document = app.state.opened.append
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def by_title(client, text):
    return next(lead for lead in client.get("/api/freelance?hidden=true").json()["leads"] if text in lead["title"])


def test_every_source_is_read_and_the_best_freelance_work_ranks_first(client):
    results = client.post("/api/freelance/check").json()
    assert {name: result.get("added") for name, result in results.items()} == {"freelancer": 3, "remoteok": 1, "remotive": 1, "himalayas": 1, "hn": 1}
    leads = client.get("/api/freelance").json()["leads"]
    assert leads[0]["title"] == "Build a React landing page for my bakery"
    top = leads[0]
    assert top["url"] == "https://www.freelancer.com/projects/react/bakery-landing" and top["bids"] == 6
    assert any("matches" in reason and "react" in reason for reason in top["reasons"]) and "only 6 bids so far" in top["reasons"]
    hn = by_title(client, "SEEKING FREELANCER")
    assert hn["url"] == "https://news.ycombinator.com/item?id=900" and hn["score"] > 0
    assert not any("SEEKING WORK" in lead["title"] for lead in leads)  # freelancers offering themselves aren't work
    assert by_title(client, "Freelance Shopify")["credit"] == "via Remotive"


def test_scores_sink_salaried_jobs_homework_crowded_and_tiny_budgets(client):
    client.post("/api/freelance/check")
    salaried = by_title(client, "Senior Python Developer")
    assert "a salaried job, not a freelance project" in salaried["reasons"] and any(reason.startswith("salary") for reason in salaried["reasons"])
    thesis = by_title(client, "thesis")
    assert any("academic" in reason for reason in thesis["reasons"]) and thesis["score"] < by_title(client, "React landing")["score"]
    logo = by_title(client, "Logo for a tea brand")
    assert "120 bids already" in logo["reasons"] and any("about USD 18" in reason for reason in logo["reasons"])  # INR shown in dollars
    plumber = by_title(client, "Plumber")
    assert plumber["score"] == 0 and plumber["reasons"] == ["doesn't match what you sell"]


def test_the_owner_profile_steers_the_scores(client):
    client.post("/api/freelance/check")
    before = by_title(client, "React landing")["score"]
    saved = client.put("/api/freelance/profile", json={"services": ["design"], "exclude": ["bakery"], "min_budget": 1000}).json()
    assert saved["services"] == ["design"] and saved["exclude"] == ["bakery"]
    bakery = by_title(client, "React landing")
    assert bakery["score"] == 0 and bakery["reasons"] == ["excluded: bakery"] and before > 0
    assert any("below your 1,000" in reason for reason in by_title(client, "Logo for a tea brand")["reasons"])
    assert client.put("/api/freelance/profile", json={"services": []}).status_code == 400


def test_sources_are_checked_politely_and_one_failure_never_stops_the_rest(client):
    finder, sources = client.app.state.finder, client.app.state.sources
    sources.broken.add("remoteok.com")
    first = finder.check()
    assert "error" in first["remoteok"] and first["freelancer"]["added"] == 3 and first["hn"]["added"] == 1
    calls = len(sources.calls)
    assert finder.check() == {} and len(sources.calls) == calls  # nothing is due yet: no requests at all
    overview = client.get("/api/freelance").json()
    remotive = next(source for source in overview["sources"] if source["id"] == "remotive")
    assert remotive["every_minutes"] == 360 and remotive["last"]["added"] == 1  # at most 4 checks a day, as Remotive asks
    client.put("/api/freelance/profile", json={"sources": {"remoteok": False}})
    sources.broken.clear()
    assert "remoteok" not in client.post("/api/freelance/check").json()  # switched off by the owner


def test_known_leads_keep_the_owners_status_when_seen_again(client):
    client.post("/api/freelance/check")
    lead = by_title(client, "React landing")
    marked = client.patch(f"/api/freelance/leads/{lead['id']}", json={"status": "applied", "notes": "Sent via Freelancer.com"}).json()
    assert marked["status"] == "applied"
    client.post("/api/freelance/check")
    again = by_title(client, "React landing")
    assert again["status"] == "applied" and again["notes"] == "Sent via Freelancer.com"
    assert len([item for item in client.get("/api/freelance?hidden=true").json()["leads"] if "React landing" in item["title"]]) == 1
    assert client.patch(f"/api/freelance/leads/{lead['id']}", json={"status": "sold"}).status_code == 400
    client.post("/api/freelance/open", json={"id": lead["id"]})
    assert client.app.state.opened == ["https://www.freelancer.com/projects/react/bakery-landing"]


def test_a_job_pasted_from_upwork_or_fiverr_is_scored_too(client):
    pasted = client.post("/api/freelance/leads", json={"title": "WordPress site for a dental clinic", "platform": "Upwork", "budget": 800,
                                                       "url": "https://www.upwork.com/jobs/~01abc", "description": "We need a WordPress website with booking and SEO."}).json()
    assert pasted["source"] == "pasted" and pasted["source_label"] == "Upwork" and pasted["score"] >= 40
    assert any("budget USD 800" in reason for reason in pasted["reasons"])
    assert client.post("/api/freelance/leads", json={"title": "x", "description": "short"}).status_code == 400
    assert client.post("/api/freelance/leads", json={"title": "Job", "description": "a" * 30, "url": "javascript:alert(1)"}).status_code == 400


def test_strong_new_matches_reach_the_phone_without_details(client):
    notifier = client.app.state.notifier
    client.put("/api/business/notifications", json={"ntfy_enabled": True})
    notifier.pending_messages()
    client.post("/api/freelance/check")
    _, messages = notifier.pending_messages()
    assert [title for title, _, _ in messages] == ["Cerebra · new freelance work"]
    assert "bakery" not in json.dumps(messages).lower()  # no job details over a public server


def test_description_html_becomes_plain_text():
    assert freelance.text_of("<p>Hello&nbsp;<b>world</b></p><ul><li>One</li><li>Two</li></ul>") == "Hello world\nOne\nTwo"


def test_placeholder_posts_are_not_stored_but_pasted_jobs_always_are():
    assert freelance.placeholder({"title": "z · y", "description": "d"}) and freelance.placeholder({"title": "QA · y", "description": "d"})
    assert not freelance.placeholder({"title": "Fix my sink · Bob", "description": "Fix pipes."})  # short, but a real job
    assert not freelance.placeholder({"title": "AI · Acme", "description": "Build an AI assistant for our support team."})


def test_a_placeholder_stored_before_is_hidden_when_seen_again(client):  # noqa: F811
    lead = {"source": "remoteok", "native_id": "77", "title": "z · y", "description": "d", "url": ""}
    with client.app.state.db.Session.begin() as session:
        session.add(freelance.FreelanceLead(id="remoteok:77", source="remoteok", title="z · y", description="d", status="new"))
    with client.app.state.db.Session.begin() as session:
        assert freelance.store(session, [lead]) == 0
    with client.app.state.db.Session() as session:
        assert session.get(freelance.FreelanceLead, "remoteok:77").status == "hidden"


def test_a_posts_read_check_is_shown_to_the_owner():
    text = "Great role.\n\nPlease mention the word **SWANKY** and tag RMTAyLjIwMi4xNTQuMjUw when applying to show you read the job post completely."
    assert freelance.applicant_checks(text) == [{"word": "SWANKY", "tag": "RMTAyLjIwMi4xNTQuMjUw"}]
    assert freelance.applicant_checks("Build a website for my bakery.") == []


def test_other_professions_and_title_less_matches_stay_below_automatic_bidding():
    settings = {"services": ["web", "mobile_ai", "design", "data"], "keywords": [], "exclude": [], "min_budget": 0}
    fresh = {"kind": "fixed", "budget_min": 250, "budget_max": 750, "currency": "USD", "bids": 5}
    lawyer, why = freelance.score({**fresh, "title": "IP Lawyer / Legal Expert Wanted: Software Copyright",
                                   "description": "Review our SaaS dashboard, scraping tool and UI design terms."}, settings)
    assert lawyer < 40 and any("asks for lawyer" in reason for reason in why)
    vague, why = freelance.score({**fresh, "title": "Knowledge booster", "description": "React front-end, mobile app for android and ios."}, settings)
    assert vague == freelance.TITLE_CAP and "not the title" in why[-1]
    real, _ = freelance.score({**fresh, "title": "React landing page for a bakery", "description": "A fast React landing page."}, settings)
    assert real >= 40


def test_a_fortune_for_a_small_job_is_flagged_not_rewarded():
    settings = {"services": ["design"], "keywords": [], "exclude": [], "min_budget": 0}
    lead = {"title": "Personal portfolio bio copywriter", "description": "Write a short bio for my portfolio website.", "kind": "fixed", "currency": "USD"}
    bait, why = freelance.score({**lead, "budget_min": 100_000, "budget_max": 100_000}, settings)
    fair, _ = freelance.score({**lead, "budget_min": 100, "budget_max": 300}, settings)
    assert bait < fair and any("looks unrealistic" in reason for reason in why)


def test_the_list_carries_previews_and_a_lead_opens_in_full(client):  # noqa: F811
    long = "We need a booking website. " * 60
    lead = client.post("/api/freelance/leads", json={"title": "Booking website for a salon", "platform": "Upwork", "description": long}).json()
    listed = next(item for item in client.get("/api/freelance?hidden=true").json()["leads"] if item["id"] == lead["id"])
    assert listed["description_cut"] and len(listed["description"]) == freelance.PREVIEW
    full = client.get(f"/api/freelance/leads/{lead['id']}").json()
    assert full["description"] == long.strip() and client.get("/api/freelance/leads/nope").status_code == 404
