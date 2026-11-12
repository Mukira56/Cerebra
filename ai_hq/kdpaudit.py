"""How well a KDP listing uses its seven keyword boxes, worked out here with no call to Amazon.

A buyer finds a book through the words in its title, subtitle and keyword boxes. A box that repeats the title, or says what
another box already says, adds nothing, so the useful number is how many new search words the boxes bring (`reach`).

"fix" findings stop a listing being uploaded as it is: too long, too many boxes, banned claims or trademarks.
"improve" findings are advice from common publishing practice, not Amazon rules, so they lower the score and block nothing.
"""
from __future__ import annotations

from .words import counted
import re

from .etsy import TRADEMARKS
from .notebooks import BANNED, KEYWORD_MAX, KEYWORDS

FIX_COST, IMPROVE_COST = 25, 8
FILLER = frozenset("a an and at book books by for from in into my of on or our the this to with you your".split())
FREE_OF = "gluten sugar dairy stress debt clutter fat grain nut egg pain smoke caffeine alcohol".split()  # "gluten free" is a topic, not a price


def grade(fix, improve, extra=0):
    """The score and its label, with `extra` for advice that counts more than once."""
    score = max(0, 100 - FIX_COST * len(fix) - IMPROVE_COST * (len(improve) + extra))
    return score, "fix" if fix else "strong" if score >= 85 else "good" if score >= 60 else "weak"


def words(text):
    """The words that count for search, with plurals folded so "planners" and "planner" are the same."""
    found = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word for word in found if word not in FILLER}


def claims(text):
    text = re.sub(r"\b(" + "|".join(FREE_OF) + r")[ -]free\b", " ", str(text or "").lower())
    found = {word for word in BANNED if re.search(r"(?<![\w#])" + re.escape(word) + r"(?!\w)", text)}
    return sorted(found), sorted({mark for mark in TRADEMARKS if re.search(r"\b" + re.escape(mark) + r"\b", text)})


def audit(title, subtitle="", keywords=()):
    """{score, label, reach, used, fix: [...], improve: [...]} for a listing's title, subtitle and keyword boxes."""
    boxes = [" ".join(str(item or "").split()) for item in keywords or []]
    filled = [item for item in boxes if item]
    fix, improve = [], []
    if len(filled) > KEYWORDS:
        fix.append(f"{len(filled)} keywords, but KDP has {KEYWORDS} boxes")
    banned, marks = claims(" ".join([str(title or ""), str(subtitle or ""), *filled]))
    if banned:
        fix.append("Remove words KDP doesn't allow: " + ", ".join(banned))
    if marks:
        fix.append("Remove trademarked names: " + ", ".join(marks))
    empty = max(0, KEYWORDS - len(filled))
    if empty:
        improve.append(f"{empty} of {KEYWORDS} boxes are empty: every box is a free chance to be found" if empty > 1 else "1 box is empty: every box is a free chance to be found")
    named = words(f"{title} {subtitle}")
    seen, new = [], set()
    for number, box in enumerate(filled, 1):
        if len(box) > KEYWORD_MAX:
            fix.append(f"Box {number} is {len(box)} characters; the limit is {KEYWORD_MAX}")
        terms = words(box)
        earlier = next((place for place, other in enumerate(seen, 1) if terms and terms <= other), None)
        if len(box.split()) == 1:
            improve.append(f"Box {number} (“{box}”) is a single word: buyers type phrases, and one word has the most competition")
        elif terms <= named:
            improve.append(f"Box {number} (“{box}”) only repeats your title: use words that aren't there yet")
        elif earlier:
            improve.append(f"Box {number} (“{box}”) adds nothing to box {earlier}: use different words")
        seen.append(terms)
        new |= terms - named
    score, label = grade(fix, improve, max(0, empty - 1))
    return {"score": score, "label": label, "reach": len(new), "summary": f"Your boxes add {counted(len(new), 'search word', 'search words')} your title doesn't have.",
            "used": sum(len(item) for item in filled), "fix": fix, "improve": improve}
