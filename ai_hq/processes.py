"""Bounded child processes with argument lists, redaction and tree cancellation.

The runner is a lifecycle boundary, not a filesystem sandbox. Live model adapters
must additionally enforce the recorded OS or explicitly accepted CLI confinement policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Sequence

from .security import canonical, redact


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    duration_seconds: float = 0.0


def scrub_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Do not inherit API tokens, Git overrides or arbitrary Python startup hooks."""
    permitted = {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "PROGRAMFILES",
        "PROGRAMFILES(X86)", "PROGRAMDATA", "LANG", "LC_ALL", "NUMBER_OF_PROCESSORS",
    }
    clean = {key: value for key, value in os.environ.items() if key.upper() in permitted}
    clean.update({"GIT_TERMINAL_PROMPT": "0",
                  "NO_COLOR": "1", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
                  "PYTHONDONTWRITEBYTECODE": "1"})
    for key, value in (extra or {}).items():
        if key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "NO_COLOR", "CI"}:
            raise ValueError("Only safe process-environment overrides are supported")
        clean[key] = str(value)
    return clean


class _WindowsJob:
    """Assign a suspended process before it can start untracked descendants."""
    def __init__(self, process: subprocess.Popen):
        from ctypes import wintypes

        class BasicLimit(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "Cannot create a process cleanup job")
        limits = ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError(ctypes.get_last_error(), "Cannot configure process cleanup job")
        if not self.api.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "Cannot securely assign process tree; execution refused")
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        if ntdll.NtResumeProcess(wintypes.HANDLE(int(process._handle))) != 0:
            self.close()
            raise OSError("Cannot resume managed child process")

    def terminate(self):
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class CommandNotFound(ValueError):
    """A bare command name (such as npm) is not installed or not on PATH."""


# npm-style Windows shims ("npm.cmd", "pnpm.cmd") only start Node.js with a JavaScript file next to them.
SHIM_SCRIPT = re.compile(r'"?%~?dp0%?\\?([^"%*]+?\.(?:c?js|mjs))"?', re.I)


def node_shim(path):
    """[node.exe, script] that an npm-style .cmd shim would run, or None when the shim isn't recognised.
    Running Node.js directly avoids cmd.exe, which would interpret &, |, ^ and % inside arguments."""
    shim = Path(path)
    try:
        text = shim.read_text(encoding="utf-8", errors="replace")[:20000]
    except OSError:
        return None
    scripts = [shim.parent / name for name in SHIM_SCRIPT.findall(text) if "prefix" not in Path(name).name.lower()]
    if shim.stem.lower() == "npm" and os.environ.get("APPDATA"):  # a globally updated npm takes precedence, as in npm.cmd
        scripts.insert(0, Path(os.environ["APPDATA"]) / "npm" / "node_modules" / "npm" / "bin" / "npm-cli.js")
    script = next((item for item in scripts if item.is_file()), None)
    node = shim.parent / "node.exe" if (shim.parent / "node.exe").is_file() else shutil.which("node")
    return [str(node), str(script)] if script and node else None


def resolve_command(args, cwd):
    """Turn a bare command name into the executable to start, with diagnostics when it can't be found.
    Explicit paths are left unchanged (and .cmd/.bat paths stay refused by ProcessRunner.run)."""
    name = args[0]
    if os.path.dirname(name):
        return list(args)
    found = shutil.which(name)
    if not found:
        folders = [folder for folder in os.environ.get("PATH", "").split(os.pathsep) if folder][:8]
        raise CommandNotFound(f"“{name}” isn't installed, or isn't on PATH, so Cerebra couldn't run “{' '.join(args)}” in {cwd}. "
                              f"Looked in: {'; '.join(folders) or 'no PATH folders'}{' and more' if len(os.environ.get('PATH', '').split(os.pathsep)) > 8 else ''}. "
                              "Install it from Required tools (npm, pnpm and yarn come with Node.js), then press Resume.")
    if os.name == "nt" and Path(found).suffix.lower() in {".cmd", ".bat"}:
        command = node_shim(found)
        if command is None:
            raise ValueError(f"“{name}” is a Windows batch wrapper ({found}). Cerebra doesn't run those through cmd.exe because "
                             "special characters in arguments could start other commands. Set the test command to the real program instead.")
        return [*command, *args[1:]]
    return [found, *args[1:]]


class ProcessRunner:
    def __init__(self, max_output_bytes: int = 262144, allowed_roots=None):
        if not 1024 <= max_output_bytes <= 16 * 1024 * 1024:
            raise ValueError("Output limit must be between 1 KiB and 16 MiB")
        self.max_output_bytes = max_output_bytes
        self.allowed_roots = allowed_roots

    def run(self, args: Sequence[str], cwd, timeout: float | None, cancel_event=None,
            input_text: str | None = None, env: dict[str, str] | None = None,
            redact_output: bool = True) -> ProcessResult:
        # redact_output=False is only for bounded machine-parsed output (Git/CLI protocol); the caller
        # must redact anything it persists, displays or raises.
        if isinstance(args, (str, bytes)) or not args or any(not isinstance(arg, str) or "\x00" in arg for arg in args):
            raise ValueError("Process arguments must be a nonempty list of NUL-free strings")
        # None means no time limit (the user chose "No limit"); cancellation still stops the process.
        if timeout is not None and not 0 < timeout <= 86400:
            raise ValueError("Process timeout must be positive and no longer than 24 hours")
        if Path(args[0]).suffix.lower() in {".cmd", ".bat", ".ps1"}:
            raise ValueError("Shell wrappers are not accepted; configure a native executable")
        try:
            directory = canonical(cwd, self.allowed_roots, must_exist=True) if self.allowed_roots is not None else Path(cwd).resolve(strict=True)
        except FileNotFoundError:
            raise ValueError(f"The working folder {cwd} doesn't exist (it may have been moved or deleted)") from None
        if not directory.is_dir():
            raise ValueError(f"The working folder {cwd} is not a folder")
        args = resolve_command(list(args), directory)
        payload = input_text.encode("utf-8") if input_text is not None else None
        if payload is not None and len(payload) > 1024 * 1024:
            raise ValueError("Process input exceeds the 1 MiB limit")
        if cancel_event is not None and cancel_event.is_set():
            return ProcessResult(-1, "", "Cancelled before process start", cancelled=True)

        started = time.monotonic()
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004 | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
        process = subprocess.Popen(list(args), cwd=directory, env=scrub_environment(env),
                                   stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                   creationflags=flags, start_new_session=(os.name != "nt"))
        job = None
        try:
            if os.name == "nt":
                try:
                    job = _WindowsJob(process)
                except Exception:
                    process.kill()
                    process.wait(timeout=5)
                    raise
            captured = [bytearray(), bytearray()]
            size = [0]
            truncated = [False]
            lock = threading.Lock()

            def drain(pipe, index):
                try:
                    while chunk := pipe.read(8192):
                        with lock:
                            keep = min(len(chunk), max(0, self.max_output_bytes - size[0]))
                            captured[index].extend(chunk[:keep])
                            size[0] += keep
                            truncated[0] |= keep < len(chunk)
                finally:
                    pipe.close()

            readers = [threading.Thread(target=drain, args=(process.stdout, 0), daemon=True),
                       threading.Thread(target=drain, args=(process.stderr, 1), daemon=True)]
            for reader in readers:
                reader.start()
            if payload is not None:
                def feed():
                    try:
                        process.stdin.write(payload)
                        process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        pass
                    finally:
                        process.stdin.close()
                threading.Thread(target=feed, daemon=True).start()
            timed_out = cancelled = False
            while process.poll() is None:
                cancelled = bool(cancel_event is not None and cancel_event.is_set())
                timed_out = timeout is not None and time.monotonic() - started >= timeout
                if cancelled or timed_out:
                    break
                time.sleep(0.025)
            # A command must not leave detached background children holding output pipes.
            if job:
                job.terminate() if cancelled or timed_out else None
                if not cancelled and not timed_out:
                    job.close()
            elif cancelled or timed_out:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for reader in readers:
                reader.join(timeout=5)
            if any(reader.is_alive() for reader in readers):
                raise RuntimeError("Managed process streams did not close after tree cleanup")
            outputs = []
            remaining = self.max_output_bytes
            for stream in captured:
                text = stream.decode("utf-8", errors="replace")
                safe = (redact(text) if redact_output else text).encode("utf-8")
                truncated[0] |= len(safe) > remaining
                bounded = safe[:remaining]
                outputs.append(bounded.decode("utf-8", errors="ignore"))
                remaining -= len(bounded)
            return ProcessResult(process.returncode, outputs[0], outputs[1], timed_out, cancelled,
                                 truncated[0], round(time.monotonic() - started, 3))
        finally:
            if job:
                job.close()
            elif os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
