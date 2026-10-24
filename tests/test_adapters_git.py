from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import pytest

from ai_hq.agents import AgentRegistry, AgentRequest, ClaudeAdapter, CodexAdapter, final_text, valid_model
from ai_hq.gitops import GitError, GitManager
from ai_hq.processes import ProcessRunner, ProcessResult, scrub_environment
from fakes import FixtureAgent as MockAdapter

PYTHON = getattr(sys, "_base_executable", sys.executable)


def test_process_output_bounds_environment_and_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-to-never-inherit")
    runner = ProcessRunner(max_output_bytes=1024)
    result = runner.run([PYTHON, "-c", "import os; print(os.environ.get('OPENAI_API_KEY','scrubbed')); print('password=example-secret'); print('x'*5000)"], tmp_path, 10)
    assert result.exit_code == 0
    assert result.output_truncated
    assert "scrubbed" in result.stdout and "example-secret" not in result.stdout
    assert "[REDACTED]" in result.stdout
    assert len(result.stdout) < 1200
    assert "OPENAI_API_KEY" not in scrub_environment()


def test_process_stdin_and_argument_lists(tmp_path):
    result = ProcessRunner().run([PYTHON, "-c", "import sys; print(sys.stdin.read()); print(sys.argv[1])", "literal; & $(does-not-execute)"], tmp_path, 10, input_text="structured input")
    assert result.exit_code == 0
    assert "structured input" in result.stdout and "$(does-not-execute)" in result.stdout
    with pytest.raises(ValueError):
        ProcessRunner().run("python -c print(1)", tmp_path, 1)
    with pytest.raises(ValueError):
        ProcessRunner().run(["unsafe.cmd"], tmp_path, 1)
    with pytest.raises(ValueError, match="authorized"):
        ProcessRunner(allowed_roots=[]).run([PYTHON, "-c", "print(1)"], tmp_path, 1)


def test_process_timeout_and_cancel(tmp_path):
    runner = ProcessRunner()
    result = runner.run([PYTHON, "-c", "import time; time.sleep(30)"], tmp_path, .15)
    assert result.timed_out and result.exit_code != 0
    cancel = threading.Event()
    timer = threading.Timer(.2, cancel.set)
    timer.start()
    try:
        result = runner.run([PYTHON, "-c", "import time; time.sleep(30)"], tmp_path, 10, cancel)
    finally:
        timer.cancel()
    assert result.cancelled and result.exit_code != 0
    result = runner.run([PYTHON, "-c", "raise SystemExit('must not start')"], tmp_path, 10, cancel)
    assert result.cancelled


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_process_cleanup_kills_descendants(tmp_path, mode):
    child = "import os,time; from pathlib import Path; Path('child.pid').write_text(str(os.getpid())); time.sleep(30)"
    parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(30)"
    pidfile = tmp_path / "child.pid"
    cancel = threading.Event()
    def cancel_when_ready():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not pidfile.exists():
            time.sleep(.025)
        cancel.set()
    if mode == "cancel":
        monitor = threading.Thread(target=cancel_when_ready, daemon=True)
        monitor.start()
    result = ProcessRunner().run([PYTHON, "-c", parent], tmp_path, 15 if mode == "cancel" else 8, cancel)
    assert result.cancelled if mode == "cancel" else result.timed_out
    assert pidfile.exists(), "Child must start before its cleanup can be verified"
    pid = int(pidfile.read_text())
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                assert api.WaitForSingleObject(handle, 1000) == 0
            finally:
                api.CloseHandle(handle)
        else:
            assert ctypes.get_last_error() in {87, 1168}, "Cleanup verification must not accept access denial"
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            status = Path(f"/proc/{pid}/status")
            assert status.exists() and "Z (zombie)" in status.read_text()


@pytest.fixture
def repo(tmp_path):
    directory = tmp_path / "registered"
    directory.mkdir()
    def git(*args):
        return subprocess.run([shutil.which("git"), "-C", str(directory), *args], check=True, capture_output=True, text=True)
    git("init", "-b", "development")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@localhost")
    (directory / ".ai-hq-demo.json").write_text(json.dumps({"kind": "calculator-addition-v1"}))
    (directory / "calculator.py").write_text("def add(a, b):\n    return a - b\n")
    (directory / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    git("add", ".")
    git("commit", "-m", "Initial isolated fixture")
    return directory


def request(directory, **kwargs):
    values = dict(task_id="demo", role="implement", description="Fix calculator addition demo", requirements=[], acceptance_criteria=["add(2,3) == 5"], workdir=str(directory), allowed_paths=["calculator.py"])
    values.update(kwargs)
    return AgentRequest(**values)


def test_mock_implementation_independent_review_and_repair(repo):
    implementation = MockAdapter("mock-codex")
    reviewer = MockAdapter("mock-claude")
    req = request(repo, description="Fix calculator addition demo [demo:needs-repair]")
    first = implementation.execute(req)
    assert first.success and first.simulated
    review = reviewer.execute(replace(req, role="review"))
    assert review.success and review.simulated and review.findings
    assert review.findings[0]["evidence"].strip() == "return a + b + 1"
    before = (repo / "calculator.py").read_bytes()
    reviewer.execute(replace(req, role="review"))
    assert (repo / "calculator.py").read_bytes() == before
    assert implementation.execute(replace(req, attempt=1)).success
    assert reviewer.execute(replace(req, role="review")).findings == []


def test_mock_rejects_arbitrary_objectives_and_paths(repo):
    adapter = MockAdapter()
    assert not adapter.execute(request(repo, description="Build a complete booking website")).success
    assert not adapter.execute(request(repo, allowed_paths=["tests/"])).success
    assert not adapter.execute(request(repo, allowed_paths=["../personal"])).success
    (repo / ".ai-hq-demo.json").unlink()
    assert not adapter.execute(request(repo)).success


def test_live_adapter_is_disabled_without_running_model(repo):
    class NeverRun:
        def run(self, *args, **kwargs):
            raise AssertionError("No live process should start")
    result = CodexAdapter(NeverRun()).execute(request(repo))
    assert not result.success and "switched off" in result.error
    registry = AgentRegistry(runner=NeverRun())
    assert set(registry.adapters) == {"codex", "claude"}, "The product ships no simulated agents"
    with pytest.raises(ValueError):
        registry.get("mock-claude")
    assert not registry.chat("codex", "hello", str(repo)).success


def test_model_choice_reaches_cli_arguments(tmp_path):
    codex = CodexAdapter()._command("codex.exe", tmp_path, False, ["."], "gpt-test")
    assert codex[codex.index("-m") + 1] == "gpt-test" and codex.index("-m") > codex.index("exec")
    assert "-m" not in CodexAdapter()._command("codex.exe", tmp_path, False, ["."], "")
    claude = ClaudeAdapter()._command("claude.exe", tmp_path, True, ["."], "opus")
    assert claude[claude.index("--model") + 1] == "opus" and "Read,Grep,Glob" in claude
    for bad in ("gpt test", "x;rm", "--dangerous", "a" * 101):
        with pytest.raises(ValueError):
            valid_model(bad)


def test_final_text_reads_codex_and_claude_answers():
    codex = "\n".join(json.dumps(record) for record in [{"type": "item.completed", "item": {"type": "agent_message", "text": "First"}},
                                                         {"type": "item.completed", "item": {"type": "agent_message", "text": "Final answer"}},
                                                         {"type": "turn.completed"}])
    assert final_text(codex) == "Final answer"
    assert final_text(json.dumps({"type": "result", "subtype": "success", "result": "Claude says hi"})) == "Claude says hi"
    assert final_text("not json") == ""


def test_cli_probe_uses_only_version_and_help(repo):
    class FixtureRunner:
        def __init__(self):
            self.calls = []
        def run(self, args, cwd, timeout):
            self.calls.append(args)
            help_text = "--json --sandbox --ephemeral --ignore-user-config --ignore-rules --ask-for-approval --no-daemon"
            return ProcessResult(0, help_text if "--help" in args else "codex fixture-v1", "")
    runner = FixtureRunner()
    adapter = CodexAdapter(runner, sys.executable)
    info = adapter.probe(authenticate=True)
    assert info["available"] and info["authentication"] == "not_checked"
    assert not info["execution_allowed"]
    adapter.allow_live, adapter.confinement_mode = True, "cli-confinement"
    assert adapter.probe()["execution_allowed"]
    assert all(args[-1] in {"--version", "--help"} for args in runner.calls)


@pytest.mark.parametrize("output,expected", [
    ('{"findings": []}', True),
    ('{\n  "findings": []\n}', True),
    ('{"result": "{\\"findings\\": []}"}', True),
    ('{"item":{"type":"agent_message","text":"{\\"findings\\": []}"}}', True),
    ('{"message": "the string findings appears"}', False),
    ('{"findings": "[]"}', False),
    ('{"findings": ["garbage"]}', False),
    ('{"type":"turn.failed","error":"Rate limit"}', False),
])
def test_live_review_parsing_and_configurable_timeout_without_model_process(tmp_path, output, expected):
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            assert timeout == 17
            assert args[args.index("--sandbox") + 1] == "read-only"
            assert args[args.index("-a") + 1] == "never"
            if os.name == "nt":
                # Without this, --ignore-user-config leaves Codex with no Windows sandbox and every command is rejected.
                assert args[args.index("-c") + 1] == 'windows.sandbox="elevated"'
            assert redact_output is False
            return ProcessResult(0, json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": output}}) + '\n{"type":"turn.completed"}', "")
    registry = AgentRegistry(runner=FixtureRunner(), allow_live=True, timeout=17, scope_verified=True)
    adapter = registry.get("codex")
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    result = registry.execute("codex", request(tmp_path, role="review"))
    assert result.success is expected
    if not expected:
        assert result.output


def test_claude_implementation_uses_only_scoped_file_tools(tmp_path):
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            tools = args[args.index("--tools") + 1]
            assert tools == "Read,Grep,Glob,Edit,Write"
            assert "Bash" not in tools and "PowerShell" not in tools
            assert args[args.index("--permission-mode") + 1] == "dontAsk"
            allowed = args[args.index("--allowedTools") + 1:args.index("--no-session-persistence")]
            assert any(item.startswith("Edit(//") and item.endswith("/calculator.py)") for item in allowed)
            assert not any(item.startswith("Edit(") and item.endswith("/worktree/**)") for item in allowed)
            assert any(item.startswith("Edit(") and item.endswith("/.git)") for item in args[args.index("--disallowedTools") + 1:])
            return ProcessResult(0, '{"type":"result","subtype":"success","is_error":false,"result":"{\\"summary\\":\\"Updated permitted source\\"}"}', "")
    adapter = ClaudeAdapter(FixtureRunner(), allow_live=True, confinement_mode="cli-confinement")
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    result = adapter.execute(request(tmp_path))
    assert result.success


def test_codex_rejects_repository_startup_configuration(tmp_path):
    class NeverRun:
        def run(self, *args, **kwargs):
            raise AssertionError("Repository startup hooks must not run")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("# local hooks or MCP settings")
    adapter = CodexAdapter(NeverRun(), allow_live=True, scope_verified=True)
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    result = adapter.execute(request(tmp_path))
    assert not result.success and "repository-local" in result.error


@pytest.mark.parametrize("adapter_class", [ClaudeAdapter, CodexAdapter])
def test_live_adapter_refuses_without_verified_os_read_scope(tmp_path, adapter_class):
    class NeverRun:
        def run(self, *args, **kwargs):
            raise AssertionError("Approval alone must not launch an unconfined model")
    result = adapter_class(NeverRun(), allow_live=True).execute(request(tmp_path, role="review"))
    assert not result.success and "no verified OS sandbox" in result.error


def test_cli_confinement_is_distinct_from_verified_os_scope(tmp_path):
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            return ProcessResult(0, '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"findings\\":[]}"}}\n{"type":"turn.completed"}', "")
    registry = AgentRegistry(FixtureRunner(), allow_live=True, confinement_mode="cli-confinement")
    adapter = registry.get("codex")
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    assert not adapter.scope_verified
    assert registry.execute("codex", request(tmp_path, role="review")).success


@pytest.mark.parametrize("name,stdout,expected", [
    ("codex", '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"findings\\":[]}"}}', False),
    ("codex", '{"type":"turn.completed"}', False),
    ("claude", '{"type":"result","subtype":"success","is_error":false,"result":"{\\"findings\\":[]}"}', True),
    ("claude", '{"type":"result","subtype":"error_max_turns","result":"{\\"findings\\":[]}"}', False),
    ("claude", '{"type":"result","subtype":"success","permission_denials":[{"tool_name":"Read"}],"result":"{\\"findings\\":[]}"}', False),
])
def test_cli_genuine_terminal_events_required_for_review(tmp_path, name, stdout, expected):
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            assert redact_output is False
            if name == "claude":
                assert args[args.index("--tools") + 1] == "Read,Grep,Glob"
                assert "--safe-mode" in args and "--strict-mcp-config" in args
                assert args[args.index("--allowedTools") + 1].startswith("Read(//")
            return ProcessResult(0, stdout, "")
    registry = AgentRegistry(FixtureRunner(), allow_live=True, confinement_mode="cli-confinement")
    registry.get(name)._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    assert registry.execute(name, request(tmp_path, role="review")).success is expected


def test_cli_parses_raw_evidence_but_redacts_display_output(tmp_path):
    token = "sk-abcdefghijklmnopqrst"
    finding = {"severity": "high", "file": "calculator.py", "line": 1, "message": "Exposed secret", "evidence": 'password="' + token + '"'}
    text = json.dumps({"findings": [finding]})
    events = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}) + '\n{"type":"turn.completed"}'
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            return ProcessResult(0, events, "")
    adapter = CodexAdapter(FixtureRunner(), allow_live=True, confinement_mode="cli-confinement")
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    result = adapter.execute(request(tmp_path, role="review"))
    assert result.success and result.findings[0]["evidence"] == finding["evidence"]
    assert token not in result.output and "[REDACTED]" in result.output


def test_cli_rate_limit_stdout_is_reported_on_nonzero_exit(tmp_path):
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            return ProcessResult(1, '{"error":"429 rate_limit_error"}', "")
    adapter = CodexAdapter(FixtureRunner(), allow_live=True, confinement_mode="cli-confinement")
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    result = adapter.execute(request(tmp_path))
    assert not result.success and "rate_limited" in result.error


def test_claude_planner_refuses_denied_coverage_and_preserves_diagnostics(tmp_path):
    class FixtureRunner:
        def run(self, args, cwd, timeout, cancel_event, input_text, *, redact_output=True):
            return ProcessResult(0, '{"type":"result","subtype":"success","permission_denials":[{"tool_name":"Read"}],"result":"Architecture coverage was blocked"}', "")
    adapter = ClaudeAdapter(FixtureRunner(), allow_live=True, confinement_mode="cli-confinement")
    adapter._capability = {"available": True, "executable": "fixture-only-not-launched.exe"}
    result = adapter.execute(request(tmp_path, role="plan"))
    assert not result.success and "denied tool access" in result.error
    assert "Architecture coverage was blocked" in result.output


def test_worktree_isolation_commit_and_approval(repo, tmp_path):
    manager = GitManager(tmp_path / "managed")
    info = manager.inspect_repository(repo)
    assert info["default_branch"] == "development" and not info["dirty"]
    work = manager.create_worktree(repo, "task/demo")
    directory = Path(work["path"])
    assert MockAdapter().execute(request(directory)).success
    assert "return a - b" in (repo / "calculator.py").read_text()
    snapshot = manager.snapshot(directory)
    assert snapshot["changed_paths"] == ["calculator.py"] and "+    return a + b" in snapshot["diff"]
    commit = manager.commit(directory, "Fix addition", ["calculator.py"])
    assert commit["changed"] and len(commit["commit"]) == 40
    cumulative = manager.candidate_snapshot(directory, work["base_commit"])
    assert cumulative["head"] == commit["commit"] and cumulative["changed_paths"] == ["calculator.py"]
    assert not cumulative["status"]
    with pytest.raises(GitError, match="approval"):
        manager.integrate(repo, work["branch"], work["base_commit"])
    with pytest.raises(GitError, match="approved branch"):
        manager.integrate(repo, work["branch"], work["base_commit"], approved=True, expected_branch="wrong-target")
    with pytest.raises(GitError, match="candidate changed"):
        manager.integrate(repo, work["branch"], work["base_commit"], approved=True, expected_candidate=work["base_commit"])
    result = manager.integrate(repo, work["branch"], work["base_commit"], approved=True,
                               expected_branch=work["base_branch"], expected_candidate=commit["commit"])
    assert result["commit"] == commit["commit"]
    assert "return a + b" in (repo / "calculator.py").read_text()


def test_git_untracked_scope_and_dirty_repository_protection(repo, tmp_path):
    manager = GitManager(tmp_path / "managed")
    work = manager.create_worktree(repo, "scoped")
    directory = Path(work["path"])
    (directory / "extra.txt").write_text("new tracked artifact")
    assert manager.snapshot(directory)["untracked"] == ["extra.txt"]
    with pytest.raises(GitError, match="allowed paths"):
        manager.commit(directory, "Unauthorized extra file", ["calculator.py"])
    manager.commit(directory, "Approved extra file", ["extra.txt"])
    (repo / "personal-notes.txt").write_text("preserve user work")
    with pytest.raises(GitError, match="user changes"):
        manager.integrate(repo, work["branch"], work["base_commit"], approved=True)
    assert (repo / "personal-notes.txt").read_text() == "preserve user work"


def test_git_detects_divergence_and_disables_hooks(repo, tmp_path):
    manager = GitManager(tmp_path / "managed")
    work = manager.create_worktree(repo, "divergence")
    directory = Path(work["path"])
    (directory / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
    marker = tmp_path / "hook-executed"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho unsafe > '" + marker.as_posix() + "'\n")
    hook.chmod(0o755)
    manager.commit(directory, "Task change", ["calculator.py"])
    assert not marker.exists()
    (repo / "other.txt").write_text("independent user change")
    manager.commit(repo, "Concurrent baseline change", ["other.txt"])
    with pytest.raises(GitError, match="moved"):
        manager.integrate(repo, work["branch"], work["base_commit"], approved=True)
    with pytest.raises(GitError, match="diverged"):
        manager.integrate(repo, work["branch"], approved=True)


def test_git_rejects_changed_symlinks(repo, tmp_path):
    manager = GitManager(tmp_path / "managed")
    work = manager.create_worktree(repo, "symlink")
    directory = Path(work["path"])
    try:
        (directory / "escape.txt").symlink_to(tmp_path / "outside.txt")
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or permission")
    with pytest.raises((GitError, ValueError), match="symlink|authorized"):
        manager.snapshot(directory)


def test_git_preserves_ignored_user_files_on_integration(repo, tmp_path):
    manager = GitManager(tmp_path / "managed")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\nprivate-notes.txt\n")
    manager.commit(repo, "Fixture ignore policy", [".gitignore"])
    work = manager.create_worktree(repo, "ignored-path")
    directory = Path(work["path"])
    (directory / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (directory / "private-notes.txt").write_text("candidate content")
    manager.commit(directory, "New tracked file", [".gitignore", "private-notes.txt"])
    (repo / "private-notes.txt").write_text("existing ignored user data")
    with pytest.raises(GitError, match="ignored user path"):
        manager.integrate(repo, work["branch"], work["base_commit"], approved=True)
    assert (repo / "private-notes.txt").read_text() == "existing ignored user data"


def test_git_disables_configured_clean_filters(repo, tmp_path):
    manager = GitManager(tmp_path / "managed")
    marker = tmp_path / "filter-executed"
    (repo / ".gitattributes").write_text("calculator.py filter=unsafe\n")
    hook = "echo unsafe > '" + marker.as_posix() + "'; cat"
    manager._git(repo, "config", "filter.unsafe.clean", hook)
    manager._git(repo, "config", "filter.unsafe.required", "true")
    (repo / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
    manager.commit(repo, "Known fixture update", [".gitattributes", "calculator.py"])
    assert not marker.exists()


def test_codex_npm_shim_resolves_to_native_binary(tmp_path, monkeypatch):
    shim = tmp_path / "codex.cmd"
    shim.write_text("@echo off")
    native = tmp_path / "node_modules" / "@openai" / "codex" / "node_modules" / "@openai" / "codex-win32-x64" / "vendor" / "x86_64-pc-windows-msvc" / "bin" / "codex.exe"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"")
    monkeypatch.setattr("ai_hq.agents.shutil.which", lambda name: str(shim))
    assert CodexAdapter()._find() == str(native.resolve())
    assert not str(CodexAdapter(executable=str(shim))._find() or "").endswith(".cmd")


def test_git_parses_unredacted_output_but_redacts_errors(tmp_path):
    # A token-like path segment used to be redacted in `rev-parse` output, corrupting the parsed path.
    directory = tmp_path / "sk-abcdefghijklmnopqrst"
    directory.mkdir()
    def git(*args):
        return subprocess.run([shutil.which("git"), "-C", str(directory), *args], check=True, capture_output=True, text=True)
    git("init", "-b", "main")
    (directory / "f.txt").write_text("x")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@localhost", "commit", "-m", "init")
    manager = GitManager(tmp_path / "managed")
    assert Path(manager.inspect_repository(directory)["path"]) == directory.resolve()
    (directory / "sk-ZYXWVUTSRQPONMLKJIHG.txt").write_text("y")
    with pytest.raises(GitError) as error:
        manager.commit(directory, "Out of scope", ["f.txt"])
    assert "ZYXWVUTSRQPONMLKJIHG" not in str(error.value) and "[REDACTED]" in str(error.value)
    assert "ZYXWVUTSRQPONMLKJIHG" not in manager.snapshot(directory)["status"]
