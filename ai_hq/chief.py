"""Chief of Staff: the layer that keeps Cerebra's money-making workers running, on time, on the record, within the owner's
rules (docs/AGENTS_ARCHITECTURE.md).

This first part is the backbone the planner will use:
- a registry of workers (each a fixed piece of Cerebra's own code; nothing here runs code a model wrote),
- one scheduler that runs every due job and records each run: what it found, how long it took, what went wrong,
- goals the owner sets, with their rules,
- the training set for Cerebra's own model: the owner's real work and what came of it, compiled from the records.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .models import ChiefGoal, ChiefJob, ChiefRun, Event, FreelanceLead, Metadata, SocialPost, now
from .security import redact

TICK_SECONDS = 30
KEEP_RUNS = 2000  # newest runs kept; older ones are pruned so the record stays fast


@dataclass
class Worker:
    key: str
    label: str
    about: str
    run: object  # callable() -> dict | int | None
    every_minutes: int
    outward: bool = False  # acts outside this computer (bids, posts, messages): its own standing rules gate it
    enabled: bool = True
    extra: dict = field(default_factory=dict)


class Registry:
    def __init__(self):
        self.workers = {}

    def add(self, key, label, about, run, every_minutes, outward=False, enabled=True):
        self.workers[key] = Worker(key, label, about, run, every_minutes, outward, enabled)
        return self.workers[key]


def _stamp(moment=None):
    return (moment or datetime.now(timezone.utc)).isoformat()


def _summary(result):
    """A run's result as a small JSON-safe record (counts and short messages, never secrets)."""
    if result is None:
        return {}
    if isinstance(result, (int, float)):
        return {"count": result}
    try:
        text = json.dumps(result, default=str)
    except (TypeError, ValueError):
        text = json.dumps(str(result))
    text = redact(text)
    return json.loads(text) if len(text) <= 4000 else {"note": text[:4000]}


def describe(summary):
    """One plain line for a run's result."""
    if not summary:
        return "Done"
    if "skipped" in summary:
        return f"Skipped: {summary['skipped']}"
    parts = []
    for key, value in summary.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            parts.append(f"{key.replace('_', ' ')} {value:g}")
        elif isinstance(value, dict):
            inner = ", ".join(f"{name.replace('_', ' ')} {amount:g}" for name, amount in value.items() if isinstance(amount, (int, float)) and not isinstance(amount, bool))
            if inner:
                parts.append(f"{key.replace('_', ' ')}: {inner}")
    return " · ".join(parts) or "Done"


class Scheduler:
    """One loop for every job: runs what is due, one at a time, and records each run."""

    def __init__(self, db, registry):
        self.db, self.registry = db, registry
        self._stop, self._thread, self._lock = threading.Event(), None, threading.Lock()
        self.running = ""  # the job running now, for the page

    def seed(self):
        """A job for every registered worker that has none yet (the owner's on/off choices are kept)."""
        with self.db.Session.begin() as session:
            known = {row.id for row in session.scalars(select(ChiefJob)).all()}
            for worker in self.registry.workers.values():
                if worker.key not in known:
                    session.add(ChiefJob(id=worker.key, worker=worker.key, every_minutes=worker.every_minutes, enabled=worker.enabled,
                                         next_run_at=_stamp(datetime.now(timezone.utc) + timedelta(minutes=worker.every_minutes))))

    def due(self, moment=None):
        stamp = _stamp(moment)
        with self.db.Session() as session:
            return [row.id for row in session.scalars(select(ChiefJob).where(ChiefJob.enabled.is_(True), ChiefJob.next_run_at <= stamp)
                                                      .order_by(ChiefJob.next_run_at)).all() if row.worker in self.registry.workers]

    def run(self, job_id, by="schedule"):
        """Run one job now and record it. Never raises: a failing worker is recorded and the others carry on."""
        with self.db.Session() as session:
            job = session.get(ChiefJob, job_id)
            if job is None:
                raise LookupError("Job not found")
            worker = self.registry.workers.get(job.worker)
            if worker is None:
                raise LookupError("This job's worker is no longer part of Cerebra")
        if not self._lock.acquire(blocking=False):
            return {"status": "busy", "message": f"{self.running or 'Another job'} is running; this one waits its turn"}
        started, clock = _stamp(), time.monotonic()
        self.running = worker.label
        status, summary, error = "ok", {}, ""
        try:
            summary = _summary(worker.run())
            if "skipped" in summary:
                status = "skipped"
        except Exception as exc:  # noqa: BLE001 - recorded for the owner, never fatal to the loop
            status, error = "failed", redact(f"{type(exc).__name__}: {exc}")[:1000]
        finally:
            self.running = ""
            self._lock.release()
        with self.db.Session.begin() as session:
            job = session.get(ChiefJob, job_id)
            finished = datetime.now(timezone.utc)
            session.add(ChiefRun(job_id=job_id, worker=job.worker, started_at=started, finished_at=_stamp(finished),
                                 seconds=round(time.monotonic() - clock, 2), status=status, summary=summary, error=error, by=by))
            job.last_run_at, job.last_status = _stamp(finished), status
            job.last_summary = {"text": error or describe(summary)}
            job.next_run_at = _stamp(finished + timedelta(minutes=job.every_minutes))
            if status == "failed":
                session.add(Event(kind="chief", message=f"{worker.label} failed: {error[:200]}", data={"job": job_id}))
        return {"status": status, "summary": summary, "error": error, "message": error or describe(summary)}

    def tick(self, moment=None):
        ran = 0
        for job_id in self.due(moment):
            if self._stop.is_set():
                break
            self.run(job_id)
            ran += 1
        if ran:
            self.prune()
        return ran

    def prune(self):
        with self.db.Session.begin() as session:
            ids = [row.id for row in session.scalars(select(ChiefRun).order_by(ChiefRun.started_at.desc()).offset(KEEP_RUNS)).all()]
            for run_id in ids:
                session.delete(session.get(ChiefRun, run_id))

    def loop(self):
        while not self._stop.wait(TICK_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the loop must survive a database hiccup
                continue

    def start(self):
        self.seed()
        if self._thread is None:
            self._thread = threading.Thread(target=self.loop, name="cerebra-chief", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()


def jobs(session, registry, running=""):
    rows = {row.id: row for row in session.scalars(select(ChiefJob)).all()}
    result = []
    for key, worker in registry.workers.items():
        row = rows.get(key)
        if row is None:
            continue
        result.append({"id": row.id, "label": worker.label, "about": worker.about, "outward": worker.outward, "enabled": row.enabled,
                       "every_minutes": row.every_minutes, "next_run_at": row.next_run_at, "last_run_at": row.last_run_at,
                       "last_status": row.last_status, "last_result": (row.last_summary or {}).get("text", ""), "running": running == worker.label})
    return result


def update_job(session, registry, job_id, fields):
    row = session.get(ChiefJob, job_id)
    if row is None or job_id not in registry.workers:
        raise LookupError("Job not found")
    if "enabled" in fields:
        row.enabled = bool(fields["enabled"])
    if "every_minutes" in fields:
        minutes = int(fields["every_minutes"] or 0)
        if not 5 <= minutes <= 7 * 24 * 60:
            raise ValueError("Run it between every 5 minutes and once a week")
        row.every_minutes = minutes
        row.next_run_at = _stamp(datetime.now(timezone.utc) + timedelta(minutes=minutes))
    return {"id": row.id, "enabled": row.enabled, "every_minutes": row.every_minutes}


def runs(session, limit=50, job_id=None):
    query = select(ChiefRun).order_by(ChiefRun.started_at.desc()).limit(limit)
    if job_id:
        query = query.where(ChiefRun.job_id == job_id)
    return [{"id": row.id, "job_id": row.job_id, "started_at": row.started_at, "seconds": row.seconds, "status": row.status, "by": row.by,
             "result": row.error or describe(row.summary or {})} for row in session.scalars(query).all()]


def overnight(session, hours=24):
    """What the workers did in the last day, for the morning brief."""
    since = _stamp(datetime.now(timezone.utc) - timedelta(hours=hours))
    rows = session.scalars(select(ChiefRun).where(ChiefRun.started_at >= since)).all()
    return {"runs": len(rows), "failed": sum(1 for row in rows if row.status == "failed"),
            "by_job": {job: sum(1 for row in rows if row.job_id == job) for job in sorted({row.job_id for row in rows})}}


# ---- goals ----
GOAL_STATUSES = {"active", "paused", "done"}


def goal_public(row):
    return {"id": row.id, "title": row.title, "target": row.target, "rules": row.rules or {}, "monthly_cap": row.monthly_cap,
            "status": row.status, "created_at": row.created_at}


def save_goal(session, fields, goal_id=None):
    row = session.get(ChiefGoal, goal_id) if goal_id else ChiefGoal(title="", target="", rules={}, monthly_cap=0.0, status="active")
    if row is None:
        raise LookupError("Goal not found")
    if "title" in fields:
        row.title = " ".join(str(fields["title"] or "").split())[:200]
    if "target" in fields:
        row.target = str(fields["target"] or "").strip()[:2000]
    if "rules" in fields:
        rules = fields["rules"] or {}
        row.rules = {"public_data_only": bool(rules.get("public_data_only", True)), "ask_before_contact": bool(rules.get("ask_before_contact", True)),
                     "notes": str(rules.get("notes") or "")[:2000]}
    if "monthly_cap" in fields:
        cap = float(fields["monthly_cap"] or 0)
        if cap < 0:
            raise ValueError("The monthly spending cap can't be negative")
        row.monthly_cap = round(cap, 2)
    if "status" in fields:
        if fields["status"] not in GOAL_STATUSES:
            raise ValueError("A goal is active, paused or done")
        row.status = fields["status"]
    if not row.title:
        raise ValueError("Write the goal, for example “$5,000 a month of new client work”")
    if goal_id is None:
        row.rules = row.rules or {"public_data_only": True, "ask_before_contact": True, "notes": ""}
        session.add(row)
        session.flush()
    return goal_public(row)


def goals(session):
    return [goal_public(row) for row in session.scalars(select(ChiefGoal).order_by(ChiefGoal.created_at.desc())).all()]


def delete_goal(session, goal_id):
    row = session.get(ChiefGoal, goal_id)
    if row is None:
        raise LookupError("Goal not found")
    session.delete(row)


# ---- the training set for Cerebra's own model ----
TRAINING_KEY = "training_settings"
OUTCOME = {"won": "won", "awarded": "won", "lost": "lost", "applied": "sent", "interview": "replied"}


def training_settings(session):
    row = session.get(Metadata, TRAINING_KEY)
    return {"collect": True, **(row.value if row else {})}


def save_training_settings(session, fields):
    value = {**training_settings(session), "collect": bool(fields.get("collect", True))}
    row = session.get(Metadata, TRAINING_KEY)
    if row is None:
        session.add(Metadata(key=TRAINING_KEY, value=value))
    else:
        row.value = value
    return value


def training_examples(session):
    """The owner's own work and what came of it: proposals (job post in, proposal out, won or lost) and posts that went
    out. Built from Cerebra's records on demand, so nothing is copied twice. Clients' deliverables are never included:
    they belong to the clients."""
    if not training_settings(session)["collect"]:
        return []
    examples = []
    for row in session.scalars(select(FreelanceLead)).all():
        proposal = row.proposal or {}
        if not proposal.get("text") or row.status not in OUTCOME:
            continue
        examples.append({"kind": "proposal", "id": row.id, "input": f"{row.title}\n\n{row.description[:6000]}", "output": proposal["text"],
                         "outcome": OUTCOME[row.status], "automatic": bool(proposal.get("auto")), "at": proposal.get("sent_at") or row.updated_at})
    for post in session.scalars(select(SocialPost).where(SocialPost.status.in_(["posted", "partial"]))).all():
        examples.append({"kind": "post", "id": post.id, "input": "", "output": post.text, "outcome": "posted", "automatic": post.origin == "ai",
                         "at": post.updated_at})
    return sorted(examples, key=lambda item: str(item["at"]), reverse=True)


def training_summary(session):
    examples = training_examples(session)
    counts = {}
    for item in examples:
        counts.setdefault(item["kind"], {}).setdefault(item["outcome"], 0)
        counts[item["kind"]][item["outcome"]] += 1
    proven = sum(1 for item in examples if item["outcome"] in {"won", "replied"})
    return {"settings": training_settings(session), "total": len(examples), "counts": counts, "proven": proven,
            "ready": proven >= 200, "needed": 200,
            "note": "A first fine-tune needs a few hundred good examples: work that won, got replies or was posted. Until then Cerebra keeps collecting."}


def training_jsonl(session, only_proven=True):
    """Chat-format lines (system, user, assistant) for fine-tuning an open model; only work that got a good result by default."""
    lines = []
    for item in training_examples(session):
        if only_proven and item["outcome"] not in {"won", "replied", "posted"}:
            continue
        system = "You write a winning freelance proposal for the job post." if item["kind"] == "proposal" else "You write a social post that brings clients."
        messages = [{"role": "system", "content": system}]
        if item["input"]:
            messages.append({"role": "user", "content": item["input"]})
        messages.append({"role": "assistant", "content": item["output"]})
        lines.append(json.dumps({"messages": messages}, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")
