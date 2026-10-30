"""Prospector: US local businesses that could use what the owner sells, found in public data, kept only with a concrete
reason seen on their own website (docs/AGENTS_ARCHITECTURE.md).

Where the data comes from, and why:
- OpenStreetMap, through Nominatim (to find the city) and Overpass (to list the businesses). Both are free and the data
  may be stored under the Open Database License, with attribution. Each service's usage policy is respected: an
  identifying User-Agent, one request at a time, and pauses between them.
- The business's own public website: one page (the home page), only where robots.txt allows it, small and with a
  timeout. Only facts are kept (and where each was seen), never the page itself.

Nothing here contacts a business. Openers are drafted for the owner, who decides.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select

from .models import Event, Prospect, ProspectSearch, now

USER_AGENT = "Cerebra prospect research (one page per business, robots.txt respected; https://github.com/Mukira56/Cerebra)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
ATTRIBUTION = "Business listings © OpenStreetMap contributors (ODbL)"
MAX_PAGE = 1_000_000  # bytes read from a business's home page
PAUSE = 1.1  # seconds between requests to the same public service
CHAIN_REPEATS = 3  # a name seen this many times in one city is a chain

# Kinds of local business, as OpenStreetMap tags them.
KINDS = {
    "dentists": ("Dentists", "amenity", "dentist"), "doctors": ("Doctors' offices", "amenity", "doctors"),
    "veterinarians": ("Veterinarians", "amenity", "veterinary"), "chiropractors": ("Chiropractors", "healthcare", "chiropractor"),
    "restaurants": ("Restaurants", "amenity", "restaurant"), "cafes": ("Cafés", "amenity", "cafe"),
    "hair_salons": ("Hair salons", "shop", "hairdresser"), "beauty_salons": ("Beauty salons", "shop", "beauty"),
    "car_repair": ("Car repair shops", "shop", "car_repair"), "plumbers": ("Plumbers", "craft", "plumber"),
    "electricians": ("Electricians", "craft", "electrician"), "lawyers": ("Law firms", "office", "lawyer"),
    "accountants": ("Accountants", "office", "accountant"), "real_estate": ("Real estate agents", "office", "estate_agent"),
    "gyms": ("Gyms", "leisure", "fitness_centre"), "hotels": ("Hotels", "tourism", "hotel"),
}
STATUSES = ("new", "kept", "dropped", "contacted", "replied", "won", "lost")
BOOKING = re.compile(r"book (an |your )?(appointment|visit|online|now)|schedule (an |your )?(appointment|visit|online|now)|(request|reserve|make) (an |your )?appointment|appointment request|"
                     r"zocdoc|nexhealth|localmed|calendly|acuityscheduling|squareup\.com/appointments|vagaro|mindbody|opentable|resy\.com|"
                     r"booksy|schedulicity|setmore|fresha", re.I)
BOOKING_LINK = re.compile(r"href=[\"'][^\"']*(appointment|booking|book-now|book-online|schedule|reserv)", re.I)  # booking on another page counts
CONTACT_LINK = re.compile(r"href=[\"'][^\"']*contact", re.I)  # so does a contact page
COPYRIGHT = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.I)


# ---- fetching public pages safely ----
class Blocked(ValueError):
    """A web address that isn't a public website (a local or private address), or one robots.txt closes."""


def public_address(host):
    """True only when every address the name resolves to is on the public internet: a business's website listed in a
    public map must never make Cerebra reach into the owner's own network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(ipaddress.ip_address(address.split("%")[0]).is_global for address in addresses)


def normal_site(url):
    url = str(url or "").strip()
    if not url:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", url, re.I) and not re.match(r"^https?://", url, re.I):
        return ""  # another scheme (javascript:, mailto:, file:): not a website
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return url


class Reader:
    """Reads one public page per business, politely."""

    def __init__(self, client=None, resolve=public_address, robots=True):
        self.client = client or httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": USER_AGENT})
        self.resolve, self.robots = resolve, robots

    def _allowed(self, url):
        if not self.robots:
            return True
        parsed = urlparse(url)
        rules = urllib.robotparser.RobotFileParser()
        try:
            response = self._get(f"{parsed.scheme}://{parsed.netloc}/robots.txt", check_robots=False)
        except (Blocked, httpx.HTTPError):
            return True  # no readable robots.txt: allowed, as crawlers treat it
        if response.status_code >= 400:
            return True
        rules.parse(response.text.splitlines())
        return rules.can_fetch(USER_AGENT, url)

    def _get(self, url, check_robots=True, hops=3):
        for _ in range(hops + 1):
            host = urlparse(url).hostname or ""
            if not self.resolve(host):
                raise Blocked(f"{host} isn't a public website")
            if check_robots and not self._allowed(url):
                raise Blocked("The site's robots.txt asks robots not to read this page")
            response = self.client.get(url, headers={"User-Agent": USER_AGENT})
            if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                url, check_robots = urljoin(url, response.headers["location"]), True
                continue
            return response
        raise Blocked("Too many redirects")

    def page(self, url):
        started = time.monotonic()
        response = self._get(url)
        return {"url": str(response.url), "status": response.status_code, "html": response.text[:MAX_PAGE], "seconds": round(time.monotonic() - started, 2)}


def facts_from(page, year=None):
    """What a business's home page shows, each fact with where it was seen. Only things Cerebra can check, nothing guessed."""
    year = year or datetime.now(timezone.utc).year
    html, url, found = page["html"], page["url"], []
    if page["status"] in {401, 403, 429}:
        raise Blocked(f"The site turned away an automated reader ({page['status']}); it may work fine for people, so nothing is claimed")
    if page["status"] >= 400:
        return [{"key": "broken", "text": f"The website answers with an error ({page['status']})", "seen": url}]
    if url.startswith("http://"):
        found.append({"key": "no_https", "text": "The website isn't secure (no HTTPS): browsers mark it “Not secure”", "seen": url})
    if not re.search(r"<meta[^>]+name=[\"']viewport", html, re.I):
        found.append({"key": "no_mobile", "text": "The page has no mobile layout: it shows tiny on phones", "seen": url})
    if not BOOKING.search(html) and not BOOKING_LINK.search(html):
        found.append({"key": "no_booking", "text": "No online booking or appointment request on the home page", "seen": url})
    years = [int(value) for value in COPYRIGHT.findall(html) if 1995 <= int(value) <= year]
    if years and max(years) <= year - 3:
        found.append({"key": "outdated", "text": f"The footer says © {max(years)}: the site looks unmaintained", "seen": url})
    if not re.search(r"<form\b", html, re.I) and not re.search(r"mailto:", html, re.I) and not CONTACT_LINK.search(html):
        found.append({"key": "no_contact", "text": "No contact form, contact page or email link on the home page", "seen": url})
    # Load time isn't judged here: measured from the owner's connection, it says nothing about a US visitor's experience.
    return found


# ---- finding businesses in OpenStreetMap ----
class Finder:
    def __init__(self, db, client=None, reader=None, pause=PAUSE):
        self.db = db
        self.client = client or httpx.Client(timeout=90, headers={"User-Agent": USER_AGENT})
        self.reader, self.pause = reader or Reader(), pause

    def city_area(self, city, state):
        """The OpenStreetMap area id of a US city."""
        response = self.client.get(NOMINATIM, params={"q": f"{city}, {state}, USA", "format": "jsonv2", "limit": 5, "countrycodes": "us"},
                                   headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        places = [place for place in response.json() if place.get("osm_type") == "relation"]
        if not places:
            raise ValueError(f"OpenStreetMap doesn't know {city}, {state} as a US city")
        return 3_600_000_000 + int(places[0]["osm_id"]), places[0].get("display_name", "")

    def businesses(self, kind, area):
        _, key, value = KINDS[kind]
        query = f'[out:json][timeout:60];area({area})->.city;nwr["{key}"="{value}"]["name"](area.city);out center tags 600;'
        time.sleep(self.pause)
        response = self.client.post(OVERPASS, data={"data": query}, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        found = []
        for element in response.json().get("elements", []):
            tags = element.get("tags") or {}
            address = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
            found.append({"osm": f"{element['type']}/{element['id']}", "name": tags.get("name", "")[:200],
                          "website": normal_site(tags.get("website") or tags.get("contact:website") or tags.get("url")),
                          "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40],
                          "address": ", ".join(filter(None, [address, tags.get("addr:city")]))[:200],
                          "brand": bool(tags.get("brand") or tags.get("brand:wikidata"))})
        return found

    def search(self, kind, city, state, read_sites=True, limit=200):
        """Find, drop chains, read each remaining site once, and keep those with a concrete reason. Returns the counts."""
        if kind not in KINDS:
            raise ValueError("Choose a kind of business")
        city, state = " ".join(str(city).split())[:80], " ".join(str(state).split())[:40]
        if not city or not state:
            raise ValueError("Name the city and the state, such as Austin, Texas")
        area, place = self.city_area(city, state)
        everything = self.businesses(kind, area)
        names = {}
        for item in everything:
            names[item["name"].lower()] = names.get(item["name"].lower(), 0) + 1
        independent = [item for item in everything if not item["brand"] and names[item["name"].lower()] < CHAIN_REPEATS]
        with self.db.Session.begin() as session:
            search = ProspectSearch(kind=kind, city=city, state=state, place=place[:300],
                                    counts={"found": len(everything), "chains": len(everything) - len(independent)})
            session.add(search)
            session.flush()
            search_id = search.id
            known = {row.osm for row in session.scalars(select(Prospect)).all()}
        fresh = [item for item in independent if item["osm"] not in known][:limit]
        kept = without_site = unreadable = 0
        for item in fresh:
            facts, note, status = [], "", "dropped"
            if not item["website"]:
                # The map lists no website; the business may still have one. Not a reason to pitch until the owner checks.
                note, status, without_site = "OpenStreetMap lists no website for them. Search for it before assuming they have none.", "new", without_site + 1
            elif read_sites:
                try:
                    facts = facts_from(self.reader.page(item["website"]))
                    status = "kept" if facts else "dropped"
                except (Blocked, httpx.HTTPError) as exc:
                    note, unreadable = str(exc)[:200], unreadable + 1
                time.sleep(self.pause)
            kept += status == "kept"
            with self.db.Session.begin() as session:
                session.add(Prospect(search_id=search_id, osm=item["osm"], name=item["name"], kind=kind, city=city, state=state, website=item["website"],
                                     phone=item["phone"], address=item["address"], facts=facts, status=status, notes=note))
        with self.db.Session.begin() as session:
            row = session.get(ProspectSearch, search_id)
            row.counts = {**row.counts, "new": len(fresh), "kept": kept, "without_site": without_site, "unreadable": unreadable}
            session.add(Event(kind="prospects", message=f"Prospects: {KINDS[kind][0].lower()} in {city}, {state}: {len(everything)} found, "
                                                          f"{row.counts['chains']} chains left out, {kept} worth contacting", data={"search": search_id}))
            return {"search_id": search_id, **row.counts}


# ---- the owner's list ----
def public(row):
    return {"id": row.id, "search_id": row.search_id, "name": row.name, "kind": row.kind, "kind_label": KINDS.get(row.kind, ("",))[0], "city": row.city,
            "state": row.state, "website": row.website, "phone": row.phone, "address": row.address, "facts": row.facts or [], "status": row.status,
            "notes": row.notes, "opener": row.opener or "", "created_at": row.created_at, "updated_at": row.updated_at}


def overview(session):
    rows = session.scalars(select(Prospect).where(Prospect.status != "dropped").order_by(Prospect.updated_at.desc()).limit(500)).all()
    searches = [{"id": row.id, "kind": row.kind, "kind_label": KINDS.get(row.kind, ("",))[0], "city": row.city, "state": row.state, "counts": row.counts or {},
                 "created_at": row.created_at} for row in session.scalars(select(ProspectSearch).order_by(ProspectSearch.created_at.desc()).limit(50)).all()]
    counts = {status: 0 for status in STATUSES}
    for status in session.scalars(select(Prospect.status)).all():
        counts[status] = counts.get(status, 0) + 1
    return {"prospects": [public(row) for row in rows], "searches": searches, "counts": counts,
            "kinds": {key: label for key, (label, _, _) in KINDS.items()}, "attribution": ATTRIBUTION}


def update(session, prospect_id, fields):
    row = session.get(Prospect, prospect_id)
    if row is None:
        raise LookupError("Prospect not found")
    if "status" in fields:
        if fields["status"] not in STATUSES:
            raise ValueError("Unknown status")
        row.status = fields["status"]
    if "notes" in fields:
        row.notes = str(fields["notes"] or "")[:2000]
    row.updated_at = now()
    return public(row)
