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
    chat: ["WORK", "Support", "Ask about any project or task (“why did EstatePilot fail?”), or have Cerebra plan, create and start the work."],
    council: ["WORK", "Council", "Codex and Claude discuss a project with each other, agree on ideas and who builds each one. You read every word."],
    business: ["WORK", "Business Studio", "Turn a client brief into original, reviewed deliverables saved on this laptop."],
    connections: ["SETUP", "Business connections", "Connect your own accounts. Secrets stay protected on this Windows account; external work needs your confirmation."],
    job: ["WORK", "Business result", ""],
    tasks: ["WORK", "Tasks", "Describe what to build. AI plans it, writes it, tests it and checks it; you approve."],
    projects: ["WORK", "Projects", "Repositories Cerebra is allowed to work in."],
    approvals: ["WORK", "Approvals", "Nothing important happens without your yes."],
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
  dialog.addEventListener("close", () => { detailTaskId = ""; });

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
    const waitingCount = pendingApprovals().length, workingCount = realTasks().filter(task => ACTIVE.includes(task.state)).length, failedCount = realTasks().filter(task => task.state === "FAILED").length;
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
    const views = {overview, council: councilView, connections: connectionView, business: businessView, job: jobView, chat: chatView, tasks: tasksView, projects: projectsView, approvals: approvalsView, system: systemView, reports: reportsView, report: reportView, activity: activityView, models: modelsView, github: githubView, toolchain: toolchainView, settings: settingsView};
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
    [/target branch moved/i, "Another task merged first. Press Try again: Cerebra now brings the work up to date and merges it."],
    [/changed the same parts of/i, "The project changed the same files since this task started. Press Try again to redo it on the latest code."],
  ];
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
      const reason = (task.state === "FAILED" || (task.state === "BLOCKED" && !task.pause_requested)) ? failureReason(task) : "";
      const calm = task.state === "BLOCKED" && (!task.results?.error || ["waiting_for_usage", "waiting_for_network"].includes(task.results?.blocked_reason));
      append(info, el("strong", "", task.description), meta, reason ? el("div", calm ? "row-reason waiting" : "row-reason", reason) : null); append(row, info, badge(task.pause_requested ? "PAUSED" : task.state), el("span", "chev", "›")); list.append(row);
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
    [["Projects", array(data.projects).length, "authorized repositories", ""], ["Active", active.length, active.length ? "AI is working" : "nothing running", "cyan"], ["Waiting for you", pendingApprovals().length, "approvals", "amber"], ["Done", tasks.filter(task => task.state === "COMPLETED").length, "finished tasks", "green"], ["Problems", tasks.filter(task => task.state === "FAILED").length, "failed tasks", "red"]]
      .forEach(([label, value, note, style]) => {
        const card = append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note));
        const target = {"Projects": ["projects"], "Active": ["tasks", "active"], "Waiting for you": ["approvals"], "Done": ["tasks", "COMPLETED"], "Problems": ["tasks", "FAILED"]}[label];
        if (target) { card.classList.add("clickable"); card.tabIndex = 0; card.setAttribute("role", "link");
          const go = () => { taskStateFilter = target[1] || ""; location.hash = target[0]; }; card.addEventListener("click", go); card.addEventListener("keydown", event => { if (event.key === "Enter") go(); }); }
        stats.append(card);
      });
    node.append(stats);
    const grid = el("div", "grid two"), left = el("div"), right = el("div");
    left.append(panel("Recent tasks", tasks.length ? taskRows(tasks.slice(0, 8)) : body(empty("No tasks yet", "Create a task: describe what you want, and the AI team plans, codes, tests and reviews it.", button("+ New task", () => taskForm(), "button primary"), "#")), link("All tasks →", "tasks"), tasks.length));
    const waiting = pendingApprovals();
    if (waiting.length) left.append(panel("Waiting for your decision", approvalCards(waiting.slice(0, 3)), link("All approvals →", "approvals"), waiting.length));
    const team = body(kv([["Planner", profileLabel(data.roles?.planner)], ["Coder", profileLabel(data.roles?.implementer)], ["Reviewer", profileLabel(data.roles?.reviewer)], ["Agents", agentsOn() ? "On · each task asks first" : "Off"],
      ...array(data.agents).filter(agent => agent.usage_until && new Date(agent.usage_until) > new Date()).map(agent => [nice(agent.name), `Out of usage until ${new Date(agent.usage_until).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}; the other model covers for it`])]), link("Change models →", "models"));
    append(right, panel("Your AI team", team), panel("Recent activity", activityList(array(data.events)), link("All →", "activity")));
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
      const progress = el("div", "progress-card"), story = task.state === "COMPLETED" ? ["Finished", "The work was tested, reviewed and merged into your project."] : pending.length ? ["Your decision is needed", `Approve or reject: ${pending.map(item => nice(item.kind)).join(", ")}.`] : task.state === "FAILED" ? ["Stopped with a problem", task.results?.error || "See Runs & logs."] : task.state === "READY" ? ["Ready", "Press Start to let the AI team work."] : [nice(task.state), "This window updates automatically."];
      append(progress, el("strong", "", story[0]), el("p", "", story[1])); root.append(progress);
      const fixing = task.results?.auto_fix;
      if (fixing && (fixing.attempts || fixing.stopped)) {
        const words = {fixing: "the Assistant is fixing it", council: "the Council is working out a solution", applying: "the Assistant is applying the Council's solution", gave_up: "it stopped trying; this task needs you", stopped: "you stopped it for this task", error: fixing.error || "it couldn't start", waiting: "waiting for the next failure"};
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
      else if (task.state === "FAILED" || (task.state === "BLOCKED" && task.results?.error && !task.pause_requested)) actions.append(button("↻ Try again", () => taskAction(taskId, "retry"), "button primary"));
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
    node.append(panel("Waiting for you", waiting.length ? approvalCards(waiting) : body(empty("Nothing to decide", "When a task needs your yes, it appears here.", null, "✓")), null, waiting.length));
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
        const names = array(info.missing.names);
        needs.replaceChildren(hint(`Its tests need local settings this laptop doesn't have yet${names.length ? `: ${names.slice(0, 6).join(", ")}${names.length > 6 ? "…" : ""}` : ""}. Copy ${info.missing.example} to a real settings file (for example .env.local) in the project folder and fill in your own values. Cerebra lends it to test runs only; the AI never sees it.`, true));
      }).catch(() => {});
      append(card, append(el("div", "card-footer"), button("New task", () => taskForm(project.id), "button small primary"), viewControls("project", project.id), button("Chat", () => newChat(project.id), "button small"), button("Tests…", () => testsForm(project), "button small ghost"), button("Push", () => act(result => `Pushed to ${result.remote}`, () => mutate(`/api/projects/${project.id}/push`, {}, "POST", 600000)), "button small ghost"), button("Publish…", () => publishForm(project), "button small ghost")));
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
    append(content, hint("Keys and tokens are saved encrypted for your Windows account only. Never paste them into Support chat or task descriptions."), actionsRow(button("Close", closeDialog, "button ghost")));
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
