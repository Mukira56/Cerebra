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
    overview: ["WORKSPACE", "Home", "Everything happening in Cerebra, at a glance."],
    chat: ["WORKSPACE", "Ask for help", "Ask about a project or task, or have Cerebra plan, create and start the work."],
    council: ["BUILD", "AI discussion", "Codex and Claude discuss a project with each other, agree on ideas and who builds each one. You read every word."],
    marketing: ["OUTREACH", "Social media posts", "Posts that bring you clients on X, your Facebook Page and Instagram. Nothing goes out until you approve it."],
    chief: ["WORKSPACE", "Goals & helpers", "Your money goals and the workers that pursue them: each on its schedule, every run on the record. Anything that reaches other people waits for your yes."],
    prospects: ["OUTREACH", "Local customers", "Local businesses in the US that could use what you sell, from public data, each kept only with a reason seen on its own website. Nobody is contacted without you."],
    partners: ["OUTREACH", "Pitch companies", "Offer your service to companies by email from your Gmail: Cerebra finds AI and language companies, reads each one's own website for its public role address and application pages, and sends your pitch within your daily number. Forms are yours to fill in."],
    funding: ["EARN", "Grants & credits", "Free cloud credits, grants and accelerators you could apply to, and what each still needs from you. You apply; Cerebra keeps track."],
    etsy: ["EARN", "Sell on Etsy", "Find what sells on Etsy and how crowded it is, from Etsy's own public listings: demand, competition, prices and the tags top sellers use. Nothing is written to Etsy."],
    books: ["EARN", "Write books", "Short nonfiction books for Amazon KDP: find a niche people pay for, plan and write the book, and see what each format earns. You upload and publish."],
    jobs: ["EARN", "Apply for jobs", "Tech jobs worldwide (remote, hybrid or on-site): each employer studied from its own website, and an application written around that job and that employer's interests, from your CV. You review and send, or let it send."],
    freelance: ["EARN", "Find work", "Paid work found for you on public job sources and scored against what you sell. Cerebra can bid for you on Freelancer.com; elsewhere you apply in your own name."],
    money: ["EARN", "Money & invoices", "Quotes, invoices and what your business has earned and is owed. You send every document; Cerebra never takes payments."],
    business: ["BUILD", "Client work", "Turn a client brief into original, reviewed deliverables saved on this laptop."],
    connections: ["SETUP", "Connected accounts", "Connect your own accounts. Secrets stay protected by this computer's own secret store; external work needs your confirmation."],
    job: ["BUILD", "Business result", ""],
    tasks: ["BUILD", "Coding tasks", "Describe what to build. AI plans it, writes it, tests it and checks it; you approve."],
    projects: ["BUILD", "Projects", "Repositories Cerebra is allowed to work in."],
    approvals: ["WORKSPACE", "Waiting for my OK", "Nothing important happens without your yes."],
    system: ["INSIGHT", "Live view", "A live blueprint of your AI development factory. Inspect a building or a person to see its recorded work."],
    reports: ["INSIGHT", "Reports", "What happened in each task, explained in plain words."],
    report: ["INSIGHT", "Task report", ""],
    activity: ["INSIGHT", "History", "Every decision the supervisor recorded."],
    models: ["SETUP", "AI accounts", "Sign in to your AI accounts, choose models, and add more."],
    github: ["SETUP", "GitHub", "Connect your GitHub account to clone, publish and push projects."],
    toolchain: ["SETUP", "Install tools", "The tools a software engineer needs, checked and installable in one place."],
    settings: ["SETUP", "Settings", "Agent permissions, limits, and where your data lives."]
  };
  // Each kind of work has its own section name and symbolic colour (style.css): Home indigo, Make money green,
  // Pitching and outreach amber, Build violet, What happened teal, Settings slate.
  const SECTIONS = {WORKSPACE: ["home", "HOME"], EARN: ["earn", "MAKE MONEY"], OUTREACH: ["outreach", "PITCHING & OUTREACH"], BUILD: ["build", "BUILD SOFTWARE"], INSIGHT: ["insight", "WHAT HAPPENED"], SETUP: ["setup", "SETTINGS & ACCOUNTS"]};
  // Comfort settings for this viewer: theme, text size and the simple menu (kept in this browser only).
  const comfort = {theme: "light", size: "normal", simple: true};
  try { Object.assign(comfort, JSON.parse(localStorage.getItem("cerebra-comfort") || "{}")); } catch { /* private window: the defaults */ }
  function applyComfort() {
    document.documentElement.dataset.theme = comfort.theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.size = ["large", "huge"].includes(comfort.size) ? comfort.size : "normal";
    document.body.classList.toggle("simple-menu", comfort.simple !== false);
    const meta = document.querySelector('meta[name="color-scheme"]'); if (meta) meta.content = comfort.theme === "dark" ? "dark" : "light";
    document.querySelectorAll("[data-comfort]").forEach(node => { const [key, value] = node.dataset.comfort.split(":"); node.setAttribute("aria-pressed", String(String(comfort[key]) === value)); });
    const toggle = document.getElementById("menu-switch"); if (toggle) toggle.textContent = comfort.simple !== false ? "Show all pages" : "Show fewer pages";
  }
  function setComfort(key, value) {
    comfort[key] = value; try { localStorage.setItem("cerebra-comfort", JSON.stringify(comfort)); } catch { /* not kept */ }
    applyComfort(); if (key === "simple" && data) render();  // Home shows or hides the coding steps
  }
  const simpleMenu = () => comfort.simple !== false;
  applyComfort();
  document.querySelectorAll("[data-comfort]").forEach(node => node.addEventListener("click", () => { const [key, value] = node.dataset.comfort.split(":"); setComfort(key, value); }));
  document.getElementById("menu-switch")?.addEventListener("click", () => setComfort("simple", comfort.simple === false));
  // Cerebra's own line icons: 16-unit grid, 1.4 stroke, square-ish geometry. Built with the DOM, never as HTML text.
  const ICONS = {
    home: [["path", "M2.5 7.5 8 3l5.5 4.5V13.5h-3.5V10h-4v3.5H2.5z"]],
    check: [["path", "M3 8.5l3 3 7-7"]],
    help: [["circle", 8, 8, 6], ["path", "M6.4 6.3a1.7 1.7 0 1 1 2.4 1.6c-.5.3-.8.6-.8 1.3"], ["path", "M8 11.2v.3"]],
    target: [["circle", 8, 8, 6], ["circle", 8, 8, 3], ["path", "M8 8h.01"]],
    mail: [["rect", 2, 3.5, 12, 9], ["path", "M2.5 4.5 8 9l5.5-4.5"]],
    search: [["circle", 7, 7, 4.5], ["path", "M10.4 10.4 14 14"]],
    money: [["rect", 1.5, 4, 13, 8], ["circle", 8, 8, 2], ["path", "M4 6.5v3M12 6.5v3"]],
    book: [["path", "M3 3.5A1.5 1.5 0 0 1 4.5 2H13v10H4.5A1.5 1.5 0 0 0 3 13.5z"], ["path", "M3 13.5A1.5 1.5 0 0 0 4.5 15H13v-3"]],
    shop: [["path", "M2.5 6h11l-1 8h-9z"], ["path", "M5.5 6V4.5a2.5 2.5 0 0 1 5 0V6"]],
    pin: [["path", "M8 14.5s4.5-4.3 4.5-8a4.5 4.5 0 0 0-9 0c0 3.7 4.5 8 4.5 8z"], ["circle", 8, 6.5, 1.6]],
    megaphone: [["path", "M2.5 6.5v3h2l5.5 3v-9l-5.5 3z"], ["path", "M12.5 6a3 3 0 0 1 0 4"]],
    grant: [["rect", 2.5, 6, 11, 8], ["path", "M2 3.5h12V6H2zM8 3.5V14"]],
    briefcase: [["rect", 2, 5, 12, 8.5], ["path", "M5.5 5V3h5v2M2 9h12"]],
    code: [["path", "M5.5 4.5 2 8l3.5 3.5M10.5 4.5 14 8l-3.5 3.5"]],
    folder: [["path", "M2 4h4.2l1.5 1.6H14v7.9H2z"]],
    chat: [["path", "M2.5 3h11v7.5h-6L4.5 13v-2.5h-2z"]],
    report: [["rect", 3, 2, 10, 12], ["path", "M5.5 5.5h5M5.5 8h5M5.5 10.5h3"]],
    clock: [["circle", 8, 8, 6], ["path", "M8 4.5V8l2.5 1.5"]],
    pulse: [["path", "M1.5 8.5h3l1.5-4 3 8 1.5-4h4"]],
    link: [["path", "M6.5 9.5l3-3"], ["path", "M7.3 4.3l1-1a2.6 2.6 0 0 1 3.7 3.7l-1 1"], ["path", "M8.7 11.7l-1 1A2.6 2.6 0 0 1 4 9l1-1"]],
    chip: [["rect", 4, 4, 8, 8], ["path", "M6 2v2M10 2v2M6 12v2M10 12v2M2 6h2M2 10h2M12 6h2M12 10h2"]],
    branch: [["circle", 4.5, 3.5, 1.5], ["circle", 4.5, 12.5, 1.5], ["circle", 11.5, 5, 1.5], ["path", "M4.5 5v6M11.5 6.5c0 3-7 2.2-7 4.5"]],
    tool: [["path", "M10.2 2.4a3 3 0 0 0-3 3.9L2.5 11l2.5 2.5 4.7-4.7a3 3 0 0 0 3.9-3l-2 2-2-.6-.6-2z"]],
    idcard: [["rect", 1.5, 3, 13, 10], ["circle", 5.5, 7.5, 1.6], ["path", "M3.3 11a2.4 2.4 0 0 1 4.4 0M9.5 6.5h3M9.5 9h3"]],
    gear: [["circle", 8, 8, 2.2], ["path", "M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6 5 5M11 11l1.4 1.4M3.6 12.4 5 11M11 5l1.4-1.4"]],
  };
  const PAGE_ICON = {overview: "home", approvals: "check", chat: "help", chief: "target", partners: "mail", jobs: "idcard", freelance: "search", money: "money", books: "book",
    etsy: "shop", prospects: "pin", marketing: "megaphone", funding: "grant", business: "briefcase", tasks: "code", projects: "folder", council: "chat",
    reports: "report", activity: "clock", system: "pulse", connections: "link", models: "chip", github: "branch", toolchain: "tool", settings: "gear"};
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16"); svg.setAttribute("fill", "none"); svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.4"); svg.setAttribute("stroke-linecap", "round"); svg.setAttribute("stroke-linejoin", "round"); svg.setAttribute("aria-hidden", "true");
    (ICONS[name] || []).forEach(([kind, ...values]) => {
      const shape = document.createElementNS("http://www.w3.org/2000/svg", kind);
      const names = {path: ["d"], circle: ["cx", "cy", "r"], rect: ["x", "y", "width", "height"]}[kind];
      names.forEach((attribute, index) => shape.setAttribute(attribute, values[index]));
      if (kind === "rect") shape.setAttribute("rx", "1");
      svg.append(shape);
    });
    return svg;
  }
  document.querySelectorAll(".nav-link[data-page]").forEach(node => { const spot = node.querySelector(".nav-icon"); const name = PAGE_ICON[node.dataset.page]; if (spot && name) spot.replaceChildren(icon(name)); });
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
  function date(value) { if (!value) return "—"; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"}); }
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
  function wireForm(form, submit, onSubmit) { const error = el("div", "form-error"); error.setAttribute("role", "alert"); error.tabIndex = -1; form.append(error); form.addEventListener("submit", async event => { event.preventDefault(); submit.disabled = true; error.textContent = ""; try { await onSubmit(); } catch (issue) { error.textContent = issue.message; error.focus(); } finally { submit.disabled = false; } }); }
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
    const [section, sectionName] = SECTIONS[eyebrow] || ["home", eyebrow];
    document.body.dataset.section = section;
    $("#page-eyebrow").textContent = sectionName; $("#page-title").textContent = title; $("#page-subtitle").textContent = subtitle;
    $("#breadcrumb-title").textContent = title;
    document.querySelectorAll("[data-page]").forEach(node => node.classList.toggle("active", node.dataset.page === page || (page === "report" && node.dataset.page === "reports") || (page === "job" && node.dataset.page === "business")));
    const actions = $("#heading-actions"); actions.replaceChildren();
    if (page === "tasks" || (page === "overview" && !simpleMenu())) actions.append(button("+ New task", () => taskForm(), "button primary"));
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
    const status = $("#agents-status"); status.className = `pill ${agentsOn() ? "good" : "warn"}`; status.replaceChildren(el("span", "dot"), document.createTextNode(agentsOn() ? (awayOn() ? "AI helpers: away mode" : "AI helpers: on") : "AI helpers: off")); status.title = awayOn() ? `Away mode until ${date(data.autopilot.until)}` : "";
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
    const views = {overview, council: councilView, connections: connectionView, business: businessView, money: moneyView, books: booksView, etsy: etsyView, chief: chiefView, prospects: prospectsView, partners: partnersView, jobs: jobsView, funding: fundingView, freelance: freelanceView, marketing: marketingView, job: jobView, chat: chatView, tasks: tasksView, projects: projectsView, approvals: approvalsView, system: systemView, reports: reportsView, report: reportView, activity: activityView, models: modelsView, github: githubView, toolchain: toolchainView, settings: settingsView};
    const result = views[page]();
    if (result) content.replaceChildren(result);
  }

  // ---------- overview ----------
  function customerWelcome(state) {
    const intro = append(el("div", "welcome-intro"), el("p", "eyebrow", "YOUR WORKSPACE"),
      el("h3", "welcome-title", "Make room for your next idea."),
      el("p", "welcome-description", "Bring your projects, choose your tools and keep your work in one place. Start with the basics; connect accounts when you need them."),
      button("Set up my workspace", () => customerSetupForm(state), "button primary"),
      el("p", "welcome-note", "Personal details are optional. Sharing and automation start off."));
    const routes = el("div", "welcome-routes");
    [["01", "Projects", "Add a folder when you’re ready to build.", "projects"],
     ["02", "AI accounts", "Connect the AI tools you choose.", "models"],
     ["03", "Connected accounts", "Use your own services and accounts.", "connections"]].forEach(([number, title, description, destination]) => {
      const item = link("", destination, "welcome-route");
      append(item, el("span", "welcome-number", number), append(el("span"), el("strong", "", title), el("small", "", description)), el("span", "welcome-arrow", "→"));
      routes.append(item);
    });
    const node = panel("Welcome to Cerebra", append(el("div", "welcome-layout"), intro, routes));
    node.classList.add("customer-welcome"); return node;
  }
  function customerSetupForm(state) {
    const profile = state.profile || {}, freelance = state.freelance || {}, options = state.options || {}, form = el("form", "workspace-setup"), save = submitButton("Save workspace setup");
    const name = input("Your name or business name (optional)", profile.name || ""), headline = input("What you do (optional)", profile.headline || ""),
      location = input("City and country (optional)", profile.location || ""), skills = input("Your skills, separated by commas", array(freelance.skills).join(", "));
    name.maxLength = 120; headline.maxLength = 200; location.maxLength = 120;
    const share = check("Share my profile details with AI tools when working on my requests", profile.share === true);
    const currency = select([["", "Choose a currency"], ...array(options.currencies).map(value => [value, value])], state.currency || ""); currency.required = true;
    const services = Object.entries(options.services || {}).map(([key, label]) => { const item = check(label, array(freelance.services).includes(key)); item.key = key; return item; });
    const sources = Object.entries(options.sources || {}).map(([key, label]) => { const item = check(label, freelance.sources?.[key] === true); item.key = key; return item; });
    const discovery = append(el("details", "setup-discovery"), el("summary", "", "Optional · Set up job discovery"),
      el("p", "row-meta", "Choose this if you want Cerebra to find freelance work. You can also configure it later on the Freelance page."));
    append(discovery, field("Your skills", skills, "Up to 12 skills, separated by commas. Only include work you can offer."),
      el("p", "row-meta", "Work categories"), append(el("div", "check-list"), ...services.map(item => item.wrap)),
      el("h3", "", "Public job sources"), el("p", "row-meta", "Selecting a source allows periodic public searches. Bidding, sending and AI execution require separate permission."),
      append(el("div", "check-list"), ...sources.map(item => item.wrap)));
    append(form, el("p", "setup-description", "A few preferences to make this workspace yours. You can change them later in Settings. Keep passwords and API keys out of this form."),
      append(el("div", "form-grid"), field("Display name", name), field("What you do", headline), field("Location", location), field("Business currency", currency, "Confirm the currency used for your business records.")),
      append(el("div", "setup-privacy"), share.wrap, el("small", "", "Off by default. Your profile is included in AI requests only if you choose to share it.")), discovery,
      actionsRow(button("Cancel", closeDialog, "button ghost"), save));
    wireForm(form, save, async () => {
      const selectedServices = services.filter(item => item.control.checked).map(item => item.key), selectedSources = sources.filter(item => item.control.checked).map(item => item.key);
      if (selectedSources.length && !selectedServices.length) throw new Error("Choose at least one kind of work before enabling job sources.");
      await mutate("/api/onboarding", {name: name.value.trim(), headline: headline.value.trim(), location: location.value.trim(), share_profile: share.control.checked,
        skills: skills.value.split(",").map(item => item.trim()).filter(Boolean), services: selectedServices, sources: selectedSources, currency: currency.value});
      closeDialog(); await refresh(true); toast("Workspace setup saved.");
    });
    showDialog("Set up your workspace", form);
  }
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
    if (!events.length) return body(empty("Your activity starts here", "Task updates and approvals appear here as you use your workspace.", null, "≡"));
    const list = el("div", "trace"); events.slice(0, limit).forEach(event => list.append(append(el("div"), el("time", "", date(event.created_at)), el("span", "k", event.kind), el("span", "", event.message)))); return list;
  }
  // Tell Cerebra what you want: it works out which workflow that is (rules first, a free model only when they can't tell)
  // and takes you there with your words filled in. Nothing starts until you confirm it there.
  function askBox() {
    const form = el("form", "ask-box"), text = input("Tell Cerebra what you want, e.g. Build a booking website for a cleaning company", ""), go = submitButton("Go");
    const answer = el("div");
    text.maxLength = 2000;
    append(form, append(el("div", "ask-row"), text, go), answer);
    wireForm(form, go, async () => {
      const result = await mutate("/api/understand", {text: text.value}, "POST", 120000);
      const open = button(`Open ${result.label}`, () => {
        if (result.workflow === "build") { taskForm("", text.value); return; }
        location.hash = result.page;
      }, "button primary");
      answer.replaceChildren(append(el("div", "ask-answer"), append(el("div"), el("strong", "", result.label), el("div", "row-meta", result.why)), el("p", "", result.about), actionsRow(open)));
    });
    return form;
  }
  // The big buttons at the top of Home: the everyday jobs, one click each.
  function homeTiles() {
    const waiting = pendingApprovals().length + finishedTasks().length;
    const tiles = [
      ["waiting", "check", "Waiting for my OK", waiting ? "Things to look at and approve" : "Nothing is waiting for you", "approvals", waiting],
      ["outreach", "mail", "Pitch companies", "Email companies about your services", "partners"],
      ["earn", "idcard", "Apply for jobs", "Tech jobs worldwide, a letter for each", "jobs"],
      ["earn", "search", "Find work", "Paid jobs that match your skills", "freelance"],
      ["earn", "money", "Money & invoices", "Quotes, invoices and what you've earned", "money"],
      ["earn", "book", "Write books", "Books for Amazon KDP", "books"],
      ["earn", "shop", "Sell on Etsy", "What sells, and listings to make", "etsy"],
      ["home", "help", "Ask for help", "Ask Cerebra anything in plain words", "chat"],
      ["setup", "gear", "Settings", "Accounts, text size and updates", "settings"],
    ];
    const box = el("div", "home-tiles");
    tiles.forEach(([kind, glyph, title, note, destination, count]) => {
      const tile = link("", destination, `home-tile ${kind}`);
      append(tile, append(el("span", "tile-icon"), icon(glyph)), append(el("span"), el("strong", "", title), el("span", "tile-note", note)), count ? el("span", "tile-count", count) : null);
      tile.setAttribute("aria-label", `${title}: ${note}`);
      box.append(tile);
    });
    return append(el("section"), el("h2", "home-question", "What would you like to do today?"), askBox(), box);
  }
  function overview() {
    const node = el("div"), tasks = realTasks(), active = tasks.filter(task => ACTIVE.includes(task.state)), setup = setupChecklist();
    node.append(homeTiles());
    if (data.onboarding?.needs_setup && !data.onboarding.existing_workspace) node.append(customerWelcome(data.onboarding));
    if (!setup.complete && !simpleMenu()) node.append(panel("Get started", body(el("p", "row-meta", "These steps apply when you want Cerebra to run a coding task. You can use other workspace tools before completing them."), setup.list)));
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
    const earn = data.earn || {};
    if (array(earn.today).length || array(earn.gaps).length) left.append(panel("Today", body(todayPanel(earn)), link("Freelance →", "freelance")));
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
    workRows.push(["Strong matches waiting", `${work.strong || 0} (score ${work.good || 50}+)`], ["Applied, waiting to hear", String(work.applied || 0)]);
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
  let taskStateFilter = "", taskProjectFilter = "";
  function tasksView() {
    const node = el("div"), filters = el("div", "form-grid"), projectFilter = select([["", "All projects"], ...array(data.projects).map(project => [project.id, project.name])], taskProjectFilter), stateFilter = select([["", "All states"], ["active", "Active (working now)"], ...[...new Set([...array(data.tasks).map(task => task.state), "FAILED", "COMPLETED"])].map(state => [state, nice(state)])], taskStateFilter);
    taskStateFilter = ""; taskProjectFilter = "";
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
    const specNotes = el("div"); let specBy = "";
    const architect = button("Ask the Prompt Architect", () => act(result => result.by === "template" ? "A short request: filled in from a template, no model needed." : `Spec written by ${result.model}. Check it before creating the plan.`,
      () => mutate("/api/architect", {project_id: project.value, objective: objective.value.trim()}, "POST", 600000)).then(result => {
        if (!result) return;
        specBy = result.by === "template" ? "template" : String(result.model || "Prompt Architect");
        requirements.value = array(result.requirements).join("\n"); criteria.value = array(result.acceptance_criteria).join("\n");
        const extra = [["Goal", [result.goal]], ["Constraints", result.constraints], ["Steps", result.steps], ["Open questions: decide these before you create the plan", result.open_questions],
          ["Assumptions it made: not added to the requirements", result.assumptions]].filter(([, items]) => array(items).filter(Boolean).length);
        specNotes.replaceChildren(...extra.map(([label, items]) => append(el("div", "hint"), el("strong", "", label), append(el("ul", "tips"), ...array(items).map(item => el("li", "", item))))));
      }), "button");
    form.insertBefore(append(el("div"), actionsRow(architect), hint("Turns your request into requirements and acceptance criteria for Claude, below. It never adds requirements on its own: what it had to assume is listed apart."), specNotes), form.children[3]);
    const submit = submitButton("Create plan"); form.append(actionsRow(button("Cancel", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      const lines = value => value.split("\n").map(item => item.trim()).filter(Boolean);
      const task = await mutate("/api/tasks", {...(specBy ? {spec_by: specBy} : {}), project_id: project.value, description: objective.value.trim(), planner: planner.value, implementer: implementer.value, reviewer: reviewer.value, requirements: lines(requirements.value), acceptance_criteria: lines(criteria.value), dependencies: [], allowed_paths: allowed.value.trim() ? allowed.value.split(",").map(value => value.trim()).filter(Boolean) : ["."]});
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
    const grid = el("div", "grid cards"), root = el("div"), glance = el("div");
    root.append(glance, grid);
    projectsAtAGlance(glance);
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
    return root;
  }
  // Every project in one table: what's working, what needs the owner, what's done or failed, and what the AI runs used.
  function projectsAtAGlance(holder) {
    const token = renderToken;
    api("/api/projects/summary").then(summary => {
      if (token !== renderToken || array(summary.projects).length < 2) return;  // one project: its card says it all
      const t = summary.totals, cell = (value, cls) => el("td", value ? cls || "" : "muted", String(value));
      const rows = summary.projects.map(item => {
        const name = el("td"), open = el("a", "", item.name);
        open.href = "#tasks"; open.addEventListener("click", () => { taskProjectFilter = item.id; });
        name.append(open);
        const level = select([["high", "High"], ["normal", "Normal"], ["low", "Low"]], item.priority || "normal");
        level.setAttribute("aria-label", `Priority for ${item.name}`);
        level.addEventListener("change", () => act(`${item.name}: ${level.value} priority. Its queued tasks start ${level.value === "high" ? "before" : level.value === "low" ? "after" : "alongside"} the others.`,
          () => mutate(`/api/projects/${encodeURIComponent(item.id)}/priority`, {priority: level.value}, "PUT")));
        return append(el("tr"), name, append(el("td"), level), cell(item.approvals, "attention"), cell(item.working), cell(item.queued), cell(item.stuck, "attention"),
          cell(item.done), cell(item.failed, "attention"), el("td", "", item.tokens ? tokens(item.tokens) : "—"), el("td", "muted", relative(item.last_activity)));
      });
      holder.replaceChildren(panel("All projects at a glance", body(
        hint(`${t.working} working, ${t.approvals} ${t.approvals === 1 ? "approval" : "approvals"} waiting for you, ${t.done} done and ${t.failed} failed across ${summary.projects.length} projects.`),
        append(el("div", "table-wrap"), append(el("table", "glance"), append(el("thead"), append(el("tr"), el("th", "", "Project"), el("th", "", "Priority"), el("th", "", "Needs you"), el("th", "", "Working"),
          el("th", "", "Queued"), el("th", "", "Stuck"), el("th", "", "Done"), el("th", "", "Failed"), el("th", "", "Tokens"), el("th", "", "Last activity"))), append(el("tbody"), ...rows))))));
    }).catch(() => {});
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
  // When automatic emails may go out (ai_hq/sendwindow.py): weekdays, during working hours on this computer's clock.
  function sendWindowFields(rules) {
    const hours = Array.from({length: 25}, (_, hour) => [String(hour), hour === 0 || hour === 24 ? "Midnight" : hour === 12 ? "Noon" : `${hour % 12} ${hour < 12 ? "am" : "pm"}`]);
    const on = check("Send automatic emails only on weekdays, during working hours: emails that arrive at night or at the weekend are buried by Monday", rules.business_hours !== false);
    const start = select(hours.slice(0, 24), String(rules.start_hour ?? 8)), end = select(hours.slice(1), String(rules.end_hour ?? 17));
    const node = append(el("div"), on.wrap, append(el("div", "form-grid"), field("From", start), field("Until", end)),
      hint("Research, drafting and reading replies carry on at any hour, and your own Send button always sends at once."));
    return {node, values: () => ({business_hours: on.control.checked, start_hour: Number(start.value), end_hour: Number(end.value)})};
  }
  // Tokens a task's AI runs used, as the providers reported them. The dollar figure is what the same work would cost at
  // list prices; the owner's subscription isn't charged per run.
  const tokens = count => count >= 1e6 ? `${(count / 1e6).toFixed(1)}M` : count >= 1e3 ? `${Math.round(count / 1e3)}k` : String(count);
  function usageLine(usage) {
    if (!usage || !usage.runs || !(usage.input_tokens || usage.output_tokens)) return null;
    return append(el("div", "usage"), el("h2", "", "What it used"),
      el("p", "", `${usage.runs} AI ${usage.runs === 1 ? "run" : "runs"}: ${tokens(usage.input_tokens + usage.cached_tokens)} tokens read, ${tokens(usage.output_tokens)} written.` +
        (usage.list_cost ? ` At list prices that would be $${usage.list_cost.toFixed(2)}; your subscription covers it.` : "")));
  }
  // Your verdict on a finished task: counted per coder model in Model intelligence, next to the test results.
  function feedbackBox(report) {
    if (!["COMPLETED", "FAILED", "CANCELLED"].includes(report.state)) return null;
    const box = el("div", "feedback"), mine = report.feedback;
    const rate = good => act("Thank you: noted.", () => mutate(`/api/tasks/${encodeURIComponent(param)}/feedback`, {good}, "POST"))
      .then(result => { if (result) box.replaceChildren(el("p", "", good ? "You rated this result good." : "You rated this result not good.")); });
    append(box, el("h2", "", "Was this result good?"), mine ? el("p", "", mine.good ? "You rated this result good." : "You rated this result not good.") : null,
      actionsRow(button("Yes, it was good", () => rate(true), "button"), button("No", () => rate(false), "button ghost")));
    return box;
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
        el("h2", "", "Where everything is saved"), saved, el("h2", "", "What happens next"), el("div", "next", report.next), usageLine(report.usage), feedbackBox(report));
      if (!["COMPLETED", "FAILED", "CANCELLED"].includes(report.state)) pageTimer = setTimeout(() => { if (token === renderToken) load(); }, 4000);
    }
    load(); return holder;
  }

  // ---------- activity ----------
  function activityView() { const events = array(data.events); return panel("Supervisor event log", activityList(events, 200), null, events.length); }

  // ---------- models & sign-in ----------
  // ---------- model intelligence: who does what, how each model measures up, and why tasks were routed ----------
  function specsTable(specs) {
    if (!array(specs).length) return hint("No finished tasks yet. Once tasks finish, this compares those that started from a Prompt Architect spec with those that didn't: how often they finished, finished first time, and how many repairs they needed.");
    return append(el("div", "table-wrap"), append(el("table"), append(el("thead"), append(el("tr"), el("th", "", "Spec written by"), el("th", "", "Finished tasks"), el("th", "", "Completed"), el("th", "", "First time, no repairs"), el("th", "", "Repairs per task"))),
      append(el("tbody"), ...specs.map(item => append(el("tr"), el("td", "", item.by), el("td", "", String(item.tasks)), el("td", "", `${item.completed_rate}%`), el("td", "", `${item.first_try_rate}%`), el("td", "", String(item.repairs_per_task)))))));
  }
  function intelligencePanel() {
    const box = el("div"); box.append(el("p", "row-meta", "Loading…"));
    (async () => {
      let state; try { state = await api("/api/models/intelligence"); } catch (issue) { box.replaceChildren(hint(issue.message, true)); return; }
      const policy = state.routing || {};
      // 1. The lead engineer.
      const lead = select([["claude", "Claude writes the code (Codex reviews)"], ["auto", "Automatic: Codex codes, Claude writes docs and reviews"]], policy.lead_coder || "claude");
      const lock = check("Keep Claude as the coder: when Claude runs out of usage, the task waits for it instead of moving to another model (you can still switch a task yourself)", policy.lock_coder !== false);
      const leadForm = el("form"), saveLead = submitButton("Save");
      append(leadForm, field("Who writes the code", lead), lock.wrap, actionsRow(saveLead));
      wireForm(leadForm, saveLead, async () => { await mutate("/api/routing", {mode: policy.mode || "rules", provider: policy.provider || "claude", model: policy.model || "opus", lead_coder: lead.value, lock_coder: lock.control.checked}, "PUT"); toast("Saved."); await refresh(true); });
      // 2. Each kind of work: who does it, how the models measured, a daily limit.
      const limits = {};
      const table = el("table"), head = el("thead"), rows = el("tbody");
      head.append(append(el("tr"), el("th", "", "Kind of work"), el("th", "", "Done by"), el("th", "", "Measured (last 30 days)"), el("th", "", "Today"), el("th", "", "Daily limit")));
      array(state.work).forEach(item => {
        const limit = input("0", item.daily_limit || 0, "number"); limit.min = 0; limit.max = 100000; limits[item.key] = limit;
        const best = array(item.measured)[0];
        const measured = best ? `${best.model}: ${best.success}% useful · ${best.seconds}s · ${best.calls} calls${array(item.measured).length > 1 ? ` (+${item.measured.length - 1} more)` : ""}` : "No calls yet";
        rows.append(append(el("tr"), append(el("td"), el("strong", "", item.label), el("div", "row-meta", item.about)),
          append(el("td"), el("div", "", item.in_use), item.in_use !== item.route ? el("div", "row-meta", `chosen on evidence (your choice: ${item.route})`) : null),
          append(el("td"), el("div", "", measured), item.recommended ? el("div", "row-meta", `Suggested: ${item.recommended}. ${item.recommendation}`) : el("div", "row-meta", item.recommendation)),
          el("td", "", String(item.today)), append(el("td"), limit)));
      });
      append(table, head, rows);
      const adaptive = check(`Route by measured performance: switch a kind of work to the model that has clearly done it best (needs ${state.min_calls} calls of evidence; free models only, never your Claude account)`, state.adaptive === true);
      const signedIn = button("Use my signed-in accounts (no OpenRouter)", () => act("Every kind of work now uses your Claude, Gemini or Qwen account.",
        () => mutate("/api/models/hub", {routes: Object.fromEntries(array(state.work).map(item => [item.key, item.default]))}, "PUT")).then(() => render()), "button");
      const saveWork = button("Save limits", () => act("Saved.", () => mutate("/api/models/hub", {adaptive: adaptive.control.checked,
        daily_calls: Object.fromEntries(Object.entries(limits).map(([key, control]) => [key, Number(control.value || 0)]))}, "PUT")), "button primary");
      // 3. Coding results per model, and recent routing decisions in plain words.
      const coding = array(state.coding).length ? append(el("table"), append(el("thead"), append(el("tr"), el("th", "", "Coder"), el("th", "", "Tasks"), el("th", "", "Completed"), el("th", "", "Failed"), el("th", "", "Your rating"))),
        append(el("tbody"), ...state.coding.map(item => append(el("tr"), el("td", "", item.model), el("td", "", String(item.tasks)), el("td", "", String(item.completed)), el("td", "", String(item.failed)), el("td", "", item.rated ? `${item.rated_good} of ${item.rated} good` : "Not rated"))))) : hint("No coding tasks yet.");
      const decisions = array(state.decisions).length ? append(el("ul", "tips"), ...state.decisions.slice(0, 8).map(item => el("li", "",
        `${item.task}: ${Object.entries(item.roles).map(([role, pick]) => `${role} ${pick.label}${pick.why ? ` (${pick.why})` : ""}`).join("; ")}`))) : hint("No tasks routed yet.");
      box.replaceChildren(
        ...array(state.regressions).map(item => hint(`Getting worse: ${item.message}`, true)),
        el("h4", "", "Lead engineer"), leadForm,
        el("h4", "", "Specialists"), hint("Each kind of work goes to one model: your Claude account, a free model or one on this computer. Choose them under Free models and routes below. Numbers come from real calls: how often a model gave a usable answer, and how fast."),
        append(el("div", "table-wrap"), table), adaptive.wrap, actionsRow(saveWork, signedIn),
        hint("Gemini and Qwen run as you, signed in with your own Google and Qwen accounts (install and sign in on this page and Install tools), read-only, within their free daily allowances. When one isn't signed in or has used today's allowance, your Claude account answers instead."),
        state.memory_gb ? hint(`This computer has ${state.memory_gb} GB of memory: local models larger than ${state.local_limit_gb} GB are never loaded, so it stays responsive.`) : null,
        el("h4", "", "Coding results by model"), append(el("div", "table-wrap"), coding),
        el("h4", "", "Do Prompt Architect specs help?"), specsTable(state.specs),
        el("h4", "", "Use per project"), projectUsage(state.projects),
        el("h4", "", "Check set"), checksPanel(state),
        el("h4", "", "Why recent tasks went where they did"), decisions, hint(state.subscription_note));
    })();
    return panel("Model intelligence", body(box));
  }
  // The fixed check set: questions with known answers per kind of work, run only when the owner presses the button.
  function checksPanel(state) {
    const label = key => (array(state.work).find(item => item.key === key) || {}).label || key;
    const rows = array(state.checks);
    const table = rows.length ? append(el("div", "table-wrap"), append(el("table"), append(el("thead"), append(el("tr"), el("th", "", "Kind of work"), el("th", "", "Model"),
      el("th", "", "Right answers"), el("th", "", "Last time"), el("th", "", "Checked"))),
      append(el("tbody"), ...rows.map(item => append(el("tr"), el("td", "", label(item.category)), el("td", "", item.route), el("td", "", `${item.score}%`),
        el("td", "", item.previous === null ? "—" : `${item.previous}%${item.previous_route !== item.route ? ` (${item.previous_route})` : ""}`), el("td", "muted", relative(item.at))))))) : hint("Not run yet.");
    const run = button("Run the check set", () => act(result => {
      const done = Object.values(result.results).filter(item => "score" in item);
      return `Checked ${done.length} kinds of work: ${done.reduce((sum, item) => sum + item.passed, 0)} of ${done.reduce((sum, item) => sum + item.total, 0)} answers right.`;
    }, () => mutate("/api/models/checks", {}, "POST", 600000)).then(result => { if (result) render(); }), "button");
    return append(el("div"), hint("Short questions with known answers, checked by Cerebra's own rules. Run it after changing a model to see whether the new one does better. It uses about 12 calls from your free allowances and runs only when you press the button."), table, actionsRow(run));
  }
  function projectUsage(rows) {
    if (!array(rows).length) return hint("No AI runs yet.");
    return append(el("div"), append(el("div", "table-wrap"), append(el("table"), append(el("thead"), append(el("tr"), el("th", "", "Project"), el("th", "", "Tasks"), el("th", "", "AI runs"),
      el("th", "", "Tokens read"), el("th", "", "Tokens written"), el("th", "", "At list prices"))),
      append(el("tbody"), ...rows.map(item => append(el("tr"), el("td", "", item.project), el("td", "", String(item.tasks)), el("td", "", String(item.runs)),
        el("td", "", tokens(item.input_tokens + item.cached_tokens)), el("td", "", tokens(item.output_tokens)), el("td", "", item.list_cost ? `$${item.list_cost.toFixed(2)}` : "Not reported")))))),
      hint("Claude reports what each run would cost at list prices; your subscription covers it, so nothing is charged per run. Codex reports tokens only."));
  }
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
    append(how, hint("When a role is set to Auto, the supervisor rates how hard the task is and picks a model: frontier models for hard work, balanced for everyday work, fast ones for small jobs. Claude plans and codes (your lead engineer); Codex reviews, from another company. The reviewer always comes from the other company."), field("How the supervisor decides", mode), brainField);
    const saveHow = submitButton("Save"); how.append(actionsRow(saveHow));
    wireForm(how, saveHow, async () => { const [provider, model] = brain.value.split(":"); await mutate("/api/routing", {mode: mode.value, provider, model}, "PUT"); await refresh(true); toast(mode.value === "model" ? "The supervisor model will now pick the AI team." : "The supervisor's rules will pick the AI team."); });
    root.append(panel("Supervisor: who picks the models", body(how)));
    root.append(intelligencePanel());

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
      if (state.catalog_loading) setTimeout(() => { if (root.isConnected) root.replaceWith(hubPanel()); }, 3000);  // fill in the free models once they've arrived
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
        state.catalog_loading ? hint("Loading today's free models from OpenRouter… this page fills them in by itself.") : null,
        table(["Kind of work", "Uses", ""], routes.map(([label, pick, test]) => [label, pick, test || ""])),
        hint("Free models allow about 20 requests a minute and 50 a day on an account that never bought credits, and they come and go: each request names free backups. Writing in your name and planning stay on your Claude account by default, for quality."),
        array(state.local_models).length ? hint(`On this computer (free, no daily limit): ${state.local_models.join(", ")}.`)
          : hint("Models on your own computer are free with no daily limit (DeepSeek, Qwen, Llama, Gemma…). Open Ollama, then pull one in a terminal, for example: ollama pull deepseek-r1:8b . It appears here when ready. A 7-8B model needs about 8 GB of memory."),
        usage.length ? append(el("div"), el("h4", "", "This month"), table(["Kind of work", "Model", "Calls", "Cost"], usage.map(item => [item.category, item.model, String(item.calls), `$${item.cost.toFixed(2)}`]))) : null);
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
    async function connectGithub() {
      if (!await act(result => result.message, () => mutate("/api/github/sign-in"))) return;
      let tries = 0;
      const look = async () => {  // about five minutes, for as long as this page is open
        if (page !== "github" || ++tries > 100) return;
        try { if ((await api("/api/github", {timeout: 60000})).signed_in) { toast("GitHub connected."); cache.repos = null; return loadAccount(); } } catch (issue) { /* try again */ }
        setTimeout(look, 3000);
      };
      setTimeout(look, 3000);
    }
    async function loadAccount() {
      account.replaceChildren(el("div", "loading", "checking GitHub…"));
      try { cache.github = await api("/api/github", {timeout: 60000}); } catch (issue) { account.replaceChildren(body(hint(issue.message, true))); return; }
      if (token !== renderToken) return; const status = cache.github;
      if (!status.installed) { account.replaceChildren(body(empty("GitHub CLI is not installed", "Cerebra talks to GitHub through the official GitHub CLI.", link("Install it from Toolchain →", "toolchain", "button primary"), "⑂"))); return; }
      if (!status.signed_in) { account.replaceChildren(body(empty("Not connected", "Sign in once; GitHub's own window handles your password and two-factor code.", button("Connect GitHub", connectGithub, "button primary"), "⑂"), append(el("div", "actions"), button("Check again", loadAccount, "button small")))); return; }
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
       ["Posted", count("posted") + count("partial"), "on your channels", "green"], ["X this month", `$${Number(state.spent_this_month || 0).toFixed(2)}`, `of your $${Number(limits.monthly_cap).toFixed(2)} budget`, ""]]
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
    Object.entries(post.results || {}).forEach(([channel, result]) => root.append(hint(`${state.channels[channel]}: ${result.posted_at ? `posted ${relative(result.posted_at)}${result.cost ? ` · $${result.cost}` : ""}${result.url ? ` · ${result.url}` : ""}` : result.error || result.waiting}`, !!result.error)));
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
        el("div", "row-meta", [goal.rules.public_data_only ? "public data only" : "", goal.rules.ask_before_contact ? "asks before contacting anyone" : "", goal.monthly_cap ? `spend at most $${goal.monthly_cap} a month` : ""].filter(Boolean).join(" · "))),
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
  const CALL_ICON = {plan: "◈", approval: "✋", award: "★", proposal: "✎", post: "✉", overdue: "!", invoice: "¤", book: "▤", problem: "⚠", rare: "⚡", followup: "↻"};
  function callList(items, emptyText = "Nothing waits for you.") {
    if (!array(items).length) return body(empty("All clear", emptyText, null, "✓"));
    const list = el("div", "row-list");
    array(items).forEach(item => { const row = append(el("a", "row clickable"), el("span", "call-icon", CALL_ICON[item.kind] || "•"), append(el("div", "row-main"), el("strong", "", item.title), el("div", "row-meta", item.detail)), el("span", "row-meta", relative(item.at)));
      row.href = `#${item.page}`; list.append(row); });
    return list;
  }
  // The money first: the jobs worth applying to now, and what still stands between the owner and the automation.
  function pickRows(items) {
    const list = el("div", "row-list");
    array(items).forEach(item => {
      const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", item.title),
        el("div", "row-meta", [item.rare ? "rare chance" : "", item.ready ? "proposal ready to send" : "", item.committee === "bid" ? "the committee says bid" : "", item.why].filter(Boolean).join(" · "))), scoreBadge(item.score));
      row.tabIndex = 0; row.setAttribute("role", "button");
      const open = () => act("", () => refreshLead(item.id)).then(result => { if (result) leadDialog(...result); });
      row.addEventListener("click", open); row.addEventListener("keydown", event => { if (event.key === "Enter") open(); });
      list.append(row);
    });
    return list;
  }
  function todayPanel(earn) {
    const root = el("div");
    root.append(el("h4", "", "Apply today"), array(earn.today).length ? pickRows(earn.today) : hint("No strong match is open right now. New work is checked all day."));
    if (array(earn.gaps).length) {
      const gaps = el("div", "row-list");
      array(earn.gaps).forEach(gap => { const row = append(el("a", "row clickable"), append(el("div", "row-main"), el("strong", "", gap.title), el("div", "row-meta", gap.why)), el("span", "row-meta", "Set up →"));
        row.href = `#${gap.page}`; gaps.append(row); });
      root.append(el("h4", "", `Ready to earn: ${earn.gaps.length} step${earn.gaps.length === 1 ? "" : "s"} left`), gaps);
    }
    return root;
  }
  function briefPanel(state) {
    const settings = state.settings || {}, root = el("div"), on = check("Send me a morning brief", settings.brief !== false);
    const hour = select(Array.from({length: 24}, (_, value) => [String(value), `${String(value).padStart(2, "0")}:00`]), String(settings.brief_hour ?? 8));
    on.control.addEventListener("change", () => act("Saved.", () => mutate("/api/chief/settings", {brief: on.control.checked}, "PUT")));
    hour.addEventListener("change", () => act("Saved.", () => mutate("/api/chief/settings", {brief_hour: Number(hour.value)}, "PUT")));
    const brief = state.brief || {}, picks = pickRows(brief.today);
    append(root, array(brief.first).length ? append(el("div"), el("h4", "", "First, what can't wait"), callList(brief.first)) : null,
      append(el("div"), el("h4", "", "Apply today"), array(brief.today).length ? picks : hint("No strong match is open right now. New work is checked all day.")),
      append(el("div"), el("h4", "", "Overnight"), append(el("ul", "tips"), ...array(brief.lines).map(line => el("li", "", line)))), append(el("div", "form-grid"), field("At", hour), on.wrap),
      actionsRow(button("Send it to my phone now", () => act(result => result.sent ? "Sent." : "Recorded. Set up phone notifications in Settings to receive it.", () => mutate("/api/chief/brief/send", {})), "button small")),
      hint("On your phone it gives counts and the top pick's score only: phone notifications can pass through a public server, so job titles, names and amounts stay in Cerebra."));
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

  // ---------- company pitches: the owner's service offered to companies by email (ai_hq/partners.py) ----------
  const PARTNER_STAGE = {new: ["not read yet", "muted"], ready: ["ready to pitch", "blue"], forms: ["apply on their site", "amber"], none: ["no contact found", "muted"],
    unreadable: ["site not readable", "muted"], sent: ["pitched", "cyan"], followed_up: ["followed up", "cyan"], replied: ["replied", "green"], opted_out: ["said no", "muted"],
    bounced: ["bounced", "red"], applied: ["you applied", "green"], dropped: ["dropped", "muted"], skipped: ["can't receive email", "muted"]};
  let partnerFilter = "ready";
  function partnerBadge(status) { const [label, style] = PARTNER_STAGE[status] || [status, "muted"]; return badge(label, style); }
  function partnersView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading…")));
    (async () => {
      let state; try { state = await api("/api/partners"); } catch (issue) { root.replaceChildren(body(empty("Company pitches unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const counts = state.counts || {}, rules = state.settings || {}, search = state.search || {}, stats = el("div", "grid stats");
      [["Companies listed", state.total || 0, `${counts.new || 0} not read yet · ${state.big_tech || 0} big tech · ${state.researched || 0} researched`, "blue"], ["Ready to pitch", counts.ready || 0, "a public role address", "cyan"],
       ["Apply on their site", counts.forms || 0, "application pages to open", "amber"], ["Pitched", (counts.sent || 0) + (counts.followed_up || 0), `${state.sent_today} of ${state.limit} today`, "blue"],
       ["Replied", counts.replied || 0, "answer from your Gmail", "green"]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      if (search.running) setTimeout(() => { if (token === renderToken) render(); }, 4000);
      // 1. the pitch
      const form = el("form", "partner-pitch"), save = submitButton("Save");
      const subject = input("Subject, e.g. Translation and language data for {company}", rules.subject || ""),
        text = textarea("Hello {company} team,\n\nWho you are, what you offer, why it helps them, and one easy next step (a free sample, a short call).\n\nThank you,", rules.body || ""),
        followUp = textarea("Your follow-up", rules.follow_up || state.default_follow_up || ""), perDay = input("10", rules.per_day ?? 10, "number"), days = input("6", rules.follow_up_days ?? 6, "number");
      subject.maxLength = 150; text.rows = 10; followUp.rows = 4; perDay.min = 1; perDay.max = state.max_per_day; days.min = 0; days.max = 30;
      const tailor = check("Tailor each email to its company: Cerebra reads what the company says about itself on its own website, and your writing model adds a short paragraph on their work and how you help it", rules.personalize !== false);
      const bigSubject = input("Subject for big tech, e.g. Kiswahili and African-language training data for {company}'s AI", rules.big_subject || ""),
        bigText = textarea("Your email to big tech companies and AI labs (Google, Microsoft, Meta, OpenAI, Anthropic…). Leave empty to send them the pitch above.", rules.big_body || "");
      bigSubject.maxLength = 150; bigText.rows = 8;
      const kinds = Object.entries(state.industries || {}).map(([key, label]) => { const box = check(label, array(rules.industries || ["ai"]).includes(key)); box.control.value = key; return box; });
      const pitchWindow = sendWindowFields(rules);
      const on = check("Work on its own: find and study companies, and send my pitch", rules.enabled === true),
        mode = select([["send", "Send each pitch automatically"], ["review", "Only when I press Send (follow-ups wait too)"]], rules.mode || "send");
      append(form, field("Subject", subject, "{company} becomes each company's name, {website} its web address."),
        field("Your email", text, "Put {personal} where each company's own paragraph should go; without it, the paragraph goes after your greeting."), tailor.wrap,
        field("Big tech and AI labs: subject", bigSubject), field("Big tech and AI labs: your email", bigText, "Used for the big tech companies and AI labs in your list. {personal} works here too."),
        field("Follow-up (sent once, in the same thread, if nobody answers)", followUp),
        append(el("div"), el("strong", "", "Kinds of companies to find"), append(el("div", "check-list"), ...kinds.map(box => box.wrap))),
        append(el("div", "form-grid"), field("Pitches a day", perDay, "Gmail's own limit applies: about 500 a day on a personal Gmail, 2,000 on Google Workspace."),
          field("Follow up after (days, 0 for none)", days), field("Sending", mode)), pitchWindow.node,
        on.wrap, Object.assign(hint(`Added under every email (US law needs your postal address and an opt-out):\n${state.signature || ""}`), {style: "white-space: pre-line"}), actionsRow(save,
          button("Run once now", () => act(result => result.message || result.skipped || "Done.", () => mutate("/api/partners/run", {}, "POST", 600000)).then(() => render()), "button ghost")));
      wireForm(form, save, async () => {
        await mutate("/api/partners", {subject: subject.value, body: text.value, follow_up: followUp.value, per_day: Number(perDay.value || 10), follow_up_days: Number(days.value || 0),
          mode: mode.value, enabled: on.control.checked, personalize: tailor.control.checked, big_subject: bigSubject.value, big_body: bigText.value,
          industries: kinds.filter(box => box.control.checked).map(box => box.control.value), ...pitchWindow.values()}, "PUT");
        toast(on.control.checked ? "Saved. Company pitches are on." : "Saved."); render();
      });
      const before = array(state.ready).length ? panel("Before a pitch can go out", body(append(el("ul", "tips"), ...state.ready.map(item => el("li", "", item))),
        actionsRow(link("Business connections →", "connections"), link("Money › Your business →", "money")))) : null;
      const status = state.status?.message ? hint(`Last run ${state.status.at ? date(state.status.at) : ""}: ${state.status.message}`, state.status.state === "error") : null;
      const paused = state.health?.paused ? append(el("div"), hint(state.health.reason, true),
        actionsRow(button("Resume sending", () => act("Resumed.", () => mutate("/api/partners/resume", {}, "POST")).then(() => render()), "button small primary"))) : null;
      const preview = state.preview ? append(el("div"), el("div", "row-meta", `To ${state.preview.company} (${state.preview.to}) · Subject: ${state.preview.subject}${state.preview.tailored ? " · tailored to them" : rules.personalize !== false ? " · its own paragraph is written just before sending" : ""}`),
        el("pre", "code-block", state.preview.body)) : null;
      // 2. the companies
      const find = button(state.total ? "Find more companies" : "Find companies and their emails", () => act(result => result.message, () => mutate("/api/partners/find", {})).then(() => render()), "button primary");
      const more = button("Read 40 more websites", () => act(result => result.message, () => mutate("/api/partners/find", {find: false})).then(() => render()), "button");
      const next = button(`Send to the next ${Math.min(5, counts.ready || 0) || 5} now`, () => act(result => result.message, () => mutate("/api/partners/send-next", {count: 5}, "POST", 600000)).then(() => render()), "button");
      find.disabled = more.disabled = !!search.running; next.disabled = !(counts.ready > 0);
      const review = button(`Review ready emails (${state.drafts_ready || 0})`, () => draftsDialog(), state.drafts_ready ? "button primary" : "button");
      const showOffered = button(`Offered me something (${state.offered || 0})`, () => { partnerFilter = "offered"; render(); }, partnerFilter === "offered" ? "button primary" : "button");
      const showNotOffered = button(`Not offered (${state.not_offered || 0})`, () => { partnerFilter = "not_offered"; render(); }, partnerFilter === "not_offered" ? "button primary" : "button");
      const readAll = button("Read the replies", () => act(result => result.read ? `Read ${result.read} repl${result.read === 1 ? "y" : "ies"}.` : "No new replies to read.", () => mutate("/api/partners/read-replies", {}, "POST", 600000)).then(() => render()), "button ghost");
      const addForm = el("form"), addGo = submitButton("Add"), addName = input("Company name"), addSite = input("Website, e.g. example.com");
      addName.required = addSite.required = true;
      append(addForm, append(el("div", "form-grid"), field("Company", addName), field("Website", addSite)), actionsRow(addGo));
      wireForm(addForm, addGo, async () => { await mutate("/api/partners/add", {name: addName.value, website: addSite.value}); toast("Added. Its website is read on the next run, or press Read 40 more websites."); render(); });
      const filters = {offered: `Offered me something (${state.offered || 0})`, not_offered: `Not offered (${state.not_offered || 0})`, ready: `Ready to pitch (${counts.ready || 0})`, forms: `Apply on their site (${counts.forms || 0})`, pitched: "Pitched", replied: "Replied or said no", applied: "You applied",
        new: `Not read yet (${counts.new || 0})`, none: "No contact found", all: "Everything"};
      const pick = select(Object.entries(filters), partnerFilter); pick.addEventListener("change", () => { partnerFilter = pick.value; render(); });
      const groups = {pitched: ["sent", "followed_up"], none: ["none", "unreadable", "skipped", "dropped"], replied: ["replied", "opted_out", "bounced"]};
      const offered = item => item.status === "replied" && item.reply?.verdict === "offered";
      const pitchedStages = ["sent", "followed_up", "replied", "opted_out", "bounced"];
      const shown = array(state.companies).filter(item => partnerFilter === "all" ? true : partnerFilter === "offered" ? offered(item)
        : partnerFilter === "not_offered" ? pitchedStages.includes(item.status) && !offered(item) : (groups[partnerFilter] || [partnerFilter]).includes(item.status));
      const list = el("div", "row-list");
      shown.slice(0, 300).forEach(item => {
        const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", item.name), el("div", "row-meta", [item.domain, item.source, item.kind === "big_tech" ? "big tech" : "", item.personal ? "tailored" : ""].filter(Boolean).join(" · ")),
          (item.summary || item.about) ? el("div", "row-meta", (item.summary || item.about).slice(0, 160)) : null,
          el("div", "row-meta", item.email ? `✉ ${item.email}` : array(item.pages).length ? `${item.pages.length} application page(s): ${item.pages.map(page => page.label).slice(0, 3).join(", ")}` :
            item.notes || (item.status === "new" ? "Its website is read next" : "No public role address")),
          item.reply?.snippet ? el("div", "row-meta", `↩ ${(item.reply.summary || item.reply.snippet).slice(0, 160)}`) : null),
          item.reply?.verdict === "offered" ? badge("offer", "green") : item.reply?.verdict === "declined" ? badge("said no", "muted") : partnerBadge(item.status));
        row.addEventListener("click", () => partnerDialog(item, state)); list.append(row);
      });
      root.replaceChildren(stats, before, paused, status,
        append(el("div", "grid two"),
          append(el("div"),
            panel("Companies", append(el("div"), body(append(el("div", "actions"), review, showOffered, showNotOffered, readAll),
              hint("Every company that replies is never pitched again. Offers get a reply drafted for you to read and send; a no stops there."),
              append(el("div", "actions"), find, more, next, pick),
              search.message ? hint(search.running ? `${search.message} This page refreshes itself.` : search.message) : null),
              shown.length ? list : body(empty(state.total ? "Nothing here" : "No companies yet", "Press Find companies: Cerebra lists AI, language-data and translation companies (a starter list, then Wikidata), then reads each one's own website for a public role address such as partnerships@ or vendors@, and for its pages for vendors, linguists and contributors.", null, "✉"))), null, shown.length),
            panel("Add a company you know", body(addForm))),
          append(el("div"), panel("Your pitch", body(form)), preview ? panel("How the next one reads", body(preview)) : null, marketFactsPanel(),
            panel("How it works", body(hint("Only a company's own role addresses are used (partnerships@, vendors@, hello@, info@…), never a person's own address, and nothing is guessed. Each email goes from your Gmail with your name, postal address and an opt-out line. One follow-up at most; a reply stops it and tells you; “no thanks” or a bounce means that company is never written to again. Many companies take vendors and linguists only through a form: open the page, apply yourself, and mark it applied. Cerebra never fills in forms."))))));
    })();
    return root;
  }
  function withPersonal(text, personal) {  // the same rule as partners.with_personal
    personal = String(personal || "").trim(); text = String(text || "");
    if (text.includes("{personal}")) return text.replaceAll("{personal}", personal).replace(/\n{3,}/g, "\n\n");
    if (!personal) return text;
    const trimmed = text.trim(), at = trimmed.indexOf("\n\n");
    return at < 0 ? `${personal}\n\n${trimmed}` : `${trimmed.slice(0, at)}\n\n${personal}\n\n${trimmed.slice(at + 2)}`;
  }
  function marketFactsPanel() {
    // The only figures besides a company's own that a pitch may use: each needs its source.
    const box = el("div"), list = el("div");
    const rowFor = (item = {}) => {
      const fact = input("What, e.g. Kiswahili speakers", item.fact || ""), figure = input("Figure, e.g. over 100 million", item.figure || ""), source = input("Source, e.g. UNESCO", item.source || "");
      const line = append(el("div", "form-grid"), field("Fact", fact), field("Figure", figure), field("Source", source));
      line.read = () => ({fact: fact.value, figure: figure.value, source: source.value});
      return line;
    };
    const save = button("Save market facts", () => act("Saved.", () => mutate("/api/partners/market-facts", {facts: [...list.children].map(line => line.read())}, "PUT")), "button small primary");
    const add = button("Add a fact", () => list.append(rowFor()), "button small ghost");
    api("/api/partners/market-facts").then(result => array(result.facts).forEach(item => list.append(rowFor(item)))).catch(() => {});
    append(box, hint("Pitches may only use figures from a company's own research or from this list, and every figure is checked before an email goes. Keep each one with where it comes from; clear a fact's boxes and save to remove it."), list, actionsRow(add, save));
    return panel("Market facts for your pitches", body(box));
  }
  function researchBlock(item) {
    const box = el("div"); box.append(el("p", "row-meta", "Loading what Cerebra has learned about them…"));
    api(`/api/partners/${item.id}/research`).then(found => {
      const facts = found.dossier || {}, read = array(found.pages).filter(page => page.readable);
      const list = (label, values) => array(values).length ? el("div", "row-meta", `${label}: ${values.join("; ")}`) : null;
      box.replaceChildren(
        facts.summary ? el("p", "", facts.summary) : hint(read.length ? `${read.length} page(s) of their website read so far; the summary is written once enough is in.` : "Their website hasn't been studied yet: it is read a few pages at a time, the companies about to be pitched first."),
        list("Products", facts.products), list("AI work", facts.ai_work), list("Languages", facts.languages), list("Markets", facts.markets),
        list("Africa", facts.africa), list("Hiring", facts.hiring), list("Priorities", facts.priorities),
        array(facts.facts).length ? append(el("ul", "tips"), ...facts.facts.map(fact => el("li", "", `${fact.fact} (${fact.url})`))) : null,
        read.length ? el("div", "row-meta", `From ${read.length} page(s) of their own website${found.dossier_at ? `, summarised ${date(found.dossier_at)}` : ""}.`) : null);
    }).catch(issue => box.replaceChildren(hint(issue.message, true)));
    return box;
  }
  // Every ready email written out in full: untick any you don't want, then send the rest with one click.
  function draftsDialog() {
    const box = el("div"); box.append(el("p", "", "Loading the emails ready to go…"));
    showDialog("Ready emails", box);
    const draw = async () => {
      let state; try { state = await api("/api/partners/drafts"); } catch (issue) { box.replaceChildren(hint(issue.message, true)); return; }
      const drafts = array(state.drafts), ticks = [];
      const prepare = button("Write the next 5", () => act(result => result.message, () => mutate("/api/partners/prepare", {count: 5}, "POST", 900000)).then(draw), "button");
      const list = el("div", "row-list");
      drafts.forEach(item => {
        const tick = el("input"); tick.type = "checkbox"; tick.checked = true; tick.value = item.id; ticks.push(tick);
        const head = append(el("label", "draft-head"), tick, append(el("span"), el("strong", "", item.name), el("span", "row-meta", ` · to ${item.to}${item.big_tech ? " · big tech pitch" : ""}`)));
        const text = el("details", "draft-text"); append(text, el("summary", "", `Subject: ${item.subject}`), el("pre", "code-block", item.body));
        list.append(append(el("div", "row draft-row"), append(el("div", "row-main"), head, text)));
      });
      const count = () => ticks.filter(tick => tick.checked).length;
      const send = button("", () => {
        const ids = ticks.filter(tick => tick.checked).map(tick => tick.value);
        act(result => result.message, () => mutate("/api/partners/send-drafts", {ids}, "POST", 900000)).then(result => { if (result) { closeDialog(); render(); } });
      }, "button primary");
      const label = () => { const n = count(); send.textContent = n ? `Send all ${n} selected` : "Nothing selected"; send.disabled = !n; };
      ticks.forEach(tick => tick.addEventListener("change", label)); label();
      const all = button("Select all", () => { ticks.forEach(tick => { tick.checked = true; }); label(); }, "button small ghost");
      const none = button("Select none", () => { ticks.forEach(tick => { tick.checked = false; }); label(); }, "button small ghost");
      box.replaceChildren(
        el("p", "", drafts.length ? `${drafts.length} email(s) ready. Open any one to read it in full; untick the ones you don't want to send.` : "No emails are written yet."),
        hint(`Today you can still send ${state.room_today}. Anything over that waits for tomorrow, to protect your Gmail.` +
          (state.waiting_to_be_written ? ` ${state.waiting_to_be_written} more companies are in line: press Write the next 5 to prepare their emails.` : "")),
        drafts.length ? actionsRow(all, none) : null, drafts.length ? list : null, actionsRow(prepare, drafts.length ? send : null));
    };
    draw();
  }
  function replyBlock(item) {
    const reply = item.reply || {}, box = el("div");
    const verdict = {offered: ["They made you an offer", "green"], declined: ["They said no: nothing more is sent", "muted"], unclear: ["No offer in it", "amber"]}[reply.verdict];
    const readIt = button(reply.verdict ? "Read it again" : "Read their reply", () => act("Read.", () => mutate(`/api/partners/${item.id}/read-reply`, {again: !!reply.verdict}, "POST", 300000))
      .then(result => { if (result) { item.reply = result; box.replaceChildren(...replyBlock(item).childNodes); } }), "button small");
    append(box, el("h4", "", "Their reply"), verdict ? badge(verdict[0], verdict[1]) : hint("Not read yet: press Read their reply."),
      reply.summary ? el("p", "", reply.summary) : null, el("pre", "code-block", reply.body || reply.snippet || ""), actionsRow(readIt));
    if (reply.answered_at) append(box, hint(`You answered on ${date(reply.answered_at)}.`), el("pre", "code-block", reply.answer || ""));
    else if (reply.verdict === "offered") {
      const text = textarea("Your reply", reply.draft || ""); text.rows = 8;
      const send = button("Send my reply from Gmail", () => act(result => result.message, () => mutate(`/api/partners/${item.id}/answer`, {text: text.value}, "POST", 120000))
        .then(result => { if (result) { closeDialog(); render(); } }), "button primary");
      append(box, field("Your reply (drafted for you: read and change it before sending)", text, reply.draft ? "Nothing is sent until you press Send." : "Write your answer here."), actionsRow(send));
    }
    return box;
  }
  function partnerDialog(item, state) {
    const rules = state.settings || {}, fill = value => String(value || "").replaceAll("{company}", item.name).replaceAll("{website}", item.domain || item.website);
    const big = item.kind === "big_tech" && rules.big_subject && rules.big_body;
    const pitchSubject = big ? rules.big_subject : rules.subject, pitchBody = big ? rules.big_body : rules.body;
    const to = input("Their email", item.email || ""), subject = input("Subject", fill(pitchSubject)), text = textarea("Your email", fill(withPersonal(pitchBody, item.personal))), notes = textarea("Notes", item.notes || "");
    const personal = textarea("A short paragraph about their work and how you help it", item.personal || "");
    text.rows = 10; notes.rows = 2; personal.rows = 3;
    const refill = value => { text.value = fill(withPersonal(pitchBody, value)); };
    const writeIt = button(item.personal ? "Write it again" : "Research them and write it", () => act("Written from their website.", () => mutate(`/api/partners/${item.id}/tailor`, {again: !!item.personal}, "POST", 300000))
      .then(result => { if (result) { personal.value = result.personal; item.personal = result.personal; refill(result.personal); } }), "button small");
    const keep = button("Use my edit", () => act("Saved.", () => mutate(`/api/partners/${item.id}`, {personal: personal.value}, "PATCH")).then(result => { if (result) { item.personal = result.personal; refill(result.personal); } }), "button small ghost");
    const open = url => act("Opened in your browser.", () => mutate(`/api/partners/${item.id}/open`, {url}));
    const pages = append(el("div", "actions"), button("Open their website", () => open(item.website), "button small"),
      ...array(item.pages).map(page => button(page.label || "Application page", () => open(page.url), "button small")));
    const sentAlready = ["sent", "followed_up", "replied", "opted_out", "bounced"].includes(item.status);
    const send = button("Send with Gmail", () => act(result => result.message, () => mutate(`/api/partners/${item.id}/send`, {to: to.value.trim(), subject: subject.value, text: text.value}, "POST", 120000))
      .then(result => { if (result) { closeDialog(); render(); } }), "button primary");
    const mark = status => act("Saved.", () => mutate(`/api/partners/${item.id}`, {status, notes: notes.value}, "PATCH")).then(result => { if (result) { closeDialog(); render(); } });
    showDialog(item.name, append(el("div"), el("div", "row-meta", [item.domain, item.source].filter(Boolean).join(" · ")), partnerBadge(item.status),
      el("h4", "", "What Cerebra has learned about them"), researchBlock(item),
      el("h4", "", "Their website and application pages"), pages,
      array(item.emails).length > 1 ? hint(`Other role addresses on their site: ${item.emails.filter(value => value !== item.email).join(", ")}`) : null,
      sentAlready ? append(el("div"), el("h4", "", "What was sent"), ...array(item.sent).map(mail => append(el("div"), el("div", "row-meta", `${date(mail.at)}${mail.follow_up ? " · follow-up" : ""}: ${mail.subject}`), el("pre", "code-block", mail.body))),
        item.reply?.snippet ? replyBlock(item) : null) :
        append(el("div"), el("h4", "", "Email them"), field("To", to, item.email ? "Their public role address, from their own website." : "No role address on their site: type one you know, or apply on their page above."),
          field(`Tailored to ${item.name}`, personal, item.personal ? "Written from what their own website says. Edit it if you like, then press Use my edit." : "Not written yet: it's written from their website just before an automatic send, or press the button now."),
          actionsRow(writeIt, keep), field("Subject", subject), field("Your email", text, "Your name, postal address and an opt-out line are added under it."), actionsRow(send)),
      field("Notes", notes), actionsRow(button("Mark as applied", () => mark("applied"), "button"), !sentAlready ? button("Drop it", () => mark("dropped"), "button ghost") : null,
        ["dropped", "applied"].includes(item.status) && !sentAlready ? button("Put back in line", () => mark("ready"), "button ghost") : null)));
  }

  // ---------- job applications: tech jobs worldwide, each employer studied, a letter for each job (ai_hq/jobs.py) ----------
  const JOB_STAGE = {ready: ["ready to email", "blue"], form: ["apply on their site", "amber"], sent: ["applied", "green"], followed_up: ["followed up", "green"],
    replied: ["replied", "green"], declined: ["said no", "muted"], bounced: ["bounced", "red"], applied: ["you applied", "green"], dropped: ["dropped", "muted"]};
  let jobFilter = "ready";
  function jobBadge(item) {
    if (item.status === "replied" && item.reply?.verdict === "offered") return badge("interview or offer", "green");
    const [label, style] = JOB_STAGE[item.status] || [item.status, "muted"]; return badge(label, style);
  }
  function jobsView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading…")));
    (async () => {
      let state; try { state = await api("/api/jobs"); } catch (issue) { root.replaceChildren(body(empty("Job applications unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const counts = state.counts || {}, rules = state.settings || {}, all = array(state.jobs);
      const stats = el("div", "grid stats");
      [["Jobs found", state.total || 0, "tech jobs, worldwide", ""], ["Ready to email", counts.ready || 0, `${state.letters_ready || 0} letters written`, "blue"],
       ["Apply on their site", counts.form || 0, "your letter, ready to paste", "amber"], ["Applied", (counts.sent || 0) + (counts.followed_up || 0) + (counts.applied || 0), "by email or on their site", "green"],
       ["Interviews and offers", state.offered || 0, "a reply is drafted for each", "green"]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const before = array(state.ready).length ? panel("Before applications can go out", body(append(el("ul", "tips"), ...state.ready.map(item => el("li", "", item))),
        actionsRow(link("Connected accounts →", "connections")))) : null;
      const status = state.status?.message ? hint(`Last run ${state.status.at ? date(state.status.at) : ""}: ${state.status.message}`, state.status.state === "error") : null;
      // 1. your CV and what you want
      const form = el("form"), save = submitButton("Save");
      const cv = textarea("Paste your CV here: your experience, projects, skills, education and results. Applications use only what it says.", rules.cv || "");
      const signature = textarea("Your sign-off: name, phone or WhatsApp, email, LinkedIn or GitHub", rules.signature || "");
      const wantedWords = input("Words a job should mention, e.g. Python, React, security (optional)", rules.wanted || "");
      const avoidWords = input("Words to skip, e.g. senior, 10+ years, unpaid (optional)", rules.avoid || "");
      const days = input("7", rules.follow_up_days ?? 7, "number");
      cv.rows = 12; signature.rows = 3; days.min = 0; days.max = 30;
      const modes = Object.entries(state.work_modes || {}).map(([key, label]) => { const box = check(label, array(rules.work_modes).includes(key)); box.control.value = key; return box; });
      const boards = Object.entries(state.sources || {}).map(([key, label]) => { const box = check(label, array(rules.sources).includes(key)); box.control.value = key; return box; });
      const on = check("Work on its own: find jobs, study each employer and write the applications", rules.enabled === true);
      const mode = select([["review", "I review each one and press Send"], ["send", "Send each application automatically"]], rules.mode || "review");
      const jobWindow = sendWindowFields(rules);
      append(form, field("Your CV", cv, "The only source of facts about you: nothing that isn't here is ever claimed."), field("Signature", signature),
        append(el("div"), el("strong", "", "Kinds of work"), append(el("div", "check-list"), ...modes.map(box => box.wrap))),
        append(el("div", "form-grid"), field("Must mention", wantedWords), field("Skip jobs that mention", avoidWords)),
        append(el("div"), el("strong", "", "Job boards"), append(el("div", "check-list"), ...boards.map(box => box.wrap))),
        append(el("div", "form-grid"), field("Sending", mode), field("Follow up after (days, 0 for none)", days)), jobWindow.node, on.wrap,
        hint("No daily number in Cerebra: Gmail's own limit applies (about 500 a day on a personal Gmail, 2,000 on Google Workspace). When Gmail refuses, sending waits for the next day."),
        actionsRow(save, button("Run once now", () => act(result => result.message || result.skipped || "Done.", () => mutate("/api/jobs/run", {}, "POST", 900000)).then(() => render()), "button ghost")));
      wireForm(form, save, async () => {
        await mutate("/api/jobs", {cv: cv.value, signature: signature.value, wanted: wantedWords.value, avoid: avoidWords.value, follow_up_days: Number(days.value || 0),
          mode: mode.value, enabled: on.control.checked, work_modes: modes.filter(box => box.control.checked).map(box => box.control.value),
          sources: boards.filter(box => box.control.checked).map(box => box.control.value), ...jobWindow.values()}, "PUT");
        toast(on.control.checked ? "Saved. Job applications are on." : "Saved."); render();
      });
      // 2. the jobs
      const review = button(`Review ready applications (${state.letters_ready || 0})`, () => jobLettersDialog(), state.letters_ready ? "button primary" : "button");
      const offers = button(`Interviews and offers (${state.offered || 0})`, () => { jobFilter = "offered"; render(); }, jobFilter === "offered" ? "button primary" : "button");
      const findNow = button("Find jobs now", () => act(result => `Found ${result.added} new job(s).` + (array(result.failed).length ? ` Couldn't reach: ${result.failed.join(", ")}.` : ""),
        () => mutate("/api/jobs/find", {}, "POST", 600000)).then(() => render()), "button");
      const writeMore = button("Write the next 10 letters", () => act(result => `${result.written} letter(s) written.` + (array(result.problems).length ? ` Not written: ${result.problems.slice(0, 2).join("; ")}` : ""),
        () => mutate("/api/jobs/write", {count: 10}, "POST", 1800000)).then(() => render()), "button ghost");
      const filters = {ready: `Ready to email (${counts.ready || 0})`, form: `Apply on their site (${counts.form || 0})`, offered: `Interviews and offers (${state.offered || 0})`,
        applied: "Applied", replied: "Replied or said no", all: "Everything"};
      const pick = select(Object.entries(filters), jobFilter); pick.addEventListener("change", () => { jobFilter = pick.value; render(); });
      const groups = {applied: ["sent", "followed_up", "applied"], replied: ["replied", "declined", "bounced"]};
      const shown = all.filter(item => jobFilter === "all" ? true : jobFilter === "offered" ? item.status === "replied" && item.reply?.verdict === "offered"
        : (groups[jobFilter] || [jobFilter]).includes(item.status));
      const list = el("div", "row-list");
      shown.slice(0, 300).forEach(item => {
        const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", item.title),
          el("div", "row-meta", [item.company, item.location, ({remote: "Remote", hybrid: "Hybrid", onsite: "On-site"})[item.mode], item.source_label].filter(Boolean).join(" · ")),
          el("div", "row-meta", item.apply_email ? `✉ ${item.apply_email}${item.letter?.body ? " · letter written" : ""}` : item.letter?.body ? "Letter ready to paste on their site" : "Apply on their site"),
          item.notes ? el("div", "row-meta", item.notes) : null), jobBadge(item));
        row.addEventListener("click", () => jobDialog(item)); list.append(row);
      });
      root.replaceChildren(stats, before, status,
        append(el("div", "grid two"),
          panel("Jobs", append(el("div"), body(append(el("div", "actions"), review, offers, findNow, writeMore, pick),
            hint("Every employer is studied from its own website before its letter is written. Each letter is built around that job's requirements and the employer's interests, from your CV only, and every figure in it is checked.")),
            shown.length ? list : body(empty(state.total ? "Nothing here" : "No jobs yet", "Paste your CV, choose the kinds of work you want, then press Find jobs now.", null, "◎"))), null, shown.length),
          panel("Your CV and the jobs you want", body(form))));
    })();
    return root;
  }
  function jobDialog(item) {
    const letter = item.letter || {}, subject = input("Subject", letter.subject || ""), text = textarea("Your letter", letter.body || ""), to = input("Their email", item.apply_email || "");
    text.rows = 14;
    const refill = result => { subject.value = result.subject || ""; text.value = result.body || ""; };
    const write = button(letter.body ? "Write it again" : "Research them and write it", () => act("Written.", () => mutate(`/api/jobs/${item.id}/letter`, {again: !!letter.body}, "POST", 600000)).then(result => { if (result) refill(result); }), "button");
    const keep = button("Save my edits", () => act("Saved.", () => mutate(`/api/jobs/${item.id}`, {letter: {subject: subject.value, body: text.value}, apply_email: to.value.trim()}, "PATCH")), "button ghost");
    const send = button("Send by email", () => act(result => result.message, () => mutate(`/api/jobs/${item.id}`, {apply_email: to.value.trim()}, "PATCH")
      .then(() => mutate(`/api/jobs/${item.id}/send`, {subject: subject.value, body: text.value}, "POST", 120000))).then(result => { if (result) { closeDialog(); render(); } }), "button primary");
    const copy = button("Copy the letter", () => { navigator.clipboard?.writeText(text.value).then(() => toast("Copied. Paste it into their application form."), () => toast("Select the letter and copy it.", true)); }, "button");
    const open = button("Open the job", () => act("Opened in your browser.", () => mutate(`/api/jobs/${item.id}/open`, {})), "button");
    const mark = status => act("Saved.", () => mutate(`/api/jobs/${item.id}`, {status}, "PATCH")).then(result => { if (result) { closeDialog(); render(); } });
    const applied = ["sent", "followed_up", "replied", "declined", "bounced"].includes(item.status);
    showDialog(item.title, append(el("div"),
      el("div", "row-meta", [item.company, item.location, ({remote: "Remote", hybrid: "Hybrid", onsite: "On-site"})[item.mode], item.source_label].filter(Boolean).join(" · ")), jobBadge(item),
      actionsRow(open), item.company_id ? append(el("div"), el("h4", "", "What Cerebra has learned about the employer"), researchBlock({id: item.company_id})) : hint("No employer website in this posting: the letter uses what the posting says."),
      append(el("details", "draft-text"), el("summary", "", "The job posting"), el("pre", "code-block", item.description || "")),
      applied ? append(el("div"), el("h4", "", "What you sent"), ...array(item.sent).map(mail => append(el("div"), el("div", "row-meta", `${date(mail.at)}${mail.follow_up ? " · follow-up" : ""}: ${mail.subject}`), el("pre", "code-block", mail.body))),
        item.reply?.snippet ? replyBlockFor(item, `/api/jobs/${item.id}`) : null, interviewPrep(item))
        : append(el("div"), el("h4", "", "Your application"), field("To", to, item.apply_email ? "The address the posting gives for applying." : "This job takes applications on its own site: copy the letter and paste it there, or type an address it gives."),
          field("Subject", subject), field("Letter", text, "Built from your CV, the posting and the employer's research. Read it and change anything before sending."),
          actionsRow(write, keep, item.apply_email ? send : copy)),
      actionsRow(button("Mark as applied", () => mark("applied"), "button"), !applied ? button("Drop it", () => mark("dropped"), "button ghost") : null)));
  }
  // Interview notes, built from the CV, the posting and the employer's research when an employer invites the owner.
  function interviewPrep(item) {
    const reply = item.reply || {}, prep = reply.prep;
    if (reply.verdict !== "offered" && !prep) return null;
    const make = button(prep ? "Write the notes again" : "Prepare for the interview", () => act("Your interview notes are ready.",
      () => mutate(`/api/jobs/${item.id}/prepare`, {again: !!prep}, "POST", 300000)).then(result => { if (result) { closeDialog(); render(); } }), prep ? "button small" : "button primary");
    if (!prep) return append(el("div"), el("h4", "", "Prepare for the interview"), hint("Likely questions with what your CV says for each, questions to ask them, and anything the posting asks for that your CV doesn't show."), actionsRow(make));
    return append(el("div", "interview-prep"), el("h4", "", "Prepare for the interview"), prep.about ? el("p", "", prep.about) : null,
      el("strong", "", "Questions they're likely to ask"),
      append(el("ol", "tips"), ...array(prep.questions).map(item => append(el("li"), el("div", "", item.question), el("div", "row-meta", item.evidence)))),
      array(prep.ask_them).length ? append(el("div"), el("strong", "", "Questions to ask them"), append(el("ul", "tips"), ...prep.ask_them.map(text => el("li", "", text)))) : null,
      array(prep.gaps).length ? append(el("div"), el("strong", "", "Be ready for"), append(el("ul", "tips"), ...prep.gaps.map(text => el("li", "", text)))) : null,
      hint("Built only from your CV, the job posting, the employer's website and their reply: nothing about you is invented."), actionsRow(make));
  }
  function replyBlockFor(item, base) {
    const reply = item.reply || {}, box = el("div");
    const verdict = {offered: ["An interview or offer", "green"], declined: ["They said no: nothing more is sent", "muted"], unclear: ["No offer in it", "amber"]}[reply.verdict];
    append(box, el("h4", "", "Their reply"), verdict ? badge(verdict[0], verdict[1]) : hint("Not read yet."), reply.summary ? el("p", "", reply.summary) : null,
      el("pre", "code-block", reply.body || reply.snippet || ""),
      actionsRow(button(reply.verdict ? "Read it again" : "Read their reply", () => act("Read.", () => mutate(`${base}/read-reply`, {again: !!reply.verdict}, "POST", 300000)).then(result => { if (result) { closeDialog(); render(); } }), "button small")));
    if (reply.answered_at) append(box, hint(`You answered on ${date(reply.answered_at)}.`), el("pre", "code-block", reply.answer || ""));
    else if (reply.verdict === "offered") {
      const text = textarea("Your reply", reply.draft || ""); text.rows = 8;
      append(box, field("Your reply (drafted for you: read and change it before sending)", text, "Nothing is sent until you press Send."),
        actionsRow(button("Send my reply from Gmail", () => act(result => result.message, () => mutate(`${base}/answer`, {text: text.value}, "POST", 120000)).then(result => { if (result) { closeDialog(); render(); } }), "button primary")));
    }
    return box;
  }
  function jobLettersDialog() {
    const box = el("div"); box.append(el("p", "", "Loading the applications ready to go…"));
    showDialog("Ready applications", box);
    (async () => {
      let state; try { state = await api("/api/jobs"); } catch (issue) { box.replaceChildren(hint(issue.message, true)); return; }
      const ready = array(state.jobs).filter(item => item.status === "ready" && item.letter?.body), ticks = [];
      const list = el("div", "row-list");
      ready.forEach(item => {
        const tick = el("input"); tick.type = "checkbox"; tick.checked = true; tick.value = item.id; ticks.push(tick);
        const head = append(el("label", "draft-head"), tick, append(el("span"), el("strong", "", item.title), el("span", "row-meta", ` · ${item.company} · to ${item.apply_email}`)));
        const text = el("details", "draft-text"); append(text, el("summary", "", `Subject: ${item.letter.subject}`), el("pre", "code-block", item.letter.body));
        list.append(append(el("div", "row draft-row"), append(el("div", "row-main"), head, text)));
      });
      const send = button("", () => act(result => result.message, () => mutate("/api/jobs/send", {ids: ticks.filter(tick => tick.checked).map(tick => tick.value)}, "POST", 1800000))
        .then(result => { if (result) { closeDialog(); render(); } }), "button primary");
      const label = () => { const n = ticks.filter(tick => tick.checked).length; send.textContent = n ? `Send all ${n} selected` : "Nothing selected"; send.disabled = !n; };
      ticks.forEach(tick => tick.addEventListener("change", label)); label();
      box.replaceChildren(el("p", "", ready.length ? `${ready.length} application(s) ready. Open any one to read it in full; untick the ones you don't want to send.` : "No applications are written yet: press Write the next 10 letters."),
        ready.length ? list : null, ready.length ? actionsRow(send) : null);
    })();
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
      const shown = array(state.prospects).filter(item => prospectFilter === "all" || (item.status === prospectFilter && !(prospectFilter === "kept" && item.emailed)));
      const list = el("div", "row-list");
      shown.slice(0, 200).forEach(item => { const row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", item.name),
        el("div", "row-meta", [item.kind_label, `${item.city}, ${item.state}`, item.website ? item.website.replace(/^https?:\/\//, "").replace(/\/$/, "") : "no website"].join(" · ")),
        el("div", "row-meta", array(item.facts).map(fact => fact.text).slice(0, 2).join(" · ")),
        el("div", "row-meta", item.email ? `✉ ${item.email}` : item.email_checked ? "No public email: call them, or type one you know" : item.website ? "Email: being looked up" : "No website listed")), badge(item.status, PROSPECT_STYLE[item.status]));
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
      root.replaceChildren(stats, panel("Writing model", body(prospectWriterPanel())), panel("Sent emails", body(sentPanel())), panel("Automatic outreach", body(outreachPanel(state.kinds)), null), append(el("div", "grid two"), left, side));
    })();
    return root;
  }
  function prospectWriterPanel() {
    const root = el("div");
    let advancedMode = null;
    async function loadModels() {
      const state = await api("/api/prospects/models");
      const form = el("form"), save = submitButton("Save writing model");
      const picker = el("select"), search = input("Search model names…"), custom = check("Use a custom model ID", false);
      let chosen = state.selected || "auto";
      if (advancedMode === null) advancedMode = chosen.startsWith("api:");
      if (!advancedMode && chosen.startsWith("api:")) chosen = "auto";
      const advanced = check("Advanced: use separately billed API models", advancedMode);
      function fillModels() {
        const groups = new Map(), query = search.value.trim().toLowerCase();
        picker.replaceChildren();
        const choices = [...array(advancedMode ? state.options : state.subscription_options)];
        if (!choices.some(item => item.id === chosen)) choices.push({id: chosen, label: `${chosen} (saved model)`, group: "Saved choice"});
        choices.filter(item => item.id === chosen || !query || `${item.label} ${item.id} ${item.group}`.toLowerCase().includes(query)).forEach(item => {
          if (!groups.has(item.group)) { const group = el("optgroup"); group.label = item.group; groups.set(item.group, group); picker.append(group); }
          const entry = option(item.id, item.reason ? `${item.label} — ${item.reason}` : item.label);
          entry.disabled = !!item.disabled; groups.get(item.group).append(entry);
        });
        picker.value = chosen;
      }
      fillModels();
      search.addEventListener("input", fillModels);
      picker.addEventListener("change", () => { chosen = picker.value; });
      const customProvider = select(advancedMode ? [["api:openai", "OpenAI API"], ["api:anthropic", "Anthropic API"], ["catalog:codex", "ChatGPT subscription"], ["catalog:claude", "Claude subscription"]] : [["catalog:codex", "ChatGPT subscription"], ["catalog:claude", "Claude subscription"]], advancedMode ? "api:openai" : "catalog:codex");
      const customId = input("Exact model ID supplied by your provider");
      const customFields = append(el("div", "form-grid hidden"), field("Connection for custom model", customProvider), field("Custom model ID", customId));
      custom.control.addEventListener("change", () => { customFields.classList.toggle("hidden", !custom.control.checked); customId.required = custom.control.checked; });
      append(form, field("Search models", search), field("Model for prospect drafts", picker), custom.wrap, customFields,
        hint(advancedMode ? "API models require separate keys and billing. Turn Advanced off to use only your subscriptions." : "Choose the GPT or Claude model by name. Uses your existing ChatGPT or Claude subscription through the signed-in official Codex or Claude Code client. No API keys and no automatic API fallback. Model availability and usage limits depend on your plan; this does not unlock every ChatGPT website mode."),
        !advancedMode ? hint("OpenAI names use the client's local catalog, with known choices shown if it is empty. Claude families are known choices. Neither list verifies your account's access. Use a custom model ID for a newer model your client supports.") : null,
        hint("Applies to first emails, offers, follow-ups and replies. Save and retry a stopped draft. Saving does not turn on outreach or send email."),
        actionsRow(save, link("Models & sign-in →", "models")), advanced.wrap);
      advanced.control.addEventListener("change", () => { advancedMode = advanced.control.checked; loadModels().catch(issue => toast(issue.message, true)); });
      wireForm(form, save, async () => {
        const choice = custom.control.checked ? `${customProvider.value}:${customId.value.trim()}` : picker.value;
        await mutate("/api/outreach", {writing_model: choice, subscription_only: !advancedMode}, "PUT");
        toast("Prospect writing model saved. Retry any draft that stopped.");
        await loadModels();
      });
      const connections = el("details");
      connections.classList.toggle("hidden", !advancedMode);
      connections.append(el("summary", "", "OpenAI and Anthropic API connections"),
        hint("Connect each provider with its own API key, then refresh its model list. API usage is billed by that provider separately from CLI sign-ins. Keys are protected by this computer and never returned to the page. Catalog refresh does not generate content."));
      Object.entries(state.connections || {}).forEach(([id, connection]) => {
        const connectForm = el("form"), key = input("Paste an API key", "", "password"), connectSave = submitButton(`Save ${connection.label} key`);
        key.autocomplete = "new-password";
        const workspace = input("Only if your Anthropic key requires it", connection.workspace_id || "");
        append(connectForm, el("h4", "", connection.label), hint(connection.configured ? `Key saved. ${connection.models.length} models cached${connection.refreshed_at ? ` · refreshed ${date(connection.refreshed_at)}` : "; refresh to check access"}.` : "No API key saved."),
          connection.error ? hint(connection.error, true) : null, field(`${connection.label} key`, key),
          id === "anthropic" ? field("Anthropic workspace ID (optional)", workspace) : null,
          actionsRow(connectSave, button(`Refresh ${connection.label} models`, () => act(result => result.message, () => mutate(`/api/prospects/models/connections/${id}/refresh`, {}, "POST", 120000)).then(reloadModels), "button"),
            connection.configured ? button(`Disconnect ${connection.label}`, () => act("API key disconnected.", () => mutate(`/api/prospects/models/connections/${id}`, {}, "DELETE")).then(reloadModels), "button ghost") : null));
        wireForm(connectForm, connectSave, async () => {
          const values = id === "anthropic" ? {workspace_id: workspace.value.trim()} : {};
          if (key.value.trim()) values.api_key = key.value.trim();
          await mutate(`/api/prospects/models/connections/${id}`, values, "PUT");
          key.value = "";
          await act(result => result.message, () => mutate(`/api/prospects/models/connections/${id}/refresh`, {}, "POST", 120000));
          await loadModels();
        });
        connections.append(connectForm);
      });
      root.replaceChildren(form, connections);
    }
    const reloadModels = () => loadModels().catch(issue => toast(issue.message, true));
    root.append(hint("Loading writing models…"));
    loadModels().catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  const OUTREACH_STAGE = {sent: ["emailed", "blue"], followed_up: ["followed up", "amber"], done: ["no answer yet", "muted"], replied: ["replied", "green"], answered: ["you answered", "cyan"],
                          opted_out: ["said no: never again", "muted"], bounced: ["bounced", "red"], drafting: ["writing", "cyan"]};
  const SENT_FILTERS = {all: "All", waiting: "Waiting for an answer", replied: "Replied", said_no: "Said no or bounced"};
  let sentFilter = "all";
  function senderLine(sender) {
    // Which Gmail the emails go out from (the one set up in Business connections), and one click to allow sending.
    const allow = label => button(label, () => act(result => result.message, () => mutate("/api/business/gmail/authorize")), "button small primary");
    if (!sender?.configured) return append(el("div", "action-card"), el("strong", "", "Emails go out from your Gmail"), hint("Set up Gmail in Business connections first (it takes about 10 minutes, once)."), actionsRow(link("Business connections →", "connections")));
    if (!sender.connected) return append(el("div", "action-card"), el("strong", "", "Gmail isn't connected"), hint("Connect it, and allow reading and sending."), actionsRow(allow("Connect Gmail…")));
    if (!sender.can_send) return append(el("div", "action-card"), append(el("div", "row-meta"), badge("read-only", "amber"), el("strong", "", ` ${sender.email}`)),
      hint("This Gmail can read but not send yet. Press Allow sending: Google's page opens; sign in as this account and allow sending email. Then refresh this page."), actionsRow(allow("Allow sending…")));
    return append(el("div", "row-meta"), badge("reads and sends", "green"), el("span", "", ` Sending from ${sender.email} (your Gmail in Business connections)`));
  }
  function sentPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/outreach/sent").then(items => {
      items = array(items);
      if (!items.length) { root.replaceChildren(hint("Businesses you email appear here, with where each one stands: waiting, followed up, replied or said no. Open a business in the list below and press Send with Gmail.")); return; }
      const group = item => ["sent", "followed_up", "done", "answered"].includes(item.stage) ? "waiting" : item.stage === "replied" ? "replied" : "said_no";
      const count = key => items.filter(item => group(item) === key).length;
      const pick = select(Object.entries(SENT_FILTERS).map(([key, label]) => [key, key === "all" ? `${label} (${items.length})` : `${label} (${count(key)})`]), sentFilter);
      pick.addEventListener("change", () => { sentFilter = pick.value; render(); });
      const shown = items.filter(item => sentFilter === "all" || group(item) === sentFilter);
      const progress = item => item.stage === "replied" ? (item.reply?.draft ? "Replied: your answer is drafted, open to send" : "Replied: your turn") : item.stage === "answered" ? "You answered; waiting for them" : item.stage === "opted_out" ? "Said no: never written to again" : item.stage === "bounced" ? "Bounced: address didn't work"
        : item.stage === "done" ? "All follow-ups sent; still watching for a reply" : item.next_at ? `Waiting · follow-up ${date(item.next_at)}` : "Waiting for an answer";
      root.replaceChildren(append(el("div", "actions"), pick), table(["Business", "Sent to", "First email", "Follow-ups", "Where it stands"], shown.map(item => {
        const name = append(el("span"), button(item.name || "Business", () => sentDialog(item), "text-button"), el("div", "row-meta", item.city));
        return [name, item.email, date(item.first_sent_at), String(item.follow_ups),
          append(el("span"), badge((OUTREACH_STAGE[item.stage] || [item.stage])[0], (OUTREACH_STAGE[item.stage] || [, "muted"])[1]), el("div", "row-meta", progress(item)),
            item.reply?.snippet ? el("div", "row-meta", `“${item.reply.snippet.slice(0, 120)}”`) : null)];
      })));
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  function sentDialog(item) {
    const root = el("div");
    append(root, kv([["Business", item.name], ["Where", item.city], ["Website", item.website || "—"], ["Email", item.email], ["Follow-ups sent", String(item.follow_ups)],
      ["Next follow-up", item.next_at ? date(item.next_at) : "None planned"]]));
    item.emails.forEach((mail, index) => append(root, el("h3", "", `${index ? `Follow-up ${index}` : "First email"} · ${date(mail.at)}`), el("strong", "", mail.subject), el("pre", "lead-description", mail.body)));
    if (item.reply?.snippet) append(root, el("h3", "", `Their reply${item.reply.at ? ` · ${date(item.reply.at)}` : ""}`), el("p", "", item.reply.text || item.reply.snippet));
    if (item.stage === "replied") {
      const answer = textarea("Your answer", item.reply?.draft || ""); answer.rows = 8;
      append(root, el("h3", "", "Your answer"), answer, hint("Drafted by your AI from what they wrote and your services and prices. Edit anything; it goes in the same thread with your details."),
        actionsRow(button("Draft again", () => act("Drafted.", () => mutate(`/api/outreach/${item.id}/draft-answer`, {}, "POST", 300000)).then(result => { if (result) answer.value = result.draft; }), "button ghost"),
          button("Send answer with Gmail", () => act(result => result.message, () => mutate(`/api/outreach/${item.id}/answer`, {text: answer.value})).then(result => { if (result) { closeDialog(); render(); } }), "button primary")));
    }
    showDialog(item.name || "Sent email", root);
  }
  function outreachPanel(kinds) {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/outreach").then(state => {
      const rules = state.settings, form = el("form"), save = submitButton(rules.enabled ? "Save" : "Save and switch on");
      const on = check("Work on its own: find businesses, research them and write to them", rules.enabled), mode = select([["draft", "Draft each email; I read, edit and send it with one click"], ["send", "Send the emails automatically"]], rules.mode || "draft"), perDay = input("10", rules.per_day, "number");
      const first = input("4", rules.follow_up_days[0] ?? 4, "number"), second = input("7", rules.follow_up_days[1] ?? 7, "number");
      const places = textarea("One city per line, such as Austin, TX", array(rules.places).map(item => `${item.city}, ${item.state}`).join("\n")); places.rows = 3;
      const chosen = new Set(array(rules.kinds)), boxes = Object.entries(kinds || {}).map(([key, label]) => { const box = check(label, chosen.has(key)); box.key = key; return box; });
      perDay.min = 1; perDay.max = state.max_per_day;
      const counts = state.counts || {}, summary = el("div", "grid stats");
      [["Emailed today", `${state.sent_today} of ${state.limit}`, state.limit < rules.per_day ? `building up to your ${rules.per_day} a day, to protect your Gmail` : "first emails and follow-ups", "blue"], ["Waiting for an answer", (counts.sent || 0) + (counts.followed_up || 0), "follow-ups are automatic", "amber"],
       ["Replied", counts.replied || 0, "your turn: answer them", "green"], ["Said no", (counts.opted_out || 0) + (counts.bounced || 0), "never written to again", "muted"]]
        .forEach(([label, value, note, style]) => summary.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      append(root.replaceChildren() || root, senderLine(state.sender), summary,
        array(state.ready).length ? append(el("div"), el("h4", "", "Before it can start"), append(el("ul", "tips"), ...state.ready.map(item => el("li", "", item))), actionsRow(link("Business connections →", "connections"), link("Money › Your business →", "money"))) : null,
        state.health?.paused ? append(el("div"), el("h4", "", "Automatic sending is paused"), hint(`${state.health.reason} Replies are still read, drafts are still written and you can still send by hand. Check the bounced addresses under Recent, then resume.`, true),
          actionsRow(button("Resume automatic sending", () => act("Resumed.", () => mutate("/api/outreach/resume", {}, "POST")).then(() => render()), "button small primary"))) : null,
        state.status?.message ? hint(`Last run ${state.status.at ? date(state.status.at) : ""}: ${state.status.message}`, state.status.state === "error") : null,
        hint("Draft mode: new businesses get their email written for you; open one below (Worth contacting), edit anything and press Send. Send mode sends them too. Either way, what it does: finds independent businesses in your cities (Prospects searches), reads each one's website for problems you can fix and its public email, has your AI write a short email in your voice about only what it saw, sends it from your Gmail, and follows up in the same thread when there's no answer. It stops the moment someone replies and tells you; anyone who says no, or whose address bounces, is never written to again. Every email carries your name, postal address and an opt-out line, as US law (CAN-SPAM) requires. Emails can go out any day, at any time, a few at a time within your daily limit."));
      append(form, on.wrap, field("What it does with each email", mode), append(el("div", "form-grid"), field("Emails or drafts a day", perDay), field("First follow-up after (days)", first), field("Second follow-up after (days)", second)),
        field("Cities", places), el("h4", "", "Kinds of business (none ticked: all)"), append(el("div", "check-grid"), ...boxes.map(box => box.wrap)), actionsRow(save,
          button("Run once now", () => act(result => result.message || result.skipped || "Done.", () => mutate("/api/outreach/run", {}, "POST", 600000)).then(() => render()), "button ghost")));
      wireForm(form, save, async () => {
        const list = places.value.split("\n").map(line => line.split(",")).filter(parts => parts.length >= 2 && parts[0].trim() && parts[1].trim()).map(parts => ({city: parts[0].trim(), state: parts.slice(1).join(",").trim()}));
        await mutate("/api/outreach", {enabled: on.control.checked, mode: mode.value, per_day: Number(perDay.value || 10), follow_up_days: [Number(first.value || 4), Number(second.value || 7)].filter(Boolean),
          places: list, kinds: boxes.filter(box => box.control.checked).map(box => box.key)}, "PUT");
        toast(on.control.checked ? "Automatic outreach is on." : "Saved. Automatic outreach is off."); render();
      });
      root.append(form);
      if (array(state.recent).length) root.append(el("h4", "", "Recent"), table(["Business", "Email", "Stage", "Emails", "Next follow-up"],
        state.recent.map(item => [item.name, item.email, append(el("span"), badge((OUTREACH_STAGE[item.stage] || [item.stage])[0], (OUTREACH_STAGE[item.stage] || [, "muted"])[1]), item.reply?.snippet ? el("div", "row-meta", item.reply.snippet.slice(0, 120)) : null),
          String(item.emails), item.next_at ? date(item.next_at) : "—"])));
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  function offerPanel(state) {
    const root = el("div"), kinds = [...new Set(array(state.searches).map(item => item.kind))];
    const kind = select(kinds.map(key => [key, state.kinds[key]]), kinds[0]), out = el("div");
    const show = () => {
      const offer = (state.offers || {})[kind.value] || {}, price = input("Your price, e.g. $1,500 setup + $150 a month", offer.price || "");
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
    const sender = el("div");
    api("/api/outreach").then(state => sender.replaceChildren(senderLine(state.sender))).catch(() => {});
    const to = input("their email address", item.email || ""), followUp = check("Send follow-ups automatically (enables the Outreach schedule; stops on reply)", false); to.type = "email";
    if (!item.email && item.website) { to.placeholder = "Looking for their email on their website…";
      api(`/api/prospects/${item.id}/email`).then(found => { if (found.email && !to.value) to.value = found.email; else if (!found.email) to.placeholder = "No email on their site: type one you know, or call them"; to.dispatchEvent(new Event("input")); }).catch(() => {}); }
    const send = button("Send with Gmail", () => act(result => result.message, () => mutate(`/api/prospects/${item.id}/send`, {to: to.value.trim(), text: opener.value, follow_up: followUp.control.checked}, "POST", 120000))
      .then(result => { if (result) { closeDialog(); render(); } }), "button primary");
    const ready = () => { send.disabled = !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to.value.trim()); send.title = send.disabled ? "Add their email address first" : ""; };
    to.addEventListener("input", ready); ready();
    const status = select([["new", "To check by hand"], ["kept", "Worth contacting"], ["contacted", "Contacted"], ["replied", "Replied"], ["won", "Won: became a client"], ["lost", "Lost"], ["dropped", "Not a fit"]], item.status);
    const facts = el("ul", "tips"); array(item.facts).forEach(fact => facts.append(append(el("li"), document.createTextNode(fact.text), el("span", "row-meta", ` (seen at ${fact.seen})`))));
    append(root, kv([["Business", item.kind_label], ["Where", [item.address, `${item.city}, ${item.state}`].filter(Boolean).join(", ")], ["Website", item.website || "None listed"], ["Phone", item.phone || "Not listed"]]),
      el("h3", "", "What Cerebra saw"), array(item.facts).length ? facts : hint(item.notes || "No issue seen on the home page."),
      append(el("div", "form-grid"), field("Status", status)), field("Notes", notes),
      el("h3", "", "First email"), sender, field("To", to), opener, followUp.wrap,
      missing.length ? hint(`Before sending, add ${missing.join(" and ")} in Money › Your business details.`, true) : null,
      hint("Read it, change anything, then press Send: it goes from your Gmail exactly as written. In the US, cold emails need your real postal address and a way to opt out (CAN-SPAM); Cerebra keeps both in, and never writes again to anyone who says no."),
      actionsRow(array(item.facts).length ? draft : null, copy, ["contacted", "replied", "won", "lost"].includes(item.status) ? null : send,
        button("Save", () => act("Saved.", () => mutate(`/api/prospects/${item.id}`, {status: status.value, notes: notes.value, opener: opener.value}, "PATCH")).then(result => { if (result) { closeDialog(); render(); } }), "button")));
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
    const company = check("I have a registered company", value.company), country = input("The state where it's registered, e.g. Delaware or Texas", value.company_country);
    const website = input("https://your-company.com", value.website), founded = input("2026", value.founded_year || "", "number");
    const product = check("Something I built is live and people use it", value.product), usOwned = check("It's a US small business, majority owned by US citizens or permanent residents", value.us_owned);
    const selfFunded = check("No outside investors yet", value.self_funded), awsPaid = check("My AWS account is on a paid plan", value.aws_paid);
    append(form, company.wrap, append(el("div", "form-grid"), field("State", country), field("Founded (year)", founded)), field("Company website", website),
      product.wrap, usOwned.wrap, selfFunded.wrap, awsPaid.wrap, actionsRow(save));
    wireForm(form, save, async () => {
      await mutate("/api/funding/facts", {company: company.control.checked, company_country: country.value, website: website.value, founded_year: Number(founded.value || 0),
        product: product.control.checked, us_owned: usOwned.control.checked, self_funded: selfFunded.control.checked, aws_paid: awsPaid.control.checked}, "PUT");
      toast("Saved. Readiness updated."); render();
    });
    return form;
  }

  // ---------- books: short nonfiction for Amazon KDP ----------
  const BOOK_STYLE = {planned: "blue", writing: "amber", files_ready: "cyan", published: "green", retired: "muted"};
  const NICHE_STYLE = {idea: "blue", researching: "amber", chosen: "green", dropped: "muted"};
  const usd = value => `$${Number(value || 0).toFixed(2)}`;
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
  // ---------- Etsy: what sells and how crowded it is ----------
  const ETSY_STYLE = {strong: "green", test: "amber", weak: "muted"};
  function etsyView() {
    const root = el("div"), token = renderToken;
    root.append(body(el("p", "", "Loading…")));
    (async () => {
      let state; try { state = await api("/api/etsy"); } catch (issue) { root.replaceChildren(body(empty("Etsy unavailable", issue.message))); return; }
      if (token !== renderToken) return;
      const niches = array(state.niches), form = el("form"), keyword = input("wedding planner printable", ""), digital = check("Digital downloads only", true), go = submitButton("Research");
      append(form, hint("Type what a buyer would search for. Cerebra reads Etsy's top 100 listings for it (one request) and works out demand, competition and prices."),
        field("Keyword", keyword), digital.wrap, actionsRow(go));
      wireForm(form, go, async () => {
        const found = await mutate("/api/etsy/research", {keyword: keyword.value, digital_only: digital.control.checked}, "POST", 60000);
        toast(`${found.keyword}: ${found.label === "strong" ? "a strong niche" : found.label === "test" ? "worth a test" : "weak or crowded"} (${found.score}).`);
        render(); etsyNicheDialog(found);
      });
      const list = el("div", "row-list");
      niches.forEach(niche => {
        const data = niche.data || {}, row = append(el("div", "row clickable"), append(el("div", "row-main"), el("strong", "", niche.keyword),
          el("div", "row-meta", [`${Number(data.count || 0).toLocaleString()} listings`, `${data.demand ?? 0} favourites/month on top listings`, data.price ? `median $${Number(data.price).toFixed(2)}` : "", niche.digital_only ? "digital only" : ""].filter(Boolean).join(" · "))),
          el("span", `badge ${ETSY_STYLE[niche.label] || "muted"}`, `${niche.label.toUpperCase()} ${niche.score}`));
        row.tabIndex = 0; row.setAttribute("role", "button");
        row.addEventListener("click", () => etsyNicheDialog(niche)); row.addEventListener("keydown", event => { if (event.key === "Enter") etsyNicheDialog(niche); });
        list.append(row);
      });
      const stats = el("div", "grid stats");
      [["Researched", niches.length, "keywords", ""], ["Strong", niches.filter(item => item.label === "strong").length, "worth making for", "green"],
       ["Worth a test", niches.filter(item => item.label === "test").length, "a few listings first", "amber"]]
        .forEach(([label, value, note, style]) => stats.append(append(el("div", `stat ${style}`), el("div", "stat-label", label), el("div", "stat-value", value), el("div", "stat-note", note))));
      const sells = etsySells(state.performance, niches), shirts = panel("Text designs for shirts and mugs", body(designMaker()));
      root.replaceChildren(stats, sells, append(el("div", "grid two"),
        append(el("div"), panel("Your niches", niches.length ? list : body(empty("No niches yet", "Research a keyword to see if it's worth making for.")), null, niches.length)),
        append(el("div"), panel("Find a niche", body(state.ready ? form : append(el("div"), hint(state.setup, true), link("Business connections →", "connections")))),
          shirts, panel("How to read it", body(append(el("ul", "tips"),
            el("li", "", "Demand is favourites a month on the first page of results: Etsy publishes favourites, not sales, so this is the honest sign of what buyers want."),
            el("li", "", "Competition is how many active listings match. Fewer than 3,000 with real demand is the sweet spot; over 50,000 needs a narrower keyword."),
            el("li", "", "Try the longer keywords each niche suggests: they are what top sellers already tag, and usually less crowded."),
            el("li", "", "Etsy requires you to disclose AI use and bans AI-made patterns and recipes. Check Etsy's seller policy before listing.")))))));
    })();
    return root;
  }
  function designMaker() {
    const root = el("div"), form = el("form"), text = input("Powered by coffee and spreadsheets", ""), colour = select([["white", "white"]], "white"), make = submitButton("Make the design"), out = el("div");
    api("/api/designs").then(state => { colour.replaceChildren(...array(state.colours).map(name => { const option = el("option", "", name); option.value = name; return option; })); colour.value = "white";
      if (array(state.files).length) out.replaceChildren(el("h4", "", "Made so far"), list(state.files.slice(0, 8).map(item => item.file))); }).catch(() => {});
    append(form, hint("A short phrase drawn by code as a 4500 × 5400 transparent PNG at 300 DPI: what Amazon Merch on Demand asks for, and what Printify accepts for shirts, mugs and totes. No AI, no fonts. Original phrases only: no brands, names or quotes you don't own."),
      append(el("div", "form-grid"), field("Phrase", text), field("Ink colour", colour)), actionsRow(make), out);
    wireForm(form, make, async () => {
      const made = await mutate("/api/designs", {text: text.value, colour: colour.value}, "POST", 120000);
      out.replaceChildren(hint(`Made ${made.file} (${made.width} × ${made.height} px, ${Math.round(made.bytes / 1024)} KB).`), append(el("ul", "tips"), ...made.use.map(item => el("li", "", item))),
        actionsRow(button("Open the designs folder", () => act("Opened.", () => mutate("/api/designs/open", {})), "button small")));
      toast("Design ready.");
    });
    return append(root, form);
  }
  function etsySells(performance, niches) {
    const data = performance || {}, worth = revenue => Object.entries(revenue || {}).map(([currency, amount]) => cash(amount, currency)).join(" + ") || cash(0, "USD");
    if (!data.orders) return panel("What sells", body(hint("After your first Etsy orders, this shows which niches and listings earn, so you make more of what sells. Orders come in every 6 hours once Etsy is connected (Money page › Import Etsy orders).")));
    const root = el("div");
    if (data.niches.length) {
      root.append(el("h4", "", "Niches that earn"));
      const list = el("div", "row-list");
      data.niches.forEach(item => {
        const niche = niches.find(entry => entry.id === item.id), row = append(el("div", `row${niche ? " clickable" : ""}`), append(el("div", "row-main"), el("strong", "", item.keyword),
          el("div", "row-meta", `${item.units} sold in ${item.orders} order(s) from ${item.listings} listing(s)${item.last_sale ? ` · last sale ${new Date(`${item.last_sale}T12:00:00`).toLocaleDateString("en-US", {month: "short", day: "numeric", year: "numeric"})}` : ""}`)),
          el("span", "badge green", worth(item.revenue)));
        if (niche) { row.tabIndex = 0; row.setAttribute("role", "button"); row.title = "Write another listing for this niche";
          row.addEventListener("click", () => etsyNicheDialog(niche)); row.addEventListener("keydown", event => { if (event.key === "Enter") etsyNicheDialog(niche); }); }
        list.append(row);
      });
      root.append(list, hint("A niche that earns is the best place for your next listings: open it and write another, a different product for the same buyers."));
    }
    root.append(el("h4", "", "Best-selling listings"), table(["Listing", "Niche", "Sold", "Earned"], data.listings.map(item => [item.title || item.listing_id, item.keyword || (item.made_here ? "—" : "made outside Cerebra"), String(item.units), worth(item.revenue)])));
    if (data.outside.units) root.append(hint(`${data.outside.units} sold (${worth(data.outside.revenue)}) from listings Cerebra didn't make or that have no niche yet.`));
    root.append(hint("Earned is the item price times quantity, before discounts and Etsy's fees."));
    return panel("What sells", body(root), null, `${data.orders} order(s)`);
  }
  function etsyNicheDialog(niche) {
    const data = niche.data || niche, root = el("div");
    const research = term => act("", () => mutate("/api/etsy/research", {keyword: term, digital_only: niche.digital_only ?? true}, "POST", 60000)).then(found => { if (found) { render(); etsyNicheDialog(found); } });
    append(root, append(el("div", "detail-top"), el("span", `badge ${ETSY_STYLE[data.label] || "muted"}`, `${String(data.label || "").toUpperCase()} ${data.score}`),
        el("span", "row-meta", `${Number(data.count || 0).toLocaleString()} active listings · prices $${(data.spread || [0, 0]).map(value => Number(value).toFixed(2)).join("–")} · ${data.digital_share ?? 0}% digital`)),
      append(el("ul", "tips"), ...array(data.reasons).map(reason => el("li", "", reason))),
      el("h4", "", "Tags top sellers use"), append(el("div", "chips"), ...array(data.tags).map(item => el("span", "badge muted", `${item.tag} · ${item.uses}`))),
      array(data.longer).length ? append(el("div"), el("h4", "", "Longer keywords to check"), append(el("div", "actions"), ...array(data.longer).map(term => button(term, () => research(term), "button small ghost")))) : null,
      el("h4", "", "On the first page"), table(["Listing", "Favourites", "Price"], array(data.examples).map(item => [item.title, String(item.favorites), item.price ? `$${Number(item.price).toFixed(2)}` : "—"])),
      hint("Titles and tags are other sellers' words: use them to understand the niche, never copy a listing."),
      niche.id ? append(el("div"), el("h4", "", "Listings written for it"), (() => { const holder = el("div", "row-list");
        api(`/api/etsy/listings?niche=${encodeURIComponent(niche.id)}`).then(rows => array(rows).forEach(listing => { const row = append(el("div", "row clickable"),
          append(el("div", "row-main"), el("strong", "", listing.title), el("div", "row-meta", [`$${Number(listing.price).toFixed(2)}`, listing.checks.length ? `${listing.checks.length} thing(s) to fix` : "passes Cerebra's checks"].join(" · "))));
          row.addEventListener("click", () => etsyListingDialog(listing, niche)); holder.append(row); })).catch(() => {}); return holder; })()) : null,
      niche.id ? actionsRow(button("Remove", () => act("Removed.", () => api(`/api/etsy/niches/${niche.id}`, {method: "DELETE"})).then(() => { closeDialog(); render(); }), "button ghost"),
        button("✍ Write a listing", () => act("Writing a listing with your AI model (about a minute)…", () => mutate(`/api/etsy/niches/${niche.id}/listing`, {}, "POST", 300000)).then(listing => { if (listing) etsyListingDialog(listing, niche); }), "button primary")) : null);
    showDialog(data.keyword || niche.keyword, root);
  }
  function etsyListingDialog(listing, niche) {
    const root = el("div"), copy = (text, what) => navigator.clipboard.writeText(text).then(() => toast(`${what} copied.`), () => toast("Couldn't copy it; select the text and copy it.", true));
    append(root, listing.checks.length ? append(el("div"), el("h4", "", "Fix before listing"), append(el("ul", "tips"), ...listing.checks.map(item => el("li", "", item))))
        : hint("Passes Cerebra's checks: title length, 13 tags, no trademarked names, no AI patterns or recipes. Etsy's own review still applies."),
      el("h4", "", `Title (${listing.title.length}/140)`), el("p", "", listing.title), actionsRow(button("Copy title", () => copy(listing.title, "Title"), "button small")),
      el("h4", "", `Tags (${listing.tags.length}/13)`), append(el("div", "chips"), ...listing.tags.map(tag => el("span", "badge muted", tag))), actionsRow(button("Copy tags", () => copy(listing.tags.join(", "), "Tags"), "button small")),
      keywordAudit(listing.audit, true),
      el("h4", "", "Description"), el("pre", "lead-description", listing.description), actionsRow(button("Copy description", () => copy(listing.description, "Description"), "button small")),
      el("h4", "", "Price and product"), el("p", "", `$${Number(listing.price).toFixed(2)} · ${listing.product || "describe the files to make"}`),
      hint("When you list it on Etsy: tick that AI was used if it was, choose “Designed by” rather than “Made by”, and upload the files you made. Nothing goes to Etsy without your confirmation."),
      actionsRow(button("Back to the niche", () => etsyNicheDialog(niche), "button ghost"),
        listing.job_id ? link("Open its product job →", `job/${listing.job_id}`)
          : button("Make it in Business Studio", () => act("Started: your AI is making the product files.", () => mutate(`/api/etsy/listings/${listing.id}/make`, {})).then(result => { if (result) { closeDialog(); location.hash = `job/${result.job_id}`; } }),
            listing.checks.length ? "button" : "button primary")));
    showDialog("Etsy listing", root);
  }
  // Notebooks, journals and logbooks for KDP: the inside pages, drawn by code (no AI, no fonts), ready to upload.
  function interiorMaker() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/books/interiors").then(state => {
      const form = el("form"), style = select(Object.entries(state.styles), "college"), trim = select(state.trims.map(key => [key, key.replace("x", " × ") + " in"]), "6x9");
      const pages = input("120", "120", "number"), paper = select([["white", "White paper"], ["cream", "Cream paper"]], "white"), make = submitButton("Make the PDF"), out = el("div");
      const theme = input("gratitude journal for women", "");
      const asBook = button("Make it a book", () => act("Your AI is writing the listing (about a minute)…", () => mutate("/api/books/notebooks",
        {theme: theme.value, style: style.value, trim: trim.value, pages: Number(pages.value || 120), paper: paper.value}, "POST", 300000))
        .then(book => { if (book) { toast(book.listing.checks.length ? "Made. Fix what the checks found before uploading." : "Ready to upload: it waits in Your calls."); render(); notebookDialog(book); } }), "button primary");
      pages.min = 24; pages.max = 828;
      const ideas = append(el("div", "idea-chips"), ...array(state.ideas).map(idea => { const chip = button(idea.theme, () => {
          theme.value = idea.theme; style.value = idea.style; trim.value = idea.trim; pages.value = idea.pages;
          out.replaceChildren(hint(`${idea.why}. Next: Check the niche, then Make it a book. It makes the pages, the cover and the listing; you upload them to KDP.`)); }, "button small ghost");
        chip.title = idea.why; return chip; }));
      append(form, array(state.ideas).length ? append(el("div"), el("h4", "", "Start with a proven idea"), ideas) : null);
      append(form, hint("The inside pages of a notebook, journal, logbook or planner: drawn by code, so Amazon's AI question is No for them. Headings are drawn as lines, not typed in a font, so KDP's font check can't fail. Pick a trim, then add a cover."),
        append(el("div", "form-grid"), field("Pages", style), field("Trim size", trim), field("Page count", pages), field("Paper", paper)),
        field("Who it's for (to make it a book)", theme, "Your AI writes the title, subtitle, description and 7 keywords for this; Cerebra checks KDP's limits."),
        actionsRow(make, button("Check the niche", () => act("", () => mutate("/api/books/niche-check", {theme: theme.value}, "POST", 60000)).then(found => { if (found) out.replaceChildren(nicheCheck(found)); }), "button"), asBook), out);
      wireForm(form, make, async () => {
        const made = await mutate("/api/books/interiors", {style: style.value, trim: trim.value, pages: Number(pages.value || 120), paper: paper.value}, "POST", 120000);
        out.replaceChildren(hint(`Made ${made.file} (${made.pages} pages, ${Math.round(made.bytes / 1024)} KB). Inside margin ${made.gutter} in on the binding side.`),
          append(el("ul", "tips"), ...made.kdp.map(line => el("li", "", line))),
          actionsRow(button("Open the folder", () => act("Opened.", () => mutate("/api/books/interiors/open", {})), "button small")));
        toast("Interior PDF ready.");
      });
      root.replaceChildren(form, state.files.length ? append(el("div"), el("h4", "", "Made so far"), list(state.files.map(item => `${item.file} · ${Math.round(item.bytes / 1024)} KB`))) : null);
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  function etsyVersion(book) {
    const root = el("div"), pages = input("2", "2", "number"), out = el("div"); pages.min = 1; pages.max = 30;
    append(root, el("h4", "", "Sell it on Etsy too"),
      hint("The same pages as a printable PDF (US Letter, printed at home), and an Etsy listing written from this book's listing. It waits on the Etsy page; each item goes to one of your shops only."),
      book.etsy_listing ? hint(`Already made: ${book.etsy_printable || "a printable"}. Making it again adds another listing.`) : null,
      append(el("div", "form-grid"), field("Pages in the printable", pages)),
      actionsRow(button("Make the Etsy printable", () => act("", () => mutate(`/api/books/${encodeURIComponent(book.id)}/etsy`, {pages: Number(pages.value || 2)}))
        .then(made => { if (!made) return; out.replaceChildren(hint(`Made ${made.file} and an Etsy listing: “${made.title}”, $${Number(made.price).toFixed(2)}.`),
          made.checks.length ? append(el("ul", "tips"), ...made.checks.map(item => el("li", "", item))) : hint("The listing passes Cerebra's Etsy checks."),
          actionsRow(link("Open the Etsy page →", "etsy"))); toast("Etsy printable ready."); }), "button")), out);
    return root;
  }
  function coverForm(book) {
    const form = el("form"), palette = select([["navy", "Navy and cream"]], book.cover_palette || "navy"), author = input("Pen name (optional)", book.cover_author || book.pen_name || ""), make = submitButton("Draw the cover again");
    api("/api/books/covers/palettes").then(names => { palette.replaceChildren(...Object.entries(names).map(([key, label]) => { const option = el("option", "", label); option.value = key; return option; })); palette.value = book.cover_palette || "navy"; }).catch(() => {});
    append(form, el("h4", "", "Cover"), hint("Drawn by code to KDP's full-wrap size (back, spine, front and bleed) for this trim and page count: no fonts, no AI images. The spine carries the title from 79 pages."),
      append(el("div", "form-grid"), field("Colours", palette), field("Author on the cover", author)), actionsRow(make));
    wireForm(form, make, async () => { const made = await mutate(`/api/books/${encodeURIComponent(book.id)}/cover`, {palette: palette.value, author: author.value}); toast(`Cover saved: ${made.file}`); });
    return form;
  }
  function marketPanel() {
    const root = el("div"), form = el("form"), theme = input("mileage log book", ""), list = textarea("Mileage Log Book for Taxes | 12500 | 840 | 7.99 | 120", ""), read = submitButton("Read what's selling"), out = el("div");
    list.rows = 5;
    const show = found => {
      const plan = found.plan, style = input("", plan.style), pages = input("120", plan.pages, "number");
      style.hidden = true; pages.min = 24; pages.max = 828;
      out.replaceChildren(el("h4", "", "What the top books have in common"), append(el("ul", "tips"), ...array(found.notes).map(item => el("li", "", item))),
        array(found.common_words).length ? hint(`Words buyers keep seeing in titles: ${found.common_words.join(", ")}. Use them in your keywords, in your own phrasing.`) : null,
        field("Pages in your book", pages),
        actionsRow(button("Make my own version", () => act("Making your pages, cover and listing (about a minute)…", () => mutate("/api/books/blueprint/make", {theme: theme.value, books: list.value, pages: Number(pages.value || plan.pages)}, "POST", 300000))
          .then(book => { if (book) { toast(array(book.listing?.checks).length ? "Made. Fix what the checks found before uploading." : "Your book is ready to check."); render(); notebookDialog(book); } }), "button primary")));
    };
    append(form, hint("Follow what buyers already want: the kind of book, its size, length and price. Your cover, words and pages stay your own, which is what keeps your KDP account safe."),
      field("What the book is", theme),
      actionsRow(button("Open the Amazon search", () => act("Opened Amazon in your browser.", () => mutate("/api/books/niche-check/amazon", {theme: theme.value})), "button small")),
      field("The top books, one per line", list, "Title | Best Sellers Rank | reviews | price | pages. Read these from each book's Amazon page."), actionsRow(read));
    wireForm(form, read, async () => show(await mutate("/api/books/blueprint", {theme: theme.value, books: list.value}, "POST")));
    return append(root, form, out);
  }
  function ebookPanel() {
    const root = el("div"), form = el("form"), brief = textarea("e.g. easy indoor gardening for beginners in small apartments", ""), go = submitButton("Plan the book"), list = el("div");
    brief.rows = 2;
    append(form, hint("Your AI plans a short, practical nonfiction eBook: title, chapters, description, 7 keywords and a price. Approve the outline and the chapters are written one by one in the background; then a Kindle file (EPUB) is made, ready to upload. Facts that need a source are marked [CHECK] for you."),
      field("What the book is about, and who it's for", brief), actionsRow(go));
    wireForm(form, go, async () => { await mutate("/api/ebooks", {brief: brief.value}, "POST", 300000); toast("Outline drafted."); render(); });
    const call = (path, done, wait = 300000) => act(done, () => mutate(path, {}, "POST", wait)).then(result => { if (result) render(); });
    api("/api/ebooks").then(items => {
      array(items).forEach(book => {
        const card = el("div", "action-card"), outline = book.outline || {};
        append(card, el("strong", "", book.title || "Planning…"), el("div", "row-meta", book.subtitle || book.brief));
        if (book.stage === "outline_ready") {
          append(card, append(el("ol", "tips"), ...array(outline.chapters).map(item => el("li", "", item.title))),
            el("p", "row-meta", `${outline.keywords?.length || 0} keywords · $${Number(outline.price || 0).toFixed(2)} (you earn about $${Number(book.royalty?.royalty || 0).toFixed(2)} a copy)`),
            array(outline.checks).length ? hint(outline.checks.join(" · "), true) : null, keywordAudit(book.audit),
            actionsRow(button("Approve and start writing", () => call(`/api/ebooks/${book.id}/approve`, "Approved: chapters are written in the background."), "button small primary"),
              button("Plan it again", () => call(`/api/ebooks/${book.id}/outline`, "Planned again."), "button small ghost")));
        } else if (book.stage === "writing") {
          append(card, el("p", "row-meta", `${book.written} of ${book.total} chapters written · ${Number(book.words).toLocaleString()} words. A chapter is written every 20 minutes.`),
            book.error ? hint(book.error, true) : null,
            actionsRow(button("Write the next chapter now", () => call(`/api/ebooks/${book.id}/write`, "Chapter written."), "button small")));
        } else if (book.stage === "ready") {
          append(card, el("p", "row-meta", `Ready to upload: ${book.total} chapters, ${Number(book.words).toLocaleString()} words.`),
            array(book.checks_to_verify).length ? hint(`Verify ${book.checks_to_verify.length} [CHECK] note(s) before publishing: ${book.checks_to_verify.slice(0, 3).join(" ")}…`, true) : hint("No facts flagged for checking."),
            hint("Upload the .epub in KDP › Kindle eBook › Manuscript, make the cover with KDP's free Cover Creator, and answer Yes for AI-generated text unless you rewrote it."),
            actionsRow(button("Open the folder", () => act("Opened.", () => mutate(`/api/ebooks/${book.id}/open`, {})), "button small")));
        }
        list.append(card);
      });
    }).catch(() => {});
    return append(root, form, list);
  }
  function collectionPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    const makeIt = group => act(result => result.message, () => mutate("/api/books/collection", group ? {group} : {}, "POST", 300000)).then(result => { if (result) render(); });
    api("/api/books/collection").then(state => {
      const groups = array(state.groups), total = groups.reduce((sum, group) => sum + group.books.length, 0), made = groups.reduce((sum, group) => sum + group.books.filter(book => book.book_id).length, 0);
      root.replaceChildren(hint("Original books for every age group, in kinds that sell steadily: each with its own design, a cover in the group's colours and pattern, an encouraging line written for that age at the foot of every page, and a complete listing (title, subtitle, description, 7 keywords, price) checked against KDP's limits. Nothing to fill in: open a book, copy each field into KDP and upload the two PDFs. KDP allows about 3 new titles a day."),
        actionsRow(button(made >= total ? `All ${total} made` : `Make all ${total - made} remaining`, () => makeIt(null), "button primary")));
      groups.forEach(group => {
        const rows = el("div", "row-list");
        group.books.forEach(book => rows.append(append(el("div", "row"), append(el("div", "row-main"), el("strong", "", book.title),
          el("div", "row-meta", `${book.style_label.split(" (")[0]} · ${book.trim.replace("x", " × ")} in · ${book.pages} pages · $${Number(book.price).toFixed(2)}`),
          el("div", "row-meta", book.why)), book.book_id ? badge("made", "green") : badge("not yet", "muted"))));
        append(root, append(el("div", "action-card"), append(el("div", "row-meta"), el("strong", "", group.label), el("span", "", ` · ${group.palette} colours, ${group.motif} pattern`)), rows,
          el("p", "row-meta", `Lines on its pages: “${group.quotes.slice(0, 3).join("”, “")}”…`),
          group.books.every(book => book.book_id) ? null : actionsRow(button(`Make ${group.label}`, () => makeIt(group.key), "button small"))));
      });
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  function nicheCheck(found) {
    const root = el("div"), etsy = found.etsy || {};
    append(root, el("h4", "", `Is “${found.theme}” worth a book?`),
      found.flags.length ? append(el("ul", "tips"), ...found.flags.map(item => el("li", "", item))) : null,
      etsy.ready ? append(el("div"), append(el("div", "row-meta"), badge(`${etsy.label.toUpperCase()} ${etsy.score}`, ETSY_STYLE[etsy.label] || "muted"), el("span", "", ` Etsy, “${etsy.keyword}”: ${Number(etsy.count).toLocaleString()} listings, about ${etsy.demand} favourites a month on top listings, median $${Number(etsy.price).toFixed(2)}`)),
          append(el("ul", "tips"), ...array(etsy.reasons).map(item => el("li", "", item))), hint("Buyers who want a printable version usually want the paperback too: strong demand here is a good sign for KDP."))
        : hint(`Etsy demand not checked: ${String(etsy.setup || "connect Etsy").replace(/\.+$/, "")}. The Amazon check below still works.`),
      found.keywords.length ? append(el("div"), el("h4", "", "Keyword ideas for KDP's 7 boxes"), list(found.keywords), actionsRow(button("Copy keywords", () => navigator.clipboard.writeText(found.keywords.join("\n")).then(() => toast("Keywords copied.")), "button small"))) : null,
      el("h4", "", "On Amazon"), append(el("ul", "tips"), ...array(found.how_to_read).map(item => el("li", "", item))),
      actionsRow(button("Open the Amazon book search ↗", () => act("Opened in your browser.", () => mutate("/api/books/niche-check/amazon", {theme: found.theme})), "button small")));
    return root;
  }
  function keywordAudit(audit, fixesShown = false) {
    if (!audit) return null;
    const style = {strong: "green", good: "blue", weak: "amber", fix: "red"}[audit.label] || "muted", tips = [...(fixesShown ? [] : array(audit.fix)), ...array(audit.improve)];
    return append(el("div"), el("h4", "", "Keyword check"), append(el("p", "row-meta"), badge(`${audit.score}/100`, style), ` ${audit.summary}`),
      tips.length ? append(el("ul", "tips"), ...tips.map(item => el("li", "", item))) : null);
  }
  function notebookDialog(book, state) {
    const listing = book.listing || {}, root = el("div"), copy = (text, what) => navigator.clipboard.writeText(text).then(() => toast(`${what} copied.`), () => toast("Couldn't copy it.", true));
    append(root, array(listing.checks).length ? append(el("div"), el("h4", "", "Fix before uploading"), append(el("ul", "tips"), ...listing.checks.map(item => el("li", "", item))))
        : hint("Passes Cerebra's checks: lengths, 7 keywords, no banned words or trademarks."),
      el("h4", "", "Title"), el("p", "", listing.title), actionsRow(button("Copy title", () => copy(listing.title, "Title"), "button small")),
      listing.subtitle ? append(el("div"), el("h4", "", "Subtitle"), el("p", "", listing.subtitle), actionsRow(button("Copy subtitle", () => copy(listing.subtitle, "Subtitle"), "button small"))) : null,
      el("h4", "", "Description"), el("pre", "lead-description", listing.description || ""), actionsRow(button("Copy description", () => copy(listing.description, "Description"), "button small")),
      el("h4", "", "7 keywords (one per box)"), list(array(listing.keywords)), actionsRow(button("Copy keywords", () => copy(array(listing.keywords).join("\n"), "Keywords"), "button small")),
      keywordAudit(book.audit),
      kv([["Interior", book.interior || "—"], ["Cover", book.cover || "—"], ["Trim and pages", `${String(book.trim).replace("x", " × ")} in · ${book.pages} pages · ${book.paper} paper`],
          ["Price", `$${Number(listing.price || book.prices?.paperback || 0).toFixed(2)}`], ["You earn per copy", book.royalty ? `$${Number(book.royalty.royalty).toFixed(2)}` : `$${Number(book.earnings?.paperback?.royalty ?? 0).toFixed(2)}`]]),
      book.price_tip ? hint(book.price_tip) : null, hint(book.ai_question || ""), hint("Upload the interior PDF as the manuscript and the cover PDF as a print-ready cover (KDP adds the barcode on the back), then publish. KDP allows about 3 new titles a day."),
      coverForm(book), etsyVersion(book),
      actionsRow(button("Open the interiors folder", () => act("Opened.", () => mutate("/api/books/interiors/open", {})), "button"),
        state ? button("Edit details (published, ASIN)", () => bookDialog(book, state), "button ghost") : null));
    showDialog(listing.title || book.title, root);
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
        row.addEventListener("click", () => book.kind === "low_content" ? notebookDialog(book, state) : bookDialog(book, state)); bookList.append(row);
      });
      const left = append(el("div"),
        panel("Niches", append(el("div"), body(append(el("div", "actions"), button("+ New niche", () => nicheDialog(null, state), "button primary")),
          hint("One reader with one problem (“sleep after menopause”, not “health”). The score uses only what you checked: competing books' Best Sellers Rank and reviews, and the search trend.")),
          niches.length ? nicheList : body(empty("No niches yet", "Add a problem people already pay to fix. Check its trend on Google Trends and its competing books on Amazon.", null, "◎"))), null, niches.length),
        panel("Books", append(el("div"), body(append(el("div", "actions"), button("+ New book", () => bookDialog(null, state), "button primary"))),
          books.length ? bookList : body(empty("No books yet", "Start one from a niche you chose. Cerebra shows what each format earns before you write a word.", null, "▤"))), null, books.length));
      const side = append(el("div"), panel("Learn from what's selling", body(marketPanel())), panel("Write a Kindle eBook", body(ebookPanel())), panel("Books for every age group", body(collectionPanel())), panel("Low-content interiors", body(interiorMaker())), panel("Start publishing", body(publishingChecklist(state))), panel("What a book earns", body(royaltyCalculator(state))),
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
      const sourcesOn = Object.values(state.profile.sources || {}).some(Boolean);
      const checkNow = button("Check for new work now", () => act(result => checkWords(result), () => mutate("/api/freelance/check", {}, "POST", 300000)).then(() => render()), "button primary");
      checkNow.disabled = !sourcesOn;
      if (!sourcesOn) checkNow.title = "Choose work categories and enable a public source first.";
      const configure = button("Configure job search", () => {
        const profile = document.querySelector("#freelance-profile");
        profile?.scrollIntoView({block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
        profile?.querySelector("input, select, button")?.focus({preventScroll: true});
      }, "button");
      const profileForm = freelanceProfileForm(state); profileForm.id = "freelance-profile";
      const left = append(el("div"), panel("Work for you", append(el("div"), body(append(el("div", "actions"), pick,
        checkNow,
        button("+ Paste a job", () => pasteLeadDialog(state), "button"))),
        shown.length ? list : body(empty(!sourcesOn && leadFilter === "open" ? "Find work on your terms" : leadFilter === "open" ? "No matches yet" : "Nothing here yet", leadFilter === "open" ? (sourcesOn ? "Check your selected sources for new opportunities, or paste a job to review it here." : "Add your skills, choose the work you offer and enable a public source. You can also paste a job without enabling searches.") : "Saved jobs and application updates will appear here.", !sourcesOn && leadFilter === "open" ? configure : null, "⌕"))), null, shown.length));
      const side = append(el("div"), panel("What you sell", body(profileForm)), panel("Where Cerebra looks", body(sourcesList(state))), panel("Freelancer.com account", body(freelancerAccount(state))), panel("What works", body(insightsPanel())), panel("Apply automatically", body(autoApplyPanel())), panel("Profiles, gigs and portfolio", body(pitchesPanel())),
        panel("How it works", body(hint("Cerebra reads only the public job sources you enable (each on its own schedule) and scores every job against what you sell: freelance and contract work, real budgets, fresh posts and few competing bids rank first. On Freelancer.com it can bid for you (Apply automatically); everywhere else, open a job and apply in your own name with the proposal Cerebra writes. Upwork and Fiverr don't allow automated bidding, so paste their jobs here to have them scored with the rest."))));
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
    const actions = append(el("div", "lead-actions"), lead.rare && lead.status === "new" ? el("span", "badge amber", "RARE") : null, scoreBadge(lead.score), lead.status !== "new" ? badge(lead.status, LEAD_STYLE[lead.status]) : null);
    if (lead.rare) row.title = "A rare chance: a strong match with few bids so far and a real budget";
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
      committeeSection(lead, state), proposalSection(lead, state), field("Notes", notes));
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
    if (lead.status === "applied") {
      // One polite follow-up after a few quiet days wins more work; the note is the owner's to send, in their own name.
      const note = `Hi, I wanted to follow up on my proposal for “${lead.title}”. I'm still available and happy to answer any questions or share a short plan for the first steps. Thanks for considering it.`;
      root.insertBefore(hint(lead.followed_up_at ? `You followed up ${relative(lead.followed_up_at)}. If there's still no reply after a week, mark it as not won so your results stay true.`
        : lead.applied_at ? `You applied ${relative(lead.applied_at)}. No reply after five days? Send one short follow-up where you applied.` : "No reply after five days? Send one short follow-up where you applied."), root.lastChild);
      actions.append(button("Copy a follow-up note", () => navigator.clipboard.writeText(note).then(() => toast("Copied. Send it where you applied, then press “I followed up”."), () => toast("Couldn't copy it.", true)), "button"),
        button("I followed up", () => setLead(lead, {followed_up: true, notes: notes.value}, "Noted. Cerebra reminds you once more in a week if there's no reply."), "button ghost"));
    }
    if (["applied", "interview"].includes(lead.status)) actions.append(button("I won it", () => setLead(lead, {status: "won", notes: notes.value}, "Congratulations! Quote or invoice it from the Money page."), "button primary"), button("Didn't get it", () => setLead(lead, {status: "lost", notes: notes.value}, "Noted."), "button ghost"));
    if (lead.status !== "hidden") actions.append(button("Hide", () => setLead(lead, {status: "hidden", notes: notes.value}, "Hidden."), "button ghost"));
    else actions.append(button("Show again", () => setLead(lead, {status: "new"}, "Back in the list."), "button"));
    actions.append(button("Save notes", () => setLead(lead, {notes: notes.value}, "Notes saved."), "button ghost"));
    root.append(actions);
    showDialog(lead.title.slice(0, 90), root);
    dialog.dataset.leadId = lead.id;
  }
  // The decision committee: an analyst, a case for, a case against, a risk reviewer who can veto, and a manager who decides.
  const COMMITTEE_ROLES = [["analyst", "Analyst"], ["bull", "Case for"], ["bear", "Case against"], ["risk", "Risk review"], ["manager", "Manager"]];
  function committeeSection(lead, state) {
    const record = lead.committee || {}, box = el("div", "proposal-box");
    const ask = () => act("The committee is looking at this job (about a minute)…", () => mutate("/api/freelance/committee", {id: lead.id})).then(async result => { if (!result) return; const [fresh, fresher] = await refreshLead(lead.id); leadDialog(fresh, fresher); });
    if (!record.decision) {
      if (!state.agents_on || !["new", "saved"].includes(lead.status)) return null;  // only worth asking before applying
      return append(box, el("strong", "", "Decision committee"), el("p", "row-meta", "Five AI roles weigh this job before you spend a bid on it: fit, the case for, the case against, a risk check that can veto, and a decision."),
        button("Ask the committee", ask, "button"));
    }
    const verdict = record.decision === "bid" ? `Bid (${record.confidence}% sure)` : record.vetoed ? "Skip: vetoed by the risk review" : `Skip (${record.confidence}% sure)`;
    const details = el("details");
    append(details, el("summary", "", "What each role said"), ...COMMITTEE_ROLES.filter(([key]) => record.roles?.[key]).map(([key, label]) => append(el("div"), el("h4", "", label), el("p", "", record.roles[key]))));
    return append(box, append(el("div", "detail-top"), el("strong", "", "Decision committee"), el("span", `badge ${record.decision === "bid" ? "green" : "amber"}`, verdict), record.at ? el("span", "row-meta", relative(record.at)) : null),
      record.reason ? el("p", "", record.reason) : null, details, state.agents_on ? button("Ask again", ask, "button ghost small") : null);
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
    else if (!["new", "saved"].includes(lead.status)) sending.append(hint("You've applied with this proposal; it stays here for reference."));
    else if (lead.source === "freelancer" && state.freelancer_account?.connected) {
      sending.append(state.freelancer_account?.connected
        ? button("Send bid on Freelancer.com", async () => { if (!await act("", save)) return;
            const connected = array(state.freelancer_account.accounts).filter(item => item.connected), from = select(connected.map(item => [item.id, item.holder ? `${item.username} (${item.holder})` : item.username]), connected[0]?.id);
            showDialog("Send this bid?", append(el("div"),
            el("p", "", `Sends your proposal as a bid of ${lead.currency || "USD"} ${Number(price.value || 0).toLocaleString()} with delivery in ${days.value} day(s) on “${lead.title}”.`),
            connected.length > 1 ? field("From the account", from) : el("p", "", `From your Freelancer.com account ${state.freelancer_account.username}.`),
            actionsRow(button("Back", () => leadDialog(lead, state), "button ghost"), button("Send bid", async () => { const result = await act(outcome => outcome.message, () => mutate("/api/freelance/bid", {id: lead.id, confirmed: true, account: from.value || null})); if (result) { closeDialog(); render(); } }, "button primary")))); }, "button primary")
        : hint("Connect your Freelancer.com account (Freelance page › Freelancer.com account) to send bids from here.", true));
    } else {
      // One step for the owner: copy, open the job page, then a plain question, so the application is on the record and leaves Your calls.
      const copyAndOpen = async () => {
        if (!await act("", save)) return;
        const copied = await navigator.clipboard.writeText(text.value).then(() => true, () => false);
        if (lead.url) await act("", () => mutate("/api/freelance/open", {id: lead.id}));
        showDialog("Did you send it?", append(el("div"),
          el("p", "", copied ? `Your proposal is copied${lead.url ? " and the job page is open in your browser" : ""}. Paste it there and send it in your own name, then come back here.`
            : "Couldn't copy it by itself: go back, select the text and copy it, then paste it on the job page."),
          actionsRow(button("Not yet", () => leadDialog(lead, state), "button ghost"),
            button("Yes, I applied", () => setLead(lead, {status: "applied"}, "Marked as applied. Good luck!"), "button primary"))));
      };
      sending.append(button(lead.url ? "Copy and open the job page" : "Copy proposal", copyAndOpen, "button primary"),
        hint(lead.source === "freelancer" ? "Send it as your bid on the job page. Or connect your Freelancer.com account (Freelance page) to send bids from here."
          : `${lead.source_label} doesn't allow automated bids, so you send it there yourself; Cerebra then asks whether you did.`));
    }
    append(box, el("strong", "", "Proposal"), proposal.fit ? hint(proposal.fit) : null, field("Text", text), append(el("div", "form-grid"), field(`Price (${proposal.currency || lead.currency || "USD"})`, price), field("Delivery (days)", days)),
      append(el("div", "actions"), button("Save edits", () => act("Proposal saved.", save), "button"), button("Write it again", start, "button ghost")), sending);
    return box;
  }
  function freelancerAccount(state) {
    const account = state.freelancer_account || {}, accounts = array(account.accounts), root = el("div");
    if (accounts.length) {
      const list = el("div", "row-list");
      accounts.forEach(item => list.append(append(el("div", "row"), append(el("div", "row-main"), el("strong", "", item.username || "Not checked yet"),
          el("div", "row-meta", item.holder ? `${item.holder}'s account` : "Your account")),
        append(el("div", "actions"), button("Check", () => act(result => result.message, () => mutate(`/api/freelance/freelancer-account/check?account=${encodeURIComponent(item.id)}`)).then(() => render()), "button small"),
          button("Disconnect", () => act(result => result.message, () => api(`/api/freelance/freelancer-account?account=${encodeURIComponent(item.id)}`, {method: "DELETE"})).then(() => render()), "button small ghost")))));
      root.append(list, hint("One bid per project, from one account. With Apply automatically on, each account gets its own daily number of bids."));
    }
    root.append(actionsRow(button("How to connect, step by step…", () => guideDialog("freelancer"), "button small ghost")));
    if (accounts.length >= (account.max || 5)) return root;
    const form = el("form"), token = input("OAuth access token", "", "password"), holder = input("Their full name", ""), save = submitButton(accounts.length ? "Add this account" : "Connect");
    const confirmed = check("This account belongs to that person, who created it and pasted this token themselves. I won't share login details.");
    token.autocomplete = "off";
    append(form, accounts.length ? append(el("div"), el("h4", "", `Add another account (${accounts.length} of ${account.max || 5})`),
        hint("Freelancer.com accounts belong to one person each and login details must never be shared (its User Agreement). Upwork and Fiverr close people who run several accounts. Add a teammate's account, connected by them, not a second account of your own."),
        field("Whose account", holder)) : hint("To bid from Cerebra: create an app at accounts.freelancer.com › Settings › Developer, give it the bidding scope, and paste its OAuth access token. Stored encrypted on this computer."),
      field("Access token", token), accounts.length ? confirmed.wrap : null, actionsRow(save));
    wireForm(form, save, async () => { const result = await mutate("/api/freelance/freelancer-account", {token: token.value.trim(), holder: holder.value, owner_confirmed: confirmed.control.checked}, "PUT"); toast(result.message); render(); });
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
      const committee = check("Ask the decision committee before each bid (skips jobs it rejects)", rules.committee !== false);
      const ahead = check("Write proposals ahead for my strongest matches from every source (nothing is sent; they wait in Your calls)", rules.ahead !== false);
      const aheadPerDay = input("5", rules.ahead_per_day, "number"); aheadPerDay.min = 1; aheadPerDay.max = 20;
      const alert = check("Tell me at once about rare chances (in Your calls, and on my phone if notifications are on)", rules.alert !== false);
      const alertScore = input("50", rules.alert_score, "number"), alertBids = input("15", rules.alert_bids, "number"), alertUsd = input("250", rules.alert_usd, "number");
      alertScore.min = 1; alertScore.max = 100; alertBids.min = 1; alertUsd.min = 1;
      const score = input("40", rules.min_score, "number"), perDay = input("15", rules.per_day, "number"); score.min = 1; score.max = 100; perDay.min = 1; perDay.max = 50;
      append(form, on.wrap, append(el("div", "form-grid"), field("Lowest score to bid on", score), field("Bids per day at most", perDay)), committee.wrap, ahead.wrap, append(el("div", "form-grid"), field("Proposals written ahead per day", aheadPerDay)),
        alert.wrap, append(el("div", "form-grid"), field("Rare: score at least", alertScore), field("Rare: fewer bids than", alertBids), field("Rare: budget at least (USD)", alertUsd)),
        accept.wrap, actionsRow(save));
      wireForm(form, save, async () => { await mutate("/api/freelance/auto", {enabled: on.control.checked, accept_awards: accept.control.checked, committee: committee.control.checked, ahead: ahead.control.checked, ahead_per_day: Number(aheadPerDay.value || 5), alert: alert.control.checked, alert_score: Number(alertScore.value || 50),
        alert_bids: Number(alertBids.value || 15), alert_usd: Number(alertUsd.value || 250), min_score: Number(score.value || 40), per_day: Number(perDay.value || 15)}, "PUT"); toast("Saved. Check the worker schedule below for automatic runs."); render(); });
      const connected = state.freelancer_account?.connected, gmail = state.gmail || {};
      root.replaceChildren(form,
        !connected ? hint("Connect your Freelancer.com account (panel above) so Cerebra can bid.", true) : null,
        rules.enabled && !state.schedules?.auto_apply ? hint("Automatic bidding is paused in Chief of Staff. Resume its worker to run scheduled rounds.", true) : null,
        rules.ahead && !state.schedules?.draft_ahead ? hint("Proposal drafting is paused in Chief of Staff.", true) : null,
        link("Manage worker schedules →", "chief"),
        hint(`Bidding: ${state.applier?.message || "waiting for the next round"}`),
        hint(gmail.connected || gmail.authorized ? "Gmail: Cerebra reads messages from Upwork, Fiverr and Freelancer.com to see what you've won." : "Connect Gmail in Business connections, so Cerebra can see hires, offers and orders from Upwork and Fiverr in your email.", !(gmail.connected || gmail.authorized)),
        append(el("div", "actions"), button("Run a round now", () => act(result => `Done: ${result.bids?.sent || 0} bid(s) sent, ${Number(result.wins?.freelancer || 0) + Number(result.wins?.email || 0)} win(s) found, ${result.work || 0} work step(s) moved on.`, () => mutate("/api/freelance/auto/run", {}, "POST", 900000)).then(() => render()), "button small"), link("Connect Gmail →", "connections")),
        hint("Only Freelancer.com is bid on by itself: Upwork and Fiverr ban automated proposals and suspend accounts that use them, so for them Cerebra writes the proposal and you paste it. Win monitoring and won-job processing run only when their workers are enabled in Chief of Staff. You review work before anything is delivered."));
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
    const skills = input("Your skills, separated by commas", array(settings.skills).join(", "));
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
  function cash(amount, currency) { const text = Number(amount || 0).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2}); return !currency || currency === "USD" ? `$${text}` : `${currency} ${text}`; }
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
        panel("Getting paid", body(hint("Each invoice can carry a payment link, shown on it as “Pay online”: a Stripe link Cerebra creates, or one you paste (PayPal, Square…). Record other payments you receive (Zelle, ACH, check) from the invoice. Payments on a business job's invoice also go into that job's money record."),
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
    const root = el("div"), names = {etsy: ["Etsy", "orders count as sales (before Etsy's fees; tax left out)"], shopify: ["Shopify", "orders count as sales (before Shopify's fees; tax left out)"], printify: ["Printify", "orders count as costs"]};
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
    const how = textarea("How clients can pay you: Zelle, ACH bank transfer, check, PayPal, Venmo…", settings.payment_instructions);
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
      const amount = input("Amount", doc.balance, "number"), method = input("e.g. Zelle, ACH, check, Stripe", ""); amount.step = "any";
      actions.append(append(el("span", "inline-field"), el("span", "", "Received"), amount, method), button("Record payment", () => reopen(mutate(`/api/money/documents/${doc.id}/payments`, {amount: Number(amount.value || 0), method: method.value}), "Payment recorded."), "button primary"));
    }
    if (doc.id && !["void", "paid", "accepted", "declined"].includes(doc.status)) actions.append(button(draft ? "Delete draft" : `Void this ${word}`, () => reopen(api(`/api/money/documents/${doc.id}`, {method: "DELETE"}), draft ? "Draft deleted." : "Voided. Its number stays used."), "button ghost"));
    root.append(actions);
    showDialog(doc.id ? `${doc.number || `Draft ${word}`} · ${doc.client}` : `New ${word}`, root);
  }
  // ---------- business studio ----------
  const STAGE_STYLE = {scope: "amber", intake: "muted", planning: "blue", creating: "blue", checking: "blue", waiting: "amber", ready: "green", completed: "green", failed: "red", cancelled: "muted"};
  const KIND_HELP = {printable: "Printable for a digital download: print-ready pages (planners, trackers, checklists) for Etsy", service_site: "Service business website with a working quote form (client delivery)", website: "Static website: index.html, styles.css, README.md", listing: "Listing copy: title, description and tags (listing.md)", svg: "Original vector design (design.svg) + README", document: "A written document (deliverable.md)"};
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

  function printifyPicker(job, fields) {
    // Pick the product from Printify's catalog instead of typing its IDs; the draft fields below are filled in for review.
    const root = el("div", "action-card"), query = input("unisex t-shirt, mug, poster…", ""), product = select([], ""), provider = select([], ""), filter = input("e.g. Black, or leave empty for all", "");
    const price = input("24.99", "24.99", "number"), image = input("from Upload an image to Printify", ""), position = select([["front", "front"]], "front"), status = el("p", "row-meta", "");
    let variants = []; price.step = "0.01";
    const fill = () => {
      const keep = variants.filter(item => !filter.value.trim() || item.title.toLowerCase().includes(filter.value.trim().toLowerCase()));
      if (!keep.length) { status.textContent = "No variant matches that filter."; return; }
      const ids = keep.slice(0, 100).map(item => item.id), cents = Math.round(Number(price.value || 0) * 100);
      fields.value = json({title: job.title, description: job.brief, blueprint_id: Number(product.value), print_provider_id: Number(provider.value),
        variants: ids.map(id => ({id, price: cents, is_enabled: true})),
        print_areas: [{variant_ids: ids, placeholders: [{position: position.value, images: [{id: image.value.trim() || "PASTE_UPLOADED_IMAGE_ID", x: .5, y: .5, scale: 1, angle: 0}]}]}]});
      status.textContent = `${ids.length} variant(s) at $${(cents / 100).toFixed(2)} each. Check Printify's cost for this product: your price must be above it.`;
    };
    const loadVariants = async () => {
      if (!provider.value) return;
      const data = await api(`/api/business/printify/catalog/${product.value}/providers/${provider.value}/variants`);
      variants = array(data.variants);
      const spots = [...new Set(variants.flatMap(item => array(item.positions)))];
      position.replaceChildren(...(spots.length ? spots : ["front"]).map(spot => { const option = el("option", "", spot); option.value = spot; return option; }));
      status.textContent = `${variants.length} in-stock variant(s).`;
    };
    const loadProviders = async () => {
      const list = await api(`/api/business/printify/catalog/${product.value}/providers`);
      provider.replaceChildren(...list.map(item => { const option = el("option", "", item.title); option.value = item.id; return option; }));
      await loadVariants();
    };
    product.addEventListener("change", () => loadProviders().catch(issue => notice(issue.message, true)));
    provider.addEventListener("change", () => loadVariants().catch(issue => notice(issue.message, true)));
    api(`/api/business/jobs/${encodeURIComponent(job.id)}/operations`).then(items => { const uploaded = array(items).filter(item => item.action === "printify_upload" && item.result?.image_id).pop(); if (uploaded && !image.value) image.value = uploaded.result.image_id; }).catch(() => {});
    append(root, el("strong", "", "Pick the product"), hint("Search Printify's catalog, choose the product and the print provider, and Cerebra fills in the IDs below."),
      append(el("div", "form-grid"), field("Product", query), field("Results", product)),
      actionsRow(button("Search the catalog", () => act("", () => api(`/api/business/printify/catalog?query=${encodeURIComponent(query.value)}`)).then(list => {
        if (!list) return; product.replaceChildren(...list.map(item => { const option = el("option", "", `${item.title}${item.brand ? ` · ${item.brand}` : ""}`); option.value = item.id; return option; }));
        status.textContent = list.length ? `${list.length} product(s) found.` : "Nothing found: try fewer words."; if (list.length) loadProviders().catch(issue => notice(issue.message, true)); }), "button small")),
      append(el("div", "form-grid"), field("Print provider", provider), field("Only variants containing", filter), field("Your price (USD)", price), field("Print position", position)),
      field("Uploaded image ID", image), status, actionsRow(button("Fill the draft fields", fill, "button small primary")));
    return root;
  }
  function externalForm(job, reload) {
    const form = el("form"), choice = select([["image", "Generate a raster image (paid API)"], ["etsy_draft", "Create an Etsy draft listing"], ["shopify_draft", "Create a Shopify draft product"], ["printify_upload", "Upload an image to Printify"], ["printify_draft", "Create a Printify draft product"]], "image");
    const prompt = textarea("Your own original creative instructions (required for image generation)", ""), path = input("e.g. generated/image-….png", "");
    const fields = textarea("Draft fields in JSON. Use real IDs from your account's catalog.", ""); fields.rows = 12;
    const details = el("div"), confirmation = check("I confirm this exact external action on my connected account. Image generation uses paid API credits."), original = check("This uses my original creative input. I will complete required AI and production-partner disclosures before publishing.");
    const shop = select([["", "Your first shop"]], ""), shopField = field("Etsy shop", shop);
    api("/api/business/connections").then(value => { const shops = array(value.etsy?.shops).filter(item => item.shop_id);
      shop.replaceChildren(...shops.map(item => { const option = el("option", "", item.shop_name || `Shop ${item.shop_id}`); option.value = item.id === "main" ? "" : item.id; return option; }));
      shopField.hidden = shops.length < 2; }).catch(() => { shopField.hidden = true; });
    shopField.hidden = true;
    const store = select([], ""), storeField = field("Shopify store", store);
    api("/api/business/shopify").then(value => { const stores = array(value.stores).filter(item => item.connected);
      store.replaceChildren(...stores.map(item => { const option = el("option", "", item.name || item.domain); option.value = item.id; return option; }));
      storeField.hidden = stores.length < 2; }).catch(() => { storeField.hidden = true; });
    const examples = {
      etsy_draft: {quantity: 1, title: job.title, description: job.brief, price: 10, who_made: "i_did", when_made: "made_to_order", taxonomy_id: 0, type: "download"},
      shopify_draft: {title: job.title, description: job.brief, price: 10, tags: [], product_type: ""},
      printify_draft: {title: job.title, description: job.brief, blueprint_id: 0, print_provider_id: 0, variants: [{id: 0, price: 2000, is_enabled: true}], print_areas: [{variant_ids: [0], placeholders: [{position: "front", images: [{id: "PASTE_UPLOADED_IMAGE_ID", x: .5, y: .5, scale: 1, angle: 0}]}]}]}
    };
    function change() {
      details.replaceChildren();
      if (choice.value === "image") details.append(field("Image instructions", prompt), hint("One 1024 × 1024 PNG. The provider bills your API account. Inspect the image before delivery; it is generated after the job's review. Export again to include it."));
      else if (choice.value === "printify_upload") details.append(field("Image path inside this job", path), hint("PNG or JPEG up to 20 MB. The result gives you an image ID for the Printify draft."));
      else { fields.value = json(examples[choice.value]); details.append(field("Review these draft fields", fields), hint("Replace zero IDs with real catalog/category IDs. This creates a draft only. It does not publish, create orders, produce goods or deliver to a client.")); }
      if (choice.value === "etsy_draft") {
        details.append(shopField, hint("Each item goes to one shop only: Etsy doesn't allow the same item listed in several of your shops."), original.wrap);
      }
      if (choice.value === "printify_draft") details.prepend(printifyPicker(job, fields));
      if (choice.value === "shopify_draft") {
        details.append(storeField, hint("Created as a Draft: add its images or download files in Shopify, review it, then set it Active yourself."));
        // A job made from an Etsy listing: its draft is the listing itself (title, 13 tags, description, price), still yours to review.
        api(`/api/etsy/listings?job=${encodeURIComponent(job.id)}`).then(rows => { const listing = array(rows)[0]; if (!listing || choice.value !== "etsy_draft") return;
          fields.value = json({quantity: 999, title: listing.title, description: listing.description, price: listing.price, tags: listing.tags,
                               who_made: "i_did", when_made: "made_to_order", taxonomy_id: 0, type: "download"}); }).catch(() => {});
      }
    }
    choice.addEventListener("change", change); change();
    const result = el("pre", "connection-result"), submit = submitButton("Run confirmed action");
    append(form, link("Account setup →", "connections"), field("Action", choice), details, confirmation.wrap, result, actionsRow(button("Close", closeDialog, "button ghost"), submit));
    wireForm(form, submit, async () => {
      const payload = {action: choice.value, confirmed: confirmation.control.checked, original_confirmed: original.control.checked};
      if (choice.value === "etsy_draft" && shop.value) payload.shop = shop.value;
      if (choice.value === "shopify_draft" && store.value) payload.shop = store.value;
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

  function shopifyStores(state) {
    const stores = array(state.stores), root = el("div");
    if (stores.length) {
      const list = el("div", "row-list");
      stores.forEach(item => list.append(append(el("div", "row"), append(el("div", "row-main"), el("strong", "", item.name || item.domain),
          el("div", "row-meta", `${item.domain}${item.currency ? ` · ${item.currency}` : ""} · ${item.connected ? "connected" : "not checked"}`)),
        append(el("div", "actions"), button("Check", () => act(result => result.message, () => mutate(`/api/business/shopify/stores/${encodeURIComponent(item.id)}/check`)).then(() => render()), "button small"),
          button("Disconnect", () => act(result => result.message, () => api(`/api/business/shopify/stores/${encodeURIComponent(item.id)}`, {method: "DELETE"})).then(() => render()), "button small ghost")))));
      root.append(list, hint("Draft products go to the store you choose, and orders from every store are imported as sales on the Money page."));
    }
    if (stores.length >= (state.max || 5)) return root;
    const form = el("form"), address = input("my-store.myshopify.com", ""), clientId = input("Client ID", ""), secret = input("Client secret", "", "password"), save = submitButton(stores.length ? "Add this store" : "Connect store");
    secret.autocomplete = "off";
    append(form, stores.length ? el("h4", "", `Add another store (${stores.length} of ${state.max || 5})`) : null,
      hint("In Shopify's Dev Dashboard (dev.shopify.com), from the organization that owns the store: create an app, and under Versions give it the scopes write_products and read_orders and release it. Install it on the store from the app's Home, then copy the Client ID and secret from Settings. The secret is stored encrypted on this computer."),
      field("Store address", address), field("Client ID", clientId), field("Client secret", secret), actionsRow(save));
    wireForm(form, save, async () => { const result = await mutate("/api/business/shopify/stores", {domain: address.value.trim(), client_id: clientId.value.trim(), client_secret: secret.value.trim()}); toast(result.message); render(); });
    return append(root, form);
  }

  function connectionView() {
    const root = el("div", "connection-grid"), token = renderToken;
    (async () => {
      const [connections, mail, notifications, stores] = await Promise.all([api("/api/business/connections"), api("/api/business/gmail"), api("/api/business/notifications"), api("/api/business/shopify")]);
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
          append(buttons, button("Authorize Etsy…", () => act(value => value.message, () => mutate("/api/business/connections/etsy/authorize"))), button("Finish authorization", () => act(value => { callback.value = ""; result.textContent = value.message; render(); return value.message; }, () => mutate("/api/business/connections/etsy/finish", {redirected_url: callback.value.trim()}))));
          const shops = array(saved.shops);
          if (shops.length) {
            const list = el("div", "row-list");
            shops.forEach((item, index) => list.append(append(el("div", "row"), append(el("div", "row-main"), el("strong", "", item.shop_name || (item.shop_id ? `Shop ${item.shop_id}` : "Shop not checked yet")),
                el("div", "row-meta", index ? "Another shop" : "Your first shop")),
              index ? button("Disconnect", () => act(value => value.message, () => api(`/api/business/connections/etsy/shops/${encodeURIComponent(item.id)}`, {method: "DELETE"})).then(() => render()), "button small ghost") : null)));
            const room = shops.length < (saved.max_shops || 5);
            append(form, el("h4", "", `Your Etsy shops (${shops.length} of ${saved.max_shops || 5})`), list,
              hint("Sell different products in each shop: Cerebra won't draft an item that already has a draft in another of your shops, because Etsy forbids duplicate listings. To add a shop, sign out of Etsy in your browser, press Add another shop…, sign in as that shop's own Etsy account, then paste the address you land on and press Finish authorization. Step-by-step: How to connect…"),
              room && saved.connected ? actionsRow(button("Add another shop…", () => act(value => value.message, () => mutate("/api/business/connections/etsy/authorize?add=true")))) : null);
          }
        }
        append(form, buttons, result); wireForm(form, save, async () => { const values = Object.fromEntries(Object.entries(controls).map(([key, control]) => [key, control.value])); await mutate(`/api/business/connections/${provider}`, {values}, "PUT"); spec.fields.forEach(([key,,secret]) => { if (secret) controls[key].value = ""; }); result.textContent = "Settings saved. Check the connection next."; });
        root.append(panel(spec.title, body(withNotes(form, provider)), button("How to connect…", () => guideDialog(provider), "button small ghost")));
      }
      root.append(panel("Shopify stores", body(withNotes(shopifyStores(stores), "shopify")), button("How to connect…", () => guideDialog("shopify"), "button small ghost")));
      const gmailForm = el("form"), clientId = input("Google Desktop app OAuth client ID", mail.client_id || ""), secret = input("Google client secret", ""); secret.type = "password"; secret.autocomplete = "off";
      const saveMail = submitButton("Save Google settings"), query = input("Gmail search", "newer_than:7d"), messages = el("div"), mailState = el("div", mail.expired ? "hint warn" : "hint", mail.expired ? `Google ended the sign-in for ${mail.email}, so nothing can be sent or read. Press Connect Gmail… again. If your Google Cloud app is in Testing, publish it (OAuth consent screen › Publish app) so the sign-in no longer ends after 7 days.` : mail.connected ? (mail.can_send ? `Connected: ${mail.email} (reads, and sends what you send from Prospects)` : `Connected read-only: ${mail.email}. Connect Gmail again and allow sending to email businesses from Prospects.`) : "Not connected");
      append(gmailForm, mailState, hint("Enable Gmail API in your own Google Cloud project and create a Desktop app OAuth client. Sign-in opens Google's page. Cerebra reads messages to see wins and replies, and sends only the emails you send from Prospects (or Automatic outreach, if you switch it on). It never deletes or changes mail. Messages are not automatically given to AI."), field("Client ID", clientId), field("Client secret", secret), actionsRow(saveMail, button("Connect Gmail…", () => act(value => value.message, () => mutate("/api/business/gmail/authorize"))), button("Disconnect Gmail", () => act(value => { mailState.textContent = "Disconnected"; messages.replaceChildren(); return value.message; }, () => mutate("/api/business/gmail", undefined, "DELETE")))), field("Search your inbox", query), button("Read matching messages", async () => { try { const items = await api(`/api/business/gmail/messages?query=${encodeURIComponent(query.value)}&limit=10`); messages.replaceChildren(...items.map(item => { const card = el("div", "action-card"); append(card, el("strong", "", item.subject), el("div", "row-meta", item.from), el("p", "mail-text", item.body || item.snippet), button("Use as business brief…", () => businessForm({title: item.subject.slice(0,120), brief: item.body || item.snippet}))); return card; })); if (!items.length) messages.textContent = "No matching messages."; } catch (issue) { notice(issue.message, true); } }), messages);
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
    append(node, kv([["This version", data.version], ["Updates from", "Cerebra's releases"]]), state, notes, log);
    const check = button("Check for updates", () => run(), "button primary");
    state.append(actionsRow(check), hint("Checks Cerebra's public releases. Updating closes Cerebra, installs the new version and reopens it; running tasks are paused and can be resumed."));
    async function run() {
      check.disabled = true; check.textContent = "Checking…";
      const install = button("Install and restart", async () => {
        install.disabled = true;
        const result = await act(value => value.message, () => mutate("/api/updates/install", {}, "POST", 60000));
        if (result) state.replaceChildren(el("div", "notice", `${result.message} A small window shows each step while Cerebra is closed.`)); else install.disabled = false;
      }, "button primary");
      const showReady = progress => {
        if (progress?.phase !== "ready") return false;
        state.replaceChildren(hint(progress.message || `Cerebra ${String(progress.tag || "").replace(/^v/, "")} is downloaded and verified. It can be installed without another GitHub check.`), actionsRow(install));
        notes.replaceChildren();
        return true;
      };
      // Installation is a local operation. A failed/rate-limited release lookup must never hide it.
      let local = data.update_progress;
      try { local = await api("/api/updates/progress", {timeout: 10000}); } catch { /* keep the last local status */ }
      if (showReady(local)) return;
      let info;
      try { info = await api("/api/updates", {timeout: 90000}); }
      catch (issue) {
        try { local = await api("/api/updates/progress", {timeout: 10000}); } catch { /* retain local status */ }
        if (!showReady(local)) state.replaceChildren(hint(issue.message, true), actionsRow(button("Try again", () => run(), "button")));
        return;
      }
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
      if (info.available) actions.append(info.downloaded ? install : download);
      if (info.available && !info.downloaded && ["starting", "downloading", "verifying"].includes(data.update_progress?.phase)) { download.disabled = true; download.textContent = "Downloading in the background…"; watch(); }
      actions.append(button("Check again", () => run(), "button ghost"));
      fill(state, append(el("div", "row-meta"), badge(info.available ? "update available" : "up to date", info.available ? "green" : "muted"), el("span", "", info.message)),
        !info.installed && info.available ? hint("You're running Cerebra from source: update it with git pull instead.", true) : null, info.installed || !info.available ? actions : null);
      notes.replaceChildren(info.available && info.notes ? append(el("details", "update-notes"), el("summary", "", `What's new in ${info.latest}`), markdown(info.notes)) : el("span"));
      log.replaceChildren(array(info.last_log).length ? append(el("details"), el("summary", "", "Last update log"), code(info.last_log.join("\n"))) : el("span"));
    }
    if (data.update_progress?.phase === "ready") run();
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
    const fields = [["name", "Name", "e.g. Alex Rivera"], ["headline", "What you do", "e.g. Software engineer and AI builder"], ["email", "Email", "the address you want on your work"],
      ["github", "GitHub username", "e.g. your-github-name"], ["linkedin", "LinkedIn", "https://www.linkedin.com/in/…"], ["website", "Website", "https://…"], ["location", "Location", "e.g. Austin, TX"]];
    fields.forEach(([key, label, hint_]) => { inputs[key] = input(hint_); grid.append(field(label, inputs[key])); });
    inputs.bio = textarea("A few sentences about you: your background, what you build, what you're proud of."); inputs.preferences = textarea("How you like things done: tone, colours, style, what to avoid.");
    const share = check("Share these details with the AI team (Support, the Council and coding tasks)", true);
    const fromGitHub = button("Use my GitHub login", async () => { const found = await act(null, () => api("/api/owner/github")); if (found?.github) { inputs.github.value = found.github; toast(`GitHub username: ${found.github}`); } }, "button small ghost");
    append(form, hint("ChatGPT's and Claude's own memories aren't shared with Cerebra. Fill this in once so portfolios, READMEs and replies use your real details instead of placeholders. Only put here what you'd put on a public profile; never passwords or keys."),
      grid, append(el("div", "row-meta"), fromGitHub), field("About you", inputs.bio), field("How you like things done", inputs.preferences), share.wrap);
    const save = submitButton("Save");
    const clear = button("Clear my details", async () => {
      if (!window.confirm("Clear everything in this section? Your name and links leave Cerebra, and the AI team stops using them.")) return;
      const blank = Object.fromEntries(Object.keys(inputs).map(key => [key, ""]));
      if (await act("Cleared.", () => mutate("/api/owner", {...blank, share: false}, "PUT"))) { Object.values(inputs).forEach(control => { control.value = ""; }); share.control.checked = false; }
    }, "button ghost");
    form.append(actionsRow(save, clear));
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
  function backupsPanel() {
    const root = el("div");
    root.append(el("p", "row-meta", "Loading…"));
    api("/api/backups").then(state => {
      const form = el("form"), folder = input("D:\\Backups", state.extra_folder || ""), save = submitButton("Save folder"), pending = array(state.backups).find(item => item.name === state.restore_pending);
      append(form, field("Second folder (optional)", folder, "A copy on the same disk won't survive that disk failing. Use an external drive or a folder that syncs. It holds your business records, so choose somewhere you trust."), actionsRow(save));
      wireForm(form, save, async () => { await mutate("/api/backups/settings", {folder: folder.value}, "PUT"); toast("Saved."); render(); });
      const latest = array(state.backups)[0];
      append(root.replaceChildren() || root,
        state.problem ? hint(state.problem, true) : null,
        pending ? append(el("div"), hint(`Going back to ${pending.label}: close Cerebra completely and open it again to finish.`, true),
          actionsRow(button("Don't go back", () => act("Cancelled.", () => api("/api/backups/restore", {method: "DELETE"})).then(() => render()), "button small ghost"))) : null,
        hint(latest ? `Last backup: ${latest.label}. Each one is checked before it counts. The last 7 days and 4 weeks are kept in ${state.folder}.` : "The first backup is made within the hour."),
        hint("This covers everything in Cerebra's records. Book files and covers aren't included, and on another computer you'd connect your accounts again."),
        actionsRow(button("Back up now", () => act(result => result.error || result.warning || "Backed up and checked.", () => mutate("/api/backups/run", {}, "POST", 120000)).then(() => render()), "button small")),
        array(state.backups).length ? table(["Backup", "Size", ""], state.backups.map(item => [item.label, `${(item.bytes / 1048576).toFixed(1)} MB`,
          button("Go back to this", () => { if (window.confirm(`Go back to ${item.label}? Everything recorded since then leaves Cerebra. Your current data is kept in the backups folder.`)) act(result => result.message, () => mutate("/api/backups/restore", {name: item.name})).then(() => render()); }, "button small ghost")])) : null,
        form);
    }).catch(issue => root.replaceChildren(hint(issue.message, true)));
    return root;
  }
  // Text size, colours and the menu, the same switches as the side menu, where anyone looks for them first.
  function appearancePanel() {
    const choice = (label, key, value) => {
      const node = button(label, () => { setComfort(key, value); render(); }, "segment");
      node.setAttribute("aria-pressed", String(String(comfort[key]) === String(value)));
      return node;
    };
    const setting = (label, note, ...choices) => append(el("div", "setting-row"), append(el("div"), el("strong", "", label), el("small", "", note)),
      append(el("div", "segmented"), ...choices));
    return panel("How Cerebra looks", body(
      setting("Text size", "Every page follows it.", choice("Normal", "size", "normal"), choice("Large", "size", "large"), choice("Largest", "size", "huge")),
      setting("Colours", "Remembered on this computer.", choice("Light", "theme", "light"), choice("Dark", "theme", "dark")),
      setting("Menu", "The coding pages are hidden until you need them.", choice("Everyday pages", "simple", true), choice("All pages", "simple", false))));
  }
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
    root.append(appearancePanel());
    root.append(panel("AI helpers: permission to work", body(permissions)));
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
    const updates = panel("Updates", body(updatesPanel())); updates.id = "updates-panel"; root.append(updates);
    root.append(panel("Backups", body(backupsPanel())));

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
      const status = $("#connection-status"); status.className = "pill good"; status.replaceChildren(el("span", "dot"), document.createTextNode("Connected")); notice("");
      if (force || fingerprint !== lastFingerprint) { lastFingerprint = fingerprint; if (["overview", "tasks", "projects", "approvals", "reports", "activity"].includes(page) || force) render(); else chrome(); if (page === "system" && !force) paintTeamBar(); }
      if (detailTaskId && dialog.open) await taskDetail(detailTaskId, true);
    } catch (issue) { const status = $("#connection-status"); status.className = "pill bad"; status.replaceChildren(el("span", "dot"), document.createTextNode("Not connected")); notice(`Cerebra isn't answering right now. Close it and open it again. (${issue.message})`, true); }
    finally { fetching = null; done(); }
  }
  function route() { const [name, ...rest] = location.hash.slice(1).split("/"); page = Object.hasOwn(pages, name) ? name : "overview"; param = rest.join("/"); if (page === "job" && !param) page = "business"; if (page === "report" && !param) page = "reports"; render(); }
  window.addEventListener("hashchange", route);
  // The top bar's update button opens Settings › Updates itself: a plain link did nothing when Settings was already open,
  // and otherwise left the Updates panel far below the fold.
  $("#update-status").addEventListener("click", event => {
    event.preventDefault();
    const show = (tries = 20) => { const target = document.getElementById("updates-panel"); if (target) target.scrollIntoView({behavior: "smooth", block: "start"}); else if (tries) setTimeout(() => show(tries - 1), 100); };
    if (page !== "settings") location.hash = "settings";
    show();
  });
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
