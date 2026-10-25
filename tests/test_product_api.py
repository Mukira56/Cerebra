"""Dashboard features: real-agent workflow, models, permissions, chat, reports, toolchain, GitHub, cleanup.

Agents, sign-in windows and installs are all faked; no provider CLI, browser or installer is launched.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.models import Project, Task
from fakes import FixtureRegistry

KEY = "local-test-key-with-over-32-characters"


def calculator(path):
    path.mkdir(parents=True)
    (path / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (path / "test_calculator.py").write_text("from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    (path / ".ai-hq-demo.json").write_text(json.dumps({"kind": "calculator-addition-v1"}), encoding="utf-8")
    (path / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    for args in (["init", "-b", "main"], ["add", "."], ["-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "base"]):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    return path


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = FixtureRegistry()
    opened = []
    app.state.integrations.terminal = lambda args, title, cwd=None, keep_open=True: opened.append((list(map(str, args)), title))
    app.state.opened = opened
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def enable_agents(client):
    response = client.post("/api/permissions", json={"enabled": True, "acknowledge_provider_usage": True, "acknowledge_residual_read_risk": True})
    assert response.status_code == 200, response.text
    return response.json()


def test_agent_permissions_need_both_acknowledgements_and_switch_off(client):
    assert client.post("/api/permissions", json={"enabled": True, "acknowledge_provider_usage": True}).status_code == 400
    settings = enable_agents(client)
    assert settings["live_enabled"] and settings["cli_confinement_accepted"]
    assert client.app.state.supervisor.registry.allow_live
    off = client.post("/api/permissions", json={"enabled": False}).json()
    assert not off["live_enabled"] and not off["cli_confinement_accepted"]


def test_real_workflow_with_chosen_models_and_plain_report(client, tmp_path):
    enable_agents(client)
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True,
                                                  "test_commands": [[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]}).json()
    assert project["mode"] == "live"
    profile = client.post("/api/models", json={"provider": "codex", "model": "gpt-test", "label": "Codex test model"}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition", "implementer": profile["id"], "allowed_paths": ["calculator.py"]}).json()
    assert task["results"]["models"]["implementer"]["model"] == "gpt-test"
    identifier = task["id"]
    assert client.post(f"/api/tasks/{identifier}/approve-plan", json={}).status_code == 200
    started = client.post(f"/api/tasks/{identifier}/start", json={}).json()
    consent = next(row for row in client.get(f"/api/tasks/{identifier}").json()["approvals"] if row["kind"] == "live_execution")
    assert started["state"] == "AWAITING_APPROVAL"
    client.post(f"/api/approvals/{consent['id']}", json={"approve": True})
    client.post(f"/api/tasks/{identifier}/start", json={})
    client.app.state.supervisor.run_until_idle()
    detail = client.get(f"/api/tasks/{identifier}").json()
    assert detail["state"] == "AWAITING_APPROVAL", detail["results"].get("error")
    assert not any(run["simulated"] for run in detail["runs"])
    assert ("codex", "gpt-test") in {(name, getattr(request, "model", None)) for name, request in client.app.state.supervisor.registry.requests}
    report = client.get(f"/api/reports/{identifier}").json()
    assert report["headline"] == "Finished and waiting for you"
    assert any("tests ran" in step["title"] for step in report["steps"])
    assert any(item["where"].endswith("hq.sqlite3") for item in report["saved"])
    proof = report["evidence"]  # the broken add() was recorded before the change, and passes after it
    assert proof["verdict"] == "fixed" and proof["before"]["failing"] == ["test_calculator.py::test_add"] and proof["after"]["passed"]
    assert proof["fixed"] == ["test_calculator.py::test_add"] and detail["results"]["baseline"]["commit"] == detail["base_commit"]
    assert len(detail["test_results"]) == 1  # the baseline is evidence, not a verification attempt
    merge = next(row for row in detail["approvals"] if row["kind"] == "merge" and row["status"] == "pending")
    client.post(f"/api/approvals/{merge['id']}", json={"approve": True})
    assert "return a + b" in (repo / "calculator.py").read_text()
    assert client.get(f"/api/reports/{identifier}").json()["emoji"] == "✅"


def test_model_profiles_crud_and_roles(client):
    assert client.post("/api/models", json={"provider": "claude", "model": "bad model;rm", "label": ""}).status_code == 400
    added = client.post("/api/models", json={"provider": "claude", "model": "opus", "label": "Opus"}).json()
    assert client.post("/api/models", json={"provider": "claude", "model": "opus", "label": "Again"}).status_code == 400
    assert client.patch("/api/models/claude", json={"model": "sonnet"}).json()["model"] == "sonnet"
    assert client.put("/api/models/roles", json={"reviewer": added["id"]}).json()["reviewer"] == added["id"]
    copilot = client.post("/api/models", json={"provider": "copilot", "model": "", "label": "Copilot"}).json()
    assert client.put("/api/models/roles", json={"implementer": copilot["id"]}).status_code == 400
    assert client.delete("/api/models/claude").status_code == 400
    assert client.delete(f"/api/models/{added['id']}").status_code == 200
    assert client.get("/api/models").json()["roles"]["reviewer"] == "auto"


def test_chat_round_trip_is_read_only_and_recorded(client):
    conversation = client.post("/api/chats", json={"profile": "codex"}).json()
    sent = client.post(f"/api/chats/{conversation['id']}/messages", json={"text": "What does this project do?"})
    assert sent.status_code == 202
    for _ in range(100):
        state = client.get(f"/api/chats/{conversation['id']}").json()
        if not state["busy"]:
            break
        time.sleep(0.05)
    assert [message["role"] for message in state["messages"]] == ["user", "assistant"]
    assert state["messages"][1]["content"] == "Fixture answer from codex"
    assert state["conversation"]["title"].startswith("What does")
    assert client.get("/api/chats/absent").status_code == 404
    assert client.delete(f"/api/chats/{conversation['id']}").status_code == 200
    assert client.post("/api/chats", json={"profile": "missing"}).status_code == 400


def test_sign_in_and_installs_open_only_fixed_visible_commands(client, monkeypatch):
    import ai_hq.integrations as integrations
    monkeypatch.setattr(integrations, "which", lambda names: "C:/tools/" + names[0] + ".exe")
    monkeypatch.setattr(client.app.state.integrations, "executables", lambda name: None)
    assert client.post("/api/providers/claude/sign-in").json()["opened"]
    assert client.post("/api/tools/gh/install").json()["opened"]
    assert client.post("/api/tools/not-a-tool/install").status_code == 400
    assert client.post("/api/providers/unknown/sign-in").status_code == 400
    opened = client.app.state.opened
    assert opened[0][0][1:] == ["auth", "login"] and opened[1][0][1:] == ["install", "--id", "GitHub.cli", "-e"]


def test_github_clone_validates_repository_names(client):
    assert client.post("/api/github/clone", json={"repository": "../../etc", "authorize": True}).status_code == 400


def test_demo_cleanup_backs_up_and_keeps_real_work(client, tmp_path):
    db = client.app.state.db
    data = client.app.state.settings.data_dir
    demo = calculator(data / "projects" / "demo-12345678")
    real = calculator(tmp_path / "real")
    with db.Session.begin() as session:
        session.add(Project(id="demo", name="Calculator demo", path=str(demo), default_branch="main", mode="mock"))
        session.add(Project(id="real", name="Real", path=str(real), default_branch="main", mode="mock"))
    with db.Session.begin() as session:
        session.add(Task(id="t1", project_id="demo", description="demo", mode="mock"))
        session.add(Task(id="t2", project_id="real", description="mock on real", mode="mock"))
        session.add(Task(id="t3", project_id="real", description="real work", mode="live"))
    assert client.get("/api/maintenance/demo-data").json() == {"tasks": 2, "projects": ["Calculator demo"]}
    assert client.post("/api/maintenance/demo-data", json={}).status_code == 422
    result = client.post("/api/maintenance/demo-data", json={"confirm": True}).json()
    assert result["tasks_removed"] == 2 and result["projects_removed"] == ["Calculator demo"]
    assert Path(result["backup"]).is_file() and not demo.exists() and real.exists()
    with db.Session() as session:
        assert [task.id for task in session.query(Task).all()] == ["t3"]
        assert session.get(Project, "real").mode == "live"


def test_system_view_reports_local_storage(client):
    system = client.get("/api/system").json()
    assert system["database"]["path"].endswith("hq.sqlite3") and system["agents_enabled"] is False
