"""Provider sign-in, engineering toolchain and GitHub integration.

Cerebra never reads, stores or forwards credentials. Sign-in opens each tool's own login flow in a
visible terminal window that the user completes; status checks only report what the tool prints
about itself, with secrets redacted. Installs run only on an explicit click, from a fixed command
list, in a visible window the user can watch and cancel.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from .processes import ProcessRunner
from .security import redact

# Providers Cerebra knows how to sign in to. Only "execution" providers can run task roles today.
PROVIDERS = {
    "codex": {"label": "OpenAI Codex", "vendor": "OpenAI", "execution": True, "command": "codex",
              "login": ["login"], "logout": ["logout"], "status": ["login", "status"],
              "models": [], "model_hint": "Any model your ChatGPT/OpenAI plan offers in Codex, for example the one shown by /model inside Codex. Leave blank for Codex's default.",
              "install": "codex-cli"},
    "claude": {"label": "Claude Code", "vendor": "Anthropic", "execution": True, "command": "claude",
               "login": ["auth", "login"], "logout": ["auth", "logout"], "status": ["auth", "status", "--json"],
               "models": ["sonnet", "opus", "haiku"], "model_hint": "Aliases always pick the newest model of that family. A full model name also works. Leave blank for Claude Code's default.",
               "install": "claude-code"},
    "copilot": {"label": "GitHub Copilot CLI", "vendor": "GitHub", "execution": False, "command": "copilot",
                "login": [], "logout": [], "status": [],
                "models": [], "model_hint": "Copilot can be installed and signed in here. Running it inside Cerebra tasks is not supported yet; its adapter has not been verified.",
                "install": "copilot-cli"},
    "gemini": {"label": "Gemini CLI", "vendor": "Google", "execution": False, "command": "gemini",
               "login": [], "logout": [], "status": [],
               "models": [], "model_hint": "Sign in with your Google account (choose Login with Google in its window). Gemini then researches, reads long documents and checks facts for Cerebra, read-only, within Google's free daily allowance. Coding tasks stay with Claude.",
               "install": "gemini-cli"},
    "qwen": {"label": "Qwen Code", "vendor": "Alibaba Qwen", "execution": False, "command": "qwen",
             "login": [], "logout": [], "status": [],
             "models": [], "model_hint": "Sign in with your Qwen account (choose Qwen OAuth in its window, or type /auth). Qwen then reasons, answers code questions and gives second checks for Cerebra, read-only, within Qwen's free daily allowance. Coding tasks stay with Claude.",
             "install": "qwen-code"},
}

# Engineering toolchain. The install command list is fixed here; nothing user-supplied is executed.
TOOLS = [
    {"id": "git", "label": "Git", "group": "Essentials", "commands": ["git"], "version": ["--version"], "install": ["winget", "install", "--id", "Git.Git", "-e"], "why": "Saves every version of your code. Cerebra needs it for every project."},
    {"id": "gh", "label": "GitHub CLI", "group": "Essentials", "commands": ["gh"], "version": ["--version"], "install": ["winget", "install", "--id", "GitHub.cli", "-e"], "why": "Connects Cerebra to your GitHub account: clone, publish and push repositories."},
    {"id": "node", "label": "Node.js LTS + npm", "group": "Languages", "commands": ["node"], "version": ["--version"], "install": ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e"], "why": "Runs JavaScript and web tooling. Needed to install the Codex, Copilot and Gemini CLIs."},
    {"id": "python", "label": "Python 3.13", "group": "Languages", "commands": ["python", "py"], "version": ["--version"], "install": ["winget", "install", "--id", "Python.Python.3.13", "-e"], "why": "Python projects and their tests (pytest)."},
    {"id": "dotnet", "label": ".NET SDK 8", "group": "Languages", "commands": ["dotnet"], "version": ["--version"], "install": ["winget", "install", "--id", "Microsoft.DotNet.SDK.8", "-e"], "why": "C#, ASP.NET and Windows apps."},
    {"id": "java", "label": "Java JDK 21 (Temurin)", "group": "Languages", "commands": ["java"], "version": ["-version"], "install": ["winget", "install", "--id", "EclipseAdoptium.Temurin.21.JDK", "-e"], "why": "Java, Kotlin and Android tooling."},
    {"id": "go", "label": "Go", "group": "Languages", "commands": ["go"], "version": ["version"], "install": ["winget", "install", "--id", "GoLang.Go", "-e"], "why": "Go services and command-line tools."},
    {"id": "rust", "label": "Rust (rustup + cargo)", "group": "Languages", "commands": ["cargo"], "version": ["--version"], "install": ["winget", "install", "--id", "Rustlang.Rustup", "-e"], "why": "Rust programs; also used by many native build tools."},
    {"id": "docker", "label": "Docker Desktop", "group": "Platforms", "commands": ["docker"], "version": ["--version"], "install": ["winget", "install", "--id", "Docker.DockerDesktop", "-e"], "why": "Runs databases and services in containers."},
    {"id": "vscode", "label": "Visual Studio Code", "group": "Editors", "commands": ["code"], "version": ["--version"], "install": ["winget", "install", "--id", "Microsoft.VisualStudioCode", "-e"], "why": "Open a task's files in an editor."},
    {"id": "codex-cli", "label": "OpenAI Codex CLI", "group": "AI coding agents", "commands": ["codex"], "version": ["--version"], "install": ["npm", "install", "-g", "@openai/codex"], "why": "The Codex coding agent. Needs Node.js."},
    {"id": "claude-code", "label": "Claude Code", "group": "AI coding agents", "commands": ["claude"], "version": ["--version"], "install": ["winget", "install", "--id", "Anthropic.ClaudeCode", "-e"], "why": "The Claude coding agent."},
    {"id": "copilot-cli", "label": "GitHub Copilot CLI", "group": "AI coding agents", "commands": ["copilot"], "version": ["--version"], "install": ["npm", "install", "-g", "@github/copilot"], "why": "GitHub's coding agent. Needs Node.js and a Copilot plan."},
    {"id": "gemini-cli", "label": "Gemini CLI", "group": "AI coding agents", "commands": ["gemini"], "version": ["--version"], "install": ["npm", "install", "-g", "@google/gemini-cli"], "why": "Google's Gemini, signed in with your Google account: research, long documents and checking for Cerebra. Needs Node.js."},
    {"id": "qwen-code", "label": "Qwen Code", "group": "AI coding agents", "commands": ["qwen"], "version": ["--version"], "install": ["npm", "install", "-g", "@qwen-code/qwen-code"], "why": "Alibaba's Qwen, signed in with a free Qwen account: reasoning, code questions and second checks for Cerebra. Needs Node.js."},
    {"id": "ollama", "label": "Ollama", "group": "AI coding agents", "commands": ["ollama"], "version": ["--version"], "install": ["winget", "install", "--id", "Ollama.Ollama", "-e"], "why": "Runs open models on this computer (optional log summaries)."},
]
TOOL_IDS = {tool["id"]: tool for tool in TOOLS}
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def installed_places(name):
    """Where a tool lands on Windows. A running app keeps the PATH it started with, so one installed since then isn't on it."""
    if name != "gh":
        return []
    return [Path(root) / "GitHub CLI" / "gh.exe" for root in (os.environ.get("ProgramFiles"), Path(os.environ.get("LOCALAPPDATA") or ".") / "Programs") if root]


def which(names):
    for name in names:
        found = shutil.which(name) or next((str(path) for path in installed_places(name) if path.is_file()), None)
        if found:
            return found
    return None


def open_terminal(args, title, cwd=None, keep_open=True):
    """Run a fixed command in a new, visible console window the user controls."""
    if os.name != "nt":
        from .desktop import open_terminal_elsewhere
        return open_terminal_elsewhere(args, title, cwd, keep_open)
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"  # PowerShell literal; @, $ and ; stay inert
    shown = subprocess.list2cmdline([Path(str(args[0])).name, *map(str, args[1:])])
    script = f"$Host.UI.RawUI.WindowTitle = {quote(title)}; Write-Host {quote('Cerebra opened this window to run: ' + shown)} -ForegroundColor Cyan; & {' '.join(quote(arg) for arg in args)}"
    if keep_open:
        script += "; Write-Host ''; Write-Host 'Finished. You can close this window and return to Cerebra.' -ForegroundColor Green; Read-Host 'Press Enter to close'"
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    # No redirection at all: the desktop app has no console of its own, so redirecting any one stream sends the window's output
    # to a dead pipe and cuts off its keyboard. The person would see a blank window and could do nothing in it.
    subprocess.Popen([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], cwd=cwd,
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


class Integrations:
    def __init__(self, settings, runner=None, terminal=open_terminal, executables=None):
        self.settings = settings
        self.runner = runner or ProcessRunner()
        self.terminal = terminal
        # Resolved provider executables, keyed by provider name (from the agent registry).
        self.executables = executables or (lambda name: None)
        self._tools_cache = (0.0, None)

    # ---- providers -------------------------------------------------------------------------
    def provider_executable(self, name):
        if name not in PROVIDERS:
            raise ValueError("Unknown provider")
        return self.executables(name) or which([PROVIDERS[name]["command"]])

    def sign_in(self, name):
        provider = PROVIDERS.get(name)
        if provider is None:
            raise ValueError("Unknown provider")
        executable = self.provider_executable(name)
        if not executable:
            raise ValueError(f"{provider['label']} is not installed. Install it from Toolchain first.")
        # Copilot and Gemini sign in from inside their own interactive session (/login).
        self.terminal([executable, *provider["login"]], f"Sign in to {provider['label']}", cwd=str(self.settings.data_dir))
        return {"opened": True, "message": f"A {provider['label']} sign-in window opened. Finish signing in there, then press Check sign-in."
                + ("" if provider["login"] else " Type /login in that window if it asks.")}

    def sign_out(self, name):
        """Run the tool's own logout command. It removes the tool's saved sign-in; Cerebra never had it."""
        provider = PROVIDERS.get(name)
        if provider is None:
            raise ValueError("Unknown provider")
        if not provider["logout"]:
            raise ValueError(f"{provider['label']} signs out from inside its own window (/logout).")
        executable = self.provider_executable(name)
        if not executable:
            raise ValueError(f"{provider['label']} is not installed.")
        result = self.runner.run([executable, *provider["logout"]], self.settings.data_dir, timeout=30)
        if result.exit_code:
            raise ValueError(f"{provider['label']} could not sign out: " + redact((result.stderr or result.stdout).strip())[:500])
        return self.sign_in_status(name)

    def sign_in_status(self, name):
        provider = PROVIDERS.get(name)
        if provider is None:
            raise ValueError("Unknown provider")
        executable = self.provider_executable(name)
        if not executable:
            return {"provider": name, "installed": False, "signed_in": False, "detail": "Not installed"}
        if not provider["status"]:
            return {"provider": name, "installed": True, "signed_in": None, "detail": "This tool has no sign-in status command. Open it to check."}
        result = self.runner.run([executable, *provider["status"]], self.settings.data_dir, timeout=30)
        text = (result.stdout + "\n" + result.stderr).strip()
        status = {"provider": name, "installed": True, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if name == "claude":
            try:
                parsed = json.loads(result.stdout)
                status.update(signed_in=parsed.get("loggedIn") is True, account=parsed.get("email"),
                              method=parsed.get("authMethod"), plan=parsed.get("subscriptionType"))
            except json.JSONDecodeError:
                status.update(signed_in=False)
        else:
            status["signed_in"] = result.exit_code == 0 and "not logged in" not in text.lower()
            first = next((line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith(("At ", "+", "CategoryInfo", "FullyQualified"))), "")
            status["method"] = first[:200]
        status["detail"] = "Signed in" if status.get("signed_in") else "Not signed in. Press Sign in."
        return {key: redact(value) if isinstance(value, str) else value for key, value in status.items()}

    def require_subscription(self, name):
        """Check the client's own status, never its stored credentials or tokens."""
        status = self.sign_in_status(name)
        method = str(status.get('method') or '').lower()
        subscription = (name == 'codex' and 'logged in using chatgpt' in method) or (
            name == 'claude' and method == 'claude.ai')
        if not status.get('signed_in') or not subscription:
            label = 'ChatGPT through Codex' if name == 'codex' else 'Claude through Claude Code'
            raise ValueError(f'Sign in to {label} with your subscription in Models & sign-in, or choose another model '
                             'under Prospects > Writing model. No API request or paid fallback was made.')
        return True

    # ---- toolchain -------------------------------------------------------------------------
    def tools(self, refresh=False):
        stamp, cached = self._tools_cache
        if cached is not None and not refresh and time.monotonic() - stamp < 300:
            return cached

        from .toolpath import refresh_path
        refresh_path()  # tools installed since Cerebra started are found without a restart

        def detect(tool):
            executable = which(tool["commands"])
            row = {key: tool[key] for key in ("id", "label", "group", "why")}
            row.update(installed=bool(executable), path=executable, version=None,
                       install_command=subprocess.list2cmdline(tool["install"]))
            if executable:
                try:
                    result = self.runner.run([executable, *tool["version"]], self.settings.data_dir, timeout=15)
                    output = (result.stdout or result.stderr).strip().splitlines()
                    if result.exit_code == 0:
                        row["version"] = redact(output[0])[:120] if output else None
                    else:
                        # Present but broken (for example the .NET host without an SDK): offer a reinstall.
                        row.update(installed=False, problem=redact(output[0])[:160] if output else f"exit code {result.exit_code}")
                except (OSError, ValueError, RuntimeError):
                    row["version"] = None
            return row

        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(detect, TOOLS))
        self._tools_cache = (time.monotonic(), rows)
        return rows

    def install(self, tool_id):
        tool = TOOL_IDS.get(tool_id)
        if tool is None:
            raise ValueError("Unknown tool")
        installer = which([tool["install"][0]])
        if not installer:
            needed = "Node.js (npm)" if tool["install"][0] == "npm" else "winget (App Installer from the Microsoft Store)"
            raise ValueError(f"Install {needed} first, then try again.")
        self.terminal([installer, *tool["install"][1:]], f"Install {tool['label']}", cwd=str(self.settings.data_dir))
        self._tools_cache = (0.0, None)
        return {"opened": True, "message": f"An install window for {tool['label']} opened. Follow it there; press Refresh here when it finishes. You may need to restart Cerebra for new tools to be found."}

    # ---- GitHub ----------------------------------------------------------------------------
    def _gh(self):
        gh = which(["gh"])
        if not gh:
            raise ValueError("GitHub CLI is not installed. Install it from Toolchain first.")
        return gh

    def github_status(self):
        gh = which(["gh"])
        if not gh:
            return {"installed": False, "signed_in": False, "detail": "GitHub CLI is not installed"}
        result = self.runner.run([gh, "auth", "status", "--hostname", "github.com"], self.settings.data_dir, timeout=30)
        text = result.stdout + "\n" + result.stderr
        account = re.search(r"account\s+([A-Za-z0-9-]+)", text)
        status = {"installed": True, "signed_in": result.exit_code == 0 and bool(account),
                  "account": account.group(1) if account else None}
        if status["signed_in"]:
            profile = self.runner.run([gh, "api", "user", "--jq", "{name: .name, url: .html_url, avatar: .avatar_url, public_repos: .public_repos}"], self.settings.data_dir, timeout=30)
            try:
                status.update(json.loads(profile.stdout))
            except json.JSONDecodeError:
                pass
        status["detail"] = f"Signed in as {status['account']}" if status["signed_in"] else "Not signed in to GitHub"
        return {key: redact(value) if isinstance(value, str) else value for key, value in status.items()}

    def github_sign_in(self):
        self.terminal([self._gh(), "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"], "Sign in to GitHub", cwd=str(self.settings.data_dir))
        return {"opened": True, "message": "A GitHub window opened. Copy the one-time code it shows and press Enter, then finish in your browser. This page updates by itself."}

    def github_sign_out(self):
        account = self.github_status().get("account")
        if not account:
            return self.github_status()
        result = self.runner.run([self._gh(), "auth", "logout", "--hostname", "github.com", "--user", account], self.settings.data_dir, timeout=30)
        if result.exit_code:
            raise ValueError("Could not sign out of GitHub: " + redact(result.stderr.strip())[:500])
        return self.github_status()

    def github_repositories(self):
        result = self.runner.run([self._gh(), "repo", "list", "--limit", "100", "--json", "nameWithOwner,description,visibility,url,updatedAt,primaryLanguage"],
                                 self.settings.data_dir, timeout=60)
        if result.exit_code:
            raise ValueError("Could not list repositories: " + redact(result.stderr.strip())[:500])
        repositories = json.loads(result.stdout or "[]")
        return [{"name": repo.get("nameWithOwner"), "description": redact(repo.get("description") or ""),
                 "visibility": repo.get("visibility"), "url": repo.get("url"), "updated_at": repo.get("updatedAt"),
                 "language": (repo.get("primaryLanguage") or {}).get("name")} for repo in repositories]

    def clone(self, repository, destination):
        if not REPOSITORY.fullmatch(repository or ""):
            raise ValueError("Use the form owner/repository")
        destination = Path(destination)
        if destination.exists():
            raise ValueError("A project folder with that name already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self.runner.run([self._gh(), "repo", "clone", repository, str(destination)], destination.parent, timeout=600)
        if result.exit_code:
            raise ValueError("Clone failed: " + redact(result.stderr.strip())[:800])
        return destination

    def create_repository(self, path, name, visibility):
        if not REPOSITORY_NAME.fullmatch(name or "") or visibility not in {"private", "public"}:
            raise ValueError("Choose a repository name (letters, digits, . _ -) and private or public")
        result = self.runner.run([self._gh(), "repo", "create", name, f"--{visibility}", "--source", str(path), "--remote", "origin", "--push"], path, timeout=600)
        if result.exit_code:
            raise ValueError("GitHub repository creation failed: " + redact(result.stderr.strip())[:800])
        return {"created": True, "output": redact(result.stdout.strip())[:800]}

    def push(self, path, branch):
        from .toolpath import GIT_MISSING, find_git
        git = find_git()
        if not git:
            raise ValueError(GIT_MISSING)
        remote = self.runner.run([git, "remote", "get-url", "origin"], path, timeout=30)
        if remote.exit_code:
            raise ValueError("This project has no GitHub remote yet. Use Publish to GitHub first.")
        result = self.runner.run([git, "push", "origin", branch], path, timeout=600)
        if result.exit_code:
            raise ValueError("Push failed: " + redact(result.stderr.strip())[:800])
        return {"pushed": True, "remote": redact(remote.stdout.strip()), "output": redact((result.stdout + result.stderr).strip())[:800]}
