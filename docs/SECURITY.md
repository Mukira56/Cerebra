# Security boundaries

AI HQ controls local subprocesses and repository changes. Treat project code and model output as untrusted. The current implementation is intended for a single trusted Windows user on a private loopback session.

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

Plan approval, task start, agent execution, and integration are deliberate operations. Since 0.5.0 AI HQ has no simulated mode: every task uses real provider CLIs, so agents are switched off on a fresh install. They cannot be switched on through a generic Settings PATCH. The only switch is the dedicated **Settings › Agent permissions** action (`POST /api/permissions`), which requires a session, a CSRF token, and **both** explicit acknowledgements (provider usage, and the residual outside-repository read risk below). Switching off needs neither. The tray's *Enable live agents* and `manage enable-live` / `accept-cli-confinement` remain equivalent alternatives. Each task still needs its own plan approval and agent consent, unless the user delegated those to Away mode (below). A CLI's output cannot grant approval, turn Away mode on, or widen scope.

Integration requires the recorded approval and fresh repository checks. The system never pushes, force-pushes, deploys, or publishes on its own. **Push** and **Publish to GitHub** run only when you press them, using your own `gh`/Git credentials. The system never reads browser credentials or purchases services. Existing projects remain untouched until explicitly registered and authorized.

## Away mode: delegated approvals (0.5.1)

**Settings › Away mode** (`PUT /api/autopilot`) is a time-limited delegation of approval gates. It is refused unless agents are switched on and the acknowledgement is ticked. It expires after 1 to 72 hours, and switching agents off ends it. While it is active, the supervisor answers pending `plan`, `live_execution` and `review_findings` gates (repair stays bounded by the retry limit), optionally only for chosen projects. It records an `autopilot` event for each gate it answers.

`merge` gates are answered only if the user separately opted into automatic merging with its own acknowledgement. Even then, the latest registered test run must have fully passed, and the merge goes through the same stale-candidate checks as a manual merge.

Away mode changes nothing about execution scope:
- the same worktrees, allowed paths, CLI confinement and residual read risk apply
- no push, publish, install or network access
- no access outside the task worktree beyond what the CLIs already had

**Sign out** runs only the tool's own logout command (`codex logout`, `claude auth logout`, `gh auth logout --hostname github.com --user <account>`). AI HQ never held the credential.

## Sign-in, toolchain installs, chat, and GitHub (0.5.0)

- **Sign-in** opens the provider's own login command in a visible terminal window that you complete:
  - `codex login`
  - `claude auth login`
  - `gh auth login --web`
  - `copilot` or `gemini` (then `/login`)

  AI HQ never receives, reads or stores passwords, tokens or API keys. **Check sign-in** runs only the tool's status command (`codex login status`, `claude auth status --json`, `gh auth status`). It keeps only the signed-in flag, account name, method and plan, with redaction applied.
- **Toolchain installs** run only on a click. Each one runs a command from the fixed list in `integrations.py` (winget package IDs, or `npm install -g` for the agent CLIs) in a visible PowerShell window that you can watch or close. No argument comes from the browser, and every argument is PowerShell single-quote literal, so `@`, `$` and `;` stay inert.
- **Chat** is read-only. Codex runs with `--sandbox read-only`, and Claude with Read/Grep/Glob tools only. Chat runs inside the chosen project folder, or an empty `chat-workspace` folder. Chat cannot edit files or run write commands; code changes go through a task. Each message is a real provider call on your account. Messages are redacted before they are stored, and any answer interrupted by a restart is marked failed.
- **Model profiles** store only a provider name and a model name, validated against `^[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,99}$`. The model reaches the CLI as a single `-m`/`--model` argument. The reviewer must be a different provider from the coder. GitHub Copilot CLI and Gemini CLI can be installed and signed in, but they cannot run tasks or chat until an adapter for them has been verified.
- **GitHub clone** accepts only `owner/name` and clones into the AI HQ data folder. The cloned project still needs your trust tick for its test commands.
- **Old demo data cleanup** runs only when you press it. It first backs up the database to `data\backups`. It then deletes only `mode="mock"` tasks and the demo-only projects/working copies that live inside AI HQ's own `projects`/`worktrees` folders.

## Authentication and providers

Use each provider's own supported login flow only with explicit consent. AI HQ does not extract/store provider tokens or bypass login. A provider CLI uses its own authenticated session; any status check requires the appropriate user authorization. Detection of an executable/version is not proof that authentication is valid. No real agent run belongs in routine test execution.

Real CLI flags must be checked against installed help output, with conservative supported permissions. A missing or incompatible CLI fails closed. Live execution requires the effective live policy and either a verified external confinement boundary or the separately accepted CLI-confinement policy below. Configuration and installed providers do not prove a genuine task succeeds; current verification belongs in `progress.md`.

### Sandbox policy B: CLI confinement (opt-in, residual risk)

On 23 October 2026 the user chose policy B. This means accepting the CLIs' own confinement instead of an OS sandbox. It is recorded as a `sandbox_policy` record in SQLite, in one of two ways:

- **Settings › Agent permissions**, which requires both acknowledgements; switching off there revokes it
- `python -m ai_hq.manage accept-cli-confinement --acknowledge-residual-read-risk`, which runs only while the server is stopped and is undone by `revoke-cli-confinement`

A Settings PATCH cannot set it. Accepting this policy records `confinement_mode=cli-confinement`; it must **not** set `scope_verified=True`. It does **not** enable live execution by itself: that still needs the live policy, supported authenticated CLIs, and per-task approval.

Under policy B:

- Claude uses read-only tools for planning and independent review (Read, Grep and Glob in `dontAsk` mode). Implementation additionally permits Edit/Write through CLI rules for the task's allowed paths and denies `.git` edits. Shell/network/MCP tools are excluded. The supervisor executes authorized tests separately.
- Codex runs with `--sandbox read-only` for review and planning, and with `workspace-write` for implementation. On Windows the adapter also passes `-c windows.sandbox="elevated"`, because `--ignore-user-config` otherwise drops the sandbox mode and Codex rejects every command.
  - Measured on this laptop on 23 October 2026 with `codex sandbox -P :workspace` (Codex CLI 0.163.0), outside `%TEMP%`:
    - writes inside the workspace: allowed
    - writes to a sibling folder or the parent folder: **blocked**
    - network: **blocked**
    - reads outside the workspace: **allowed**
  - `%TEMP%` is writable by Codex's design.
  - The elevated sandbox depends on Codex's one-time Windows sandbox setup, which already exists on this laptop.
- **Residual risk: outside-repository reads remain possible with your Windows account's rights.** Read-only tools and CLI write restrictions do not establish OS read isolation.

Use the accepted policy for trusted project/test code and the explicit task scope. It does not grant unrelated operations or permission to extract secrets. To revoke it, stop the application, run `manage revoke-cli-confinement`, and restart. The supervisor, dashboard, logs, and Git operations are local; provider inference can send task/workspace content to Codex/Claude services under their account settings.

## Data and operations

SQLite, raw logs, worktrees, and managed repositories are local application data under the chosen data directory. No provider credentials should be stored there. The managed-server stamp contains process identity, not a launch secret. Stop verifies PID, executable, and creation time before acting, to avoid killing a reused PID or unrelated Python process.

Stop the server before backup. Preserve the complete database and worktree/repository metadata. No automatic destructive cleanup runs; the only deletion is the explicit, backed-up demo cleanup described above. Review disk growth manually, especially on the initially space-constrained `C:` drive.

Report suspected boundary failures through local development records without including tokens or private unrelated files. A security-sensitive change requires targeted tests for path traversal, origin/session/CSRF checks, approval enforcement, process bounds, and recovery behavior.
