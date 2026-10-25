"""Checkpoint history, restore, undo merge, built-in previews and the readiness check. Fixture agents only."""
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_hq.agents import AgentResult
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.models import BusinessJob, Project, Task
from fakes import FixtureRegistry
from test_product_api import KEY, enable_agents
from test_supervisor import consent, git, hq, pending_approval, proposed, ready  # noqa: F401  (hq is a fixture)


def test_checkpoints_restore_and_retest(hq):
    supervisor, project_id, repo, db, _ = hq
    task_id = supervisor.propose(project_id, "Fix the calculator addition demonstration [demo:needs-repair]", allowed_paths=["calculator.py"]).id
    supervisor.approve_plan(task_id); consent(hq, task_id)
    supervisor.run_until_idle()
    history = supervisor.checkpoints(task_id)
    assert len(history["checkpoints"]) == 2 and history["current"] == history["candidate"] == history["checkpoints"][-1]["commit"]
    assert history["checkpoints"][0]["files"] == ["calculator.py"]
    first = history["checkpoints"][0]["commit"]
    with pytest.raises(ValueError):
        supervisor.restore_checkpoint(task_id, "0" * 40)
    restored = supervisor.restore_checkpoint(task_id, first)
    assert restored.state == "BLOCKED" and restored.results["resume_stage"] == "review"
    assert "a + b + 1" in (Path(restored.worktree_path) / "calculator.py").read_text(encoding="utf-8")
    with db.Session() as session:
        from ai_hq.models import Approval
        assert all(row.status != "pending" for row in session.query(Approval).filter(Approval.task_id == task_id, Approval.kind == "merge"))
    supervisor.resume(task_id); supervisor.start(task_id); supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL" and pending_approval(db, task_id, "merge")  # re-tested, repaired, reviewed


def test_undo_merge_reverts_with_one_commit(hq):
    supervisor, _, repo, db, _ = hq
    task_id = ready(hq)
    supervisor.run_until_idle()
    supervisor.resolve_approval(pending_approval(db, task_id, "merge").id, True)
    assert supervisor.get(task_id).state == "COMPLETED" and "a + b" in (repo / "calculator.py").read_text(encoding="utf-8")
    (repo / "notes.txt").write_text("uncommitted user work", encoding="utf-8")
    with pytest.raises(Exception, match="not committed"):
        supervisor.undo_integration(task_id)
    (repo / "notes.txt").unlink()
    undone = supervisor.undo_integration(task_id)
    assert "a - b" in (repo / "calculator.py").read_text(encoding="utf-8")
    assert git(repo, "log", "-1", "--format=%s").startswith("Undo Cerebra task") and undone.results["undone"]["commit"]
    with pytest.raises(ValueError, match="already undone"):
        supervisor.undo_integration(task_id)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", test_timeout=60), bootstrap_key=KEY, start_worker=False)
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def test_preview_is_confined_and_sandboxed(client, tmp_path):
    folder = tmp_path / "job"; (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<html><head><link rel=stylesheet href=styles.css><script>alert(1)</script></head><body>Hi</body></html>", encoding="utf-8")
    (folder / "styles.css").write_text("body{color:red}", encoding="utf-8")
    (folder / "cerebra-brief.json").write_text("{}", encoding="utf-8")
    (folder / "tool.py").write_text("print(1)", encoding="utf-8")
    with client.app.state.db.Session.begin() as session:
        session.add(Project(id="p", name="Job", path=str(folder), default_branch="main")); session.flush()
        session.add(Task(id="t", project_id="p", description="Site", state="COMPLETED")); session.flush()
        session.add(BusinessJob(id="job", title="Site", kind="website", brief="A site for a bakery in Nairobi.", output_dir=str(folder), project_id="p", task_id="t"))
    page = client.get("/api/business/jobs/job/preview/index.html")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    policy = page.headers["content-security-policy"]
    assert policy.startswith("sandbox allow-same-origin;") and "script-src" not in policy and "default-src 'none'" in policy
    assert page.headers["x-frame-options"] == "SAMEORIGIN"
    assert client.get("/api/business/jobs/job/preview/styles.css").status_code == 200
    for bad in ("cerebra-brief.json", "tool.py", "../job/index.html", "missing.html", ".git/config"):
        assert client.get(f"/api/business/jobs/job/preview/{bad}").status_code == 404, bad
    previews = client.get("/api/business/jobs/job").json()["previews"]
    assert {item["path"] for item in previews} == {"index.html", "styles.css"}
    assert client.get("/api/overview").headers["x-frame-options"] == "DENY"  # the rest of the app is unchanged


class ReadinessAgent(FixtureRegistry):
    """Plans, fixes calculator.py and reviews, like a real provider would; no CLI is launched."""
    def execute(self, name, request, cancel_event=None):
        self.requests.append((name, request))
        if request.role == "implement":
            (Path(request.workdir) / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            return AgentResult(True, "Fixed add")
        if request.role == "review":
            return AgentResult(True, "Reviewed", [])
        return AgentResult(True, "Plan: correct the operator in add")


def test_readiness_check_runs_every_stage_and_never_merges(client):
    assert client.post("/api/readiness").status_code == 400  # agents off
    enable_agents(client)
    supervisor = client.app.state.supervisor
    supervisor.registry = ReadinessAgent(); supervisor._refresh_registry = lambda: None
    started = client.post("/api/readiness").json()
    assert started["status"] == "running"
    assert client.post("/api/readiness").status_code == 400  # one at a time
    supervisor.run_until_idle()
    result = client.get("/api/readiness").json()
    assert result["status"] == "passed", result
    assert [(stage["key"], stage["state"]) for stage in result["stages"]] == [("plan", "passed"), ("code", "passed"), ("tests", "passed"), ("review", "passed")]
    task = client.get(f"/api/tasks/{result['task_id']}").json()
    assert task["state"] == "BLOCKED" and task["results"]["origin"] == "readiness"
    project = client.get("/api/overview").json()["projects"][0]
    assert "a - b" in (Path(project["path"]) / "calculator.py").read_text(encoding="utf-8")  # nothing merged
    again = client.post("/api/readiness").json()  # the same test project is reused
    assert again["status"] == "running" and len(client.get("/api/overview").json()["projects"]) == 1
