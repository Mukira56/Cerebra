"""Progress notifications to the user's phone: ntfy push and/or the user's own Telegram bot.

A background loop reads new supervisor events (task state changes and order intake) and sends short
messages. Only the task's short title and state leave the computer, never code, diffs, logs or secrets.
"""
from __future__ import annotations

import secrets
import threading

import httpx
from sqlalchemy import select

from .models import Event, Metadata, Task, now
from .security import redact
from . import vault
from .network import LazyClient

KEY = "notify_settings"
CURSOR = "notify_cursor"
DEFAULT = {"ntfy_enabled": False, "ntfy_server": "https://ntfy.sh", "ntfy_topic": "", "telegram_enabled": False,
           "telegram_token": "", "telegram_chat_id": "", "only_orders": False}
# Task states worth a message, with a short plain-language line.
STATES = {
    "RUNNING": ("▶", "started work"),
    "AWAITING_APPROVAL": ("✋", "needs your decision"),
    "NEEDS_CHANGES": ("🔧", "tests or review found problems; repairing"),
    "COMPLETED": ("✅", "finished and merged"),
    "FAILED": ("❌", "stopped with a problem"),
    "BLOCKED": ("⏸", "is blocked"),
}


def load(session):
    row = session.get(Metadata, KEY)
    value = {**DEFAULT, **(row.value if row else {})}
    if not value["ntfy_topic"]:
        value["ntfy_topic"] = "cerebra-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:22].lower()
        _store(session, value)
    return value


def public(value):
    """Settings for the dashboard: the bot token is never returned, only whether one is saved."""
    return {**{k: v for k, v in value.items() if k != "telegram_token"}, "telegram_token_saved": bool(value.get("telegram_token"))}


def _store(session, value):
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))


def save(session, changes):
    value = load(session)
    for key in ("ntfy_enabled", "telegram_enabled", "only_orders"):
        if key in changes:
            value[key] = bool(changes[key])
    if changes.get("ntfy_server"):
        server = str(changes["ntfy_server"]).rstrip("/")
        if not server.startswith("https://"):
            raise ValueError("The ntfy server must use https://")
        value["ntfy_server"] = server
    if changes.get("new_ntfy_topic"):
        value["ntfy_topic"] = ""
    if changes.get("telegram_token"):
        token = str(changes["telegram_token"]).strip()
        if not __import__("re").fullmatch(r"\d{5,12}:[A-Za-z0-9_-]{30,50}", token):
            raise ValueError("That does not look like a Telegram bot token (from @BotFather)")
        value["telegram_token"], value["telegram_chat_id"] = vault.protect(token), ""
    if "telegram_chat_id" in changes and changes["telegram_chat_id"] is not None:
        value["telegram_chat_id"] = str(changes["telegram_chat_id"]).strip()[:32]
    _store(session, value)
    return load(session)


class Notifier:
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or LazyClient(timeout=20)
        self._stop = threading.Event()
        self._thread = None

    # ---- sending -----------------------------------------------------------------------------
    def send(self, title, text, settings=None, tags=""):
        with self.db.Session.begin() as session:
            settings = settings or load(session)
        title, text = redact(title)[:120], redact(text)[:1500]
        sent, problems = [], []
        if settings["ntfy_enabled"]:
            try:
                response = self.client.post(settings["ntfy_server"], json={"topic": settings["ntfy_topic"], "title": title, "message": text, "tags": [tags or "robot"]})
                response.raise_for_status()
                sent.append("ntfy")
            except Exception as exc:
                problems.append(f"ntfy: {redact(str(exc))[:200]}")
        if settings["telegram_enabled"] and settings["telegram_token"] and settings["telegram_chat_id"]:
            token = ""
            try:
                token = vault.unprotect(settings["telegram_token"])
                response = self.client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                            json={"chat_id": settings["telegram_chat_id"], "text": f"{title}\n{text}", "disable_web_page_preview": True})
                response.raise_for_status()
                sent.append("telegram")
            except Exception as exc:
                message = str(exc).replace(token, "[token]") if token else str(exc)
                problems.append("telegram: " + redact(message)[:200])
        return {"sent": sent, "problems": problems}

    def find_telegram_chat(self):
        """After the user sends any message to their bot, read the chat id from the bot's updates."""
        with self.db.Session.begin() as session:
            settings = load(session)
            if not settings["telegram_token"]:
                raise ValueError("Save your bot token first")
            token = vault.unprotect(settings["telegram_token"])
        try:
            response = self.client.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 20})
        except httpx.HTTPError as exc:
            raise ValueError("Could not reach Telegram: " + str(exc).replace(token, "[token]")[:200]) from None
        if response.status_code != 200:
            raise ValueError("Telegram did not accept the token. Check it in @BotFather.")
        chats = [update.get("message", {}).get("chat", {}) for update in response.json().get("result", [])]
        private = [chat for chat in chats if chat.get("type") == "private" and chat.get("id")]
        if not private:
            raise ValueError("Open your bot in Telegram, press Start or send it any message, then try again.")
        chat = private[-1]
        with self.db.Session.begin() as session:
            value = save(session, {"telegram_chat_id": str(chat["id"])})
        return {"chat_id": value["telegram_chat_id"], "name": " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) or chat.get("username", "")}

    # ---- watching ----------------------------------------------------------------------------
    def pending_messages(self):
        """New events worth telling the user about, since the last run. Advances the cursor."""
        self._task_refs = {}  # message index -> (task id, state): Telegram gets these with the reason and buttons instead
        with self.db.Session.begin() as session:
            settings = load(session)
            if not (settings["ntfy_enabled"] or settings["telegram_enabled"]):
                return settings, []
            cursor_row = session.get(Metadata, CURSOR)
            since = cursor_row.value.get("at") if cursor_row else None
            if since is None:  # first start: don't replay history
                session.add(Metadata(key=CURSOR, value={"at": now()}))
                return settings, []
            events = session.scalars(select(Event).where(Event.created_at > since, Event.kind.in_(["state", "order", "money", "freelance"])).order_by(Event.created_at).limit(50)).all()
            messages = []
            for event in events:
                task = session.get(Task, event.task_id) if event.task_id else None
                if settings["only_orders"] and event.kind == "state" and not (task and task.results.get("order")):
                    continue
                if event.kind == "freelance":
                    if (event.data or {}).get("notify") == "rare":  # counts only: ntfy topics travel through a public server
                        best = event.data.get("best") or {}
                        messages.append(("Cerebra · a rare chance", f"{int(event.data.get('count') or 0)} strong match(es) with few bids so far and a real budget"
                                         + (f" (best: score {int(best.get('score') or 0)}, {int(best.get('bids') or 0)} bids)" if best else "") + ". Apply soon: open Freelance in Cerebra.", "zap"))
                    elif (event.data or {}).get("notify") == "leads":
                        messages.append(("Cerebra · new freelance work", f"{int(event.data.get('count') or 0)} strong new match(es) for what you sell. Open Freelance in Cerebra.", "briefcase"))
                    continue
                if event.kind == "money":
                    # Money news, kept generic: ntfy topics travel through a public server, so no client names or amounts.
                    kind = (event.data or {}).get("notify")
                    if kind == "paid":
                        messages.append(("Cerebra · payment received", f"Invoice {str(event.data.get('number', ''))[:20]} was paid through Stripe. Open Money in Cerebra for details.", "moneybag"))
                    elif kind == "sold":
                        messages.append(("Cerebra · you made a sale", "A product sold through your Stripe link. Open Money in Cerebra for details.", "moneybag"))
                    elif kind == "plans":
                        messages.append(("Cerebra · invoices to send", f"{int(event.data.get('count') or 0)} recurring invoice(s) are ready. Open Money in Cerebra to send them.", "receipt"))
                    continue
                if event.kind == "order":
                    messages.append(("Cerebra · new order", "New intake recorded. Open Cerebra on your laptop to read it.", "package"))
                    continue
                state = (event.data or {}).get("to")
                if state not in STATES or task is None:
                    continue
                if state == "RUNNING" and (event.data or {}).get("from") not in {"READY", "PENDING", "BLOCKED"}:
                    continue  # repair rounds are covered by NEEDS_CHANGES
                symbol, words = STATES[state]
                title = " ".join(task.description.split())[:70]
                messages.append((f"{symbol} {title}", f"Task {task.id[:8]} {words}. Open Cerebra for details.", ""))
                self._task_refs[len(messages) - 1] = (task.id, state)
            if events:
                cursor_row.value = {"at": events[-1].created_at}
            return settings, messages

    def tick(self):
        settings, messages = self.pending_messages()
        for index, (title, text, tags) in enumerate(messages[:10]):
            if self._stop.is_set(): break
            ref, rich = self._task_refs.get(index), getattr(self, "rich_task", None)
            if ref and rich is not None and settings["telegram_enabled"]:
                try:
                    told = rich(*ref)  # the phone gets the reason and Yes/Resume buttons
                except Exception:  # noqa: BLE001 - fall back to the plain message
                    told = False
                if told:
                    if settings["ntfy_enabled"]:
                        self.send(title, text, {**settings, "telegram_enabled": False}, tags)
                    continue
            self.send(title, text, settings, tags)
        return len(messages)

    def start(self, interval=15):
        def loop():
            while not self._stop.wait(interval):
                try:
                    self.tick()
                except Exception:
                    pass  # A notification problem must never affect task execution.
        self._thread = threading.Thread(target=loop, name="cerebra-notify", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive(): self._thread.join(timeout=2)
