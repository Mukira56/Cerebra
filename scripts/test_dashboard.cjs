// Drives every dashboard page in headless Edge against a throwaway Cerebra server (agents off, temp data).
// Usage: set AIHQ_PLAYWRIGHT=<path to playwright-core>, AIHQ_URL=http://127.0.0.1:<port>/#key=<key>, AIHQ_SHOTS=<dir>
const { chromium } = require(process.env.AIHQ_PLAYWRIGHT);
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const shots = process.env.AIHQ_SHOTS;
  let activePage;
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 960}});
    const page = await context.newPage(), errors = [];
    activePage = page;
    page.setDefaultTimeout(60000);
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && !/Failed to load resource/.test(message.text())) errors.push(message.text()); });
    await page.goto(process.env.AIHQ_URL);
    await page.getByText('Local connection', {exact: true}).waitFor();
    const shot = async name => { if (shots) await page.screenshot({path: path.join(shots, `${name}.png`), fullPage: false}); };
    assert.equal(await page.locator('.brand-mark').evaluate(node => node.complete && node.naturalWidth > 0), true);
    assert.equal(await page.getByText(/mock|demo/i).count(), 0, 'No demo or mock wording on the overview');
    await page.getByText('Get started', {exact: true}).waitFor();
    await shot('overview-empty');

    // Add a project through the form.
    await page.locator('[data-page="projects"]').click();
    await page.locator('#heading-actions').getByRole('button', {name: '+ Add project'}).click();
    await page.locator('dialog select').first().selectOption('new');
    await page.locator('dialog input[placeholder^="e.g."]').fill('Booking platform');
    await page.locator('dialog textarea').fill('[["python", "-m", "pytest", "-q"]]');
    await page.locator('dialog input[type=checkbox]').check();
    await page.locator('dialog').getByRole('button', {name: 'Add project', exact: true}).click();
    await page.locator('.card h3', {hasText: 'Booking platform'}).waitFor();

    // Add a model profile and use it in a task.
    await page.locator('[data-page="models"]').click();
    await page.getByText('Your AI accounts', {exact: true}).waitFor();
    await page.getByRole('button', {name: '+ Add model'}).click();
    await page.locator('dialog select').first().selectOption('claude');
    await page.locator('dialog input').first().fill('opus');
    await page.locator('dialog input').nth(1).fill('Claude Opus');
    await page.locator('dialog').getByRole('button', {name: 'Add model', exact: true}).click();
    await page.locator('table strong', {hasText: 'Claude Opus'}).waitFor();
    await page.getByText('Available models', {exact: true}).waitFor();
    assert.ok(await page.locator('.model-row strong', {hasText: 'Claude Opus 5.5'}).count() >= 1, 'Claude catalog listed');
    assert.ok(await page.locator('.panel-header h2', {hasText: 'Supervisor: who picks the models'}).count() === 1);
    assert.equal(await page.locator('form select').filter({hasText: 'Auto: the supervisor picks'}).count(), 3, 'Each default role offers Auto');
    await page.locator('.card h3', {hasText: 'OpenAI Codex'}).waitFor();
    await shot('models');

    await page.locator('[data-page="tasks"]').click();
    await page.locator('#heading-actions').getByRole('button', {name: '+ New task'}).click();
    await page.locator('dialog textarea').first().fill('Add a booking calendar page with tests');
    await page.locator('dialog .form-grid select').nth(2).selectOption('claude-opus');
    await page.locator('dialog').getByRole('button', {name: 'Create plan', exact: true}).click();
    await page.locator('dialog').getByRole('button', {name: 'Approve plan', exact: true}).waitFor();
    await shot('task-detail');
    await page.locator('dialog').getByRole('button', {name: 'Approve plan', exact: true}).click();
    await page.getByRole('button', {name: '▶ Start'}).waitFor();
    await page.getByRole('button', {name: '▶ Start'}).click();
    await page.getByText(/switched off/).first().waitFor();   // agents are off on the test server
    await page.getByRole('button', {name: 'Close dialog'}).click();

    // Plain report.
    await page.locator('[data-page="reports"]').click();
    await page.locator('.row', {hasText: 'booking calendar'}).click();
    await page.getByText('What you asked for', {exact: true}).waitFor();
    await page.getByText('Where everything is saved', {exact: true}).waitFor();
    assert.ok(await page.getByText('Claude Code (opus) checked the code.', {exact: true}).count());
    await shot('report');

    // System view.
    await page.locator('[data-page="system"]').click();
    await page.locator('.diagram .node').first().waitFor();
    assert.equal(await page.locator('.diagram .node').count(), 12);
    assert.equal(await page.locator('.person').count(),72,'Factory starts with a large visual crew');
    await page.getByText('0 recorded AI runs active',{exact:true}).waitFor();
    await page.locator('.diagram .node[aria-label="Test runner"]').click();
    await page.locator('.inspector h3', {hasText: 'Test runner'}).waitFor();
    await page.locator('.trace div').first().waitFor();
    await shot('system');

    // Animation fixtures exist only in this browser test. No simulated product mode or AI calls.
    const telemetryUrl = new URL('/api/telemetry', process.env.AIHQ_URL).href;
    const recorded = await (await page.request.get(telemetryUrl)).json();
    const recordedTask = recorded.tasks[0];
    let fixtureState = 'RUNNING';
    await page.route('**/api/telemetry', async route => {
      if (fixtureState === 'offline') return route.abort();
      const now = new Date().toISOString();
      const fixture = {...recorded, tasks: [{...recordedTask, state: fixtureState}], approvals: fixtureState === 'AWAITING_APPROVAL' ? [{task_id: recordedTask.id, kind: 'merge'}] : [],
        runs: fixtureState === 'RUNNING' ? [{id:'browser-test-only',task_id:recordedTask.id,source:'live',agent:'codex',role:'implement',status:'running',started_at:now,elapsed_seconds:3}] : []};
      await route.fulfill({json: fixture});
    });
    await page.locator('.courier[data-state="running"]').first().waitFor();
    await page.getByText('1 recorded AI run active',{exact:true}).waitFor();
    const modelName = await page.locator('.person[data-sector="coder"]').first().getAttribute('data-model');
    assert.ok(modelName && modelName !== 'Model unassigned','People show the recorded task model');
    assert.equal(await page.locator('.person[data-sector="coder"] .person-label').first().textContent(),modelName.slice(0,28));
    await page.getByLabel('Visual crew density').selectOption('24');
    assert.equal(await page.locator('.person').count(),24);
    await page.getByText('1 recorded AI run active',{exact:true}).waitFor();
    await page.getByLabel('Visual crew density').selectOption('72');
    await page.getByRole('button',{name:'Zoom in',exact:true}).click();
    await shot('factory-active-zoom');
    await page.getByRole('button',{name:'Fit factory',exact:true}).click();
    // Mouse controls: Ctrl + wheel zooms at the pointer, drag pans, right-click opens the blueprint menu.
    const floor = page.locator('.factory-viewport'), readout = page.locator('.factory-zoom-readout');
    const fitted = await readout.textContent(), box = await floor.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.keyboard.down('Control'); await page.mouse.wheel(0, -600); await page.keyboard.up('Control');
    assert.ok(parseInt(await readout.textContent()) > parseInt(fitted), 'Ctrl + wheel zooms in');
    const scrolled = await floor.evaluate(element => element.scrollLeft);
    await page.mouse.move(box.x + 30, box.y + box.height - 30); await page.mouse.down(); await page.mouse.move(box.x + 230, box.y + box.height - 30, {steps: 6}); await page.mouse.up();
    assert.notEqual(await floor.evaluate(element => element.scrollLeft), scrolled, 'Dragging the floor pans the blueprint');
    await page.locator('.factory-building[aria-label="Test runner"]').click({button: 'right'});
    await page.locator('.context-menu .context-item', {hasText: 'Inspect this building'}).click();
    await page.locator('.inspector h3', {hasText: 'Test runner'}).waitFor();
    await floor.click({button: 'right', position: {x: 40, y: 40}});
    await page.locator('.context-menu .context-item', {hasText: 'Fit factory to window'}).click();
    assert.equal(await readout.textContent(), fitted, 'Fit from the right-click menu restores the fitted zoom');
    await shot('factory-active');
    const courier = page.locator('.courier[data-state="running"]').first();
    const before = await courier.getAttribute('transform'); await page.waitForTimeout(350);
    assert.notEqual(await courier.getAttribute('transform'), before, 'Real running telemetry animates the courier');
    await page.emulateMedia({reducedMotion:'reduce'}); await page.waitForTimeout(100);
    const still = await courier.getAttribute('transform'); await page.waitForTimeout(200);
    assert.equal(await courier.getAttribute('transform'), still, 'Reduced motion keeps workers stationary');
    await page.locator('.courier[aria-label^="Working worker: Coder"]').first().click();
    await page.locator('.inspector h3', {hasText:'Coder'}).waitFor();
    await page.emulateMedia({reducedMotion:'no-preference'});
    fixtureState = 'AWAITING_APPROVAL';
    await page.locator('.courier[data-state="waiting"]').first().waitFor();
    assert.equal(await page.locator('.courier[data-state="running"]').count(), 0, 'Approval does not animate running work');
    await shot('system-workers-waiting');
    fixtureState = 'FAILED'; await page.locator('.courier[data-state="failed"]').first().waitFor();
    fixtureState = 'offline'; await page.waitForTimeout(2500);
    assert.equal(await page.locator('.courier[data-state="running"]').count(), 0, 'Disconnected factory stops active workers');
    const offlinePerson=page.locator('.person').first(), offlinePosition=await offlinePerson.getAttribute('transform');
    await page.waitForTimeout(200);assert.equal(await offlinePerson.getAttribute('transform'),offlinePosition,'Offline positions are frozen');
    await page.unroute('**/api/telemetry');

    const floorPhone = await browser.newContext({viewport:{width:390,height:860}});
    await floorPhone.addCookies(await context.cookies());
    const floorSmall = await floorPhone.newPage();
    floorSmall.on('pageerror', error => errors.push('factory mobile: '+error.message));
    await floorSmall.goto(process.env.AIHQ_URL.split('#')[0]+'#system');
    await floorSmall.locator('.person').first().waitFor();
    await floorSmall.getByRole('button',{name:'Zoom in',exact:true}).click();
    await floorSmall.locator('.factory-viewport').scrollIntoViewIfNeeded();
    assert.ok(await floorSmall.evaluate(()=>document.documentElement.scrollWidth<=400),'Factory pans inside its viewport, not the phone page');
    assert.ok(await floorSmall.locator('.factory-viewport').evaluate(element=>element.scrollWidth>element.clientWidth),'Zoomed floor supports horizontal panning');
    if(shots) await floorSmall.screenshot({path:path.join(shots,'factory-phone.png')});
    await floorPhone.close();

    // Chat: agents are off, so the reply fails with a clear message (no provider is launched).
    await page.locator('[data-page="chat"]').click();
    await page.getByRole('button', {name: '+ New chat'}).click();
    await page.locator('.composer textarea').fill('Explain the **project** layout');
    await page.locator('.composer textarea').press('Enter');
    await page.locator('.message.user .bubble', {hasText: 'Explain the **project** layout'}).waitFor({timeout: 15000});
    await page.locator('.bubble.failed', {hasText: 'AI agents are switched off'}).waitFor({timeout: 60000});
    assert.ok(await page.getByRole('button', {name: 'Send', exact: true}).isVisible());
    await shot('chat');

    // Business Studio: empty state, a job created through the form, and its plain results page.
    await page.locator('[data-page="business"]').click();
    await page.getByText('No business jobs yet', {exact: true}).waitFor();
    await page.getByText('Marketplaces', {exact: true}).waitFor();
    assert.ok(await page.getByText(/own OpenAI API key/).count(), 'Image generation needs an explicit connection');
    await page.locator('#heading-actions').getByRole('button', {name: '+ New business job'}).click();
    await page.locator('dialog input').first().fill('Bakery website for Ama');
    await page.locator('dialog textarea').first().fill('A one-page website for the Ama bakery in Nairobi with opening hours and a cake menu.');
    await page.locator('dialog').getByRole('button', {name: 'Create job', exact: true}).click();
    await page.getByText('What needs attention', {exact: true}).waitFor({timeout: 60000});
    await page.getByText('Where they are', {exact: true}).waitFor();
    assert.ok(await page.locator('.report-head .badge', {hasText: 'WAITING FOR YOU'}).count(), 'A new job waits for plan approval');
    assert.ok(await page.getByText(/does not mean anything was sold/).count());
    await shot('business-job');
    const narrow = await browser.newContext({viewport: {width: 390, height: 860}}); await narrow.addCookies(await context.cookies());
    const small = await narrow.newPage(); small.on('pageerror', error => errors.push('narrow: ' + error.message));
    await small.goto(process.env.AIHQ_URL.split('#')[0] + '#business'); await small.locator('.row', {hasText: 'Bakery website'}).waitFor();
    assert.ok(await small.evaluate(() => document.documentElement.scrollWidth <= 400), 'Business Studio fits a narrow window');
    if (shots) await small.screenshot({path: path.join(shots, 'business-narrow.png')});
    await narrow.close();

    await page.locator('[data-page="connections"]').click();
    await page.getByText('Read-only Gmail intake', {exact:true}).waitFor();
    assert.equal(await page.locator('.connection-grid input[type="password"]').count(), 6, 'Secrets use password fields');
    await shot('business-connections');
    const connectionPhone = await browser.newContext({viewport:{width:390,height:860}}); await connectionPhone.addCookies(await context.cookies());
    const connectionSmall = await connectionPhone.newPage();
    connectionSmall.on('pageerror', error => errors.push('connections mobile: '+error.message));
    await connectionSmall.goto(process.env.AIHQ_URL.split('#')[0]+'#connections');
    await connectionSmall.getByText('Raster images', {exact:true}).waitFor();
    assert.ok(await connectionSmall.evaluate(() => document.documentElement.scrollWidth <= 400), 'Connection forms fit a phone');
    if (shots) await connectionSmall.screenshot({path:path.join(shots,'connections-narrow.png')});
    await connectionPhone.close();

    // App-wide right-click: Cerebra's menu on a task row; text boxes keep the native edit menu.
    await page.locator('[data-page="tasks"]').click();
    await page.locator('[data-task-id]').first().click({button: 'right'});
    for (const label of ['Open task', 'Plain report', 'Copy task ID', 'Refresh']) await page.locator('.context-menu .context-item', {hasText: label}).first().waitFor();
    await page.keyboard.press('Escape');
    assert.ok(await page.locator('.context-menu').isHidden(), 'Escape closes the menu');
    await page.locator('[data-task-id]').first().click({button: 'right'});
    await page.locator('.context-menu .context-item', {hasText: 'Open task'}).click();
    await page.locator('dialog .tabs').waitFor(); await page.getByRole('button', {name: 'Close dialog'}).click();
    await page.locator('[data-page="settings"]').first().click();
    const prevented = await page.locator('input[type=number]').first().evaluate(input => { const event = new MouseEvent('contextmenu', {bubbles: true, cancelable: true}); input.dispatchEvent(event); return event.defaultPrevented; });
    assert.equal(prevented, false, 'Text boxes keep the native cut/copy/paste menu');
    assert.ok(await page.locator('.context-menu').isHidden());

    for (const name of ['approvals', 'activity', 'toolchain', 'github', 'settings', 'overview']) {
      await page.locator(`[data-page="${name}"]`).first().click();
      await page.waitForTimeout(700);
    }
    await page.locator('[data-page="settings"]').first().click();
    await page.getByRole('button', {name: 'Switch agents on'}).waitFor();
    await page.getByText('Where your data lives', {exact: true}).waitFor();
    assert.ok(await page.getByRole('button', {name: 'Turn Away mode on'}).isDisabled(), 'Away mode needs agents on first');
    await shot('settings');

    // Switch agents on, delegate approvals to Away mode, then turn both off again.
    await page.getByText(/run on my own accounts/).click();
    await page.getByText(/read files outside the project folder/).click();
    await page.getByRole('button', {name: 'Switch agents on'}).click();
    await page.getByRole('button', {name: 'Give full access'}).click();
    await page.locator('.form-error', {hasText: 'Tick both boxes to give full access'}).waitFor();
    await page.getByText(/run any command on this laptop/).click();
    await page.getByText(/use my GitHub login/).click();
    await page.getByRole('button', {name: 'Give full access'}).click();
    await page.locator('.badge', {hasText: 'FULL ACCESS'}).waitFor();
    await shot('full-access');
    await page.getByRole('button', {name: 'Limit agents to the project copy'}).click();
    await page.locator('.badge', {hasText: 'PROJECT ONLY'}).waitFor();
    await page.getByRole('button', {name: 'Turn Away mode on'}).click();
    await page.locator('.form-error', {hasText: 'Tick the first box'}).waitFor();
    await page.getByText(/approve plans, start the AI team/).click();
    await page.getByText(/Also merge finished work/).click();
    await page.getByRole('button', {name: 'Turn Away mode on'}).click();
    await page.locator('.form-error', {hasText: 'merge confirmation'}).waitFor();
    await page.getByText(/merged work changes my real project folder/).click();
    await page.getByRole('button', {name: 'Turn Away mode on'}).click();
    await page.locator('.badge', {hasText: 'AWAY MODE ON'}).waitFor();
    assert.match(await page.locator('#agents-status').innerText(), /away mode/);
    await shot('away-mode');
    await page.getByRole('button', {name: 'Turn Away mode off'}).click();
    await page.locator('.badge', {hasText: 'AWAY MODE OFF'}).waitFor();
    await page.getByRole('button', {name: 'Switch agents off'}).click();
    await page.getByRole('button', {name: 'Switch agents on'}).waitFor();
    await page.locator('[data-page="toolchain"]').first().click();
    await page.locator('.panel-header h2', {hasText: 'Essentials'}).waitFor({timeout: 60000});
    await shot('toolchain');

    const mobile = await browser.newContext({viewport: {width: 390, height: 860}});
    const phone = await mobile.newPage(); phone.on('pageerror', error => errors.push('mobile: ' + error.message));
    const cookies = await context.cookies(); await mobile.addCookies(cookies);
    await phone.goto(process.env.AIHQ_URL.split('#')[0] + '#overview');
    await phone.getByText('Local connection', {exact: true}).waitFor();
    if (shots) await phone.screenshot({path: path.join(shots, 'mobile.png')});
    const wide = await phone.evaluate(() => [...document.querySelectorAll('body *')].filter(node => node.getBoundingClientRect().right > 392).slice(0, 8).map(node => `${node.tagName}.${node.className} ${Math.round(node.getBoundingClientRect().right)}`));
    assert.ok(await phone.evaluate(() => document.documentElement.scrollWidth <= 400), 'No horizontal page overflow on a phone: ' + wide.join(' | '));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({pages: 16, errors: errors.length, mobile_width_ok: true, workers_running_waiting_failed_offline: true, reduced_motion:true}));
  } catch (error) {
    if (shots && activePage) {
      await activePage.screenshot({path:path.join(shots,'failure.png')}).catch(() => {});
      require('node:fs').writeFileSync(path.join(shots,'failure.txt'), await activePage.locator('body').innerText().catch(() => 'Page unavailable'));
    }
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
