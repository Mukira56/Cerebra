"""Find tools installed after Cerebra started, without asking the user to restart.

Windows gives each process a copy of PATH when it starts, so Git or Node.js installed afterwards (by Setup,
the Required tools page or by hand) is invisible until Cerebra restarts. ``refresh_path`` re-reads the saved
user and machine PATH from the registry and adds Git for Windows' standard folders, appending only folders
that exist and are missing. Child processes inherit the result through ``processes.scrub_environment``.
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

GIT_MISSING = ("Git isn't installed yet. Cerebra needs it to save every version of your projects. "
               "Open Required tools and press Install next to Git, or install it from git-scm.com, then try again.")
_lock = threading.Lock()


def _registry_path():
    """Folders on the user's and the machine's saved PATH (what a newly opened window would get)."""
    if os.name != "nt":
        return []
    import winreg
    folders = []
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(hive, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "Path")
        except OSError:
            continue
        folders += [os.path.expandvars(part.strip().strip('"')) for part in str(value).split(";") if part.strip()]
    return folders


def _git_folders():
    """Git for Windows' recorded install folder and its standard per-user and per-machine locations."""
    if os.name != "nt":
        return []
    import winreg
    roots = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\GitForWindows") as handle:
                roots.append(winreg.QueryValueEx(handle, "InstallPath")[0])
        except OSError:
            continue
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(str(Path(local) / "Programs" / "Git"))
    roots += [str(Path(os.environ[name]) / "Git") for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)") if os.environ.get(name)]
    return [str(Path(root) / "cmd") for root in roots if root]


def refresh_path():
    """Append missing, existing tool folders to this process's PATH. Returns the folders added."""
    with _lock:
        current = os.environ.get("PATH", "")
        known = {os.path.normcase(os.path.normpath(part)) for part in current.split(os.pathsep) if part}
        candidates = _registry_path() + ([] if shutil.which("git") else _git_folders())
        added = []
        for folder in candidates:
            key = os.path.normcase(os.path.normpath(folder))
            if key in known or not os.path.isdir(folder):
                continue
            known.add(key)
            added.append(folder)
        if added:
            os.environ["PATH"] = os.pathsep.join([part for part in [current, *added] if part])
        return added


def find_git():
    """Path to git.exe, looking beyond this process's PATH when needed; None when Git isn't installed."""
    found = shutil.which("git")
    if not found:
        refresh_path()
        found = shutil.which("git")
    return found
