// Regression for a verified local installer surviving an unavailable GitHub lookup.
const {chromium} = require(process.env.AIHQ_PLAYWRIGHT);
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1280, height: 900}});
    for (const scenario of ['ready', 'becomes-ready', 'not-ready']) {
      const page = await context.newPage();
      let releaseCalls = 0, progressCalls = 0, installs = 0;
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      if (process.env.AIHQ_INSTALLED_JS) await page.route('**/static/app.js', route => route.fulfill({contentType: 'text/javascript', body: fs.readFileSync(process.env.AIHQ_INSTALLED_JS)}));
      await page.route('**/api/onboarding', route => route.fulfill({json: {needs_setup: false}}));
      await page.route('**/api/updates', route => {
        releaseCalls++;
        return route.fulfill({status: 400, json: {detail: 'GitHub is limiting update checks from this internet connection for now.'}});
      });
      await page.route('**/api/updates/progress', route => {
        progressCalls++;
        const ready = scenario === 'ready' || (scenario === 'becomes-ready' && progressCalls > 1);
        return route.fulfill({json: {phase: ready ? 'ready' : 'idle', tag: 'v99.0.0', message: ready ? 'Downloaded and verified. Install when ready.' : ''}});
      });
      await page.route('**/api/updates/install', route => {
        installs++;
        return route.fulfill({json: {restarting: true, message: 'Fixture install requested'}});
      });
      await page.goto(scenario === 'ready' ? process.env.AIHQ_URL : process.env.AIHQ_URL.split('#')[0]);
      await page.locator('[data-page="settings"]').click();
      if (scenario === 'not-ready') {
        await page.getByRole('button', {name: 'Try again', exact: true}).waitFor();
        assert.equal(await page.getByRole('button', {name: 'Install and restart', exact: true}).count(), 0);
      } else {
        const install = page.getByRole('button', {name: 'Install and restart', exact: true});
        await install.waitFor();
        assert.equal(releaseCalls, scenario === 'ready' ? 0 : 1);
        await install.scrollIntoViewIfNeeded();
        await page.screenshot({path: path.join(process.env.AIHQ_SHOTS, `update-${scenario}.png`)});
        await install.click();
        await page.locator('.notice').filter({hasText: 'Fixture install requested'}).waitFor();
        assert.equal(installs, 1);
      }
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`${scenario}: passed`);
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});
