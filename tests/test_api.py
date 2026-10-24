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
        assert c.post("/api/permissions",json={"enabled":True}).status_code==403
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

def test_settings_persist(client):
    assert client.patch("/api/settings",json={"max_retries":2,"test_timeout":30}).status_code==200
    other=create_app(Settings(data_dir=client.app.state.settings.data_dir),bootstrap_key="a"*32,start_worker=False)
    assert other.state.settings.max_retries==2
    other.state.db.close()
