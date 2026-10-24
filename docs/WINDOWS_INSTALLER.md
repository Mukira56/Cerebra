# AI Development HQ for Windows

Windows 10/11 x64. This personal build includes its own Python 3.13 runtime and application dependencies. It does not require a separate Python, npm, or PowerShell setup command. Git is required for project work; Codex and Claude Code must be installed and signed in separately for live agents. No provider credentials or project data are included in the installer.

Run AI-HQ-Setup-0.4.0-Windows-x64.exe. Setup installs only for your Windows account, without administrator elevation. The normal program location is %LOCALAPPDATA%\Programs\AI HQ. It adds a Start menu entry, an optional desktop shortcut, and a Windows Installed Apps uninstall entry.

Your project data stays outside the program directory. If this account already has AI HQ at %USERPROFILE%\AI-Development-HQ\data, setup selects that existing data location without copying, moving or deleting it. Keep that folder: registered repositories and Git worktrees can contain absolute paths. On a new account, data defaults to %LOCALAPPDATA%\AI HQ\data.

If the earlier source-based AI HQ is still running, stop it with its original scripts\stop.ps1 before opening the installed version. Setup never kills an active development task or migrates a database behind your back. Installation can complete while the old version is running, but the installed launcher must not take over a server from another Python runtime.

Open AI Development HQ from the Start menu or desktop. The app opens its own Windows desktop window with a taskbar icon, using an embedded WebView2 renderer and a private local backend. It does not open a tab in your browser. The local interface remains on 127.0.0.1; it is not exposed publicly. Right-click the tray icon for diagnostics, the data folder, restart, live-agent policy setup, or Stop AI HQ and exit. If the local session expires, use the tray menu to restart the workspace. Active tasks require confirmation before stopping and remain recoverable in their worktrees.

Fresh installations keep live execution disabled. The tray's Enable live agents action explains the usage and confinement policy and requires an explicit decision. It does not install coding CLIs or handle provider keys. Each task still requires its plan and live execution approvals, and merging has its own approval. Existing installations retain their recorded policy in the original data location.

Uninstall through Windows Settings > Apps > Installed apps, or the Start menu's Uninstall AI HQ entry. Exit the running tray app first. Uninstall removes only recorded program files and its own matching shortcuts/registration. It keeps project repositories, SQLite history, settings and logs. Unknown files added to the program directory are not removed. Updates preserve the previous program directory in a clearly named .previous-* folder rather than deleting unknown user additions.

This installer is unsigned: Windows identifies its publisher as unknown. It is a local personal build, not a Microsoft Store package. Python and dependency license notices are included with the installed files. No Windows security setting, firewall rule, PATH entry, service, execution policy, or automatic-start task is changed by setup.

For diagnostics from a terminal, the native launcher also accepts --doctor, --status, --start-no-browser, and --stop. Its private runtime is at runtime\python.exe. Existing project-specific interpreters and test commands remain separate from the bundled application runtime.

Build source is under packaging/windows and scripts/build_windows.py. The builder uses the installed project environment, the existing Python runtime and the Windows .NET Framework C# compiler. It downloads and installs no build tools. The emitted .sha256 file records the exact installer digest.

The desktop window requires Microsoft Edge WebView2 Runtime, which is already installed on this laptop. AI HQ uses its own profile in the data directory and does not read your browser profile. External navigation, popups, downloads, browser shortcuts, host objects, and browser permissions are disabled. The installer includes the Microsoft WebView2 SDK assemblies and license; it does not silently install a machine-wide runtime.
