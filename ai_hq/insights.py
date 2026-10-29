"""What works: where the owner's freelance work and money actually come from, so they spend their time there.

Phase 5 of docs/FREELANCE_PLAN.md. From the owner's own records only: every lead (where it came from, which service it
fits, whether it was applied to, awarded, won), the bids Cerebra sent by itself and the ones the owner sent, and the
money a won job earned (its Business Studio job's invoices and ledger). Suggestions are simple rules over these numbers,
shown with the numbers, and only once there is enough to go on: nothing is guessed.
"""
from __future__ import annotations

import functools
import re

from sqlalchemy import select

from .models import BusinessRecord, FreelanceLead, MoneyDocument

APPLIED = {"applied", "interview", "awarded", "won", "lost"}
MIN_FOR_ADVICE = 5  # applications in a group before a rate is worth acting on


@functools.cache
def _pattern(key):
    """One search for all of a service's words (longest first), instead of one search per word."""
    from .freelance import SERVICES
    words = sorted({word.strip().lower() for word in SERVICES[key][1] if word.strip()}, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(map(re.escape, words)) + r")(?![a-z0-9])")


def _service(row, services):
    """The service a job fits best: the one with the most different words in its title and description."""
    text = f"{row.title} {row.description[:2000]}".lower()
    best, hits = "other", 0
    for key in services:
        found = len(set(_pattern(key).findall(text)))
        if found > hits:
            best, hits = key, found
    return best


def _earned(session, job_id, copies, main):
    """Money a won job brought in, per currency: payments on its invoices plus payments recorded on the job by hand
    (an invoice's copy in the job's ledger is counted once)."""
    from .money import _is_invoice_copy
    totals = {}
    if not job_id:
        return totals
    for doc in session.scalars(select(MoneyDocument).where(MoneyDocument.job_id == job_id, MoneyDocument.kind == "invoice")).all():
        for payment in doc.payments or []:
            totals[doc.currency] = totals.get(doc.currency, 0.0) + float(payment.get("amount") or 0)
    record = session.get(BusinessRecord, job_id)
    for item in (record.ledger if record else None) or []:
        if item.get("kind") == "payment" and not _is_invoice_copy(job_id, item, copies):
            totals[main] = totals.get(main, 0.0) + float(item.get("amount") or 0)
    return totals


def _group():
    return {"found": 0, "applied": 0, "awarded": 0, "won": 0, "earned": {}}


def _rate(group):
    return round(100 * group["won"] / group["applied"]) if group["applied"] else None


def summary(session):
    from . import business
    from .freelance import SERVICES, SOURCES, profile
    from .money import _invoice_copies
    services, copies, main = profile(session)["services"], _invoice_copies(session), business.load(session)["currency"]
    by_source, by_service, by_way = {}, {}, {"automatic": _group(), "by you": _group()}
    for row in session.scalars(select(FreelanceLead)).all():
        extra, proposal = row.extra or {}, row.proposal or {}
        source = SOURCES.get(row.source, {}).get("label") if row.source != "pasted" else (extra.get("company") or "Pasted")
        groups = [by_source.setdefault(source or row.source, _group()), by_service.setdefault(_service(row, services), _group())]
        if row.status in APPLIED:
            groups.append(by_way["automatic" if proposal.get("auto") else "by you"])
        earned = _earned(session, extra.get("job_id"), copies, main) if row.status == "won" else {}
        for index, group in enumerate(groups):
            if index < 2:
                group["found"] += 1
            if row.status in APPLIED:
                group["applied"] += 1
            if row.status in {"awarded", "won"}:
                group["awarded"] += 1
            if row.status == "won":
                group["won"] += 1
                for currency, amount in earned.items():
                    group["earned"][currency] = round(group["earned"].get(currency, 0.0) + amount, 2)
    labels = {key: label for key, (label, _) in SERVICES.items()} | {"other": "Other work"}
    table = lambda groups, names=None: [{"name": (names or {}).get(key, key), **values, "win_rate": _rate(values)}  # noqa: E731
                                         for key, values in sorted(groups.items(), key=lambda item: (-item[1]["won"], -item[1]["applied"], -item[1]["found"], item[0]))]
    result = {"currency": main, "sources": table(by_source), "services": table(by_service, labels), "ways": table(by_way)}
    totals = {key: sum(row[key] for row in result["sources"]) for key in ("found", "applied", "awarded", "won")}
    totals["earned"] = {}
    for row in result["sources"]:
        for currency, amount in row["earned"].items():
            totals["earned"][currency] = round(totals["earned"].get(currency, 0.0) + amount, 2)
    result["totals"] = totals
    result["advice"] = advice(result)
    return result


def advice(result):
    """Plain suggestions from the numbers; each says the numbers it rests on."""
    tips = []
    enough = [row for row in result["sources"] if row["applied"] >= MIN_FOR_ADVICE]
    if enough:
        best = max(enough, key=lambda row: (row["win_rate"] or 0, row["earned"].get(result.get("currency"), 0)))
        if best["won"]:
            tips.append(f"{best['name']} is where you win most: {best['won']} of {best['applied']} applications ({best['win_rate']}%). Spend your time there first.")
        for row in enough:
            if row is not best and row["won"] == 0 and row["applied"] >= 2 * MIN_FOR_ADVICE:
                tips.append(f"{row['name']}: {row['applied']} applications and no wins yet. Try fewer, more tailored applications there, or focus elsewhere.")
    services = [row for row in result["services"] if row["applied"] >= MIN_FOR_ADVICE]
    if services:
        strong = max(services, key=lambda row: (row["win_rate"] or 0))
        if strong["won"]:
            tips.append(f"Clients hire you most for {strong['name'].lower()} ({strong['win_rate']}% of applications won). Lead with it in your profiles and posts.")
    auto = next((row for row in result["ways"] if row["name"] == "automatic"), None)
    manual = next((row for row in result["ways"] if row["name"] == "by you"), None)
    if auto and auto["applied"] >= 2 * MIN_FOR_ADVICE and (auto["win_rate"] or 0) < 5:
        tips.append(f"Automatic bids have won {auto['won']} of {auto['applied']}. Raise the lowest score to bid on (Apply automatically) so only the best matches get a bid.")
    if auto and manual and auto["applied"] >= MIN_FOR_ADVICE and manual["applied"] >= MIN_FOR_ADVICE and (manual["win_rate"] or 0) > (auto["win_rate"] or 0) + 10:
        tips.append(f"Proposals you send yourself win more ({manual['win_rate']}% against {auto['win_rate']}% automatic). Edit the automatic ones' wording in your profile details.")
    if not tips:
        tips.append("Not enough results yet to see a pattern: after a few more applications, this shows where you win and earn most.")
    return tips
