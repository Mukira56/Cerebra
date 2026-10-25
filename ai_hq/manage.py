"""Portable user-session process manager. No services, elevation or policy edits."""
from __future__ import annotations
import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from .config import ROOT, Settings

STARTUP_TIMEOUT=60  # seconds to wait for /health after spawning the server

def process_identity(pid):
    if os.name != "nt":
        os.kill(pid,0)
        return {"pid":pid,"image":str(Path(sys.executable).resolve()),"created":Path(f"/proc/{pid}/stat").read_text().split()[21]}
    from ctypes import wintypes
    api=ctypes.WinDLL("kernel32",use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    api.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle: raise ProcessLookupError(pid)
    try:
        exit_code=wintypes.DWORD()
        if not api.GetExitCodeProcess(handle,ctypes.byref(exit_code)) or exit_code.value != 259:
            raise ProcessLookupError(pid)
        times=[wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(handle,*[ctypes.byref(item) for item in times]): raise OSError("Cannot verify process creation time")
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(32768)
        if not api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)): raise OSError("Cannot verify process image")
        return {"pid":pid,"image":str(Path(buffer.value).resolve()),"created":(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime}
    finally: api.CloseHandle(handle)

def owned_process(settings):
    stamp=settings.data_dir/"server.json"
    if not stamp.exists(): return None
    stored=json.loads(stamp.read_text())
    try: actual=process_identity(stored["pid"])
    except (ProcessLookupError, OSError): return None
    # A Windows venv python.exe is a launcher; the interpreter process it starts runs the base executable image.
    interpreters={Path(sys.executable).resolve(),Path(getattr(sys,"_base_executable",sys.executable)).resolve()}
    if any(actual[key]!=stored[key] for key in ("pid","created","image")) or Path(actual["image"]) not in interpreters:
        raise RuntimeError("PID identity does not match the managed Cerebra server; refusing to act")
    return stored

def start(settings,open_browser=True,desktop=False):
    existing=owned_process(settings)
    if existing:
        if desktop:
            print(json.dumps({"url":f"http://127.0.0.1:{existing['port']}/", "already_running":True}))
            return
        print(f"Cerebra is already running at http://127.0.0.1:{existing['port']}. Browser session is required; stop and restart if it was lost.")
        if open_browser: webbrowser.open(f"http://127.0.0.1:{existing['port']}")
        return
    with socket.socket() as probe:
        try: probe.bind(("127.0.0.1",settings.port))
        except OSError as exc: raise RuntimeError(f"Port {settings.port} is occupied; Cerebra will not reuse an unrelated server") from exc
    key=secrets.token_urlsafe(32)
    env=os.environ.copy();env["AIHQ_BOOTSTRAP_KEY"]=key;env["AIHQ_DATA_DIR"]=str(settings.data_dir)
    log_path=settings.data_dir/"server.log"
    with log_path.open("ab") as log:
        child=subprocess.Popen([sys.executable,"-m","ai_hq.manage","serve","--port",str(settings.port)],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    identity=process_identity(child.pid);identity["port"]=settings.port
    temp=settings.data_dir/"server.json.tmp";temp.write_text(json.dumps(identity));temp.replace(settings.data_dir/"server.json")
    from urllib.request import urlopen
    # Time-based: a cold start on a busy laptop can take far longer than a fixed number of polls.
    deadline=time.monotonic()+STARTUP_TIMEOUT
    while time.monotonic()<deadline:
        if child.poll() is not None: raise RuntimeError(f"Server exited. Inspect {log_path}")
        try:
            with urlopen(f"http://127.0.0.1:{settings.port}/health",timeout=0.4) as response:
                if json.load(response).get("application")=="AI Development HQ": break
        except OSError: time.sleep(0.1)
    else: raise RuntimeError("Server did not become healthy; inspect server.log")
    if desktop:
        # Private redirected stdout to the native parent, never persisted or logged.
        print(json.dumps({"url":f"http://127.0.0.1:{settings.port}/#key={key}", "already_running":False}))
    else:
        if open_browser: webbrowser.open(f"http://127.0.0.1:{settings.port}/#key={key}")
        print(f"Cerebra running at http://127.0.0.1:{settings.port}. Launch key sent directly to your browser; it is not persisted or logged.")
    return f"http://127.0.0.1:{settings.port}/#key={key}"

def stop(settings):
    owned=owned_process(settings)
    if not owned:
        print("No matching Cerebra server is running.");return
    if os.name=="nt":
        # Recheck immediately before termination; PID plus creation time protects against PID reuse.
        if not owned_process(settings): return
        result=subprocess.run([str(Path(os.environ["SYSTEMROOT"])/"System32"/"taskkill.exe"),"/PID",str(owned["pid"]),"/T","/F"],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and owned_process(settings):
            raise RuntimeError("Managed server could not be stopped: "+result.stderr)
    else:
        import signal
        os.kill(owned["pid"],signal.SIGTERM)
    (settings.data_dir/"server.json").unlink(missing_ok=True)
    print("Stopped the verified Cerebra process tree. Task files and history are preserved; interrupted tasks require resume.")

def serve(settings):
    # One backend process owns this data directory; release the lock on exit/crash.
    lock=(settings.data_dir/"server.lock").open("a+b")
    lock.seek(0);lock.write(b"0");lock.flush();lock.seek(0)
    if os.name=="nt":
        import msvcrt
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    key=os.environ.pop("AIHQ_BOOTSTRAP_KEY",None)
    if not key: raise RuntimeError("Use scripts/start.ps1 to create a private local browser session")
    from .api import create_app
    import uvicorn
    app=create_app(settings,bootstrap_key=key)
    uvicorn.run(app,host="127.0.0.1",port=settings.port,access_log=False,log_level="warning")

def status(settings):
    running = bool(owned_process(settings))
    active = 0
    if settings.db_path.is_file():
        from .db import Database
        from .models import Task
        from sqlalchemy import select, func
        db = Database(settings.db_path)
        with db.Session() as session:
            active = session.scalar(select(func.count()).select_from(Task).where(Task.state.in_(["RUNNING", "VERIFYING", "REVIEWING", "NEEDS_CHANGES"])))
        db.close()
    return {"running":running,"active_tasks":active,"url":f"http://127.0.0.1:{settings.port}"}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["start","stop","serve","doctor","status","enable-live","disable-live","accept-cli-confinement","revoke-cli-confinement"])
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--desktop",action="store_true",help="Return a private launch URL to the native parent; never open a browser")
    parser.add_argument("--acknowledge-provider-usage",action="store_true")
    parser.add_argument("--acknowledge-residual-read-risk",action="store_true")
    args=parser.parse_args();settings=Settings(port=args.port)
    if args.command in {"accept-cli-confinement","revoke-cli-confinement"}:
        accepted=args.command=="accept-cli-confinement"
        if accepted and not args.acknowledge_residual_read_risk: parser.error("Explicit --acknowledge-residual-read-risk is required. CLI confinement is not an OS sandbox: Claude is limited to read-only review tools, but Codex can still read files outside the repository.")
        if owned_process(settings): raise RuntimeError("Stop Cerebra before changing the sandbox policy")
        from .db import Database
        from .models import Metadata
        value={"mode":"cli-confinement","residual_read_risk_acknowledged":True,"accepted_at":time.strftime("%Y-%m-%dT%H:%M:%S%z")} if accepted else {"mode":"none"}
        db=Database(settings.db_path);db.init()
        with db.Session.begin() as session:
            record=session.get(Metadata,"sandbox_policy")
            if record: record.value=value
            else: session.add(Metadata(key="sandbox_policy",value=value))
        db.close();print("CLI confinement accepted; live execution still requires enable-live and per-task approval." if accepted else "Sandbox policy revoked; live adapters fail closed.")
        return 0
    if args.command=="doctor":
        from .doctor import main as doctor
        return doctor()
    if args.command=="status":
        print(json.dumps(status(settings)))
        return 0
    if args.command in {"enable-live","disable-live"}:
        enabled=args.command=="enable-live"
        if enabled and not args.acknowledge_provider_usage: parser.error("Explicit --acknowledge-provider-usage is required. CLI execution may consume paid usage and access authenticated provider sessions. Per-task approval is also required.")
        if owned_process(settings): raise RuntimeError("Stop Cerebra before changing live execution policy")
        from .db import Database
        from .models import Metadata
        db=Database(settings.db_path);db.init()
        with db.Session.begin() as session:
            record=session.get(Metadata,"live_policy")
            if record: record.value={"enabled":enabled}
            else: session.add(Metadata(key="live_policy",value={"enabled":enabled}))
        db.close();print("Live policy enabled; each task still requires approval." if enabled else "Live execution disabled.")
    elif args.command=="serve": serve(settings)
    elif args.command=="start": start(settings,not args.no_browser and not args.desktop,desktop=args.desktop)
    elif args.command=="stop": stop(settings)
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError) as exc:
        print("Cerebra: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
