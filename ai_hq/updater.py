"""In-app updates from the user's GitHub releases, installed without leaving Cerebra by hand.

Check asks GitHub (through the user's own signed-in GitHub CLI; Cerebra never handles a GitHub token) for
the newest release of the Cerebra repository. Download fetches its Windows installer and checksum into the
data folder and verifies them. Install writes a small plan and starts a detached helper that stops Cerebra
(running tasks are paused, as when closing normally), verifies the installer again, installs it silently
over the existing copy (data and shortcuts kept), and reopens Cerebra. Every step is logged.

Limits: the installer is unsigned, so the checksum proves the download is intact and matches the release,
not who built it. Only someone who can publish releases to the repository can ship an update.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import __version__
from .config import ROOT
from .processes import ProcessRunner
from .security import redact

REPOSITORY = "Mukira56/Cerebra"
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
INSTALLER = re.compile(r"^Cerebra-Setup-(\d+\.\d+\.\d+)-Windows-x64\.exe$")


def version_tuple(text):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text).strip())
    if not match:
        raise ValueError(f"Not a version: {text}")
    return tuple(int(part) for part in match.groups())


def installed_root():
    """The installation folder when running the installed app, else None (running from source)."""
    return ROOT if (ROOT / "desktop-settings.json").is_file() and (ROOT / "AIHQ.exe").is_file() and (ROOT / "runtime" / "python.exe").is_file() else None


HELPER = r"""# Cerebra update helper: stop Cerebra, install the verified update silently, reopen Cerebra.
$ErrorActionPreference = 'Stop'
$plan = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'update-plan.json') | ConvertFrom-Json
$log = Join-Path $PSScriptRoot 'update.log'
function Write-Log($message) { Add-Content -LiteralPath $log -Value ("{0} {1}" -f (Get-Date -Format s), $message) -Encoding UTF8 }
$root = $plan.root.TrimEnd('\')
try {
    Start-Sleep -Seconds 3
    Write-Log "Updating Cerebra $($plan.from) -> $($plan.to)"
    $env:AIHQ_DATA_DIR = $plan.data; Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Push-Location -LiteralPath $root
    try { & (Join-Path $root 'runtime\python.exe') -X utf8 -m ai_hq.manage stop --port $plan.port 2>&1 | ForEach-Object { Write-Log "$_" } } finally { Pop-Location }
    Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $plan.installer).Hash -ne $plan.sha256.ToUpper()) { throw 'The downloaded installer changed after it was verified; update cancelled.' }
    $arguments = "--quiet --dir `"$root`" --data `"$($plan.data)`" --port $($plan.port)"
    if (-not $plan.desktop_shortcut) { $arguments += ' --no-desktop' }
    if ($plan.test_registration) { $arguments += ' --test-registration' }
    $setup = Start-Process -FilePath $plan.installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) { throw "The installer reported exit code $($setup.ExitCode); the previous version is kept." }
    Write-Log "Installed $($plan.to)"
} catch { Write-Log "Update failed: $_" }
finally {
    if ($plan.relaunch -ne $false) { Start-Process -FilePath (Join-Path $root 'AIHQ.exe'); Write-Log 'Cerebra reopened' } else { Write-Log 'Done' }
}
"""


class Updater:
    def __init__(self, settings, runner=None, spawn=None):
        self.settings = settings
        self.runner = runner or ProcessRunner()
        self.spawn = spawn or self._spawn_detached
        self.folder = settings.data_dir / "updates"

    def _gh(self):
        gh = shutil.which("gh")
        if not gh:
            raise ValueError("Updates come from your GitHub releases. Install the GitHub CLI (Toolchain) and sign in on the GitHub page first.")
        return gh

    def _run(self, args, timeout=120):
        result = self.runner.run([self._gh(), *args], self.settings.data_dir, timeout=timeout)
        if result.exit_code:
            text = redact((result.stderr or result.stdout).strip())[:400]
            if "release not found" in text.lower():
                return None
            raise ValueError("GitHub could not be reached or you are not signed in: " + text)
        return result.stdout

    def check(self):
        output = self._run(["release", "view", "--repo", REPOSITORY, "--json", "tagName,name,body,publishedAt,assets,isDraft,isPrerelease"], timeout=60)
        current = __version__
        base = {"current": current, "repository": REPOSITORY, "installed": installed_root() is not None, "last_log": self.last_log()}
        if output is None:
            return {**base, "available": False, "message": "No releases have been published yet."}
        release = json.loads(output)
        tag = release.get("tagName", "")
        if not TAG.match(tag):
            return {**base, "available": False, "message": f"The newest release tag ({tag}) is not a Cerebra version."}
        assets = [asset.get("name", "") for asset in release.get("assets", [])]
        installer = next((name for name in assets if INSTALLER.match(name)), None)
        available = version_tuple(tag) > version_tuple(current) and installer is not None and f"{installer}.sha256" in assets
        message = (f"Cerebra {tag[1:]} is available." if available else "You have the latest version." if version_tuple(tag) <= version_tuple(current)
                   else f"Release {tag} has no Windows installer and checksum attached.")
        return {**base, "available": available, "latest": tag[1:], "tag": tag, "title": release.get("name") or tag, "notes": redact(release.get("body") or "")[:6000],
                "published_at": release.get("publishedAt"), "installer": installer, "message": message,
                "downloaded": self._pending(tag) is not None}

    def download(self, tag):
        if not TAG.match(tag or ""):
            raise ValueError("Choose a release version to download")
        if version_tuple(tag) <= version_tuple(__version__):
            raise ValueError("That version is not newer than the one you have")
        target = self.folder / tag
        target.mkdir(parents=True, exist_ok=True)
        if self._run(["release", "download", tag, "--repo", REPOSITORY, "--pattern", "Cerebra-Setup-*-Windows-x64.exe*", "--dir", str(target), "--clobber"], timeout=900) is None:
            raise ValueError(f"Release {tag} was not found")
        installer = next((path for path in target.iterdir() if INSTALLER.match(path.name) and path.name[14:].startswith(tag[1:] + "-")), None)
        if installer is None or not installer.with_name(installer.name + ".sha256").is_file():
            raise ValueError("The release is missing its installer or checksum file")
        expected = installer.with_name(installer.name + ".sha256").read_text(encoding="utf-8").split()[0].lower()
        actual = hashlib.sha256(installer.read_bytes()).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
            installer.unlink(missing_ok=True)
            raise ValueError("The downloaded installer does not match its published checksum, so it was deleted. Try again.")
        (self.folder / "pending.json").write_text(json.dumps({"tag": tag, "installer": str(installer), "sha256": actual}), encoding="utf-8")
        return {"downloaded": True, "tag": tag, "sha256": actual, "bytes": installer.stat().st_size,
                "message": f"Cerebra {tag[1:]} downloaded and verified. Press Install and restart when you're ready."}

    def _pending(self, tag=None):
        try:
            pending = json.loads((self.folder / "pending.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        installer = Path(pending.get("installer", ""))
        if (tag and pending.get("tag") != tag) or not installer.is_file() or self.folder.resolve() not in installer.resolve().parents:
            return None
        if hashlib.sha256(installer.read_bytes()).hexdigest() != pending.get("sha256"):
            return None
        return pending

    def install(self):
        root = installed_root()
        if root is None:
            raise ValueError("You are running Cerebra from source. Update it with git pull instead.")
        pending = self._pending()
        if pending is None:
            raise ValueError("Download and verify an update first")
        if version_tuple(pending["tag"]) <= version_tuple(__version__):
            raise ValueError("The downloaded update is not newer than this version")
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / "Cerebra.lnk"
        plan = {"from": __version__, "to": pending["tag"][1:], "installer": pending["installer"], "sha256": pending["sha256"], "root": str(root),
                "data": str(self.settings.data_dir), "port": self.settings.port, "desktop_shortcut": desktop.exists()}
        (self.folder / "update-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        script = self.folder / "apply-update.ps1"
        script.write_text(HELPER, encoding="utf-8-sig")
        self.spawn(script)
        return {"restarting": True, "message": f"Updating to Cerebra {plan['to']}. Cerebra will close, update and reopen in about a minute. Running tasks are paused and can be resumed."}

    @staticmethod
    def _spawn_detached(script):
        # Started through a short-lived cmd so the helper is not a child of the server: stopping the server's
        # process tree during the update must not stop the helper itself.
        powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        subprocess.Popen(["cmd.exe", "/d", "/c", "start", "", "/min", str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

    def last_log(self):
        try:
            lines = (self.folder / "update.log").read_text(encoding="utf-8-sig").strip().splitlines()
        except OSError:
            return []
        return lines[-6:]
