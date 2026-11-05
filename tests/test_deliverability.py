"""Domains that can't receive mail are skipped, and too many bounces pause automatic sending until the owner resumes it.
DNS, Gmail and the model are simulated."""
import httpx

from ai_hq import deliverability
from ai_hq.deliverability import MailCheck
from ai_hq.models import Event, Outbox, Prospect
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import setup

ZONES = {
    "good.com": {"MX": {"Status": 0, "Answer": [{"type": 15, "data": "10 mail.good.com."}]}},
    "nomx.com": {"MX": {"Status": 0}, "A": {"Status": 0, "Answer": [{"type": 1, "data": "192.0.2.1"}]}},
    "v6.com": {"MX": {"Status": 0}, "A": {"Status": 0}, "AAAA": {"Status": 0, "Answer": [{"type": 28, "data": "2001:db8::1"}]}},
    "nullmx.com": {"MX": {"Status": 0, "Answer": [{"type": 15, "data": "0 ."}]}},
    "empty.com": {"MX": {"Status": 0}, "A": {"Status": 0}, "AAAA": {"Status": 0}},
    "flaky.com": {"MX": {"Status": 2}},
    "cname.com": {"MX": {"Status": 0, "Answer": [{"type": 5, "data": "other.com."}, {"type": 15, "data": "5 mx.other.com."}]}},
}


class Dns:
    def __init__(self):
        self.asked = []

    def __call__(self, request):
        name, kind = request.url.params["name"], request.url.params["type"]
        self.asked.append((name, kind))
        if name == "broken.com":
            return httpx.Response(500)
        if name == "garbled.com":
            return httpx.Response(200, content=b"not json")
        if name == "timeout.com":
            raise httpx.ConnectTimeout("no answer", request=request)
        return httpx.Response(200, json=ZONES.get(name, {}).get(kind, {"Status": 3}))


def checker():
    dns = Dns()
    return MailCheck(httpx.Client(transport=httpx.MockTransport(dns))), dns


def test_what_a_domain_can_receive():
    check, dns = checker()
    for domain, answer in [("good.com", "ok"), ("cname.com", "ok"), ("nomx.com", "ok"), ("v6.com", "ok"), ("GOOD.com.", "ok"),
                           ("missing.com", "dead"), ("nullmx.com", "dead"), ("empty.com", "dead")]:
        assert check.domain(domain) == answer, domain
    assert check.can_receive("hi@good.com") and not check.can_receive("hi@missing.com")


def test_a_failed_lookup_never_blocks_an_email():
    check, _ = checker()
    for domain in ("flaky.com", "broken.com", "garbled.com", "timeout.com"):
        assert check.domain(domain) == "unknown", domain
        assert check.can_receive(f"hi@{domain}")


def test_reserved_names_and_blanks_are_never_looked_up():
    check, dns = checker()
    assert check.domain("smile-dental.example") == check.domain("x.test") == check.domain("") == "unknown"
    assert dns.asked == []


def test_only_the_domain_is_sent_to_the_resolver():
    check, dns = checker()
    check.can_receive("private.person@good.com")
    assert dns.asked == [("good.com", "MX")]


def business(state, key, email=""):
    site = f"http://{email.rsplit('@', 1)[1]}" if email else f"http://{key}.example"  # a business's address is at its own site
    with state.db.Session.begin() as session:
        session.add(Prospect(id=key, name=f"Business {key}", kind="dentists", city="Austin", state="Texas", website=site, status="kept",
                             facts=[{"key": "no_booking", "text": "No online booking", "seen": site}],
                             opener="Subject: Online booking\n\nHello, a short note about booking on your website." if email else ""))
        if email:
            session.add(Outbox(prospect_id=key, email=email, stage="draft"))


def history(state, sent, bounced, at="2026-11-01T10:00:00+00:00"):
    """Emails already sent, the first `bounced` of them bounced."""
    with state.db.Session.begin() as session:
        for number in range(sent):
            key = f"old{at[:10]}{number}"
            session.add(Prospect(id=key, name=key, kind="dentists", city="Austin", state="Texas", status="lost" if number < bounced else "contacted"))
            session.add(Outbox(prospect_id=key, email=f"a{number}@{key}.example", stage="bounced" if number < bounced else "done",
                               emails=[{"at": at, "subject": "s", "body": "b", "message_id": f"<{key}>"}]))


def send_mode(client):  # noqa: F811
    assert client.put("/api/outreach", json={"enabled": True, "mode": "send", "per_day": 10, "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]}).status_code == 200


def test_the_one_click_send_refuses_a_dead_domain_and_says_why(client):  # noqa: F811
    state = setup(client)
    state.outreach.mail_check = checker()[0]
    business(state, "p1")
    answer = client.post("/api/prospects/p1/send", json={"to": "hello@missing.com", "text": "Subject: Hi\n\nHello, a short note about booking on your website."})
    assert answer.status_code == 400 and "can't receive email" in answer.json()["detail"] and state.outreach.gmail.sent == []
    assert client.post("/api/prospects/p1/send", json={"to": "hello@good.com", "text": "Subject: Hi\n\nHello, a short note about booking on your website."}).status_code == 200
    assert [item["to"] for item in state.outreach.gmail.sent] == ["hello@good.com"]


def test_automatic_sending_skips_a_dead_domain_and_carries_on_with_the_next(client):  # noqa: F811
    state = setup(client)
    state.outreach.mail_check = checker()[0]
    business(state, "dead", "hello@missing.com")
    business(state, "live", "hello@good.com")
    send_mode(client)
    assert state.outreach.tick()["sent"] == 1  # the dead one doesn't stop the round
    assert [item["to"] for item in state.outreach.gmail.sent] == ["hello@good.com"]
    with state.db.Session() as session:
        assert session.query(Outbox).filter_by(prospect_id="dead").one().stage == "skipped"
        assert any("can't receive email" in item.message for item in session.query(Event).all())
    state.outreach.tick()
    assert "hello@missing.com" not in [item["to"] for item in state.outreach.gmail.sent]  # never tried again


def test_one_or_two_bounces_never_pause_anything(client):  # noqa: F811
    state = setup(client)
    history(state, 5, 2)
    with state.db.Session() as session:
        health = deliverability.health(session)
    assert health["bounced"] == 2 and health["sent"] == 5 and health["paused"] is False and health["reason"] == ""


def test_three_in_the_last_hundred_pause_but_older_bounces_age_out(client):  # noqa: F811
    state = setup(client)
    history(state, 100, 3)
    with state.db.Session() as session:
        health = deliverability.health(session)
    assert health["sent"] == 100 and health["rate"] == 0.03 and health["paused"] is True
    history(state, 100, 0, at="2026-11-02T10:00:00+00:00")  # a hundred good emails since
    with state.db.Session() as session:
        health = deliverability.health(session)
    assert health["sent"] == 100 and health["bounced"] == 0 and health["paused"] is False


def test_drafts_and_unsent_rows_do_not_count_as_sent(client):  # noqa: F811
    state = setup(client)
    business(state, "p1", "hello@good.com")
    history(state, 3, 3)
    with state.db.Session() as session:
        health = deliverability.health(session)
    assert health["sent"] == 3 and health["paused"] is True


def test_too_many_bounces_pause_sending_but_replies_are_still_read_and_the_owner_is_told_once(client):  # noqa: F811
    state = setup(client)
    told = []

    class Phone:
        def send(self, title, text, tags=""):
            told.append(title)

    state.outreach.notifier = Phone()
    business(state, "p1", "hello@smile-dental.example")
    history(state, 10, 3)
    with state.db.Session.begin() as session:  # a reply is waiting in a thread from before the pause
        session.add(Prospect(id="p2", name="Hill Family", kind="dentists", city="Austin", state="Texas", status="contacted"))
        session.add(Outbox(prospect_id="p2", email="front@hillfamily.example", stage="sent", thread_id="t9",
                           emails=[{"at": "2026-11-01T09:00:00+00:00", "subject": "s", "body": "b", "message_id": "<x>"}]))
    state.outreach.gmail.threads["t9"] = [{"id": "r1", "from": "front@hillfamily.example", "subject": "Re: s", "message_id": "<r1>", "snippet": "Sounds good, call me Tuesday.", "labels": ["INBOX"]}]
    send_mode(client)
    result = state.outreach.tick()
    assert result["paused"] is True and result["sent"] == 0 and result["replies"] == 1 and state.outreach.gmail.sent == []
    overview = client.get("/api/outreach").json()
    assert overview["health"]["paused"] is True and "3 of your last 11 emails bounced" in overview["health"]["reason"]
    assert overview["status"]["state"] == "waiting"
    state.outreach.tick()
    assert told.count("Automatic emails paused") == 1 and told.count("A business replied") == 1


def test_a_pause_stops_follow_ups_too(client):  # noqa: F811
    state = setup(client)
    history(state, 3, 3)
    with state.db.Session.begin() as session:
        session.add(Prospect(id="p3", name="Due", kind="dentists", city="Austin", state="Texas", status="contacted"))
        session.add(Outbox(prospect_id="p3", email="due@due.example", stage="sent", thread_id="t3", next_at="2026-01-01T00:00:00+00:00",
                           emails=[{"at": "2026-10-01T09:00:00+00:00", "subject": "s", "body": "b", "message_id": "<y>"}]))
    send_mode(client)
    assert state.outreach.tick()["paused"] is True and state.outreach.gmail.sent == []


def test_while_paused_the_owner_can_still_send_by_hand(client):  # noqa: F811
    state = setup(client)
    history(state, 3, 3)
    business(state, "p1")
    assert client.post("/api/prospects/p1/send", json={"to": "hello@smile-dental.example", "text": "Subject: Hi\n\nHello, a short note about booking on your website."}).status_code == 200
    assert len(state.outreach.gmail.sent) == 1


def test_draft_mode_keeps_drafting_while_paused(client):  # noqa: F811
    state = setup(client)
    history(state, 3, 3)
    state.prospector.search("dentists", "Austin", "Texas")
    client.put("/api/outreach", json={"enabled": True, "mode": "draft", "per_day": 10, "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]})
    result = state.outreach.tick()
    assert result["paused"] is True and result["drafted"] >= 1 and state.outreach.gmail.sent == []


def test_resuming_counts_only_what_is_sent_afterwards_and_a_new_pause_is_told_again(client):  # noqa: F811
    state = setup(client)
    told = []

    class Phone:
        def send(self, title, text, tags=""):
            told.append(title)

    state.outreach.notifier = Phone()
    history(state, 3, 3)
    business(state, "p1", "hello@smile-dental.example")
    send_mode(client)
    assert state.outreach.tick()["paused"] is True
    assert client.post("/api/outreach/resume").status_code == 200
    assert client.get("/api/outreach").json()["health"] == {"sent": 0, "bounced": 0, "rate": 0.0, "paused": False, "reason": ""}
    assert state.outreach.tick()["sent"] == 1
    history(state, 3, 3, at="2099-01-01T10:00:00+00:00")
    assert state.outreach.tick()["paused"] is True
    assert told.count("Automatic emails paused") == 2


def days_ago(number):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=number, hours=1)).isoformat()


def test_a_new_sender_builds_up_and_then_the_owners_number_applies(client):  # noqa: F811
    state = setup(client)
    with state.db.Session() as session:
        assert deliverability.daily_limit(session, 40) == 10  # nothing sent yet
        assert deliverability.daily_limit(session, 5) == 5  # never more than the owner asked for
    for age, limit in [(1, 10), (6, 10), (7, 20), (13, 20), (14, 30), (20, 30), (21, 40)]:
        with state.db.Session.begin() as session:
            session.query(Outbox).delete()
        history(state, 1, 0, at=days_ago(age))
        with state.db.Session() as session:
            assert deliverability.daily_limit(session, 40) == limit, age


def test_the_oldest_email_sets_the_age_and_a_bad_date_stays_safe(client):  # noqa: F811
    state = setup(client)
    history(state, 1, 0, at=days_ago(30))
    history(state, 1, 0, at=days_ago(1))
    with state.db.Session() as session:
        assert deliverability.daily_limit(session, 40) == 40
    with state.db.Session.begin() as session:
        session.query(Outbox).delete()
    history(state, 1, 0, at="not a date")
    with state.db.Session() as session:
        assert deliverability.daily_limit(session, 40) == 10


def test_automatic_sending_stops_at_the_build_up_limit_but_the_owner_can_still_send(client):  # noqa: F811
    state = setup(client)
    history(state, 10, 0, at=days_ago(0))  # ten already went out in the last day
    business(state, "p1", "hello@smile-dental.example")
    client.put("/api/outreach", json={"enabled": True, "mode": "send", "per_day": 40, "places": [{"city": "Austin", "state": "Texas"}], "kinds": ["dentists"]})
    assert "Today's 10 emails are sent" in state.outreach.tick()["message"] and state.outreach.gmail.sent == []
    overview = client.get("/api/outreach").json()
    assert overview["limit"] == 10 and overview["settings"]["per_day"] == 40  # the owner's choice is kept for later
    business(state, "p2")
    assert client.post("/api/prospects/p2/send", json={"to": "front@hillfamily.example", "text": "Subject: Hi\n\nHello, a short note about booking on your website."}).status_code == 200
