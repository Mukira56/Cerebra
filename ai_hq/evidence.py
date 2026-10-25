"""Before/after test evidence for a job: what failed on the untouched code, and what passes after the change.

Built only from recorded test runs. Failing test names are read from common runners' output (pytest, unittest,
Jest/Vitest, Go, Cargo, .NET, Maven); when a runner's format isn't recognised, only the command's pass/fail is
reported. Nothing here runs a command.
"""
from __future__ import annotations

import re

MAX_NAMES = 50
TAIL = 4000
PATTERNS = [
    re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)", re.M),                  # pytest short summary
    re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.M),           # unittest
    re.compile(r"^\s*[✕×✗]\s+(.+?)(?:\s+\(\d+(?:\.\d+)?\s*m?s\))?\s*$", re.M),  # Jest / Vitest
    re.compile(r"^\s*--- FAIL: (\S+)", re.M),                           # go test
    re.compile(r"^test (\S+) \.\.\. FAILED", re.M),                     # cargo test
    re.compile(r"^\s*Failed (\S+) \[", re.M),                           # dotnet test
    re.compile(r"^\[ERROR\]\s+(\S+)(?::\d+)?\s+(?:»|Time elapsed)", re.M),  # Maven surefire
]


def failing_tests(text):
    """Names of failing tests found in a runner's output, in order, without duplicates."""
    names = []
    for pattern in PATTERNS:
        for match in pattern.finditer(text or ""):
            groups = [group for group in match.groups() if group]
            name = f"{groups[1]}.{groups[0]}" if pattern is PATTERNS[1] else groups[0]
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return names[:MAX_NAMES]


def summarize(results):
    """Compact record of one set of test runs: per command pass/fail, failing names and an output tail."""
    commands = []
    for result in results:
        output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
        commands.append({"command": result.get("command"), "passed": bool(result.get("passed")), "exit_code": result.get("exit_code"),
                         "timed_out": bool(result.get("timed_out")), "duration_seconds": result.get("duration_seconds"),
                         "failing": [] if result.get("passed") else failing_tests(output), "output_tail": output.strip()[-TAIL:]})
    return {"passed": bool(commands) and all(item["passed"] for item in commands), "commands": commands,
            "failing": list(dict.fromkeys(name for item in commands for name in item["failing"]))[:MAX_NAMES]}


def latest_attempt(test_results):
    """The verification runs of the most recent attempt (each repair attempt re-runs every command)."""
    if not test_results:
        return []
    last = max(result.get("attempt", 0) for result in test_results)
    return [result for result in test_results if result.get("attempt", 0) == last]


def compare(baseline, test_results):
    """Plain-language before/after verdict; never claims more than the recorded runs show."""
    after = summarize(latest_attempt(test_results)) if test_results else None
    if not baseline:
        return {"available": False, "text": "No before-the-change test run was recorded for this job (it started before Cerebra 0.16)."}
    before_count = sum(1 for item in baseline["commands"] if not item["passed"])
    total = len(baseline["commands"])
    if after is None:
        verdict = "not_yet"
        text = (f"Before the change, {before_count} of {total} test command{'s' if total != 1 else ''} failed."
                if before_count else "Before the change, all tests passed.") + " The change hasn't been tested yet."
        return {"available": True, "verdict": verdict, "text": text, "before": baseline, "after": None, "fixed": [], "still_failing": [], "newly_failing": []}
    before_names, after_names = set(baseline["failing"]), set(after["failing"])
    fixed = [name for name in baseline["failing"] if name not in after_names]
    still = [name for name in after["failing"] if name in before_names]
    new = [name for name in after["failing"] if name not in before_names]
    if before_count and after["passed"]:
        verdict = "fixed"
        detail = f" ({len(fixed)} named test{'s' if len(fixed) != 1 else ''} now pass)" if fixed else ""
        text = f"Proof of the fix: the tests failed before the change and all pass after it{detail}."
    elif not before_count and after["passed"]:
        verdict = "still_passing"
        text = ("The tests passed before and after the change: nothing they cover broke. "
                "They don't prove the new behaviour unless a test for it was added.")
    elif before_count and not after["passed"]:
        verdict = "still_failing"
        text = "The tests failed before the change and still fail after it, so this isn't proven fixed yet."
    else:
        verdict = "broke"
        text = "The tests passed before the change but fail after it: the change broke something."
    return {"available": True, "verdict": verdict, "text": text, "before": baseline, "after": after, "fixed": fixed, "still_failing": still, "newly_failing": new}
