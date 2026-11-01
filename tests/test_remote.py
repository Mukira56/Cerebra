"""Cerebra from the owner's phone: their Telegram bot answers only their own chat, and one tap sends a drafted email.
Telegram, Gmail and the businesses' websites are simulated."""
import httpx

from ai_hq import vault
from ai_hq.models import Metadata, Prospect
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import setup

OWNER, STRANGER = 1001, 2002


class Telegram:
    def __init__(self):
        self.updates, self.said, self.answered, self.next_id = [], [], [], 1

    def message(self, chat, text):
        self.updates.append({"update_id": self.next_id, "message": {"chat": {"id": chat}, "text": text}})
        self.next_id += 1

    def tap(self, chat, data):
        self.updates.append({"update_id": self.next_id, "callback_query": {"id": f"q{self.next_id}", "data": data, "message": {"chat": {"id": chat}}}})
        self.next_id += 1

    def __call__(self, request):
        import json
        method, body = request.url.path.rsplit("/", 1)[-1], json.loads(request.content or b"{}")
        if method == "getUpdates":
            ready = [item for item in self.updates if item["update_id"] >= body.get("offset", 0)]
            return httpx.Response(200, json={"ok": True, "result": ready})
        if method == "sendMessage":
            self.said.append(body)
        if method == "answerCallbackQuery":
            self.answered.append(body["callback_query_id"])
        return httpx.Response(200, json={"ok": True, "result": {}})


def phone(client):  # noqa: F811
    state = client.app.state
    bot = Telegram()
    state.notifier.client = httpx.Client(transport=httpx.MockTransport(bot))
    with state.db.Session.begin() as session:
        session.add(Metadata(key="notify_settings", value={"telegram_enabled": True, "telegram_token": vault.protect("12345:" + "a" * 35),
                                                           "telegram_chat_id": str(OWNER), "ntfy_topic": "x"}))
    return bot


def test_only_the_owner_is_answered_and_the_status_is_real(client):  # noqa: F811
    setup(client)
    bot = phone(client)
    bot.message(STRANGER, "/status")
    bot.message(OWNER, "/status")
    bot.message(OWNER, "hello")
    client.app.state.remote.poll(wait=0)
    assert [item["chat_id"] for item in bot.said] == [str(OWNER), str(OWNER)]  # the stranger got nothing
    assert "Drafts ready to send: 0" in bot.said[0]["text"] and "/drafts" in bot.said[1]["text"]  # unknown words get the command list
    client.app.state.remote.poll(wait=0)
    assert len(bot.said) == 2  # each update is handled once


def test_one_tap_sends_a_drafted_email_and_skip_drops_one(client):  # noqa: F811
    state = setup(client)
    state.prospector.search("dentists", "Austin", "Texas")
    bot = phone(client)
    with state.db.Session.begin() as session:
        smile = session.query(Prospect).filter_by(name="Smile Dental").one()
        smile.opener = "Subject: Online booking\n\nHello Smile Dental, a short note about booking on your website."
        smile_id = smile.id
    bot.message(OWNER, "/drafts")
    state.remote.poll(wait=0)
    shown = bot.said[-1]
    assert "Smile Dental" in shown["text"] and "hello@smile-dental.example" in shown["text"]
    assert shown["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"send:{smile_id}"
    bot.tap(STRANGER, f"send:{smile_id}")  # someone else pressing it does nothing
    state.remote.poll(wait=0)
    assert state.outreach.gmail.sent == []
    bot.tap(OWNER, f"send:{smile_id}")
    state.remote.poll(wait=0)
    assert state.outreach.gmail.sent[0]["to"] == "hello@smile-dental.example" and "PO Box 100" in state.outreach.gmail.sent[0]["body"]
    assert any("Sent to Smile Dental" in item["text"] for item in bot.said) and bot.answered
    bot.tap(OWNER, f"send:{smile_id}")  # pressed twice: never sent twice
    state.remote.poll(wait=0)
    assert len(state.outreach.gmail.sent) == 1 and "already sent" in bot.said[-1]["text"]
    bot.message(OWNER, "/sent")
    state.remote.poll(wait=0)
    assert "Emailed 1 business" in bot.said[-1]["text"] and "Smile Dental: waiting" in bot.said[-1]["text"]


def test_without_a_bot_nothing_is_read(client):  # noqa: F811
    assert client.app.state.remote.poll(wait=0) == 0
