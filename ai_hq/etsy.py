"""Etsy niche finder: what sells, and how crowded it is, from Etsy's own public listings (docs/ETSY_AMAZON_PLAN.md, phase 1).

One search per keyword through Etsy's official Open API v3 (`findAllListingsActive`), with only the owner's app key
(keystring and shared secret); no shop login and nothing written to Etsy. From the total number of active listings
and the top results Cerebra works out:
- competition: how many active listings match;
- demand: favourites per month on the top listings (Etsy publishes favourites, not sales, so this is the honest proxy);
- prices (median and spread, in US dollars) and how many are digital downloads;
- the tags top sellers use, and longer keywords taken from them to check next.

Titles and tags are written by other sellers: they are shown to the owner as data and never followed as instructions.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlencode

from sqlalchemy import select

from . import vault
from .models import EtsyNiche, now

SEARCH = "https://api.etsy.com/v3/application/listings/active"
SAMPLE = 100  # Etsy's largest page: one call per keyword (the app's limit is a few thousand calls a day)
TOP = 24  # the first page a buyer sees: where demand is measured
MONTH = 30 * 24 * 3600


def credentials(commerce):
    """The x-api-key header from the owner's Etsy app (Business connections › Etsy)."""
    try:
        item = commerce.config("etsy")
    except ValueError:
        item = {}
    if not item.get("api_key") or not item.get("shared_secret"):
        raise ValueError("Save your Etsy app's keystring and shared secret in Business connections › Etsy first "
                         "(etsy.com/developers › Create a new app). Research needs only these: no shop login.")
    return {"x-api-key": vault.unprotect(item["api_key"]) + ":" + vault.unprotect(item["shared_secret"])}


def _price(item):
    money = item.get("converted_price") or item.get("price") or {}
    try:
        return round(float(money.get("amount", 0)) / float(money.get("divisor") or 1), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def analyze(keyword, count, results, moment=None):
    """Competition, demand, prices and tags for one keyword, with a 0-100 opportunity score and the reasons for it."""
    moment = (moment or datetime.now(timezone.utc)).timestamp()
    keyword = " ".join(str(keyword).lower().split())
    rates, prices, digital, tags = [], [], 0, Counter()
    for position, item in enumerate(results):
        created = item.get("original_creation_timestamp") or item.get("creation_timestamp") or moment
        months = max(1.0, (moment - float(created)) / MONTH)
        if position < TOP:
            rates.append(int(item.get("num_favorers") or 0) / months)
        price = _price(item)
        if price:
            prices.append(price)
        digital += item.get("listing_type") in {"download", "both"}
        tags.update({" ".join(str(tag).lower().split()) for tag in item.get("tags") or [] if str(tag).strip()})
    tags.pop(keyword, None)
    demand = round(statistics.median(rates), 1) if rates else 0.0
    price = round(statistics.median(prices), 2) if prices else 0.0
    spread = (round(min(prices), 2), round(max(prices), 2)) if prices else (0.0, 0.0)
    share = round(100 * digital / len(results)) if results else 0

    reasons, points = [], 0
    points += min(55, round(14 * math.log2(1 + demand)))
    reasons.append(f"top listings gain about {demand:g} favourite(s) a month" + (" (strong demand)" if demand >= 8 else " (little demand)" if demand < 1 else ""))
    for limit, bonus, words in ((3000, 35, "few competitors"), (15000, 25, "a moderate number of competitors"),
                                (50000, 12, "many competitors"), (float("inf"), 0, "a crowded search")):
        if count < limit:
            points += bonus
            reasons.append(f"{count:,} active listings: {words}")
            break
    if price >= 5:
        points += 10
        reasons.append(f"median price USD {price:.2f}: worth the listing fee")
    elif prices:
        reasons.append(f"median price USD {price:.2f}: low, so each sale earns little after fees")
    score = max(0, min(100, points))
    label = "strong" if score >= 60 else "test" if score >= 40 else "weak"
    common = [{"tag": tag, "uses": uses} for tag, uses in sorted(tags.items(), key=lambda item: (-item[1], item[0]))[:15]]  # ties alphabetically: a stable list
    longer = [item["tag"] for item in common if len(item["tag"].split()) >= 2 and item["uses"] >= 3][:8]
    return {"keyword": keyword, "count": count, "demand": demand, "price": price, "spread": spread, "digital_share": share,
            "score": score, "label": label, "reasons": reasons, "tags": common, "longer": longer,
            "examples": [{"title": str(item.get("title") or "")[:140], "favorites": int(item.get("num_favorers") or 0), "price": _price(item)}
                         for item in results[:8]]}


def search(commerce, keyword, digital_only=False):
    """One read of Etsy's public search, as a buyer in the US sees it (prices in US dollars)."""
    keyword = " ".join(str(keyword or "").split())[:80]
    if len(keyword) < 2:
        raise ValueError("Type a keyword to research, such as “wedding planner printable”")
    headers = credentials(commerce)
    query = {"keywords": keyword, "limit": SAMPLE, "sort_on": "score", "sort_order": "desc", "currency": "USD", "buyer_country": "US", "is_safe": "true"}
    data = commerce.request("GET", f"{SEARCH}?{urlencode(query)}", headers=headers)
    results = [item for item in data.get("results") or [] if not digital_only or item.get("listing_type") in {"download", "both"}]
    return analyze(keyword, int(data.get("count") or 0), results)


def public(row):
    return {"id": row.id, "keyword": row.keyword, "digital_only": row.digital_only, "score": row.score, "label": row.label,
            "data": row.data or {}, "notes": row.notes, "updated_at": row.updated_at}


def research(session_factory, commerce, keyword, digital_only=False):
    """Research a keyword and keep it (the same keyword again refreshes it)."""
    found = search(commerce, keyword, digital_only)
    with session_factory.begin() as session:
        row = session.scalars(select(EtsyNiche).where(EtsyNiche.keyword == found["keyword"], EtsyNiche.digital_only.is_(bool(digital_only)))).first()
        if row is None:
            row = EtsyNiche(keyword=found["keyword"], digital_only=bool(digital_only))
            session.add(row)
        row.score, row.label, row.data, row.updated_at = found["score"], found["label"], found, now()
        session.flush()
        return public(row)


def niches(session):
    return [public(row) for row in session.scalars(select(EtsyNiche).order_by(EtsyNiche.score.desc(), EtsyNiche.updated_at.desc())).all()]
