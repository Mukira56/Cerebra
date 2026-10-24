"""Test-only fixture agent. Never shipped as a product mode; tests must not launch real CLIs."""
from __future__ import annotations

import ast
import json

from pathlib import Path

from ai_hq.agents import AgentRegistry, AgentRequest, AgentResult, _allows, _request_directory
from ai_hq.processes import ProcessRunner
from ai_hq.security import canonical, redact


class FixtureAgent:
    """Deterministic calculator fixture used only by tests; never general AI."""
    def __init__(self, name="mock-codex", runner=None):
        self.name = name
        self.runner = runner or ProcessRunner()

    def execute(self, request: AgentRequest, cancel_event=None) -> AgentResult:
        if cancel_event is not None and cancel_event.is_set():
            return AgentResult(False, "[SIMULATED] Cancelled", simulated=True, error="cancelled")
        try:
            directory = _request_directory(request)
            if request.role.lower() in {"plan", "planning", "architecture"}:
                return AgentResult(True, "[SIMULATED] Plan: inspect calculator.py, correct addition, run registered tests, obtain independent review, request integration approval.", simulated=True)
            marker = canonical(directory / ".ai-hq-demo.json", [directory])
            if marker.stat().st_size > 4096:
                raise ValueError("Unsupported demo fixture: marker is too large")
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            if marker.is_symlink() or not isinstance(metadata, dict) or metadata.get("kind") != "calculator-addition-v1":
                raise ValueError("Unsupported demo fixture")
            if not any(word in request.description.lower() for word in ("demo", "calculator", "addition", "add(")):
                raise ValueError("Mock adapters support only the calculator addition demonstration")
            filename = directory / "calculator.py"
            if filename.is_symlink() or (getattr(filename.lstat(), "st_file_attributes", 0) & 0x400):
                raise ValueError("Demo source cannot be a symlink or reparse point")
            filename = canonical(filename, [directory])
            if filename.stat().st_size > 1024 * 1024:
                raise ValueError("Unsupported calculator fixture: source is too large")
            source = filename.read_text(encoding="utf-8")
            tree = ast.parse(source)
            add = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "add"), None)
            if add is None or [arg.arg for arg in add.args.args] != ["a", "b"]:
                raise ValueError("Unsupported calculator fixture: expected add(a, b)")
            role = request.role.lower()
            if role in {"review", "reviewing", "security", "security_review"}:
                actual = add.body[-1]
                correct = isinstance(actual, ast.Return) and isinstance(actual.value, ast.BinOp) and isinstance(actual.value.op, ast.Add) and isinstance(actual.value.left, ast.Name) and actual.value.left.id == "a" and isinstance(actual.value.right, ast.Name) and actual.value.right.id == "b"
                findings = [] if correct else [{"severity": "high", "code": "DEMO_ADD_INCORRECT", "file": "calculator.py", "path": "calculator.py", "line": actual.lineno, "message": "The demonstration addition function does not return a + b.", "evidence": source.splitlines()[actual.lineno - 1], "verified": False}]
                return AgentResult(True, "[SIMULATED] Independent static review of the calculator fixture; actual tests are run by the supervisor.", findings, simulated=True)
            if role not in {"implement", "implementation", "repair", "coding", "debug", "debugging"}:
                raise ValueError("Unsupported mock role")
            if not _allows("calculator.py", request.allowed_paths):
                raise ValueError("calculator.py is outside this task's allowed paths")
            if len(add.body) != 1 or not isinstance(add.body[0], ast.Return):
                raise ValueError("Unsupported calculator fixture: expected one return statement")
            replacement = "    return a + b + 1" if "[demo:needs-repair]" in request.description and request.attempt == 0 else "    return a + b"
            lines = source.splitlines(keepends=True)
            statement = add.body[0]
            lines[statement.lineno - 1:statement.end_lineno] = [replacement + "\n"]
            filename.write_text("".join(lines), encoding="utf-8")
            return AgentResult(True, "[SIMULATED] Updated calculator.py in the isolated fixture. Completion remains subject to actual test execution and independent review.", simulated=True)
        except (OSError, ValueError, SyntaxError, StopIteration, json.JSONDecodeError) as exc:
            return AgentResult(False, "[SIMULATED] No supported work completed.", simulated=True, error=redact(str(exc)))


class FixtureRegistry(AgentRegistry):
    """In-process stand-in for the provider CLIs: no process, authentication or billing is used."""
    def __init__(self, planner_modifies=False):
        super().__init__()
        self.planner_modifies = planner_modifies
        self.fixture = FixtureAgent("fixture")
        self.requests = []

    def probe(self, authenticate=False):
        return {name: {"name": name, "available": True, "execution_allowed": True, "fixture": True} for name in ("codex", "claude")}

    def execute(self, name, request, cancel_event=None):
        if name not in {"codex", "claude"}:
            raise ValueError(f"Unknown agent: {name}")
        self.requests.append((name, request))
        if request.role == "plan" and self.planner_modifies:
            (Path(request.workdir) / "calculator.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
        result = self.fixture.execute(request, cancel_event)
        # Supervisor rejects simulated output, exactly as it would from a real provider.
        return AgentResult(result.success, result.output.replace("[SIMULATED] ", "Fixture: "), result.findings, simulated=False, error=result.error)

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.requests.append((name, prompt))
        return AgentResult(True, f"Fixture answer from {name}" + (f" ({model})" if model else ""))
