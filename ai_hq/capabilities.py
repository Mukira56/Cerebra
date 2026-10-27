"""One place that decides what a coding run may do, from the owner's grants and the work's true origin.

A task's origin (`user`, `support`, `readiness`, ...) is recorded when it is created and never rewritten;
model-written fix instructions are noted separately in `instructions_from`. Full access goes to work the
owner asked for directly, and to model-touched work only when an owner grant covers it: the Auto-fix permission,
or "Support and Council work too" (ASSISTANT_KEY), a separate switch in the Full access panel.
The decision is made again before every agent run, so revoking a grant applies to the next run.
"""
from __future__ import annotations

from . import autofix
from .models import Metadata, now

ASSISTANT_KEY = "assistant_full_access"
MODEL_ORIGINS = {"support", "council"}


def assistant_grant(session):
    row = session.get(Metadata, ASSISTANT_KEY)
    return bool(row and (row.value or {}).get("enabled"))


def set_assistant_grant(session, enabled):
    value = {"enabled": bool(enabled), "changed_at": now()}
    row = session.get(Metadata, ASSISTANT_KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=ASSISTANT_KEY, value=value))
    return value


def full_access(settings, session, task):
    """(allowed, reason) for giving this task's coding run shell, network and GitHub access."""
    if not settings.full_access:
        return False, "Full access is off"
    results = task.results or {}
    origin = results.get("origin", "user")
    if origin == "user" and not results.get("instructions_from"):
        return True, "the owner asked for this task"
    source = results.get("instructions_from") or origin
    if source in MODEL_ORIGINS and assistant_grant(session):
        return True, f"the owner's permission for Support and Council work (origin {origin})"
    policy, fix = autofix.load(session), results.get("auto_fix") or {}
    if policy["enabled"] and policy["full_access"] and fix.get("attempts") and not fix.get("stopped"):
        return True, "the owner's Auto-fix permission (origin " + origin + ")"
    return False, f"text written by {source} runs project-only unless the owner allows it (Settings › Full access, or Auto-fix)"
