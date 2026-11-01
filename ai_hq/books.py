"""Books: short nonfiction books for Amazon KDP, from a niche to an upload package to the royalties they earn.

Phase 1 of docs/BOOKS_PLAN.md: KDP's numbers (each with the help page it came from), the money and cover maths, niches
scored from the evidence the owner has (never guessed), and books with their formats and prices.

KDP has no publishing API, and driving its website with a bot would risk the owner's account: Cerebra prepares the
files and the listing, and the owner uploads and clicks Publish, including Amazon's AI-content disclosure.
"""
from __future__ import annotations

import math
import re
import statistics

from sqlalchemy import select

from .models import Book, BookNiche, Metadata, now

# ---- KDP's numbers for Amazon.com (checked 2026-10-30; the official page wins over any third-party figure) ----
CHECKED = "2026-10-30"
SOURCES = {
    "print_cost": "https://kdp.amazon.com/en_US/help/topic/G201834340",
    "hardcover_cost": "https://kdp.amazon.com/en_US/help/topic/GHT976ZKSKUXBB6H",
    "print_royalty": "https://kdp.amazon.com/en_US/help/topic/G201834330",
    "trim_margins": "https://kdp.amazon.com/en_US/help/topic/G201857950",
    "cover": "https://kdp.amazon.com/help/topic/G201953020",
    "ebook_royalty": "https://kdp.amazon.com/help/topic/G200634560",
    "daily_cap": "https://authorsguild.org/news/amazon-adds-to-kdp-generative-ai-policy-caps-daily-self-publishing-uploads/",
}
# Paperback trim sizes (inches, width x height) and black-ink page ranges by paper (KDP trim-size table).
PAPERBACK_TRIMS = {
    "5x8": (5.0, 8.0), "5.06x7.81": (5.06, 7.81), "5.25x8": (5.25, 8.0), "5.5x8.5": (5.5, 8.5), "6x9": (6.0, 9.0),
    "6.14x9.21": (6.14, 9.21), "6.69x9.61": (6.69, 9.61), "7x10": (7.0, 10.0), "7.44x9.69": (7.44, 9.69), "7.5x9.25": (7.5, 9.25),
    "8x10": (8.0, 10.0), "8.5x11": (8.5, 11.0),
}
PAPERBACK_PAGES = {"white": (24, 828), "cream": (24, 776)}
LETTER_PAGES = {"white": (24, 590), "cream": (24, 550)}  # 8.5 x 11 has a lower maximum
HARDCOVER_TRIMS = {"5.5x8.5", "6x9", "6.14x9.21", "7x10"}  # KDP also lists 8.25 x 11, not offered here (no matching paperback)
HARDCOVER_PAGES = (75, 550)
# Printing cost, black ink, US: fixed cost only up to 108 pages, then 1.00 (paperback) or 5.65 (hardcover) plus per page.
PAPERBACK_SHORT = {"regular": 2.30, "large": 2.84}
HARDCOVER_SHORT = {"regular": 6.80, "large": 7.49}
PER_PAGE = {"regular": 0.012, "large": 0.017}
PAPERBACK_FIXED, HARDCOVER_FIXED = 1.00, 5.65
SHORT_UNTIL = 108  # page counts are even: 110 and above use fixed + per-page
# Print royalty on Amazon.com: 50% at or below 9.98 USD, 60% at or above 9.99 USD (since 10 June 2025). Hardcover follows
# the same 50/60 split by list price (KDP's hardcover page says so without its own figures).
PRINT_RATE_HIGH_FROM, PRINT_RATE_LOW, PRINT_RATE_HIGH = 9.99, 0.50, 0.60
PRINT_MAX_PRICE = 250.0
# Kindle on Amazon.com: 70% from 2.99 to 12.99 USD (since 7 July 2026) minus delivery; 35% otherwise, no delivery cost.
EBOOK_70 = (2.99, 12.99)
EBOOK_DELIVERY_PER_MB = 0.15
EBOOK_MIN_35 = ((3, 0.99), (10, 1.99), (None, 2.99))  # by file size in MB: under 3, under 10, 10 or more
EBOOK_MAX = 200.0
# Paper thickness per page (inches) for the spine; covers need 0.125 in of bleed; spine text from 79 pages.
PAPER_THICKNESS = {"white": 0.002252, "cream": 0.0025}
COVER_BLEED, SPINE_TEXT_FROM = 0.125, 79
MARGINS = ((150, 0.375), (300, 0.5), (500, 0.625), (700, 0.75), (828, 0.875))  # inside (gutter) margin by page count
OUTSIDE_MARGIN = 0.25  # at least, with no bleed (text books have no interior bleed)
KINDLE_COVER = (1600, 2560)  # pixels, width x height: KDP's recommended 1:1.6 ideal size
DAILY_CAP = 3  # new titles a day per KDP account (KDP to the Authors Guild; can change)
WORDS_PER_PAGE = {"5x8": 250, "5.5x8.5": 280, "6x9": 320, "7x10": 400}  # rough, 11 pt body text; an estimate only


def _round(value):
    return round(value + 1e-9, 2)


def _cents_up(value):
    return math.ceil(round(value * 100, 6)) / 100


def trim_class(trim):
    width, height = PAPERBACK_TRIMS[trim]
    return "large" if width > 6.12 or height > 9.0 else "regular"


def page_range(trim, paper="white", binding="paperback"):
    if binding == "hardcover":
        return HARDCOVER_PAGES
    return (LETTER_PAGES if trim == "8.5x11" else PAPERBACK_PAGES)[paper]


def check_format(trim, pages, paper="white", binding="paperback"):
    """A plain reason when KDP won't print this, else None."""
    if trim not in PAPERBACK_TRIMS:
        return f"{trim} isn't a KDP trim size"
    if binding == "hardcover" and trim not in HARDCOVER_TRIMS:
        return f"Hardcovers come in {', '.join(sorted(HARDCOVER_TRIMS))}"
    if paper not in PAPER_THICKNESS:
        return "Choose white or cream paper"
    low, high = page_range(trim, paper, binding)
    if not low <= int(pages) <= high:
        return f"A {binding} at {trim} on {paper} paper needs {low} to {high} pages"
    return None


def print_cost(pages, trim, binding="paperback"):
    """KDP's printing cost in USD for a black-ink book sold on Amazon.com."""
    size = trim_class(trim)
    pages = int(pages)
    if binding == "hardcover":
        return HARDCOVER_SHORT[size] if pages <= SHORT_UNTIL else _round(HARDCOVER_FIXED + pages * PER_PAGE[size])
    return PAPERBACK_SHORT[size] if pages <= SHORT_UNTIL else _round(PAPERBACK_FIXED + pages * PER_PAGE[size])


def print_royalty(price, pages, trim, binding="paperback"):
    """What the owner earns on one print copy sold on Amazon.com, and how it is worked out."""
    price, cost = float(price), print_cost(pages, trim, binding)
    rate = PRINT_RATE_HIGH if price >= PRINT_RATE_HIGH_FROM else PRINT_RATE_LOW
    # The lowest price whose royalty covers printing: at 50% while that stays under 9.99, else at 60%.
    minimum = _cents_up(cost / PRINT_RATE_LOW) if cost / PRINT_RATE_LOW < PRINT_RATE_HIGH_FROM else max(PRINT_RATE_HIGH_FROM, _cents_up(cost / PRINT_RATE_HIGH))
    return {"price": price, "rate": rate, "printing": cost, "royalty": _round(rate * price - cost), "minimum_price": minimum,
            "allowed": minimum <= price <= PRINT_MAX_PRICE}


def ebook_royalty(price, size_mb=1.0):
    price, size = float(price), max(0.01, float(size_mb))
    minimum = next(low for limit, low in EBOOK_MIN_35 if limit is None or size < limit)
    if EBOOK_70[0] <= price <= EBOOK_70[1]:
        delivery = _round(size * EBOOK_DELIVERY_PER_MB)
        return {"price": price, "rate": 0.70, "delivery": delivery, "royalty": _round(0.70 * (price - delivery)), "minimum_price": minimum,
                "allowed": True}
    return {"price": price, "rate": 0.35, "delivery": 0.0, "royalty": _round(0.35 * price), "minimum_price": minimum,
            "allowed": minimum <= price <= EBOOK_MAX}


def spine_width(pages, paper="white"):
    return round(int(pages) * PAPER_THICKNESS[paper], 4)


def cover_size(trim, pages, paper="white"):
    """The full-wrap paperback cover in inches: bleed + back + spine + front + bleed, by bleed + height + bleed."""
    width, height = PAPERBACK_TRIMS[trim]
    spine = spine_width(pages, paper)
    return {"width": round(2 * COVER_BLEED + 2 * width + spine, 4), "height": round(2 * COVER_BLEED + height, 4), "spine": spine,
            "spine_text": int(pages) >= SPINE_TEXT_FROM}


def inside_margin(pages):
    return next(margin for limit, margin in MARGINS if int(pages) <= limit)


def estimate_pages(words, trim="6x9"):
    """Printed pages for a word count: an estimate (front matter, chapter openings and headings add some)."""
    per_page = WORDS_PER_PAGE.get(trim) or WORDS_PER_PAGE["6x9"]
    body = -(-int(words) // per_page)
    pages = body + 8 + 12  # front and back matter, and part-empty chapter openings
    return max(24, pages + pages % 2)


def calculate(fields):
    """Every format's earnings for one book, for the Books page's calculator and each book's card."""
    trim, paper = str(fields.get("trim") or "6x9"), str(fields.get("paper") or "white")
    pages = int(fields.get("pages") or 0) or estimate_pages(int(fields.get("words") or 25000), trim)
    result = {"trim": trim, "paper": paper, "pages": pages, "pages_estimated": not fields.get("pages")}
    problem = check_format(trim, pages, paper)
    if problem:
        return {**result, "problem": problem}
    prices = fields.get("prices") or {}
    if prices.get("paperback"):
        result["paperback"] = print_royalty(prices["paperback"], pages, trim)
    if prices.get("hardcover"):
        issue = check_format(trim, pages, paper, "hardcover")
        result["hardcover"] = {"problem": issue} if issue else print_royalty(prices["hardcover"], pages, trim, "hardcover")
    if prices.get("kindle"):
        result["kindle"] = ebook_royalty(prices["kindle"], fields.get("size_mb") or 1.0)
    result["cover"] = cover_size(trim, pages, paper)
    result["margins"] = {"inside": inside_margin(pages), "outside": OUTSIDE_MARGIN}
    return result


# ---- settings and the "Start publishing" checklist ----
KEY = "books_settings"
CHECKLIST = (
    ("kdp_account", "Create your KDP account", "At kdp.amazon.com, with your own name and details (the pen name goes on the books, not the account)."),
    ("tax", "Complete the tax interview", "In KDP: Account › Tax information. As a US person you fill in form W-9 with your Social Security number (or your business's EIN). "
            "Amazon sends you a 1099 for royalties each year; report them on your tax return."),
    ("payments", "Add how KDP pays you", "In KDP: Account › Getting paid. Add your US bank account (routing and account number) for direct deposit."),
    ("pen_name", "Choose your pen name", "One pen name per niche keeps each niche's books together on Amazon."),
    ("keepa", "Add a Keepa API key (optional)", "Keepa gives sales rank and price history for competing books. Without it, type the numbers from Amazon yourself."),
    ("images", "Add an image API key", "For cover artwork, in Business connections. Cerebra sets the title text itself."),
)
DEFAULTS = {"pen_names": [], "daily_cap": DAILY_CAP, "done": [], "default_trim": "6x9", "default_paper": "white"}


def settings(session):
    row = session.get(Metadata, KEY)
    value = {**DEFAULTS, **(row.value if row else {})}
    return value


def save_settings(session, fields):
    value = settings(session)
    if "pen_names" in fields:
        value["pen_names"] = list(dict.fromkeys(_clean(name, 80) for name in fields["pen_names"] or [] if _clean(name, 80)))[:20]
    if "done" in fields:
        value["done"] = [key for key, _, _ in CHECKLIST if key in set(fields["done"] or [])]
    if "daily_cap" in fields:
        value["daily_cap"] = max(1, min(10, int(fields["daily_cap"] or DAILY_CAP)))
    for key, allowed in (("default_trim", PAPERBACK_TRIMS), ("default_paper", PAPER_THICKNESS)):
        if key in fields:
            if fields[key] not in allowed:
                raise ValueError(f"Unknown {key.replace('default_', '')}: {fields[key]}")
            value[key] = fields[key]
    row = session.get(Metadata, KEY)
    if row is None:
        session.add(Metadata(key=KEY, value=value))
    else:
        row.value = value
    return value


def checklist(session):
    done = set(settings(session)["done"])
    return [{"key": key, "title": title, "how": how, "done": key in done} for key, title, how in CHECKLIST]


# ---- niches: one reader, one problem, scored from evidence ----
TRENDS = {"rising": (15, "searches are rising"), "flat": (10, "steady searches for years: a lasting market"),
          "fad": (-20, "a spike that fell: probably a fad"), "": (0, "search trend not checked")}
NICHE_STATUSES = {"idea", "researching", "chosen", "dropped"}


def _clean(value, size):
    return " ".join(str(value or "").split())[:size]


def _number(value):
    text = re.sub(r"[^\d.]", "", str(value or ""))
    try:
        return float(text) if text else None
    except ValueError:
        return None


def parse_competitors(text):
    """Lines of "Title | Best Sellers Rank | reviews | paperback price | Kindle price", as the owner reads them on Amazon."""
    books = []
    for line in str(text or "").splitlines():
        parts = [part.strip() for part in line.split("|")]
        if not parts[0]:
            continue
        rank, reviews, paperback, kindle = ([_number(part) for part in parts[1:5]] + [None] * 4)[:4]
        books.append({"title": parts[0][:200], "bsr": int(rank) if rank else None, "reviews": int(reviews) if reviews is not None else None,
                      "paperback": paperback, "kindle": kindle})
    return books[:30]


def score_niche(niche, trim="6x9"):
    """0-100 and its reasons, only from what the owner has entered (Keepa fills it in Phase 2). Missing evidence says so."""
    points, reasons = 30, []
    books = [book for book in niche.get("competitors") or [] if book.get("bsr")]
    if books:
        ranks = sorted(book["bsr"] for book in books)
        median, selling = statistics.median(ranks), sum(1 for rank in ranks if rank < 100_000)
        if median < 30_000:
            points += 30
            reasons.append(f"top books sell well (median rank {median:,.0f})")
        elif median < 100_000:
            points += 20
            reasons.append(f"top books sell (median rank {median:,.0f})")
        elif median < 300_000:
            points += 5
            reasons.append(f"slow sellers (median rank {median:,.0f})")
        elif median > 1_000_000:
            points -= 25
            reasons.append(f"almost nobody buys (median rank {median:,.0f})")
        else:
            reasons.append(f"weak sales (median rank {median:,.0f})")
        reasons.append(f"{selling} of {len(ranks)} competing books rank under 100,000")
        reviews = [book["reviews"] for book in books if book.get("reviews") is not None and book["bsr"] < 100_000]
        if reviews:
            typical = statistics.median(reviews)
            if typical < 100:
                points += 15
                reasons.append(f"sellers have few reviews ({typical:,.0f}): a new book can compete")
            elif typical > 1000:
                points -= 10
                reasons.append(f"sellers have many reviews ({typical:,.0f}): hard to compete")
    else:
        reasons.append("sales not checked: add competing books with their Best Sellers Rank")
    bonus, why = TRENDS.get(niche.get("trend") or "", TRENDS[""])
    points += bonus
    reasons.append(why)
    prices = [book["paperback"] for book in niche.get("competitors") or [] if book.get("paperback")]
    if prices:
        typical = statistics.median(prices)
        profit = print_royalty(typical, 120, trim)["royalty"]
        if profit >= 5:
            points += 10
        elif profit < 2:
            points -= 10
        reasons.append(f"a 120-page paperback at the typical {typical:.2f} USD earns {profit:.2f} USD a copy")
    if not (niche.get("reader") and niche.get("problem")):
        points -= 10
        reasons.append("name one reader and one problem")
    return max(1, min(100, points)), reasons


def niche_public(row):
    return {"id": row.id, "area": row.area, "reader": row.reader, "problem": row.problem, "trend": row.trend, "notes": row.notes,
            "competitors": row.competitors or [], "score": row.score, "reasons": row.reasons or [], "status": row.status,
            "created_at": row.created_at, "updated_at": row.updated_at}


def _apply_niche(row, fields, trim):
    for key, size in (("area", 120), ("reader", 200), ("problem", 300)):
        if key in fields:
            setattr(row, key, _clean(fields[key], size))
    if "notes" in fields:
        row.notes = str(fields["notes"] or "")[:4000]
    if "trend" in fields:
        if fields["trend"] not in TRENDS:
            raise ValueError("Trend is rising, flat, fad, or not checked")
        row.trend = fields["trend"]
    if "competitors" in fields:
        row.competitors = parse_competitors(fields["competitors"]) if isinstance(fields["competitors"], str) else list(fields["competitors"] or [])[:30]
    if "status" in fields:
        if fields["status"] not in NICHE_STATUSES:
            raise ValueError("Unknown niche status")
        row.status = fields["status"]
    if not row.area:
        raise ValueError("Name the area, such as “sleep after menopause”")
    row.score, row.reasons = score_niche(niche_public(row), trim)
    row.updated_at = now()


def create_niche(session, fields):
    row = BookNiche(area="", reader="", problem="", trend="", notes="", competitors=[], status="idea")
    _apply_niche(row, fields, settings(session)["default_trim"])
    session.add(row)
    session.flush()
    return niche_public(row)


def update_niche(session, niche_id, fields):
    row = session.get(BookNiche, niche_id)
    if row is None:
        raise LookupError("Niche not found")
    _apply_niche(row, fields, settings(session)["default_trim"])
    return niche_public(row)


def delete_niche(session, niche_id):
    row = session.get(BookNiche, niche_id)
    if row is None:
        raise LookupError("Niche not found")
    if session.scalars(select(Book).where(Book.niche_id == niche_id)).first():
        raise ValueError("This niche has books: drop it instead of deleting it")
    session.delete(row)


# ---- books ----
BOOK_STATUSES = ("planned", "writing", "files_ready", "published", "retired")
FORMATS = ("paperback", "kindle", "hardcover")


def book_public(row):
    extra = row.extra or {}
    fields = {"trim": row.trim, "paper": row.paper, "pages": row.pages or 0, "words": row.words or 0, "prices": row.prices or {}}
    return {"id": row.id, "niche_id": row.niche_id, "title": row.title, "subtitle": row.subtitle, "pen_name": row.pen_name, "status": row.status,
            "formats": row.formats or [], "trim": row.trim, "paper": row.paper, "pages": row.pages, "words": row.words, "prices": row.prices or {},
            "asins": extra.get("asins", {}), "published_at": extra.get("published_at", ""), "earnings": calculate(fields),
            "kind": extra.get("kind", ""), "listing": extra.get("listing") or {}, "price_tip": extra.get("price_tip", ""), "interior": extra.get("interior", ""), "ai_question": extra.get("ai_question", ""),
            "created_at": row.created_at, "updated_at": row.updated_at}


def _apply_book(row, fields):
    for key, size in (("title", 200), ("subtitle", 200), ("pen_name", 80)):
        if key in fields:
            setattr(row, key, _clean(fields[key], size))
    if "trim" in fields:
        if fields["trim"] not in PAPERBACK_TRIMS:
            raise ValueError(f"{fields['trim']} isn't a KDP trim size")
        row.trim = fields["trim"]
    if "paper" in fields:
        if fields["paper"] not in PAPER_THICKNESS:
            raise ValueError("Choose white or cream paper")
        row.paper = fields["paper"]
    for key in ("pages", "words"):
        if key in fields:
            setattr(row, key, max(0, int(fields[key] or 0)))
    if "formats" in fields:
        row.formats = [name for name in FORMATS if name in set(fields["formats"] or [])]
    if "prices" in fields:
        prices = {}
        for name, value in (fields["prices"] or {}).items():
            amount = _number(value)
            if name in FORMATS and amount:
                prices[name] = round(amount, 2)
        row.prices = prices
    if "status" in fields:
        if fields["status"] not in BOOK_STATUSES:
            raise ValueError("Unknown book status")
        row.status = fields["status"]
        if row.status == "published" and not (row.extra or {}).get("published_at"):
            row.extra = {**(row.extra or {}), "published_at": now()}
    if "asins" in fields:
        asins = {name: _clean(value, 20).upper() for name, value in (fields["asins"] or {}).items() if name in FORMATS and _clean(value, 20)}
        if any(not re.fullmatch(r"[A-Z0-9]{10}|97[89]\d{10}", value) for value in asins.values()):
            raise ValueError("An ASIN is 10 letters and digits; an ISBN is 13 digits starting 978 or 979")
        row.extra = {**(row.extra or {}), "asins": asins}
    if not row.title:
        raise ValueError("Give the book a working title")
    pages = row.pages or estimate_pages(row.words or 25000, row.trim)
    problem = check_format(row.trim, pages, row.paper)
    if problem and row.pages:
        raise ValueError(problem)
    row.updated_at = now()


def create_book(session, fields):
    defaults = settings(session)
    niche_id = fields.get("niche_id") or None
    if niche_id and session.get(BookNiche, niche_id) is None:
        raise LookupError("Niche not found")
    row = Book(niche_id=niche_id, title="", subtitle="", pen_name="", status="planned", formats=["paperback", "kindle"],
               trim=defaults["default_trim"], paper=defaults["default_paper"], pages=0, words=0, prices={}, extra={})
    _apply_book(row, fields)
    session.add(row)
    session.flush()
    return book_public(row)


def update_book(session, book_id, fields):
    row = session.get(Book, book_id)
    if row is None:
        raise LookupError("Book not found")
    cap = settings(session)["daily_cap"]
    if fields.get("status") == "published" and row.status != "published" and published_today(session) >= cap:
        raise ValueError(f"KDP allows {cap} new titles a day: publish this one tomorrow")
    _apply_book(row, fields)
    return book_public(row)


def delete_book(session, book_id):
    row = session.get(Book, book_id)
    if row is None:
        raise LookupError("Book not found")
    if row.status == "published":
        raise ValueError("A published book can't be deleted: mark it retired")
    session.delete(row)


def published_today(session, today=None):
    day = (today or now())[:10]
    return sum(1 for row in session.scalars(select(Book).where(Book.status == "published")).all()
               if str((row.extra or {}).get("published_at", ""))[:10] == day)


def overview(session):
    niches = [niche_public(row) for row in session.scalars(select(BookNiche).order_by(BookNiche.score.desc())).all()]
    items = [book_public(row) for row in session.scalars(select(Book).order_by(Book.updated_at.desc())).all()]
    value = settings(session)
    return {"settings": value, "checklist": checklist(session), "niches": niches, "books": items,
            "today": {"published": published_today(session), "cap": value["daily_cap"]},
            "options": {"trims": list(PAPERBACK_TRIMS), "hardcover_trims": sorted(HARDCOVER_TRIMS), "papers": list(PAPER_THICKNESS),
                        "statuses": list(BOOK_STATUSES), "formats": list(FORMATS)},
            "sources": SOURCES, "checked": CHECKED}


def glance(session):
    """The Overview's Books card."""
    from sqlalchemy import func
    counts = dict(session.execute(select(Book.status, func.count()).group_by(Book.status)).all())
    niches = session.scalar(select(func.count()).select_from(BookNiche).where(BookNiche.status.in_(["idea", "researching", "chosen"]))) or 0
    return {"niches": niches, **{status: counts.get(status, 0) for status in BOOK_STATUSES}}
