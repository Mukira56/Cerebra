# Cerebra AI workforce: implementation roadmap

This file is the checkpoint for turning Cerebra into a coordinated AI workforce. Any session continues from here.

**Permanent rules**
- **Claude is the only premium AI service.** It is the primary software engineer, and any switch to another model needs the owner's approval.
- **Every other model must be free or local:** free OpenRouter models, local Ollama models, or Codex only while the owner's existing account covers it at no extra cost. A priced model is refused when a route is saved and again when it is called.
- **Real tests decide success.** A model's opinion never replaces a test.
- **The owner approves** every send, publish, payment, deployment and merge.

A phase is **Completed** only when its tests pass and the behaviour has been checked. Written code alone doesn't count.

---

## Phase 1: System audit and architecture foundation

**Status:** Completed (0.74.34)

**What exists**

| Area | Where | What it does |
|---|---|---|
| Coding pipeline | `ai_hq/supervisor.py` | plan → approval → code in an isolated Git worktree → the project's real tests → independent review → owner approves the merge |
| Coding router | `ai_hq/routing.py` | rates how hard a task is (rules), picks a model tier per role, and keeps the reviewer from a different company |
| Model catalog | `ai_hq/catalog.py`, `ai_hq/profiles.py` | the Claude and Codex models the owner's command-line tools offer |
| Model hub | `ai_hq/modelhub.py` | routes each kind of work to the owner's Claude or Codex account, a free OpenRouter model, or a local Ollama model, and records every call in `model_usage` |
| Direct API connections | `ai_hq/modelconnections.py` | optional and owner-supplied; not used on the free-only path |
| Security | `ai_hq/capabilities.py`, `ai_hq/security.py` | permission decisions and redaction; see `docs/SECURITY.md` |

**Gaps found**
- Codex was the default coder.
- There was no step that turns a request into a spec.
- There were no reasoning or large-document routes.
- Calls through the owner's accounts weren't measured.
- There were no per-kind daily limits.
- A local model could exceed the computer's memory.
- There was no performance comparison per kind of work.

## Phase 2: Model registry and free providers

**Status:** In progress

**Done**
- The hub's kinds of work now include **Prompt Architect**, **Reasoning and maths** and **Large documents**. Each defaults to OpenRouter's free router, and the owner picks a specific free model (such as a DeepSeek or Gemini one) from the live list. No model name is assumed.
- The live free list comes from OpenRouter itself. A priced model is refused.
- Local Ollama models are listed with their sizes. A model larger than 60% of the computer's memory is never loaded (`memory_bytes`, `too_big`).

**Remaining**
- A direct Gemini API adapter for Google AI Studio's free tier. It needs the owner's key, and the free-tier terms must be checked first.
- A health check per provider on the Models page. Today one test call per kind of work exists.
- Capability profiles from provider metadata, such as context length and tool support. Context length is read for OpenRouter models but not yet shown.

**Tests:** `tests/test_modelhub.py`, `tests/test_model_workforce.py`

## Phase 3: Prompt Architect and requirements

**Status:** In progress

**Done** (`ai_hq/architect.py`, `POST /api/architect`, the **Ask the Prompt Architect** button in New task)
- It turns a request into a goal, requirements, constraints, acceptance criteria and steps.
- Open questions and assumptions are kept apart and never added to the requirements.
- The project is described by name, test commands and top-level names only, never file contents or hidden files.
- Short, plain requests use a template with no model call. Building work always goes to the architect.
- Answers are validated; an unusable spec is refused.

**Remaining**
- Measure prompt quality by downstream success: record which tasks started from an architect spec, and compare how many completed against tasks without one.
- Templates for research, job applications and business tasks. Applications and pitches have their own prompts today.
- Instructions written for the specific receiving model.

**Tests:** `tests/test_model_workforce.py`

## Phase 4: Routing and specialisation

**Status:** In progress

**Done**
- **Claude is the lead coder** (`lead_coder: claude`) and Codex reviews independently.
- **Claude stays the coder** (`lock_coder`): when Claude runs out of usage, the task waits for it rather than moving to another company. The owner can switch a task, or turn the lock off.
- Every role's choice carries a plain reason, shown in **Model intelligence** under "Why recent tasks went where they did".
- **Performance-based routing** is optional and off by default. It only moves free-model routes, never the owner's account choices, and only after 20 calls of evidence and 10 points better.

**Remaining**
- Model-assisted classification of non-coding requests, to send a request to the right workflow.

**Tests:** `tests/test_routing_access.py`, `tests/test_model_workforce.py`

## Phase 5: Tokens and resources

**Status:** In progress

**Done**
- Every hub call is recorded with kind of work, model, tokens (where the provider reports them), cost (zero on the free path), success and seconds. Calls through the owner's Claude and Codex accounts are recorded too.
- Each kind of work can have a daily call limit, which is a hard stop.
- Subscription balances are not shown, because Claude and Codex don't report them. Cerebra notices when a plan runs out and waits.

**Remaining**
- Retrieve only the files that matter when context is needed.
- Cache repeated questions.
- Show cost per task and per project.
- Continue free-model research while Claude work is queued.

## Phase 6: Software development workflow

**Status:** Completed for the existing pipeline (plan, isolated worktree, real tests, independent review, owner-approved merge).

**Remaining:** feed the architect spec into the plan automatically. Today it fills the form for the owner to check.

## Phase 7: Jobs, freelancing and research

**Status:** In progress

**Done**
- Apply for jobs (0.74.33)
- Find work and Freelancer bidding
- Pitch companies with research dossiers
- Prospects, Books and Etsy research

**Remaining**
- Tailored CV documents
- Interview preparation
- A general research-report workflow

## Phase 8: Computer automation

**Status:** Not started. Beyond the existing toolchain, terminal and project actions.

## Phase 9: Performance learning

**Status:** In progress

**Done**
- Measured results per kind of work and model: usable-answer rate, speed, tokens, last 30 days.
- Coding results per coder model: tasks, completed, failed.
- Recommendations require enough evidence.

**Remaining**
- Repeatable evaluation sets.
- Owner feedback on finished work.
- Regression alerts.

## Phase 10: Multi-project management

**Status:** Not started on new work. Projects, task queues, dependencies and resumable tasks already exist.

## Phase 11: Hardening

**Status:** Ongoing. 0.74.28 added retries, a circuit breaker, logging, rate limits and database upgrades; see `docs/SECURITY.md`.

---

**Next priority:** Phase 3, measuring downstream success. Record when a task started from an architect spec, then compare completion and first-review pass rates per architect model in Model intelligence.
