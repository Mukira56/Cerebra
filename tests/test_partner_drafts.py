"""Ready emails: every pitch ready to go, written out in full for the owner to read, and sent with one click, only the
ones they kept and within the day's number. Gmail and the writing model are simulated; nothing is sent anywhere."""
from ai_hq import partners
from ai_hq.models import PartnerCompany
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_partner_tailoring import PITCH, Writer, company, ready


def test_ready_emails_are_shown_in_full_with_their_own_paragraph(client):  # noqa: F811
    state, robot = ready(client)
    with client.app.state.db.Session.begin() as session:
        for name in ("Voice Co", "Text Co"):
            session.add(PartnerCompany(name=name, website=f"https://{name.split()[0].lower()}.example", domain=f"{name.split()[0].lower()}.example",
                                       status="ready", email=f"partners@{name.split()[0].lower()}.example", personal=f"I read about {name}'s new languages.",
                                       checked_at="2026-01-01"))
        session.add(PartnerCompany(name="Waiting Co", website="https://waiting.example", domain="waiting.example", status="ready",
                                   email="partners@waiting.example", checked_at="2026-01-02"))
    drafts = client.get("/api/partners/drafts").json()
    assert [item["name"] for item in drafts["drafts"]] == ["Voice Co", "Text Co"] and drafts["waiting_to_be_written"] == 1
    first = drafts["drafts"][0]
    assert first["subject"] == "Language data for Voice Co" and "I read about Voice Co's new languages." in first["body"]
    assert "no thanks" in first["body"]  # the owner's details and the opt-out line, as it will go out
    assert client.get("/api/partners").json()["drafts_ready"] == 2
    assert robot.gmail.sent == []  # looking sends nothing


def test_one_click_sends_only_the_ticked_emails(client):  # noqa: F811
    state, robot = ready(client)
    robot.write = Writer()
    keep, skip, other = (company(client, name, f"{name.split()[0].lower()}.example") for name in ("Voice Co", "Text Co", "Third Co"))
    assert robot.prepare(5)["written"] == 3
    result = client.post("/api/partners/send-drafts", json={"ids": [keep, other]}).json()
    assert result["sent"] == 2 and "Sent 2 emails" in result["message"]
    assert [mail["to"] for mail in robot.gmail.sent] == ["partners@voice.example", "partners@third.example"]
    listed = {item["id"]: item["status"] for item in client.get("/api/partners").json()["companies"]}
    assert listed[keep] == listed[other] == "sent" and listed[skip] == "ready"  # the unticked one is still in line


def test_the_day_s_number_is_kept_and_the_rest_wait(client):  # noqa: F811
    state, robot = ready(client, {"per_day": 1})
    robot.write = Writer()
    ids = [company(client, f"Co {number}", f"co{number}.example") for number in range(3)]
    robot.prepare(5)
    result = robot.send_drafts(ids)
    assert result["sent"] == 1 and "2 wait for tomorrow" in result["message"] and len(robot.gmail.sent) == 1
    assert robot.send_drafts(ids[1:])["message"].startswith("Today's emails are sent")


def test_nothing_ticked_sends_nothing(client):  # noqa: F811
    state, robot = ready(client)
    refused = client.post("/api/partners/send-drafts", json={"ids": []})
    assert refused.status_code == 400 and "Tick the emails" in refused.json()["detail"]


def test_writing_the_next_emails_says_what_is_still_being_researched(client):  # noqa: F811
    state, robot = ready(client)
    robot.write = Writer()
    company(client, "Voice Co", "voice.example")
    with client.app.state.db.Session.begin() as session:
        session.add(PartnerCompany(name="New Co", website="https://new.example", domain="new.example", status="ready", email="partners@new.example"))
    result = client.post("/api/partners/prepare", json={"count": 5}).json()
    assert result["written"] == 1 and "1 more are still being researched" in result["message"]
    assert partners.PERSONAL_CHARS and PITCH["personalize"] is True
