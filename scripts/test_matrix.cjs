const {chromium}=require(process.env.AIHQ_PLAYWRIGHT);
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const context=await browser.newContext({viewport:{width:1600,height:1050}}),page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:18766/#key=matrix-ui-local-test-key-1234567890');
    await page.getByText('Local connection',{exact:true}).waitFor();
    await page.locator('[data-page="matrix"]').click();
    await page.getByText('● CONNECTED / LOCAL TELEMETRY',{exact:true}).waitFor();
    assert.equal(await page.locator('.matrix-station').count(),6);
    assert.match(await page.locator('.matrix-source-notice').textContent(),/LIVE MODEL RUNS/);
    const post=async(path,payload={})=>page.evaluate(async({path,payload})=>{
      const session=await(await fetch('/api/session')).json();
      const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify(payload)});
      if(!response.ok)throw new Error(await response.text());return response.json();
    },{path,payload});
    const before=await page.evaluate(async()=>(await(await fetch('/api/overview')).json()).tasks.length);
    await page.getByRole('button',{name:'Preview',exact:true}).click();
    assert.match(await page.locator('.matrix-source-notice').textContent(),/SIMULATED PREVIEW/);
    await page.waitForTimeout(4200);
    assert.equal(await page.evaluate(async()=>(await(await fetch('/api/overview')).json()).tasks.length),before);
    assert.match(await page.locator('.matrix-metrics').textContent(),/Not reported/);
    await page.getByRole('button',{name:'Expand view',exact:true}).click();
    await page.screenshot({path:'work/windows-build/matrix-preview.png',fullPage:true});
    await page.getByRole('button',{name:'Pause animation',exact:true}).click();
    const state=await page.locator('.matrix-station-state').allTextContents();
    await page.waitForTimeout(2500);assert.deepEqual(await page.locator('.matrix-station-state').allTextContents(),state);
    await page.getByRole('button',{name:'Exit expanded view',exact:true}).click();
    await page.getByRole('button',{name:'Mock runs',exact:true}).click();
    const demo=await post('/api/demo');
    await post(`/api/tasks/${demo.task.id}/approve-plan`);await post(`/api/tasks/${demo.task.id}/start`);
    await page.waitForFunction(async()=>{
      const data=await(await fetch('/api/telemetry')).json();
      return data.runs.some(r=>r.status==='succeeded') && data.tasks.some(t=>t.state==='AWAITING_APPROVAL'&&t.tests_passed>0);
    },null,{timeout:90000});
    await page.locator('.matrix-run').first().waitFor({timeout:20000});
    await page.getByRole('button',{name:'Inspect CODEX',exact:true}).click();
    assert.match(await page.locator('.matrix-metrics').textContent(),/100%/);
    await page.getByRole('button',{name:'Live runs',exact:true}).click();
    assert.equal(await page.locator('.matrix-run').count(),0);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
    await page.screenshot({path:'work/windows-build/matrix-mobile.png',fullPage:true});
    await page.route('**/api/telemetry',route=>route.abort());
    await page.getByText(/TELEMETRY DISCONNECTED/).waitFor({timeout:10000});
    await page.locator('[data-page="overview"]').click();
    assert.equal(await page.locator('.matrix-console').count(),0);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({sixNodes:true,previewLabeled:true,previewCreatesNoTasks:true,pauseFreezes:true,mockWorkflowMeasured:true,liveMockSeparated:true,disconnectionVisible:true,mobile390:true,unmount:true,pageErrors:errors}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
