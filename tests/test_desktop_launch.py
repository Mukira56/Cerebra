import json
import os
import sys
from unittest.mock import Mock

from ai_hq.config import Settings
from ai_hq import manage


def test_existing_desktop_launch_returns_local_url_without_browser(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(manage, "owned_process", lambda settings: {"port": 18765})
    browser = Mock()
    monkeypatch.setattr(manage.webbrowser, "open", browser)
    manage.start(Settings(data_dir=tmp_path), desktop=True)
    assert json.loads(capsys.readouterr().out) == {"url": "http://127.0.0.1:18765/", "already_running": True}
    browser.assert_not_called()


def test_cli_desktop_disables_external_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("AIHQ_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["manage", "start", "--desktop"])
    start = Mock()
    monkeypatch.setattr(manage, "start", start)
    assert manage.main() == 0
    assert start.call_args.kwargs == {"desktop": True}
    assert start.call_args.args[1] is False


def _slow_server(monkeypatch, healthy_after):
    clock = {"now": 0.0, "polls": 0}
    child = Mock(pid=1234)
    child.poll.return_value = None
    monkeypatch.setattr(manage.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(manage, "owned_process", lambda settings: None)
    monkeypatch.setattr(manage, "process_identity", lambda pid: {"pid": pid})
    monkeypatch.setattr(manage.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(manage.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))

    class Healthy:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b'{"application": "AI Development HQ"}'

    def urlopen(url, timeout):
        clock["polls"] += 1
        if clock["now"] < healthy_after: raise OSError("not yet")
        return Healthy()
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return clock


def test_start_waits_for_a_slow_cold_start(tmp_path, monkeypatch, capsys):
    # A cold private runtime can take 20+ seconds to import; the old fixed 100 polls gave up after about 10.
    clock = _slow_server(monkeypatch, healthy_after=25)
    manage.start(Settings(data_dir=tmp_path, port=0), desktop=True)
    assert clock["polls"] > 100
    assert json.loads(capsys.readouterr().out)["already_running"] is False


def test_start_gives_up_after_the_startup_timeout(tmp_path, monkeypatch):
    clock = _slow_server(monkeypatch, healthy_after=10**6)
    try:
        manage.start(Settings(data_dir=tmp_path, port=0), desktop=True)
    except RuntimeError as error:
        assert "did not become healthy" in str(error)
    else:
        raise AssertionError("start should fail when the server never becomes healthy")
    assert manage.STARTUP_TIMEOUT <= clock["now"] < manage.STARTUP_TIMEOUT + 1
