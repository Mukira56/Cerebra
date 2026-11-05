# Cerebra for Windows

Windows 10/11 x64. This installer includes its own Python 3.13 runtime and application dependencies. It does not require a separate Python, npm, or PowerShell setup command. Git is required for project work; Codex and Claude Code must be installed and signed in separately for live agents. No provider credentials or project data are included in the installer.

Run Cerebra-Setup-0.74.21-Windows-x64.exe. Setup installs only for your Windows account, without administrator elevation. The normal program location is %LOCALAPPDATA%\Programs\Cerebra. It adds a Start menu entry, an optional desktop shortcut, and a Windows Installed Apps uninstall entry.

Official releases include a public GitHub update destination in release-channel.json, with no account credentials. Distributors can set their channel with scripts/build_windows.py --update-repository owner/repository, or omit it for an edition with no update destination. CEREBRA_UPDATE_REPOSITORY overrides the packaged channel; an empty value disables checks.

Your project data stays outside the program directory, at %LOCALAPPDATA%\Cerebra\data on a fresh installation. Setup never searches development folders for an existing database. Verified upgrades retain the data directory recorded by that installation; an explicit --data path overrides it. For a separate installation use distinct --dir and --data paths.

New workspaces have no projects, job-search history, profile, linked accounts or credentials. The welcome form lets each customer enter their own profile, currency, skills and optional job sources. Profile sharing and all job sources start off. Scheduled jobs, bidding, automatic drafts, alerts, email follow-ups and live AI execution require explicit configuration. Provider sign-in takes place through the provider's own tools; Cerebra does not ask for account passwords.

This edition has no default update repository. A distributor can configure CEREBRA_UPDATE_REPOSITORY=owner/repository for its public GitHub release channel before launching. Without one, update checks do not contact GitHub; use the distributor's verified installer.

If the earlier source-based Cerebra is still running, stop it with its original scripts\stop.ps1 before opening the installed version. Setup never kills an active development task or migrates a database behind your back. Installation can complete while the old version is running, but the installed launcher must not take over a server from another Python runtime.

Open Cerebra from the Start menu or desktop. The app opens its own Windows desktop window with a taskbar icon, using an embedded WebView2 renderer and a private local backend. It does not open a tab in your browser. The local interface remains on 127.0.0.1; it is not exposed publicly. Right-click the tray icon for diagnostics, the data folder, restart, live-agent policy setup, or Stop Cerebra and exit. If the local session expires, use the tray menu to restart the workspace. Active tasks require confirmation before stopping and remain recoverable in their worktrees.

Fresh installations keep live execution disabled. The tray's Enable live agents action explains the usage and confinement policy and requires an explicit decision. It does not install coding CLIs or handle provider keys. Each task still requires its plan and live execution approvals, and merging has its own approval. Existing installations retain their recorded policy in the original data location.

Uninstall through Windows Settings > Apps > Installed apps, or the Start menu's Uninstall Cerebra entry. Exit the running tray app first. Uninstall removes only recorded program files and its own matching shortcuts/registration. It keeps project repositories, SQLite history, settings and logs. Unknown files added to the program directory are not removed. An update moves the previous program directory aside, then deletes only the files that copy's own install record lists. If you had added unknown files there, they stay in a clearly named .previous-* folder. Older .previous-* folders left by versions before 0.4.1 are cleaned the same way.

This installer is unsigned: Windows identifies its publisher as unknown. It is not a Microsoft Store package. Python and dependency license notices are included with the installed files. No Windows security setting, firewall rule, PATH entry, service, execution policy, or automatic-start task is changed by setup.

For diagnostics from a terminal, the native launcher also accepts --doctor, --status, --start-no-browser, and --stop. Its private runtime is at runtime\python.exe. Existing project-specific interpreters and test commands remain separate from the bundled application runtime.

Build source is under packaging/windows and scripts/build_windows.py. The builder uses the installed project environment, the existing Python runtime and the Windows .NET Framework C# compiler. It downloads and installs no build tools. The emitted .sha256 file records the exact installer digest.

The desktop window requires Microsoft Edge WebView2 Runtime, available separately from Microsoft if it is missing. Cerebra uses its own profile in the data directory and does not read your browser profile. External navigation, popups, downloads, browser shortcuts, host objects, and browser permissions are disabled. The installer includes the Microsoft WebView2 SDK assemblies and license; it does not silently install a machine-wide runtime.


## Git is installed first

Cerebra needs Git. Setup checks for it before installing Cerebra. It looks on PATH, in Git for Windows' recorded install folder (registry) and in its standard folders, and only counts a Git that answers `git --version`.

If Git is missing, Setup explains why and offers to install it:
- **Yes** installs Git for Windows for your account with Windows Package Manager (`winget install --id Git.Git --exact --source winget --scope user`) in a visible window. This needs an internet connection and accepts the Git package licence (GPL v2) and the winget source agreement. Windows may ask for permission.
- Afterwards Setup checks that Git runs. If it doesn't (no internet, permission refused, download failed, cancelled), Setup says so and lets you install Cerebra now or try again. Success is never reported without that check.
- If winget isn't available, Setup opens the official Git download page; press Install again once Git is installed.
- **No** installs Cerebra without Git. **Cancel** stops.

Cerebra itself opens without Git: the Required tools page shows Git as missing with an Install button, and project actions explain that Git is needed instead of failing. Git installed while Cerebra is running is found without restarting, because Cerebra re-reads the saved PATH and Git's standard folders.

Quiet installs (`--quiet`, used by in-app updates and tests) never install system software. Add `--install-git` to allow a quiet install to install Git first (silently, with the same verification).

`Cerebra-Setup-….exe --check-git` prints the Git and winget that Setup would use, as JSON (exit code 3 when Git is missing). Use it to diagnose a laptop where Git isn't found.

Not yet verified on a clean Windows installation without Git, without winget or without internet. Those paths are covered by code review and by tests that hide Git from Cerebra, not by a real fresh machine.
