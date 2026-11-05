// Full dashboard and real persistence, with fixture providers and no external sends.
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
    const picker = page.getByLabel('Model for prospect drafts');
    try { await picker.waitFor(); }
    catch (error) {
      console.error('Fixture page:', (await page.locator('body').innerText()).slice(0, 5000), 'Page errors:', errors);
      throw error;
    }
    assert.equal(await picker.inputValue(), 'auto');
    await page.getByText('Fixture Dental', {exact: true}).click();
    await page.getByRole('button', {name: 'Draft a first email', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Claude usage limit reached'}).waitFor();
    await page.locator('#dialog-close').click();
    assert.equal(await picker.locator('option[value="catalog:claude:sonnet"]').innerText(), 'Claude Sonnet');
    assert.equal(await picker.locator('option[value^="api:"]').count(), 0);
    await picker.selectOption('catalog:codex:gpt-subscription-fixture');
    await page.getByRole('button', {name: 'Save writing model', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Prospect writing model saved'}).waitFor();
    await page.reload();
    await picker.waitFor();
    assert.equal(await picker.inputValue(), 'catalog:codex:gpt-subscription-fixture');
    const settings = await page.evaluate(async () => (await fetch('/api/outreach')).json());
    assert.equal(settings.settings.enabled, false);
    assert.equal(settings.settings.subscription_only, true);
    await page.getByText('Fixture Dental', {exact: true}).click();
    await page.getByRole('button', {name: 'Draft a first email', exact: true}).click();
    await page.waitForFunction(() => [...document.querySelectorAll('dialog textarea')].some(node => node.value.includes('Codex fixture draft')));
    assert.deepEqual(await page.evaluate(async () => (await fetch('/fixture-provider-calls')).json()), ['claude', 'codex']);
    await page.locator('#dialog-close').click();
    await picker.scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'prospect-writing-model.png')});
    assert.deepEqual(errors, []);
    console.log('Claude limit -> save ChatGPT (Codex) -> reload -> draft succeeds; automation stays off: passed');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});
