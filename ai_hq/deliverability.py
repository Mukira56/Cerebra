"""Keeping the owner's Gmail in good standing: don't write to domains that can't receive mail, and stop when too much bounces.

A domain is checked before an email is written or sent: its MX records, or its plain address when it has none (RFC 5321),
and a null MX (RFC 7505) means it refuses all mail. Only the business's domain name leaves this computer, over DNS-over-HTTPS,
so it works the same on every system with no extra package. If the lookup fails the answer is "unknown" and sending goes on:
a problem on our side never blocks an email.

Automatic sending pauses when PAUSE_BOUNCES of the last WINDOW first emails have bounced, which is 3% at the very least,
so one or two bad addresses never stop anything. Replies are still read and drafts still written, and the owner can still send by
hand. The pause lasts until the owner resumes it, because no new sends means the rate can't fall on its own; only emails
sent after that count.

A new sender also builds up: automatic emails are capped by RAMP for the first three weeks after its first email, then the
owner's own daily number applies. The steps follow common deliverability practice, not a published Google limit. Emails the
owner sends by hand are never held back.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from .network import LazyClient
from .models import Metadata, Outbox, now

KEY = "outreach_health"
RESOLVER = "https://cloudflare-dns.com/dns-query"
PAUSE_BOUNCES, WINDOW = 3, 100
UNSENT = ("draft", "no_email", "skipped", "drafting")
RESERVED = (".example", ".test", ".invalid", ".localhost")  # never exist on the internet, so there's nothing to ask
MX, NO_SUCH_DOMAIN = 15, 3
RAMP = ((7, 10), (14, 20), (21, 30))  # up to this many days after the first email, at most this many a day


class MailCheck:
    def __init__(self, client=None):
        self.client = client or LazyClient(timeout=5)

    def _ask(self, domain, kind):
        reply = self.client.get(RESOLVER, params={"name": domain, "type": kind}, headers={"accept": "application/dns-json"})
        reply.raise_for_status()
        return reply.json()

    def domain(self, domain):
        """"ok", "dead" (it can't receive mail) or "unknown" (the lookup failed)."""
        domain = str(domain or "").strip().lower().rstrip(".")
        if not domain or domain.endswith(RESERVED):
            return "unknown"
        try:
            answer = self._ask(domain, "MX")
            if answer.get("Status") == NO_SUCH_DOMAIN:
                return "dead"
            if answer.get("Status") != 0:
                return "unknown"
            hosts = [item.get("data", "").split()[-1].rstrip(".") for item in answer.get("Answer") or [] if item.get("type") == MX and item.get("data", "").split()]
            if hosts:
                return "ok" if any(hosts) else "dead"
            for kind, number in (("A", 1), ("AAAA", 28)):
                answer = self._ask(domain, kind)
                if answer.get("Status") != 0:
                    return "unknown"
                if any(item.get("type") == number for item in answer.get("Answer") or []):
                    return "ok"
            return "dead"
        except (httpx.HTTPError, ValueError, AttributeError):
            return "unknown"

    def can_receive(self, email):
        return self.domain(str(email or "").rsplit("@", 1)[-1]) != "dead"


def _state(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row else {}


def _save(session, value):
    row = session.get(Metadata, KEY)
    if row is None:
        session.add(Metadata(key=KEY, value=value))
    else:
        row.value = value


def health(session):
    """How the last first emails did, and whether automatic sending is paused."""
    since = _state(session).get("cleared_at", "")
    rows = [row for row in session.scalars(select(Outbox).where(Outbox.stage.notin_(UNSENT))).all() if row.emails and row.emails[0].get("at", "") > since]
    rows = sorted(rows, key=lambda row: row.emails[0].get("at", ""), reverse=True)[:WINDOW]
    bounced = sum(row.stage == "bounced" for row in rows)
    rate = bounced / len(rows) if rows else 0.0
    paused = bounced >= PAUSE_BOUNCES
    reason = f"{bounced} of your last {len(rows)} emails bounced ({rate:.0%}). Too many bounces can get a Gmail account limited, so automatic sending has stopped." if paused else ""
    return {"sent": len(rows), "bounced": bounced, "rate": round(rate, 4), "paused": paused, "reason": reason}


def daily_limit(session, per_day):
    """How many automatic emails today: the owner's number, or less while a new sender builds up."""
    sends = [row.emails[0].get("at", "") for row in session.scalars(select(Outbox).where(Outbox.stage.notin_(UNSENT))).all() if row.emails]
    try:
        first = datetime.fromisoformat(min(item for item in sends if item))
        age = (datetime.now(timezone.utc) - (first if first.tzinfo else first.replace(tzinfo=timezone.utc))).days
    except ValueError:  # nothing sent yet, or a date that can't be read: the first step is the safe answer
        age = 0
    return next((min(per_day, cap) for days, cap in RAMP if age < days), per_day)


def first_notice(session):
    """True once per pause, so the owner is told once rather than every run."""
    value = _state(session)
    if value.get("told"):
        return False
    _save(session, {**value, "told": True})
    return True


def resume(session):
    """The owner has looked at the list: count only what's sent from now on."""
    _save(session, {"cleared_at": now(), "told": False})
