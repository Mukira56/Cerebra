"""Opening files, terminals and the folder chooser on macOS and Linux, simulated: the commands are checked, never run."""
import shlex
import subprocess

import pytest

from ai_hq import desktop

EVIL = "C:/odd dir/it's $HOME; rm -rf ~ & \"quoted\""


def commands(line):
    """The shell line as bash reads it: a list of commands, each a list of words."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    found, current = [], []
    for token in lexer:
        if token in {";", "&&"}:
            found.append(current); current = []
        else:
            current.append(token)
    return found + [current]


def on(monkeypatch, where):
    monkeypatch.setattr(desktop, "platform", lambda: where)
    started = []
    monkeypatch.setattr(desktop, "_detached", started.append)
    return started


def test_files_open_with_the_system_app_and_the_path_is_one_argument(monkeypatch):
    started = on(monkeypatch, "mac")
    desktop.open_path(EVIL)
    desktop.edit_text(EVIL)
    assert started[0][0] == "/usr/bin/open" and started[0][-1].endswith("rm -rf ~ & \"quoted\"") and started[1][:2] == ["/usr/bin/open", "-t"]
    started = on(monkeypatch, "linux")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None)
    desktop.open_path("/home/me/page.html")
    assert started == [["/usr/bin/xdg-open", "/home/me/page.html"]]
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="xdg-utils"):
        desktop.open_path("/home/me/page.html")


def test_a_linux_terminal_runs_exactly_the_command_with_every_argument_inert(monkeypatch):
    on(monkeypatch, "linux")
    command = desktop.terminal_command(["/usr/bin/gh", "auth", "login", EVIL], "Sign in", cwd="/home/me/my project",
                                       which=lambda name: "/usr/bin/gnome-terminal" if name == "gnome-terminal" else None)
    assert command[:4] == ["/usr/bin/gnome-terminal", "--", "bash", "-c"]
    steps = commands(command[4])
    assert steps[1] == ["cd", "/home/me/my project"] and steps[2] == ["/usr/bin/gh", "auth", "login", EVIL]
    assert "Press Enter to close" in command[4]
    assert desktop.terminal_command(["gh"], "x", which=lambda name: None) is None
    with pytest.raises(ValueError, match="Run this yourself in a terminal: gh auth"):
        monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
        desktop.open_terminal_elsewhere(["gh", "auth"], "x")


def test_macos_opens_terminal_app_with_the_line_escaped_for_applescript(monkeypatch):
    on(monkeypatch, "mac")
    command = desktop.terminal_command(["gh", "auth", "login", 'say "hi" \\ there'], "Sign in")
    assert command[:2] == ["/usr/bin/osascript", "-e"] and 'tell application "Terminal"' in command[2]
    inner = command[2].split('do script "', 1)[1].rsplit('"\nend tell', 1)[0]
    line = inner.replace('\\"', '"').replace("\\\\", "\\")
    assert shlex.split(line.split("; ")[1]) == ["gh", "auth", "login", 'say "hi" \\ there'] and "Press Enter" not in line


def test_the_folder_chooser_uses_the_system_dialog_and_cancel_means_nothing_chosen(monkeypatch):
    on(monkeypatch, "linux")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: "/usr/bin/zenity" if name == "zenity" else None)
    answer = lambda code, out: (lambda command, **kwargs: subprocess.CompletedProcess(command, code, out, ""))  # noqa: E731
    assert desktop.pick_folder_elsewhere(answer(0, "/home/me/work/\n")) == "/home/me/work"
    assert desktop.pick_folder_elsewhere(answer(1, "")) == ""
    on(monkeypatch, "mac")
    assert "choose folder" in desktop.folder_picker_command()[2]
    on(monkeypatch, "linux")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="Type the folder instead"):
        desktop.pick_folder_elsewhere()
