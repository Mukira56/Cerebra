"""Run & view: what a project built opens in the browser (websites) or the right program (everything else)."""
import json
import sys
import time
import urllib.request

import pytest

from ai_hq.viewer import Viewer, detect
from test_product_api import calculator, client  # noqa: F401  (client is a fixture)


def write(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize("files,kind,extra", [
    ({"package.json": json.dumps({"scripts": {"dev": "vite", "build": "vite build"}}), "pnpm-lock.yaml": ""}, "node", {"manager": "pnpm", "script": "dev"}),
    ({"package.json": json.dumps({"scripts": {"start": "react-scripts start"}})}, "node", {"manager": "npm", "script": "start"}),
    ({"package.json": json.dumps({"scripts": {"test": "jest"}}), "dist/index.html": "<h1>x</h1>"}, "static", {"root": "dist"}),
    ({"index.html": "<h1>Portfolio</h1>"}, "static", {"root": ""}),
    ({"manage.py": "import django"}, "django", {}),
    ({"app.py": "from flask import Flask\napp = Flask(__name__)\n"}, "flask", {"module": "app"}),
    ({"main.py": "from fastapi import FastAPI\napi = FastAPI()\n"}, "fastapi", {"target": "main:api"}),
    ({"streamlit_app.py": "import streamlit as st\n"}, "streamlit", {"file": "streamlit_app.py"}),
    ({"pubspec.yaml": "name: app"}, "flutter", {}),
    ({"Shop.sln": ""}, "open", {"file": "Shop.sln"}),
    ({"README.md": "x", "output/report.pdf": "%PDF"}, "open", {"file": "output/report.pdf"}),
    ({"tool.py": "print('hi')", "test_tool.py": ""}, "script", {"file": "tool.py"}),
    ({"README.md": "only notes"}, "folder", {}),
])
def test_each_kind_of_project_gets_the_right_way_to_view_it(tmp_path, files, kind, extra):
    plan = detect(write(tmp_path, files))
    assert plan["kind"] == kind and all(plan[key] == value for key, value in extra.items()), plan


class Recorder:
    def __init__(self):
        self.opened, self.started, self.terminals = [], [], []


def viewer_for(tmp_path):
    record = Recorder()
    viewer = Viewer(tmp_path / "data", lambda args, title, cwd=None: record.terminals.append((list(map(str, args)), cwd)),
                    opener=record.opened.append, starter=record.started.append, python=sys.executable)
    return viewer, record


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode()


def wait_running(viewer, key, seconds=60):
    for _ in range(seconds * 4):
        status = viewer.status(key)
        if status["state"] != "starting":
            return status
        time.sleep(0.25)
    raise AssertionError("still starting")


def test_a_plain_html_site_is_served_and_opened_in_the_browser(tmp_path):
    site = write(tmp_path / "site", {"index.html": "<h1>Hello from the portfolio</h1>"})
    viewer, record = viewer_for(tmp_path)
    status = viewer.start("project:1", site, "Portfolio")
    assert status["state"] == "running" and record.opened == [status["url"]] and status["url"].startswith("http://127.0.0.1:")
    assert "Hello from the portfolio" in fetch(status["url"])
    assert viewer.start("project:1", site, "Portfolio")["url"] == status["url"] and len(record.opened) == 2  # opens again, same server
    viewer.stop("project:1")
    with pytest.raises(OSError):
        fetch(status["url"])


def test_a_python_web_app_really_runs_and_stop_ends_it(tmp_path):
    app = write(tmp_path / "api", {"main.py": "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/')\ndef home():\n    return {'hello': 'cerebra'}\n"})
    viewer, record = viewer_for(tmp_path)
    viewer.start("project:2", app, "API")
    status = wait_running(viewer, "project:2")
    assert status["state"] == "running", status
    assert record.opened == [status["url"]] and json.loads(fetch(status["url"])) == {"hello": "cerebra"}
    viewer.stop("project:2")
    time.sleep(1)
    with pytest.raises(OSError):
        fetch(status["url"])


def test_other_results_open_with_their_own_program(tmp_path):
    viewer, record = viewer_for(tmp_path)
    report = write(tmp_path / "report", {"output/summary.pdf": "%PDF"})
    assert viewer.start("project:3", report, "Report")["state"] == "opened" and record.started == [str(report / "output/summary.pdf")]
    tool = write(tmp_path / "tool", {"main.py": "input('name? ')"})
    assert viewer.start("project:4", tool, "Tool")["state"] == "opened"
    assert record.terminals == [([sys.executable, "main.py"], str(tool))]
    flutter = write(tmp_path / "phone", {"pubspec.yaml": "name: app"})
    status = viewer.start("project:5", flutter, "Phone")
    assert status["state"] == "opened" or "Flutter isn't installed" in status["message"]


def test_the_project_and_task_buttons_use_the_api(client, tmp_path):  # noqa: F811
    repo = calculator(tmp_path / "calc")
    (repo / "index.html").write_text("<h1>Calculator page</h1>", encoding="utf-8")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]}).json()
    opened = []
    client.app.state.viewer.opener = opened.append
    info = client.get(f"/api/view/project/{project['id']}").json()
    assert info["plan"]["kind"] == "static" and info["status"]["state"] == "stopped"
    started = client.post(f"/api/view/project/{project['id']}").json()
    assert started["state"] == "running" and opened == [started["url"]] and "Calculator page" in fetch(started["url"])
    assert client.get(f"/api/view/project/{project['id']}").json()["status"]["state"] == "running"
    assert client.delete(f"/api/view/project/{project['id']}").json()["state"] == "stopped"
    assert client.post("/api/view/project/nope").status_code == 404
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Change the page", "allowed_paths": ["index.html"]}).json()
    assert client.post(f"/api/view/task/{task['id']}").status_code == 400  # no working copy yet


def test_a_finished_install_step_is_not_mistaken_for_a_stopped_server(tmp_path):
    from ai_hq.viewer import free_port
    viewer, record = viewer_for(tmp_path)
    site = write(tmp_path / "web", {"index.html": "<h1>Built site</h1>"})
    port = free_port()
    with viewer._lock:
        viewer._running["project:6"] = {"state": "starting", "url": None, "message": "", "log": str(tmp_path / "view.log")}
    steps = [("install", [sys.executable, "-c", "import time; time.sleep(1)"]),  # like npm install: runs, then exits 0
             ("serve", [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"])]
    import threading
    worker = threading.Thread(target=viewer._run, args=("project:6", site, steps, port, tmp_path / "view.log"), daemon=True)
    worker.start()
    status = wait_running(viewer, "project:6")
    assert status["state"] == "running", status
    assert "Built site" in fetch(status["url"])
    viewer.stop("project:6")


def test_support_can_open_a_project_for_the_owner(client, tmp_path):  # noqa: F811
    from ai_hq import support
    repo = calculator(tmp_path / "calc")
    (repo / "index.html").write_text("<h1>Shown by Support</h1>", encoding="utf-8")
    client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["python", "-c", "pass"]]})
    opened = []
    client.app.state.viewer.opener = opened.append
    _, actions, problems = support.parse('```cerebra-actions\n[{"action": "run_and_view", "project": "Calc"}]\n```')
    assert not problems
    result = client.app.state.chats.executor(actions[0])
    assert result["next_state"] == "running" and opened and "Shown by Support" in fetch(opened[0])
