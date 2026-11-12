"""Talking to Cerebra from the phone in plain words (ai_hq/assistant.py): simple requests by rules, the rest by the owner's
writing model (a fixture here), carried out through Cerebra's own API in-process, with a yes asked first for anything that
sends, installs or approves. Telegram and the model are simulated; nothing leaves this computer."""
from ai_hq import assistant
from test_freelance import client  # noqa: F401  (client is a fixture)


class Thinker:
    """A stand-in for the owner's writing model: answers from a script, keyed by a word in the owner's message."""
    def __init__(self, script):
        self.script, self.prompts = script, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        message = prompt.rsplit("THE OWNER'S NEW MESSAGE:", 1)[1]
        for word, answers in self.script.items():
            if word in message:
                return answers.pop(0) if isinstance(answers, list) and len(answers) > 1 else (answers[0] if isinstance(answers, list) else answers)
        return {"reply": "I'm not sure what you mean.", "actions": []}


class Updates:
    def __init__(self, available=True):
        self.available, self.installed, self.downloads = available, False, []

    def check(self):
        if not self.available:
            return {"available": False, "current": "0.74.39", "message": "You have the latest version."}
        return {"available": True, "current": "0.74.39", "latest": "0.74.40", "tag": "v0.74.40", "downloaded": False}

    def start_download(self, tag):
        self.downloads.append(tag)

    def progress(self):
        return {"phase": "ready"}

    def install(self):
        self.installed = True
        return {"message": "Updating to Cerebra 0.74.40. Cerebra will close, update and reopen in about a minute."}


def phone(client, script=None, updater=None):  # noqa: F811
    helper = client.app.state.assistant
    helper.think = Thinker(script or {})
    helper.updater, helper.wait_seconds = updater or Updates(), 0.01
    return helper


def test_dark_mode_from_the_phone_reaches_every_window(client):  # noqa: F811
    helper = phone(client)
    answer = helper.reply("Put dark mode on please")
    assert answer["text"].startswith("Dark mode is on") and not helper.think.prompts  # plain request: no model needed
    look = client.get("/api/overview").json()["preferences"]
    assert look["theme"] == "dark" and look["changed_at"]
    assert helper.reply("make the text bigger text")["text"].startswith("Text is larger")
    assert client.get("/api/preferences").json()["size"] == "large"
    assert client.put("/api/preferences", json={"theme": "purple"}).status_code == 400


def test_updating_asks_first_then_downloads_and_installs(client):  # noqa: F811
    updates = Updates()
    helper = phone(client, updater=updates)
    notes = []
    helper.notify = notes.append
    question = helper.reply("Update my Cerebra to the newest release")
    assert "0.74.40 is available" in question["text"] and question["buttons"] and not updates.downloads
    started = helper.reply("yes")
    assert "Downloading Cerebra 0.74.40" in started["text"]
    import time
    for _ in range(200):
        if updates.installed:
            break
        time.sleep(0.01)
    assert updates.downloads == ["v0.74.40"] and updates.installed and "close, update and reopen" in notes[-1]
    phone(client, updater=Updates(available=False))
    assert "latest version" in client.app.state.assistant.reply("update cerebra")["text"]


def test_saying_no_or_a_stale_button_leaves_it(client):  # noqa: F811
    updates = Updates()
    helper = phone(client, updater=updates)
    helper.reply("update cerebra")
    assert helper.reply("no")["text"] == "OK, I've left it." and not updates.downloads
    assert "expired" in helper.answer_pending(True, "not-the-token")["text"]


def test_settings_change_through_cerebra_s_own_rules_and_starting_to_send_asks_first(client):  # noqa: F811
    helper = phone(client, {
        "100 pitches": {"reply": "Done: 100 a day.", "actions": [{"name": "change", "method": "PUT", "path": "/api/partners", "body": {"per_day": 100}}]},
        "switch pitches on": {"reply": "Switching pitches on.", "actions": [{"name": "change", "method": "PUT", "path": "/api/partners", "body": {"enabled": True}}]},
        "a million": {"reply": "Trying.", "actions": [{"name": "change", "method": "PUT", "path": "/api/partners", "body": {"per_day": 1000000}}]},
    })
    assert "100 a day" in helper.reply("send 100 pitches a day")["text"]
    assert client.get("/api/partners").json()["settings"]["per_day"] == 100
    refused = helper.reply("send a million pitches a day")["text"]
    assert "That didn't work" in refused and client.get("/api/partners").json()["settings"]["per_day"] == 100  # the laptop's own limit applies
    asked = helper.reply("switch pitches on")
    assert asked["buttons"] and client.get("/api/partners").json()["settings"]["enabled"] is False


def test_it_reads_before_it_answers(client):  # noqa: F811
    helper = phone(client, {"how many projects": [
        {"reply": "", "actions": [{"name": "read", "path": "/api/overview"}]},
        {"reply": "You have no projects yet.", "actions": []}]})
    answer = helper.reply("how many projects do I have?")
    assert answer["text"] == "You have no projects yet."
    assert "WHAT YOU READ: /api/overview" in helper.think.prompts[-1]


def test_keys_passwords_and_unknown_paths_never_go_through_the_phone(client):  # noqa: F811
    helper = phone(client, {
        "stripe": {"reply": "", "actions": [{"name": "change", "method": "PUT", "path": "/api/money/stripe", "body": {"secret_key": "sk_test_x"}}]},
        "gmail": {"reply": "", "actions": [{"name": "change", "method": "PUT", "path": "/api/business/gmail", "body": {}}]},
        "made up": {"reply": "", "actions": [{"name": "change", "method": "POST", "path": "/api/self-destruct", "body": {}}]},
        "delete": {"reply": "", "actions": [{"name": "change", "method": "DELETE", "path": "/api/chats/x", "body": {}}]},
    })
    assert "stay on the laptop" in helper.reply("connect my stripe")["text"]
    assert "stay on the laptop" in helper.reply("reconnect gmail")["text"]
    assert "don't know how" in helper.reply("do the made up thing")["text"]
    deleting = helper.reply("delete my project")
    assert deleting["buttons"] and deleting["text"].startswith("Delete chats")  # deleting works from the phone, with a yes first
    assert "/api/money/stripe" not in helper.think.prompts[0]  # not even listed for the model


def test_without_a_model_simple_requests_still_work(client):  # noqa: F811
    helper = client.app.state.assistant
    helper.think = None
    assert helper.reply("light mode")["text"].startswith("Light mode is on")
    assert "writing model" in helper.reply("how are my pitches doing this week?")["text"]
    assert "Talk to me" in helper.reply("help")["text"]


def test_the_telegram_bot_passes_words_to_the_assistant_and_yes_buttons_back(client):  # noqa: F811
    remote = client.app.state.remote
    said = []
    remote.say = lambda settings, text, buttons=None: said.append((text, buttons))
    remote._call = lambda settings, method, **payload: {}
    phone(client, updater=Updates())
    owner = {"token": "x", "chat": "42"}
    remote.handle(owner, {"message": {"chat": {"id": 42}, "text": "dark mode"}})
    assert said[-1][0].startswith("Dark mode is on")
    remote.handle(owner, {"message": {"chat": {"id": 7}, "text": "dark mode"}})  # a stranger: ignored
    assert len(said) == 1
    remote.handle(owner, {"message": {"chat": {"id": 42}, "text": "update cerebra"}})
    token = said[-1][1][0][1][1].split(":")[1]
    remote.handle(owner, {"callback_query": {"id": "q", "data": f"no:{token}", "message": {"chat": {"id": 42}}}})
    assert said[-1][0] == "OK, I've left it."
    assert assistant.describe("PUT", "/api/jobs", {"mode": "send"}) == "Change jobs (mode = send)"


def _tasks(client):  # noqa: F811
    from ai_hq.models import Approval, Project, Task
    with client.app.state.db.Session.begin() as session:
        session.add(Project(id="shop", name="Shop site", path="C:/shop-example", default_branch="main"))
        session.flush()
        session.add(Task(id="blocked0001", project_id="shop", description="Add a contact page", state="BLOCKED",
                         results={"blocked_reason": "repository_has_changes", "error": "Merge waiting: the project folder has uncommitted changes (package-lock.json)"}))
        session.add(Task(id="waiting0001", project_id="shop", description="Add online booking", state="AWAITING_APPROVAL", results={}))
        session.flush()
        session.add(Approval(id="ap1", task_id="waiting0001", kind="merge", status="pending", payload={}))


def test_where_my_tasks_are_and_why_they_wait_comes_straight_from_the_records(client):  # noqa: F811
    _tasks(client)
    helper = phone(client)
    answer = helper.reply("where is my task?")["text"]
    assert not helper.think.prompts  # no model needed: it reads Cerebra's own records
    assert "Add a contact page" in answer and "aren't committed" in answer and "package-lock.json" in answer
    assert "Waiting for your OK: merge" in answer and "Shop site" in answer
    assert "why is it blocked" and "aren't committed" in helper.reply("why is it blocked?")["text"]


def test_run_it_means_start_or_resume_and_cancelling_asks_first(client):  # noqa: F811
    _tasks(client)
    helper = phone(client)
    calls = []
    real = helper.call
    helper.call = lambda method, path, body=None: (calls.append((method, path)), (200, {}))[1] if "/api/tasks/" in path else real(method, path, body)
    assert "Done." in helper._run({"name": "task", "id": "blocked0", "do": "run"})["text"]
    assert calls[-1] == ("POST", "/api/tasks/blocked0001/resume")  # a blocked task resumes
    asked = helper._run({"name": "task", "id": "blocked0001", "do": "cancel"})
    assert asked["buttons"] and calls[-1][1].endswith("/resume")
    assert "started, resumed" in helper._run({"name": "task", "id": "blocked0001", "do": "explode"})["text"]
    assert "couldn't find" in helper._run({"name": "task", "id": "nope", "do": "start"})["text"]


def test_task_alerts_say_why_and_come_with_buttons_and_new_waiting_items_are_announced(client):  # noqa: F811
    _tasks(client)
    phone(client)
    remote = client.app.state.remote
    said = []
    remote.say = lambda settings, text, buttons=None: said.append((text, buttons))
    remote._settings = lambda: {"token": "x", "chat": "42"}
    remote.supervisor = object()
    assert remote.task_alert("blocked0001", "BLOCKED")
    assert "aren't committed" in said[-1][0] and said[-1][1][0][0][1] == "tsk:resume:blocked0001"
    remote.task_alert("waiting0001", "AWAITING_APPROVAL")
    assert said[-1][1][0][0] == ("YES ✓", "apr:ap1")
    owner = remote._settings()
    assert remote.announce_waiting(owner) == 0  # the first look only remembers what was already waiting
    from ai_hq.models import Approval
    with client.app.state.db.Session.begin() as session:
        session.add(Approval(id="ap2", task_id="blocked0001", kind="plan", status="pending", payload={}))
    assert remote.announce_waiting(owner) == 1 and "Approve a plan" in said[-1][0] and said[-1][1][0][0][1].startswith("w:")
    assert remote.announce_waiting(owner) == 0  # told once
