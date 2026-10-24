from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("AIHQ_DATA_DIR", ROOT / "data")))
    agent_timeout: int = 600
    test_timeout: int = 120
    max_retries: int = 3
    max_concurrency: int = 1
    live_enabled: bool = False
    # Sandbox policy B: the user accepted CLI-enforced confinement and its residual read risk.
    # Loaded only from the "sandbox_policy" record written by `manage accept-cli-confinement`.
    cli_confinement_accepted: bool = False
    codex_path: str = ""
    claude_path: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    port: int = 8765
    output_limit: int = 262144

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self):
        return self.data_dir / "hq.sqlite3"


def apply_stored_policies(session, settings):
    """Load the live and sandbox policies written only by `manage` commands."""
    from .models import Metadata
    live_policy = session.get(Metadata, "live_policy")
    if live_policy:
        settings.live_enabled = live_policy.value.get("enabled") is True
    sandbox_policy = session.get(Metadata, "sandbox_policy")
    settings.cli_confinement_accepted = bool(sandbox_policy and sandbox_policy.value.get("mode") == "cli-confinement"
                                             and sandbox_policy.value.get("residual_read_risk_acknowledged") is True)
