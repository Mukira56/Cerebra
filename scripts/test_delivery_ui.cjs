// The sending pause and the keyword check, on the real pages with isolated records and no external sends.
const {chromium} = require(process.env.AIHQ_PLAYWRIGHT);
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1366, height: 940}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/onboarding', route => route.fulfill({json: {needs_setup: false}}));
    await page.goto(process.env.AIHQ_URL);

    await page.locator('[data-page="prospects"]').click();
    const paused = page.getByText('Automatic sending is paused', {exact: true});
    await paused.waitFor();
    await page.getByText('3 of your last 3 emails bounced', {exact: false}).first().waitFor();
    await paused.scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'sending-paused.png')});
    await page.getByRole('button', {name: 'Resume automatic sending', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Resumed.'}).waitFor();
    await paused.waitFor({state: 'detached'});
    const state = await page.evaluate(async () => (await fetch('/api/outreach')).json());
    assert.equal(state.health.paused, false);
    assert.equal(state.health.sent, 0);

    const saved = await page.evaluate(async () => {
      const {csrf_token} = await (await fetch('/api/session')).json();
      return (await fetch('/api/outreach', {method: 'PUT', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf_token}, body: JSON.stringify({per_day: 40})})).status;
    });
    assert.equal(saved, 200);
    await page.reload();
    await page.getByText('building up to your 40 a day', {exact: false}).waitFor();
    await page.getByText('3 of 10', {exact: true}).waitFor();
    await page.locator('[data-page="books"]').click();
    await page.getByText('Daily Gratitude Journal', {exact: true}).first().click();
    await page.getByRole('heading', {name: 'Keyword check', exact: true}).waitFor();
    const dialog = await page.locator('dialog').innerText();
    assert.match(dialog, /\d+\/100/);
    assert.match(dialog, /Box 1 \(“journal”\) is a single word/);
    assert.match(dialog, /Box 2 \(“daily gratitude journals”\) only repeats your title/);
    assert.match(dialog, /3 of 7 boxes are empty/);
    await page.getByRole('heading', {name: 'Keyword check', exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'keyword-check.png')});
    await page.locator('#dialog-close').click();
    await page.getByPlaceholder('mileage log book', {exact: true}).fill('mileage log book');
    await page.getByPlaceholder('Mileage Log Book for Taxes | 12500 | 840 | 7.99 | 120').fill('Road Miles Tracker | 12500 | 840 | 7.99 | 120\nVehicle Mileage Record | 45000 | 60 | 8.99 | 110\nDriver Mileage Book | 80000 | 35 | 6.99 | 130');
    await page.getByRole('button', {name: "Read what's selling", exact: true}).click();
    await page.getByText('What the top books have in common', {exact: true}).waitFor();
    await page.getByText('3 of 3 rank under 100,000', {exact: false}).waitFor();
    await page.getByRole('button', {name: 'Make my own version', exact: true}).waitFor();
    await page.getByText('What the top books have in common', {exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'market-panel.png')});

    await page.locator('[data-page="etsy"]').click();
    await page.getByText('wedding planner printable', {exact: true}).first().click();
    await page.getByText('Modern Bridal Organizer Set', {exact: false}).first().click();
    await page.getByRole('heading', {name: 'Keyword check', exact: true}).waitFor();
    const etsy = await page.locator('dialog').innerText();
    assert.match(etsy, /\d+\/100/);
    assert.match(etsy, /Your main keyword “wedding planner printable” isn't in the title/);
    assert.match(etsy, /Tag 2 \(“journal”\) is a single word/);
    await page.getByRole('heading', {name: 'Keyword check', exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'etsy-check.png')});
    await page.locator('#dialog-close').click();

    await page.locator('[data-page="settings"]').click();
    await page.getByRole('button', {name: 'Back up now', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Backed up and checked.'}).waitFor();
    const goBack = page.getByRole('button', {name: 'Go back to this', exact: true}).first();
    await goBack.waitFor();
    page.once('dialog', dialog => dialog.accept());
    await goBack.click();
    await page.getByText('close Cerebra completely and open it again to finish', {exact: false}).first().waitFor();
    await page.getByRole('button', {name: "Don't go back", exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'backups.png')});
    await page.getByRole('button', {name: "Don't go back", exact: true}).click();
    await page.getByRole('button', {name: "Don't go back", exact: true}).waitFor({state: 'detached'});
    assert.equal((await page.evaluate(async () => (await fetch('/api/backups')).json())).restore_pending, '');
    await page.evaluate(async () => {
      const {csrf_token} = await (await fetch('/api/session')).json();
      await fetch('/api/owner', {method: 'PUT', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf_token}, body: JSON.stringify({name: 'Sample Person', github: 'sample-person', share: true})});
    });
    await page.reload();
    const nameField = page.getByPlaceholder('e.g. Alex Rivera');
    await nameField.waitFor();
    await page.waitForFunction(() => document.querySelector('input[placeholder="e.g. Alex Rivera"]').value === 'Sample Person');
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', {name: 'Clear my details', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Cleared.'}).waitFor();
    assert.equal(await nameField.inputValue(), '');
    const cleared = await page.evaluate(async () => (await fetch('/api/owner')).json());
    assert.equal(cleared.name, ''); assert.equal(cleared.github, ''); assert.equal(cleared.share, false);

    let connected = false, opened = 0;
    await page.route('**/api/github', route => route.fulfill({json: connected ? {installed: true, signed_in: true, account: 'sample-user', name: 'Sample', url: 'https://github.test/sample-user', public_repos: 3} : {installed: true, signed_in: false}}));
    await page.route('**/api/github/repositories', route => route.fulfill({json: []}));
    await page.route('**/api/github/sign-in', route => { opened += 1; route.fulfill({json: {opened: true, message: 'A GitHub window opened. Copy the one-time code it shows and press Enter, then finish in your browser. This page updates by itself.'}}); });
    await page.locator('[data-page="github"]').click();
    await page.getByRole('button', {name: 'Connect GitHub', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'This page updates by itself'}).waitFor();
    assert.equal(opened, 1);
    connected = true;  // the person finishes in their browser and touches nothing here
    await page.locator('#toast').filter({hasText: 'GitHub connected.'}).waitFor({timeout: 15000});
    await page.getByText('sample-user', {exact: true}).first().waitFor();
    assert.deepEqual(errors, []);
    console.log('Paused notice -> resume clears it; build-up limit shows; KDP and Etsy checks name each weak spot; market reader plans a book; back up, choose, cancel; About you clears; GitHub page updates by itself: passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
