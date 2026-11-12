"""Small helpers for the words Cerebra shows people."""
from __future__ import annotations


def counted(number, one, many):
    """'1 email', '3 emails', '0 replies': a count with the right form of the word."""
    try:
        value = int(number)
    except (TypeError, ValueError):
        return f"{number} {many}"
    return f"{number} {one if value == 1 else many}"
