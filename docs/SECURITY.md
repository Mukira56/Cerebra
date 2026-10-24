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

Plan approval, task start, live provider execution, and integration are deliberate operations. Live execution is disabled initially and cannot be enabled through a generic Settings PATCH. It requires a separate policy action acknowledging provider usage, followed by specific task approval. A CLI's output cannot grant approval or widen scope.

Integration requires the recorded approval and fresh repository checks. The system does not automatically push, force-push, deploy, publish repositories, install system software, change Windows policies, read browser credentials, or purchase services. Existing projects remain untouched until explicitly registered and authorized.

## Authentication and providers

Use each provider's own supported login flow only with explicit consent. AI HQ does not extract/store provider tokens or bypass login. A provider CLI uses its own authenticated session; any status check requires the appropriate user authorization. Detection of an executable/version is not proof that authentication is valid. No real agent run belongs in routine test execution.

Real CLI flags must be checked against installed help output, with conservative supported permissions. A missing or incompatible CLI fails closed. Live execution requires the effective live policy and either a verified external confinement boundary or the separately accepted CLI-confinement policy below. Configuration and installed providers do not prove a genuine task succeeds; current verification belongs in `progress.md`.

### Sandbox policy B: CLI confinement (opt-in, residual risk)

On 23 October 2026 the user chose policy B. This means accepting the CLIs' own confinement instead of an OS sandbox. It is recorded only by `python -m ai_hq.manage accept-cli-confinement --acknowledge-residual-read-risk`. This command:

- runs only while the server is stopped
- writes a `sandbox_policy` record to SQLite
- is undone by `revoke-cli-confinement`

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

Stop the server before backup. Preserve the complete database and worktree/repository metadata. No automatic destructive cleanup is provided. Review disk growth manually, especially on the initially space-constrained `C:` drive.

Report suspected boundary failures through local development records without including tokens or private unrelated files. A security-sensitive change requires targeted tests for path traversal, origin/session/CSRF checks, approval enforcement, process bounds, and recovery behavior.
