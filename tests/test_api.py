import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.models import Approval, Task

KEY="local-test-key-with-over-32-characters"

@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/"data"),bootstrap_key=KEY,start_worker=False)
    with TestClient(app) as client:
        response=client.post("/api/session",json={"key":KEY})
        assert response.status_code==200
        client.headers["X-CSRF-Token"]=response.json()["csrf_token"]
        yield client

def test_health_and_auth_boundaries(tmp_path):
    app=create_app(Settings(data_dir=tmp_path),bootstrap_key=KEY,start_worker=False)
    with TestClient(app) as c:
        assert c.get("/health").json()["status"]=="ok"
        assert c.get("/api/overview").status_code==401
        assert c.get("/health",headers={"Host":"evil.example"}).status_code==403
        assert c.post("/api/session",json={"key":KEY},headers={"Origin":"https://evil.example"}).status_code==403
        assert c.post("/api/session",json={"key":"x"*30}).status_code==401
        assert c.post("/api/session",json={"key":KEY}).status_code==200
        assert c.post("/api/session",json={"key":KEY}).status_code==401
        assert c.post("/api/demo",json={}).status_code==403
        assert c.get("/api/overview",headers={"Sec-Fetch-Site":"cross-site"}).status_code==403

def test_api_validation(client):
    assert client.post("/api/projects",json={"name":"oops"}).status_code==422
    assert client.post("/api/projects",json={"name":"oops","path":"..","authorize":True}).status_code==400
    assert client.post("/api/tasks",json={"project_id":"absent","description":"do something","allowed_paths":["../escape"]}).status_code==422
    assert client.patch("/api/settings",json={"max_concurrency":2}).status_code==422
    assert client.patch("/api/settings",json={"live_enabled":True}).status_code==422
    assert client.patch("/api/settings",json={"cli_confinement_accepted":True}).status_code==422
    assert client.patch("/api/settings",json={"ollama_url":"https://example.com"}).status_code==422
    assert client.get("/api/tasks/missing").status_code==404
    assert client.post("/api/projects",json={"name":"Absent","path":"C:/this-ai-hq-repo-does-not-exist","authorize":True}).status_code==400

def test_demo_end_to_end_api(client):
    response=client.post("/api/demo",json={})
    assert response.status_code==201, response.text
    demo=response.json();task=demo["task"];identifier=task["id"]
    assert task["state"]=="AWAITING_APPROVAL"
    assert client.post(f"/api/tasks/{identifier}/start",json={}).status_code==400
    assert client.post(f"/api/tasks/{identifier}/approve-plan",json={}).status_code==200
    assert client.post(f"/api/tasks/{identifier}/start",json={}).status_code==200
    client.app.state.supervisor.run_until_idle()
    detail=client.get(f"/api/tasks/{identifier}").json()
    assert detail["state"]=="AWAITING_APPROVAL",detail
    assert detail["results"]["verified"] is True
    assert detail["runs"] and all(run["simulated"] or run["role"]=="verification" for run in detail["runs"])
    assert detail["reviews"]
    approval=next(row for row in detail["approvals"] if row["kind"]=="merge")
    # Candidate cannot reach registered working directory without a separate approval.
    assert "return a - b" in (Path(demo["project"]["path"])/"calculator.py").read_text()
    assert client.post(f"/api/approvals/{approval['id']}",json={"approve":True}).status_code==200
    assert client.get(f"/api/tasks/{identifier}").json()["state"]=="COMPLETED"
    assert "return a + b" in (Path(demo["project"]["path"])/"calculator.py").read_text()

def test_settings_persist(client):
    assert client.patch("/api/settings",json={"max_retries":2,"test_timeout":30}).status_code==200
    other=create_app(Settings(data_dir=client.app.state.settings.data_dir),bootstrap_key="a"*32,start_worker=False)
    assert other.state.settings.max_retries==2
    other.state.db.close()

def test_user_command_authorization_and_reversed_roles(client):
    response=client.post("/api/demo",json={})
    demo=response.json()
    response=client.post("/api/tasks",json={"project_id":demo["project"]["id"],"description":"Fix calculator.add for positive and negative numbers","assigned_agent":"claude","allowed_paths":["calculator.py"],"mode":"mock"})
    assert response.status_code==201,response.text
    task=response.json()
    assert task["reviewer"]=="codex"
    client.post(f"/api/tasks/{task['id']}/approve-plan",json={})
    client.post(f"/api/tasks/{task['id']}/start",json={})
    client.app.state.supervisor.run_until_idle()
    task=client.get(f"/api/tasks/{task['id']}").json()
    assert task["state"]=="AWAITING_APPROVAL",task
    assert any(row["agent"]=="claude" and row["simulated"] for row in task["runs"])
