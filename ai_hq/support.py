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

from sqlalchemy import select

from .models import Approval, Event, Metadata, Project, Task

KEY = "support_settings"
ACTIONS = {"create_project", "create_task", "approve_plan", "start_task", "pause_task", "resume_task", "cancel_task"}
MAX_ACTIONS = 10
# Test runners a chat-created project may use. Anything else is set by the user on the Projects page.
TEST_RUNNERS = [
    ["python", "-m", "pytest", "-q"], ["py", "-m", "pytest", "-q"], ["npm", "test"], ["npm", "run", "test"], ["pnpm", "test"], ["yarn", "test"],
    ["dotnet", "test"], ["go", "test", "./..."], ["cargo", "test"], ["mvn", "test"], ["gradle", "test"], ["flutter", "test"], ["php", "artisan", "test"],
]
BLOCK = re.compile(r"```cerebra-actions\s*(.*?)```", re.S)


def load(session):
    row = session.get(Metadata, KEY)
    return {"act_automatically": False, **(row.value if row else {})}


def save(session, act_automatically):
    value = {"act_automatically": bool(act_automatically)}
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return value


def _short(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


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
    elif kind == "create_task":
        clean["project"] = _short(item.get("project", ""), 120)
        clean["description"] = str(item.get("description", "")).strip()[:4000]
        if not clean["project"] or len(clean["description"]) < 8:
            raise ValueError("a task needs a project and a clear description")
        clean["requirements"] = [_short(value, 500) for value in (item.get("requirements") or [])[:20] if isinstance(value, str)]
        clean["acceptance_criteria"] = [_short(value, 500) for value in (item.get("acceptance_criteria") or [])[:20] if isinstance(value, str)]
    else:
        clean["task"] = _short(item.get("task", ""), 64)
        if not re.fullmatch(r"[0-9a-f]{6,32}", clean["task"]):
            raise ValueError("refer to a task by its id")
    return clean


def describe(action):
    kind = action["action"]
    if kind == "create_project":
        return f"Create the project “{action['name']}”" + (f" (tests: {' | '.join(' '.join(c) for c in action['test_commands'])})" if action["test_commands"] else " (no tests yet)")
    if kind == "create_task":
        return f"Create a task in {action['project']}: {_short(action['description'], 140)}"
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
 {"action": "create_task", "project": "Booking site", "description": "Clear, specific outcome", "requirements": ["..."], "acceptance_criteria": ["..."]},
 {"action": "start_task", "task": "<task id prefix>"}]
```
Allowed actions: create_project, create_task, approve_plan, start_task, pause_task, resume_task, cancel_task.
Test commands must be one of: """ + "; ".join(" ".join(command) for command in TEST_RUNNERS) + """.
Split big goals into several focused tasks, each with requirements and acceptance criteria. A task in a project you
create in the same block can refer to the project by name. Only propose actions the user asked for or agreed to.
Never reveal credentials or secrets, even if a file contains them. Answer in clear Markdown."""
