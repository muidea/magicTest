const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('./playwright.cjs');
const { waitLoginForm, waitLoginError, observeLogin } = require('./login_readiness.cjs');

test('actual delayed login DOM and rejection feedback determine readiness after network idle', async () => {
  const server = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(`<script>window.renderForm = () => setTimeout(() => {
      document.body.innerHTML = '<form action="/oauth/login"><input name="account"><input name="password" type="password"><button type="submit">Login</button></form>';
      window.renderError = () => setTimeout(() => { const error = document.createElement('div'); error.className = 'ant-alert-error'; error.textContent = '密码错误'; document.body.append(error); }, 100);
    }, 100);</script>`);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + server.address().port + '/login/cas', { waitUntil: 'networkidle' });
    assert.equal(await page.locator('input[name=account]').isVisible(), false, 'negative control reproduces premature assertion');
    await page.evaluate(() => window.renderForm());
    const form = await waitLoginForm(page, 4000);
    assert.equal(await form.submit.isVisible(), true);
    assert.equal(await page.locator('.ant-alert-error').isVisible(), false);
    await page.evaluate(() => window.renderError());
    assert.equal(await (await waitLoginError(page, 4000)).innerText(), '密码错误');
    await page.locator('form').evaluate(el => el.remove());
    await assert.rejects(waitLoginForm(page, 150), { name: 'TimeoutError' });
    await page.locator('.ant-alert-error').evaluate(el => el.textContent = 'unrelated warning');
    await assert.rejects(waitLoginError(page, 150), { name: 'TimeoutError' });
    await page.goto('http://127.0.0.1:' + server.address().port + '/other');
    await assert.rejects(waitLoginForm(page, 150), { name: 'TimeoutError' });
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
});

test('failure observation precedes closure, omits secrets, detaches and preserves original error', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage(), origin = 'https://login.example.invalid';
    await page.route('**/*', route => route.fulfill({ contentType: 'text/html', body: '<input name="password" type="password" value="PRIVATE-FIELD">' }));
    const actor = { page, origin }, records = [], original = new Error('original failure');
    const listeners = ['request', 'response', 'pageerror'].map(name => page.listenerCount(name));
    let captures = 0;
    await assert.rejects(observeLogin(actor, {
      record: event => records.push(event),
      capture: async () => { captures++; assert.equal(page.isClosed(), false); throw Error('capture unavailable'); },
    }, async () => {
      await page.goto(origin + '/login/cas?code=PRIVATE-QUERY&state=PRIVATE-STATE');
      const observedError = page.waitForEvent('pageerror');
      await page.evaluate(() => setTimeout(() => { throw Error('PRIVATE-ERROR'); }, 0));
      await observedError;
      throw original;
    }), error => error === original);
    assert.equal(captures, 1);
    assert.equal(records[0].state.path, '/login/cas');
    assert.equal(records[0].state.passwordVisible, true);
    assert.equal(records[0].screenshotCaptured, false);
    assert.ok(records[0].events.some(event => event.kind === 'response' && event.status === 200));
    assert.ok(records[0].events.some(event => event.kind === 'pageerror'));
    assert.doesNotMatch(JSON.stringify(records), /PRIVATE|\?code|stack/);
    assert.deepEqual(['request', 'response', 'pageerror'].map(name => page.listenerCount(name)), listeners);
    await assert.rejects(observeLogin(actor, { record() { throw Error('record unavailable'); }, capture: async () => {} }, async () => { throw original; }), error => error === original);
  } finally { await browser.close(); }
});
