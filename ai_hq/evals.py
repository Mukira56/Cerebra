"""A fixed check set for the model hub: short questions with known answers, one small set per kind of work. The owner runs
it on demand (Model intelligence › Run the check set); nothing runs it on a schedule, so it never spends a free allowance by
itself. Scores are kept with their date, so a change of model, or a model that has got worse, shows up as a number.

Answers are checked by Cerebra's own rules (a number, a word, valid JSON), never by another model's opinion. Kinds of work
routed to the owner's Claude or Codex account aren't checked here: those calls belong to the owner's plan.
"""
from __future__ import annotations

import json
import re

from .models import Metadata, now

KEY = "model_checks"
HISTORY = 20  # results kept per kind of work


def _has_number(expected):
    return lambda answer: re.search(rf"(?<!\d)(?<!\d\.){re.escape(expected)}(?!\d|\.\d)", answer.replace(",", "")) is not None


def _first_word(*allowed):
    return lambda answer: (re.findall(r"[a-z]+", answer.lower()) or [""])[0] in allowed


def _json_with(*keys):
    def check(answer):
        found = re.search(r"\{.*\}", answer, re.S)
        try:
            data = json.loads(found.group(0)) if found else None
        except ValueError:
            return False
        return isinstance(data, dict) and all(key in data for key in keys)
    return check


_FILLER = " ".join(f"Section {n}: the quarterly report discusses routine office matters, supplies and scheduling." for n in range(1, 121))

CHECKS = {
    "research": [
        ("Read the page text and reply with the monthly price as a number only.\nPAGE: The Starter plan is $19 per month. The Team plan is $49 per month.\nQuestion: what does the Starter plan cost per month?", _has_number("19")),
        ("Reply with the company's founding year only.\nPAGE: Northwind Tools was founded in 2014 in Denver and moved to Austin in 2019.", _has_number("2014")),
    ],
    "verify": [
        ("Does the source support the claim? Reply yes or no only.\nSOURCE: The store ships to the United States and Canada.\nCLAIM: The store ships to Mexico.", _first_word("no")),
        ("Does the source support the claim? Reply yes or no only.\nSOURCE: Orders over $50 ship free.\nCLAIM: An order of $80 ships free.", _first_word("yes")),
    ],
    "verify_second": [
        ("Does the source support the claim? Reply yes or no only.\nSOURCE: The course has 12 lessons.\nCLAIM: The course has 20 lessons.", _first_word("no")),
    ],
    "bulk": [
        ("Classify the review as positive or negative. Reply with one word.\nREVIEW: Arrived broken and support never answered.", _first_word("negative")),
        ("Classify the review as positive or negative. Reply with one word.\nREVIEW: Exactly as described, fast shipping, would buy again.", _first_word("positive")),
    ],
    "coding": [
        ("What does this Python print? Reply with the output only.\nprint(sum(x * x for x in range(4)))", _has_number("14")),
    ],
    "reasoning": [
        ("Reply with the number only: 17 * 23 - 40", _has_number("351")),
        ("A shirt costs $25 and is discounted 20%. Then $3 shipping is added. Reply with the total in dollars as a number only.", _has_number("23")),
    ],
    "long_context": [
        ("Read the document and reply with the access code only.\nDOCUMENT: " + _FILLER[: len(_FILLER) // 2] + " Note: the access code for the archive room is 4827. " + _FILLER[len(_FILLER) // 2:], _has_number("4827")),
    ],
    "architect": [
        ('Turn this request into JSON with the keys "goal" and "requirements" (a list). Reply with JSON only.\nREQUEST: Add a contact form that emails the owner.', _json_with("goal", "requirements")),
    ],
}


def history(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row and isinstance(row.value, dict) else {}


def run(hub, categories=None):
    """Run the check set through the hub (fresh answers, never the saved ones) and keep the scores. Returns this run's
    results per kind of work: the route, how many answers were right, and which questions failed."""
    from . import modelhub
    results = {}
    for category, checks in CHECKS.items():
        if categories and category not in categories:
            continue
        route = hub.route(category)
        if route in modelhub.ACCOUNTS and route not in modelhub.SIGNED_IN:
            results[category] = {"route": route, "skipped": "Uses your Claude or Codex account: not checked here"}
            continue
        passed, failed = 0, []
        for number, (prompt, check) in enumerate(checks, 1):
            answer = hub.chat(category, prompt, max_tokens=300, fresh=True)
            right = bool(answer.success and check(answer.output or ""))
            passed += right
            if not right:
                failed.append({"question": number, "why": answer.error or "wrong answer"})
        results[category] = {"route": route, "passed": passed, "total": len(checks), "score": round(100 * passed / len(checks)), "failed": failed}
    stamp = now()
    with hub.db.Session.begin() as session:
        kept = history(session)
        for category, result in results.items():
            if "score" in result:
                kept[category] = ([{"at": stamp, "route": result["route"], "score": result["score"]}] + list(kept.get(category, [])))[:HISTORY]
        row = session.get(Metadata, KEY)
        if row is None:
            session.add(Metadata(key=KEY, value=kept))
        else:
            row.value = kept
    return results


def summary(session):
    """The latest score per kind of work next to the one before it, for Model intelligence."""
    rows = []
    for category, entries in history(session).items():
        if not entries:
            continue
        latest, previous = entries[0], entries[1] if len(entries) > 1 else None
        rows.append({"category": category, "route": latest["route"], "score": latest["score"], "at": latest["at"],
                     "previous": previous["score"] if previous else None, "previous_route": previous["route"] if previous else None})
    return rows
