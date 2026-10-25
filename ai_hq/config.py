from dataclasses import dataclass, field
from pathlib import Path
import os
import json

ROOT = Path(__file__).resolve().parent.parent

def default_data_dir():
    explicit = os.environ.get("AIHQ_DATA_DIR")
    if explicit:
        return Path(explicit)
    desktop = ROOT / "desktop-settings.json"
    if desktop.is_file():
        value = json.loads(desktop.read_text(encoding="utf-8"))
        location = value.get("data_dir")
        if value.get("app_id") != "AIDevelopmentHQ" or not isinstance(location, str) or not Path(location).is_absolute():
            raise ValueError("Invalid installed desktop data location")
        return Path(location)
    return ROOT / "data"

@dataclass
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    agent_timeout: int = 600
    test_timeout: int = 120
    max_retries: int = 3  # -1 = no limit
    max_concurrency: int = 1
    live_enabled: bool = False
    # Sandbox policy B: the user accepted CLI-enforced confinement and its residual read risk.
    # Loaded only from the "sandbox_policy" record written by `manage accept-cli-confinement`.
    cli_confinement_accepted: bool = False
    # Full access: the user let coding agents run any command with their Windows account and GitHub login.
    # Loaded only from the "access_policy" record written by the acknowledged Settings switch.
    full_access: bool = False
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
    access_policy = session.get(Metadata, "access_policy")
    settings.full_access = bool(access_policy and access_policy.value.get("level") == "full"
                                and access_policy.value.get("acknowledged") is True)
