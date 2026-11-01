# Installation and startup

Cerebra uses a project-local Python environment. It does not require administrator privileges, npm, Docker, a cloud account, or a local language model.

## Requirements

- Windows with PowerShell, Python 3.13+, and Git available on PATH.
- Enough free disk for the Python environment, SQLite data, repositories, and Git worktrees. The initial inspection found less than 1 GB free on `C:`; inspect current capacity before expanding usage.
- Claude Code and Codex are required to run tasks and chat. Install them from **Toolchain** and sign in from **Models & sign-in**.

## Install project packages

```powershell
Set-Location 'C:\Users\ADMIN\AI-Development-HQ'
.\scripts\setup.ps1
.\scripts\doctor.ps1
.\.venv\Scripts\python.exe -m pytest -q
```

Setup creates `.venv`, installs the local package with development dependencies using `pip install --no-cache-dir -e '.[dev]'` and `--constraint requirements.lock` when the lock file is present, and runs doctor. It installs no external CLIs and does not alter PowerShell execution policy.

If your organization blocks PowerShell scripts, do not change its policy automatically. The equivalent Python commands are:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --constraint requirements.lock -e '.[dev]'
.\.venv\Scripts\python.exe -m ai_hq.manage doctor
.\.venv\Scripts\python.exe -m ai_hq.manage start
```

## Launch, stop, and relaunch

```powershell
.\scripts\start.ps1
# Optional alternate loopback port:
.\scripts\start.ps1 -Port 8766
.\scripts\stop.ps1
```

The backend runs as a hidden child process in your current Windows user session. A browser opens with a one-time session key in the URL fragment; the UI exchanges it for a local HttpOnly SameSite cookie, removes the fragment, and uses CSRF tokens for mutations. The key is not written to a log or file. Keep the resulting browser session private. The ordinary loopback URL requires that cookie.

The server checks its own health before reporting successful startup. If an unrelated process occupies the selected port, startup refuses to reuse it. The stop command verifies executable identity and creation time as well as PID. Never substitute broad `taskkill /IM python.exe` commands.

If the browser session expires or cookies are lost, use stop followed by start. Restarted active tasks are preserved as interrupted work and require deliberate resume. Pause marks a task blocked and requests managed process cancellation; cancellation records a terminal cancelled task. Both preserve its files and history.

## Data location and portability

By default, all mutable application data lives under `data` in the application root. To select another authorized local data directory before startup:

```powershell
$env:AIHQ_DATA_DIR = 'D:\AIHQ-Data'
.\scripts\start.ps1
```

Use the same environment variable when running doctor and stop. Choose an actual available drive. Changing the directory selects a different database; it does not migrate old data. The example `.env` and YAML files document values but are not automatically loaded.

For backup, stop Cerebra first, then copy the application and its complete data directory to a safe location. Preserve registered repositories and their `.git` worktree metadata together. Moving active worktrees to a different absolute path requires Git worktree repair; do not assume a copied database updates repository paths.

## Missing agents

Doctor reports absent agents as warnings; tasks cannot run until they are installed and signed in. Run doctor for the current installed versions. Do not install external software or start provider login without explicit user approval. Node.js/npm are not required by this dashboard itself.

To configure an already installed CLI, enter its executable path in **Settings**, save, and run doctor again. Doctor probes versions and supported help output without extracting provider credentials. Paths do not enable live mode. The dashboard distinguishes capabilities, effective execution policy, and authentication; a detected executable is not a successful live run.

Live execution requires separate live/confinement policies and task approval. The user has selected CLI confinement, acknowledging that reads outside the repository remain possible. This policy is not verified OS isolation. Provider installation/authentication alone does not establish execution readiness. Do not run a live smoke test as part of routine setup. See the policy commands and validation requirements in `DEVELOPMENT.md`.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Virtual environment missing | Run setup inside the application root. |
| No local session | Stop/start and use the browser opened by start. |
| Port already occupied | Choose `-Port 8766` or inspect the owning application; never kill an unidentified process. |
| Doctor reports low disk | Free space through your normal reviewed process, or choose an authorized data drive. Cerebra performs no cleanup. |
| Repository registration rejected | Supply an exact absolute Git root; avoid linked/junction paths, drive roots, and your profile root. |
| No verification commands | Register the project with reviewed command argument arrays. No commands means no verified completion. |
| Agent unavailable | Install it from Toolchain, press Sign in on Models & sign-in, then Re-check tools. |
| Server fails to launch | Inspect `data\server.log` and run doctor. Do not paste credentials from unrelated logs. |
| Start/stop identity mismatch | Do not force termination. Inspect the recorded and running process identity before acting. |
