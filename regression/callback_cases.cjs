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
function callbackTamperURL(origin, params = {}) {
  const url = new URL(callbackPath, origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  }
  return url.href;
}
async function awaitRows(read, predicate) {
  let rows = [];
  for (let i = 0; i < 15; i++) {
    rows = await read();
    if (predicate(rows)) return rows;
    if (i < 14) await new Promise(resolve => setTimeout(resolve, 1000));
  }
  return rows;
}
async function verifyCallbackSubstitutionsAndAudit(h) {
  const original = h.user, n = original.identity.namespace;
  const beforeSession = (await h.ok(original, 'GET', '/api/v1/web/session/')).value;
  const subject = 'account:' + beforeSession.account.id;
  const casAuditRoute = '/cas/namespaces/' + n + '/oauth/audit/';
  const panelAccessRoute = '/panel/support/audit/access';
  const sessionRoute = '/api/v1/web/login-sessions/?' + new URLSearchParams({ namespace: n, accountId: String(beforeSession.account.id), _pageSize: '100' });
  const sessions = () => h.directory(h.tenantAdmin, sessionRoute).then(rows => rows.map(r => r.id).sort());
  const beforeCasAuditIDs = new Set((await h.directory(h.tenantAdmin, casAuditRoute)).map(r => r.id));
  const beforePanelAccessIDs = new Set((await h.directory(h.tenantAdmin, panelAccessRoute)).map(r => r.id));
  const beforeSessionIDs = await sessions();
  const startedAt = Date.now();
  await runControls(h);
  const normalProbe = [...(h.state.callbackProbes || [])].reverse().find(p => p.mode === 'normal');
  const consumedCode = normalProbe?.callbacks?.[0]?.originalURL ? new URL(normalProbe.callbacks[0].originalURL).searchParams.get('code') : '';
  h.check('Normal first-party probe captured a real single-use CAS authorization code', typeof consumedCode === 'string' && consumedCode.length > 0);
  const casAfterControls = await awaitRows(
    () => h.directory(h.tenantAdmin, casAuditRoute),
    rows => {
      const fresh = rows.filter(r => !beforeCasAuditIDs.has(r.id) && r.subject === subject && r.createTime >= startedAt - 2000);
      return fresh.some(r => r.eventType === 'login_success' && r.outcome === 'success') &&
        fresh.some(r => r.eventType === 'token_issued' && r.outcome === 'success' && JSON.parse(r.detailJson || '{}').grantType === 'authorization_code') &&
        fresh.some(r => r.eventType === 'logout_success' && r.outcome === 'success');
    }
  );
  const newCasEvents = casAfterControls.filter(r => !beforeCasAuditIDs.has(r.id) && r.subject === subject && r.createTime >= startedAt - 2000);
  const authCodeTokens = newCasEvents.filter(r => r.eventType === 'token_issued' && r.outcome === 'success' && JSON.parse(r.detailJson || '{}').grantType === 'authorization_code');
  h.check('CAS OAuth audit records exact authorization-code consumption, login and logout for original subject without code/token leakage',
    newCasEvents.some(r => r.eventType === 'login_success' && r.outcome === 'success') &&
    authCodeTokens.length >= 1 &&
    newCasEvents.some(r => r.eventType === 'logout_success' && r.outcome === 'success') &&
    newCasEvents.every(r => r.namespace === n && !(r.detailJson || '').includes(consumedCode) && !(r.detailJson || '').includes('access_token') && !(r.detailJson || '').includes('refresh_token')),
    { count: newCasEvents.length, eventTypes: newCasEvents.map(r => r.eventType) });
  const panelEvents = await awaitRows(
    () => h.directory(h.tenantAdmin, panelAccessRoute),
    rows => authCodeTokens.every(a => rows.some(p => !beforePanelAccessIDs.has(p.id) && p.id === a.id))
  );
  h.check('Panel access audit correlates with CAS OAuth audit on first-party authorization-code grant',
    authCodeTokens.every(a => panelEvents.some(p => p.id === a.id && p.eventType === a.eventType && p.subject === a.subject && p.namespace === n)));
  const tokenIssuedBeforeReplay = new Set(casAfterControls.filter(r => r.eventType === 'token_issued').map(r => r.id));
  const loginSuccessBeforeReplay = new Set(casAfterControls.filter(r => r.eventType === 'login_success').map(r => r.id));
  const runCallbackProbe = async (probeName, buildParams) => {
    const context = await h.browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
    const probeActor = { context, page: await context.newPage(), origin: original.origin, identity: structuredClone(original.identity) };
    try {
      const page = probeActor.page;
      let pendingState = '', loginStatus = 0;
      const captureLogin = res => {
        const u = new URL(res.url());
        if (u.origin === original.origin && u.pathname === '/api/v1/web/auth/login') {
          loginStatus = res.status();
          if (res.status() === 302 && res.headers().location) {
            pendingState = new URL(res.headers().location, original.origin).searchParams.get('state') || '';
          }
        }
      };
      page.on('response', captureLogin);
      await page.goto(original.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
      page.off('response', captureLogin);
      h.check('Callback probe ' + probeName + ' starts from a genuine pending BFF transaction', loginStatus === 302 && typeof pendingState === 'string' && pendingState.length > 0, { loginStatus });
      const targetURL = callbackTamperURL(original.origin, buildParams(pendingState));
      const response = await page.goto(targetURL, { waitUntil: 'networkidle' });
      const status = response ? response.status() : 0;
      const bodyText = await page.textContent('body').catch(() => '');
      const sessionCheck = await ownerRequest(probeActor, 'GET', '/api/v1/web/session/', undefined, h.observe);
      const unauthenticated = sessionCheck.status === 401 || sessionCheck.data?.error?.code === 11;
      const noLeak = !bodyText.includes(consumedCode) && !bodyText.includes('access_token') && !bodyText.includes('refresh_token') && !bodyText.includes('client_secret');
      h.check('Callback probe ' + probeName + ' refuses substitution/replay without establishing a session or leaking code',
        [400, 401, 403].includes(status) && unauthenticated && noLeak, { probeName, status, sessionStatus: sessionCheck.status });
      h.observe({ kind: 'first-party-callback-substitution-probe', probeName, status, unauthenticated, noLeak });
    } finally {
      await context.close();
    }
    const retained = await ownerRequest(original, 'GET', '/api/v1/web/session/', undefined, h.observe);
    h.check('Callback probe ' + probeName + ' leaves original ordinary session intact', h.good(retained) && retained.data.value.account.id === beforeSession.account.id && retained.data.value.homeNamespace === n);
    h.check('Callback probe ' + probeName + ' creates zero new BFF sessions', require('node:util').isDeepStrictEqual(await sessions(), beforeSessionIDs));
  };
  await runCallbackProbe('consumed-code-reuse', pendingState => ({ code: consumedCode, state: pendingState }));
  await runCallbackProbe('forged-code', pendingState => ({ code: 'forged-' + crypto.randomBytes(16).toString('base64url'), state: pendingState }));
  await runCallbackProbe('missing-code', pendingState => ({ state: pendingState }));
  await runCallbackProbe('tampered-callback-state', () => ({ code: consumedCode, state: crypto.randomBytes(16).toString('base64url') }));
  const bareContext = await h.browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
  const bareActor = { context: bareContext, page: await bareContext.newPage(), origin: original.origin, identity: structuredClone(original.identity) };
  try {
    const barePage = bareActor.page;
    const res = await barePage.goto(callbackTamperURL(original.origin, { code: consumedCode, state: crypto.randomBytes(16).toString('base64url') }), { waitUntil: 'networkidle' });
    const sessionCheck = await ownerRequest(bareActor, 'GET', '/api/v1/web/session/', undefined, h.observe);
    h.check('Callback without original pending browser cookie is rejected', !!res && [400, 401, 403].includes(res.status()) && (sessionCheck.status === 401 || sessionCheck.data?.error?.code === 11));
    for (const badTarget of ['https://other.test/', '//other.test/', '/\\other.test/']) {
      const loginRes = await barePage.goto(original.origin + '/api/v1/web/auth/login?return_to=' + encodeURIComponent(badTarget), { waitUntil: 'networkidle' });
      const cookies = await bareContext.cookies();
      h.check('Unsafe return_to ' + badTarget + ' is rejected cleanly before redirecting or setting cookies',
        !!loginRes && loginRes.status() === 400 && new URL(barePage.url()).pathname === '/api/v1/web/auth/login' && cookies.length === 0,
        { badTarget, status: loginRes?.status(), finalURL: barePage.url(), cookieCount: cookies.length });
    }
  } finally {
    await bareContext.close();
  }
  const casAfterReplay = await h.directory(h.tenantAdmin, casAuditRoute);
  const unexpectedGrants = casAfterReplay.filter(r => r.subject === subject && ((r.eventType === 'token_issued' && !tokenIssuedBeforeReplay.has(r.id)) || (r.eventType === 'login_success' && !loginSuccessBeforeReplay.has(r.id))));
  h.check('Code reuse and callback substitution probes generate zero new CAS token issuances or logins', unexpectedGrants.length === 0 && require('node:util').isDeepStrictEqual(await sessions(), beforeSessionIDs), unexpectedGrants);
}
const handlers = { 'F001-006': verifyCallbackSubstitutionsAndAudit };
handlers['F001-006'].actors = ['user', 'tenantAdmin']; handlers['F001-006'].transport = 'owner-api';
module.exports = { handlers, authorizationVariant, withOriginalAuthorizationEntry, runControls, callbackTamperURL };
