from typing import Literal
import re
from pydantic import BaseModel, Field, ConfigDict, field_validator
from .security import relative_paths, redact

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(default="", max_length=2048)
    create_new: bool = False
    authorize: Literal[True]
    test_commands: list[list[str]] = Field(default_factory=list, max_length=10)

    @field_validator("test_commands")
    @classmethod
    def commands(cls, values):
        for command in values:
            if not command or len(command) > 50 or any(not arg or "\x00" in arg or len(arg)>4096 for arg in command):
                raise ValueError("Each test command needs a bounded list of literal arguments")
            if command[0].startswith("-"):
                raise ValueError("Executable cannot be an option")
            if any(redact(arg) != arg for arg in command):
                raise ValueError("Do not embed credentials in stored test commands")
            credential_flags = re.compile(r"^--?(?:api[-_]?key|access[-_]?token|refresh[-_]?token|token|password|passwd|secret)(?:=|$)", re.I)
            if any(credential_flags.match(arg) for arg in command):
                raise ValueError("Credential-bearing command options cannot be stored; use the provider's login flow")
        return values

class TaskCreate(StrictModel):
    project_id: str
    description: str = Field(min_length=8, max_length=30000)
    # Model profile IDs (see Models). Omitted roles use the saved defaults.
    planner: str | None = Field(default=None, max_length=120)
    implementer: str | None = Field(default=None, max_length=120)
    reviewer: str | None = Field(default=None, max_length=120)
    requirements: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    allowed_paths: list[str] = Field(default_factory=lambda:["."], min_length=1, max_length=100)

    @field_validator("allowed_paths")
    @classmethod
    def paths(cls, values): return relative_paths(values)

class ApprovalDecision(StrictModel):
    approve: bool

class SessionCreate(StrictModel):
    key: str = Field(min_length=20, max_length=200)

class SettingsUpdate(StrictModel):
    # 0 seconds means no time limit; -1 repair attempts means repair until the work passes or stops progressing.
    agent_timeout: int | None = Field(default=None, ge=0, le=86400)
    test_timeout: int | None = Field(default=None, ge=0, le=86400)
    max_retries: int | None = Field(default=None, ge=-1, le=100)
    max_concurrency: Literal[1] | None = None
    codex_path: str | None = Field(default=None, max_length=2048)
    claude_path: str | None = Field(default=None, max_length=2048)
    ollama_url: str | None = None

    @field_validator("ollama_url")
    @classmethod
    def local_ollama(cls, value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Ollama must use a loopback HTTP endpoint")
        return value

class ReviewFinding(StrictModel):
    severity: Literal["critical", "high", "medium", "low", "info"]
    path: str = ""
    line: int = Field(default=0, ge=0)
    message: str = Field(min_length=1, max_length=10000)
    validated: bool = False

class AgentTaskMessage(StrictModel):
    task_id: str
    project_id: str
    description: str
    requirements: list[str]
    acceptance_criteria: list[str]
    assigned_agent: Literal["codex", "claude"]
    dependencies: list[str]
    allowed_paths: list[str]
    base_commit: str
    branch: str
    working_directory: str
    attempt: int = Field(ge=0, le=3)

class ProfileCreate(StrictModel):
    provider: Literal["codex", "claude", "copilot", "gemini"]
    model: str = Field(default="", max_length=100)
    label: str = Field(default="", max_length=80)

class ProfileUpdate(StrictModel):
    model: str | None = Field(default=None, max_length=100)
    label: str | None = Field(default=None, max_length=80)

class RolesUpdate(StrictModel):
    planner: str | None = Field(default=None, max_length=120)
    implementer: str | None = Field(default=None, max_length=120)
    reviewer: str | None = Field(default=None, max_length=120)

class AgentPermissions(StrictModel):
    enabled: bool
    # Both acknowledgements are required to switch agents on; switching off needs neither.
    acknowledge_provider_usage: bool = False
    acknowledge_residual_read_risk: bool = False

class AutopilotUpdate(StrictModel):
    enabled: bool
    hours: int = Field(default=8, ge=1, le=72)
    auto_merge: bool = False
    auto_push: bool = False
    projects: list[str] = Field(default_factory=list, max_length=100)
    acknowledge_auto_approval: bool = False
    acknowledge_auto_merge: bool = False

class FullAccess(StrictModel):
    enabled: bool
    acknowledge_full_access: bool = False
    acknowledge_github: bool = False

class RoutingUpdate(StrictModel):
    mode: str = Field(pattern="^(rules|model)$")
    provider: str = Field(default="claude", pattern="^(codex|claude)$")
    model: str = Field(default="", max_length=100)

class SupportSettings(StrictModel):
    act_automatically: bool | None = None
    allow_approvals: bool | None = None

class ActionDecision(StrictModel):
    run: bool

class BusinessJobCreate(StrictModel):
    title: str = Field(min_length=3, max_length=120)
    kind: str = Field(pattern="^(website|service_site|listing|svg|document)$")
    brief: str = Field(min_length=20, max_length=20000)
    client: str = Field(default="", max_length=120)
    requirements: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=20)
    no_ai_requested: bool = False

class BusinessSettingsUpdate(StrictModel):
    output_root: str | None = Field(default=None, min_length=3, max_length=1024)
    hourly_rate: float | None = None
    currency: str | None = Field(default=None, max_length=3)

class BusinessExport(StrictModel):
    zip: bool = False

class BusinessOpen(StrictModel):
    what: str = Field(default="folder", pattern="^(folder|result)$")

class BusinessConnection(StrictModel):
    values: dict[str, str] = Field(default_factory=dict, max_length=8)

class BusinessExternal(StrictModel):
    action: Literal["etsy_draft", "printify_draft", "printify_upload", "image"]
    confirmed: bool = False
    original_confirmed: bool = False
    prompt: str = Field(default="", max_length=12000)
    path: str = Field(default="", max_length=1024)
    fields: dict = Field(default_factory=dict)

class OAuthFinish(StrictModel):
    redirected_url: str = Field(min_length=10, max_length=4096)

class GmailSetup(StrictModel):
    client_id: str = Field(max_length=256)
    client_secret: str = Field(max_length=200)

class NotificationSetup(StrictModel):
    ntfy_enabled: bool = False
    ntfy_server: str = Field(default="https://ntfy.sh", max_length=512)
    telegram_enabled: bool = False
    telegram_token: str = Field(default="", max_length=100)
    telegram_chat_id: str = Field(default="", max_length=32)
    only_orders: bool = False

class UpdateDownload(StrictModel):
    tag: str = Field(pattern=r"^v\d+\.\d+\.\d+$")

class ChatCreate(StrictModel):
    profile: str = Field(default="codex", max_length=120)
    project_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=120)

class CouncilCreate(StrictModel):
    project_id: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=4000)
    rounds: int = Field(default=3, ge=0)  # 0: until both models agree
    send_to_support: bool = False
    first: str = Field(default="codex", max_length=120)
    second: str = Field(default="claude", max_length=120)

class ChatSend(StrictModel):
    text: str = Field(min_length=1, max_length=20000)

class GithubClone(StrictModel):
    repository: str = Field(min_length=3, max_length=201)
    name: str = Field(default="", max_length=120)
    authorize: Literal[True]
    test_commands: list[list[str]] = Field(default_factory=list, max_length=10)

    @field_validator("test_commands")
    @classmethod
    def commands(cls, values): return ProjectCreate.commands(values)

class GithubPublish(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    visibility: Literal["private", "public"] = "private"

class DemoCleanup(StrictModel):
    confirm: Literal[True]
