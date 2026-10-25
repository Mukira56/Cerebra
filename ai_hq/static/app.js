"use strict";
// AI HQ dashboard. Every value from the server or a model is inserted as text, never as HTML.
(() => {
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const pages = {
    overview: ["WORKSPACE", "Overview", "Everything happening in your development HQ, at a glance."],
    chat: ["WORK", "Chat", "Ask Codex or Claude about a project. Chat is read-only: to change code, create a task."],
    tasks: ["WORK", "Tasks", "Describe what to build. AI plans it, writes it, tests it and checks it; you approve."],
    projects: ["WORK", "Projects", "Repositories AI HQ is allowed to work in."],
    approvals: ["WORK", "Approvals", "Nothing important happens without your yes."],
    system: ["INSIGHT", "System view", "A live map of the backend: what runs where, right now."],
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
  let csrf = "", data = null, page = "overview", param = "", lastFingerprint = "", fetching = false, toastTimer = 0;
  let detailTaskId = "", detailTab = "Overview", detailFingerprint = "", pageTimer = 0, renderToken = 0;
  const cache = {providers: null, tools: null, github: null, repos: null, chats: null};
  const content = $("#page-content"), dialog = $("#dialog"), dialogContent = $("#dialog-content");

  // ---------- small DOM helpers ----------
  function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined && text !== null) node.textContent = String(text); return node; }
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
  function kv(values) { const node = el("dl", "kv"); values.forEach(([key, value]) => append(node, el("dt", "", key), el("dd", "", value === true ? "Yes" : value === false ? "No" : (value ?? "—")))); return node; }
  function table(headers, rows) { const wrap = el("div", "table-wrap"), node = el("table"), head = el("tr"); headers.forEach(header => head.append(el("th", "", header))); node.append(append(el("thead"), head)); const tbody = el("tbody"); rows.forEach(cells => { const row = el("tr"); cells.forEach(value => { const cell = el("td"); cell.append(value instanceof Node ? value : document.createTextNode(String(value ?? "—"))); row.append(cell); }); tbody.append(row); }); node.append(tbody); wrap.append(node); return wrap; }
  function option(value, label, selected = false) { const node = el("option", "", label); node.value = value; node.selected = selected; return node; }
  function select(options, value) { const node = el("select"); options.forEach(([key, label, disabled]) => { const item = option(key, label); item.disabled = !!disabled; node.append(item); }); if (value !== undefined) node.value = value; return node; }
  function field(label, control, help) { return append(el("label", "field"), el("span", "", label), control, help ? el("small", "", help) : null); }
  function input(placeholder = "", value = "", type = "text") { const node = el("input"); node.type = type; node.placeholder = placeholder; node.value = value ?? ""; return node; }
  function textarea(placeholder = "", value = "") { const node = el("textarea"); node.placeholder = placeholder; node.value = value; return node; }
  function check(label) { const wrap = el("label", "check-field"), control = input("", "", "checkbox"); append(wrap, control, el("span", "", label)); return {wrap, control}; }
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
  function profileLabel(id) { const profile = profiles().find(item => item.id === id); return profile ? profile.label : id; }
  function taskModels(task) { const models = task?.results?.models || {}; return {planner: models.planner?.label || "Claude", implementer: models.implementer?.label || nice(task?.assigned_agent), reviewer: models.reviewer?.label || nice(task?.reviewer)}; }

  // ---------- chrome ----------
  function heading() {
    const [eyebrow, title, subtitle] = pages[page];
    $("#page-eyebrow").textContent = eyebrow; $("#page-title").textContent = title; $("#page-subtitle").textContent = subtitle;
    $("#breadcrumb-title").textContent = param ? `${page}/${param.slice(0, 8)}` : page;
    document.querySelectorAll("[data-page]").forEach(node => node.classList.toggle("active", node.dataset.page === page || (page === "report" && node.dataset.page === "reports")));
    const actions = $("#heading-actions"); actions.replaceChildren();
    if (["overview", "tasks"].includes(page)) actions.append(button("+ New task", () => taskForm(), "button primary"));
    if (page === "projects") actions.append(button("+ Add project", () => projectForm(), "button primary"));
    if (page === "models") actions.append(button("↻ Re-check tools", () => act("Agent tools re-checked.", async () => { cache.providers = await mutate("/api/providers/refresh", {}, "POST", 120000); await refresh(true); }), "button ghost"));
    if (page === "report") actions.append(button("← All reports", () => { location.hash = "reports"; }, "button ghost"), button("Technical details", () => taskDetail(param), "button ghost"));
  }
  function chrome() {
    if (!data) return;
    $("#project-count").textContent = array(data.projects).length;
    const count = pendingApprovals().length; $("#approval-count").textContent = count; $("#approval-count").classList.toggle("hidden", !count);
    const status = $("#agents-status"); status.className = `pill ${agentsOn() ? "good" : "warn"}`; status.replaceChildren(el("span", "dot"), document.createTextNode(agentsOn() ? (awayOn() ? "away mode" : "agents on") : "agents off")); status.title = awayOn() ? `Away mode until ${date(data.autopilot.until)}` : "";
    $("#version-label").textContent = `AI HQ v${data.version || ""}`;
  }

  function render() {
    clearInterval(pageTimer); pageTimer = 0; renderToken++;
    if (page !== "system") window.AIHQSystem?.unmount();
    heading(); chrome();
    if (!data) { content.replaceChildren(el("div", "loading", "connecting to your local workspace…")); return; }
    const views = {overview, chat: chatView, tasks: tasksView, projects: projectsView, approvals: approvalsView, system: systemView, reports: reportsView, report: reportView, activity: activityView, models: modelsView, github: githubView, toolchain: toolchainView, settings: settingsView};
    const result = views[page]();
    if (result) content.replaceChildren(result);
  }

  // ---------- overview ----------
  function setupChecklist() {
    const signIn = name => cache.providers?.find(item => item.id === name)?.sign_in?.signed_in === true || agentRow(name).authentication === "verified_by_execution";
    const items = [
      ["Install Git and the AI coding tools", "Toolchain checks and installs Git, Codex and Claude Code.", agentRow("codex").installed && agentRow("claude").installed, "toolchain"],
      ["Sign in to Codex and Claude", "Use your own accounts; AI HQ never sees your password.", signIn("codex") && signIn("claude"), "models"],
      ["Switch AI agents on", "One-time permission in Settings. Every task still asks you first.", agentsOn(), "settings"],
      ["Add a project", "An existing folder, a new project, or one cloned from GitHub.", array(data.projects).length > 0, "projects"],
      ["Create your first task", "Describe what you want built.", realTasks().length > 0, "tasks"]
    ];
    const list = el("div", "checklist");
    items.forEach(([title, text, done, target], index) => { const item = el("div", `check-item${done ? " done" : ""}`), info = el("div"); append(info, el("strong", "", title), el("small", "", text)); append(item, el("span", "tick", done ? "✓" : index + 1), info, done ? badge("done", "green") : link("Open →", target)); list.append(item); });
    return {list, complete: items.every(item => item[2])};
  }
  function taskRows(tasks) {
    const list = el("div", "row-list");
    tasks.forEach(task => {
      const row = el("div", "row"), info = el("div", "row-main"), meta = el("div", "row-meta"), models = taskModels(task);
      row.tabIndex = 0; row.setAttribute("role", "button"); row.addEventListener("click", () => taskDetail(task.id)); row.addEventListener("keydown", event => { if (event.key === "Enter") taskDetail(task.id); });
      append(meta, el("span", "", projectFor(task.project_id)?.name || "project"), el("span", "", "·"), el("span", "", `${models.implementer} → ${models.reviewer}`), el("span", "", "·"), el("span", "", relative(task.updated_at)), task.mode === "mock" ? badge("old demo", "muted") : null);
      append(info, el("strong", "", task.description), meta); append(row, info, badge(task.pause_requested ? "PAUSED" : task.state), el("span", "chev", "›")); list.append(row);
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
    const stats = el("div", "grid stats");
    [["Projects", array(data.projects).length, "authorized repositories", ""], ["Active", active.length, active.length ? "AI is working" : "nothing running", "cyan"], ["Waiting for you", pendingApprovals().length, "approvals", "amber"], ["Done", tasks.filter(task => task.state === "COMPLETED").length, "finished tasks", "green"], ["Problems", tasks.filter(task => task.state === "FAILED").length, "see reports", "red"]]
      .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
    node.append(stats);
    const grid = el("div", "grid two"), left = el("div"), right = el("div");
    left.append(panel("Recent tasks", tasks.length ? taskRows(tasks.slice(0, 8)) : body(empty("No tasks yet", "Create a task: describe what you want, and the AI team plans, codes, tests and reviews it.", button("+ New task", () => taskForm(), "button primary"), "#")), link("All tasks →", "tasks"), tasks.length));
    const waiting = pendingApprovals();
    if (waiting.length) left.append(panel("Waiting for your decision", approvalCards(waiting.slice(0, 3)), link("All approvals →", "approvals"), waiting.length));
    const team = body(kv([["Planner", profileLabel(data.roles?.planner)], ["Coder", profileLabel(data.roles?.implementer)], ["Reviewer", profileLabel(data.roles?.reviewer)], ["Agents", agentsOn() ? "On · each task asks first" : "Off"]]), link("Change models →", "models"));
    append(right, panel("Your AI team", team), panel("Recent activity", activityList(array(data.events)), link("All →", "activity")));
    append(grid, left, right); node.append(grid); return node;
  }

  // ---------- tasks ----------
  function tasksView() {
    const node = el("div"), filters = el("div", "form-grid"), projectFilter = select([["", "All projects"], ...array(data.projects).map(project => [project.id, project.name])]), stateFilter = select([["", "All states"], ...[...new Set(array(data.tasks).map(task => task.state))].map(state => [state, nice(state)])]);
    const holder = el("div");
    function paint() { const tasks = array(data.tasks).filter(task => (!projectFilter.value || task.project_id === projectFilter.value) && (!stateFilter.value || task.state === stateFilter.value)); holder.replaceChildren(panel("Tasks", tasks.length ? taskRows(tasks) : body(empty("No tasks here", "Create a task to get the AI team working.", button("+ New task", () => taskForm(projectFilter.value), "button primary"), "#")), null, tasks.length)); }
    projectFilter.addEventListener("change", paint); stateFilter.addEventListener("change", paint);
    append(filters, field("Project", projectFilter), field("State", stateFilter)); append(node, panel("Filter", body(filters)), holder); paint(); return node;
  }
  function profileSelect(role, value) { return select(runnable().map(profile => [profile.id, `${profile.label}`]), value || data.roles?.[role]); }
  function taskForm(projectId = "", description = "") {
    if (!array(data?.projects).length) { toast("Add a project first."); projectForm(); return; }
    const form = el("form"), project = select(array(data.projects).map(item => [item.id, item.name]), projectId || array(data.projects)[0].id);
    const objective = textarea("What should be built or fixed? Be specific about the result you expect."), requirements = textarea("Optional. One requirement per line."), criteria = textarea("Optional. How will you know it works? One per line."), allowed = input(". (whole project), or e.g. src/, README.md");
    const planner = profileSelect("planner"), implementer = profileSelect("implementer"), reviewer = profileSelect("reviewer");
    objective.required = true; objective.minLength = 8; objective.value = description;
    const team = el("div", "form-grid"); append(team, field("Planner", planner, "Writes the plan"), field("Coder", implementer, "Writes the code"), field("Reviewer", reviewer, "Checks the code; must be a different provider"));
    const project_info = el("div"); function describe() { const chosen = projectFor(project.value); project_info.replaceChildren(chosen && !array(chosen.test_commands).length ? hint("This project has no test commands, so AI HQ cannot verify the work. Add them on the Projects page first.", true) : hint(`Tests: ${array(chosen?.test_commands).map(command => command.join(" ")).join("  |  ") || "none"}`)); } project.addEventListener("change", describe); describe();
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
  async function taskAction(taskId, action) { await act(action === "approve-plan" ? "Plan approved." : `${nice(action)} requested.`, () => mutate(`/api/tasks/${encodeURIComponent(taskId)}/${action}`)); await refresh(true); taskDetail(taskId); }
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
      const actions = el("div", "actions");
      if (pending.some(item => item.kind === "plan")) actions.append(button("Approve plan", () => taskAction(taskId, "approve-plan"), "button primary"));
      if (task.state === "READY" && task.approved) actions.append(button("▶ Start", () => startTask(taskId), "button primary"));
      pending.filter(item => item.kind !== "plan").forEach(item => actions.append(button(`Decide: ${nice(item.kind)}`, () => approvalDialog(item), "button primary")));
      if (ACTIVE.includes(task.state) && !task.pause_requested) actions.append(button("Pause", () => taskAction(taskId, "pause")));
      if (task.pause_requested || task.state === "BLOCKED") actions.append(button("Resume", () => taskAction(taskId, "resume")));
      if (!["CANCELLED", "COMPLETED", "FAILED"].includes(task.state)) actions.append(button("Cancel", () => taskAction(taskId, "cancel"), "button danger"));
      actions.append(button("Plain report", () => { closeDialog(); location.hash = `report/${taskId}`; }, "button ghost"));
      root.append(actions);
      const tabs = el("div", "tabs"), pane = el("div");
      const views = {
        "Overview": () => append(el("div", "section"), kv([["Project", projectFor(task.project_id)?.name], ["Planner", models.planner], ["Coder", models.implementer], ["Reviewer", models.reviewer], ["Files allowed", array(task.allowed_paths).join(", ")], ["Repairs", `${task.retry_count || 0} / ${task.max_retries ?? 3}`], ["Created", date(task.created_at)], ["Task ID", task.id]]), el("h3", "", "Plan"), plan(task.plan), array(task.requirements).length ? [el("h3", "", "Requirements"), list(task.requirements)] : null, task.results?.architecture?.output ? [el("h3", "", "AI architecture advisory"), code(task.results.architecture.output)] : null),
        "Results": () => { const node = append(el("div", "section"), el("h3", "", "Tests")); if (!array(task.test_results).length) node.append(el("p", "", "No tests have run yet.")); array(task.test_results).forEach(result => append(node, append(el("div", "row-meta"), badge(result.passed ? "passed" : "failed", result.passed ? "green" : "red"), el("code", "", array(result.command).join(" "))), code((result.stdout || "") + (result.stderr ? `\n${result.stderr}` : "")))); node.append(el("h3", "", "Review findings")); if (!array(task.review_findings).length) node.append(el("p", "", array(task.reviews).length ? "The reviewer found no problems." : "No review yet.")); array(task.review_findings).forEach(finding => append(node, append(el("div", "row-meta"), badge(finding.severity, ["critical", "high"].includes(finding.severity) ? "red" : "amber"), el("code", "", `${finding.path || ""}${finding.line ? `:${finding.line}` : ""}`), finding.validated ? badge("verified", "green") : badge("unverified", "muted")), el("p", "", finding.message))); return node; },
        "Changes": () => append(el("div", "section"), kv([["Branch", task.branch], ["Base commit", task.base_commit], ["Working copy", task.worktree_path]]), code(task.diff || task.results?.diff || "No changes yet.")),
        "Runs & logs": () => { const node = el("div", "section"); if (!array(task.runs).length) node.append(el("p", "", "No AI runs yet.")); array(task.runs).forEach(run => append(node, append(el("div", "row-meta"), el("strong", "", `${nice(run.agent)} · ${run.role}`), badge(run.status, run.status === "succeeded" ? "green" : run.status === "running" ? "blue" : "red"), el("span", "", date(run.started_at))), run.error ? code(run.error) : null, run.output ? code(run.output.slice(-6000)) : null)); node.append(el("h3", "", "Event history")); node.append(activityList([...array(task.events)].reverse(), 200)); return node; }
      };
      function choose(label) { detailTab = label; tabs.querySelectorAll("button").forEach(item => item.classList.toggle("active", item.textContent === label)); pane.replaceChildren(views[label]()); }
      Object.keys(views).forEach(label => tabs.append(button(label, () => choose(label), ""))); append(root, tabs, pane); choose(views[detailTab] ? detailTab : "Overview");
      showDialog(task.description, root); dialog.scrollTop = scroll;
    } catch (issue) { if (!background) toast(issue.message, true); }
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

  // ---------- projects ----------
  function projectsView() {
    if (!array(data.projects).length) return panel("Projects", body(empty("No projects yet", "Add an existing folder, start a new project, or clone one from GitHub.", button("+ Add project", () => projectForm(), "button primary"), "{}")));
    const grid = el("div", "grid cards");
    data.projects.forEach(project => {
      const card = el("article", "card"), top = el("div", "card-top"), info = el("div"), tasks = array(data.tasks).filter(task => task.project_id === project.id);
      append(info, el("h3", "", project.name), el("div", "row-meta", project.path)); append(top, el("span", "icon-tile", "{}"), info);
      append(card, top, kv([["Branch", project.default_branch], ["Tasks", tasks.length], ["Tests", array(project.test_commands).map(command => command.join(" ")).join(" | ") || "none — add some"]]));
      append(card, append(el("div", "card-footer"), button("New task", () => taskForm(project.id), "button small primary"), button("Chat", () => newChat(project.id), "button small"), button("Tests…", () => testsForm(project), "button small ghost"), button("Push", () => act(result => `Pushed to ${result.remote}`, () => mutate(`/api/projects/${project.id}/push`, {}, "POST", 600000)), "button small ghost"), button("Publish…", () => publishForm(project), "button small ghost")));
      grid.append(card);
    });
    return grid;
  }
  function commandsInput(value) { return textarea('[["python", "-m", "pytest", "-q"]]', value); }
  function parseCommands(text) { let commands; try { commands = JSON.parse(text || "[]"); } catch { throw new Error("Test commands must be JSON, for example [[\"npm\", \"test\"]]"); } if (!Array.isArray(commands) || commands.some(command => !Array.isArray(command) || !command.length || command.some(arg => typeof arg !== "string"))) throw new Error("Use a list of argument lists, each argument a string."); return commands; }
  const TEST_HELP = "How AI HQ checks the work. Examples: [[\"python\",\"-m\",\"pytest\",\"-q\"]] · [[\"npm\",\"test\"]] · [[\"dotnet\",\"test\"]]. These run as your Windows user, so only add projects you trust.";
  function projectForm(source = "existing") {
    const form = el("form"), kind = select([["existing", "A folder on this computer"], ["new", "A new, empty project"], ["github", "Clone from GitHub"]], source), name = input("e.g. Booking platform"), path = input("C:\\Users\\you\\Projects\\my-app"), repo = el("select"), tests = commandsInput("[]"), consent = check("I trust this project and allow AI HQ to create working copies and run its test commands as my Windows user.");
    const pathField = field("Folder", path, "The exact Git repository folder."), repoField = field("GitHub repository", repo, "Sign in on the GitHub page to see your repositories.");
    async function loadRepos() { repo.replaceChildren(option("", "Loading your repositories…")); try { cache.repos = cache.repos || await api("/api/github/repositories", {timeout: 60000}); repo.replaceChildren(...cache.repos.map(item => option(item.name, `${item.name} · ${item.visibility?.toLowerCase() || ""}`))); if (!cache.repos.length) repo.replaceChildren(option("", "No repositories found")); } catch (issue) { repo.replaceChildren(option("", issue.message)); } }
    function sync() { pathField.classList.toggle("hidden", kind.value !== "existing"); repoField.classList.toggle("hidden", kind.value !== "github"); if (kind.value === "github" && !repo.options.length) loadRepos(); }
    kind.addEventListener("change", sync); sync();
    append(form, field("Where is the project?", kind), field("Name", name), pathField, repoField, field("Test commands", tests, TEST_HELP), consent.wrap);
    const submit = submitButton("Add project"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      if (!consent.control.checked) throw new Error("Tick the trust box to continue.");
      const commands = parseCommands(tests.value);
      const project = kind.value === "github" ? await mutate("/api/github/clone", {repository: repo.value, name: name.value.trim(), authorize: true, test_commands: commands}, "POST", 600000)
        : await mutate("/api/projects", {name: name.value.trim() || "New project", path: kind.value === "new" ? "" : path.value.trim(), create_new: kind.value === "new", authorize: true, test_commands: commands});
      closeDialog(); await refresh(true); toast(`Project “${project.name}” added.`);
    });
    showDialog("Add a project", form);
  }
  function testsForm(project) {
    const form = el("form"), tests = commandsInput(JSON.stringify(project.test_commands || [])); append(form, field("Test commands", tests, TEST_HELP));
    const submit = submitButton("Save"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => { await mutate(`/api/projects/${project.id}`, {test_commands: parseCommands(tests.value)}, "PATCH"); closeDialog(); await refresh(true); toast("Test commands saved."); });
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
  let chatId = "", chatPoll = 0;
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
  async function newChat(projectId = "", profile = data?.roles?.implementer || "codex") {
    const conversation = await act(null, () => mutate("/api/chats", {profile, project_id: projectId || null}));
    if (conversation) { chatId = conversation.id; cache.chats = null; if (page === "chat") render(); else location.hash = "chat"; }
  }
  function chatView() {
    const root = el("div", "chat"), side = el("div", "chat-list"), head = el("div", "chat-list-head"), items = el("div", "chat-items"), main = el("div", "chat-main");
    const profile = select(runnable().map(item => [item.id, item.label]), data.roles?.implementer), project = select([["", "No project (general chat)"], ...array(data.projects).map(item => [item.id, item.name])]);
    append(head, field("Talk to", profile), field("About", project), button("+ New chat", () => newChat(project.value, profile.value), "button primary"));
    append(side, head, items); append(root, side, main);
    const token = renderToken;
    async function loadList() { try { cache.chats = await api("/api/chats"); } catch (issue) { toast(issue.message, true); cache.chats = []; } if (token !== renderToken) return; items.replaceChildren(); if (!cache.chats.length) items.append(el("p", "hint", "No chats yet. Pick who to talk to, then press New chat.")); cache.chats.forEach(item => { const entry = button("", () => { chatId = item.id; paintList(); openChat(); }, `chat-item${item.id === chatId ? " active" : ""}`); append(entry, el("strong", "", item.title), el("small", "", `${profileLabel(item.profile)} · ${relative(item.updated_at)}`)); entry.dataset.id = item.id; items.append(entry); }); if (!chatId && cache.chats.length) chatId = cache.chats[0].id; paintList(); openChat(); }
    function paintList() { items.querySelectorAll(".chat-item").forEach(node => node.classList.toggle("active", node.dataset.id === chatId)); }
    async function openChat(keepScroll = false) {
      clearTimeout(chatPoll);
      if (!chatId) { main.replaceChildren(body(empty("Chat with your AI team", "Ask how something works, plan a feature, or get a review of a file. Chat can read the chosen project but never changes it.", null, ">_"))); return; }
      let state; try { state = await api(`/api/chats/${encodeURIComponent(chatId)}`); } catch (issue) { main.replaceChildren(body(empty("Chat unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const conversation = state.conversation, header = el("div", "chat-head"), messages = el("div", "messages"), composer = el("form", "composer"), box = textarea("Message " + profileLabel(conversation.profile) + "…  (Enter to send, Shift+Enter for a new line)"), send = submitButton("Send");
      const previous = main.querySelector(".messages"), wasAtBottom = !previous || previous.scrollHeight - previous.scrollTop - previous.clientHeight < 40, draft = main.querySelector("textarea")?.value || "";
      append(header, el("strong", "", conversation.title), badge(profileLabel(conversation.profile), "blue"), conversation.project_id ? badge(projectFor(conversation.project_id)?.name || "project", "purple") : badge("no project", "muted"), badge("read-only", "green"), el("span", "", ""), button("→ Make it a task", () => taskForm(conversation.project_id || "", [...state.messages].reverse().find(message => message.role === "user")?.content || ""), "button small primary"), button("Delete", async () => { if (await act("Chat deleted.", () => api(`/api/chats/${encodeURIComponent(chatId)}`, {method: "DELETE"}))) { chatId = ""; loadList(); } }, "button small ghost"));
      if (!agentsOn()) messages.append(hint("AI agents are switched off, so messages will fail. Turn them on in Settings › Agent permissions.", true));
      if (!state.messages.length) messages.append(empty("Say hello", conversation.project_id ? "This chat can read the project's files to answer you." : "This is a general chat, not linked to a project.", null, ">_"));
      state.messages.forEach(message => {
        const row = el("div", `message ${message.role}`), bubble = el("div", `bubble${message.status === "failed" ? " failed" : ""}`), holder = el("div");
        if (message.role === "user") bubble.append(el("p", "", message.content));
        else if (message.status === "pending") bubble.append(append(el("div", "typing"), el("span"), el("span"), el("span")), el("small", "", `${nice(message.provider)} is thinking… this can take a minute.`));
        else if (message.status === "failed") bubble.append(el("p", "", `⚠ ${message.error || "No answer."}`));
        else bubble.append(markdown(message.content));
        append(holder, bubble, el("div", "message-meta", `${message.role === "user" ? "you" : nice(message.provider) + (message.model ? ` · ${message.model}` : "")} · ${relative(message.created_at)}`));
        append(row, el("span", "avatar", message.role === "user" ? "you" : PROVIDER_ICON[message.provider] || "AI"), holder); messages.append(row);
      });
      box.value = draft; send.disabled = state.busy;
      box.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); composer.requestSubmit(); } });
      composer.addEventListener("submit", async event => { event.preventDefault(); const text = box.value.trim(); if (!text) return; send.disabled = true; if (await act(null, () => mutate(`/api/chats/${encodeURIComponent(chatId)}/messages`, {text}))) { box.value = ""; await openChat(); } else send.disabled = false; });
      append(composer, box, state.busy ? button("Stop", () => act("Stopping…", () => mutate(`/api/chats/${encodeURIComponent(chatId)}/stop`)), "button danger") : null, send);
      main.replaceChildren(header, messages, composer);
      if (wasAtBottom || !keepScroll) messages.scrollTop = messages.scrollHeight;
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
    return null;
  }

  // ---------- reports ----------
  function reportsView() {
    const tasks = realTasks();
    if (!tasks.length) return panel("Reports", body(empty("No reports yet", "Every task gets an easy-to-read report: what you asked, who did what, whether the tests passed, and where everything is saved.", null, "¶")));
    const list = el("div", "row-list");
    tasks.forEach(task => { const row = el("div", "row"), info = el("div", "row-main"); row.addEventListener("click", () => { location.hash = `report/${task.id}`; }); append(info, el("strong", "", task.description), el("div", "row-meta", `${projectFor(task.project_id)?.name || ""} · ${relative(task.updated_at)}`)); append(row, info, badge(task.state), el("span", "chev", "›")); list.append(row); });
    return append(el("div"), hint("Each report explains a task in short, simple sentences, so anyone can follow what the AI team did."), panel("All reports", list, null, tasks.length));
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
      append(holder.replaceChildren() || holder, hero, el("h2", "", "What you asked for"), el("div", "asked", report.asked), el("h2", "", "Who helped"), helpers, el("h2", "", "What happened, step by step"), story,
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
    root.append(panel("Your AI accounts", body(hint("Sign in uses each tool's own login window. AI HQ never sees your passwords or keys; your plan (ChatGPT, Claude, Copilot…) pays for usage."), el("div", "", ""), providersHolder)));
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

    const roles = el("form"), planner = profileSelect("planner"), implementer = profileSelect("implementer"), reviewer = profileSelect("reviewer");
    append(roles, el("div", "form-grid"), hint("New tasks start with these. You can still change them per task. The reviewer must use a different provider from the coder, so the review is truly independent."));
    append(roles.firstChild, field("Planner", planner), field("Coder", implementer), field("Reviewer", reviewer));
    const saveRoles = submitButton("Save defaults"); roles.append(actionsRow(saveRoles));
    wireForm(roles, saveRoles, async () => { await mutate("/api/models/roles", {planner: planner.value, implementer: implementer.value, reviewer: reviewer.value}, "PUT"); await refresh(true); toast("Default AI team saved."); });
    root.append(panel("Default AI team", body(roles)));

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
      if (!status.installed) { account.replaceChildren(body(empty("GitHub CLI is not installed", "AI HQ talks to GitHub through the official GitHub CLI.", link("Install it from Toolchain →", "toolchain", "button primary"), "⑂"))); return; }
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
    root.append(hint("Install opens a visible window running the official installer (winget or npm), so you can watch it. Nothing is installed without your click. Restart AI HQ after installing so it finds new tools."), el("div", "", ""), holder);
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

  // ---------- away mode ----------
  const awayOn = () => data?.autopilot?.active === true;
  function awayForm() {
    const policy = data.autopilot || {}, form = el("form");
    if (awayOn()) {
      append(form, append(el("div", "row-meta"), badge("away mode on", "purple"), el("span", "", `Until ${date(policy.until)}${policy.auto_merge ? " · merges passing work" : " · stops before merging"}`)),
        kv([["Projects", array(policy.projects).length ? array(policy.projects).map(id => projectFor(id)?.name || id).join(", ") : "All projects"], ["Started", date(policy.started_at)]]),
        hint("AI HQ approves plans, starts the AI team and sends review findings back for repair for you. Everything it answers is written in Activity with “Away mode answered…”."));
      const off = submitButton("Turn Away mode off"); off.className = "button danger"; form.append(actionsRow(off));
      wireForm(form, off, async () => { await mutate("/api/autopilot", {enabled: false}, "PUT"); await refresh(true); toast("Away mode is off. Every step asks you again."); });
      return form;
    }
    const hours = select([[2, "2 hours"], [4, "4 hours"], [8, "8 hours (a work day or a night)"], [12, "12 hours"], [24, "24 hours"], [48, "48 hours"], [72, "72 hours"]].map(([value, label]) => [String(value), label]), "8");
    const scope = el("div", "check-list"), boxes = array(data.projects).map(project => { const box = check(project.name); box.control.value = project.id; scope.append(box.wrap); return box; });
    const approve = check("Let AI HQ approve plans, start the AI team and send review findings back for repair, without asking me."), merge = check("Also merge finished work into my project when every test passed and the review found nothing to fix."), mergeOk = check("I understand merged work changes my real project folder (locally only — nothing is pushed or published).");
    mergeOk.wrap.classList.add("hidden"); merge.control.addEventListener("change", () => mergeOk.wrap.classList.toggle("hidden", !merge.control.checked));
    append(form, append(el("div", "row-meta"), badge("away mode off", "muted"), el("span", "", "Every plan, run and merge waits for you.")),
      hint("Turn this on before you leave so queued tasks keep going. Create the tasks first; Away mode answers their approval steps for the time you choose, then switches itself off."),
      field("For how long", hours), field("Which projects (none ticked = all)", scope), approve.wrap, merge.wrap, mergeOk.wrap,
      hint("What stays the same: agents still work only in a separate copy of the project, may change only the files the task allows, have no network in Codex, and cannot install software, push to GitHub or touch the rest of your laptop. Keep the computer awake and AI HQ running. Usage counts against your Codex/Claude plans."),
      !agentsOn() ? hint("Switch AI agents on above first.", true) : null);
    const on = submitButton("Turn Away mode on"); on.disabled = !agentsOn(); form.append(actionsRow(on));
    wireForm(form, on, async () => {
      if (!approve.control.checked) throw new Error("Tick the first box to let AI HQ answer for you.");
      if (merge.control.checked && !mergeOk.control.checked) throw new Error("Tick the merge confirmation too, or untick automatic merging.");
      const result = await mutate("/api/autopilot", {enabled: true, hours: Number(hours.value), auto_merge: merge.control.checked, projects: boxes.filter(box => box.control.checked).map(box => box.control.value), acknowledge_auto_approval: true, acknowledge_auto_merge: merge.control.checked}, "PUT");
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
    root.append(panel("Away mode — work while I'm away", body(awayForm())));

    const limits = el("form"), controls = {}, grid = el("div", "form-grid");
    [["agent_timeout", "AI run time limit (seconds)", 10, 7200], ["test_timeout", "Test time limit (seconds)", 1, 1800], ["max_retries", "Automatic repair attempts", 0, 3]].forEach(([name, label, min, max]) => { const node = input("", values[name], "number"); node.min = min; node.max = max; controls[name] = node; grid.append(field(label, node)); });
    controls.codex_path = input("found automatically", values.codex_path); controls.claude_path = input("found automatically", values.claude_path);
    append(limits, grid, field("Codex program path (optional)", controls.codex_path), field("Claude program path (optional)", controls.claude_path));
    const save = submitButton("Save"); limits.append(actionsRow(save));
    wireForm(limits, save, async () => { const payload = {}; Object.entries(controls).forEach(([name, control]) => { payload[name] = control.type === "number" ? Number(control.value) : control.value.trim(); }); await mutate("/api/settings", payload, "PATCH"); await refresh(true); toast("Settings saved."); });
    root.append(panel("Limits & programs", body(limits)));

    root.append(panel("Where your data lives", body(kv([["Everything AI HQ records", `${values.data_dir}\\hq.sqlite3`], ["AI working copies", `${values.data_dir}\\worktrees`], ["What each AI said (logs)", `${values.data_dir}\\logs`], ["AI plans", `${values.data_dir}\\artifacts`], ["Projects created here", `${values.data_dir}\\projects`], ["Backups", `${values.data_dir}\\backups`]]), hint("All of this stays on this computer. Stop AI HQ before copying it for a backup."))));

    const cleanup = el("div");
    (async () => { try { const preview = await api("/api/maintenance/demo-data"); if (!preview.tasks && !preview.projects.length) { cleanup.replaceChildren(el("p", "", "No old demo data. ✓")); return; } const go = button(`Remove ${preview.tasks} demo task(s)${preview.projects.length ? ` and ${preview.projects.length} demo project(s)` : ""}`, async () => { go.disabled = true; const result = await act(r => `Removed ${r.tasks_removed} demo tasks. Backup saved.`, () => mutate("/api/maintenance/demo-data", {confirm: true}, "POST", 120000)); if (result) { await refresh(true); } else go.disabled = false; }, "button danger"); cleanup.replaceChildren(el("p", "", "Earlier versions had a simulated demo. Its records are no longer used. Real tasks and projects are kept, and the database is backed up first."), preview.projects.length ? el("p", "row-meta", `Demo projects: ${preview.projects.join(", ")}`) : null, go); } catch (issue) { cleanup.replaceChildren(hint(issue.message, true)); } })();
    root.append(panel("Old demo data", body(cleanup)));
    return root;
  }

  // ---------- data loop & routing ----------
  async function refresh(force = false) {
    if (fetching) return; fetching = true;
    try {
      const next = await api("/api/overview"), fingerprint = JSON.stringify(next); data = next;
      const status = $("#connection-status"); status.className = "pill good"; status.replaceChildren(el("span", "dot"), document.createTextNode("Local connection")); notice("");
      if (force || fingerprint !== lastFingerprint) { lastFingerprint = fingerprint; if (["overview", "tasks", "projects", "approvals", "reports", "activity"].includes(page) || force) render(); else chrome(); }
      if (detailTaskId && dialog.open) await taskDetail(detailTaskId, true);
    } catch (issue) { const status = $("#connection-status"); status.className = "pill bad"; status.replaceChildren(el("span", "dot"), document.createTextNode("Disconnected")); notice(`Local connection unavailable. ${issue.message}`, true); }
    finally { fetching = false; }
  }
  function route() { const [name, ...rest] = location.hash.slice(1).split("/"); page = Object.hasOwn(pages, name) ? name : "overview"; param = rest.join("/"); if (page === "report" && !param) page = "reports"; render(); }
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
      notice(`Session required. Use the AI HQ tray menu: Restart workspace. ${issue.message}`, true);
      content.replaceChildren(empty("Open your private launch link", "AI HQ needs a private local session. Choose Restart workspace from the AI HQ tray icon (or run scripts\\start.ps1).", null, "⌘"));
    }
  }
  route(); boot();
})();
