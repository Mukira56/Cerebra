"""One place that decides what a coding run may do, from the owner's grants and the work's true origin.

A task's origin (`user`, `support`, `readiness`, ...) is recorded when it is created and never rewritten;
model-written fix instructions are noted separately in `instructions_from`. Full access goes to work the
owner asked for directly, and to model-touched work only when the owner's Auto-fix permission covers it.
The decision is made again before every agent run, so revoking a grant applies to the next run.
"""
from __future__ import annotations

from . import autofix


def full_access(settings, session, task):
    """(allowed, reason) for giving this task's coding run shell, network and GitHub access."""
    if not settings.full_access:
        return False, "Full access is off"
    results = task.results or {}
    origin = results.get("origin", "user")
    if origin == "user" and not results.get("instructions_from"):
        return True, "the owner asked for this task"
    policy, fix = autofix.load(session), results.get("auto_fix") or {}
    if policy["enabled"] and policy["full_access"] and fix.get("attempts") and not fix.get("stopped"):
        return True, "the owner's Auto-fix permission (origin " + origin + ")"
    source = results.get("instructions_from") or origin
    return False, f"text written by {source} runs project-only unless the owner's Auto-fix permission covers it"
