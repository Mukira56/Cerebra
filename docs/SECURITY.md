# Security boundaries

## Business connections (0.9.0)

Optional Etsy/Printify/image/Gmail/notification secrets use the Windows account's DPAPI through vault.py; on macOS the login Keychain and on Linux the Secret Service (`secret-tool`, secret on stdin) hold the secret, and the database keeps only a `keychain:` reference. Without a secret store, saving fails rather than storing plain text. APIs return saved/checked flags, never plaintext secrets. Service destinations are fixed for Etsy, Printify, Google and OpenAI; the user explicitly configures an HTTPS ntfy server. No application server access logging records OAuth callback query strings. Gmail callback bypasses the cross-site navigation check only on its exact GET route and still requires a single-use, expiring OAuth state and PKCE. All other API session/origin/CSRF rules remain.

Only reviewed, integrated business jobs can invoke confirmed external draft/upload/image operations. The backend records an operation reservation before sending a request. Pending and uncertain outcomes are not retried automatically, including after restart. No model/Support action can invoke these operations. Printify order creation, order import, production and publishing are not implemented: manual approval cannot be verified through the current connector. Etsy creates drafts only. Generated raster assets are explicitly post-review and require user inspection; exports include their provenance and final hashes.

Gmail requests read and send scopes during connection. The customer may grant reading only; sending requires the saved send grant and an explicit send action or enabled outreach policy. Message-to-brief intake and win tracking read messages; Gmail deletion and inbox modification are not implemented. Notifications are off by default; enabling sends task titles/states to the selected service. Treat those titles and ntfy topic URLs as potentially sensitive. A key saved locally is not proof of a working account or external API validation.

Cerebra controls local subprocesses and repository changes. Treat project code and model output as untrusted. The current implementation is intended for a single trusted Windows user on a private loopback session.

## Local access

- The server binds to `127.0.0.1`; it is not a public service.
- Startup gives the browser a random one-time key through a URL fragment. The UI exchanges it for an HttpOnly SameSite Strict session cookie, removes the fragment, and uses a per-session CSRF token on mutation requests.
- The backend validates loopback clients, Host, origin, and cross-site request context. Browser policy headers restrict scripts, styles, connections, framing, and referrers.
- The browser uses text-based DOM construction. Repository names, logs, findings, and model output are not inserted as HTML.
- Session credentials are held in memory and are not stored in SQLite. Restart invalidates browser sessions. Keep the browser session and local user account private.

Loopback authentication does not defend against a malicious process already running as your Windows user, an administrator, or a compromised browser profile. Do not expose the service through port forwarding or reverse proxies.

## Repository and execution scope

Projects require exact directory registration and explicit authorization. Canonical paths and traversal checks reject unsuitable scope; linked/junction paths are not accepted as a way around the allowlist. Task messages include allowed relative repository paths, and Git changes are checked against them.

Coding assignments use isolated task branches and worktrees. **Git worktrees are not an operating-system sandbox.** The registration checkbox explicitly grants execution of the configured literal test commands with your current Windows user's rights. Repository path allowlists do not sandbox test execution. Register trusted repositories and inspect project/test code and commands before authorizing them. Scope checks cannot make hostile project code safe.

The process runner uses argument lists instead of shell interpolation, bounded execution time/output, captured results, and process-tree cleanup. Do not configure shell launchers to circumvent this boundary. Logs are redacted before persistence/display, but no redaction mechanism can guarantee detection of every unknown secret format; avoid passing secrets in prompts, arguments, or test output.

## Human approvals

Plan approval, task start, agent execution, and integration are deliberate operations. Since 0.5.0 Cerebra has no simulated mode: every task uses real provider CLIs, so agents are switched off on a fresh install. They cannot be switched on through a generic Settings PATCH. The only switch is the dedicated **Settings › Agent permissions** action (`POST /api/permissions`), which requires a session, a CSRF token, and **both** explicit acknowledgements (provider usage, and the residual outside-repository read risk below). Switching off needs neither. The tray's *Enable live agents* and `manage enable-live` / `accept-cli-confinement` remain equivalent alternatives. Each task still needs its own plan approval and agent consent, unless the user delegated those to Away mode (below). A CLI's output cannot grant approval, turn Away mode on, or widen scope.

Integration requires the recorded approval and fresh repository checks. The system never pushes, force-pushes, deploys, or publishes on its own. **Push** and **Publish to GitHub** run only when you press them, using your own `gh`/Git credentials. The system never reads browser credentials or purchases services. Existing projects remain untouched until explicitly registered and authorized.

## Business Studio and hardening (0.8.0)

**Business Studio jobs** are new Git projects under the user's chosen output root. The root must be an absolute, dedicated folder: not a drive root, and not the profile itself.
- The brief file `cerebra-brief.json` and copied sources are committed first. They lie outside the task's allowed paths, so the creator cannot change the rules it is checked against.
- The job's test command is fixed: Cerebra's own runtime runs `business_check.py`, which uses only the standard library. SVGs with scripts, event handlers or external links fail.
- Source files must be existing regular files (not links) of up to 20 MB each. They are copied, never moved.
- Export writes into a new folder, and ZIPs are created with mode `x`, so nothing is overwritten.
- Open folder/result is confined to the job folder.
- Duplicate jobs (same title and brief while active) are refused.
- Briefs are treated as untrusted text in the task objective.
- Support's `create_business_job` action creates `origin="support"` tasks.

**Hardening:**
- Tasks created from model text (Support actions, including business jobs), and tasks retried with model-written fix instructions, run project-only even when Full access is on. The one exception is the owner's **Auto-fix Full access** grant (0.21.0, below). One function, `ai_hq/capabilities.py`, makes this decision before every agent run, and the task's origin is never rewritten (model-written instructions are marked `instructions_from`).
- The task origin is recorded at creation, so there is no window in which it is unset.
- Expired sessions are pruned.
- Responses add `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` and a restrictive `Permissions-Policy`.

**Not provided:** no system is invulnerable. The remaining risks are documented above: residual outside-repository reads, Full access by design, and the user's own test commands. This review was done by Claude, not an external penetration test.

## Support chat actions (0.7.0)

Each support message includes a bounded brief of the stored records (`support.brief`: projects, tasks, states, errors, test output, pending gates), labelled as data, not instructions.

The model may request actions in a fenced `cerebra-actions` JSON block. `support.validate` keeps only seven kinds: create_project, create_task, approve_plan, start_task, pause_task, resume_task, cancel_task.
- Tasks are referenced by hex id prefix.
- New projects are only empty folders under the data directory.
- Test commands must equal one of the fixed standard runners in `support.TEST_RUNNERS`, so model text can never define an executable command.

Actions are stored as `chat_actions` rows. They run once, through the same supervisor methods as dashboard buttons, either on the user's click or automatically if *Let support act for me* is on. Plan, run-consent and merge gates are unchanged; Away mode may answer them.

**No limits.** A run with a time limit of `0` has no deadline, and repair attempts of `-1` are unbounded. Repair still stops when an attempt produces no new change. The user can always pause or cancel.

## Full access (0.6.0, opt-in)

**Settings › Full access** (`POST /api/permissions/full-access`) is refused unless agents are switched on and both acknowledgements are ticked (machine, and GitHub). It is stored as the `access_policy` record, and switching agents off resets it.

While it is on, **implementation runs only** change:
- Codex runs with `--sandbox danger-full-access`, without the Windows elevated sandbox.
- Claude gets `Read,Grep,Glob,Edit,Write,Bash,WebFetch,WebSearch`, unscoped. It still runs with `--safe-mode`, no MCP servers, and no settings sources.
- The prompt policy tells the agent it may run commands, install dependencies, use the network and use git/gh. It must still not merge into the base branch or touch approvals.

Planning, review and chat keep their read-only flags.

## Support and Council tasks with Full access (0.30.0, opt-in)

**Settings › Full access › "Tasks that Support or the Council create for me get Full access too"** (`POST /api/permissions/assistant-full-access`, stored as `assistant_full_access`).
- **Default:** off. It needs Full access to be on and a confirmation that explains the risk: their instructions come from what the models read, so a planted instruction could reach the laptop.
- **When it applies:** `capabilities.full_access` checks it before every run, for tasks whose origin or fix instructions came from `support` or `council`. Turning it off applies to the next run.
- **Not covered:** readiness tasks.

## Money center (0.36.0)

Quotes, invoices and payments are the owner's own records in Cerebra's database. Cerebra never takes, moves or requests money, and never sends a document to a client: the owner issues each one and sends it themselves. Payment links must be `https://` addresses, and every text on the printable page is HTML-escaped. The in-app preview (`/api/money/documents/{id}/print`) gets the same sandboxed policy as Business Studio previews: no scripts, no forms, no outside connections. "Save & open" writes only inside the business output folder. Models have no tool to create, change or pay documents.

**Stripe.** The owner's key is stored with DPAPI (a restricted key is recommended: Products, Prices and Payment Links: write; Checkout Sessions: read) and never returned by the API. Creating a payment link requires `confirmed: true` from the owner's dialog for each invoice, and Stripe idempotency keys (`cerebra-<invoice>-<amount>`) prevent duplicates. Otherwise Cerebra only reads completed checkouts on links it created, and switches a link off once its invoice is paid or superseded. It never charges, refunds or transfers money. Error messages show Stripe's own text, redacted, never the key.

**Marketplace imports.** Etsy (scope `transactions_r`, through the existing authorized connection) and Printify are read with GET requests only: shop receipts and orders. Each order is stored as an amount, date and order number, with no buyer names or addresses. Nothing is created, changed, bought or fulfilled.

**Recurring plans and exports.** Recurring plans only create invoices in Cerebra's own database (drafts, or issued if the owner chose that) and never send them. The year export is written inside the business output folder with formula-like cells escaped (`'=`), so a client-supplied name can't run as a spreadsheet formula.

**Freelance leads.** The finder makes read-only GET requests to public job APIs (Freelancer.com project search, Remote OK, Remotive, Himalayas, HN Algolia). Each request carries a User-Agent naming Cerebra, sends no credentials, and keeps to each source's interval. Leads are stored locally. "Open the job page" opens only http(s) addresses, in the owner's default browser. Cerebra never bids, applies or messages anyone. Upwork and Fiverr forbid automated bidding, so jobs from them are only pasted in by the owner.

**Proposals and bids.** Proposal prompts contain only the owner's own records. The job post is wrapped as untrusted data with an instruction to ignore instructions inside it. The model returns text only, and the owner edits it before anything is sent. A bid is sent only to Freelancer.com's official API, after the owner confirms the exact amount, days and project (`confirmed: true`), and never twice for the same project. The owner's Freelancer.com OAuth token is stored with DPAPI and never returned. Upwork, Fiverr and every other platform: Cerebra only copies the text for the owner to paste.

**Social posting.** Posts go out only after the owner approves each one: drafts never post, and an edit after approval sends a post back to draft. They are sent only through the platforms' official APIs, with the owner's own app keys and tokens. Those are stored with DPAPI, never returned, and never in the model's prompt. X posts are signed with OAuth 1.0a and counted against the owner's monthly budget, and a per-channel daily limit applies. Results are saved after each channel, and failed channels are never retried automatically, so a post can't be published twice. Model-written posts arrive as drafts. The rules forbid invented clients, results or reviews and engagement bait.

**Automatic bidding and won work.** Bids are automatic only on Freelancer.com's official API, and only after the owner switches it on. They are limited by score, by a daily number and by the client's budget, and the model may decline a poor fit. Account, limit and connection errors stop a round. Upwork and Fiverr are never automated. Win tracking uses Gmail read access for messages from upwork.com, fiverr.com and freelancer.com, each once. Separately, manual replies and outreach require the customer’s Gmail send grant and the relevant send action or opt-in. Accepting a Freelancer.com award is a commitment, so it is the owner's click unless they turn on "accept awards by myself". Won work runs as a Business Studio job whose plan and agent steps Cerebra answers. Its merge, the delivery, always waits for the owner. The client's post enters the brief marked as untrusted data.

**Products.** Packages are built only from a registered project or business job. They always leave out `.git`, `node_modules` and other installed or cached folders, `.env*` settings files (examples are kept), `*.key`, `*.pem`, `*.p12`, `*.pfx` and databases. They are capped at 200 MB and 5,000 files and written only inside the business output folder. The download link must be `https://`, and Cerebra never uploads the package anywhere: the owner does. Buyer emails reported by Stripe are stored locally with the sale and never sent anywhere by Cerebra.

## Settings files for test runs (0.31.0)

A project's real settings files (`.env*`, not examples) are copied from the project folder into a task's working copy only for the duration of Cerebra's own test run, then deleted (in a `finally`, so a crash doesn't leave them). AI runs happen before or after test runs, never during them, so the models don't see these files; a test asserts this for the planner, coder and reviewer. Project cards list missing setting names from `.env.example` only, never values. Since 0.35.0, a task whose tests fail while the project has only an example settings file waits for the owner (`needs_settings`) instead of asking the AI to repair it; its message names the settings, never values, and the AI is never asked to invent secrets. The owner's “Create <file> and open it” copies the example (names and placeholders, no values) to the path the example names or `.env` beside it, only inside the project, only when `git check-ignore` confirms Git ignores it, and never over an existing file; it opens in Notepad for the owner to fill in.

## About you (0.30.0)

The owner's public-profile details (`owner_profile`) are sent to the providers in Support, Council and planning or coding prompts only while "share with the AI team" is on. Reviewers never receive them. The form says not to enter passwords or keys, and values pass through `redact`.

## Auto-fix (0.21.0, opt-in)

**Settings › Auto-fix** (`PUT /api/auto-fix`), stored as the `auto_fix` record, is off by default.
- **What it does:** when a task fails, Cerebra opens that task's fix chat and sends the failure to the Assistant. The Assistant acts without asking, using only its fixed action vocabulary (retry with fix instructions, set test commands, resume, ask the Council).
- **Which tasks:** only the tasks the owner ticks (`scope: selected`, the default, from 0.22.0), or every failed task (`scope: all`). A stopped task is never fixed until the owner ticks it again.
- **Limits:** each new failure is one attempt, up to `max_attempts` (default 4). After that Cerebra stops and records that the task needs the owner.
- **The Council:** after `council_after` failed fixes (default 2), the failure goes to a Council meeting. Its agreed solution, which can be a restructure as plan tasks, is sent back for the Assistant to apply.
- **Approvals stay as they are:** merges wait for the owner unless Away mode or "May answer approvals" says otherwise.
- **The Full access grant:** `full_access` is accepted only while Full access is on. With it, fix runs of tasks under Auto-fix keep Full access even though a model wrote their instructions. This is the owner's informed choice: a planted instruction in a project file could then reach the laptop and GitHub.
- **Revoking:** turning the grant or Full access off, or pressing a task's **Stop auto-fix** (`POST /api/tasks/{id}/auto-fix`), applies to the next agent run. Stop also stops that task's fix chat and Council meeting and pauses a fix run in progress.

This deliberately removes the write and network boundary on the user's machine. Prompt injection from repository content can then run arbitrary commands with the user's Windows account and GitHub credentials. The supervisor's controls still apply to what reaches the project: path validation of the worktree diff, branch checks, registered tests, independent review, and merge approval. They cannot undo side effects outside the worktree.

**Routing.** Automatic model choice is rule-based by default (`routing.py`). With *Ask a supervisor model*, a read-only chat turn in the empty chat workspace returns JSON. The supervisor accepts it only if every model is in the catalog and the reviewer's provider differs from the coder's; otherwise the rules' choice stands. The model's text never becomes a command.

The Codex catalog is read from `~/.codex/models_cache.json`, which holds model names and descriptions only. `auth.json` and other credential files are never read.

## Away mode: delegated approvals (0.5.1)

**Settings › Away mode** (`PUT /api/autopilot`) is a time-limited delegation of approval gates. It is refused unless agents are switched on and the acknowledgement is ticked. It expires after 1 to 72 hours, and switching agents off ends it. While it is active, the supervisor answers pending `plan`, `live_execution` and `review_findings` gates (repair stays bounded by the retry limit), optionally only for chosen projects. It records an `autopilot` event for each gate it answers.

`merge` gates are answered only if the user separately opted into automatic merging with its own acknowledgement. Even then, the latest registered test run must have fully passed, and the merge goes through the same stale-candidate checks as a manual merge.

Away mode changes nothing about execution scope:
- the same worktrees, allowed paths, CLI confinement and residual read risk apply
- no push, publish, install or network access
- no access outside the task worktree beyond what the CLIs already had

**Sign out** runs only the tool's own logout command (`codex logout`, `claude auth logout`, `gh auth logout --hostname github.com --user <account>`). Cerebra never held the credential.

## Sign-in, toolchain installs, chat, and GitHub (0.5.0)

- **Sign-in** opens the provider's own login command in a visible terminal window that you complete:
  - `codex login`
  - `claude auth login`
  - `gh auth login --web`
  - `copilot` or `gemini` (then `/login`)

  Cerebra never receives, reads or stores passwords, tokens or API keys. **Check sign-in** runs only the tool's status command (`codex login status`, `claude auth status --json`, `gh auth status`). It keeps only the signed-in flag, account name, method and plan, with redaction applied.
- **Toolchain installs** run only on a click. Each one runs a command from the fixed list in `integrations.py` (winget package IDs, or `npm install -g` for the agent CLIs) in a visible PowerShell window that you can watch or close. No argument comes from the browser, and every argument is PowerShell single-quote literal, so `@`, `$` and `;` stay inert.
- **Chat** is read-only. Codex runs with `--sandbox read-only`, and Claude with Read/Grep/Glob tools only. Chat runs inside the chosen project folder, or an empty `chat-workspace` folder. Chat cannot edit files or run write commands; code changes go through a task. Each message is a real provider call on your account. Messages are redacted before they are stored, and any answer interrupted by a restart is marked failed.
- **Model profiles** store only a provider name and a model name, validated against `^[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,99}$`. The model reaches the CLI as a single `-m`/`--model` argument. The reviewer must be a different provider from the coder. GitHub Copilot CLI and Gemini CLI can be installed and signed in, but they cannot run tasks or chat until an adapter for them has been verified.
- **GitHub clone** accepts only `owner/name` and clones into the Cerebra data folder. The cloned project still needs your trust tick for its test commands.
- **Old demo data cleanup** runs only when you press it. It first backs up the database to `data\backups`. It then deletes only `mode="mock"` tasks and the demo-only projects/working copies that live inside Cerebra's own `projects`/`worktrees` folders.

## Authentication and providers

Use each provider's own supported login flow only with explicit consent. Cerebra does not extract/store provider tokens or bypass login. A provider CLI uses its own authenticated session; any status check requires the appropriate user authorization. Detection of an executable/version is not proof that authentication is valid. No real agent run belongs in routine test execution.

Real CLI flags must be checked against installed help output, with conservative supported permissions. A missing or incompatible CLI fails closed. Live execution requires the effective live policy and either a verified external confinement boundary or the separately accepted CLI-confinement policy below. Configuration and installed providers do not prove a genuine task succeeds; current verification belongs in `progress.md`.

### Sandbox policy B: CLI confinement (opt-in, residual risk)

On 23 October 2026 the user chose policy B. This means accepting the CLIs' own confinement instead of an OS sandbox. It is recorded as a `sandbox_policy` record in SQLite, in one of two ways:

- **Settings › Agent permissions**, which requires both acknowledgements; switching off there revokes it
- `python -m ai_hq.manage accept-cli-confinement --acknowledge-residual-read-risk`, which runs only while the server is stopped and is undone by `revoke-cli-confinement`

A Settings PATCH cannot set it. Accepting this policy records `confinement_mode=cli-confinement`; it must **not** set `scope_verified=True`. It does **not** enable live execution by itself: that still needs the live policy, supported authenticated CLIs, and per-task approval.

Under policy B:

- Claude uses read-only tools for planning and independent review (Read, Grep and Glob in `dontAsk` mode). Implementation additionally permits Edit/Write through CLI rules for the task's allowed paths and denies `.git` edits. Shell/network/MCP tools are excluded. The supervisor executes authorized tests separately.
- Codex runs with `--sandbox read-only` for review and planning, and with `workspace-write` for implementation. On Windows the adapter also passes `-c windows.sandbox="elevated"`, because `--ignore-user-config` otherwise drops the sandbox mode and Codex rejects every command.
  - Measured on a validation host on 23 October 2026 with `codex sandbox -P :workspace` (Codex CLI 0.163.0), outside `%TEMP%`:
    - writes inside the workspace: allowed
    - writes to a sibling folder or the parent folder: **blocked**
    - network: **blocked**
    - reads outside the workspace: **allowed**
  - `%TEMP%` is writable by Codex's design.
  - The elevated sandbox depends on Codex's one-time Windows sandbox setup. Each customer must complete the provider's setup on their own computer; these historical measurements do not verify that computer.
- **Residual risk: outside-repository reads remain possible with your Windows account's rights.** Read-only tools and CLI write restrictions do not establish OS read isolation.

Use the accepted policy for trusted project/test code and the explicit task scope. It does not grant unrelated operations or permission to extract secrets. To revoke it, stop the application, run `manage revoke-cli-confinement`, and restart. The supervisor, dashboard, logs, and Git operations are local; provider inference can send task/workspace content to Codex/Claude services under their account settings.

## Prospector (0.55.0)
Reads only public data: OpenStreetMap (Nominatim, Overpass) and one home page per business.
- **Every request** carries an identifying User-Agent.
- **robots.txt is respected,** and pages are capped at 1 MB with a 15 s timeout.
- **Each host and redirect target must resolve only to public internet addresses,** so a website listed on the public map can never make Cerebra reach the owner's own network.
- **Only facts are stored, never page content.**
- **Nothing contacts a business.**

## Data and operations

SQLite, raw logs, worktrees, and managed repositories are local application data under the chosen data directory. No provider credentials should be stored there. The managed-server stamp contains process identity, not a launch secret. Stop verifies PID, executable, and creation time before acting, to avoid killing a reused PID or unrelated Python process.

Stop the server before backup. Preserve the complete database and worktree/repository metadata. No automatic destructive cleanup runs; the only deletion is the explicit, backed-up demo cleanup described above. Review disk growth manually, especially on the initially space-constrained `C:` drive.

Report suspected boundary failures through local development records without including tokens or private unrelated files. A security-sensitive change requires targeted tests for path traversal, origin/session/CSRF checks, approval enforcement, process bounds, and recovery behavior.
