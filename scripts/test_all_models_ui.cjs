const {chromium} = require(process.env.AIHQ_PLAYWRIGHT);
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1366, height: 960}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/onboarding', route => route.fulfill({json: {needs_setup: false}}));
    await page.goto(process.env.AIHQ_URL);
    await page.locator('[data-page="prospects"]').click();
    const picker = page.getByLabel('Model for prospect drafts');
    await picker.waitFor();
    await page.getByLabel('Advanced: use separately billed API models').check();
    assert.equal(await picker.locator('option[value="catalog:claude:sonnet"]').count(), 1);
    assert.equal(await picker.locator('option[value="catalog:codex:gpt-cli-fixture"]').count(), 1);
    for (const [name, key, option] of [['OpenAI API', 'fixture-openai-key', 'api:openai:gpt-api-fixture'], ['Anthropic API', 'fixture-anthropic-key', 'api:anthropic:claude-api-fixture']]) {
      const details = page.locator('details').filter({has: page.locator('summary').getByText('OpenAI and Anthropic API connections', {exact: true})});
      if (!(await details.getAttribute('open'))) {
        if (!(await details.evaluate(node => node.open))) await details.locator('summary').click();
      }
      await page.getByLabel(`${name} key`, {exact: true}).fill(key);
      await page.getByRole('button', {name: `Save ${name} key`, exact: true}).click();
      await picker.locator(`option[value="${option}"]`).waitFor({state: 'attached'});
    }
    assert.equal(await picker.locator('option[value="api:openai:gpt-image-fixture"]').evaluate(node => node.disabled), true);
    await picker.selectOption('api:anthropic:claude-api-fixture');
    await page.getByRole('button', {name: 'Save writing model', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Prospect writing model saved'}).waitFor();
    await page.getByText('API Fixture Dental', {exact: true}).click();
    await page.getByRole('button', {name: 'Draft a first email', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Fixture Claude API quota reached'}).waitFor();
    await page.locator('#dialog-close').click();
    await picker.selectOption('api:openai:gpt-api-fixture');
    await page.getByRole('button', {name: 'Save writing model', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Prospect writing model saved'}).waitFor();
    await page.reload();
    await picker.waitFor();
    assert.equal(await picker.inputValue(), 'api:openai:gpt-api-fixture');
    await page.getByText('API Fixture Dental', {exact: true}).click();
    await page.getByRole('button', {name: 'Draft a first email', exact: true}).click();
    await page.waitForFunction(() => [...document.querySelectorAll('dialog textarea')].some(node => node.value.includes('OpenAI API fixture draft')));
    const calls = await page.evaluate(async () => (await fetch('/fixture-api-calls')).json());
    assert.deepEqual(calls, [{host: 'api.anthropic.com', model: 'claude-api-fixture'}, {host: 'api.openai.com', model: 'gpt-api-fixture'}]);
    const state = await page.evaluate(async () => (await fetch('/api/outreach')).json());
    assert.equal(state.settings.enabled, false);
    await page.locator('#dialog-close').click();
    await picker.scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, 'all-models-picker.png')});
    await page.getByLabel('Search models', {exact: true}).fill('gpt-api-fixture');
    assert.equal(await picker.locator('option[value="catalog:claude:sonnet"]').count(), 0);
    await page.getByLabel('Search models', {exact: true}).fill('');
    await page.getByText('Use a custom model ID', {exact: true}).click();
    await page.getByLabel('Custom model ID', {exact: true}).fill('gpt-custom-fixture');
    await page.getByRole('button', {name: 'Save writing model', exact: true}).click();
    await page.locator('#toast').filter({hasText: 'Prospect writing model saved'}).waitFor();
    await page.reload();
    await picker.waitFor();
    assert.equal(await picker.inputValue(), 'api:openai:gpt-custom-fixture');
    assert.deepEqual(errors, []);
    console.log('Individual CLI + API catalogs, secure key save/refresh, quota switch, persisted exact model, non-text guard, search and custom ID: passed');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});
