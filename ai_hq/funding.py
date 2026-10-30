"""Funding: free credits, grants and accelerators the owner could apply to, and what each still needs from them
(docs/AGENTS_ARCHITECTURE.md, "Funding, sponsors and Cerebra's own model").

The programs are a short, hand-checked list: each with its official page and the date it was checked, because amounts and
windows change. Readiness compares each program's requirements with the owner's own facts and Cerebra's real records
(money earned, clients won). Nothing is applied to: the owner submits every application.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from .models import Metadata

CHECKED = "2026-10-30"
# Requirement keys: company (a registered company), website (a working company website), product (something live people use),
# developer (someone who writes code: the owner counts), african (an African citizen or resident, 18+), self_funded (no outside
# investors yet), young (founded in the last 10 years), revenue (paying customers), aws_paid (an AWS account on a paid plan).
PROGRAMS = [
    {"key": "google_cloud", "name": "Google for Startups Cloud Program", "kind": "credits", "url": "https://cloud.google.com/startup",
     "gives": "Google Cloud credits: up to USD 200,000 over two years (Scale), up to USD 350,000 for AI-first startups. Third-party models on Vertex AI aren't covered.",
     "needs": ["company", "website", "young"], "window": "Rolling: apply any time", "equity": False},
    {"key": "aws_activate", "name": "AWS Activate (Founders)", "kind": "credits", "url": "https://aws.amazon.com/startups/credits",
     "gives": "USD 1,000 in AWS credits for self-funded startups; select startups up to USD 5,000 over time.",
     "needs": ["company", "website", "young", "self_funded", "aws_paid"], "window": "Rolling: apply any time", "equity": False},
    {"key": "microsoft", "name": "Microsoft for Startups Founders Hub", "kind": "credits", "url": "https://foundershub.startups.microsoft.com",
     "gives": "Azure credits from about USD 1,000, growing up to USD 150,000 as you reach milestones, plus GitHub and Microsoft 365 benefits. No funding required.",
     "needs": ["website", "product"], "window": "Rolling: apply any time", "equity": False},
    {"key": "nvidia", "name": "NVIDIA Inception", "kind": "credits", "url": "https://www.nvidia.com/en-us/startups/",
     "gives": "Free membership: partner GPU cloud credits (requested one by one, not automatic), discounts on NVIDIA products and training, introductions to investors.",
     "needs": ["company", "website", "developer", "young"], "window": "Rolling: apply any time", "equity": False},
    {"key": "tef", "name": "Tony Elumelu Foundation Entrepreneurship Programme", "kind": "grant", "url": "https://www.tonyelumelufoundation.org",
     "gives": "USD 5,000 non-refundable seed capital, 12 weeks of online business training and a mentor.",
     "needs": ["african"], "window": "Once a year: the 2026 call closed on 1 March 2026; watch for the next one (usually opens in January)", "equity": False},
    {"key": "google_africa", "name": "Google for Startups Accelerator: Africa", "kind": "accelerator", "url": "https://startup.google.com/programs/accelerator/africa/",
     "gives": "A 12-week accelerator for AI-first startups (seed to Series A): mentors, Google Cloud credits, early access to AI products. Takes no equity.",
     "needs": ["african", "company", "product", "revenue"], "window": "Once a year: the 2026 call closed on 18 March 2026", "equity": False},
    {"key": "ycombinator", "name": "Y Combinator", "kind": "accelerator", "url": "https://www.ycombinator.com/deal",
     "gives": "USD 500,000: USD 125,000 for 7% of the company plus USD 375,000 on an uncapped SAFE (most-favoured-nation terms). Funded companies usually incorporate in the US.",
     "needs": ["product"], "window": "Several batches a year: see ycombinator.com/apply for the next deadline", "equity": True},
]
NEEDS = {
    "company": "a registered company", "website": "a working company website", "product": "a live product people use",
    "developer": "someone who writes code (you count)", "african": "African citizenship or residence (18+)", "self_funded": "no outside investors yet",
    "young": "a company founded in the last 10 years", "revenue": "paying customers", "aws_paid": "an AWS account on a paid plan",
}
FACTS_KEY = "funding_facts"
FACT_FIELDS = ("company", "company_country", "website", "product", "founded_year", "african", "self_funded", "aws_paid")
APPLIED_KEY = "funding_applied"


def facts(session):
    row = session.get(Metadata, FACTS_KEY)
    value = {"company": False, "company_country": "", "website": "", "product": False, "founded_year": 0, "african": False, "self_funded": True,
             "aws_paid": False, **(row.value if row else {})}
    return value


def save_facts(session, fields):
    value = facts(session)
    for key in ("company", "product", "african", "self_funded", "aws_paid"):
        if key in fields:
            value[key] = bool(fields[key])
    if "company_country" in fields:
        value["company_country"] = " ".join(str(fields["company_country"] or "").split())[:60]
    if "website" in fields:
        site = str(fields["website"] or "").strip()[:200]
        if site and not site.lower().startswith(("http://", "https://")):
            site = "https://" + site
        value["website"] = site
    if "founded_year" in fields:
        year = int(fields["founded_year"] or 0)
        if year and not 1950 <= year <= date.today().year:
            raise ValueError("The year your company was founded looks wrong")
        value["founded_year"] = year
    row = session.get(Metadata, FACTS_KEY)
    if row is None:
        session.add(Metadata(key=FACTS_KEY, value=value))
    else:
        row.value = value
    return value


def evidence(session):
    """What Cerebra's own records show, so readiness doesn't rest on the owner's word alone where it can be checked."""
    from . import money
    from .models import FreelanceLead, Product
    summary = money.summary(session)
    earned = {currency: entry.get("earned_year", 0) for currency, entry in (summary.get("by_currency") or {}).items() if entry.get("earned_year")}
    sales = sum(len(product.sales or []) for product in session.scalars(select(Product)).all())
    won = session.scalar(select(__import__("sqlalchemy").func.count()).select_from(FreelanceLead).where(FreelanceLead.status == "won")) or 0
    return {"earned_this_year": earned, "product_sales": sales, "jobs_won": won, "paying_customers": bool(earned or sales or won)}


def readiness(session, today=None):
    """Each program with what is already true and what is still missing, in plain words."""
    today = today or date.today()
    owner, proof = facts(session), evidence(session)
    met_by = {
        "company": owner["company"], "website": bool(owner["website"]), "product": owner["product"], "developer": True,
        "african": owner["african"], "self_funded": owner["self_funded"], "revenue": proof["paying_customers"], "aws_paid": owner["aws_paid"],
        "young": bool(owner["founded_year"]) and today.year - owner["founded_year"] < 10,
    }
    applied = applications(session)
    result = []
    for program in PROGRAMS:
        missing = [NEEDS[need] for need in program["needs"] if not met_by.get(need)]
        result.append({**program, "missing": missing, "ready": not missing, "checked": CHECKED, "applied": applied.get(program["key"], {}),
                       "open": not program["window"].startswith("Once a year")})
    # Ready first, then those open now (a closed yearly call waits), then the fewest things missing; equity-free before equity.
    return sorted(result, key=lambda item: (not item["ready"], not item["open"], len(item["missing"]), item["equity"]))


def applications(session):
    row = session.get(Metadata, APPLIED_KEY)
    return dict(row.value) if row else {}


def mark(session, key, status, note=""):
    """The owner records where an application stands; Cerebra never applies itself."""
    if key not in {program["key"] for program in PROGRAMS}:
        raise LookupError("Unknown program")
    if status not in {"", "planned", "applied", "accepted", "declined"}:
        raise ValueError("Status is planned, applied, accepted or declined")
    value = applications(session)
    if status:
        value[key] = {"status": status, "note": str(note or "")[:500], "at": date.today().isoformat()}
    else:
        value.pop(key, None)
    row = session.get(Metadata, APPLIED_KEY)
    if row is None:
        session.add(Metadata(key=APPLIED_KEY, value=value))
    else:
        row.value = value
    return value.get(key, {})


def overview(session):
    programs = readiness(session)
    return {"programs": programs, "facts": facts(session), "evidence": evidence(session), "checked": CHECKED,
            "ready": sum(1 for program in programs if program["ready"]), "needs": NEEDS}
