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

**Done in 0.74.35: signed-in accounts** (`ai_hq/signin_models.py`), at the owner's request ("like i signed in to chatgpt and claude… i dont want to use that openrouter thing").
- Gemini CLI uses the owner's Google account and its free daily allowance. Qwen Code uses a free Qwen account.
- Each runs headless (`-p`) with JSON output, in plan (read-only) approval mode, in Cerebra's empty chat folder.
- Both are installed from Install tools and signed in in their own window, like Claude and Codex.
- They are the default routes for research, long documents, the Prompt Architect, checking, reasoning and code questions. Claude keeps writing and plans; OpenRouter is optional.
- If a tool isn't installed, isn't signed in, or has used its allowance, the owner's Claude account answers that turn.
- The Gemini CLI on the owner's computer (0.67.0) was found and its flags confirmed from `gemini --help`. A live answer is checked by the owner pressing Test on the Models page, because Cerebra's tests never call real accounts.
- DeepSeek has no sign-in tool, only a paid API, so it isn't offered (except small local models through Ollama).

**Remaining**
- Show the Gemini and Qwen sign-in status without a test call; neither tool has a status command.
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

**Done in 0.74.35**
- Each task records which model wrote its spec, or "template".
- Model intelligence compares finished tasks with and without a spec: share completed, share completed first time with no repairs, and repairs per task. Prompt quality is measured by outcomes, not by how a spec reads.

**Remaining**
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

**Done in 0.74.35:** understanding plain requests (`ai_hq/orchestrator.py`, the box on Home). A request goes to one of 11 workflows by Cerebra's own rules first, with strong phrases such as "find … jobs" outweighing passing mentions. A free model is asked only when the rules can't tell, and its answer must name a listed workflow. The owner gets a suggestion with a reason and opens the workflow; nothing starts from Home.

**Remaining**
- Splitting a request that spans several workflows into steps across them.

**Tests:** `tests/test_routing_access.py`, `tests/test_model_workforce.py`

## Phase 5: Tokens and resources

**Status:** In progress

**Done**
- Every hub call is recorded with kind of work, model, tokens (where the provider reports them), cost (zero on the free path), success and seconds. Calls through the owner's Claude and Codex accounts are recorded too.
- Each kind of work can have a daily call limit, which is a hard stop.
- Subscription balances are not shown, because Claude and Codex don't report them. Cerebra notices when a plan runs out and waits.

**Remaining**
- ~~Retrieve only the files that matter when context is needed~~ Done after 0.74.36: the Prompt Architect's outline names up to 12 files whose names match the request (camelCase and snake_case split, a source before its test), and the spec points the engineer at them. Only names are read, never contents; hidden, dependency and build folders and anything that may hold a secret are left out.
- ~~Cache repeated questions~~ Done after 0.74.35: an exact repeat of a research, checking, sorting or large-document question within 24 hours gets the saved answer instead of another call against a free allowance (`answer_cache`, keyed by a SHA-256 of kind, model and prompt; the prompt isn't stored). Writing, plans, specs and code questions are never cached, and the Models page's Test button always asks for real.
- ~~Show cost per task and per project~~ Done after 0.74.35: every coding run records the tokens and list-price equivalent its provider reported (Claude's result event, Codex's turn events; nothing estimated). Each task report shows "What it used", and Model intelligence has "Use per project" from one grouped query.
- ~~Continue non-coding work while Claude is used up~~ Done in 0.74.35: a writing turn routed to the owner's Claude account moves to a free model when Claude's plan is used up, and only then. Coding tasks still wait for Claude.

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
- ~~Tailored CV documents~~ Done after 0.74.38: each job can get a version of the owner's CV with what the posting asks for first (`Jobs.tailor_cv`), using only the CV's facts: a skill the CV doesn't name is dropped and a figure from anywhere else is refused. It becomes a text PDF (`ai_hq/resumepdf.py`, no outside library) attached to the application email, and can be saved for application forms.
- ~~Interview preparation~~ Done after 0.74.37: an interview invitation comes with notes (`Jobs.prepare`): likely questions with the CV's evidence for each, questions to ask them, and gaps to be ready for, built only from the CV, posting, employer research and their reply; a figure from anywhere else is refused.
- A general research-report workflow

## Phase 8: Computer automation

**Status:** Not started. Beyond the existing toolchain, terminal and project actions.

## Phase 9: Performance learning

**Status:** In progress

**Done**
- Measured results per kind of work and model: usable-answer rate, speed, tokens, last 30 days.
- Coding results per coder model: tasks, completed, failed.
- Recommendations require enough evidence.

**Done in 0.74.35:** "Was this result good?" on every finished task's report. Ratings are counted per coder model in Model intelligence, next to the test results.

**Remaining**
- ~~Repeatable evaluation sets~~ Done after 0.74.36: a fixed check set (`ai_hq/evals.py`) of short questions with known answers for each kind of work the hub runs, checked by Cerebra's own rules (a number, a word, valid JSON), never another model's opinion. The owner runs it from Model intelligence; scores are kept with their date and model, next to the previous run. Claude and Codex account routes aren't checked there.
- ~~Regression alerts~~ Done after 0.74.36: Model intelligence warns when a model's usable-answer rate in a kind of work this week is 20 points or more below its own previous four weeks (at least 10 calls this week and 20 before), and says what to do.

## Phase 10: Multi-project management

**Status:** In progress. Projects, task queues, dependencies and resumable tasks already exist.

**Done after 0.74.35:** **All projects at a glance** on the Projects page (`GET /api/projects/summary`): per project, the approvals waiting for the owner, tasks working, queued, stuck, done and failed, tokens used and last activity, from grouped queries over every task. Projects needing the owner come first; a name opens Tasks filtered to that project.

**Done after 0.74.36:** project priorities (high, normal, low) on the at-a-glance table; queued tasks from high-priority projects start first, oldest first within a priority (`supervisor.by_priority`).

**Remaining:** a weekly progress summary per project.

## Phase 11: Hardening

**Status:** Ongoing. 0.74.28 added retries, a circuit breaker, logging, rate limits and database upgrades; see `docs/SECURITY.md`.

---

**Also fixed in 0.74.35:** three invisible control characters in Company pitches' page finder (since it was added) kept translator, interpreter and "become a…" pages from being recognised. A source check (`tests/test_source_hygiene.py`) now fails on any control character.

**Next priority:** Phase 10's cross-project priorities, then Phase 3's templates for research and business tasks.

**Previous priority:** Phase 3, measuring downstream success. Record when a task started from an architect spec, then compare completion and first-review pass rates per architect model in Model intelligence.
