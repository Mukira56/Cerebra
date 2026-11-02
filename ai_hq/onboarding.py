"""Local first-run setup. No accounts, projects, history or execution grants are imported."""
from __future__ import annotations

from sqlalchemy import select

from . import business, freelance, owner
from .models import Book, BusinessJob, FreelanceLead, Metadata, MoneyDocument, Project, Prospect, Task, now

KEY = "workspace_onboarding"
CURRENCIES = ("USD", "EUR", "GBP", "KES", "CAD", "AUD")


def status(session):
    saved = session.get(Metadata, KEY)
    complete = bool(saved and saved.value.get("complete") is True)
    # Existing workspaces keep their records and choices. Reading this status never resets or migrates them.
    existing = any(session.get(Metadata, key) is not None for key in (owner.KEY, freelance.KEY, business.KEY, "money_settings"))
    if not existing:
        existing = any(session.scalar(select(model.id).limit(1)) is not None
                       for model in (Project, Task, FreelanceLead, Book, Prospect, BusinessJob, MoneyDocument))
    return {"complete": complete, "existing_workspace": bool(existing and not complete),
            "needs_setup": not complete and not existing, "profile": owner.load(session),
            "freelance": freelance.profile(session), "currency": business.load(session)["currency"],
            "options": {"services": {key: item[0] for key, item in freelance.SERVICES.items()},
                        "sources": {key: item["label"] for key, item in freelance.SOURCES.items()},
                        "currencies": list(CURRENCIES)}}


def complete(session, fields):
    sources, services = fields["sources"], fields["services"]
    if set(sources) - set(freelance.SOURCES) or set(services) - set(freelance.SERVICES):
        raise ValueError("Choose work categories and job sources from the available options")
    if sources and not services:
        raise ValueError("Choose at least one work category before enabling job sources")
    # All changes commit together at the API boundary. No permission, sender or provider credential is accepted here.
    owner.save(session, {"name": fields["name"], "headline": fields["headline"], "location": fields["location"],
                         "share": fields["share_profile"]})
    freelance.save_profile(session, {"services": services, "skills": fields["skills"],
                                    "sources": {key: key in sources for key in freelance.SOURCES}})
    business.save(session, currency=fields["currency"])
    row = session.get(Metadata, KEY)
    value = {"version": 1, "complete": True, "completed_at": now()}
    if row is None:
        session.add(Metadata(key=KEY, value=value))
    else:
        row.value = value
    session.flush()
    return status(session)
