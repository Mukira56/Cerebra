"""When an AI provider's usage comes back, read from its own limit message.

Codex says "try again at 10:31 PM"; Claude says "resets 3pm" or "resets at 3:30pm"; some messages say
"try again in 2 hours 5 minutes". Times are this computer's local time. Anything unrecognised returns None, and the
caller keeps its default wait.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

CLOCK = re.compile(r"(?:try again at|resets?(?: at)?|available (?:again )?at|until)\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", re.I)
DURATION = re.compile(r"(?:try again|retry|resets?|available again)\s+in\s+((?:\d+\s*(?:d|day|days|h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|seconds)\b[\s,and]*)+)", re.I)
UNIT = re.compile(r"(\d+)\s*(d|day|days|h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|seconds)\b", re.I)
SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
LIMIT = 24 * 3600
MARGIN = 60  # a minute after the reset, so the first try lands after it


def reset_in(text, now=None):
    """Seconds until the provider says usage is available again (with a small margin), or None."""
    text = str(text or "")
    now = now or datetime.now()
    duration = DURATION.search(text)
    if duration:
        total = sum(int(amount) * SECONDS[unit[0].lower()] for amount, unit in UNIT.findall(duration.group(1)))
        if total:
            return min(LIMIT, total + MARGIN)
    clock = CLOCK.search(text)
    if not clock:
        return None
    hour, minute, meridiem = int(clock.group(1)), int(clock.group(2) or 0), (clock.group(3) or "").lower().replace(".", "")
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return min(LIMIT, int((target - now).total_seconds()) + MARGIN)
