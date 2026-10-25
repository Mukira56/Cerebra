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
   - Press **Browse…** to choose the folder in Windows' own folder picker, or type it.
   - Cerebra looks at the folder and suggests how it is tested (for example pytest, npm test, dotnet test, go test or cargo test). Check the suggestion under **How is it tested?**, choose another runner, or pick **Something else** and type the command as you would in a terminal. Cerebra runs these tests to prove that the AI's code works. Several commands go under **Several commands? (advanced)**.
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

## Delivering a client website (Business Studio)

1. **+ New business job** › *Service business website (quote requests)*. Paste what the client told you.
2. Fill in the **Scope** with your client: services, service areas, pages, what's included and not, revisions, deadline, price, their phone, and the **form delivery address**. That's where quote requests go; a free Formspree form works: formspree.io › New form › copy its https address.
3. Press **Approve scope and start**. Only now does the AI team plan and build. The site is checked automatically:
   - every page works on phones,
   - no links are broken,
   - images are described,
   - the form sends to your address and asks for the right details,
   - every service and area you agreed appears.
4. Review the result in **Preview**, then press **Send test enquiry** and check the client's inbox.
5. Track the job:
   - **Money:** payments, expenses, your hours.
   - **Customer results:** each enquiry and whether it became a booked job.
   - **Change requests:** counted against the revisions you included.

Profit is calculated only from what you enter.

## When something fails: ask the Assistant

Open a failed or paused task and press **Ask the Assistant to fix this**:
- It reads the real error, the log of the failing run and the failing test output, and explains the cause.
- Then it retries the task with precise instructions for the coder, or tells you what it needs from you (for example signing in again).
- You can also just ask in the Assistant: "why did my last task fail? fix it".

The Assistant can create, start, pause, retry and restore tasks, set a project's tests, change the AI team and run the readiness check. Tick **May answer approvals** in the Assistant to let it approve plans, runs and merges too.
- Full access, agents on/off, accounts, keys and anything that spends money or publishes always stay with you.

## Is everything working? The readiness check

**Settings › Readiness check › Run readiness check** gives Cerebra a tiny real job: fix a one-line bug in a separate test project. It goes through planning, coding, your tests and the independent review using your own models, and shows a ✓ or ✗ for each stage with its time. It stops before merging, so none of your projects change. It uses a little of your Codex/Claude usage.

## Going back: checkpoint history and undo

Open a task and choose the **History** tab:
- Every coding attempt is a saved checkpoint.
- **Restore** puts the task's working copy back to an earlier checkpoint (pause the task first). Then press Resume and Start: the work is tested and reviewed again before anything can be merged.
- **Undo merge** (on a finished task) adds one new commit to your project that reverses the task's changes. Your history is kept. If later work changed the same lines, Cerebra stops and changes nothing.

Both ask for a second click to confirm.

## Previewing finished work

A Business Studio job's page has a **Preview** section. Click a file to see the website, design, image or document right inside Cerebra. Generated pages are shown safely: their scripts and outside links are blocked.

## Updating Cerebra

Open **Settings › Updates** and press **Check for updates**.
- If a newer version is published on your GitHub, press **Download**. A progress bar shows 0–100% and how many MB have arrived.
- The download runs in the background: you can close Settings and keep working. The top bar shows "Update N%", and a message appears when it is ready.
- If the connection drops, press **Download** again; it continues from where it stopped. When it finishes, Cerebra checks that the installer matches its published checksum.
- Then press **Install and restart**. Cerebra closes and a small window shows each step of the update (closing, installing, starting) until Cerebra opens again by itself, in about a minute.
- Running tasks are paused and can be resumed, and your projects, tasks and settings are kept.

Updates use your GitHub sign-in (GitHub page), so the GitHub CLI must be installed and signed in.

## Connecting your business accounts

On **Business connections**, every account has setup notes beside it. Press **How to connect…** for a full step-by-step guide:
- how to open an Etsy shop or a Printify store if you don't have one,
- where to get each key or token,
- how to finish connecting.

The buttons marked ↗ open the official pages in your browser.

## Closing Cerebra while tasks run

If a task is running when you close Cerebra, it warns you and lists the tasks. If you close anyway, the tasks are paused, not lost. When you open Cerebra again, the Overview shows **Paused when Cerebra closed**: press **Resume all**. Work continues from where it stopped. A task that was being tested or reviewed goes straight back to testing and review.

## When an AI runs out of usage

If Claude or Codex runs out of usage (or its sign-in expires) in the middle of a task:
- The other AI takes over the same step. It reads what the first one already changed and its last notes, and finishes the job instead of starting over.
- The reviewer must still come from the other company than the coder. If only one company has usage left, the task pauses before review.
- If no AI has usage left, the task pauses and Cerebra tries again by itself every 15 minutes. You can also press Resume.

The Overview's **Waiting for AI usage** panel shows these tasks and when Cerebra will try again.

## Pause, resume, cancel

Open a task:
- **Pause** stops the current step and keeps everything.
- **Resume** continues the task.
- **Cancel** stops the task for good. Its history and branch are kept for inspection.
- Stopping Cerebra from the tray keeps all records. Interrupted work waits for you to press Resume.

## Old demo data

Versions before 0.5 had a simulated calculator demo. **Settings › Old demo data** removes those records after backing up the database. Your real projects and tasks are kept.
# Business Studio connections and workers (0.9.0)

Create a job in **Business Studio**, choose Website, Listing copy, SVG or Document, and paste your own brief. Approve its plan and execution in the usual task window. A different provider reviews the work. After integration approval, use **Export ZIP** on the results page. Files normally live in `Documents\Cerebra Business\<job>`; the results page shows the exact path and has Open folder/result buttons. Export preserves the reviewed README and includes a manifest of the final file hashes.

**First task to try:** choose Website, title `My bakery website`, brief `Make an original one-page website for my Nairobi bakery. Include a menu, opening hours, phone contact and a mobile layout. Use original SVG decoration. Do not publish it or use paid services.` This uses your signed-in coding models; it does not require a marketplace connection.

System view's original workshop couriers follow recorded task stages through the pipes. Moving workers mean recorded active work, a stationary worker at the approval gate means a decision is waiting, and a red worker means failure. Idle/offline views do not invent jobs. Select a worker for the inspector and task/report links. Reduced-motion users see stationary workers. These are stage indicators, not extra agents or a view into hidden reasoning.

Open **Business connections** to configure optional services. Blank secret fields keep an existing protected value; Disconnect removes a connection. Secrets are encrypted for the current Windows account and are not sent to coding models. Saving a key is different from successfully checking it.

- **Etsy:** register your own developer app and HTTPS callback you control; enter keystring, shared secret, shop ID and exact callback URL. Authorize in the external browser, then paste the full redirected callback URL into Cerebra and finish authorization. Check the shop. On a reviewed job choose Image / marketplace draft, review all listing fields and confirm your original creative input/disclosures. This creates a draft only. Complete images/files, AI and production-partner disclosures and publishing in Etsy.
- **Printify:** save a personal API token, Check connection to see your shop IDs, then save your chosen shop. A reviewed job can upload a PNG/JPEG and create a draft product using real blueprint/provider/variant IDs and print areas from Printify's catalog. This release deliberately provides no order creation, order import, publishing or production endpoint. New Printify shops may auto-produce orders, and this app cannot verify a shop's manual-approval setting.
- **Raster images:** save your own OpenAI API key and an available GPT image model (default `gpt-image-2.5-flare`). Checking access is separate from generating. On a reviewed job provide your own creative instructions and confirm one paid API image. The PNG and provenance are saved under the job's `generated` folder. Inspect it before delivery: it is created after the job's independent review. Export again to include it. Coding subscriptions do not pay these API charges.
- **Gmail:** enable Gmail API and create a Desktop app OAuth client in your Google Cloud project. Configure the consent screen/test users as required by Google. Save its client ID and secret, Connect Gmail, and complete Google's browser flow. Search/read messages and explicitly choose Use as business brief. No email sending, modifying, deleting, automatic intake or automatic client replies is provided.
- **Phone notifications:** optionally enable ntfy or your Telegram bot and provide your own private chat ID. Subscribe to the displayed ntfy topic. Task titles/states leave the laptop when enabled; use nonsensitive titles. Anyone who knows an unprotected ntfy topic can read its messages. Test delivery is a separate button. Both services are off by default.

External actions are recorded. A repeated successful request returns its existing result; a pending/uncertain request is blocked from automatic retry. Check the provider's dashboard after timeouts rather than generating duplicates. External actions are not delegated to Support/Away mode. These connections require your accounts, permissions and provider access; fixture tests do not establish successful live execution.

# Factory floor (0.10.0)

Open **System view** to see the factory blueprint. Each building represents a real Cerebra sector: intake, research/planning, coding, independent review, local server, coordination, tests, approvals, database, logs, working copy and results. Select a building or person to inspect it and open its task or plain report.

There are 72 illustrated people by default. Choose 24 or 48 for a quieter floor. These people are a visual crew, not separate agent processes. Idle staff may walk inside rooms; active sectors send people along corridors. The separate **recorded AI runs active** badge reports actual provider runs recorded by Cerebra. Model labels come from the task's routing record, not an invented version or claim about an unreported server-side model snapshot. An unassigned model stays unassigned. Non-model buildings show their software or human approval role.

Mouse and keyboard:
- the **wheel** scrolls the floor; **Ctrl + wheel** zooms toward the pointer
- **drag** empty floor to move around; **double-click** to zoom in
- **+**, **−** and **Fit factory** are also buttons, and `+`, `-` and `0` work when the floor has focus
- **Right-click** a building to inspect it, or anywhere on the floor to zoom or fit

Right-click works throughout Cerebra:
- on tasks, business jobs and chats it offers their actions (open, report, copy ID, folder)
- in text boxes it gives the normal cut, copy and paste menu Switch model labels on or off. A person holds position when hovered or keyboard-focused. Waiting staff pause, failed sectors show a problem, and disconnected telemetry freezes movement. Reduced-motion and offscreen/hidden views stop walking animation. The design is based on the user's transcript and factory description; no external creator's assets were copied.

