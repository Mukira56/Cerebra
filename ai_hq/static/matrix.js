"use strict";
// A circuit representation of orchestration state, not a picture of model internals.
window.AIHQMatrix = (() => {
  const stations = [
    {id:"supervisor",title:"SUPERVISOR",sub:"PLAN / COORDINATE",x:395,y:55,w:145,h:105,color:"#ffa94d"},
    {id:"codex",title:"CODEX",sub:"OPENAI / CLI",x:115,y:280,w:170,h:205,color:"#71b8ff"},
    {id:"claude",title:"CLAUDE",sub:"ANTHROPIC / CLI",x:665,y:105,w:225,h:165,color:"#50ead9"},
    {id:"review",title:"REVIEW",sub:"INDEPENDENT CHECK",x:390,y:390,w:170,h:145,color:"#ff7a99"},
    {id:"verify",title:"VERIFICATION",sub:"LOCAL TEST RUNNER",x:705,y:390,w:205,h:165,color:"#a8f273"},
    {id:"approval",title:"HUMAN GATE",sub:"YOUR APPROVAL",x:120,y:100,w:155,h:100,color:"#35ef9c"}
  ];
  const routes = [["approval","supervisor"],["supervisor","codex"],["supervisor","claude"],["codex","review"],["claude","review"],["review","verify"],["verify","approval"],["claude","verify"]];
  let dispose = null;
  function node(tag, cls, text) { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=String(text);return e; }
  function add(parent,...children) {children.flat().forEach(child=>parent.append(child));return parent;}
  function control(text,action,cls="matrix-button") {const b=node("button",cls,text);b.type="button";b.onclick=action;return b;}
  function duration(value) {if(value===null || value===undefined)return "—";return value<60?`${value.toFixed(1)}s`:`${Math.floor(value/60)}m ${Math.floor(value%60)}s`;}
  function time(value) {return value?new Date(value).toLocaleTimeString([], {hour12:false}):"—";}
  function unmount() {if(dispose)dispose();dispose=null;}
  function mount(container,{api,inspect}) {
    unmount();
    let disposed=false,snapshot=null,source="live",selectedTask="",selected="codex",online=false;
    let motion=!matchMedia("(prefers-reduced-motion: reduce)").matches,frame=0,lastFrame=0,loading=false,simulationClock=0;
    const root=node("section","matrix-console"),toolbar=node("div","matrix-toolbar"),heading=node("div","matrix-wordmark");
    add(heading,node("strong","","AI HQ / MATRIX"),node("small","","ORCHESTRATION SIGNAL MONITOR"));
    const choices=node("div","matrix-modes"),sourceButtons={};
    for(const [value,label] of [["live","Live runs"],["mock","Mock runs"],["preview","Preview"]]) {
      sourceButtons[value]=control(label,()=>{source=value;selectedTask="";paintPanels();});choices.append(sourceButtons[value]);
    }
    const pause=control(motion?"Pause animation":"Resume animation",()=>{motion=!motion;pause.textContent=motion?"Pause animation":"Resume animation";});
    const expand=control("Expand view",()=>{
      root.classList.toggle("matrix-expanded");expand.textContent=root.classList.contains("matrix-expanded")?"Exit expanded view":"Expand view";
    });
    add(toolbar,heading,choices,pause,expand);
    const banner=node("div","matrix-source-notice"),grid=node("div","matrix-grid"),left=node("aside","matrix-rail"),middle=node("div","matrix-center"),right=node("aside","matrix-rail");
    const selector=node("select","matrix-select");selector.setAttribute("aria-label","Matrix task filter");
    selector.onchange=()=>{selectedTask=selector.value;paintPanels();};
    const queue=node("div","matrix-queue"),events=node("div","matrix-events"),runlist=node("div","matrix-run-list"),metrics=node("div","matrix-metrics"),details=node("div","matrix-detail");
    add(left,node("h2","matrix-caption","ASSIGNMENT BUS"),selector,queue,node("h2","matrix-caption","EVENT TRACE"),events);
    const summary=node("div","matrix-summary"),stageWrap=node("div","matrix-stage-wrap"),stage=node("div","matrix-stage"),canvas=node("canvas","matrix-canvas");
    canvas.width=1050;canvas.height=650;canvas.setAttribute("aria-hidden","true");
    stage.append(canvas);
    const stationButtons={};
    for(const station of stations) {
      const button=control("",()=>{selected=station.id;paintPanels();},"matrix-station");
      button.style.left=`${station.x/10.5}%`;button.style.top=`${station.y/6.5}%`;button.style.width=`${station.w/10.5}%`;button.style.height=`${station.h/6.5}%`;
      button.style.setProperty("--signal",station.color);button.setAttribute("aria-label",`Inspect ${station.title}`);
      add(button,node("strong","",station.title),node("small","",station.sub),node("span","matrix-station-state","IDLE"));
      stationButtons[station.id]=button;stage.append(button);
    }
    const map=node("div","matrix-minimap"),mini=node("canvas");mini.width=160;mini.height=95;
    add(map,node("small","","TOPOLOGY / 06 NODES"),mini);stage.append(map);
    add(stageWrap,stage);add(middle,summary,stageWrap,node("p","matrix-explanation","Signals map recorded orchestration stages. The network drawing is a visualization, not model internals."));
    add(right,node("h2","matrix-caption","NODE INSPECTOR"),details,node("h2","matrix-caption","MEASURED PERFORMANCE"),metrics,node("h2","matrix-caption","RUN LEDGER"),runlist);
    add(grid,left,middle,right);const footer=node("div","matrix-footer");add(root,toolbar,banner,grid,footer);container.replaceChildren(root);
    const context=canvas.getContext("2d"),miniContext=mini.getContext("2d");
    function tasks() {return (snapshot?.tasks||[]).filter(t=>t.mode===source);}
    function runs() {return (snapshot?.runs||[]).filter(r=>r.source===source && (!selectedTask || r.task_id===selectedTask));}
    function scopedTasks() {return tasks().filter(t=>!selectedTask || t.id===selectedTask);}
    function stateFor(id,clock=performance.now()) {
      if(source==="preview") {
        const phase=Math.floor(simulationClock/3500)%6,order=["supervisor","codex","verify","claude","review","approval"];
        return id===order[phase]?"PREVIEW":"STANDBY";
      }
      const records=runs(),taskRows=scopedTasks();
      if(id==="codex" || id==="claude") return records.some(r=>r.agent===id && r.status==="running")?"RUNNING":"IDLE";
      if(id==="review")return records.some(r=>r.role==="review" && r.status==="running")?"REVIEWING":"IDLE";
      if(id==="verify")return taskRows.some(t=>t.state==="VERIFYING")?"TESTING":"IDLE";
      if(id==="supervisor")return taskRows.some(t=>["RUNNING","VERIFYING","REVIEWING","NEEDS_CHANGES","PLANNING"].includes(t.state))?"WORKING":"IDLE";
      return (snapshot?.approvals||[]).some(a=>taskRows.some(t=>t.id===a.task_id))?"AWAITING YOU":"CLEAR";
    }
    function active(id,clock) {return (online || source==="preview") && motion && !["IDLE","CLEAR","STANDBY"].includes(stateFor(id,clock));}
    function stat(label,value,note) {const item=node("div","matrix-stat");add(item,node("small","",label),node("strong","",value));if(note)item.append(node("small","matrix-dim",note));return item;}
    function paintPanels() {
      if(disposed)return;
      Object.entries(sourceButtons).forEach(([key,b])=>{b.classList.toggle("selected",key===source);b.setAttribute("aria-pressed",String(key===source));});
      const preview=source==="preview";
      banner.className=`matrix-source-notice${preview?" preview":""}${!online?" disconnected":""}`;
      banner.textContent=preview?"SIMULATED PREVIEW · Illustrative signals only. No models or tasks are started; performance figures are hidden.":!online?"TELEMETRY DISCONNECTED · Showing the last snapshot. Activity animation is frozen.":`${source==="live"?"LIVE MODEL RUNS":"MOCK AGENT RUNS"} · Actual recorded task states, refreshed every 2 seconds. ${source==="mock"?"Agent behavior is simulated; configured tests still run locally.":"No inference is started by this view."}`;
      const taskRows=tasks();
      if(selectedTask && !taskRows.some(t=>t.id===selectedTask))selectedTask="";
      selector.replaceChildren(node("option","","All tasks in this feed"));selector.firstChild.value="";
      for(const task of taskRows) {const option=node("option","",task.description.slice(0,65));option.value=task.id;selector.append(option);}
      selector.value=selectedTask;selector.disabled=preview;
      queue.replaceChildren();
      if(preview)queue.append(node("p","matrix-dim","Preview cycles through the six orchestration stations. Switch to Live runs for actual activity."));
      else if(!scopedTasks().length)queue.append(node("p","matrix-dim",`No ${source} tasks recorded. Submit a task in Task console to populate this view.`));
      for(const task of scopedTasks().slice(0,7)) {
        const item=control("",()=>inspect(task.id),"matrix-task");add(item,node("small","",`${task.id.slice(0,8)} / ${task.mode.toUpperCase()}`),node("strong","",task.description.slice(0,105)),node("span","",task.state.replaceAll("_"," ")));queue.append(item);
      }
      const records=runs(),finished=records.filter(r=>r.finished_at),durations=finished.map(r=>r.duration_seconds).filter(v=>v!==null);
      summary.replaceChildren(stat("ACTIVE SIGNALS",preview?"SIM":String(records.filter(r=>r.status==="running").length)),stat("RECORDED RUNS",preview?"—":String(records.length)),stat("AVG RUN TIME",preview?"—":duration(durations.length?durations.reduce((a,b)=>a+b,0)/durations.length:null)),stat("TEST COMMANDS PASSED",preview?"—":String(scopedTasks().reduce((sum,t)=>sum+t.tests_passed,0))));
      for(const station of stations) {
        const button=stationButtons[station.id],state=stateFor(station.id);
        button.classList.toggle("selected",selected===station.id);button.classList.toggle("working",!["IDLE","CLEAR","STANDBY"].includes(state));
        button.setAttribute("aria-pressed",String(selected===station.id));button.querySelector(".matrix-station-state").textContent=state;
      }
      const station=stations.find(s=>s.id===selected),provider=["codex","claude"].includes(selected);
      const providerRuns=provider?records.filter(r=>r.agent===selected):records.filter(r=>selected==="review"?r.role==="review":true);
      details.replaceChildren(node("strong","matrix-node-title",station.title),node("span","matrix-node-state",stateFor(selected)),node("p","matrix-dim",provider?"Provider CLI state and measured wall-clock runtime.":selected==="approval"?"Human approvals are required before controlled actions advance.":"Deterministic supervisor stage; this is not a separate model."));
      const last=providerRuns[0];
      if(last && !preview)add(details,node("small","matrix-dim",`${last.role.toUpperCase()} / ${last.id.slice(0,8)}`),node("p","matrix-output",last.error || last.output_tail || (last.finished_at?"Open the task to inspect its complete recorded output.":"Run started. CLI output is recorded when the run finishes.")));
      metrics.replaceChildren();
      const complete=providerRuns.filter(r=>["succeeded","failed","interrupted"].includes(r.status));
      const success=complete.filter(r=>r.status==="succeeded").length,clocked=complete.map(r=>r.duration_seconds).filter(v=>v!==null);
      add(metrics,stat("RUN SUCCESS",preview || !complete.length?"—":`${Math.round(success*100/complete.length)}%`,`${preview?0:complete.length} finished runs in this view`),stat("AVERAGE WALL TIME",preview?"—":duration(clocked.length?clocked.reduce((a,b)=>a+b,0)/clocked.length:null)),stat("TOKENS / SECOND","—","Not reported by CLI integration"),stat("PROVIDER COST","—","Not reported by CLI integration"));
      const chart=node("div","matrix-history");chart.setAttribute("aria-label","Measured duration of the last 16 finished runs");
      const samples=preview?[]:clocked.slice(0,16).reverse(),max=Math.max(1,...samples);
      samples.forEach(value=>{const bar=node("span");bar.style.height=`${Math.max(2,value/max*54)}px`;bar.title=duration(value);chart.append(bar);});
      metrics.append(chart,node("small","matrix-dim","Run duration includes CLI startup and orchestration."));
      runlist.replaceChildren();
      if(!records.length || preview)runlist.append(node("p","matrix-dim",preview?"Preview has no measured runs.":"Awaiting recorded runs."));
      if(!preview)for(const run of records.slice(0,8)) {
        const row=control("",()=>inspect(run.task_id),"matrix-run");
        add(row,node("strong","",`${run.agent.toUpperCase()} / ${run.role}`),node("small","",`${run.status.toUpperCase()} · ${duration(run.status==="running"?run.elapsed_seconds:run.duration_seconds)}`));runlist.append(row);
      }
      const ids=new Set(scopedTasks().map(t=>t.id));events.replaceChildren();
      if(!preview)for(const event of (snapshot?.events||[]).filter(e=>ids.has(e.task_id)).slice(0,10)) {
        const entry=node("div","matrix-event");add(entry,node("time","",time(event.created_at)),node("span","",event.message));events.append(entry);
      }
      if(!events.childNodes.length)events.append(node("p","matrix-dim",preview?"Visual preview only. No task events generated.":"No events in this feed."));
      footer.replaceChildren(node("span","",`${online?"● CONNECTED":"○ OFFLINE"} / LOCAL TELEMETRY`),node("span","",`${preview?"PREVIEW":source.toUpperCase()} · ${snapshot?time(snapshot.snapshot_at):"CONNECTING"} · UP TO 500 RECENT RUNS`));
    }
    function line(ctx,points,color,width=1) {ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();}
    function draw(clock) {
      context.clearRect(0,0,1050,650);context.fillStyle="#050d10";context.fillRect(0,0,1050,650);
      context.strokeStyle="#12302b";context.lineWidth=.5;
      for(let x=15;x<1050;x+=25)line(context,[[x,0],[x,650]],"#0d2422",.5);
      for(let y=15;y<650;y+=25)line(context,[[0,y],[1050,y]],"#0d2422",.5);
      // Traces and contact pads mirror the visible circuit-board reference.
      for(let i=0;i<36;i++) {
        const y=30+i*17,x=35+(i*73)%900;
        line(context,[[x,y],[x+35,y],[x+48,y+13],[Math.min(1030,x+115),y+13]],"#163a35",.7);
        context.fillStyle="#226454";context.fillRect(x-2,y-2,3,3);
      }
      for(let index=0;index<routes.length;index++) {
        const [a,b]=routes[index].map(id=>stations.find(s=>s.id===id));
        const from=[a.x+a.w/2,a.y+a.h/2],to=[b.x+b.w/2,b.y+b.h/2],mid=(from[0]+to[0])/2;
        const points=[from,[mid,from[1]],[mid,to[1]],to];
        const lit=active(a.id,clock)||active(b.id,clock);
        for(let lane=-1;lane<=1;lane++)line(context,points.map(([x,y])=>[x+lane*5,y+lane*5]),lit?"#329f7e":"#1c4a41",lane===0?1.5:.5);
        if(lit) {
          const phase=((clock/3500)+index*.17)%1,segments=[Math.abs(mid-from[0]),Math.abs(to[1]-from[1]),Math.abs(to[0]-mid)],total=segments.reduce((a,b)=>a+b,0);
          let remaining=phase*total,position=from;
          for(let i=0;i<3;i++){if(remaining<=segments[i]) {const t=segments[i]?remaining/segments[i]:0;position=[points[i][0]+(points[i+1][0]-points[i][0])*t,points[i][1]+(points[i+1][1]-points[i][1])*t];break;}remaining-=segments[i];}
          context.shadowBlur=12;context.shadowColor="#54ffd0";context.fillStyle="#91ffe3";context.fillRect(position[0]-2,position[1]-2,4,4);context.shadowBlur=0;
        }
      }
      for(let index=0;index<stations.length;index++) {
        const s=stations[index],lit=active(s.id,clock),chosen=selected===s.id;
        context.fillStyle="#071519";context.fillRect(s.x,s.y,s.w,s.h);
        context.strokeStyle=s.color;context.globalAlpha=chosen?.95:.4;context.lineWidth=chosen?2:1;context.strokeRect(s.x,s.y,s.w,s.h);context.strokeRect(s.x-7,s.y-7,s.w+14,s.h+14);context.globalAlpha=1;
        const count=s.id==="codex"?65:38,nodes=[];
        for(let n=0;n<count;n++)nodes.push([s.x+15+((n*79+index*43)%Math.max(1,s.w-30)),s.y+48+((n*47+index*13)%Math.max(1,s.h-78))]);
        for(let n=0;n<nodes.length;n++) {
          const next=nodes[(n+7)%nodes.length];line(context,[nodes[n],next],s.color+"30",.5);
          const glow=lit && Math.sin(clock/250+n)>0.35;context.fillStyle=glow?"#e3fff2":s.color;context.globalAlpha=glow?1:.38;
          context.fillRect(nodes[n][0]-1,nodes[n][1]-1,glow?3:2,glow?3:2);context.globalAlpha=1;
        }
        for(let n=0;n<8;n++) {const px=s.x+12+n*(s.w-24)/7;line(context,[[px,s.y-12],[px,s.y-3]],s.color+"88",1);line(context,[[px,s.y+s.h+3],[px,s.y+s.h+12]],s.color+"88",1);}
      }
      context.font="10px Consolas, monospace";context.fillStyle="#448b73";
      context.fillText("AI HQ / EXECUTION TOPOLOGY",25,24);context.fillText(source==="preview"?"SIMULATED SIGNAL PREVIEW":"STATE-DRIVEN SIGNAL ROUTING",25,625);
      const small=miniContext;small.clearRect(0,0,160,95);small.fillStyle="#061415";small.fillRect(0,0,160,95);
      for(const [aId,bId] of routes) {const a=stations.find(s=>s.id===aId),b=stations.find(s=>s.id===bId);line(small,[[(a.x+a.w/2)*.15,(a.y+a.h/2)*.14],[(b.x+b.w/2)*.15,(b.y+b.h/2)*.14]],"#237753",1);}
      for(const s of stations) {small.fillStyle=s.color;small.globalAlpha=active(s.id,clock)?1:.5;small.fillRect(s.x*.15,s.y*.14,s.w*.15,s.h*.14);}small.globalAlpha=1;
    }
    function animate(clock) {if(disposed)return;frame=requestAnimationFrame(animate);if(document.hidden || clock-lastFrame<(motion?50:400))return;if(motion)simulationClock+=Math.min(100,clock-lastFrame);lastFrame=clock;draw(clock);if(source==="preview")for(const s of stations)stationButtons[s.id].querySelector(".matrix-station-state").textContent=stateFor(s.id,clock);}
    async function poll() {
      if(disposed || loading || document.hidden)return;loading=true;
      try {const next=await api("/api/telemetry");if(disposed)return;snapshot=next;online=true;}
      catch {if(disposed)return;online=false;}
      finally {loading=false;if(!disposed)paintPanels();}
    }
    function visibility(){if(!document.hidden)poll();}
    const timer=setInterval(poll,2000);document.addEventListener("visibilitychange",visibility);
    frame=requestAnimationFrame(animate);paintPanels();poll();
    dispose=()=>{disposed=true;clearInterval(timer);cancelAnimationFrame(frame);document.removeEventListener("visibilitychange",visibility);root.remove();};
  }
  return {mount,unmount};
})();
