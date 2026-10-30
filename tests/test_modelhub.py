"""The model hub: only the owner's Claude and Codex accounts and free models; anything with a price is refused.
OpenRouter is simulated; no real key or model is used."""
import json

import httpx

from ai_hq import modelhub
from ai_hq.agents import AgentResult
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401  (client is a fixture)

KEY = "sk-or-v1-test-key-1234567890abcdef1234567890abcdef"
MODELS = {"data": [
    {"id": "google/gemma-4-31b-it:free", "name": "Gemma 4 (free)", "pricing": {"prompt": "0", "completion": "0"}, "context_length": 262144},
    {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "name": "Nemotron (free)", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "openrouter/free", "name": "Free router", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "x-ai/grok-4.7", "name": "Grok 4.7", "pricing": {"prompt": "0.000002", "completion": "0.000006"}},
]}


class OpenRouter:
    def __init__(self, status=200):
        self.status, self.bodies = status, []

    def __call__(self, request):
        if request.url.host == "127.0.0.1":  # no Ollama on this simulated computer
            raise httpx.ConnectError("refused")
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json=MODELS)
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "Rate limit exceeded: free-models-per-day"}})
        return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"content": "ready"}}],
                                         "usage": {"prompt_tokens": 12, "completion_tokens": 1, "cost": 0}})


def connect(client, status=200):  # noqa: F811
    site = OpenRouter(status)
    client.app.state.hub.client = httpx.Client(transport=httpx.MockTransport(site))
    client.put("/api/models/hub", json={"api_key": KEY})
    return site


def test_only_free_models_and_the_owners_accounts_can_be_chosen(client):  # noqa: F811
    connect(client)
    state = client.get("/api/models/hub").json()
    assert state["connected"] and state["free_only"] and "api_key" not in json.dumps(state).replace('"api_key"', "") and KEY not in json.dumps(state)
    assert {item["id"] for item in state["free_models"]} == {"google/gemma-4-31b-it:free", "nvidia/nemotron-3-ultra-550b-a55b:free", "openrouter/free"}
    assert state["routes"]["writing"] == "account:claude" and state["routes"]["judgment"] == "account:claude"
    refused = client.put("/api/models/hub", json={"routes": {"bulk": "x-ai/grok-4.7"}})
    assert refused.status_code == 400 and "isn't free" in refused.json()["detail"]
    assert client.put("/api/models/hub", json={"routes": {"bulk": "google/gemma-4-31b-it:free", "writing": "account:codex"}}).json()["routes"]["writing"] == "account:codex"
    assert client.put("/api/models/hub", json={"api_key": "not-a-key"}).status_code == 400


def test_a_free_model_answers_with_fallbacks_and_costs_nothing(client):  # noqa: F811
    site = connect(client)
    assert client.post("/api/models/hub/test", json={"category": "verify"}).json() == {"ok": True, "answer": "ready"}
    body = site.bodies[-1]
    assert body["model"] == "google/gemma-4-31b-it:free" and body["models"][-1] == "openrouter/free" and "tools" not in body  # no paid web search
    usage = client.get("/api/models/hub").json()["usage"]
    assert usage == [{"category": "verify", "model": "google/gemma-4-31b-it:free", "calls": 1, "cost": 0.0}]


def test_a_paid_model_is_never_called_even_if_stored(client):  # noqa: F811
    site = connect(client)
    with client.app.state.db.Session.begin() as session:  # as if an older setting or a hand edit had named a paid model
        row = session.get(modelhub.Metadata, modelhub.KEY)
        row.value = {**row.value, "routes": {"bulk": "x-ai/grok-4.7"}}
    result = client.app.state.hub.chat("bulk", "hello")
    assert not result.success and "isn't free right now" in result.error and site.bodies == []


def test_the_daily_free_limit_is_explained(client):  # noqa: F811
    connect(client, status=429)
    refused = client.post("/api/models/hub/test", json={"category": "bulk"})
    assert refused.status_code == 400 and "50 requests a day" in refused.json()["detail"]


def test_writing_goes_to_the_owners_claude_account(client):  # noqa: F811
    calls = []

    class Accounts(FixtureRegistry):
        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            calls.append(name)
            return AgentResult(True, "drafted")
    hub = client.app.state.hub
    result = modelhub.chat_for(hub, "writing", lambda: Accounts(), {"provider": "codex", "model": "gpt-x"}, "Write a proposal", ".")
    assert result.output == "drafted" and calls == ["claude"]
    assert modelhub.chat_for(None, "writing", lambda: Accounts(), {"provider": "codex"}, "x", ".").output == "drafted" and calls[-1] == "codex"  # no hub: as before


class Ollama:
    def __init__(self, models=("deepseek-r1:8b", "qwen3:14b")):
        self.models, self.bodies = list(models), []

    def __call__(self, request):
        if request.url.host == "127.0.0.1" and request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": name} for name in self.models]})
        if request.url.host == "127.0.0.1" and request.url.path == "/api/chat":
            body = json.loads(request.content)
            self.bodies.append(body)
            if body["model"] not in self.models:
                return httpx.Response(404, json={"error": "model not found"})
            return httpx.Response(200, json={"message": {"content": "<think>let me think</think>\nready"}, "prompt_eval_count": 10, "eval_count": 2})
        return OpenRouter()(request)


def test_models_on_this_computer_work_without_any_key_and_cost_nothing(client):  # noqa: F811
    local = Ollama()
    client.app.state.hub.client = httpx.Client(transport=httpx.MockTransport(local))
    state = client.get("/api/models/hub").json()
    assert state["local_models"] == ["deepseek-r1:8b", "qwen3:14b"] and not state["connected"]  # no OpenRouter key needed
    assert client.put("/api/models/hub", json={"routes": {"verify": "local:deepseek-r1:8b"}}).status_code == 200
    assert client.post("/api/models/hub/test", json={"category": "verify"}).json()["answer"] == "ready"  # its thinking is left out
    assert local.bodies[-1]["model"] == "deepseek-r1:8b" and local.bodies[-1]["stream"] is False
    usage = client.get("/api/models/hub").json()["usage"]
    assert usage == [{"category": "verify", "model": "local:deepseek-r1:8b", "calls": 1, "cost": 0.0}]
    client.put("/api/models/hub", json={"routes": {"verify": "local:llama4:70b"}})
    missing = client.post("/api/models/hub/test", json={"category": "verify"})
    assert missing.status_code == 400 and "ollama pull llama4:70b" in missing.json()["detail"]


def test_without_ollama_running_the_message_says_so(client):  # noqa: F811
    def down(request):
        raise httpx.ConnectError("refused")
    client.app.state.hub.client = httpx.Client(transport=httpx.MockTransport(down))
    assert client.get("/api/models/hub").json()["local_models"] == []
    client.put("/api/models/hub", json={"routes": {"bulk": "local:qwen3:14b"}})
    result = client.app.state.hub.chat("bulk", "hello")
    assert not result.success and "Ollama isn't running" in result.error


def test_a_slow_model_list_never_blocks_the_models_page(client):  # noqa: F811
    import threading
    gate = threading.Event()

    def slow(request):
        if request.url.host == "127.0.0.1":
            raise httpx.ConnectError("refused")
        gate.wait(10)  # OpenRouter over a slow connection
        return httpx.Response(200, json=MODELS)
    client.app.state.hub.client = httpx.Client(transport=httpx.MockTransport(slow))
    state = client.get("/api/models/hub").json()  # answers within about 1.5 s instead of waiting
    assert state["catalog_loading"] and state["free_models"] == [] and state["catalog_reachable"]
    gate.set()
    for _ in range(100):
        state = client.get("/api/models/hub").json()
        if not state["catalog_loading"]:
            break
    assert {item["id"] for item in state["free_models"]} == {"google/gemma-4-31b-it:free", "nvidia/nemotron-3-ultra-550b-a55b:free", "openrouter/free"}
