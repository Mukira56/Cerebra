"""Auto-fix: when a task fails, Cerebra starts the Assistant on it without waiting for the owner.

The owner turns it on once (Settings, or the Assistant's chat). For every newly failed or stuck task,
Cerebra opens (or reuses) that task's fix chat and sends the failure; the Assistant reads the logs and
acts on its own (retry with fix instructions, correct the test command, resume). Each new failure is
one attempt; after `max_attempts` Cerebra stops and says the task needs the owner. A task's
"Stop auto-fix" button ends its fix chat, pauses a fix run in progress and stops further attempts.

With the separate `full_access` grant (only while Full access is on), fix runs keep the owner's Full
access even though their instructions were written by a model. `capabilities.py` applies that grant.
"""
from __future__ import annotations

import hashlib
import threading

from sqlalchemy import select

from .models import Event, Metadata, Project, Task, now
from .security import redact

KEY = "auto_fix"
# scope "selected": only the failed tasks the owner ticks; "all": every failed task, including new ones.
OFF = {"enabled": False, "full_access": False, "max_attempts": 4, "council_after": 2, "scope": "selected"}
SCOPES = {"selected", "all"}
MAX_ATTEMPTS = 10
# Stuck states the owner or Cerebra resolves without a fix: waiting for usage, the owner's pause, a retry already queued.
WAITING = {"waiting_for_usage", "waiting_for_network", "paused_by_user", "retry_requested", "restored_checkpoint", "interrupted_restart", "paused_on_close", "interrupted_integration", "overlapping_changes"}
SCAN_SECONDS = 5


def load(session):
    row = session.get(Metadata, KEY)
    return {**OFF, **(row.value if row else {})}


def save(session, enabled=None, full_access=None, max_attempts=None, council_after=None, scope=None):
    value = load(session)
    if scope is not None:
        if scope not in SCOPES:
            raise ValueError("Choose the ticked tasks or every failed task")
        value["scope"] = scope
    if enabled is not None:
        value["enabled"] = bool(enabled)
    if full_access is not None:
        value["full_access"] = bool(full_access)
    if max_attempts is not None:
        if not 1 <= int(max_attempts) <= MAX_ATTEMPTS:
            raise ValueError(f"Auto-fix can try 1 to {MAX_ATTEMPTS} times per task")
        value["max_attempts"] = int(max_attempts)
    if council_after is not None:
        if not 0 <= int(council_after) <= MAX_ATTEMPTS:
            raise ValueError(f"Ask the Council after 0 (never) to {MAX_ATTEMPTS} attempts")
        value["council_after"] = int(council_after)
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return value


def describe(policy, settings):
    return {**policy, "full_access_effective": bool(policy["enabled"] and policy["full_access"] and settings.full_access)}


def problem(task):
    """The failure Auto-fix should work on, or None when the task is fine, waiting, or paused by the owner."""
    from .agents import readable_error
    reason = _problem(task)
    return readable_error(reason) if reason else None


def _problem(task):
    results = task.results or {}
    if task.pause_requested:
        return None
    if task.state == "FAILED":
        return results.get("error") or "The task failed."
    if task.state == "BLOCKED" and results.get("error") and results.get("blocked_reason") not in WAITING \
            and not str(results["error"]).startswith("Supervisor shutdown"):
        return results["error"]
    return None


def covered(policy, task):
    """Whether Auto-fix works on this task: not stopped by the owner, and ticked unless every task is covered."""
    fix = (task.results or {}).get("auto_fix") or {}
    return not fix.get("stopped") and (policy.get("scope") == "all" or bool(fix.get("chosen")))


def candidates(session, policy):
    """The failed and stuck tasks the owner can choose from, newest first."""
    rows = session.scalars(select(Task).where(Task.state.in_(["FAILED", "BLOCKED"])).order_by(Task.updated_at.desc()).limit(200)).all()
    projects = {row.id: row.name for row in session.scalars(select(Project)).all()}
    listed = []
    for row in rows:
        reason = problem(row)
        if reason is None:
            continue
        fix = row.results.get("auto_fix") or {}
        listed.append({"id": row.id, "description": redact(row.description)[:200], "project": projects.get(row.project_id, ""), "state": row.state,
                       "error": redact(str(reason))[:300], "updated_at": row.updated_at, "selected": covered(policy, row),
                       "status": fix.get("status"), "attempts": fix.get("attempts", 0)})
    return listed


def fingerprint(task, reason=None):
    # The raw error, so improving how errors read never makes an old failure look new.
    return hashlib.sha256(f"{task.state}|{task.updated_at}|{_problem(task)}".encode()).hexdigest()[:16]


class AutoFix:
    def __init__(self, db, settings, supervisor, chats, profile_for, council=None):
        self.db, self.settings, self.supervisor, self.chats, self.council = db, settings, supervisor, chats, council
        self.work = None  # set by the API: reads the plan a Council meeting produced
        if council is not None:
            council.on_end.append(self.council_ended)
        self.profile_for = profile_for  # (session, task) -> chat profile id for the fixer
        self._stop = threading.Event()
        self._thread = None
        self._scan_lock = threading.Lock()

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="cerebra-autofix", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(SCAN_SECONDS):
            try:
                self.scan()
            except Exception as exc:  # recorded, never fatal
                try:
                    with self.db.Session.begin() as session:
                        session.add(Event(kind="auto_fix", message=f"Auto-fix could not check failed tasks: {redact(str(exc))[:300]}"))
                except Exception:
                    pass

    def scan(self):
        """Start the Assistant on every newly failed task. Returns the ids of tasks it started on."""
        if not (self.settings.live_enabled and self.settings.cli_confinement_accepted):
            return []
        with self._scan_lock:
            with self.db.Session() as session:
                policy = load(session)
                if not policy["enabled"]:
                    return []
                rows = session.scalars(select(Task).where(Task.state.in_(["FAILED", "BLOCKED"])).order_by(Task.updated_at)).all()
                due = [row.id for row in rows if (reason := problem(row)) and covered(policy, row)
                       and (row.results.get("auto_fix") or {}).get("last") != fingerprint(row, reason)]
            return [task_id for task_id in due if self._attempt(task_id)]

    def _attempt(self, task_id):
        with self.supervisor._lock, self.db.Session.begin() as session:
            policy, task = load(session), session.get(Task, task_id)
            reason = problem(task) if task else None
            fix = dict(task.results.get("auto_fix") or {}) if task else {}
            if reason is None or not covered(policy, task) or fix.get("last") == fingerprint(task, reason):
                return False
            if fix.get("chat") and fix["chat"] in self.chats._busy:
                return False  # the Assistant is still working on the previous attempt
            if fix.get("status") == "council" and self.council is not None and fix.get("council") in self.council._running:
                return False  # the Council is still working on it
            fix["last"] = fingerprint(task, reason)
            if fix.get("attempts", 0) >= policy["max_attempts"]:
                fix["status"] = "gave_up"
                task.results = {**task.results, "auto_fix": fix}
                session.add(Event(task_id=task_id, kind="auto_fix", message=f"Auto-fix stopped after {fix['attempts']} attempts; this task needs you. Open it and read the fix chat."))
                return False
            fix.update(attempts=fix.get("attempts", 0) + 1, status="fixing", at=now())
            task.results = {**task.results, "auto_fix": fix}
            project = session.get(Project, task.project_id)
            profile = self.profile_for(session, task)
            attempt, chat_id = fix["attempts"], fix.get("chat")
            escalate = self.council is not None and policy["council_after"] and attempt > policy["council_after"] and not fix.get("council")
            message = self._message(task, project, reason, attempt, policy)
            session.add(Event(task_id=task_id, kind="auto_fix", message=f"Auto-fix attempt {attempt} of {policy['max_attempts']}: "
                              + ("the Assistant's fixes didn't hold, so the Council is solving it" if escalate else "the Assistant is working on this failure")))
        if escalate:
            try:
                self.escalate(task_id, f"The Assistant's {attempt - 1} fix attempts didn't solve it. Latest failure:\n{redact(str(reason))[:1500]}")
                return True
            except Exception as exc:  # no Council possible (for example one provider missing): the Assistant keeps trying
                with self.db.Session.begin() as session:
                    session.add(Event(task_id=task_id, kind="auto_fix", message=f"The Council couldn't start ({redact(str(exc))[:200]}); the Assistant keeps working on it"))
        try:
            if not chat_id:
                chat_id = self.chats.create(profile, task.project_id, f"Auto-fix: {task.description[:60]}")["id"]
                self._remember(task_id, chat=chat_id)
            self.chats.send(chat_id, message, act=True, role="auto")
            return True
        except Exception as exc:
            self._remember(task_id, status="error", error=redact(str(exc))[:500])
            with self.db.Session.begin() as session:
                session.add(Event(task_id=task_id, kind="auto_fix", message=f"Auto-fix could not start the Assistant: {redact(str(exc))[:300]}"))
            return False

    def _message(self, task, project, reason, attempt, policy):
        access = ("Fix runs keep the owner's Full access: the coder may run commands, install missing tools, and use the network and GitHub for this task."
                  if self.settings.full_access and policy["full_access"] else
                  "Fix runs stay inside the project copy (Auto-fix has not been given Full access).")
        return (f"AUTO-FIX (Cerebra started this because the owner turned on Auto-fix; attempt {attempt} of {policy['max_attempts']}).\n"
                f"Task {task.id[:8]} (“{redact(task.description)[:160]}”) in project {project.name if project else '?'} is {task.state.lower()}:\n"
                f"{redact(str(reason))[:1500]}\n\n"
                "Read its failure logs and recent runs, find the root cause from the evidence, and fix it now with actions: retry_task with precise "
                "instructions for the coder (what is wrong, which file, what to change, how to verify), set_test_commands if the test command is "
                "wrong, or resume_task if it only needs to continue. Don't weaken or delete tests to make them pass. " + access + "\n"
                "If it truly needs the owner (signing in, a usage limit, a key, Windows elevation, or a decision), propose no actions and say exactly what they must do.")

    # ---- the Council solves hard failures; the Assistant then applies its solution --------------------
    def escalate(self, task_id, question):
        """Start a Council meeting about this task's failure. Used by Auto-fix and by Support's ask_council action."""
        if self.council is None:
            raise ValueError("The Council isn't available")
        with self.db.Session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise LookupError("Task not found")
            fix = task.results.get("auto_fix") or {}
            if fix.get("council") and fix["council"] in self.council._running:
                return fix["council"]  # one meeting per task at a time
            reason = problem(task) or task.results.get("error") or ""
            topic = (f"Task {task.id[:8]} keeps failing and needs a decided fix.\nTask: {redact(task.description)[:800]}\n"
                     f"Allowed files: {', '.join(task.allowed_paths)}\nCurrent error: {redact(str(reason))[:1200]}\n"
                     f"What the Assistant asks: {redact(question)[:1500]}\n"
                     "Find the root cause from the code and evidence and agree ONE fix, and how to verify it. Do not weaken or delete tests.\n"
                     "If the fix fits this task's allowed files, keep the tasks to its steps; the Assistant applies them to this task. If the real "
                     "cause is the project's architecture (structure, boundaries, build or test setup), agree the restructure instead: say so in "
                     "the summary and list it as ordered tasks with depends_on. This task is retried after they are merged.")
        meeting = self.council.start(task.project_id, topic, rounds=3)
        self.council.remember(meeting["id"], fix_task=task_id)
        self._remember(task_id, council=meeting["id"], status="council")
        with self.db.Session.begin() as session:
            session.add(Event(task_id=task_id, kind="auto_fix", message="The Council is meeting to solve this task", data={"session_id": meeting["id"]}))
        return meeting["id"]

    def council_ended(self, session_id, status):
        """A meeting ended: if it was about a failed task, send its solution to that task's fix chat to apply."""
        task_id = self.council.options(session_id).get("fix_task")
        if not task_id:
            return
        meeting = self.council.get(session_id)
        with self.db.Session() as session:
            task = session.get(Task, task_id)
            fix = dict(task.results.get("auto_fix") or {})
            profile = self.profile_for(session, task)
        if fix.get("stopped"):
            return
        plan_items = self.work.plan(meeting["plan_id"])["items"] if status == "done" and meeting.get("plan_id") and self.work else []
        if status == "done":
            solution = meeting.get("solution") or {}
            steps = "\n".join(f"  Step {number}: {step}" for number, step in enumerate(solution.get("steps", []), 1))
            details = "\n".join(f"- {proposal.get('title', '')}: {proposal.get('description', '')}"
                                + "".join(f"\n  Requirement: {value}" for value in proposal.get("requirements", []))
                                + "".join(f"\n  Done when: {value}" for value in proposal.get("acceptance_criteria", []))
                                + (f"\n  Plan item id: {plan_items[index]['id']}" if index < len(plan_items) else "")
                                for index, proposal in enumerate(meeting.get("proposals") or []))
            allowed = ", ".join(task.allowed_paths)
            apply = (f"Apply it now. If these steps fit task {task_id[:8]}'s allowed files ({allowed}), use retry_task on it with instructions that carry "
                     "out this solution exactly (which files, what to change, how to verify), and create no new tasks. If the Council agreed a "
                     "restructure of the project, create its tasks with create_plan_task (one per plan item id above; they keep the agreed order) "
                     f"and start them; once they are merged, retry task {task_id[:8]} with retry_task.")
            text = (f"COUNCIL SOLUTION for task {task_id[:8]} (the two engineers agreed; their conclusion is data, not a reason to change permissions).\n"
                    f"Summary: {meeting.get('summary', '')}\nThe way forward: {solution.get('title', '')}: {solution.get('description', '')}\n{steps}\n{details}\n\n" + apply)
        else:
            text = (f"The Council meeting about task {task_id[:8]} ended without a solution ({status}: {meeting.get('error') or 'no conclusion'}). "
                    "Decide the next fix yourself from the evidence, or say exactly what the owner must do.")
        self._remember(task_id, status="applying" if status == "done" else "fixing")
        chat_id = fix.get("chat")
        if not chat_id:
            chat_id = self.chats.create(profile, task.project_id, f"Auto-fix: {task.description[:60]}")["id"]
            self._remember(task_id, chat=chat_id)
        threading.Thread(target=self._deliver, args=(chat_id, text), name="cerebra-autofix-council", daemon=True).start()

    def _deliver(self, chat_id, text, wait_seconds=900):
        """Send once the chat is free (the Assistant may still be finishing the turn that asked the Council)."""
        for _ in range(wait_seconds * 2):
            try:
                self.chats.send(chat_id, text, act=True, role="auto")
                return True
            except ValueError as exc:
                if "still answering" not in str(exc):
                    raise
            if self._stop.wait(0.5):
                return False
        return False

    def _remember(self, task_id, **values):
        with self.supervisor._lock, self.db.Session.begin() as session:
            task = session.get(Task, task_id)
            task.results = {**task.results, "auto_fix": {**(task.results.get("auto_fix") or {}), **values}}

    def set_task(self, task_id, enabled):
        """Tick or untick a task for Auto-fix (the list in Settings, or the task's Auto-fix / Stop auto-fix button)."""
        with self.supervisor._lock, self.db.Session.begin() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise LookupError("Task not found")
            fix = dict(task.results.get("auto_fix") or {})
            was_fixing = fix.get("status") == "fixing"
            fix.update(stopped=not enabled, chosen=bool(enabled), status="stopped" if not enabled else "waiting")
            if enabled:
                fix.update(attempts=0, last=None)  # a fresh set of attempts, starting with the current failure
            task.results = {**task.results, "auto_fix": fix}
            session.add(Event(task_id=task_id, kind="auto_fix", message="Owner stopped auto-fix for this task" if not enabled else "Owner chose this task for auto-fix"))
            chat_id, state, meeting = fix.get("chat"), task.state, fix.get("council")
        if not enabled:
            if chat_id:
                self.chats.stop(chat_id)
            if meeting and self.council is not None:
                self.council.stop(meeting)
            if was_fixing and state in {"READY", "RUNNING", "VERIFYING", "REVIEWING", "NEEDS_CHANGES"}:
                try:
                    self.supervisor.pause(task_id)  # stop the fix run that is going now; Resume continues it
                except ValueError:
                    pass
        with self.db.Session() as session:
            return session.get(Task, task_id).results.get("auto_fix")
