"""Security hardening checks: support-made tasks never get Full access, protective headers, approvals in telemetry."""
import pytest
from fastapi.testclient import TestClient

from ai_hq.api import create_app
from ai_hq.config import Settings
from fakes import FixtureRegistry
from test_product_api import KEY, calculator, enable_agents


class AccessRecorder(FixtureRegistry):
    """Notes whether Full access was on for each coding run."""
    def __init__(self):
        super().__init__()
        self.access = []

    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            self.access.append(self.full_access)
        return super().execute(name, request, cancel_event)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = AccessRecorder()
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def run_task(client, tmp_path, origin):
    supervisor = client.app.state.supervisor
    repo = calculator(tmp_path / origin)
    project = client.post("/api/projects", json={"name": origin, "path": str(repo), "authorize": True,
                                                  "test_commands": [["python", "-c", "pass"]]}).json()
    task = supervisor.propose(project["id"], "Fix calculator addition", allowed_paths=["calculator.py"], origin=origin)
    supervisor.approve_plan(task.id)
    supervisor.start(task.id)
    consent = next(row for row in client.get(f"/api/tasks/{task.id}").json()["approvals"] if row["kind"] == "live_execution")
    client.post(f"/api/approvals/{consent['id']}", json={"approve": True})
    supervisor.run_until_idle()
    return supervisor.get(task.id)


def test_tasks_requested_by_support_chat_never_get_full_access(client, tmp_path):
    enable_agents(client)
    client.post("/api/permissions/full-access", json={"enabled": True, "acknowledge_full_access": True, "acknowledge_github": True})
    assert run_task(client, tmp_path, "user").results["origin"] == "user"
    assert run_task(client, tmp_path, "support").results["origin"] == "support"
    assert client.app.state.supervisor.registry.access == [True, False]


def test_protective_headers_and_rejected_requests(client):
    response = client.get("/api/overview")
    for header, value in {"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin", "X-Frame-Options": "DENY"}.items():
        assert response.headers[header] == value
    assert "camera=()" in response.headers["Permissions-Policy"] and "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert client.post("/api/settings", headers={"X-CSRF-Token": "wrong"}).status_code in {403, 405}
    assert client.patch("/api/settings", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.get("/api/overview", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/api/overview", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/session", json={"key": KEY}).status_code == 401  # the launch key works once


def test_waiting_approvals_reach_the_system_view(client, tmp_path):
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition"}).json()
    assert {"task_id": task["id"], "kind": "plan"} in client.get("/api/telemetry").json()["approvals"]
