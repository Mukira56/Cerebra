from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from threading import Lock
import hashlib
import json
import os
import secrets
import sys
import time
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .config import Settings, apply_stored_policies
from .db import Database
from .models import Project, Task, Run, Review, Approval, Event, Dependency, Metadata, Agent, as_dict, uid
from .schemas import ProjectCreate, TaskCreate, SessionCreate, SettingsUpdate, ApprovalDecision
from .security import redact
from . import __version__

STATIC = Path(__file__).parent / "static"

def create_app(settings=None, bootstrap_key=None, start_worker=True):
    settings = settings or Settings()
    db = Database(settings.db_path)
    db.init()
    with db.Session() as session:
        saved = session.get(Metadata, "settings")
        if saved:
            validated = SettingsUpdate.model_validate(saved.value)
            for key, value in validated.model_dump(exclude_none=True).items():
                setattr(settings, key, value)
        apply_stored_policies(session, settings)
    from .supervisor import Supervisor
    supervisor = Supervisor(db, settings)
    bootstrap_hash = hashlib.sha256((bootstrap_key or secrets.token_urlsafe(32)).encode()).digest()
    bootstrap_used = False
    sessions = {}
    bootstrap_lock = Lock()
    failed_sessions = []

    @asynccontextmanager
    async def lifespan(app):
        if start_worker: supervisor.startup()
        yield
        supervisor.shutdown()
        db.close()

    app = FastAPI(title="AI Development HQ", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.db, app.state.supervisor, app.state.settings = db, supervisor, settings

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        host = request.headers.get("host", "")
        parsed_host = urlparse("http://" + host)
        if parsed_host.hostname not in {"127.0.0.1", "localhost", "[::1]", "::1", "testserver"}:
            return JSONResponse({"detail":"Only a loopback Host is accepted"}, status_code=403)
        # testserver is used solely by the in-process pytest client.
        if parsed_host.hostname == "testserver" and (not request.client or request.client.host != "testclient"):
            return JSONResponse({"detail":"Invalid Host"}, status_code=403)
        client = request.client.host if request.client else ""
        if client not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail":"Loopback clients only"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail":"Cross-site requests are blocked"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail":"Origin does not match this local server"}, status_code=403)
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            token = request.cookies.get("aihq_session", "")
            entry = sessions.get(token)
            if not entry or time.monotonic() - entry[1] > 12*3600:
                return JSONResponse({"detail":"Open the launch URL to establish a local session"}, status_code=401)
            if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), entry[0]):
                return JSONResponse({"detail":"Missing or invalid CSRF token"}, status_code=403)
        if request.method in {"POST", "PATCH", "PUT"}:
            try:
                body_length = int(request.headers.get("content-length", "0") or 0)
            except ValueError:
                return JSONResponse({"detail":"Invalid Content-Length"}, status_code=400)
            if body_length < 0 or body_length > 131072:
                return JSONResponse({"detail":"Request body too large"}, status_code=413)
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 131072:
                    return JSONResponse({"detail":"Request body too large"}, status_code=413)
                body.extend(chunk)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options":"nosniff", "Referrer-Policy":"no-referrer", "X-Frame-Options":"DENY", "Cache-Control":"no-store", "Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    @app.exception_handler(ValueError)
    async def bad_value(_, exc): return JSONResponse({"detail":redact(str(exc))}, status_code=400)

    @app.exception_handler(IntegrityError)
    async def conflict(_, exc): return JSONResponse({"detail":"Record conflicts with an existing record or dependency"}, status_code=409)

    @app.exception_handler(FileNotFoundError)
    @app.exception_handler(NotADirectoryError)
    async def missing_path(_, exc): return JSONResponse({"detail":"The specified directory does not exist or is not a directory"}, status_code=400)

    from .gitops import GitError
    @app.exception_handler(GitError)
    async def git_error(_, exc): return JSONResponse({"detail":redact(str(exc))[:2000]}, status_code=400)

    @app.get("/health")
    def health(): return {"status":"ok", "application":"AI Development HQ", "version":__version__}

    @app.post("/api/session")
    def create_session(payload: SessionCreate):
        nonlocal bootstrap_used
        with bootstrap_lock:
            current = time.monotonic()
            failed_sessions[:] = [stamp for stamp in failed_sessions if current-stamp < 60]
            if len(failed_sessions) >= 10:
                raise HTTPException(429, "Too many session attempts; retry in one minute")
            if bootstrap_used or not secrets.compare_digest(hashlib.sha256(payload.key.encode()).digest(), bootstrap_hash):
                failed_sessions.append(current)
                raise HTTPException(401, "Invalid or already consumed launch key; restart using start.ps1 if your session was lost")
            bootstrap_used = True
            session_key, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            sessions[session_key] = (csrf, current)
        response = JSONResponse({"csrf_token":csrf})
        response.set_cookie("aihq_session", session_key, httponly=True, samesite="strict", max_age=43200, path="/")
        return response

    @app.get("/api/session")
    def get_session(request: Request):
        entry = sessions.get(request.cookies.get("aihq_session", ""))
        if not entry or time.monotonic()-entry[1] > 43200: raise HTTPException(401,"No local session")
        return {"csrf_token":entry[0]}

    def task_or_404(session, task_id):
        task = session.get(Task, task_id)
        if not task: raise HTTPException(404, "Task not found")
        return task

    def public_settings():
        values = asdict(settings)
        values["data_dir"] = str(values["data_dir"])
        values["cost_information"] = "No usage charges in mock mode. Real CLI usage depends on your provider account; costs are not estimated."
        return values

    @app.get("/api/overview")
    def overview():
        with db.Session() as session:
            projects = [as_dict(row) for row in session.scalars(select(Project).order_by(Project.created_at.desc()))]
            tasks = [as_dict(row) for row in session.scalars(select(Task).order_by(Task.created_at.desc()).limit(500))]
            approvals = [as_dict(row) for row in session.scalars(select(Approval).order_by(Approval.created_at.desc()).limit(200))]
            events = [as_dict(row) for row in session.scalars(select(Event).order_by(Event.created_at.desc()).limit(100))]
            agents = [dict(as_dict(row)["status"], name=row.id) for row in session.scalars(select(Agent))]
        if not agents:
            agents = [{"name":"claude","available":False,"status":"Not probed; run doctor", "authentication":"Not checked"},{"name":"codex","available":False,"status":"Not probed; run doctor", "authentication":"Not checked"}]
        active = next((task for task in tasks if task["state"] in {"RUNNING","VERIFYING","REVIEWING"}),None)
        return {"projects":projects,"tasks":tasks,"agents":agents,"approvals":approvals,"events":events,"settings":public_settings(),"supervisor":{"state":"working" if active else "idle","active_task":active["id"] if active else None}}

    @app.get("/api/telemetry")
    def telemetry(task_id: str | None = None):
        if task_id is not None:
            if len(task_id) > 64:
                raise HTTPException(422, "Task ID is too long")
            with db.Session() as session:
                task_or_404(session, task_id)
        from .telemetry import snapshot
        return snapshot(db, task_id)

    @app.post("/api/projects", status_code=201)
    def register(payload: ProjectCreate):
        from .gitops import GitManager
        git = GitManager(settings.data_dir)
        if payload.create_new:
            project_path = settings.data_dir / "projects" / uid()
            project_path.mkdir(parents=True)
            from .processes import ProcessRunner
            runner = ProcessRunner()
            for args in (["git","init","--initial-branch=main"], ["git","-c","user.name=AI HQ","-c","user.email=local@ai-hq.invalid","-c","commit.gpgsign=false","-c","core.hooksPath=" + str(settings.data_dir/"disabled-hooks"),"commit","--allow-empty","-m","Initialize authorized AI HQ project"]):
                result = runner.run(args, project_path, timeout=30)
                if result.exit_code != 0: raise ValueError("Git initialization failed: " + result.stderr)
        else:
            if not payload.path or not Path(payload.path).is_absolute(): raise ValueError("Provide an absolute repository directory")
            project_path = Path(payload.path).resolve(strict=True)
            # Registration establishes the exact allowed repository, never a parent directory.
            if project_path == Path(project_path.anchor) or project_path == Path.home(): raise ValueError("Register a specific repository, not your drive or profile")
            current_path = Path(payload.path)
            for part in (current_path, *current_path.parents):
                if part.is_symlink() or (hasattr(part,"is_junction") and part.is_junction()): raise ValueError("Linked/junction repository paths are not permitted")
        info = git.inspect_repository(project_path)
        with db.Session.begin() as session:
            project = Project(name=payload.name.strip(),path=str(project_path),default_branch=info["default_branch"],test_commands=payload.test_commands,mode=payload.mode,protected_branches=[info["default_branch"]])
            session.add(project); session.flush()
            session.add(Event(kind="project_registered", message="User authorized this repository and its configured test commands",data={"project_id":project.id,"path":str(project_path)}))
            return as_dict(project)

    @app.post("/api/tasks", status_code=201)
    def propose(payload: TaskCreate):
        with db.Session() as session:
            if not session.get(Project,payload.project_id): raise HTTPException(404,"Project not found")
            for dep_id in payload.dependencies:
                dep = task_or_404(session,dep_id)
                if dep.project_id != payload.project_id: raise ValueError("Dependencies must belong to the same project")
        values = payload.model_dump()
        values["objective"] = values.pop("description")
        return supervisor.propose(**values)

    @app.get("/api/tasks/{task_id}")
    def detail(task_id: str):
        from .gitops import GitManager
        with db.Session() as session:
            task = task_or_404(session,task_id)
            result = as_dict(task)
            for model,name in [(Run,"runs"),(Review,"reviews"),(Event,"events"),(Approval,"approvals")]:
                result[name] = [as_dict(row) for row in session.scalars(select(model).where(model.task_id==task_id))]
            result["dependencies"] = list(session.scalars(select(Dependency.depends_on).where(Dependency.task_id==task_id)))
            result["diff"] = ""
            if task.worktree_path and Path(task.worktree_path).is_dir():
                try:
                    from .security import canonical
                    canonical(task.worktree_path,[settings.data_dir/"worktrees"])
                    snapshot = GitManager(settings.data_dir).snapshot(task.worktree_path)
                    result["diff"] = snapshot.get("diff", "") or task.results.get("diff", "")
                except (ValueError, RuntimeError, OSError) as exc: result["diff"] = redact(str(exc))
            return result

    @app.post("/api/tasks/{task_id}/{action}")
    def task_action(task_id: str, action: str):
        method = {"approve-plan":supervisor.approve_plan,"start":supervisor.start,"cancel":supervisor.cancel,"pause":supervisor.pause,"resume":supervisor.resume}.get(action)
        if not method: raise HTTPException(404,"Unknown task action")
        with db.Session() as session: task_or_404(session,task_id)
        return method(task_id)

    @app.post("/api/approvals/{approval_id}")
    def decide(approval_id: str, payload: ApprovalDecision):
        with db.Session() as session:
            if not session.get(Approval,approval_id): raise HTTPException(404,"Approval not found")
        return supervisor.resolve_approval(approval_id,payload.approve)

    @app.patch("/api/settings")
    def update_settings(payload: SettingsUpdate):
        updates = payload.model_dump(exclude_none=True)
        with db.Session.begin() as session:
            saved = session.get(Metadata,"settings")
            values = dict(saved.value) if saved else {}
            values.update(updates)
            if saved: saved.value=values
            else: session.add(Metadata(key="settings",value=values))
            session.add(Event(kind="settings_changed",message="User changed local settings",data={"keys":list(updates)}))
        for key,value in updates.items(): setattr(settings,key,value)
        return public_settings()

    @app.post("/api/demo",status_code=201)
    def demo():
        project_path = settings.data_dir / "projects" / ("demo-" + uid()[:8])
        project_path.mkdir(parents=True)
        (project_path/"calculator.py").write_text("def add(a, b):\n    return a - b\n",encoding="utf-8")
        (project_path/"test_calculator.py").write_text("from calculator import add\n\ndef test_add_positive():\n    assert add(2, 3) == 5\n\ndef test_add_negative():\n    assert add(-2, -3) == -5\n",encoding="utf-8")
        (project_path/".ai-hq-demo.json").write_text(json.dumps({"kind":"calculator-addition-v1"}),encoding="utf-8")
        (project_path/".gitignore").write_text("__pycache__/\n.pytest_cache/\n",encoding="utf-8")
        from .processes import ProcessRunner
        runner = ProcessRunner()
        for args in (["git","init","--initial-branch=demo"],["git","add","--","."],["git","-c","user.name=AI HQ Demo","-c","user.email=demo@ai-hq.invalid","-c","commit.gpgsign=false","-c","core.hooksPath="+str(settings.data_dir/"disabled-hooks"),"commit","-m","Create isolated demo with failing addition tests"]):
            result = runner.run(args,project_path,timeout=30)
            if result.exit_code: raise ValueError("Demo initialization failed: "+result.stderr)
        project = register(ProjectCreate(name="Calculator • isolated demo",path=str(project_path),authorize=True,test_commands=[[sys.executable,"-m","pytest","-q"]],mode="mock"))
        task = supervisor.propose(project_id=project["id"],objective="Fix calculator.add so that it adds positive and negative numbers",assigned_agent="codex",mode="mock",requirements=["Correct calculator.add addition"],acceptance_criteria=["Both actual pytest tests pass"],dependencies=[],allowed_paths=["calculator.py"])
        return {"project":project,"task":task}

    @app.get("/")
    def index(): return FileResponse(STATIC/"index.html")
    STATIC.mkdir(exist_ok=True)
    app.mount("/static",StaticFiles(directory=STATIC),name="static")
    return app
