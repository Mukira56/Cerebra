"""Away mode: the user's time-limited permission for Cerebra to answer approval gates on their behalf.

While it is on, the supervisor approves plans, starts the AI team and sends review findings back for
repair, so queued work keeps moving without the user at the keyboard. Merging into the project is a
separate opt-in and only happens for candidates whose registered tests passed and whose independent
review left nothing to fix. Pushing the merged branch to the project's GitHub remote is a further
opt-in on top of merging. Away mode never widens what agents may touch; that is the separate
Full access switch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Metadata, now

KEY = "autopilot"
MAX_HOURS = 72
OFF = {"enabled": False, "auto_merge": False, "auto_push": False, "projects": [], "until": None, "started_at": None}


def load(session):
    row = session.get(Metadata, KEY)
    return {**OFF, **(row.value if row else {})}


def active(policy, at=None):
    if not policy.get("enabled") or not policy.get("until"):
        return False
    try:
        until = datetime.fromisoformat(policy["until"])
    except (TypeError, ValueError):
        return False
    return (at or datetime.now(timezone.utc)) < until


def covers(policy, project_id):
    return not policy.get("projects") or project_id in policy["projects"]


def describe(policy):
    return {**policy, "active": active(policy)}


def save(session, enabled, hours=8, auto_merge=False, projects=(), auto_push=False):
    if enabled:
        hours = int(hours)
        if not 1 <= hours <= MAX_HOURS:
            raise ValueError(f"Away mode can last 1 to {MAX_HOURS} hours")
        if auto_push and not auto_merge:
            raise ValueError("Pushing to GitHub needs automatic merging too")
        value = {"enabled": True, "auto_merge": bool(auto_merge), "auto_push": bool(auto_push), "projects": list(dict.fromkeys(projects)),
                 "started_at": now(), "until": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()}
    else:
        value = dict(OFF)
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return describe(value)
