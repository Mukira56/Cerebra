"""Opening Cerebra must not set up any network connection: each TLS context costs about 2 seconds on Windows, and the
owner's local work needs none. Clients are created when a connection is first used (network.LazyClient)."""
import ssl

from ai_hq.api import create_app
from ai_hq.config import Settings


def test_creating_the_app_sets_up_no_network_connection(tmp_path, monkeypatch):
    made = []
    real = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda *args, **kwargs: made.append(1) or real(*args, **kwargs))
    create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key="k" * 40, start_worker=False)
    assert made == []
