"""Company pitches: offer your service to companies by email, from your own Gmail.

The owner says what they offer (a language, data, translation or any other service) and writes one pitch. Cerebra then:
1. Finds companies: a starter list of AI, language-data and translation companies, then every company Wikidata lists in
   artificial intelligence, machine learning, language technology or translation (free public data, no key needed).
2. Reads each company's own website, politely (robots.txt respected, at most a few pages, a pause between them): its public
   role addresses (partnerships@, vendors@, hello@...) and its pages for vendors, partners, linguists and contributors.
   A person's own address is never used and nothing is guessed: a company that publishes no role address gets no email.
3. Sends the pitch from the owner's Gmail, with their name, postal address and an opt-out line (US CAN-SPAM), within a
   daily number that starts low to protect the Gmail account. One follow-up goes into the same thread if nobody answers.
   A reply stops it and tells the owner; "no thanks" or a bounce puts the address on the do-not-contact list for good.
Application forms are listed for the owner to open and fill in: they ask for a person (and often a CAPTCHA), so Cerebra
never submits them. "Mark as applied" keeps track.
"""
from __future__ import annotations

import html as html_module
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select

from . import deliverability
from .models import Event, Metadata, PartnerCompany, now

KEY = "partner_settings"
MAX_PER_DAY, PER_RUN, RESEARCH_PER_RUN, PAGES_PER_COMPANY = 30, 3, 4, 4
SECONDS_PER_COMPANY = 40  # a slow site gets what was read by then, so one company never holds up the rest
CONTACT_GUESSES = ("/contact", "/contact-us")  # read when the home page links no contact page
PAUSE_BOUNCES, BOUNCE_WINDOW = 3, 30
PLACEHOLDERS = ("{company}", "{website}")
DEFAULTS = {"enabled": False, "mode": "send", "per_day": 10, "follow_up_days": 6, "offer": "", "subject": "", "body": "", "follow_up": ""}
MODES = ("send", "review")
DEFAULT_FOLLOW_UP = ("Hello again {company} team,\n\nI'm following up on my note below in case it reached the wrong inbox. If someone else at "
                     "{company} looks after vendors, partnerships or data, I'd be grateful if you could pass it on or point me to them.\n\nThank you.")
SENT_STAGES = ("sent", "followed_up", "replied", "opted_out", "bounced")
WAITING = ("sent", "followed_up")

# AI, language-data and translation companies that commonly buy language work. Public names and home pages only:
# whatever is written to them comes from their own websites, read when the owner asks.
STARTER = (
    ("Appen", "https://www.appen.com"), ("TELUS Digital", "https://www.telusdigital.com"), ("Scale AI", "https://scale.com"),
    ("Toloka", "https://toloka.ai"), ("Defined.ai", "https://www.defined.ai"), ("LXT", "https://www.lxt.ai"), ("Sama", "https://www.sama.com"),
    ("CloudFactory", "https://www.cloudfactory.com"), ("iMerit", "https://imerit.net"), ("Shaip", "https://www.shaip.com"),
    ("Surge AI", "https://www.surgehq.ai"), ("DataAnnotation", "https://www.dataannotation.tech"), ("Prolific", "https://www.prolific.com"),
    ("Labelbox", "https://labelbox.com"), ("Snorkel AI", "https://snorkel.ai"), ("Invisible Technologies", "https://www.invisible.co"),
    ("Turing", "https://www.turing.com"), ("Mercor", "https://www.mercor.com"), ("Welocalize", "https://www.welocalize.com"),
    ("Lionbridge", "https://www.lionbridge.com"), ("RWS", "https://www.rws.com"), ("TransPerfect", "https://www.transperfect.com"),
    ("Gengo", "https://gengo.com"), ("Unbabel", "https://unbabel.com"), ("DeepL", "https://www.deepl.com"), ("Summa Linguae", "https://summalinguae.com"),
    ("Andovar", "https://www.andovar.com"), ("Globalme", "https://www.globalme.net"), ("CLEAR Global", "https://clearglobal.org"),
    ("Lelapa AI", "https://lelapa.ai"), ("Smartcat", "https://www.smartcat.com"), ("Lilt", "https://lilt.com"), ("Acolad", "https://www.acolad.com"),
    ("Argos Multilingual", "https://www.argosmultilingual.com"), ("Alconost", "https://alconost.com"), ("Keywords Studios", "https://www.keywordsstudios.com"),
    ("Cohere", "https://cohere.com"), ("Hugging Face", "https://huggingface.co"), ("ElevenLabs", "https://elevenlabs.io"),
    ("Speechmatics", "https://www.speechmatics.com"), ("AssemblyAI", "https://www.assemblyai.com"), ("Deepgram", "https://deepgram.com"),
    ("Rev", "https://www.rev.com"), ("Mistral AI", "https://mistral.ai"), ("AI21 Labs", "https://www.ai21.com"),
)
WIKIDATA = "https://query.wikidata.org/sparql"


def contact_site():
    """Wikimedia asks every automated reader for a way to reach its maker: the public release channel's website."""
    from .updater import release_repository
    try:
        owner, _, name = release_repository().partition("/")
    except (ValueError, OSError):
        owner = name = ""
    return f"https://{owner.lower()}.github.io/{name}/" if owner and name else "https://github.com/"


LANGUAGE_FIELDS = {"Q7553", "Q79798", "Q30642", "Q189436"}  # translation, machine translation, language processing, speech recognition
AI_FIELDS = {"Q11660", "Q2539", "Q2878974"}  # artificial intelligence, machine learning, deep learning
QUERY = ("SELECT ?item ?itemLabel ?site ?field WHERE { VALUES ?field { " + " ".join(f"wd:{key}" for key in sorted(LANGUAGE_FIELDS | AI_FIELDS)) + " } "
         "?item wdt:P452 ?field; wdt:P856 ?site. FILTER NOT EXISTS { ?item wdt:P576 ?ended } "
         'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }')
NOT_A_HOME = re.compile(r"(^|\.)(wikipedia\.org|wikidata\.org|facebook\.com|twitter\.com|x\.com|linkedin\.com|github\.com|youtube\.com|instagram\.com|medium\.com)$")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LINK = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TAGS = re.compile(r"<[^>]+>")
# Pages worth reading for an address or an application: (pattern over the link and its words, how useful, is it a page that takes applications)
PAGE_KINDS = (
    (re.compile(r"vendor|supplier|procurement|become[ -]?a[ -]?partner|partner[ -]?with|partnership", re.I), 5, True),
    (re.compile(r"linguist|translators|interpreters|contributor|annotator|transcriber|freelanc|work[ -]?with[ -]?us|join[ -]?(our|the)?[ -]?(community|team|network)|"
                r"become[ -]?a|find[ -]?work|apply", re.I), 4, True),
    (re.compile(r"careers?|jobs|opportunit", re.I), 2, True),
    (re.compile(r"contact|get[ -]?in[ -]?touch|talk[ -]?to|reach[ -]?us|enquir|inquir", re.I), 3, False),
    (re.compile(r"about|company|partners?\b", re.I), 1, False),
)
NOT_A_POLICY = re.compile(r"code of conduct|privacy|policy|notice|terms|cookie|security|statement|guide|e-?book|white ?paper|blog|webinar|case[ -]?stud|report|podcast|news", re.I)
NOT_A_PAGE = re.compile(r"^(mailto|tel|javascript):|\.(pdf|jpe?g|png|gif|svg|webp|zip|mp4)(\?|$)|/(login|signin|sign-in|cart|privacy|terms|cookie)", re.I)
# Role addresses, best first. A company's own inbox for this kind of message; never a person's.
ROLES = (("partner", "partnership", "bd", "bizdev", "business", "alliances", "collaborat"),
         ("vendor", "supplier", "procurement", "purchasing", "resourcing", "linguist", "language", "localization", "localisation", "translation",
          "translator", "data", "datasets", "crowd", "community", "recruit", "vm"),
         ("sales", "enquir", "inquir"),
         ("hello", "hi", "info", "contact", "team", "office", "general", "mail"),
         ("careers", "jobs", "talent", "hr", "people"))
NEVER = re.compile(r"^(support|help|helpdesk|privacy|legal|security|abuse|press|media|pr|invest|ir|noreply|no-reply|donotreply|do-not-reply|dpo|gdpr|"
                   r"billing|accounts|accounting|finance|payments|compliance|webmaster|admin|postmaster|hostmaster|unsubscribe|dmca|copyright|trust|"
                   r"data[._-]?protection|dataprivacy)(?![a-z])", re.I)
SHORT = 3  # a role word this short must be the whole name (hi@, bd@, hr@), or it would match people such as hilda@ or vmorris@


def settings(session):
    row = session.get(Metadata, KEY)
    return {**DEFAULTS, **(row.value if row else {})}


def check_template(subject, body, follow_up=""):
    """What's wrong with the pitch, in plain words (empty when it can go out)."""
    problems = []
    if not subject.strip():
        problems.append("Write a subject line")
    if len(body.strip()) < 60:
        problems.append("Write the email (at least a few sentences)")
    for text in (subject, body, follow_up):
        for item in re.findall(r"\{[^{}]*\}", text):
            if item not in PLACEHOLDERS:
                problems.append(f"{item} isn't filled in by Cerebra: use {{company}} or {{website}}, or type the words yourself")
        for item in re.findall(r"\[[^\[\]\n]{1,40}\]", text):
            problems.append(f"Replace {item} with your own words")
    return list(dict.fromkeys(problems))


def save_settings(session, changes):
    value = settings(session)
    if "enabled" in changes:
        if not isinstance(changes["enabled"], bool):
            raise ValueError("Enabled must be true or false")
        value["enabled"] = changes["enabled"]
    if "mode" in changes:
        if changes["mode"] not in MODES:
            raise ValueError("Choose to send automatically or to review each one")
        value["mode"] = changes["mode"]
    if "per_day" in changes:
        try:
            number = int(changes["per_day"])
        except (TypeError, ValueError):
            raise ValueError("Emails a day must be a number") from None
        if not 1 <= number <= MAX_PER_DAY:
            raise ValueError(f"Send between 1 and {MAX_PER_DAY} a day: more than that risks your Gmail account being limited")
        value["per_day"] = number
    if "follow_up_days" in changes:
        try:
            days = int(changes["follow_up_days"] or 0)
        except (TypeError, ValueError):
            raise ValueError("Follow-up days must be a number") from None
        if days and not 3 <= days <= 30:
            raise ValueError("Follow up after 3 to 30 days, or 0 for no follow-up")
        value["follow_up_days"] = days
    for key, limit in (("offer", 600), ("subject", 150), ("body", 4000), ("follow_up", 2000)):
        if key in changes:
            value[key] = str(changes[key] or "").replace("\r\n", "\n").strip()[:limit]
    problems = check_template(value["subject"], value["body"], value["follow_up"]) if value["subject"] or value["body"] else []
    if problems:
        raise ValueError("; ".join(problems))
    row = session.get(Metadata, KEY)
    if row is None:
        session.add(Metadata(key=KEY, value=value))
    else:
        row.value = value
    return value


def domain_of(url):
    return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")


def own_address(email, domain):
    """An address at the company's own domain (or a subdomain of it)."""
    at = email.rsplit("@", 1)[-1]
    return bool(domain) and (at == domain or at.endswith("." + domain) or domain.endswith("." + at))


def role_rank(email):
    """How good this address is for a pitch (0 is best), or None for a person's own address or one that's for something else."""
    local = email.split("@", 1)[0].lower()
    if NEVER.match(local):
        return None
    flat = re.sub(r"[^a-z]", "", local)
    for rank, words in enumerate(ROLES):
        if any(flat == word or (len(word) > SHORT and flat.startswith(word)) for word in words):
            return rank
    return None


def best_email(found):
    ranked = sorted((role_rank(email), index, email) for index, email in enumerate(found) if role_rank(email) is not None)
    return ranked[0][2] if ranked else ""


def _text(fragment):
    return " ".join(html_module.unescape(TAGS.sub(" ", fragment)).split())


def ours(email, domains):
    return any(own_address(email, domain) for domain in domains)


def links(page, domains):
    """Pages on the company's own site worth reading: [(how useful, url, words, takes applications)], most useful first."""
    found = {}
    for href, label in LINK.findall(page["html"]):
        href = html_module.unescape(href.strip())
        if NOT_A_PAGE.search(href):
            continue
        url = urljoin(page["url"], href).split("#", 1)[0]
        if not url.startswith(("http://", "https://")) or not ours("x@" + domain_of(url), domains) or url.rstrip("/") == page["url"].rstrip("/"):
            continue
        words = _text(label).replace("�", "")[:50].strip()
        key = f"{urlparse(url).path} {words}"
        if NOT_A_POLICY.search(key):
            continue
        for pattern, score, applies in PAGE_KINDS:
            if pattern.search(key):
                if url not in found or found[url][0] < score:
                    found[url] = (score, url, words or urlparse(url).path.strip("/"), applies)
                break
    return sorted(found.values(), key=lambda item: -item[0])


def hidden_emails(page_html):
    """Addresses a site's CDN hides from robots in the page source but shows to every visitor (an XOR with the first byte)."""
    found = []
    for code in re.findall(r"data-cfemail=[\"']([0-9a-fA-F]+)|email-protection#([0-9a-fA-F]+)", page_html):
        code = code[0] or code[1]
        try:
            key = int(code[:2], 16)
            found.append("".join(chr(int(code[index:index + 2], 16) ^ key) for index in range(2, len(code), 2)))
        except ValueError:
            continue
    return found


def emails_in(page_html, domains):
    from .outreach import tidy_email
    seen = []
    for raw in EMAIL.findall(page_html.replace("%40", "@").replace("&#64;", "@").replace("[at]", "@")) + hidden_emails(page_html):
        email = tidy_email(raw)
        if email and ours(email, domains) and email not in seen:
            seen.append(email)
    return seen


def describe(page_html):
    match = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']+)", page_html, re.I) or \
        re.search(r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+name=[\"']description", page_html, re.I) or re.search(r"<title[^>]*>(.*?)</title>", page_html, re.I | re.S)
    return _text(match.group(1))[:240] if match else ""


def read_company(reader, website, pause=1.1):
    """What the company's own site shows: {"emails", "email", "pages", "about"}, or {"problem"} when it can't be read."""
    from .prospects import Blocked
    domain = domain_of(website)
    try:
        home = reader.page(website)
    except Blocked as exc:
        return {"problem": str(exc)}
    except (httpx.HTTPError, ValueError, OSError):
        return {"problem": "The website couldn't be reached"}
    if home["status"] in {401, 403, 429}:
        return {"problem": f"The site turned away an automated reader ({home['status']}): open it yourself"}
    if home["status"] >= 400:
        return {"problem": f"The website answers with an error ({home['status']})"}
    domains = {item for item in (domain, domain_of(home["url"])) if item}  # a renamed company redirects to its new domain
    found, started = emails_in(home["html"], domains), time.monotonic()
    candidates = links(home, domains)
    applying, labels = [], set()
    for _, url, words, applies in candidates:
        if applies and words.lower() not in labels:
            labels.add(words.lower())
            applying.append({"url": url, "label": words})
    contact = [url for _, url, _, applies in candidates if not applies][:1] or [urljoin(home["url"], path) for path in CONTACT_GUESSES]
    for url in [*contact, *[item["url"] for item in applying[:PAGES_PER_COMPANY - 1]]]:
        if time.monotonic() - started > SECONDS_PER_COMPANY:
            break
        time.sleep(pause)
        try:
            page = reader.page(url)
        except Exception:  # noqa: BLE001 - one page that can't be read doesn't stop the others
            continue
        if page["status"] < 400:
            found += [email for email in emails_in(page["html"], domains) if email not in found]
    roles = [email for email in found if role_rank(email) is not None]
    return {"emails": roles, "email": best_email(roles), "pages": applying[:6], "about": describe(home["html"])}


def compose(session, company, text, subject=""):
    """The email as it goes out: the owner's words for this company, then their details and the opt-out line."""
    from .prospects import footer
    fill = lambda value: value.replace("{company}", company.name).replace("{website}", company.domain or company.website)  # noqa: E731
    return fill(subject), f"{fill(text).strip()}\n\n—\n{footer(session)[0]}"


class Partners:
    def __init__(self, db, gmail, notifier=None, reader=None, client=None):
        self.db, self.gmail, self.notifier = db, gmail, notifier
        self.reader, self.pause, self.starter = reader, 1.1, STARTER
        from .network import LazyClient
        from . import __version__
        self.client = client or LazyClient(timeout=90, headers={"User-Agent": f"Cerebra/{__version__} ({contact_site()}; company research)",
                                                                "Accept": "application/sparql-results+json"})
        self.mail_check = deliverability.MailCheck()
        self.status = {"state": "idle", "message": "", "at": ""}
        self.search = {"running": False, "message": "", "checked": 0, "found": 0}
        self._lock, self._research = threading.Lock(), threading.Lock()

    def _reader(self):
        if self.reader is None:
            from .prospects import Reader
            self.reader = Reader()
        return self.reader

    def _note(self, message, state="idle"):
        self.status = {"state": state, "message": message, "at": now()}
        return {"state": state, "message": message}

    # ---- finding companies ----
    def add(self, session, name, website, source="you", rank=0):
        """Adds a company once (by its domain). Returns it, or None when it's already listed or isn't a website."""
        from .prospects import normal_site
        website, name = normal_site(website), " ".join(str(name or "").split())[:120]
        domain = domain_of(website)
        if not website or not domain or NOT_A_HOME.search(domain):
            return None
        if session.scalars(select(PartnerCompany).where(PartnerCompany.domain == domain)).first():
            return None
        row = PartnerCompany(name=name or domain, website=website, domain=domain, source=source, rank=rank)
        session.add(row)
        session.flush()
        return row

    def discover(self):
        """The starter list, then Wikidata's AI and language companies. Returns how many were new."""
        added = 0
        with self.db.Session.begin() as session:
            for name, website in self.starter:
                added += self.add(session, name, website, "starter list", 0) is not None
        response = self.client.get(WIKIDATA, params={"query": QUERY, "format": "json"})
        if response.status_code != 200:
            raise ValueError(f"Wikidata didn't answer ({response.status_code}); the starter list is ready, try finding more later")
        best = {}
        for item in response.json().get("results", {}).get("bindings", []):
            name, site = item.get("itemLabel", {}).get("value", ""), item.get("site", {}).get("value", "")
            field = item.get("field", {}).get("value", "").rsplit("/", 1)[-1]
            if not name or re.fullmatch(r"Q\d+", name) or not site:
                continue
            rank = 1 if field in LANGUAGE_FIELDS else 2
            key = item.get("item", {}).get("value", name)
            if key not in best or rank < best[key][2]:
                best[key] = (name, site, rank)
        with self.db.Session.begin() as session:
            for name, site, rank in sorted(best.values(), key=lambda value: (value[2], value[0].lower())):
                added += self.add(session, name, site, "Wikidata", rank) is not None
            session.add(Event(kind="partners", message=f"Found {added} new companies to pitch", data={}))
        return added

    def research_some(self, limit=RESEARCH_PER_RUN):
        """Reads the next few companies' websites for their role addresses and application pages."""
        if not self._research.acquire(blocking=False):
            return {"checked": 0, "found": 0, "skipped": "already reading"}
        try:
            with self.db.Session() as session:
                todo = [(row.id, row.website) for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status == "new")
                                                                          .order_by(PartnerCompany.rank, PartnerCompany.created_at)).all()[:limit]]
            found = 0
            for index, (company_id, website) in enumerate(todo):
                if index:
                    time.sleep(self.pause)
                seen = read_company(self._reader(), website, self.pause)
                with self.db.Session.begin() as session:
                    row = session.get(PartnerCompany, company_id)
                    if row is None or row.status != "new":
                        continue
                    row.checked_at = row.updated_at = now()
                    if seen.get("problem"):
                        row.status, row.notes = "unreadable", seen["problem"]
                        continue
                    row.emails, row.email, row.pages, row.about = seen["emails"], seen["email"], seen["pages"], seen["about"]
                    row.status = "ready" if row.email else "forms" if row.pages else "none"
                    found += bool(row.email)
            return {"checked": len(todo), "found": found}
        finally:
            self._research.release()

    def start_search(self, find=True, limit=40):
        """In the background: find companies (when asked), then read up to `limit` of their websites. The page shows progress."""
        if self.search.get("running"):
            return {"message": "Already looking: this page shows progress."}
        self.search = {"running": True, "message": "Finding companies…", "checked": 0, "found": 0}

        def work():
            try:
                added = self.discover() if find else 0
                checked = found = 0
                while checked < limit:
                    self.search["message"] = f"{added} new companies listed. Reading their websites: {checked} read, {found} with an email so far…"
                    result = self.research_some(min(4, limit - checked))
                    if not result["checked"]:
                        break
                    checked, found = checked + result["checked"], found + result["found"]
                    self.search.update(checked=checked, found=found)
                self.search["message"] = f"Done: {added} new companies listed; {checked} websites read, {found} with an email to pitch. " + \
                    ("Press again to read more." if checked >= limit else "")
            except (httpx.HTTPError, ValueError) as exc:
                self.search["message"] = f"Stopped: {exc if isinstance(exc, ValueError) else 'the internet connection dropped'}. Press again to carry on."
            except Exception as exc:  # noqa: BLE001 - a background search must say why it stopped, never vanish
                self.search["message"] = f"Stopped: {type(exc).__name__}. Press again to carry on."
            finally:
                self.search["running"] = False
        threading.Thread(target=work, daemon=True, name="partner-search").start()
        return {"message": "Looking for companies. This page shows progress."}

    # ---- sending ----
    def ready(self, session):
        """What still stops a pitch going out, in plain words (empty when it can)."""
        from .outreach import Outreach
        rules = settings(session)
        problems = Outreach.can_send(session)
        if not rules["subject"] or not rules["body"]:
            problems.append("Write your pitch (subject and email) on this page")
        return problems + check_template(rules["subject"], rules["body"], rules["follow_up"]) if rules["subject"] else problems

    def sent_today(self, session):
        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        return sum(1 for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status.in_(SENT_STAGES))).all()
                   for item in row.sent or [] if item.get("at", "") >= since)

    def limit(self, session):
        """The owner's daily number, or less while this kind of sending builds up (a new pattern of mail is watched closely)."""
        rules = settings(session)
        firsts = [row.sent[0]["at"] for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status.in_(SENT_STAGES))).all() if row.sent]
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(min(firsts))).days if firsts else 0
        return next((min(rules["per_day"], cap) for days, cap in deliverability.RAMP if age < days), rules["per_day"])

    def health(self, session):
        rows = sorted((row for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status.in_(SENT_STAGES))).all() if row.sent),
                      key=lambda row: row.sent[0]["at"], reverse=True)[:BOUNCE_WINDOW]
        cleared = settings(session).get("cleared_at", "")
        bounced = sum(row.status == "bounced" and row.sent[0]["at"] > cleared for row in rows)
        paused = bounced >= PAUSE_BOUNCES
        return {"paused": paused, "bounced": bounced, "reason": f"{bounced} of your last {len(rows)} pitches bounced, so automatic sending has stopped to protect your Gmail." if paused else ""}

    def send_to(self, company_id, to=None, subject=None, text=None):
        """One pitch to one company: the owner's click, or the next one in line. Raises ValueError with the reason it can't."""
        from .outreach import blocked
        with self.db.Session() as session:
            problems = self.ready(session) if subject is None else self.ready_to_send_by_hand(session)
            if problems:
                raise ValueError("; ".join(problems))
            row = session.get(PartnerCompany, company_id)
            if row is None:
                raise LookupError("Company not found")
            if row.status in SENT_STAGES:
                raise ValueError(f"{row.name} was already emailed: the follow-up and any reply are in the same thread")
            if row.status in {"dropped", "applied"} and subject is None:
                raise ValueError(f"{row.name} is marked {row.status}")
            to = str(to or row.email or "").strip().lower()
            if not EMAIL.fullmatch(to):
                raise ValueError(f"{row.name} has no email to send to: type one, or apply on their website")
            stop = blocked(session)
            if to in stop["emails"] or to.split("@", 1)[1] in stop["domains"]:
                raise ValueError(f"{to} asked not to be contacted, or bounced before: Cerebra won't write to it")
            rules = settings(session)
            subject_out, body = compose(session, row, rules["body"] if text is None else str(text), rules["subject"] if subject is None else str(subject))
            if text is not None and check_template(subject_out, body):
                raise ValueError("; ".join(check_template(subject_out, body)))
            follow_days, name = rules["follow_up_days"], row.name
        if not self.mail_check.can_receive(to):
            with self.db.Session.begin() as session:
                row = session.get(PartnerCompany, company_id)
                row.status, row.notes, row.updated_at = "skipped", f"{to.split('@', 1)[1]} can't receive email", now()
            raise ValueError(f"{to.split('@', 1)[1]} can't receive email, so this would bounce; {name} is set aside")
        sent = self.gmail.send(to, subject_out[:150], body)
        with self.db.Session.begin() as session:
            row = session.get(PartnerCompany, company_id)
            row.email, row.thread_id, row.status = to, sent.get("thread_id", ""), "sent"
            row.sent = [{"at": now(), "subject": subject_out[:150], "body": body, "message_id": sent.get("message_id", "")}]
            row.next_at = (datetime.now(timezone.utc) + timedelta(days=follow_days)).isoformat() if follow_days else ""
            row.updated_at = now()
            session.add(Event(kind="partners", message=f"Pitched {name} ({to})", data={"company": company_id}))
        return {"message": f"Sent to {name} at {to} from your Gmail." + (f" One follow-up goes in {follow_days} days if they don't answer." if follow_days else "")}

    def ready_to_send_by_hand(self, session):
        from .outreach import Outreach
        return Outreach.can_send(session)

    def send_next(self, count):
        """Sends to the next companies in line, within today's number. Returns what happened."""
        with self.db.Session() as session:
            problems = self.ready(session)
            if problems:
                raise ValueError("; ".join(problems))
            room = self.limit(session) - self.sent_today(session)
            if self.health(session)["paused"]:
                raise ValueError(self.health(session)["reason"] + " Check the bounced addresses, then resume.")
            queue = [row.id for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status == "ready").order_by(PartnerCompany.rank, PartnerCompany.checked_at)).all()]
        count = min(int(count or 0), room, len(queue))
        if room <= 0:
            return {"sent": 0, "message": "Today's emails are sent; more tomorrow."}
        sent, problems = 0, []
        for company_id in queue:
            if sent >= count:
                break
            try:
                self.send_to(company_id)
                sent += 1
            except ValueError as exc:
                problems.append(str(exc))
                if "Gmail" in str(exc):
                    break  # Gmail itself said no: stop, don't try the rest
        message = f"Sent {sent} pitch(es)." + (f" Skipped: {'; '.join(problems[:3])}" if problems else "") + ("" if queue else " Nobody is waiting: find companies first.")
        return {"sent": sent, "message": message}

    def follow_ups(self, room):
        with self.db.Session() as session:
            rules = settings(session)
            due = [row.id for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status == "sent", PartnerCompany.next_at != "")).all()
                   if row.next_at <= datetime.now(timezone.utc).isoformat()][:max(0, room)]
        from .outreach import blocked
        done = 0
        for company_id in due:
            with self.db.Session() as session:
                row = session.get(PartnerCompany, company_id)
                stop = blocked(session)
                if row.email in stop["emails"] or row.email.split("@", 1)[-1] in stop["domains"]:
                    with self.db.Session.begin() as change:
                        change.get(PartnerCompany, company_id).next_at = ""
                    continue
                first = (row.sent or [{}])[0]
                subject = first.get("subject", "")
                _, body = compose(session, row, rules["follow_up"] or DEFAULT_FOLLOW_UP)
                to, thread, last = row.email, row.thread_id, (row.sent or [{}])[-1].get("message_id") or None
            sent = self.gmail.send(to, subject if subject.lower().startswith("re:") else f"Re: {subject}", body, thread_id=thread or None, reply_to_message_id=last)
            with self.db.Session.begin() as session:
                row = session.get(PartnerCompany, company_id)
                row.sent = [*(row.sent or []), {"at": now(), "subject": subject, "body": body, "message_id": sent.get("message_id", ""), "follow_up": True}]
                row.status, row.next_at, row.updated_at = "followed_up", "", now()
            done += 1
        return done

    def check_replies(self):
        from . import gmail as gmail_module
        from .outreach import AUTO_REPLY, BOUNCE, OPT_OUT, block
        with self.db.Session() as session:
            me = gmail_module.load(session).get("email", "").lower()
            since = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
            rows = [(row.id, row.thread_id, row.email) for row in session.scalars(select(PartnerCompany).where(PartnerCompany.status.in_(WAITING))).all()
                    if row.thread_id and row.updated_at >= since]
        found = 0
        for company_id, thread_id, email in rows:
            try:
                messages = self.gmail.thread(thread_id)
            except ValueError:
                continue  # a thread the owner deleted, or Gmail busy for a moment: the others are still read
            answers = [item for item in messages if "SENT" not in item["labels"] and not (me and me in item["from"].lower())]
            if not answers:
                continue
            answer = answers[-1]
            if AUTO_REPLY.search(answer["subject"]) and not BOUNCE.search(answer["from"]):
                continue  # an out-of-office note isn't an answer
            text = f"{answer['subject']}\n{answer['snippet']}"
            with self.db.Session.begin() as session:
                row = session.get(PartnerCompany, company_id)
                if BOUNCE.search(answer["from"]) or BOUNCE.search(answer["subject"]):
                    stage = "bounced"
                    row.status, note = "bounced", f"The pitch to {row.name} bounced; {email} is off the list"
                    block(session, email, "bounced")
                elif OPT_OUT.search(text):
                    stage = "opted_out"
                    row.status, note = "opted_out", f"{row.name} asked not to be contacted: they won't be written to again"
                    block(session, email, "asked not to be contacted")
                else:
                    stage = "replied"
                    row.status, note = "replied", f"{row.name} replied to your pitch: {answer['snippet'][:160]}"
                    found += 1
                row.reply = {"from": answer["from"][:200], "snippet": answer["snippet"][:600], "at": now()}
                row.next_at, row.updated_at = "", now()
                session.add(Event(kind="partners", message=note, data={"company": company_id}))
            if self.notifier and stage == "replied":
                self.notifier.send("A company replied to your pitch", note[:300] + " Answer it from your Gmail.", tags="email")
        return found

    def tick(self):
        if not self._lock.acquire(blocking=False):
            return {"skipped": "already running"}
        try:
            with self.db.Session() as session:
                rules = settings(session)
                waiting = session.scalars(select(PartnerCompany).where(PartnerCompany.status.in_(WAITING))).first() is not None
                if not rules["enabled"] and not waiting:
                    return {"skipped": "off"}
                problems = self.ready(session) if rules["enabled"] else self.ready_to_send_by_hand(session)
                unread = session.scalars(select(PartnerCompany).where(PartnerCompany.status == "new")).first() is not None
                listed = session.scalars(select(PartnerCompany)).first() is not None
            if problems:
                return self._note("Waiting for you: " + "; ".join(problems), "waiting")
            replies = self.check_replies() if waiting else 0
            if rules["enabled"] and not self.search.get("running"):
                if not listed:
                    try:
                        self.discover()
                    except (ValueError, httpx.HTTPError):
                        pass  # the starter list is in; Wikidata is asked again next time
                if unread or not listed:
                    self.research_some()
            with self.db.Session() as session:
                room = min(PER_RUN, self.limit(session) - self.sent_today(session))
                health = self.health(session)
            if health["paused"]:
                return {**self._note(f"Paused: {health['reason']} Replies are still read.", "waiting"), "replies": replies}
            if room <= 0:
                return {**self._note("Today's pitches are sent; more tomorrow."), "replies": replies}
            sending = rules["enabled"] and rules["mode"] == "send"  # switched off, or "only when I press Send": nothing goes on its own
            sent = self.follow_ups(room) if sending else 0
            if sending and sent < room:
                sent += self.send_next(room - sent)["sent"]
            return {**self._note(f"Sent {sent} email(s); {replies} new repl(ies)."), "sent": sent, "replies": replies}
        except ValueError as exc:
            return self._note(f"Stopped: {exc}", "error")
        except httpx.HTTPError:
            return self._note("Couldn't reach the internet. Cerebra tries again on the next run.", "error")
        finally:
            self._lock.release()

    # ---- the owner's own changes ----
    def update(self, company_id, changes):
        with self.db.Session.begin() as session:
            row = session.get(PartnerCompany, company_id)
            if row is None:
                raise LookupError("Company not found")
            if "email" in changes:
                email = str(changes["email"] or "").strip().lower()
                if email and not EMAIL.fullmatch(email):
                    raise ValueError("That isn't an email address")
                if row.status in SENT_STAGES:
                    raise ValueError("This company was already emailed")
                row.email = email
                row.status = "ready" if email else ("forms" if row.pages else "none")
            if "status" in changes:
                if changes["status"] not in {"applied", "dropped", "ready", "forms"}:
                    raise ValueError("Mark it applied, dropped or back in line")
                if row.status in SENT_STAGES and changes["status"] != "applied":
                    raise ValueError("This company was already emailed")
                row.status = "ready" if changes["status"] in {"ready", "forms"} and row.email else "forms" if changes["status"] in {"ready", "forms"} else changes["status"]
            if "notes" in changes:
                row.notes = str(changes["notes"] or "")[:2000]
            row.updated_at = now()
            return public(row)

    def page_for(self, company_id, url):
        with self.db.Session() as session:
            row = session.get(PartnerCompany, company_id)
            if row is None:
                raise LookupError("Company not found")
            known = [row.website, *[item.get("url", "") for item in row.pages or []]]
        if url not in known:
            raise ValueError("Only the company's own website and the pages found on it can be opened from here")
        return url

    def resume(self):
        with self.db.Session.begin() as session:
            value = settings(session)
            value["cleared_at"] = now()
            row = session.get(Metadata, KEY)
            if row is None:
                session.add(Metadata(key=KEY, value=value))
            else:
                row.value = value
        return {"message": "Automatic sending resumed."}

    def overview(self, session):
        from .prospects import footer
        rows = session.scalars(select(PartnerCompany)).all()
        counts = {}
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        order = {"replied": 0, "ready": 1, "forms": 2, "sent": 3, "followed_up": 3, "applied": 4, "new": 5}
        rows = sorted(rows, key=lambda row: (order.get(row.status, 6), row.rank, row.name.lower()))
        rules = settings(session)
        sample = next((row for row in rows if row.status == "ready"), None)
        preview = compose(session, sample, rules["body"], rules["subject"]) if sample and rules["body"] else None
        return {"settings": {key: value for key, value in rules.items() if key != "cleared_at"}, "counts": counts, "total": len(rows),
                "companies": [public(row) for row in rows[:600]], "ready": self.ready(session), "sent_today": self.sent_today(session),
                "limit": self.limit(session), "max_per_day": MAX_PER_DAY, "health": self.health(session), "status": self.status,
                "search": dict(self.search), "signature": footer(session)[0], "default_follow_up": DEFAULT_FOLLOW_UP,
                "preview": {"company": sample.name, "to": sample.email, "subject": preview[0], "body": preview[1]} if preview else None}


def public(row):
    return {"id": row.id, "name": row.name, "website": row.website, "domain": row.domain, "source": row.source, "status": row.status,
            "email": row.email, "emails": row.emails or [], "pages": row.pages or [], "about": row.about, "notes": row.notes,
            "sent": [{"at": item.get("at", ""), "subject": item.get("subject", ""), "body": item.get("body", ""), "follow_up": bool(item.get("follow_up"))} for item in row.sent or []],
            "next_at": row.next_at, "reply": row.reply or {}, "checked_at": row.checked_at}
