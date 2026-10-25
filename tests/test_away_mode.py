"""Away mode (delegated approvals) and signing out. Agents and provider CLIs are faked."""
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ai_hq import autopilot
from ai_hq.api import create_app
from ai_hq.config import Settings
from fakes import FixtureRegistry
from test_product_api import KEY, calculator, enable_agents

AWAY = {"enabled": True, "hours": 4, "acknowledge_auto_approval": True}


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = FixtureRegistry()
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def task_for(client, tmp_path, name="calc"):
    repo = calculator(tmp_path / name)
    project = client.post("/api/projects", json={"name": name, "path": str(repo), "authorize": True,
                                                  "test_commands": [[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition", "allowed_paths": ["calculator.py"]}).json()
    return project, task["id"]


def kinds(client, identifier, status):
    return [row["kind"] for row in client.get(f"/api/tasks/{identifier}").json()["approvals"] if row["status"].lower() == status]


def test_away_mode_needs_agents_on_and_acknowledgement(client):
    assert client.put("/api/autopilot", json=AWAY).status_code == 400  # agents still off
    enable_agents(client)
    assert client.put("/api/autopilot", json={**AWAY, "acknowledge_auto_approval": False}).status_code == 400
    assert client.put("/api/autopilot", json={**AWAY, "auto_merge": True}).status_code == 400
    assert client.put("/api/autopilot", json={**AWAY, "hours": 100}).status_code == 422
    policy = client.put("/api/autopilot", json=AWAY).json()
    assert policy["active"] and not policy["auto_merge"]
    assert client.get("/api/overview").json()["autopilot"]["active"]
    client.post("/api/permissions", json={"enabled": False})
    assert not client.get("/api/autopilot").json()["active"]  # switching agents off ends Away mode


def test_away_mode_runs_task_but_stops_before_merge_without_opt_in(client, tmp_path):
    enable_agents(client)
    _, identifier = task_for(client, tmp_path)
    client.put("/api/autopilot", json=AWAY)
    client.app.state.supervisor.run_until_idle()
    detail = client.get(f"/api/tasks/{identifier}").json()
    assert detail["state"] == "AWAITING_APPROVAL" and detail["runs"]
    assert kinds(client, identifier, "pending") == ["merge"]
    assert {"plan", "live_execution"} <= set(kinds(client, identifier, "approved"))
    assert any(event["kind"] == "autopilot" for event in detail["events"])


def test_away_mode_merges_only_with_opt_in_and_passing_tests(client, tmp_path):
    enable_agents(client)
    project, identifier = task_for(client, tmp_path)
    client.put("/api/autopilot", json={**AWAY, "auto_merge": True, "acknowledge_auto_merge": True, "projects": [project["id"]]})
    client.app.state.supervisor.run_until_idle()
    detail = client.get(f"/api/tasks/{identifier}").json()
    assert detail["state"] == "COMPLETED" and all(result["passed"] for result in detail["test_results"][-1:])
    assert "return a + b" in (tmp_path / "calc" / "calculator.py").read_text(encoding="utf-8")


def test_away_mode_respects_project_scope_and_expiry(client, tmp_path):
    enable_agents(client)
    other, _ = task_for(client, tmp_path, "other")
    _, identifier = task_for(client, tmp_path, "calc")
    client.put("/api/autopilot", json={**AWAY, "projects": [other["id"]]})
    client.app.state.supervisor.auto_approve()
    assert kinds(client, identifier, "pending") == ["plan"]
    with client.app.state.db.Session.begin() as session:
        autopilot.save(session, True, 1)
        row = session.get(autopilot.Metadata, autopilot.KEY)
        row.value = {**row.value, "projects": [], "until": "2000-01-01T00:00:00+00:00"}
    assert client.app.state.supervisor.auto_approve() == 0
    assert kinds(client, identifier, "pending") == ["plan"]


def test_sign_out_runs_the_tools_own_logout(client):
    calls = []
    def run(args, cwd, timeout=None):
        calls.append([str(arg) for arg in args])
        signed_out = any("logout" in call for call in calls)
        return SimpleNamespace(exit_code=0, stdout='{"loggedIn": %s}' % ("false" if signed_out else "true"), stderr="")
    integrations = client.app.state.integrations
    integrations.runner = SimpleNamespace(run=run)
    integrations.executables = lambda name: f"C:/tools/{name}.exe"
    assert client.post("/api/providers/claude/check").json()["signed_in"] is True
    status = client.post("/api/providers/claude/sign-out").json()
    assert status["signed_in"] is False and ["C:/tools/claude.exe", "auth", "logout"] in calls
    providers = {row["id"]: row for row in client.get("/api/providers").json()}
    assert providers["claude"]["sign_in"]["signed_in"] is False and providers["claude"]["can_sign_out"]
    assert not providers["copilot"]["can_sign_out"]
    assert client.post("/api/providers/copilot/sign-out").status_code == 400
