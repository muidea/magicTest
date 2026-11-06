#!/usr/bin/env node
// Runs only explicitly implemented standard branches; never infers coverage from a suite exit code.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const { handlers } = require('./standard_cases.cjs');
const { restoreSessionPolicy } = require('./session_cases.cjs');
const { publicGet } = require('./public_probe.cjs');
const { cleanupNegativeMutation } = require('./negative_mutations.cjs');
const root = path.resolve(__dirname, '..');
const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  if (!process.argv[i].startsWith('--') || !process.argv[i + 1]) throw Error('Expected --option value');
  options[process.argv[i].slice(2)] = process.argv[i + 1];
}
function sanitize(value, key = '') {
  if (/password|secret|token|csrf|authorization|cookie|code_verifier|code_challenge/i.test(key)) return '[REDACTED]';
  if (Array.isArray(value)) return value.map(x => sanitize(x));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, sanitize(v, k)]));
  if (typeof value === 'string') return value.replace(/\x1b\[[0-9;]*m/g, '').replace(/((?:set-cookie|cookie|authorization)\s*:\s*)[^\r\n]*/gi, '$1[REDACTED]').replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[REDACTED-JWT]').replace(/([?&](?:code|state|nonce|transaction|fileToken)=)[^&\s"']+/gi, '$1[REDACTED]');
  return value;
}
class Blocked extends Error {}
class ProductFailure extends Error {}
const selectCases = catalog => catalog.cases.filter(c => c.required && c.execution.some(p => p.suite === 'standard') && (!options.case || c.id === options.case) && (!options.cases || options.cases.split(',').includes(c.id)) && (!options.exclude || !options.exclude.split(',').includes(c.id)));
async function main() {
  if (options['dry-run'] === 'true') {
    const catalog = JSON.parse(fs.readFileSync(options.catalog || path.join(root, '../docs/acceptance/platform-catalog.json')));
    const selected = selectCases(catalog);
    console.log(JSON.stringify({ suite: 'standard', selected: selected.length, registeredHandlers: selected.filter(c => handlers[c.id]).map(c => c.id), missing: selected.filter(c => !handlers[c.id]).map(c => c.id), note: 'Registered handlers can still report partial verification; registration is not complete coverage.' }, null, 2));
    return;
  }
  for (const key of ['credentials', 'output', 'private-state', 'baseline-health']) if (!options[key]) throw Error('Missing --' + key);
  const out = path.resolve(options.output), priv = path.resolve(options['private-state']);
  if (priv === root || priv.startsWith(root + path.sep)) throw Error('Private state must stay outside repository');
  if (fs.existsSync(path.join(out, 'results.json'))) throw Error('Output already contains results. Use a new output directory to preserve prior execution evidence.');
  fs.mkdirSync(priv, { recursive: true, mode: 0o700 });
  fs.mkdirSync(out, { recursive: true });
  const attempt = new Date().toISOString().replaceAll(/[:.]/g, '-') + '-' + crypto.randomBytes(3).toString('hex');
  const attemptDir = path.join(out, 'attempts', attempt);
  fs.mkdirSync(attemptDir, { recursive: true });
  const credentials = JSON.parse(fs.readFileSync(options.credentials));
  const origin = credentials.origin;
  if (!origin || new URL(origin).protocol !== 'https:') throw Error('Credentials need an explicit HTTPS origin');
  const catalog = JSON.parse(fs.readFileSync(options.catalog || path.join(root, '../docs/acceptance/platform-catalog.json')));
  const baseline = JSON.parse(fs.readFileSync(options['baseline-health']));
  const selected = selectCases(catalog);
  selected.sort((a, b) => Number(a.id === 'F003-001') - Number(b.id === 'F003-001'));
  if (!selected.length) throw Error('No selected standard cases');
  const stateFile = path.join(priv, 'state.json');
  const state = fs.existsSync(stateFile) ? JSON.parse(fs.readFileSync(stateFile)) : { prefix: 'rg' + crypto.randomBytes(4).toString('hex'), password: 'Rg@' + crypto.randomBytes(16).toString('hex'), resources: [], fixtures: {} };
  if (state.resources.length && state.resources.every(r => r.phase === 'deleted')) throw Error('This fixture execution has already been cleaned. Preserve its state and use a separate private-state directory for a new execution.');
  const persist = () => fs.writeFileSync(stateFile, JSON.stringify(state), { mode: 0o600 });
  persist();
  const browser = await chromium.launch({ executablePath: options.chrome || chromium.executablePath(), headless: true, args: ['--no-sandbox', '--no-proxy-server', '--host-resolver-rules=MAP *.local.vpc 127.0.0.1'] });
  const sessions = [];
  let trace = [], currentCase = 'preparation';
  const write = (name, value) => { const file = path.join(attemptDir, name); fs.writeFileSync(file, JSON.stringify(sanitize(value), null, 2) + '\n', { flag: 'wx' }); return path.relative(out, file); };
  const fail = message => { throw new ProductFailure(message); };
  const check = (message, condition, details) => { trace.push({ kind: 'assertion', message, passed: !!condition, details: sanitize(details) }); if (!condition) fail(message); };
  const api = async (actor, method, route, body, extraHeaders = {}, directPublic = false) => {
    if (directPublic && (method !== 'GET' || !route.startsWith('/') || route.startsWith('//'))) throw Error('Direct public probe must be a same-origin GET');
    const endpoint = directPublic || route.startsWith('/api/') ? route : '/api/v1/web/proxy' + route;
    const result = directPublic ? await publicGet(actor, route) : await actor.page.evaluate(async ({ endpoint, method, body, extraHeaders }) => {
      const r = await fetch(endpoint, { method, headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(30000) });
      const text = await r.text(); let data;
      try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; }
      return { status: r.status, data };
    }, { endpoint, method, body, extraHeaders });
    trace.push(sanitize({ kind: 'request', actor: actor.identity, origin: actor.origin, method, route, ...(directPublic ? { transport: 'direct-public-read' } : {}), body, headers: extraHeaders, response: result }));
    return result;
  };
  const good = r => r.status === 200 && r.data.error == null && !('text' in r.data);
  const ok = async (actor, method, route, body) => { const r = await api(actor, method, route, body); check(method + ' ' + route + ' succeeds', good(r), { status: r.status, error: r.data.error }); return r.data; };
  const denied = (r, label) => {
    if (r.status === 401 || r.data?.error?.code === 11) throw new Blocked('AUTH-INVALID: cannot prove authorization denial with an unauthenticated session: ' + label);
    check(label, r.status === 403 || [5, 12, 22].includes(r.data?.error?.code), r);
  };
  const inaccessible = (r, label) => {
    if ([200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null) check(label + ' (owner conceals cross-namespace resource)', true, r);
    else denied(r, label);
  };
  const invalid = (r, label) => check(label, [400, 409, 422].includes(r.status) || (r.status === 200 && [3, 4, 7, 19, 21].includes(r.data?.error?.code)), r);
  async function login(account, password, namespace = credentials.namespace, newPassword, beforePasswordChange) {
    const actorOrigin = namespace === credentials.namespace ? origin : origin.replace(new URL(origin).hostname, namespace + '.' + new URL(origin).hostname.split('.').slice(1).join('.'));
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
    const page = await context.newPage();
    const actor = { context, page, origin: actorOrigin, identity: { account, namespace }, password };
    sessions.push(actor);
    page.on('pageerror', e => trace.push({ kind: 'browser-error', message: sanitize(e.message) }));
    let loginResponse = await page.goto(actorOrigin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle', timeout: 45000 });
    // Namespace ingress publication reaches Traefik through its watched files.
    // Retry only this same read-only login page, never the OAuth command.
    for (let retry = 0; retry < 5 && loginResponse?.status() === 404 && new URL(page.url()).pathname === '/login/cas'; retry++) {
      trace.push({ kind: 'ingress-readiness', status: 404, path: '/login/cas', retry: retry + 1 });
      await new Promise(resolve => setTimeout(resolve, 1000));
      loginResponse = await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
    }
    try {
      await page.locator('input[name=account]').fill(account);
    } catch (error) {
      const location = new URL(page.url());
      trace.push({ kind: 'login-entry-diagnostic', status: loginResponse?.status(), location: location.origin + location.pathname,
        error: location.searchParams.get('error'), text: sanitize((await page.locator('body').innerText()).slice(0, 1000)) });
      await screenshot(actor, 'login-entry-' + sessions.length);
      throw error;
    }
    await page.locator('input[name=password]').fill(password);
    await page.locator('form[action="/oauth/login"] button[type=submit]').click();
    await page.waitForFunction(() => document.querySelector('form[action="/oauth/password/change"]') || ['/panel', '/portal'].some(p => location.pathname.startsWith(p)) || new URL(location.href).searchParams.has('error'), {}, { timeout: 30000 });
    if (await page.locator('form[action="/oauth/password/change"]').count()) {
      if (!newPassword) throw new Blocked('First password change needs a dedicated account credential');
      if (beforePasswordChange) await beforePasswordChange(actor);
      await page.locator('#cas-new-password').fill(newPassword);
      await page.locator('#cas-new-password-confirm').fill(newPassword);
      await page.locator('form[action="/oauth/password/change"] button[type=submit]').click();
      actor.password = newPassword; actor.passwordChanged = true;
    }
    await page.waitForURL(u => ['/panel', '/portal'].some(p => u.pathname.startsWith(p)), { timeout: 45000 });
    await page.waitForLoadState('networkidle');
    const session = (await ok(actor, 'GET', '/api/v1/web/session/')).value;
    check('BFF session belongs to original account and namespace', session.account.account === account && session.homeNamespace === namespace, session);
    return actor;
  }
  let admin, user, tenantAdmin, otherTenantAdmin;
  async function authorizedAdmin() {
    const session = await api(admin, 'GET', '/api/v1/web/session/');
    if (session.status === 401 || session.data?.error?.code === 11) {
      trace.push({ kind: 'session-recovery', message: 'Reauthenticate the same original administrator; no business command replay.' });
      admin = await login(credentials.account, credentials.password); h.admin = admin;
    }
    return admin;
  }
  async function sessionAtOrigin(actor, targetOrigin) {
    // Preserve exact original session bytes; only address a different tenant
    // host. Never synthesize identity claims or obtain administrator credentials.
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
    const cookies = await actor.context.cookies(actor.origin);
    check('Cross-host test has an existing protected original session', cookies.some(c => c.httpOnly));
    await context.addCookies(cookies.map(cookie => ({ ...cookie, domain: new URL(targetOrigin).hostname })));
    const page = await context.newPage();
    const addressed = { context, page, origin: targetOrigin, identity: actor.identity };
    sessions.push(addressed);
    trace.push({ kind: 'session-host-boundary', originalIdentity: actor.identity, sourceOrigin: actor.origin, targetOrigin, credentialSource: 'unchanged original BFF cookies; values never archived' });
    await page.goto(targetOrigin + '/portal/', { waitUntil: 'networkidle', timeout: 30000 });
    return addressed;
  }
  async function anonymous(namespace) {
    const actorOrigin = origin.replace(new URL(origin).hostname, namespace + '.' + new URL(origin).hostname.split('.').slice(1).join('.'));
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
    const page = await context.newPage(), actor = { context, page, origin: actorOrigin, identity: { account: 'anonymous', namespace } };
    sessions.push(actor);
    await page.goto(actorOrigin + '/register/', { waitUntil: 'networkidle', timeout: 45000 });
    const session = await api(actor, 'GET', '/api/v1/web/session/');
    check('Public applicant has no authenticated BFF session', session.status === 401 || session.data?.error?.code === 11, session);
    return actor;
  }
  function namespaceDependent(namespaceID, collection, id, kind) {
    const parent = state.resources.find(r => r.kind === 'namespace' && r.id === namespaceID);
    if (!parent) throw new Blocked('Namespace teardown has no original tracked owner identity');
    parent.dependents ||= [];
    if (!parent.dependents.some(r => r.collection === collection && r.id === id)) parent.dependents.push({ collection, id, kind });
    persist();
  }
  async function rejectedLogin(account, password, namespace) {
    const actorOrigin = namespace === credentials.namespace ? origin : origin.replace(new URL(origin).hostname, namespace + '.' + new URL(origin).hostname.split('.').slice(1).join('.'));
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await context.newPage(), actor = { context, page, origin: actorOrigin, identity: { account, namespace } };
    sessions.push(actor);
    await page.goto(actorOrigin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle', timeout: 45000 });
    await page.locator('input[name=account]').fill(account);
    await page.locator('input[name=password]').fill(password);
    await page.locator('form[action="/oauth/login"] button[type=submit]').click();
    await page.waitForLoadState('networkidle');
    check('Rejected login stays on official login form', new URL(page.url()).pathname === '/login/cas' && await page.locator('input[name=password]').count() === 1);
    const error = page.locator('.ant-alert-error');
    check('Rejected login reports explicit credential/account error', await error.count() === 1 && await error.isVisible() && /密码|凭据|账号|account|password|credential/i.test(await error.innerText()));
    const session = await api(actor, 'GET', '/api/v1/web/session/');
    check('Rejected password establishes no BFF application session', session.status === 401 || session.data?.error?.code === 11, session);
    await screenshot(actor, 'rejected-login-' + sessions.length);
    return actor;
  }
  const owned = (collection, resource, kind, actor) => { state.resources.push({ collection, id: resource.id, kind, name: resource.name || resource.account || resource.key, ...(actor ? { actor } : {}), phase: 'created' }); persist(); return resource; };
  const create = async (collection, payload, kind) => owned(collection, (await ok(admin, 'POST', collection, payload)).value, kind);
  const createAs = async (actorName, collection, payload, kind) => {
    if (!h[actorName]) throw new Blocked('Missing fixture owner actor ' + actorName);
    return owned(collection, (await ok(h[actorName], 'POST', collection, payload)).value, kind, actorName);
  };
  const screenshot = async (actor, label) => { const name = currentCase + '-' + label + '.png'; const file = path.join(attemptDir, name); if (fs.existsSync(file)) throw Error('Screenshot evidence label reused: ' + name); await actor.page.screenshot({ path: file, fullPage: true, animations: 'disabled' }); const relative = path.relative(out, file); trace.push({ kind: 'screenshot', path: relative, sha256: 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') }); return relative; };
  const h = { fs, path, root, state, persist, browser, login, anonymous, namespaceDependent, rejectedLogin, sessionAtOrigin, api, publicGet: (actor, route) => api(actor, 'GET', route, undefined, {}, true), ok, check, good, denied, inaccessible, invalid, Blocked, create, createAs, owned, screenshot, credentials, authorizedAdmin,
    need(key) { if (!state.fixtures[key]) throw new Blocked('Missing current-run fixture: ' + key); return state.fixtures[key]; },
    async gone(collection, id) { const r = await api(admin, 'GET', collection + id); check('Owner confirms target absent', r.data?.error?.code === 2 && r.data.value == null, r); },
    async remove(collection, id) { await ok(admin, 'DELETE', collection + id); const resource = state.resources.find(x => x.collection === collection && x.id === id); if (resource) { resource.phase = 'deleted'; persist(); } },
    async partial(message) { throw new Blocked('Partial verification: ' + message); }
  };
  let prepError;
  try {
    admin = await login(credentials.account, credentials.password);
    h.admin = admin;
    if (options['reconcile-cleanup']) {
      const originalBytes = fs.readFileSync(options['reconcile-cleanup']);
      const original = JSON.parse(originalBytes), reconciled = [];
      for (const resource of original.resources) {
        if (resource.confirmed === true) { reconciled.push({ ...resource, proof: 'retained original successful cleanup receipt' }); continue; }
        let aggregate = resource;
        if (resource.kind !== 'namespace') {
          // CAS retirement's acknowledged account phase precedes namespace deletion.
          // A failed individual DELETE is retained; it is never relabeled successful.
          const match = resource.collection.match(/^\/cas\/namespaces\/([^/]+)\/accounts\/$/);
          const targetNamespace = match && ['account', 'unexpected-account'].includes(resource.kind) ? match[1]
            : resource.kind === 'namespace-branding' && resource.collection === '/panel/namespace-branding/' ? resource.name : null;
          if (!targetNamespace) throw new Blocked('Original resource has no reviewed aggregate retirement contract');
          aggregate = original.resources.find(r => r.kind === 'namespace' && r.name === targetNamespace);
          if (!aggregate) throw new Blocked('Original child has no exact original namespace identity');
        }
        const acknowledgement = original.trace.find(t => t.kind === 'request' && t.method === 'DELETE' && t.route === aggregate.collection + aggregate.id && good(t.response) && t.response.data.value?.id === aggregate.id && t.response.data.value?.name === aggregate.name);
        check('Original exact namespace DELETE was acknowledged before reconciliation', !!acknowledgement);
        const absent = await api(admin, 'GET', '/cas/namespaces/' + aggregate.id);
        check('Independent namespace owner confirms original identity absent', absent.data?.error?.code === 2 && absent.data.value == null, absent);
        const receipt = (await ok(admin, 'GET', '/panel/namespace-onboardings/' + aggregate.id + '/retirement')).value;
        check('Original aggregate retirement is complete under immutable request identity', receipt?.namespaceId === aggregate.id && receipt.name === aggregate.name && receipt.phase === 'complete' && receipt.requestId && receipt.expectedVersion > 0 && receipt.revision > 0, receipt);
        reconciled.push({ ...resource, confirmed: true, retirement: receipt, ...(aggregate !== resource ? { aggregateIdentity: { id: aggregate.id, name: aggregate.name }, individualDeleteConfirmed: false } : {}), proof: 'original successful namespace DELETE, owner durable aggregate receipt, independent namespace absence; child visibility unavailable after deletion' });
      }
      write('cleanup-reconciliation.json', { originalSha256: 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex'), environment: baseline.environment, allCurrentResourcesDisposed: reconciled.every(r => r.confirmed), resources: reconciled, trace });
      for (const actor of sessions) { await actor.context.close(); }
      await browser.close();
      return;
    }
    for (const namespace of [state.fixtures.tenantA, state.fixtures.tenantB].filter(Boolean)) {
      const current = (await ok(admin, 'GET', '/cas/namespaces/' + namespace.id)).value;
      if (current.status === 1) {
        trace.push({ kind: 'original-resource-recovery', id: current.id, message: 'Restore the original test namespace disabled by the interrupted standard case.' });
        await ok(admin, 'PUT', '/panel/namespace-onboardings/' + current.id, { expectedVersion: current.updateTime, description: current.description, scope: current.scope || [], status: 2, startTime: current.startTime, expireTime: current.expireTime });
        await authorizedAdmin();
      }
    }
    // All fixture identities are created in this run. Existing business objects are never adopted.
    for (const suffix of ['a', 'b']) {
      const key = 'tenant' + suffix.toUpperCase();
      if (!state.fixtures[key]) {
        state.fixtures[key] = await create('/panel/namespace-onboardings/', { name: state.prefix + suffix, description: 'Current standard regression fixture', scope: [], status: 2, startTime: Date.now() - 1000, expireTime: Date.now() + 86400000, initialAdminPassword: state.password }, 'namespace'); persist();
      }
    }
    const a = state.fixtures.tenantA, b = state.fixtures.tenantB;
    if (!state.fixtures.user) { state.fixtures.user = await create('/cas/namespaces/' + a.name + '/accounts/', { account: state.prefix + '-member', displayName: '回归普通成员', password: state.password, status: 2, roleTemplateKeys: ['portal-user'] }, 'account'); persist(); }
    user = await login(state.fixtures.user.account, state.fixtures.userPassword || state.password, a.name, state.password + 'U');
    state.fixtures.userPassword = user.password; persist(); h.user = user;
    for (const [namespace, key] of [[a, 'tenantAdmin'], [b, 'otherTenantAdmin']]) {
      const accounts = (await ok(admin, 'GET', '/cas/namespaces/' + namespace.name + '/accounts/?_pageSize=100')).values;
      const account = accounts.find(x => x.account.includes('admin'));
      if (!account) throw new Blocked('Namespace bootstrap has no public administrator account');
      const actor = await login(account.account, state.fixtures[key + 'Password'] || state.password, namespace.name, state.password + (key === 'tenantAdmin' ? 'A' : 'B'));
      state.fixtures[key + 'Password'] = actor.password; persist(); h[key] = actor;
    }
  } catch (e) {
    if (options['reconcile-cleanup']) {
      write('cleanup-reconciliation-failed.json', { error: sanitize(e.message), trace });
      for (const actor of sessions) await actor.context.close();
      await browser.close();
      throw e;
    }
    prepError = sanitize(e.message);
  }
  const preparationEvidence = write('preparation.json', { completed: !prepError, error: prepError, trace });
  const results = [];
  try {
    for (const entry of selected) {
      currentCase = entry.id; trace = [];
      let status = 'blocked', reason = 'TOOL-NO-COMPLETE-HANDLER: 尚无覆盖本常规分项全部步骤及预期的已复核执行器', defectId;
      const handler = handlers[entry.id];
      if (handler) {
        try {
          if (!h.admin) throw new Blocked('AUTH-PREPARATION: ' + prepError);
          for (const actor of handler.actors || []) if (!h[actor]) throw new Blocked('Missing original test actor ' + actor + ': ' + prepError);
          await authorizedAdmin();
          for (const name of handler.actors || []) {
            const session = await api(h[name], 'GET', '/api/v1/web/session/');
            if (!good(session) || session.data.value?.account?.account !== h[name].identity.account || session.data.value?.homeNamespace !== h[name].identity.namespace) throw new Blocked('AUTH-INVALID: original actor session is unavailable: ' + name);
          }
          await handler(h);
          check('Case has real assertions', trace.some(x => x.kind === 'assertion'));
          status = 'passed'; reason = undefined;
        } catch (e) {
          reason = sanitize(e.message);
          status = e instanceof ProductFailure ? 'failed' : 'blocked';
          if (status === 'failed') defectId = 'STD-' + entry.id + '-' + state.prefix;
        }
      }
      const proofPath = write(entry.id + '.json', { caseId: entry.id, suite: 'standard', scope: entry.execution.find(p => p.suite === 'standard'), status, reason, trace, preparationEvidence });
      const method = entry.methods.includes('browser') ? 'browser' : 'live';
      const evidence = [{ kind: method, path: proofPath, sha256: 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(path.join(out, proofPath))).digest('hex') }];
      results.push({ caseId: entry.id, suite: 'standard', status, method, role: 'original-admin-and-dedicated-test-subjects', namespace: state.fixtures.tenantA?.name || credentials.namespace, resource: state.prefix, observedAt: new Date().toISOString(), environmentFingerprint: baseline.environment.fingerprint, actual: status === 'passed' ? '本次执行全部已声明常规断言，操作及独立回读见逐例证据。' : reason, ...(reason ? { reason } : {}), ...(defectId ? { defectId } : {}), evidence });
      if (handler) console.log(JSON.stringify({ caseId: entry.id, status, reason }));
      fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ ...baseline, runId: state.prefix, results }, null, 2) + '\n');
    }
  } finally {
    trace = []; const cleanup = [];
    if (admin) for (const r of [...state.resources].reverse()) {
      if (r.phase === 'deleted') continue;
      try {
        await authorizedAdmin();
        if (['negative-branding', 'negative-create'].includes(r.kind)) {
          const proof = await cleanupNegativeMutation(h, r);
          r.phase = 'deleted'; persist();
          cleanup.push({ ...r, confirmed: true, ...proof });
          continue;
        }
        if (r.kind === 'session-policy-restore') {
          const restored = await restoreSessionPolicy(h, r);
          r.phase = 'deleted'; persist();
          cleanup.push({ ...r, confirmed: true, restored, proof: 'Guarded public restore and independent policy owner read; no byte-for-byte historical revision claim' });
          continue;
        }
        let cleanupActor = r.actor ? h[r.actor] : admin;
        if (!cleanupActor) throw new Blocked('Missing original cleanup actor ' + r.actor);
        if (r.actor) {
          let session = await api(cleanupActor, 'GET', '/api/v1/web/session/');
          for (let retry = 0; retry < 5 && session.status === 404; retry++) {
            await new Promise(resolve => setTimeout(resolve, 1000));
            session = await api(cleanupActor, 'GET', '/api/v1/web/session/');
          }
          if (session.status === 401 || session.data?.error?.code === 11) {
            cleanupActor = await login(cleanupActor.identity.account, cleanupActor.password, cleanupActor.identity.namespace);
            h[r.actor] = cleanupActor;
          }
        }
        await ok(cleanupActor, 'DELETE', r.collection + r.id);
        const readRoute = r.kind === 'namespace' ? '/cas/namespaces/' + r.id : r.collection + r.id;
        let after = await api(cleanupActor, 'GET', readRoute);
        if (after.status === 401 && !r.actor) {
          trace.push({ kind: 'environment-observation', message: 'Management session invalidated after namespace deletion; checking original resource using a new independent authorized session.' });
          admin = await login(credentials.account, credentials.password); h.admin = admin;
          after = await api(admin, 'GET', readRoute);
        }
        const absent = r.kind === 'namespace-branding' ? good(after) && after.data.value?.namespace === r.name && after.data.value.override == null : after.data?.error?.code === 2 && after.data.value == null;
        check('Cleanup has independent owner absence proof', absent, { collection: r.collection, id: r.id, response: after });
        let retirement;
        if (r.dependents?.length) {
          retirement = (await ok(admin, 'GET', '/panel/namespace-onboardings/' + r.id + '/retirement')).value;
          check('Owner confirms exact original namespace aggregate retirement completed', retirement?.namespaceId === r.id && retirement.name === r.name && retirement.phase === 'complete' && retirement.requestId && retirement.expectedVersion > 0 && retirement.revision > 0, retirement);
        }
        r.phase = 'deleted'; cleanup.push({ ...r, confirmed: true, ...(retirement ? { retirement, dependentProofMethod: 'owner aggregate retirement receipt and independent namespace absence; no post-deletion child visibility claim' } : {}) }); persist();
      } catch (e) { cleanup.push({ ...r, confirmed: false, error: sanitize(e.message) }); }
    }
    write('cleanup.json', { allCleaned: state.resources.every(r => r.phase === 'deleted'), resources: cleanup, trace });
    for (const actor of sessions) {
      try { await actor.page.goto(actor.origin + '/api/v1/web/auth/logout', { waitUntil: 'domcontentloaded', timeout: 10000 }); } catch {}
      await actor.context.close();
    }
    await browser.close();
  }
  if (!results.every(x => x.status === 'passed') || state.resources.some(r => r.phase !== 'deleted')) process.exitCode = 2;
}
main().catch(e => { console.error(sanitize({ error: e.name, message: e.message })); process.exitCode = 1; });
