# Using AI HQ

Start AI HQ with `scripts/start.ps1` and use its private browser session. The dashboard polls the local backend every three seconds while the tab is visible. Metrics, projects, task states, and events come from persisted application records; there are no decorative progress percentages.

## Understand the modes

**Mock** means the coding and review agents are simulated. It lets you exercise the supervisor without provider usage. The isolated demo is a known calculator fixture, not a general autonomous website builder. Its tests and Git operations are real.

**Live** invokes actual coding CLIs and can consume provider usage. It requires supported authenticated CLIs, the live policy, an accepted confinement policy, and a specific task approval. The user selected CLI confinement: Codex uses workspace-write for implementation and read-only for review; Claude uses read-only planning/review tools and scoped file Edit/Write for implementation. Reads outside the repository remain possible under this policy. Acceptance is not a verified OS sandbox.

The dashboard and orchestration are local. Live Codex/Claude inference still uses their providers. An installed CLI or configured policy is not evidence that a genuine task has completed; the current progress record distinguishes configuration from verified execution.

## Try the isolated demonstration

1. In Overview, choose **Try mock demo**, then **Create mock demo**.
2. Inspect **Plan & scope** in the task dialog. The objective is to repair addition in an isolated calculator repository. Check the requirements and allowed file path.
3. Select **Approve proposed plan**, then **Start approved task**.
4. Refresh the task evidence while it progresses. The supervisor creates a task branch/worktree, invokes mock implementation, runs configured tests, records mock independent review, and bounds any repairs.
5. Inspect **Evidence** for test output and review records, **Git diff** for changes, and **Runs & logs** for labeled execution artifacts.
6. In **Git & approvals**, inspect the specific integration request before approving or rejecting it. The backend revalidates integration conditions. Approval is a concrete action, not a general waiver for future tasks.

## Register a project

Use **Projects → Add project**. You may create a fresh managed repository or register an existing exact Git root. Registering an existing repository requires its absolute path and explicit authorization. AI HQ does not scan your computer for projects.

Test commands are JSON lists of literal arguments:

```json
[["python", "-m", "pytest", "-q"]]
```

The registration checkbox explicitly grants execution of the configured literal commands with your current Windows user's rights. Trust the project and test code before authorizing them. Repository path allowlists and Git worktrees do not sandbox tests. Supply a suitable Python interpreter path if the project needs its own environment. The process runner performs no shell expansion, pipelines, or `&&` interpretation. A clean committed repository is the safest baseline; the app detects conditions that prevent safe integration rather than discarding user changes.

Select a project card to make it the default project for new tasks. Each project retains its own tests, task records, protected default branch, and execution artifacts. Storage and memory remain practical limits on project count.

## Submit an objective

Choose **New task**, select the project and agent roles, describe the requested outcome, add requirements and concrete acceptance criteria, and select allowed relative repository paths. The default roles are Codex implementing and Claude reviewing. Reversed live assignment is offered only when Claude reports file-write capability. Its implementation excludes shell/network/MCP tools, and the supervisor runs configured verification commands separately. A capability probe is not proof that a genuine reversed task has succeeded. Read-only tools alone cannot ensure personal files outside a repository remain inaccessible.

Leave allowed paths blank, or enter `.`, for the registered repository scope. Enter `calculator.py` to limit that task to the named file. Do not add a leading dot unless the filename itself starts with one; `.calculator.py` is a different filename. Multiple paths use commas.

The deterministic planner records a proposed sequence of milestones. Review it before approving. This MVP creates one task per dashboard objective; it does not silently turn an open-ended product brief into a complete verified product. Dependency identifiers are available through validated task API records; the dashboard does not yet expose a dependency editor.

Plan approval and task start are separate controls. A task cannot use another task's approval or an agent's self-reported success as proof. The supervisor records execution results, real test commands, captured diffs, and review findings.

For a live task, the first **Start** requests a separate `live_execution` approval. Approve that specific request, then select **Start** again. A configured CLI still needs valid authentication. Each approval shows the recorded scope, roles, and usage notice.

## Pause, resume, and cancel

Open the task dialog:

- **Request pause** marks the task blocked, requests cancellation of managed execution, and preserves its branch and history. Process cleanup may take a moment; it does not freeze an operating-system process in place.
- **Resume task** continues paused or interrupted work after its state is inspected.
- **Cancel task** requests cancellation and process-tree cleanup. Recorded output, branches, worktrees, and task history remain for inspection.

To stop the whole application, run `scripts/stop.ps1`. Stopping while a task is active preserves its records; startup recovery marks interrupted work so it does not silently continue.

## Read evidence and approvals

Task states are `PENDING`, `PLANNING`, `READY`, `RUNNING`, `VERIFYING`, `REVIEWING`, `NEEDS_CHANGES`, `AWAITING_APPROVAL`, `COMPLETED`, `FAILED`, `BLOCKED`, and `CANCELLED`. A completed mock workflow proves orchestration of that fixture; it does not prove real AI collaboration or general correctness.

Review findings carry severity and evidence. Repair attempts are bounded at three by default, and tests run again after repairs. Failed commands, missing tests, agent errors, and conflicts remain visible. No automatic Git push or deployment follows approval.

## Agent and settings screens

**AI agents** shows tool detection, available adapter information, and limitations. A detected executable is different from verified authentication or live end-to-end readiness. **Settings** controls supported executable paths, timeouts, and retry limits. The MVP enforces one active coding assignment. **Activity log** shows recent persisted events; task details show task-specific logs.

Ollama is optional and not required to plan or execute a mock workflow. Entering an endpoint downloads no model and does not make it the supervisor. The app does not estimate actual provider billing.
