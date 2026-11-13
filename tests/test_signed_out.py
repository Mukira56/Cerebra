"""An expired Claude or ChatGPT sign-in is named plainly, remembered, and told to the owner's phone once. No real CLI runs."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ai_hq import agents
from ai_hq.agents import ClaudeAdapter, signed_out
from ai_hq.api import create_app
from ai_hq.config import Settings
from test_product_api import KEY

LIVE = "Failed to authenticate: OAuth session expired and could not be refreshed"  # what a live Council turn printed


class Runner:
    def __init__(self, stderr, exit_code=1):
        self.stderr, self.exit_code = stderr, exit_code

    def run(self, *args, **kwargs):
        return SimpleNamespace(cancelled=False, timed_out=False, exit_code=self.exit_code, stderr=self.stderr, stdout="")


def adapter(stderr):
    claude = ClaudeAdapter(runner=Runner(stderr), allow_live=True, confinement_mode="cli-confinement")
    claude._capability = {"available": True, "executable": "claude", "plain": True}
    return claude


def test_the_words_of_an_expired_sign_in_are_recognised():
    assert signed_out(LIVE) and signed_out("Invalid API key · Please run /login") and signed_out("401 Unauthorized: refresh token expired")
    assert not signed_out("You've hit your usage limit") and not signed_out("tests failed: assert 401 == 200")


def test_a_chat_turn_names_the_expired_sign_in_and_tells_the_watchers(tmp_path, monkeypatch):
    told = []
    monkeypatch.setattr(agents, "signed_out_watchers", [lambda name, detail: told.append((name, detail))])
    result = adapter(LIVE).chat("hello", str(tmp_path))
    assert not result.success and result.error.startswith("authentication_error: Claude is signed out")
    assert "open Models, then Sign in for Claude" in result.error
    assert told == [("claude", LIVE)]
    other = adapter("something else broke").chat("hello", str(tmp_path))
    assert "signed out" not in other.error and len(told) == 1


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def test_cerebra_remembers_it_and_alerts_the_phone_once(client):
    sent = []
    client.app.state.notifier.send = lambda title, text, *args, **kwargs: sent.append((title, text)) or {"sent": ["telegram"]}
    for _ in range(3):
        agents.report_signed_out("claude", LIVE)
    assert len(sent) == 1 and "Claude is signed out" in sent[0][1] and "Models" in sent[0][1]
    claude = next(item for item in client.get("/api/providers").json() if item["id"] == "claude")
    assert claude["sign_in"]["signed_in"] is False and "expired" in claude["sign_in"]["detail"]
    agents.report_signed_out("codex", "Not logged in")
    assert len(sent) == 2 and "ChatGPT (Codex) is signed out" in sent[1][1]
