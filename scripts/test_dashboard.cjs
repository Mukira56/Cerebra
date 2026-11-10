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
    await page.getByText('Connected', {exact: true}).waitFor();
    // The simple menu shows the everyday pages; the rest are one click away.
    assert.equal(await page.locator('[data-page="projects"]').isVisible(), false, 'Coding pages wait behind Show all pages');
    await page.getByText('What would you like to do today?', {exact: true}).waitFor();
    await page.locator('.ask-box input').fill('Find software engineering jobs I qualify for');
    await page.locator('.ask-box').getByRole('button', {name: 'Go'}).click();
    await page.locator('.ask-answer strong', {hasText: 'Apply for jobs'}).waitFor();
    assert.ok(await page.getByRole('button', {name: 'Open Apply for jobs'}).count() === 1, 'Home understands a plain request and offers the right workflow');
    assert.equal(await page.locator('.home-tile').count(), 9, 'Home has a shortcut for each everyday job');
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'light', 'Light colours by default');
    assert.equal(await page.locator('[data-comfort]').count(), 0, 'Text size and colours are in Settings, not the menu');
    await page.locator('[data-page="settings"]').click();
    await page.getByText('How Cerebra looks', {exact: true}).waitFor();
    await page.getByRole('button', {name: 'Largest', exact: true}).click();
    assert.equal(await page.evaluate(() => getComputedStyle(document.body).fontSize), '18px', 'The largest text size applies');
    await page.getByRole('button', {name: 'Normal', exact: true}).click();
    await page.getByRole('button', {name: 'Dark', exact: true}).click();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark', 'Dark colours on request');
    if (shots) await page.screenshot({path: path.join(shots, 'settings-dark.png')});
    await page.getByRole('button', {name: 'Light', exact: true}).click();
    await page.locator('[data-page="overview"]').click();
    await page.locator('#menu-switch').click();
    assert.equal(await page.locator('[data-page="projects"]').isVisible(), true, 'Show all pages reveals the rest');
    await page.getByText('Get started', {exact: true}).waitFor();  // the coding steps show once all pages are shown
    const shot = async name => { if (shots) await page.screenshot({path: path.join(shots, `${name}.png`), fullPage: false}); };
    assert.equal(await page.locator('.brand-mark').evaluate(node => node.complete && node.naturalWidth > 0), true);
    assert.equal(await page.getByText(/mock|demo/i).count(), 0, 'No demo or mock wording on the overview');

    await shot('overview-empty');

    // Add a project through the form.
    await page.locator('[data-page="projects"]').click();
    await page.locator('#heading-actions').getByRole('button', {name: '+ Add project'}).click();
    await page.locator('dialog select').first().selectOption('new');
    await page.locator('dialog input[placeholder="e.g. Booking platform"]').fill('Booking platform');
    // Tests are chosen from a plain list (no JSON), with a typed command or advanced lists as options.
    await page.locator('dialog .test-picker select').selectOption('custom');
    await page.locator('dialog .test-picker input').fill('python -m pytest -q');
    assert.ok(await page.locator('dialog button', {hasText: 'Browse…'}).count(), 'The folder can be chosen with the Windows picker');
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
    await page.locator('.panel-header h2', {hasText: 'Model intelligence'}).waitFor();
    await page.getByText('Lead engineer', {exact: true}).waitFor();
    assert.ok(await page.locator('select').filter({hasText: 'Claude writes the code (Codex reviews)'}).count() === 1, 'Claude leads the coding by default');
    assert.ok(await page.getByText('Prompt Architect', {exact: true}).count() >= 1, 'The Prompt Architect is a kind of work');
    assert.ok(await page.locator('.model-row strong', {hasText: 'Claude Opus 5.5'}).count() >= 1, 'Claude catalog listed');
    assert.ok(await page.locator('.panel-header h2', {hasText: 'Supervisor: who picks the models'}).count() === 1);
    assert.equal(await page.locator('form select').filter({hasText: 'Auto: the supervisor picks'}).count(), 3, 'Each default role offers Auto');
    await page.locator('.card h3', {hasText: 'OpenAI Codex'}).waitFor();
    await shot('models');

    await page.locator('[data-page="tasks"]').click();
    await page.locator('#heading-actions').getByRole('button', {name: '+ New task'}).click();
    await page.locator('dialog textarea').first().fill('Add a booking calendar page with tests');
    assert.ok(await page.locator('dialog').getByRole('button', {name: 'Ask the Prompt Architect'}).count() === 1, 'New task offers the Prompt Architect');
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
    await page.locator('#page-title', {hasText: 'Reports'}).waitFor();  // the Coding tasks row may still be on screen for a moment
    await page.locator('#page-content .row', {hasText: 'booking calendar'}).click();
    await page.getByText('What you asked for', {exact: true}).waitFor();
    await page.getByText('Where everything is saved', {exact: true}).waitFor();
    assert.ok(await page.getByText('Was this result good?', {exact: true}).count() === 0, 'Only a finished task can be rated');
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
    // Idle sectors: exactly one standby worker each, everyone else seated. Busy sectors exchange visits both ways.
    const perRoom = await page.locator('.person[data-sector="database"]').count();
    assert.equal(await page.locator('.person[data-sector="database"][data-pose="standby"]').count(), 1, 'One standby worker in an idle sector');
    assert.equal(await page.locator('.person[data-sector="database"][data-pose="seated"]').count(), perRoom - 1, 'The rest of an idle sector is seated');
    const seatedBefore = await page.locator('.person[data-sector="database"][data-pose="seated"]').first().getAttribute('transform');
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.person[data-sector="database"][data-pose="seated"]').first().getAttribute('transform'), seatedBefore, 'Seated workers stay seated');
    assert.ok(await page.locator('.person[data-sector="coder"][data-pose="walking"]').count() >= 1 && await page.locator('.person[data-sector="supervisor"][data-pose="walking"]').count() >= 1, 'Both busy sectors send workers');
    assert.ok(await page.locator('.factory-exchange').count() >= 1, 'Busy sectors are linked both ways');
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
    await floor.scrollIntoViewIfNeeded();
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
    await page.emulateMedia({reducedMotion:'reduce'}); await page.waitForTimeout(600);  // the factory snaps workers to rest on its next frame; a busy laptop needs longer than 100 ms
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
    await page.locator('dialog select').first().selectOption('service_site');
    await page.locator('dialog textarea').first().fill('A one-page website for the Ama bakery in Nairobi with opening hours and a cake menu.');
    await page.locator('dialog').getByRole('button', {name: 'Create job', exact: true}).click();
    await page.getByText('What needs attention', {exact: true}).waitFor({timeout: 60000});
    await page.getByText('Where they are', {exact: true}).waitFor();
    assert.ok(await page.locator('.report-head .badge', {hasText: 'SCOPE NEEDS YOUR APPROVAL'}).count(), 'A client website job waits for scope approval');
    await page.locator('.panel-header h2', {hasText: 'Scope — needs your approval'}).waitFor();
    for (const title of ['Money', 'Customer results']) await page.locator('.panel-header h2', {hasText: title}).first().waitFor();
    await page.getByRole('button', {name: 'Approve scope and start'}).click();
    await page.getByText(/before approving the scope/).first().waitFor();  // services, areas and form address are required
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
    assert.equal(await page.locator('.connection-grid input[type="password"]').count(), 7, 'Secrets use password fields (Shopify client secret included)');
    // Setup notes beside each connection, and the full guide in a pop-up.
    assert.equal(await page.locator('.guide-notes').count(), 7, 'Setup notes beside every connection (Etsy, Printify, images, Shopify, Gmail, phone, Fiverr)');
    assert.ok(await page.getByText('Fiverr orders', {exact: true}).count(), 'Fiverr card is shown');
    await page.locator('.panel', {hasText: 'Etsy drafts'}).locator('.guide-notes').getByRole('button', {name: 'How to connect…'}).click();
    await page.locator('dialog h3', {hasText: '1. Open an Etsy shop'}).waitFor();
    assert.ok(await page.locator('dialog .guide-links button', {hasText: 'Your Etsy apps'}).count(), 'Guide links to the official pages');
    await shot('connection-guide');
    await page.locator('dialog').getByRole('button', {name: 'Close', exact: true}).click();
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
    await page.locator('dialog .tabs').waitFor();
    await page.locator('dialog .tabs button', {hasText: 'History'}).click();
    await page.getByText(/Every coding attempt is saved as a checkpoint/).waitFor();
    await page.getByRole('button', {name: 'Close dialog'}).click();
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
    await page.locator('.panel-header h2', {hasText: 'Updates'}).waitFor();
    await page.locator('.panel-header h2', {hasText: 'Readiness check'}).waitFor();
    assert.ok(await page.getByRole('button', {name: 'Run readiness check'}).isDisabled(), 'Readiness needs agents on first');
    assert.ok(await page.getByRole('button', {name: 'Check for updates'}).isVisible(), 'Updates can be checked from inside the app');
    assert.ok(await page.getByRole('button', {name: 'Turn Away mode on'}).isDisabled(), 'Away mode needs agents on first');
    await shot('settings');
    // The top bar's update button scrolls to Settings › Updates, even when Settings is already open.
    await page.evaluate(() => { const pill = document.getElementById('update-status'); pill.className = 'pill good'; pill.textContent = 'Update 9.9.9 ready · install'; window.scrollTo(0, 0); document.querySelector('main, .content, #content')?.scrollTo?.(0, 0); });
    await page.locator('#update-status').click(); await page.waitForTimeout(900);
    const updatesTop = await page.evaluate(() => document.getElementById('updates-panel').getBoundingClientRect().top);
    assert.ok(updatesTop >= 0 && updatesTop < 400, `The update button brings Settings › Updates into view (top ${updatesTop})`);

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
    await phone.getByText('Connected', {exact: true}).waitFor();
    if (shots) await phone.screenshot({path: path.join(shots, 'mobile.png')});
    const wide = await phone.evaluate(() => [...document.querySelectorAll('body *')].filter(node => node.getBoundingClientRect().right > 392).slice(0, 8).map(node => `${node.tagName}.${node.className} ${Math.round(node.getBoundingClientRect().right)}`));
    assert.ok(await phone.evaluate(() => document.documentElement.scrollWidth <= 400), 'No horizontal page overflow on a phone: ' + wide.join(' | '));
    // No page prints a stray "null" (an empty value handed to the browser's append).
    for (const name of ['overview', 'tasks', 'projects', 'approvals', 'reports', 'activity', 'settings', 'models', 'toolchain', 'github', 'connections', 'business', 'money', 'books', 'etsy', 'chief', 'prospects', 'partners', 'jobs', 'funding', 'freelance', 'marketing', 'council', 'chat', 'system']) {
      await page.evaluate(view => { location.hash = view; }, name); await page.waitForTimeout(600);
      assert.ok(!/(^|\s)null(\s|$)/.test(await page.locator('body').innerText()), `"null" is printed on the ${name} page`);
    }
    await page.evaluate(() => { location.hash = 'partners'; });
    await page.getByRole('button', {name: 'Find companies and their emails'}).waitFor();
    assert.ok(await page.getByRole('button', {name: 'Offered me something (0)'}).count() && await page.getByRole('button', {name: 'Not offered (0)'}).count(), 'Pitch companies can show offers and the rest');
    assert.ok(await page.getByRole('button', {name: 'Find companies and their emails'}).count() && await page.locator('.panel-header h2', {hasText: 'Your pitch'}).count(), 'Company pitches shows the pitch and the find button');
    await page.evaluate(() => { location.hash = 'jobs'; });
    await page.getByRole('button', {name: 'Find jobs now'}).waitFor();
    assert.ok(await page.locator('.panel-header h2', {hasText: 'Your CV and the jobs you want'}).count() && await page.getByRole('button', {name: 'Review ready applications (0)'}).count(), 'Apply for jobs shows the CV and the jobs');
    await page.evaluate(() => { location.hash = 'money'; }); await page.waitForTimeout(800);
    assert.ok(await page.getByText('Earned this month').count() && await page.getByRole('button', {name: '+ New quote'}).count(), 'The Money page shows earnings and can start a quote');
    assert.ok(await page.getByText(/Start earning · \d of 6 done/).count(), 'A new owner sees the Start earning checklist');
    await page.evaluate(() => { location.hash = 'tasks'; }); await page.waitForTimeout(600);
    assert.match(await page.title(), /^(\(\d+\) )?Cerebra/, 'The window title names Cerebra and what needs the owner');
    const rowsBefore = await page.locator('.row[data-task-id]').count();
    await page.getByPlaceholder(/Search tasks/).fill('no task is called this zzz'); await page.waitForTimeout(300);
    assert.equal(await page.locator('.row[data-task-id]').count(), 0, 'Search hides tasks that do not match');
    await page.getByPlaceholder(/Search tasks/).fill(''); await page.waitForTimeout(300);
    assert.equal(await page.locator('.row[data-task-id]').count(), rowsBefore, 'Clearing the search shows every task again');
    if (await page.locator('.row[data-task-id]').count()) {
      await page.locator('.row[data-task-id]').first().click(); await page.locator('dialog[open]').waitFor(); await page.waitForTimeout(800);
      assert.ok(!/(^|\s)null(\s|$)/.test(await page.locator('dialog[open]').innerText()), '"null" is printed in a task window');
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({pages: 25, errors: errors.length, mobile_width_ok: true, workers_running_waiting_failed_offline: true, reduced_motion:true}));
  } catch (error) {
    if (shots && activePage) {
      await activePage.screenshot({path:path.join(shots,'failure.png')}).catch(() => {});
      require('node:fs').writeFileSync(path.join(shots,'failure.txt'), await activePage.locator('body').innerText().catch(() => 'Page unavailable'));
    }
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
