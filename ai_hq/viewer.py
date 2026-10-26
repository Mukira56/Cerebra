"""Run & view: start what a project built and open it where a person can use it.

Websites run on this computer and open in the default browser (Brave, Chrome, Edge...): an npm/pnpm/yarn
dev script, a Python web app (Django, Flask, FastAPI, Streamlit) on a free local port, or plain HTML served by
Cerebra itself. Other results open with the tool made for them: documents and images in their default app,
notebooks in Jupyter, Flutter apps in Chrome, Visual Studio solutions in Visual Studio, scripts in a visible
terminal window. It always runs at the owner's click, like the project's own tests; servers listen on this
computer only where Cerebra chooses the address, and Stop ends the whole process tree.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from .processes import resolve_command
from .security import redact

URL = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d{2,5}[^\s'\"\x1b]*")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
DOCUMENTS = (".html", ".pdf", ".docx", ".pptx", ".xlsx", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".md", ".txt", ".csv")
WAIT_SECONDS = 180  # npm install + a first dev-server build can take minutes on a slow laptop
SKIP = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist-ssr"}


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _read(path, limit=200_000):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def detect(folder):
    """How this folder's result is viewed: {"kind", "label", "how", ...}. Never runs anything."""
    root = Path(folder)
    if not root.is_dir():
        return {"kind": "missing", "label": "Folder not found", "how": f"{folder} doesn't exist any more."}
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(_read(package)).get("scripts") or {}
        except ValueError:
            scripts = {}
        script = next((name for name in ("dev", "start", "preview", "serve") if name in scripts), None)
        if script:
            manager = "pnpm" if (root / "pnpm-lock.yaml").is_file() else "yarn" if (root / "yarn.lock").is_file() else "npm"
            return {"kind": "node", "label": "Open the website", "how": f"Runs “{manager} run {script}” and opens it in your browser.",
                    "manager": manager, "script": script, "command": scripts[script]}
    if (root / "manage.py").is_file():
        return {"kind": "django", "label": "Open the website", "how": "Runs the Django development server and opens it in your browser."}
    for name in ("streamlit_app.py", "app.py", "main.py", "server.py", "wsgi.py"):
        source = _read(root / name)
        if not source:
            continue
        module = name[:-3]
        if "import streamlit" in source or "from streamlit" in source:
            return {"kind": "streamlit", "label": "Open the app", "how": f"Runs “streamlit run {name}” and opens it in your browser.", "file": name}
        if re.search(r"\bFlask\(", source):
            return {"kind": "flask", "label": "Open the website", "how": f"Runs the Flask app in {name} and opens it in your browser.", "module": module}
        variable = re.search(r"^(\w+)\s*=\s*FastAPI\(", source, re.M)
        if variable:
            return {"kind": "fastapi", "label": "Open the app", "how": f"Runs {name} with uvicorn and opens its page in your browser.",
                    "target": f"{module}:{variable.group(1)}"}
    for sub in ("", "dist", "build", "public", "site", "docs", "www", "src"):
        if (root / sub / "index.html").is_file():
            return {"kind": "static", "label": "Open the website", "how": "Serves the pages on this computer and opens them in your browser.", "root": sub}
    if (root / "pubspec.yaml").is_file():
        return {"kind": "flutter", "label": "Run the app", "how": "Runs the Flutter app in Chrome (needs Flutter installed)."}
    solution = next(iter(sorted(root.glob("*.sln"))), None)
    if solution:
        return {"kind": "open", "label": "Open in Visual Studio", "how": f"Opens {solution.name} with its default program.", "file": solution.name}
    notebook = next(iter(sorted(root.glob("*.ipynb"))), None)
    if notebook:
        jupyter = shutil.which("jupyter")
        return {"kind": "notebook" if jupyter else "open", "label": "Open the notebook",
                "how": f"Opens {notebook.name} in Jupyter." if jupyter else f"Opens {notebook.name} with its default program (Jupyter isn't installed).",
                "file": notebook.name}
    document = _main_document(root)
    if document:
        return {"kind": "open", "label": f"Open {Path(document).name}", "how": "Opens the result with its default program.", "file": document}
    script = next((name for name in ("main.py", "app.py", "run.py", "cli.py") if (root / name).is_file()), None) \
        or next((path.name for path in sorted(root.glob("*.py")) if not path.name.startswith("test")), None)
    if script:
        return {"kind": "script", "label": "Run it", "how": f"Runs {script} in a terminal window you can type into.", "file": script}
    return {"kind": "folder", "label": "Open the folder", "how": "Opens the project folder so you can look at the files."}


def _main_document(root):
    for sub in ("output", "out", "exports", "results", ""):
        folder = root / sub
        if not folder.is_dir():
            continue
        for suffix in DOCUMENTS:
            for path in sorted(folder.glob(f"*{suffix}")):
                if path.name.lower() not in {"readme.md", "license.txt", "requirements.txt", "changelog.md"}:
                    return path.relative_to(root).as_posix()
    return None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Viewer:
    """Runs at most one viewer per key (a project or a task) and remembers how it is doing."""

    def __init__(self, data_dir, terminal, opener=None, starter=None, python=None):
        self.data_dir = Path(data_dir)
        self.terminal = terminal  # integrations.open_terminal: a visible console window
        self.opener = opener or webbrowser.open  # the default browser
        self.starter = starter or (lambda path: os.startfile(path))  # noqa: S606 - a file inside the project, at the owner's click
        self.python = python or os.environ.get("AIHQ_PYTHON") or shutil.which("python") or "python"
        self._lock = threading.Lock()
        self._running: dict[str, dict] = {}

    def status(self, key):
        with self._lock:
            entry = self._running.get(key)
            if entry is None:
                return {"state": "stopped"}
            process = entry.get("process")
            # Only the server itself counts: an install step finishing is expected.
            if entry["state"] in {"starting", "running"} and entry.get("serving") and process is not None and process.poll() is not None:
                entry.update(state="failed", message=f"It stopped (exit code {process.returncode}). The log has the details.")
            return {key_: value for key_, value in entry.items() if key_ not in {"process", "server", "serving"}}

    def start(self, key, folder, title):
        """Start (or reopen) the viewer for this folder. Returns its status; servers finish starting in the background."""
        current = self.status(key)
        if current["state"] == "running" and current.get("url"):
            self.opener(current["url"])
            return current
        if current["state"] == "starting":
            return current
        self.stop(key)
        plan = detect(folder)
        root = Path(folder)
        log = self.data_dir / "logs" / f"view-{re.sub(r'[^A-Za-z0-9_-]', '-', key)[:60]}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        entry = {"state": "starting", "kind": plan["kind"], "label": plan["label"], "how": plan["how"], "log": str(log), "url": None, "message": "Starting…"}
        with self._lock:
            self._running[key] = entry
        kind = plan["kind"]
        if kind == "missing":
            return self._finish(key, "failed", plan["how"])
        if kind == "open":
            self.starter(str(root / plan["file"]))
            return self._finish(key, "opened", f"Opened {plan['file']}.")
        if kind == "folder":
            self.starter(str(root))
            return self._finish(key, "opened", "Opened the folder.")
        if kind == "script":
            self.terminal([self.python, plan["file"]], f"Cerebra · {title}", cwd=str(root))
            return self._finish(key, "opened", f"Started {plan['file']} in a terminal window.")
        if kind == "flutter":
            if not shutil.which("flutter"):
                return self._finish(key, "failed", "Flutter isn't installed. Install it from Toolchain, then press Run again.")
            self.terminal(["flutter", "run", "-d", "chrome"], f"Cerebra · {title}", cwd=str(root))
            return self._finish(key, "opened", "Started the Flutter app in a terminal window; it opens Chrome when it's built.")
        if kind == "static":
            return self._serve_static(key, root / plan["root"])
        port = free_port()
        steps = self._commands(plan, port)
        threading.Thread(target=self._run, args=(key, root, steps, port, log), name=f"cerebra-view-{key[:8]}", daemon=True).start()
        return self.status(key)

    def _commands(self, plan, port):
        kind, python = plan["kind"], self.python
        if kind == "node":
            manager, steps = plan["manager"], []
            steps.append(("install", [manager, "install"]))
            extra = ["--", "--port", str(port), "--strictPort"] if re.search(r"\bvite\b", plan["command"]) else []
            steps.append(("serve", [manager, "run", plan["script"], *extra]))
            return steps
        if kind == "django":
            return [("serve", [python, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"])]
        if kind == "flask":
            return [("serve", [python, "-m", "flask", "--app", plan["module"], "run", "--host", "127.0.0.1", "--port", str(port)])]
        if kind == "fastapi":
            return [("serve", [python, "-m", "uvicorn", plan["target"], "--host", "127.0.0.1", "--port", str(port)])]
        if kind == "streamlit":
            return [("serve", [python, "-m", "streamlit", "run", plan["file"], "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true"])]
        if kind == "notebook":
            return [("serve", ["jupyter", "notebook", plan["file"], "--ip", "127.0.0.1", "--port", str(port), "--no-browser"])]
        raise ValueError(f"Nothing to run for {kind}")

    def _run(self, key, root, steps, port, log):
        env = {**os.environ, "PORT": str(port), "BROWSER": "none", "HOST": "127.0.0.1", "FORCE_COLOR": "0"}
        try:
            with log.open("w", encoding="utf-8") as out:
                for name, args in steps:
                    if name == "install":
                        if (root / "node_modules").is_dir():
                            continue
                        self._update(key, message="Installing the project's packages (first run only)…")
                    command = resolve_command(args, root)
                    out.write(f"$ {' '.join(args)}\n"); out.flush()
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               stdin=subprocess.DEVNULL, creationflags=flags)
                    self._update(key, process=process, serving=name == "serve")
                    if name == "install":
                        for line in process.stdout:
                            out.write(redact(line.decode("utf-8", "replace")))
                        if process.wait() != 0:
                            return self._finish(key, "failed", "Installing the project's packages failed. The log has the details.")
                        continue
                    self._update(key, message="Starting the server…")
                    self._watch(key, process, port, out)
        except Exception as exc:  # recorded for the owner, never raised into the server
            self._finish(key, "failed", redact(str(exc))[:500])

    def _watch(self, key, process, port, out):
        """Read the server's output until it says where it is listening (or our port answers), then open it."""
        found = {"url": None}

        def read():
            for raw in process.stdout:
                line = ANSI.sub("", raw.decode("utf-8", "replace"))
                out.write(redact(line)); out.flush()
                match = URL.search(line)
                if match and not found["url"]:
                    found["url"] = match.group(0).replace("0.0.0.0", "127.0.0.1").rstrip("/.,)") + "/"
        threading.Thread(target=read, daemon=True).start()
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            if self.status(key)["state"] == "stopped":
                return
            if process.poll() is not None:
                return self._finish(key, "failed", f"The server stopped before it was ready (exit code {process.returncode}). The log has the details.")
            if found["url"] or _answers(port):
                url = found["url"] or f"http://127.0.0.1:{port}/"
                self._update(key, url=url)
                self.opener(url)
                return self._finish(key, "running", f"Running at {url} and opened in your browser.")
            time.sleep(0.5)
        self._finish(key, "failed", "The server didn't say where it was listening within 3 minutes. The log has the details.")

    def _serve_static(self, key, folder):
        handler = functools.partial(_QuietHandler, directory=str(folder))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, name=f"cerebra-static-{key[:8]}", daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        self._update(key, server=server, url=url)
        self.opener(url)
        return self._finish(key, "running", f"Serving the pages at {url} and opened them in your browser.")

    def stop(self, key):
        with self._lock:
            entry = self._running.pop(key, None)
        if not entry:
            return {"state": "stopped"}
        if entry.get("server"):
            entry["server"].shutdown(); entry["server"].server_close()
        process = entry.get("process")
        if process is not None and process.poll() is None:
            if os.name == "nt":  # the dev server's own child processes too
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                process.kill()
        return {"state": "stopped"}

    def stop_all(self):
        for key in list(self._running):
            self.stop(key)

    def _update(self, key, **values):
        with self._lock:
            if key in self._running:
                self._running[key].update(values)

    def _finish(self, key, state, message):
        self._update(key, state=state, message=message)
        return self.status(key)


def _answers(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False
