"""Business research lab: two scripted fixture models take turns researching, attacking and improving ideas, with a
shared memory and a scored idea board. No real CLI runs."""
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_hq import research_lab
from ai_hq.agents import AgentResult, ClaudeAdapter, CodexAdapter
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.research_lab import parse_turn, total
from fakes import FixtureRegistry
from test_product_api import KEY, enable_agents


def block(**data):
    return f"My reasoning for the other researcher.\n```cerebra-research\n{json.dumps(data)}\n```"


SCORES = {"pain": 8, "willingness_to_pay": 7, "sells_itself": 6, "reach": 7, "speed_to_cash": 8, "defensibility": 5, "evidence": 6, "legal_safety": 9}


class LabRegistry(FixtureRegistry):
    """Answers each stage with a fixed research block and records which entry point and folder each turn used."""
    def __init__(self, failing=()):
        super().__init__()
        self.turns, self.failing, self.used_research = [], set(failing), 0

    def research(self, name, prompt, workdir, model="", cancel_event=None):
        self.used_research += 1
        return self.chat(name, prompt, workdir, model, cancel_event)

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.turns.append((name, prompt, workdir))
        if name in self.failing:
            return AgentResult(False, "", error="usage limit reached")
        if "YOUR TURN: Research and propose" in prompt:
            return AgentResult(True, block(notes=[{"kind": "market", "title": "Small clinics still fax referrals", "detail": "Surveys show fax use.",
                                                   "source": "https://example.org/survey", "confidence": "medium"},
                                                  {"kind": "price", "title": "Referral tools cost $300 a month", "detail": "Pricing page.", "source": "https://example.org/pricing"}],
                                           ideas=[{"name": "Fax-to-EHR inbox", "track": "floor", "customer": "US dental clinics", "price": "$149/month",
                                                   "change": "first version", "scores": SCORES}],
                                           questions=["How many clinics still fax?"]))
        if "YOUR TURN: Attack" in prompt:
            return AgentResult(True, block(notes=[{"kind": "competitor", "title": "A competitor sells the same for $99", "source": "https://example.org/rival"},
                                                  {"kind": "market", "title": "Small clinics still fax referrals"}],  # already known: not stored twice
                                           ideas=[{"name": "Fax-to-EHR inbox for orthodontists", "improves": "Fax-to-EHR inbox", "price": "$199/month",
                                                   "change": "narrower buyer who pays more", "scores": {"willingness_to_pay": 8}},
                                                  {"name": "Crypto pump signals", "track": "big", "kill": True, "kill_reason": "not legal"}]))
        if "YOUR TURN: Be the customer" in prompt:
            return AgentResult(True, block(notes=[{"kind": "customer", "title": "Office managers hate retyping referrals", "source": "https://example.org/forum"}],
                                           ideas=[{"name": "Tender alerts for EU SMEs", "track": "big", "customer": "EU construction firms",
                                                   "change": "new", "scores": {**SCORES, "legal_safety": 3}}]))
        return AgentResult(True, block(ideas=[{"name": "Fax-to-EHR inbox for orthodontists", "change": "re-scored", "scores": {"evidence": 8}}],
                                       questions=["What do orthodontists use today?"],
                                       report={"summary": "The fax inbox leads.", "floor": {"idea": "Fax-to-EHR inbox for orthodontists", "why": "Paid pain", "plan": ["Call 20 clinics"]},
                                               "big": {"idea": "Tender alerts for EU SMEs", "why": "Large market", "plan": ["Check the rules"]}, "confidence": "low"}))


@pytest.fixture
def lab_app(tmp_path, monkeypatch):
    monkeypatch.setattr(research_lab, "WAIT_FIRST", 0.05)
    monkeypatch.setattr(research_lab, "WAIT_MOST", 0.1)
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    app.state.supervisor.registry = LabRegistry()
    app.state.supervisor._refresh_registry = lambda: None
    told = []
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        enable_agents(client)
        app.state.research.on_report = lambda lab_id, text: told.append(text)
        client.told = told
        yield client, app
        app.state.research.pause_all()


def wait_for(check, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_parse_turn_takes_the_last_valid_block_and_cleans_it():
    text = "```cerebra-research\nnot json```\n" + block(notes=[{"kind": "gossip", "title": " A "}, {"title": ""}],
                                                        ideas=[{"name": "X", "track": "weird", "scores": {"pain": 42, "reach": "7", "bogus": 3}}])
    parsed = parse_turn(text)
    assert parsed["notes"] == [{"kind": "fact", "title": "A", "detail": "", "source": "", "confidence": "medium"}]
    assert parsed["ideas"][0]["track"] == "" and parsed["ideas"][0]["scores"] == {"pain": 10, "reach": 7}
    assert parse_turn("no block here") is None


def test_score_weights_pain_and_payment_and_halves_unsafe_ideas():
    assert total({}) == 0
    assert total({name: 10 for name in research_lab.SCORE_WEIGHTS}) == 100
    assert total({**SCORES, "legal_safety": 3}) == total(SCORES) // 2 or total({**SCORES, "legal_safety": 3}) == round(total(SCORES) / 2)


def test_roles_swap_each_round_and_the_lead_judges():
    service = research_lab.ResearchLabService(None, None, None)
    lead, other = {"provider": "claude"}, {"provider": "codex"}
    order = [(stage, speaker["provider"]) for stage, speaker, _ in (service.speakers(number, [lead, other]) for number in range(1, 9))]
    assert order == [("scout", "claude"), ("critic", "codex"), ("customer", "claude"), ("synthesis", "claude"),
                     ("scout", "codex"), ("critic", "claude"), ("customer", "codex"), ("synthesis", "claude")]


def test_a_lab_researches_improves_and_reports_until_stopped(lab_app, tmp_path):
    client, app = lab_app
    lab = client.post("/api/research", json={"pace": 3600}).json()  # one turn, then a long pause: the rest run here, in order
    assert lab["status"] == "running" and "United States" in lab["goal"]
    wait_for(lambda: client.get(f"/api/research/{lab['id']}").json()["turn"] >= 1)
    assert [app.state.research.step(lab["id"]) for _ in range(3)] == [(True, "")] * 3
    assert client.post(f"/api/research/{lab['id']}/stop").status_code == 200
    wait_for(lambda: not client.get(f"/api/research/{lab['id']}").json()["busy"])
    state = client.get(f"/api/research/{lab['id']}").json()
    registry = app.state.supervisor.registry
    assert registry.used_research >= 4  # every turn goes through the web-research entry point
    assert Path(registry.turns[0][2]).name == lab["id"]  # turns run in the lab's own folder

    ideas = {idea["name"]: idea for idea in state["ideas"]}
    improved = ideas["Fax-to-EHR inbox for orthodontists"]  # the critic renamed and improved the scout's idea
    assert "Fax-to-EHR inbox" not in ideas and improved["version"] >= 3 and improved["current"]["price"] == "$199/month"
    assert improved["current"]["customer"] == "US dental clinics"  # fields left out keep their value
    assert [step["stage"] for step in improved["history"]][:3] == ["scout", "critic", "synthesis"]
    assert "Crypto pump signals" not in ideas  # a kill of an unknown idea adds nothing
    risky = ideas["Tender alerts for EU SMEs"]
    assert risky["score"] < improved["score"]  # low legal safety halves the score

    notes = client.get(f"/api/research/{lab['id']}/notes").json()
    titles = [note["title"] for note in notes]
    assert titles.count("Small clinics still fax referrals") == 1 and "A competitor sells the same for $99" in titles
    assert [note["title"] for note in client.get(f"/api/research/{lab['id']}/notes", params={"q": "competitor"}).json()] == ["A competitor sells the same for $99"]

    assert state["report"]["floor"]["idea"] == "Fax-to-EHR inbox for orthodontists" and state["questions"] == ["What do orthodontists use today?"]
    assert client.told and "Fax-to-EHR inbox for orthodontists" in client.told[0]
    folder = tmp_path / "data" / "research" / lab["id"]
    assert "Small clinics still fax referrals" in (folder / "NOTES.md").read_text(encoding="utf-8")
    assert "Fax-to-EHR inbox for orthodontists" in (folder / "IDEAS.md").read_text(encoding="utf-8")

    # The next turn sees the board, the memory, the open questions and the last turns, and must improve on them.
    prompt = app.state.research.prompt(lab["id"], 5, "scout", {"provider": "codex", "provider_label": "Codex"}, {"provider": "claude", "provider_label": "Claude"}, [])
    assert "Fax-to-EHR inbox for orthodontists" in prompt and "What do orthodontists use today?" in prompt and "Crypto pump signals" not in prompt.split("KILLED")[0]
    assert state["status"] == "stopped"


def test_the_owner_joins_in_and_the_next_turn_reads_it_first(lab_app):
    client, app = lab_app
    gate = threading.Event()
    registry = app.state.supervisor.registry
    original = registry.chat
    registry.chat = lambda *args, **kwargs: (gate.wait(10), original(*args, **kwargs))[1]
    lab = client.post("/api/research", json={"pace": 0}).json()
    said = client.post(f"/api/research/{lab['id']}/say", json={"text": "Focus on health care in Texas"}).json()
    assert "next turn" in said["message"]
    gate.set()
    wait_for(lambda: any("Focus on health care in Texas" in prompt for _, prompt, _ in registry.turns[1:]))
    client.post(f"/api/research/{lab['id']}/stop")
    turns = client.get(f"/api/research/{lab['id']}").json()["turns"]
    assert any(turn["stage"] == "owner" and turn["content"] == "Focus on health care in Texas" for turn in turns)


def test_when_one_model_is_out_of_usage_the_other_takes_the_turn(lab_app):
    client, app = lab_app
    app.state.supervisor.registry.failing = {"claude"}
    lab = client.post("/api/research", json={"pace": 0}).json()
    wait_for(lambda: client.get(f"/api/research/{lab['id']}").json()["turn"] >= 1)
    client.post(f"/api/research/{lab['id']}/stop")
    turns = client.get(f"/api/research/{lab['id']}").json()["turns"]
    assert turns[0]["provider"] == "claude" and turns[0]["status"] == "failed" and turns[1]["provider"] == "codex" and turns[1]["status"] == "done"


def test_when_both_are_out_the_lab_waits_and_carries_on_by_itself(lab_app):
    client, app = lab_app
    registry = app.state.supervisor.registry
    registry.failing = {"claude", "codex"}
    lab = client.post("/api/research", json={"pace": 0}).json()
    state = wait_for(lambda: (lambda value: value if value["status"] == "waiting" else None)(client.get(f"/api/research/{lab['id']}").json()))
    assert "Neither model" in state["error"] and state["next_at"]
    registry.failing = set()
    wait_for(lambda: client.get(f"/api/research/{lab['id']}").json()["turn"] >= 1)
    assert client.delete(f"/api/research/{lab['id']}").status_code == 400  # still running
    client.post(f"/api/research/{lab['id']}/stop")
    wait_for(lambda: not client.get(f"/api/research/{lab['id']}").json()["busy"])
    assert client.post(f"/api/research/{lab['id']}/resume").status_code == 200
    client.post(f"/api/research/{lab['id']}/stop")
    wait_for(lambda: not client.get(f"/api/research/{lab['id']}").json()["busy"])
    assert client.delete(f"/api/research/{lab['id']}").json() == {"deleted": True}
    assert client.get(f"/api/research/{lab['id']}").status_code == 404


def test_the_lab_needs_two_providers_and_a_known_pace(lab_app):
    client, _ = lab_app
    assert client.post("/api/research", json={"first": "claude", "second": "claude"}).status_code == 400
    lab = client.post("/api/research", json={"pace": 0}).json()
    client.post(f"/api/research/{lab['id']}/stop")
    assert client.put(f"/api/research/{lab['id']}", json={"pace": 7}).status_code == 400
    assert client.put(f"/api/research/{lab['id']}", json={"pace": 300}).status_code == 200


def test_research_turns_may_search_the_web_but_never_edit_or_run_commands(tmp_path):
    claude = ClaudeAdapter()
    args = claude._command("claude", tmp_path, True, ["."], web=True)
    tools = args[args.index("--tools") + 1]
    assert tools == "Read,Grep,Glob,WebSearch,WebFetch" and "WebSearch" in args and "Edit" not in tools and "Bash" not in tools
    assert "WebSearch" not in claude._command("claude", tmp_path, True, ["."])
    codex = CodexAdapter()
    assert 'web_search="live"' in codex._command("codex", tmp_path, True, ["."], web=True)
    assert 'web_search="live"' not in codex._command("codex", tmp_path, True, ["."])
    plain = codex._command("codex", tmp_path, True, ["."], web=True)
    assert plain[plain.index("--sandbox") + 1] == "read-only"
