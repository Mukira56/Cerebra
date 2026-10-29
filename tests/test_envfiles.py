"""Local settings files (.env…) reach a project's test runs, never the AI, and missing ones are named for the owner.
EstatePilot's sign-up returned 503 in every e2e run: the settings it needs were never in the task's working copy."""
import sys
from pathlib import Path

from ai_hq import envfiles
from ai_hq.models import Project
from fakes import FixtureRegistry
from test_supervisor import git, hq, ready  # noqa: F401  (hq is a fixture)


def write(root, files):
    for name, text in files.items():
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Path(root)


def test_settings_files_are_found_and_missing_ones_are_named(tmp_path):
    root = write(tmp_path / "p", {".env.example": "# comment\nDATABASE_URL=postgres://...\nexport BETTER_AUTH_SECRET=\n",
                                  "node_modules/x/.env": "A=1", "apps/web/.gitkeep": ""})
    assert envfiles.settings_files(root) == []
    missing = envfiles.missing(root)
    assert missing == {"example": ".env.example", "names": ["DATABASE_URL", "BETTER_AUTH_SECRET"], "target": ".env"}
    write(root, {"apps/web/.env.local": "DATABASE_URL=secret"})
    assert envfiles.settings_files(root) == ["apps/web/.env.local"] and envfiles.missing(root) is None
    assert envfiles.missing(write(tmp_path / "plain", {"README.md": ""})) is None


def test_lent_files_are_removed_and_existing_ones_left_alone(tmp_path):
    project = write(tmp_path / "project", {".env": "SECRET=1", "apps/web/.env.local": "B=2", "apps/web/page.ts": ""})
    copy = write(tmp_path / "copy", {".env": "SECRET=already here", "apps/web/page.ts": ""})
    with envfiles.lent(project, copy) as lent:
        assert lent == ["apps/web/.env.local"] and (copy / "apps/web/.env.local").read_text() == "B=2"
        assert (copy / ".env").read_text() == "SECRET=already here"
    assert not (copy / "apps/web/.env.local").exists() and (copy / ".env").exists()
    try:
        with envfiles.lent(project, write(tmp_path / "second", {"apps/web/page.ts": ""})):
            raise RuntimeError("tests crashed")
    except RuntimeError:
        pass
    assert not (tmp_path / "second" / ".env").exists()  # removed even when the run fails


class SeesSettings(FixtureRegistry):
    """Records whether the settings file was visible to each AI run."""
    def __init__(self):
        super().__init__()
        self.saw = []

    def execute(self, name, request, cancel_event=None):
        self.saw.append((request.role, (Path(request.workdir) / ".env").exists()))
        return super().execute(name, request, cancel_event)


def test_tests_get_the_settings_and_the_ai_never_sees_them(hq):
    supervisor, project_id, repo, db, _ = hq
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + ".env\n", encoding="utf-8")
    git(repo, "add", "."); git(repo, "commit", "-m", "Ignore settings")
    (repo / ".env").write_text("SECRET=owner-only\n", encoding="utf-8")
    needs_settings = "import pathlib, sys; sys.exit(0 if pathlib.Path('.env').read_text().startswith('SECRET=') else 1)"
    with db.Session.begin() as session:
        session.get(Project, project_id).test_commands = [[sys.executable, "-c", needs_settings], [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]
    supervisor.registry = SeesSettings()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL", task.results.get("error")
    assert supervisor.registry.saw and not any(seen for _, seen in supervisor.registry.saw)  # planner, coder, reviewer
    assert not (Path(task.worktree_path) / ".env").exists()


def needs_settings_project(hq):
    """A project whose tests fail without .env.local and that only ships .env.example (EstatePilot's case)."""
    supervisor, project_id, repo, db, _ = hq
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + ".env.local\n", encoding="utf-8")
    (repo / ".env.example").write_text("DATABASE_URL=\nBETTER_AUTH_SECRET=\n", encoding="utf-8")
    git(repo, "add", "."); git(repo, "commit", "-m", "Example settings")
    needs = "import pathlib, sys; sys.exit(0 if pathlib.Path('.env.local').exists() else 1)"
    with db.Session.begin() as session:
        session.get(Project, project_id).test_commands = [[sys.executable, "-c", needs], [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]
    supervisor.registry = SeesSettings()
    return supervisor, repo


def coder_runs(supervisor):
    return sum(1 for role, _ in supervisor.registry.saw if role == "implement")


def test_missing_settings_wait_for_the_owner_instead_of_repairs(hq):
    supervisor, repo = needs_settings_project(hq)
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "needs_settings", task.results.get("error")
    assert "DATABASE_URL" in task.results["error"] and coder_runs(supervisor) == 1 and task.retry_count == 0  # no repair spent
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "BLOCKED"  # still waiting while the file is missing
    (repo / ".env.local").write_text("DATABASE_URL=postgres://mine\n", encoding="utf-8")
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "AWAITING_APPROVAL", task.results.get("error")
    assert coder_runs(supervisor) == 1  # the saved work was tested again, not rewritten
    assert not any(seen for _, seen in supervisor.registry.saw)


def test_try_again_without_settings_repairs_as_usual(hq):
    supervisor, repo = needs_settings_project(hq)
    task_id = ready(hq)
    supervisor.run_until_idle()
    assert supervisor.get(task_id).results["blocked_reason"] == "needs_settings"
    supervisor.try_again(task_id)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.results.get("settings_override") and task.results.get("blocked_reason") != "needs_settings"
    assert coder_runs(supervisor) > 1  # failures went to the coder this time


def test_the_settings_file_goes_where_the_example_says_and_only_when_git_ignores_it(tmp_path):
    import pytest
    root = write(tmp_path / "estate", {".env.example": "# Copy to apps/web/.env.local; use synthetic data.\nDATABASE_URL=\n", "apps/web/page.ts": ""})
    git(root, "init", "-q")
    assert envfiles.missing(root)["target"] == "apps/web/.env.local"
    with pytest.raises(ValueError, match="doesn't ignore"):
        envfiles.create(root)  # secrets could be committed
    assert not (root / "apps/web/.env.local").exists()
    (root / ".gitignore").write_text(".env.*\n!.env.example\n", encoding="utf-8")
    assert envfiles.create(root) == "apps/web/.env.local"
    assert (root / "apps/web/.env.local").read_text(encoding="utf-8").endswith("DATABASE_URL=\n")
    assert envfiles.missing(root) is None
    with pytest.raises(ValueError):
        envfiles.create(root)  # never overwrites the owner's file
    plain = write(tmp_path / "plain", {"server/.env.sample": "TOKEN=\n", "notes": "copy to ../../.env.evil\n"})
    assert envfiles.missing(plain)["target"] == "server/.env"
    assert envfiles._target(".env.example", "# Copy to ../.env\n") == ".env"  # never outside the project
