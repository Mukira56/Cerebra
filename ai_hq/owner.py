"""About you: the owner's own details, entered once in Settings, so the AI team can use them in the owner's work.

A portfolio, a README, a client reply or an "about" page needs the owner's real name, links and voice, and the AI
providers' own memories (ChatGPT's, Claude's) are not shared with Cerebra. The owner types them here; Support, the
Council and coding runs receive them as a short block, only while "share with the AI team" is on. It never
holds passwords or keys: only what the owner would put on a public profile, plus how they like things done.
"""
from __future__ import annotations

import re

from .models import Metadata, now
from .security import redact

KEY = "owner_profile"
FIELDS = {  # name: (label, longest allowed)
    "name": ("Name", 120), "headline": ("What you do", 200), "email": ("Email", 200), "github": ("GitHub username", 60),
    "linkedin": ("LinkedIn", 300), "website": ("Website", 300), "location": ("Location", 120),
    "bio": ("About you", 1500), "preferences": ("How you like things done", 1500),
}
EMPTY = {name: "" for name in FIELDS} | {"share": True}


def load(session):
    row = session.get(Metadata, KEY)
    return {**EMPTY, **(row.value if row else {})}


def save(session, values):
    current = load(session)
    for name, (label, limit) in FIELDS.items():
        if name in values and values[name] is not None:
            text = " ".join(str(values[name]).split()) if name not in {"bio", "preferences"} else str(values[name]).strip()
            if len(text) > limit:
                raise ValueError(f"{label} can be at most {limit} characters")
            current[name] = text
    if current["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", current["email"]):
        raise ValueError("That email address doesn't look right")
    if current["github"] and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", current["github"]):
        raise ValueError("A GitHub username has only letters, digits and dashes")
    if "share" in values and values["share"] is not None:
        current["share"] = bool(values["share"])
    current["updated_at"] = now()
    row = session.get(Metadata, KEY)
    if row:
        row.value = current
    else:
        session.add(Metadata(key=KEY, value=current))
    return current


def brief(session):
    """The block the AI team receives, or "" when there's nothing to share (or sharing is off)."""
    profile = load(session)
    if not profile.get("share"):
        return ""
    lines = [f"{label}: {redact(profile[name])}" for name, (label, _) in FIELDS.items() if profile.get(name)]
    if not lines:
        return ""
    return ("ABOUT THE OWNER (their own details, entered by them in Cerebra for use in their projects; use them where the work "
            "calls for the owner's name, links or voice instead of placeholders, and never invent details that aren't here):\n" + "\n".join(lines))
