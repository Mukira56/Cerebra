"use strict";
// Cerebra dashboard. Every value from the server or a model is inserted as text, never as HTML.
(() => {
  // The browser's own append/replaceChildren print "null" for an empty value; skip empty values everywhere instead.
  for (const proto of [Element.prototype, DocumentFragment.prototype]) {
    for (const name of ["append", "replaceChildren"]) {
      const native = proto[name];
      proto[name] = function (...nodes) { return native.apply(this, nodes.filter(node => node !== null && node !== undefined && node !== false)); };
    }
  }
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const pages = {
    overview: ["WORKSPACE", "Overview", "Everything happening in Cerebra, at a glance."],
    chat: ["WORKSPACE", "Support", "Ask about any project or task (“why did EstatePilot fail?”), or have Cerebra plan, create and start the work."],
    council: ["BUILD", "Council", "Codex and Claude discuss a project with each other, agree on ideas and who builds each one. You read every word."],
    marketing: ["EARN", "Marketing", "Posts that bring you clients on X, your Facebook Page and Instagram. Nothing goes out until you approve it."],
    chief: ["WORKSPACE", "Chief of Staff", "Your money goals and the workers that pursue them: each on its schedule, every run on the record. Anything that reaches other people waits for your yes."],
    prospects: ["EARN", "Prospects", "Local businesses in the US that could use what you sell, from public data, each kept only with a reason seen on its own website. Nobody is contacted without you."],
    funding: ["EARN", "Funding", "Free cloud credits, grants and accelerators you could apply to, and what each still needs from you. You apply; Cerebra keeps track."],
    books: ["EARN", "Books", "Short nonfiction books for Amazon KDP: find a niche people pay for, plan and write the book, and see what each format earns. You upload and publish."],
    freelance: ["EARN", "Freelance", "Paid work found for you on public job sources and scored against what you sell. Cerebra can bid for you on Freelancer.com; elsewhere you apply in your own name."],
    money: ["EARN", "Money", "Quotes, invoices and what your business has earned and is owed. You send every document; Cerebra never takes payments."],
    business: ["BUILD", "Business Studio", "Turn a client brief into original, reviewed deliverables saved on this laptop."],
    connections: ["SETUP", "Business connections", "Connect your own accounts. Secrets stay protected by this computer's own secret store; external work needs your confirmation."],
    job: ["BUILD", "Business result", ""],
    tasks: ["BUILD", "Tasks", "Describe what to build. AI plans it, writes it, tests it and checks it; you approve."],
    projects: ["BUILD", "Projects", "Repositories Cerebra is allowed to work in."],
    approvals: ["BUILD", "Approvals", "Nothing important happens without your yes."],
    system: ["INSIGHT", "Factory floor", "A live blueprint of your AI development factory. Inspect a building or a person to see its recorded work."],
    reports: ["INSIGHT", "Reports", "What happened in each task, explained in plain words."],
    report: ["INSIGHT", "Task report", ""],
    activity: ["INSIGHT", "Activity log", "Every decision the supervisor recorded."],
    models: ["SETUP", "Models & sign-in", "Sign in to your AI accounts, choose models, and add more."],
    github: ["SETUP", "GitHub", "Connect your GitHub account to clone, publish and push projects."],
    toolchain: ["SETUP", "Toolchain", "The tools a software engineer needs, checked and installable in one place."],
    settings: ["SETUP", "Settings", "Agent permissions, limits, and where your data lives."]
  };
  const PROVIDER_ICON = {codex: "◇", claude: "✳", copilot: "⧉", gemini: "✦"};
  const ACTIVE = ["RUNNING", "VERIFYING", "REVIEWING", "NEEDS_CHANGES"];
  let csrf = "", data = null, page = "overview", param = "", lastFingerprint = "", fetching = null, toastTimer = 0;
  let detailTaskId = "", detailTab = "Overview", detailFingerprint = "", pageTimer = 0, renderToken = 0;
  const cache = {providers: null, tools: null, github: null, repos: null, chats: null};
  const content = $("#page-content"), dialog = $("#dialog"), dialogContent = $("#dialog-content");

  // ---------- small DOM helpers ----------
  function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined && text !== null) node.textContent = String(text); return node; }
  // Like replaceChildren, but skips empty values (replaceChildren would print "null").
  function fill(parent, ...nodes) { parent.replaceChildren(); return append(parent, ...nodes); }
  function append(parent, ...nodes) { nodes.flat(Infinity).forEach(node => { if (node !== null && node !== undefined && node !== false) parent.append(node); }); return parent; }
  function button(label, action, className = "button") { const node = el("button", className, label); node.type = "button"; node.addEventListener("click", action); return node; }
  function link(label, destination, className = "text-link") { const node = el("a", className, label); node.href = `#${destination}`; return node; }
  function array(value) { return Array.isArray(value) ? value : []; }
  function nice(value) { return String(value ?? "—").replaceAll("_", " ").toLowerCase().replace(/^./, c => c.toUpperCase()); }
  function json(value) { return typeof value === "string" ? value : JSON.stringify(value, null, 2); }
  function date(value) { if (!value) return "—"; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}); }
  function relative(value) { if (!value) return "—"; const delta = Date.now() - new Date(value).getTime(); if (!Number.isFinite(delta)) return date(value); if (delta < 60000) return "just now"; if (delta < 3600000) return `${Math.floor(delta / 60000)} min ago`; if (delta < 86400000) return `${Math.floor(delta / 3600000)} h ago`; return date(value); }
  const STATE_STYLE = {COMPLETED: "green", RUNNING: "blue", VERIFYING: "blue", REVIEWING: "blue", PLANNING: "blue", READY: "blue", FAILED: "red", REJECTED: "red", CANCELLED: "muted", BLOCKED: "amber", NEEDS_CHANGES: "amber", AWAITING_APPROVAL: "amber", PENDING: "muted", APPROVED: "green"};
  function badge(value, style) { const key = String(value ?? "unknown").toUpperCase(); return el("span", `badge ${style || STATE_STYLE[key] || "muted"}`, key.replaceAll("_", " ")); }
  function panel(title, body, action, count) { const node = el("section", "panel"), header = el("div", "panel-header"), heading = el("h2", "", title); if (count !== undefined) heading.append(el("span", "count", count)); append(header, heading, action); append(node, header, body); return node; }
  function body(...nodes) { return append(el("div", "panel-body"), nodes); }
  function empty(title, description, action, symbol = "∅") { return append(el("div", "empty-state"), el("div", "empty-icon", symbol), el("h3", "", title), el("p", "", description), action); }
  function code(value) { return el("pre", "code-block", json(value)); }
  function hint(text, warn = false) { return el("div", warn ? "hint warn" : "hint", text); }
  // An AI run's output is a stream of JSON records (Codex) or one result record (Claude). Show what the model said;
  // the raw records stay one click away.
  function runText(output) {
    const said = [];
    for (const line of String(output || "").split("\n")) {
      let record; try { record = JSON.parse(line); } catch { continue; }
      const item = record?.item || {};
      if (item.type === "agent_message" && item.text) said.push(item.text);
      else if (typeof record?.result === "string" && record.result.trim()) said.push(record.result);
    }
    return said.map(text => { try { const value = JSON.parse(text); return typeof value?.summary === "string" ? value.summary : text; } catch { return text; } }).join("\n\n").trim();
  }
  function runOutput(output) {
    const said = runText(output), raw = String(output || "").slice(-6000);
    if (!said) return raw.length > 2000 ? append(el("details"), el("summary", "", "Raw output"), code(raw)) : code(raw);
    return [el("div", "run-said", said), append(el("details"), el("summary", "", "Raw output"), code(raw))];
  }
  // Long provider errors (pages of connection logs) show their start; the rest is one click away.
  function failureText(text, mark = "⚠ ") {
    const value = String(text || ""), node = el("div", "failure-text");
    if (value.length <= 320) { node.append(el("p", "", mark + value)); return node; }
    return append(node, el("p", "", `${mark}${value.slice(0, 300).trimEnd()}…`), append(el("details"), el("summary", "", "Show full error"), code(value)));
  }
  function kv(values) { const node = el("dl", "kv"); values.forEach(([key, value]) => append(node, el("dt", "", key), value instanceof Node ? append(el("dd"), value) : el("dd", "", value === true ? "Yes" : value === false ? "No" : (value ?? "—")))); return node; }
  function table(headers, rows) { const wrap = el("div", "table-wrap"), node = el("table"), head = el("tr"); headers.forEach(header => head.append(el("th", "", header))); node.append(append(el("thead"), head)); const tbody = el("tbody"); rows.forEach(cells => { const row = el("tr"); cells.forEach(value => { const cell = el("td"); cell.append(value instanceof Node ? value : document.createTextNode(String(value ?? "—"))); row.append(cell); }); tbody.append(row); }); node.append(tbody); wrap.append(node); return wrap; }
  function option(value, label, selected = false) { const node = el("option", "", label); node.value = value; node.selected = selected; return node; }
  function select(options, value) { const node = el("select"); options.forEach(([key, label, disabled]) => { const item = option(key, label); item.disabled = !!disabled; node.append(item); }); if (value !== undefined) node.value = value; return node; }
  function field(label, control, help) { return append(el("label", "field"), el("span", "", label), control, help ? el("small", "", help) : null); }
  function input(placeholder = "", value = "", type = "text") { const node = el("input"); node.type = type; node.placeholder = placeholder; node.value = value ?? ""; return node; }
  function textarea(placeholder = "", value = "") { const node = el("textarea"); node.placeholder = placeholder; node.value = value; return node; }
  function check(label, checked = false) { const wrap = el("label", "check-field"), control = input("", "", "checkbox"); control.checked = !!checked; append(wrap, control, el("span", "", label)); return {wrap, control}; }
  function actionsRow(...nodes) { return append(el("div", "form-actions"), nodes); }
  function wireForm(form, submit, onSubmit) { const error = el("div", "form-error"); error.setAttribute("role", "alert"); form.append(error); form.addEventListener("submit", async event => { event.preventDefault(); submit.disabled = true; error.textContent = ""; try { await onSubmit(); } catch (issue) { error.textContent = issue.message; } finally { submit.disabled = false; } }); }
  function submitButton(label) { const node = el("button", "button primary", label); node.type = "submit"; return node; }
  function toast(message, error = false) { const node = $("#toast"); node.textContent = message; node.className = `toast${error ? " error" : ""}`; clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.add("hidden"), 6500); }
  function notice(message, error = false) { const node = $("#global-notice"); node.textContent = message; node.className = message ? `notice${error ? " error" : ""}` : "notice hidden"; }
  function showDialog(title, nodeBody) { $("#dialog-title").textContent = title; dialogContent.replaceChildren(nodeBody); if (!dialog.open) dialog.showModal(); }
  function closeDialog() { if (dialog.open) dialog.close(); detailTaskId = ""; }
  $("#dialog-close").addEventListener("click", closeDialog);
  dialog.addEventListener("close", () => { detailTaskId = ""; delete dialog.dataset.leadId; });

  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(options.timeout || 30000), ...options,
      headers: {"Content-Type": "application/json", ...(options.method && options.method !== "GET" ? {"X-CSRF-Token": csrf} : {}), ...options.headers}});
    const type = response.headers.get("content-type") || "";
    const result = type.includes("json") ? await response.json() : {detail: await response.text()};
    if (!response.ok) { let message = result.detail || `Request failed (${response.status})`; if (Array.isArray(message)) message = message.map(issue => `${array(issue.loc).slice(1).join(".")}: ${issue.msg}`).join("\n"); throw new Error(typeof message === "string" ? message : json(message)); }
    return result;
  }
  const mutate = (path, payload = {}, method = "POST", timeout) => api(path, {method, body: JSON.stringify(payload), timeout});
  async function act(label, work) { try { const result = await work(); if (label) toast(typeof label === "function" ? label(result) : label); return result; } catch (issue) { toast(issue.message, true); return null; } }

  // ---------- derived state ----------
  const projectFor = id => array(data?.projects).find(project => project.id === id);
  const taskFor = id => array(data?.tasks).find(task => task.id === id);
  const pendingApprovals = () => array(data?.approvals).filter(item => String(item.status).toLowerCase() === "pending");
  const agentsOn = () => data?.settings?.live_enabled === true && data?.settings?.cli_confinement_accepted === true;
  const realTasks = () => array(data?.tasks).filter(task => task.mode !== "mock");
  const profiles = () => array(data?.profiles);
  const runnable = () => profiles().filter(profile => profile.can_run_tasks);
  const agentRow = name => array(data?.agents).find(agent => agent.name === name) || {};
  function profileLabel(id) { if (id === "auto") return "Auto"; const profile = profiles().find(item => item.id === id); if (profile) return profile.label; const [, provider, model] = String(id).split(":"); const known = array(data?.catalog?.[provider]).find(item => item.model === model); return known ? known.label : id; }
  function taskModels(task) { const models = task?.results?.models || {}; return {planner: models.planner?.label || "Claude", implementer: models.implementer?.label || nice(task?.assigned_agent), reviewer: models.reviewer?.label || nice(task?.reviewer)}; }

  // ---------- chrome ----------
  function heading() {
    const [eyebrow, title, subtitle] = pages[page];
    $("#page-eyebrow").textContent = eyebrow; $("#page-title").textContent = title; $("#page-subtitle").textContent = subtitle;
    $("#breadcrumb-title").textContent = param ? `${page}/${param.slice(0, 8)}` : page;
    document.querySelectorAll("[data-page]").forEach(node => node.classList.toggle("active", node.dataset.page === page || (page === "report" && node.dataset.page === "reports") || (page === "job" && node.dataset.page === "business")));
    const actions = $("#heading-actions"); actions.replaceChildren();
    if (["overview", "tasks"].includes(page)) actions.append(button("+ New task", () => taskForm(), "button primary"));
    if (page === "projects") actions.append(button("+ Add project", () => projectForm(), "button primary"));
    if (page === "business") actions.append(button("+ New business job", () => businessForm(), "button primary"));
    if (page === "job") actions.append(button("← Business Studio", () => { location.hash = "business"; }, "button ghost"));
    if (page === "models") actions.append(button("↻ Re-check tools", () => act("Agent tools re-checked.", async () => { cache.providers = await mutate("/api/providers/refresh", {}, "POST", 120000); await refresh(true); }), "button ghost"));
    if (page === "report") actions.append(button("← All reports", () => { location.hash = "reports"; }, "button ghost"), button("Technical details", () => taskDetail(param), "button ghost"));
  }
  function chrome() {
    if (!data) return;
    $("#project-count").textContent = array(data.projects).length;
    const count = pendingApprovals().length; $("#approval-count").textContent = count; $("#approval-count").classList.toggle("hidden", !count);
    const status = $("#agents-status"); status.className = `pill ${agentsOn() ? "good" : "warn"}`; status.replaceChildren(el("span", "dot"), document.createTextNode(agentsOn() ? (awayOn() ? "away mode" : "agents on") : "agents off")); status.title = awayOn() ? `Away mode until ${date(data.autopilot.until)}` : "";
    $("#version-label").textContent = `Cerebra v${data.version || ""}`;
    // The taskbar shows the window title: say when something needs the owner, is running, or failed.
    const waitingCount = pendingApprovals().length + finishedTasks().length, workingCount = realTasks().filter(task => ACTIVE.includes(task.state)).length, failedCount = realTasks().filter(task => task.state === "FAILED" && !task.finished).length;
    document.title = waitingCount ? `(${waitingCount}) Cerebra — waiting for you` : workingCount ? "Cerebra — working…" : failedCount ? `Cerebra — ${failedCount} problem${failedCount === 1 ? "" : "s"}` : "Cerebra · Development command center";
    const update = data.update_progress || {}, pill = $("#update-status"), active = ["starting", "downloading", "verifying"].includes(update.phase);
    pill.classList.toggle("hidden", !(active || update.phase === "ready"));
    pill.className = `pill ${update.phase === "ready" ? "good" : ""}${active || update.phase === "ready" ? "" : " hidden"}`;
    pill.textContent = update.phase === "ready" ? `Update ${String(update.tag || "").replace(/^v/, "")} ready · install`.replace("Update  ready", "Update ready") : active ? `Update ${update.percent || 0}%` : "";
    if (lastUpdatePhase && lastUpdatePhase !== update.phase) {
      if (update.phase === "ready") toast("The update is downloaded and verified. Install it from Settings › Updates when you're ready.");
      if (update.phase === "failed") toast(`The update download didn't finish: ${update.error}`, true);
    }
    lastUpdatePhase = update.phase;
    const permission = $("#footer-permission");
    if (permission) permission.textContent = awayOn() ? `Away mode answers approvals until ${date(data.autopilot.until)}` : data.assistant?.allow_approvals ? "You or the Assistant approve each step" : "You approve every step";
  }
  let lastUpdatePhase = "";

  function render() {
    clearInterval(pageTimer); pageTimer = 0; renderToken++;
    if (page !== "system") window.AIHQSystem?.unmount();
    heading(); chrome();
    if (!data) { content.replaceChildren(el("div", "loading", "connecting to your local workspace…")); return; }
    const views = {overview, council: councilView, connections: connectionView, business: businessView, money: moneyView, books: booksView, chief: chiefView, prospects: prospectsView, funding: fundingView, freelance: freelanceView, marketing: marketingView, job: jobView, chat: chatView, tasks: tasksView, projects: projectsView, approvals: approvalsView, system: systemView, reports: reportsView, report: reportView, activity: activityView, models: modelsView, github: githubView, toolchain: toolchainView, settings: settingsView};
    const result = views[page]();
    if (result) content.replaceChildren(result);
  }

  // ---------- overview ----------
  function setupChecklist() {
    const signIn = name => cache.providers?.find(item => item.id === name)?.sign_in?.signed_in === true || agentRow(name).authentication === "verified_by_execution";
    const items = [
      ["Install Git and the AI coding tools", "Toolchain checks and installs Git, Codex and Claude Code.", agentRow("codex").installed && agentRow("claude").installed, "toolchain"],
      ["Sign in to Codex and Claude", "Use your own accounts; Cerebra never sees your password.", signIn("codex") && signIn("claude"), "models"],
      ["Switch AI agents on", "One-time permission in Settings. Every task still asks you first.", agentsOn(), "settings"],
      ["Add a project", "An existing folder, a new project, or one cloned from GitHub.", array(data.projects).length > 0, "projects"],
      ["Create your first task", "Describe what you want built.", realTasks().length > 0, "tasks"]
    ];
    const list = el("div", "checklist");
    items.forEach(([title, text, done, target], index) => { const item = el("div", `check-item${done ? " done" : ""}`), info = el("div"); append(info, el("strong", "", title), el("small", "", text)); append(item, el("span", "tick", done ? "✓" : index + 1), info, done ? badge("done", "green") : link("Open →", target)); list.append(item); });
    return {list, complete: items.every(item => item[2])};
  }
  // Plain words for the errors people actually hit; anything else shows its own first sentence.
  const REASONS = [
    [/No meaningful progress/i, "The coder made no new change. If its tests pass, press Try again; the review may have asked for something it can't do."],
    [/lacks verified|lacks required conservative/i, "Cerebra couldn't confirm the AI's command-line tool (often just a slow start). Press Try again."],
    [/WinError 2|cannot find the file specified/i, "A program it needed wasn't found. Fixed in 0.19: press Try again."],
    [/couldn't reach its servers|can't reach the api|ENOTFOUND|offline:/i, "The AI couldn't be reached: the internet was down when it ran. Press Try again."],
    [/rate.?limit|usage limit|out of usage|No AI model with available usage/i, "The AI ran out of usage. It continues when usage is back."],
    [/timeout|timed out/i, "A step took too long and was stopped. Press Try again, or raise the time limit in Settings."],
    [/Repair retry limit/i, "Tests or review still failed after every repair attempt. Ask the Assistant, or let Auto-fix take it."],
    [/changed or created these files|changed or created files/i, "Running the tests wrote files into the project. Open the task to see which ones."],
    [/No verification commands/i, "The project has no tests set. Add them on the Projects page."],
    [/changes that aren't committed|registered repository has user changes/i, "Your project folder has uncommitted changes, so the merge is waiting. Open the task to set them aside and merge."],
    [/has no settings file yet/i, "Its tests need settings only you have (database address, secrets…). Open the task to see which ones; it continues by itself once you add them."],
    [/target branch moved/i, "Another task merged first. Press Try again: Cerebra now brings the work up to date and merges it."],
    [/changed the same parts of/i, "The project changed the same files since this task started. Press Try again to redo it on the latest code."],
  ];
  function finishedTasks() { return realTasks().filter(task => task.finished); }
  function failureReason(task) {
    const error = String(task.results?.error || "");
    if (!error && task.state === "BLOCKED") {
      const waiting = array(task.dependencies).map(taskFor).filter(other => other && other.state !== "COMPLETED");
      return waiting.length ? `Waiting for “${waiting[0].description.slice(0, 70)}” to finish first.` : "";
    }
    if (!error) return "";
    if (task.results?.blocked_reason === "waiting_for_network") return "No internet right now. Cerebra tries again every 5 minutes.";
    if (task.results?.blocked_reason === "waiting_for_usage") return "Waiting for AI usage. Cerebra tries again every 15 minutes.";
    const known = REASONS.find(([pattern]) => pattern.test(error));
    return known ? known[1] : error.split(/(?<=[.!?])\s|\n/)[0].slice(0, 160);
  }
  function taskRows(tasks) {
    const list = el("div", "row-list");
    tasks.forEach(task => {
      const row = el("div", "row"), info = el("div", "row-main"), meta = el("div", "row-meta"), models = taskModels(task);
      row.tabIndex = 0; row.setAttribute("role", "button"); row.dataset.taskId = task.id; row.addEventListener("click", () => taskDetail(task.id)); row.addEventListener("keydown", event => { if (event.key === "Enter") taskDetail(task.id); });
      append(meta, el("span", "", projectFor(task.project_id)?.name || "project"), el("span", "", "·"), el("span", "", `${models.implementer} → ${models.reviewer}`), el("span", "", "·"), el("span", "", relative(task.updated_at)), task.mode === "mock" ? badge("old demo", "muted") : null);
      const reason = task.finished ? "Finished and reviewed: only the merge is left. Open it to merge."
        : (task.state === "FAILED" || (task.state === "BLOCKED" && !task.pause_requested)) ? failureReason(task) : "";
      const calm = task.finished || (task.state === "BLOCKED" && (!task.results?.error || ["waiting_for_usage", "waiting_for_network", "needs_settings"].includes(task.results?.blocked_reason)));
      append(info, el("strong", "", task.description), meta, reason ? el("div", calm ? "row-reason waiting" : "row-reason", reason) : null); append(row, info, task.finished ? badge("READY TO MERGE", "green") : badge(task.pause_requested ? "PAUSED" : task.state), el("span", "chev", "›")); list.append(row);
    });
    return list;
  }
  function activityList(events, limit = 8) {
    if (!events.length) return body(empty("No activity yet", "Supervisor decisions appear here as they happen.", null, "≡"));
    const list = el("div", "trace"); events.slice(0, limit).forEach(event => list.append(append(el("div"), el("time", "", date(event.created_at)), el("span", "k", event.kind), el("span", "", event.message)))); return list;
  }
  function overview() {
    const node = el("div"), tasks = realTasks(), active = tasks.filter(task => ACTIVE.includes(task.state)), setup = setupChecklist();
    if (!setup.complete) node.append(panel("Get started", body(setup.list)));
    // Tasks paused because Cerebra closed or stopped, or waiting for an AI model with usage left.
    const stopped = tasks.filter(task => task.state === "BLOCKED" && ["paused_on_close", "interrupted_restart"].includes(task.results?.blocked_reason));
    const noUsage = tasks.filter(task => task.state === "BLOCKED" && task.results?.blocked_reason === "waiting_for_usage");
    const offline = tasks.filter(task => task.state === "BLOCKED" && task.results?.blocked_reason === "waiting_for_network");
    if (stopped.length) {
      const resumeAll = button(`Resume ${stopped.length === 1 ? "it" : `all ${stopped.length}`}`, async () => { resumeAll.disabled = true; for (const task of stopped) { const resumed = await act(null, () => mutate(`/api/tasks/${encodeURIComponent(task.id)}/resume`)); if (resumed?.state === "READY") await act(null, () => mutate(`/api/tasks/${encodeURIComponent(task.id)}/start`)); } await refresh(true); toast("Resumed. The AI team picks up where it stopped."); }, "button primary");
      node.append(panel("Paused when Cerebra closed", body(el("p", "", `${stopped.length === 1 ? "One task was" : `${stopped.length} tasks were`} paused when Cerebra closed. Nothing was lost; resume to continue from where ${stopped.length === 1 ? "it" : "they"} stopped.`), taskRows(stopped), actionsRow(resumeAll))));
    }
    if (noUsage.length) node.append(panel("Waiting for AI usage", body(el("p", "", "No AI model had usage left for these tasks. Cerebra tries again automatically every 15 minutes, or press Resume in a task to try now."),
      list(noUsage.map(task => `${task.description.slice(0, 80)} · next try ${date(task.results.retry_after)}`)))));
    if (offline.length) node.append(panel("Waiting for the internet", body(el("p", "", "These tasks couldn't reach the AI because the internet or DNS was down. Nothing is lost: Cerebra tries again every 5 minutes, or press Resume in a task to try now."),
      list(offline.map(task => `${task.description.slice(0, 80)} · next try ${date(task.results.retry_after)}`)))));
    const stats = el("div", "grid stats");
    [["Projects", array(data.projects).length, "authorized repositories", ""], ["Active", active.length, active.length ? "AI is working" : "nothing running", "cyan"], ["Waiting for you", pendingApprovals().length + finishedTasks().length, finishedTasks().length ? "approvals and merges" : "approvals", "amber"], ["Done", tasks.filter(task => task.state === "COMPLETED").length, "finished tasks", "green"], ["Problems", tasks.filter(task => task.state === "FAILED" && !task.finished).length, "failed tasks", "red"]]
      .forEach(([label, value, note, style]) => {
        const card = append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note));
        const target = {"Projects": ["projects"], "Active": ["tasks", "active"], "Waiting for you": ["approvals"], "Done": ["tasks", "COMPLETED"], "Problems": ["tasks", "FAILED"]}[label];
        if (target) { card.classList.add("clickable"); card.tabIndex = 0; card.setAttribute("role", "link");
          const go = () => { taskStateFilter = target[1] || ""; location.hash = target[0]; }; card.addEventListener("click", go); card.addEventListener("keydown", event => { if (event.key === "Enter") go(); }); }
        stats.append(card);
      });
    node.append(stats);
    const grid = el("div", "grid two"), left = el("div"), right = el("div");
    if (data.calls?.count) left.append(panel("Your calls", callList(data.calls.items), link("All →", "chief"), data.calls.count));
    left.append(panel("Recent tasks", tasks.length ? taskRows(tasks.slice(0, 8)) : body(empty("No tasks yet", "Create a task: describe what you want, and the AI team plans, codes, tests and reviews it.", button("+ New task", () => taskForm(), "button primary"), "#")), link("All tasks →", "tasks"), tasks.length));
    const waiting = pendingApprovals(), merges = finishedTasks();
    if (waiting.length) left.append(panel("Waiting for your decision", approvalCards(waiting.slice(0, 3)), link("All approvals →", "approvals"), waiting.length));
    if (merges.length) left.append(panel("Finished work to merge", taskRows(merges.slice(0, 3)), link("All →", "approvals"), merges.length));
    const team = body(kv([["Planner", profileLabel(data.roles?.planner)], ["Coder", profileLabel(data.roles?.implementer)], ["Reviewer", profileLabel(data.roles?.reviewer)], ["Agents", agentsOn() ? "On · each task asks first" : "Off"],
      ...array(data.agents).filter(agent => agent.usage_until && new Date(agent.usage_until) > new Date()).map(agent => [nice(agent.name), `Out of usage until ${new Date(agent.usage_until).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}; the other model covers for it`])]), link("Change models →", "models"));
    const glance = data.money?.by_currency?.[data.money?.currency] || {}, main = data.money?.currency || "USD";
    const moneyCard = body(kv([["Earned this month", cash(glance.earned_month, main)], ["Owed to you", glance.overdue_count ? `${cash(glance.owed, main)} · ${glance.overdue_count} overdue` : cash(glance.owed, main)],
      ["Quotes out", cash(glance.pipeline, main)], ...(glance.won_unbilled ? [["Won, not invoiced", cash(glance.won_unbilled, main)]] : [])]), link("Open Money →", "money"));
    const work = data.freelance || {}, workRows = [];
    if (work.awarded) workRows.push(["Clients chose you", `${work.awarded}: accept on the Freelance page`]);
    workRows.push(["Strong matches waiting", `${work.strong || 0} (score ${work.min_score || 40}+)`], ["Applied, waiting to hear", String(work.applied || 0)]);
    if (work.won) workRows.push(["Won", String(work.won)]);
    workRows.push(["Automatic bidding", work.auto ? `On · up to ${work.per_day} a day on Freelancer.com` : "Off"]);
    const workCard = body(kv(workRows), link("Open Freelance →", "freelance"));
    const shelf = data.books || {}, shelfRows = [];
    if (shelf.files_ready) shelfRows.push(["Ready to upload", `${shelf.files_ready}: upload on KDP`]);
    shelfRows.push(["Niches being checked", String(shelf.niches || 0)], ["Being written", String((shelf.planned || 0) + (shelf.writing || 0))], ["Published", String(shelf.published || 0)]);
    const shelfCard = body(kv(shelfRows), link("Open Books →", "books"));
    append(right, panel("Money", moneyCard), panel("Freelance", workCard), panel("Books", shelfCard), panel("Your AI team", team), panel("Recent activity", activityList(array(data.events)), link("All →", "activity")));
    append(grid, left, right); node.append(grid); return node;
  }

  // ---------- tasks ----------
  let taskStateFilter = "";
  function tasksView() {
    const node = el("div"), filters = el("div", "form-grid"), projectFilter = select([["", "All projects"], ...array(data.projects).map(project => [project.id, project.name])]), stateFilter = select([["", "All states"], ["active", "Active (working now)"], ...[...new Set([...array(data.tasks).map(task => task.state), "FAILED", "COMPLETED"])].map(state => [state, nice(state)])], taskStateFilter);
    taskStateFilter = "";
    const search = input("Search tasks: words, a task ID, a project, an error…"); search.type = "search";
    const holder = el("div");
    function paint() { const tasks = array(data.tasks).filter(task => (!projectFilter.value || task.project_id === projectFilter.value) && (!stateFilter.value || task.state === stateFilter.value || (stateFilter.value === "active" && ACTIVE.includes(task.state)))
      && (!search.value.trim() || search.value.trim().toLowerCase().split(/\s+/).every(word => `${task.description} ${task.id} ${projectFor(task.project_id)?.name || ""} ${failureReason(task)} ${task.results?.error || ""}`.toLowerCase().includes(word)))); holder.replaceChildren(panel("Tasks", tasks.length ? taskRows(tasks) : body(empty("No tasks here", "Create a task to get the AI team working.", button("+ New task", () => taskForm(projectFilter.value), "button primary"), "#")), null, tasks.length)); }
    projectFilter.addEventListener("change", paint); stateFilter.addEventListener("change", paint); search.addEventListener("input", paint);
    append(filters, field("Search", search), field("Project", projectFilter), field("State", stateFilter)); append(node, panel("Filter", body(filters)), holder); paint(); return node;
  }
  const TIER_NAME = {frontier: "frontier", balanced: "balanced", fast: "fast"};
  function catalogModels() { return ["claude", "codex"].flatMap(provider => array(data?.catalog?.[provider]).map(item => ({...item, provider}))); }
  function roleChoices() {
    const fromCatalog = catalogModels().map(item => [`catalog:${item.provider}:${item.model}`, `${item.label}${item.tier ? ` · ${TIER_NAME[item.tier]}` : ""}`]);
    const custom = runnable().map(profile => [profile.id, `${profile.label} (saved profile)`]);
    return [["auto", "⚡ Auto: the supervisor picks the best model"], ...fromCatalog, ...custom];
  }
  function profileSelect(role, value) { const chosen = value || data.roles?.[role] || "auto", choices = roleChoices(); if (!choices.some(([id]) => id === chosen)) choices.push([chosen, profileLabel(chosen)]); return select(choices, chosen); }
  function taskForm(projectId = "", description = "") {
    if (!array(data?.projects).length) { toast("Add a project first."); projectForm(); return; }
    const form = el("form"), project = select(array(data.projects).map(item => [item.id, item.name]), projectId || array(data.projects)[0].id);
    const objective = textarea("What should be built or fixed? Be specific about the result you expect."), requirements = textarea("Optional. One requirement per line."), criteria = textarea("Optional. How will you know it works? One per line."), allowed = input(". (whole project), or e.g. src/, README.md");
    const planner = profileSelect("planner"), implementer = profileSelect("implementer"), reviewer = profileSelect("reviewer");
    objective.required = true; objective.minLength = 8; objective.value = description;
    const team = el("div", "form-grid"); append(team, field("Planner", planner, "Writes the plan"), field("Coder", implementer, "Writes the code"), field("Reviewer", reviewer, "Checks the code; must be a different provider"));
    [planner, implementer, reviewer].forEach(control => { control.addEventListener("change", () => { if (control === implementer && control.value !== "auto" && reviewer.value !== "auto") { const coder = control.value.split(":")[1] || profiles().find(item => item.id === control.value)?.provider; const checker = reviewer.value.split(":")[1] || profiles().find(item => item.id === reviewer.value)?.provider; if (coder && coder === checker) reviewer.value = "auto"; } }); });
    const project_info = el("div"); function describe() { const chosen = projectFor(project.value); project_info.replaceChildren(chosen && !array(chosen.test_commands).length ? hint("This project has no test commands, so Cerebra cannot verify the work. Add them on the Projects page first.", true) : hint(`Tests: ${array(chosen?.test_commands).map(command => command.join(" ")).join("  |  ") || "none"}`)); } project.addEventListener("change", describe); describe();
    append(form, field("Project", project), project_info, field("What do you want?", objective), team, field("Requirements", requirements), field("Acceptance criteria", criteria), field("Files the AI may change", allowed, "Comma-separated paths inside the project. Leave blank for the whole project."), !agentsOn() ? hint("AI agents are switched off. You can create the task now, but it will only run after you switch agents on in Settings.", true) : null);
    const submit = submitButton("Create plan"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      const lines = value => value.split("\n").map(item => item.trim()).filter(Boolean);
      const task = await mutate("/api/tasks", {project_id: project.value, description: objective.value.trim(), planner: planner.value, implementer: implementer.value, reviewer: reviewer.value, requirements: lines(requirements.value), acceptance_criteria: lines(criteria.value), dependencies: [], allowed_paths: allowed.value.trim() ? allowed.value.split(",").map(value => value.trim()).filter(Boolean) : ["."]});
      closeDialog(); await refresh(true); toast("Plan created. Review and approve it to continue."); taskDetail(task.id);
    });
    showDialog("New task", form);
  }
  const STAGES = [["Plan", ["PENDING", "PLANNING"]], ["Approve", ["AWAITING_APPROVAL", "READY"]], ["Code", ["RUNNING", "NEEDS_CHANGES"]], ["Test", ["VERIFYING"]], ["Review", ["REVIEWING"]], ["Merge", []], ["Done", ["COMPLETED"]]];
  function stepper(task) {
    const node = el("div", "stepper"), pending = array(task.approvals).filter(item => String(item.status).toLowerCase() === "pending");
    let current = STAGES.findIndex(([, states]) => states.includes(task.state));
    if (pending.some(item => item.kind === "merge")) current = 5;
    if (task.state === "COMPLETED") current = 6;
    STAGES.forEach(([label], index) => node.append(el("span", index < current ? "done" : index === current ? "now" : "", label)));
    return node;
  }
  async function taskAction(taskId, action) { await act(action === "approve-plan" ? "Plan approved." : action === "retry" ? "Trying again from where it stopped." : `${nice(action)} requested.`, () => mutate(`/api/tasks/${encodeURIComponent(taskId)}/${action}`)); await refresh(true); taskDetail(taskId); }
  async function startTask(taskId) {
    const task = await act(null, () => mutate(`/api/tasks/${encodeURIComponent(taskId)}/start`)); if (!task) return;
    await refresh(true);
    const consent = pendingApprovals().find(item => item.task_id === taskId && item.kind === "live_execution");
    if (consent) approvalDialog(consent); else { toast("Task queued. The AI team is starting."); taskDetail(taskId); }
  }
  async function taskDetail(taskId, background = false) {
    if (background && (!dialog.open || detailTaskId !== taskId)) return;
    if (detailTaskId !== taskId) { detailTab = "Overview"; detailFingerprint = ""; }
    detailTaskId = taskId;
    try {
      const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
      if (detailTaskId !== taskId) return;
      const fingerprint = JSON.stringify(task); if (background && fingerprint === detailFingerprint) return; detailFingerprint = fingerprint;
      const scroll = background ? dialog.scrollTop : 0, root = el("div"), models = taskModels(task);
      append(root, append(el("div", "detail-top"), badge(task.state), task.mode === "mock" ? badge("retired demo", "muted") : null, badge(`${models.implementer} codes`, "blue"), badge(`${models.reviewer} reviews`, "purple")), stepper(task));
      const pending = array(task.approvals).filter(item => String(item.status).toLowerCase() === "pending");
      const progress = el("div", "progress-card"), story = task.state === "COMPLETED" ? ["Finished", "The work was tested, reviewed and merged into your project."] : pending.length ? ["Your decision is needed", `Approve or reject: ${pending.map(item => nice(item.kind)).join(", ")}.`] : task.finished_work?.ready ? ["Finished and reviewed: only the merge is left", `${task.finished_work.why} Press ✓ Merge the finished work. Try again would spend AI usage on work that's already done.`] : task.state === "FAILED" ? ["Stopped with a problem", task.results?.error || "See Runs & logs."] : task.state === "READY" ? ["Ready", "Press Start to let the AI team work."] : [nice(task.state), "This window updates automatically."];
      append(progress, el("strong", "", story[0]), el("p", "", story[1])); root.append(progress);
      const needs = task.missing_settings;
      if (needs && task.results?.blocked_reason !== "needs_settings") root.append(hint(`Its tests may need settings only you have${array(needs.names).length ? `: ${array(needs.names).slice(0, 8).join(", ")}${needs.names.length > 8 ? "…" : ""}` : ""}. This project has ${needs.example} but no ${needs.target || ".env"}, and no AI can supply your database or secrets. Create it from the Projects page (or copy ${needs.example} to ${needs.target || ".env"}), fill in your values, then press ↻ Try again. Cerebra lends it to test runs only; the AI never sees it.`, true));
      const fixing = task.results?.auto_fix;
      if (fixing && (fixing.attempts || fixing.stopped)) {
        const words = {fixing: "the Assistant is fixing it", council: "the Council is working out a solution", applying: "the Assistant is applying the Council's solution", gave_up: "it stopped trying; this task needs you", finished: "nothing to fix: the work is finished and only needs your merge", stopped: "you stopped it for this task", error: fixing.error || "it couldn't start", waiting: "waiting for the next failure", ended: "the Assistant's last attempt ended without fixing it. It tries again only if the failure changes; open the fix chat to see what it found."};
        root.append(append(el("div", "progress-card auto-fix-card"), el("strong", "", `Auto-fix · attempt ${fixing.attempts || 0} of ${data.auto_fix?.max_attempts ?? "?"}`), el("p", "", words[fixing.status] || nice(fixing.status || "")),
          append(el("div", "actions"), fixing.chat ? button("Open the fix chat", () => { closeDialog(); chatId = fixing.chat; cache.chats = null; location.hash = "chat"; render(); }, "button small") : null,
            fixing.council ? button("Open the Council meeting", () => { closeDialog(); councilId = fixing.council; location.hash = "council"; render(); }, "button small") : null)));
      }
      const actions = el("div", "actions");
      if (pending.some(item => item.kind === "plan")) actions.append(button("Approve plan", () => taskAction(taskId, "approve-plan"), "button primary"));
      if (task.state === "READY" && task.approved) actions.append(button("▶ Start", () => startTask(taskId), "button primary"));
      pending.filter(item => item.kind !== "plan").forEach(item => actions.append(button(`Decide: ${nice(item.kind)}`, () => approvalDialog(item), "button primary")));
      if (ACTIVE.includes(task.state) && !task.pause_requested) actions.append(button("Pause", () => taskAction(taskId, "pause")));
      if (task.pause_requested || task.state === "BLOCKED") actions.append(button("Resume", () => taskAction(taskId, "resume")));
      if (!["CANCELLED", "COMPLETED", "FAILED"].includes(task.state)) actions.append(button("Cancel", () => taskAction(taskId, "cancel"), "button danger"));
      const finished = task.finished_work || {};
      if (finished.ready) actions.append(button("✓ Merge the finished work", () => showDialog("Merge the finished work?", append(el("div"),
        el("p", "", finished.why),
        finished.uncommitted ? el("p", "", `Your project folder has uncommitted changes (${finished.uncommitted}). Cerebra saves them in Git's stash with a clear label first (nothing is deleted); run git stash pop in the project folder to get them back.`) : null,
        actionsRow(button("Cancel", closeDialog, "button ghost"), button("Merge", async () => { closeDialog(); if (await act("Merged into your project.", () => mutate(`/api/tasks/${encodeURIComponent(taskId)}/merge-finished`))) { await refresh(true); taskDetail(taskId); } }, "button primary")))), "button primary"));
      else if (task.state === "BLOCKED" && (task.results?.blocked_reason === "repository_has_changes" || /registered repository has user changes/.test(task.results?.error || ""))) actions.append(button("Set aside my changes and merge", () => showDialog("Set aside your changes and merge?", append(el("div"),
        el("p", "", task.results.error || "Your project folder has uncommitted changes."),
        el("p", "", "Cerebra saves them in Git's stash with a clear label (nothing is deleted), then merges this task's tested and reviewed work. To get them back later, run git stash pop in the project folder."),
        actionsRow(button("Cancel", closeDialog, "button ghost"), button("Set aside and merge", async () => { closeDialog(); if (await act("Merged. Your changes are saved in Git's stash.", () => mutate(`/api/tasks/${encodeURIComponent(taskId)}/set-aside-and-merge`))) { await refresh(true); taskDetail(taskId); } }, "button primary")))), "button primary"));
      if (task.state === "FAILED" || (task.state === "BLOCKED" && task.results?.error && !task.pause_requested && task.results?.blocked_reason !== "repository_has_changes")) actions.append(button("↻ Try again", () => taskAction(taskId, "retry"), finished.ready ? "button" : "button primary"));
      if (["FAILED", "BLOCKED"].includes(task.state)) actions.append(button("Ask the Assistant to fix this", () => askAssistantToFix(task), "button"));
      const fix = task.results?.auto_fix || {};
      const fixCovered = !fix.stopped && (data.auto_fix?.scope === "all" || fix.chosen);
      if (data.auto_fix?.enabled && !["COMPLETED", "CANCELLED"].includes(task.state)) append(actions, fixCovered
        ? button("■ Stop auto-fix", () => setAutoFix(taskId, false), "button danger")
        : ["FAILED", "BLOCKED"].includes(task.state) ? button("Auto-fix this task", () => setAutoFix(taskId, true), "button") : null);
      if (task.worktree_path && !["COMPLETED", "CANCELLED"].includes(task.state)) actions.append(viewControls("task", taskId, "▶ View this result"));
      actions.append(button("Plain report", () => { closeDialog(); location.hash = `report/${taskId}`; }, "button ghost"));
      if (["FAILED", "CANCELLED", "BLOCKED"].includes(task.state)) actions.append(button("Delete task", () => deleteTasks([{id: taskId, description: task.description, project: projectFor(task.project_id)?.name || ""}], () => render()), "button ghost"));
      root.append(actions);
      const tabs = el("div", "tabs"), pane = el("div");
      const views = {
        "Overview": () => append(el("div", "section"), routingCard(task), kv([["Project", projectFor(task.project_id)?.name], ["Planner", models.planner], ["Coder", models.implementer], ["Reviewer", models.reviewer], ["Files allowed", array(task.allowed_paths).join(", ")], ["Repairs", `${task.retry_count || 0} / ${task.max_retries < 0 ? "no limit" : task.max_retries ?? 3}`], ["Created", date(task.created_at)], ["Task ID", task.id]]), el("h3", "", "Plan"), plan(task.plan), array(task.requirements).length ? [el("h3", "", "Requirements"), list(task.requirements)] : null, task.results?.architecture?.output ? [el("h3", "", "AI architecture advisory"), code(task.results.architecture.output)] : null),
        "Results": () => { const node = append(el("div", "section"), el("h3", "", "Tests")); if (!array(task.test_results).length) node.append(el("p", "", "No tests have run yet.")); array(task.test_results).forEach(result => { const raw = (result.stdout || "") + (result.stderr ? `\n${result.stderr}` : "");
          append(node, append(el("div", "row-meta"), badge(result.passed ? "passed" : "failed", result.passed ? "green" : "red"), el("code", "", shortCommand(result.command)), result.attempt ? el("span", "", `attempt ${result.attempt}`) : null),
            !result.passed && result.what_failed ? [el("strong", "what-failed-label", "What failed"), code(result.what_failed), append(el("details"), el("summary", "", "Full output"), code(raw))] : raw.length > 4000 ? append(el("details"), el("summary", "", `Full output (${Math.round(raw.length / 1000)} KB)`), code(raw)) : code(raw)); }); node.append(el("h3", "", "Review findings")); if (!array(task.review_findings).length) node.append(el("p", "", array(task.reviews).length ? "The reviewer found no problems." : "No review yet.")); array(task.review_findings).forEach(finding => append(node, append(el("div", "row-meta"), badge(finding.severity, ["critical", "high"].includes(finding.severity) ? "red" : "amber"), el("code", "", `${finding.path || ""}${finding.line ? `:${finding.line}` : ""}`), finding.validated ? badge("verified", "green") : badge("unverified", "muted")), el("p", "", finding.message))); return node; },
        "Changes": () => append(el("div", "section"), kv([["Branch", task.branch], ["Base commit", task.base_commit], ["Working copy", task.worktree_path]]), code(task.diff || task.results?.diff || "No changes yet.")),
        "History": () => checkpointsView(task),
        "Runs & logs": () => { const node = el("div", "section"); if (!array(task.runs).length) node.append(el("p", "", "No AI runs yet.")); array(task.runs).forEach(run => append(node, append(el("div", "row-meta"), el("strong", "", `${nice(run.agent)} · ${run.role}`), badge(run.status, run.status === "succeeded" ? "green" : run.status === "running" ? "blue" : "red"), el("span", "", date(run.started_at))), run.error ? failureText(run.error) : null, run.output ? runOutput(run.output) : null)); node.append(el("h3", "", "Event history")); node.append(activityList([...array(task.events)].reverse(), 200)); return node; }
      };
      function choose(label) { detailTab = label; tabs.querySelectorAll("button").forEach(item => item.classList.toggle("active", item.textContent === label)); pane.replaceChildren(views[label]()); }
      Object.keys(views).forEach(label => tabs.append(button(label, () => choose(label), ""))); append(root, tabs, pane); choose(views[detailTab] ? detailTab : "Overview");
      showDialog(task.description, root); dialog.scrollTop = scroll;
    } catch (issue) { if (!background) toast(issue.message, true); }
  }
  function routingCard(task) {
    const routing = task.results?.routing, chosen = task.results?.models || {};
    if (!routing || !array(routing.automatic).length) return null;
    const node = el("div", "progress-card"), assessment = routing.assessment || {};
    append(node, el("strong", "", routing.status === "done" ? `Models chosen by the ${routing.decided_by}` : "The supervisor model is choosing the models…"),
      el("p", "", `Task looks ${assessment.level || "normal"}${assessment.kind === "writing" ? " and writing-heavy" : ""}: ${array(assessment.signals).join(", ")}.`),
      list(array(routing.automatic).map(role => `${{planner: "Planner", implementer: "Coder", reviewer: "Reviewer"}[role]}: ${chosen[role]?.label || "?"} (${chosen[role]?.why || ""})`)),
      routing.reason ? el("p", "row-meta", `Supervisor model: ${routing.reason}`) : null);
    return node;
  }
  // Two-click confirmation for actions that change files.
  function confirmButton(label, confirmLabel, action, className = "button small") {
    let armed = false; const node = button(label, async () => {
      if (!armed) { armed = true; node.textContent = confirmLabel; node.classList.add("danger"); setTimeout(() => { if (armed) { armed = false; node.textContent = label; node.classList.remove("danger"); } }, 5000); return; }
      node.disabled = true; await action(); }, className);
    return node;
  }
  function checkpointsView(task) {
    const node = el("div", "section");
    node.append(el("p", "row-meta", "Loading saved stages…"));
    (async () => {
      let data; try { data = await api(`/api/tasks/${encodeURIComponent(task.id)}/checkpoints`); } catch (issue) { node.replaceChildren(hint(issue.message, true)); return; }
      node.replaceChildren(el("p", "", "Every coding attempt is saved as a checkpoint in the task's own working copy. Restoring one sends it back through your tests and the independent review before anything can be merged."));
      if (!data.checkpoints.length) node.append(el("p", "row-meta", "No checkpoints yet: the coder hasn't saved any work."));
      const canRestore = ["BLOCKED", "FAILED", "AWAITING_APPROVAL"].includes(task.state);
      data.checkpoints.slice().reverse().forEach((item, index) => {
        const card = el("div", "action-card"), top = el("div", "row-meta");
        append(top, el("code", "", item.commit.slice(0, 8)), el("strong", "", item.message), el("span", "", date(item.at)),
          item.commit === data.merged ? badge("merged into project", "green") : null, item.commit === data.current ? badge("current", "blue") : null);
        card.append(top, el("p", "row-meta", `${item.files.length} file(s): ${item.files.slice(0, 6).join(", ")}${item.files.length > 6 ? "…" : ""}`));
        if (canRestore && item.commit !== data.current) card.append(confirmButton("Restore this checkpoint", "Click again to restore", async () => {
          if (await act("Checkpoint restored. Resume, then Start, to test and review it.", () => mutate(`/api/tasks/${encodeURIComponent(task.id)}/checkpoints/restore`, {commit: item.commit}))) { await refresh(true); taskDetail(task.id); }
        }));
        node.append(card);
      });
      if (data.undone) node.append(hint(`This task's changes were undone in your project on ${date(data.undone.at)} (commit ${data.undone.commit.slice(0, 8)}).`));
      else if (task.state === "COMPLETED" && data.merged) node.append(append(el("div", "action-card"), el("strong", "", "Undo this task in your project"),
        el("p", "", "Adds one new commit to your project that reverses this task's changes. Your history is kept. If later work changed the same lines, Cerebra stops and changes nothing."),
        confirmButton("Undo merge", "Click again to undo", async () => { if (await act("Undone: a revert commit was added to your project.", () => mutate(`/api/tasks/${encodeURIComponent(task.id)}/undo`))) { await refresh(true); taskDetail(task.id); } }, "button small danger")));
      if (!canRestore && task.state !== "COMPLETED") node.append(hint("Pause the task to restore an earlier checkpoint."));
    })();
    return node;
  }
  function list(values) { const node = el("ul"); array(values).forEach(value => node.append(el("li", "", typeof value === "string" ? value : json(value)))); return node; }
  function plan(milestones) { const node = el("ol"); array(milestones).forEach(item => { const entry = el("li"); append(entry, el("strong", "", `${item.milestone} · ${nice(item.agent)}`), list(item.tasks)); node.append(entry); }); return node; }

  // ---------- approvals ----------
  const APPROVAL_TEXT = {
    plan: ["Approve the plan?", "Saying yes makes the task ready. Nothing runs until you press Start."],
    live_execution: ["Let the AI agents work on this task?", "Codex/Claude will run on your accounts (this can use your plan's usage). They can only change the allowed files, inside a separate copy of the project."],
    review_findings: ["Are these review findings real?", "Yes sends them back to the coder to fix. No dismisses them, and the task moves on to the merge decision."],
    merge: ["Add the finished code to your project?", "The code passed its tests and an independent review. Yes merges it into your project's main branch on this computer. Nothing is pushed to GitHub."]
  };
  function approvalCards(approvals) {
    const list = el("div", "row-list");
    approvals.forEach(approval => { const task = taskFor(approval.task_id), row = el("div", "row"), info = el("div", "row-main"); append(info, el("strong", "", APPROVAL_TEXT[approval.kind]?.[0] || nice(approval.kind)), el("div", "row-meta", task?.description || approval.task_id)); append(row, info, button("Decide", () => approvalDialog(approval), "button small primary")); list.append(row); });
    return list;
  }
  function approvalsView() {
    const node = el("div"), waiting = pendingApprovals();
    const merges = finishedTasks();
    if (waiting.length || !merges.length) node.append(panel("Waiting for you", waiting.length ? approvalCards(waiting) : body(empty("Nothing to decide", "When a task needs your yes, it appears here.", null, "✓")), null, waiting.length));
    if (merges.length) node.append(panel("Finished work to merge", taskRows(merges), null, merges.length));
    const history = array(data.approvals).filter(item => String(item.status).toLowerCase() !== "pending").slice(0, 60);
    if (history.length) node.append(panel("Decision history", table(["Decision", "Task", "Answer", "When"], history.map(item => [nice(item.kind), button(taskFor(item.task_id)?.description?.slice(0, 60) || item.task_id.slice(0, 8), () => taskDetail(item.task_id), "text-link"), badge(item.status), date(item.resolved_at)]))));
    return node;
  }
  function approvalDialog(approval) {
    detailTaskId = "";
    const [question, explain] = APPROVAL_TEXT[approval.kind] || [nice(approval.kind), ""], task = taskFor(approval.task_id), root = el("div", "section");
    append(root, el("p", "", task?.description || ""), hint(explain));
    if (approval.kind === "merge") append(root, el("h3", "", "Changes"), code(approval.payload?.diff || "No diff recorded."));
    else if (approval.kind === "review_findings") array(approval.payload?.findings).forEach(finding => append(root, append(el("div", "row-meta"), badge(finding.severity, "amber"), el("code", "", finding.path || "")), el("p", "", finding.message)));
    else if (approval.kind === "plan") root.append(plan(approval.payload?.plan));
    const buttons = actionsRow();
    async function decide(approve) { buttons.querySelectorAll("button").forEach(item => { item.disabled = true; }); const done = await act(approve ? "Recorded: yes." : "Recorded: no.", () => mutate(`/api/approvals/${encodeURIComponent(approval.id)}`, {approve})); await refresh(true); if (done && approval.kind === "live_execution" && approve) { await act("The AI team is starting.", () => mutate(`/api/tasks/${encodeURIComponent(approval.task_id)}/start`)); await refresh(true); } if (done) taskDetail(approval.task_id); else buttons.querySelectorAll("button").forEach(item => { item.disabled = false; }); }
    append(buttons, button("No", () => decide(false), "button danger"), button("Yes", () => decide(true), "button primary")); root.append(buttons);
    showDialog(question, root);
  }

  // ---------- run & view: open what was built in the browser or the right program ----------
  function viewControls(kind, id, label = "▶ Run & view") {
    const holder = el("span", "view-controls"), path = `/api/view/${kind}/${encodeURIComponent(id)}`;
    const run = button(label, () => runAndView(), "button small"), stop = button("■ Stop", async () => { await act("Stopped.", () => api(path, {method: "DELETE"})); paint({state: "stopped"}); }, "button small ghost");
    function paint(status) { stop.hidden = !["running", "starting"].includes(status.state); run.textContent = status.state === "running" ? "↗ Open again" : status.state === "starting" ? "Starting…" : label; run.disabled = status.state === "starting"; }
    async function runAndView() {
      let status = await act(null, () => mutate(path)); if (!status) return;
      paint(status); toast(status.message || "Starting…");
      for (let tries = 0; status.state === "starting" && tries < 300; tries++) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        try { status = (await api(path)).status; } catch (issue) { break; }
        paint(status);
      }
      if (status.state === "failed") toast(`${status.message}${status.log ? ` Log: ${status.log}` : ""}`, true); else if (status.state !== "starting") toast(status.message);
    }
    api(path).then(info => { run.title = info.plan?.how || ""; paint(info.status); }).catch(() => {});
    paint({state: "stopped"});
    return append(holder, run, stop);
  }

  // ---------- projects ----------
  // "C:\…\node.exe C:\…\pnpm.mjs check" reads as "node pnpm check"; the full command is in the tooltip.
  function shortCommand(command) {
    return array(command).map((part, index) => /[\\/]/.test(part) && (index === 0 || /\.(m?js|cjs|py|exe|cmd)$/i.test(part)) ? part.split(/[\\/]/).pop().replace(/\.(exe|mjs|cjs|js|cmd)$/i, "") : part).join(" ");
  }
  // Ready-made, well-scoped tasks that let the owner's own apps take payments with Stripe (built, tested and
  // reviewed like any task; keys come from the project's settings file, never from code).
  const PAYMENT_TASKS = {
    checkout: ["One-time payments", "Customers pay once for a product, service or booking (Stripe Checkout).",
      "Add one-time payments with Stripe Checkout. On the server, create a Checkout Session for the item being bought (price and currency decided on the server, never trusted from the browser) and redirect the customer to Stripe's hosted page; add success and cancelled pages. Add a webhook endpoint that verifies the Stripe-Signature header with STRIPE_WEBHOOK_SECRET and marks the order paid only on checkout.session.completed with payment_status 'paid', idempotently (a repeated event changes nothing). Read STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET from environment variables only; never put keys in code, the browser or logs. Add both names, with empty values, to the example settings file (.env.example). Write automated tests that mock Stripe (no network): session creation uses the server's price, a valid signed webhook marks the order paid once, an invalid signature is rejected. Document in the README how to create test keys in Stripe and run the Stripe CLI to forward webhooks locally. Use Stripe test mode only; do not deploy."],
    subscription: ["Subscriptions", "Customers pay monthly or yearly for access (Stripe Billing + customer portal).",
      "Add subscriptions with Stripe Billing. On the server, create a Checkout Session in subscription mode for a plan whose Price ID comes from configuration (STRIPE_PRICE_MONTHLY, optionally STRIPE_PRICE_YEARLY), linked to the signed-in user. Add a webhook endpoint that verifies the Stripe-Signature header with STRIPE_WEBHOOK_SECRET and keeps each user's subscription status in the database from customer.subscription.created/updated/deleted and invoice.paid/payment_failed, idempotently. Gate the paid features on an active or trialing status, checked on the server. Add a 'Manage billing' button that opens the Stripe customer portal. Read STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET and the price IDs from environment variables only; never put keys in code, the browser or logs; add the names, with empty values, to the example settings file (.env.example). Write automated tests that mock Stripe (no network) for the webhook status changes, the server-side gate and signature rejection. Document in the README how to create the product, prices and test keys in Stripe and forward webhooks with the Stripe CLI. Use Stripe test mode only; do not deploy."]};
  function storefrontTask(selling) {
    const lines = selling.map(item => `- ${item.name}: ${cash(item.price, item.currency)}${item.description ? ` (${item.description.replace(/\s+/g, " ").slice(0, 160)})` : ""}. Buy button link: ${item.link}`).join("; ");
    return "Add a clear 'Services and pricing' section (or page, linked from the main navigation) that shows exactly these offers, with their names, prices and descriptions as written, and a prominent 'Buy' or 'Book now' button for each that opens its Stripe payment link in the same tab: " + lines +
      ". Use only these facts: invent no other prices, reviews, guarantees or claims. Match the site's existing look, keep it fast, accessible (real links with descriptive text) and mobile-friendly. Add automated tests that check every offer, price and exact link appears. Do not add any Stripe keys or server code: the links are public payment pages.";
  }
  function paymentsTaskChooser(project) {
    const root = el("div");
    root.append(hint(`Let ${project.name} take payments through your Stripe account. Cerebra plans, codes, tests and reviews it like any task, and you approve every step. It uses test mode and keeps keys in the project's settings file (lent to tests, never shown to the AI).`));
    Object.values(PAYMENT_TASKS).forEach(([title, detail, text]) => root.append(append(el("div", "action-card"), el("strong", "", title), el("p", "", detail), button("Use this", () => { closeDialog(); taskForm(project.id, text); }, "button small primary"))));
    const storefront = el("div"); root.append(storefront);
    api("/api/money").then(state => {
      const selling = array(state.products).filter(item => item.selling && item.link);
      const card = append(el("div", "action-card"), el("strong", "", "Show my services with Buy buttons"),
        el("p", "", selling.length ? `Adds what you sell on Stripe (${selling.map(item => item.name).join(", ")}) to this site, each with its price and a Buy button that opens its Stripe payment page. No keys and no server needed.` : "First put a service or product on sale on the Money page (Products you sell › Start selling with Stripe); then its Buy button can go on this site."));
      if (selling.length) card.append(button("Use this", () => { closeDialog(); taskForm(project.id, storefrontTask(selling)); }, "button small primary"));
      storefront.replaceChildren(card);
    }).catch(() => {});
    showDialog(`Get paid in ${project.name}`, root);
  }
  function projectsView() {
    if (!array(data.projects).length) return panel("Projects", body(empty("No projects yet", "Add an existing folder, start a new project, or clone one from GitHub.", button("+ Add project", () => projectForm(), "button primary"), "{}")));
    const grid = el("div", "grid cards");
    data.projects.forEach(project => {
      const card = el("article", "card"), top = el("div", "card-top"), info = el("div"), tasks = array(data.tasks).filter(task => task.project_id === project.id);
      const where = el("div", "row-meta project-path", project.path); where.title = project.path;
      append(info, el("h3", "", project.name), where); append(top, el("span", "icon-tile", "{}"), info);
      const tests = array(project.test_commands), shown = el("div", "test-commands");
      tests.forEach(command => { const line = el("code", "", shortCommand(command)); line.title = command.join(" "); shown.append(line); });
      append(card, top, kv([["Branch", project.default_branch], ["Tasks", tasks.length], ["Tests", tests.length ? shown : "none — add some"]]));
      const needs = el("div"); card.append(needs);
      api(`/api/projects/${encodeURIComponent(project.id)}/settings-files`).then(info => {
        if (!info.missing) return;
        const names = array(info.missing.names), target = info.missing.target || ".env";
        needs.replaceChildren(append(hint(`Its tests need local settings this laptop doesn't have yet${names.length ? `: ${names.slice(0, 6).join(", ")}${names.length > 6 ? "…" : ""}` : ""}. They belong in ${target}, which doesn't exist yet. Cerebra lends it to test runs only; the AI never sees it.`, true),
          append(el("div", "actions"), button(`Create ${target} and open it`, async () => { if (await act(result => `Created ${result.created} from ${info.missing.example}. Fill in your own values and save; tasks waiting for these settings continue by themselves.`, () => mutate(`/api/projects/${encodeURIComponent(project.id)}/settings-file`, {}))) render(); }, "button small"))));
      }).catch(() => {});
      append(card, append(el("div", "card-footer"), button("New task", () => taskForm(project.id), "button small primary"), viewControls("project", project.id), button("Chat", () => newChat(project.id), "button small"), button("Get paid…", () => paymentsTaskChooser(project), "button small"), button("Tests…", () => testsForm(project), "button small ghost"), button("Push", () => act(result => `Pushed to ${result.remote}`, () => mutate(`/api/projects/${project.id}/push`, {}, "POST", 600000)), "button small ghost"), button("Publish…", () => publishForm(project), "button small ghost")));
      grid.append(card);
    });
    return grid;
  }
  const TEST_PRESETS = [["none", "Not yet: add tests later", null], ["pytest", "Python: pytest", ["python", "-m", "pytest", "-q"]], ["unittest", "Python: unittest", ["python", "-m", "unittest", "-q"]],
    ["npm", "Node.js: npm test", ["npm", "test"]], ["pnpm", "Node.js: pnpm test", ["pnpm", "test"]], ["yarn", "Node.js: yarn test", ["yarn", "test"]], ["dotnet", ".NET: dotnet test", ["dotnet", "test"]],
    ["go", "Go: go test ./...", ["go", "test", "./..."]], ["cargo", "Rust: cargo test", ["cargo", "test"]], ["maven", "Java: mvn test", ["mvn", "test"]], ["gradle", "Java/Kotlin: gradle test", ["gradle", "test"]],
    ["flutter", "Flutter: flutter test", ["flutter", "test"]], ["laravel", "PHP Laravel: php artisan test", ["php", "artisan", "test"]], ["custom", "Something else: type the command", null]];
  function splitCommand(text) { return (text.match(/"[^"]*"|'[^']*'|\S+/g) || []).map(part => part.replace(/^(["'])(.*)\1$/, "$2")); }
  function testPicker(initial = []) {
    const choice = select(TEST_PRESETS.map(([key, label]) => [key, label])), custom = input("e.g. npm run test:ci"), note = el("small", "detect-note", ""), advanced = commandsInput("");
    const customField = field("Test command", custom, "Type it exactly as you would in a terminal inside the project folder."), more = append(el("details", "advanced-tests"), el("summary", "", "Several commands? (advanced)"), field("One list per command", advanced, TEST_HELP));
    const node = append(el("div", "test-picker"), field("How is it tested?", choice, "Cerebra runs this after every change to prove the work."), customField, note, more);
    const sync = () => customField.classList.toggle("hidden", choice.value !== "custom");
    choice.addEventListener("change", sync);
    function set(commands, reason = "") {
      commands = array(commands);
      if (commands.length > 1) { advanced.value = JSON.stringify(commands); more.open = true; choice.value = "none"; }
      else if (!commands.length) choice.value = "none";
      else { const match = TEST_PRESETS.find(([, , command]) => command && JSON.stringify(command) === JSON.stringify(commands[0])); choice.value = match ? match[0] : "custom"; if (!match) custom.value = commands[0].join(" "); }
      note.textContent = reason; sync();
    }
    function value() {
      if (advanced.value.trim() && advanced.value.trim() !== "[]") return parseCommands(advanced.value);
      if (choice.value === "custom") { const parts = splitCommand(custom.value.trim()); if (!parts.length) throw new Error("Type the test command, or choose “Not yet”."); return [parts]; }
      const preset = TEST_PRESETS.find(([key]) => key === choice.value); return preset && preset[2] ? [preset[2]] : [];
    }
    set(initial); return {node, set, value};
  }
  function commandsInput(value) { return textarea('[["python", "-m", "pytest", "-q"]]', value); }
  function parseCommands(text) { let commands; try { commands = JSON.parse(text || "[]"); } catch { throw new Error("Test commands must be JSON, for example [[\"npm\", \"test\"]]"); } if (!Array.isArray(commands) || commands.some(command => !Array.isArray(command) || !command.length || command.some(arg => typeof arg !== "string"))) throw new Error("Use a list of argument lists, each argument a string."); return commands; }
  const TEST_HELP = "How Cerebra checks the work. Examples: [[\"python\",\"-m\",\"pytest\",\"-q\"]] · [[\"npm\",\"test\"]] · [[\"dotnet\",\"test\"]]. These run as your Windows user, so only add projects you trust.";
  function projectForm(source = "existing") {
    const form = el("form"), kind = select([["existing", "A folder on this computer"], ["new", "A new, empty project"], ["github", "Clone from GitHub"]], source), name = input("e.g. Booking platform"), path = input("C:\\Users\\you\\Projects\\my-app"), repo = el("select"), tests = commandsInput("[]"), consent = check("I trust this project and allow Cerebra to create working copies and run its test commands as my Windows user.");
    const pathField = field("Folder", path, "The exact Git repository folder."), repoField = field("GitHub repository", repo, "Sign in on the GitHub page to see your repositories.");
    async function loadRepos() { repo.replaceChildren(option("", "Loading your repositories…")); try { cache.repos = cache.repos || await api("/api/github/repositories", {timeout: 60000}); repo.replaceChildren(...cache.repos.map(item => option(item.name, `${item.name} · ${item.visibility?.toLowerCase() || ""}`))); if (!cache.repos.length) repo.replaceChildren(option("", "No repositories found")); } catch (issue) { repo.replaceChildren(option("", issue.message)); } }
    function sync() { pathField.classList.toggle("hidden", kind.value !== "existing"); repoField.classList.toggle("hidden", kind.value !== "github"); if (kind.value === "github" && !repo.options.length) loadRepos(); }
    kind.addEventListener("change", sync); sync();
    const picker = testPicker([]);
    const browse = button("Browse…", async () => { browse.disabled = true; try { const chosen = await mutate("/api/pick-folder", {}, "POST", 600000); if (chosen.path) { path.value = chosen.path; if (!name.value.trim()) name.value = chosen.path.split(/[\\/]/).filter(Boolean).pop() || ""; detect(); } } catch (issue) { toast(issue.message, true); } finally { browse.disabled = false; } }, "button small");
    async function detect() { const folder = path.value.trim(); if (!/^[A-Za-z]:[\\/]/.test(folder)) return; try { const found = await api(`/api/projects/detect?path=${encodeURIComponent(folder)}`); picker.set(found.test_commands, found.key === "none" ? found.reason : `Detected: ${found.reason}.`); } catch (issue) { picker.set([], issue.message); } }
    path.addEventListener("change", detect); pathField.append(browse);
    append(form, field("Where is the project?", kind), field("Name", name), pathField, repoField, picker.node, consent.wrap);
    const submit = submitButton("Add project"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      if (!consent.control.checked) throw new Error("Tick the trust box to continue.");
      const commands = picker.value();
      const project = kind.value === "github" ? await mutate("/api/github/clone", {repository: repo.value, name: name.value.trim(), authorize: true, test_commands: commands}, "POST", 600000)
        : await mutate("/api/projects", {name: name.value.trim() || "New project", path: kind.value === "new" ? "" : path.value.trim(), create_new: kind.value === "new", authorize: true, test_commands: commands});
      closeDialog(); await refresh(true); toast(`Project “${project.name}” added.`);
    });
    showDialog("Add a project", form);
  }
  function testsForm(project) {
    const form = el("form"), picker = testPicker(project.test_commands || []), redetect = button("Detect again", async () => { try { const found = await api(`/api/projects/detect?path=${encodeURIComponent(project.path)}`); picker.set(found.test_commands, found.key === "none" ? found.reason : `Detected: ${found.reason}.`); } catch (issue) { toast(issue.message, true); } }, "button small ghost");
    append(form, picker.node, redetect);
    const submit = submitButton("Save"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => { await mutate(`/api/projects/${project.id}`, {test_commands: picker.value()}, "PATCH"); closeDialog(); await refresh(true); toast("Test commands saved."); });
    showDialog(`Tests · ${project.name}`, form);
  }
  function publishForm(project) {
    const form = el("form"), name = input("repository-name", project.name.toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "")), visibility = select([["private", "Private — only you"], ["public", "Public — anyone can see it"]], "private");
    append(form, hint("Creates a new repository on your GitHub account and pushes this project to it."), field("Repository name", name), field("Visibility", visibility));
    const submit = submitButton("Publish to GitHub"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => { await mutate(`/api/projects/${project.id}/publish`, {name: name.value.trim(), visibility: visibility.value}, "POST", 600000); closeDialog(); await refresh(true); toast("Published to GitHub."); });
    showDialog(`Publish · ${project.name}`, form);
  }

  // ---------- chat ----------
  let chatId = "", chatPoll = 0, councilId = "", councilPoll = 0, councilShown = "";
  // Re-rendering a live conversation must not move the reader: follow new messages only when already at the bottom.
  // Measure before the old list is replaced (a detached element reports zero sizes), restore after.
  function readingPlace(node) { return node && node.isConnected ? {top: node.scrollTop, atBottom: node.scrollHeight - node.scrollTop - node.clientHeight < 40} : null; }
  function keepReading(place, next) { next.scrollTop = !place || place.atBottom ? next.scrollHeight : place.top; }
  function markdown(text) {
    // A deliberately small renderer that builds DOM nodes: fences, headings, lists, inline code, bold.
    const root = el("div"), lines = String(text || "").split("\n"); let paragraph = [], listNode = null, fence = null;
    const inline = (target, value) => { String(value).split(/(`[^`]+`|\*\*[^*]+\*\*)/g).forEach(part => { if (/^`[^`]+`$/.test(part)) target.append(el("code", "", part.slice(1, -1))); else if (/^\*\*[^*]+\*\*$/.test(part)) target.append(el("strong", "", part.slice(2, -2))); else if (part) target.append(document.createTextNode(part)); }); return target; };
    const flush = () => { if (paragraph.length) { root.append(inline(el("p"), paragraph.join(" "))); paragraph = []; } listNode = null; };
    for (const line of lines) {
      if (fence) { if (/^```/.test(line)) { root.append(append(el("pre"), el("code", "", fence.join("\n")))); fence = null; } else fence.push(line); continue; }
      if (/^```/.test(line)) { flush(); fence = []; continue; }
      const heading = line.match(/^#{1,4}\s+(.*)/), bullet = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
      if (heading) { flush(); root.append(inline(el("h4"), heading[1])); }
      else if (bullet) { if (paragraph.length) { root.append(inline(el("p"), paragraph.join(" "))); paragraph = []; } if (!listNode) { listNode = el(/^\s*\d/.test(line) ? "ol" : "ul"); root.append(listNode); } listNode.append(inline(el("li"), bullet[1])); }
      else if (!line.trim()) flush();
      else { listNode = null; paragraph.push(line); }
    }
    if (fence) root.append(append(el("pre"), el("code", "", fence.join("\n"))));
    flush(); return root;
  }
  const chatDefault = () => (data?.roles?.implementer && data.roles.implementer !== "auto" ? data.roles.implementer : "codex");
  function actionCard(action) {
    const node = el("div", `action-card ${action.status}`), top = el("div", "row-meta");
    append(top, badge(action.status === "proposed" ? "proposed" : action.status, {done: "green", failed: "red", proposed: "amber", dismissed: "muted", running: "blue"}[action.status]), el("strong", "", action.summary));
    node.append(top);
    if (action.result) node.append(el("p", "", action.result));
    if (action.status === "proposed") {
      const decide = run => async event => { node.querySelectorAll("button").forEach(item => { item.disabled = true; }); if (await act(run ? "Done." : "Dismissed.", () => mutate(`/api/chats/actions/${encodeURIComponent(action.id)}`, {run}, "POST", 120000))) { await refresh(true); render(); } else node.querySelectorAll("button").forEach(item => { item.disabled = false; }); };
      node.append(append(el("div", "actions"), button("Do it", decide(true), "button small primary"), button("Dismiss", decide(false), "button small ghost")));
    }
    return node;
  }
  async function setAutoFix(taskId, enabled) {
    if (await act(enabled ? "Auto-fix will work on this task." : "Auto-fix stopped for this task. Its fix chat and any fix run were stopped; Resume continues the run.", () => mutate(`/api/tasks/${encodeURIComponent(taskId)}/auto-fix`, {enabled}))) { await refresh(true); taskDetail(taskId); }
  }
  async function askAssistantToFix(task) {
    const conversation = await act(null, () => mutate("/api/chats", {profile: chatDefault(), project_id: task.project_id || null, title: `Fix: ${task.description.slice(0, 50)}`}));
    if (!conversation) return;
    const sent = await act("The Assistant is reading the logs…", () => mutate(`/api/chats/${encodeURIComponent(conversation.id)}/messages`, {text: `Task ${task.id.slice(0, 8)} (“${task.description.slice(0, 120)}”) is ${task.state.toLowerCase()}. Read its failure logs, find the root cause from the evidence, and fix it: give the coder precise instructions with retry_task, or tell me what I need to do if it needs me (for example signing in).`}));
    if (sent) { closeDialog(); chatId = conversation.id; cache.chats = null; location.hash = "chat"; render(); }
  }
  async function newChat(projectId = "", profile = chatDefault()) {
    const conversation = await act(null, () => mutate("/api/chats", {profile, project_id: projectId || null}));
    if (conversation) { chatId = conversation.id; cache.chats = null; if (page === "chat") render(); else location.hash = "chat"; }
  }
  // ---------- council: a recorded meeting between two models ----------
  function councilView() {
    const root = el("div", "chat council"), side = el("div", "chat-list"), head = el("div", "chat-list-head"), items = el("div", "chat-items"), main = el("div", "chat-main"), token = renderToken;
    append(head, button("+ New meeting", () => councilForm(), "button primary"));
    append(side, head, items); append(root, side, main);
    async function loadList() {
      let meetings = []; try { meetings = await api("/api/council"); } catch (issue) { toast(issue.message, true); }
      if (token !== renderToken) return;
      items.replaceChildren();
      if (!meetings.length) items.append(el("p", "hint", "No meetings yet. Start one and pick what Codex and Claude should decide."));
      meetings.forEach(item => { const entry = button("", () => { councilId = item.id; openMeeting(); paint(); }, `chat-item${item.id === councilId ? " active" : ""}`); entry.dataset.id = item.id;
        append(entry, el("strong", "", item.topic.slice(0, 80)), el("small", "", `${projectFor(item.project_id)?.name || "project"} · ${nice(item.status)} · ${relative(item.updated_at)}`)); items.append(entry); });
      if (!councilId && meetings.length) councilId = meetings[0].id;
      paint(); openMeeting();
    }
    function paint() { items.querySelectorAll(".chat-item").forEach(node => node.classList.toggle("active", node.dataset.id === councilId)); }
    async function openMeeting(poll = false) {
      clearTimeout(councilPoll);
      if (!councilId) { main.replaceChildren(body(empty("Council", "Codex and Claude read your project, talk it through with each other, and agree on a short list of improvements, each with who should build it. You can follow the whole conversation and turn any idea into a task.", button("+ New meeting", () => councilForm(), "button primary"), "⇄"))); return; }
      let state; try { state = await api(`/api/council/${encodeURIComponent(councilId)}`); } catch (issue) { main.replaceChildren(body(empty("Meeting unavailable", issue.message))); return; }
      if (token !== renderToken || page !== "council") return;
      const shown = JSON.stringify([state.id, state.status, state.busy, state.support_chat, state.handoff_error, state.messages.map(message => [message.id, message.status]), state.proposals.map(item => item.task_id)]);
      if (poll && shown === councilShown) { councilPoll = setTimeout(() => { if (token === renderToken && page === "council") openMeeting(true); }, 2500); return; }
      councilShown = shown;
      const place = readingPlace(main.querySelector(".messages")), pageY = window.scrollY;
      const header = el("div", "chat-head"), messages = el("div", "messages");
      append(header, el("strong", "", state.topic.slice(0, 120)), badge(projectFor(state.project_id)?.name || "project", "purple"), badge(`${profileLabel(state.first)} ⇄ ${profileLabel(state.second)}`, "blue"), badge("read-only meeting", "green"),
        badge(nice(state.status), state.status === "done" ? "green" : state.status === "failed" ? "red" : state.status === "running" ? "cyan" : "muted"), el("span", "", ""),
        state.support_chat ? button("Open Support chat →", () => { chatId = state.support_chat; location.hash = "chat"; }, "button small primary")
          : state.status === "done" && state.proposals.length ? button("Send to Support", async () => { if (await act("Sent to Support. It is checking the plan and preparing the tasks.", () => mutate(`/api/council/${encodeURIComponent(councilId)}/support`, {}))) openMeeting(); }, "button small primary") : null,
        state.busy ? button("Stop meeting", () => act("Stopping after the current turn…", () => mutate(`/api/council/${encodeURIComponent(councilId)}/stop`, {})), "button small danger")
                   : button("Delete", async () => { if (await act("Meeting deleted.", () => api(`/api/council/${encodeURIComponent(councilId)}`, {method: "DELETE"}))) { councilId = ""; loadList(); } }, "button small ghost"));
      if (!agentsOn()) messages.append(hint("AI agents are switched off, so the meeting can't run. Turn them on in Settings › Agent permissions.", true));
      messages.append(hint(`The owner asked: “${state.topic}”` + (state.rounds === 0 ? " · they talk until they both agree" : ` · ${state.rounds} round${state.rounds === 1 ? "" : "s"}`) + (state.send_to_support ? " · the plan goes to Support when they agree" : "")));
      const kinds = {discussion: "", closing: " · closing summary", confirm: " · confirms the list"};
      state.messages.forEach(message => {
        const row = el("div", `message ${message.speaker === state.second ? "user" : "assistant"}`), bubble = el("div", `bubble${message.status === "failed" ? " failed" : ""}`), holder = el("div");
        if (message.status === "pending") bubble.append(append(el("div", "typing"), el("span"), el("span"), el("span")), el("small", "", `${nice(message.provider)} is reading the project and replying…`));
        else if (message.status === "failed") bubble.append(failureText(message.error || "No answer."));
        else bubble.append(markdown(message.content.replace(/```cerebra-council[\s\S]*?```/g, "").trim() || "(agreed list below)"));
        append(holder, bubble, el("div", "message-meta", `${nice(message.provider)}${message.model ? ` · ${message.model}` : ""} · round ${message.round}${kinds[message.kind] || ""} · ${relative(message.created_at)}`));
        append(row, el("span", "avatar", PROVIDER_ICON[message.provider] || "AI"), holder); messages.append(row);
      });
      if (state.error) messages.append(append(hint("", state.status === "failed"), failureText(state.error, "")));
      if (state.handoff_error) messages.append(hint(`Sending the plan to Support failed: ${state.handoff_error}`, true));
      const conclusionPlace = readingPlace(main.querySelector(".council-conclusion"));
      const panes = append(el("div", "council-body"), messages), parts = [header, panes];
      let conclusion = null;
      if (state.summary || state.solution || state.proposals.length) {
        conclusion = el("section", "council-conclusion");
        conclusion.append(el("h2", "", "Conclusion"));
        if (state.summary) conclusion.append(el("p", "", state.summary));
        if (state.solution) {
          const way = append(el("div", "way-forward"), el("span", "eyebrow", "The agreed way forward"), el("strong", "", state.solution.title), el("p", "", state.solution.description),
            state.solution.why ? el("p", "row-meta", `Why this one: ${state.solution.why}`) : null);
          if (array(state.solution.steps).length) way.append(append(el("ol", ""), ...state.solution.steps.map(step => el("li", "", step))));
          conclusion.append(way);
        }
      }
      if (state.proposals.length) {
        const list = el("div", "council-proposals");
        state.proposals.forEach((proposal, index) => {
          const card = append(el("div", "proposal"), el("strong", "", proposal.title), el("p", "", proposal.description), proposal.why ? el("p", "row-meta", `Why: ${proposal.why}`) : null,
            el("p", "row-meta", `Builds it: ${nice(proposal.executor)} · reviews it: ${proposal.reviewer ? nice(proposal.reviewer) : "the other model"}`),
            proposal.acceptance_criteria.length ? append(el("ul", ""), ...proposal.acceptance_criteria.map(item => el("li", "", item))) : null);
          card.append(proposal.task_id ? button("Open task →", () => taskDetail(proposal.task_id), "button small ghost")
            : button("Create task", async () => { const made = await act("Task created. It still asks for your approval before any work starts.", () => mutate(`/api/council/${encodeURIComponent(councilId)}/proposals/${index}/task`, {})); if (made) { await refresh(true); openMeeting(); } }, "button small primary"));
          list.append(card);
        });
        append(conclusion, el("h2", "", "Tasks that carry it out"), el("p", "row-meta", "Each task runs through the normal steps: your plan approval, tests, the other model's review, and your approval to merge. Full access applies only if you've switched it on."), list);
      }
      if (conclusion) { panes.classList.add("split"); panes.append(conclusion); }
      main.replaceChildren(...parts);
      keepReading(place, messages); window.scrollTo(window.scrollX, pageY);
      if (conclusion && conclusionPlace) conclusion.scrollTop = conclusionPlace.top;
      if (state.busy || (state.send_to_support && state.status === "done" && !state.support_chat && !state.handoff_error))
        councilPoll = setTimeout(() => { if (token === renderToken && page === "council") openMeeting(true).then(() => loadListQuiet()); }, 2500);
    }
    async function loadListQuiet() { try { const meetings = await api("/api/council"); const current = meetings.find(item => item.id === councilId); const entry = items.querySelector(`[data-id="${councilId}"] small`); if (current && entry) entry.textContent = `${projectFor(current.project_id)?.name || "project"} · ${nice(current.status)} · ${relative(current.updated_at)}`; } catch (issue) { /* the next refresh retries */ } }
    function councilForm() {
      if (!array(data.projects).length) { toast("Add a project first (Projects › Add project).", true); return; }
      const form = el("form"), project = select(array(data.projects).map(item => [item.id, item.name])), topic = textarea("e.g. How should we make this project ready for paying customers? Agree on the 3 most valuable changes and who builds each.");
      const choices = roleChoices().filter(([id]) => id !== "auto"), first = select(choices, "codex"), second = select(choices, "claude"), rounds = select([["0", "Until they agree (no limit)"], ["1", "1 round (quick)"], ["2", "2 rounds"], ["3", "3 rounds"], ["5", "5 rounds"], ["10", "10 rounds"], ["custom", "Another number…"]], "0");
      const custom = input("Number of rounds"); custom.type = "number"; custom.min = "1"; const customField = field("Rounds", custom); customField.classList.add("hidden");
      rounds.addEventListener("change", () => customField.classList.toggle("hidden", rounds.value !== "custom"));
      const handoff = check("When they agree, send the plan to Support to create and start the tasks"); handoff.control.checked = true;
      handoff.wrap.title = "Support checks the plan against your projects and tasks, corrects conflicts, creates any new projects needed and proposes (or, if you let it act automatically, runs) the tasks.";
      append(form, field("Which project?", project), field("What should they decide?", topic, "Both models read this project's files, docs and Git history. They can't change anything during the meeting."),
        field("Speaks first", first), field("Replies", second), field("How long?", rounds, "Each round is one turn each, then a closing summary and a confirmation. With no limit they keep reviewing each other until both agree; you can stop them any time. Every turn uses your AI plan."), customField, handoff.wrap);
      const submit = submitButton("Start meeting"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
      wireForm(form, submit, async () => {
        const count = rounds.value === "custom" ? Number(custom.value) : Number(rounds.value);
        if (!Number.isInteger(count) || count < 0) throw new Error("Type a whole number of rounds, 1 or more.");
        const meeting = await mutate("/api/council", {project_id: project.value, topic: topic.value, rounds: count, first: first.value, second: second.value, send_to_support: handoff.control.checked});
        closeDialog(); councilId = meeting.id; councilShown = ""; toast("Meeting started. The first model is reading the project."); loadList();
      });
      showDialog("New council meeting", form);
    }
    loadList();
    return root;
  }

  function chatView() {
    const root = el("div", "chat"), side = el("div", "chat-list"), head = el("div", "chat-list-head"), items = el("div", "chat-items"), main = el("div", "chat-main");
    const profile = select(roleChoices().filter(([id]) => id !== "auto"), chatDefault()), project = select([["", "All projects"], ...array(data.projects).map(item => [item.id, item.name])]);
    append(head, field("Talk to", profile), field("About", project), button("+ New chat", () => newChat(project.value, profile.value), "button primary"));
    append(side, head, items); append(root, side, main);
    const token = renderToken;
    async function loadList() { try { cache.chats = await api("/api/chats"); } catch (issue) { toast(issue.message, true); cache.chats = []; } if (token !== renderToken) return; items.replaceChildren(); if (!cache.chats.length) items.append(el("p", "hint", "No chats yet. Pick who to talk to, then press New chat.")); cache.chats.forEach(item => { const entry = button("", () => { chatId = item.id; paintList(); openChat(); }, `chat-item${item.id === chatId ? " active" : ""}`); append(entry, el("strong", "", item.title), el("small", "", `${profileLabel(item.profile)} · ${relative(item.updated_at)}`)); entry.dataset.id = item.id; items.append(entry); }); if (!chatId && cache.chats.length) chatId = cache.chats[0].id; paintList(); openChat(); }
    function paintList() { items.querySelectorAll(".chat-item").forEach(node => node.classList.toggle("active", node.dataset.id === chatId)); }
    async function openChat(keepScroll = false) {
      clearTimeout(chatPoll);
      if (!chatId) { main.replaceChildren(body(empty("Cerebra Support", "Ask where any project or task stands and why, paste a client's request to have it understood and planned, or ask Cerebra to build something. Support sees all your projects and tasks.", button("+ Start a conversation", () => newChat(project.value, profile.value), "button primary"), ">_"))); return; }
      let state; try { state = await api(`/api/chats/${encodeURIComponent(chatId)}`); } catch (issue) { main.replaceChildren(body(empty("Chat unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const conversation = state.conversation, header = el("div", "chat-head"), messages = el("div", "messages"), composer = el("form", "composer"), box = textarea("Message " + profileLabel(conversation.profile) + "…  (Enter to send, Shift+Enter for a new line)"), send = submitButton("Send");
      const place = readingPlace(main.querySelector(".messages")), draft = main.querySelector("textarea")?.value || "";
      const auto = check("Let support act for me"); auto.control.checked = state.settings?.act_automatically === true; auto.wrap.title = "When ticked, projects and tasks that support proposes are created and started right away. Approval steps still ask you unless Away mode is on.";
      auto.control.addEventListener("change", async () => { if (!await act(auto.control.checked ? "Support will act on its own." : "Support will ask before acting.", () => mutate("/api/support", {act_automatically: auto.control.checked}, "PUT"))) auto.control.checked = !auto.control.checked; });
      const approvals = check("May answer approvals"); approvals.control.checked = state.settings?.allow_approvals === true;
      approvals.wrap.title = "Lets the Assistant approve or reject plans, runs, review findings and merges for you. Full access, accounts, keys, paid and publishing actions always stay with you.";
      approvals.control.addEventListener("change", async () => {
        if (approvals.control.checked) { approvals.control.checked = false; showDialog("Let the Assistant answer approvals?", append(el("div"),
          el("p", "", "The Assistant will be able to approve plans, agent runs, review findings and merges into your projects, the same steps you approve now. It acts from what it reads in your projects and logs, so a mistake or a hidden instruction in a file could approve the wrong thing."),
          el("p", "", "It still cannot turn on Full access, switch agents on or off, change accounts or keys, spend money or publish anything."),
          actionsRow(button("Cancel", closeDialog, "button ghost"), button("Allow", async () => { if (await act("The Assistant may now answer approvals.", () => mutate("/api/support", {allow_approvals: true}, "PUT"))) { approvals.control.checked = true; } closeDialog(); }, "button danger")))); return; }
        if (!await act("Only you answer approvals now.", () => mutate("/api/support", {allow_approvals: false}, "PUT"))) approvals.control.checked = true;
      });
      append(header, el("strong", "", conversation.title), badge(profileLabel(conversation.profile), "blue"), conversation.project_id ? badge(projectFor(conversation.project_id)?.name || "project", "purple") : badge("all projects", "muted"), badge("read-only", "green"), el("span", "", ""), auto.wrap, approvals.wrap, button("→ Make it a task", () => taskForm(conversation.project_id || "", [...state.messages].reverse().find(message => message.role === "user")?.content || ""), "button small primary"), button("Delete", async () => { if (await act("Chat deleted.", () => api(`/api/chats/${encodeURIComponent(chatId)}`, {method: "DELETE"}))) { chatId = ""; loadList(); } }, "button small ghost"));
      if (!agentsOn()) messages.append(hint("AI agents are switched off, so messages will fail. Turn them on in Settings › Agent permissions.", true));
      if (!state.messages.length) {
        const ideas = el("div", "prompt-chips"), named = projectFor(conversation.project_id)?.name || array(data.projects)[0]?.name || "my project";
        [`Where are we on ${named}, and why did anything fail?`, "What is waiting for my approval, and what should I do first?", "Build me a small web app for booking appointments. Plan it, create the project and tasks, and start them.", "Here is a client's request. Help me understand exactly what they want, list questions to ask them, draft my reply, and plan the work:\n\n"].forEach(text => ideas.append(button(text.split("\n")[0], () => { box.value = text; box.focus(); }, "chip")));
        messages.append(empty("How can I help?", "I can see every project and task in Cerebra. Ask anything, or pick a starting point:", ideas, ">_"));
      }
      state.messages.forEach(message => {
        if (message.role === "cerebra") {  // recorded action results fed back to Support (not something the owner typed)
          let recorded = message.content.replace(/^ACTION RESULTS[^\n]*\n/, "").split("\nContinue with")[0];
          try { recorded = JSON.parse(recorded); } catch (issue) { /* show the text as it is */ }
          messages.append(append(el("div", "action-results"), el("strong", "", "⚙ Cerebra ran the actions and recorded the results"),
            append(el("details"), el("summary", "", "Show the recorded results"), code(recorded)), el("small", "", relative(message.created_at))));
          return;
        }
        if (message.role === "auto") {  // Auto-fix: a failure or the Council's solution, sent by Cerebra itself
          messages.append(append(el("div", "action-results"), el("strong", "", message.content.startsWith("COUNCIL") ? "⚙ Cerebra sent the Council's solution" : "⚙ Auto-fix: Cerebra sent this failure to the Assistant"),
            append(el("details"), el("summary", "", "Show what was sent"), code(message.content)), el("small", "", relative(message.created_at))));
          return;
        }
        const row = el("div", `message ${message.role}`), bubble = el("div", `bubble${message.status === "failed" ? " failed" : ""}`), holder = el("div");
        if (message.role === "user") bubble.append(el("p", "", message.content));
        else if (message.status === "pending") bubble.append(append(el("div", "typing"), el("span"), el("span"), el("span")), el("small", "", `${nice(message.provider)} is thinking… this can take a minute.`));
        else if (message.status === "failed") bubble.append(failureText(message.error || "No answer."));
        else { bubble.append(markdown(message.content)); array(message.actions).forEach(action => bubble.append(actionCard(action))); }
        append(holder, bubble, el("div", "message-meta", `${message.role === "user" ? "you" : nice(message.provider) + (message.model ? ` · ${message.model}` : "")} · ${relative(message.created_at)}`));
        append(row, el("span", "avatar", message.role === "user" ? "you" : PROVIDER_ICON[message.provider] || "AI"), holder); messages.append(row);
      });
      box.value = draft; send.disabled = state.busy;
      box.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); composer.requestSubmit(); } });
      composer.addEventListener("submit", async event => { event.preventDefault(); const text = box.value.trim(); if (!text) return; send.disabled = true; if (await act(null, () => mutate(`/api/chats/${encodeURIComponent(chatId)}/messages`, {text}))) { box.value = ""; await openChat(); } else send.disabled = false; });
      append(composer, box, state.busy ? button("Stop", () => act("Stopping…", () => mutate(`/api/chats/${encodeURIComponent(chatId)}/stop`)), "button danger") : null, send);
      main.replaceChildren(header, messages, composer);
      if (!keepScroll) messages.scrollTop = messages.scrollHeight; else keepReading(place, messages);
      if (!keepScroll) box.focus();
      if (state.busy) chatPoll = setTimeout(() => { if (token === renderToken && page === "chat") openChat(true).then(() => { if (!state.busy) loadList(); }); }, 1500);
    }
    loadList();
    return root;
  }

  // ---------- system view ----------
  function systemView() {
    if (!content.querySelector(".system")) { window.AIHQSystem.mount(content, {api, overview: () => data, inspect: taskDetail, report: id => { location.hash = `report/${id}`; }}); }
    else window.AIHQSystem.update?.();
    paintTeamBar();
    return null;
  }

  // ---------- who does the work: switch planner, coder and reviewer between Codex and Claude models ----------
  const ROLES = [["planner", "Planner", "Plans the work"], ["implementer", "Coder", "Writes the code"], ["reviewer", "Reviewer", "Checks the code (another company than the coder)"]];
  let teamTaskId = "", teamFingerprint = "", teamOpen = null;
  const providerOf = choice => String(choice).startsWith("catalog:") ? String(choice).split(":")[1] : (profiles().find(item => item.id === choice)?.provider || choice);
  function outOfUsage(provider) {
    const until = agentRow(provider).usage_until;
    return until && new Date(until) > new Date() ? new Date(until).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"}) : "";
  }
  function paintTeamBar() {
    const live = realTasks().filter(task => !["COMPLETED", "CANCELLED"].includes(task.state));
    const pick = live.find(task => task.id === teamTaskId) || live.find(task => ACTIVE.includes(task.state))
      || live.find(task => task.results?.blocked_reason === "waiting_for_usage") || live[0];
    teamTaskId = pick?.id || "";
    let bar = content.querySelector(".team-bar");
    const fingerprint = JSON.stringify([teamTaskId, teamOpen, live.map(task => [task.id, task.state, task.results?.models, task.results?.blocked_reason]), data.roles, array(data.agents).map(agent => agent.usage_until)]);
    if (bar && (fingerprint === teamFingerprint || bar.contains(document.activeElement))) return;  // don't redraw under the owner's hand
    teamFingerprint = fingerprint;
    const fresh = teamBar(live, pick);
    if (bar) bar.replaceWith(fresh); else content.prepend(fresh);
  }
  function teamBar(live, task) {
    const node = el("section", "panel team-bar"), rows = el("div", "team-rows");
    const stuck = task && (task.state === "FAILED" || task.results?.blocked_reason === "waiting_for_usage");
    const open = teamOpen ?? Boolean(stuck);  // compact by default; opens by itself when a model change would help
    const summary = task ? ROLES.map(([key, label]) => `${label}: ${taskModels(task)[key]}`).join(" · ") : ROLES.map(([key, label]) => `${label}: ${profileLabel(data.roles?.[key] || "auto")}`).join(" · ");
    const toggle = button(open ? "Close ▴" : "Change ▾", () => { teamOpen = !open; teamFingerprint = ""; paintTeamBar(); }, "button small");
    const header = append(el("div", "panel-header"), el("h2", "", "Who does the work"), toggle);
    node.append(header, append(el("div", "team-summary"), el("span", "", summary), stuck ? badge(task.state === "FAILED" ? "failed" : "waiting for usage", "amber") : null));
    if (!open) return node;
    const target = select([...live.map(item => [item.id, `${item.description.slice(0, 70)} · ${nice(item.pause_requested ? "PAUSED" : item.state)}`]), ["", "New tasks only (the default team)"]], task?.id || "");
    target.addEventListener("change", () => { teamTaskId = target.value; teamFingerprint = ""; paintTeamBar(); });
    const remember = check("Also use for new tasks", !task);
    const models = task ? task.results?.models || {} : {};
    const choices = roleChoices().filter(([id]) => id !== "auto");
    append(node, append(el("div", "team-target"), field("Change the team of", target), task ? remember.wrap : null), rows);
    if (task?.state === "FAILED") node.append(hint("This task failed. Switch the job that stopped to another model, then press ↻ Try again in the task: it continues from where it stopped."));
    if (task?.results?.blocked_reason === "waiting_for_usage") node.append(hint("This task is waiting for AI usage. Switch the job to the other company's model and it continues straight away, from where it stopped.", true));
    for (const [key, label, help] of ROLES) {
      const current = task ? (models[key]?.provider || {implementer: task.assigned_agent, reviewer: task.reviewer}[key] || "claude") : providerOf(data.roles?.[key] || "auto");
      const shown = task ? taskModels(task)[key] : profileLabel(data.roles?.[key] || "auto");
      const other = current === "codex" ? "claude" : "codex", empty_ = outOfUsage(current);
      const chooser = select([["", "Choose a model…"], ...choices], "");
      const apply = async (choice, message, allowSame = false) => {
        if (task) {
          const coderCompany = models.implementer?.provider || task.assigned_agent, target = choice === "switch" ? other : providerOf(choice);
          if (key === "reviewer" && target === coderCompany && !allowSame) {
            showDialog(`Let ${nice(target)} review ${nice(target)}'s own work?`, append(el("div"),
              el("p", "", `The coder is a ${nice(target)} model. Normally the reviewer comes from the other company, so mistakes one model makes are caught by a different one.`),
              el("p", "", outOfUsage(target === "codex" ? "claude" : "codex") ? `${nice(target === "codex" ? "claude" : "codex")} is out of usage right now, so this keeps the task moving. The review is less independent, and Cerebra records that you chose it.` : "The review will be less independent. Cerebra records that you chose it."),
              actionsRow(button("Cancel", closeDialog, "button ghost"), button(`Yes, ${nice(target)} reviews`, () => { closeDialog(); apply(choice, message, true); }, "button primary"))));
            return;
          }
          const updated = await act(message, () => mutate(`/api/tasks/${encodeURIComponent(task.id)}/team`, {role: key, choice, allow_same_company: allowSame}));
          if (!updated) return;
          if (remember.control.checked) { const chosen = updated.results?.models?.[key]; if (chosen) await act(null, () => mutate("/api/models/roles", {[key]: `catalog:${chosen.provider}:${chosen.model}`}, "PUT")); }
        } else if (!await act(message, () => mutate("/api/models/roles", {[key]: choice === "switch" ? `catalog:${other}:${array(data.catalog?.[other]).find(item => item.tier === "balanced")?.model || ""}` : choice}, "PUT"))) return;
        teamFingerprint = ""; await refresh(true);
      };
      chooser.addEventListener("change", () => { if (chooser.value) apply(chooser.value, `${label}: ${profileLabel(chooser.value)}.`); });
      rows.append(append(el("div", `team-row${empty_ ? " out" : ""}`),
        append(el("div", "team-role"), el("strong", "", label), el("small", "", help)),
        append(el("div", "team-now"), el("span", `team-model ${current}`, shown), empty_ ? badge(`out of usage until ${empty_}`, "amber") : null),
        append(el("div", "team-actions"), button(`↔ Switch to ${nice(other)}`, () => apply("switch", `${label} switched to ${nice(other)}.`), empty_ ? "button small primary" : "button small"), chooser)));
    }
    return node;
  }

  // ---------- reports ----------
  function reportsView() {
    const tasks = realTasks();
    if (!tasks.length) return panel("Reports", body(empty("No reports yet", "Every task gets an easy-to-read report: what you asked, who did what, whether the tests passed, and where everything is saved.", null, "¶")));
    const list = el("div", "row-list");
    tasks.forEach(task => { const row = el("div", "row"), info = el("div", "row-main"); row.addEventListener("click", () => { location.hash = `report/${task.id}`; }); append(info, el("strong", "", task.description), el("div", "row-meta", `${projectFor(task.project_id)?.name || ""} · ${relative(task.updated_at)}`)); append(row, info, badge(task.state), el("span", "chev", "›")); list.append(row); });
    return append(el("div"), hint("Each report explains a task in short, simple sentences, so anyone can follow what the AI team did."), panel("All reports", list, null, tasks.length));
  }
  // Before/after test evidence: what failed on the untouched code and what passes after the change.
  function proofSection(proof) {
    if (!proof || !proof.available) return proof ? append(el("div", "proof muted"), el("h2", "", "Before and after"), el("p", "", proof.text)) : null;
    const tone = {fixed: "good", still_passing: "neutral", still_failing: "bad", broke: "bad", not_yet: "neutral"}[proof.verdict] || "neutral";
    const column = (title, run) => {
      const box = append(el("div", "proof-col"), el("strong", "", title));
      if (!run) { box.append(el("p", "row-meta", "Not tested yet.")); return box; }
      run.commands.forEach(item => box.append(append(el("div", `proof-run ${item.passed ? "pass" : "fail"}`), el("span", "", item.passed ? "✓ passed" : item.timed_out ? "⏱ timed out" : "✗ failed"), el("code", "", array(item.command).join(" ")))));
      if (run.failing.length) box.append(el("p", "row-meta", `Failing: ${run.failing.slice(0, 8).join(", ")}${run.failing.length > 8 ? ` and ${run.failing.length - 8} more` : ""}`));
      return box;
    };
    return append(el("section", `proof ${tone}`), el("h2", "", "Before and after"), el("p", "proof-verdict", proof.text),
      append(el("div", "proof-grid"), column("Before the change", proof.before), column("After the change", proof.after)),
      proof.newly_failing.length ? el("p", "row-meta", `Newly failing: ${proof.newly_failing.join(", ")}`) : null);
  }
  function reportView() {
    const holder = el("div", "report"), token = renderToken; holder.append(el("div", "loading", "loading report…"));
    async function load() {
      let report; try { report = await api(`/api/reports/${encodeURIComponent(param)}`); } catch (issue) { holder.replaceChildren(empty("Report not found", issue.message)); return; }
      if (token !== renderToken) return;
      $("#page-subtitle").textContent = report.project ? `Project: ${report.project}` : "";
      const hero = append(el("div", "report-hero"), el("div", "big", report.emoji), el("h1", "", report.headline), el("p", "", report.meaning));
      const helpers = el("ul", "helpers"); report.helpers.forEach(item => helpers.append(el("li", "", item)));
      const story = el("ol", "story"); report.steps.forEach(step => { const item = el("li", step.good === true ? "good" : step.good === false ? "bad" : ""), text = el("div"); append(text, el("strong", "", step.title), el("p", "", step.text), step.when ? el("time", "", date(step.when)) : null); append(item, el("span", "icon", step.icon), text); story.append(item); });
      const saved = el("div", "saved"); report.saved.forEach(item => saved.append(append(el("div"), el("strong", "", item.what), el("p", "", item.explain), el("code", "", item.where))));
      append(holder.replaceChildren() || holder, hero, el("h2", "", "What you asked for"), el("div", "asked", report.asked), proofSection(report.evidence), el("h2", "", "Who helped"), helpers, el("h2", "", "What happened, step by step"), story,
        report.changed_files.length ? [el("h2", "", "Files that changed"), list(report.changed_files)] : null,
        el("h2", "", "Where everything is saved"), saved, el("h2", "", "What happens next"), el("div", "next", report.next));
      if (!["COMPLETED", "FAILED", "CANCELLED"].includes(report.state)) pageTimer = setTimeout(() => { if (token === renderToken) load(); }, 4000);
    }
    load(); return holder;
  }

  // ---------- activity ----------
  function activityView() { const events = array(data.events); return panel("Supervisor event log", activityList(events, 200), null, events.length); }

  // ---------- models & sign-in ----------
  function modelsView() {
    const root = el("div"), providersHolder = el("div", "grid cards"), token = renderToken;
    root.append(panel("Your AI accounts", body(hint("Sign in uses each tool's own login window. Cerebra never sees your passwords or keys; your plan (ChatGPT, Claude, Copilot…) pays for usage."), el("div", "", ""), providersHolder)));
    function paintProviders() {
      providersHolder.replaceChildren();
      array(cache.providers).forEach(provider => {
        const status = provider.status || {}, signIn = provider.sign_in, card = el("article", "card"), top = el("div", "card-top"), info = el("div");
        append(info, el("h3", "", provider.label), el("div", "row-meta", `${provider.vendor} · ${status.version || (status.installed ? "installed" : "not installed")}`)); append(top, el("span", `icon-tile ${provider.id}`, PROVIDER_ICON[provider.id] || "AI"), info);
        const state = !status.installed && !signIn?.installed ? badge("not installed", "muted") : signIn?.signed_in === true ? badge("signed in", "green") : signIn?.signed_in === false ? badge("signed out", "red") : badge("sign-in not checked", "amber");
        append(card, top, append(el("div", "row-meta"), state, provider.execution ? badge("runs tasks + chat", "blue") : badge("sign-in only for now", "muted")));
        if (signIn?.account || signIn?.method) card.append(kv([["Account", signIn.account || "—"], ["Method", signIn.method || "—"], ["Plan", signIn.plan || "—"], ["Checked", relative(signIn.checked_at)]]));
        card.append(el("p", "", provider.model_hint));
        const foot = el("div", "card-footer");
        const check = provider.execution ? button("Check sign-in", async () => { const result = await act(r => r.detail, () => mutate(`/api/providers/${provider.id}/check`, {}, "POST", 60000)); if (result) { provider.sign_in = result; paintProviders(); } }, "button small") : null;
        const signOut = button("Sign out", async event => { event.currentTarget.disabled = true; const result = await act(r => r.signed_in ? `Still signed in: ${r.detail}` : `Signed out of ${provider.label}.`, () => mutate(`/api/providers/${provider.id}/sign-out`, {}, "POST", 60000)); if (result) { provider.sign_in = result; await refresh(true); } paintProviders(); }, "button small danger");
        if (signIn?.signed_in === true && provider.can_sign_out) append(foot, signOut, check);
        else if (status.installed || signIn?.installed !== false) append(foot, button("Sign in", () => act(result => result.message, () => mutate(`/api/providers/${provider.id}/sign-in`)), "button small primary"), check);
        foot.append(link("Install →", "toolchain"));
        card.append(foot); providersHolder.append(card);
      });
    }
    (async () => { try { cache.providers = await api("/api/providers"); } catch (issue) { toast(issue.message, true); } if (token === renderToken) paintProviders(); })();
    if (cache.providers) paintProviders();

    const how = el("form"), policy = data.routing || {}, mode = select([["rules", "Supervisor rules (instant, free)"], ["model", "Ask a supervisor model (uses your plan)"]], policy.mode || "rules");
    const brain = select(catalogModels().filter(item => item.model).map(item => [`${item.provider}:${item.model}`, item.label]), `${policy.provider || "claude"}:${policy.model || "opus"}`), brainField = field("Supervisor model", brain, "Reads the task and the model list, then picks planner, coder and reviewer. Its answer is checked: only listed models, and the reviewer must be from the other company.");
    const syncMode = () => brainField.classList.toggle("hidden", mode.value !== "model"); mode.addEventListener("change", syncMode); syncMode();
    append(how, hint("When a role is set to Auto, the supervisor rates how hard the task is and picks a model: frontier models for hard work, balanced for everyday work, fast ones for small jobs. Claude plans and reviews; Codex codes (Claude writes docs). The reviewer always comes from the other company."), field("How the supervisor decides", mode), brainField);
    const saveHow = submitButton("Save"); how.append(actionsRow(saveHow));
    wireForm(how, saveHow, async () => { const [provider, model] = brain.value.split(":"); await mutate("/api/routing", {mode: mode.value, provider, model}, "PUT"); await refresh(true); toast(mode.value === "model" ? "The supervisor model will now pick the AI team." : "The supervisor's rules will pick the AI team."); });
    root.append(panel("Supervisor: who picks the models", body(how)));

    const roles = el("form"), planner = profileSelect("planner"), implementer = profileSelect("implementer"), reviewer = profileSelect("reviewer");
    append(roles, el("div", "form-grid"), hint("New tasks start with these. You can still change them per task. The reviewer must use a different provider from the coder, so the review is truly independent."));
    append(roles.firstChild, field("Planner", planner), field("Coder", implementer), field("Reviewer", reviewer));
    const saveRoles = submitButton("Save defaults"); roles.append(actionsRow(saveRoles));
    wireForm(roles, saveRoles, async () => { await mutate("/api/models/roles", {planner: planner.value, implementer: implementer.value, reviewer: reviewer.value}, "PUT"); await refresh(true); toast("Default AI team saved."); });
    root.append(panel("Default AI team", body(roles)));

    const catalogHolder = el("div", "grid cards");
    ["claude", "codex"].forEach(provider => {
      const card = el("article", "card"), top = el("div", "card-top"), info = el("div");
      append(info, el("h3", "", provider === "claude" ? "Claude (Anthropic)" : "ChatGPT / Codex (OpenAI)"), el("div", "row-meta", provider === "codex" ? "List read from your Codex app, so new models appear by themselves" : "Aliases always use the newest model of that family"));
      append(top, el("span", `icon-tile ${provider}`, PROVIDER_ICON[provider] || "AI"), info); card.append(top);
      array(data.catalog?.[provider]).forEach(item => append(card, append(el("div", "model-row"), append(el("div"), el("strong", "", item.label), el("div", "row-meta", item.strengths)), append(el("div", "row-meta"), item.tier ? badge(item.tier, item.tier === "frontier" ? "purple" : item.tier === "fast" ? "green" : "blue") : badge("manual only", "muted"), el("code", "", item.model || "(default)")))));
      catalogHolder.append(card);
    });
    root.append(panel("Available models", body(hint("Pick any of these for a role above or per task, or leave the role on Auto."), catalogHolder)));

    const rows = profiles().map(profile => [append(el("div"), el("strong", "", profile.label), el("div", "row-meta", profile.id)), append(el("span"), el("span", `icon-tile ${profile.provider}`, PROVIDER_ICON[profile.provider] || "AI")), el("code", "", profile.model || "(CLI default)"), profile.can_run_tasks ? badge("ready", "green") : badge("not runnable yet", "muted"),
      append(el("div", "card-footer"), button("Edit", () => profileForm(profile), "button small"), profile.built_in ? null : button("Remove", () => act("Model removed.", async () => { await api(`/api/models/${profile.id}`, {method: "DELETE"}); await refresh(true); }), "button small danger"))]);
    root.append(panel("Models", table(["Name", "Provider", "Model", "Status", ""], rows), button("+ Add model", () => profileForm(), "button small primary"), profiles().length));
    root.append(panel("Free models and your accounts", body(hubPanel())));
    return root;
  }
  function hubPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/models/hub").then(state => {
      const key = input(state.connected ? "Saved: paste a new key to replace it" : "sk-or-v1-…", "", "password"), saveKey = button("Save key", () => act("Saved.", () => mutate("/api/models/hub", {api_key: key.value.trim()}, "PUT")).then(() => render()), "button small");
      const choices = [...Object.entries(state.accounts || {}).map(([id, label]) => [id, label]), ...array(state.local_models).map(name => [`local:${name}`, `${name} (on this computer, free)`]), ...array(state.free_models).map(item => [item.id, /free/i.test(item.name) ? item.name : `${item.name} (free)`])];
      const routes = array(state.categories).map(category => {
        const pick = select(choices.length ? choices : [[state.routes[category.key], state.routes[category.key]]], state.routes[category.key]);
        if (!Array.from(pick.options).some(option => option.value === state.routes[category.key])) { pick.append(option(state.routes[category.key], `${state.routes[category.key]} (no longer free: choose another)`)); pick.value = state.routes[category.key]; }
        pick.addEventListener("change", () => act("Saved.", () => mutate("/api/models/hub", {routes: {[category.key]: pick.value}}, "PUT")));
        const test = button("Test", () => act(result => `Answered: ${result.answer}`, () => mutate("/api/models/hub/test", {category: category.key}, "POST", 120000)), "button small ghost");
        return [append(el("div"), el("strong", "", category.label), el("div", "row-meta", category.about)), pick, String(state.routes[category.key]).startsWith("account:") ? "" : test];
      });
      const usage = array(state.usage);
      root.replaceChildren(
        hint("Only what costs you nothing extra: your Claude and Codex accounts (already paid), and free models through OpenRouter. Paid models are refused, so there is no surprise bill."),
        append(el("div", "form-grid"), field("Free OpenRouter key", key, "Make a free account at openrouter.ai › Keys. No card needed for free models."), actionsRow(saveKey)),
        state.catalog_reachable ? null : hint("Couldn't reach OpenRouter to list today's free models; check your internet connection.", true),
        table(["Kind of work", "Uses", ""], routes.map(([label, pick, test]) => [label, pick, test || ""])),
        hint("Free models allow about 20 requests a minute and 50 a day on an account that never bought credits, and they come and go: each request names free backups. Writing in your name and planning stay on your Claude account by default, for quality."),
        array(state.local_models).length ? hint(`On this computer (free, no daily limit): ${state.local_models.join(", ")}.`)
          : hint("Models on your own computer are free with no daily limit (DeepSeek, Qwen, Llama, Gemma…). Open Ollama, then pull one in a terminal, for example: ollama pull deepseek-r1:8b . It appears here when ready. A 7-8B model needs about 8 GB of memory."),
        usage.length ? append(el("div"), el("h4", "", "This month"), table(["Kind of work", "Model", "Calls", "Cost"], usage.map(item => [item.category, item.model, String(item.calls), `USD ${item.cost.toFixed(2)}`]))) : null);
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }

  function profileForm(profile = null) {
    const form = el("form"), provider = select([["codex", "OpenAI Codex"], ["claude", "Claude Code"], ["copilot", "GitHub Copilot CLI"], ["gemini", "Gemini CLI"]], profile?.provider || "claude"), model = input("e.g. opus, sonnet, gpt-5-codex …", profile?.model || ""), label = input("A name you will recognise", profile?.label || ""), suggestions = el("div", "row-meta");
    provider.disabled = !!profile;
    function suggest() { const known = array(cache.providers).find(item => item.id === provider.value); suggestions.replaceChildren(...array(known?.models).map(name => button(name, () => { model.value = name; }, "button small ghost"))); if (known?.model_hint) suggestions.append(el("small", "", known.model_hint)); }
    provider.addEventListener("change", suggest); suggest();
    append(form, field("Provider", provider), field("Model", model, "Leave blank to use the tool's default model."), suggestions, field("Display name", label));
    const submit = submitButton(profile ? "Save" : "Add model"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => { if (profile) await mutate(`/api/models/${profile.id}`, {model: model.value.trim(), label: label.value.trim()}, "PATCH"); else await mutate("/api/models", {provider: provider.value, model: model.value.trim(), label: label.value.trim()}); closeDialog(); await refresh(true); toast("Model saved."); });
    showDialog(profile ? `Edit ${profile.label}` : "Add a model", form);
  }

  // ---------- GitHub ----------
  function githubView() {
    const root = el("div"), account = el("div"), repos = el("div"), token = renderToken;
    root.append(panel("Account", account), panel("Your repositories", repos, button("↻", () => { cache.repos = null; loadRepos(); }, "button small ghost")));
    async function loadAccount() {
      account.replaceChildren(el("div", "loading", "checking GitHub…"));
      try { cache.github = await api("/api/github", {timeout: 60000}); } catch (issue) { account.replaceChildren(body(hint(issue.message, true))); return; }
      if (token !== renderToken) return; const status = cache.github;
      if (!status.installed) { account.replaceChildren(body(empty("GitHub CLI is not installed", "Cerebra talks to GitHub through the official GitHub CLI.", link("Install it from Toolchain →", "toolchain", "button primary"), "⑂"))); return; }
      if (!status.signed_in) { account.replaceChildren(body(empty("Not connected", "Sign in once; GitHub's own window handles your password and two-factor code.", button("Connect GitHub", () => act(result => result.message, () => mutate("/api/github/sign-in")), "button primary"), "⑂"), append(el("div", "actions"), button("Check again", loadAccount, "button small")))); return; }
      account.replaceChildren(body(kv([["Signed in as", status.account], ["Name", status.name], ["Profile", status.url], ["Public repositories", status.public_repos]]), append(el("div", "actions"), button("Check again", loadAccount, "button small ghost"), button("Sign out", async () => { if (await act("Signed out of GitHub.", () => mutate("/api/github/sign-out", {}, "POST", 60000))) { cache.repos = null; loadAccount(); loadRepos(); } }, "button small danger"), button("+ Clone a repository", () => projectForm("github"), "button small primary"))));
      loadRepos();
    }
    async function loadRepos() {
      if (!cache.github?.signed_in) { repos.replaceChildren(body(el("p", "", "Connect GitHub to see your repositories."))); return; }
      repos.replaceChildren(el("div", "loading", "loading repositories…"));
      try { cache.repos = cache.repos || await api("/api/github/repositories", {timeout: 60000}); } catch (issue) { repos.replaceChildren(body(hint(issue.message, true))); return; }
      if (token !== renderToken) return;
      repos.replaceChildren(table(["Repository", "Language", "Visibility", "Updated", ""], cache.repos.map(repo => [append(el("div"), el("strong", "", repo.name), el("div", "row-meta", repo.description || "")), repo.language || "—", badge(repo.visibility || "?", repo.visibility === "PUBLIC" ? "amber" : "muted"), relative(repo.updated_at), button("Clone as project", () => projectForm("github"), "button small")])));
    }
    loadAccount(); return root;
  }

  // ---------- toolchain ----------
  function toolchainView() {
    const root = el("div"), holder = el("div"), token = renderToken;
    root.append(hint("Install opens a visible window running the official installer (winget or npm), so you can watch it. Nothing is installed without your click. When it finishes, press Re-check: Cerebra finds new tools without a restart."), el("div", "", ""), holder);
    async function load(refresh = false) {
      holder.replaceChildren(el("div", "loading", "checking tools on this computer…"));
      try { cache.tools = await api(`/api/tools${refresh ? "?refresh=true" : ""}`, {timeout: 120000}); } catch (issue) { holder.replaceChildren(hint(issue.message, true)); return; }
      if (token !== renderToken) return;
      holder.replaceChildren();
      const groups = [...new Set(cache.tools.map(tool => tool.group))];
      groups.forEach(group => { const tools = cache.tools.filter(tool => tool.group === group); holder.append(panel(group, table(["Tool", "Status", "Why you need it", ""], tools.map(tool => [append(el("div"), el("strong", "", tool.label), el("div", "row-meta", tool.version || tool.problem || tool.install_command)), tool.installed ? badge("installed", "green") : tool.problem ? badge("needs repair", "red") : badge("missing", "amber"), tool.why, tool.installed ? el("span", "row-meta", "✓") : button("Install", () => act(result => result.message, () => mutate(`/api/tools/${tool.id}/install`)), "button small primary")])), group === groups[0] ? button("↻ Re-check", () => load(true), "button small ghost") : null, `${tools.filter(tool => tool.installed).length}/${tools.length}`)); });
    }
    load(); return root;
  }

  // ---------- marketing: posts to the owner's X, Facebook Page and Instagram ----------
  const POST_STYLE = {draft: "muted", approved: "blue", posted: "green", partial: "amber", failed: "red"};
  function marketingView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading your posts…")));
    (async () => {
      let state; try { state = await api("/api/social"); } catch (issue) { root.replaceChildren(body(empty("Marketing unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const posts = array(state.posts), count = status => posts.filter(post => post.status === status).length, limits = state.settings;
      const stats = el("div", "grid stats");
      [["To approve", count("draft"), "drafts waiting for your yes", "amber"], ["Scheduled", count("approved"), "go out by themselves", "cyan"],
       ["Posted", count("posted") + count("partial"), "on your channels", "green"], ["X this month", `USD ${Number(state.spent_this_month || 0).toFixed(2)}`, `of your USD ${Number(limits.monthly_cap).toFixed(2)} budget`, ""]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const writer = state.writer || {};
      const tools = append(el("div", "actions"), button("+ New post", () => postDialog({channels: ["x", "facebook"], status: "draft"}, state), "button primary"),
        state.agents_on ? button(writer.state === "writing" ? "Writing posts…" : "✍ Write posts for me", () => act("Your AI model is writing 5 posts from your real work (about a minute). They arrive as drafts to approve.", () => mutate("/api/social/write", {count: 5, channels: ["x", "facebook"]})).then(() => setTimeout(() => render(), 1500)), "button") : null);
      const list = el("div", "row-list");
      posts.forEach(post => list.append(postRow(post, state)));
      const left = append(el("div"), panel("Your posts", append(el("div"), body(tools, writer.state === "failed" ? hint(`Couldn't write posts: ${writer.error}`, true) : writer.state === "done" ? hint(`${writer.count} new draft(s) written. Read and approve them.`) : null,
        state.agents_on ? null : hint("Switch AI agents on in Settings to have posts written for you.")),
        posts.length ? list : body(empty("No posts yet", "Share finished work, tips and your services so clients find you. Write one, or have your AI model draft a batch from your real work; nothing goes out until you approve it.", null, "✎"))), null, posts.length));
      const side = append(el("div"), panel("Your accounts", body(socialAccounts(state))), panel("Budget and limits", body(socialLimits(state))),
        panel("How it works", body(hint("Drafts never post. When you approve a post, it goes out by itself at the time you choose, through each platform's official API with your own app. X charges per post, so Cerebra records each post's cost and stops at your monthly budget. A post that failed is never retried by itself, because it may have gone out; press Retry."))));
      root.replaceChildren(stats, append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  function postRow(post, state) {
    const row = el("div", "row lead-row"), info = el("div", "row-main");
    row.tabIndex = 0; row.setAttribute("role", "button");
    const where = array(post.channels).map(channel => state.channels[channel] || channel).join(", ");
    const when = post.status === "approved" ? `goes out ${date(post.scheduled_at)}` : post.status === "posted" ? "posted" : post.origin === "ai" ? "written by your AI model" : "";
    append(info, el("strong", "", post.text.length > 140 ? post.text.slice(0, 140) + "…" : post.text), el("div", "row-meta", [where, when].filter(Boolean).join(" · ")));
    const notes = Object.entries(post.results || {}).map(([channel, result]) => result.error ? `${state.channels[channel]}: ${result.error}` : result.waiting ? `${state.channels[channel]}: ${result.waiting}` : "").filter(Boolean);
    if (notes.length) info.append(el("div", "row-reason", notes.join(" · ")));
    append(row, info, badge(post.status, POST_STYLE[post.status]));
    row.addEventListener("click", () => postDialog(post, state)); row.addEventListener("keydown", event => { if (event.key === "Enter") postDialog(post, state); });
    return row;
  }
  function postDialog(post, state) {
    const root = el("div"), editable = !["posted", "partial"].includes(post.status);
    const text = textarea("What do you want to share? A project you finished, a tip, a service you offer…", post.text || ""), link = input("https://… (optional)", post.link || ""), image = input("https://… public image link (needed for Instagram)", post.image_url || "");
    text.rows = 6; [text, link, image].forEach(control => { control.disabled = !editable; });
    const counter = el("small", "row-meta");
    const recount = () => { const full = `${text.value} ${link.value}`.trim().replace(/https?:\/\/\S+/g, "x".repeat(23)); counter.textContent = `${full.length} / 280 on X (each link counts as 23)`; counter.style.color = full.length > 280 ? "var(--red)" : ""; };
    text.addEventListener("input", recount); link.addEventListener("input", recount); recount();
    const boxes = Object.entries(state.channels).map(([key, label]) => { const item = check(`${label}${state.accounts[key]?.connected ? "" : " (not connected)"}`, array(post.channels).includes(key)); item.key = key; item.control.disabled = !editable; return item; });
    append(root, field("Post", append(el("div"), text, counter)), field("Link", link), field("Picture", image, "Instagram needs one; it must be a public https:// address (for example from your site)."), append(el("div", "check-list"), ...boxes.map(item => item.wrap)));
    Object.entries(post.results || {}).forEach(([channel, result]) => root.append(hint(`${state.channels[channel]}: ${result.posted_at ? `posted ${relative(result.posted_at)}${result.cost ? ` · USD ${result.cost}` : ""}${result.url ? ` · ${result.url}` : ""}` : result.error || result.waiting}`, !!result.error)));
    const payload = () => ({text: text.value, link: link.value.trim(), image_url: image.value.trim(), channels: boxes.filter(item => item.control.checked).map(item => item.key)});
    const save = async () => post.id ? mutate(`/api/social/posts/${post.id}`, payload(), "PATCH") : mutate("/api/social/posts", payload());
    const after = message => result => { if (result) { toast(message); closeDialog(); render(); } };
    const actions = el("div", "actions");
    if (editable) {
      const when = input("", "", "datetime-local");
      actions.append(button(post.id ? "Save" : "Save draft", () => act("", save).then(after("Saved.")), "button"),
        append(el("span", "inline-field"), el("span", "", "Post at"), when),
        button("Approve", async () => { const saved = await act("", save); if (!saved) return; act("", () => mutate(`/api/social/posts/${saved.id}/approve`, {when: when.value ? new Date(when.value).toISOString() : ""})).then(after(when.value ? "Approved: it goes out by itself at that time." : "Approved: it goes out within a minute.")); }, "button primary"),
        button("Post now", async () => { const saved = await act("", save); if (!saved) return; act("", () => mutate(`/api/social/posts/${saved.id}/post-now`, {}, "POST", 120000)).then(after("Posting done; check the results on the post.")); }, "button"));
    }
    if (post.status === "approved") actions.append(button("Back to draft", () => act("", () => mutate(`/api/social/posts/${post.id}/unapprove`)).then(after("It won't go out until you approve it again.")), "button ghost"));
    if (["failed", "partial"].includes(post.status)) actions.append(button("Retry the failed channels", () => act("", () => mutate(`/api/social/posts/${post.id}/retry`, {}, "POST", 120000)).then(after("Retried.")), "button primary"));
    if (post.id && editable) actions.append(button("Delete", () => act("", () => api(`/api/social/posts/${post.id}`, {method: "DELETE"})).then(after("Deleted.")), "button ghost"));
    root.append(actions);
    showDialog(post.id ? "Post" : "New post", root);
  }
  function socialAccounts(state) {
    const root = el("div"), accounts = state.accounts || {};
    const forms = {
      x: ["X", [["consumer_key", "API key"], ["consumer_secret", "API key secret"], ["access_token", "Access token"], ["access_secret", "Access token secret"]], "In the X Developer Portal: create an app with Read and write permission, then copy its API key and secret and generate an access token and secret for your own account."],
      facebook: ["Facebook Page", [["page_id", "Page ID"], ["page_token", "Page access token"]], "From your Meta app (developers.facebook.com): a Page access token with pages_manage_posts, and your Page's ID."],
      instagram: ["Instagram", [["ig_user_id", "Instagram professional account ID"]], "Your Instagram business or creator account linked to the Page above. It posts with the Page's token."]};
    Object.entries(forms).forEach(([channel, [label, fields, help]]) => {
      const item = accounts[channel] || {}, box = el("div", "action-card");
      append(box, append(el("div", "row-meta"), badge(item.connected ? "connected" : "not connected", item.connected ? "green" : "muted"), el("strong", "", label)));
      if (item.connected) {
        append(box, el("p", "", item.username ? `@${item.username}` : item.page || ""), append(el("div", "actions"),
          button("Check", () => act(result => result.message, () => mutate(`/api/social/accounts/${channel}/check`)).then(() => render()), "button small"),
          button("Disconnect", () => act(result => result.message, () => api(`/api/social/accounts/${channel}`, {method: "DELETE"})).then(() => render()), "button small ghost")));
      } else {
        const form = el("form"), inputs = fields.map(([key, name]) => { const control = input(name, "", key.includes("id") ? "text" : "password"); control.autocomplete = "off"; control.key = key; return control; }), save = submitButton("Connect");
        append(form, hint(help), ...inputs.map(control => field(control.placeholder, control)), actionsRow(save));
        wireForm(form, save, async () => { const result = await mutate(`/api/social/accounts/${channel}`, Object.fromEntries(inputs.map(control => [control.key, control.value.trim()])), "PUT"); toast(result.message); render(); });
        box.append(form);
      }
      root.append(box);
    });
    root.append(hint("Keys and tokens are stored encrypted by this computer's own secret store and never shown again."));
    return root;
  }
  function socialLimits(state) {
    const limits = state.settings, form = el("form"), save = submitButton("Save");
    const cap = input("10", limits.monthly_cap, "number"), per = input("0.015", limits.x_cost_per_post, "number"), withLink = input("0.20", limits.x_cost_with_link, "number"), day = input("3", limits.per_day, "number");
    [cap, per, withLink].forEach(control => { control.step = "any"; control.min = 0; }); day.min = 1;
    append(form, field("Monthly X budget (USD)", cap, "Nothing posts on X once this month's posts reach it."), append(el("div", "form-grid"), field("X cost per post", per), field("X cost with a link", withLink)),
      field("Posts per day on each channel", day, "So you share, not flood. Extra approved posts wait for the next day."), hint("Check X's current prices in your developer dashboard and set them here; Cerebra uses these to keep you within budget."), actionsRow(save));
    wireForm(form, save, async () => { await mutate("/api/social/settings", {monthly_cap: Number(cap.value || 0), x_cost_per_post: Number(per.value || 0), x_cost_with_link: Number(withLink.value || 0), per_day: Number(day.value || 1)}, "PUT"); toast("Saved."); render(); });
    return form;
  }
  // ---------- chief of staff: goals, the workers on their schedules, every run on the record ----------
  const RUN_STYLE = {ok: "green", skipped: "muted", failed: "red", busy: "amber"};
  function everyText(minutes) { return minutes % 1440 === 0 ? `every ${minutes / 1440} day(s)` : minutes % 60 === 0 ? `every ${minutes / 60} hour(s)` : `every ${minutes} minutes`; }
  function chiefView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading…")));
    (async () => {
      let state; try { state = await api("/api/chief"); } catch (issue) { root.replaceChildren(body(empty("Chief of Staff unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const jobs = array(state.jobs), goals = array(state.goals), runs = array(state.runs), day = state.overnight || {}, stats = el("div", "grid stats");
      [["Goals", goals.filter(goal => goal.status === "active").length, "active", "green"], ["Workers", jobs.filter(job => job.enabled).length, `of ${jobs.length} on`, ""],
       ["Last 24 hours", day.runs || 0, "runs", "cyan"], ["Problems", day.failed || 0, "failed runs", day.failed ? "red" : ""]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const goalList = el("div", "row-list");
      goals.forEach(goal => { const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", goal.title),
        el("div", "row-meta", [goal.rules.public_data_only ? "public data only" : "", goal.rules.ask_before_contact ? "asks before contacting anyone" : "", goal.monthly_cap ? `spend at most USD ${goal.monthly_cap} a month` : ""].filter(Boolean).join(" · "))),
        (state.plans || {})[goal.id] ? badge(`plan ${(state.plans || {})[goal.id].status}`, {proposed: "amber", approved: "green", declined: "muted"}[(state.plans || {})[goal.id].status]) : null,
        badge(goal.status, goal.status === "active" ? "green" : "muted")); row.addEventListener("click", () => goalDialog(goal, (state.plans || {})[goal.id])); goalList.append(row); });
      const jobRows = el("div", "row-list");
      jobs.forEach(job => {
        const toggle = check(job.enabled ? "On" : "Off", job.enabled);
        toggle.control.addEventListener("change", () => act(toggle.control.checked ? `${job.label}: on.` : `${job.label}: off.`, () => mutate(`/api/chief/jobs/${job.id}`, {enabled: toggle.control.checked}, "PATCH")).then(() => render()));
        const pace = select([[10, "every 10 minutes"], [30, "every 30 minutes"], [60, "every hour"], [360, "every 6 hours"], [1440, "every day"], [10080, "every week"]].map(([value, label]) => [String(value), label]), String(job.every_minutes));
        if (!Array.from(pace.options).some(item => item.value === String(job.every_minutes))) pace.append(option(String(job.every_minutes), everyText(job.every_minutes))), pace.value = String(job.every_minutes);
        pace.addEventListener("change", () => act("Saved.", () => mutate(`/api/chief/jobs/${job.id}`, {every_minutes: Number(pace.value)}, "PATCH")));
        const last = job.running ? "Running now…" : job.last_run_at ? `${relative(job.last_run_at)}: ${job.last_result}` : "Not run yet";
        jobRows.append(append(el("div", "worker"), append(el("div", "worker-head"), el("strong", "", job.label), job.outward ? el("span", "badge amber", "ACTS OUTSIDE") : null,
          job.last_status ? badge(job.last_status, RUN_STYLE[job.last_status]) : null),
          el("div", "row-meta", job.about), el("div", "row-meta", last),
          append(el("div", "worker-controls"), pace, toggle.wrap,
            button("Run now", () => act(result => result.message, () => mutate(`/api/chief/jobs/${job.id}/run`, {})).then(() => setTimeout(() => render(), 1500)), "button small"))));
      });
      const runTable = runs.length ? table(["When", "Worker", "Result", "Took"], runs.slice(0, 30).map(run => [relative(run.started_at), jobs.find(job => job.id === run.job_id)?.label || run.job_id,
        append(el("span"), badge(run.status, RUN_STYLE[run.status]), document.createTextNode(` ${run.result}`)), `${run.seconds}s`])) : body(empty("No runs yet", "Workers run on their schedules; the first runs appear here.", null, "◷"));
      const left = append(el("div"),
        panel("Goals", append(el("div"), body(append(el("div", "actions"), button("+ New goal", () => goalDialog(null), "button primary")),
          hint("Say what you want and the rules: “$5,000 a month of new client work, public data only, contact nobody without my yes”. The planner that turns a goal into jobs comes next; for now, goals keep your target and rules in one place.")),
          goals.length ? goalList : body(empty("No goals yet", "Set your first money goal and its rules.", null, "◎"))), null, goals.length),
        panel("Workers", append(el("div"), jobRows, body(hint("Each worker is part of Cerebra itself; nothing here runs code an AI wrote. Workers that act outside this computer follow the standing rules you set on their own pages (Apply automatically, approved posts)."))), null, jobs.length),
        panel("Recent runs", runTable, null, runs.length));
      const side = append(el("div"), panel("Your calls", callList(state.calls), null, array(state.calls).length), panel("Morning brief", body(briefPanel(state))),
        panel("Training data for Cerebra's own model", body(trainingPanel(state.training))),
        panel("Also running", body(kv(array(state.built_in).map(item => [item.label, item.about])))));
      root.replaceChildren(stats, append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  const CALL_ICON = {plan: "◈", approval: "✋", award: "★", proposal: "✎", post: "✉", overdue: "!", invoice: "¤", book: "▤", problem: "⚠"};
  function callList(items, emptyText = "Nothing waits for you.") {
    if (!array(items).length) return body(empty("All clear", emptyText, null, "✓"));
    const list = el("div", "row-list");
    array(items).forEach(item => { const row = append(el("a", "row clickable"), el("span", "call-icon", CALL_ICON[item.kind] || "•"), append(el("div", "row-main"), el("strong", "", item.title), el("div", "row-meta", item.detail)), el("span", "row-meta", relative(item.at)));
      row.href = `#${item.page}`; list.append(row); });
    return list;
  }
  function briefPanel(state) {
    const settings = state.settings || {}, root = el("div"), on = check("Send me a morning brief", settings.brief !== false);
    const hour = select(Array.from({length: 24}, (_, value) => [String(value), `${String(value).padStart(2, "0")}:00`]), String(settings.brief_hour ?? 8));
    on.control.addEventListener("change", () => act("Saved.", () => mutate("/api/chief/settings", {brief: on.control.checked}, "PUT")));
    hour.addEventListener("change", () => act("Saved.", () => mutate("/api/chief/settings", {brief_hour: Number(hour.value)}, "PUT")));
    append(root, append(el("ul", "tips"), ...array(state.brief?.lines).map(line => el("li", "", line))), append(el("div", "form-grid"), field("At", hour), on.wrap),
      actionsRow(button("Send it to my phone now", () => act(result => result.sent ? "Sent." : "Recorded. Set up phone notifications in Settings to receive it.", () => mutate("/api/chief/brief/send", {})), "button small")),
      hint("On your phone it says only how many decisions wait and how many runs happened: phone notifications can pass through a public server, so names and amounts stay in Cerebra."));
    return root;
  }
  function trainingPanel(training) {
    const root = el("div"), counts = training.counts || {}, collect = check("Keep collecting my work and its results", training.settings?.collect !== false);
    collect.control.addEventListener("change", () => act(collect.control.checked ? "Collecting." : "Stopped collecting.", () => mutate("/api/chief/training", {collect: collect.control.checked}, "PUT")).then(() => render()));
    const progress = el("div", "progress-bar"), fill = el("div", "progress-fill"); fill.style.width = `${Math.min(100, Math.round(100 * (training.proven || 0) / (training.needed || 200)))}%`; progress.append(fill);
    const rows = Object.entries(counts).flatMap(([kind, outcomes]) => Object.entries(outcomes).map(([outcome, count]) => [`${nice(kind)}s ${outcome}`, String(count)]));
    const save = button("Save the training file", async () => {
      const response = await fetch("/api/chief/training.jsonl", {credentials: "same-origin", cache: "no-store"});
      if (!response.ok) { toast("Couldn't build the file.", true); return; }
      const link = document.createElement("a"); link.href = URL.createObjectURL(await response.blob()); link.download = "cerebra-training.jsonl"; link.click(); URL.revokeObjectURL(link.href);
    }, "button small");
    append(root, kv([["Examples", String(training.total || 0)], ["With a good result", `${training.proven || 0} of the ${training.needed || 200} a first fine-tune needs`], ...rows]), progress,
      hint(training.note || ""), collect.wrap, actionsRow(save),
      hint("Your proposals with the job post and whether they won, and your posts that went out. Clients' deliverables are never included. When there are enough, Cerebra fine-tunes an open model on them, tests it against your paid model, and runs it on this computer."));
    return root;
  }
  function planSection(goal, plan) {
    const root = el("div");
    root.append(el("h3", "", "Plan"));
    const draft = () => act("Plan proposed. Read it before you approve.", () => mutate(`/api/chief/goals/${goal.id}/plan`, {}, "POST", 300000)).then(result => { if (result) goalDialog(goal, result); });
    if (!plan) return append(root, hint("Your AI looks at this goal, your rules and what has worked, and proposes which workers to run and how often. Nothing changes until you approve."), actionsRow(button("Plan it with my AI", draft, "button primary")));
    const jobs = table(["Worker", "Run", "How often", "Why"], array(plan.plan.jobs).map(job => [append(el("span"), document.createTextNode(job.label), job.outward ? el("span", "badge amber", " ACTS OUTSIDE") : null),
      job.run ? "Yes" : "No", everyText(job.every_minutes), job.why]));
    append(root, hint(plan.plan.summary || ""), jobs,
      array(plan.plan.owner_steps).length ? append(el("div"), el("h4", "", "Only you can do these"), append(el("ul", "tips"), ...plan.plan.owner_steps.map(step => el("li", "", step)))) : null,
      el("p", "row-meta", `Plan ${plan.status}${plan.model ? ` · written by ${plan.model}` : ""}. Workers that act outside still follow your own rules on their pages.`));
    if (plan.status === "proposed") root.append(actionsRow(button("Decline", () => act("Declined: nothing changed.", () => mutate(`/api/chief/goals/${goal.id}/plan/decline`, {})).then(result => { if (result) { closeDialog(); render(); } }), "button ghost"),
      button("Approve and apply", () => act("Approved: the workers are set.", () => mutate(`/api/chief/goals/${goal.id}/plan/approve`, {})).then(result => { if (result) { closeDialog(); render(); } }), "button primary")));
    else root.append(actionsRow(button("Plan again", draft, "button")));
    return root;
  }
  function goalDialog(goal, plan) {
    const form = el("form"), save = submitButton(goal ? "Save" : "Set the goal"), value = goal || {rules: {public_data_only: true, ask_before_contact: true}};
    const title = input("e.g. $5,000 a month of new client work", value.title || ""), target = textarea("What counts, where to look, who you sell to", value.target || "");
    const publicOnly = check("Public data only", value.rules.public_data_only !== false), ask = check("Contact nobody without my yes", value.rules.ask_before_contact !== false);
    const notes = textarea("Other rules, e.g. “US businesses only”, “no cold calls”", value.rules.notes || ""), cap = input("100", value.monthly_cap || "", "number");
    const status = select([["active", "Active"], ["paused", "Paused"], ["done", "Done"]], value.status || "active");
    title.required = true; cap.min = 0; cap.step = "1"; target.rows = 3; notes.rows = 2;
    append(form, field("Goal", title), field("Details", target), publicOnly.wrap, ask.wrap, field("Other rules", notes),
      append(el("div", "form-grid"), field("Spend at most (USD a month, on data and AI)", cap), field("Status", status)),
      actionsRow(goal ? button("Delete", () => act("Deleted.", () => api(`/api/chief/goals/${goal.id}`, {method: "DELETE"})).then(result => { if (result) { closeDialog(); render(); } }), "button ghost") : null, save));
    wireForm(form, save, async () => {
      const payload = {title: title.value, target: target.value, monthly_cap: Number(cap.value || 0), status: status.value,
        rules: {public_data_only: publicOnly.control.checked, ask_before_contact: ask.control.checked, notes: notes.value}};
      if (goal) await mutate(`/api/chief/goals/${goal.id}`, payload, "PATCH"); else await mutate("/api/chief/goals", payload);
      closeDialog(); toast("Saved."); render();
    });
    if (goal) form.append(planSection(goal, plan));
    showDialog(goal ? goal.title : "New goal", form);
  }

  // ---------- prospects: US local businesses that could use what you sell ----------
  const PROSPECT_STYLE = {kept: "blue", contacted: "amber", replied: "cyan", won: "green", lost: "muted", new: "muted", dropped: "muted"};
  let prospectFilter = "kept", prospectSender = [];
  function prospectsView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading…")));
    (async () => {
      let state; try { state = await api("/api/prospects"); } catch (issue) { root.replaceChildren(body(empty("Prospects unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const counts = state.counts || {}, stats = el("div", "grid stats");
      [["Worth contacting", counts.kept || 0, "each with a reason", "blue"], ["Contacted", counts.contacted || 0, "waiting to hear", "amber"],
       ["Replied", counts.replied || 0, "talking with you", "cyan"], ["Won", counts.won || 0, "became clients", "green"]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const form = el("form"), go = submitButton("Find businesses");
      const kind = select(Object.entries(state.kinds).map(([key, label]) => [key, label]), "dentists"), city = input("Austin"), where = input("Texas");
      city.required = true; where.required = true;
      append(form, append(el("div", "form-grid"), field("Kind of business", kind), field("City", city), field("State", where)), actionsRow(go));
      wireForm(form, go, async () => { const result = await mutate("/api/prospects/search", {kind: kind.value, city: city.value, state: where.value}); toast(result.message); render(); });
      const search = state.search || {}; prospectSender = array(state.sender_missing);
      if (search.running) { go.disabled = true; setTimeout(() => { if (token === renderToken) render(); }, 5000); }
      const filters = {kept: "Worth contacting", new: `To check by hand (${counts.new || 0})`, contacted: "Contacted", replied: "Replied", won: "Won", lost: "Lost", all: "Everything"};
      const pick = select(Object.entries(filters), prospectFilter); pick.addEventListener("change", () => { prospectFilter = pick.value; render(); });
      const shown = array(state.prospects).filter(item => prospectFilter === "all" || item.status === prospectFilter);
      const list = el("div", "row-list");
      shown.slice(0, 200).forEach(item => { const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", item.name),
        el("div", "row-meta", [item.kind_label, `${item.city}, ${item.state}`, item.website ? item.website.replace(/^https?:\/\//, "").replace(/\/$/, "") : "no website"].join(" · ")),
        el("div", "row-meta", array(item.facts).map(fact => fact.text).slice(0, 2).join(" · "))), badge(item.status, PROSPECT_STYLE[item.status]));
        row.addEventListener("click", () => prospectDialog(item)); list.append(row); });
      const searches = array(state.searches).slice(0, 8).map(item => [`${item.kind_label} in ${item.city}, ${item.state}`, `${item.counts.found ?? "…"} found · ${item.counts.chains ?? 0} chains left out · ${item.counts.kept ?? 0} kept`]);
      const left = append(el("div"), panel("Businesses", append(el("div"), body(append(el("div", "actions"), pick)),
        shown.length ? list : body(empty(prospectFilter === "kept" ? "None yet" : "Nothing here", "Run a search: Cerebra lists local businesses from OpenStreetMap, leaves out chains, reads each one's own home page once, and keeps those with a concrete reason to talk to you.", null, "⌖"))), null, shown.length));
      const side = append(el("div"),
        panel("Find businesses", body(form, search.message ? hint(search.running ? `${search.message} This page refreshes itself.` : search.message) : null,
          hint("Public data only. Nobody is contacted: you decide who to approach, and how. Your searches run again every week and add only new businesses (switch it off on the Chief of Staff page)."))),
        searches.length ? panel("Recent searches", body(kv(searches))) : null,
        searches.length ? panel("Your offer", body(offerPanel(state))) : null,
        panel("How it works", body(hint("Each fact comes from the business's own home page, read once where its robots.txt allows, and shows where it was seen. A site that turns robots away gets no claim at all. Chains (brand-tagged, or 3 or more locations in the city) are left out."),
          el("p", "row-meta", state.attribution))));
      root.replaceChildren(stats, append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  function offerPanel(state) {
    const root = el("div"), kinds = [...new Set(array(state.searches).map(item => item.kind))];
    const kind = select(kinds.map(key => [key, state.kinds[key]]), kinds[0]), out = el("div");
    const show = () => {
      const offer = (state.offers || {})[kind.value] || {}, price = input("Your price, e.g. USD 1,500 setup + USD 150 a month", offer.price || "");
      const headline = input("Headline", offer.headline || ""), problem = textarea("The problem", offer.problem || ""), included = textarea("What's included, one per line", array(offer.included).join("\n"));
      const steps = textarea("How it works, one step per line", array(offer.steps).join("\n")), timeline = input("Timeline", offer.timeline || "");
      problem.rows = 3; included.rows = 4; steps.rows = 3;
      const payload = () => ({headline: headline.value, problem: problem.value, included: included.value.split("\n"), steps: steps.value.split("\n"), timeline: timeline.value, price: price.value});
      const text = () => [headline.value, "", problem.value, "", "What's included:", ...included.value.split("\n").filter(Boolean).map(line => `- ${line}`), "", "How it works:",
        ...steps.value.split("\n").filter(Boolean).map((line, index) => `${index + 1}. ${line}`), "", `Timeline: ${timeline.value}`, `Price: ${price.value || "(set your price)"}`].join("\n");
      out.replaceChildren(offer.headline ? append(el("div"), field("Headline", headline), field("The problem (from what Cerebra saw)", problem), field("What's included", included), field("How it works", steps),
          append(el("div", "form-grid"), field("Timeline", timeline), field("Price (yours to set)", price))) : hint("No offer yet for these businesses."),
        actionsRow(button(offer.headline ? "Draft again" : "Draft the offer", () => act("Drafted. Set your price.", () => mutate(`/api/prospects/offer/${kind.value}`, {}, "POST", 300000)).then(result => { if (result) render(); }), "button"),
          offer.headline ? button("Copy as text", () => navigator.clipboard.writeText(text()).then(() => toast("Copied.")), "button ghost") : null,
          offer.headline ? button("Save", () => act("Saved.", () => mutate(`/api/prospects/offer/${kind.value}`, payload(), "PUT")), "button primary") : null),
        offer.headline && !offer.price ? hint("The price is blank on purpose: it's your call.", true) : null);
    };
    kind.addEventListener("change", show); show();
    append(root, field("For", kind), out, hint("Built from what Cerebra saw on these businesses' sites and from your own services. No invented results or testimonials."));
    return root;
  }
  function prospectDialog(item, missing = array(prospectSender)) {
    const root = el("div"), notes = textarea("What you did, who you spoke to, next step…", item.notes || "");
    const opener = textarea("Draft a first email about what Cerebra saw on their site", item.opener || ""); opener.rows = 9;
    const draft = button(item.opener ? "Draft again" : "Draft a first email", () => act(result => result.missing?.length ? "Drafted. Add the missing details before sending." : "Drafted. Read it before you send it.",
      () => mutate(`/api/prospects/${item.id}/opener`, {}, "POST", 300000)).then(result => { if (result) { opener.value = result.opener; prospectSender = result.missing; } }), "button");
    const copy = button("Copy", () => navigator.clipboard.writeText(opener.value).then(() => toast("Copied. Paste it into your email.")), "button ghost");
    const status = select([["new", "To check by hand"], ["kept", "Worth contacting"], ["contacted", "Contacted"], ["replied", "Replied"], ["won", "Won: became a client"], ["lost", "Lost"], ["dropped", "Not a fit"]], item.status);
    const facts = el("ul", "tips"); array(item.facts).forEach(fact => facts.append(append(el("li"), document.createTextNode(fact.text), el("span", "row-meta", ` (seen at ${fact.seen})`))));
    append(root, kv([["Business", item.kind_label], ["Where", [item.address, `${item.city}, ${item.state}`].filter(Boolean).join(", ")], ["Website", item.website || "None listed"], ["Phone", item.phone || "Not listed"]]),
      el("h3", "", "What Cerebra saw"), array(item.facts).length ? facts : hint(item.notes || "No issue seen on the home page."),
      append(el("div", "form-grid"), field("Status", status)), field("Notes", notes),
      el("h3", "", "First email"), opener,
      missing.length ? hint(`Before sending, add ${missing.join(" and ")} in Money › Your business details.`, true) : null,
      hint("Read it, change anything, then send it yourself from your own email. In the US, cold emails need your real postal address and a way to opt out (CAN-SPAM); Cerebra adds both."),
      actionsRow(array(item.facts).length ? draft : null, copy,
        button("Save", () => act("Saved.", () => mutate(`/api/prospects/${item.id}`, {status: status.value, notes: notes.value, opener: opener.value}, "PATCH")).then(result => { if (result) { closeDialog(); render(); } }), "button primary")));
    showDialog(item.name, root);
  }

  // ---------- funding: credits, grants and accelerators ----------
  const FUND_STYLE = {credits: "cyan", grant: "green", accelerator: "purple"};
  function fundingView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading…")));
    (async () => {
      let state; try { state = await api("/api/funding"); } catch (issue) { root.replaceChildren(body(empty("Funding unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const programs = array(state.programs), proof = state.evidence || {}, stats = el("div", "grid stats");
      const applied = programs.filter(item => item.applied?.status === "applied").length, accepted = programs.filter(item => item.applied?.status === "accepted").length;
      [["Ready to apply", state.ready, `of ${programs.length} programs`, "green"], ["Applied", applied, "waiting to hear", "amber"], ["Accepted", accepted, "credits or funding won", "cyan"],
       ["Paying customers", proof.paying_customers ? "Yes" : "Not yet", proof.jobs_won ? `${proof.jobs_won} job(s) won` : "from your records", ""]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const list = el("div", "row-list");
      programs.forEach(program => {
        const status = select([["", "Not started"], ["planned", "Planning to apply"], ["applied", "Applied"], ["accepted", "Accepted"], ["declined", "Declined"]], program.applied?.status || "");
        status.addEventListener("change", () => act("Saved.", () => mutate(`/api/funding/programs/${program.key}`, {status: status.value}, "PUT")).then(() => render()));
        list.append(append(el("div", "worker"), append(el("div", "worker-head"), el("strong", "", program.name), badge(program.kind, FUND_STYLE[program.kind]),
            program.equity ? el("span", "badge amber", "TAKES EQUITY") : el("span", "badge muted", "NO EQUITY"), program.ready ? el("span", "badge green", "READY") : null),
          el("div", "", program.gives), el("div", "row-meta", program.window),
          program.ready ? el("div", "row-meta", "You meet what this program asks for.") : el("div", "row-meta", `Still needed: ${program.missing.join(", ")}`),
          append(el("div", "worker-controls"), status, button("Open the official page", () => act("Opened in your browser.", () => mutate(`/api/funding/programs/${program.key}/open`, {})), "button small"),
            button((state.drafts || {})[program.key] ? "Your draft answers" : "Draft my answers", () => (state.drafts || {})[program.key] ? fundingDraftDialog(program, state.drafts[program.key])
              : act("Drafted. Read it and fill in the TO FILL lines.", () => mutate(`/api/funding/programs/${program.key}/draft`, {}, "POST", 300000)).then(result => { if (result) fundingDraftDialog(program, result); }), "button small"))));
      });
      const left = append(el("div"), panel("Programs", append(el("div"), list, body(hint(`Each program was checked against its official page on ${state.checked}. Amounts and deadlines change: open the official page before you apply. Cerebra never applies for you.`))), null, programs.length));
      const side = append(el("div"), panel("Your facts", body(fundingFacts(state))),
        panel("What your records show", body(kv([["Earned this year", Object.entries(proof.earned_this_year || {}).map(([currency, amount]) => `${currency} ${Number(amount).toLocaleString(undefined, {minimumFractionDigits: 2})}`).join(" + ") || "Nothing recorded yet"],
          ["Product sales", String(proof.product_sales || 0)], ["Freelance jobs won", String(proof.jobs_won || 0)]]), hint("Programs that ask for paying customers are checked against these records, not just your word."))),
        panel("Why this matters", body(hint("Credits pay for the cloud and AI that run Cerebra's own model later; grants and accelerators bring money and mentors. A registered company and a website unlock most of them."))));
      root.replaceChildren(stats, append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  function fundingDraftDialog(program, draft) {
    const root = el("div"), boxes = array(draft.answers).map(item => { const box = textarea("", item.answer); box.rows = 5; return {question: item.question, box}; });
    const gaps = boxes.filter(item => item.box.value.includes("TO FILL:")).length;
    append(root, gaps ? hint(`${gaps} answer(s) have a TO FILL line: replace it with the real detail before you submit.`, true) : hint("Read every answer: it's your application."),
      ...boxes.map(item => field(item.question, item.box)),
      hint(`Written from your records${draft.model ? ` by ${draft.model}` : ""}. Never submit anything you can't back up. Paste the answers into the program's own form.`),
      actionsRow(button("Draft again", () => act("Drafted again.", () => mutate(`/api/funding/programs/${program.key}/draft`, {}, "POST", 300000)).then(result => { if (result) fundingDraftDialog(program, result); }), "button ghost"),
        button("Copy all", () => navigator.clipboard.writeText(boxes.map(item => `${item.question}\n${item.box.value}`).join("\n\n")).then(() => toast("Copied.")), "button"),
        button("Save", () => act("Saved.", () => mutate(`/api/funding/programs/${program.key}/draft`, {answers: boxes.map(item => item.box.value)}, "PUT")).then(result => { if (result) { closeDialog(); render(); } }), "button primary")));
    showDialog(`${program.name}: your answers`, root);
  }
  function fundingFacts(state) {
    const value = state.facts, form = el("form"), save = submitButton("Save");
    const company = check("I have a registered company", value.company), country = input("Where it's registered, e.g. Kenya or Delaware, USA", value.company_country);
    const website = input("https://your-company.com", value.website), founded = input("2026", value.founded_year || "", "number");
    const product = check("Something I built is live and people use it", value.product), african = check("I'm an African citizen or resident, 18 or older", value.african);
    const selfFunded = check("No outside investors yet", value.self_funded), awsPaid = check("My AWS account is on a paid plan", value.aws_paid);
    append(form, company.wrap, append(el("div", "form-grid"), field("Country", country), field("Founded (year)", founded)), field("Company website", website),
      product.wrap, african.wrap, selfFunded.wrap, awsPaid.wrap, actionsRow(save));
    wireForm(form, save, async () => {
      await mutate("/api/funding/facts", {company: company.control.checked, company_country: country.value, website: website.value, founded_year: Number(founded.value || 0),
        product: product.control.checked, african: african.control.checked, self_funded: selfFunded.control.checked, aws_paid: awsPaid.control.checked}, "PUT");
      toast("Saved. Readiness updated."); render();
    });
    return form;
  }

  // ---------- books: short nonfiction for Amazon KDP ----------
  const BOOK_STYLE = {planned: "blue", writing: "amber", files_ready: "cyan", published: "green", retired: "muted"};
  const NICHE_STYLE = {idea: "blue", researching: "amber", chosen: "green", dropped: "muted"};
  const usd = value => `USD ${Number(value || 0).toFixed(2)}`;
  function royaltyLine(name, result) {
    if (!result) return null;
    if (result.problem) return [name, result.problem];
    const how = result.printing !== undefined ? `${Math.round(result.rate * 100)}% of ${usd(result.price)} − ${usd(result.printing)} printing`
      : `${Math.round(result.rate * 100)}% of ${usd(result.price)}${result.delivery ? ` − ${usd(result.delivery)} delivery` : ""}`;
    return [name, result.allowed ? `${usd(result.royalty)} a copy (${how})` : `Not allowed: the lowest price is ${usd(result.minimum_price)}`];
  }
  function earningsRows(earnings) {
    if (!earnings) return [];
    if (earnings.problem) return [["Size", earnings.problem]];
    return [royaltyLine("Paperback", earnings.paperback), royaltyLine("Kindle", earnings.kindle), royaltyLine("Hardcover", earnings.hardcover),
      ["Pages", `${earnings.pages}${earnings.pages_estimated ? " (estimated from the word count)" : ""} · ${earnings.trim} in, ${earnings.paper} paper`],
      ["Cover (paperback)", `${earnings.cover.width}" × ${earnings.cover.height}" with a ${earnings.cover.spine}" spine${earnings.cover.spine_text ? "" : " (too thin for spine text)"}`]].filter(Boolean);
  }
  function booksView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading your books…")));
    (async () => {
      let state; try { state = await api("/api/books"); } catch (issue) { root.replaceChildren(body(empty("Books unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const books = array(state.books), niches = array(state.niches), stats = el("div", "grid stats");
      const count = status => books.filter(book => book.status === status).length;
      [["Niches", niches.filter(niche => niche.status !== "dropped").length, "ideas being checked", ""], ["Writing", count("planned") + count("writing"), "planned or being written", "amber"],
       ["Ready to upload", count("files_ready"), "files waiting for you", "cyan"], ["Published", count("published"), `${state.today.published} of ${state.today.cap} new titles today`, "green"]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const nicheList = el("div", "row-list");
      niches.forEach(niche => nicheList.append(append(el("div", "row clickable"), scoreBadge(niche.score), append(el("div", "row-main"), el("strong", "", niche.area),
        el("div", "row-meta", [niche.reader, niche.problem].filter(Boolean).join(" · ") || "Name one reader and one problem")), badge(niche.status, NICHE_STYLE[niche.status]))));
      Array.from(nicheList.children).forEach((row, index) => row.addEventListener("click", () => nicheDialog(niches[index], state)));
      const bookList = el("div", "row-list");
      books.forEach(book => {
        const best = book.earnings?.paperback?.royalty ?? book.earnings?.kindle?.royalty;
        const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", book.title), el("div", "row-meta", [book.subtitle, book.pen_name ? `by ${book.pen_name}` : "", best !== undefined ? `${usd(best)} a paperback` : ""].filter(Boolean).join(" · "))),
          badge(book.status, BOOK_STYLE[book.status]));
        row.addEventListener("click", () => bookDialog(book, state)); bookList.append(row);
      });
      const left = append(el("div"),
        panel("Niches", append(el("div"), body(append(el("div", "actions"), button("+ New niche", () => nicheDialog(null, state), "button primary")),
          hint("One reader with one problem (“sleep after menopause”, not “health”). The score uses only what you checked: competing books' Best Sellers Rank and reviews, and the search trend.")),
          niches.length ? nicheList : body(empty("No niches yet", "Add a problem people already pay to fix. Check its trend on Google Trends and its competing books on Amazon.", null, "◎"))), null, niches.length),
        panel("Books", append(el("div"), body(append(el("div", "actions"), button("+ New book", () => bookDialog(null, state), "button primary"))),
          books.length ? bookList : body(empty("No books yet", "Start one from a niche you chose. Cerebra shows what each format earns before you write a word.", null, "▤"))), null, books.length));
      const side = append(el("div"), panel("Start publishing", body(publishingChecklist(state))), panel("What a book earns", body(royaltyCalculator(state))),
        panel("How it works", body(hint("You pick a niche, Cerebra helps plan, write and check the book, and prepares the files and listing. KDP has no publishing API, so you upload and click Publish yourself, including Amazon's AI-content question. KDP allows 3 new titles a day."),
          el("p", "row-meta", `KDP's numbers were checked on ${state.checked} against its help pages: ${Object.values(state.sources).join(" · ")}`))));
      root.replaceChildren(stats, append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  function publishingChecklist(state) {
    const root = el("div"), boxes = array(state.checklist).map(item => { const box = check(item.title, item.done); box.key = item.key; box.how = item.how; return box; });
    boxes.forEach(box => { box.control.addEventListener("change", () => act("Saved.", () => mutate("/api/books/settings", {done: boxes.filter(item => item.control.checked).map(item => item.key)}, "PUT")));
      root.append(append(el("div", "steps-item"), box.wrap, el("small", "row-meta", box.how))); });
    const names = input("Pen names, separated by commas", array(state.settings.pen_names).join(", "));
    names.addEventListener("change", () => act("Pen names saved.", () => mutate("/api/books/settings", {pen_names: names.value.split(",").map(name => name.trim()).filter(Boolean)}, "PUT")));
    return append(el("div"), root, field("Pen names", names, "Used on your books; your KDP account stays in your own name."));
  }
  function bookSizeFields(state, values) {
    const trim = select(array(state.options.trims).map(name => [name, `${name.replace("x", " × ")} in`]), values.trim || state.settings.default_trim);
    const paper = select([["white", "White paper"], ["cream", "Cream paper"]], values.paper || state.settings.default_paper);
    const pages = input("Printed pages (or leave empty)", values.pages || "", "number"), words = input("Words, about", values.words || "", "number");
    pages.min = 0; words.min = 0; words.step = 500;
    const prices = Object.fromEntries(["paperback", "kindle", "hardcover"].map(name => { const box = input(name === "kindle" ? "4.99" : name === "paperback" ? "12.99" : "22.99", values.prices?.[name] || "", "number"); box.step = "0.01"; box.min = 0; return [name, box]; }));
    return {trim, paper, pages, words, prices, payload: () => ({trim: trim.value, paper: paper.value, pages: Number(pages.value || 0), words: Number(words.value || 0),
      prices: Object.fromEntries(Object.entries(prices).filter(([, box]) => box.value).map(([name, box]) => [name, Number(box.value)]))})};
  }
  function royaltyCalculator(state) {
    const root = el("div"), size = bookSizeFields(state, {pages: 120, prices: {paperback: 12.99, kindle: 4.99}}), out = el("div");
    const run = async () => { const result = await api("/api/books/calculate", {method: "POST", body: JSON.stringify(size.payload())}).catch(issue => ({problem: issue.message})); out.replaceChildren(kv(earningsRows(result))); };
    [size.trim, size.paper, size.pages, size.words, ...Object.values(size.prices)].forEach(control => control.addEventListener("input", run));
    append(root, append(el("div", "form-grid"), field("Trim size", size.trim), field("Paper", size.paper), field("Pages", size.pages), field("Words", size.words)),
      append(el("div", "form-grid"), field("Paperback USD", size.prices.paperback), field("Kindle USD", size.prices.kindle), field("Hardcover USD", size.prices.hardcover)), out,
      hint("From KDP's published printing costs and royalties on Amazon.com. Paperbacks earn 50% under 9.99 USD and 60% from 9.99; Kindle earns 70% from 2.99 to 12.99 USD, else 35%."));
    run();
    return root;
  }
  function nicheDialog(niche, state) {
    const form = el("form"), save = submitButton(niche ? "Save and re-score" : "Add and score it"), value = niche || {};
    const area = input("e.g. Sleep after menopause", value.area || ""), reader = input("e.g. Women 45–60 who wake at 3 am", value.reader || ""), problem = input("e.g. Can't stay asleep, tired at work", value.problem || "");
    const trend = select([["", "Not checked yet"], ["rising", "Rising"], ["flat", "Flat for years (lasting)"], ["fad", "A spike that fell (fad)"]], value.trend || "");
    const status = select([["idea", "Idea"], ["researching", "Researching"], ["chosen", "Chosen"], ["dropped", "Dropped"]], value.status || "idea");
    const competitors = textarea("Title | Best Sellers Rank | reviews | paperback price | Kindle price — one book a line",
      array(value.competitors).map(book => [book.title, book.bsr ?? "", book.reviews ?? "", book.paperback ?? "", book.kindle ?? ""].join(" | ")).join("\n"));
    const notes = textarea("Your notes", value.notes || ""); area.required = true; competitors.rows = 6; notes.rows = 3;
    append(form, field("Area", area), append(el("div", "form-grid"), field("The reader", reader), field("Their problem", problem)),
      append(el("div", "form-grid"), field("Google Trends, 5 years", trend, "Search it on trends.google.com over 5 years."), field("Status", status)),
      field("Competing books on Amazon", competitors, "From each top book's page: Product details › Best Sellers Rank. Under 100,000 sells; over 1,000,000 doesn't."),
      field("Notes", notes), value.reasons ? hint(`Score ${value.score}: ${array(value.reasons).join(" · ")}`) : null,
      actionsRow(niche ? button("Delete", () => act("Deleted.", () => api(`/api/books/niches/${niche.id}`, {method: "DELETE"})).then(result => { if (result) { closeDialog(); render(); } }), "button ghost") : null, save));
    wireForm(form, save, async () => {
      const payload = {area: area.value, reader: reader.value, problem: problem.value, trend: trend.value, status: status.value, competitors: competitors.value, notes: notes.value};
      const saved = niche ? await mutate(`/api/books/niches/${niche.id}`, payload, "PATCH") : await mutate("/api/books/niches", payload);
      toast(`Scored ${saved.score}/100.`); render(); nicheDialog(saved, state);
    });
    showDialog(niche ? niche.area : "New niche", form);
  }
  function bookDialog(book, state) {
    const form = el("form"), save = submitButton(book ? "Save" : "Add the book"), value = book || {};
    const niche = select([["", "No niche"], ...array(state.niches).map(item => [item.id, item.area])], value.niche_id || "");
    const title = input("Working title", value.title || ""), subtitle = input("Subtitle (optional)", value.subtitle || "");
    const pen = select([["", "Choose a pen name"], ...array(state.settings.pen_names).map(name => [name, name])], value.pen_name || "");
    const status = select(array(state.options.statuses).map(name => [name, nice(name)]), value.status || "planned");
    const formats = array(state.options.formats).map(name => { const box = check(nice(name), array(value.formats || ["paperback", "kindle"]).includes(name)); box.key = name; return box; });
    const size = bookSizeFields(state, value), asins = Object.fromEntries(array(state.options.formats).map(name => [name, input(name === "kindle" ? "ASIN, e.g. B0…" : "ISBN or ASIN", value.asins?.[name] || "")]));
    title.required = true;
    append(form, append(el("div", "form-grid"), field("Title", title), field("Subtitle", subtitle)), append(el("div", "form-grid"), field("Niche", niche), field("Pen name", pen), field("Status", status)),
      append(el("div", "check-list"), ...formats.map(box => box.wrap)),
      append(el("div", "form-grid"), field("Trim size", size.trim), field("Paper", size.paper), field("Pages", size.pages), field("Words", size.words)),
      append(el("div", "form-grid"), field("Paperback USD", size.prices.paperback), field("Kindle USD", size.prices.kindle), field("Hardcover USD", size.prices.hardcover)),
      value.earnings ? kv(earningsRows(value.earnings)) : null,
      value.status === "published" || value.status === "files_ready" ? append(el("div", "form-grid"), field("Paperback ISBN", asins.paperback), field("Kindle ASIN", asins.kindle), field("Hardcover ISBN", asins.hardcover)) : null,
      actionsRow(book && book.status !== "published" ? button("Delete", () => act("Deleted.", () => api(`/api/books/items/${book.id}`, {method: "DELETE"})).then(result => { if (result) { closeDialog(); render(); } }), "button ghost") : null, save));
    wireForm(form, save, async () => {
      const payload = {...size.payload(), niche_id: niche.value || null, title: title.value, subtitle: subtitle.value, pen_name: pen.value, status: status.value,
        formats: formats.filter(box => box.control.checked).map(box => box.key)};
      if (value.status === "published" || value.status === "files_ready") payload.asins = Object.fromEntries(Object.entries(asins).map(([name, box]) => [name, box.value.trim()]));
      if (payload.status === "published" && value.status !== "published" && state.today.published >= state.today.cap) throw new Error(`KDP allows ${state.today.cap} new titles a day; publish this one tomorrow.`);
      const saved = book ? await mutate(`/api/books/items/${book.id}`, payload, "PATCH") : await mutate("/api/books/items", payload);
      toast("Saved."); render(); bookDialog(saved, state);
    });
    showDialog(book ? book.title : "New book", form);
  }

  // ---------- freelance: work found for the owner ----------
  const LEAD_STYLE = {new: "blue", saved: "amber", applied: "purple", interview: "cyan", awarded: "green", won: "green", lost: "muted", hidden: "muted"};
  let leadFilter = "open";
  function scoreBadge(score) { return el("span", `badge ${score >= 50 ? "green" : score >= 25 ? "amber" : "muted"}`, String(score)); }
  function leadMoney(lead) {
    const low = lead.budget_min, high = lead.budget_max;
    if (!low && !high) return "";
    const range = `${lead.currency || ""} ${Number(low || high).toLocaleString()}${high && high !== low ? `–${Number(high).toLocaleString()}` : ""}`.trim();
    return lead.kind === "hourly" ? `${range}/hour` : lead.kind === "job" ? `salary ${range}` : range;
  }
  function freelanceView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading freelance work…")));
    (async () => {
      let state; try { state = await api("/api/freelance"); } catch (issue) { root.replaceChildren(body(empty("Freelance unavailable", issue.message))); return; }
      freelanceState = state;
      if (token !== renderToken) return;
      const counts = state.summary, stats = el("div", "grid stats");
      [["Strong matches", counts.good_matches, "new work that fits what you sell", "green"], ["Applied", counts.applied, "waiting for the client", "amber"],
       ["Interviews", counts.interview, "talking with clients", "cyan"], ["Won", counts.won, "jobs you got", ""]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const filters = {open: ["Best matches", lead => ["new", "saved"].includes(lead.status) && lead.score > 0], saved: ["Saved", lead => lead.status === "saved"],
        applied: ["In progress", lead => ["applied", "interview", "awarded"].includes(lead.status)], done: ["Won & lost", lead => ["won", "lost"].includes(lead.status)], all: ["Everything", () => true]};
      const pick = select(Object.entries(filters).map(([key, [label]]) => [key, label]), leadFilter);
      pick.addEventListener("change", () => { leadFilter = pick.value; render(); });
      const shown = array(state.leads).filter(filters[leadFilter]?.[1] || (() => true)).slice(0, 120);
      const list = el("div", "row-list");
      shown.forEach(lead => list.append(leadRow(lead, state)));
      const left = append(el("div"), panel("Work for you", append(el("div"), body(append(el("div", "actions"), pick,
        button("Check for new work now", () => act(result => checkWords(result), () => mutate("/api/freelance/check", {}, "POST", 300000)).then(() => render()), "button primary"),
        button("+ Paste a job", () => pasteLeadDialog(state), "button"))),
        shown.length ? list : body(empty(leadFilter === "open" ? "No matches yet" : "Nothing here yet", leadFilter === "open" ? "Press “Check for new work now”: Cerebra reads Freelancer.com, Remote OK, Remotive, Himalayas and Hacker News for work that fits what you sell. Paste jobs from Upwork or Fiverr too." : "Leads you mark appear here.", null, "⌕"))), null, shown.length));
      const side = append(el("div"), panel("What you sell", body(freelanceProfileForm(state))), panel("Where Cerebra looks", body(sourcesList(state))), panel("Freelancer.com account", body(freelancerAccount(state))), panel("What works", body(insightsPanel())), panel("Apply automatically", body(autoApplyPanel())), panel("Profiles, gigs and portfolio", body(pitchesPanel())),
        panel("How it works", body(hint("Cerebra reads public job sources on its own (each on its own polite schedule) and scores every job against what you sell: freelance and contract work, real budgets, fresh posts and few competing bids rank first. On Freelancer.com it can bid for you (Apply automatically); everywhere else, open a job and apply in your own name with the proposal Cerebra writes. Upwork and Fiverr don't allow automated bidding, so paste their jobs here to have them scored with the rest."))));
      root.replaceChildren(stats, append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  const SOURCE_NAMES = {freelancer: "Freelancer.com", remoteok: "Remote OK", remotive: "Remotive", himalayas: "Himalayas", hn: "Hacker News"};
  function checkWords(result) {
    const parts = Object.entries(result || {}).map(([name, item]) => `${SOURCE_NAMES[name] || name}: ${item.error ? "couldn't read it" : `${item.added} new`}`);
    return parts.length ? `Checked. ${parts.join(" · ")}` : "Nothing to check: all sources are switched off.";
  }
  function leadRow(lead, state) {
    const row = el("div", "row lead-row"), info = el("div", "row-main");
    row.tabIndex = 0; row.setAttribute("role", "button"); row.dataset.leadId = lead.id;
    const meta = [lead.source_label, leadMoney(lead), lead.posted_at ? relative(lead.posted_at) : "", lead.bids != null ? `${lead.bids} bids` : ""].filter(Boolean).join(" · ");
    append(info, el("strong", "", lead.title), el("div", "row-meta", meta), el("div", "row-reason waiting", array(lead.reasons).join(" · ")));
    const actions = append(el("div", "lead-actions"), scoreBadge(lead.score), lead.status !== "new" ? badge(lead.status, LEAD_STYLE[lead.status]) : null);
    append(row, info, actions);
    row.addEventListener("click", () => leadDialog(lead, state)); row.addEventListener("keydown", event => { if (event.key === "Enter") leadDialog(lead, state); });
    return row;
  }
  function setLead(lead, changes, message) { return act(message, () => mutate(`/api/freelance/leads/${encodeURIComponent(lead.id)}`, changes, "PATCH")).then(result => { if (result) { closeDialog(); render(); } }); }
  function leadDialog(lead, state) {
    const root = el("div"), notes = textarea("Your notes: what you offered, the client's name, next step…", lead.notes || "");
    append(root, append(el("div", "detail-top"), scoreBadge(lead.score), badge(lead.status, LEAD_STYLE[lead.status]), el("span", "row-meta", [lead.source_label, leadMoney(lead), lead.posted_at ? relative(lead.posted_at) : ""].filter(Boolean).join(" · "))),
      hint(array(lead.reasons).join(" · ")), (() => { const text = el("pre", "lead-description", lead.description || "No description.");
        if (lead.description_cut) { text.textContent += "…"; api(`/api/freelance/leads/${encodeURIComponent(lead.id)}`).then(full => { text.textContent = full.description; }).catch(() => {}); }
        return text; })(),
      lead.credit ? el("p", "row-meta", `${lead.credit}. Apply on their page.`) : null,
      array(lead.checks).length ? hint(`This post checks that applicants read it: it asks you to mention the word ${array(lead.checks).map(item => `“${item.word}”${item.tag ? ` (and the tag ${item.tag})` : ""}`).join(", ")}. Cerebra doesn't add it by itself; put it in your application if you apply.`) : null,
      proposalSection(lead, state), field("Notes", notes));
    const actions = el("div", "actions");
    if (lead.url) actions.append(button("Open the job page", () => act("Opened in your browser.", () => mutate("/api/freelance/open", {id: lead.id})), "button primary"));
    if (lead.status === "new") actions.append(button("Save for later", () => setLead(lead, {status: "saved", notes: notes.value}, "Saved."), "button"));
    if (["new", "saved"].includes(lead.status)) actions.append(button("I applied", () => setLead(lead, {status: "applied", notes: notes.value}, "Marked as applied. Good luck!"), "button"));
    if (lead.status === "applied") actions.append(button("Client replied", () => setLead(lead, {status: "interview", notes: notes.value}, "Marked as talking with the client."), "button"));
    if (lead.status === "awarded" && lead.source === "freelancer") actions.append(button("Accept the award", () => showDialog("Accept this award?", append(el("div"),
      el("p", "", `Accepting commits you to “${lead.title}” at your bid (${lead.currency || "USD"} ${lead.proposal?.price || "?"}, ${lead.proposal?.days || "?"} day(s)). Cerebra then starts the work.`),
      actionsRow(button("Back", () => leadDialog(lead, state), "button ghost"), button("Accept", () => act(result => result.message, () => mutate("/api/freelance/accept-award", {id: lead.id})).then(result => { if (result) { closeDialog(); render(); } }), "button primary")))), "button primary"));
    if (lead.status === "awarded" && lead.source !== "freelancer") root.append(hint(`The client chose you. Accept the offer on ${lead.source_label}; when the contract starts, Cerebra sees it in your email and starts the work.`));
    if (lead.status === "won") root.append(lead.job_id ? append(hint("Won. Cerebra is building this job by itself; you review it before anything goes to the client."), link("Open the job →", `job/${lead.job_id}`))
      : hint(lead.work_error ? `Won, but the work couldn't start: ${lead.work_error}` : "Won. Cerebra starts the work in its next round (every 10 minutes).", !!lead.work_error));
    if (["applied", "interview"].includes(lead.status)) actions.append(button("I won it", () => setLead(lead, {status: "won", notes: notes.value}, "Congratulations! Quote or invoice it from the Money page."), "button primary"), button("Didn't get it", () => setLead(lead, {status: "lost", notes: notes.value}, "Noted."), "button ghost"));
    if (lead.status !== "hidden") actions.append(button("Hide", () => setLead(lead, {status: "hidden", notes: notes.value}, "Hidden."), "button ghost"));
    else actions.append(button("Show again", () => setLead(lead, {status: "new"}, "Back in the list."), "button"));
    actions.append(button("Save notes", () => setLead(lead, {notes: notes.value}, "Notes saved."), "button ghost"));
    root.append(actions);
    showDialog(lead.title.slice(0, 90), root);
    dialog.dataset.leadId = lead.id;
  }
  // Phase 2: a proposal written by the owner's own model from facts only; the owner edits and sends it.
  let freelanceState = null;  // the page's last state; a single lead is fetched on its own, not the whole list
  async function refreshLead(id) { return [await api(`/api/freelance/leads/${encodeURIComponent(id)}`), freelanceState || await api("/api/freelance")]; }
  function watchDraft(lead) {
    setTimeout(async () => {
      if (!dialog.open || dialog.dataset.leadId !== lead.id) return;
      try { const [fresh, state] = await refreshLead(lead.id); if (!fresh) return; if (fresh.proposal?.status === "drafting") watchDraft(fresh); else leadDialog(fresh, state); } catch { watchDraft(lead); }
    }, 4000);
  }
  function proposalSection(lead, state) {
    const proposal = lead.proposal || {}, box = el("div", "proposal-box");
    const start = () => act("Writing your proposal with your AI model (about a minute)…", () => mutate("/api/freelance/draft", {id: lead.id})).then(async result => { if (!result) return; const [fresh, fresher] = await refreshLead(lead.id); leadDialog(fresh, fresher); });
    if (!proposal.status) {
      append(box, el("strong", "", "Proposal"), state.agents_on ? el("p", "row-meta", "Cerebra writes a tailored proposal and price from your own details, services and finished work. You edit it and send it.") : hint("Switch AI agents on in Settings to have proposals written for you.", true),
        state.agents_on ? button("✍ Write a proposal", start, "button primary") : null);
      return box;
    }
    if (proposal.status === "drafting") { watchDraft(lead); return append(box, el("strong", "", "Proposal"), el("p", "row-meta", `Writing it with ${proposal.model || "your AI model"}… this usually takes about a minute.`)); }
    if (proposal.status === "failed") return append(box, el("strong", "", "Proposal"), hint(`It couldn't be written: ${proposal.error || "unknown problem"}`, true), button("Try again", start, "button"));
    const text = textarea("", proposal.text || ""), price = input("Price", proposal.price || "", "number"), days = input("Days", proposal.days || "", "number");
    text.rows = 10; price.min = 0; price.step = "any"; days.min = 1;
    const save = () => mutate("/api/freelance/proposal", {id: lead.id, text: text.value, price: Number(price.value || 0), days: Number(days.value || 0)}, "PUT");
    const sending = el("div", "actions");
    if (proposal.sent_at) sending.append(hint(`Sent ${relative(proposal.sent_at)} via ${proposal.sent_via}.`));
    else if (lead.source === "freelancer") {
      sending.append(state.freelancer_account?.connected
        ? button("Send bid on Freelancer.com", async () => { if (!await act("", save)) return; showDialog("Send this bid?", append(el("div"),
            el("p", "", `Sends your proposal as a bid of ${lead.currency || "USD"} ${Number(price.value || 0).toLocaleString()} with delivery in ${days.value} day(s) on “${lead.title}”, from your Freelancer.com account ${state.freelancer_account.username}.`),
            actionsRow(button("Back", () => leadDialog(lead, state), "button ghost"), button("Send bid", async () => { const result = await act(outcome => outcome.message, () => mutate("/api/freelance/bid", {id: lead.id, confirmed: true})); if (result) { closeDialog(); render(); } }, "button primary")))); }, "button primary")
        : hint("Connect your Freelancer.com account (Freelance page › Freelancer.com account) to send bids from here.", true));
    } else {
      sending.append(button("Copy proposal", async () => { if (!await act("", save)) return; navigator.clipboard.writeText(text.value).then(() => toast("Saved and copied. Paste it on the job page and send it."), () => toast("Saved. Couldn't copy; select the text and copy it.", true)); }, "button primary"),
        hint(`${lead.source_label} doesn't allow automated bids: copy it, open the job page, paste and send it there, then press “I applied”.`));
    }
    append(box, el("strong", "", "Proposal"), proposal.fit ? hint(proposal.fit) : null, field("Text", text), append(el("div", "form-grid"), field(`Price (${proposal.currency || lead.currency || "USD"})`, price), field("Delivery (days)", days)),
      append(el("div", "actions"), button("Save edits", () => act("Proposal saved.", save), "button"), button("Write it again", start, "button ghost")), sending);
    return box;
  }
  function freelancerAccount(state) {
    const account = state.freelancer_account || {}, root = el("div");
    if (account.connected) return append(root, kv([["Account", account.username]]), hint("Bids go out only when you press Send on a proposal."),
      append(el("div", "actions"), button("Check", () => act(result => result.message, () => mutate("/api/freelance/freelancer-account/check")).then(() => render()), "button small"),
        button("Disconnect", () => act(result => result.message, () => api("/api/freelance/freelancer-account", {method: "DELETE"})).then(() => render()), "button small ghost")));
    const form = el("form"), token = input("OAuth access token", "", "password"), save = submitButton("Connect"); token.autocomplete = "off";
    append(form, hint("To bid from Cerebra: create an app at accounts.freelancer.com › Settings › Developer, give it the bidding scope, and paste its OAuth access token. Stored encrypted on this computer."), field("Access token", token), actionsRow(save));
    wireForm(form, save, async () => { const result = await mutate("/api/freelance/freelancer-account", {token: token.value.trim()}, "PUT"); toast(result.message); render(); });
    return append(root, form);
  }
  // Phase 4: profiles, gigs and case studies, written from the owner's real details; the owner copies them in.
  // Phase 5: what works. Wins and money by source, service and way of applying, from the owner's own records.
  function insightsPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/freelance/insights").then(result => {
      const earned = value => Object.entries(value || {}).map(([currency, amount]) => `${currency} ${Number(amount).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`).join(" + ") || "—";
      const totals = result.totals || {}, paid = Object.keys(totals.earned || {}).length > 0;
      const won = row => row.applied ? `${row.won} (${row.win_rate}%)` : String(row.won);
      const grid = (first, list, found = true) => {
        const shown = array(list).filter(row => found ? row.found || row.applied : row.applied);
        return table([first, ...(found ? ["Found"] : []), "Applied", "Won", ...(paid ? ["Earned"] : [])],
          shown.map(row => [row.label || row.name, ...(found ? [row.found] : []), row.applied, won(row), ...(paid ? [earned(row.earned)] : [])]));
      };
      const ways = array(result.ways).map(row => ({...row, label: row.name === "automatic" ? "By Cerebra" : "By you"}));
      root.replaceChildren(
        hint(totals.applied ? `${totals.applied} application(s), ${totals.awarded || 0} chosen by the client, ${totals.won || 0} won, ${paid ? `${earned(totals.earned)} earned from won jobs` : "nothing earned from won jobs yet"}.` : `${totals.found || 0} job(s) found so far and none applied to yet. Mark the jobs you apply to (or switch on Apply automatically) and this shows where you win.`),
        totals.applied ? append(el("ul", "tips"), ...array(result.advice).map(tip => el("li", "", tip))) : null,
        append(el("div"), el("h4", "", "By where the job came from"), grid("Source", result.sources)),
        append(el("div"), el("h4", "", "By the kind of work"), grid("Service", result.services)),
        ways.some(row => row.applied) ? append(el("div"), el("h4", "", "Automatic bids and your own"), grid("Sent", ways, false)) : null,
        hint("Won shows the share of applications won. Earnings are what won jobs' invoices and recorded payments brought in. Mark leads as applied, won or lost so this stays true."));
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  // Phase 4b: applying by itself on Freelancer.com, and noticing what was won.
  function autoApplyPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/freelance/auto").then(state => {
      const rules = state.settings, form = el("form"), save = submitButton("Save");
      const on = check("Bid by myself on Freelancer.com", rules.enabled), accept = check("Also accept awards by myself (a commitment to the client's job at your bid)", rules.accept_awards);
      const score = input("40", rules.min_score, "number"), perDay = input("15", rules.per_day, "number"); score.min = 1; score.max = 100; perDay.min = 1; perDay.max = 50;
      append(form, on.wrap, append(el("div", "form-grid"), field("Lowest score to bid on", score), field("Bids per day at most", perDay)), accept.wrap, actionsRow(save));
      wireForm(form, save, async () => { await mutate("/api/freelance/auto", {enabled: on.control.checked, accept_awards: accept.control.checked, min_score: Number(score.value || 40), per_day: Number(perDay.value || 15)}, "PUT"); toast(on.control.checked ? "Saved. Cerebra bids on new matches every 10 minutes." : "Saved. Automatic bidding is off."); render(); });
      const connected = state.freelancer_account?.connected, gmail = state.gmail || {};
      root.replaceChildren(form,
        !connected ? hint("Connect your Freelancer.com account (panel above) so Cerebra can bid.", true) : null,
        hint(`Bidding: ${state.applier?.message || "waiting for the next round"}`),
        hint(gmail.connected || gmail.authorized ? "Gmail (read-only): Cerebra reads messages from Upwork, Fiverr and Freelancer.com to see what you've won." : "Connect Gmail (read-only) in Business connections, so Cerebra can see hires, offers and orders from Upwork and Fiverr in your email.", !(gmail.connected || gmail.authorized)),
        append(el("div", "actions"), button("Run a round now", () => act(result => `Done: ${result.bids?.sent || 0} bid(s) sent, ${Number(result.wins?.freelancer || 0) + Number(result.wins?.email || 0)} win(s) found, ${result.work || 0} work step(s) moved on.`, () => mutate("/api/freelance/auto/run", {}, "POST", 900000)).then(() => render()), "button small"), link("Connect Gmail →", "connections")),
        hint("Only Freelancer.com is bid on by itself: Upwork and Fiverr ban automated proposals and suspend accounts that use them, so for them Cerebra writes the proposal and you paste it. When a job is won (on Freelancer.com, or in your email), Cerebra creates the work and builds it by itself; you review it before anything is delivered."));
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  function pitchesPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/pitches").then(state => {
      root.replaceChildren();
      if (!state.agents_on) root.append(hint("Switch AI agents on in Settings to have these written for you.", true));
      Object.entries(state.kinds).forEach(([kind, piece]) => root.append(pitchRow(kind, piece.label, piece, state)));
      const finished = array(state.finished);
      root.append(el("strong", "", "Portfolio from your finished work"));
      if (!finished.length) root.append(el("p", "row-meta", "Case studies appear here for tasks you finish with Cerebra."));
      finished.slice(0, 6).forEach(task => root.append(pitchRow("case", `${task.project}: ${task.description.slice(0, 60)}`, state.cases[task.id] || {}, state, task.id)));
      root.append(hint("Upwork, Fiverr and LinkedIn don't let apps edit profiles, so copy each piece into the site yourself. Everything is written from your About you, services and finished work only."));
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  function pitchRow(kind, label, piece, state, taskId) {
    const row = append(el("div", "source-row"), el("span", "", label));
    const start = () => act("Writing it with your AI model (about a minute)…", () => mutate("/api/pitches/write", {kind, task_id: taskId})).then(result => { if (result) setTimeout(() => render(), 1500); });
    const status = piece.status === "writing" ? el("span", "row-meta", "writing…") : piece.status === "failed" ? el("span", "row-meta", `couldn't write it: ${piece.error}`) : null;
    const actions = append(el("span", "actions"), status,
      piece.status === "ready" ? button("Open", () => pitchDialog(kind, label, piece, taskId), "button small primary") : null,
      state.agents_on && piece.status !== "writing" ? button(piece.status === "ready" ? "Rewrite" : kind === "case" ? "Case study" : "Write", start, "button small") : null);
    row.append(actions);
    return row;
  }
  function pitchDialog(kind, label, piece, taskId) {
    const root = el("div"), data = piece.data || {}, key = kind === "case" ? `case:${taskId}` : kind, inputs = {};
    const textField = (name, value, limit) => {
      const control = String(value || "").length > 90 || name === "solution" || name === "overview" || name === "description" || name === "summary" || name === "about" ? textarea("", value || "") : input("", value || "");
      if (control.tagName === "TEXTAREA") control.rows = 8;
      inputs[name] = control;
      const counter = el("small", "row-meta", limit ? `${String(value || "").length} / ${limit}` : "");
      control.addEventListener("input", () => { counter.textContent = limit ? `${control.value.length} / ${limit}` : ""; counter.style.color = limit && control.value.length > limit ? "var(--red)" : ""; });
      return field(name[0].toUpperCase() + name.slice(1), append(el("div"), control, append(el("div", "actions"), counter, button("Copy", () => navigator.clipboard.writeText(control.value).then(() => toast("Copied."), () => toast("Couldn't copy; select the text.", true)), "button small ghost"))));
    };
    const limits = {upwork: {title: 70, overview: 5000}, fiverr: {title: 80, description: 1200}, freelancer: {headline: 50, summary: 1600}, linkedin: {headline: 220, about: 2600}}[kind] || {};
    Object.entries(data).forEach(([name, value]) => {
      if (typeof value === "string") root.append(textField(name, value, limits[name] || (name === "post" ? 280 : 0)));
    });
    if (array(data.packages).length) root.append(field("Packages", table(["Package", "Price", "Days", "Includes"], data.packages.map(item => [item.name, String(item.price), String(item.days), item.includes]))));
    if (array(data.tags).length) root.append(field("Tags", el("code", "", data.tags.join(", "))));
    if (array(data.faq).length) root.append(field("FAQ", append(el("div"), ...data.faq.map(item => append(el("p"), el("strong", "", item.q), el("br"), document.createTextNode(item.a))))));
    if (array(data.skills).length) root.append(field("Skills", el("code", "", data.skills.join(", "))));
    const actions = append(el("div", "actions"), button("Save edits", () => act("Saved.", () => mutate("/api/pitches/piece", {key, data: Object.fromEntries(Object.entries(inputs).map(([name, control]) => [name, control.value]))}, "PUT")), "button"),
      kind === "case" && data.post ? button("Make a post from this", () => act("Added to Marketing as a draft. Approve it there to post it.", () => mutate("/api/pitches/case-post", {task_id: taskId})), "button primary") : null);
    root.append(actions, hint(piece.edited ? "Edited by you." : `Written by ${piece.model || "your AI model"} ${piece.written_at ? relative(piece.written_at) : ""}. Read it before you use it.`));
    showDialog(label, root);
  }
  function pasteLeadDialog(state) {
    const form = el("form"), save = submitButton("Add and score it");
    const platform = select([["Upwork", "Upwork"], ["Fiverr", "Fiverr"], ["LinkedIn", "LinkedIn"], ["Facebook", "Facebook group"], ["WhatsApp", "WhatsApp or referral"], ["Other", "Somewhere else"]], "Upwork");
    const title = input("The job's title"), link = input("https://www.upwork.com/jobs/… (optional)"), budget = input("Budget (optional)", "", "number"), description = textarea("Paste the full job description");
    const hourly = check("The budget is per hour"); title.required = true; description.required = true; description.rows = 10; budget.min = 0; budget.step = "any";
    append(form, append(el("div", "form-grid"), field("Where it's from", platform), field("Budget", budget)), hourly.wrap, field("Title", title), field("Job link", link), field("Description", description), actionsRow(button("Cancel", closeDialog, "button ghost"), save));
    wireForm(form, save, async () => {
      const lead = await mutate("/api/freelance/leads", {platform: platform.value, title: title.value, url: link.value.trim(), budget: Number(budget.value || 0), hourly: hourly.control.checked, description: description.value});
      closeDialog(); toast(`Scored ${lead.score}/100.`); render(); leadDialog(lead, state);
    });
    showDialog("Paste a job", form);
  }
  function freelanceProfileForm(state) {
    const settings = state.profile, form = el("form"), save = submitButton("Save and re-score");
    const services = Object.entries(state.services).map(([key, label]) => { const item = check(label, array(settings.services).includes(key)); item.key = key; return item; });
    const words = textarea("Extra skills or tools, one per line (e.g. Supabase, Tailwind)", array(settings.keywords).join("\n")), exclude = textarea("Words that rule a job out, one per line (e.g. unpaid, crypto)", array(settings.exclude).join("\n"));
    const minimum = input("0", settings.min_budget || 0, "number"); minimum.min = 0; minimum.step = "any";
    const skills = input("Cybersecurity, AI integration, Web development, API integration", array(settings.skills).join(", "));
    append(form, field("Your skills", skills, "How you describe yourself, separated by commas. Every proposal, email and profile leads with these, written as you."),
      append(el("div", "check-list"), ...services.map(item => item.wrap)), field("Extra skills", words), field("Rule out jobs that mention", exclude), field("Smallest budget you take (USD)", minimum, "Jobs below it sink to the bottom."), actionsRow(save));
    wireForm(form, save, async () => {
      const lines = value => value.split("\n").map(item => item.trim()).filter(Boolean);
      await mutate("/api/freelance/profile", {skills: skills.value.split(",").map(item => item.trim()).filter(Boolean), services: services.filter(item => item.control.checked).map(item => item.key), keywords: lines(words.value), exclude: lines(exclude.value), min_budget: Number(minimum.value || 0)}, "PUT");
      toast("Saved. Every open lead was scored again."); render();
    });
    return form;
  }
  function sourcesList(state) {
    const root = el("div");
    array(state.sources).forEach(source => {
      const toggle = check(source.label, source.enabled), last = source.last || {};
      toggle.control.addEventListener("change", () => act(toggle.control.checked ? `${source.label} switched on.` : `${source.label} switched off.`, () => mutate("/api/freelance/profile", {sources: {[source.id]: toggle.control.checked}}, "PUT")));
      append(root, append(el("div", "source-row"), toggle.wrap, el("span", "row-meta", last.at ? (last.error ? `couldn't read it ${relative(last.at)}` : `${last.added} new ${relative(last.at)}`) : `checked every ${source.every_minutes >= 60 ? `${source.every_minutes / 60} h` : `${source.every_minutes} min`}`)));
    });
    root.append(hint("Upwork, Fiverr, LinkedIn: paste their jobs with “+ Paste a job”. Upwork and Fiverr ban automated bidding, so Cerebra never applies on them; it finds, scores and (next) drafts, and you send."));
    return root;
  }
  // ---------- money: quotes, invoices, earnings ----------
  const DOC_STYLE = {draft: "muted", sent: "blue", accepted: "green", declined: "red", paid: "green", void: "muted"};
  function cash(amount, currency) { return `${currency} ${Number(amount || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`; }
  function moneyView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading your money…")));
    (async () => {
      let state; try { state = await api("/api/money"); } catch (issue) { root.replaceChildren(body(empty("Money unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const main = state.summary.currency, figures = state.summary.by_currency[main] || {};
      const stats = el("div", "grid stats");
      [["Earned this month", cash(figures.earned_month, main), `${cash(figures.earned_year, main)} this year${figures.spent_month ? ` · ${cash(figures.spent_month, main)} spent this month` : ""}`, "green"],
       ["Owed to you", cash(figures.owed, main), figures.overdue_count ? `${figures.overdue_count} overdue · ${cash(figures.overdue, main)}` : "nothing overdue", figures.overdue_count ? "red" : "amber"],
       ["Quotes out", cash(figures.pipeline, main), "waiting for the client's yes", "cyan"],
       ["Won, not invoiced", cash(figures.won_unbilled, main), "accepted quotes to bill", ""]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value money-value", value), el("div", "stat-note", note))));
      const others = Object.entries(state.summary.by_currency).filter(([currency]) => currency !== main);
      const left = el("div"), side = el("div");
      const docs = array(state.documents), rows = docs.map(doc => [el("strong", "nowrap", doc.number || "Draft"), doc.client, doc.kind === "quote" ? "Quote" : "Invoice", cash(doc.total, doc.currency),
        doc.kind === "invoice" && doc.status === "sent" ? cash(doc.balance, doc.currency) : "—", doc.overdue ? badge("overdue", "red") : badge(doc.status, DOC_STYLE[doc.status]), doc.due_date || "—",
        button("Open", () => moneyDocDialog(doc, state), "button small")]);
      const fromJob = select([["", "Quote from a business job…"], ...array(state.jobs).map(job => [job.id, `${job.title}${job.client ? ` · ${job.client}` : ""}`])]);
      fromJob.addEventListener("change", async () => { if (!fromJob.value) return; const doc = await act("Quote drafted from the job's agreed scope. Check the price, then issue it.", () => mutate(`/api/money/documents/from-job/${encodeURIComponent(fromJob.value)}`)); if (doc) { render(); moneyDocDialog(doc, state); } });
      const tools = append(el("div", "actions"), button("+ New quote", () => moneyDocDialog({kind: "quote", items: [], currency: main, status: "draft"}, state), "button primary"),
        button("+ New invoice", () => moneyDocDialog({kind: "invoice", items: [], currency: main, status: "draft"}, state), "button"), state.jobs.length ? fromJob : null);
      const late = docs.filter(doc => doc.overdue);
      if (late.length) left.append(panel("Needs chasing", table(["Invoice", "Client", "Still owed", "Due", "Reminders", ""], late.map(doc => [el("strong", "nowrap", doc.number), doc.client, cash(doc.balance, doc.currency), doc.due_date,
        String(array(doc.provider?.reminders).length), button("Remind", () => reminderDialog(doc, state), "button small primary")])), null, late.length));
      left.append(panel("Quotes & invoices", append(el("div"), body(tools), docs.length ? table(["Number", "Client", "Kind", "Total", "Still owed", "Status", "Due / valid until", ""], rows)
        : body(empty("No quotes or invoices yet", "Quote a client, get their yes, invoice a deposit and the rest, and record what they pay. Cerebra numbers and lays out each one; you send it.", null, "$"))), null, docs.length));
      left.append(plansPanel(state), productsPanel(state));
      if (others.length) left.append(panel("Other currencies", table(["Currency", "Earned this month", "Owed", "Quotes out"], others.map(([currency, values]) => [currency, cash(values.earned_month, currency), cash(values.owed, currency), cash(values.pipeline, currency)]))));
      side.append(panel("Get paid with Stripe", body(stripePanel(state.stripe))), panel("Marketplace sales", body(channelsPanel(state.channels))), panel("Your business", body(moneySettingsForm(state.settings))),
        panel("Getting paid", body(hint("Each invoice can carry a payment link, shown on it as “Pay online”: a Stripe link Cerebra creates, or one you paste (PayPal, Paystack…). Record other payments you receive (M-Pesa, bank) from the invoice. Payments on a business job's invoice also go into that job's money record."),
          hint(state.summary.note), exportRow(state))));
      root.replaceChildren(...[startEarning(state), stats, append(el("div", "grid two"), left, side)].filter(Boolean));
    })();
    return root;
  }
  const EVERY_WORDS = {month: "Every month", quarter: "Every 3 months", year: "Every year"};
  // The first steps to earning with Cerebra, ticked off from the owner's own records; hidden once all are done.
  function startEarning(state) {
    const docs = array(state.documents), settings = state.settings || {};
    const goTo = (title, selector = "input, textarea") => () => { const section = [...document.querySelectorAll(".panel")].find(node => node.querySelector("h2")?.textContent.startsWith(title));
      if (!section) return; section.scrollIntoView({behavior: "smooth", block: "start"}); setTimeout(() => section.querySelector(selector)?.focus({preventScroll: true}), 400); };
    const steps = [
      [!!settings.business_name, "Add your business details", "Your name, email and how clients pay you appear on every quote and invoice.", goTo("Your business")],
      [array(settings.services).length > 0, "Save your services and prices", "So each quote takes a minute: pick a service and its line fills itself in.", goTo("Your business", "textarea[placeholder^='One per line']")],
      [!!state.stripe?.connected, "Connect Stripe", "Clients pay by card from a link on the invoice; Cerebra marks it paid.", goTo("Get paid with Stripe")],
      [docs.some(doc => doc.kind === "quote" && doc.status !== "draft"), "Send your first quote", "Quote a client: when they say yes, Cerebra drafts the deposit invoice.", () => moneyDocDialog({kind: "quote", items: [], currency: state.summary.currency, status: "draft"}, state)],
      [array(state.plans).length > 0, "Offer a monthly care plan", "Steady income: hosting, updates and fixes for a client whose site you built.", () => planDialog({every: "month", currency: state.summary.currency, items: [], active: true}, state)],
      [array(state.products).length > 0, "Sell something you already made", "Package a finished project as a template and sell it with a Stripe link.", () => productDialog({price: "", currency: state.summary.currency, status: "draft"}, state)]];
    const done = steps.filter(([finished]) => finished).length;
    if (done === steps.length) return null;
    const list = el("div", "start-steps");
    steps.forEach(([finished, title, detail, start]) => list.append(append(el("div", `start-step${finished ? " done" : ""}`), el("span", "start-mark", finished ? "✓" : "○"),
      append(el("div"), el("strong", "", title), el("p", "", detail)), !finished && start ? button("Start", start, "button small") : null)));
    return panel(`Start earning · ${done} of ${steps.length} done`, body(list));
  }
  function exportRow(state) {
    const thisYear = Number((state.summary.today || new Date().toISOString()).slice(0, 4)), year = select([[String(thisYear), String(thisYear)], [String(thisYear - 1), String(thisYear - 1)]]);
    return append(el("div", "actions"), year, button("Export the year (CSV) for my accountant", () => act(result => `Saved ${result.rows} row(s) to ${result.path}. It opens in Excel.`,
      () => mutate("/api/money/export", {year: Number(year.value)})), "button small"));
  }
  function plansPanel(state) {
    const items = array(state.plans), main = state.summary.currency;
    const monthly = items.filter(plan => plan.active && plan.currency === main).reduce((sum, plan) => sum + plan.monthly, 0);
    const rows = items.map(plan => [el("strong", "", plan.client), cash(plan.total, plan.currency), EVERY_WORDS[plan.every] || plan.every, plan.active ? plan.next_date : "paused",
      plan.auto_issue ? "issued for you" : "drafted for you", button("Open", () => planDialog(plan, state), "button small")]);
    return panel("Recurring plans", append(el("div"), body(append(el("div", "actions"), button("+ New plan", () => planDialog({every: "month", currency: main, items: [], active: true}, state), "button primary"),
        items.length ? el("span", "row-meta", `${cash(monthly, main)} a month in active plans`) : null),
      items.length ? null : hint("Bill clients on a schedule: a website care plan, hosting and updates, a monthly retainer. On each date Cerebra drafts the invoice (or issues it, if you choose); you send it.")),
      items.length ? table(["Client", "Each time", "How often", "Next invoice", "Invoice", ""], rows) : null), null, items.length);
  }
  function planDialog(plan, state) {
    const form = el("form"), save = submitButton(plan.id ? "Save plan" : "Start plan");
    const client = input("Client or company name", plan.client || ""), email = input("client@example.com (optional)", plan.client_email || "", "email");
    const every = select(Object.entries(EVERY_WORDS), plan.every || "month"), start = input("", plan.next_date || new Date().toISOString().slice(0, 10), "date");
    const currency = input("USD", plan.currency || "USD"), notes = textarea("Notes printed on each invoice (optional)", plan.notes || "");
    const auto = check("Issue each invoice automatically (numbered and dated; you still send it)", plan.auto_issue), active = check("Active", plan.active !== false);
    const lines = el("div", "money-lines");
    const addLine = (item = {description: "", quantity: 1, unit_price: ""}) => {
      const row = el("div", "money-line"), text = input("What you do each period", item.description), qty = input("1", item.quantity, "number"), price = input("Price", item.unit_price, "number");
      qty.min = "0.01"; qty.step = "any"; price.min = "0"; price.step = "any";
      append(row, text, qty, price, button("×", () => row.remove(), "button small ghost")); row._read = () => ({description: text.value.trim(), quantity: Number(qty.value || 0), unit_price: Number(price.value || 0)}); lines.append(row);
    };
    (array(plan.items).length ? plan.items : [undefined]).forEach(item => addLine(item));
    append(form, append(el("div", "form-grid"), field("Client", client), field("Client email", email)), append(el("div", "form-grid"), field("How often", every), field(plan.id ? "Next invoice" : "First invoice", start, "Days after the 28th become the 28th, so every month has one.")),
      field("Lines", append(el("div"), lines, append(el("div", "actions"), button("+ Add a line", () => addLine(), "button small ghost"),
        servicePicker(state, item => { [...lines.children].filter(row => { const line = row._read(); return !line.description && !line.unit_price; }).forEach(row => row.remove()); addLine(item); })))),
      field("Currency", currency), field("Notes", notes), auto.wrap, plan.id ? active.wrap : null,
      array(plan.made).length ? hint(`Invoices made so far: ${plan.made.length} (last for ${plan.made[plan.made.length - 1].date}).`) : null,
      actionsRow(plan.id ? button("Delete plan", () => act("Plan deleted. Its invoices stay.", () => api(`/api/money/plans/${plan.id}`, {method: "DELETE"})).then(result => { if (result) { closeDialog(); render(); } }), "button ghost") : null,
        button("Cancel", closeDialog, "button ghost"), save));
    wireForm(form, save, async () => {
      const payload = {client: client.value, client_email: email.value.trim(), every: every.value, next_date: start.value, currency: currency.value.trim().toUpperCase(), notes: notes.value,
        auto_issue: auto.control.checked, active: plan.id ? active.control.checked : true, items: [...lines.children].map(row => row._read()).filter(item => item.description || item.unit_price)};
      plan.id ? await mutate(`/api/money/plans/${plan.id}`, payload, "PATCH") : await mutate("/api/money/plans", payload);
      toast(plan.id ? "Plan saved." : "Plan started. Its invoices appear under Quotes & invoices on each date."); closeDialog(); render();
    });
    showDialog(plan.id ? `Recurring plan · ${plan.client}` : "New recurring plan", form);
  }
  function productsPanel(state) {
    const items = array(state.products);
    const rows = items.map(item => [el("strong", "", item.name), cash(item.price, item.currency), String(item.sold), cash(item.revenue, item.currency),
      badge(item.selling ? "selling" : item.status, item.selling ? "green" : item.status === "paused" ? "amber" : "muted"), button("Open", () => productDialog(item, state), "button small")]);
    return panel("Products you sell", append(el("div"), body(append(el("div", "actions"), button("+ New product", () => productDialog({price: "", currency: state.summary.currency, status: "draft"}, state), "button primary")),
      items.length ? null : hint("Sell your services (a website deposit, a support hour: no download link needed) or templates, design packs and guides made from your finished work. Cerebra packages the files (never Git history, installed packages or settings files); you upload the ZIP to your Google Drive, Dropbox or OneDrive and paste its share link; Stripe sells it and shows buyers that link right after they pay.")),
      items.length ? table(["Product", "Price", "Sold", "Revenue", "Status", ""], rows) : null, items.some(item => item.selling) ? body(hint("Put these on your website with Buy buttons: open Projects, choose your site's project, then “Get paid…” › “Show my services with Buy buttons”.")) : null), null, items.length);
  }
  function productDialog(item, state) {
    const root = el("div"), reopen = async (promise, message) => { const result = await act(message, () => promise); if (!result) return; closeDialog(); render(); const fresh = await api("/api/money"); const again = fresh.products.find(entry => entry.id === item.id); if (again) productDialog(again, fresh); };
    const live = item.selling, form = el("form"), save = submitButton(item.id ? "Save" : "Create product");
    const name = input("e.g. Bakery website template", item.name || ""), description = textarea("What buyers get, in a sentence or two", item.description || "");
    const price = input("29", item.price ?? "", "number"), currency = input("USD", item.currency || "USD"), download = input("https://drive.google.com/… share link", item.download_url || "");
    price.min = "0.5"; price.step = "any"; [price, currency, download].forEach(control => { control.disabled = live; });
    append(form, field("Name", name), field("Description", description), append(el("div", "form-grid"), field("Price", price), field("Currency", currency)),
      field("Download link", download, live ? "Pause selling to change the price or download link." : "Selling files: upload the package (below) to your own cloud storage, set sharing to “anyone with the link”, and paste the link; buyers see it right after paying. Selling a service (a website deposit, an hour of support): leave it empty; Stripe asks for the buyer's phone and tells them you'll be in touch."),
      actionsRow(button("Close", closeDialog, "button ghost"), save));
    wireForm(form, save, async () => {
      const payload = {name: name.value, description: description.value, ...(live ? {} : {price: Number(price.value || 0), currency: currency.value.trim().toUpperCase(), download_url: download.value.trim()})};
      const saved = item.id ? await mutate(`/api/money/products/${item.id}`, payload, "PATCH") : await mutate("/api/money/products", payload);
      toast("Product saved."); closeDialog(); render(); productDialog(saved, state);
    });
    root.append(form);
    if (item.id) {
      const source = select([["", "Package files from…"], ...array(state.sources).map(entry => [`${entry.kind}:${entry.id}`, entry.label])]);
      source.addEventListener("change", () => { if (!source.value) return; const [kind, id] = source.value.split(/:(.*)/s); reopen(mutate(`/api/money/products/${item.id}/package`, {kind, id}, "POST", 300000), "Packaged. The folder with the ZIP is open: upload it to your cloud storage and paste the share link above."); });
      const pack = item.package || {};
      root.append(panel("Files", body(pack.zip ? kv([["Package", pack.zip], ["Files", `${pack.files} (${Math.round((pack.bytes || 0) / 1024)} KB)`], ["Made", date(pack.at)]]) : hint("No package yet. Choose finished work to package; settings files, Git history and installed packages are always left out."), source)));
      const actions = el("div", "actions");
      if (!state.stripe?.connected) actions.append(hint("Connect Stripe on the Money page to sell this product with a payment link.", true));
      else if (!item.link || !live) actions.append(button(item.link ? "Resume selling" : "Start selling with Stripe", () => item.link
        ? reopen(mutate(`/api/money/products/${item.id}/selling`, {active: true}), "On sale again.")
        : showDialog("Start selling on Stripe?", append(el("div"), el("p", "", `Creates a payment link in your Stripe account (${state.stripe.mode} mode) selling “${item.name}” for ${cash(item.price, item.currency)}. After paying, buyers see your download link: ${item.download_url || "(add it first)"}.`),
            actionsRow(button("Cancel", () => productDialog(item, state), "button ghost"), button("Create link", () => reopen(mutate(`/api/money/products/${item.id}/stripe-link`, {confirmed: true}, "POST", 60000), "On sale. Copy the link and share it."), "button primary")))), "button primary"));
      if (item.link) {
        actions.append(append(el("span", "inline-field"), el("code", "nowrap", item.link)), button("Copy link", () => navigator.clipboard.writeText(item.link).then(() => toast("Link copied. Share it on your site, social media or WhatsApp."), () => toast("Couldn't copy; select the link and copy it.", true)), "button small"));
        if (live) actions.append(button("Pause selling", () => reopen(mutate(`/api/money/products/${item.id}/selling`, {active: false}), "Paused. The link no longer accepts payments."), "button"));
      }
      if (!array(item.sales).length && !live) actions.append(button("Delete product", () => reopen(api(`/api/money/products/${item.id}`, {method: "DELETE"}), "Product deleted."), "button ghost"));
      root.append(actions);
      if (array(item.sales).length) root.append(panel("Sales", table(["Date", "Amount", "Buyer", "Phone"], item.sales.map(sale => [sale.date, cash(sale.amount, item.currency), sale.email || "—", sale.phone || "—"])), null, item.sales.length));
    }
    showDialog(item.id ? item.name : "New product", root);
  }
  function channelsPanel(channels) {
    const root = el("div"), names = {etsy: ["Etsy", "orders count as sales (before Etsy's fees; tax left out)"], printify: ["Printify", "orders count as costs"]};
    Object.entries(names).forEach(([source, [label, meaning]]) => {
      const info = channels?.[source] || {}, totals = Object.entries(info.totals || {}).map(([currency, amount]) => cash(amount, currency)).join(", ") || "nothing yet";
      append(root, append(el("div", "action-card"), append(el("div", "row-meta"), badge(info.connected ? "connected" : "not connected", info.connected ? "green" : "muted"), el("strong", "", label)),
        el("p", "", `${info.count || 0} order(s): ${totals}. ${label} ${meaning}.${info.last_import ? ` Last import ${date(info.last_import)}.` : ""}`),
        info.connected ? button(`Import ${label} orders`, () => act(result => result.message, () => mutate(`/api/money/channels/${source}/import`, {}, "POST", 180000)).then(() => render()), "button small")
          : link(`Connect ${label} →`, "connections")));
    });
    const recent = array(channels?.recent);
    if (recent.length) root.append(table(["Date", "From", "Amount"], recent.slice(0, 8).map(entry => [entry.date, entry.note, `${entry.kind === "cost" ? "−" : ""}${cash(entry.amount, entry.currency)}`])));
    root.append(hint("Read-only: Cerebra lists your orders every 6 hours (or when you press Import) and never creates or changes anything in your shops."));
    return root;
  }
  function stripePanel(stripe) {
    const root = el("div");
    if (!stripe?.configured) {
      const form = el("form"), key = input("rk_live_…", "", "password"), save = submitButton("Connect Stripe"); key.autocomplete = "off";
      append(form, hint("Clients pay your invoices by card through your own Stripe account, and Cerebra marks each invoice paid when Stripe reports the payment (it checks every 10 minutes)."),
        field("Restricted API key", key, `In Stripe: Developers › API keys › Create restricted key. Allow only: ${stripe?.permissions || "Products, Prices, Payment Links: Write; Checkout Sessions: Read"}. Stored encrypted on this computer, never shown again.`), actionsRow(save));
      wireForm(form, save, async () => { await mutate("/api/money/stripe", {key: key.value.trim()}, "PUT"); const result = await mutate("/api/money/stripe/check"); toast(result.message); render(); });
      return append(root, form);
    }
    append(root, kv([["Status", stripe.connected ? `Connected · ${stripe.mode} mode` : "Key saved, not checked yet"], ["Checked", stripe.checked_at ? date(stripe.checked_at) : "—"]]),
      stripe.mode === "test" ? hint("Test mode: payment links work with Stripe's test cards only. Use a live restricted key for real clients.", true) : null,
      append(el("div", "actions"), button("Check connection", () => act(result => result.message, () => mutate("/api/money/stripe/check")).then(() => render()), "button small"),
        button("Check for payments now", () => act(result => result.message, () => mutate("/api/money/stripe/sync", {}, "POST", 120000)).then(() => render()), "button small"),
        button("Disconnect", () => act(result => result.message, () => api("/api/money/stripe", {method: "DELETE"})).then(() => render()), "button small ghost")));
    return root;
  }
  async function reminderDialog(doc, state) {
    const text = await act("", () => api(`/api/money/documents/${doc.id}/reminder`)); if (!text) return;
    const subject = input("", text.subject), message = textarea("", text.body); subject.readOnly = true; message.readOnly = true; message.rows = 14;
    const sent = array(text.sent), tone = {friendly: "Friendly", firm: "Firm", final: "Final"}[text.tone] || text.tone;
    const root = append(el("div"), hint(`${tone} reminder${text.days_late > 0 ? ` · ${text.days_late} day(s) overdue` : ""}. Cerebra never sends it: copy it into WhatsApp or email, or open it in your email app, and send it yourself.${state.settings?.business_name ? "" : " Add your business name under Your business so reminders are signed."}${sent.length ? ` Reminders you sent: ${sent.map(item => `${item.date} (${item.tone})`).join(", ")}.` : ""}`),
      field("To", el("div", "", text.to || "No email saved on this invoice: copy the text instead.")), field("Subject", subject), field("Message", message),
      actionsRow(button("Back", () => moneyDocDialog(doc, state), "button ghost"),
        button("Copy text", () => navigator.clipboard.writeText(`${text.subject}\n\n${text.body}`).then(() => toast("Copied. Paste it into your email or WhatsApp."), () => toast("Couldn't copy; select the text and copy it.", true)), "button"),
        text.to ? button("Open in my email app", () => act("Opened in your email app. Check it, then send.", () => mutate(`/api/money/documents/${doc.id}/reminder`, {action: "open"})), "button") : null,
        button("I sent it", () => act("Noted. The next reminder will be firmer if it's still unpaid.", () => mutate(`/api/money/documents/${doc.id}/reminder`, {action: "sent", tone: text.tone})).then(result => { if (result) { closeDialog(); render(); } }), "button primary")));
    showDialog(`Reminder for ${doc.number} · ${doc.client}`, root);
  }
  function servicePicker(state, addLine) {
    const saved = array(state.settings?.services);
    if (!saved.length) return null;
    const picker = select([["", "+ Add a saved service…"], ...saved.map((item, index) => [String(index), `${item.name} · ${cash(item.price, state.summary?.currency || "USD")}`])]);
    picker.addEventListener("change", () => { const item = saved[Number(picker.value)]; if (item) addLine({description: item.name, quantity: 1, unit_price: item.price}); picker.value = ""; });
    return picker;
  }
  function moneySettingsForm(settings) {
    const form = el("form"), save = submitButton("Save");
    const name = input("Your name or business name", settings.business_name), email = input("you@example.com", settings.email, "email"), phone = input("Phone", settings.phone);
    const address = textarea("Address (optional)", settings.address), tax = input("Optional", settings.tax_id), terms = input("14", settings.payment_terms_days, "number"), valid = input("30", settings.quote_valid_days, "number");
    const how = textarea("How clients can pay you: bank details, M-Pesa till or paybill, PayPal…", settings.payment_instructions);
    const services = textarea("One per line, name | price. For example:\n5-page website | 600\nLogo design | 150", array(settings.services).map(item => `${item.name} | ${item.price}`).join("\n"));
    append(form, field("Business name", name), append(el("div", "form-grid"), field("Email", email), field("Phone", phone)), field("Address", address),
      append(el("div", "form-grid"), field("Invoices due after (days)", terms), field("Quotes valid for (days)", valid)), field("Tax ID", tax), field("How to pay you", how, "Printed on every invoice."), field("Your services and prices", services, "Pick them when you write a quote or invoice, so each line fills itself in."), actionsRow(save));
    wireForm(form, save, async () => { await mutate("/api/money/settings", {business_name: name.value, email: email.value.trim(), phone: phone.value, address: address.value, tax_id: tax.value,
      payment_terms_days: Number(terms.value || 0), quote_valid_days: Number(valid.value || 1), payment_instructions: how.value,
      services: services.value.split("\n").map(line => line.trim()).filter(Boolean).map(line => { const at = line.lastIndexOf("|"); return at < 0 ? {name: line, price: 0} : {name: line.slice(0, at).trim(), price: Number(line.slice(at + 1).replace(/[^0-9.]/g, "") || 0)}; })}, "PUT"); toast("Business details saved. They appear on your quotes and invoices."); });
    return form;
  }
  function moneyDocDialog(doc, state) {
    const root = el("div"), draft = doc.status === "draft", word = doc.kind === "quote" ? "quote" : "invoice";
    const reopen = async (promise, message) => { const result = await act(message, () => promise); if (!result) return; closeDialog(); render(); if (result.id) moneyDocDialog(result, state); };
    const top = append(el("div", "detail-top"), badge(doc.kind), doc.overdue ? badge("overdue", "red") : badge(doc.status, DOC_STYLE[doc.status]), doc.number ? el("strong", "", doc.number) : null);
    root.append(top);
    if (draft) {
      const client = input("Client or company name", doc.client), email = input("client@example.com (optional)", doc.client_email, "email"), currency = input("USD", doc.currency || "USD");
      const job = select([["", "No business job"], ...array(state.jobs).map(item => [item.id, item.title])], doc.job_id || "");
      const lines = el("div", "money-lines"), notes = textarea("Notes for the client (optional): what's not included, how changes are handled…", doc.notes || "");
      const link = input("https://buy.stripe.com/… (optional)", doc.payment_url || "");
      const addLine = (item = {description: "", quantity: 1, unit_price: ""}) => {
        const row = el("div", "money-line"), text = input("What you'll do", item.description), qty = input("1", item.quantity, "number"), price = input("Price", item.unit_price, "number");
        qty.min = "0.01"; qty.step = "any"; price.min = "0"; price.step = "any";
        append(row, text, qty, price, button("×", () => row.remove(), "button small ghost")); row._read = () => ({description: text.value.trim(), quantity: Number(qty.value || 0), unit_price: Number(price.value || 0)}); lines.append(row);
      };
      (array(doc.items).length ? doc.items : [undefined]).forEach(item => addLine(item));
      const form = el("form"), save = submitButton(doc.id ? "Save draft" : `Create ${word}`);
      append(form, append(el("div", "form-grid"), field("Client", client), field("Client email", email)), append(el("div", "form-grid"), field("Business job", job), field("Currency", currency)),
        field("Lines", append(el("div"), lines, append(el("div", "actions"), button("+ Add a line", () => addLine(), "button small ghost"), servicePicker(state, item => { [...lines.children].filter(row => { const line = row._read(); return !line.description && !line.unit_price; }).forEach(row => row.remove()); addLine(item); }))), "Description, quantity and price for each piece of work. You set every price."),
        field("Notes", notes), doc.kind === "invoice" ? field("Payment link", link, "Shown on the invoice as “Pay online”.") : null, actionsRow(button("Cancel", closeDialog, "button ghost"), save));
      wireForm(form, save, async () => {
        const payload = {client: client.value, client_email: email.value.trim(), job_id: job.value || null, currency: currency.value.trim().toUpperCase(), notes: notes.value,
          items: [...lines.children].map(row => row._read()).filter(item => item.description || item.unit_price), ...(doc.kind === "invoice" ? {payment_url: link.value.trim()} : {})};
        const saved = doc.id ? await mutate(`/api/money/documents/${doc.id}`, payload, "PATCH") : await mutate("/api/money/documents", {kind: doc.kind, ...payload});
        toast(`Draft ${word} saved.`); closeDialog(); render(); moneyDocDialog(saved, state);
      });
      root.append(form);
    } else {
      root.append(kv([["Client", `${doc.client}${doc.client_email ? ` · ${doc.client_email}` : ""}`], ["Total", cash(doc.total, doc.currency)], ...(doc.kind === "invoice" ? [["Paid", cash(doc.paid, doc.currency)], ["Still owed", cash(doc.balance, doc.currency)]] : []),
        ["Issued", doc.issued_at], [doc.kind === "quote" ? "Valid until" : "Due", doc.due_date], ...(doc.payment_url ? [["Payment link", doc.payment_url]] : [])]));
      if (array(doc.payments).length) root.append(table(["Paid on", "Amount", "How"], doc.payments.map(payment => [payment.date, cash(payment.amount, doc.currency), payment.method || "—"])));
    }
    const actions = el("div", "actions");
    if (doc.id) actions.append(button("Preview", () => { const frame = el("iframe", "money-preview"); frame.setAttribute("sandbox", "allow-same-origin"); frame.setAttribute("referrerpolicy", "no-referrer"); frame.title = "Printable preview"; frame.src = `/api/money/documents/${encodeURIComponent(doc.id)}/print`; showDialog(`${doc.number || "Draft"} · ${doc.client}`, append(el("div"), frame, actionsRow(button("Back", () => moneyDocDialog(doc, state), "button ghost")))); }, "button"),
      button("Save & open to print / PDF", () => act(result => `Saved ${result.path}. Print it or save it as PDF from your browser.`, () => mutate(`/api/money/documents/${doc.id}/save`)), "button"));
    if (draft && doc.id) actions.append(button(`Issue this ${word}`, () => reopen(mutate(`/api/money/documents/${doc.id}/issue`), `${doc.kind === "quote" ? "Quote" : "Invoice"} numbered and dated. Send it to ${doc.client} yourself (Save & open, then email the PDF).`), "button primary"));
    if (doc.kind === "quote" && doc.status === "sent") {
      const deposit = input("50", "50", "number"); deposit.min = 0; deposit.max = 100;
      actions.append(append(el("span", "inline-field"), el("span", "", "Deposit %"), deposit), button("Client accepted → draft the invoice", () => reopen(mutate(`/api/money/documents/${doc.id}/accept`, {deposit_percent: Number(deposit.value || 0)}), "Accepted. The invoice draft is ready."), "button primary"),
        button("Client declined", () => reopen(mutate(`/api/money/documents/${doc.id}/decline`), "Marked declined."), "button"));
    }
    if (doc.kind === "quote" && doc.status === "accepted") actions.append(button("Invoice the rest", () => reopen(mutate(`/api/money/documents/${doc.id}/balance`), "Balance invoice drafted."), "button primary"));
    if (doc.kind === "invoice" && doc.status === "sent" && state.stripe?.connected) {
      const stripeLink = doc.provider?.stripe;
      actions.append(button(stripeLink?.active ? "New Stripe link for the balance" : "Create Stripe payment link", () => showDialog("Create a Stripe payment link?", append(el("div"),
        el("p", "", `Creates a payment link for ${cash(doc.balance, doc.currency)} in your Stripe account (${state.stripe.mode} mode), named “Invoice ${doc.number} · ${doc.client}”. ${doc.client} pays Stripe directly; Cerebra marks this invoice paid when Stripe reports the payment and then switches the link off.`),
        stripeLink?.active ? hint("The current link is switched off, so the old amount can't be paid twice.") : null,
        actionsRow(button("Cancel", () => moneyDocDialog(doc, state), "button ghost"), button("Create link", () => reopen(mutate(`/api/money/documents/${doc.id}/stripe-link`, {confirmed: true}, "POST", 60000).then(() => api("/api/money")).then(fresh => fresh.documents.find(item => item.id === doc.id)), "Payment link added to the invoice as “Pay online”. Send the invoice to your client."), "button primary")))), stripeLink?.active ? "button" : "button primary"));
      if (stripeLink) actions.append(button("Check Stripe for payment", () => reopen(mutate("/api/money/stripe/sync", {document_id: doc.id}, "POST", 60000).then(() => api("/api/money")).then(fresh => fresh.documents.find(item => item.id === doc.id)), "Checked Stripe."), "button"));
    }
    if (doc.kind === "invoice" && doc.status === "sent") actions.append(button(doc.overdue ? "Payment reminder (overdue)" : "Payment reminder", () => reminderDialog(doc, state), doc.overdue ? "button primary" : "button"));
    if (doc.kind === "invoice" && doc.status === "sent") {
      const amount = input("Amount", doc.balance, "number"), method = input("e.g. M-Pesa, bank, Stripe", ""); amount.step = "any";
      actions.append(append(el("span", "inline-field"), el("span", "", "Received"), amount, method), button("Record payment", () => reopen(mutate(`/api/money/documents/${doc.id}/payments`, {amount: Number(amount.value || 0), method: method.value}), "Payment recorded."), "button primary"));
    }
    if (doc.id && !["void", "paid", "accepted", "declined"].includes(doc.status)) actions.append(button(draft ? "Delete draft" : `Void this ${word}`, () => reopen(api(`/api/money/documents/${doc.id}`, {method: "DELETE"}), draft ? "Draft deleted." : "Voided. Its number stays used."), "button ghost"));
    root.append(actions);
    showDialog(doc.id ? `${doc.number || `Draft ${word}`} · ${doc.client}` : `New ${word}`, root);
  }
  // ---------- business studio ----------
  const STAGE_STYLE = {scope: "amber", intake: "muted", planning: "blue", creating: "blue", checking: "blue", waiting: "amber", ready: "green", completed: "green", failed: "red", cancelled: "muted"};
  const KIND_HELP = {service_site: "Service business website with a working quote form (client delivery)", website: "Static website: index.html, styles.css, README.md", listing: "Listing copy: title, description and tags (listing.md)", svg: "Original vector design (design.svg) + README", document: "A written document (deliverable.md)"};
  function businessForm(prefill = {}) {
    const form = el("form"), title = input("e.g. Bakery website for Ama", prefill.title || ""), kind = select(Object.entries(KIND_HELP).map(([key, label]) => [key, label]), prefill.kind || "website");
    const client = input("Client name (optional)", prefill.client || ""), brief = textarea("Paste the client's brief or describe your product idea in full.", prefill.brief || ""), requirements = textarea("Optional. One requirement per line.");
    const sources = textarea("Optional. Full paths of your own files to give the AI as reference, one per line (they are copied, never changed).");
    const noAi = check("The client asked for no AI to be used"); brief.required = true; title.required = true;
    append(form, field("Job title", title), field("What to make", kind), field("Client", client), field("Brief", brief), field("Requirements", requirements), field("Your source files", sources), noAi.wrap,
      hint("Cerebra plans it, creates it, checks the files and has a second AI review it. Nothing is merged into the job folder until you approve, and nothing is sent to anyone."),
      !agentsOn() ? hint("AI agents are switched off. The job is saved, but it only runs after you switch agents on in Settings.", true) : null);
    const submit = submitButton("Create job"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      const lines = value => value.split("\n").map(item => item.trim()).filter(Boolean);
      const job = await mutate("/api/business/jobs", {title: title.value.trim(), kind: kind.value, client: client.value.trim(), brief: brief.value.trim(), requirements: lines(requirements.value), sources: lines(sources.value), no_ai_requested: noAi.control.checked}, "POST", 120000);
      closeDialog(); await refresh(true); toast("Job created. Approve its plan to start."); location.hash = `job/${job.id}`;
    });
    showDialog("New business job", form);
  }
  function businessView() {
    const root = el("div"), list = el("div"), side = el("div"), token = renderToken;
    root.append(append(el("div", "grid two"), list, side));
    (async () => {
      let state; try { state = await api("/api/business"); } catch (issue) { list.replaceChildren(body(empty("Business Studio unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const rows = state.jobs.map(job => { const row = el("a", "row"); row.href = `#job/${job.id}`; row.dataset.jobId = job.id; append(row, append(el("div"), el("strong", "", job.title), el("div", "row-meta", `${job.kind_label}${job.client ? ` · ${job.client}` : ""} · ${relative(job.created_at)}`)), badge(job.stage_words, STAGE_STYLE[job.stage])); return row; });
      list.replaceChildren(panel("Jobs", rows.length ? append(el("div", "row-list"), rows) : body(empty("No business jobs yet", "Paste a client brief or describe a product, and Cerebra makes original, reviewed files for you.", button("+ New business job", () => businessForm(), "button primary"), "$")), null, rows.length));
      const folder = el("form"), root_ = input("", state.settings.output_root), save = submitButton("Save");
      const rate = input("25", state.settings.hourly_rate ?? 25, "number"), currency = input("USD", state.settings.currency || "USD"); rate.min = 0; rate.step = "0.5";
      append(folder, field("Save jobs in", root_, "Each job gets its own folder here. Existing files are never overwritten."), append(el("div", "form-grid"), field("Your hourly rate", rate, "Used to value your time in each job's profit."), field("Currency", currency, "3 letters, e.g. USD")), actionsRow(save));
      wireForm(folder, save, async () => { await mutate("/api/business/settings", {output_root: root_.value.trim(), hourly_rate: Number(rate.value), currency: currency.value.trim().toUpperCase()}, "PUT"); toast("Business settings saved."); });
      const markets = append(el("div"), ...state.marketplaces.map(item => append(el("div", "action-card"), append(el("div", "row-meta"), badge(item.state, item.state === "manual" ? "blue" : "muted"), el("strong", "", item.name)), el("p", "", item.detail))));
      side.replaceChildren(panel("Where results are saved", body(folder)), panel("Marketplaces", body(append(el("div"), markets, link("Set up business connections →", "connections")))), panel("Images", body(hint(state.capabilities.image_generation.detail)))) ;
    })();
    return root;
  }
  function previewSection(job) {
    if (!array(job.previews).length) return null;
    const viewer = el("div", "preview-viewer"), tabs = el("div", "preview-tabs");
    const base = `/api/business/jobs/${encodeURIComponent(job.id)}/preview/`;
    async function show(item, tab) {
      tabs.querySelectorAll("button").forEach(node => node.classList.toggle("active", node === tab));
      const url = base + item.path.split("/").map(encodeURIComponent).join("/");
      if (["html", "htm", "svg", "png", "jpg", "jpeg", "gif", "webp"].includes(item.kind)) {
        const frame = el("iframe", "preview-frame"); frame.setAttribute("sandbox", "allow-same-origin"); frame.setAttribute("referrerpolicy", "no-referrer"); frame.title = `Preview of ${item.path}`; frame.src = url;
        viewer.replaceChildren(frame);
      } else {
        try { const response = await fetch(url, {credentials: "same-origin"}); const text = await response.text(); viewer.replaceChildren(item.kind === "md" ? append(el("div", "preview-doc"), markdown(text)) : code(text)); }
        catch (issue) { viewer.replaceChildren(hint(issue.message, true)); }
      }
    }
    job.previews.forEach((item, index) => { const tab = button(item.path, () => show(item, tab), "chip"); tabs.append(tab); if (index === 0) setTimeout(() => show(item, tab), 0); });
    return append(el("section", "report-section"), el("h2", "", "Preview"), el("p", "row-meta", "Shown safely inside Cerebra: scripts and outside links in generated files are blocked."), tabs, viewer);
  }
  // ---------- client delivery workspace ----------
  function deliveryWorkspace(id) {
    const holder = el("div", "delivery"), token = renderToken;
    const jobPath = suffix => `/api/business/jobs/${encodeURIComponent(id)}${suffix}`;
    const money = value => `${Number(value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    async function load() {
      let info; try { info = await api(jobPath("/delivery")); } catch (issue) { holder.replaceChildren(hint(issue.message, true)); return; }
      if (token !== renderToken) return;
      const currency = info.scope.currency || data?.business_currency || "";
      const parts = [];
      // Scope: agreed before any AI work.
      if (info.scoped) {
        const scope = info.scope, approved = !!info.scope_approved_at, form = el("form");
        if (approved) {
          parts.push(panel("Agreed scope", body(append(el("div", "row-meta"), badge("approved", "green"), el("span", "", `on ${date(info.scope_approved_at)}`)),
            kv([["Client", scope.client], ["Pages", scope.pages.join(", ")], ["Services", scope.services.join(", ")], ["Service areas", scope.service_areas.join(", ")], ["Features", scope.features.join(", ")],
              ["Not included", scope.exclusions.join(", ")], ["Revisions included", scope.revisions_included], ["Deadline", scope.deadline || "—"], ["Price", `${currency} ${money(scope.price)}`], ["Form delivery address", scope.form_endpoint], ["Business phone", scope.phone || "—"]]))));
        } else {
          const lines = values => array(values).join("\n"), split = value => value.split("\n").map(item => item.trim()).filter(Boolean);
          const controls = {client: input("Client or business name", scope.client), services: textarea("One per line, e.g. Deep cleaning", lines(scope.services)), service_areas: textarea("One per line, e.g. Austin, TX", lines(scope.service_areas)),
            pages: textarea("", lines(scope.pages)), features: textarea("", lines(scope.features)), exclusions: textarea("", lines(scope.exclusions)), revisions_included: input("2", scope.revisions_included, "number"),
            deadline: input("e.g. 2026-11-15", scope.deadline), price: input("750", scope.price || "", "number"), currency: input("USD", scope.currency), form_endpoint: input("https://formspree.io/f/…", scope.form_endpoint), phone: input("Business phone shown on the site", scope.phone)};
          append(form, hint("Agree this with your client before any AI work starts. Cerebra checks the finished site against it: every service and area must appear and the form must send to this address."),
            append(el("div", "form-grid"), field("Client", controls.client), field("Price", controls.price), field("Currency", controls.currency), field("Deadline", controls.deadline), field("Revisions included", controls.revisions_included), field("Business phone", controls.phone)),
            field("Services", controls.services), field("Service areas", controls.service_areas), field("Pages", controls.pages), field("Features", controls.features), field("Not included", controls.exclusions),
            field("Form delivery address", controls.form_endpoint, "Where quote requests are sent, e.g. a free Formspree form (formspree.io › New form › copy its https address). Without it enquiries would be lost."));
          const save = submitButton("Save scope"), approve = button("Approve scope and start", async () => {
            approve.disabled = true;
            try { await mutate(jobPath("/scope"), payload(), "PUT"); if (await act("Scope approved. The AI team is planning.", () => mutate(jobPath("/scope/approve")))) { await refresh(true); render(); return; } } catch (issue) { toast(issue.message, true); }
            approve.disabled = false;
          }, "button primary");
          const payload = () => ({client: controls.client.value, services: split(controls.services.value), service_areas: split(controls.service_areas.value), pages: split(controls.pages.value), features: split(controls.features.value),
            exclusions: split(controls.exclusions.value), revisions_included: Number(controls.revisions_included.value || 0), deadline: controls.deadline.value, price: Number(controls.price.value || 0), currency: controls.currency.value.toUpperCase(), form_endpoint: controls.form_endpoint.value.trim(), phone: controls.phone.value});
          form.append(actionsRow(save, approve));
          wireForm(form, save, async () => { await mutate(jobPath("/scope"), payload(), "PUT"); toast("Scope saved."); });
          parts.push(panel("Scope — needs your approval", body(form), button("Open Formspree ↗", () => openLink("formspree"), "button small ghost")));
        }
        // Form delivery check.
        if (approved) {
          const last = array(info.delivery_checks).slice(-1)[0], node = el("div");
          append(node, el("p", "", "Send one clearly marked test enquiry through the real form address, then check that it reached the client's inbox."),
            last ? append(el("div", "row-meta"), badge(last.sent ? (last.received === true ? "received" : last.received === false ? "not received" : "sent") : "failed", last.received === true ? "green" : last.sent ? "amber" : "red"), el("span", "", `${date(last.at)} · ${last.detail}`)) : null,
            actionsRow(confirmButton("Send test enquiry", "Click again to send", async () => { await act(value => value.message, () => mutate(jobPath("/test-enquiry"), {confirmed: true})); load(); }, "button"),
              last?.sent ? button("It arrived ✓", async () => { await act("Recorded: the enquiry arrived.", () => mutate(jobPath("/test-enquiry/received"), {received: true})); load(); }, "button small") : null,
              last?.sent ? button("It didn't arrive", async () => { await act("Recorded: not received.", () => mutate(jobPath("/test-enquiry/received"), {received: false})); load(); }, "button small ghost") : null));
          parts.push(panel("Does the form deliver?", body(node)));
        }
      }
      // Money: collected, expenses, time.
      const m = info.money, ledgerForm = el("form", "inline-form"), kind = select([["payment", "Payment received"], ["expense", "Expense"], ["time", "My work time (hours)"], ["support", "Support time (hours)"]]);
      const amount = input("Amount or hours", "", "number"), note = input("Note (optional)"), when = input("", new Date().toISOString().slice(0, 10), "date"); amount.step = "0.01"; amount.min = 0;
      const addLedger = submitButton("Add"); append(ledgerForm, kind, amount, when, note, addLedger);
      wireForm(ledgerForm, addLedger, async () => { const hours = ["time", "support"].includes(kind.value); await mutate(jobPath("/ledger"), {kind: kind.value, [hours ? "hours" : "amount"]: Number(amount.value), date: when.value, note: note.value}); load(); });
      const ledgerRows = m.entries.slice().reverse().map(item => [item.date, nice(item.kind), item.hours ? `${item.hours} h` : `${currency} ${money(item.amount)}`, item.note || "—", button("✕", async () => { await act(null, () => api(jobPath(`/ledger/${item.id}`), {method: "DELETE"})); load(); }, "button small ghost")]);
      parts.push(panel("Money", body(append(el("div", "grid stats"), ...[["Collected", `${currency} ${money(m.collected)}`], ["Expenses", `${currency} ${money(m.expenses)}`], ["Your time", `${m.hours} h × ${money(m.hourly_rate)} = ${money(m.time_cost)}`], ["Profit before tax", `${currency} ${money(m.profit_before_tax)}`]]
        .map(([label, value]) => append(el("div", "stat"), el("div", "stat-label", label), el("div", "stat-value small-value", value)))), hint(m.note), ledgerForm, ledgerRows.length ? table(["Date", "Type", "Amount", "Note", ""], ledgerRows) : el("p", "row-meta", "No entries yet."))));
      // Customer results: enquiries → booked jobs.
      const o = info.outcomes, enquiryForm = el("form", "inline-form"), source = input("Source, e.g. website form"), status = select([["new", "New"], ["quoted", "Quoted"], ["booked", "Booked"], ["lost", "Lost"]]);
      const value = input("Booked value", "", "number"), confirmed = check("Confirmed by the client"), enquiryDate = input("", new Date().toISOString().slice(0, 10), "date"), addEnquiry = submitButton("Add enquiry");
      append(enquiryForm, enquiryDate, source, status, value, confirmed.wrap, addEnquiry);
      wireForm(enquiryForm, addEnquiry, async () => { await mutate(jobPath("/enquiries"), {date: enquiryDate.value, source: source.value || "website form", status: status.value, value: Number(value.value || 0), confirmed: confirmed.control.checked}); load(); });
      const enquiryRows = o.entries.slice().reverse().map(item => { const change = select([["new", "New"], ["quoted", "Quoted"], ["booked", "Booked"], ["lost", "Lost"]], item.status); change.addEventListener("change", async () => { await act("Updated.", () => mutate(jobPath(`/enquiries/${item.id}`), {status: change.value}, "PATCH")); load(); });
        return [item.date, item.source, change, item.value ? `${currency} ${money(item.value)}` : "—", item.confirmed ? badge("client confirmed", "green") : badge("your entry", "muted"), button("✕", async () => { await act(null, () => api(jobPath(`/enquiries/${item.id}`), {method: "DELETE"})); load(); }, "button small ghost")]; });
      parts.push(panel("Customer results", body(append(el("div", "grid stats"), ...[["Enquiries", o.enquiries], ["Booked jobs", o.booked], ["Booked value", `${currency} ${money(o.booked_value)}`], ["Client-confirmed value", `${currency} ${money(o.confirmed_booked_value)}`]]
        .map(([label, value]) => append(el("div", "stat"), el("div", "stat-label", label), el("div", "stat-value small-value", value)))), hint(o.note), enquiryForm, enquiryRows.length ? table(["Date", "Source", "Status", "Value", "Source of figure", ""], enquiryRows) : el("p", "row-meta", "No enquiries recorded yet."))));
      // Change requests against the revisions included.
      const changeForm = el("form"), request = textarea("What did the client ask to change?"), sendChange = submitButton("Create change task");
      const used = info.revisions.length, included = info.revisions_included;
      append(changeForm, request, actionsRow(sendChange));
      wireForm(changeForm, sendChange, async () => { const result = await mutate(jobPath("/changes"), {request: request.value}); toast(result.extra ? "Change task created. This is beyond the included revisions: consider charging for it." : "Change task created."); load(); });
      parts.push(panel(`Change requests (${used} of ${included} included)`, body(used > included ? hint(`${used - included} change(s) beyond the agreed revisions.`, true) : null,
        info.revisions.length ? list(info.revisions.map(item => `${date(item.at)} · ${item.request.slice(0, 100)} · task ${item.task_id.slice(0, 8)} (${nice(item.state)})${item.extra ? " · extra" : ""}`)) : null, changeForm)));
      holder.replaceChildren(...parts);
    }
    load();
    return holder;
  }

  function jobView() {
    const root = el("div"), report = el("div"), token = renderToken, id = param;
    root.append(report, deliveryWorkspace(id));
    async function load() {
      let job; try { job = await api(`/api/business/jobs/${encodeURIComponent(id)}`); } catch (issue) { root.replaceChildren(body(empty("Job not found", issue.message))); return; }
      if (token !== renderToken) return;
      $("#page-title").textContent = job.title;
      const section = (heading, ...nodes) => append(el("section", "report-section"), el("h2", "", heading), ...nodes);
      const actions = el("div", "actions");
      const run = (label, path, payload = {}) => button(label, async event => { event.currentTarget.disabled = true; await act(result => result.opened ? "Opened." : "Done.", () => mutate(`/api/business/jobs/${encodeURIComponent(id)}/${path}`, payload, "POST", 120000)); load(); }, "button");
      if (["ready", "completed"].includes(job.stage)) append(actions, button("Image / marketplace draft…", () => externalForm(job, load), "button"));
      append(actions, run("Open folder", "open", {what: "folder"}), job.files.some(file => file.exists) ? run("Open result", "open", {what: "result"}) : null,
        ["ready", "completed"].includes(job.stage) ? run("Export", "export", {zip: false}) : null, ["ready", "completed"].includes(job.stage) ? run("Export ZIP", "export", {zip: true}) : null,
        job.task_id ? button("Technical details", () => taskDetail(job.task_id), "button ghost") : null,
        !["completed", "cancelled", "failed"].includes(job.stage) ? run("Cancel job", "cancel") : null);
      report.replaceChildren(append(el("div", "report"),
        append(el("div", "report-head"), badge(job.stage_words, STAGE_STYLE[job.stage]), el("span", "row-meta", `${job.kind_label}${job.client ? ` for ${job.client}` : ""}`)), actions,
        section("What you asked for", el("div", "asked", job.asked)),
        section("What passed", job.passed.length ? list(job.passed) : el("p", "", "Nothing has passed yet.")),
        section("What needs attention", job.attention.length ? list(job.attention) : el("p", "", "Nothing. ✓")),
        section("Files made", list(job.files.map(file => `${file.path}: ${file.exists ? `${file.bytes} bytes` : "not made yet"}`))),
        section("Where they are", kv([["Job folder", job.where], ["Exported package", job.export_folder || "not exported yet"], ["ZIP", job.zip || "—"]])),
        section("Next step", el("p", "", job.next_step)), previewSection(job), hint(job.note)));
      const operations = await api(`/api/business/jobs/${encodeURIComponent(id)}/operations`);
      if (token === renderToken && page === "job" && operations.length) report.append(panel("External actions — recorded results", body(list(operations.map(item => `${nice(item.action)}: ${item.status}. ${item.result.message || "Check the provider dashboard before retrying an uncertain action."}${item.result.listing_id ? ` Listing ID: ${item.result.listing_id}` : ""}${item.result.product_id ? ` Product ID: ${item.result.product_id}` : ""}${item.result.image_id ? ` Image ID: ${item.result.image_id}` : ""}${item.result.path ? ` File: ${item.result.path}` : ""}`)))));
      if (!["completed", "cancelled", "failed"].includes(job.stage) && token === renderToken) setTimeout(() => { if (token === renderToken && page === "job") load(); }, 4000);
    }
    load();
    return root;
  }

  function externalForm(job, reload) {
    const form = el("form"), choice = select([["image", "Generate a raster image (paid API)"], ["etsy_draft", "Create an Etsy draft listing"], ["printify_upload", "Upload an image to Printify"], ["printify_draft", "Create a Printify draft product"]], "image");
    const prompt = textarea("Your own original creative instructions (required for image generation)", ""), path = input("e.g. generated/image-….png", "");
    const fields = textarea("Draft fields in JSON. Use real IDs from your account's catalog.", ""); fields.rows = 12;
    const details = el("div"), confirmation = check("I confirm this exact external action on my connected account. Image generation uses paid API credits."), original = check("This uses my original creative input. I will complete required AI and production-partner disclosures before publishing.");
    const examples = {
      etsy_draft: {quantity: 1, title: job.title, description: job.brief, price: 10, who_made: "i_did", when_made: "made_to_order", taxonomy_id: 0, type: "download"},
      printify_draft: {title: job.title, description: job.brief, blueprint_id: 0, print_provider_id: 0, variants: [{id: 0, price: 2000, is_enabled: true}], print_areas: [{variant_ids: [0], placeholders: [{position: "front", images: [{id: "PASTE_UPLOADED_IMAGE_ID", x: .5, y: .5, scale: 1, angle: 0}]}]}]}
    };
    function change() {
      details.replaceChildren();
      if (choice.value === "image") details.append(field("Image instructions", prompt), hint("One 1024 × 1024 PNG. The provider bills your API account. Inspect the image before delivery; it is generated after the job's review. Export again to include it."));
      else if (choice.value === "printify_upload") details.append(field("Image path inside this job", path), hint("PNG or JPEG up to 20 MB. The result gives you an image ID for the Printify draft."));
      else { fields.value = json(examples[choice.value]); details.append(field("Review these draft fields", fields), hint("Replace zero IDs with real catalog/category IDs. This creates a draft only. It does not publish, create orders, produce goods or deliver to a client.")); }
      if (choice.value === "etsy_draft") details.append(original.wrap);
    }
    choice.addEventListener("change", change); change();
    const result = el("pre", "connection-result"), submit = submitButton("Run confirmed action");
    append(form, link("Account setup →", "connections"), field("Action", choice), details, confirmation.wrap, result, actionsRow(button("Close", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      const payload = {action: choice.value, confirmed: confirmation.control.checked, original_confirmed: original.control.checked};
      if (choice.value === "image") payload.prompt = prompt.value;
      else if (choice.value === "printify_upload") payload.path = path.value.trim();
      else payload.fields = JSON.parse(fields.value);
      const value = await mutate(`/api/business/jobs/${encodeURIComponent(job.id)}/external`, payload, "POST", 240000);
      result.textContent = json(value); toast(value.message); reload();
    });
    showDialog("Review an external action", form);
  }

  // ---------- setup guides ----------
  function openLink(id) { return act(() => "Opened in your browser.", () => mutate(`/api/open-link/${encodeURIComponent(id)}`)); }
  function linkButtons(links) { return append(el("div", "guide-links"), ...array(links).map(([label, id]) => button(`${label} ↗`, () => openLink(id), "button small ghost"))); }
  function guideDialog(key) {
    const guide = window.CerebraGuides?.[key]; if (!guide) return;
    const content = el("div", "guide");
    append(content, el("h3", "", "What you need"), list(guide.need));
    guide.sections.forEach(section => { const steps = el("ol"); section.steps.forEach(step => steps.append(el("li", "", step))); append(content, el("h3", "", section.heading), steps, section.links ? linkButtons(section.links) : null); });
    append(content, hint("Keys and tokens are saved encrypted for your user account on this computer only. Never paste them into Support chat or task descriptions."), actionsRow(button("Close", closeDialog, "button ghost")));
    showDialog(`How to connect ${guide.title}`, content);
  }
  function guideNotes(key) {
    const guide = window.CerebraGuides?.[key]; if (!guide) return null;
    const notes = el("aside", "guide-notes"), steps = el("ol");
    guide.quick.forEach(step => steps.append(el("li", "", step)));
    append(notes, el("div", "eyebrow", "SETUP NOTES"), el("strong", "", "You need"), list(guide.need), el("strong", "", "Steps"), steps,
      button("How to connect…", () => guideDialog(key), "button small primary"), linkButtons(guide.links));
    return notes;
  }
  function withNotes(form, key) { return append(el("div", "connection-layout"), append(el("div", "connection-form"), form), guideNotes(key)); }

  function connectionView() {
    const root = el("div", "connection-grid"), token = renderToken;
    (async () => {
      const [connections, mail, notifications] = await Promise.all([api("/api/business/connections"), api("/api/business/gmail"), api("/api/business/notifications")]);
      if (token !== renderToken) return;
      const specs = {
        etsy: {title: "Etsy drafts", help: "Register your own Etsy developer app. Etsy requires a registered HTTPS callback you control. Authorize in your browser, then paste the full redirected callback URL here. Credentials alone do not mean a connection has been verified.", fields: [["api_key", "App keystring", true], ["shared_secret", "Shared secret", true], ["shop_id", "Shop ID (optional: found for you by Check connection)"], ["redirect_uri", "Registered HTTPS callback URL"]]},
        printify: {title: "Printify drafts", help: "Use your own Printify personal API token. Check connection to list your shop IDs. Choose real catalog variant/provider IDs in each product draft. Orders, order imports and production are blocked because shop auto-approval cannot be verified here.", fields: [["api_key", "API token", true], ["shop_id", "Shop ID (optional if you have one store)"]]},
        images: {title: "Raster images", help: "Use your own OpenAI API key with image-model access. Checking access does not generate an image. A reviewed job offers a separate paid generation action. Your coding subscription does not include these API charges.", fields: [["api_key", "OpenAI API key", true], ["model", "Image model"]]}
      };
      for (const [provider, spec] of Object.entries(specs)) {
        const saved = connections[provider], form = el("form"), controls = {}, result = el("pre", "connection-result");
        append(form, badge(saved.connected ? "verified connection" : saved.authorized ? "authorized; check shop" : saved.configured ? "key saved; not verified" : "not connected", saved.connected ? "green" : "muted"), el("p", "hint", spec.help));
        spec.fields.forEach(([key, label, secret]) => { const control = input(secret && saved.key_saved ? "Saved — leave blank to keep" : label, secret ? "" : saved[key] || ""); if (secret) { control.type = "password"; control.autocomplete = "off"; } controls[key] = control; form.append(field(label, control)); });
        const save = submitButton("Save protected settings"), buttons = actionsRow(save,
          button("Check connection", () => act(value => { result.textContent = json(value); return value.message; }, () => mutate(`/api/business/connections/${provider}/check`))),
          button("Disconnect", () => act(value => { result.textContent = value.message; return value.message; }, () => mutate(`/api/business/connections/${provider}`, undefined, "DELETE")), "button danger"));
        if (provider === "etsy") {
          const callback = textarea("Paste your redirected HTTPS callback URL here", "");
          append(form, field("After Etsy authorization", callback));
          append(buttons, button("Authorize Etsy…", () => act(value => value.message, () => mutate("/api/business/connections/etsy/authorize"))), button("Finish authorization", () => act(value => { callback.value = ""; result.textContent = value.message; return value.message; }, () => mutate("/api/business/connections/etsy/finish", {redirected_url: callback.value.trim()}))));
        }
        append(form, buttons, result); wireForm(form, save, async () => { const values = Object.fromEntries(Object.entries(controls).map(([key, control]) => [key, control.value])); await mutate(`/api/business/connections/${provider}`, {values}, "PUT"); spec.fields.forEach(([key,,secret]) => { if (secret) controls[key].value = ""; }); result.textContent = "Settings saved. Check the connection next."; });
        root.append(panel(spec.title, body(withNotes(form, provider)), button("How to connect…", () => guideDialog(provider), "button small ghost")));
      }
      const gmailForm = el("form"), clientId = input("Google Desktop app OAuth client ID", mail.client_id || ""), secret = input("Google client secret", ""); secret.type = "password"; secret.autocomplete = "off";
      const saveMail = submitButton("Save Google settings"), query = input("Gmail search", "newer_than:7d"), messages = el("div"), mailState = el("div", "hint", mail.connected ? `Connected read-only: ${mail.email}` : "Not connected");
      append(gmailForm, mailState, hint("Enable Gmail API in your own Google Cloud project and create a Desktop app OAuth client. Sign-in opens Google's page. Cerebra can read selected messages; it cannot send, delete or change mail. Messages are not automatically given to AI."), field("Client ID", clientId), field("Client secret", secret), actionsRow(saveMail, button("Connect Gmail…", () => act(value => value.message, () => mutate("/api/business/gmail/authorize"))), button("Disconnect Gmail", () => act(value => { mailState.textContent = "Disconnected"; messages.replaceChildren(); return value.message; }, () => mutate("/api/business/gmail", undefined, "DELETE")))), field("Search your inbox", query), button("Read matching messages", async () => { try { const items = await api(`/api/business/gmail/messages?query=${encodeURIComponent(query.value)}&limit=10`); messages.replaceChildren(...items.map(item => { const card = el("div", "action-card"); append(card, el("strong", "", item.subject), el("div", "row-meta", item.from), el("p", "mail-text", item.body || item.snippet), button("Use as business brief…", () => businessForm({title: item.subject.slice(0,120), brief: item.body || item.snippet}))); return card; })); if (!items.length) messages.textContent = "No matching messages."; } catch (issue) { notice(issue.message, true); } }), messages);
      wireForm(gmailForm, saveMail, async () => { await mutate("/api/business/gmail", {client_id: clientId.value.trim(), client_secret: secret.value.trim()}, "PUT"); secret.value = ""; toast("Google settings saved."); }); root.append(panel("Read-only Gmail intake", body(withNotes(gmailForm, "gmail")), button("How to connect…", () => guideDialog("gmail"), "button small ghost")));
      const notifyForm = el("form"), ntfy = check("Send progress notifications through ntfy", notifications.ntfy_enabled), telegram = check("Send progress notifications to my Telegram bot", notifications.telegram_enabled);
      const server = input("HTTPS ntfy server", notifications.ntfy_server), bot = input("Telegram bot token (blank keeps saved token)", ""), chat = input("Your private Telegram chat ID", notifications.telegram_chat_id || ""); bot.type = "password"; bot.autocomplete = "off";
      const saveNotify = submitButton("Save notifications"), notifyResult = el("pre", "connection-result");
      append(notifyForm, hint("Optional: task titles and states leave your computer for your selected service. Do not put client secrets in titles. Anyone with your ntfy topic can read its messages. Subscribe privately in your ntfy app."), field("ntfy subscription topic", input("", notifications.ntfy_topic)), ntfy.wrap, field("ntfy HTTPS server", server), telegram.wrap, field("Bot token", bot), field("Your Telegram chat ID", chat, "After pressing Start in your bot, press Find my chat."), button("Find my chat", () => act(value => { chat.value = value.chat_id; return `Found your chat${value.name ? ` with ${value.name}` : ""}.`; }, () => mutate("/api/business/notifications/telegram-chat")), "button small"), actionsRow(saveNotify, button("Send me a test", () => act(value => { notifyResult.textContent = json(value); return value.sent.length ? "Test sent." : "No notification sent; check settings."; }, () => mutate("/api/business/notifications/test")))), notifyResult);
      wireForm(notifyForm, saveNotify, async () => { await mutate("/api/business/notifications", {ntfy_enabled: ntfy.control.checked, ntfy_server: server.value, telegram_enabled: telegram.control.checked, telegram_token: bot.value, telegram_chat_id: chat.value}, "PUT"); bot.value = ""; toast("Notifications saved."); }); root.append(panel("Progress on your phone", body(withNotes(notifyForm, "notify")), button("How to connect…", () => guideDialog("notify"), "button small ghost")));
      const fiverr = append(el("div"), badge("manual", "blue"), el("p", "", "Fiverr has no seller API, so there is nothing to connect. Paste each order's requirements into Business Studio, review the exported files yourself and deliver them in Fiverr."), button("+ New business job from a Fiverr order", () => businessForm(), "button small"));
      root.append(panel("Fiverr orders", body(withNotes(fiverr, "fiverr")), button("How to connect…", () => guideDialog("fiverr"), "button small ghost")));
    })().catch(issue => { if (token === renderToken) root.replaceChildren(body(empty("Connections unavailable", issue.message))); });
    return root;
  }

  // ---------- readiness check ----------
  function readinessPanel() {
    const node = el("div"), stages = el("div"), token = renderToken;
    const run = button("Run readiness check", async () => { run.disabled = true; if (await act("Readiness check started.", () => mutate("/api/readiness", {}, "POST", 120000))) poll(); else run.disabled = false; }, "button primary");
    append(node, el("p", "", "Runs one small, real task in a separate test project: planning, coding, your tests and an independent review, with your own models. It stops before merging, so none of your projects change. It uses a little of your Codex/Claude usage."), actionsRow(run), stages);
    const ICON = {passed: "✓", failed: "✗", running: "…", waiting: "·"};
    async function poll() {
      let state; try { state = await api("/api/readiness"); } catch { return; }
      if (token !== renderToken) return;
      if (state.status === "never") { stages.replaceChildren(el("p", "row-meta", "Not run yet.")); run.disabled = !agentsOn(); return; }
      const rows = state.stages.map(stage => append(el("div", `readiness-stage ${stage.state}`), el("span", "readiness-icon", ICON[stage.state] || "·"), el("strong", "", stage.label),
        el("span", "row-meta", [stage.model, stage.seconds ? `${Math.round(stage.seconds)} s` : ""].filter(Boolean).join(" · ")), stage.detail ? el("p", "row-meta", stage.detail) : null));
      const headline = {passed: ["green", "Ready: every stage worked end to end."], failed: ["red", "Not ready: a stage failed (details below)."], running: ["blue", "Running…"], "waiting for usage": ["amber", "Paused: no AI model has usage left right now."], "waiting for internet": ["amber", "Paused: the AI couldn't be reached. It tries again every 5 minutes."], cancelled: ["muted", "Stopped before it finished; nothing failed. Run it again any time."]}[state.status] || ["muted", state.status];
      fill(stages, append(el("div", "row-meta"), badge(state.status, headline[0]), el("span", "", headline[1]), state.task_id ? button("Open task", () => taskDetail(state.task_id), "button small ghost") : null), ...rows, state.error ? hint(state.error, true) : null);
      run.disabled = state.status === "running" || !agentsOn();
      if (["running", "waiting for usage"].includes(state.status) && token === renderToken) setTimeout(poll, 3000);
    }
    run.disabled = !agentsOn(); poll();
    if (!agentsOn()) node.append(hint("Switch AI agents on above first.", true));
    return node;
  }

  // ---------- updates ----------
  function updatesPanel() {
    const node = el("div"), state = el("div"), notes = el("div"), log = el("div");
    append(node, kv([["This version", data.version], ["Updates from", "your GitHub releases (Mukira56/Cerebra)"]]), state, notes, log);
    const check = button("Check for updates", () => run(), "button primary");
    state.append(actionsRow(check), hint("Uses your GitHub sign-in (GitHub page). Updating closes Cerebra, installs the new version and reopens it; running tasks are paused and can be resumed."));
    async function run() {
      check.disabled = true; check.textContent = "Checking…";
      let info; try { info = await api("/api/updates", {timeout: 90000}); } catch (issue) { state.replaceChildren(hint(issue.message, true), actionsRow(button("Try again", () => run(), "button"))); return; }
      const bar = el("progress", "update-bar"), barText = el("span", "row-meta"), meter = append(el("div", "update-meter hidden"), bar, barText); bar.max = 100; bar.value = 0;
      const megabytes = value => `${(Number(value || 0) / 1048576).toFixed(1)} MB`;
      async function watch() {
        let state_; try { state_ = await api("/api/updates/progress"); } catch { setTimeout(watch, 2000); return; }
        meter.classList.remove("hidden"); bar.value = state_.percent || 0;
        barText.textContent = state_.phase === "downloading" ? `${state_.percent || 0}% · ${megabytes(state_.bytes)} of ${megabytes(state_.total)}` : state_.phase === "verifying" ? "99% · checking the checksum…"
          : state_.phase === "ready" ? "100% · downloaded and verified" : state_.phase === "failed" ? `Failed: ${state_.error}` : state_.message || "Starting…";
        if (state_.phase === "ready") { download.replaceWith(install); return; }
        if (state_.phase === "failed") { download.disabled = false; download.textContent = `Try again`; return; }
        if (page === "settings") setTimeout(watch, 500);
      }
      const download = button(`Download ${info.latest || ""}`, async () => {
        download.disabled = true; download.textContent = "Downloading in the background…";
        if (await act("Downloading in the background. You can keep working; the top bar shows its progress.", () => mutate("/api/updates/download", {tag: info.tag}))) watch();
        else { download.disabled = false; download.textContent = `Download ${info.latest}`; }
      }, "button primary");
      const actions = el("div", "form-actions");
      const install = button("Install and restart", async () => {
        install.disabled = true;
        const result = await act(value => value.message, () => mutate("/api/updates/install", {}, "POST", 60000));
        if (result) state.replaceChildren(el("div", "notice", `${result.message} A small window shows each step while Cerebra is closed.`)); else install.disabled = false;
      }, "button primary");
      if (info.available) actions.append(info.downloaded ? install : download);
      if (info.available && !info.downloaded && ["starting", "downloading", "verifying"].includes(data.update_progress?.phase)) { download.disabled = true; download.textContent = "Downloading in the background…"; watch(); }
      actions.append(button("Check again", () => run(), "button ghost"));
      fill(state, append(el("div", "row-meta"), badge(info.available ? "update available" : "up to date", info.available ? "green" : "muted"), el("span", "", info.message)),
        !info.installed && info.available ? hint("You're running Cerebra from source: update it with git pull instead.", true) : null, info.installed || !info.available ? actions : null);
      notes.replaceChildren(info.available && info.notes ? append(el("details", "update-notes"), el("summary", "", `What's new in ${info.latest}`), markdown(info.notes)) : el("span"));
      log.replaceChildren(array(info.last_log).length ? append(el("details"), el("summary", "", "Last update log"), code(info.last_log.join("\n"))) : el("span"));
    }
    return node;
  }

  // ---------- full access ----------
  const fullOn = () => data?.settings?.full_access === true;
  function fullAccessForm() {
    const form = el("form");
    if (fullOn()) {
      append(form, append(el("div", "row-meta"), badge("full access", "red"), el("span", "", "Coding agents can run any command with your Windows account and use your GitHub login.")),
        hint("Planning, review and chat stay read-only. The supervisor still tests and reviews every change before it is merged."));
      const helpers = check("Tasks that Support or the Council create for me get Full access too", data.assistant_full_access === true);
      helpers.wrap.title = "Off: tasks written by Support or the Council run inside the project copy only. On: they can install packages, run commands, and use the network and GitHub, like tasks you start yourself.";
      helpers.control.addEventListener("change", () => {
        if (!helpers.control.checked) { act("Support and Council tasks run inside the project copy again.", () => mutate("/api/permissions/assistant-full-access", {enabled: false})).then(() => refresh(true)); return; }
        helpers.control.checked = false;
        showDialog("Give Support and Council tasks Full access?", append(el("div"),
          el("p", "", "Support and the Council write task instructions from what they read in your projects, logs and messages. With this on, those tasks can run commands, install packages and use the network and your GitHub login, just like the tasks you start yourself."),
          el("p", "", "A mistake, or a hidden instruction inside a file they read, could then reach the rest of this laptop. Turn it off any time; it applies from the next AI run."),
          actionsRow(button("Cancel", closeDialog, "button ghost"), button("Allow", async () => { closeDialog(); if (await act("Support and Council tasks now get Full access.", () => mutate("/api/permissions/assistant-full-access", {enabled: true, acknowledge: true}))) { await refresh(true); } }, "button danger"))));
      });
      form.append(helpers.wrap);
      const off = submitButton("Limit agents to the project copy"); off.className = "button"; form.append(actionsRow(off));
      wireForm(form, off, async () => { await mutate("/api/permissions/full-access", {enabled: false}); await refresh(true); toast("Agents are limited to the project copy again."); });
      return form;
    }
    const machine = check("I let Codex and Claude run any command on this laptop (install software, use the network, change files outside the project) while they code a task."), github = check("I let them use my GitHub login (push, open pull requests, create or change repositories) when a task needs it.");
    append(form, append(el("div", "row-meta"), badge("project only", "green"), el("span", "", "Agents can only change the files a task allows, in a separate copy.")),
      hint("Full access is powerful and risky: a mistake, or a hidden instruction inside some project file, could delete files, leak data or change your repositories, and nothing stops a command while it runs. Use it on projects you trust, and keep backups.", true),
      machine.wrap, github.wrap, !agentsOn() ? hint("Switch AI agents on above first.", true) : null);
    const on = submitButton("Give full access"); on.className = "button danger"; on.disabled = !agentsOn(); form.append(actionsRow(on));
    wireForm(form, on, async () => { if (!machine.control.checked || !github.control.checked) throw new Error("Tick both boxes to give full access."); await mutate("/api/permissions/full-access", {enabled: true, acknowledge_full_access: true, acknowledge_github: true}); await refresh(true); toast("Coding agents now have full access."); });
    return form;
  }

  // ---------- about you ----------
  function ownerForm() {
    const form = el("form"), grid = el("div", "form-grid"), inputs = {};
    const fields = [["name", "Name", "e.g. Godfrey Mukira"], ["headline", "What you do", "e.g. Software engineer and AI builder"], ["email", "Email", "the address you want on your work"],
      ["github", "GitHub username", "e.g. Mukira56"], ["linkedin", "LinkedIn", "https://www.linkedin.com/in/…"], ["website", "Website", "https://…"], ["location", "Location", "e.g. Nairobi, Kenya"]];
    fields.forEach(([key, label, hint_]) => { inputs[key] = input(hint_); grid.append(field(label, inputs[key])); });
    inputs.bio = textarea("A few sentences about you: your background, what you build, what you're proud of."); inputs.preferences = textarea("How you like things done: tone, colours, style, what to avoid.");
    const share = check("Share these details with the AI team (Support, the Council and coding tasks)", true);
    const fromGitHub = button("Use my GitHub login", async () => { const found = await act(null, () => api("/api/owner/github")); if (found?.github) { inputs.github.value = found.github; toast(`GitHub username: ${found.github}`); } }, "button small ghost");
    append(form, hint("ChatGPT's and Claude's own memories aren't shared with Cerebra. Fill this in once so portfolios, READMEs and replies use your real details instead of placeholders. Only put here what you'd put on a public profile; never passwords or keys."),
      grid, append(el("div", "row-meta"), fromGitHub), field("About you", inputs.bio), field("How you like things done", inputs.preferences), share.wrap);
    const save = submitButton("Save"); form.append(actionsRow(save));
    api("/api/owner").then(profile => { Object.entries(inputs).forEach(([key, control]) => { control.value = profile[key] || ""; }); share.control.checked = profile.share !== false; }).catch(() => {});
    wireForm(form, save, async () => {
      const values = Object.fromEntries(Object.entries(inputs).map(([key, control]) => [key, control.value])); values.share = share.control.checked;
      await mutate("/api/owner", values, "PUT"); toast(share.control.checked ? "Saved. The AI team will use your details." : "Saved, and kept to yourself.");
    });
    return form;
  }

  // ---------- auto-fix ----------
  function autoFixForm() {
    const policy = data.auto_fix || {}, form = el("form");
    const enabled = check("When a task fails, start the Assistant on it right away (it reads the logs and retries with a fix).", policy.enabled);
    const access = check("Give fix runs Full access (commands, installs, network and GitHub), like tasks I start myself.", policy.full_access);
    access.control.disabled = !fullOn();
    const attempts = select([1, 2, 3, 4, 5, 6, 8, 10].map(value => [String(value), `${value} attempt${value === 1 ? "" : "s"} per task`]), String(policy.max_attempts ?? 4));
    const council = select([[0, "Never"], [1, "After 1 failed fix"], [2, "After 2 failed fixes"], [3, "After 3 failed fixes"]].map(([value, label]) => [String(value), label]), String(policy.council_after ?? 2));
    const scope = select([["selected", "Only the tasks I tick below"], ["all", "Every failed task, including new failures"]], policy.scope || "selected");
    append(form, append(el("div", "row-meta"), badge(policy.enabled ? "auto-fix on" : "auto-fix off", policy.enabled ? "green" : "muted"), el("span", "", policy.enabled ? (policy.full_access_effective ? "Fix runs use Full access." : "Fix runs stay inside the project copy.") : "Failed tasks wait for you.")),
      hint("Each new failure is one attempt. When fixes don't hold, Codex and Claude meet in the Council, agree the solution (a restructure if the project's design is the problem), and the Assistant applies it. Every task has a Stop auto-fix button. Merges still wait for you unless Away mode is on; every attempt uses your plan's usage."),
      enabled.wrap, access.wrap, !fullOn() ? hint("Turn on Full access above first if fix runs should be able to install tools and use the network.") : null,
      field("Which tasks", scope), field("Stop after", attempts), field("Ask the Council", council));
    const save = submitButton("Save auto-fix"); form.append(actionsRow(save));
    form.append(autoFixTaskList());
    wireForm(form, save, async () => {
      await mutate("/api/auto-fix", {enabled: enabled.control.checked, full_access: access.control.checked && fullOn(), max_attempts: Number(attempts.value), council_after: Number(council.value), scope: scope.value}, "PUT");
      await refresh(true); toast(enabled.control.checked ? "Auto-fix is on. Failed tasks go to the Assistant." : "Auto-fix is off.");
    });
    return form;
  }

  function autoFixTaskList() {
    const node = el("div", "auto-fix-tasks"), rows = el("div", "check-list"), head = el("div", "row-meta");
    append(node, el("h3", "", "Failed tasks"), head, rows);
    const describeScope = () => data.auto_fix?.scope === "all" ? "Every failed task is fixed unless you untick it." : "Tick the tasks Auto-fix should work on.";
    async function choose(ids, enabled) {
      if (!ids.length) return;
      const listed = await act(null, () => mutate("/api/auto-fix/tasks", {task_ids: ids, enabled}));
      if (listed) paint(listed);
    }
    function paint(items) {
      rows.replaceChildren();
      head.replaceChildren(el("span", "", items.length ? `${items.filter(item => item.selected).length} of ${items.length} chosen. ${describeScope()}${data.auto_fix?.enabled ? "" : " Nothing runs until Auto-fix is switched on and saved."}` : "No failed tasks right now."));
      if (items.length) head.append(button("Tick all", () => choose(items.filter(item => !item.selected).map(item => item.id), true), "button small"), button("Untick all", () => choose(items.filter(item => item.selected).map(item => item.id), false), "button small ghost"),
        button("Delete all listed", () => deleteTasks(items, reload), "button small danger"));
      items.forEach(item => {
        const box = check("", item.selected), label = box.wrap.querySelector("span");
        label.replaceChildren(append(el("span", "auto-fix-task"), el("strong", "", item.description), el("small", "", `${item.project} · ${nice(item.state)} · ${relative(item.updated_at)}${item.attempts ? ` · attempt ${item.attempts}` : ""}${item.status ? ` · ${nice(item.status)}` : ""}`), el("small", "hint-line", item.error)));
        box.control.addEventListener("change", () => choose([item.id], box.control.checked));
        rows.append(append(el("div", "auto-fix-row"), box.wrap, button("Delete", () => deleteTasks([item], reload), "button small ghost")));
      });
    }
    function reload() { api("/api/auto-fix/tasks").then(paint).catch(issue => rows.replaceChildren(hint(issue.message, true))); }
    reload();
    return node;
  }
  function deleteTasks(items, after) {
    const many = items.length > 1;
    showDialog(many ? `Delete ${items.length} tasks?` : "Delete this task?", append(el("div"),
      many ? list(items.map(item => `${item.description} (${item.project})`)) : el("p", "", items[0].description),
      el("p", "", "Their records, logs and working copies are removed. Cerebra backs up its database first, keeps each task's Git branch in the project, and keeps the history in Activity."),
      actionsRow(button("Cancel", closeDialog, "button ghost"), button(many ? `Delete ${items.length} tasks` : "Delete task", async () => {
        const done = await act(many ? `${items.length} tasks deleted.` : "Task deleted.", () => mutate("/api/tasks/delete", {task_ids: items.map(item => item.id), confirm: true}));
        closeDialog(); if (done) { await refresh(true); if (after) after(); }
      }, "button danger"))));
  }

  // ---------- away mode ----------
  const awayOn = () => data?.autopilot?.active === true;
  function awayForm() {
    const policy = data.autopilot || {}, form = el("form");
    if (awayOn()) {
      append(form, append(el("div", "row-meta"), badge("away mode on", "purple"), el("span", "", `Until ${date(policy.until)}${policy.auto_merge ? (policy.auto_push ? " · merges and pushes passing work" : " · merges passing work") : " · stops before merging"}`)),
        kv([["Projects", array(policy.projects).length ? array(policy.projects).map(id => projectFor(id)?.name || id).join(", ") : "All projects"], ["Started", date(policy.started_at)]]),
        hint("Cerebra approves plans, starts the AI team and sends review findings back for repair for you. Everything it answers is written in Activity with “Away mode answered…”."));
      const off = submitButton("Turn Away mode off"); off.className = "button danger"; form.append(actionsRow(off));
      wireForm(form, off, async () => { await mutate("/api/autopilot", {enabled: false}, "PUT"); await refresh(true); toast("Away mode is off. Every step asks you again."); });
      return form;
    }
    const hours = select([[2, "2 hours"], [4, "4 hours"], [8, "8 hours (a work day or a night)"], [12, "12 hours"], [24, "24 hours"], [48, "48 hours"], [72, "72 hours"]].map(([value, label]) => [String(value), label]), "8");
    const scope = el("div", "check-list"), boxes = array(data.projects).map(project => { const box = check(project.name); box.control.value = project.id; scope.append(box.wrap); return box; });
    const push = check("Then push merged work to the project's GitHub repository."); push.wrap.classList.add("hidden");
    const approve = check("Let Cerebra approve plans, start the AI team and send review findings back for repair, without asking me."), merge = check("Also merge finished work into my project when every test passed and the review found nothing to fix."), mergeOk = check("I understand merged work changes my real project folder (locally only — nothing is pushed or published).");
    mergeOk.wrap.classList.add("hidden"); merge.control.addEventListener("change", () => { mergeOk.wrap.classList.toggle("hidden", !merge.control.checked); push.wrap.classList.toggle("hidden", !merge.control.checked); if (!merge.control.checked) push.control.checked = false; });
    append(form, append(el("div", "row-meta"), badge("away mode off", "muted"), el("span", "", "Every plan, run and merge waits for you.")),
      hint("Turn this on before you leave so queued tasks keep going. Create the tasks first; Away mode answers their approval steps for the time you choose, then switches itself off."),
      field("For how long", hours), field("Which projects (none ticked = all)", scope), approve.wrap, merge.wrap, mergeOk.wrap, push.wrap,
      hint(fullOn() ? "Full access is on, so coding agents can also run commands, use the network and your GitHub login. Keep the computer awake and Cerebra running. Usage counts against your Codex/Claude plans." : "What stays the same: agents still work only in a separate copy of the project, may change only the files the task allows, have no network in Codex, and cannot install software, push to GitHub or touch the rest of your laptop. Keep the computer awake and Cerebra running. Usage counts against your Codex/Claude plans."),
      !agentsOn() ? hint("Switch AI agents on above first.", true) : null);
    const on = submitButton("Turn Away mode on"); on.disabled = !agentsOn(); form.append(actionsRow(on));
    wireForm(form, on, async () => {
      if (!approve.control.checked) throw new Error("Tick the first box to let Cerebra answer for you.");
      if (merge.control.checked && !mergeOk.control.checked) throw new Error("Tick the merge confirmation too, or untick automatic merging.");
      const result = await mutate("/api/autopilot", {enabled: true, hours: Number(hours.value), auto_merge: merge.control.checked, auto_push: push.control.checked, projects: boxes.filter(box => box.control.checked).map(box => box.control.value), acknowledge_auto_approval: true, acknowledge_auto_merge: merge.control.checked}, "PUT");
      await refresh(true); toast(`Away mode is on until ${date(result.until)}.`);
    });
    return form;
  }

  // ---------- settings ----------
  function settingsView() {
    const values = data.settings || {}, root = el("div");
    const permissions = el("form"), usage = check("I understand the AI agents run on my own accounts and can use my plan's usage or credits."), reads = check("I understand the agents can read files outside the project folder with my Windows permissions (they can only write inside it).");
    if (agentsOn()) {
      append(permissions, append(el("div", "row-meta"), badge("agents on", "green"), el("span", "", awayOn() ? "Away mode is answering approval steps for you (below)." : "Each task still asks you before agents run.")));
      const off = submitButton("Switch agents off"); off.className = "button danger"; permissions.append(actionsRow(off));
      wireForm(permissions, off, async () => { await mutate("/api/permissions", {enabled: false}); await refresh(true); toast("AI agents switched off."); });
    } else {
      append(permissions, append(el("div", "row-meta"), badge("agents off", "amber"), el("span", "", "Codex and Claude cannot run until you switch them on.")), usage.wrap, reads.wrap, hint("Agents work in a separate copy of your project and can only change the files you allow. Codex writes are sandboxed to that copy and it has no network. Nothing reaches your real project until you approve the merge."));
      const on = submitButton("Switch agents on"); permissions.append(actionsRow(on));
      wireForm(permissions, on, async () => { if (!usage.control.checked || !reads.control.checked) throw new Error("Tick both boxes to switch agents on."); await mutate("/api/permissions", {enabled: true, acknowledge_provider_usage: true, acknowledge_residual_read_risk: true}); await refresh(true); toast("AI agents switched on."); });
    }
    root.append(panel("Agent permissions", body(permissions)));
    root.append(panel("Readiness check", body(readinessPanel())));
    root.append(panel("Full access — let agents control this laptop", body(fullAccessForm())));
    root.append(panel("About you — so the AI team can use your real details", body(ownerForm())));
    root.append(panel("Away mode — work while I'm away", body(awayForm())));
    root.append(panel("Auto-fix — the Assistant fixes failed tasks by itself", body(autoFixForm())));

    const limits = el("form"), controls = {}, grid = el("div", "form-grid");
    const unlimited = {};
    // "No limit" sends 0 seconds for time limits and -1 for repair attempts.
    [["agent_timeout", "AI run time limit (seconds)", 10, 86400, 0, 600], ["test_timeout", "Test time limit (seconds)", 1, 86400, 0, 120], ["max_retries", "Automatic repair attempts", 0, 100, -1, 3]].forEach(([name, label, min, max, none, fallback]) => {
      const current = values[name], node = input("", current === none ? fallback : current, "number"), box = check("No limit");
      node.min = min; node.max = max; box.control.checked = current === none; node.disabled = box.control.checked;
      box.control.addEventListener("change", () => { node.disabled = box.control.checked; });
      controls[name] = node; unlimited[name] = [box.control, none];
      grid.append(append(field(label, node, name === "max_retries" ? "With no limit, repairs continue until tests and review pass, or an attempt changes nothing." : "With no limit, use Pause or Cancel to stop a long run."), box.wrap));
    });
    controls.codex_path = input("found automatically", values.codex_path); controls.claude_path = input("found automatically", values.claude_path);
    append(limits, grid, field("Codex program path (optional)", controls.codex_path), field("Claude program path (optional)", controls.claude_path));
    const save = submitButton("Save"); limits.append(actionsRow(save));
    wireForm(limits, save, async () => { const payload = {}; Object.entries(controls).forEach(([name, control]) => { payload[name] = unlimited[name]?.[0].checked ? unlimited[name][1] : control.type === "number" ? Number(control.value) : control.value.trim(); }); await mutate("/api/settings", payload, "PATCH"); await refresh(true); toast("Settings saved."); });
    root.append(panel("Limits & programs", body(limits)));
    root.append(panel("Updates", body(updatesPanel())));

    root.append(panel("Where your data lives", body(kv([["Everything Cerebra records", `${values.data_dir}\\hq.sqlite3`], ["AI working copies", `${values.data_dir}\\worktrees`], ["What each AI said (logs)", `${values.data_dir}\\logs`], ["AI plans", `${values.data_dir}\\artifacts`], ["Projects created here", `${values.data_dir}\\projects`], ["Backups", `${values.data_dir}\\backups`]]), hint("All of this stays on this computer. Stop Cerebra before copying it for a backup."))));

    const cleanup = el("div");
    (async () => { try { const preview = await api("/api/maintenance/demo-data"); if (!preview.tasks && !preview.projects.length) { cleanup.replaceChildren(el("p", "", "No old demo data. ✓")); return; } const go = button(`Remove ${preview.tasks} demo task(s)${preview.projects.length ? ` and ${preview.projects.length} demo project(s)` : ""}`, async () => { go.disabled = true; const result = await act(r => `Removed ${r.tasks_removed} demo tasks. Backup saved.`, () => mutate("/api/maintenance/demo-data", {confirm: true}, "POST", 120000)); if (result) { await refresh(true); } else go.disabled = false; }, "button danger"); fill(cleanup, el("p", "", "Earlier versions had a simulated demo. Its records are no longer used. Real tasks and projects are kept, and the database is backed up first."), preview.projects.length ? el("p", "row-meta", `Demo projects: ${preview.projects.join(", ")}`) : null, go); } catch (issue) { cleanup.replaceChildren(hint(issue.message, true)); } })();
    root.append(panel("Old demo data", body(cleanup)));
    return root;
  }

  // ---------- right-click menu ----------
  // Text boxes and selected text keep the Windows edit menu (cut/copy/paste); everything else gets Cerebra's menu.
  const menu = el("div", "context-menu"); menu.setAttribute("role", "menu"); menu.hidden = true; document.body.append(menu);
  async function copyText(text, label = "Copied.") {
    try { await navigator.clipboard.writeText(text); }
    catch { const area = el("textarea"); area.value = text; area.style.position = "fixed"; area.style.opacity = "0"; document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
    toast(label);
  }
  function closeMenu() { if (!menu.hidden) { menu.hidden = true; menu.replaceChildren(); } }
  function openMenu(items, x, y) {
    menu.replaceChildren();
    items.forEach(item => {
      if (item === "-") { menu.append(el("div", "context-separator")); return; }
      const [label, action, disabled] = item, entry = button(label, () => { closeMenu(); action(); }, "context-item");
      entry.setAttribute("role", "menuitem"); entry.tabIndex = -1; entry.disabled = !!disabled; menu.append(entry);
    });
    menu.hidden = false;
    const width = menu.offsetWidth, height = menu.offsetHeight;
    menu.style.left = `${Math.max(4, Math.min(x, innerWidth - width - 4))}px`; menu.style.top = `${Math.max(4, Math.min(y, innerHeight - height - 4))}px`;
    menu.querySelector(".context-item:not(:disabled)")?.focus();
  }
  menu.addEventListener("keydown", event => {
    const items = [...menu.querySelectorAll(".context-item:not(:disabled)")], index = items.indexOf(document.activeElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus(); }
    else if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); closeMenu(); }
  });
  document.addEventListener("contextmenu", event => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest("input, textarea, select, [contenteditable='true']") || String(getSelection()).trim()) { closeMenu(); return; }  // native edit menu
    if (target.closest(".context-menu")) { event.preventDefault(); return; }
    event.preventDefault();
    const items = [...(event.cerebraMenu || [])];
    const taskRow = target.closest("[data-task-id]"), jobRow = target.closest("[data-job-id]"), chat = target.closest(".chat-item"), code = target.closest("pre, code, .code-block");
    const taskId = taskRow?.dataset.taskId, task = taskId && taskFor(taskId);
    if (taskId) {
      if (items.length) items.push("-");
      items.push(["Open task", () => taskDetail(taskId)], ["Plain report", () => { closeDialog(); location.hash = `report/${taskId}`; }]);
      if (task && pendingApprovals().some(item => item.task_id === taskId)) items.push(["Go to its approvals", () => { closeDialog(); location.hash = "approvals"; }]);
      if (task && ["RUNNING", "VERIFYING", "REVIEWING", "NEEDS_CHANGES"].includes(task.state)) items.push(["Pause task", () => taskAction(taskId, "pause")]);
      items.push(["Copy task ID", () => copyText(taskId, "Task ID copied.")]);
    }
    if (jobRow) {
      const id = jobRow.dataset.jobId;
      if (items.length) items.push("-");
      items.push(["Open job", () => { location.hash = `job/${id}`; }], ["Open job folder", () => act("Opened.", () => mutate(`/api/business/jobs/${encodeURIComponent(id)}/open`, {what: "folder"}))], ["Copy job ID", () => copyText(id, "Job ID copied.")]);
    }
    if (chat?.dataset.id) { if (items.length) items.push("-"); items.push(["Open chat", () => chat.click()]); }
    if (code) { if (items.length) items.push("-"); items.push(["Copy this text", () => copyText(code.textContent)]); }
    if (items.length) items.push("-");
    items.push(["Back", () => history.back(), history.length < 2], ["Refresh", async () => { await refresh(true); render(); toast("Refreshed."); }]);
    items.push("-", ["New task", () => taskForm()], ["New business job", () => { location.hash = "business"; setTimeout(() => businessForm(), 0); }], ["Ask Support", () => { location.hash = "chat"; }]);
    openMenu(items, event.clientX || target.getBoundingClientRect().left + 10, event.clientY || target.getBoundingClientRect().top + 10);
  });
  // Close on user actions only: panels that refresh themselves can fire scroll events every few seconds.
  ["pointerdown", "wheel"].forEach(kind => window.addEventListener(kind, event => { if (menu.contains(event.target)) return; closeMenu(); }, true));
  window.addEventListener("resize", closeMenu); window.addEventListener("blur", event => { if (event.target === window) closeMenu(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeMenu(); });

  // ---------- data loop & routing ----------
  async function refresh(force = false) {
    // A background poll may be in flight. A forced refresh (after a button press) must not be dropped:
    // wait for that poll, then fetch again so the page shows the state the action produced.
    while (fetching) { if (!force) return fetching; await fetching; }
    let done; fetching = new Promise(resolve => { done = resolve; });
    try {
      const next = await api("/api/overview"), fingerprint = JSON.stringify(next); data = next;
      const status = $("#connection-status"); status.className = "pill good"; status.replaceChildren(el("span", "dot"), document.createTextNode("Local connection")); notice("");
      if (force || fingerprint !== lastFingerprint) { lastFingerprint = fingerprint; if (["overview", "tasks", "projects", "approvals", "reports", "activity"].includes(page) || force) render(); else chrome(); if (page === "system" && !force) paintTeamBar(); }
      if (detailTaskId && dialog.open) await taskDetail(detailTaskId, true);
    } catch (issue) { const status = $("#connection-status"); status.className = "pill bad"; status.replaceChildren(el("span", "dot"), document.createTextNode("Disconnected")); notice(`Local connection unavailable. ${issue.message}`, true); }
    finally { fetching = null; done(); }
  }
  function route() { const [name, ...rest] = location.hash.slice(1).split("/"); page = Object.hasOwn(pages, name) ? name : "overview"; param = rest.join("/"); if (page === "job" && !param) page = "business"; if (page === "report" && !param) page = "reports"; render(); }
  window.addEventListener("hashchange", route);
  async function boot() {
    try {
      const hash = new URLSearchParams(location.hash.slice(1)), key = hash.get("key");
      if (key) { history.replaceState(null, "", location.pathname + location.search); try { await mutate("/api/session", {key}); } catch (bootstrapError) { const existing = await api("/api/session"); if (!existing.csrf_token) throw bootstrapError; } }
      csrf = (await api("/api/session")).csrf_token; if (!csrf) throw new Error("No session token was returned.");
      route(); await refresh(true);
      api("/api/providers").then(result => { cache.providers = result; if (page === "overview") render(); }).catch(() => {});
      setInterval(() => { if (!document.hidden) refresh(); }, 3000);
      document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
    } catch (issue) {
      notice(`Session required. Use the Cerebra tray menu: Restart workspace. ${issue.message}`, true);
      content.replaceChildren(empty("Open your private launch link", "Cerebra needs a private local session. Choose Restart workspace from the Cerebra tray icon (or run scripts\\start.ps1).", null, "⌘"));
    }
  }
  route(); boot();
})();
