// Observe the original first-party browser transaction, never synthesize tokens.
const crypto = require('node:crypto');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
const { ownerRequest } = require('./owner_transport.cjs');
const { waitLoginForm } = require('./login_readiness.cjs');
const callbackPath = '/api/v1/web/auth/callback';
const authorizePaths = ['/oauth/authorize', '/api/v1/cas/oauth/authorize'];
function authorizationVariant(original, origin, mode) {
  const url = new URL(original);
  if (url.origin !== origin || !authorizePaths.includes(url.pathname) || !['normal', 'nonce', 'state', 'pkce'].includes(mode)) throw Error('Exact original first-party authorization is required');
  for (const field of ['state', 'nonce', 'client_id', 'redirect_uri', 'code_challenge', 'code_challenge_method']) if (url.searchParams.getAll(field).length !== 1 || !url.searchParams.get(field)) throw Error('Incomplete or ambiguous first-party authorization');
  if (url.searchParams.get('code_challenge_method') !== 'S256' || new URL(url.searchParams.get('redirect_uri')).origin !== origin) throw Error('Invalid original PKCE or callback binding');
  if (mode !== 'normal') {
    const field = { nonce: 'nonce', state: 'state', pkce: 'code_challenge' }[mode];
    const changed = crypto.randomBytes(32).toString('base64url');
    if (changed === url.searchParams.get(field)) throw Error('Authorization negative control did not change');
    url.searchParams.set(field, changed);
  }
  return url;
}
// Capture the original BFF redirect at its first navigation. Playwright does
// not route every hop of a redirect chain; observe actual later responses.
async function withOriginalAuthorizationEntry(actor, mode, hooks, action) {
  const { journal, persist } = hooks, page = actor.page, pending = [];
  let failure;
  const entryMatch = url => url.origin === actor.origin && url.pathname === '/api/v1/web/auth/login';
  const entry = async route => {
    try {
      const request = route.request();
      if (journal.authorizations.length || request.method() !== 'GET' || !request.isNavigationRequest() || request.frame() !== page.mainFrame()) throw Error('Exact original BFF login navigation required once');
      journal.entry = { originalURL: request.url(), outcome: 'unknown' }; persist();
      const target = new URL(request.url()), connect = new URL(target);
      if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
      const response = await route.fetch({ url: connect.href, headers: { ...await request.allHeaders(), host: target.host }, maxRedirects: 0, maxRetries: 0, timeout: 30000 });
      journal.entry.status = response.status(); journal.entry.outcome = 'response-received'; persist();
      if (response.status() !== 302 || !response.headers().location) throw Error('Original BFF must supply one real authorization redirect');
      const original = new URL(response.headers().location, actor.origin), dispatched = authorizationVariant(original.href, actor.origin, mode);
      journal.authorizations.push({ originalURL: original.href, dispatchedURL: dispatched.href, observations: 0, outcome: 'prepared' }); persist();
      await route.fulfill({ response, headers: { ...response.headers(), location: dispatched.href } });
    } catch (error) { failure ||= error; await route.abort('failed').catch(() => {}); }
  };
  const observe = response => {
    const request = response.request(), url = new URL(request.url());
    if (url.origin !== actor.origin || request.method() !== 'GET' || !request.isNavigationRequest() || request.frame() !== page.mainFrame()) return;
    if (authorizePaths.includes(url.pathname)) {
      const original = journal.authorizations[0];
      if (!original || request.url() !== original.dispatchedURL || original.observations) { failure ||= Error('Authorization response differs from exact original redirected transaction'); return; }
      original.observations++; original.status = response.status(); original.outcome = 'response-received'; persist();
    }
    if (url.pathname === callbackPath) {
      const task = (async () => {
        if (journal.callbacks.length || url.searchParams.getAll('state').length !== 1 || url.searchParams.getAll('code').length !== 1) throw Error('Exact original authorization-code callback required once');
        const record = { originalURL: url.href, status: response.status(), outcome: 'response-received' };
        journal.callbacks.push(record); persist();
        if (response.status() >= 400) record.body = await response.text();
        record.location = response.headers().location || ''; persist();
      })().catch(error => { failure ||= error; });
      pending.push(task);
    }
  };
  await page.route(entryMatch, entry); page.on('response', observe);
  try { const result = await action(); await Promise.all(pending); if (failure) throw failure; return result; }
  finally { page.off('response', observe); await page.unroute(entryMatch, entry); await Promise.all(pending); }
}
async function attempt(h, mode) {
  const original = h.user;
  const beforeSession = (await h.ok(original, 'GET', '/api/v1/web/session/')).value;
  const sessionRoute = '/api/v1/web/login-sessions/?' + new URLSearchParams({ namespace: original.identity.namespace, accountId: String(beforeSession.account.id), _pageSize: '100' });
  const sessions = async () => {
    const result = (await ownerRequest(h.tenantAdmin, 'GET', sessionRoute, undefined, h.observe));
    h.check('Independent callback session directory is complete and bound to the original ordinary account', h.good(result) && Array.isArray(result.data.values) && result.data.values.every(row => row.accountId === beforeSession.account.id && row.namespace === original.identity.namespace) && !result.data.pagination?.hasMore && (result.data.pagination?.total ?? result.data.values.length) === result.data.values.length);
    return result.data.values;
  };
  const beforeIDs = (await sessions()).map(row => row.id).sort();
  const context = await h.browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
  const actor = { context, page: await context.newPage(), origin: original.origin, identity: structuredClone(original.identity) };
  const journal = { mode, identity: structuredClone(actor.identity), origin: actor.origin, phase: 'prepared', authorizations: [], callbacks: [] };
  (h.state.callbackProbes ||= []).push(journal); h.persist();
  const callbackMatch = url => url.pathname === callbackPath;
  let authenticated = false, verdict;
  try {
    await withOriginalAuthorizationEntry(actor, mode, { journal, persist: h.persist }, () => withOriginalCasForms(actor, { journal: h.state.originalCasForms ||= [], persist: h.persist, record: h.observe }, async () => {
      await actor.page.goto(actor.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
      const form = await waitLoginForm(actor.page);
      await form.account.fill(actor.identity.account); await form.password.fill(original.password);
      const returned = actor.page.waitForResponse(response => callbackMatch(new URL(response.url())), { timeout: 30000 }); returned.catch(() => {});
      await form.submit.click(); await returned;
      await actor.page.waitForLoadState('networkidle');
    }));
    const response = await ownerRequest(actor, 'GET', '/api/v1/web/session/', undefined, h.observe);
    authenticated = h.good(response);
    const a = journal.authorizations[0], c = journal.callbacks[0];
    h.check('Original first-party authorization and callback each reached their real owner once', journal.authorizations.length === 1 && journal.callbacks.length === 1 && a.outcome === 'response-received' && c.outcome === 'response-received');
    const expected = new URL(a.originalURL), sent = new URL(a.dispatchedURL), returned = new URL(c.originalURL);
    const changedField = { nonce: 'nonce', state: 'state', pkce: 'code_challenge' }[mode];
    const unchanged = ['state', 'nonce', 'client_id', 'redirect_uri', 'code_challenge', 'code_challenge_method', 'scope'].filter(key => key !== changedField).every(key => expected.searchParams.get(key) === sent.searchParams.get(key));
    const changed = mode === 'normal' || expected.searchParams.get(changedField) !== sent.searchParams.get(changedField);
    h.check('Probe preserves every original binding except the one deliberate negative-control field', unchanged && changed && returned.searchParams.get('state') === sent.searchParams.get('state'));
    journal.phase = 'observed'; h.persist();
    h.observe({ kind: 'first-party-callback-probe', mode, actor: actor.identity, authorizeStatus: a.status, callbackStatus: c.status, authenticated, changedField, changedOnlyNonce: mode === 'nonce' && unchanged && changed, preservesOtherBindings: unchanged, secrets: 'original code, state and nonce retained only in external private journal' });
    await h.screenshot(actor, 'callback-' + mode);
    if (mode === 'normal') {
      h.check('Normal original callback establishes the exact ordinary account and tenant', c.status === 302 && authenticated && response.data.value.account.account === actor.identity.account && response.data.value.homeNamespace === actor.identity.namespace);
      const currentIDs = (await sessions()).map(row => row.id);
      h.check('Normal callback creates exactly one additional original-account BFF session', currentIDs.length === beforeIDs.length + 1 && beforeIDs.every(id => currentIDs.includes(id)));
      verdict = { mode, passed: true, authenticated, callbackStatus: c.status };
    }
    else verdict = { mode, passed: changed && [400, 401, 403].includes(c.status) && !authenticated && (response.status === 401 || response.data?.error?.code === 11), authenticated, callbackStatus: c.status };
    journal.verdict = verdict; h.persist();
    h.observe({ kind: 'first-party-callback-verdict', ...verdict });
  } finally {
    try {
      if (authenticated) {
        journal.logout = { outcome: 'unknown' }; h.persist();
        await actor.page.goto(actor.origin + '/api/v1/web/auth/logout', { waitUntil: 'networkidle' });
        const response = await ownerRequest(actor, 'GET', '/api/v1/web/session/', undefined, h.observe);
        h.check('Probe logout independently retires its original authenticated BFF session', response.status === 401 || response.data?.error?.code === 11);
        journal.logout.outcome = 'confirmed'; h.persist();
      }
      const retained = await ownerRequest(original, 'GET', '/api/v1/web/session/', undefined, h.observe);
      h.check('Callback probe preserves the unrelated original ordinary-user session', h.good(retained) && retained.data.value.account.id === beforeSession.account.id && retained.data.value.homeNamespace === original.identity.namespace);
      h.check('Callback probe leaves no additional active original-account session after disposition', require('node:util').isDeepStrictEqual((await sessions()).map(row => row.id).sort(), beforeIDs));
    } finally { await context.close(); }
  }
  return verdict;
}
async function runControls(h, run = attempt) {
  const results = [];
  const firstProbe = h.state.callbackProbes?.length || 0;
  // Dispose each exact probe before moving to the next independent binding.
  // A confirmed nonce defect must not prevent observing state and PKCE too.
  try {
    for (const mode of ['normal', 'nonce', 'state', 'pkce']) results.push(await run(h, mode));
  } catch (error) {
    const observed = [...results, ...(h.state.callbackProbes || []).slice(firstProbe).map(p => p.verdict).filter(Boolean)];
    h.observe({ kind: 'callback-controls-interrupted', reason: error.message, observed });
    // A later environment/cleanup error must not erase an already confirmed
    // security failure. The runner's independent cleanup gate remains false
    // when disposition did not finish.
    h.check('Previously confirmed callback security failures remain failed after a later interruption', !observed.some(r => r.passed === false), observed);
    throw error;
  }
  h.check('Normal first-party callback and all independent nonce/state/S256 binding controls enforce their original transaction', results.every(result => result.passed), results);
}
const handlers = { 'F001-006': async h => {
  await runControls(h);
  await h.partial('Normal first-party callback and nonce/state/S256 controls proven; callback substitutions, original CAS code-consumption/reuse and security-audit correlation still require their complete independent assertions.');
} };
handlers['F001-006'].actors = ['user', 'tenantAdmin']; handlers['F001-006'].transport = 'owner-api';
module.exports = { handlers, authorizationVariant, withOriginalAuthorizationEntry, runControls };
