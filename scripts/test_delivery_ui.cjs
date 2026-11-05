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
    assert.deepEqual(errors, []);
    console.log('Paused notice -> resume clears it; build-up limit shows; KDP and Etsy checks name each weak spot: passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
