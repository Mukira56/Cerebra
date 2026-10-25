"""One-click readiness check: a small, real task through planning, coding, real tests and independent review.

It uses a dedicated throwaway project inside the data folder (a calculator with one bug and failing unit
tests), runs with the user's own models and current settings, and stops before merging: when the task
reaches the merge gate the check is marked passed and the merge is declined, so nothing is integrated.
Pressing the button is the user's consent for this one task; it uses a little of their providers' usage.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from .models import Approval, Metadata, Project, Run, Task, now
from .security import redact

KEY = "readiness_check"
PROJECT_NAME = "Cerebra readiness check"
FILES = {
    "calculator.py": "def add(a, b):\n    return a - b\n",
    "test_calculator.py": ("import unittest\n\nfrom calculator import add\n\n\nclass AddTest(unittest.TestCase):\n"
                           "    def test_adds_two_numbers(self):\n        self.assertEqual(add(2, 3), 5)\n\n"
                           "    def test_adds_negative_numbers(self):\n        self.assertEqual(add(-2, -4), -6)\n\n\n"
                           "if __name__ == \"__main__\":\n    unittest.main()\n"),
    ".gitignore": "__pycache__/\n",
}
OBJECTIVE = ("Readiness check: fix the add function in calculator.py so that it returns the sum of its two arguments. "
             "Change only calculator.py; do not change the tests.")


def load(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row else {}


def _save(session, value):
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))


def start(db, settings, supervisor, register_folder):
    if not (settings.live_enabled and settings.cli_confinement_accepted):
        raise ValueError("Switch AI agents on first (Settings › Agent permissions)")
    with db.Session() as session:
        state = load(session)
        running = state.get("task_id") and session.get(Task, state["task_id"])
        if running and state.get("status") == "running" and running.state not in {"COMPLETED", "FAILED", "CANCELLED"}:
            raise ValueError("A readiness check is already running")
        project = session.get(Project, state.get("project_id")) if state.get("project_id") else None
        project_id = project.id if project and Path(project.path).is_dir() else None
    if project_id is None:
        folder = settings.data_dir / "readiness" / "project"
        if folder.exists() and any(folder.iterdir()):
            import shutil
            shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in FILES.items():
            (folder / name).write_text(text, encoding="utf-8")
        project_id = register_folder(PROJECT_NAME, str(folder), [[sys.executable, "-m", "unittest", "-q"]])["id"]
    task = supervisor.propose(project_id, OBJECTIVE, allowed_paths=["calculator.py"], origin="readiness",
                              acceptance_criteria=["The project's unit tests pass", "The independent review finds no problems"])
    supervisor.approve_plan(task.id)
    supervisor.start(task.id)  # asks for run consent; the button press is that consent for this one task
    with db.Session() as session:
        consent = session.scalars(select(Approval).where(Approval.task_id == task.id, Approval.kind == "live_execution", Approval.status == "pending")).first()
        consent_id = consent.id if consent else None
    if consent_id:
        supervisor.resolve_approval(consent_id, True)
    supervisor.start(task.id)
    with db.Session.begin() as session:
        _save(session, {"project_id": project_id, "task_id": task.id, "status": "running", "started_at": now(), "finished_at": None})
    return status(db, supervisor)


STAGES = [("plan", "Planning", "plan"), ("code", "Coding", "implement"), ("tests", "Your tests", None), ("review", "Independent review", "review")]


def status(db, supervisor):
    with db.Session() as session:
        state = load(session)
        if not state.get("task_id"):
            return {"status": "never", "stages": []}
        task = session.get(Task, state["task_id"])
        if task is None:
            return {"status": "never", "stages": []}
        runs = session.scalars(select(Run).where(Run.task_id == task.id).order_by(Run.started_at)).all()
        merge = session.scalars(select(Approval).where(Approval.task_id == task.id, Approval.kind == "merge", Approval.status == "pending")).first()
        models = (task.results or {}).get("models", {})
        stages = []
        for key, label, role in STAGES:
            if role:
                mine = [run for run in runs if run.role == role]
                last = mine[-1] if mine else None
                stage_state = "waiting" if last is None else {"running": "running", "succeeded": "passed"}.get(last.status, "failed")
                seconds = None
                if last and last.finished_at:
                    from .telemetry import seconds as between
                    seconds = between(last.started_at, last.finished_at)
                who = {"plan": models.get("planner"), "implement": models.get("implementer"), "review": models.get("reviewer")}[role] or {}
                stages.append({"key": key, "label": label, "state": stage_state, "seconds": seconds, "model": who.get("label", ""),
                               "detail": redact(last.error or "")[:300] if last and last.status == "failed" else ""})
            else:
                tests = list(task.test_results or [])
                latest = [result for result in tests if result.get("attempt") == (tests[-1].get("attempt") if tests else None)]
                stage_state = "running" if task.state == "VERIFYING" else "waiting" if not latest else "passed" if all(r.get("passed") for r in latest) else "failed"
                stages.append({"key": key, "label": label, "state": stage_state, "seconds": sum(r.get("duration_seconds") or 0 for r in latest) or None,
                               "model": "Cerebra runs them", "detail": redact((latest[-1].get("stdout") or "")[-300:]) if stage_state == "failed" else ""})
        task_id, task_state, error, blocked = task.id, task.state, (task.results or {}).get("error"), (task.results or {}).get("blocked_reason")
        merge_id = merge.id if merge else None
    overall = state.get("status", "running")
    if overall == "running":
        if merge_id:
            supervisor.resolve_approval(merge_id, False)  # stop before merging: the check never changes a project
            overall = "passed"
        elif task_state == "FAILED" or task_state == "CANCELLED":
            overall = "failed"
        elif task_state == "BLOCKED" and blocked == "waiting_for_usage":
            overall = "waiting for usage"
        if overall != "running" and overall != "waiting for usage":
            with db.Session.begin() as session:
                saved = load(session); saved.update(status=overall, finished_at=now()); _save(session, saved)
                state = saved
    return {"status": overall, "task_id": task_id, "started_at": state.get("started_at"), "finished_at": state.get("finished_at"),
            "stages": stages, "error": redact(error or "")[:500] if overall == "failed" else ""}
