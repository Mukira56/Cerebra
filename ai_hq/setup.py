"""The Setup Center: one place that takes a first-time owner from "just installed" to "it's working for me".

The owner picks what they want Cerebra to do (their goals). Cerebra then lists only the connections those goals need,
in the order they depend on each other, checks each one from its own records (no network calls, so the page is instant),
and points to the one next thing to do. When the essentials are done, each goal offers a first job to run.

Everything here reads settings that already exist; nothing is connected or switched on from this file. Each step's button
opens the page where that connection is made, and the step turns green by itself once it is done.
"""
from __future__ import annotations

from sqlalchemy import func, select

from .models import Metadata, Project, now

KEY = "setup_center"

GOALS = {
    "jobs": ("Get a job", "Find jobs worldwide and apply with a letter and CV written for each one"),
    "freelance": ("Find freelance clients", "Paid work that matches your skills, with proposals written for you"),
    "pitch": ("Pitch companies by email", "Find companies, study them and email a pitch tailored to each"),
    "build": ("Build software with AI", "Claude plans, codes and tests; another model reviews; you approve"),
    "books": ("Write and sell books", "Plan, write and package books for Amazon KDP"),
    "etsy": ("Sell on Etsy", "Find what sells and write listings for digital and print-on-demand products"),
    "paid": ("Send invoices and get paid", "Quotes, invoices and card payments through Stripe"),
    "phone": ("Run Cerebra from my phone", "Talk to Cerebra on Telegram, approve with Yes and No, and get alerts"),
}
EVERYONE = tuple(GOALS)
NEEDS_AI = ("jobs", "freelance", "pitch", "build", "books", "etsy", "phone")

# Pages each goal uses, for the short menu.
PAGES = {"jobs": ["jobs"], "freelance": ["freelance"], "pitch": ["partners", "prospects"], "build": ["projects", "tasks", "council"],
         "books": ["books"], "etsy": ["etsy"], "paid": ["money"], "phone": ["connections"]}

# The first thing to do once a goal's essentials are in place.
FIRST_WINS = {
    "jobs": ("Find jobs that fit you", "jobs", "POST", "/api/jobs/find"),
    "freelance": ("Check for paid work now", "freelance", "POST", "/api/freelance/check"),
    "pitch": ("Find companies to pitch", "partners", "POST", "/api/partners/find"),
    "build": ("Describe your first task", "tasks", "", ""),
    "books": ("Plan your first book", "books", "", ""),
    "etsy": ("Research what sells", "etsy", "", ""),
    "paid": ("Write your first invoice", "money", "", ""),
    "phone": ("Send a test message to your phone", "connections", "POST", "/api/business/notifications/test"),
}


def _signed_in(session, *providers):
    row = session.get(Metadata, "sign_in_status")
    seen = (row.value or {}) if row else {}
    from .models import Agent
    for name in providers:
        if (seen.get(name) or {}).get("signed_in") is True:
            return True
        agent = session.get(Agent, name)
        if agent and (agent.status or {}).get("authentication") == "verified_by_execution":
            return True
    return False


def _checks(session, settings):
    """Each connection: whether it's done, and a short detail. Read from Cerebra's own records only."""
    from . import books, commerce, freelance, gmail, jobs, modelhub, notify, owner, payments
    from .prospects import footer
    me = owner.load(session)
    mail = gmail.public(gmail.load(session))
    stored = commerce.load(session)
    alert = notify.load(session)
    hub = modelhub.settings(session)
    missing_footer = footer(session)[1]
    return {
        "profile": (bool((me.get("name") or "").strip()), me.get("name") or ""),
        "ai_on": (bool(settings.live_enabled and settings.cli_confinement_accepted), ""),
        "ai_account": (_signed_in(session, "claude", "codex"), ""),
        "free_models": (_signed_in(session, "gemini", "qwen") or bool(hub.get("api_key")), ""),
        "gmail": (bool(mail["connected"] and mail["can_send"] and not mail.get("expired")), mail.get("email") or ""),
        "address": (not missing_footer, ""),
        "cv": (len((jobs.settings(session).get("cv") or "").strip()) > 200, ""),
        "skills": (bool(freelance.profile(session).get("services")), ""),
        "freelancer": (any(item.get("user_id") for item in stored.get("freelancer_accounts") or [stored.get("freelancer_account") or {}]), ""),
        "project": ((session.scalar(select(func.count()).select_from(Project)) or 0) > 0, ""),
        "kdp": ("kdp_account" in (books.settings(session).get("done") or []), ""),
        "etsy": (bool((stored.get("etsy") or {}).get("api_key")), ""),
        "stripe": (payments.status(session)["connected"], ""),
        "telegram": (bool(alert.get("telegram_enabled") and alert.get("telegram_token") and alert.get("telegram_chat_id")), ""),
    }


# id: (title, why, goals that need it, optional, minutes, page to open, what to do there). FIND: the panel to jump to.
STEPS = [
    ("profile", "Your name and what you do", "Letters, pitches and proposals go out in your name.", EVERYONE, False, 1, "settings",
     ["Open Settings › About you.", "Type your name, a one-line headline and your city, then Save."]),
    ("ai_on", "Let Cerebra use AI", "Cerebra's helpers run your own Claude or ChatGPT sign-in on this computer.", NEEDS_AI, False, 1, "settings",
     ["Open Settings › AI helpers: permission to work.", "Tick the boxes to let the AI helpers work, then Save."]),
    ("ai_account", "Sign in to Claude (or ChatGPT's Codex)", "This is the AI that writes, plans and builds. Your plan pays for it; nothing is billed by Cerebra.",
     NEEDS_AI, False, 3, "models",
     ["If Claude isn't installed yet, open Install tools and install Claude Code first.", "Open Models › Your AI accounts and press Sign in next to Claude.",
      "Finish the sign-in in the window that opens. It turns green here by itself."]),
    ("free_models", "Add free helper models (optional)", "Gemini signed in with your Google account does research and easy jobs, so your Claude usage lasts longer.",
     ("jobs", "freelance", "pitch", "phone"), True, 3, "models",
     ["Install Gemini CLI on Install tools.", "Press Sign in next to Gemini on Models and choose Login with Google."]),
    ("gmail", "Connect Gmail", "Applications and pitches are sent from your own Gmail, and replies are read there.", ("jobs", "pitch"), False, 5, "connections",
     ["Open Connected accounts › Gmail and press How to connect for the 5-minute Google setup.", "Press Connect Gmail and allow reading and sending."]),
    ("address", "Your business name and postal address", "US law (CAN-SPAM) requires a postal address in every business email you send.", ("pitch",), False, 1,
     "money", ["Open Money › Your business.", "Add your business name and a postal address (a PO box is fine), then Save."]),
    ("cv", "Paste your CV", "Your CV is the only source of facts about you: nothing that isn't in it is ever claimed.", ("jobs",), False, 2, "jobs",
     ["Open Apply for jobs.", "Paste your CV into the Your CV box and Save."]),
    ("skills", "What you sell and where to look", "Cerebra scores every job against what you do.", ("freelance",), False, 2, "freelance",
     ["Open Find work › Your profile.", "Tick the kinds of work you do, add your skills, choose job boards, then Save."]),
    ("freelancer", "Connect Freelancer.com (optional)", "Lets Cerebra place bids for you with one tap.", ("freelance",), True, 5, "freelance",
     ["Open Find work › Freelancer.com account and follow How to connect."]),
    ("project", "Add a project folder", "The code Cerebra builds lives in a folder on this computer, kept in Git.", ("build",), False, 2, "projects",
     ["Open Projects and press Add project.", "Pick an existing folder, start a new one, or clone from GitHub."]),
    ("kdp", "Have an Amazon KDP account", "Books are uploaded by you at kdp.amazon.com (it's free).", ("books",), True, 10, "books",
     ["Open Write books › Getting started and tick each step as you do it at kdp.amazon.com."]),
    ("etsy", "Connect Etsy", "Research what sells and manage listings with Etsy's own API.", ("etsy",), False, 5, "connections",
     ["Open Connected accounts › Etsy and follow How to connect."]),
    ("stripe", "Connect Stripe", "Clients pay invoices by card, and Cerebra marks them paid by itself.", ("paid",), False, 5, "money",
     ["Open Money › Get paid with Stripe and follow the steps."]),
    ("telegram", "Connect your Telegram", "Talk to Cerebra from your phone, approve with Yes and No, and get alerts.", ("phone",), False, 5, "connections",
     ["In Telegram, message @BotFather, send /newbot and copy the token it gives you.",
      "Open Connected accounts › Progress on your phone, paste the token and Save.", "Press Start in your new bot, then Find my chat and Save."]),
]


FIND = {'profile': 'About you', 'ai_on': 'AI helpers', 'ai_account': 'Your AI accounts', 'free_models': 'Your AI accounts', 'gmail': 'Gmail', 'address': 'Your business', 'cv': 'Your CV', 'skills': 'What you sell', 'freelancer': 'Freelancer.com account', 'project': '', 'kdp': '', 'etsy': 'Etsy', 'stripe': 'Get paid with Stripe', 'telegram': 'Progress on your phone'}


def load(session):
    row = session.get(Metadata, KEY)
    value = dict(row.value or {}) if row else {}
    return {"goals": [goal for goal in value.get("goals", []) if goal in GOALS], "skipped": list(value.get("skipped", [])),
            "chosen_at": value.get("chosen_at", ""), "dismissed": bool(value.get("dismissed"))}


def save(session, changes):
    value = load(session)
    if "goals" in changes:
        goals = [goal for goal in changes["goals"] or [] if goal in GOALS]
        if not goals:
            raise ValueError("Choose at least one thing you want Cerebra to do")
        value["goals"], value["chosen_at"] = goals, now()
    for key in ("skip", "unskip"):
        if key in changes:
            step = str(changes[key])
            if step not in {item[0] for item in STEPS}:
                raise ValueError("Unknown setup step")
            value["skipped"] = sorted(set(value["skipped"]) | {step}) if key == "skip" else [item for item in value["skipped"] if item != step]
    if "dismissed" in changes:
        value["dismissed"] = bool(changes["dismissed"])
    row = session.get(Metadata, KEY)
    if row is None:
        session.add(Metadata(key=KEY, value=value))
    else:
        row.value = value
    return value


def status(session, settings):
    """The owner's goals, the steps those goals need (in order, each done, skipped or to do), the next step, progress,
    and a first job for each goal whose essentials are done."""
    chosen = load(session)
    goals = chosen["goals"]
    checks = _checks(session, settings)
    steps = []
    for key, title, why, needed_by, optional, minutes, page, how in STEPS:
        if goals and not set(needed_by) & set(goals):
            continue
        if not goals and key != "profile":
            continue
        done, detail = checks[key]
        steps.append({"id": key, "title": title, "why": why, "done": done, "detail": detail, "optional": optional,
                      "skipped": key in chosen["skipped"] and not done, "minutes": minutes, "page": page, "how": how,
                      "for": [GOALS[goal][0] for goal in needed_by if goal in goals], "goals": [goal for goal in needed_by if goal in goals],
                      "find": FIND.get(key, "")})
    essential = [step for step in steps if not step["optional"]]
    next_step = next((step for step in steps if not step["done"] and not step["skipped"] and not step["optional"]), None) or \
        next((step for step in steps if not step["done"] and not step["skipped"]), None)
    done_ids = {step["id"] for step in steps if step["done"]}
    wins = []
    for goal in goals:
        needed = [step for step in essential if goal in step["goals"]]
        ready = all(step["id"] in done_ids for step in needed)
        label, page, method, path = FIRST_WINS[goal]
        wins.append({"goal": goal, "goal_label": GOALS[goal][0], "label": label, "page": page, "method": method, "path": path, "ready": ready,
                     "waiting_for": [step["title"] for step in needed if step["id"] not in done_ids][:2]})
    count = len(essential)
    finished = sum(1 for step in essential if step["done"])
    return {"goals": goals, "available": {key: {"label": label, "about": about} for key, (label, about) in GOALS.items()},
            "steps": steps, "next": next_step, "done": finished, "total": count, "complete": bool(goals) and finished == count,
            "minutes_left": sum(step["minutes"] for step in essential if not step["done"]), "first_wins": wins,
            "pages": sorted({page for goal in goals for page in PAGES[goal]}), "dismissed": chosen["dismissed"]}


def glance(session, settings):
    """The few facts Home needs (cheap: the Overview polls every few seconds)."""
    value = status(session, settings)
    return {"goals": value["goals"], "done": value["done"], "total": value["total"], "complete": value["complete"],
            "next": {key: value["next"][key] for key in ("id", "title", "page", "find")} if value["next"] else None,
            "pages": value["pages"], "dismissed": value["dismissed"]}
