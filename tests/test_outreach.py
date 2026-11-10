"""Outreach to local businesses from the owner's Gmail: emails found with each business, drafts sent with one click, and the
automatic rounds (draft or send, follow-ups in the thread, replies, opt-outs and bounces). Gmail, the map and the websites
are simulated; nothing is sent anywhere."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ai_hq import outreach, prospects, vault
from ai_hq.agents import AgentResult
from ai_hq.models import Metadata, Prospect
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_prospects import OLD, osm

CONTACT = '<html><body><a href="mailto:hello@smile-dental.example">Email us</a> or info@wixpress.com</body></html>'


def site(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if request.url.host == "smile-dental.example" and request.url.path == "/contact":
        return httpx.Response(200, text=CONTACT)
    if request.url.host == "smile-dental.example":
        return httpx.Response(200, text=OLD.replace("<p>Call us!</p>", '<p>Call us!</p><a href="/contact">Contact</a>'))
    if request.url.host == "modern-teeth.example":
        return httpx.Response(200, text="<html><head><meta name='viewport' content='x'></head><body>Book an appointment<form></form>© 2026</body></html>")
    raise AssertionError(f"read {request.url}")


def mapped(request):
    """The map also lists an email for the business that has no website."""
    response = osm(request)
    if request.url.host == "overpass-api.de":
        data = response.json()
        for element in data["elements"]:
            if element["tags"]["name"] == "Hill Family Dentistry":
                element["tags"]["email"] = "Front@HillFamily.example"
        return httpx.Response(200, json=data)
    return response


class Gmail:
    """Sends nothing: records what would go out, and answers threads as told."""
    def __init__(self):
        self.sent, self.threads = [], {}

    def send(self, to, subject, body, thread_id=None, reply_to_message_id=None, attachments=None):
        number = len(self.sent) + 1
        self.sent.append({"to": to, "subject": subject, "body": body, "thread_id": thread_id, "reply_to": reply_to_message_id, "attachments": attachments or []})
        return {"id": f"m{number}", "thread_id": thread_id or f"t{number}", "message_id": f"<m{number}@mail.example>"}

    def thread(self, thread_id):
        return [{"id": "x", "from": "Owner <owner@gmail.example>", "subject": "", "snippet": "", "labels": ["SENT"]}] + self.threads.get(thread_id, [])


class Model(FixtureRegistry):
    def __init__(self):
        super().__init__()
        self.prompts = []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        if "follow-up" in prompt:
            return AgentResult(True, json.dumps({"body": "Just a quick note: people searching on their phones can't book with you yet."}))
        return AgentResult(True, json.dumps({"subject": "Online booking for Smile Dental", "body": "Hello Smile Dental, I looked at your website and noticed a few things."}))


def setup(client, can_send=True):  # noqa: F811
    from test_product_api import enable_agents
    state = client.app.state
    reader = prospects.Reader(httpx.Client(transport=httpx.MockTransport(site)), resolve=lambda host: host.endswith(".example"))
    state.prospector.client, state.prospector.reader, state.prospector.pause = httpx.Client(transport=httpx.MockTransport(mapped)), reader, 0
    state.outreach.gmail = Gmail()
    with state.db.Session.begin() as session:
        session.add(Metadata(key="gmail_oauth", value={"client_id": "1-a.apps.googleusercontent.com", "refresh_token": vault.protect("r"),
                                                       "email": "owner@gmail.example", "can_send": can_send}))
    client.put("/api/money/settings", json={"business_name": "Mukira Studio", "email": "owner@gmail.example", "address": "PO Box 100, Austin, TX 78701"})
    enable_agents(client)
    state.supervisor.registry = Model()
    return state


def test_every_business_found_comes_with_its_public_email(client):  # noqa: F811
    state = setup(client)
    result = state.prospector.search("dentists", "Austin", "Texas")
    assert result["emails"] == 2  # Smile Dental's from its contact page (the website builder's address ignored), Hill Family's from the map
    listed = {item["name"]: item for item in client.get("/api/prospects").json()["prospects"]}
    assert listed["Smile Dental"]["email"] == "hello@smile-dental.example" and listed["Smile Dental"]["email_checked"]
    assert listed["Hill Family Dentistry"]["email"] == "front@hillfamily.example"  # no website, but the map lists an email
    assert client.get(f"/api/prospects/{listed['Smile Dental']['id']}/email").json() == {"email": "hello@smile-dental.example"}  # not read again


def test_businesses_found_before_get_their_email_in_the_background(client):  # noqa: F811
    state = setup(client)
    with state.db.Session.begin() as session:
        session.add(Prospect(id="p1", name="Smile Dental", kind="dentists", city="Austin", state="Texas", website="http://smile-dental.example",
                             status="kept", facts=[{"key": "no_booking", "text": "No online booking", "seen": "http://smile-dental.example"}]))
    assert state.outreach.find_missing_emails() == {"checked": 1, "found": 1}
    assert client.get("/api/prospects").json()["prospects"][0]["email"] == "hello@smile-dental.example"
    assert "skipped" in state.outreach.find_missing_emails()  # each site is read once


def test_one_click_sends_the_edited_draft_keeps_the_legal_footer_and_never_twice(client):  # noqa: F811
    state = setup(client)
    state.prospector.search("dentists", "Austin", "Texas")
    smile = next(item for item in client.get("/api/prospects").json()["prospects"] if item["name"] == "Smile Dental")
    edited = "Subject: A faster way to book\n\nHi Smile Dental team, I noticed your site has no online booking. Happy to help."
    sent = client.post(f"/api/prospects/{smile['id']}/send", json={"to": smile["email"], "text": edited})
    assert sent.status_code == 200, sent.text
    assert client.get('/api/outreach/sent').json()[0]['next_at'] == ''  # follow-ups require a separate opt-in
    assert not next(job for job in client.get('/api/chief').json()['jobs'] if job['id'] == 'outreach')['enabled']
    mail = state.outreach.gmail.sent[0]
    assert mail["to"] == "hello@smile-dental.example" and mail["subject"] == "A faster way to book" and mail["body"].startswith("Hi Smile Dental team")
    assert "PO Box 100, Austin, TX 78701" in mail["body"] and "no thanks" in mail["body"]  # the owner removed the footer: it's put back (CAN-SPAM)
    assert next(item for item in client.get("/api/prospects").json()["prospects"] if item["id"] == smile["id"])["status"] == "contacted"
    again = client.post(f"/api/prospects/{smile['id']}/send", json={"to": smile["email"], "text": edited})
    assert again.status_code == 400 and "already emailed" in again.json()["detail"] and len(state.outreach.gmail.sent) == 1
    assert client.post(f"/api/prospects/{smile['id']}/send", json={"to": "", "text": edited}).status_code == 400
    assert "Subject" in client.post(f"/api/prospects/{smile['id']}/send", json={"to": "a@b.example", "text": "no subject line here at all"}).json()["detail"]


def test_sending_needs_gmail_permission_to_send(client):  # noqa: F811
    state = setup(client, can_send=False)
    with state.db.Session.begin() as session:
        session.add(Prospect(id="p1", name="Smile Dental", kind="dentists", city="Austin", state="Texas", status="kept"))
    refused = client.post("/api/prospects/p1/send", json={"to": "hello@smile-dental.example", "text": "Subject: Hi\n\nHello there, a short note about your site."})
    assert refused.status_code == 400 and "allow sending" in refused.json()["detail"] and state.outreach.gmail.sent == []


def test_prospect_writing_switches_to_codex_after_claude_limit_for_all_drafts(client):
    state = setup(client)
    calls = []
    class LimitedClaude(Model):
        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            calls.append(name)
            if name == 'claude':
                return AgentResult(False, '', error='Claude usage limit reached')
            return super().chat(name, prompt, workdir, model, cancel_event)
    state.supervisor.registry = LimitedClaude()

    def no_plan(name):  # the other client isn't proven to be on a plan, so nothing switches by itself
        raise ValueError('No API request or paid fallback was made.')
    state.prospect_writer.subscription_status = no_plan
    client.put('/api/models/hub', json={'routes': {'writing': 'account:claude'}}).raise_for_status()
    state.prospector.search('dentists', 'Austin', 'Texas')
    smile = next(p for p in client.get('/api/prospects').json()['prospects'] if p['name'] == 'Smile Dental')
    refused = client.post(f"/api/prospects/{smile['id']}/opener")
    assert refused.status_code == 400 and 'usage limit' in refused.json()['detail']
    saved = client.put('/api/outreach', json={'writing_provider': 'codex'})
    assert saved.status_code == 200 and saved.json()['writing_provider'] == 'codex'
    assert saved.json()['enabled'] is False
    assert not next(j for j in client.get('/api/chief').json()['jobs'] if j['id'] == 'outreach')['enabled']
    assert client.get('/api/outreach').json()['settings']['writing_provider'] == 'codex'
    drafted = client.post(f"/api/prospects/{smile['id']}/opener")
    assert drafted.status_code == 200 and calls[-1] == 'codex'
    assert client.post('/api/prospects/offer/dentists').status_code == 200 and calls[-1] == 'codex'
    sent = client.post(f"/api/prospects/{smile['id']}/send", json={'to': smile['email'], 'text': drafted.json()['opener'], 'follow_up': True})
    assert sent.status_code == 200
    with state.db.Session.begin() as session:
        row = session.query(outreach.Outbox).filter_by(prospect_id=smile['id'], stage='sent').one()
        row.next_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        outbox_id = row.id
        rules = outreach.settings(session)
    assert state.outreach.follow_up(1, rules) == 1 and calls[-1] == 'codex'
    with state.db.Session.begin() as session:
        session.get(outreach.Outbox, outbox_id).reply = {'snippet': 'Can you tell us more?'}
    assert client.post(f'/api/outreach/{outbox_id}/draft-answer').status_code == 200 and calls[-1] == 'codex'
    assert client.get('/api/models/hub').json()['routes']['writing'] == 'account:claude'
    client.put('/api/outreach', json={'writing_provider': 'auto'}).raise_for_status()
    assert client.post(f"/api/prospects/{smile['id']}/opener").status_code == 400 and calls[-1] == 'claude'


@pytest.mark.parametrize('provider', ['unknown', True, None, []])
def test_prospect_writing_choice_rejects_invalid_providers(client, provider):
    response = client.put('/api/outreach', json={'writing_provider': provider})
    assert response.status_code == 400
    assert client.get('/api/outreach').json()['settings']['writing_provider'] == 'auto'


def weekday(hour=10):
    return lambda: datetime(2026, 11, 4, hour, 0).astimezone()  # a Wednesday


def test_automatic_rounds_follow_up_stop_on_reply_and_honour_a_no(client):  # noqa: F811
    state = setup(client)
    state.prospector.search("dentists", "Austin", "Texas")
    robot = state.outreach
    robot.clock = weekday()
    client.put("/api/outreach", json={"enabled": True, "mode": "send", "per_day": 10, "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]})
    first = robot.tick()
    assert first["sent"] == 1 and robot.gmail.sent[0]["to"] == "hello@smile-dental.example" and "PO Box 100" in robot.gmail.sent[0]["body"]
    robot.clock = lambda: datetime(2026, 11, 8, 23, tzinfo=timezone.utc)  # Sunday-night follow-ups
    with state.db.Session.begin() as session:  # four days later
        row = session.query(outreach.Outbox).filter_by(stage="sent").one()
        row.next_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    robot.tick()
    follow = robot.gmail.sent[1]
    assert follow["subject"] == "Re: Online booking for Smile Dental" and follow["thread_id"] == "t1" and follow["reply_to"] == "<m1@mail.example>"
    assert "can't book with you yet" in follow["body"] and "PO Box 100" in follow["body"]
    robot.gmail.threads["t1"] = [{"id": "r", "from": "Smile Dental <hello@smile-dental.example>", "subject": "Re: Online booking",
                                  "snippet": "No thanks, please remove us from your list.", "labels": ["INBOX"]}]
    robot.tick()
    with state.db.Session() as session:
        assert session.query(outreach.Outbox).filter_by(email="hello@smile-dental.example").one().stage == "opted_out"
        assert "hello@smile-dental.example" in outreach.blocked(session)["emails"] and "smile-dental.example" in outreach.blocked(session)["domains"]
    smile = next(item for item in client.get("/api/prospects").json()["prospects"] if item["name"] == "Smile Dental")
    assert smile["status"] == "lost"
    refused = client.post(f"/api/prospects/{smile['id']}/send", json={"to": "office@smile-dental.example", "text": "Subject: Hi\n\nOne more try about your website."})
    assert refused.status_code == 400 and "won't write to it" in refused.json()["detail"]  # nobody at that business, ever again


@pytest.mark.parametrize("day", range(2, 9))  # Monday through Sunday, November 2026
@pytest.mark.parametrize("hour", [0, 20, 23])
def test_outreach_sends_every_day_and_hour_with_legacy_hours(client, day, hour):
    state = setup(client)
    state.prospector.search("dentists", "Austin", "Texas")
    client.put("/api/outreach", json={"enabled": True, "mode": "send", "per_day": 1,
               "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]})
    with state.db.Session.begin() as session:
        row = session.get(Metadata, outreach.KEY)
        row.value = {**row.value, "start_hour": 9, "end_hour": 17}
    state.outreach.clock = lambda: datetime(2026, 11, day, hour, tzinfo=timezone.utc)
    result = state.outreach.tick()
    assert result["sent"] == 1, result
    assert len(state.outreach.gmail.sent) == 1
    assert "Today's 1 emails are sent" in state.outreach.tick()["message"]
    settings = client.get("/api/outreach").json()["settings"]
    assert "start_hour" not in settings and "end_hour" not in settings


def test_a_reply_stops_follow_ups_and_tells_the_owner_and_out_of_office_does_not(client):  # noqa: F811
    state = setup(client)
    told = []
    state.outreach.notifier = type("Phone", (), {"send": lambda self, title, text, tags="": told.append(text)})()
    with state.db.Session.begin() as session:
        session.add(Prospect(id="p1", name="Smile Dental", kind="dentists", city="Austin", state="Texas", status="kept"))
    client.post("/api/prospects/p1/send", json={"to": "hello@smile-dental.example", "text": "Subject: Hi\n\nA short note about your website and booking."})
    robot = state.outreach
    robot.clock = weekday()
    robot.gmail.threads["t1"] = [{"id": "a", "from": "hello@smile-dental.example", "subject": "Automatic reply: out of office", "snippet": "Back Monday", "labels": ["INBOX"]}]
    robot.tick()
    with state.db.Session() as session:
        assert session.query(outreach.Outbox).one().stage == "sent"  # an out-of-office note isn't an answer
    robot.gmail.threads["t1"].append({"id": "b", "from": "hello@smile-dental.example", "subject": "Re: Hi", "snippet": "Sounds good, can you call me Thursday?", "labels": ["INBOX"]})
    robot.tick()
    with state.db.Session() as session:
        row = session.query(outreach.Outbox).one()
        assert row.stage == "replied" and row.next_at == "" and session.get(Prospect, "p1").status == "replied"
    assert told and "Thursday" in told[0]


def test_draft_mode_writes_emails_for_the_owner_and_sends_nothing(client):  # noqa: F811
    state = setup(client)
    state.prospector.search("dentists", "Austin", "Texas")
    client.put("/api/outreach", json={"enabled": True, "mode": "draft", "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]})
    assert next(job for job in client.get('/api/chief').json()['jobs'] if job['id'] == 'outreach')['enabled']
    state.outreach.clock = weekday()
    result = state.outreach.tick()
    assert result["drafted"] == 1 and state.outreach.gmail.sent == []
    smile = next(item for item in client.get("/api/prospects").json()["prospects"] if item["name"] == "Smile Dental")
    assert smile["opener"].startswith("Subject: Online booking for Smile Dental") and smile["email"] == "hello@smile-dental.example"  # ready for one click


def test_switching_on_needs_what_sending_needs(client):  # noqa: F811
    state = setup(client, can_send=False)
    refused = client.put("/api/outreach", json={"enabled": True, "mode": "send", "places": [{"city": "Austin", "state": "TX"}]})
    assert refused.status_code == 400 and "allow sending" in refused.json()["detail"]
    assert client.put("/api/outreach", json={"enabled": True, "mode": "draft", "places": [{"city": "Austin", "state": "TX"}]}).status_code == 200  # drafting needs no Gmail
    assert client.put("/api/outreach", json={"per_day": 500}).json()["per_day"] == outreach.MAX_PER_DAY
    assert state.registry.workers["outreach"].outward


def test_emailed_businesses_leave_worth_contacting_and_show_their_progress(client):  # noqa: F811
    state = setup(client)
    state.prospector.search("dentists", "Austin", "Texas")
    smile = next(item for item in client.get("/api/prospects").json()["prospects"] if item["name"] == "Smile Dental")
    before = client.get("/api/prospects").json()["counts"]["kept"]
    client.post(f"/api/prospects/{smile['id']}/send", json={"follow_up": True, "to": smile["email"], "text": "Subject: Online booking\n\nHello, a short note about booking on your website."})
    assert next(job for job in client.get('/api/chief').json()['jobs'] if job['id'] == 'outreach')['enabled']
    assert not client.get('/api/outreach').json()['settings']['enabled']  # no consent to new-business outreach
    with state.db.Session.begin() as session:  # even if its status is set back by hand, an emailed business isn't "worth contacting" again
        session.get(Prospect, smile["id"]).status = "kept"
    data = client.get("/api/prospects").json()
    assert data["counts"]["kept"] == before - 1 and next(item for item in data["prospects"] if item["id"] == smile["id"])["emailed"]
    sent = client.get("/api/outreach/sent").json()
    assert len(sent) == 1 and sent[0]["name"] == "Smile Dental" and sent[0]["email"] == "hello@smile-dental.example" and sent[0]["stage"] == "sent"
    assert sent[0]["emails"][0]["subject"] == "Online booking" and sent[0]["follow_ups"] == 0 and sent[0]["next_at"]  # a follow-up is planned
    state.outreach.clock = weekday()
    state.outreach.gmail.threads["t1"] = [{"id": "r", "from": "hello@smile-dental.example", "subject": "Re: Online booking", "snippet": "Yes, call me Friday.", "labels": ["INBOX"]}]
    state.outreach.tick()
    sent = client.get("/api/outreach/sent").json()
    assert sent[0]["stage"] == "replied" and sent[0]["reply"]["snippet"] == "Yes, call me Friday." and sent[0]["next_at"] == ""


def test_prospects_use_the_gmail_from_business_connections_and_say_when_it_cant_send(client):  # noqa: F811
    from ai_hq.prospects import footer
    state = setup(client, can_send=False)
    sender = client.get("/api/outreach").json()["sender"]
    assert sender == {"configured": True, "connected": True, "email": "owner@gmail.example", "can_send": False}  # read-only until Google allows sending
    client.put("/api/money/settings", json={"email": ""})
    with state.db.Session() as session:
        assert "owner@gmail.example" in footer(session)[0]  # no business email set: the Gmail it's sent from goes in the footer
    with state.db.Session.begin() as session:
        row = session.get(Metadata, "gmail_oauth")
        row.value = {**row.value, "can_send": True}
    assert client.get("/api/outreach").json()["sender"]["can_send"] is True


def subscription_setup(client, signed_in=('codex', 'claude')):  # noqa: F811
    """Claude is out of usage; the sign-in check answers from `signed_in`, as the official clients would."""
    state = setup(client)
    calls = []

    class LimitedClaude(Model):
        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            calls.append((name, model))
            if name == 'claude':
                return AgentResult(False, '', error='Claude usage limit reached.')
            return super().chat(name, prompt, workdir, model, cancel_event)

    def check(name):
        if name not in signed_in:
            raise ValueError(f'Sign in to {name} with your subscription')
        return True
    state.supervisor.registry = LimitedClaude()
    state.prospect_writer.subscription_status = check
    state.prospector.search('dentists', 'Austin', 'Texas')
    smile = next(p for p in client.get('/api/prospects').json()['prospects'] if p['name'] == 'Smile Dental')
    return state, calls, smile


def test_when_claude_runs_out_a_named_gpt_model_writes_on_the_subscription_with_no_api_key(client):  # noqa: F811
    state, calls, smile = subscription_setup(client)
    client.put('/api/models/hub', json={'routes': {'writing': 'account:claude'}}).raise_for_status()
    assert client.post(f"/api/prospects/{smile['id']}/opener").status_code == 200  # the other subscription took over by itself
    assert [name for name, _ in calls] == ['claude', 'codex']
    choice = 'catalog:codex:gpt-6.1-sol'
    saved = client.put('/api/outreach', json={'writing_model': choice, 'subscription_only': True})
    assert saved.status_code == 200 and saved.json()['subscription_only'] is True and saved.json()['enabled'] is False  # saving never starts outreach
    assert client.post(f"/api/prospects/{smile['id']}/opener").status_code == 200
    assert calls[-1] == ('codex', 'gpt-6.1-sol')  # that exact model, through the signed-in client
    assert client.get('/api/prospects/models').json()['selected'] == choice
    assert client.get('/api/models/hub').json()['routes']['writing'] == 'account:claude'  # other work keeps its own route


def test_subscription_choices_list_gpt_and_claude_models_and_no_api_models(client):  # noqa: F811
    setup(client)
    data = client.get('/api/prospects/models').json()
    ids = [item['id'] for item in data['subscription_options']]
    groups = {item['group'] for item in data['subscription_options']}
    assert {'ChatGPT / OpenAI subscription', 'Claude subscription'} <= groups
    assert any(item.startswith('catalog:codex:') for item in ids) and any(item.startswith('catalog:claude:') for item in ids)
    assert not any(item.startswith('api:') for item in ids)


def test_subscription_only_refuses_api_models_and_a_client_not_signed_in_to_a_subscription(client):  # noqa: F811
    state, calls, smile = subscription_setup(client, signed_in=('claude',))
    assert client.put('/api/outreach', json={'writing_model': 'api:openai:gpt-6.1-sol', 'subscription_only': True}).status_code == 400
    client.put('/api/outreach', json={'writing_model': 'catalog:codex:gpt-6.1-sol', 'subscription_only': True}).raise_for_status()
    refused = client.post(f"/api/prospects/{smile['id']}/opener")
    assert refused.status_code == 400 and 'Sign in' in refused.json()['detail'] and calls == []  # checked first: no model was called


def test_only_a_chatgpt_or_claude_ai_sign_in_counts_as_a_subscription(client):  # noqa: F811
    import pytest
    integrations = client.app.state.integrations
    answers = {'codex': {'signed_in': True, 'method': 'Logged in using ChatGPT'}, 'claude': {'signed_in': True, 'method': 'claude.ai'}}
    integrations.sign_in_status = lambda name: answers[name]
    assert integrations.require_subscription('codex') and integrations.require_subscription('claude')
    for name, status in (('codex', {'signed_in': True, 'method': 'Logged in using an API key'}), ('claude', {'signed_in': True, 'method': 'api_key'}),
                         ('claude', {'signed_in': False, 'method': 'claude.ai'}), ('codex', {'signed_in': True})):
        answers[name] = status
        with pytest.raises(ValueError, match='No API request'):
            integrations.require_subscription(name)
