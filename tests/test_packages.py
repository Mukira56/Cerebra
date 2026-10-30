"""A JavaScript project's packages are installed in the task's fresh working copy before its tests run.
The owner's portfolio task failed four times with "'vitest' is not recognized": node_modules is never in Git,
and a project-only coder can't install it."""
import json
import sys
from pathlib import Path

from ai_hq import packages
from ai_hq.models import Project
from ai_hq.processes import ProcessResult
from test_supervisor import git, hq, ready  # noqa: F401  (hq is a fixture)


def write(root, files):
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_the_install_command_follows_the_lockfile_and_the_test_tool(tmp_path):
    root = write(tmp_path, {"package.json": json.dumps({"scripts": {"test": "vitest run"}}), "package-lock.json": "{}"})
    plan = packages.plan(root, [["npm", "test"]])
    assert plan["prefix"] == ["npm"] and plan["steps"] == [["ci"], ["install", "--no-package-lock"]] and not plan["installed"]
    (root / "package-lock.json").unlink(); (root / "pnpm-lock.yaml").write_text("lockfileVersion: 9", encoding="utf-8")
    node, script = ((r"C:\cache\node\bin\node.exe", r"C:\cache\node\node_modules\pnpm\bin\pnpm.mjs") if sys.platform == "win32"
                    else ("/opt/cache/node/bin/node", "/opt/cache/node/lib/node_modules/pnpm/bin/pnpm.mjs"))
    plan = packages.plan(root, [[node, script, "check"]])
    assert plan["prefix"] == [node, script] and plan["steps"] == [["install", "--frozen-lockfile"], ["install", "--no-lockfile"]]
    (tmp_path / "yarn-project").mkdir()
    yarn = write(tmp_path / "yarn-project", {"package.json": "{}"})
    assert packages.plan(yarn, [["yarn", "test"]])["steps"][0] == ["install", "--no-lockfile"]
    assert packages.plan(tmp_path / "missing") is None


def test_installs_again_only_when_package_files_change(tmp_path):
    root = write(tmp_path, {"package.json": "{}"})
    first = packages.plan(root)
    (root / "node_modules").mkdir()
    assert packages.needed(first, None) and not packages.needed(packages.plan(root), first["fingerprint"])
    write(root, {"package.json": json.dumps({"devDependencies": {"vitest": "^5"}})})  # the coder added a package
    assert packages.needed(packages.plan(root), first["fingerprint"])


class FakeInstaller:
    """Records commands; package installs succeed (or fail) without touching the network; tests really run."""
    def __init__(self, inner, fail=False):
        self.inner, self.fail, self.calls = inner, fail, []

    def run(self, args, cwd, timeout=None, cancel_event=None, **kwargs):
        args = list(map(str, args))
        self.calls.append(args)
        if args[1:2] in (["ci"], ["install"]):
            if self.fail:
                return ProcessResult(1, "", "npm ERR! code ENOTFOUND\nnpm ERR! request to https://registry.npmjs.org/vitest failed")
            (Path(cwd) / "node_modules").mkdir(exist_ok=True)
            return ProcessResult(0, "added 42 packages in 3s", "")
        return self.inner.run(args, cwd, timeout, cancel_event, **kwargs)


def javascript_project(hq):
    supervisor, project_id, repo, db, _ = hq
    write(repo, {"package.json": json.dumps({"name": "site", "scripts": {"test": "vitest run"}}), "package-lock.json": "{}"})
    (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + "node_modules/\n", encoding="utf-8")
    git(repo, "add", "."); git(repo, "commit", "-m", "Add package.json")
    with db.Session.begin() as session:
        session.get(Project, project_id).test_commands = [[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]
    return supervisor


def test_packages_are_installed_once_before_the_tests_in_the_working_copy(hq):
    supervisor = javascript_project(hq)
    supervisor.runner = FakeInstaller(supervisor.runner)
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    installs = [call for call in supervisor.runner.calls if call[1:2] == ["ci"]]
    assert installs == [["npm", "ci"]] and task.state == "AWAITING_APPROVAL"  # once: baseline and verification share it
    first_test = next(index for index, call in enumerate(supervisor.runner.calls) if "pytest" in call)
    assert supervisor.runner.calls.index(["npm", "ci"]) < first_test
    from ai_hq.models import Event
    with hq[3].Session() as session:
        assert session.query(Event).filter(Event.task_id == task_id, Event.kind == "packages").count() == 1


def test_a_failed_install_is_reported_instead_of_running_the_tests(hq):
    supervisor = javascript_project(hq)
    supervisor.runner = FakeInstaller(supervisor.runner, fail=True)
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    failed = [result for result in task.test_results if result.get("install")]
    assert failed and "ENOTFOUND" in failed[0]["what_failed"] and "couldn't install" in failed[0]["stderr"]
    assert not any("pytest" in call for call in supervisor.runner.calls)  # no test run that could only fail
