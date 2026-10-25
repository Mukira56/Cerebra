"use strict";
// Factory drawing only. The supervisor owns execution; figures never create extra agent calls.
window.CerebraFactory = (() => {
  const NS = "http://www.w3.org/2000/svg", WIDTH = 1780, HEIGHT = 1130, RW = 330, RH = 230;
  const ROOMS = [
    ["browser", "RECEPTION", "Mission intake", 50, 90, "#85c8e9", "office"],
    ["planner", "RESEARCH LAB", "Planning & research", 490, 90, "#c1a1fc", "lab"],
    ["coder", "SOFTWARE FACTORY", "Build & creation", 930, 90, "#69dbb3", "factory"],
    ["reviewer", "QUALITY LAB", "Independent review", 1370, 90, "#efb680", "lab"],
    ["server", "SERVICE BUILDING", "Local operations", 50, 460, "#82b6ea", "racks"],
    ["supervisor", "COMMAND CENTER", "Task coordination", 490, 460, "#e3cf83", "command"],
    ["tests", "TEST FACILITY", "Verification", 930, 460, "#7dd8df", "factory"],
    ["gate", "APPROVALS OFFICE", "Your decisions", 1370, 460, "#e3bc6c", "office"],
    ["database", "DATA ARCHIVE", "Project memory", 50, 830, "#83c6c5", "racks"],
    ["logs", "OBSERVATORY", "Evidence & logs", 490, 830, "#a6b8df", "racks"],
    ["worktree", "ENGINEERING BAY", "Isolated working copy", 930, 830, "#87bdf0", "factory"],
    ["project", "DISPATCH BUILDING", "Reviewed results", 1370, 830, "#8ed6ac", "office"]
  ].map(([id, sector, title, x, y, color, kind], index) => ({id, sector, title, x, y, color, kind, number: index + 1}));
  const BY_ID = Object.fromEntries(ROOMS.map(room => [room.id, room]));
  const SKINS = ["#d2a17e", "#8e5f47", "#efc7a4", "#b8805a", "#684839", "#d7af8b"];
  const HAIR = ["#252326", "#523c31", "#151b22", "#896147", "#3b302b", "#bca186"];
  const node = (tag, attrs = {}, text) => { const item = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([key, value]) => item.setAttribute(key, value)); if (text !== undefined) item.textContent = text; return item; };
  const add = (parent, ...children) => { children.forEach(child => parent.append(child)); return parent; };
  const compact = text => String(text || "Unassigned").replace(/Claude Code\s*\(([^)]+)\)/i, "Claude $1").replace(/^OpenAI /, "").slice(0, 28);

  function mount(svg, {onSelect}) {
    let disposed = false, frame = 0, lastFrame = 0, visible = true, online = false, people = [], snapshot = null, selected = "supervisor", density = 72, labels = true, zoom = 1;
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const viewport = svg.parentElement;
    viewport.classList.add("factory-viewport");
    svg.setAttribute("viewBox", `0 0 ${WIDTH} ${HEIGHT}`);
    svg.setAttribute("role", "group");
    svg.setAttribute("aria-label", "Cerebra factory blueprint. Select a building or person to inspect its recorded work.");
    svg.classList.add("factory-floor");
    const defs = node("defs"), grid = node("pattern", {id: "factory-grid", width: 25, height: 25, patternUnits: "userSpaceOnUse"});
    add(grid, node("path", {d: "M25 0H0V25", fill: "none", stroke: "#416574", "stroke-opacity": .16, "stroke-width": 1}));
    const largeGrid = node("pattern", {id: "factory-major-grid", width: 100, height: 100, patternUnits: "userSpaceOnUse"});
    add(largeGrid, node("rect", {width: 100, height: 100, fill: "url(#factory-grid)"}), node("path", {d: "M100 0H0V100", fill: "none", stroke: "#416574", "stroke-opacity": .24, "stroke-width": 1}));
    add(defs, grid, largeGrid); svg.append(defs);
    add(svg, node("rect", {width: WIDTH, height: HEIGHT, fill: "#081c29"}), node("rect", {x: 20, y: 20, width: WIDTH - 40, height: HEIGHT - 40, fill: "url(#factory-major-grid)", stroke: "#56818a", "stroke-opacity": .35}));
    add(svg, node("text", {x: 52, y: 54, class: "factory-heading"}, "CEREBRA / OPERATIONS CAMPUS"), node("text", {x: 1720, y: 54, class: "factory-caption", "text-anchor": "end"}, "LIVE SECTORS · FLOOR 01"));
    const hall = node("g", {class: "factory-corridors", "aria-hidden": "true"});
    const hallPaths = ["M215 390H1535", "M215 760H1535", "M875 390V760"];
    ROOMS.forEach(room => { const y = room.y < 400 ? room.y + RH : room.y; const corridor = room.y < 800 ? 390 : 760; hallPaths.push(`M${room.x + RW / 2} ${y}V${corridor}`); });
    hallPaths.forEach(d => add(hall, node("path", {d, class: "hall-outline"}), node("path", {d, class: "hall-floor"}), node("path", {d, class: "hall-center"})));
    svg.append(hall);
    add(svg, node("text", {x: 70, y: 382, class: "factory-caption"}, "NORTH WALK"), node("text", {x: 70, y: 752, class: "factory-caption"}, "SOUTH WALK"),
      node("text", {x: 52, y: 1100, class: "factory-caption"}, "PEOPLE = VISUAL SECTOR CREW   /   ACTUAL AI CALLS ARE COUNTED SEPARATELY"),
      node("text", {x: 1720, y: 1100, class: "factory-caption", "text-anchor": "end"}, "N ↑   ·   SCHEMATIC / NOT TO SCALE"));
    const structures = node("g"), routes = node("g", {class: "factory-routes", "aria-hidden": "true"}), crew = node("g", {class: "factory-people"});
    const rooms = {};
    function choose(id) { selected = id; Object.entries(rooms).forEach(([key, room]) => room.group.classList.toggle("selected", id === key)); onSelect(id); }
    ROOMS.forEach(room => {
      const group = node("g", {class: "node factory-building", transform: `translate(${room.x} ${room.y})`, role: "button", tabindex: 0,
        "aria-label": {browser:"This window",server:"Web server",supervisor:"Supervisor",planner:"Planner",coder:"Coder",reviewer:"Reviewer",worktree:"Working copy",tests:"Test runner",gate:"Approval gate",project:"Your project",database:"Database",logs:"Run logs"}[room.id]});
      group.style.setProperty("--sector-color", room.color);
      add(group, node("rect", {class: "building-shadow", x: 7, y: 7, width: RW, height: RH}), node("rect", {class: "building-floor", width: RW, height: RH}),
        node("rect", {class: "building-wall", x: 5, y: 5, width: RW - 10, height: RH - 10}),
        node("text", {x: 18, y: 27, class: "sector-code"}, `${String(room.number).padStart(2,"0")} / ${room.sector}`),
        node("text", {x: 18, y: 52, class: "building-title"}, room.title), node("circle", {class: "sector-led", cx: RW - 20, cy: 24, r: 5}));
      const model = node("text", {x: 18, y: 73, class: "sector-model"}), status = node("text", {x: 18, y: 94, class: "sector-status"});
      add(group, model, status);
      // Architectural furniture, not pretend jobs or marketplace sales.
      for (let column = 0; column < 3; column++) {
        if (column === 1) continue; // Keep the central door-to-floor aisle clear for people.
        const x = 24 + column * 104, y = 110, furniture = node("g", {class: "factory-furniture"});
        add(furniture, node("rect", {x, y, width: 74, height: 31, rx: 2}), node("path", {d: `M${x+6} ${y+23}h62 M${x+15} ${y+31}v8 M${x+58} ${y+31}v8`}));
        if (room.kind === "racks") for (let slot = 0; slot < 3; slot++) add(furniture, node("rect", {x: x+8, y: y+4+slot*7, width: 56, height: 4}));
        else if (room.kind === "factory") add(furniture, node("circle", {cx:x+22,cy:y+14,r:8}), node("path", {d:`M${x+38} ${y+7}h24v14h-24z M${x+45} ${y+12}h10`}));
        else add(furniture, node("rect", {x:x+22,y:y+3,width:30,height:16,rx:2}), node("path", {d:`M${x+37} ${y+19}v5 M${x+28} ${y+25}h18`}));
        group.append(furniture);
      }
      const doorY = room.y < 400 ? RH : 0;
      add(group, node("path", {class:"door-opening", d:`M${RW/2-20} ${doorY}h40`}), node("path", {class:"door-swing", d:`M${RW/2-20} ${doorY}v${doorY ? -35 : 35} a35 35 0 0 ${doorY ? 1 : 0} 35 ${doorY ? 35 : -35}`}));
      const plant = node("g", {class:"factory-plant", transform:`translate(${RW-19} ${RH-18})`});
      add(plant, node("circle",{r:8}), node("path",{d:"M-5 0L0 -9L5 0L0 7Z"})); group.append(plant);
      group.addEventListener("click", () => choose(room.id)); group.addEventListener("keydown", event => {if (["Enter"," "].includes(event.key)) {event.preventDefault();choose(room.id);}});
      structures.append(group); rooms[room.id] = {group, model, status};
    });
    add(svg, structures, routes, crew);

    function buildPeople() {
      crew.replaceChildren(); people = [];
      ROOMS.forEach((room, sectorIndex) => {
        for (let slot = 0; slot < density / ROOMS.length; slot++) {
          const index = people.length, person = node("g", {class:"person courier", tabindex:0, role:"button", "data-sector":room.id});
          const figure = node("g", {class:"human-figure"}), skin = SKINS[index % SKINS.length];
          const legs = node("path", {class:"human-legs", d:"M-3 7L-4 17 M3 7L5 17", stroke: index % 2 ? "#8c9ba8" : "#516878", "stroke-width":4, fill:"none", "stroke-linecap":"round"});
          const arms = node("path", {class:"human-arms", d:"M-5 -2L-8 7 M5 -2L8 7", stroke:skin,"stroke-width":3, fill:"none", "stroke-linecap":"round"});
          add(figure, node("ellipse", {cx:1,cy:19,rx:10,ry:3,fill:"#000",opacity:.35}), legs, arms,
            node("path",{d:"M-5 -5Q0 -8 5 -5L6 7Q0 10 -6 7Z", fill:room.color,stroke:"#20303b","stroke-width":1}),
            node("path",{d:"M-1 -4V7 M-5 5H5",stroke:"#fff","stroke-opacity":.3,fill:"none"}),
            node("circle",{cx:0,cy:-10,r:5,fill:skin}), node("path",{d:"M-5 -10Q-5 -17 1 -16Q7 -16 5 -9L3 -12L-3 -12Z",fill:HAIR[index%HAIR.length]}),
            node("path",{d:"M-5 17h-3 M5 17h3",stroke:"#1b252f","stroke-width":3,"stroke-linecap":"round"}));
          if (index % 4 === 0) figure.append(node("circle",{cx:2,cy:-16,r:3,fill:HAIR[index%HAIR.length]}));
          const label = node("text", {x:0,y:-25,class:"person-label","text-anchor":"middle"});
          add(person, figure, label); crew.append(person);
          person.addEventListener("click", () => choose(room.id));
          person.addEventListener("keydown", event => {if (["Enter"," "].includes(event.key)) {event.preventDefault();choose(room.id);}});
          person.addEventListener("pointerenter", () => {person.dataset.pinned="true";});
          person.addEventListener("pointerleave", () => {delete person.dataset.pinned;});
          person.addEventListener("focus", () => {person.dataset.pinned="true";});
          person.addEventListener("blur", () => {delete person.dataset.pinned;});
          people.push({person, legs, arms, label, room, slot, sectorIndex, index, state:"idle", route:[], key:""});
        }
      });
      if (snapshot) render(snapshot);
    }
    function inside(room, slot) { return [room.x + 48 + (slot % 3)*101, room.y + 166 + Math.floor(slot / 3)*40]; }
    function loop(room, slot) { const [x,y]=inside(room,slot);return [[x,y],[x+25,y],[x+25,y+9],[x,y+9],[x,y]]; }
    function between(from, to, slot) {
      const a=BY_ID[from], b=BY_ID[to], ah=a.y<800?390:760, bh=b.y<800?390:760;
      const start=inside(a,slot), end=inside(b,slot), ax=a.x+RW/2, bx=b.x+RW/2;
      const path=[start,[ax,start[1]],[ax,a.y<400?a.y+RH:a.y],[ax,ah]];
      if (ah!==bh) path.push([875,ah],[875,bh]);
      path.push([bx,bh],[bx,b.y<400?b.y+RH:b.y],[bx,end[1]],end);
      return [...path,...path.slice(0,-1).reverse()];
    }
    function pointOn(route, distance) {
      const lengths=[]; let total=0;
      for(let i=1;i<route.length;i++){const length=Math.hypot(route[i][0]-route[i-1][0],route[i][1]-route[i-1][1]);lengths.push(length);total+=length;}
      let left=distance%Math.max(1,total);
      for(let i=0;i<lengths.length;i++){if(left<=lengths[i]&&lengths[i]){const t=left/lengths[i];return [route[i][0]+(route[i+1][0]-route[i][0])*t,route[i][1]+(route[i+1][1]-route[i][1])*t];}left-=lengths[i];}
      return route[0];
    }
    function draw(at=0) {
      people.forEach(item => {
        const moving=online&&!media.matches&&visible&&!document.hidden&&!['waiting','failed','offline'].includes(item.state);
        const distance=moving ? at/1000*(item.state==='running'?46:12)+item.index*37 : item.index*37;
        const point=pointOn(item.route.length?item.route:loop(item.room,item.slot),distance);
        if((online||!item.person.hasAttribute('transform'))&&(!item.person.dataset.pinned||!item.person.hasAttribute('transform'))) item.person.setAttribute('transform',`translate(${point[0]} ${point[1]})`);
        const stride=moving?Math.sin(at/150+item.index)*4:0;
        item.legs.setAttribute('d',`M-3 7L${-4+stride} 17 M3 7L${4-stride} 17`);
        item.arms.setAttribute('d',`M-5 -2L${-8-stride*.5} 7 M5 -2L${8+stride*.5} 7`);
      });
    }
    function animate(at) {
      frame=0;
      if(disposed||!online||!visible||document.hidden||media.matches)return;
      if(at-lastFrame>=50){draw(at);lastFrame=at;}
      frame=requestAnimationFrame(animate);
    }
    function restart() {cancelAnimationFrame(frame);frame=0;draw(performance.now());if(!disposed&&online&&visible&&!document.hidden&&!media.matches)frame=requestAnimationFrame(animate);}
    function render(data) {
      snapshot=data; online=!!data.online;
      svg.classList.toggle('factory-offline',!online);
      routes.replaceChildren();
      ROOMS.forEach(room=>{
        const state=online?(data.states[room.id]||'idle'):'offline', parts=rooms[room.id];
        parts.group.setAttribute('class',`node factory-building ${state}${selected===room.id?' selected':''}`);
        parts.model.textContent=compact(data.labels[room.id]);
        parts.status.textContent=data.lines[room.id]?.[1]||state;
        parts.group.setAttribute('data-model',data.labels[room.id]||'');
        if(state==='active'&&['planner','coder','reviewer','tests'].includes(room.id)){
          const path=between('supervisor',room.id,0);
          routes.append(node('polyline',{points:path.slice(0,path.length/2+1).map(point=>point.join(',')).join(' '),class:'factory-live-route',stroke:room.color}));
        }
      });
      people.forEach(item=>{
        const sectorState=data.states[item.room.id]||'idle';
        const state=!online?'offline':sectorState==='active'?'running':sectorState==='waiting'?'waiting':sectorState==='failed'?'failed':'idle';
        const isModel=['planner','coder','reviewer'].includes(item.room.id);
        const label=data.labels[item.room.id]||'Unassigned';
        const key=[state,label,data.task?.id].join(':');
        if(item.key!==key){delete item.person.dataset.pinned;item.key=key;}
        item.state=state;
        item.route=state==='running'&&item.slot<2?between('supervisor',item.room.id,item.slot):loop(item.room,item.slot);
        item.person.setAttribute('data-state',state);
        item.person.setAttribute('data-model',label);
        item.person.setAttribute('data-task-id',data.task?.id||'');
        item.person.setAttribute('aria-label',`${state==='running'?'Working':state} worker: ${data.titles[item.room.id]}. ${label}. Visual crew member ${item.slot+1}; not a separate AI call.`);
        item.label.textContent=labels&&(isModel||item.slot===0)?compact(label):'';
        item.person.classList.toggle('model-person',isModel);
      });
      restart();
    }
    function fit(){const maxHeight=parseFloat(getComputedStyle(viewport).maxHeight)||innerHeight*.76;zoom=Math.min(1,Math.max(.15,Math.min((viewport.clientWidth-4)/WIDTH,(maxHeight-4)/HEIGHT)));applyZoom();}
    function applyZoom(){svg.style.width=`${WIDTH*zoom}px`;svg.style.height=`${HEIGHT*zoom}px`;}
    function setZoom(delta){zoom=Math.min(1.8,Math.max(.15,zoom+delta));applyZoom();}
    const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;restart();});observer.observe(svg);
    const resize=new ResizeObserver(()=>{if(!svg.dataset.manualZoom)fit();});resize.observe(viewport);
    document.addEventListener('visibilitychange',restart);media.addEventListener('change',restart);
    buildPeople();fit();
    return {render, fit:()=>{delete svg.dataset.manualZoom;fit();}, zoom:delta=>{svg.dataset.manualZoom='true';setZoom(delta);},
      density:value=>{density=[24,48,72].includes(Number(value))?Number(value):72;buildPeople();},
      labels:value=>{labels=!!value;if(snapshot)render(snapshot);},
      dispose:()=>{disposed=true;cancelAnimationFrame(frame);observer.disconnect();resize.disconnect();document.removeEventListener('visibilitychange',restart);media.removeEventListener('change',restart);}};
  }
  return {mount};
})();
