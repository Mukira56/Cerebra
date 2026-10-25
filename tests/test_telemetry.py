from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.models import Project, Task, Run, Event

KEY = "telemetry-test-key-with-over-32-characters"


def fixture(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), bootstrap_key=KEY, start_worker=False)
    with app.state.db.Session.begin() as session:
        session.add(Project(id="p", name="Fixture", path=str(tmp_path / "repo"), default_branch="main"))
        session.flush()
        session.add_all([
            Task(id="live", project_id="p", description="Live fixture", mode="live", state="RUNNING", test_results=[{"passed":True}]),
            Task(id="mock", project_id="p", description="Mock fixture", mode="mock")])
        session.flush()
        session.add_all([
            Run(id="lc",task_id="live",agent="codex",role="implement",status="succeeded",simulated=False,
                started_at="2026-10-24T10:00:00+00:00",finished_at="2026-10-24T10:00:10+00:00",output="password=do-not-expose-this"),
            Run(id="lf",task_id="live",agent="claude",role="review",status="failed",simulated=False,
                started_at="2026-10-24T10:00:10+00:00",finished_at="2026-10-24T10:00:30+00:00"),
            Run(id="mc",task_id="mock",agent="codex",role="implement",status="succeeded",simulated=True,
                started_at="2026-10-24T10:00:00+00:00",finished_at="2026-10-24T10:00:01+00:00"),
            Run(id="active",task_id="live",agent="codex",role="implement",status="running",simulated=False,
                started_at=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat()),
            Event(task_id="live",kind="run",message="api_key=secretfixturevalue")])
    return app


def test_telemetry_auth_measurements_sources_and_read_only(tmp_path):
    app = fixture(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/telemetry").status_code == 401
        client.post("/api/session",json={"key":KEY}).raise_for_status()
        response=client.get("/api/telemetry");response.raise_for_status();data=response.json()
        assert data["metrics"]["live"]["codex"]["mean_duration_seconds"] == 10
        assert data["metrics"]["mock"]["codex"]["mean_duration_seconds"] == 1
        assert data["metrics"]["live"]["claude"]["success_percent"] == 0
        assert data["metrics"]["live"]["codex"]["active"] == 1
        active=next(run for run in data["runs"] if run["id"]=="active")
        assert 5 <= active["elapsed_seconds"] < 60 and active["duration_seconds"] is None
        assert "do-not-expose-this" not in response.text and "secretfixturevalue" not in response.text
        assert "[REDACTED]" in response.text
        assert "tokens_per_second" not in data and "cost" not in data
        assert next(task for task in data["tasks"] if task["id"]=="live")["tests_passed"] == 1
        filtered=client.get("/api/telemetry?task_id=mock").json()
        assert len(filtered["runs"])==1 and filtered["runs"][0]["source"]=="mock"
        assert client.get("/api/telemetry?task_id=missing").status_code==404
        assert client.get("/api/telemetry?task_id="+"x"*65).status_code==422
        assert client.post("/api/telemetry",json={}).status_code==403
        assert len(client.get("/api/telemetry").json()["runs"])==4


def test_telemetry_bounded_history_and_simulation_cannot_be_live(tmp_path):
    app=fixture(tmp_path)
    with app.state.db.Session.begin() as session:
        session.add_all([Run(id=f"r{i}",task_id="live",agent="codex",role="implement",status="succeeded",simulated=True,
            # Newer than every fixture run (including the one started "now"), so they fill the 500-run window.
            started_at=(datetime.now(timezone.utc)+timedelta(minutes=1,seconds=i)).isoformat(),
            finished_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()) for i in range(505)])
    with TestClient(app) as client:
        client.post("/api/session",json={"key":KEY}).raise_for_status()
        data=client.get("/api/telemetry").json()
        assert len(data["runs"])==500
        # A simulated adapter can never count as genuine provider performance, even on a live task.
        assert all(run["source"]=="mock" for run in data["runs"])
        assert data["metrics"]["live"]["codex"]["runs"]==0
