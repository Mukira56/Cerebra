"""Guess how a project is tested from the files at its top level, so users don't have to write commands by hand.

Read-only: it only lists the folder and reads small configuration files. The result is a suggestion the
user confirms in the Add project form; nothing runs here.
"""
from __future__ import annotations

import json
from pathlib import Path

PRESETS = [
    ("pytest", "Python: pytest", ["python", "-m", "pytest", "-q"]),
    ("unittest", "Python: unittest", ["python", "-m", "unittest", "-q"]),
    ("npm", "Node.js: npm test", ["npm", "test"]),
    ("pnpm", "Node.js: pnpm test", ["pnpm", "test"]),
    ("yarn", "Node.js: yarn test", ["yarn", "test"]),
    ("dotnet", ".NET: dotnet test", ["dotnet", "test"]),
    ("go", "Go: go test ./...", ["go", "test", "./..."]),
    ("cargo", "Rust: cargo test", ["cargo", "test"]),
    ("maven", "Java: mvn test", ["mvn", "test"]),
    ("gradle", "Java/Kotlin: gradle test", ["gradle", "test"]),
    ("flutter", "Flutter: flutter test", ["flutter", "test"]),
    ("laravel", "PHP Laravel: php artisan test", ["php", "artisan", "test"]),
]
BY_KEY = {key: command for key, _, command in PRESETS}


def _read(path, limit=200_000):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit] if path.is_file() and path.stat().st_size <= limit else ""
    except OSError:
        return ""


def detect(folder):
    """Return {"key", "label", "test_commands", "reason"}; key "none" when nothing recognisable was found."""
    root = Path(folder)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Choose an existing folder")
    try:
        names = {entry.name.lower() for entry in root.iterdir()}
    except OSError as exc:
        raise ValueError(f"Cerebra can't read that folder: {exc.strerror or exc}") from None

    def found(key, reason):
        label = next(label for item, label, _ in PRESETS if item == key)
        return {"key": key, "label": label, "test_commands": [BY_KEY[key]], "reason": reason}

    if "package.json" in names:
        try:
            script = (json.loads(_read(root / "package.json") or "{}").get("scripts") or {}).get("test", "")
        except ValueError:
            script = ""
        if script and "no test specified" not in script:
            manager = "pnpm" if "pnpm-lock.yaml" in names else "yarn" if "yarn.lock" in names else "npm"
            return found(manager, f"package.json has a test script ({script[:60]})")
    if "artisan" in names and "composer.json" in names:
        return found("laravel", "Laravel project (artisan)")
    if "pubspec.yaml" in names:
        return found("flutter", "Flutter/Dart project (pubspec.yaml)")
    if "cargo.toml" in names:
        return found("cargo", "Rust project (Cargo.toml)")
    if "go.mod" in names:
        return found("go", "Go module (go.mod)")
    if any(name.endswith((".sln", ".csproj", ".fsproj")) for name in names):
        return found("dotnet", ".NET solution or project file")
    if "pom.xml" in names:
        return found("maven", "Maven project (pom.xml)")
    if names & {"build.gradle", "build.gradle.kts"}:
        return found("gradle", "Gradle project")
    python = names & {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pytest.ini", "tox.ini"}
    tests = [path for path in [root, root / "tests", root / "test"] if path.is_dir()]
    has_tests = any(child.name.startswith("test") and child.suffix == ".py" for folder_ in tests for child in folder_.iterdir() if child.is_file())
    if python or has_tests:
        mentions_pytest = "pytest" in (_read(root / "pyproject.toml") + _read(root / "requirements.txt") + _read(root / "setup.cfg")).lower() or "pytest.ini" in names
        if mentions_pytest or not has_tests:
            return found("pytest", "Python project" + (" using pytest" if mentions_pytest else ""))
        return found("unittest", "Python tests found (test_*.py)")
    return {"key": "none", "label": "Not detected", "test_commands": [], "reason": "No known project type found. Choose how it is tested, or add tests later."}


PICK_SCRIPT = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$owner = New-Object System.Windows.Forms.Form -Property @{TopMost=$true; ShowInTaskbar=$false; WindowState='Minimized'}; "
    "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; $dialog.Description = 'Choose your project folder'; $dialog.ShowNewFolderButton = $true; "
    "if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($dialog.SelectedPath) }"
)


def pick_folder():
    """Open Windows' own folder picker on this computer and return the chosen folder ("" if cancelled)."""
    import os
    import subprocess
    if os.name != "nt":
        raise ValueError("The folder picker is only available in the Windows app; type the folder instead")
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    result = subprocess.run([str(powershell), "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", PICK_SCRIPT],
                            capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout.strip()
