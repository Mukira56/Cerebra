"""Learning from what sells: the facts of the top books in a niche become the plan for the owner's own, original book.

The owner reads the first books on Amazon's search page and pastes one per line: title, Best Sellers Rank, reviews, price and
pages. Amazon has no free search API, so these numbers stay the owner's to read. What buyers already accept can be followed
freely: the kind of book, its size, length and price. A seller's cover, words and page designs belong to them, so none of those
are read here at all, and a title too close to a competitor's is flagged before upload: KDP removes books for that.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter

from . import books
from .etsy import TRADEMARKS
from .kdpaudit import FILLER, words

SELLING_RANK = 100_000  # under this a book sells most days
MIN_BOOKS, MAX_BOOKS = 3, 30
TOO_CLOSE = 0.6  # share of the title's words in common with a competitor's
GENERIC = FILLER | frozenset("journal notebook log planner tracker diary logbook record paperback edition large size pages inches gift gifts".split())
STYLE_WORDS = (("mileage", "mileage"), ("blood pressure", "blood_pressure"), ("reading", "reading"), ("workout", "workout"), ("fitness", "workout"),
               ("gratitude", "gratitude"), ("weekly", "weekly"), ("planner", "weekly"), ("dot grid", "dot"), ("bullet", "dot"), ("graph", "graph"),
               ("sketch", "bordered"), ("draw", "draw_write"), ("large print", "large_print"), ("wide ruled", "wide"), ("composition", "college"))


def parse(text):
    """One book per line: title | rank | reviews | price | pages. A tab works as well as a bar. Missing numbers are allowed."""
    found = []
    for line in str(text or "").splitlines():
        parts = [part.strip() for part in re.split(r"\t|\|", line)]
        if len(parts[0]) < 3:
            continue
        rank, reviews, price, pages = ([books._number(part) for part in parts[1:5]] + [None] * 4)[:4]
        found.append({"title": parts[0][:200], "rank": int(rank) if rank else None, "reviews": int(reviews) if reviews is not None else None,
                      "price": price, "pages": int(pages) if pages else None})
    return found[:MAX_BOOKS]


def style_for(theme):
    theme = " ".join(str(theme or "").lower().split())
    return next((style for word, style in STYLE_WORDS if word in theme), "college")


def too_close(title, rivals):
    """The competitor's title this one is too like, or "". Words shared by every book in a niche don't count."""
    mine = words(title) - GENERIC
    for rival in rivals:
        theirs = words(rival) - GENERIC
        if len(mine & theirs) >= 2 and len(mine & theirs) / len(mine | theirs) >= TOO_CLOSE:
            return rival
    return ""


def _even(pages):
    return max(24, min(828, int(round(pages / 2)) * 2))


def analyze(theme, text):
    """What the top books have in common, and the plan for the owner's own book."""
    theme = " ".join(str(theme or "").split())[:160]
    if len(theme) < 3:
        raise ValueError("Say what the book is, such as “mileage log book”")
    rows = parse(text)
    if len(rows) < MIN_BOOKS:
        raise ValueError(f"Add at least {MIN_BOOKS} books, one per line: title | rank | reviews | price | pages")
    ranked = [row for row in rows if row["rank"]]
    selling = [row for row in ranked if row["rank"] < SELLING_RANK]
    base = selling or rows
    prices, lengths = [row["price"] for row in base if row["price"]], [row["pages"] for row in base if row["pages"]]
    reviews = [row["reviews"] for row in base if row["reviews"] is not None]
    pages = _even(statistics.median(lengths)) if lengths else 120
    price = round(statistics.median(prices), 2) if prices else None
    trim = "6x9"
    counts = Counter(word for row in rows for word in words(row["title"]) - GENERIC)
    common = [word for word, count in counts.most_common(8) if count >= 2 and word not in TRADEMARKS]
    typical_reviews = statistics.median(reviews) if reviews else None
    notes = []
    if not ranked:
        notes.append("No ranks yet: add each book's Best Sellers Rank to see whether buyers are there.")
    elif not selling:
        notes.append("None of these rank under 100,000, so few buyers are looking. Try a different niche.")
    else:
        notes.append(f"{len(selling)} of {len(ranked)} rank under 100,000, so people are buying these.")
    if typical_reviews is not None:
        notes.append(f"The sellers have about {typical_reviews:,.0f} reviews: " + ("a new book can compete." if typical_reviews < 100 else
                     "a hard market for a new book." if typical_reviews > 1000 else "room to compete with a sharper angle."))
    earning = None
    if price:
        result = books.print_royalty(price, pages, trim)
        earning = result["royalty"]
        notes.append(f"At the typical ${price:.2f} you'd earn about ${earning:.2f} a copy." if result["allowed"] else
                     f"${price:.2f} is below KDP's lowest price for {pages} pages, ${result['minimum_price']:.2f}.")
    return {"theme": theme, "books": len(rows), "selling": len(selling), "ranked": len(ranked), "price": price, "earning": earning, "reviews": typical_reviews,
            "common_words": common, "notes": notes, "plan": {"style": style_for(theme), "trim": trim, "pages": pages, "paper": "white"},
            "titles": [row["title"] for row in rows]}
