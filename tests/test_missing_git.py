"""A laptop without Git: Cerebra still opens and guides setup; Git installed later is found without a restart."""
import os

import pytest
from fastapi.testclient import TestClient

from ai_hq import toolpath
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.gitops import GitError, GitManager
from fakes import FixtureRegistry
from test_product_api import KEY


@pytest.fixture
def no_git(tmp_path, monkeypatch):
    """This process sees no Git anywhere: an empty PATH, nothing saved in the registry, no standard folders."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(toolpath, "_registry_path", lambda: [])
    folders = []
    monkeypatch.setattr(toolpath, "_git_folders", lambda: list(folders))
    return folders  # a test appends a folder here to "install" Git


def fake_git(folder):
    folder.mkdir(parents=True)
    executable = folder / ("git.exe" if os.name == "nt" else "git")
    executable.write_bytes(b"")  # only located, never run
    executable.chmod(0o755)  # macOS and Linux only find programs marked executable
    return executable


def test_cerebra_opens_and_explains_when_git_is_missing(tmp_path, no_git):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = FixtureRegistry()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        assert client.get("/api/overview").status_code == 200
        git = next(tool for tool in client.get("/api/tools").json() if tool["id"] == "git")
        assert git["installed"] is False and "winget" in git["install_command"]
        folder = tmp_path / "project"
        folder.mkdir()
        response = client.post("/api/projects", json={"name": "Shop", "path": str(folder), "authorize": True, "test_commands": []})
        assert response.status_code == 400 and "Required tools" in response.json()["detail"]


def test_git_manager_reports_missing_git_only_when_used(tmp_path, no_git):
    manager = GitManager(tmp_path / "data")
    with pytest.raises(GitError, match="Required tools"):
        manager.require()


def test_git_installed_after_start_is_found_without_restart(tmp_path, no_git):
    manager = GitManager(tmp_path / "data")
    assert manager.executable is None
    executable = fake_git(tmp_path / "Prögram Files" / "Git" / "cmd")  # spaces and non-ASCII
    no_git.append(str(executable.parent))
    assert os.path.samefile(manager.require(), executable)
    assert str(executable.parent) in os.environ["PATH"].split(os.pathsep)


def test_refresh_adds_saved_path_folders_once_and_skips_missing_ones(tmp_path, no_git, monkeypatch):
    tools = tmp_path / "node"
    tools.mkdir()
    monkeypatch.setattr(toolpath, "_registry_path", lambda: [str(tools), str(tmp_path / "gone"), str(tools)])
    assert toolpath.refresh_path() == [str(tools)]
    assert toolpath.refresh_path() == []
    assert os.environ["PATH"].split(os.pathsep).count(str(tools)) == 1


def test_git_already_on_path_is_used_and_standard_folders_are_not_added(tmp_path, no_git, monkeypatch):
    executable = fake_git(tmp_path / "on-path")
    monkeypatch.setenv("PATH", str(executable.parent))
    no_git.append(str(fake_git(tmp_path / "other" / "cmd").parent))
    assert os.path.samefile(toolpath.find_git(), executable)
    assert toolpath.refresh_path() == []
