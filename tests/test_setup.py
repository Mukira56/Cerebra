"""The Setup Center: goals first, then only the connections those goals need, in order, checked from Cerebra's own
records, with the one next step and a first job per goal once its essentials are done."""
from ai_hq import setup
from ai_hq.models import Metadata
from test_freelance import client  # noqa: F401  (client is a fixture)


def steps(state):
    return [step["id"] for step in state["steps"]]


def test_a_new_owner_picks_goals_and_sees_only_what_those_need(client):  # noqa: F811
    fresh = client.get("/api/setup").json()
    assert fresh["goals"] == [] and steps(fresh) == ["profile"] and not fresh["complete"]
    assert client.put("/api/setup", json={"goals": []}).status_code == 400
    jobs = client.put("/api/setup", json={"goals": ["jobs"]}).json()
    assert steps(jobs) == ["profile", "ai_on", "ai_account", "free_models", "gmail", "cv"]
    assert jobs["next"]["id"] == "profile" and jobs["total"] == 5 and jobs["minutes_left"] > 0  # the optional step isn't counted
    assert "telegram" not in steps(jobs) and "stripe" not in steps(jobs) and jobs["pages"] == ["jobs"]
    paid = client.put("/api/setup", json={"goals": ["paid"]}).json()
    assert steps(paid) == ["profile", "stripe"]  # no AI needed to send invoices
    overview = client.get("/api/overview").json()["setup"]
    assert overview["goals"] == ["paid"] and overview["next"]["id"] == "profile" and overview["next"]["find"] == "About you"


def test_steps_turn_green_from_cerebra_s_own_records_and_the_first_job_unlocks(client):  # noqa: F811
    client.put("/api/setup", json={"goals": ["jobs"]})
    client.put("/api/owner", json={"name": "Jane Example", "headline": "Developer", "location": "Austin, TX"})
    with client.app.state.db.Session.begin() as session:
        from ai_hq import jobs
        jobs.save_settings(session, {"cv": "Jane Example, developer. " * 20})
    state = client.get("/api/setup").json()
    done = {step["id"] for step in state["steps"] if step["done"]}
    assert {"profile", "cv"} <= done and state["next"]["id"] == "ai_on"
    win = state["first_wins"][0]
    assert win["goal"] == "jobs" and not win["ready"] and win["waiting_for"]  # AI and Gmail still missing
    assert win["path"] == "/api/jobs/find"


def test_skipping_a_step_moves_on_and_it_can_be_brought_back(client):  # noqa: F811
    client.put("/api/setup", json={"goals": ["phone"]})
    skipped = client.put("/api/setup", json={"skip": "profile"}).json()
    assert skipped["next"]["id"] == "ai_on" and next(step for step in skipped["steps"] if step["id"] == "profile")["skipped"]
    back = client.put("/api/setup", json={"unskip": "profile"}).json()
    assert back["next"]["id"] == "profile"
    assert client.put("/api/setup", json={"skip": "nonsense"}).status_code == 400


def test_signed_in_ai_counts_from_the_saved_sign_in_check(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(Metadata(key="sign_in_status", value={"claude": {"signed_in": True}}))
        assert setup._signed_in(session, "claude", "codex") and not setup._signed_in(session, "gemini")


def test_every_step_names_a_real_page_and_the_panel_to_open():
    pages = {"settings", "models", "connections", "money", "jobs", "freelance", "projects", "books"}
    for key, title, why, needed_by, optional, minutes, page, how in setup.STEPS:
        assert page in pages and how and set(needed_by) <= set(setup.GOALS) and key in setup.FIND
