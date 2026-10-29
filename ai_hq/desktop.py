"""Opening things on the owner's own computer, on Windows, macOS and Linux: a file or folder in its usual app, a text
file in an editor, and a visible terminal window running one fixed command (sign-ins such as `gh auth login`).

Every command is a fixed program with the path or arguments passed as separate arguments; only the terminal needs a
shell line, and there each argument is quoted for that shell, so spaces, quotes, `;`, `$` and `&` stay inert.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

LINUX_TERMINALS = (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]), ("xfce4-terminal", ["-x"]),
                   ("kitty", []), ("alacritty", ["-e"]), ("xterm", ["-e"]))


def platform():
    return "windows" if os.name == "nt" else "mac" if sys.platform == "darwin" else "linux"


def _detached(command):
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)  # noqa: S603


def _opener():
    found = shutil.which("xdg-open")
    if not found:
        raise ValueError("Opening files needs xdg-open (the xdg-utils package) on Linux. Open the file yourself: it is saved on your computer.")
    return found


def open_path(path):
    """A file or folder in the app the system uses for it (a browser for a page, the file manager for a folder)."""
    target = os.fspath(path)
    where = platform()
    if where == "windows":
        os.startfile(target)  # noqa: S606 - a local path Cerebra chose or wrote
    elif where == "mac":
        _detached(["/usr/bin/open", target])
    else:
        _detached([_opener(), target])


def edit_text(path):
    """A text file (such as a project's .env settings) in a plain editor."""
    target = os.fspath(path)
    where = platform()
    if where == "windows":
        subprocess.Popen(["notepad.exe", target])  # noqa: S603,S607
    elif where == "mac":
        _detached(["/usr/bin/open", "-t", target])  # the default text editor (TextEdit unless changed)
    else:
        _detached([_opener(), target])


def _shell_line(args, title, cwd, keep_open):
    shown = " ".join(shlex.quote(str(arg)) for arg in [Path(str(args[0])).name, *args[1:]])
    line = f"printf '%s\\n' {shlex.quote('Cerebra opened this window to run: ' + shown)}; "
    if cwd:
        line += f"cd {shlex.quote(str(cwd))} && "
    line += " ".join(shlex.quote(str(arg)) for arg in args)
    if keep_open:
        line += "; echo; echo 'Finished. You can close this window and return to Cerebra.'"
        if platform() != "mac":  # a Terminal.app window stays open by itself; elsewhere the window closes with the command
            line += "; read -r -p 'Press Enter to close ' _"
    return line


def terminal_command(args, title, cwd=None, keep_open=True, which=None):
    """The command that opens a visible terminal on macOS or Linux running `args`; None when Linux has no terminal."""
    which, line = which or shutil.which, _shell_line(args, title, cwd, keep_open)
    if platform() == "mac":
        script = 'tell application "Terminal"\nactivate\ndo script "' + line.replace("\\", "\\\\").replace('"', '\\"') + '"\nend tell'
        return ["/usr/bin/osascript", "-e", script]
    for name, flag in LINUX_TERMINALS:
        found = which(name)
        if found:
            return [found, *flag, "bash", "-c", line]
    return None


def open_terminal_elsewhere(args, title, cwd=None, keep_open=True):
    command = terminal_command(args, title, cwd, keep_open)
    if not command:
        raise ValueError("No terminal app was found (such as GNOME Terminal, Konsole or xterm). Run this yourself in a terminal: "
                         + " ".join(shlex.quote(str(arg)) for arg in args))
    _detached(command)


def folder_picker_command(which=None):
    """The system's own folder chooser on macOS or Linux; None when Linux has neither zenity nor kdialog."""
    which = which or shutil.which
    if platform() == "mac":
        return ["/usr/bin/osascript", "-e", 'POSIX path of (choose folder with prompt "Choose a folder for Cerebra")']
    if which("zenity"):
        return [which("zenity"), "--file-selection", "--directory", "--title=Choose a folder for Cerebra"]
    if which("kdialog"):
        return [which("kdialog"), "--getexistingdirectory", str(Path.home()), "--title", "Choose a folder for Cerebra"]
    return None


def pick_folder_elsewhere(run=subprocess.run):
    """The chosen folder, or "" when the owner cancels."""
    command = folder_picker_command()
    if not command:
        raise ValueError("No folder chooser was found (zenity or kdialog). Type the folder instead.")
    result = run(command, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    chosen = result.stdout.strip() if result.returncode == 0 else ""
    return chosen.rstrip("/") or ("/" if chosen else "")
