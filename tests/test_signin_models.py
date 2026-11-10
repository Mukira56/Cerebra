"""Models the owner signs in to (Gemini CLI, Qwen Code): run read-only in their headless JSON mode, measured, and with a
plain fallback to the owner's account when one isn't installed, signed in or out of allowance. The tools are simulated."""
from types import SimpleNamespace

from ai_hq import modelhub, signin_models
from ai_hq.agents import AgentResult
from test_freelance import client  # noqa: F401  (client is a fixture)


class Runner:
    def __init__(self, stdout="", stderr="", code=0):
        self.calls, self.result = [], SimpleNamespace(stdout=stdout, stderr=stderr, exit_code=code, timed_out=False)

    def run(self, args, cwd, timeout, cancel_event=None, input_text=None, env=None, redact_output=True):
        self.calls.append((args, input_text))
        return self.result


def installed(monkeypatch):
    monkeypatch.setattr(signin_models, "command", lambda name: ["node", f"{name}.js"])


def test_a_turn_runs_read_only_with_the_prompt_on_stdin(monkeypatch, tmp_path):
    installed(monkeypatch)
    runner = Runner(stdout='Loaded.\n{"response": "ready", "stats": {}}')
    result = signin_models.chat("gemini", "Reply with: ready", tmp_path, runner=runner)
    assert result.success and result.output == "ready"
    args, stdin = runner.calls[0]
    assert args[:2] == ["node", "gemini.js"] and "-p" in args and ["--approval-mode", "plan"] == args[args.index("--approval-mode"):args.index("--approval-mode") + 2]
    assert ["-o", "json"] == args[args.index("-o"):args.index("-o") + 2] and stdin == "Reply with: ready"


def test_plain_reasons_when_it_cant_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(signin_models, "command", lambda name: None)
    assert "isn't installed" in signin_models.chat("qwen", "hi", tmp_path).error
    installed(monkeypatch)
    signed_out = signin_models.chat("gemini", "hi", tmp_path, runner=Runner(stderr="Please set an Auth method in settings.json", code=1))
    assert signed_out.error.startswith("not signed in") and "Google account" in signed_out.error
    used_up = signin_models.chat("qwen", "hi", tmp_path, runner=Runner(stderr="Error 429: quota exceeded", code=1))
    assert used_up.error.startswith("usage limit")
    off = signin_models.chat("gemini", "hi", tmp_path, allowed=False)
    assert "switched off" in off.error


def test_routed_work_goes_to_the_signed_in_account_and_is_measured(client, monkeypatch):  # noqa: F811
    installed(monkeypatch)
    hub = client.app.state.hub
    hub.allow_signed_in, hub.runner = (lambda: True), Runner(stdout='{"response": "Three sources agree."}')
    result = modelhub.chat_for(hub, "research", lambda: None, {"provider": "claude"}, "Check this claim", "/tmp")
    assert result.success and result.output == "Three sources agree."
    with client.app.state.db.Session() as session:
        assert modelhub.calls_today(session, "research") == 1


def test_when_the_account_cant_answer_the_owners_own_account_does(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(signin_models, "command", lambda name: None)
    hub = client.app.state.hub

    class Claude:
        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            return AgentResult(True, f"{name} answered")
    result = modelhub.chat_for(hub, "research", lambda: Claude(), {"provider": "claude"}, "Check this claim", "/tmp")
    assert result.success and result.output == "claude answered"


def test_the_signed_in_accounts_can_be_tested_from_the_models_page(client, monkeypatch):  # noqa: F811
    installed(monkeypatch)
    hub = client.app.state.hub
    hub.allow_signed_in, hub.runner = (lambda: True), Runner(stdout='{"response": "ready"}')
    assert client.post("/api/models/hub/test", json={"category": "research"}).json() == {"ok": True, "answer": "ready"}


def test_qwen_can_be_installed_and_signed_in_like_the_others(client):  # noqa: F811
    from ai_hq import integrations
    assert integrations.PROVIDERS["qwen"]["command"] == "qwen" and integrations.PROVIDERS["qwen"]["execution"] is False
    assert any(tool["id"] == "qwen-code" and tool["install"] == ["npm", "install", "-g", "@qwen-code/qwen-code"] for tool in integrations.TOOLS)


def test_one_click_back_to_the_signed_in_accounts(client):  # noqa: F811
    client.put("/api/models/hub", json={"routes": {"writing": "openrouter/free", "judgment": "openrouter/free"}}).raise_for_status()
    work = client.get("/api/models/intelligence").json()["work"]
    defaults = {item["key"]: item["default"] for item in work}
    assert client.put("/api/models/hub", json={"routes": defaults}).status_code == 200
    routes = {item["key"]: item["route"] for item in client.get("/api/models/intelligence").json()["work"]}
    assert routes["writing"] == "account:claude" and routes["research"] == "account:gemini" and "openrouter" not in "".join(routes.values())
