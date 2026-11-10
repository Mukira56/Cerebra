"""The model workforce: Claude leads the coding and isn't replaced without the owner, the Prompt Architect writes specs
without inventing requirements, every kind of work is measured, daily limits stop calls, local models too big for the
computer aren't loaded, and performance-based routing only switches on strong evidence. Providers are simulated."""
from datetime import datetime, timezone

import pytest

from ai_hq import architect, modelhub, routing
from ai_hq.agents import AgentResult
from ai_hq.models import ModelUsage
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_modelhub import connect


def usage(client, category, model, ok, calls):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        for number in range(calls):
            session.add(ModelUsage(category=category, model=model, ok=number < ok, seconds=2.0, prompt_tokens=100, completion_tokens=50))


# ---- Claude leads the coding ----
def test_claude_writes_the_code_and_another_company_reviews_it():
    chosen = routing.route(routing.assess("Build a booking page with a calendar"))
    assert chosen["implementer"]["provider"] == "claude" and chosen["reviewer"]["provider"] == "codex"
    assert "lead engineer" in chosen["implementer"]["why"]


def test_claude_running_out_waits_instead_of_handing_the_code_to_another_model(client):  # noqa: F811
    supervisor = client.app.state.supervisor

    class Task:
        id, results, assigned_agent = "t", {"models": {"implementer": {"provider": "claude", "tier": "balanced"}}}, "claude"
    assert supervisor._take_over(Task, "implement", "claude", "usage limit") is None
    with client.app.state.db.Session.begin() as session:
        routing.save(session, "rules", lock_coder=False)  # the owner allows the switch
    assert routing.load(client.app.state.db.Session()) ["lock_coder"] is False


def test_the_lead_coder_setting_is_saved(client):  # noqa: F811
    saved = client.put("/api/routing", json={"mode": "rules", "lead_coder": "auto", "lock_coder": False}).json()
    assert saved["lead_coder"] == "auto" and saved["lock_coder"] is False
    assert client.put("/api/routing", json={"mode": "rules", "lead_coder": "gemini"}).status_code == 422


# ---- the Prompt Architect ----
def test_a_short_plain_request_needs_no_model():
    calls = []
    spec = architect.write_spec("Fix the typo in the footer", {}, lambda prompt: calls.append(prompt))
    assert spec["by"] == "template" and spec["requirements"] == ["Fix the typo in the footer"] and calls == []


def test_the_architect_keeps_assumptions_and_questions_out_of_the_requirements(tmp_path):
    (tmp_path / "app.py").write_text("print('hi')")
    (tmp_path / ".env").write_text("SECRET=1")
    prompts = []

    def run(prompt):
        prompts.append(prompt)
        return AgentResult(True, '{"goal": "Clients book cleanings online", "requirements": ["Clients pick a date and time", "The owner sees bookings"], '
                                 '"constraints": ["Python"], "acceptance_criteria": ["A booking appears in the owner view"], "steps": ["Model", "Pages"], '
                                 '"open_questions": ["Should clients pay online?"], "assumptions": ["Prices are fixed per service"]}')
    spec = architect.write_spec("Build me a booking website for cleaning companies in America, with an admin view for the owner",
                                {"name": "Clean", "path": str(tmp_path), "test_commands": [["pytest", "-q"]]}, run)
    assert spec["by"] == "architect" and spec["requirements"] == ["Clients pick a date and time", "The owner sees bookings"]
    assert spec["open_questions"] == ["Should clients pay online?"] and spec["assumptions"] == ["Prices are fixed per service"]
    assert "app.py" in prompts[0] and ".env" not in prompts[0] and "SECRET" not in prompts[0]  # names only, never contents or hidden files
    assert "never put something the request doesn't say" in prompts[0]


@pytest.mark.parametrize("answer", ["no json here", '{"goal": ""}', "[1, 2]"])
def test_a_spec_that_isnt_usable_is_refused(answer):
    with pytest.raises(ValueError):
        architect.write_spec("Build an online shop with payments and an admin dashboard for my products", {}, lambda prompt: AgentResult(True, answer))


def test_the_architect_endpoint_uses_its_own_route(client):  # noqa: F811
    connect(client)
    spec = client.post("/api/architect", json={"objective": "Rename the button"}).json()
    assert spec["by"] == "template" and spec["model"] == "template"


# ---- measured performance, limits, local models ----
def test_every_kind_of_work_is_measured_and_a_better_model_is_suggested_only_on_evidence(client):  # noqa: F811
    usage(client, "research", "slow/model:free", ok=12, calls=24)
    usage(client, "research", "good/model:free", ok=23, calls=24)
    usage(client, "research", "new/model:free", ok=5, calls=5)
    with client.app.state.db.Session() as session:
        measured = modelhub.performance(session)
    better, why = modelhub.recommend(measured, "research", "slow/model:free")
    assert better == "good/model:free" and "96%" in why
    assert modelhub.recommend(measured, "research", "good/model:free")[0] is None
    assert modelhub.recommend(measured, "bulk", "x")[0] is None  # no evidence, no change
    intelligence = client.get("/api/models/intelligence").json()
    research = next(item for item in intelligence["work"] if item["key"] == "research")
    assert research["measured"][0]["model"] == "good/model:free" and "Claude and Codex don't tell Cerebra" in intelligence["subscription_note"]


def test_performance_routing_switches_only_when_on_and_never_away_from_an_account(client):  # noqa: F811
    hub = client.app.state.hub
    connect(client)
    client.put("/api/models/hub", json={"routes": {"research": "nvidia/nemotron-3-ultra-550b-a55b:free"}}).raise_for_status()
    usage(client, "research", "nvidia/nemotron-3-ultra-550b-a55b:free", ok=10, calls=25)
    usage(client, "research", "google/gemma-4-31b-it:free", ok=24, calls=25)
    assert hub.route("research") == "nvidia/nemotron-3-ultra-550b-a55b:free"  # off by default
    client.put("/api/models/hub", json={"adaptive": True}).raise_for_status()
    assert hub.route("research") == "google/gemma-4-31b-it:free"
    usage(client, "writing", "google/gemma-4-31b-it:free", ok=25, calls=25)
    assert hub.route("writing") == "account:claude"  # the owner's own account choice stays


def test_a_daily_limit_stops_calls_for_that_kind_of_work(client):  # noqa: F811
    connect(client)
    client.put("/api/models/hub", json={"daily_calls": {"bulk": 2}}).raise_for_status()
    hub = client.app.state.hub
    assert hub.chat("bulk", "one").success and hub.chat("bulk", "two").success
    third = hub.chat("bulk", "three")
    assert not third.success and "Today's limit of 2 calls" in third.error
    assert client.put("/api/models/hub", json={"daily_calls": {"bulk": -1}}).status_code == 400


def test_calls_through_the_owners_account_are_measured_too(client):  # noqa: F811
    hub = client.app.state.hub

    class Registry:
        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            return AgentResult(True, "done")
    result = modelhub.chat_for(hub, "writing", lambda: Registry(), {"provider": "claude"}, "Write it", "/tmp")
    assert result.success
    with client.app.state.db.Session() as session:
        assert modelhub.calls_today(session, "writing") == 1


def test_a_local_model_too_big_for_this_computer_is_never_loaded(client, monkeypatch):  # noqa: F811
    hub = client.app.state.hub
    monkeypatch.setattr(modelhub, "memory_bytes", lambda: 8 * 2**30)
    hub._local_sizes = {"giant:70b": 40 * 2**30, "small:3b": 2 * 2**30}
    assert "won't load it" in hub.too_big("giant:70b") and hub.too_big("small:3b") == ""
    refused = hub.chat_local("bulk", "local:giant:70b", "hello")
    assert not refused.success and "won't load it" in refused.error


def test_new_specialist_kinds_of_work_default_to_free_routes():
    for key in ("architect", "reasoning", "long_context"):
        assert modelhub.CATEGORIES[key][2] == "openrouter/free"  # free by default: never a paid service, never the Codex account
    assert datetime.now(timezone.utc)


def test_choosing_claude_to_review_makes_codex_the_coder():
    chosen = routing.route(routing.assess("Add a feature"), fixed={"reviewer": {"provider": "claude", "model": "opus", "label": "Claude Opus"}})
    assert chosen["implementer"]["provider"] == "codex" and "You chose Claude to review" in chosen["implementer"]["why"]
