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
