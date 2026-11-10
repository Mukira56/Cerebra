"""Automatic model routing: which model plans, codes and reviews a task.

The supervisor always decides with transparent rules first: it rates how hard the task looks and what
kind of work it is, then picks a model tier per role. Claude is the owner's lead engineer: it plans and writes the
code (a frontier model for hard work, a balanced one otherwise, a fast one for small jobs). Codex, from another company,
reviews it, so the review stays independent. With "lead_coder" set to "auto", the older split applies (Codex codes,
Claude reviews). With "lock_coder" on, a task never moves its coding to another company on its own when Claude runs out
of usage: it waits for Claude, and the owner can switch it. Optionally a "supervisor model" is asked for a second opinion. Its answer is only
data: it is accepted only if every choice is a known model and the reviewer is still independent.
"""
from __future__ import annotations

import json
import re

from .catalog import best, catalog as model_catalog
from .models import Metadata

KEY = "routing"
DEFAULT = {"mode": "rules", "provider": "claude", "model": "opus", "lead_coder": "claude", "lock_coder": True}
ROLES = ("planner", "implementer", "reviewer")
HARD = ("architect", "redesign", "refactor", "migrat", "security", "authenticat", "authoriz", "concurren", "race condition",
        "performance", "optimi", "distributed", "schema", "encrypt", "payment", "from scratch", "full app", "entire",
        "multi-tenant", "scal", "deadlock", "memory leak", "algorithm", "compiler", "crash")
EASY = ("typo", "rename", "readme", "comment", "format", "lint", "bump", "spelling", "small", "tiny", "wording",
        "label", "colour", "color", "one line", "copy text", "docstring")
WRITING = ("readme", "documentation", "docs", "guide", "tutorial", "changelog", "release notes", "blog", "copywriting")


def load(session):
    row = session.get(Metadata, KEY)
    return {**DEFAULT, **(row.value if row else {})}


def save(session, mode, provider="claude", model="opus", lead_coder=None, lock_coder=None):
    from .agents import valid_model
    if mode not in {"rules", "model"}:
        raise ValueError("Routing mode must be rules or model")
    if provider not in {"codex", "claude"}:
        raise ValueError("The supervisor model must be Codex or Claude")
    before = load(session)
    lead = before["lead_coder"] if lead_coder is None else lead_coder
    if lead not in {"claude", "auto"}:
        raise ValueError("The lead coder is Claude, or automatic")
    lock = before["lock_coder"] if lock_coder is None else lock_coder
    if not isinstance(lock, bool):
        raise ValueError("Keeping Claude as the coder must be on or off")
    value = {"mode": mode, "provider": provider, "model": valid_model(model), "lead_coder": lead, "lock_coder": lock}
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return value


def assess(objective, requirements=(), allowed_paths=(".",)):
    text = " ".join([str(objective), *map(str, requirements)]).lower()
    hard = [word for word in HARD if word in text]
    easy = [word for word in EASY if word in text]
    points = 2 * len(hard) - 2 * len(easy)
    signals = [f"mentions {word}…" for word in hard[:4]] + [f"looks small ({word})" for word in easy[:3]]
    if len(text) > 700:
        points += 1; signals.append("long description")
    if len(requirements) > 5:
        points += 1; signals.append(f"{len(requirements)} requirements")
    narrow = [path for path in allowed_paths if path not in {".", "*", "**", "**/*"}]
    if narrow and len(narrow) <= 2:
        points -= 1; signals.append("limited to a few files")
    level = "hard" if points >= 2 else "easy" if points <= -2 else "normal"
    writing = sum(word in text for word in WRITING) >= 1 and not hard
    return {"level": level, "kind": "writing" if writing else "code", "signals": signals or ["no strong signals: treated as normal"]}


def _pick(models, provider, tier, why):
    item = best(models, provider, tier)
    return {"provider": provider, "model": item["model"], "label": item["label"], "tier": item.get("tier") or tier, "why": why}


def route(assessment, fixed=None, models=None, lead_coder="claude"):
    """Rule-based choices for every role not fixed by the user. `fixed` maps role -> chosen dict."""
    models = models or model_catalog()
    fixed = dict(fixed or {})
    level, kind = assessment["level"], assessment["kind"]
    tier = {"hard": "frontier", "normal": "balanced", "easy": "fast"}[level]
    chosen = dict(fixed)
    if "planner" not in chosen:
        chosen["planner"] = _pick(models, "claude", "frontier" if level == "hard" else "balanced",
                                  f"Claude plans well; {'a frontier model for a hard task' if level == 'hard' else 'a balanced model is enough'}.")
    if "implementer" not in chosen:
        if lead_coder == "claude" and chosen.get("reviewer", {}).get("provider") == "claude":
            chosen["implementer"] = _pick(models, "codex", tier, f"You chose Claude to review, so Codex codes and the review stays independent; {level} task, so a {tier} model.")
        elif lead_coder == "claude":
            chosen["implementer"] = _pick(models, "claude", tier, f"Claude is your lead engineer; {level} task, so a {tier} model.")
        else:
            provider = "claude" if kind == "writing" else "codex"
            chosen["implementer"] = _pick(models, provider, tier,
                                          ("Writing-heavy work goes to Claude" if provider == "claude" else "Codex is built for hands-on coding")
                                          + f"; {level} task, so a {tier} model.")
    if "reviewer" not in chosen:
        other = "codex" if chosen["implementer"]["provider"] == "claude" else "claude"
        review_tier = "frontier" if level == "hard" else "balanced"
        chosen["reviewer"] = _pick(models, other, review_tier, "A different provider from the coder keeps the review independent"
                                   + ("; frontier for a hard task." if level == "hard" else "."))
    return chosen


def router_prompt(objective, requirements, assessment, proposal, models):
    options = {provider: [{"model": item["model"], "label": item["label"], "tier": item["tier"] or "unranked", "strengths": item["strengths"]}
                          for item in items] for provider, items in models.items()}
    return ("You are the supervisor model of Cerebra, a software team of AI models. Choose which model should plan, code and "
            "review the task below. Pick the model that will do each job best; don't waste a frontier model on a small job. "
            "The reviewer MUST be from a different provider than the coder. Choose only from the listed models.\n\n"
            + json.dumps({"task": str(objective)[:4000], "requirements": list(requirements)[:20], "assessment": assessment,
                          "available_models": options,
                          "rules_proposal": {role: {"provider": value["provider"], "model": value["model"]} for role, value in proposal.items()}}, ensure_ascii=False)
            + '\n\nReply with only one JSON object: {"planner": {"provider": "...", "model": "..."}, "implementer": {...}, '
            '"reviewer": {...}, "reason": "one or two sentences"}')


def parse_router(text, models, fixed=None):
    """Validate a supervisor model's answer. Returns (choices, reason) or raises ValueError."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("no JSON object in the answer")
    answer = json.loads(match.group(0))
    reason = str(answer.get("reason", ""))[:500]
    chosen = dict(fixed or {})
    for role in ROLES:
        if role in chosen:
            continue
        pick = answer.get(role)
        if not isinstance(pick, dict):
            raise ValueError(f"missing {role}")
        provider, model = str(pick.get("provider", "")), str(pick.get("model", ""))
        item = next((entry for entry in models.get(provider, []) if entry["model"] == model), None)
        if item is None:
            raise ValueError(f"{provider}/{model} is not an available model")
        chosen[role] = {"provider": provider, "model": model, "label": item["label"], "tier": item["tier"], "why": reason or "Chosen by the supervisor model."}
    if chosen["reviewer"]["provider"] == chosen["implementer"]["provider"]:
        raise ValueError("the reviewer was not independent of the coder")
    return chosen, reason
