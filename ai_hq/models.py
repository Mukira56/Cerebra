from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, JSON, Boolean, Integer, Float, Index
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
    # What the provider reported for this run (agents.usage_of). list_cost is the list-price equivalent Claude reports;
    # on the owner's subscription nothing is billed per run.
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    list_cost: Mapped[float] = mapped_column(default=0.0)

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

class BusinessJob(Base):
    """A Business Studio job: the user's brief, its output folder, and the Cerebra project/task doing the work."""
    __tablename__ = "business_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    client: Mapped[str] = mapped_column(String, default="")
    brief: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    output_dir: Mapped[str] = mapped_column(String)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | completed (exported) | cancelled
    export: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class BusinessRecord(Base):
    """A client job's delivery records: agreed scope, money in and out, customer results and change requests.
    Every figure is entered by the user (or by a confirmed check); nothing is estimated."""
    __tablename__ = "business_records"
    job_id: Mapped[str] = mapped_column(ForeignKey("business_jobs.id"), primary_key=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    scope_approved_at: Mapped[str] = mapped_column(String, default="")
    ledger: Mapped[list] = mapped_column(JSON, default=list)
    enquiries: Mapped[list] = mapped_column(JSON, default=list)
    revisions: Mapped[list] = mapped_column(JSON, default=list)
    delivery_checks: Mapped[list] = mapped_column(JSON, default=list)

class MoneyDocument(Base):
    """A quote or an invoice the owner sends a client. Amounts are the owner's own; Cerebra never takes payments."""
    __tablename__ = "money_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String)  # quote | invoice
    number: Mapped[str] = mapped_column(String, default="")  # given when issued, so numbers have no gaps
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | sent | accepted | declined | paid | void
    client: Mapped[str] = mapped_column(String, default="")
    client_email: Mapped[str] = mapped_column(String, default="")
    job_id: Mapped[str | None] = mapped_column(ForeignKey("business_jobs.id"), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)  # the quote an invoice came from
    items: Mapped[list] = mapped_column(JSON, default=list)
    currency: Mapped[str] = mapped_column(String, default="USD")
    notes: Mapped[str] = mapped_column(Text, default="")
    issued_at: Mapped[str] = mapped_column(String, default="")
    due_date: Mapped[str] = mapped_column(String, default="")
    payment_url: Mapped[str] = mapped_column(String, default="")
    payments: Mapped[list] = mapped_column(JSON, default=list)
    provider: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class Product(Base):
    """A digital product the owner sells (a template, a design pack…): its price, where buyers download it,
    its Stripe payment link and the sales Stripe reported."""
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(default=0.0)
    currency: Mapped[str] = mapped_column(String, default="USD")
    download_url: Mapped[str] = mapped_column(String, default="")
    package: Mapped[dict] = mapped_column(JSON, default=dict)
    stripe: Mapped[dict] = mapped_column(JSON, default=dict)
    sales: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | selling | paused
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class ChannelEntry(Base):
    """Money from or to a marketplace the owner sells through: an Etsy order (a sale) or a Printify order (a cost).
    Imported from the service, read-only; the ID is the service's own, so importing again only updates it."""
    __tablename__ = "channel_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "etsy:1234567890"
    source: Mapped[str] = mapped_column(String)  # etsy | printify
    kind: Mapped[str] = mapped_column(String)  # sale | cost
    amount: Mapped[float] = mapped_column(default=0.0)
    currency: Mapped[str] = mapped_column(String, default="USD")
    date: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default=now)

class RecurringPlan(Base):
    """A client the owner bills on a schedule (a monthly care plan, a retainer): each period Cerebra drafts the
    invoice from these lines, or issues it when the owner chose that. The owner still sends it."""
    __tablename__ = "recurring_plans"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    client: Mapped[str] = mapped_column(String, default="")
    client_email: Mapped[str] = mapped_column(String, default="")
    job_id: Mapped[str | None] = mapped_column(ForeignKey("business_jobs.id"), nullable=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    currency: Mapped[str] = mapped_column(String, default="USD")
    notes: Mapped[str] = mapped_column(Text, default="")
    every: Mapped[str] = mapped_column(String, default="month")  # month | quarter | year
    next_date: Mapped[str] = mapped_column(String, default="")
    auto_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    made: Mapped[list] = mapped_column(JSON, default=list)  # [{"date", "document"}]
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class FreelanceLead(Base):
    """A piece of paid work found for the owner (or pasted by them), scored against what they sell."""
    __tablename__ = "freelance_leads"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "<source>:<the source's own id>"
    source: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    url: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    budget_min: Mapped[float] = mapped_column(default=0.0)
    budget_max: Mapped[float] = mapped_column(default=0.0)
    currency: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="job")  # fixed | hourly | job
    skills: Mapped[list] = mapped_column(JSON, default=list)
    posted_at: Mapped[str] = mapped_column(String, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="new")  # new | saved | hidden | applied | interview | won | lost
    notes: Mapped[str] = mapped_column(Text, default="")
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class SocialPost(Base):
    """A post for the owner's X, Facebook Page or Instagram: a draft until the owner approves it, then published on time."""
    __tablename__ = "social_posts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    text: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String, default="")
    image_url: Mapped[str] = mapped_column(String, default="")
    channels: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | approved | posted | partial | failed
    scheduled_at: Mapped[str] = mapped_column(String, default="")
    results: Mapped[dict] = mapped_column(JSON, default=dict)  # per channel: id, url, posted_at, cost | error | waiting
    origin: Mapped[str] = mapped_column(String, default="owner")  # owner | ai
    approved_at: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class ChatAction(Base):
    """Something the support chat asked Cerebra to do, and what happened when it ran."""
    __tablename__ = "chat_actions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("chat_messages.id"))
    conversation_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="proposed")  # proposed | done | failed | dismissed
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)

class CouncilSession(Base):
    """A recorded meeting where two models discuss a project and agree on proposals (see council.py)."""
    __tablename__ = "council_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    topic: Mapped[str] = mapped_column(Text)
    first: Mapped[str] = mapped_column(String, default="codex")  # model profile ids, in speaking order
    second: Mapped[str] = mapped_column(String, default="claude")
    rounds: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String, default="running")  # running | done | stopped | failed
    error: Mapped[str] = mapped_column(Text, default="")
    proposals: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class CouncilMessage(Base):
    __tablename__ = "council_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("council_sessions.id"))
    speaker: Mapped[str] = mapped_column(String)  # model profile id
    provider: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    round: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String, default="discussion")  # discussion | closing | confirm
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | done | failed
    content: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)
    finished_at: Mapped[str] = mapped_column(String, default="")

class Plan(Base):
    """An executable plan (see work.py). Its items stay the authoritative source for the tasks made from them."""
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    source: Mapped[str] = mapped_column(String, default="owner")  # council | support | owner
    source_id: Mapped[str] = mapped_column(String, default="")  # e.g. the council session id
    version: Mapped[int] = mapped_column(Integer, default=1)
    objective: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    solution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="active")  # active | superseded | done | cancelled
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class PlanItem(Base):
    __tablename__ = "plan_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    why: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)  # ids of items in the same plan
    allowed_paths: Mapped[list] = mapped_column(JSON, default=lambda: ["."])
    implementer: Mapped[str] = mapped_column(String, default="")  # model profile ids
    reviewer: Mapped[str] = mapped_column(String, default="")
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="proposed")  # proposed | task_created | dropped
    created_at: Mapped[str] = mapped_column(String, default=now)

class ActionRecord(Base):
    """One action Support (or the owner, or Cerebra itself) asked for: its inputs and its recorded result."""
    __tablename__ = "action_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    source: Mapped[str] = mapped_column(String, default="support")  # support | council | owner | system
    conversation_id: Mapped[str] = mapped_column(String, default="")
    chat_action_id: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="")
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="running")  # running | done | failed
    outcome: Mapped[str] = mapped_column(Text, default="")
    affected: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"task_id": ..., "project_id": ...}
    error: Mapped[str] = mapped_column(Text, default="")
    next_state: Mapped[str] = mapped_column(String, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    finished_at: Mapped[str] = mapped_column(String, default="")

class BookNiche(Base):
    """A book idea: one reader with one problem, scored from the sales and search evidence the owner gathered."""
    __tablename__ = "book_niches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    area: Mapped[str] = mapped_column(String, default="")
    reader: Mapped[str] = mapped_column(String, default="")
    problem: Mapped[str] = mapped_column(String, default="")
    trend: Mapped[str] = mapped_column(String, default="")  # rising | flat | fad | "" (not checked)
    notes: Mapped[str] = mapped_column(Text, default="")
    competitors: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="idea")  # idea | researching | chosen | dropped
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class EtsyNiche(Base):
    """A keyword researched on Etsy: competition, demand, prices and tags from its public listings (ai_hq/etsy.py)."""
    __tablename__ = "etsy_niches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    keyword: Mapped[str] = mapped_column(String, index=True)
    digital_only: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String, default="")  # strong | test | weak
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class EtsyListing(Base):
    """A listing written for a researched niche: checked against Etsy's rules, sent to Etsy only as a draft the owner confirms."""
    __tablename__ = "etsy_listings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    niche_id: Mapped[str | None] = mapped_column(ForeignKey("etsy_niches.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    product: Mapped[str] = mapped_column(Text, default="")
    checks: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | ready | on_etsy
    job_id: Mapped[str] = mapped_column(String, default="")  # the Business Studio job that makes its files
    model: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)


class EtsySaleLine(Base):
    """One item in a paid Etsy order: which listing sold, how many and for how much, so sales can be traced back to the
    listing and niche Cerebra made them from. Replaced on every import of its order."""
    __tablename__ = "etsy_sale_lines"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # Etsy's transaction ID
    receipt_id: Mapped[str] = mapped_column(String, index=True)
    listing_id: Mapped[str] = mapped_column(String, index=True, default="")  # Etsy's listing ID
    shop_id: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[float] = mapped_column(Float, default=0.0)  # price x quantity, before order-level discounts
    currency: Mapped[str] = mapped_column(String, default="USD")
    date: Mapped[str] = mapped_column(String, default="")


class Book(Base):
    """A book for Amazon KDP: its formats, size, prices and where it is on the way to publishing. Its text lives in files."""
    __tablename__ = "books"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    niche_id: Mapped[str | None] = mapped_column(ForeignKey("book_niches.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, default="")
    subtitle: Mapped[str] = mapped_column(String, default="")
    pen_name: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="planned")  # planned | writing | files_ready | published | retired
    formats: Mapped[list] = mapped_column(JSON, default=list)
    trim: Mapped[str] = mapped_column(String, default="6x9")
    paper: Mapped[str] = mapped_column(String, default="white")
    pages: Mapped[int] = mapped_column(Integer, default=0)
    words: Mapped[int] = mapped_column(Integer, default=0)
    prices: Mapped[dict] = mapped_column(JSON, default=dict)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class ChiefGoal(Base):
    """A money goal the owner set for the Chief of Staff, with its rules (public data only, ask before contacting anyone)."""
    __tablename__ = "chief_goals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String, default="")
    target: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    monthly_cap: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String, default="active")  # active | paused | done
    created_at: Mapped[str] = mapped_column(String, default=now)

class ChiefJob(Base):
    """A worker on a schedule: which one, how often, on or off, and how its last run went."""
    __tablename__ = "chief_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    worker: Mapped[str] = mapped_column(String)
    goal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    every_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[str] = mapped_column(String, default="")
    last_run_at: Mapped[str] = mapped_column(String, default="")
    last_status: Mapped[str] = mapped_column(String, default="")
    last_summary: Mapped[dict] = mapped_column(JSON, default=dict)

class ChiefRun(Base):
    """One run of a job: when, how long, what it found or what went wrong."""
    __tablename__ = "chief_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(String, index=True)
    worker: Mapped[str] = mapped_column(String, default="")
    started_at: Mapped[str] = mapped_column(String, default=now, index=True)
    finished_at: Mapped[str] = mapped_column(String, default="")
    seconds: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok | skipped | failed
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    by: Mapped[str] = mapped_column(String, default="schedule")  # schedule | owner

class ProspectSearch(Base):
    """One search for local businesses: what kind, which US city, and what it found."""
    __tablename__ = "prospect_searches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String, default="")
    city: Mapped[str] = mapped_column(String, default="")
    state: Mapped[str] = mapped_column(String, default="")
    place: Mapped[str] = mapped_column(String, default="")
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)

class Prospect(Base):
    """A local business that could use what the owner sells, with the facts seen on its own website and where."""
    __tablename__ = "prospects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    search_id: Mapped[str] = mapped_column(String, default="", index=True)
    osm: Mapped[str] = mapped_column(String, default="", index=True)  # its OpenStreetMap id, so a business is found once
    name: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="")
    city: Mapped[str] = mapped_column(String, default="")
    state: Mapped[str] = mapped_column(String, default="")
    website: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="")
    facts: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="new")  # new | kept | dropped | contacted | replied | won | lost
    opener: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)

class Outbox(Base):
    """Automatic outreach to one business (ai_hq/outreach.py): the address, every email sent with when, the Gmail thread,
    when the next follow-up is due and the reply. stage: drafting | sent | followed_up | done | replied | opted_out |
    bounced | no_email | skipped."""
    __tablename__ = "outreach"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    prospect_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, default="", index=True)
    stage: Mapped[str] = mapped_column(String, default="drafting", index=True)
    thread_id: Mapped[str] = mapped_column(String, default="")
    emails: Mapped[list] = mapped_column(JSON, default=list)
    next_at: Mapped[str] = mapped_column(String, default="")
    reply: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class PartnerCompany(Base):
    """A company the owner pitches their service to (ai_hq/partners.py): its public role addresses and application pages,
    read from its own website, and every email sent with the reply. status: new | ready | forms | none | unreadable |
    sent | followed_up | replied | opted_out | bounced | applied | dropped | skipped."""
    __tablename__ = "partner_companies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String, default="")
    website: Mapped[str] = mapped_column(String, default="")
    domain: Mapped[str] = mapped_column(String, default="", index=True)
    source: Mapped[str] = mapped_column(String, default="")
    rank: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    email: Mapped[str] = mapped_column(String, default="")
    emails: Mapped[list] = mapped_column(JSON, default=list)
    pages: Mapped[list] = mapped_column(JSON, default=list)
    about: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    thread_id: Mapped[str] = mapped_column(String, default="")
    sent: Mapped[list] = mapped_column(JSON, default=list)
    next_at: Mapped[str] = mapped_column(String, default="")
    reply: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_at: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="")  # "big_tech" for big tech companies and AI labs (their own pitch)
    research: Mapped[str] = mapped_column(Text, default="")  # what the company says about itself on its own site
    personal: Mapped[str] = mapped_column(Text, default="")  # the paragraph written for this company from that research
    personal_at: Mapped[str] = mapped_column(String, default="")  # when it was written ("" = not yet)
    dossier: Mapped[dict] = mapped_column(JSON, default=dict)  # the research summary written from its pages (ai_hq/dossier.py)
    dossier_at: Mapped[str] = mapped_column(String, default="")
    research_state: Mapped[str] = mapped_column(String, default="")  # "" reading | read (all worth reading is in) | done (analysed)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class JobPosting(Base):
    """A tech job the owner can apply for (ai_hq/jobs.py), its employer's research record, the letter written for it, and
    what was sent and answered. status: ready (email given) | form (apply on their site) | sent | followed_up | replied |
    declined | bounced | applied (the owner applied on the site) | dropped."""
    __tablename__ = "job_postings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    source: Mapped[str] = mapped_column(String, default="", index=True)
    native_id: Mapped[str] = mapped_column(String, default="", index=True)
    title: Mapped[str] = mapped_column(String, default="")
    company: Mapped[str] = mapped_column(String, default="")
    company_id: Mapped[str] = mapped_column(String, default="", index=True)  # its research record in partner_companies
    location: Mapped[str] = mapped_column(String, default="")
    mode: Mapped[str] = mapped_column(String, default="remote")  # remote | hybrid | onsite
    url: Mapped[str] = mapped_column(String, default="")
    apply_email: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="ready", index=True)
    letter: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    thread_id: Mapped[str] = mapped_column(String, default="")
    sent: Mapped[list] = mapped_column(JSON, default=list)
    next_at: Mapped[str] = mapped_column(String, default="")
    reply: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now, index=True)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class CompanyPage(Base):
    """One page of a pitched company's own website, kept for its research (ai_hq/dossier.py). kind: home | about | products | ..."""
    __tablename__ = "company_pages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey("partner_companies.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    readable: Mapped[bool] = mapped_column(Boolean, default=False)
    links: Mapped[list] = mapped_column(JSON, default=list)  # on the home page: the pages worth reading next
    fetched_at: Mapped[str] = mapped_column(String, default=now)


class ModelUsage(Base):
    """One call through the model hub: which kind of work, which model, the tokens and what it cost (USD)."""
    __tablename__ = "model_usage"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    at: Mapped[str] = mapped_column(String, default=now, index=True)
    category: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(default=0.0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    seconds: Mapped[float] = mapped_column(default=0.0)

class AnswerCache(Base):
    """A free model's answer to an exact question, kept for a day so the same question isn't asked twice (modelhub.CACHED).
    The key is a SHA-256 of the kind of work, the model and the prompt; the prompt itself isn't stored."""
    __tablename__ = "answer_cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[str] = mapped_column(String, default=now, index=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)

class Metadata(Base):
    __tablename__ = "configuration_metadata"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)

# Lookups the pages and workers make constantly (task lists, a task's runs/reviews/approvals, the event feed, a chat's
# messages). SQLite does not index foreign keys by itself. db.Database.init creates any missing index on older databases.
Index("ix_tasks_state", Task.state)
Index("ix_tasks_created_at", Task.created_at)
Index("ix_dependencies_depends_on", Dependency.depends_on)
Index("ix_runs_task_id", Run.task_id)
Index("ix_reviews_task_id", Review.task_id)
Index("ix_review_findings_review_id", Finding.review_id)
Index("ix_approvals_task_id_status", Approval.task_id, Approval.status)
Index("ix_approvals_created_at", Approval.created_at)
Index("ix_worktrees_task_id", Worktree.task_id)
Index("ix_execution_events_task_id", Event.task_id)
Index("ix_execution_events_created_at", Event.created_at)
Index("ix_chat_messages_conversation_id", ChatMessage.conversation_id)
Index("ix_business_jobs_task_id", BusinessJob.task_id)

def as_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
