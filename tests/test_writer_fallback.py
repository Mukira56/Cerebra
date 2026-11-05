"""When one subscription stops, the other writes, but only a proven subscription: never an API key, never paid usage. Models are simulated."""
from ai_hq.agents import AgentResult
from ai_hq.models import Event
from ai_hq.prospects import failure_kind, plain_failure
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_outreach import Model, setup

LOG = "2026-11-05T08:00:48.873132Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out"


def prepared(client, errors, signed_in=("codex", "claude")):  # noqa: F811
    """`errors` says which models fail, and how."""
    state = setup(client)
    calls, checks = [], []

    class Limited(Model):
        def chat(self, name, prompt, workdir, model="", cancel_event=None):
            calls.append((name, model))
            if name in errors:
                return AgentResult(False, "", error=errors[name])
            return super().chat(name, prompt, workdir, model, cancel_event)

    def check(name):
        checks.append(name)
        if name not in signed_in:
            raise ValueError("No API request or paid fallback was made.")
        return True
    state.supervisor.registry = Limited()
    state.prospect_writer.subscription_status = check
    state.prospector.search("dentists", "Austin", "Texas")
    smile = next(item for item in client.get("/api/prospects").json()["prospects"] if item["name"] == "Smile Dental")
    client.put("/api/outreach", json={"writing_model": "codex"}).raise_for_status()
    return state, calls, checks, smile


def draft(client, smile):  # noqa: F811
    return client.post(f"/api/prospects/{smile['id']}/opener")


def test_real_failure_texts_are_understood():
    assert failure_kind("codex exited with code 1: You\u2019ve hit your usage limit. Upgrade to Pro") == "limit"
    assert failure_kind("rate_limited: agent exited with code 1") == "limit"
    assert failure_kind(LOG) == "network" and failure_kind("offline: agent exited") == "network"
    assert failure_kind("The prompt was refused") == "" and failure_kind(None) == ""


def test_the_owner_gets_a_sentence_not_log_lines():
    assert plain_failure("codex", "You\u2019ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro)") == "ChatGPT has reached its usage limit or needs signing in again."
    assert plain_failure("claude", LOG) == "Claude couldn't be reached: the connection timed out."
    assert plain_failure("codex", f"{LOG}\nThe prompt was too long") == "ChatGPT couldn't be reached: the connection timed out."
    assert plain_failure("codex", "2026-11-05T08:00:48Z WARN x\nThe prompt was refused") == "The prompt was refused"
    assert plain_failure("codex", None) == "The model couldn't write it"


def test_a_usage_limit_hands_the_draft_to_the_other_subscription_and_says_so(client):  # noqa: F811
    state, calls, checks, smile = prepared(client, {"codex": "You\u2019ve hit your usage limit."})
    assert draft(client, smile).status_code == 200
    assert [name for name, _ in calls] == ["codex", "claude"] and "claude" in checks
    with state.db.Session() as session:
        assert any("Claude wrote this draft instead" in item.message for item in session.query(Event).all())


def test_a_timeout_hands_it_over_too(client):  # noqa: F811
    _, calls, _, smile = prepared(client, {"codex": LOG})
    assert draft(client, smile).status_code == 200 and calls[-1][0] == "claude"


def test_a_client_on_an_api_key_is_never_used(client):  # noqa: F811
    _, calls, checks, smile = prepared(client, {"codex": "usage limit"}, signed_in=("codex",))
    answer = draft(client, smile)
    assert answer.status_code == 400 and [name for name, _ in calls] == ["codex"] and "claude" in checks  # asked about, never called
    assert answer.json()["detail"].startswith("ChatGPT has reached its usage limit") and "Writing model" in answer.json()["detail"]


def test_without_a_way_to_prove_a_subscription_there_is_no_switch(client):  # noqa: F811
    state, calls, _, smile = prepared(client, {"codex": "usage limit"})
    del state.prospect_writer.subscription_status
    assert draft(client, smile).status_code == 400 and [name for name, _ in calls] == ["codex"]


def test_a_problem_another_model_would_not_fix_is_not_handed_over(client):  # noqa: F811
    _, calls, _, smile = prepared(client, {"codex": "The prompt was refused"})
    answer = draft(client, smile)
    assert answer.status_code == 400 and [name for name, _ in calls] == ["codex"] and "The prompt was refused" in answer.json()["detail"]


def test_when_both_are_out_it_says_so_plainly_and_tries_each_once(client):  # noqa: F811
    _, calls, _, smile = prepared(client, {"codex": "usage limit", "claude": "usage limit"})
    answer = draft(client, smile)
    assert answer.status_code == 400 and [name for name, _ in calls] == ["codex", "claude"]
    assert "ERROR" not in answer.json()["detail"] and "usage limit" in answer.json()["detail"]


def test_a_named_model_that_works_is_used_with_no_switch(client):  # noqa: F811
    _, calls, checks, smile = prepared(client, {})
    assert draft(client, smile).status_code == 200 and [name for name, _ in calls] == ["codex"] and "claude" not in checks
