"""Business Studio: brief to reviewed export, real deliverable checks, refusals, duplicates, cancellation, paths.

A test-only fixture agent writes the deliverables; the supervisor, checker, review flow and export are real.
"""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_hq import business_check
from ai_hq.agents import AgentResult
from ai_hq.api import create_app
from ai_hq.config import Settings
from fakes import FixtureRegistry
from test_product_api import KEY, enable_agents

GOOD = "## Title\nHand-drawn mountain sunrise print\n\n## Description\nAn original sunrise over the Aberdares, for Jane's studio.\n\n## Tags\nsunrise, mountain, print\n"
BAD = "## Title\n" + "x" * 200 + "\n"


class DeliverableAgent(FixtureRegistry):
    """Writes listing.md in the working copy (only when coding); plans and reviews without findings."""
    def __init__(self, content=GOOD):
        super().__init__()
        self.content = content

    def execute(self, name, request, cancel_event=None):
        self.requests.append((name, request))
        if request.role == "implement":
            (Path(request.workdir) / "listing.md").write_text(self.content, encoding="utf-8")
            return AgentResult(True, "Fixture: wrote listing.md")
        if request.role == "review":
            return AgentResult(True, "Fixture: reviewed", [])
        return AgentResult(True, "Fixture: plan")


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", test_timeout=60), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = DeliverableAgent()
    app.state.supervisor._refresh_registry = lambda: None
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        assert client.put("/api/business/settings", json={"output_root": str(tmp_path / "Cerebra Business")}).status_code == 200
        yield client


JOB = {"title": "Sunrise print listing", "kind": "listing", "client": "Jane", "brief": "Write listing copy for my original sunrise mountain print for Etsy."}


def drive(client, job_id):
    """Approve every gate the way the user would, and run the supervisor until the job settles."""
    supervisor = client.app.state.supervisor
    for _ in range(12):
        job = client.get(f"/api/business/jobs/{job_id}").json()
        if job["stage"] in {"ready", "failed", "completed"}:
            return job
        task = client.get(f"/api/tasks/{job['task_id']}").json()
        for approval in task["approvals"]:
            if approval["status"].lower() == "pending":
                client.post(f"/api/approvals/{approval['id']}", json={"approve": True})
                if approval["kind"] in {"plan", "live_execution"}:
                    client.post(f"/api/tasks/{job['task_id']}/start", json={})
        supervisor.run_until_idle()
    return client.get(f"/api/business/jobs/{job_id}").json()


def test_brief_to_reviewed_export(client, tmp_path):
    enable_agents(client)
    created = client.post("/api/business/jobs", json=JOB)
    assert created.status_code == 201, created.text
    job = created.json()
    folder = Path(job["output_dir"])
    assert folder.parent == tmp_path / "Cerebra Business" and (folder / "cerebra-brief.json").is_file()
    assert job["stage"] == "waiting" and "plan" in " ".join(job["attention"]).lower()
    assert client.post(f"/api/business/jobs/{job['id']}/export", json={}).status_code == 400  # not reviewed yet
    finished = drive(client, job["id"])
    assert finished["stage"] == "ready" and finished["reviewed"] and any("passed the deliverable checks" in line for line in finished["passed"])
    assert (folder / "listing.md").read_text(encoding="utf-8") == GOOD  # merged into the job folder only after approval
    exported = client.post(f"/api/business/jobs/{job['id']}/export", json={"zip": True}).json()
    assert exported["stage"] == "completed"
    package = Path(exported["export"]["folder"])
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert "listing.md" in [item["path"] for item in manifest["files"]] and manifest["checks"][0]["passed"] is True
    assert {"README.md", "review-findings.md", "listing.md"} <= {path.name for path in package.iterdir()}
    with zipfile.ZipFile(exported["export"]["zip"]) as bundle:
        assert "listing.md" in bundle.namelist() and "manifest.json" in bundle.namelist()
    again = client.post(f"/api/business/jobs/{job['id']}/export", json={"zip": True}).json()
    assert again["export"]["folder"] != str(package) and again["export"]["zip"] != exported["export"]["zip"]  # nothing overwritten
    assert package.joinpath("manifest.json").is_file()
    report = client.get(f"/api/business/jobs/{job['id']}").json()
    assert "does not mean anything was sold" in report["note"] and report["files"][0]["exists"]


def test_failed_checks_stop_the_job_honestly(client):
    enable_agents(client)
    client.app.state.supervisor.registry.content = BAD
    client.patch("/api/settings", json={"max_retries": 0})
    job = client.post("/api/business/jobs", json=JOB).json()
    finished = drive(client, job["id"])
    assert finished["stage"] == "failed"
    assert any("checks failed" in line for line in finished["attention"])
    assert not any("passed the deliverable checks" in line for line in finished["passed"])
    assert client.post(f"/api/business/jobs/{job['id']}/export", json={}).status_code == 400


def test_refusals_duplicates_and_cancel(client, tmp_path):
    assert "no AI" in client.post("/api/business/jobs", json={**JOB, "no_ai_requested": True}).json()["detail"]
    assert client.post("/api/business/jobs", json={**JOB, "kind": "video"}).status_code == 422
    assert client.post("/api/business/jobs", json={**JOB, "sources": [str(tmp_path / "missing.png")]}).status_code == 400
    first = client.post("/api/business/jobs", json=JOB).json()
    assert "already exists" in client.post("/api/business/jobs", json=JOB).json()["detail"]
    cancelled = client.post(f"/api/business/jobs/{first['id']}/cancel").json()
    assert cancelled["stage"] == "cancelled" and client.get(f"/api/tasks/{first['task_id']}").json()["state"] == "CANCELLED"
    assert client.put("/api/business/settings", json={"output_root": "relative/folder"}).status_code == 400
    assert client.put("/api/business/settings", json={"output_root": str(Path.home())}).status_code == 400


def test_sources_are_copied_and_brief_is_protected(client, tmp_path):
    source = tmp_path / "logo-sketch.svg"
    source.write_text("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'><rect/><rect/></svg>", encoding="utf-8")
    job = client.post("/api/business/jobs", json={**JOB, "sources": [str(source)]}).json()
    folder = Path(job["output_dir"])
    assert (folder / "sources" / "logo-sketch.svg").read_text(encoding="utf-8") == source.read_text(encoding="utf-8") and source.exists()
    task = client.get(f"/api/tasks/{job['task_id']}").json()
    assert task["allowed_paths"] == ["listing.md"] and task["results"]["origin"] == "user"  # the brief and sources are not writable


def test_support_can_start_a_business_job(client):
    from ai_hq import support
    _, actions, problems = support.parse('```cerebra-actions\n[{"action": "create_business_job", "title": "Bakery site", "type": "website", "client": "Ama", "brief": "A one-page site for Ama\'s bakery in Nairobi with opening hours."}]\n```')
    assert not problems and actions[0]["type"] == "website"
    result = client.app.state.chats.executor(actions[0])
    assert "Started the Business Studio job Bakery site" in result
    job = client.get("/api/business").json()["jobs"][0]
    assert client.get(f"/api/tasks/{job['task_id']}").json()["results"]["origin"] == "support"


def test_open_is_confined_to_the_job_folder(client, monkeypatch):
    opened = []
    monkeypatch.setattr("os.startfile", lambda path: opened.append(path), raising=False)
    job = client.post("/api/business/jobs", json=JOB).json()
    assert client.post(f"/api/business/jobs/{job['id']}/open", json={"what": "folder"}).json()["opened"] == job["output_dir"]
    assert client.post(f"/api/business/jobs/{job['id']}/open", json={"what": "result"}).status_code == 400  # not created yet
    assert client.post(f"/api/business/jobs/{job['id']}/open", json={"what": "../../Windows"}).status_code == 422


@pytest.mark.parametrize("files,ok", [
    ({"design.svg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><circle r='4'/><rect width='2' height='2'/></svg>", "README.md": "About"}, True),
    ({"design.svg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><script>alert(1)</script><rect/></svg>", "README.md": "About"}, False),
    ({"design.svg": "<svg", "README.md": "About"}, False),
    ({"README.md": "About"}, False),
])
def test_checker_validates_svg(tmp_path, files, ok):
    (tmp_path / "cerebra-brief.json").write_text(json.dumps({"required_files": ["design.svg", "README.md"]}), encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert (business_check.main(str(tmp_path)) == 0) is ok
    process = subprocess.run([sys.executable, "-I", business_check.__file__, str(tmp_path)], capture_output=True, text=True)
    assert (process.returncode == 0) is ok


def test_checker_validates_website(tmp_path):
    (tmp_path / "cerebra-brief.json").write_text(json.dumps({"required_files": ["index.html"]}), encoding="utf-8")
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    assert business_check.main(str(tmp_path)) == 1
    (tmp_path / "index.html").write_text("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='styles.css'><title>Ama's Bakery</title></head><body>hi</body></html>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("body { margin: 0; }", encoding="utf-8")
    assert business_check.main(str(tmp_path)) == 0


def test_website_requires_viewport_and_real_local_stylesheet(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<html><head><meta charset='utf-8'><title>Bakery</title></head><body>Hi</body></html>")
    problems = []; business_check.check_html(page, problems)
    assert any("viewport" in item for item in problems) and any("stylesheet" in item for item in problems)
    page.write_text("<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Bakery</title><link rel='stylesheet' href='../outside.css'></head><body>Hi</body></html>")
    problems = []; business_check.check_html(page, problems)
    assert any("inside the website folder" in item for item in problems)


@pytest.mark.parametrize("kind", ["website", "svg"])
def test_export_preserves_deliverable_readme_and_hashes_final_bytes(tmp_path, monkeypatch, kind):
    import hashlib
    from types import SimpleNamespace as NS
    from ai_hq import business
    from ai_hq.models import BusinessJob
    original = "My reviewed instructions, palette and attribution."
    for name in business.KINDS[kind]["files"]: (tmp_path / name).write_text(original if name == "README.md" else "Deliverable")
    (tmp_path / "generated").mkdir(); (tmp_path / "generated/image.png").write_bytes(b"fixture-image")
    job = NS(id="audit", status="active", task_id="task", output_dir=str(tmp_path), kind=kind, title="Original design", client="", export={})
    task = NS(id="task", state="COMPLETED", review_findings=[], test_results=[{"attempt":0,"passed":True}], results={})
    class Session:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,model,key): return job if model is BusinessJob else task
    class Factory:
        def __call__(self): return Session()
        def begin(self): return Session()
    monkeypatch.setattr(business, "describe", lambda session, job: job.export)
    result = business.export(Factory(), "audit", True)
    target = Path(result["folder"])
    assert (target / "README.md").read_text() == original and (target / "CEREBRA-EXPORT.md").is_file()
    manifest = json.loads((target / "manifest.json").read_text())
    for entry in manifest["files"]:
        raw = (target / entry["path"]).read_bytes()
        assert entry["bytes"] == len(raw) and entry["sha256"] == hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(result["zip"]) as archive:
        assert archive.read("README.md").decode() == original and "generated/image.png" in archive.namelist()
