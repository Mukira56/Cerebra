// Uses the bundled Playwright and installed Edge; no browser/package downloads.
const { chromium } = require(process.env.AIHQ_PLAYWRIGHT);
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:18766/#key=ui-polish-local-test-key-1234567890');
    await page.getByText('Local connection',{exact:true}).waitFor();
    assert.equal(await page.locator('.brand-mark').evaluate(node => node.complete && node.naturalWidth>0),true);
    const post = async (path, payload={}) => page.evaluate(async ({path,payload}) => {
      const session = await (await fetch('/api/session')).json();
      const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify(payload)});
      if(!response.ok) throw new Error(await response.text());
      return response.json();
    },{path,payload});
    const demo = await post('/api/demo');
    await page.locator('[data-page="tasks"]').click();
    await page.getByRole('button',{name:`Inspect task: ${demo.task.description}`,exact:true}).waitFor();
    const filter = page.getByRole('combobox',{name:'Filter project'});
    await filter.selectOption(demo.project.id);
    await page.locator('.filters select').nth(1).selectOption(demo.task.state);
    await page.getByRole('button',{name:`Inspect task: ${demo.task.description}`,exact:true}).click();
    await page.getByRole('button',{name:'Evidence',exact:true}).click();
    await post(`/api/tasks/${demo.task.id}/approve-plan`);
    await page.getByText('Plan approved · Ready to start',{exact:true}).waitFor({timeout:15000});
    assert.equal(await page.locator('.detail-tabs button.active').textContent(),'Evidence');
    await page.getByRole('button',{name:'Close dialog'}).click();
    assert.equal(await page.locator('.filters select').nth(1).inputValue(),demo.task.state);
    for (const route of ['overview','projects','agents','reviews','git','logs','settings']) {
      await page.locator(`[data-page="${route}"]:visible`).first().click();
      await page.waitForTimeout(100);
      assert.ok(await page.locator('#page-title').textContent());
    }
    await page.locator('[data-page="overview"]').click();
    await page.screenshot({path:'work/windows-build/dashboard-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
    await page.screenshot({path:'work/windows-build/dashboard-mobile.png',fullPage:true});
    const blocked = await browser.newContext({storageState:await context.storageState()});
    await blocked.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError');}}));
    const fallback = await blocked.newPage();
    fallback.on('pageerror',error=>errors.push(error.message));
    await fallback.goto('http://127.0.0.1:18766/');
    await fallback.getByText('Local connection',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({desktop:true,mobile390:true,logo:true,automaticEvidence:true,preservedTab:true,preservedFilter:true,blockedStorage:true,pageErrors:errors}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
