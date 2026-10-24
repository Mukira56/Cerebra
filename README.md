# AI HQ — Development Command Center

A Windows desktop command center where real AI coding agents build software with you, under your control.

- **Real agents, your accounts.** OpenAI Codex and Anthropic Claude Code plan, write and review code using your own ChatGPT/Claude sign-in. There are no API keys to paste and no demo mode.
- **A supervisor, not a chatbot.** A deterministic Python supervisor gives each task to a planner, a coder and an *independent* reviewer from a different provider. It runs your project's real tests itself and repairs failures up to three times.
- **You approve every step.** The plan, letting agents run, and merging the result each need your yes. Code is written in an isolated Git worktree; your project changes only when you approve the merge.
- **See inside.** The *System view* is a live map of the backend: web server, supervisor, AI roles, working copy, test runner, approval gate, database and logs, lighting up as work flows through them.
- **Explained simply.** Every task gets a plain-language *Report* that anyone can read: what was asked, who did what, whether the tests passed, and where everything is saved.
- **Chat** with Codex or Claude about any project (read-only).
- **Models & sign-in**: sign in from the dashboard, choose models, and add more model profiles.
- **GitHub**: connect your account, clone repositories, publish and push.
- **Toolchain**: check and install Git, Node.js, Python, .NET, Java, Go, Rust, Docker, VS Code and the AI CLIs in one place.

Everything except AI inference runs on `127.0.0.1`. Data stays in a local SQLite database.

## Install (Windows 10/11 x64)

Run `AI-HQ-Setup-<version>-Windows-x64.exe`. Setup installs for your account only, without administrator rights. It bundles its own Python runtime, needs Microsoft Edge WebView2 (preinstalled on Windows 11), and opens AI HQ in its own window. See [docs/WINDOWS_INSTALLER.md](docs/WINDOWS_INSTALLER.md).

Then follow the *Get started* checklist on the Overview page, or read [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Run from source

```powershell
.\scripts\setup.ps1          # creates .venv from requirements.lock
.\scripts\start.ps1          # opens the dashboard with a private one-time session link
.\scripts\stop.ps1
```

Python 3.13+ and Git are required.

## Build the installer

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py --output dist
.\.venv\Scripts\python.exe scripts\test_windows_installer.py dist\AI-HQ-Setup-<version>-Windows-x64.exe --test-root <empty folder>
```

The builder uses the project's Python environment and the Windows .NET Framework C# compiler, and downloads nothing. The installer is unsigned until you add a code-signing certificate.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests never launch a real AI CLI. They use the fixture agent in `tests/fakes.py`. The dashboard has a headless Edge test in `scripts/test_dashboard.cjs`.

## Documentation

- [User guide](docs/USER_GUIDE.md): setup, tasks, chat, models, GitHub, and where results are saved
- [Security boundaries](docs/SECURITY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Windows installer](docs/WINDOWS_INSTALLER.md)
- [Development](docs/DEVELOPMENT.md)
- [Progress record](docs/progress.md)

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE).
