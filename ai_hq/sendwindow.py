"""When automatic emails may go out: Monday to Friday, during business hours on this computer's clock (8 am to 5 pm unless
the owner changes it). Pitches and applications sent at 2 am or on a Sunday sit under a pile of newer mail by the time
someone reads them; sending while people are at work is what gets a reply.

Only automatic sending waits. Research, drafting and reading replies carry on at any hour, and the owner's own Send button
always sends at once.
"""
from __future__ import annotations

from datetime import datetime

DEFAULT = {"business_hours": True, "start_hour": 8, "end_hour": 17}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def rules(value):
    """The window settings from a feature's saved settings, with defaults."""
    value = value or {}
    return {key: value.get(key, default) for key, default in DEFAULT.items()}


def validate(changes, value):
    """Apply the owner's changes to the window into value, refusing anything that isn't a sensible window."""
    if "business_hours" in changes:
        if not isinstance(changes["business_hours"], bool):
            raise ValueError("Business hours must be on or off")
        value["business_hours"] = changes["business_hours"]
    for key in ("start_hour", "end_hour"):
        if key in changes:
            try:
                value[key] = int(changes[key])
            except (TypeError, ValueError):
                raise ValueError("Hours must be whole numbers from 0 to 24") from None
    start, end = value.get("start_hour", DEFAULT["start_hour"]), value.get("end_hour", DEFAULT["end_hour"])
    if not (0 <= start < end <= 24 and end - start >= 2):
        raise ValueError("Choose a sending window of at least 2 hours, starting before it ends (for example 8 to 17)")
    return value


def _clock(hour):
    return "midnight" if hour in (0, 24) else "noon" if hour == 12 else f"{hour % 12} {'am' if hour < 12 else 'pm'}"


def describe(value):
    window = rules(value)
    if not window["business_hours"]:
        return "Automatic emails go out at any hour."
    return f"Automatic emails go out Monday to Friday, {_clock(window['start_hour'])} to {_clock(window['end_hour'])} on this computer's clock."


def closed(value, now=None):
    """Why automatic sending waits right now, in plain words; empty when it may send."""
    window = rules(value)
    if not window["business_hours"]:
        return ""
    now = now or datetime.now().astimezone()
    if now.weekday() >= 5:
        return f"It's {DAYS[now.weekday()]}: automatic emails wait for Monday, {_clock(window['start_hour'])}, when people read them."
    if now.hour < window["start_hour"]:
        return f"Automatic emails wait for {_clock(window['start_hour'])}, when people are at work."
    if now.hour >= window["end_hour"]:
        return "The working day is over: automatic emails wait for tomorrow morning" + (" (Monday)." if now.weekday() == 4 else ".")
    return ""
