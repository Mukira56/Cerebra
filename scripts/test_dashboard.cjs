// Drives every dashboard page in headless Edge against a throwaway Cerebra server (agents off, temp data).
// Usage: set AIHQ_PLAYWRIGHT=<path to playwright-core>, AIHQ_URL=http://127.0.0.1:<port>/#key=<key>, AIHQ_SHOTS=<dir>
const { chromium } = require(process.env.AIHQ_PLAYWRIGHT);
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const shots = process.env.AIHQ_SHOTS;
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 960}});
    const page = await context.newPage(), errors = [];
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
    await page.locator('.diagram .node[aria-label="Test runner"]').click();
    await page.locator('.inspector h3', {hasText: 'Test runner'}).waitFor();
    await page.locator('.trace div').first().waitFor();
    await shot('system');

    // Chat: agents are off, so the reply fails with a clear message (no provider is launched).
    await page.locator('[data-page="chat"]').click();
    await page.getByRole('button', {name: '+ New chat'}).click();
    await page.locator('.composer textarea').fill('Explain the **project** layout');
    await page.locator('.composer textarea').press('Enter');
    await page.locator('.message.user .bubble', {hasText: 'Explain the **project** layout'}).waitFor({timeout: 15000});
    await page.locator('.bubble.failed', {hasText: 'AI agents are switched off'}).waitFor({timeout: 15000});
    assert.ok(await page.getByRole('button', {name: 'Send', exact: true}).isVisible());
    await shot('chat');

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
    console.log(JSON.stringify({pages: 13, errors: errors.length, mobile_width_ok: true}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
