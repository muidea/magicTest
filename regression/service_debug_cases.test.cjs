// Browser timing checks for the tool; deployed debugger verification is separate.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('./playwright.cjs');
const { choose } = require('./service_debug_cases.cjs');

test('every operation change waits for the delayed form remount before writing input', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.setContent(`<code>/api/v1/gateway/services/fixture/echo</code>
      <button role="menuitem" data-key="echo">JSON echo</button>
      <button role="menuitem" data-key="slow">Slow original</button>
      <button role="menuitem" data-key="fast">Current fast</button>
      <table><tbody><tr data-row-key="query:marker"><td><textarea></textarea></td></tr></tbody></table>
      <script>
      window.generation = 0;
      for (const button of document.querySelectorAll('button')) button.onclick = () => {
        const header = document.querySelector('code');
        const path = '/api/v1/gateway/services/fixture/' + button.dataset.key;
        if (header.textContent === path) return;
        header.textContent = path;
        setTimeout(() => {
          document.querySelector('textarea').replaceWith(document.createElement('textarea'));
          window.generation++;
        }, 250);
      };
      </script>`);
    const field = page.locator('textarea');
    // Reproduce the bug: a changed header does not prove resetFields finished.
    await page.getByRole('menuitem', { name: 'Slow original' }).click();
    await field.fill('premature-input');
    await page.waitForFunction(() => window.generation === 1);
    assert.equal(await field.inputValue(), '');
    for (const [name, generation] of [['Current fast', 2], ['Slow original', 3], ['Current fast', 4]]) {
      await choose(page, name);
      assert.equal(await page.evaluate(() => window.generation), generation);
      await field.fill('preserved-' + generation);
      assert.equal(await field.inputValue(), 'preserved-' + generation);
    }
    await choose(page, 'Current fast');
    assert.equal(await page.evaluate(() => window.generation), 4);
    assert.equal(await field.inputValue(), 'preserved-4');
  } finally { await browser.close(); }
});
