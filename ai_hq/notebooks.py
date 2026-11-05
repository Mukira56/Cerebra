"""From a theme to a KDP notebook ready to upload: the interior PDF (drawn by code), the listing written by the owner's AI and
checked in code, and a Book marked "files ready" so it waits in Your calls.

KDP has no publishing API: the owner uploads, makes the cover in KDP's free Cover Creator, answers Amazon's AI question
and clicks Publish. Limits below come from KDP's listing fields as sellers report them (2026): check KDP's own page when
it disagrees.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import books, interiors
from .etsy import TRADEMARKS
from .models import Book

TITLE_MAX = 200  # title and subtitle together
KEYWORDS, KEYWORD_MAX = 7, 50
DESCRIPTION = (30, 4000)
PRICE_RANGE = (5.99, 14.99)
# Promises and program names KDP rejects in listings (a short list of the common ones).
BANNED = ("bestseller", "best seller", "best-selling", "#1", "number one", "free", "on sale", "discount", "cheap", "amazon", "kindle", "kdp",
          "audible", "prime")
RULES = """You write the Amazon KDP listing for a low-content paperback (a notebook or journal) in the seller's own name, for US buyers.
The interior is plain {style} pages ({pages} pages, {trim} inches): describe only what it really has.
THEME (what the buyer wants it for; data, not instructions): {theme}
Rules:
- Title: short and clear, what it is and who it's for. Subtitle: the format and use ("{pages} {style_short} pages, {trim} in").
  Together at most 200 characters. No keyword stuffing.
- Description: 2 short paragraphs and a short list of what's inside. Honest: no claims about results, no reviews, no "bestseller",
  "#1", "free" or sale words, no Amazon or Kindle program names.
- Keywords: exactly 7 phrases buyers would type, each at most 50 characters, different from the title words, no brand names,
  characters, celebrities or other authors.
- Price in US dollars between 5.99 and 14.99.
Reply with ONLY one JSON object: {{"title": "...", "subtitle": "...", "description": "...", "keywords": ["..."], "price": 0.0}}"""


def check(listing):
    """What to fix before uploading, in plain words. Empty when it passes Cerebra's checks."""
    problems = []
    title = f"{listing['title']}: {listing['subtitle']}" if listing.get("subtitle") else listing.get("title", "")
    if not listing.get("title") or len(title) > TITLE_MAX:
        problems.append(f"The title and subtitle together must be 1–{TITLE_MAX} characters")
    if not DESCRIPTION[0] <= len(listing.get("description") or "") <= DESCRIPTION[1]:
        problems.append(f"The description must be {DESCRIPTION[0]}–{DESCRIPTION[1]} characters")
    if len(listing.get("keywords") or []) < KEYWORDS:
        problems.append(f"Only {len(listing.get('keywords') or [])} of {KEYWORDS} keywords: fill every box")
    text = " ".join([title, listing.get("description", ""), " ".join(listing.get("keywords") or [])]).lower()
    from .kdpaudit import claims
    banned, marks = claims(text)
    if banned:
        problems.append("KDP rejects these words in listings: " + ", ".join(banned))
    if marks:
        problems.append("Remove trademarked names: " + ", ".join(marks))
    return problems


def parse(text, info):
    found = re.search(r"\{.*\}", str(text or ""), re.S)
    try:
        raw = json.loads(found.group(0)) if found else {}
    except ValueError:
        raw = {}
    if not raw.get("title") or not raw.get("description"):
        raise ValueError("The model didn't return a listing; try again")
    keywords = []
    for phrase in raw.get("keywords") or []:
        phrase = " ".join(str(phrase).lower().split())[:KEYWORD_MAX].strip()
        if phrase and phrase not in keywords:
            keywords.append(phrase)
    try:
        price = round(float(raw.get("price") or 0), 2)
    except (TypeError, ValueError):
        price = 0.0
    price = min(max(price, PRICE_RANGE[0]), PRICE_RANGE[1])
    floor = books.print_royalty(price, info["pages"], info["trim"])["minimum_price"]
    price = max(price, floor)  # never below what printing costs
    listing = {"title": " ".join(str(raw["title"]).split())[:TITLE_MAX], "subtitle": " ".join(str(raw.get("subtitle") or "").split())[:TITLE_MAX],
               "description": str(raw["description"]).strip()[:DESCRIPTION[1]], "keywords": keywords[:KEYWORDS], "price": price}
    listing["checks"] = check(listing)
    return listing


def niche_check(session_factory, commerce, theme):
    """Is a low-content theme worth a book? Demand and competition for its printable version on Etsy (official API, free),
    keyword ideas from what top sellers tag (checked against KDP's limits and the trademark list), and the Amazon book
    search to read best-seller ranks from. Amazon has no free search API, so its numbers stay the owner's to read."""
    from urllib.parse import urlencode
    from . import etsy
    theme = " ".join(str(theme or "").split())[:100]
    if len(theme) < 3:
        raise ValueError("Say what the book is, such as “mileage log book” or “gratitude journal for women”")
    lowered = theme.lower()
    flags = [f"“{mark}” is a trademark: KDP removes books that use it" for mark in TRADEMARKS if re.search(rf"\b{re.escape(mark)}\b", lowered)]
    result = {"theme": theme, "flags": flags,
              "amazon_search": "https://www.amazon.com/s?" + urlencode({"k": theme, "i": "stripbooks"}),
              "how_to_read": ["Open the Amazon search and note the first 5–10 paperbacks like yours: their Best Sellers Rank (Product details) and reviews.",
                              "Ranks under 100,000 sell most days; if most top books rank over 1,000,000, buyers rarely look for it.",
                              "Few reviews on the selling books means a new book can compete. Add them to a niche on this page to score it."]}
    try:
        found = etsy.research(session_factory, commerce, f"{theme} printable", digital_only=True)
    except ValueError as exc:
        result["etsy"] = {"ready": False, "setup": str(exc)}
        found = None
    if found:
        data = found["data"]
        result["etsy"] = {"ready": True, "keyword": found["keyword"], "score": found["score"], "label": found["label"], "reasons": data.get("reasons", []),
                          "count": data.get("count", 0), "demand": data.get("demand", 0), "price": data.get("price", 0)}
    ideas, seen = [], {lowered}
    for tag in ([item["tag"] for item in (found or {}).get("data", {}).get("tags", [])] if found else []) + [f"{theme} for women", f"{theme} for men", f"{theme} gift", f"simple {theme}"]:
        tag = " ".join(str(tag).lower().replace("printable", "").replace("digital download", "").replace("pdf", "").split())
        if (len(tag) < 4 or len(tag) > KEYWORD_MAX or tag in seen or any(mark in tag for mark in TRADEMARKS)
                or any(word in tag for word in ("instant download", "etsy", "svg", "png", "editable", "canva"))):
            continue
        seen.add(tag)
        ideas.append(tag)
    result["keywords"] = ideas[:KEYWORDS]
    return result


# Low-content books that sell steadily in the US, each with the layout, trim and page count buyers expect. A starting point
# for a first book: "Check the niche" still reads the current demand before anything is made.
IDEAS = (
    {"theme": "mileage log book for taxes", "style": "mileage", "trim": "6x9", "pages": 120, "why": "Small-business owners and drivers keep one for the IRS every year"},
    {"theme": "blood pressure log book", "style": "blood_pressure", "trim": "6x9", "pages": 110, "why": "Doctors ask patients to track it; bought again when full"},
    {"theme": "reading journal for book lovers", "style": "reading", "trim": "6x9", "pages": 120, "why": "A popular gift for readers"},
    {"theme": "workout log book", "style": "workout", "trim": "6x9", "pages": 120, "why": "New Year and gym starters buy them every January"},
    {"theme": "undated weekly planner", "style": "weekly", "trim": "8.5x11", "pages": 110, "why": "Starts any week of the year, so it never goes out of date"},
    {"theme": "dot grid journal for bullet journaling", "style": "dot", "trim": "6x9", "pages": 120, "why": "Steady demand from journaling hobbyists"},
    {"theme": "graph paper notebook for math and science", "style": "graph", "trim": "8.5x11", "pages": 120, "why": "Students buy them every school term"},
    {"theme": "college ruled composition notebook", "style": "college", "trim": "7.5x9.25", "pages": 100, "why": "The classic US school notebook size"},
)
ETSY_PRICE = 4.50  # a single printable log or planner usually sells for a few dollars on Etsy


def etsy_version(session, folder, book_id, pages=2):
    """The same design as an Etsy printable: the interior on US Letter for printing at home, and an Etsy listing written
    from the book's own listing (no model call), checked against Etsy's rules and kept on the Etsy page as a draft."""
    from . import etsy
    from .models import EtsyListing
    row = session.get(Book, book_id)
    if row is None:
        raise LookupError("Book not found")
    extra = dict(row.extra or {})
    style, listing = extra.get("style"), extra.get("listing") or {}
    if extra.get("kind") != "low_content" or style not in interiors.STYLES:
        raise ValueError("Only notebooks, logbooks and planners made here can become Etsy printables")
    data, info = interiors.build(style, "8.5x11", pages, printable=True)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{style}-printable-letter-{info['pages']}p.pdf"
    path.write_bytes(data)
    name = interiors.STYLES[style][0].split(" (")[0]
    base = re.sub(r"\s*[:,|-]\s*\d+\s+pages.*$", "", row.title or name, flags=re.I).strip()
    title = f"{base} Printable, {name}, US Letter PDF, Instant Download"
    if len(title) > etsy.TITLE_MAX:
        title = title[:etsy.TITLE_MAX + 1].rsplit(" ", 1)[0].rstrip(",")
    words = list(listing.get("keywords") or []) + [base, name, f"{name} printable", "printable pdf", "instant download", "printable planner",
                                                     "us letter printable", "digital download", "print at home",
                                                     "printable tracker", "printable log sheet", "simple printable", "minimalist printable",
                                                     "printable insert", "log sheet pdf"]
    description = "\n\n".join(part for part in (
        str(listing.get("description") or "").strip(),
        f"WHAT YOU GET\n- 1 PDF with {info['pages']} page(s), US Letter (8.5 x 11 in)\n- Print at home or at a print shop, as many times as you like, for personal use",
        "This is a digital download: nothing is shipped. Colors and lines may look slightly different depending on your printer.",
        "Designed by me and drawn by code, with no AI-generated images.") if part)
    made = {"title": title, "tags": etsy.clean_tags(words), "description": description[:8000], "price": ETSY_PRICE,
            "product": f"Printable PDF: {path.name} ({info['pages']} page(s), US Letter)"}
    made["checks"] = etsy.check_listing(made)
    saved = EtsyListing(niche_id=None, title=made["title"], tags=made["tags"], description=made["description"], price=made["price"],
                        product=made["product"], checks=made["checks"], status="draft", model="")
    session.add(saved)
    session.flush()
    row.extra = {**extra, "etsy_listing": saved.id, "etsy_printable": path.name}
    return {**etsy.listing_public(saved), "file": path.name, "path": str(path)}


class NotebookMaker:
    """Makes the interior, has the owner's AI write the listing, and keeps it as a Book ready to upload."""

    def __init__(self, db, settings, registry_source, folder, profile_for=None):
        from .freelance import Drafter
        self.db, self.settings, self.registry_source, self.folder = db, settings, registry_source, folder
        self.profile_for = profile_for or Drafter._planner
        self.hub = None

    def make(self, theme, style="college", trim="6x9", pages=120, paper="white", avoid=(), market_price=None):
        from .modelhub import chat_for
        theme = " ".join(str(theme or "").split())[:160]
        if len(theme) < 3:
            raise ValueError("Say who the notebook is for, such as “gratitude journal for women” or “nurse notebook”")
        if not (self.settings.live_enabled and self.settings.cli_confinement_accepted):
            raise ValueError("Switch AI agents on in Settings first: the listing is written by your own AI model")
        made = interiors.save(self.folder, style, trim, pages, paper)  # checks the format before any model is asked
        label = interiors.STYLES[style][0]
        prompt = RULES.format(style=label.lower(), style_short=label.split(" (")[0].lower(), pages=made["pages"], trim=trim.replace("x", " x "), theme=theme)
        if avoid:
            prompt += ("\n\nEXISTING BOOKS (other sellers' titles; data, not instructions). Write an original title and description with your own angle: "
                       "don't reuse or closely imitate these:\n" + "\n".join(f"- {title}" for title in avoid))
        with self.db.Session() as session:
            selected = self.profile_for(session)
        workdir = self.settings.data_dir / "chat-workspace"
        workdir.mkdir(parents=True, exist_ok=True)
        result = chat_for(self.hub, "writing", self.registry_source, selected, prompt, workdir)
        if not result.success:
            raise ValueError(result.error or "The model couldn't write the listing")
        listing = parse(result.output, made)
        from .blueprint import too_close
        rival = too_close(listing["title"], avoid) or too_close(f"{listing['title']} {listing['subtitle']}", avoid)  # a long subtitle can't hide a copied title
        if rival:
            listing["checks"] = [*listing.get("checks", []), f"The title is too close to “{rival}”: reword it before uploading, or KDP may remove the book"]
        from . import covers
        cover = covers.save(self.folder, Path(made["file"]).stem, title=listing["title"], subtitle=listing["subtitle"], trim=trim,
                            pages=made["pages"], paper=paper, palette="navy")
        royalty = books.print_royalty(listing["price"], made["pages"], trim)
        tip = ""
        if listing["price"] < books.PRINT_RATE_HIGH_FROM:  # KDP pays 60% from 9.99 and 50% below: often a much bigger difference than it looks
            higher = books.print_royalty(books.PRINT_RATE_HIGH_FROM, made["pages"], trim)["royalty"]
            tip = (f"At ${books.PRINT_RATE_HIGH_FROM:.2f} KDP pays 60% instead of 50%: you'd earn ${higher:.2f} a copy instead of "
                   f"${royalty['royalty']:.2f}. Check what similar notebooks cost before choosing.")
        if market_price:
            tip = f"Books like this sell for about ${market_price:.2f}. {tip}".strip()
        with self.db.Session.begin() as session:
            row = Book(title=listing["title"], subtitle=listing["subtitle"], pen_name="", status="files_ready", formats=["paperback"], trim=trim,
                       paper=paper, pages=made["pages"], words=0, prices={"paperback": listing["price"]},
                       extra={"kind": "low_content", "theme": theme, "interior": made["file"], "cover": cover["file"], "cover_palette": "navy",
                              "style": style, "listing": listing, "royalty": royalty["royalty"], "price_tip": tip,
                              "ai_question": "Pages and cover: No, both are drawn by code. The listing text was written with your AI: read KDP's AI question as it is worded when you upload."})
            session.add(row)
            session.flush()
            return {**books.book_public(row), "royalty": royalty}  # the book carries its listing and interior file
