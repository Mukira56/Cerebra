# Using Cerebra

Cerebra is a local command center where real AI coding agents work on your projects:
- OpenAI **Codex** and Anthropic **Claude Code** do the work.
- GitHub Copilot CLI and Gemini CLI can be installed and signed in, and their task support is coming later.

A plain Python **supervisor** directs every step, runs your project's real tests, and asks your permission before anything important happens. There is no demo or simulated mode: every task is real work on your accounts.

## First-time setup (about 5 minutes)

The **Overview** page shows a *Get started* checklist:

1. **Toolchain**: check what is installed.
   - Install anything that's missing: Git, Node.js, Python, the Codex CLI, Claude Code, the GitHub CLI and more.
   - **Install** opens a visible window running the official installer (winget or npm). Restart Cerebra afterwards so it finds the new tools.
2. **Models & sign-in**: press **Sign in** for Codex and for Claude.
   - Each tool opens its own login window. Your password goes only to OpenAI or Anthropic; Cerebra never sees it, and you don't need API keys.
   - Press **Check sign-in** to confirm. Once you're signed in, the button becomes **Sign out**, which runs the tool's own logout.
3. **Settings › Agent permissions**: tick both boxes and press **Switch agents on**. This is a one-time permission; every task still asks you before agents run.
4. **Projects › Add project**: pick an existing folder, a new empty project, or **Clone from GitHub**.
   - Add the project's **test commands**, for example `[["python","-m","pytest","-q"]]` or `[["npm","test"]]`. Cerebra uses them to prove that the AI's code works.
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

## Business Studio

**Business Studio** turns a client brief, or your own product idea, into original files saved on your laptop.

1. Press **+ New business job**. Give it a title, pick what to make, and paste the brief. Optionally add requirements and the full paths of your own reference files (they are copied, never changed).
   - What it can make: a website package (index.html, styles.css, README), listing copy (title, description, tags), an original SVG design, or a written document.
2. Approve its plan. Away mode can do this for you.
3. Cerebra's AI team works on it:
   - a planner plans,
   - a creator makes the files,
   - Cerebra checks the files with fixed rules: required files exist; the SVG is valid and self-contained; the web page has a title and meta tags; listing titles and tags are within limits,
   - a second AI from the other company reviews the work.
4. Approve the result. Only then are the files merged into the job folder.
5. Press **Export** or **Export ZIP**. Cerebra writes the deliverables plus a README, a manifest (with a checksum for every file) and the review findings into an `export` folder.
   - Existing files are never overwritten; each export gets a new folder.
   - **Open folder** and **Open result** show them in Explorer.

Jobs are saved in `Documents\Cerebra Business` (change it on the Business Studio page), one folder per job. Each job's page explains in plain words what you asked for, what passed, what needs attention, which files were made, where they are, and the next step. **Technical details** shows the full task record.

The stages mean:
- **Exported**: a reviewed package exists on your laptop. Nothing has been sold, published or delivered.
- **Failed**: the checks or the review did not pass.
- If a client asks for no AI, tick the box. Cerebra refuses the job.

Images: Cerebra has no image-generation service connected, so it makes vector (SVG) designs only. Raster images are shown as unavailable.

Marketplaces:
- **Fiverr** has no seller API. Paste each order's brief into Business Studio or Support, and deliver the exported files yourself.
- **Etsy** and **Printify** are not connected yet (see the cards on the page).

Support can start a business job for you too. Ask it, for example: "Make listing copy for my sunrise print."

## Support

**Support** is your support engineer. Every message includes the live record of all your projects and tasks: states, errors, test output and what's waiting for you. So you can ask:
- "Where are we in EstatePilot, and why did it fail?"
- "What is waiting for my approval?"
- "Build me a booking web app." Support plans it and proposes the project and tasks.
- "Here is a client's request: …" Support works out what the client really wants, lists questions to ask, drafts a reply for you to send, and plans the work.

When Support wants to do something (create a project, create a task, approve a plan, start, pause, resume or cancel a task), its answer shows an **action card**.
- Press **Do it** to run it, or **Dismiss**.
- Tick **Let support act for me** to run actions straight away.
- Approval steps still ask you, unless Away mode is on. With both on, Cerebra plans, creates and runs the work by itself.

Support can read the chosen project's files but never edits them directly; code is written by tasks.
- Projects it creates are new, empty folders in Cerebra's data folder.
- Their tests must be a standard runner (`npm test`, `python -m pytest -q`, `dotnet test`, `go test ./...`, `cargo test` and similar). Other test commands you set yourself on the Projects page.
- **→ Make it a task** still turns your last message into a task by hand.

Each message uses your provider account. Chats are saved, and you can delete them.

### Freelance platforms and email

Cerebra does not log in to Upwork, Fiverr or Gmail, bid on jobs, or message clients on its own:
- Fiverr has no public API for sellers.
- Upwork's API needs an approved developer application, and its terms prohibit automated proposals.
- Sending messages to clients as you, without them knowing it's an AI, risks your accounts and misleads the people paying you.

Instead, paste a job post or client email into Support. It breaks down the requirements, writes the questions and the reply for you to send, and turns the work into a project and tasks that run on their own (with **Let support act for me** and **Away mode**).

## Limits

In **Settings › Limits & programs**, each limit has a **No limit** box:
- **AI run time** and **Test time**: with no limit, a run continues until it finishes. Use Pause or Cancel to stop it.
- **Automatic repair attempts**: with no limit, Cerebra keeps sending failures back for repair until the tests and review pass. It stops as soon as an attempt changes nothing.

No limit can use a lot of your plan's usage on a stubborn task.

## Models

In **Models & sign-in**:
- **Available models** lists every model you can use.
  - Claude: Opus 5.5 (frontier), Sonnet 5.5 (balanced), Haiku 5.5 (fast), and Fable 5.1.
  - ChatGPT/Codex: the list comes from your own Codex app, so new OpenAI models appear by themselves, for example GPT-6-Astra (frontier), GPT-6.1-Sol (balanced) and GPT-6-Luna (fast).
- **Default AI team** sets the planner, coder and reviewer for new tasks. Choose a model for each role, or **Auto**. Each new task can change these.
- **Auto** lets the supervisor decide:
  - It rates the task. Words like *architecture*, *security* or *refactor* make it hard; *typo*, *rename* or *readme* make it small.
  - Hard work gets frontier models, everyday work gets balanced ones, and small jobs get fast ones.
  - Claude plans and reviews; Codex writes the code, except documentation, which goes to Claude.
  - The reviewer always comes from the other company.
  - The task's window shows what was decided and why.
- **Supervisor: who picks the models** chooses how Auto works.
  - **Supervisor rules** is instant and free.
  - **Ask a supervisor model** (for example Claude Opus 5.5) lets that model read the task and choose. Its answer is used only if every pick is a listed model and the reviewer is still from the other company; otherwise the rules' choice stays. Asking uses your plan, like any message.
- **Add model** saves your own provider + model pair under a name.

## Full access: let the agents use your laptop and GitHub

By default, the coding agent changes only the files the task allows, in a separate copy of the project.

**Settings › Full access** removes that limit for coding runs:
- Codex runs without its sandbox.
- Claude gets the shell, the web and all file tools.
- Both can install software, use the network, change files anywhere your Windows account can, and use your GitHub login (push, open pull requests, create or change repositories).

Turning it on takes two ticks. Switching agents off also turns it off.

What still holds:
- Planning, reviewing and chat stay read-only.
- The supervisor still runs your tests and an independent review before anything is merged.

The risk: a mistake, or a hidden instruction planted in some project file, can delete files, leak data or change your repositories, and nothing stops a command while it runs. Use it on projects you trust, and keep backups.

## GitHub

**GitHub › Connect GitHub** signs in through the official GitHub CLI. Then you can:
- see your repositories, and clone one as a project
- **Publish** a local project to a new private or public GitHub repository
- **Push** a project's main branch after you have approved merges

## Away mode: let the AI work while you're away

Normally every task waits for you three times: to approve the plan, to let the agents run, and to merge the result. **Settings › Away mode** lets Cerebra answer those for you for a set time (2 to 72 hours), so tasks you created keep going while you're away.

1. Create your tasks first. Each one needs test commands on its project.
2. Make sure agents are switched on (Settings › Agent permissions).
3. In **Away mode**, pick how long, and optionally which projects. Tick the first box and press **Turn Away mode on**.
4. Optional: tick **Also merge finished work** to let Cerebra merge work into your project folder. It merges only when every test passed and the independent review found nothing to fix. Merging is local: nothing is ever pushed to GitHub.

While Away mode is on:
- Plans are approved, the AI team starts, and review findings are sent back to the coder for repair (up to the repair limit).
- Every step it answers appears in **Activity** as "Away mode answered …".
- The top bar shows **away mode**.
- It switches itself off when the time is up, or when you switch agents off.

What it does **not** do:
- It doesn't widen what the agents may touch. Unless you also turned on **Full access**, they still work only in a separate copy of the project, can change only the files the task allows, and can't install software, use the network (Codex), or push to GitHub. Cerebra itself pushes merged work only if you ticked that option.
- It doesn't keep your laptop awake. Set Windows to not sleep while plugged in, and leave Cerebra running in the tray.

## Pause, resume, cancel

Open a task:
- **Pause** stops the current step and keeps everything.
- **Resume** continues the task.
- **Cancel** stops the task for good. Its history and branch are kept for inspection.
- Stopping Cerebra from the tray keeps all records. Interrupted work waits for you to press Resume.

## Old demo data

Versions before 0.5 had a simulated calculator demo. **Settings › Old demo data** removes those records after backing up the database. Your real projects and tasks are kept.
