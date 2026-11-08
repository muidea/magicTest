// Observe the actual interaction without replaying navigation or authentication.
const selectors = {
  account: 'input[name=account]',
  password: 'input[name=password]',
  submit: 'form[action="/oauth/login"] button[type=submit]',
};
async function waitLoginForm(page, timeout = 30000) {
  const deadline = Date.now() + timeout;
  const remaining = () => Math.max(1, deadline - Date.now());
  await page.waitForURL(url => url.pathname === '/login/cas', { timeout: remaining() });
  const form = Object.fromEntries(Object.entries(selectors).map(([key, value]) => [key, page.locator(value)]));
  for (const locator of Object.values(form)) await locator.waitFor({ state: 'visible', timeout: remaining() });
  return form;
}
async function waitLoginError(page, timeout = 30000) {
  const error = page.locator('.ant-alert-error').filter({ hasText: /密码|凭据|账号|account|password|credential|invalid|incorrect/i }).first();
  await error.waitFor({ state: 'visible', timeout });
  return error;
}
async function observeLogin(actor, { record, capture }, action) {
  const { page } = actor, started = Date.now(), events = [];
  const add = event => { if (events.length < 200) events.push({ elapsedMs: Date.now() - started, ...event }); };
  const trackedPath = raw => {
    const url = new URL(raw);
    if (url.origin !== actor.origin) return null;
    return ['/api/v1/web/auth/login', '/api/v1/web/branding/', '/login/cas', '/oauth/login'].includes(url.pathname)
      || /^\/[a-zA-Z0-9_.-]+\.(js|css)$/.test(url.pathname) ? url.pathname : null;
  };
  const request = req => { const path = trackedPath(req.url()); if (path) add({ kind: 'request', path, method: req.method() }); };
  const response = res => { const path = trackedPath(res.url()); if (path) add({ kind: 'response', path, status: res.status(), contentType: res.headers()['content-type'] }); };
  const requestfailed = req => { const path = trackedPath(req.url()); if (path) add({ kind: 'requestfailed', path, method: req.method(), error: req.failure()?.errorText }); };
  // Messages, stacks, queries, headers, bodies and field values are never recorded.
  const pageerror = () => add({ kind: 'pageerror' });
  page.on('request', request); page.on('response', response); page.on('pageerror', pageerror); page.on('requestfailed', requestfailed);
  try {
    const result = await action();
    record({ kind: 'login-observation', outcome: 'completed', events });
    return result;
  } catch (error) {
    const state = {};
    try {
      state.path = new URL(page.url()).pathname;
      for (const [key, selector] of Object.entries(selectors)) state[key + 'Visible'] = await page.locator(selector).isVisible();
      state.errorVisible = await page.locator('.ant-alert-error').first().isVisible();
      state.document = await page.evaluate(() => ({ readyState: document.readyState, rootChildren: document.getElementById('root')?.childElementCount, bodyChildren: document.body?.childElementCount, resourceCount: performance.getEntriesByType('resource').length }));
      const location = new URL(page.url());
      state.queryShape = { transactionCount: location.searchParams.getAll('transaction').length, namespaceMatches: location.searchParams.get('namespace') === actor.identity.namespace, errorPresent: location.searchParams.has('error') };
    } catch { state.unavailable = true; }
    let screenshotCaptured = false;
    try { await capture(); screenshotCaptured = true; } catch { /* Preserve the original failure even when evidence capture fails. */ }
    try { record({ kind: 'login-observation', outcome: 'failed', state, screenshotCaptured, events }); } catch {}
    throw error;
  } finally {
    page.off('request', request); page.off('response', response); page.off('pageerror', pageerror); page.off('requestfailed', requestfailed);
  }
}
module.exports = { waitLoginForm, waitLoginError, observeLogin };
