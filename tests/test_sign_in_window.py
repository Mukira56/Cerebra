"""The window Cerebra opens for signing in and installing must be a real console, even when the app has none of its own."""
import os
import subprocess

import pytest

from ai_hq import integrations


@pytest.mark.skipif(os.name != "nt", reason="the console window is the Windows path")
def test_the_window_is_left_a_real_keyboard_and_screen(monkeypatch):
    opened = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **options: opened.append((args, options)))
    integrations.open_terminal(["gh", "auth", "login", "--web"], "Sign in to GitHub", cwd="C:/data")
    args, options = opened[0]
    assert options["creationflags"] == subprocess.CREATE_NEW_CONSOLE
    assert not {"stdin", "stdout", "stderr"} & set(options)  # redirecting any one of them breaks all three in the desktop app
    assert "auth" in args[-1] and "Read-Host" in args[-1]


def test_a_github_cli_installed_since_the_app_started_is_found(tmp_path, monkeypatch):
    place = tmp_path / "GitHub CLI" / "gh.exe"
    place.parent.mkdir()
    place.write_bytes(b"x")
    monkeypatch.setattr(integrations.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert integrations.which(["gh"]) == str(place)


def test_it_is_also_found_in_the_per_user_folder(tmp_path, monkeypatch):
    place = tmp_path / "Programs" / "GitHub CLI" / "gh.exe"
    place.parent.mkdir(parents=True)
    place.write_bytes(b"x")
    monkeypatch.setattr(integrations.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "empty"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert integrations.which(["gh"]) == str(place)


def test_the_path_still_comes_first_and_a_missing_tool_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(integrations.shutil, "which", lambda name: "C:/on/path/gh.exe")
    assert integrations.which(["gh"]) == "C:/on/path/gh.exe"
    monkeypatch.setattr(integrations.shutil, "which", lambda name: None)
    assert integrations.which(["gh"]) is None and integrations.which(["node"]) is None
