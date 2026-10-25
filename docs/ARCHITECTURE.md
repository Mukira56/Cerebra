# Architecture

Cerebra is a single local Python application with a dependency-free browser dashboard and SQLite persistence. It uses a deterministic supervisor so normal coordination needs no additional model, cloud service, or large resident process.

```text
Local browser (HTML / CSS / JavaScript)
  │ local session + same-origin requests + CSRF
FastAPI API ───────── SQLite / SQLAlchemy
  │                    projects, tasks, dependencies, runs,
Deterministic supervisor reviews, findings, approvals, events,
  ├─ planner + task state machine          worktrees, metadata
  ├─ agent router
  │    ├─ chat service (read-only provider conversations)
  │    ├─ Codex CLI adapter
  │    └─ Claude Code CLI adapter
  ├─ Git manager → per-task branch and worktree
  ├─ bounded process runner → actual test commands
  ├─ independent review → evidence / repair limits
  └─ human approval → checked integration

Optional Ollama interface; deterministic coordination remains the default
```

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Conservative runtime defaults and managed data paths. |
| `models.py`, `db.py` | Relational persistence, foreign keys, metadata/schema handling. |
| `schemas.py` | Validated API and structured task message boundaries. |
| `security.py` | Canonical path constraints, allowed relative paths, redaction. |
| `processes.py` | Argument-list subprocess execution, bounded output, timeouts, cancellation. |
| `agents.py` | Capability detection, model selection and the Codex/Claude CLI adapters (tasks and read-only chat). |
| `integrations.py` | Provider sign-in windows, sign-in status, toolchain detection/installs, GitHub (`gh`). |
| `profiles.py` | Model profiles (provider + model) and the default planner/coder/reviewer. |
| `catalog.py` | Known models per provider, tiered frontier/balanced/fast (Codex list read from its model cache). |
| `routing.py` | Automatic model choice per role: supervisor rules, optionally checked advice from a supervisor model. |
| `autopilot.py` | Away mode: time-limited delegation of approval gates, optional merge and push. |
| `chat.py` | Read-only chat conversations, answered in background threads. |
| `reports.py` | Plain-language task reports built from recorded facts. |
| `maintenance.py` | Explicit, backed-up removal of pre-0.5 demo records. |
| `gitops.py` | Repository inspection, locks, isolated task worktrees, diffs, integration checks. |
| `supervisor.py` | Persistent state transitions, routing, verification, independent review, bounded repair and approvals. |
| `api.py` | Loopback API, one-time session bootstrap, origin/Host controls, CSRF, frontend files. |
| `doctor.py` | Safe environment/tool checks and persisted agent detection. |
| `manage.py` | Local launch, health check, process identity tracking, owned stop, live-policy gate. |
| `ollama.py` | Optional loopback-only local model interface. |
| `static/` | Responsive dashboard; safe DOM text construction and local polling. |

## Task lifecycle

Typical success path:

```text
PENDING → PLANNING → AWAITING_APPROVAL
  explicit plan approval → READY → explicit start
RUNNING → VERIFYING → REVIEWING → AWAITING_APPROVAL
  explicit action approval + repository revalidation
COMPLETED
```

Review issues may produce `NEEDS_CHANGES` and a bounded repair/verification/review cycle. Failed operations, unmet dependencies, invalid scope, unavailable agents, cancellation, and recovery have explicit recorded outcomes. The transition implementation in `supervisor.py` is authoritative; callers cannot arbitrarily set a state through the API.

Pause is represented through `pause_requested` and the `BLOCKED` state; it signals cancellation of managed execution and preserves history. It is not an extra task-state value or an operating-system process suspension. On restart, interrupted active tasks are retained for deliberate inspection and resume. The worker is limited to one coding assignment in this MVP.

## Structured coordination

Tasks record project identity, objective, requirements, acceptance criteria, agent/reviewer roles, dependencies, allowed paths, base commit, branch, worktree path, plan approval, retries, results, findings, and timestamps. Runs retain role and simulation labels. Reviews and severity-rated findings are distinct from test results. Events record supervisor decisions. Raw execution logs remain separate from structured records.

Agents do not communicate by sharing a working directory. The supervisor hands off structured records and captured artifacts. Model output is untrusted and cannot change approval, scope, or process policy. Roles can be reversed when the selected implementer reports write capability. Claude implementation uses scoped file tools while the supervisor executes tests separately. Live execution requires effective live/confinement policies and per-task consent. CLI-confinement acceptance and verified external sandbox scope are distinct fields; accepting residual read risk must never set `scope_verified=True`. CLI read-only options do not prove restricted read scope.

## Git and verification

A coding assignment receives a baseline commit, unique branch, and dedicated worktree. Repository operations use locks and safety checks. A worktree provides file separation; it cannot constrain arbitrary processes at the operating-system level. Tests run as real argument-list commands under time/output limits and preserve results, including failure.

Integration approval is tied to a recorded task/action. Repository and task conditions are rechecked. Conflicts and unrelated changes must remain visible; they are never resolved by overwriting user files. Remote pushes and deployment are outside this MVP.

## Persistence and future extensions

SQLite uses proper foreign-key relationships and schema metadata. Keep backups while the server is stopped; future schema changes must be explicit migrations, not silent table deletion. Extensible adapter and supervisor boundaries permit richer planners, an optional LLM supervisor, additional agents, and configurable concurrency later. A future extension must retain deterministic authorization and evidence gates.
