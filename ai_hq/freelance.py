"""Freelance: find paid work for the owner, automatically, and score it against what they sell.

Phase 1 of docs/FREELANCE_PLAN.md. Read-only fetchers check public job sources politely (each source keeps its own
interval: Remotive asks for at most 4 checks a day), and the owner can paste any job from Upwork, Fiverr or elsewhere.
Every lead is stored once under its source's own ID, scored 0-100 against the owner's services, keywords,
excluded words and minimum budget, with the plain reasons for the score. Nothing is sent anywhere: applying is the
owner's click (Phase 2 drafts the proposal). RemoteOK and Remotive are credited and linked as their terms ask.
"""
from __future__ import annotations

import html
import re
import threading
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from .models import Event, FreelanceLead, Metadata, now
from .security import redact

KEY = "freelance_profile"
USER_AGENT = "Cerebra (personal freelance job search; https://github.com/Mukira56/Cerebra)"
SERVICES = {
    "web": ("Websites & web apps", ["website", "web app", "landing page", "wordpress", "shopify", "woocommerce", "e-commerce", "ecommerce", "react",
                                     "next.js", "nextjs", "vue", "angular", "frontend", "front-end", "full stack", "full-stack", "django", "flask",
                                     "laravel", "php", "node", "javascript", "typescript", "html", "css", "webflow", "wix", "seo"]),
    "mobile_ai": ("Mobile & AI apps", ["mobile app", "android", "ios", "flutter", "react native", "swift", "kotlin", "ai", "artificial intelligence",
                                       "chatbot", "chat bot", "gpt", "openai", "llm", "rag", "machine learning", "automation", "zapier", "n8n",
                                       "make.com", "api integration", "integration", "python", "telegram bot", "whatsapp bot"]),
    "design": ("Design & content", ["logo", "graphic design", "branding", "brand identity", "ui design", "ux", "ui/ux", "figma", "canva", "illustration",
                                    "banner", "flyer", "copywriting", "copywriter", "content writing", "blog", "article", "social media", "video editing",
                                    "thumbnail", "presentation"]),
    "data": ("Data & tech support", ["scraping", "scraper", "web scraping", "data entry", "excel", "google sheets", "spreadsheet", "dashboard",
                                     "power bi", "tableau", "sql", "database", "data analysis", "analytics", "bug fix", "fix bug", "debug", "maintenance",
                                     "tech support", "devops", "server", "hosting", "deployment", "aws", "docker"])}
SOURCES = {
    "freelancer": {"label": "Freelancer.com", "every": 30 * 60, "url": "https://www.freelancer.com"},
    "remoteok": {"label": "Remote OK", "every": 60 * 60, "url": "https://remoteok.com"},
    "remotive": {"label": "Remotive", "every": 6 * 60 * 60, "url": "https://remotive.com"},  # their API asks for at most ~4 checks a day
    "himalayas": {"label": "Himalayas", "every": 60 * 60, "url": "https://himalayas.app"},
    "hn": {"label": "Hacker News hiring threads", "every": 3 * 60 * 60, "url": "https://news.ycombinator.com"},
}
STATUSES = {"new", "saved", "hidden", "applied", "interview", "won", "lost"}
DEFAULTS = {"services": list(SERVICES), "keywords": [], "exclude": [], "min_budget": 0.0, "currency": "USD",
            "sources": {name: True for name in SOURCES}, "checked": {}}
MAX_DESCRIPTION = 6000
GOOD = 50  # a strong match: worth a phone alert and the top of the list
TAG = re.compile(r"<[^>]+>")


def text_of(value, limit=MAX_DESCRIPTION):
    """Plain text from a job description's HTML (links and markup removed, entities decoded)."""
    value = re.sub(r"<\s*(br|p|li|div)[^>]*>", "\n", str(value or ""), flags=re.I)
    value = html.unescape(TAG.sub(" ", value)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:limit]


def _words(values, limit=60, size=60):
    return [" ".join(str(item).split()).lower()[:size] for item in (values or []) if str(item).strip()][:limit]


# ---- the owner's profile ----
def profile(session):
    row = session.get(Metadata, KEY)
    value = {**DEFAULTS, **(row.value if row else {})}
    value["sources"] = {**DEFAULTS["sources"], **(value.get("sources") or {})}
    return value


def save_profile(session, changes):
    value = profile(session)
    if "services" in changes:
        chosen = [item for item in changes["services"] or [] if item in SERVICES]
        if not chosen:
            raise ValueError("Choose at least one kind of work you sell")
        value["services"] = chosen
    for key in ("keywords", "exclude"):
        if key in changes:
            value[key] = _words(changes[key])
    if "min_budget" in changes:
        budget = float(changes["min_budget"] or 0)
        if not 0 <= budget <= 1_000_000:
            raise ValueError("Enter a minimum budget of 0 or more")
        value["min_budget"] = round(budget, 2)
    if "sources" in changes:
        value["sources"] = {name: bool((changes["sources"] or {}).get(name, value["sources"].get(name, True))) for name in SOURCES}
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return value


def keywords(settings):
    words = [word for service in settings["services"] for word in SERVICES[service][1]] + list(settings.get("keywords") or [])
    return list(dict.fromkeys(word.lower() for word in words if word.strip()))


# ---- scoring ----
def _hits(words, text):
    found = []
    for word in words:
        pattern = r"(?<![a-z0-9])" + re.escape(word.strip()) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            found.append(word.strip())
    return found


# Broad words that appear in almost any description: they count only in a job's title. ("IP Lawyer wanted" matched
# on "ai", "presentation" and "scraping" in its text and ranked as a design job.)
WEAK = {"ai", "seo", "server", "integration", "presentation", "blog", "node", "ux", "sql", "python", "automation", "database",
        "hosting", "analytics", "html", "css", "javascript", "banner", "article", "deployment", "debug", "spreadsheet", "excel", "maintenance"}
ACADEMIC = re.compile(r"\b(homework|assignment|thesis|dissertation|coursework|academic project|exam|quiz)\b", re.I)
FULL_TIME = re.compile(r"\b(full[- ]?time|permanent|salaried)\b", re.I)
FREELANCE = re.compile(r"\b(contract|contractor|freelance|freelancer|part[- ]?time|project[- ]based|gig|consultant)\b", re.I)


def score(lead, settings, now_ts=None):
    """0-100 and the reasons, so the owner sees why a job is near the top. Freelance and contract work, paying budgets,
    fresh posts and little competition rank first; salaried jobs, homework and crowded projects sink."""
    title, body = lead["title"].lower(), lead.get("description", "").lower()
    excluded = _hits(settings.get("exclude") or [], f"{title} {body}")
    if excluded:
        return 0, [f"excluded: {', '.join(excluded[:3])}"]
    words = keywords(settings)
    in_title = _hits(words, title)
    in_body = [word for word in _hits(words, body) if word not in WEAK]
    matched = list(dict.fromkeys(in_title + in_body))
    if not in_title and len(in_body) < 2:
        return 0, ["doesn't match what you sell" if not matched else f"only mentions {', '.join(matched[:3])} in passing"]
    points, reasons = min(45, 12 * len(in_title) + 4 * len(set(in_body) - set(in_title))), [f"matches {', '.join(matched[:5])}"]
    employment = str(lead.get("employment") or "")
    if lead.get("kind") == "job":
        if FREELANCE.search(employment) or FREELANCE.search(title):
            points += 10
            reasons.append("contract or freelance")
        else:
            points -= 25
            reasons.append("a salaried job, not a freelance project" if FULL_TIME.search(employment + " " + title) else "may be a salaried job")
    if ACADEMIC.search(title) or ACADEMIC.search(body[:600]):
        points -= 30
        reasons.append("looks like a student's academic work (often against platform rules)")
    low, high, minimum = lead.get("budget_min") or 0, lead.get("budget_max") or 0, settings.get("min_budget") or 0
    currency = lead.get("currency") or "USD"
    rate = float(lead.get("usd_rate") or (1.0 if currency == "USD" else 0) or 0)
    if (high or low) and lead.get("kind") != "job":
        hourly, top = lead.get("kind") == "hourly", max(low, high)
        money = f"{currency} {low:,.0f}" + (f"–{high:,.0f}" if high and high != low else "") + (" an hour" if hourly else "")
        usd = top * rate if rate else None
        if usd is not None and currency != "USD":
            money += f" (about USD {usd:,.0f})"
        value = usd if usd is not None else top
        if minimum and value < minimum:
            points -= 30
            reasons.append(f"budget {money} is below your {minimum:,.0f}")
        else:
            if value >= (40 if hourly else 500):
                points += 20
            elif value >= (15 if hourly else 100):
                points += 10
            elif value < (8 if hourly else 50):
                points -= 15
            reasons.append(f"budget {money}" + (" fits" if minimum else ""))
    elif high or low:
        reasons.append(f"salary {currency} {low:,.0f}" + (f"–{high:,.0f}" if high and high != low else ""))
    posted = lead.get("posted_at") or ""
    if posted:
        try:
            age = ((now_ts or datetime.now(timezone.utc).timestamp()) - datetime.fromisoformat(posted).timestamp()) / 3600
        except ValueError:
            age = None
        if age is not None:
            if age <= 24:
                points += 15
                reasons.append(f"posted {int(age)} h ago" if age >= 1 else "posted in the last hour")  # whole hours, like the list
            elif age <= 72:
                points += 7
                reasons.append(f"posted {int(age // 24)} days ago")
            else:
                points -= 5
                reasons.append(f"posted {int(age // 24)} days ago")
    bids = lead.get("bids")
    if bids is not None:
        if bids <= 10:
            points += 12
            reasons.append(f"only {bids} bids so far")
        elif bids >= 100:
            points -= 20
            reasons.append(f"{bids} bids already")
        elif bids >= 50:
            points -= 10
            reasons.append(f"{bids} bids already")
        else:
            reasons.append(f"{bids} bids so far")
    return max(1, min(100, points)), reasons


def rescore(session):
    """Score every open lead again (after the owner changed their profile)."""
    settings = profile(session)
    for row in session.scalars(select(FreelanceLead).where(FreelanceLead.status.in_(["new", "saved"]))).all():
        row.score, row.reasons = score(_as_lead(row), settings)


def _as_lead(row):
    extra = row.extra or {}
    return {"title": row.title, "description": row.description, "budget_min": row.budget_min, "budget_max": row.budget_max,
            "currency": row.currency, "kind": row.kind, "posted_at": row.posted_at, "bids": extra.get("bids"),
            "usd_rate": extra.get("usd_rate"), "employment": extra.get("employment")}


# ---- storing ----
def store(session, leads, settings=None):
    """Add new leads and refresh known ones (bids and budget change); the owner's status and notes are kept."""
    settings = settings or profile(session)
    added = 0
    for lead in leads:
        identifier = f"{lead['source']}:{lead['native_id']}"[:200]
        points, reasons = score(lead, settings)
        row = session.get(FreelanceLead, identifier)
        extra = {key: lead[key] for key in ("bids", "company", "credit", "usd_rate", "employment") if lead.get(key) is not None}
        if row is None:
            session.add(FreelanceLead(id=identifier, source=lead["source"], title=lead["title"][:300], url=lead["url"][:600],
                                      description=lead.get("description", "")[:MAX_DESCRIPTION], budget_min=lead.get("budget_min") or 0,
                                      budget_max=lead.get("budget_max") or 0, currency=(lead.get("currency") or "")[:3], kind=lead.get("kind") or "job",
                                      skills=lead.get("skills") or [], posted_at=lead.get("posted_at") or "", score=points, reasons=reasons,
                                      status="hidden" if points == 0 and reasons[0].startswith("excluded") else "new", extra=extra))
            added += 1
        else:
            row.budget_min, row.budget_max, row.extra = lead.get("budget_min") or 0, lead.get("budget_max") or 0, {**(row.extra or {}), **extra}
            if row.status in {"new", "saved"}:
                row.score, row.reasons = points, reasons
    return added


def paste(session, fields):
    """A job the owner found anywhere (Upwork, Fiverr, LinkedIn, a WhatsApp group): saved and scored like the rest."""
    title, description = " ".join(str(fields.get("title") or "").split())[:300], str(fields.get("description") or "").strip()
    url = str(fields.get("url") or "").strip()
    if not title or len(description) < 20:
        raise ValueError("Paste the job's title and its full description")
    if url and (not url.startswith(("https://", "http://")) or len(url) > 600 or any(c in url for c in " <>\"'")):
        raise ValueError("The job link must be a web address")
    platform = " ".join(str(fields.get("platform") or "Pasted").split())[:40]
    budget = float(fields.get("budget") or 0)
    lead = {"source": "pasted", "native_id": now() + "-" + str(abs(hash(title + description)) % 10**8), "title": title, "url": url,
            "description": description[:MAX_DESCRIPTION], "budget_min": budget, "budget_max": budget, "currency": (fields.get("currency") or profile(session)["currency"])[:3].upper(),
            "kind": "hourly" if fields.get("hourly") else "fixed", "posted_at": now(), "company": platform}
    store(session, [lead])
    return session.get(FreelanceLead, f"pasted:{lead['native_id']}"[:200])


def update(session, lead_id, changes):
    row = session.get(FreelanceLead, lead_id)
    if row is None:
        raise LookupError("Lead not found")
    if "status" in changes:
        if changes["status"] not in STATUSES:
            raise ValueError("Unknown status")
        row.status = changes["status"]
    if "notes" in changes:
        row.notes = str(changes["notes"] or "")[:2000]
    row.updated_at = now()
    return row


def public(row):
    extra = row.extra or {}
    return {"id": row.id, "source": row.source, "source_label": SOURCES.get(row.source, {}).get("label") or extra.get("company") or "Pasted",
            "title": row.title, "url": row.url, "description": row.description, "budget_min": row.budget_min, "budget_max": row.budget_max,
            "currency": row.currency, "kind": row.kind, "skills": row.skills or [], "posted_at": row.posted_at, "score": row.score,
            "reasons": row.reasons or [], "status": row.status, "notes": row.notes, "company": extra.get("company", ""), "bids": extra.get("bids"),
            "credit": extra.get("credit", ""), "proposal": row.proposal or {}, "created_at": row.created_at}


def leads(session, include_hidden=False, limit=300):
    query = select(FreelanceLead).order_by(FreelanceLead.score.desc(), FreelanceLead.posted_at.desc()).limit(limit)
    if not include_hidden:
        query = query.where(FreelanceLead.status != "hidden")
    return [public(row) for row in session.scalars(query)]


def summary(session):
    rows = session.scalars(select(FreelanceLead)).all()
    counts = {status: sum(1 for row in rows if row.status == status) for status in STATUSES}
    counts["good_matches"] = sum(1 for row in rows if row.status == "new" and row.score >= GOOD)
    return counts


# ---- fetching (read-only, polite) ----
def _iso(seconds):
    try:
        return datetime.fromtimestamp(int(seconds), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def fetch_freelancer(client, settings):
    """Freelancer.com's public project search: active projects for the owner's keywords (newest first)."""
    found, queries = [], []
    for service in settings["services"]:
        queries.append(" ".join(SERVICES[service][1][:3]))
    queries += list(settings.get("keywords") or [])[:3]
    for query in list(dict.fromkeys(queries))[:6]:
        response = client.get("https://www.freelancer.com/api/projects/0.1/projects/active/",
                              params={"query": query, "limit": 30, "full_description": "true", "job_details": "true", "sort_field": "time_updated"})
        response.raise_for_status()
        for project in (response.json().get("result") or {}).get("projects") or []:
            budget, currency = project.get("budget") or {}, project.get("currency") or {}
            found.append({"source": "freelancer", "native_id": str(project["id"]), "title": project.get("title") or "",
                          "url": "https://www.freelancer.com/projects/" + str(project.get("seo_url") or project["id"]),
                          "description": text_of(project.get("description") or project.get("preview_description")),
                          "budget_min": float(budget.get("minimum") or 0), "budget_max": float(budget.get("maximum") or budget.get("minimum") or 0),
                          "currency": currency.get("code") or "", "kind": "hourly" if project.get("type") == "hourly" else "fixed",
                          "skills": [job.get("name") for job in project.get("jobs") or [] if job.get("name")][:12],
                          "posted_at": _iso(project.get("time_submitted")), "bids": (project.get("bid_stats") or {}).get("bid_count"),
                          "usd_rate": currency.get("exchange_rate")})
    return found


def fetch_remoteok(client, settings):
    response = client.get("https://remoteok.com/api")
    response.raise_for_status()
    found = []
    for job in response.json()[1:]:  # the first item is Remote OK's legal notice
        found.append({"source": "remoteok", "native_id": str(job.get("id")), "title": f"{job.get('position', '')} · {job.get('company', '')}".strip(" ·"),
                      "url": job.get("url") or "", "description": text_of(job.get("description")), "budget_min": float(job.get("salary_min") or 0),
                      "budget_max": float(job.get("salary_max") or 0), "currency": "USD" if job.get("salary_min") else "", "kind": "job",
                      "skills": list(job.get("tags") or [])[:12], "posted_at": _iso(job.get("epoch")), "company": job.get("company", ""),
                      "credit": "via Remote OK", "employment": " ".join(tag for tag in job.get("tags") or [] if FREELANCE.search(tag) or FULL_TIME.search(tag))})
    return found


def fetch_remotive(client, settings):
    categories = {"web": "software-dev", "mobile_ai": "software-dev", "design": "design", "data": "data"}
    found = []
    for category in dict.fromkeys(categories[service] for service in settings["services"]):
        response = client.get("https://remotive.com/api/remote-jobs", params={"category": category, "limit": 60})
        response.raise_for_status()
        for job in response.json().get("jobs") or []:
            found.append({"source": "remotive", "native_id": str(job.get("id")), "title": f"{job.get('title', '')} · {job.get('company_name', '')}".strip(" ·"),
                          "url": job.get("url") or "", "description": text_of(job.get("description")), "kind": "job",
                          "skills": list(job.get("tags") or [])[:12], "posted_at": (job.get("publication_date") or "")[:19] + ("+00:00" if job.get("publication_date") else ""),
                          "company": job.get("company_name", ""), "credit": "via Remotive", "employment": str(job.get("job_type") or "").replace("_", " ")})
    return found


def fetch_himalayas(client, settings):
    response = client.get("https://himalayas.app/jobs/api", params={"limit": 50})
    response.raise_for_status()
    found = []
    for job in response.json().get("jobs") or []:
        found.append({"source": "himalayas", "native_id": str(job.get("guid") or job.get("applicationLink")), "title": f"{job.get('title', '')} · {job.get('companyName', '')}".strip(" ·"),
                      "url": job.get("applicationLink") or "", "description": text_of(job.get("description") or job.get("excerpt")),
                      "budget_min": float(job.get("minSalary") or 0), "budget_max": float(job.get("maxSalary") or 0), "currency": job.get("currency") or "",
                      "kind": "job", "skills": list(job.get("categories") or [])[:12], "posted_at": _iso(job.get("pubDate")), "company": job.get("companyName", ""),
                      "employment": str(job.get("employmentType") or "")})
    return found


def fetch_hn(client, settings):
    """This month's "Seeking freelancer" posts, and contract or freelance posts in "Who is hiring?"."""
    stories = client.get("https://hn.algolia.com/api/v1/search_by_date", params={"query": "Freelancer? Seeking freelancer?", "tags": "story", "hitsPerPage": 5})
    stories.raise_for_status()
    hiring = client.get("https://hn.algolia.com/api/v1/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": 4})
    hiring.raise_for_status()
    threads = [hit for hit in stories.json().get("hits") or [] if str(hit.get("title", "")).startswith("Ask HN: Freelancer? Seeking freelancer?")][:1]
    threads += [hit for hit in hiring.json().get("hits") or [] if str(hit.get("title", "")).startswith("Ask HN: Who is hiring?")][:1]
    found = []
    for thread in threads:
        item = client.get(f"https://hn.algolia.com/api/v1/items/{thread['objectID']}")
        item.raise_for_status()
        freelance_thread = "Freelancer?" in thread["title"]
        for comment in item.json().get("children") or []:
            text = text_of(comment.get("text"))
            if not text:
                continue
            first = text.split("\n", 1)[0]
            wanted = first.upper().startswith("SEEKING FREELANCER") if freelance_thread else re.search(r"\b(contract|contractor|freelance|part[- ]time)\b", first, re.I)
            if not wanted:
                continue
            found.append({"source": "hn", "native_id": str(comment.get("id")), "title": first[:200], "url": f"https://news.ycombinator.com/item?id={comment.get('id')}",
                          "description": text, "kind": "job", "posted_at": _iso(comment.get("created_at_i")), "company": comment.get("author", ""),
                          "employment": "freelance" if freelance_thread else first})
    return found


FETCHERS = {"freelancer": fetch_freelancer, "remoteok": fetch_remoteok, "remotive": fetch_remotive, "himalayas": fetch_himalayas, "hn": fetch_hn}


def _remember_check(session, name, info):
    value = profile(session)
    value["checked"] = {**(value.get("checked") or {}), name: info}
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))


class Finder:
    """Checks the enabled sources on their own schedules in the background; one failing source never stops the others."""
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def check(self, only=None, force=False):
        """Check the sources that are due (or `only` one, now). Returns {source: {"added", "seen"} or {"error"}}."""
        with self._lock:
            with self.db.Session() as session:
                settings = profile(session)
            results, stamp = {}, datetime.now(timezone.utc).timestamp()
            for name, fetcher in FETCHERS.items():
                if only and name != only:
                    continue
                if not settings["sources"].get(name):
                    continue
                last = (settings.get("checked") or {}).get(name) or {}
                if not force and not only and stamp - float(last.get("at_ts") or 0) < SOURCES[name]["every"]:
                    continue
                try:
                    found = fetcher(self.client, settings)
                    with self.db.Session.begin() as session:
                        added = store(session, found, settings)
                    results[name] = {"added": added, "seen": len(found)}
                except Exception as exc:  # recorded for the owner; the next source still runs
                    results[name] = {"error": redact(str(exc))[:200] or "The source could not be read"}
                with self.db.Session.begin() as session:
                    _remember_check(session, name, {"at": now(), "at_ts": stamp, **results[name]})
            added = sum(item.get("added", 0) for item in results.values())
            if added:
                with self.db.Session.begin() as session:
                    since = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
                    good = session.scalars(select(FreelanceLead).where(FreelanceLead.created_at >= since, FreelanceLead.score >= GOOD,
                                                                       FreelanceLead.status == "new")).all()
                    session.add(Event(kind="freelance", message=f"Found {added} new freelance lead(s), {len(good)} strong match(es)",
                                      data={"notify": "leads" if good else "", "count": len(good)}))
            return results

    def start(self, interval=300):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            def loop():
                while not self._stop.wait(interval):
                    try:
                        self.check()
                    except Exception:
                        pass
            self._thread = threading.Thread(target=loop, name="cerebra-freelance", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
