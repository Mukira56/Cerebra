"""In-app updates from Cerebra's public GitHub releases, installed without leaving Cerebra by hand.

Check asks GitHub's public API for the newest release of the Cerebra repository: no GitHub account, sign-in or
token is needed, for anyone. Download fetches its Windows installer and checksum from the release's public
download links into the data folder and verifies them. Install writes a small plan and starts a detached helper that stops Cerebra
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
import threading
import time
from pathlib import Path

from . import __version__, desktop
from .config import ROOT
from .processes import ProcessRunner
from .security import redact

def release_repository():
    """Use an explicitly configured distributor channel, never personal runtime data."""
    repository = os.environ.get("CEREBRA_UPDATE_REPOSITORY")
    if repository is None:
        channel = ROOT / "release-channel.json"
        repository = json.loads(channel.read_text(encoding="utf-8"))["repository"] if channel.is_file() else ""
    if not isinstance(repository, str):
        raise ValueError("Update channel must be a public owner/repository name")
    repository = repository.strip()
    if repository and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Update channel must be a public owner/repository name")
    return repository


REPOSITORY = release_repository()
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
# Shows a small window with the real step being done (Cerebra itself is closed during these steps).
$ErrorActionPreference = 'Stop'
# Never work from inside the program folder: Windows can't replace a folder that a process is using.
Set-Location -LiteralPath $PSScriptRoot; [Environment]::CurrentDirectory = $PSScriptRoot
$plan = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'update-plan.json') | ConvertFrom-Json
$log = Join-Path $PSScriptRoot 'update.log'
function Write-Log($message) { Add-Content -LiteralPath $log -Value ("{0} {1}" -f (Get-Date -Format s), $message) -Encoding UTF8 }
$root = $plan.root.TrimEnd('\')
$window = $null; $failed = $false
if (-not $plan.quiet_ui) {
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    $window = New-Object System.Windows.Forms.Form
    $window.Text = "Updating Cerebra to $($plan.to)"; $window.Width = 460; $window.Height = 170; $window.StartPosition = 'CenterScreen'
    $window.FormBorderStyle = 'FixedDialog'; $window.MaximizeBox = $false; $window.MinimizeBox = $false; $window.TopMost = $true
    $label = New-Object System.Windows.Forms.Label; $label.SetBounds(20, 18, 410, 40); $label.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $bar = New-Object System.Windows.Forms.ProgressBar; $bar.SetBounds(20, 66, 405, 24); $bar.Maximum = 100
    $window.Controls.Add($label); $window.Controls.Add($bar); $window.Show()
}
function Step($percent, $text) {
    Write-Log "$percent% $text"
    if ($window) { $label.Text = $text; $bar.Value = $percent; [System.Windows.Forms.Application]::DoEvents() }
}
try {
    Step 5 "Step 1 of 4: closing Cerebra (running tasks are paused)…"
    Start-Sleep -Seconds 3
    Write-Log "Updating Cerebra $($plan.from) -> $($plan.to)"
    $env:AIHQ_DATA_DIR = $plan.data; Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Push-Location -LiteralPath $root
    try { & (Join-Path $root 'runtime\python.exe') -X utf8 -m ai_hq.manage stop --port $plan.port 2>&1 | ForEach-Object { Write-Log "$_" } } finally { Pop-Location }
    Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Step 25 "Step 2 of 4: checking the downloaded installer…"
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $plan.installer).Hash -ne $plan.sha256.ToUpper()) { throw 'The downloaded installer changed after it was verified; update cancelled.' }
    Step 40 "Step 3 of 4: installing Cerebra $($plan.to)… (about a minute)"
    $arguments = "--quiet --dir `"$root`" --data `"$($plan.data)`" --port $($plan.port)"
    if (-not $plan.desktop_shortcut) { $arguments += ' --no-desktop' }
    if ($plan.test_registration) { $arguments += ' --test-registration' }
    $out = Join-Path $PSScriptRoot 'installer-output.txt'; $err = Join-Path $PSScriptRoot 'installer-error.txt'
    $setup = Start-Process -FilePath $plan.installer -ArgumentList $arguments -PassThru -WindowStyle Hidden -WorkingDirectory $PSScriptRoot -RedirectStandardOutput $out -RedirectStandardError $err
    $null = $setup.Handle  # without reading Handle now, PowerShell reports no ExitCode for a redirected process
    while (-not $setup.HasExited) { if ($window) { [System.Windows.Forms.Application]::DoEvents() }; Start-Sleep -Milliseconds 200 }
    $setup.WaitForExit()
    $reason = ((Get-Content -Raw -LiteralPath $err -ErrorAction SilentlyContinue) + '').Trim()
    if ($setup.ExitCode -ne 0) { throw "The installer stopped (exit code $($setup.ExitCode)): $(if ($reason) { $reason } else { 'it gave no reason' }) The previous version is kept." }
    Write-Log "Installed $($plan.to)"
    Step 90 "Step 4 of 4: opening Cerebra $($plan.to)…"
} catch { $failed = $true; Write-Log "Update failed: $_"; if ($window) { $label.Text = "The update didn't finish: $_  Cerebra will reopen as before."; [System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Seconds 4 } }
finally {
    if ($plan.relaunch -ne $false) { Start-Process -FilePath (Join-Path $root 'AIHQ.exe'); Write-Log 'Cerebra reopened' } else { Write-Log 'Done' }
    if ($window) { if (-not $failed) { Step 100 "Done." }; Start-Sleep -Milliseconds 800; $window.Close() }
}
"""


DOWNLOAD_ATTEMPTS = 3
API = "https://api.github.com/repos/" + REPOSITORY
USER_AGENT = "Cerebra-updater"


CONNECT_TRIES = 3


def _ask(client, method, url, **options):
    """One request, tried again when the connection itself fails: some routes to GitHub drop about half of all new
    connections, and a connection that never opened can safely be tried again."""
    import httpx
    for attempt in range(CONNECT_TRIES):
        try:
            return client.request(method, url, **options)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if attempt == CONNECT_TRIES - 1:
                raise
            time.sleep(1 + attempt)


class PublicGitHub:
    """Reads Cerebra's releases from GitHub, with no sign-in. The public API allows 60 checks an hour per internet address, and
    an address can be shared with many other people, so when it says no, the same facts come from GitHub's ordinary web pages."""

    def release(self, tag=None):
        """The newest release (or the one with this tag) as {tagName, name, body, publishedAt, assets: [{name, size, url}]}, or None."""
        if not REPOSITORY:
            raise ValueError("No update channel is configured for this edition")
        import httpx
        path = f"/releases/tags/{tag}" if tag else "/releases/latest"
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}) as client:
                answer = _ask(client, "GET", API + path)
        except httpx.HTTPError:
            # GitHub's API and its ordinary pages are served from different addresses: when only the API can't be
            # reached (a blocked or unreliable route), the same facts still come from the release pages.
            try:
                return self._from_website(tag)
            except ValueError:
                raise ValueError("GitHub could not be reached. Check your internet connection and try again.") from None
        if answer.status_code == 404:
            return None
        if answer.status_code in {403, 429}:
            return self._from_website(tag)
        if answer.status_code != 200:
            raise ValueError(f"GitHub answered {answer.status_code}. Try again in a few minutes.")
        data = answer.json()
        if data.get("draft"):
            return None
        return {"tagName": data.get("tag_name", ""), "name": data.get("name") or "", "body": data.get("body") or "",
                "publishedAt": data.get("published_at"), "assets": [{"name": item.get("name", ""), "size": item.get("size", 0),
                                                                     "url": item.get("browser_download_url", "")} for item in data.get("assets") or []]}

    def _from_website(self, tag=None):
        """The release as GitHub's pages show it: the latest page redirects to its tag, and files sit at fixed addresses.
        It has no notes, and nothing is trusted more for it: the download is still checked against its checksum."""
        import httpx
        limited = ValueError("GitHub is limiting update checks from this internet connection for now. Try again in an hour.")
        site = f"https://github.com/{REPOSITORY}/releases"
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), headers={"User-Agent": USER_AGENT}) as client:
                if not tag:
                    latest = _ask(client, "GET", f"{site}/latest")
                    tag = str(latest.headers.get("location") or "").rsplit("/", 1)[-1] if latest.status_code in {301, 302, 303, 307, 308} else ""
                if not TAG.fullmatch(tag or ""):
                    raise limited
                name = f"Cerebra-Setup-{tag[1:]}-Windows-x64.exe"
                found = _ask(client, "HEAD", f"{site}/download/{tag}/{name}", follow_redirects=True)
        except httpx.HTTPError:
            raise limited from None
        if found.status_code == 404:
            return None
        if found.status_code != 200:
            raise limited
        return {"tagName": tag, "name": f"Cerebra {tag[1:]}", "body": "", "publishedAt": None,
                "assets": [{"name": name, "size": int(found.headers.get("content-length") or 0), "url": f"{site}/download/{tag}/{name}"},
                           {"name": f"{name}.sha256", "size": 0, "url": f"{site}/download/{tag}/{name}.sha256"}]}


class Updater:
    def __init__(self, settings, runner=None, spawn=None):
        self.settings = settings
        self.runner = runner or ProcessRunner()
        self.github = PublicGitHub()
        self.spawn = spawn or self._spawn_detached
        self.stream = self._stream
        self.retry_wait = 5  # seconds before resuming a dropped download (longer each time)
        self.folder = settings.data_dir / "updates"
        self._lock = threading.Lock()
        self._progress = {"phase": "idle", "percent": 0, "bytes": 0, "total": 0, "message": "", "error": ""}
        # A download that finished before Cerebra restarted is still ready to install: say so straight away.
        try:
            pending = self._pending()
        except OSError:
            pending = None
        if pending and version_tuple(pending["tag"]) > version_tuple(__version__):
            self._progress = {"phase": "ready", "tag": pending["tag"], "percent": 100, "bytes": 0, "total": 0, "error": "",
                              "message": f"Cerebra {pending['tag'][1:]} is downloaded and verified. Press Install and restart when you're ready."}

    def check(self):
        current = __version__
        base = {"current": current, "repository": REPOSITORY, "installed": installed_root() is not None, "last_log": self.last_log()}
        pending = self._pending()
        if desktop.platform() == "windows" and pending and TAG.fullmatch(pending.get("tag", "")) and version_tuple(pending["tag"]) > version_tuple(current):
            tag = pending["tag"]
            return {**base, "available": True, "downloaded": True, "latest": tag[1:], "tag": tag,
                    "installer": Path(pending["installer"]).name, "notes": "",
                    "message": f"Cerebra {tag[1:]} is downloaded and verified. Install and restart when you're ready."}
        if not REPOSITORY:
            return {**base, "available": False, "message": "No update channel is configured for this edition. Use an installer supplied by your distributor."}
        release = self.github.release()
        if release is None:
            return {**base, "available": False, "message": "No releases have been published yet."}
        tag = release.get("tagName", "")
        if not TAG.match(tag):
            return {**base, "available": False, "message": f"The newest release tag ({tag}) is not a Cerebra version."}
        assets = [asset.get("name", "") for asset in release.get("assets", [])]
        installer = next((name for name in assets if INSTALLER.match(name)), None)
        newer = version_tuple(tag) > version_tuple(current)
        if desktop.platform() != "windows":  # macOS and Linux run Cerebra from its folder: an update is a pull and a fresh setup, done by the owner
            return {**base, "available": False, "newer": newer, "latest": tag[1:], "tag": tag, "title": release.get("name") or tag,
                    "notes": redact(release.get("body") or "")[:6000], "published_at": release.get("publishedAt"), "installer": None, "downloaded": False,
                    "message": (f"Cerebra {tag[1:]} is available. To update, stop Cerebra and run in its folder: git pull && ./scripts/setup.sh && ./scripts/start.sh"
                                if newer else "You have the latest version.")}
        available = newer and installer is not None and f"{installer}.sha256" in assets
        message = (f"Cerebra {tag[1:]} is available." if available else "You have the latest version." if not newer
                   else f"Release {tag} has no Windows installer and checksum attached.")
        return {**base, "available": available, "latest": tag[1:], "tag": tag, "title": release.get("name") or tag, "notes": redact(release.get("body") or "")[:6000],
                "published_at": release.get("publishedAt"), "installer": installer, "message": message,
                "downloaded": self._pending(tag) is not None}

    # ---- download with real progress ------------------------------------------------------------
    def progress(self):
        with self._lock:
            return dict(self._progress)

    def _set(self, **values):
        with self._lock:
            self._progress.update(values)
            total, done = self._progress.get("total") or 0, self._progress.get("bytes") or 0
            if self._progress["phase"] == "downloading" and total:
                self._progress["percent"] = min(99, int(done * 100 / total))

    def start_download(self, tag):
        """Download in the background; progress() reports real bytes received out of the installer's size."""
        if desktop.platform() != "windows":
            raise ValueError("Updates download as a Windows installer. On macOS and Linux, run: git pull && ./scripts/setup.sh")
        if not TAG.match(tag or ""):
            raise ValueError("Choose a release version to download")
        if version_tuple(tag) <= version_tuple(__version__):
            raise ValueError("That version is not newer than the one you have")
        with self._lock:
            if self._progress.get("phase") in {"starting", "downloading", "verifying"}:
                raise ValueError("A download is already in progress")
            self._progress = {"phase": "starting", "tag": tag, "bytes": 0, "total": 0, "percent": 0, "message": "Starting the download…", "error": ""}
        def work():
            try:
                result = self.download(tag)
                self._set(phase="ready", percent=100, message=result["message"])
            except Exception as exc:  # shown in the progress bar, never raised into the server
                self._set(phase="failed", error=redact(str(exc))[:400], message="The download didn't finish.")
        threading.Thread(target=work, name="cerebra-update-download", daemon=True).start()
        return self.progress()

    def _stream(self, url, path, on_bytes, expected_size=0):
        """Stream one release file from its public download link (no sign-in), reporting bytes as they arrive.
        GitHub redirects the link to its file server, which is followed; only github.com links are accepted."""
        import httpx
        if not str(url).startswith(f"https://github.com/{REPOSITORY}/releases/download/"):
            raise ValueError("That isn't a Cerebra release download")
        # Resume a partial download (slow or dropped connections) instead of starting over.
        received = path.stat().st_size if path.exists() and expected_size and path.stat().st_size < expected_size else 0
        try:
            with httpx.Client(timeout=httpx.Timeout(60, read=60), follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:  # a stall is retried by download()
                with client.stream("GET", url, headers={"Range": f"bytes={received}-"} if received else {}) as response:
                    if response.status_code == 200:
                        received = 0  # the server sent the whole file again
                    elif response.status_code != 206:
                        raise ValueError(f"The download link answered {response.status_code}")
                    on_bytes(received)
                    with path.open("ab" if received else "wb") as handle:
                        for chunk in response.iter_bytes(65536):
                            handle.write(chunk); received += len(chunk); on_bytes(received)
        except httpx.HTTPError:
            raise ValueError("The connection to GitHub dropped. Check your internet and try again.") from None
        return received

    def download(self, tag):
        if not TAG.match(tag or ""):
            raise ValueError("Choose a release version to download")
        if version_tuple(tag) <= version_tuple(__version__):
            raise ValueError("That version is not newer than the one you have")
        target = self.folder / tag
        target.mkdir(parents=True, exist_ok=True)
        release = self.github.release(tag)
        if release is None:
            raise ValueError(f"Release {tag} was not found")
        assets = {asset.get("name", ""): asset for asset in release.get("assets", [])}
        name = next((item for item in assets if INSTALLER.match(item) and item[14:].startswith(tag[1:] + "-")), None)
        if name is None or f"{name}.sha256" not in assets:
            raise ValueError("The release is missing its installer or checksum file")
        installer = target / name
        self._set(phase="downloading", total=int(assets[name].get("size") or 0), bytes=0, message=f"Downloading Cerebra {tag[1:]}…")
        installer.with_name(name + ".sha256").unlink(missing_ok=True)
        self.stream(assets[f"{name}.sha256"]["url"], installer.with_name(name + ".sha256"), lambda _: None)
        size = int(assets[name].get("size") or 0)
        if installer.exists() and installer.stat().st_size > size:
            installer.unlink()
        # A dropped or stalled connection (one owner's download got 0 bytes and gave up) resumes by itself from
        # where it stopped, a few times, before asking the owner to try again.
        for attempt in range(DOWNLOAD_ATTEMPTS):
            try:
                self.stream(assets[name]["url"], installer, lambda done: self._set(bytes=done), size)
            except ValueError as exc:
                if "dropped" not in str(exc) or attempt == DOWNLOAD_ATTEMPTS - 1:
                    raise
            if not size or (installer.exists() and installer.stat().st_size == size):
                break
            if attempt < DOWNLOAD_ATTEMPTS - 1:
                self._set(message=f"The connection dropped; resuming the download (try {attempt + 2} of {DOWNLOAD_ATTEMPTS})…")
                time.sleep(self.retry_wait * (attempt + 1))
        if size and installer.stat().st_size != size:
            raise ValueError("The download stopped early. Press Download again to continue from where it stopped, "
                             "or install the copy in your Downloads folder if you have one.")
        self._set(phase="verifying", percent=99, message="Checking the download against its published checksum…")
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
        # Start in the updates folder, never the server's working folder (the program folder): a process using the
        # program folder as its working folder stops the installer from replacing it.
        subprocess.Popen(["cmd.exe", "/d", "/c", "start", "", "/min", str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)],
                         cwd=str(Path(script).parent), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

    def last_log(self):
        try:
            lines = (self.folder / "update.log").read_text(encoding="utf-8-sig").strip().splitlines()
        except OSError:
            return []
        return lines[-6:]
