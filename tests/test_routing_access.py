"""Model catalog, automatic routing (rules and supervisor model) and the full-access level.

No provider CLI is launched: commands are captured by fixture runners and the supervisor model is a fixture.
"""
import json

import pytest
from fastapi.testclient import TestClient

from ai_hq import routing
from ai_hq.agents import AgentRequest, AgentResult, ClaudeAdapter, CodexAdapter
from ai_hq.api import create_app
from ai_hq.catalog import catalog, codex_models
from ai_hq.config import Settings
from ai_hq.processes import ProcessResult
from fakes import FixtureRegistry
from test_product_api import KEY, calculator, enable_agents

CACHE = {"models": [
    {"slug": "gpt-frontier", "display_name": "GPT Frontier", "description": "Frontier intelligence for the most demanding work.", "visibility": "list", "priority": 2},
    {"slug": "gpt-work", "display_name": "GPT Work", "description": "Latest workhorse model for coding and everyday work.", "visibility": "list", "priority": 1},
    {"slug": "gpt-quick", "display_name": "GPT Quick", "description": "Fast and affordable model for easier tasks.", "visibility": "list", "priority": 5},
    {"slug": "gpt-old", "display_name": "GPT Old", "description": "Older generation workhorse model.", "visibility": "list", "priority": 6},
    {"slug": "hidden", "display_name": "Hidden", "description": "internal", "visibility": "hide", "priority": 3},
]}


@pytest.fixture
def home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    (folder / ".codex").mkdir(parents=True)
    (folder / ".codex" / "models_cache.json").write_text(json.dumps(CACHE), encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: folder)
    return folder


@pytest.fixture
def client(tmp_path, home):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = FixtureRegistry()
    app.state.supervisor._spawn = lambda function, *args: function(*args)  # run the supervisor model inline
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def test_codex_catalog_comes_from_its_cache_and_tiers_models(home):
    models = {item["model"]: item for item in codex_models()}
    assert list(models) == ["gpt-work", "gpt-frontier", "gpt-quick", "gpt-old"]
    assert (models["gpt-frontier"]["tier"], models["gpt-work"]["tier"], models["gpt-quick"]["tier"], models["gpt-old"]["tier"]) == ("frontier", "balanced", "fast", "")
    assert [item["model"] for item in codex_models(home / "missing")] == [""]  # fallback: Codex's default
    assert {item["label"] for item in catalog()["claude"]} >= {"Claude Opus 5.5", "Claude Sonnet 5.5", "Claude Haiku 5.5"}


def test_rules_match_model_strength_to_task_difficulty(home):
    hard = routing.route(routing.assess("Redesign the authentication architecture and fix the race condition"))
    assert (hard["planner"]["model"], hard["implementer"]["model"], hard["reviewer"]["model"]) == ("opus", "gpt-frontier", "opus")
    easy = routing.route(routing.assess("Fix a typo in a label", allowed_paths=["src/app.js"]))
    assert (easy["implementer"]["provider"], easy["implementer"]["model"], easy["reviewer"]["provider"]) == ("codex", "gpt-quick", "claude")
    writing = routing.route(routing.assess("Write the user guide documentation for installing the app"))
    assert writing["implementer"]["provider"] == "claude" and writing["reviewer"]["provider"] == "codex"
    fixed = routing.route(routing.assess("Add a feature"), fixed={"implementer": {"provider": "claude", "model": "opus", "label": "x"}})
    assert fixed["reviewer"]["provider"] == "codex"


def test_auto_task_records_routing_and_reaches_agents_with_models(client, tmp_path):
    enable_agents(client)
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition"}).json()
    chosen, record = task["results"]["models"], task["results"]["routing"]
    assert record["decided_by"] == "supervisor rules" and set(record["automatic"]) == {"planner", "implementer", "reviewer"}
    assert chosen["implementer"]["provider"] != chosen["reviewer"]["provider"] and chosen["implementer"]["model"]
    picked = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition", "implementer": "catalog:claude:opus"}).json()
    assert picked["results"]["models"]["implementer"]["model"] == "opus" and picked["results"]["models"]["reviewer"]["provider"] == "codex"
    assert client.put("/api/models/roles", json={"implementer": "catalog:codex:gpt-quick", "planner": "auto"}).json()["implementer"] == "catalog:codex:gpt-quick"


class RouterRegistry(FixtureRegistry):
    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.requests.append((name, model, prompt))
        return AgentResult(True, self.answer)


@pytest.mark.parametrize("answer,applied", [
    ('{"planner": {"provider": "codex", "model": "gpt-work"}, "implementer": {"provider": "claude", "model": "sonnet"}, "reviewer": {"provider": "codex", "model": "gpt-frontier"}, "reason": "Claude for the UI copy."}', True),
    ('{"planner": {"provider": "claude", "model": "opus"}, "implementer": {"provider": "codex", "model": "gpt-work"}, "reviewer": {"provider": "codex", "model": "gpt-work"}}', False),
    ('{"planner": {"provider": "claude", "model": "made-up"}}', False),
    ("I think Opus.", False),
])
def test_supervisor_model_choice_is_validated(client, tmp_path, answer, applied):
    enable_agents(client)
    client.app.state.supervisor.registry = RouterRegistry(answer)
    assert client.put("/api/routing", json={"mode": "model", "provider": "claude", "model": "opus"}).json()["mode"] == "model"
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition"}).json()
    detail = client.get(f"/api/tasks/{task['id']}").json()
    name, model, prompt = client.app.state.supervisor.registry.requests[0]
    assert (name, model) == ("claude", "opus") and "gpt-frontier" in prompt
    assert detail["results"]["routing"]["status"] == "done"
    assert (detail["results"]["routing"]["decided_by"] == "supervisor model") is applied
    assert (detail["results"]["models"]["implementer"]["model"] == "sonnet") is applied
    if applied:
        assert detail["assigned_agent"] == "claude" and detail["reviewer"] == "codex"
        plan = next(row for row in detail["approvals"] if row["kind"] == "plan")
        assert plan["payload"]["models"]["implementer"]["model"] == "sonnet"
    assert any(event["kind"] == "routing" for event in detail["events"])


def test_full_access_needs_agents_on_and_both_acknowledgements(client):
    assert client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True}).status_code == 400
    enable_agents(client)
    assert client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True}).status_code == 400
    settings = client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True}).json()
    assert settings["full_access"] and client.app.state.supervisor.registry.full_access
    assert client.post("/api/permissions/full-access", json={"enabled": False}).json()["full_access"] is False
    client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True})
    assert client.post("/api/permissions", json={"enabled": False}).json()["full_access"] is False  # agents off resets it


def captured(adapter_class, tmp_path, role, full_access):
    seen = {}
    class Runner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            seen["args"], seen["prompt"] = args, input_text
            return ProcessResult(1, "", "stop here")
    adapter = adapter_class(Runner(), allow_live=True, confinement_mode="cli-confinement")
    adapter.full_access = full_access
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    adapter.execute(AgentRequest(task_id="t", role=role, description="d", requirements=[], acceptance_criteria=[], workdir=str(tmp_path), allowed_paths=["src"]))
    return seen["args"], json.loads(seen["prompt"])["supervisor_policy"]


def test_full_access_widens_only_coding_runs(tmp_path):
    args, policy = captured(CodexAdapter, tmp_path, "implement", True)
    assert args[args.index("--sandbox") + 1] == "danger-full-access" and "full access" in policy
    args, _ = captured(CodexAdapter, tmp_path, "review", True)
    assert args[args.index("--sandbox") + 1] == "read-only"
    args, _ = captured(CodexAdapter, tmp_path, "implement", False)
    assert args[args.index("--sandbox") + 1] == "workspace-write"
    args, policy = captured(ClaudeAdapter, tmp_path, "implement", True)
    assert "Bash" in args[args.index("--tools") + 1] and "--safe-mode" in args and "full access" in policy
    args, policy = captured(ClaudeAdapter, tmp_path, "plan", True)
    assert args[args.index("--tools") + 1] == "Read,Grep,Glob" and "Never deploy" in policy
