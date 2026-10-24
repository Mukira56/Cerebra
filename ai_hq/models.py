from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, JSON, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def uid(): return uuid4().hex
def now(): return datetime.now(timezone.utc).isoformat()
class Base(DeclarativeBase): pass

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, unique=True)
    default_branch: Mapped[str] = mapped_column(String)
    test_commands: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String, default="live")  # "mock" only on pre-0.5 demo rows
    protected_branches: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String, default=now)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    description: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String, default="PENDING")
    assigned_agent: Mapped[str] = mapped_column(String, default="codex")
    reviewer: Mapped[str] = mapped_column(String, default="claude")
    mode: Mapped[str] = mapped_column(String, default="live")  # "mock" only on pre-0.5 demo rows
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    allowed_paths: Mapped[list] = mapped_column(JSON, default=lambda:["."])
    base_commit: Mapped[str] = mapped_column(String, default="")
    branch: Mapped[str] = mapped_column(String, default="")
    worktree_path: Mapped[str] = mapped_column(String, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    test_results: Mapped[list] = mapped_column(JSON, default=list)
    review_findings: Mapped[list] = mapped_column(JSON, default=list)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class Dependency(Base):
    __tablename__ = "dependencies"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)

class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    agent: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[str] = mapped_column(String, default=now)
    finished_at: Mapped[str] = mapped_column(String, default="")

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    agent: Mapped[str] = mapped_column(String)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String, default=now)

class Finding(Base):
    __tablename__ = "review_findings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"))
    severity: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, default="")
    line: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)

class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    resolved_at: Mapped[str] = mapped_column(String, default="")

class Worktree(Base):
    __tablename__ = "worktrees"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    path: Mapped[str] = mapped_column(String)
    branch: Mapped[str] = mapped_column(String)
    base_commit: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ACTIVE")

class Event(Base):
    __tablename__ = "execution_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)

class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[dict] = mapped_column(JSON, default=dict)

class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String, default="New chat")
    profile: Mapped[str] = mapped_column(String, default="codex")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"))
    role: Mapped[str] = mapped_column(String)  # user | assistant
    status: Mapped[str] = mapped_column(String, default="done")  # pending | done | failed
    provider: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)
    finished_at: Mapped[str] = mapped_column(String, default="")

class Metadata(Base):
    __tablename__ = "configuration_metadata"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)

def as_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
