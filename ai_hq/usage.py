"""When an AI provider's usage comes back, read from its own limit message.

Codex says "try again at 10:31 PM", or with a date when a weekly limit is used up ("try again at Nov 16th, 2026
8:14 AM"); Claude says "resets 3pm" or "resets at 3:30pm"; some messages say "try again in 2 hours 5 minutes". Times are this computer's local time. Anything unrecognised returns None, and the
caller keeps its default wait.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

CLOCK = re.compile(r"(?:try again at|resets?(?: at)?|available (?:again )?at|until)\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", re.I)
DURATION = re.compile(r"(?:try again|retry|resets?|available again)\s+in\s+((?:\d+\s*(?:d|day|days|h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|seconds)\b[\s,and]*)+)", re.I)
UNIT = re.compile(r"(\d+)\s*(d|day|days|h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|seconds)\b", re.I)
DATED = re.compile(r"(?:try again at|resets?(?: at| on)?|available (?:again )?(?:at|on))\s+([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?"
                   r"(?:\s+(\d{4}))?,?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", re.I)
MONTHS = {name: number for number, name in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
LIMIT = 24 * 3600
WEEK_LIMIT = 8 * 86400  # a dated reset (a weekly limit) can be days away
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
    dated = DATED.search(text)
    if dated and dated.group(1)[:3].lower() in MONTHS:
        hour = clock_hour(dated.group(4), dated.group(6))
        try:
            target = now.replace(year=int(dated.group(3) or now.year), month=MONTHS[dated.group(1)[:3].lower()], day=int(dated.group(2)),
                                 hour=hour, minute=int(dated.group(5) or 0), second=0, microsecond=0) if hour is not None else None
        except ValueError:
            target = None
        if target is not None and not dated.group(3) and target < now - timedelta(days=1):
            target = target.replace(year=target.year + 1)  # "Jan 2nd" read on Dec 30th
        if target is None or target <= now:
            return None
        return min(WEEK_LIMIT, int((target - now).total_seconds()) + MARGIN)
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


def clock_hour(hour, meridiem):
    """24-hour hour from "8" and "AM"/"p.m." (or none), or None if it isn't a real time."""
    hour, meridiem = int(hour), (meridiem or "").lower().replace(".", "")
    if meridiem:
        return hour % 12 + (12 if meridiem == "pm" else 0) if 1 <= hour <= 12 else None
    return hour if hour <= 23 else None
