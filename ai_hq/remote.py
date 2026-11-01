"""Run Cerebra from your phone: the owner's own Telegram bot, two-way.

The bot already set up for progress notifications (ai_hq/notify.py) now also listens. Only messages from the owner's
saved chat are read: anyone else who finds the bot is ignored without a reply. Commands answer from Cerebra's own
records, and the buttons act on them:
  /status    what's waiting and what's working today
  /drafts    the next drafted business email, with Send, Skip and Next buttons (Send goes from the owner's Gmail)
  /replies   businesses that answered, newest first
  /sent      where the emailed businesses stand
  /jobs      the best new freelance matches: write a proposal, open the post, or hide (and bid, on Freelancer.com)
  /books     KDP books ready to upload
  /money     earned this month and what's owed
  /outreach  run a round of outreach now (find, draft or send, follow up, check replies)
Updates are read by long polling (no public web address needed), one at a time, with the offset kept so nothing is
handled twice. A failure here never touches the rest of Cerebra.
"""
from __future__ import annotations

import threading

from sqlalchemy import select

from . import notify, vault
from .models import Book, Metadata, Prospect, now

OFFSET = "telegram_offset"
HELP = ("Cerebra on your phone:\n"
        "/status - what's waiting and what's working\n"
        "/drafts - drafted business emails: send or skip with one tap\n"
        "/replies - businesses that answered\n"
        "/sent - where emailed businesses stand\n"
        "/jobs - the best new freelance jobs: proposal with one tap\n"
        "/books - KDP books ready to upload\n"
        "/money - this month's money\n"
        "/outreach - run a round of outreach now")


class Remote:
    def __init__(self, db, notifier, outreach, drafter=None, bidder=None):
        self.db, self.notifier, self.outreach, self.drafter, self.bidder = db, notifier, outreach, drafter, bidder
        self._stop, self._thread = threading.Event(), None

    # ---- Telegram ----
    def _settings(self):
        with self.db.Session.begin() as session:
            value = notify.load(session)
        if not (value["telegram_enabled"] and value["telegram_token"] and value["telegram_chat_id"]):
            return None
        return {"token": vault.unprotect(value["telegram_token"]), "chat": str(value["telegram_chat_id"])}

    def _call(self, settings, method, **payload):
        response = self.notifier.client.post(f"https://api.telegram.org/bot{settings['token']}/{method}", json=payload, timeout=40)
        return response.json() if response.status_code == 200 else {}

    def say(self, settings, text, buttons=None):
        payload = {"chat_id": settings["chat"], "text": text[:4000], "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": [[{"text": label, "url": data} if data.startswith("https://") else {"text": label, "callback_data": data}
                                                            for label, data in row] for row in buttons]}
        return self._call(settings, "sendMessage", **payload)

    def poll(self, wait=25):
        """Read and handle new updates once. Returns how many were handled."""
        settings = self._settings()
        if settings is None:
            return 0
        with self.db.Session() as session:
            row = session.get(Metadata, OFFSET)
            offset = int((row.value or {}).get("next", 0)) if row else 0
        data = self._call(settings, "getUpdates", offset=offset, timeout=wait, allowed_updates=["message", "callback_query"])
        handled = 0
        for update in data.get("result") or []:
            offset = max(offset, int(update["update_id"]) + 1)
            with self.db.Session.begin() as session:  # remembered first: an update is never handled twice
                row = session.get(Metadata, OFFSET)
                if row is None:
                    session.add(Metadata(key=OFFSET, value={"next": offset}))
                else:
                    row.value = {"next": offset, "at": now()}
            try:
                handled += self.handle(settings, update)
            except Exception as exc:  # noqa: BLE001 - say what went wrong, keep listening
                self.say(settings, f"That didn't work: {str(exc)[:300]}")
        return handled

    def handle(self, settings, update):
        if "callback_query" in update:
            query = update["callback_query"]
            if str((query.get("message") or {}).get("chat", {}).get("id")) != settings["chat"]:
                return 0  # not the owner's chat: ignored
            self._call(settings, "answerCallbackQuery", callback_query_id=query.get("id"))
            action, _, value = str(query.get("data") or "").partition(":")
            if action == "send":
                return self.send_draft(settings, value)
            if action == "skip":
                return self.skip_draft(settings, value)
            if action == "next":
                return self.show_draft(settings, after=value)
            if action == "ans":
                return self.send_reply_answer(settings, value)
            if action == "prop":
                return self.write_proposal(settings, value)
            if action == "hide":
                return self.hide_job(settings, value)
            if action == "bid":
                return self.send_bid(settings, value)
            if action == "redo":
                self.outreach.draft_answer(value)
                return self.replies(settings)
            return 0
        message = update.get("message") or {}
        if str(message.get("chat", {}).get("id")) != settings["chat"]:
            return 0  # strangers get no reply at all
        command = str(message.get("text") or "").strip().split()[0].lower().split("@")[0] if message.get("text") else ""
        handlers = {"/status": self.status, "/drafts": self.show_draft, "/replies": self.replies, "/sent": self.sent, "/jobs": self.jobs, "/books": self.books,
                    "/money": self.money, "/outreach": self.run_outreach}
        handler = handlers.get(command)
        if handler is None:
            self.say(settings, HELP)
            return 1
        handler(settings)
        return 1

    # ---- what the commands answer ----
    def _drafts(self, session):
        from .models import Outbox
        from .outreach import SENT_STAGES, emails
        emailed = set(session.scalars(select(Outbox.prospect_id).where(Outbox.stage.in_(SENT_STAGES))).all())
        rows = [row for row in session.scalars(select(Prospect).where(Prospect.status == "kept").order_by(Prospect.updated_at.desc())).all()
                if row.id not in emailed and (row.opener or "").lower().startswith("subject:")]
        found = emails(session, [row.id for row in rows])
        return [(row, found.get(row.id, "")) for row in rows if found.get(row.id)]

    def status(self, settings):
        from .outreach import sent as sent_list
        with self.db.Session() as session:
            drafts, sent = self._drafts(session), sent_list(session)
            books = session.scalars(select(Book).where(Book.status == "files_ready")).all()
        waiting = sum(1 for item in sent if item["stage"] in {"sent", "followed_up", "done"})
        replied = sum(1 for item in sent if item["stage"] == "replied")
        state = self.outreach.status
        self.say(settings, f"Drafts ready to send: {len(drafts)}\nWaiting for an answer: {waiting}\nReplied: {replied}\nBooks ready to upload: {len(books)}\n"
                           f"Outreach: {state.get('message') or 'no run yet'}\n\n/drafts to send, /replies to read answers.")
        return 1

    def show_draft(self, settings, after=""):
        with self.db.Session() as session:
            drafts = self._drafts(session)
            if after:
                ids = [row.id for row, _email in drafts]
                drafts = drafts[ids.index(after) + 1:] if after in ids else drafts
            if not drafts:
                self.say(settings, "No drafts waiting. /outreach drafts more (with Automatic outreach on), or open Prospects on your laptop.")
                return 1
            row, email = drafts[0]
            text, name, prospect_id = row.opener, row.name, row.id
        self.say(settings, f"{name}\nTo: {email}\n\n{text[:3200]}", buttons=[[("Send ✉", f"send:{prospect_id}"), ("Skip", f"skip:{prospect_id}"), ("Next ▶", f"next:{prospect_id}")]])
        return 1

    def send_draft(self, settings, prospect_id):
        with self.db.Session() as session:
            pairs = dict((row.id, (row, email)) for row, email in self._drafts(session))
            if prospect_id not in pairs:
                self.say(settings, "That draft was already sent or changed. /drafts shows what's waiting.")
                return 1
            row, email = pairs[prospect_id]
            text, name = row.opener, row.name
        result = self.outreach.send_one(prospect_id, email, text, follow_up=True)
        self.say(settings, f"Sent to {name}. {result['message']}")
        return self.show_draft(settings, after=prospect_id)

    def skip_draft(self, settings, prospect_id):
        with self.db.Session.begin() as session:
            row = session.get(Prospect, prospect_id)
            if row is not None and row.status == "kept":
                row.status, row.updated_at = "dropped", now()
        self.say(settings, "Skipped: it won't be offered again.")
        return self.show_draft(settings)

    def replies(self, settings):
        """Each business waiting for your answer: what they wrote, and the answer drafted for you, with one-tap buttons."""
        from .outreach import sent as sent_list
        with self.db.Session() as session:
            waiting = [item for item in sent_list(session) if item["stage"] == "replied"][:5]
        if not waiting:
            self.say(settings, "No replies waiting for an answer.")
            return 1
        for item in waiting:
            draft = item["reply"].get("draft", "")
            text = f"{item['name']} ({item['email']}) wrote:\n“{(item['reply'].get('text') or item['reply'].get('snippet', ''))[:900]}”"
            if draft:
                self.say(settings, f"{text}\n\nYour answer (drafted):\n{draft[:2000]}", buttons=[[("Send answer ✉", f"ans:{item['id']}"), ("Redraft", f"redo:{item['id']}")]])
            else:
                self.say(settings, f"{text}\n\nNo answer drafted yet.", buttons=[[("Draft an answer", f"redo:{item['id']}")]])
        return 1

    def send_reply_answer(self, settings, outbox_id):
        from .models import Outbox
        with self.db.Session() as session:
            row = session.get(Outbox, outbox_id)
            draft = (row.reply or {}).get("draft", "") if row else ""
        if not draft:
            self.say(settings, "That answer was already sent, or there's no draft. /replies shows what's waiting.")
            return 1
        self.say(settings, self.outreach.send_answer(outbox_id, draft)["message"])
        return 1

    def sent(self, settings):
        from .outreach import sent as sent_list
        with self.db.Session() as session:
            items = sent_list(session)
        if not items:
            self.say(settings, "Nothing sent yet. /drafts shows emails ready to send.")
            return 1
        counts = {}
        for item in items:
            counts[item["stage"]] = counts.get(item["stage"], 0) + 1
        words = {"sent": "waiting", "followed_up": "followed up", "done": "all follow-ups sent", "replied": "replied", "opted_out": "said no", "bounced": "bounced"}
        lines = [f"{words.get(stage, stage)}: {count}" for stage, count in counts.items()]
        recent = [f"- {item['name']}: {words.get(item['stage'], item['stage'])}" for item in items[:6]]
        self.say(settings, f"Emailed {len(items)} business(es)\n" + "\n".join(lines) + "\n\nLatest:\n" + "\n".join(recent))
        return 1

    # ---- freelance jobs ----
    def jobs(self, settings):
        """The best new matches, one message each, with buttons."""
        from .models import FreelanceLead
        with self.db.Session() as session:
            rows = session.scalars(select(FreelanceLead).where(FreelanceLead.status == "new").order_by(FreelanceLead.score.desc(), FreelanceLead.posted_at.desc()).limit(5)).all()
            items = [{"id": row.id, "title": row.title, "source": row.source, "score": row.score, "url": row.url,
                      "budget": f"{row.currency or 'USD'} {row.budget_min:,.0f}–{row.budget_max:,.0f}" if row.budget_max else "budget not given",
                      "about": " ".join(str(row.description or "").split())[:300]} for row in rows]
        if not items:
            self.say(settings, "No new matches right now. Cerebra keeps searching and tells you when strong ones appear.")
            return 1
        for item in items:
            buttons = [("Write proposal", f"prop:{item['id']}"), ("Hide", f"hide:{item['id']}")] if len(item["id"]) <= 58 else []
            if item["url"].startswith("https://"):
                buttons.append(("Open ↗", item["url"]))
            self.say(settings, f"{item['title']}\n{item['source']} · score {item['score']} · {item['budget']}\n\n{item['about']}", buttons=[buttons] if buttons else None)
        return 1

    def write_proposal(self, settings, lead_id):
        from .models import FreelanceLead
        if self.drafter is None:
            self.say(settings, "Proposals aren't available here.")
            return 1
        self.say(settings, "Writing your proposal (about a minute)…")
        self.drafter.start(lead_id, wait=True)
        with self.db.Session() as session:
            row = session.get(FreelanceLead, lead_id)
            proposal, source, url, title = dict(row.proposal or {}), row.source, row.url, row.title
        if proposal.get("status") != "ready":
            self.say(settings, f"The proposal couldn't be written: {proposal.get('error') or 'try again'}")
            return 1
        terms = " · ".join(part for part in (f"price {proposal['price']:g}" if proposal.get("price") else "", f"{proposal['days']} day(s)" if proposal.get("days") else "") if part)
        buttons = []
        if source == "freelancer" and self.bidder is not None and self.bidder.status()["connected"] and proposal.get("price") and proposal.get("days"):
            buttons.append(("Send bid on Freelancer.com", f"bid:{lead_id}"))
        if url.startswith("https://"):
            buttons.append(("Open the job ↗", url))
        self.say(settings, f"Proposal for {title}{f' ({terms})' if terms else ''}:\n\n{proposal.get('text', '')[:3300]}\n\n"
                           + ("Press Send bid, or open the job and paste it." if buttons and buttons[0][1].startswith("bid:") else "Copy it, open the job and apply."),
                 buttons=[buttons] if buttons else None)
        return 1

    def send_bid(self, settings, lead_id):
        if self.bidder is None:
            return 0
        self.say(settings, self.bidder.bid(lead_id, confirmed=True)["message"])
        return 1

    def hide_job(self, settings, lead_id):
        from .models import FreelanceLead
        with self.db.Session.begin() as session:
            row = session.get(FreelanceLead, lead_id)
            if row is not None and row.status == "new":
                row.status = "hidden"
        self.say(settings, "Hidden.")
        return 1

    def books(self, settings):
        with self.db.Session() as session:
            ready = session.scalars(select(Book).where(Book.status == "files_ready").order_by(Book.created_at)).all()
            titles = [row.title for row in ready]
        self.say(settings, (f"{len(titles)} book(s) ready to upload to KDP (about 3 a day):\n" + "\n".join(f"- {title}" for title in titles[:12])
                            + "\n\nOpen each in Cerebra › Books to copy its fields and upload its two PDFs.") if titles else "No books waiting. Cerebra › Books › Make all makes the age-group collection.")
        return 1

    def money(self, settings):
        from . import money
        with self.db.Session() as session:
            summary = money.summary(session)
        rows = summary.get("by_currency") or {}
        if not rows:
            self.say(settings, "No money recorded yet.")
            return 1
        lines = [f"{currency}: earned this month {money._money(item.get('earned_month', 0), currency)}, owed {money._money(item.get('owed', 0), currency)}"
                 + (f" ({item.get('overdue_count', 0)} overdue)" if item.get("overdue_count") else "") for currency, item in rows.items()]
        self.say(settings, "\n".join(lines))
        return 1

    def run_outreach(self, settings):
        self.say(settings, "Running outreach now…")
        result = self.outreach.tick()
        self.say(settings, result.get("message") or {"off": "Automatic outreach is off: switch it on in Prospects."}.get(result.get("skipped"), str(result)))
        return 1

    # ---- the loop ----
    def start(self):
        def loop():
            while not self._stop.is_set():
                try:
                    if not self.poll():
                        self._stop.wait(5 if self._settings() else 60)  # nothing new, or Telegram isn't set up yet
                except Exception:  # noqa: BLE001 - never affects the rest of Cerebra
                    self._stop.wait(30)
        self._thread = threading.Thread(target=loop, name="cerebra-remote", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
