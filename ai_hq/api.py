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
from .models import Project, Task, Run, Review, Approval, Event, Dependency, Metadata, Agent, as_dict, uid, now
from .schemas import (ProjectCreate, TaskCreate, SessionCreate, SettingsUpdate, ApprovalDecision, ProfileCreate, ProfileUpdate,
                      RolesUpdate, AgentPermissions, ChatCreate, ChatSend, GithubClone, GithubPublish, DemoCleanup, AutopilotUpdate, FullAccess, RoutingUpdate)
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
    from .chat import ChatService
    from .integrations import Integrations
    def resolved_executable(name):
        adapter = supervisor.registry.adapters.get(name)
        return adapter._find() if adapter is not None else None
    integrations = Integrations(settings, executables=resolved_executable)
    def chat_registry():
        supervisor._refresh_registry()
        return supervisor.registry
    chats = ChatService(db, settings, chat_registry)
    chats.recover()
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

    app = FastAPI(title="Cerebra", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.db, app.state.supervisor, app.state.settings = db, supervisor, settings
    app.state.integrations, app.state.chats = integrations, chats

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
        values["cost_information"] = "AI usage is billed by your provider account (ChatGPT, Claude, GitHub). Cerebra does not estimate costs."
        return values

    @app.get("/api/overview")
    def overview():
        with db.Session() as session:
            projects = [as_dict(row) for row in session.scalars(select(Project).order_by(Project.created_at.desc()))]
            tasks = [as_dict(row) for row in session.scalars(select(Task).order_by(Task.created_at.desc()).limit(500))]
            approvals = [as_dict(row) for row in session.scalars(select(Approval).order_by(Approval.created_at.desc()).limit(200))]
            events = [as_dict(row) for row in session.scalars(select(Event).order_by(Event.created_at.desc()).limit(100))]
            agents = [dict(as_dict(row)["status"], name=row.id) for row in session.scalars(select(Agent)) if not row.id.startswith("mock-")]
            from .profiles import list_profiles, default_roles
            profiles, roles = list_profiles(session), default_roles(session)
            from . import autopilot, routing
            from .catalog import catalog
            away = autopilot.describe(autopilot.load(session))
            route_policy = routing.load(session)
        if not agents:
            agents = [{"name":"claude","available":False,"status":"Not probed; run doctor", "authentication":"Not checked"},{"name":"codex","available":False,"status":"Not probed; run doctor", "authentication":"Not checked"}]
        active = next((task for task in tasks if task["state"] in {"RUNNING","VERIFYING","REVIEWING"}),None)
        return {"projects":projects,"tasks":tasks,"agents":agents,"approvals":approvals,"events":events,"settings":public_settings(),"profiles":profiles,"roles":roles,"autopilot":away,"routing":route_policy,"catalog":catalog(),"version":__version__,"supervisor":{"state":"working" if active else "idle","active_task":active["id"] if active else None}}

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
            for args in (["git","init","--initial-branch=main"], ["git","-c","user.name=Cerebra","-c","user.email=local@ai-hq.invalid","-c","commit.gpgsign=false","-c","core.hooksPath=" + str(settings.data_dir/"disabled-hooks"),"commit","--allow-empty","-m","Initialize authorized Cerebra project"]):
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
            project = Project(name=payload.name.strip(),path=str(project_path),default_branch=info["default_branch"],test_commands=payload.test_commands,mode="live",protected_branches=[info["default_branch"]])
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

    # ---- models and providers ---------------------------------------------------------------
    @app.get("/api/providers")
    def providers():
        from .integrations import PROVIDERS
        with db.Session() as session:
            rows = {row.id: row.status for row in session.scalars(select(Agent))}
            sign_ins = session.get(Metadata, "sign_in_status")
            sign_ins = sign_ins.value if sign_ins else {}
        return [{"id": name, **{key: value for key, value in provider.items() if key not in {"login", "logout", "status"}}, "can_sign_out": bool(provider["logout"]),
                 "status": rows.get(name, {}), "sign_in": sign_ins.get(name)} for name, provider in PROVIDERS.items()]

    @app.post("/api/providers/{name}/sign-in")
    def sign_in(name: str):
        with db.Session.begin() as session:
            session.add(Event(kind="sign_in", message=f"User opened the {name} sign-in window"))
        return integrations.sign_in(name)

    def remember_sign_in(name, status):
        with db.Session.begin() as session:
            row = session.get(Metadata, "sign_in_status")
            values = dict(row.value) if row else {}
            values[name] = status
            if row: row.value = values
            else: session.add(Metadata(key="sign_in_status", value=values))
        return status

    @app.post("/api/providers/{name}/check")
    def check_sign_in(name: str): return remember_sign_in(name, integrations.sign_in_status(name))

    @app.post("/api/providers/{name}/sign-out")
    def sign_out(name: str):
        status = remember_sign_in(name, integrations.sign_out(name))
        with db.Session.begin() as session:
            session.add(Event(kind="sign_in", message=f"User signed out of {name}"))
        return status

    @app.post("/api/providers/refresh")
    def refresh_providers():
        from .doctor import inspect
        inspect(settings)
        supervisor._refresh_registry()
        for adapter in supervisor.registry.adapters.values(): adapter._capability = None
        return providers()

    @app.get("/api/models")
    def models():
        from .profiles import list_profiles, default_roles
        from .catalog import catalog, TIER_LABEL
        from . import routing
        with db.Session() as session:
            return {"profiles": list_profiles(session), "roles": default_roles(session), "catalog": catalog(), "tiers": TIER_LABEL, "routing": routing.load(session)}

    @app.post("/api/models", status_code=201)
    def add_model(payload: ProfileCreate):
        from .profiles import add_profile
        with db.Session.begin() as session:
            profile = add_profile(session, payload.provider, payload.model, payload.label)
            session.add(Event(kind="settings_changed", message=f"Added model profile {profile['label']}"))
            return profile

    @app.patch("/api/models/{identifier}")
    def change_model(identifier: str, payload: ProfileUpdate):
        from .profiles import update_profile
        with db.Session.begin() as session:
            profile = update_profile(session, identifier, payload.model, payload.label)
            session.add(Event(kind="settings_changed", message=f"Changed model profile {profile['label']}"))
            return profile

    @app.delete("/api/models/{identifier}")
    def remove_model(identifier: str):
        from .profiles import delete_profile
        with db.Session.begin() as session:
            delete_profile(session, identifier)
            session.add(Event(kind="settings_changed", message=f"Removed model profile {identifier}"))
        return {"deleted": identifier}

    @app.put("/api/models/roles")
    def model_roles(payload: RolesUpdate):
        from .profiles import set_default_roles
        with db.Session.begin() as session:
            return set_default_roles(session, payload.model_dump(exclude_none=True))

    # ---- agent permissions ---------------------------------------------------------------------
    @app.post("/api/permissions")
    def permissions(payload: AgentPermissions):
        """The dedicated, acknowledged switch for real agent execution. Each task still asks first."""
        if payload.enabled and not (payload.acknowledge_provider_usage and payload.acknowledge_residual_read_risk):
            raise ValueError("Tick both acknowledgements to switch AI agents on")
        with db.Session.begin() as session:
            for key, value in (("live_policy", {"enabled": payload.enabled}),
                               ("sandbox_policy", {"mode": "cli-confinement", "residual_read_risk_acknowledged": True, "accepted_at": now()} if payload.enabled else {"mode": "none"})):
                row = session.get(Metadata, key)
                if row: row.value = value
                else: session.add(Metadata(key=key, value=value))
            session.add(Event(kind="policy", message="User switched AI agents on (each task still asks first)" if payload.enabled else "User switched AI agents off"))
            if not payload.enabled:
                from . import autopilot
                autopilot.save(session, False)
                row = session.get(Metadata, "access_policy")
                if row: row.value = {"level": "project"}
            apply_stored_policies(session, settings)
        supervisor._refresh_registry()
        for adapter in supervisor.registry.adapters.values(): adapter._capability = None
        return public_settings()

    @app.post("/api/permissions/full-access")
    def full_access(payload: FullAccess):
        """The user's explicit choice to let coding agents run anything with their account and GitHub login."""
        if payload.enabled:
            if not (settings.live_enabled and settings.cli_confinement_accepted):
                raise ValueError("Switch AI agents on first")
            if not (payload.acknowledge_full_access and payload.acknowledge_github):
                raise ValueError("Tick both boxes to give the agents full access")
        with db.Session.begin() as session:
            value = {"level": "full", "acknowledged": True, "accepted_at": now()} if payload.enabled else {"level": "project"}
            row = session.get(Metadata, "access_policy")
            if row: row.value = value
            else: session.add(Metadata(key="access_policy", value=value))
            session.add(Event(kind="policy", message="User gave coding agents full access to this computer and GitHub" if payload.enabled else "User limited coding agents to the project copy again"))
            apply_stored_policies(session, settings)
        supervisor._refresh_registry()
        return public_settings()

    @app.get("/api/routing")
    def routing_status():
        from . import routing
        with db.Session() as session: return routing.load(session)

    @app.put("/api/routing")
    def routing_update(payload: RoutingUpdate):
        from . import routing
        with db.Session.begin() as session:
            value = routing.save(session, payload.mode, payload.provider, payload.model)
            session.add(Event(kind="settings_changed", message="Supervisor now picks models with rules" if payload.mode == "rules" else f"Supervisor now asks {payload.provider} {payload.model or ''} to pick models".replace("  ", " ")))
            return value

    @app.get("/api/autopilot")
    def autopilot_status():
        from . import autopilot
        with db.Session() as session: return autopilot.describe(autopilot.load(session))

    @app.put("/api/autopilot")
    def autopilot_update(payload: AutopilotUpdate):
        """Away mode: a time-limited delegation of approval gates. Separate from switching agents on."""
        from . import autopilot
        if payload.enabled:
            if not (settings.live_enabled and settings.cli_confinement_accepted):
                raise ValueError("Switch AI agents on first (Agent permissions, above)")
            if not payload.acknowledge_auto_approval:
                raise ValueError("Tick the box to let Cerebra approve plans and runs for you")
            if payload.auto_merge and not payload.acknowledge_auto_merge:
                raise ValueError("Tick the merge box too, or turn automatic merging off")
        with db.Session.begin() as session:
            for project_id in payload.projects: project_or_404(session, project_id)
            policy = autopilot.save(session, payload.enabled, payload.hours, payload.auto_merge, payload.projects, payload.auto_push)
            session.add(Event(kind="policy", message=(f"User turned Away mode on until {policy['until'][:16].replace('T', ' ')} UTC"
                + (" with automatic merging" if policy["auto_merge"] else "") + (" and pushing to GitHub" if policy["auto_push"] else "")) if payload.enabled else "User turned Away mode off"))
        supervisor._wake.set()
        return policy

    # ---- toolchain ---------------------------------------------------------------------------
    @app.get("/api/tools")
    def tools(refresh: bool = False): return integrations.tools(refresh)

    @app.post("/api/tools/{tool_id}/install")
    def install_tool(tool_id: str):
        result = integrations.install(tool_id)
        with db.Session.begin() as session:
            session.add(Event(kind="toolchain", message=f"User opened an install window for {tool_id}"))
        return result

    # ---- GitHub ------------------------------------------------------------------------------
    @app.get("/api/github")
    def github(): return integrations.github_status()

    @app.post("/api/github/sign-in")
    def github_sign_in(): return integrations.github_sign_in()

    @app.post("/api/github/sign-out")
    def github_sign_out():
        status = integrations.github_sign_out()
        with db.Session.begin() as session:
            session.add(Event(kind="github", message="User signed out of GitHub"))
        return status

    @app.get("/api/github/repositories")
    def github_repositories(): return integrations.github_repositories()

    @app.post("/api/github/clone", status_code=201)
    def github_clone(payload: GithubClone):
        import re
        folder = re.sub(r"[^A-Za-z0-9_.-]+", "-", payload.repository.split("/")[-1]).strip("-.") or "project"
        destination = integrations.clone(payload.repository, settings.data_dir / "projects" / f"{folder}-{uid()[:6]}")
        project = register(ProjectCreate(name=payload.name.strip() or payload.repository, path=str(destination), authorize=True, test_commands=payload.test_commands))
        with db.Session.begin() as session:
            session.add(Event(kind="github", message=f"Cloned {payload.repository} from GitHub"))
        return project

    def project_or_404(session, project_id):
        project = session.get(Project, project_id)
        if not project: raise HTTPException(404, "Project not found")
        return project

    @app.post("/api/projects/{project_id}/publish")
    def github_publish(project_id: str, payload: GithubPublish):
        with db.Session() as session: project = project_or_404(session, project_id)
        result = integrations.create_repository(project.path, payload.name, payload.visibility)
        with db.Session.begin() as session:
            session.add(Event(kind="github", message=f"Published {project.name} to GitHub as a {payload.visibility} repository"))
        return result

    @app.post("/api/projects/{project_id}/push")
    def github_push(project_id: str):
        with db.Session() as session: project = project_or_404(session, project_id)
        result = integrations.push(project.path, project.default_branch)
        with db.Session.begin() as session:
            session.add(Event(kind="github", message=f"Pushed {project.name} ({project.default_branch}) to GitHub"))
        return result

    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, payload: dict):
        commands = ProjectCreate.commands(payload.get("test_commands", []))
        if set(payload) - {"test_commands"}: raise ValueError("Only test_commands can be changed")
        with db.Session.begin() as session:
            project = project_or_404(session, project_id)
            project.test_commands = commands
            session.add(Event(kind="settings_changed", message=f"Changed the test commands of {project.name}"))
            return as_dict(project)

    # ---- chat -------------------------------------------------------------------------------
    @app.get("/api/chats")
    def chat_list(): return chats.conversations()

    @app.post("/api/chats", status_code=201)
    def chat_create(payload: ChatCreate): return chats.create(payload.profile, payload.project_id, payload.title)

    def chat_or_404(call, *args):
        try: return call(*args)
        except LookupError as exc: raise HTTPException(404, str(exc))

    @app.get("/api/chats/{conversation_id}")
    def chat_messages(conversation_id: str): return chat_or_404(chats.messages, conversation_id)

    @app.post("/api/chats/{conversation_id}/messages", status_code=202)
    def chat_send(conversation_id: str, payload: ChatSend): return chat_or_404(chats.send, conversation_id, payload.text)

    @app.post("/api/chats/{conversation_id}/stop")
    def chat_stop(conversation_id: str): return chats.stop(conversation_id)

    @app.delete("/api/chats/{conversation_id}")
    def chat_delete(conversation_id: str):
        chat_or_404(chats.delete, conversation_id)
        return {"deleted": conversation_id}

    # ---- plain-language reports and system view ------------------------------------------
    @app.get("/api/reports/{task_id}")
    def report(task_id: str):
        from .reports import build
        task = detail(task_id)
        with db.Session() as session:
            project = as_dict(session.get(Project, task["project_id"]))
        return build(task, project, settings.data_dir)

    @app.get("/api/system")
    def system():
        def size(path): return path.stat().st_size if path.exists() else 0
        with db.Session() as session:
            queued = sum(1 for task in session.scalars(select(Task).where(Task.state.in_(["READY","RUNNING","VERIFYING","REVIEWING","NEEDS_CHANGES"]))))
        worktrees = settings.data_dir / "worktrees"
        logs = settings.data_dir / "logs"
        return {"version": __version__, "server": f"http://127.0.0.1:{settings.port}", "data_dir": str(settings.data_dir),
                "database": {"path": str(settings.db_path), "bytes": size(settings.db_path) + size(settings.db_path.with_name(settings.db_path.name + "-wal"))},
                "logs": {"path": str(logs), "files": len(list(logs.glob("*.log"))) if logs.is_dir() else 0},
                "worktrees": {"path": str(worktrees), "count": sum(1 for _ in worktrees.glob("*/*")) if worktrees.is_dir() else 0},
                "queue": queued, "agents_enabled": settings.live_enabled and settings.cli_confinement_accepted}

    # ---- maintenance ---------------------------------------------------------------------------
    @app.get("/api/maintenance/demo-data")
    def demo_data():
        from .maintenance import preview
        return preview(db, settings.data_dir)

    @app.post("/api/maintenance/demo-data")
    def remove_demo(payload: DemoCleanup):
        from .maintenance import remove_demo_data
        with supervisor._lock:
            return remove_demo_data(db, settings.data_dir)

    @app.get("/")
    def index(): return FileResponse(STATIC/"index.html")
    STATIC.mkdir(exist_ok=True)
    app.mount("/static",StaticFiles(directory=STATIC),name="static")
    return app
