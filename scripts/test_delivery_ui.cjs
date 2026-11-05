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

    await page.locator('[data-page="books"]').click();
    await page.getByText('Daily Gratitude Journal', {exact: true}).first().click();
    await page.getByRole('heading', {name: 'Keyword check', exact: true}).waitFor();
    const dialog = await page.locator('dialog').innerText();
    assert.match(dialog, /\d+\/100/);
    assert.match(dialog, /Box 1 \(“journal”\) is a single word/);
    assert.match(dialog, /Box 2 \(“daily gratitude journals”\) only repeats your title/);
    assert.match(dialog, /Box 5 is empty/);
    await page.getByRole('heading', {name: 'Keyword check', exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'keyword-check.png')});
    assert.deepEqual(errors, []);
    console.log('Paused notice -> resume clears it; keyword check names each wasted box: passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
