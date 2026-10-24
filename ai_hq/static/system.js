"use strict";
// System view: a live map of AI HQ's real backend parts, driven only by recorded telemetry.
window.AIHQSystem = (() => {
  const SVG = "http://www.w3.org/2000/svg";
  const W = 190, H = 92;
  const NODES = [
    {id: "browser", kind: "YOU", title: "This window", x: 30, y: 60, plain: "Where you see everything and give your yes or no. It talks only to the server on this computer.", where: () => "Your AI HQ window"},
    {id: "server", kind: "LOCAL SERVER", title: "Web server", x: 30, y: 250, plain: "A small private web server (FastAPI) on 127.0.0.1. Only this computer can reach it. Every request needs your private session.", where: system => system?.server},
    {id: "supervisor", kind: "CONTROL", title: "Supervisor", x: 275, y: 155, plain: "The boss. A plain Python program (no AI) that follows fixed rules: it hands out work, runs the tests, and always stops to ask you before anything important.", where: () => "Python state machine inside the server"},
    {id: "planner", kind: "AI · PLAN", title: "Planner", x: 525, y: 30, plain: "An AI (usually Claude) reads the project and writes a plan. It can read files but cannot change anything.", where: () => "Read-only copy of your project"},
    {id: "coder", kind: "AI · CODE", title: "Coder", x: 525, y: 200, plain: "An AI (usually Codex) writes the code in a separate copy of your project. It may only change the files you allowed.", where: () => "Its own working copy (Git worktree)"},
    {id: "reviewer", kind: "AI · REVIEW", title: "Reviewer", x: 525, y: 370, plain: "A different AI checks the code, like a second pair of eyes. It reads a frozen snapshot and cannot change it.", where: () => "Read-only review snapshot"},
    {id: "worktree", kind: "GIT", title: "Working copy", x: 775, y: 115, plain: "A separate copy of your project on its own branch. The AI works here, so your real code stays safe until you approve.", where: system => system?.worktrees?.path},
    {id: "tests", kind: "VERIFY", title: "Test runner", x: 775, y: 290, plain: "Runs your project's own tests on the AI's code. The AI cannot fake this: the supervisor runs the tests itself.", where: () => "Your project's test commands"},
    {id: "gate", kind: "YOU DECIDE", title: "Approval gate", x: 1000, y: 60, plain: "Nothing important happens without your yes: the plan, letting agents run, and adding the code to your project.", where: () => "Approvals page"},
    {id: "project", kind: "RESULT", title: "Your project", x: 1000, y: 250, plain: "Your real repository. Finished, tested, reviewed code is merged here only after you approve. Nothing is pushed to GitHub unless you press Push.", where: (system, task, telemetry, overview) => overview?.projects?.find(project => project.id === task?.project_id)?.path || "Projects page"},
    {id: "database", kind: "STORAGE", title: "Database", x: 275, y: 470, plain: "A single file that remembers every task, step, test result and decision, so nothing is lost when you close AI HQ.", where: system => system?.database?.path},
    {id: "logs", kind: "STORAGE", title: "Run logs", x: 775, y: 470, plain: "One text file per AI run, with exactly what the AI said (secrets removed).", where: system => system?.logs?.path}
  ];
  const EDGES = [["browser", "server"], ["server", "supervisor"], ["supervisor", "planner"], ["supervisor", "coder"], ["supervisor", "reviewer"], ["coder", "worktree"], ["planner", "worktree"], ["reviewer", "worktree"], ["supervisor", "tests"], ["tests", "worktree"], ["supervisor", "gate"], ["gate", "project"], ["worktree", "project"], ["supervisor", "database"], ["supervisor", "logs"]];
  let dispose = null, refreshNow = null;

  function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined && text !== null) node.textContent = String(text); return node; }
  function svg(tag, attributes = {}, text) { const node = document.createElementNS(SVG, tag); Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value)); if (text !== undefined) node.textContent = text; return node; }
  function append(parent, ...nodes) { nodes.flat().forEach(node => { if (node) parent.append(node); }); return parent; }
  const duration = seconds => seconds === null || seconds === undefined ? "—" : seconds < 60 ? `${seconds.toFixed(0)}s` : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  const clock = value => value ? new Date(value).toLocaleTimeString([], {hour12: false}) : "—";
  const short = (value, size = 24) => { const text = String(value ?? ""); return text.length > size ? text.slice(0, size - 1) + "…" : text; };

  function unmount() { if (dispose) dispose(); dispose = null; refreshNow = null; }
  function update() { if (refreshNow) refreshNow(); }

  function mount(container, {api, overview, inspect, report}) {
    unmount();
    let disposed = false, timer = 0, telemetry = null, system = null, selected = "supervisor", focusTask = "";
    const root = el("div"), layout = el("div", "system"), lower = el("div", "system-lower");
    const toolbar = el("div", "follow"), taskPicker = el("select");
    taskPicker.setAttribute("aria-label", "Task to follow");
    taskPicker.addEventListener("change", () => { focusTask = taskPicker.value; paint(); });
    append(toolbar, el("span", "row-meta", "Follow:"), taskPicker);
    const wrap = el("div", "diagram-wrap"), diagram = svg("svg", {class: "diagram", viewBox: "0 0 1220 590", role: "img", "aria-label": "Live map of AI HQ's backend"});
    wrap.append(diagram);
    const legend = append(el("div", "legend"), el("span", "l-active", "working now"), el("span", "l-wait", "waiting for you"), el("span", "l-ok", "ready / done"), el("span", "l-fail", "problem"));
    const traceBody = el("div", "trace"), ledger = el("div");
    const inspector = el("div", "panel-body inspector");
    append(lower, panel("Inspector — click any part of the map", inspector), panel("Live trace — what the backend just did", traceBody));
    append(layout, toolbar, append(el("div"), wrap, legend), lower, panel("Run ledger — every AI run, measured", ledger));
    root.append(layout); container.replaceChildren(root);

    function panel(title, body) { const node = el("section", "panel"), header = el("div", "panel-header"); header.append(el("h2", "", title)); append(node, header, body); return node; }

    const edgeNodes = {}, nodeNodes = {};
    const center = node => ({x: node.x + W / 2, y: node.y + H / 2});
    const byId = Object.fromEntries(NODES.map(node => [node.id, node]));
    EDGES.forEach(([from, to]) => {
      const a = byId[from], b = byId[to], start = center(a), end = center(b);
      const horizontal = Math.abs(end.x - start.x) > Math.abs(end.y - start.y);
      const p1 = horizontal ? {x: a.x + (end.x > start.x ? W : 0), y: start.y} : {x: start.x, y: a.y + (end.y > start.y ? H : 0)};
      const p2 = horizontal ? {x: b.x + (end.x > start.x ? 0 : W), y: end.y} : {x: end.x, y: b.y + (end.y > start.y ? 0 : H)};
      const bend = horizontal ? `C ${(p1.x + p2.x) / 2} ${p1.y}, ${(p1.x + p2.x) / 2} ${p2.y},` : `C ${p1.x} ${(p1.y + p2.y) / 2}, ${p2.x} ${(p1.y + p2.y) / 2},`;
      const path = svg("path", {class: "edge", d: `M ${p1.x} ${p1.y} ${bend} ${p2.x} ${p2.y}`});
      edgeNodes[`${from}>${to}`] = path; diagram.append(path);
    });
    NODES.forEach(node => {
      const group = svg("g", {class: "node", transform: `translate(${node.x} ${node.y})`, tabindex: "0", role: "button", "aria-label": node.title});
      append(group, svg("rect", {class: "box", width: W, height: H, rx: 10}), svg("circle", {class: "led", cx: W - 16, cy: 16, r: 5}), svg("text", {class: "kind", x: 14, y: 22}, node.kind), svg("text", {class: "title", x: 14, y: 45}, node.title));
      const line1 = svg("text", {class: "status", x: 14, y: 66}, ""), line2 = svg("text", {class: "status", x: 14, y: 82}, "");
      append(group, line1, line2);
      const choose = () => { selected = node.id; paint(); };
      group.addEventListener("click", choose); group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
      nodeNodes[node.id] = {group, line1, line2}; diagram.append(group);
    });

    function currentTask() {
      const tasks = (telemetry?.tasks || []).filter(task => task.mode !== "mock");
      if (focusTask) return tasks.find(task => task.id === focusTask) || null;
      return tasks.find(task => ["RUNNING", "VERIFYING", "REVIEWING", "NEEDS_CHANGES", "PLANNING"].includes(task.state))
        || tasks.find(task => (telemetry?.approvals || []).some(approval => approval.task_id === task.id))
        || tasks[0] || null;
    }
    function computeStates(task) {
      const state = Object.fromEntries(NODES.map(node => [node.id, ""])), edges = {};
      const online = !!telemetry;
      state.browser = online ? "ok" : "failed"; state.server = online ? "ok" : "failed"; state.database = online ? "ok" : ""; state.logs = system?.logs?.files ? "ok" : "";
      if (!task) return {state, edges};
      const runs = (telemetry.runs || []).filter(run => run.task_id === task.id);
      const running = runs.find(run => run.status === "running");
      const pending = (telemetry.approvals || []).filter(approval => approval.task_id === task.id);
      const flow = (...pairs) => pairs.forEach(pair => { edges[pair] = "active"; });
      const done = (...pairs) => pairs.forEach(pair => { if (!edges[pair]) edges[pair] = "done"; });
      state.supervisor = ["RUNNING", "VERIFYING", "REVIEWING", "NEEDS_CHANGES"].includes(task.state) ? "active" : "ok";
      if (runs.some(run => run.role === "plan" && run.status === "succeeded")) { state.planner = "ok"; done("supervisor>planner", "planner>worktree"); }
      if (runs.some(run => run.role === "implement" && run.status === "succeeded")) { state.coder = "ok"; done("supervisor>coder", "coder>worktree"); }
      if (runs.some(run => run.role === "review" && run.status === "succeeded")) { state.reviewer = "ok"; done("supervisor>reviewer", "reviewer>worktree"); }
      if (task.test_commands) { state.tests = task.tests_passed === task.test_commands ? "ok" : "failed"; done("supervisor>tests", "tests>worktree"); }
      if (task.state !== "PENDING") state.worktree = "ok";
      runs.filter(run => run.status === "failed").forEach(run => { state[{plan: "planner", implement: "coder", review: "reviewer"}[run.role]] = "failed"; });
      if (running) {
        const node = {plan: "planner", implement: "coder", review: "reviewer"}[running.role];
        state[node] = "active"; flow("server>supervisor", `supervisor>${node}`, `${node}>worktree`);
      } else if (task.state === "VERIFYING") { state.tests = "active"; flow("supervisor>tests", "tests>worktree"); }
      if (pending.length) { state.gate = "waiting"; flow("supervisor>gate"); if (pending.some(approval => approval.kind === "merge")) edges["browser>server"] = "active"; }
      if (task.state === "COMPLETED") { state.gate = "ok"; state.project = "ok"; done("supervisor>gate", "gate>project", "worktree>project"); }
      if (task.state === "FAILED") state.supervisor = "failed";
      return {state, edges};
    }
    function statusLines(task) {
      const runs = (telemetry?.runs || []).filter(run => run.task_id === task?.id), data = overview(), models = task ? (data?.tasks?.find(item => item.id === task.id)?.results?.models || {}) : {};
      const roleRun = role => runs.find(run => run.role === role);
      const runLine = role => { const run = roleRun(role); if (!run) return "not started"; return run.status === "running" ? `working · ${duration(run.elapsed_seconds)}` : `${run.status} · ${duration(run.duration_seconds)}`; };
      const label = (key, fallback) => short(models[key]?.label || data?.profiles?.find(profile => profile.id === data?.roles?.[key])?.label || fallback, 23);
      const pending = (telemetry?.approvals || []).length;
      return {
        browser: [telemetry ? "connected" : "offline", "you are in control"],
        server: [short(system?.server?.replace("http://", "") || "127.0.0.1"), `v${system?.version || ""} · private`],
        supervisor: [task ? `task ${task.id.slice(0, 8)}` : "idle", task ? short(task.state.replaceAll("_", " ").toLowerCase(), 23) : `queue: ${system?.queue ?? 0}`],
        planner: [label("planner", "Claude"), task ? runLine("plan") : "waiting for a task"],
        coder: [label("implementer", "Codex"), task ? runLine("implement") : "waiting for a task"],
        reviewer: [label("reviewer", "Claude"), task ? runLine("review") : "waiting for a task"],
        worktree: [`${system?.worktrees?.count ?? 0} working copies`, task ? "isolated branch" : "—"],
        tests: [task?.test_commands ? `${task.tests_passed}/${task.test_commands} passed` : "no run yet", task ? `${task.retry_count} repair(s)` : "—"],
        gate: [pending ? `${pending} waiting for you` : "nothing to decide", task?.state === "AWAITING_APPROVAL" ? "your turn" : "—"],
        project: [short(data?.projects?.find(project => project.id === task?.project_id)?.name || "—"), task?.state === "COMPLETED" ? "merged ✓" : "unchanged until you approve"],
        database: [`${((system?.database?.bytes || 0) / 1024).toFixed(0)} KB`, `${(telemetry?.runs || []).length} runs recorded`],
        logs: [`${system?.logs?.files ?? 0} log files`, "secrets removed"]
      };
    }
    function paint() {
      const task = currentTask(), {state, edges} = computeStates(task), lines = statusLines(task);
      const tasks = (telemetry?.tasks || []).filter(item => item.mode !== "mock");
      const options = [["", "Most active task"], ...tasks.slice(0, 30).map(item => [item.id, short(item.description, 60)])];
      if (taskPicker.options.length !== options.length || [...taskPicker.options].some((item, index) => item.value !== options[index][0])) {
        taskPicker.replaceChildren(...options.map(([value, label]) => { const item = el("option", "", label); item.value = value; return item; }));
        taskPicker.value = focusTask;
      }
      NODES.forEach(node => { const parts = nodeNodes[node.id]; parts.group.setAttribute("class", `node ${state[node.id] || ""}${selected === node.id ? " selected" : ""}`); parts.line1.textContent = lines[node.id][0]; parts.line2.textContent = lines[node.id][1]; });
      Object.entries(edgeNodes).forEach(([key, path]) => path.setAttribute("class", `edge ${edges[key] || ""}`));
      const node = byId[selected], details = el("dl", "kv");
      [["Now", lines[selected].join(" · ")], ["Lives at", node.where(system, task, telemetry, overview()) || "—"], ["Task", task ? short(task.description, 80) : "none"]].forEach(([key, value]) => append(details, el("dt", "", key), el("dd", "", value)));
      const actions = el("div", "actions");
      if (task) append(actions, button("Open task", () => inspect(task.id)), button("Plain report", () => report(task.id)));
      inspector.replaceChildren(el("div", "eyebrow", node.kind), el("h3", "", node.title), el("p", "plain", node.plain), details, actions);
      const trace = [...(telemetry?.events || []).filter(event => !task || !focusTask || event.task_id === task.id).map(event => ({at: event.created_at, kind: event.kind, text: event.message})),
        ...(telemetry?.runs || []).filter(run => run.source === "live").slice(0, 30).map(run => ({at: run.finished_at || run.started_at, kind: `${run.agent}:${run.role}`, text: run.status === "running" ? `running for ${duration(run.elapsed_seconds)}` : `${run.status} in ${duration(run.duration_seconds)}${run.error ? " — " + short(run.error, 90) : ""}`}))]
        .sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 80);
      traceBody.replaceChildren(...(trace.length ? trace.map(item => append(el("div"), el("time", "", clock(item.at)), el("span", "k", item.kind), el("span", "", item.text))) : [el("div", "", "No activity recorded yet.")]));
      const runs = (telemetry?.runs || []).filter(run => run.source === "live").slice(0, 25);
      const metrics = telemetry?.metrics?.live || {}, summary = el("div", "panel-body row-meta");
      Object.entries(metrics).forEach(([provider, value]) => summary.append(el("span", "badge muted", `${provider}: ${value.runs} runs · ${value.success_percent ?? "—"}% ok · avg ${duration(value.mean_duration_seconds)}`)));
      const table = el("table"), head = el("tr"); ["When", "Agent", "Role", "Result", "Time"].forEach(label => head.append(el("th", "", label))); table.append(head);
      runs.forEach(run => { const row = el("tr"); [clock(run.started_at), run.agent, run.role, run.status, duration(run.duration_seconds ?? run.elapsed_seconds)].forEach(value => row.append(el("td", "", value))); table.append(row); });
      ledger.replaceChildren(summary, runs.length ? append(el("div", "table-wrap"), table) : el("div", "panel-body", "No AI runs yet."), el("div", "panel-body hint", telemetry?.measurement_note || ""));
    }
    function button(label, action) { const node = el("button", "button small", label); node.type = "button"; node.addEventListener("click", action); return node; }
    async function load() {
      if (disposed) return;
      try { [telemetry, system] = await Promise.all([api("/api/telemetry"), api("/api/system")]); } catch { telemetry = null; }
      if (disposed) return;
      paint();
      clearTimeout(timer); timer = setTimeout(() => { if (!document.hidden) load(); else timer = setTimeout(load, 2000); }, 2000);
    }
    paint(); load();
    refreshNow = () => paint();
    dispose = () => { disposed = true; clearTimeout(timer); };
  }
  return {mount, unmount, update};
})();
