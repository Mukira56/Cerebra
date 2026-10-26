"""Deleting failed tasks: confirmed, backed up, working copies removed, branches and history kept, active work refused."""
import subprocess
from pathlib import Path

from ai_hq.models import Event
from test_autofix import setup
from test_product_api import client  # noqa: F401  (fixture)


def test_a_failed_task_is_deleted_with_a_backup_and_its_branch_kept(client, tmp_path):
    task_id = setup(client, tmp_path)
    task = client.get(f"/api/tasks/{task_id}").json()
    worktree, branch = Path(task["worktree_path"]), task["branch"]
    assert worktree.is_dir()
    assert client.post("/api/tasks/delete", json={"task_ids": [task_id]}).status_code == 422  # must be confirmed
    result = client.post("/api/tasks/delete", json={"task_ids": [task_id], "confirm": True}).json()
    assert result["deleted"] == [task_id] and Path(result["backup"]).is_file()
    assert client.get(f"/api/tasks/{task_id}").status_code == 404 and not worktree.exists()
    repo = tmp_path / "calc"
    assert subprocess.run(["git", "-C", str(repo), "branch", "--list", branch], capture_output=True, text=True).stdout.strip()  # work recoverable
    with client.app.state.db.Session() as session:
        assert session.query(Event).filter(Event.message.like(f"Owner deleted task {task_id[:8]}%")).count() == 1
    assert client.get("/api/auto-fix/tasks").json() == []


def test_active_tasks_and_tasks_others_depend_on_are_refused(client, tmp_path):
    task_id = setup(client, tmp_path)
    project_id = client.get(f"/api/tasks/{task_id}").json()["project_id"]
    waiting = client.post("/api/tasks", json={"project_id": project_id, "description": "Add subtraction", "allowed_paths": ["calculator.py"]}).json()
    response = client.post("/api/tasks/delete", json={"task_ids": [waiting["id"]], "confirm": True})
    assert response.status_code == 400 and "only failed, cancelled or paused" in response.json()["detail"]
    dependent = client.post("/api/tasks", json={"project_id": project_id, "description": "Build on the fix", "allowed_paths": ["calculator.py"], "dependencies": [task_id]}).json()
    response = client.post("/api/tasks/delete", json={"task_ids": [task_id], "confirm": True})
    assert response.status_code == 400 and "depends on" in response.json()["detail"]
    client.post(f"/api/tasks/{dependent['id']}/cancel")
    assert client.post("/api/tasks/delete", json={"task_ids": [task_id, dependent["id"]], "confirm": True}).status_code == 200  # together is fine
