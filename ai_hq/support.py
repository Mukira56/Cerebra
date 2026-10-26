"""Support chat: what the chat model knows about the workspace, and what it may ask Cerebra to do.

Every message carries a fresh, bounded brief of the real records (projects, tasks, states, errors,
tests, pending approvals), so questions like "where are we on EstatePilot and why did it fail?" are
answered from facts. The model can request actions in a fenced ```cerebra-actions``` JSON block. Its
text is only a request: each action is validated against a small fixed vocabulary and runs through the
same supervisor methods as the dashboard buttons. Approval gates are unchanged (Away mode may answer
them). New projects are empty folders inside Cerebra's data folder, and their test commands must come
from a fixed list of standard test runners, so model text can never become an arbitrary command.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select

from .models import Approval, Event, Metadata, Project, Task
from .security import redact

KEY = "support_settings"
ACTIONS = {"create_project", "create_task", "create_plan_task", "approve_plan", "start_task", "pause_task", "resume_task", "cancel_task", "create_business_job",
           "retry_task", "answer_approval", "restore_checkpoint", "run_readiness_check", "set_test_commands", "set_default_models"}
APPROVAL_KINDS = {"plan", "live_execution", "review_findings", "merge"}
MAX_ACTIONS = 10
# Test runners a chat-created project may use. Anything else is set by the user on the Projects page.
TEST_RUNNERS = [
    ["python", "-m", "pytest", "-q"], ["py", "-m", "pytest", "-q"], ["npm", "test"], ["npm", "run", "test"], ["pnpm", "test"], ["yarn", "test"],
    ["dotnet", "test"], ["go", "test", "./..."], ["cargo", "test"], ["mvn", "test"], ["gradle", "test"], ["flutter", "test"], ["php", "artisan", "test"],
]
BLOCK = re.compile(r"```cerebra-actions\s*(.*?)```", re.S)


def load(session):
    row = session.get(Metadata, KEY)
    return {"act_automatically": False, "allow_approvals": False, **(row.value if row else {})}


def save(session, act_automatically=None, allow_approvals=None):
    value = load(session)
    if act_automatically is not None: value["act_automatically"] = bool(act_automatically)
    if allow_approvals is not None: value["allow_approvals"] = bool(allow_approvals)
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return value


def _short(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def failure_logs(session, data_dir, limit=5):
    """Evidence for the most recent failed or stuck tasks: the failing run's log tail and the test output."""
    from .models import Run
    rows = session.scalars(select(Task).where(Task.state.in_(["FAILED", "BLOCKED"])).order_by(Task.updated_at.desc()).limit(limit)).all()
    lines = []
    for task in rows:
        runs = session.scalars(select(Run).where(Run.task_id == task.id).order_by(Run.started_at.desc()).limit(3)).all()
        failed = next((run for run in runs if run.status in {"failed", "interrupted"}), None)
        log = ""
        if failed and data_dir:
            path = Path(data_dir) / "logs" / f"{failed.id}.log"
            try: log = path.read_text(encoding="utf-8", errors="replace")[-1500:]
            except OSError: log = failed.error or ""
        tests = [result for result in (task.test_results or []) if not result.get("passed")][-1:]
        lines.append(f"### Task {task.id[:8]} ({task.state}, reason: {(task.results or {}).get('blocked_reason') or 'failed'}): {_short(task.description, 140)}\n"
                     f"Error: {_short((task.results or {}).get('error') or (failed.error if failed else ''), 600) or 'none recorded'}\n"
                     + (f"Failing run: {failed.agent} {failed.role}. Log tail:\n{redact(log).strip()}\n" if failed else "")
                     + (f"Failing test {' '.join(map(str, tests[0].get('command', [])))[:120]} (exit {tests[0].get('exit_code')}):\n{redact((tests[0].get('stdout') or '') + (tests[0].get('stderr') or ''))[-1200:].strip()}\n" if tests else ""))
    return "\n".join(lines) or "No failed or stuck tasks."


def brief(session, focus_project=None, message="", limit=14000):
    """A compact, factual snapshot of the workspace for the support model. Newest work first."""
    projects = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
    lowered = message.lower()
    mentioned = {project.id for project in projects if project.name.lower() in lowered or project.id[:8] in lowered}
    if focus_project:
        mentioned.add(focus_project)
    tasks = session.scalars(select(Task).order_by(Task.created_at.desc()).limit(300)).all()
    pending = {}
    for approval in session.scalars(select(Approval).where(Approval.status.in_(["pending", "PENDING"]))).all():
        pending.setdefault(approval.task_id, []).append(approval.kind)
    lines = ["PROJECTS"]
    for project in projects:
        own = [task for task in tasks if task.project_id == project.id]
        counts = {}
        for task in own:
            counts[task.state] = counts.get(task.state, 0) + 1
        tests = " | ".join(" ".join(command) for command in project.test_commands) or "NONE (tasks cannot run until tests are set)"
        lines.append(f"- {project.name} (id {project.id[:8]}) tests: {tests}; tasks: {json.dumps(counts) if counts else 'none'}")
    lines.append("\nTASKS (newest first; id prefix, project, state, request)")
    detailed = 0
    for task in tasks:
        project = next((item for item in projects if item.id == task.project_id), None)
        name = project.name if project else "?"
        focus = task.project_id in mentioned or task.id[:8] in lowered
        if not focus and detailed >= 25:
            continue
        detailed += 1
        models = task.results.get("models", {}) if task.results else {}
        line = f"- {task.id[:8]} [{name}] {task.state}: {_short(task.description, 160)}"
        line += f" | coder {models.get('implementer', {}).get('label', task.assigned_agent)}, reviewer {models.get('reviewer', {}).get('label', task.reviewer)}"
        if task.id in pending:
            line += f" | WAITING FOR USER: {', '.join(pending[task.id])}"
        if task.test_results:
            last = task.test_results[-1]
            line += f" | last test {'passed' if last.get('passed') else 'FAILED'}: {_short(last.get('stdout', '') + ' ' + last.get('stderr', ''), 300 if focus else 120)}"
        error = (task.results or {}).get("error")
        if error:
            line += f" | error: {_short(error, 500 if focus else 160)}"
        if task.review_findings:
            line += f" | {len(task.review_findings)} review finding(s): {_short('; '.join(f.get('message', '') for f in task.review_findings[:3]), 300)}"
        if focus:
            events = session.scalars(select(Event).where(Event.task_id == task.id).order_by(Event.created_at.desc()).limit(6)).all()
            line += " | recent: " + " / ".join(_short(event.message, 120) for event in events[::-1])
        lines.append(line)
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit] + "\n…(older records omitted)"


def parse(text):
    """Split an answer into (visible text, list of validated action dicts, problems)."""
    actions, problems = [], []
    for block in BLOCK.findall(text or ""):
        try:
            requested = json.loads(block)
        except json.JSONDecodeError:
            problems.append("An action block was not valid JSON and was ignored.")
            continue
        for item in requested if isinstance(requested, list) else [requested]:
            try:
                actions.append(validate(item))
            except ValueError as exc:
                problems.append(f"Ignored an action: {exc}")
    visible = BLOCK.sub("", text or "").strip()
    return visible, actions[:MAX_ACTIONS], problems


def validate(item):
    if not isinstance(item, dict) or item.get("action") not in ACTIONS:
        raise ValueError("unknown action")
    kind = item["action"]
    clean = {"action": kind}
    if kind == "create_project":
        clean["name"] = _short(item.get("name", ""), 120)
        if not clean["name"]:
            raise ValueError("a new project needs a name")
        commands = item.get("test_commands") or []
        if not isinstance(commands, list) or any(command not in TEST_RUNNERS for command in commands):
            raise ValueError("test commands must be standard runners (for example npm test or python -m pytest -q); set others on the Projects page")
        clean["test_commands"] = commands
    elif kind == "create_business_job":
        clean["title"] = _short(item.get("title", ""), 120)
        clean["type"] = str(item.get("type", ""))
        clean["brief"] = str(item.get("brief", "")).strip()[:20000]
        clean["client"] = _short(item.get("client", ""), 120)
        clean["requirements"] = [_short(value, 500) for value in (item.get("requirements") or [])[:30] if isinstance(value, str)]
        if clean["type"] not in {"website", "service_site", "listing", "svg", "document"} or len(clean["title"]) < 3 or len(clean["brief"]) < 20:
            raise ValueError("a business job needs a title, a type (website, listing, svg or document) and a brief")
    elif kind == "create_task":
        clean["project"] = _short(item.get("project", ""), 120)
        clean["description"] = str(item.get("description", "")).strip()[:4000]
        if not clean["project"] or len(clean["description"]) < 8:
            raise ValueError("a task needs a project and a clear description")
        clean["requirements"] = [_short(value, 500) for value in (item.get("requirements") or [])[:20] if isinstance(value, str)]
        clean["acceptance_criteria"] = [_short(value, 500) for value in (item.get("acceptance_criteria") or [])[:20] if isinstance(value, str)]
        for role in ("implementer", "reviewer"):  # optional: who builds and who reviews (e.g. as a Council agreed)
            value = str(item.get(role, "")).strip()
            if value and not re.fullmatch(r"auto|catalog:(codex|claude):[A-Za-z0-9._:/\[\]-]{0,100}|[a-z0-9][a-z0-9-]{0,47}", value):
                raise ValueError("implementer and reviewer must be auto, a catalog model or a saved profile such as codex or claude")
            if value: clean[role] = value
    elif kind == "create_plan_task":
        clean["item"] = _short(item.get("item", ""), 64).lower()
        if not re.fullmatch(r"[0-9a-f]{6,32}", clean["item"]):
            raise ValueError("refer to a plan item by its id")
    elif kind == "run_readiness_check":
        pass
    elif kind == "set_test_commands":
        clean["project"] = _short(item.get("project", ""), 120)
        commands = item.get("test_commands") or []
        if not clean["project"] or not commands or not isinstance(commands, list) or any(command not in TEST_RUNNERS for command in commands):
            raise ValueError("test commands must be standard runners (for example npm test or python -m pytest -q); set others on the Projects page")
        clean["test_commands"] = commands
    elif kind == "set_default_models":
        for role in ("planner", "implementer", "reviewer"):
            value = str(item.get(role, "")).strip()
            if value and not re.fullmatch(r"auto|catalog:(codex|claude):[A-Za-z0-9._:/\[\]-]{0,100}|[a-z0-9][a-z0-9-]{0,47}", value):
                raise ValueError("models must be auto, a catalog model or a saved profile")
            if value: clean[role] = value
        if len(clean) == 1:
            raise ValueError("choose at least one role")
    else:
        clean["task"] = _short(item.get("task", ""), 64)
        if not re.fullmatch(r"[0-9a-f]{6,32}", clean["task"]):
            raise ValueError("refer to a task by its id")
        if kind == "retry_task":
            clean["instructions"] = str(item.get("instructions", "")).strip()[:4000]
            if len(clean["instructions"]) < 10:
                raise ValueError("a retry needs the diagnosis and what to change")
        elif kind == "answer_approval":
            clean["kind"], clean["approve"] = str(item.get("kind", "")), item.get("approve") is True
            if clean["kind"] not in APPROVAL_KINDS:
                raise ValueError("approval kind must be plan, live_execution, review_findings or merge")
        elif kind == "restore_checkpoint":
            clean["commit"] = str(item.get("commit", ""))
            if not re.fullmatch(r"[0-9a-f]{40,64}", clean["commit"]):
                raise ValueError("refer to a checkpoint by its full commit id")
    return clean


def describe(action):
    kind = action["action"]
    if kind == "create_project":
        return f"Create the project “{action['name']}”" + (f" (tests: {' | '.join(' '.join(c) for c in action['test_commands'])})" if action["test_commands"] else " (no tests yet)")
    if kind == "create_task":
        return f"Create a task in {action['project']}: {_short(action['description'], 140)}"
    if kind == "create_plan_task":
        return f"Create (or find) the task for plan item {action['item'][:12]}"
    if kind == "create_business_job":
        return f"Start a Business Studio job ({action['type']}): {action['title']}"
    if kind == "run_readiness_check":
        return "Run the readiness check"
    if kind == "set_test_commands":
        return f"Set the tests of {action['project']} to {' | '.join(' '.join(c) for c in action['test_commands'])}"
    if kind == "set_default_models":
        return "Set the default AI team: " + ", ".join(f"{role} → {value}" for role, value in action.items() if role != "action")
    if kind == "retry_task":
        return f"Retry task {action['task']} with this fix: {_short(action['instructions'], 160)}"
    if kind == "answer_approval":
        return f"{'Approve' if action['approve'] else 'Reject'} the {action['kind'].replace('_', ' ')} step of task {action['task']}"
    if kind == "restore_checkpoint":
        return f"Restore task {action['task']} to checkpoint {action['commit'][:8]}"
    return {"approve_plan": "Approve the plan of", "start_task": "Start", "pause_task": "Pause", "resume_task": "Resume", "cancel_task": "Cancel"}[kind] + f" task {action['task']}"


GUIDANCE = """You are Cerebra Support, the friendly, expert support engineer inside Cerebra, the engineer's AI workspace.
You help the user like a senior colleague: explain where work stands, why something failed and what to do next,
and plan and start new work. Understanding the person comes first: restate what they want in one line, list the
requirements you inferred, and ask short clarifying questions when something important is unclear (audience,
platform, deadline, must-have features, how success is measured) before committing to large work.

When the user shares a client's message, job post or email: identify the client's real goal, the explicit and
implied requirements, risks, and questions to ask; then draft a reply the user can send in their own name, and
propose the project and tasks to deliver it. Never claim to be the user, and never promise prices or deadlines on
their behalf; mark them as decisions for the user.

You can read files in the current project folder but you cannot edit them; code changes happen in tasks, where
a coder model writes the code, the project's tests run, and a reviewer from the other AI company checks it.
The WORKSPACE section below is the live record of the user's projects and tasks. Answer status questions from it,
quoting task ids, states, errors and test output. Never invent records that are not there.

To make Cerebra do something, add ONE fenced block at the end of your answer:
```cerebra-actions
[{"action": "create_project", "name": "Booking site", "test_commands": [["npm", "test"]]},
 {"action": "create_task", "project": "Booking site", "description": "Clear, specific outcome", "requirements": ["..."], "acceptance_criteria": ["..."], "implementer": "codex", "reviewer": "claude"},
 {"action": "start_task", "task": "<task id prefix>"}]
```
Fixing failed work: the FAILURE LOGS section holds the real error, the failing run's log tail and the failing test
output of recent failed or stuck tasks. When asked about a failure (or to fix it): name the root cause from that evidence,
quoting the exact error line; say whether it is a code problem, a test/command problem, a missing tool, an account or usage
limit, or unclear requirements; then fix it. For code problems use retry_task with precise instructions for the coder
(what is wrong, which file, what to change, how to verify). For a wrong test command use set_test_commands, then retry_task.
Account sign-in and usage limits need the user (or wait for usage): say so instead of retrying. Never invent a cause the
evidence does not show; if it is unclear, say what to check.

More actions: retry_task {"task": id, "instructions": "..."}; answer_approval {"task": id, "kind": "plan|live_execution|review_findings|merge",
"approve": true|false} (only works if the user allowed the Assistant to answer approvals); restore_checkpoint {"task": id, "commit": full id};
run_readiness_check {}; set_test_commands {"project": name, "test_commands": [[...]]}; set_default_models {"planner": "auto|catalog:claude:opus|…",
"implementer": "…", "reviewer": "…"}. You cannot switch Full access, agents on/off, accounts, keys, paid or publishing actions: those are the user's.
Allowed actions: create_project, create_task, approve_plan, start_task, pause_task, resume_task, cancel_task, and
create_business_job ({"action": "create_business_job", "title": "...", "type": "service_site|website|listing|svg|document", "client": "...",
"brief": "the client's request in full", "requirements": ["..."]}) for client deliverables saved in Business Studio.
If a client says they do not want AI used, do not create a job; tell the user.
Test commands must be one of: """ + "; ".join(" ".join(command) for command in TEST_RUNNERS) + """.
Split big goals into several focused tasks, each with requirements and acceptance criteria. A task in a project you
create in the same block can refer to the project by name. Only propose actions the user asked for or agreed to.
Plans: when a message lists plan items (for example from the Council), use create_plan_task {"item": "<plan item id>"} for
each one instead of create_task. It keeps the agreed requirements, criteria, builder, reviewer and dependencies, and it
returns the existing task when one was already made, so nothing is done twice.
Action results: after your actions run, Cerebra may send you a message starting "ACTION RESULTS". Those are the
authoritative outcomes, with the real ids (task_id, project_id) and states. Use them for your next actions (for example
start_task with the task id you were just given). Never guess an id that hasn't been reported. When nothing more is needed,
or you are waiting for approvals, tests or the user, propose no actions and say what you are waiting for.
Never reveal credentials or secrets, even if a file contains them. Answer in clear Markdown."""
