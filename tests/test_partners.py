"""Company pitches: companies found from a starter list and Wikidata, their role addresses and application pages read from their
own websites, the pitch sent from the owner's Gmail within a daily number, one follow-up in the thread, and replies, opt-outs
and bounces. Wikidata, the websites and Gmail are simulated; nothing is sent anywhere."""
import time
from datetime import datetime, timedelta, timezone

import httpx

from ai_hq import partners, prospects
from ai_hq.models import PartnerCompany
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import setup

LINGUA_HOME = """<html><head><title>Lingua Data</title><meta name="description" content="Speech and text data for AI in 80 languages."></head><body>
<a href="/vendors">Become a vendor</a> <a href="/contact">Contact us</a> <a href="/careers">Careers</a> <a href="/privacy">Privacy</a>
<a href="https://twitter.com/lingua">Twitter</a> <p>Write to jane.doe@lingua.example or support@lingua.example, or our agency partners@other-agency.example</p></body></html>"""
PAGES = {
    ("www.lingua.example", "/"): LINGUA_HOME,
    ("www.lingua.example", "/vendors"): "<html><body><h1>Vendors</h1>Send your profile to vendors&#64;lingua.example <form></form></body></html>",
    ("www.lingua.example", "/contact"): '<html><body><a href="mailto:hello@lingua.example">hello@lingua.example</a></body></html>',
    ("www.lingua.example", "/careers"): "<html><body>Open roles</body></html>",
    ("forms.example", "/"): '<html><body><a href="/join-our-community">Join our linguist community</a></body></html>',
    ("forms.example", "/join-our-community"): "<html><body><form></form></body></html>",
    ("quiet.example", "/"): "<html><body>Hello</body></html>",
    ("hidden.example", "/contact-us"): '<html><body><a href="/cdn-cgi/l/email-protection#2f474a4343406f47464b4b4a41014a574e425f434a">[email&#160;protected]</a></body></html>',
}
PITCH = {"subject": "Language data for {company}", "body": "Hello {company} team,\n\nI provide translation and language data in two languages, "
         "reviewed by native speakers, for teams training AI models. I'd be glad to send a free sample.\n\nThank you for reading."}


def site(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if request.url.host == "blocked.example":
        return httpx.Response(403, text="no robots")
    text = PAGES.get((request.url.host, request.url.path))
    return httpx.Response(404, text="Not found") if text is None else httpx.Response(200, text=text)


def binding(item, name, site_, field):
    return {"item": {"value": f"http://www.wikidata.org/entity/{item}"}, "itemLabel": {"value": name}, "site": {"value": site_},
            "field": {"value": f"http://www.wikidata.org/entity/{field}"}}


WIKIDATA = [binding("Q1", "Lingua Data", "https://www.lingua.example/", "Q11660"), binding("Q1", "Lingua Data", "https://www.lingua.example/", "Q7553"),
            binding("Q2", "Forms Co", "https://forms.example", "Q11660"), binding("Q3", "Quiet AI", "https://quiet.example", "Q11660"),
            binding("Q4", "Blocked AI", "https://blocked.example", "Q2539"), binding("Q5", "Q5", "https://nolabel.example", "Q11660"),
            binding("Q6", "Wiki Only", "https://en.wikipedia.org/wiki/Wiki_Only", "Q11660")]
asked = []


def wikidata(request):
    asked.append(request.url)
    assert request.url.host == "query.wikidata.org" and "P452" in request.url.params["query"]
    return httpx.Response(200, json={"results": {"bindings": WIKIDATA}})


class Receiving:
    def can_receive(self, email):
        return not email.endswith("@dead.example")


def prepared(client, pitch=True):  # noqa: F811
    state = setup(client)
    robot = state.partners
    robot.reader = prospects.Reader(httpx.Client(transport=httpx.MockTransport(site)), resolve=lambda host: host.endswith(".example"))
    robot.client, robot.pause, robot.starter = httpx.Client(transport=httpx.MockTransport(wikidata)), 0, ()
    robot.gmail, robot.mail_check = state.outreach.gmail, Receiving()
    if pitch:
        client.put("/api/partners", json=PITCH).raise_for_status()
    return state, robot


def companies(client):  # noqa: F811
    return {item["name"]: item for item in client.get("/api/partners").json()["companies"]}


def found(client):  # noqa: F811
    state, robot = prepared(client)
    assert robot.discover() == 4  # no unnamed item, no Wikipedia page as a home page, each company once
    assert robot.research_some(10) == {"checked": 4, "found": 1}
    return state, robot


def test_the_pitch_must_be_ready_to_send_as_written(client):  # noqa: F811
    prepared(client, pitch=False)
    bad = client.put("/api/partners", json={"subject": "Hi {name}", "body": PITCH["body"] + " Regards, [Your name]"})
    assert bad.status_code == 400 and "{name} isn't filled in" in bad.json()["detail"] and "Replace [Your name]" in bad.json()["detail"]
    assert client.put("/api/partners", json={"subject": "Hi", "body": "Too short"}).status_code == 400
    assert client.put("/api/partners", json={"per_day": 500}).status_code == 400
    saved = client.put("/api/partners", json={**PITCH, "per_day": 5}).json()
    assert saved["subject"] == PITCH["subject"] and saved["per_day"] == 5 and saved["enabled"] is False


def test_companies_are_found_and_their_own_role_addresses_and_application_pages_read(client):  # noqa: F811
    found(client)
    listed = companies(client)
    lingua = listed["Lingua Data"]
    # Their vendor inbox beats hello@; a person's address, support@ and another firm's address are never used
    assert lingua["status"] == "ready" and lingua["email"] == "vendors@lingua.example" and set(lingua["emails"]) == {"vendors@lingua.example", "hello@lingua.example"}
    assert {page["label"] for page in lingua["pages"]} == {"Become a vendor", "Careers"} and lingua["about"] == "Speech and text data for AI in 80 languages."
    assert listed["Forms Co"]["status"] == "forms" and listed["Forms Co"]["pages"][0]["url"] == "https://forms.example/join-our-community"
    assert listed["Quiet AI"]["status"] == "none" and listed["Blocked AI"]["status"] == "unreadable" and "403" in listed["Blocked AI"]["notes"]
    assert set(listed) == {"Lingua Data", "Forms Co", "Quiet AI", "Blocked AI"}
    assert list(listed)[0] == "Lingua Data"  # ready to pitch comes first
    with client.app.state.db.Session() as session:
        assert session.query(PartnerCompany).filter_by(name="Lingua Data").one().rank == 1  # a language company is read before general AI


def test_the_find_button_works_in_the_background_and_reports_progress(client):  # noqa: F811
    prepared(client)
    assert "Looking" in client.post("/api/partners/find", json={}).json()["message"]
    for _ in range(100):
        search = client.get("/api/partners").json()["search"]
        if not search["running"]:
            break
        time.sleep(0.05)
    assert search["running"] is False and search["checked"] == 4 and search["found"] == 1 and search["message"].startswith("Done: 4 new companies")
    client.post("/api/partners/add", json={"name": "Manual Co", "website": "quiet.example"})  # already listed by its domain
    assert client.post("/api/partners/add", json={"name": "Manual Co", "website": "quiet.example"}).status_code == 400


def test_a_pitch_goes_out_from_gmail_with_the_owners_details_and_only_once(client):  # noqa: F811
    state, robot = found(client)
    preview = client.get("/api/partners").json()["preview"]
    assert preview["to"] == "vendors@lingua.example" and preview["subject"] == "Language data for Lingua Data"
    result = client.post("/api/partners/send-next", json={"count": 5}).json()
    assert result["sent"] == 1 and len(robot.gmail.sent) == 1
    mail = robot.gmail.sent[0]
    assert mail["to"] == "vendors@lingua.example" and mail["subject"] == "Language data for Lingua Data" and mail["body"].startswith("Hello Lingua Data team")
    assert "PO Box 100, Austin, TX 78701" in mail["body"] and "no thanks" in mail["body"]  # CAN-SPAM: address and opt-out in every email
    lingua = companies(client)["Lingua Data"]
    assert lingua["status"] == "sent" and lingua["next_at"] > datetime.now(timezone.utc).isoformat()
    again = client.post(f"/api/partners/{lingua['id']}/send", json={})
    assert again.status_code == 400 and "already emailed" in again.json()["detail"] and len(robot.gmail.sent) == 1


def test_a_company_with_only_a_form_can_be_emailed_at_an_address_the_owner_types_or_marked_applied(client):  # noqa: F811
    state, robot = found(client)
    forms = companies(client)["Forms Co"]
    assert client.post(f"/api/partners/{forms['id']}/send", json={}).status_code == 400  # no address: apply on their site
    sent = client.post(f"/api/partners/{forms['id']}/send", json={"to": "team@forms.example", "subject": "Hello Forms Co", "text": PITCH["body"]})
    assert sent.status_code == 200 and robot.gmail.sent[-1]["to"] == "team@forms.example" and "no thanks" in robot.gmail.sent[-1]["body"]
    quiet = companies(client)["Quiet AI"]
    assert client.patch(f"/api/partners/{quiet['id']}", json={"status": "applied", "notes": "Applied on their form"}).json()["status"] == "applied"
    dead = client.post(f"/api/partners/{quiet['id']}/send", json={"to": "x@dead.example", "subject": "Hi", "text": PITCH["body"]})
    assert dead.status_code == 400 and "can't receive email" in dead.json()["detail"] and robot.gmail.sent[-1]["to"] == "team@forms.example"


def test_sending_needs_gmail_the_postal_address_and_a_pitch(client):  # noqa: F811
    state, robot = prepared(client, pitch=False)
    refused = client.put("/api/partners", json={"enabled": True})
    assert refused.status_code == 400 and "Write your pitch" in refused.json()["detail"]
    client.put("/api/money/settings", json={"address": ""})
    client.put("/api/partners", json=PITCH).raise_for_status()
    refused = client.put("/api/partners", json={"enabled": True})
    assert refused.status_code == 400 and "postal address" in refused.json()["detail"]
    assert client.get("/api/partners").json()["settings"]["enabled"] is False


def test_switched_on_it_finds_reads_and_sends_within_the_daily_number_then_follows_up_once(client):  # noqa: F811
    state, robot = prepared(client)
    client.put("/api/partners", json={"enabled": True, "per_day": 1}).raise_for_status()
    job = next(item for item in client.get("/api/chief").json()["jobs"] if item["id"] == "partners")
    assert job["enabled"]
    first = robot.tick()
    assert first["sent"] == 1 and robot.gmail.sent[0]["to"] == "vendors@lingua.example"  # found, read and sent in one run
    assert "Today's pitches are sent" in robot.tick()["message"] and len(robot.gmail.sent) == 1
    with state.db.Session.begin() as session:  # a week later, no answer
        row = session.query(PartnerCompany).filter_by(name="Lingua Data").one()
        row.next_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        row.sent = [{**row.sent[0], "at": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}]
    assert robot.tick()["sent"] == 1
    follow = robot.gmail.sent[1]
    assert follow["subject"] == "Re: Language data for Lingua Data" and follow["thread_id"] == "t1" and follow["reply_to"] == "<m1@mail.example>"
    assert "Hello again Lingua Data team" in follow["body"] and "no thanks" in follow["body"]
    assert companies(client)["Lingua Data"]["status"] == "followed_up"
    robot.tick()
    assert sum(item["to"] == "vendors@lingua.example" for item in robot.gmail.sent) == 2  # never a second follow-up


def test_replies_stop_it_and_no_thanks_or_a_bounce_is_never_written_to_again(client):  # noqa: F811
    state, robot = found(client)
    robot.send_next(1)
    robot.gmail.threads["t1"] = [{"id": "o", "from": "vendors@lingua.example", "subject": "Automatic reply: out of office", "snippet": "Back Monday", "labels": ["INBOX"]}]
    robot.tick()
    assert companies(client)["Lingua Data"]["status"] == "sent"  # an out-of-office note isn't an answer
    robot.gmail.threads["t1"].append({"id": "r", "from": "Vendor Team <vendors@lingua.example>", "subject": "Re: Language data", "snippet": "Please send a sample.", "labels": ["INBOX"]})
    robot.tick()
    lingua = companies(client)["Lingua Data"]
    assert lingua["status"] == "replied" and lingua["reply"]["snippet"] == "Please send a sample." and lingua["next_at"] == ""
    forms = companies(client)["Forms Co"]
    client.post(f"/api/partners/{forms['id']}/send", json={"to": "team@forms.example", "subject": "Hello", "text": PITCH["body"]}).raise_for_status()
    robot.gmail.threads["t2"] = [{"id": "n", "from": "team@forms.example", "subject": "Re: Hello", "snippet": "Not interested, thanks.", "labels": ["INBOX"]}]
    robot.tick()
    assert companies(client)["Forms Co"]["status"] == "opted_out"
    quiet = companies(client)["Quiet AI"]
    again = client.post(f"/api/partners/{quiet['id']}/send", json={"to": "someone@forms.example", "subject": "Hi", "text": PITCH["body"]})
    assert again.status_code == 400 and "asked not to be contacted" in again.json()["detail"]  # nobody else at that company either


def test_finding_and_reading_never_send_anything(client):  # noqa: F811
    state, robot = found(client)
    assert robot.gmail.sent == [] and robot.tick() == {"skipped": "off"}


def test_role_addresses_only():
    assert partners.role_rank("partnerships@a.example") == 0 and partners.role_rank("vendor.management@a.example") == 1
    assert partners.role_rank("hello@a.example") == 3 and partners.role_rank("jane.doe@a.example") is None
    assert partners.role_rank("support@a.example") is None and partners.role_rank("privacy@a.example") is None
    assert partners.best_email(["info@a.example", "jane@a.example", "bd@a.example"]) == "bd@a.example"


def test_an_address_the_site_hides_from_robots_but_shows_visitors_is_found_and_slow_pages_():
    reader = prospects.Reader(httpx.Client(transport=httpx.MockTransport(lambda request: site(request) if request.url.path != "/" else
                                                                          httpx.Response(200, text="<html><body>Nothing linked</body></html>"))),
                              resolve=lambda host: host.endswith(".example"))
    seen = partners.read_company(reader, "https://hidden.example", pause=0)
    assert seen["email"] == "hello@hidden.example"  # no contact link: the usual contact address was tried
    assert partners.hidden_emails('<a href="/cdn-cgi/l/email-protection#2f474a4343406f5e5a464a5b014a574e425f434a">x</a>') == ["hello@quiet.example"]


def test_short_role_words_never_match_a_persons_name_and_procurement_is_kept():
    assert partners.role_rank("procurement@a.example") == 1 and partners.role_rank("pr@a.example") is None
    assert partners.role_rank("hi@a.example") == 3 and partners.role_rank("hilda@a.example") is None
    assert partners.role_rank("vmorris@a.example") is None and partners.role_rank("hr@a.example") == 4 and partners.role_rank("hrobinson@a.example") is None
    assert partners.role_rank("dataprotection@a.example") is None and partners.role_rank("data@a.example") == 1


def test_switched_off_or_in_review_mode_no_follow_up_goes_on_its_own_but_replies_are_read(client):  # noqa: F811
    state, robot = found(client)
    robot.send_next(1)
    with state.db.Session.begin() as session:
        session.query(PartnerCompany).filter_by(name="Lingua Data").one().next_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    robot.tick()
    client.put("/api/partners", json={"enabled": True, "mode": "review"}).raise_for_status()
    robot.tick()
    assert len(robot.gmail.sent) == 1  # off, then review only: the follow-up waits for the owner
    with client.app.state.db.Session.begin() as session:  # an owner whose Gmail address wasn't saved still sees replies
        from ai_hq import gmail as gmail_module
        value = gmail_module.load(session)
        gmail_module._store(session, {**value, "email": ""})
    robot.gmail.threads["t1"] = [{"id": "r", "from": "vendors@lingua.example", "subject": "Re: Language data", "snippet": "Tell us more.", "labels": ["INBOX"]}]
    robot.tick()
    assert companies(client)["Lingua Data"]["status"] == "replied"


def test_an_unreadable_thread_doesnt_stop_the_other_replies(client):  # noqa: F811
    state, robot = found(client)
    robot.send_next(1)
    forms = companies(client)["Forms Co"]
    client.post(f"/api/partners/{forms['id']}/send", json={"to": "team@forms.example", "subject": "Hello", "text": PITCH["body"]}).raise_for_status()
    robot.gmail.threads["t2"] = [{"id": "r", "from": "team@forms.example", "subject": "Re: Hello", "snippet": "Yes, send a sample.", "labels": ["INBOX"]}]
    real = robot.gmail.thread
    robot.gmail.thread = lambda thread_id: (_ for _ in ()).throw(ValueError("Gmail returned 404")) if thread_id == "t1" else real(thread_id)
    robot.tick()
    assert companies(client)["Forms Co"]["status"] == "replied" and companies(client)["Lingua Data"]["status"] == "sent"


def test_a_sent_email_counts_as_sent_even_when_gmail_cant_say_its_message_id(client):  # noqa: F811
    from ai_hq import gmail as gmail_module
    posted = []

    def google(request):
        if request.method == "POST":
            posted.append(request.url.path)
            return httpx.Response(200, json={"id": "abc", "threadId": "t9"})
        return httpx.Response(500, json={})
    db = client.app.state.db
    with db.Session.begin() as session:
        gmail_module._store(session, {"client_id": "1-a.apps.googleusercontent.com", "refresh_token": "x", "email": "owner@gmail.example", "can_send": True})
    mailbox = gmail_module.Gmail(db, "http://127.0.0.1/callback", client=httpx.Client(transport=httpx.MockTransport(google)))
    mailbox._access = ("token", time.monotonic() + 600)
    assert mailbox.send("team@forms.example", "Hello", "A short note.") == {"id": "abc", "thread_id": "t9", "message_id": ""}
    assert posted == ["/gmail/v1/users/me/messages/send"]
