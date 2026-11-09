import httpx
import pytest

from ai_hq import logs, resilience


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    waits = []
    monkeypatch.setattr(resilience, "sleep", waits.append)
    return waits


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_connection_that_never_opened_is_retried_even_for_a_send(no_waiting):
    calls = []
    def handler(request):
        calls.append(request.method)
        if len(calls) < 3:
            raise httpx.ConnectError("dropped", request=request)
        return httpx.Response(200, json={"id": "sent"})
    with client_for(handler) as client:
        response = resilience.send(client, "POST", "https://mail.example.test/send", json={"to": "a@example.test"})
    assert response.json() == {"id": "sent"} and calls == ["POST"] * 3
    assert len(no_waiting) == 2 and no_waiting[0] < no_waiting[1]  # the wait grows


def test_a_post_that_may_have_arrived_is_not_repeated():
    calls = []
    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("no answer", request=request)
    with client_for(handler) as client, pytest.raises(httpx.ReadTimeout):
        resilience.send(client, "POST", "https://pay.example.test/charge")
    assert len(calls) == 1


def test_busy_service_is_retried_for_reads_and_honours_retry_after(no_waiting):
    answers = [httpx.Response(503, headers={"Retry-After": "2"}), httpx.Response(429), httpx.Response(200, text="ok")]
    with client_for(lambda request: answers.pop(0)) as client:
        assert resilience.send(client, "GET", "https://api.example.test/items").text == "ok"
    assert no_waiting[0] == 2.0


def test_busy_answer_to_a_post_is_returned_not_retried():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(503)
    with client_for(handler) as client:
        assert resilience.send(client, "POST", "https://api.example.test/items").status_code == 503
    assert len(calls) == 1


def test_a_program_on_this_computer_is_asked_once():
    calls = []
    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)
    with client_for(handler) as client, pytest.raises(httpx.ConnectError):
        resilience.send(client, "GET", "http://127.0.0.1:11434/api/tags", breaker=resilience.Breaker(failures_to_open=1))
    assert len(calls) == 1


def test_last_failure_is_raised_after_all_tries():
    with client_for(lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request))) as client:
        with pytest.raises(httpx.ConnectError):
            resilience.send(client, "GET", "https://down.example.test/")


def test_breaker_pauses_a_failing_service_then_lets_one_trial_through(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(resilience, "clock", lambda: now[0])
    breaker = resilience.Breaker(failures_to_open=3, pause=30)
    calls = []
    healthy = [False]
    def handler(request):
        calls.append(1)
        if not healthy[0]:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200)
    with client_for(handler) as client:
        with pytest.raises(httpx.ConnectError):
            resilience.send(client, "GET", "https://flaky.example.test/", breaker=breaker)
        assert len(calls) == 3 and breaker.state() == "open"
        with pytest.raises(resilience.ServicePaused):
            resilience.send(client, "GET", "https://flaky.example.test/", breaker=breaker)
        assert len(calls) == 3  # nothing was sent while paused
        now[0] += 31
        assert breaker.state() == "half-open"
        healthy[0] = True
        assert resilience.send(client, "GET", "https://flaky.example.test/", breaker=breaker).status_code == 200
        assert breaker.state() == "closed"


def test_failed_trial_reopens_the_breaker(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(resilience, "clock", lambda: now[0])
    breaker = resilience.Breaker(failures_to_open=1, pause=10)
    breaker.failure("x")
    now[0] = 11
    assert breaker.allow() and not breaker.allow()  # exactly one trial
    breaker.failure("x")
    assert breaker.state() == "open"


def test_lazy_client_uses_retries_and_breaker(monkeypatch, no_waiting):
    from ai_hq.network import LazyClient
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("dropped", request=request)
        return httpx.Response(200, json={"ok": True})
    client = LazyClient(timeout=5)
    client._client = client_for(handler)
    assert client.get("https://api.example.test/").json() == {"ok": True}
    assert len(calls) == 2 and client.breaker("https://api.example.test/").state() == "closed"
    assert client.breaker("http://127.0.0.1:11434/") is not client.breaker("https://api.example.test/")
    client.close()


def test_log_is_redacted_rotated_and_never_keeps_the_file_open(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "MAX_BYTES", 200)
    logger = logs.setup(tmp_path)
    logger.warning("Saved token=abcdefghijklmnop1234 for the shop")
    assert "abcdefghijklmnop1234" not in "\n".join(logs.tail())
    assert "[REDACTED]" in "\n".join(logs.tail())
    for number in range(20):
        logger.warning("line %d %s", number, "x" * 40)
    folder = tmp_path / "logs"
    assert (folder / "cerebra.log.1").is_file() and not (folder / f"cerebra.log.{logs.KEEP + 1}").exists()
    (folder / "cerebra.log").unlink()  # not held open, so Windows can delete it


def test_older_database_gains_new_columns_and_indexes_without_losing_rows(tmp_path):
    import sqlite3
    from ai_hq.db import Database
    path = tmp_path / "old.sqlite3"
    first = Database(path)
    first.init()
    first.close()
    with sqlite3.connect(path) as connection:  # as an older Cerebra left it: a column and an index missing
        connection.execute("INSERT INTO chat_conversations (id, title, profile, created_at, updated_at) VALUES ('c1', 'Kept', 'codex', '2026-01-01', '2026-01-01')")
        connection.execute("DROP INDEX ix_tasks_state")
        connection.execute("ALTER TABLE chat_messages DROP COLUMN status")
    upgraded = Database(path)
    upgraded.init()
    upgraded.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT title FROM chat_conversations WHERE id='c1'").fetchone() == ("Kept",)
        assert "status" in {row[1] for row in connection.execute("PRAGMA table_info(chat_messages)")}
        assert connection.execute("SELECT dflt_value FROM pragma_table_info('chat_messages') WHERE name='status'").fetchone() == ("'done'",)
        assert "ix_tasks_state" in {row[1] for row in connection.execute("PRAGMA index_list(tasks)")}
    again = Database(path)
    again.init()  # a second start changes nothing
    again.close()
