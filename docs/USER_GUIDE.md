# Using AI HQ

AI HQ is a local command center where real AI coding agents work on your projects:
- OpenAI **Codex** and Anthropic **Claude Code** do the work.
- GitHub Copilot CLI and Gemini CLI can be installed and signed in, and their task support is coming later.

A plain Python **supervisor** directs every step, runs your project's real tests, and asks your permission before anything important happens. There is no demo or simulated mode: every task is real work on your accounts.

## First-time setup (about 5 minutes)

The **Overview** page shows a *Get started* checklist:

1. **Toolchain**: check what is installed.
   - Install anything that's missing: Git, Node.js, Python, the Codex CLI, Claude Code, the GitHub CLI and more.
   - **Install** opens a visible window running the official installer (winget or npm). Restart AI HQ afterwards so it finds the new tools.
2. **Models & sign-in**: press **Sign in** for Codex and for Claude.
   - Each tool opens its own login window. Your password goes only to OpenAI or Anthropic; AI HQ never sees it, and you don't need API keys.
   - Press **Check sign-in** to confirm.
3. **Settings › Agent permissions**: tick both boxes and press **Switch agents on**. This is a one-time permission; every task still asks you before agents run.
4. **Projects › Add project**: pick an existing folder, a new empty project, or **Clone from GitHub**.
   - Add the project's **test commands**, for example `[["python","-m","pytest","-q"]]` or `[["npm","test"]]`. AI HQ uses them to prove that the AI's code works.
5. **Tasks › New task**: describe what you want.

## How a task works

```
You describe it ─► Plan ─► you approve ─► Start ─► you allow agents ─► Planner AI ─► Coder AI ─► Tests ─► Reviewer AI ─► you approve merge ─► Done
                                                                                                  ▲            │
                                                                                                  └── repair ◄──┘ (if tests fail, up to 3 times)
```

- **Planner** (Claude by default) reads the project and writes an architecture plan. It cannot change files.
- **Coder** (Codex by default) writes code in a *separate working copy* (a Git worktree on its own branch). It may only change the files you allowed. Codex's writes are sandboxed to that copy, and it has no network access.
- **Tests**: the supervisor itself runs your test commands. The AI cannot fake this step.
- **Reviewer** must be a *different* provider from the coder. It checks a frozen snapshot of the code and cannot change it.
- **Merge**: only after you say yes is the finished code merged into your project's main branch. Nothing is pushed to GitHub unless you press **Push**.

Watch it live in the **System view**, a map of every backend part that lights up as work flows through it. Click a part to see what it does and where it lives.

## Where results are saved

Everything stays on this computer, in the data folder shown in **Settings › Where your data lives**:

| What | Where | What it is |
|---|---|---|
| Every task, step, test result and decision | `data\hq.sqlite3` | A small database file |
| The AI's working copies | `data\worktrees\…` | One folder per task, on branch `ai-hq/<task>-…` |
| What each AI said | `data\logs\<run-id>.log` | One text file per AI run, with secrets removed |
| The AI's plan | `data\artifacts\<task-id>\architecture.md` | A Markdown file |
| Projects created or cloned here | `data\projects\…` | Normal Git repositories |
| Backups made by the demo cleanup | `data\backups\…` | Database copies |
| Your finished code | Your project folder | Merged only after your approval |

**Reports** explains each task in short, simple sentences:
- what you asked for
- who helped
- what happened, step by step
- whether the tests passed
- which files changed
- where everything is saved
- what happens next

Open **Reports** from the sidebar, or press **Plain report** in any task. Each report opens on its own page that you can simply read through.

## Chat

**Chat** lets you talk to Codex or Claude about a project: ask how something works, plan a feature, or get a second opinion.
- Chat is **read-only**: the agent can read the chosen project, but it never changes files. To change code, create a task.
- Each message uses your provider account, just like a task.
- Chats are saved, and you can delete them.

## Models

In **Models & sign-in**:
- **Add model** pairs a provider with a model name, for example Claude with `opus` or `sonnet`, or Codex with any model your plan offers. Leave the name blank for the tool's default.
- **Default AI team** chooses who plans, codes and reviews new tasks. Each task can override these choices.

## GitHub

**GitHub › Connect GitHub** signs in through the official GitHub CLI. Then you can:
- see your repositories, and clone one as a project
- **Publish** a local project to a new private or public GitHub repository
- **Push** a project's main branch after you have approved merges

## Pause, resume, cancel

Open a task:
- **Pause** stops the current step and keeps everything.
- **Resume** continues the task.
- **Cancel** stops the task for good. Its history and branch are kept for inspection.
- Stopping AI HQ from the tray keeps all records. Interrupted work waits for you to press Resume.

## Old demo data

Versions before 0.5 had a simulated calculator demo. **Settings › Old demo data** removes those records after backing up the database. Your real projects and tasks are kept.
