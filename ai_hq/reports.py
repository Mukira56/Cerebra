"""Plain-language task reports. Short sentences anyone can follow, built only from recorded facts."""
from __future__ import annotations

from pathlib import Path

from . import evidence
from .integrations import PROVIDERS

NAMES = {name: provider["label"] for name, provider in PROVIDERS.items()}
STATE_STORY = {
    "PENDING": ("📝", "Just created", "The task was written down. Nothing has started yet."),
    "PLANNING": ("🗺️", "Making a plan", "Cerebra is writing down the steps."),
    "AWAITING_APPROVAL": ("✋", "Waiting for you", "The work is paused until you say yes or no."),
    "READY": ("🚦", "Ready to start", "You said yes to the plan. Press Start when you are ready."),
    "RUNNING": ("🛠️", "Working on it", "An AI helper is writing code right now."),
    "VERIFYING": ("🧪", "Checking the code", "The tests are running to see if the code works."),
    "REVIEWING": ("🔍", "Second opinion", "A different AI helper is checking the work."),
    "NEEDS_CHANGES": ("🔧", "Fixing problems", "Something did not pass, so the code is being fixed."),
    "BLOCKED": ("⏸️", "Paused", "The task is paused. Nothing is lost. You can resume it."),
    "COMPLETED": ("✅", "All done", "The work is finished and was added to your project."),
    "FAILED": ("❌", "Stopped with a problem", "The task could not finish. The steps below show where it stopped."),
    "CANCELLED": ("🛑", "Cancelled", "The task was stopped on purpose. Nothing was added to your project."),
}
ROLE_WORDS = {"plan": "made the plan", "implement": "wrote the code", "review": "checked the code"}


def _name(provider, model=""):
    label = NAMES.get(provider, provider or "an AI helper")
    return f"{label} ({model})" if model else label


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def build(task, project, data_dir):
    state = task.get("state", "PENDING")
    pending = [approval for approval in task.get("approvals", []) if str(approval.get("status")).lower() == "pending"]
    emoji, headline, meaning = STATE_STORY.get(state, ("ℹ️", state.title(), "This is the current step."))
    if pending and pending[0]["kind"] == "merge":
        emoji, headline, meaning = "🎁", "Finished and waiting for you", "The code is written, tested and checked. Say yes to add it to your project."
    models = task.get("results", {}).get("models", {})
    helpers = []
    for role, key in (("plan", "planner"), ("implement", "implementer"), ("review", "reviewer")):
        chosen = models.get(key) or {}
        provider = chosen.get("provider") or {"implement": task.get("assigned_agent"), "review": task.get("reviewer"), "plan": "claude"}[role]
        helpers.append(f"{_name(provider, chosen.get('model', ''))} {ROLE_WORDS[role]}.")

    steps = []
    def step(icon, title, text, when=None, good=None):
        steps.append({"icon": icon, "title": title, "text": text, "when": when, "good": good})

    step("📝", "You asked for something", f"You wrote: “{task.get('description', '')[:400]}”", task.get("created_at"))
    approvals = sorted(task.get("approvals", []), key=lambda item: item.get("created_at") or "")
    for approval in approvals:
        status = str(approval.get("status")).lower()
        kind = approval.get("kind")
        words = {"plan": "the plan", "live_execution": "letting the AI helpers work", "merge": "adding the finished code to your project",
                 "review_findings": "the problems the checker found"}.get(kind, kind)
        if status == "approved":
            step("👍", "You said yes", f"You said yes to {words}.", approval.get("resolved_at"), True)
        elif status == "rejected":
            step("👎", "You said no", f"You said no to {words}.", approval.get("resolved_at"), False)
    for run in sorted(task.get("runs", []), key=lambda item: item.get("started_at") or ""):
        who = _name(run.get("agent"))
        action = {"plan": "made a plan", "implement": "wrote code", "review": "checked the code"}.get(run.get("role"), run.get("role"))
        if run.get("status") == "succeeded":
            step("🤖", f"{who} {action}", f"{who} {action}. It worked.", run.get("finished_at") or run.get("started_at"), True)
        elif run.get("status") == "running":
            step("⏳", f"{who} is working", f"{who} is busy right now. This can take a few minutes.", run.get("started_at"))
        else:
            reason = (run.get("error") or "").strip().splitlines()[0][:240] if (run.get("error") or "").strip() else "it did not say why"
            step("⚠️", f"{who} had a problem", f"{who} tried to {action.replace('made', 'make').replace('wrote', 'write').replace('checked', 'check')} but it did not work. The reason: {reason}", run.get("finished_at"), False)
    first, timeline = steps[0], sorted(steps[1:], key=lambda item: item["when"] or "")
    steps[:] = [first, *timeline]
    tests = task.get("test_results", [])
    baseline = task.get("results", {}).get("baseline")
    if baseline:
        broken = [item for item in baseline["commands"] if not item["passed"]]
        names = f" Failing: {', '.join(baseline['failing'][:5])}{'…' if len(baseline['failing']) > 5 else ''}." if baseline["failing"] else ""
        step("🩺", "Checked before changing anything", (f"Cerebra ran the tests on the untouched code first: {len(broken)} of {_plural(len(baseline['commands']), 'test check')} failed.{names}"
                                                       if broken else "Cerebra ran the tests on the untouched code first: they all passed."), baseline.get("recorded_at"), None)
    proof = evidence.compare(baseline, tests)
    if tests:
        passed = sum(1 for result in tests if result.get("passed"))
        good = passed == len(tests)
        step("🧪", "The tests ran", (f"All {_plural(len(tests), 'test check')} passed. The code works the way the tests expect." if good else
                                     f"{passed} of {_plural(len(tests), 'test check')} passed. The others failed, so the code needed fixing."), None, good)
    findings = task.get("review_findings", [])
    if any(run.get("role") == "review" and run.get("status") == "succeeded" for run in task.get("runs", [])):
        serious = [item for item in findings if item.get("severity") in {"critical", "high", "medium"}]
        step("🔍", "A second AI checked the work", "It found no problems." if not findings else
             f"It found {_plural(len(findings), 'note')}, and {len(serious)} of them looked important.", None, not serious)
    if task.get("retry_count"):
        step("🔧", "Problems were fixed", f"The code was fixed {_plural(task['retry_count'], 'time')} after a test or check failed.")
    for approval in approvals:
        if str(approval.get("status")).lower() == "pending":
            words = {"plan": "the plan", "live_execution": "letting the AI helpers work", "merge": "adding the finished code to your project",
                     "review_findings": "the problems the checker found"}.get(approval.get("kind"), approval.get("kind"))
            step("✋", "Cerebra is waiting for you", f"Cerebra needs you to say yes or no to {words}.", approval.get("created_at"))
    if state == "COMPLETED":
        step("🎉", "Added to your project", f"The finished code was added to the “{task.get('results', {}).get('base_branch') or project.get('default_branch', 'main')}” branch of {project.get('name')}.", task.get("updated_at"), True)
    if state == "FAILED" and task.get("results", {}).get("error"):
        step("❌", "Why it stopped", task["results"]["error"].splitlines()[0][:400], task.get("updated_at"), False)

    data_dir = Path(data_dir)
    saved = [
        {"what": "The task's history (every step above)", "where": str(data_dir / "hq.sqlite3"), "explain": "A small database file on this computer. Cerebra writes every step into it."},
        {"what": "Your project", "where": project.get("path", ""), "explain": "The folder with your code. Finished work is added here only after you say yes."},
    ]
    if task.get("worktree_path"):
        saved.append({"what": "The AI's working copy", "where": task["worktree_path"], "explain": f"A separate copy of your project where the AI did its work, on the branch “{task.get('branch')}”. Your main code is not touched until you approve."})
    if task.get("runs"):
        saved.append({"what": "What each AI helper said", "where": str(data_dir / "logs"), "explain": f"One text file per AI run ({_plural(len(task['runs']), 'file')} for this task), named after the run."})
    if task.get("results", {}).get("architecture", {}).get("artifact"):
        saved.append({"what": "The plan the AI wrote", "where": task["results"]["architecture"]["artifact"], "explain": "A text file with the AI's plan."})

    changed = task.get("results", {}).get("changed_paths", [])
    next_step = ("Nothing to do. You can open your project to see the new code." if state == "COMPLETED" else
                 "Go to Approvals and say yes or no." if pending else
                 "Press Start on the task." if state == "READY" else
                 "Read why it stopped, change the request if needed, and create a new task." if state == "FAILED" else
                 "Open the task and press Resume." if state == "BLOCKED" else
                 "Wait a little. This page updates by itself.")
    return {"task_id": task.get("id"), "project": project.get("name"), "emoji": emoji, "headline": headline, "meaning": meaning,
            "asked": task.get("description", ""), "helpers": helpers, "steps": steps, "changed_files": changed,
            "saved": saved, "next": next_step, "state": state, "updated_at": task.get("updated_at"), "evidence": proof}
