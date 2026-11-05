"""Throwaway Cerebra for scripts/test_dashboard.cjs: temp data, no worker, agents off. Usage: dashboard_test_server.py <repo> <temp folder>"""
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
sys.path[:0] = [str(root), str(root / "tests")]
import uvicorn
from ai_hq.api import create_app
from ai_hq.config import Settings

app = create_app(Settings(data_dir=Path(tempfile.mkdtemp(prefix="ui-data-", dir=sys.argv[2])), port=18767),
                 bootstrap_key="ui-test-local-key-1234567890abcdefghij", start_worker=False)
supervisor = app.state.supervisor
assert not app.state.supervisor.settings.live_enabled  # agents off: the real registry refuses, and no provider can start
supervisor._refresh_registry = lambda: None  # never swap in the real CLI registry
app.state.integrations.terminal = lambda *args, **kwargs: None  # never open sign-in/install windows
uvicorn.run(app, host="127.0.0.1", port=18767, log_level="warning")
