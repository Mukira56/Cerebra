"""Running test commands on Windows: bare names resolve, npm-style .cmd shims run through node.exe without cmd.exe,
missing tools and folders explain themselves, and a project with no test target reports it instead of crashing."""
import os
import shutil
import sys

import pytest

from ai_hq.processes import CommandNotFound, ProcessRunner, node_shim, resolve_command
from test_product_api import KEY, client, enable_agents  # noqa: F401  (fixture)


def test_missing_command_names_itself_the_folder_and_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    with pytest.raises(CommandNotFound) as error:
        ProcessRunner().run(["npm", "test"], tmp_path, 30)
    message = str(error.value)
    assert "“npm”" in message and str(tmp_path) in message and str(tmp_path / "bin") in message and "Required tools" in message


def test_missing_working_folder_is_explained(tmp_path):
    with pytest.raises(ValueError, match="doesn't exist"):
        ProcessRunner().run([sys.executable, "-c", "print(1)"], tmp_path / "gone", 30)


@pytest.mark.skipif(os.name != "nt", reason="Windows .cmd shims")
@pytest.mark.parametrize("shim,script", [
    ('@ECHO OFF\nSET "NPM_PREFIX_JS=%~dp0\\node_modules\\npm\\bin\\npm-prefix.js"\nSET "NPM_CLI_JS=%~dp0\\node_modules\\npm\\bin\\npm-cli.js"\n"%NODE_EXE%" "%NPM_CLI_JS%" %*\n',
     "node_modules/npm/bin/npm-cli.js"),
    ('@SETLOCAL\n"%_prog%"  "%dp0%\\node_modules\\pnpm\\bin\\pnpm.cjs" %*\n', "node_modules/pnpm/bin/pnpm.cjs"),
])
def test_npm_style_shims_run_node_directly(tmp_path, monkeypatch, shim, script):
    monkeypatch.delenv("APPDATA", raising=False)
    folder = tmp_path / "Program Files" / "nodejs"
    (folder / script).parent.mkdir(parents=True)
    (folder / script).write_text("// cli", encoding="utf-8")
    (folder / "node.exe").write_bytes(b"")
    (folder / "tool.cmd").write_text(shim, encoding="utf-8")
    assert node_shim(folder / "tool.cmd") == [str(folder / "node.exe"), str(folder / script)]


@pytest.mark.skipif(os.name != "nt", reason="Windows .cmd shims")
def test_unrecognised_batch_wrappers_are_refused(tmp_path, monkeypatch):
    (tmp_path / "deploy.cmd").write_text("@echo off\ncall something.exe %*\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ValueError, match="batch wrapper"):
        resolve_command(["deploy"], tmp_path)
    with pytest.raises(ValueError, match="Shell wrappers"):
        ProcessRunner().run([str(tmp_path / "deploy.cmd")], tmp_path, 30)


@pytest.mark.skipif(os.name != "nt" or not shutil.which("npm"), reason="needs npm on Windows")
def test_real_npm_test_runs_with_spaces_and_special_characters_kept_literal(tmp_path):
    project = tmp_path / "my app & co"
    project.mkdir()
    (project / "package.json").write_text('{"scripts": {"test": "node -e \\"console.log(JSON.stringify(process.argv.slice(1)))\\" --"}}', encoding="utf-8")
    result = ProcessRunner().run(["npm", "test", "--", "a&echo INJECTED", "50%", "x|y"], project, 180)
    assert result.exit_code == 0, result.stderr
    assert '["a&echo INJECTED","50%","x|y"]' in result.stdout
    assert "INJECTED" not in result.stdout.replace("a&echo INJECTED", "")  # the & did not start a second command


def test_project_without_package_json_reports_no_test_target(client, tmp_path):
    enable_agents(client)
    empty = tmp_path / "MUKIRA"
    empty.mkdir()
    supervisor = client.app.state.supervisor
    import subprocess
    subprocess.run(["git", "init", "-q", str(empty)], check=True)
    subprocess.run(["git", "-C", str(empty), "-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "--allow-empty", "-m", "init"], check=True)  # like MUKIRA: one empty commit
    project = client.post("/api/projects", json={"name": "Empty", "path": str(empty), "authorize": True, "test_commands": [["npm", "test"]]}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "description": "Build a portfolio site"}).json()
    result = supervisor._run_test(task["id"], ["npm", "test"], str(empty))
    assert result["no_target"] and not result["passed"] and "No package.json" in result["stderr"]


def test_a_missing_test_tool_pauses_the_task_with_instructions(client, tmp_path):
    from test_product_api import calculator
    enable_agents(client)
    repo = calculator(tmp_path / "calc")
    project = client.post("/api/projects", json={"name": "Calc", "path": str(repo), "authorize": True, "test_commands": [["cerebra-missing-tool-xyz", "test"]]}).json()
    identifier = client.post("/api/tasks", json={"project_id": project["id"], "description": "Fix calculator addition"}).json()["id"]
    client.post(f"/api/tasks/{identifier}/approve-plan", json={})
    client.post(f"/api/tasks/{identifier}/start", json={})
    consent = next(row for row in client.get(f"/api/tasks/{identifier}").json()["approvals"] if row["kind"] == "live_execution")
    client.post(f"/api/approvals/{consent['id']}", json={"approve": True})
    client.post(f"/api/tasks/{identifier}/start", json={})
    client.app.state.supervisor.run_until_idle()
    detail = client.get(f"/api/tasks/{identifier}").json()
    assert detail["state"] == "BLOCKED" and "cerebra-missing-tool-xyz" in detail["results"]["error"] and "Resume" in detail["results"]["error"]
