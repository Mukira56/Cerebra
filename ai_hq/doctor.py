"""Read-only tool discovery. Never inspect provider credential storage."""
import importlib.metadata
import json
import platform
import shutil
import sys
from pathlib import Path
from .config import Settings, apply_stored_policies
from .db import Database
from .models import Agent

def inspect(settings=None):
    from .agents import AgentRegistry
    from .processes import ProcessRunner
    settings = settings or Settings()
    db=Database(settings.db_path);db.init()
    from .models import Metadata
    from .schemas import SettingsUpdate
    with db.Session() as session:
        saved=session.get(Metadata,"settings")
        if saved:
            validated=SettingsUpdate.model_validate(saved.value)
            for name,value in validated.model_dump(exclude_none=True).items(): setattr(settings,name,value)
        apply_stored_policies(session,settings)
    checks = []
    def check(name,status,detail): checks.append({"name":name,"status":status,"detail":detail})
    check("OS","PASS",f"{platform.system()} {platform.release()} {platform.machine()}")
    check("Python","PASS" if sys.version_info >= (3,13) else "FAIL",platform.python_version())
    runner = ProcessRunner()
    for name in ["git","powershell","node","npm","ollama"]:
        executable=shutil.which(name)
        if not executable:
            check(name,"FAIL" if name=="git" else "WARN","Not on PATH" + (" (optional)" if name not in {"git"} else ""))
        else:
            if name in {"git","node","ollama"}:
                result=runner.run([executable,"--version"],settings.data_dir,timeout=10)
                detail=(result.stdout or result.stderr).strip()[:400]
            else: detail=executable
            check(name,"PASS",detail)
    for package in ["pip","fastapi","pydantic","sqlalchemy","uvicorn","pytest","httpx"]:
        try: check(package,"PASS",importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError: check(package,"FAIL","Missing from this Python environment")
    disk=shutil.disk_usage(settings.data_dir)
    check("Free disk","WARN" if disk.free < 2*1024**3 else "PASS",f"{disk.free/1024**2:.0f} MiB free; no cleanup performed")
    probes=AgentRegistry(executable_paths={"codex":settings.codex_path,"claude":settings.claude_path},allow_live=settings.live_enabled,
                         confinement_mode="cli-confinement" if settings.cli_confinement_accepted else "none").probe(authenticate=False)
    with db.Session.begin() as session:
        for name,info in probes.items():
            row=session.get(Agent,name)
            if row:
                for key in ("last_live_success_at", "last_live_task", "last_live_role", "last_authentication_error_at"):
                    if key in row.status: info[key] = row.status[key]
                if row.status.get("authentication") in {"verified_by_execution", "failed"}:
                    info["authentication"] = row.status["authentication"]
            if row: row.status=info
            else: session.add(Agent(id=name,status=info))
            check(name,"PASS" if info.get("available") else "WARN",info.get("reason",""))
    db.close()
    check("Provider authentication","WARN","Not checked; requires explicit consent. No credentials read.")
    return {"checks":checks,"agents":probes}

def main():
    report=inspect()
    for row in report["checks"]: print(f"{row['status']:4}  {row['name']}: {row['detail']}")
    return 1 if any(row["status"]=="FAIL" for row in report["checks"]) else 0

if __name__=="__main__": raise SystemExit(main())
