#!/usr/bin/env node
// Runs only explicitly implemented standard branches; never infers coverage from a suite exit code.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { isDeepStrictEqual: sameIdentity } = require('node:util');
const { chromium } = require('./playwright.cjs');
const { handlers } = require('./standard_cases.cjs');
const { waitLoginForm, waitLoginError, observeLogin } = require('./login_readiness.cjs');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
const { restoreSessionPolicy } = require('./session_cases.cjs');
const { publicGet } = require('./public_probe.cjs');
const { cleanupNegativeMutation } = require('./negative_mutations.cjs');
const { readDirectory } = require('./directory.cjs');
const { createResource, deleteResource } = require('./resource_lifecycle.cjs');
const root = path.resolve(__dirname, '..');
const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  if (!process.argv[i].startsWith('--') || !process.argv[i + 1]) throw Error('Expected --option value');
  options[process.argv[i].slice(2)] = process.argv[i + 1];
}
const { sanitize } = require('./evidence_sanitizer.cjs');
class Blocked extends Error {}
class ProductFailure extends Error {}
const selectCases = catalog => catalog.cases.filter(c => c.required && c.execution.some(p => p.suite === 'standard') && (!options.case || c.id === options.case) && (!options.cases || options.cases.split(',').includes(c.id)) && (!options.exclude || !options.exclude.split(',').includes(c.id)));
async function main() {
  const recoveryFlags = ['reconcile-authoring-deletions', 'reconcile-rejected-definitions', 'reconcile-authoring-writes', 'reconcile-rejected-page-writes', 'reconcile-authoring-conflicts', 'reconcile-cas-identities', 'reconcile-business-creates', 'reconcile-member-scopes', 'reconcile-matrix-write-refusals', 'reconcile-endpoint-template-refusals', 'reconcile-source-lifecycles', 'reconcile-proxy-session-refusals'];
  for (const flag of recoveryFlags) if (options[flag] && options[flag] !== 'true') throw Error('Recovery operation requires literal true: ' + flag);
  if ([...recoveryFlags, 'reconcile-cleanup', 'resume-cleanup', 'resume-tracked-cleanup'].filter(flag => options[flag]).length > 1) throw Error('Select exactly one recovery operation');
  if (options['authoring-conflict-evidence'] && !options['reconcile-authoring-conflicts']) throw Error('Original conflict evidence requires conflict recovery mode');
  if (options['reconcile-authoring-conflicts'] && !options['authoring-conflict-evidence']) throw Error('Conflict recovery requires the original immutable case evidence');
  if (!!options['reconcile-rejected-page-writes'] !== !!options['author-write-refusal-evidence']) throw Error('Rejected page write recovery requires its original immutable case evidence and explicit recovery mode');
  if (!!options['reconcile-source-lifecycles'] !== !!options['source-lifecycle-evidence']) throw Error('Source lifecycle recovery requires exact original immutable case and cleanup evidence');
  if (options['reconcile-namespace-ingress'] && (!options['resume-tracked-cleanup'] || options['reconcile-namespace-ingress'] !== 'true')) throw Error('Ingress recovery requires explicit original tracked cleanup and literal true');
  if (options['file-deletion-proofs'] && !options['resume-tracked-cleanup']) throw Error('File deletion proofs require explicit original tracked cleanup recovery');
  if (options['namespace-creation-proofs'] && !options['resume-tracked-cleanup']) throw Error('Namespace proofs require explicit original tracked cleanup recovery');
  if (options['namespace-rollback-proofs'] && !options['resume-tracked-cleanup']) throw Error('Namespace rollback proofs require original tracked cleanup recovery');
  if ((options['dns-failure-proofs'] || options['reconcile-retired-credentials'] || options['reconcile-retired-creators']) && !options['resume-tracked-cleanup']) throw Error('Transport disposition requires explicit original tracked cleanup recovery');
  if (options['package-refusal-proofs'] && !options['resume-tracked-cleanup']) throw Error('Package refusal disposition requires explicit original tracked cleanup recovery');
  if (options['native-abort-proofs'] && !options['resume-tracked-cleanup']) throw Error('Native abort disposition requires original tracked cleanup recovery');
  if (options['reconcile-retired-creators'] && options['reconcile-retired-creators'] !== 'true') throw Error('Retired creator disposition requires literal true');
  if (options['reconcile-retired-credentials'] && options['reconcile-retired-credentials'] !== 'true') throw Error('Credential disposition requires literal true');
  if (options['dry-run'] === 'true') {
    const catalog = JSON.parse(fs.readFileSync(options.catalog || path.join(root, '../docs/acceptance/platform-catalog.json')));
    const selected = selectCases(catalog);
    console.log(JSON.stringify({ suite: 'standard', selected: selected.length, registeredHandlers: selected.filter(c => handlers[c.id]).map(c => c.id), missing: selected.filter(c => !handlers[c.id]).map(c => c.id), note: 'Registered handlers can still report partial verification; registration is not complete coverage.' }, null, 2));
    return;
  }
  for (const key of ['credentials', 'output', 'private-state', 'baseline-health']) if (!options[key]) throw Error('Missing --' + key);
  const out = path.resolve(options.output), priv = path.resolve(options['private-state']);
  if (priv === root || priv.startsWith(root + path.sep)) throw Error('Private state must stay outside repository');
  if (recoveryFlags.some(flag => options[flag]) && !fs.existsSync(path.join(priv, 'state.json'))) throw Error('Recovery requires an existing original private state; never create replacement recovery state');
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
  const persist = () => {
    const bytes = JSON.stringify(state), temporary = path.join(priv, '.state-' + crypto.randomBytes(12).toString('hex'));
    const fd = fs.openSync(temporary, 'wx', 0o600);
    try { fs.writeFileSync(fd, bytes); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, stateFile);
    const directory = fs.openSync(priv, 'r');
    try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
  };
  persist();
  const browser = await chromium.launch({ executablePath: options.chrome || chromium.executablePath(), headless: true, args: ['--no-sandbox', '--no-proxy-server', '--host-resolver-rules=MAP *.local.vpc 127.0.0.1'] });
  // Direct original-state recovery may reuse the private directory. The
  // orchestrator always creates a fresh one and rejects a preexisting marker.
  if (!fs.existsSync(path.join(priv, 'browser-started.json'))) fs.writeFileSync(path.join(priv, 'browser-started.json'), JSON.stringify({ launched: true }), { mode: 0o600, flag: 'wx' });
  const sessions = [], teardowns = [];
  let trace = [], currentCase = 'preparation';
  const write = (name, value) => { const file = path.join(attemptDir, name); fs.writeFileSync(file, JSON.stringify(sanitize(value), null, 2) + '\n', { flag: 'wx' }); return path.relative(out, file); };
  const fail = message => { throw new ProductFailure(message); };
  const check = (message, condition, details) => { trace.push({ kind: 'assertion', message, passed: !!condition, details: sanitize(details) }); if (!condition) fail(message); };
  // Installation lifecycle operations wait up to 30s for a Gateway route receipt
  // and then stage/launch Base. A 30s client abort would cancel that server wait
  // and turn a valid transition into "wait was canceled", so lifecycle POSTs use
  // a bounded longer budget while every other request keeps the 30s bound.
  const requestTimeout = (method, route) => {
    if (method === 'POST' && /^\/panel\/application\/(installations|deployment-requests)\//.test(route)) return 120000;
    // CAS management collection reads build per-item views over a growing
    // identity directory; keep a bounded larger budget than ordinary reads.
    if (method === 'GET' && /^\/cas\/namespaces\//.test(route)) return 90000;
    return 30000;
  };
  const api = async (actor, method, route, body, extraHeaders = {}, directPublic = false) => {
    if (directPublic && (method !== 'GET' || !route.startsWith('/') || route.startsWith('//'))) throw Error('Direct public probe must be a same-origin GET');
    const endpoint = directPublic || route.startsWith('/api/') ? route : '/api/v1/web/proxy' + route;
    const timeoutMs = requestTimeout(method, route);
    const result = directPublic ? await publicGet(actor, route) : await actor.page.evaluate(async ({ endpoint, method, body, extraHeaders, timeoutMs }) => {
      const r = await fetch(endpoint, { method, headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(timeoutMs) });
      const text = await r.text(); let data;
      try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; }
      return { status: r.status, data };
    }, { endpoint, method, body, extraHeaders, timeoutMs });
    trace.push(sanitize({ kind: 'request', actor: actor.identity, origin: actor.origin, method, route, ...(directPublic ? { transport: 'direct-public-read' } : {}), body, headers: extraHeaders, response: result }));
    return result;
  };
  const ownerApi = (actor, method, route, body) => require('./owner_transport.cjs').ownerRequest(actor, method, route, body, event => trace.push(sanitize(event)));
  const good = r => r.status === 200 && r.data.error == null && !('text' in r.data);
  // Protocol requests carry only the test's explicit machine credential. BFF
  // cookies must never turn a rejected Endpoint into an administrator request.
  const protocol = async (actor, method, route, form, headers = {}) => {
    if (!route.startsWith('/api/v1/cas/') || route.startsWith('//') || !['GET', 'POST'].includes(method) ||
      (method === 'POST' && !['/api/v1/cas/oauth/token', '/api/v1/cas/oauth/revoke', '/api/v1/cas/oauth/introspect'].includes(route))) throw new Blocked('Unsupported public CAS protocol probe');
    const result = await actor.page.evaluate(async ({ method, route, form, headers }) => {
      const response = await fetch(route, { method, credentials: 'omit', redirect: 'error', cache: 'no-store',
        headers: { ...(form ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}), ...headers },
        ...(form ? { body: new URLSearchParams(form).toString() } : {}), signal: AbortSignal.timeout(30000) });
      const text = await response.text(); let data;
      try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; }
      return { status: response.status, data };
    }, { method, route, form, headers });
    trace.push(sanitize({ kind: 'request', transport: 'direct-public-cas-no-cookies', actor: actor.identity, origin: actor.origin, method, route, form, headers, response: result }));
    return result;
  };
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
  const originalCasForms = (actor, action) => {
    state.originalCasForms ||= [];
    return withOriginalCasForms(actor, { journal: state.originalCasForms, persist, record: event => trace.push(sanitize(event)) }, action);
  };
  async function login(account, password, namespace = credentials.namespace, newPassword, beforePasswordChange) {
    const actorOrigin = namespace === credentials.namespace ? origin : origin.replace(new URL(origin).hostname, namespace + '.' + new URL(origin).hostname.split('.').slice(1).join('.'));
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
    const page = await context.newPage();
    const actor = { context, page, origin: actorOrigin, identity: { account, namespace }, password };
    sessions.push(actor);
    page.on('pageerror', e => trace.push({ kind: 'browser-error', message: sanitize(e.message) }));
    page.on('requestfailed', request => {
      const url = new URL(request.url());
      trace.push({ kind: 'browser-transport-failure', origin: url.origin, path: url.pathname, method: request.method(), error: request.failure()?.errorText });
    });
    return originalCasForms(actor, async () => {
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
    await page.waitForFunction(() => document.querySelector('form[action="/oauth/password/change"]') || ['/panel', '/portal'].some(p => location.pathname.startsWith(p)) || new URL(location.href).searchParams.has('error'), {}, { timeout: 60000 });
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
    const sessionResponse = await ownerApi(actor, 'GET', '/api/v1/web/session/');
    check('Original login session read succeeds', good(sessionResponse), sessionResponse);
    const session = sessionResponse.data.value;
    check('BFF session belongs to original account and namespace', session.account.account === account && session.homeNamespace === namespace, session);
    return actor;
    });
  }
  let admin, user, tenantAdmin, otherTenantAdmin;
  async function authorizedAdmin() {
    const session = await ownerApi(admin, 'GET', '/api/v1/web/session/');
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
    await page.goto(targetOrigin + '/portal/', { waitUntil: 'networkidle', timeout: 60000 });
    return addressed;
  }
  async function anonymous(namespace, prepareSessionCheck) {
    const actorOrigin = origin.replace(new URL(origin).hostname, namespace + '.' + new URL(origin).hostname.split('.').slice(1).join('.'));
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1366, height: 768 } });
    const page = await context.newPage(), actor = { context, page, origin: actorOrigin, identity: { account: 'anonymous', namespace } };
    sessions.push(actor);
    await page.goto(actorOrigin + '/register/', { waitUntil: 'networkidle', timeout: 45000 });
    if (prepareSessionCheck) await prepareSessionCheck(actor);
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
    return originalCasForms(actor, () => observeLogin(actor, {
      record: event => trace.push(sanitize(event)),
      capture: () => screenshot(actor, 'rejected-login-unresolved-' + sessions.length),
    }, async () => {
      await page.goto(actorOrigin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle', timeout: 45000 });
      const form = await waitLoginForm(page);
      await form.account.fill(account);
      await form.password.fill(password);
      // One original command only; wait for its navigation and actual rendered feedback.
      await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 60000 }), form.submit.click()]);
      await waitLoginForm(page);
      await waitLoginError(page);
      check('Rejected login stays on official login form', new URL(page.url()).pathname === '/login/cas');
      check('Rejected login reports explicit credential/account error', true);
      const session = await api(actor, 'GET', '/api/v1/web/session/');
      check('Rejected password establishes no BFF application session', session.status === 401 || session.data?.error?.code === 11, session);
      await screenshot(actor, 'rejected-login-' + sessions.length);
      return actor;
    }));
  }
  const owned = (collection, resource, kind, actor) => { state.resources.push({ collection, id: resource.id, kind, name: resource.name || resource.account || resource.key, ...(actor ? { actor } : {}), phase: 'created' }); persist(); return resource; };
  const create = async (collection, payload, kind) => createResource(h, admin, 'admin', collection, payload, kind);
  const createAs = async (actorName, collection, payload, kind) => {
    if (!h[actorName]) throw new Blocked('Missing fixture owner actor ' + actorName);
    return createResource(h, h[actorName], actorName, collection, payload, kind);
  };
  const screenshot = async (actor, label) => { const name = currentCase + '-' + label + '.png'; const file = path.join(attemptDir, name); if (fs.existsSync(file)) throw Error('Screenshot evidence label reused: ' + name); await actor.page.screenshot({ path: file, fullPage: true, animations: 'disabled' }); const relative = path.relative(out, file); trace.push({ kind: 'screenshot', path: relative, sha256: 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') }); return relative; };
  const h = { fileUploadMaxBytes: options['file-upload-max-bytes'] === undefined ? undefined : Number(options['file-upload-max-bytes']), teardowns, observe: event => trace.push(sanitize(event)), fs, path, root, state, persist, browser, login, anonymous, namespaceDependent, rejectedLogin, sessionAtOrigin, api, ownerApi, protocol, publicGet: (actor, route) => api(actor, 'GET', route, undefined, {}, true), ok, check, good, denied, inaccessible, invalid, Blocked, create, createAs, owned, screenshot, credentials, authorizedAdmin,
    deliveryFixtureConfig: options['delivery-fixture-config'],
    databaseFixtureMode: options['database-fixture-mode'],
    runtimeSnapshotConfig: options['runtime-snapshot-config'],
    directory(actor, route, options) { return readDirectory(h, actor, route, options); },
    need(key) { if (!state.fixtures[key]) throw new Blocked('Missing current-run fixture: ' + key); return state.fixtures[key]; },
    async gone(collection, id) { const r = await api(admin, 'GET', collection + id); check('Owner confirms target absent', r.data?.error?.code === 2 && r.data.value == null, r); },
    async remove(collection, id) {
      const resource = state.resources.find(x => x.collection === collection && x.id === id);
      if (!resource?.creation) throw new Blocked('Removal requires the original tracked creation');
      await deleteResource(h, resource.actor ? h[resource.actor] : admin, resource);
      resource.phase = 'deleted'; persist();
    },
    async partial(message) { throw new Blocked('Partial verification: ' + message); }
  };
  const ownerHarness = Object.create(h);
  ownerHarness.api = ownerApi;
  ownerHarness.ok = async (...args) => {
    const response = await ownerApi(...args);
    check(args[1] + ' ' + args[2] + ' succeeds', good(response), response);
    return response.data;
  };
  ownerHarness.directory = (actor, route, options) => readDirectory(ownerHarness, actor, route, options);
  let prepError;
  try {
    admin = await login(credentials.account, credentials.password);
    h.admin = admin;
    if (options['resume-tracked-cleanup']) {
      const originalBytes = fs.readFileSync(options['resume-tracked-cleanup']);
      const original = JSON.parse(originalBytes);
      const pending = require('./cleanup_recovery.cjs').bindOriginalCleanup(state, original);
      ownerHarness.originalCleanupEvidence = original;
      ownerHarness.originalCleanupBytes = originalBytes;
      ownerHarness.originalCleanupSha256 = 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex');
      const previousHealth = JSON.parse(fs.readFileSync(path.resolve(path.dirname(options['resume-tracked-cleanup']), '../../../health-before/results.json')));
      check('Recovery addresses the exact original deployment candidate', previousHealth.environment.fingerprint === baseline.environment.fingerprint);
      if (options['native-abort-proofs']) {
        const spec = JSON.parse(fs.readFileSync(options['native-abort-proofs']));
        const originalCleanup = fs.readFileSync(spec.cleanupFile), diagnosis = fs.readFileSync(spec.diagnosisFile);
        check('Native disposition inputs match immutable cleanup and exact original component diagnosis hashes',
          'sha256:' + crypto.createHash('sha256').update(originalCleanup).digest('hex') === spec.cleanupSha256 &&
          'sha256:' + crypto.createHash('sha256').update(diagnosis).digest('hex') === spec.diagnosisSha256);
        const evidence = JSON.parse(originalCleanup), components = JSON.parse(diagnosis).observations, proofs = [];
        for (const r of pending.filter(r => r.kind === 'native-runtime-request'))
          proofs.push(await require('./native_runtime_cases.cjs').confirmPackageDisposition(ownerHarness, r, evidence, spec.cleanupSha256, components.filter(v => v.requestId === r.id)));
        write('original-native-package-disposition.json', { proofs, trace });
      }
      const roleSourceProofs = [];
      for (const resource of pending.filter(r => r.kind === 'account')) {
        for (const command of resource.authorityCommands || []) {
          if (command.outcome !== 'unknown' || !command.before || !command.actorIdentity || command.route !== resource.collection + resource.id) continue;
          const proof = await require('./audit_cases.cjs').confirmRoleChange(ownerHarness, h.admin, resource, command);
          roleSourceProofs.push({ accountId: resource.id, proof });
        }
      }
      if (roleSourceProofs.length) write('original-role-source-confirmation.json', { originalCleanupSha256: 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex'), proofs: roleSourceProofs, trace });
      if (options['namespace-creation-proofs']) {
        const proofs = JSON.parse(fs.readFileSync(options['namespace-creation-proofs'])).entries;
        check('Namespace recovery contains distinct original owner proof references', Array.isArray(proofs) && new Set(proofs.map(p => p.name)).size === proofs.length);
        for (const resource of pending.filter(r => r.kind === 'namespace' && !r.id)) {
          const proof = proofs.find(p => p.name === resource.creation.intended.name);
          if (proof) await require('./cleanup_recovery.cjs').recoverNamespace(ownerHarness, resource, proof);
        }
      }
      if(options['namespace-rollback-proofs']) {
        const proofs=JSON.parse(fs.readFileSync(options['namespace-rollback-proofs'])).entries;
        check('Rollback proof entries preserve distinct original namespace identities',Array.isArray(proofs) && new Set(proofs.map(p=>p.name)).size===proofs.length);
        for(const resource of pending.filter(r=>r.kind==='namespace' && !r.id)) {
          const proof=proofs.find(p=>p.name===resource.creation.intended.name);
          if(proof)await require('./cleanup_recovery.cjs').confirmRolledBackNamespace(ownerHarness,resource,proof);
        }
      }
      if (options['reconcile-namespace-ingress']) for (const resource of pending.filter(r => r.kind === 'namespace' && r.id)) await require('./namespace_availability.cjs').reconcileIngress(ownerHarness, resource);
      for (const key of ['tenantAdmin', 'otherTenantAdmin', 'user']) {
        const namespace = state.fixtures[key === 'tenantAdmin' ? 'tenantA' : 'tenantB'];
        const actorNamespace = key === 'user' ? state.fixtures.tenantA : namespace;
        if (!actorNamespace) continue;
        const namedIdentities = pending.flatMap(r => r.kind === 'ordinary-file' && r.actorName === key ? [r.actorIdentity] : r.kind === 'feedback-ticket' ? [r.creator, r.manager].filter(spec => spec.actorName === key).map(spec => spec.identity) : []);
        const identities = [...namedIdentities, ...(key === 'user' ? [] : pending.flatMap(r => [r.ownerIdentity, r.actor === key ? r.creation?.actorIdentity : null, r.kind.startsWith('cas-probe-') ? r.actorIdentity : null]))].filter(identity => identity?.namespace === actorNamespace.name);
        if (!identities.length) continue;
        check('Original pending children have one exact tenant owner', identities.every(identity => sameIdentity(identity, identities[0])));
        h[key] = await login(identities[0].account, state.fixtures[key + 'Password'], actorNamespace.name);
      }
      await require('./cleanup_authentication.cjs').restoreScopedCreator(h,pending);
      if (options['file-deletion-proofs']) {
        const proofs = JSON.parse(fs.readFileSync(options['file-deletion-proofs']));
        check('File disposition binds the exact original cleanup bytes', proofs.originalCleanupDigest === 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex'));
        check('File disposition contains distinct exact original file references', Array.isArray(proofs.entries) && proofs.entries.length > 0 && new Set(proofs.entries.map(p => p.fileID)).size === proofs.entries.length);
        for (const proof of proofs.entries) {
          const matches = pending.filter(r => r.kind === 'ordinary-file' && r.id === proof.fileID);
          check('File disposition binds exactly one pending original file', matches.length === 1);
          await require('./file_cases.cjs').reconcileOwnerDeletedFile(ownerHarness, matches[0], proof);
        }
      }
      if (options['dns-failure-proofs']) {
        const entries = JSON.parse(fs.readFileSync(options['dns-failure-proofs'])).entries;
        check('DNS proofs bind distinct original journals', Array.isArray(entries) && new Set(entries.map(p => p.journalId)).size === entries.length);
        for (const proof of entries) {
          check('DNS proof references a case in the original immutable attempt', /^F\d{3}-\d{3}\.json$/.test(proof.caseFile));
          const bytes = fs.readFileSync(path.join(path.dirname(options['resume-tracked-cleanup']), proof.caseFile));
          check('Original DNS case bytes match the explicit proof digest', proof.sha256 === 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'));
          const matches = pending.filter(r => r.creation?.journalId === proof.journalId);
          check('DNS proof binds exactly one pending original intent', matches.length === 1);
          const disposition = await require('./cleanup_recovery.cjs').confirmUnsentTemplate(ownerHarness, matches[0], JSON.parse(bytes));
          disposition.caseSha256 = proof.sha256; persist();
        }
      }
      if (options['package-refusal-proofs']) {
        const proofs = JSON.parse(fs.readFileSync(options['package-refusal-proofs']));
        check('Package refusal proofs bind exact original cleanup bytes and distinct journals', proofs.originalCleanupDigest === 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex') &&
          Array.isArray(proofs.entries) && proofs.entries.length > 0 && new Set(proofs.entries.map(p => p.journalId)).size === proofs.entries.length);
        for (const proof of proofs.entries) {
          check('Package refusal references exact original case in the immutable cleanup attempt', /^F031-00[23]\.json$/.test(proof.caseFile));
          const bytes = fs.readFileSync(path.join(path.dirname(options['resume-tracked-cleanup']), proof.caseFile));
          check('Package refusal original case bytes match explicit proof digest', proof.sha256 === 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'));
          const matches = pending.filter(r => r.kind === 'package-preview-request' && r.creation?.journalId === proof.journalId);
          check('Package refusal proof binds one exact original request journal', matches.length === 1);
          await require('./delivery_cases.cjs').reconcilePreviewRefusal(ownerHarness, matches[0], JSON.parse(bytes), proof.sha256);
        }
      }
      if (options['reconcile-retired-creators']) for (const resource of pending.filter(r => r.actor && !h[r.actor])) {
        await require('./cleanup_recovery.cjs').cleanupRetiredCreator(ownerHarness, resource, original);
      }
      if (options['reconcile-retired-credentials']) for (const resource of pending.filter(r => r.kind === 'service-graph-credential' && r.outcome === 'unknown')) {
        await require('./cleanup_recovery.cjs').confirmRetiredCredential(ownerHarness, resource, original);
      }
      for (const resource of pending.filter(r => r.pendingDatabaseCommands?.some(command => !command.confirmed))) await require('./database_cases.cjs').reconcileDatabaseCommands(ownerHarness, resource);
      for (const fixture of state.externalDatabaseFixtures || []) {
        if (fixture.phase !== 'deleted') {
          check('External database fixture belongs to one exact original resource', original.resources.filter(r => r.kind === 'database-instance' && r.creation?.intended?.address === fixture.name + ':5432').length === 1);
          teardowns.push(require('./postgres_fixture.cjs').postgresCleanup(h, fixture));
        }
      }
      write('tracked-cleanup-resume.json', { originalSha256: 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex'), environment: baseline.environment,
        resources: pending.map(r => ({ kind: r.kind, id: r.id, name: r.name, collection: r.collection })), action: 'No case execution or replacement fixture; exact original owner cleanup gates remain in force', trace });
      selected.length = 0;
    } else if (options['resume-cleanup']) {
      const originalBytes = fs.readFileSync(options['resume-cleanup']);
      const original = JSON.parse(originalBytes);
      const pending = state.resources.filter(r => r.phase !== 'deleted');
      check('Cleanup resume has exactly the original rejected brand reset and its blocked parent', pending.length === 2 && pending.some(r => r.kind === 'namespace-branding') && pending.some(r => r.kind === 'namespace'));
      const resource = pending.find(r => r.kind === 'namespace-branding');
      const previous = original.resources.find(r => r.kind === resource.kind && r.collection === resource.collection && r.id === resource.id && r.name === resource.name && r.confirmed === false);
      check('Original immutable cleanup records this unresolved brand identity', !!previous);
      const requests = original.trace.filter(t => t.kind === 'request' && t.method === 'DELETE' && t.route === resource.collection && t.actor?.namespace === resource.name);
      const rejected = requests.at(-1);
      check('Only an explicitly rejected original admission permits cleanup resume', require('./branding_cleanup.cjs').rejectedAdmission(rejected?.response));
      check('Parent remains the original acknowledged creation', pending.find(r => r.kind === 'namespace').id === state.fixtures.tenantA.id && resource.name === state.fixtures.tenantA.name && resource.actor === 'tenantAdmin');
      h.tenantAdmin = await login(rejected.actor.account, state.fixtures.tenantAdminPassword, rejected.actor.namespace);
      check('Recovered cleanup retains exact original actor and origin', JSON.stringify(h.tenantAdmin.identity) === JSON.stringify(rejected.actor) && h.tenantAdmin.origin === rejected.origin);
      write('cleanup-resume.json', { originalSha256: 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex'), originalRejection: rejected, environment: baseline.environment, trace });
      selected.length = 0; // No replacement fixture or case execution.
    } else if (options['reconcile-cleanup']) {
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
    } else if (options['reconcile-proxy-session-refusals'] === 'true') {
      const pending = state.resources.filter(r => r.phase === 'intent' && r.creation?.outcome === 'unconfirmed' && r.creation.response?.status === 503);
      if (!pending.length) throw new Blocked('No original acknowledged session refusals to reconcile');
      const proofs = [];
      for (const resource of pending) proofs.push(await require('./cleanup_recovery.cjs').confirmProxySessionRefusal(ownerHarness, resource));
      write('proxy-session-refusal-reconciliation.json', { environment: baseline.environment, proofs, trace });
      selected.length = 0;
    } else if (options['reconcile-endpoint-template-refusals'] === 'true') {
      const pending = state.resources.filter(r => r.phase !== 'deleted' && r.endpointAuthorityCommands?.some(c => c.outcome === 'unknown'));
      if (!pending.length) throw new Blocked('No original pending Endpoint template refusal');
      const proofs = [];
      for (const resource of pending) proofs.push(await require('./service_contract_cases.cjs').reconcileEndpointTemplateRefusal(ownerHarness, resource));
      write('endpoint-template-refusal-reconciliation.json', { environment: baseline.environment, proofs, trace });
      selected.length = 0;
    } else if (options['reconcile-matrix-write-refusals'] === 'true') {
      const pending = require('./cleanup_recovery.cjs').pendingBusinessReconciliation(state.resources, 'matrix-write-refusal');
      if (!pending.length) throw new Blocked('No original unresolved matrix write refusal');
      const proofs = [];
      for (const resource of pending) proofs.push(await require('./application_authority_cases.cjs').reconcileMatrixWriteRefusal(ownerHarness, resource));
      write('matrix-write-refusal-reconciliation.json', { environment: baseline.environment, proofs, trace });
      selected.length = 0;
    } else if (options['reconcile-member-scopes'] === 'true') {
      const pending = state.resources.filter(r => r.kind === 'account' && r.phase !== 'deleted' && r.authorityCommands?.some(c => c.outcome === 'unknown'));
      if (!pending.length) throw new Blocked('No original unresolved member scope assignment');
      const proofs = [];
      for (const resource of pending) proofs.push(await require('./application_authority_cases.cjs').reconcile(ownerHarness, resource));
      write('member-scope-reconciliation.json', { environment: baseline.environment, proofs, trace });
      selected.length = 0;
    } else if (options['reconcile-business-creates'] === 'true') {
      const pending = require('./cleanup_recovery.cjs').pendingBusinessReconciliation(state.resources, 'business-create');
      if (!pending.length) throw new Blocked('No original unresolved business records to reconcile');
      const proofs = [];
      for (const resource of pending) proofs.push(await require('./business_cases.cjs').reconcile(ownerHarness, resource));
      write('business-create-reconciliation.json', { environment: baseline.environment, proofs, trace });
      selected.length = 0;
    } else if (options['reconcile-cas-identities'] === 'true') {
      const original = state.resources.find(r => r.actor === 'tenantAdmin' && r.phase !== 'deleted');
      const identity = original?.actorIdentity || original?.creation?.actorIdentity;
      if (!identity) throw new Blocked('No original CAS actor available for read-only reconciliation');
      h.tenantAdmin = await login(identity.account, state.fixtures.tenantAdminPassword, identity.namespace);
      const proof = await require('./cas_identity_cases.cjs').reconcile(h);
      write('cas-identity-reconciliation.json', { environment: baseline.environment, proof, trace });
      selected.length = 0;
    } else if (options['reconcile-authoring-conflicts'] === 'true') {
      const pending = state.resources.filter(r => r.phase !== 'deleted' && r.pendingAuthoringSave?.confirmed === false);
      if (pending.length !== 1) throw new Blocked('Conflict recovery requires exactly one original unresolved command');
      const bytes = fs.readFileSync(options['authoring-conflict-evidence']);
      const proof = await require('./authoring_conflict_recovery.cjs').reconcileConflict(ownerHarness, pending[0], JSON.parse(bytes), 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'));
      write('authoring-conflict-reconciliation.json', { environment: baseline.environment, proof, trace });
      selected.length = 0;
    } else if (options['reconcile-rejected-page-writes'] === 'true') {
      const pending = state.resources.filter(r => r.phase !== 'deleted' && r.pendingAuthoringSave?.confirmed === false);
      if (pending.length !== 1) throw new Blocked('Rejected page recovery requires one original pending save');
      const bytes = fs.readFileSync(options['author-write-refusal-evidence']);
      const proof = await require('./page_author_cases.cjs').reconcileRejectedPageWrite(ownerHarness, pending[0], JSON.parse(bytes), 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'));
      write('rejected-page-write-reconciliation.json', { environment: baseline.environment, proof, trace });
      selected.length = 0;
    } else if (options['reconcile-source-lifecycles'] === 'true') {
      const spec = JSON.parse(fs.readFileSync(options['source-lifecycle-evidence'])), originalBytes = fs.readFileSync(spec.originalCleanup);
      check('Source recovery binds exact original cleanup bytes', spec.cleanupSha256 === 'sha256:' + crypto.createHash('sha256').update(originalBytes).digest('hex'));
      const pending = require('./cleanup_recovery.cjs').bindOriginalCleanup(state, JSON.parse(originalBytes)).filter(r => r.kind === 'source-effect-scenario');
      check('Source recovery explicitly covers distinct original pending installations', pending.length > 0 && Array.isArray(spec.entries) && spec.entries.length === pending.length &&
        new Set(spec.entries.map(v => v.installationId)).size === pending.length);
      const proofs = [];
      for (const resource of pending) {
        const ref = spec.entries.find(v => v.installationId === resource.identity.installationId);
        check('Source recovery references an original case file in its immutable attempt', !!ref && /^F(?:033-001|071-005)\.json$/.test(ref.caseFile));
        const bytes = fs.readFileSync(path.join(path.dirname(spec.originalCleanup), ref.caseFile));
        check('Original source case bytes match the exact proof digest', ref.sha256 === 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'));
        proofs.push(await require('./source_effect_cases.cjs').reconcileLifecycle(ownerHarness, resource, JSON.parse(bytes), ref.sha256));
      }
      write('source-lifecycle-reconciliation.json', { environment: baseline.environment, originalCleanupSha256: spec.cleanupSha256, proofs, trace });
      selected.length = 0;
    } else if (options['reconcile-authoring-writes'] === 'true') {
      const proof = await require('./page_author_cases.cjs').reconcileAcknowledgedAuthorWrites(h);
      write('authoring-write-reconciliation.json', { environment: baseline.environment, proof, trace });
      selected.length = 0;
    } else if (options['reconcile-rejected-definitions'] === 'true') {
      const proof = await require('./page_author_cases.cjs').reconcileRejectedDefinitionCreations(h);
      write('rejected-definition-reconciliation.json', { environment: baseline.environment, proof, trace });
      selected.length = 0; // Read-only original-intent reconciliation, never create new fixtures.
    } else if (options['reconcile-authoring-deletions'] === 'true') {
      const pending = state.resources.filter(r => r.phase !== 'deleted' && r.pendingAuthoringSave?.confirmed === false);
      if (!pending.length) throw new Blocked('No original unresolved author deletion to reconcile');
      const { reconcileAuthorDeletion } = require('./definition_browser_cases.cjs');
      for (const resource of pending) await reconcileAuthorDeletion(h, resource);
      write('authoring-deletion-reconciliation.json', { environment: baseline.environment, trace, resources: pending.map(r => ({ id: r.id, ...r.pendingAuthoringSave.reconciliation })) });
      selected.length = 0; // Recovery never runs cases or creates replacement fixtures.
    } else if (require('./delivery_fixture.cjs').dedicatedDeliveryOnly(selected, handlers, h.deliveryFixtureConfig, state)) {
      await require('./delivery_cases.cjs').fixture(ownerHarness);
      check('Explicit isolated delivery-only executors validate their original published owner fixture without unrelated generic tenants', true, { cases: selected.map(c => c.id) });
    } else {
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
        const accounts = await readDirectory(h, admin, '/cas/namespaces/' + namespace.name + '/accounts/');
        const account = accounts.find(x => x.account.includes('admin'));
        if (!account) throw new Blocked('Namespace bootstrap has no public administrator account');
        const actor = await login(account.account, state.fixtures[key + 'Password'] || state.password, namespace.name, state.password + (key === 'tenantAdmin' ? 'A' : 'B'));
        state.fixtures[key + 'Password'] = actor.password; persist(); h[key] = actor;
      }
    }
  } catch (e) {
    if (options['resume-tracked-cleanup'] || options['resume-cleanup'] || options['reconcile-cleanup'] || recoveryFlags.some(flag => options[flag])) {
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
            await require('./session_lifecycle.cjs').readyActor(h,name,handler.transport === 'owner-api' ? ownerApi : api);
          }
          await handler(handler.transport === 'owner-api' ? ownerHarness : h);
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
      if (handler) {
        const parked = await require('./session_lifecycle.cjs').parkSessions(sessions);
        if (parked.length) write(entry.id + '-browser-lifecycle.json', { caseId: entry.id, results: parked });
      }
    }
  } finally {
    trace = []; const cleanup = [];
    if (admin) for (const r of [...state.resources].reverse()) {
      if (r.phase === 'deleted') continue;
      try {
        if (r.kind === 'tls-material-restore') {
          const proof = await require('./tls_delivery_cases.cjs').restoreMaterial(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        await authorizedAdmin();
        await require('./cleanup_authentication.cjs').renewCleanupOwners(h, r, ownerApi);
        if (r.kind === 'deployment-material-probe') {
          const proof = require('./deployment_material_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ kind: r.kind, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'native-lifecycle-probe') {
          const proof = await require('./native_lifecycle_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ kind: r.kind, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'generated-service-graph') {
          const proof = await require('./generated_service_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ kind: r.kind, confirmed: true, ...proof }); continue;
        }
        require('./resource_lifecycle.cjs').guardFixtureAccountCleanup(h, r);
        require('./business_action_cases.cjs').guardCleanup(h, r);
        require('./scenario_commands.cjs').guard(h, r);
        require('./native_admission.cjs').guardDefinitionCleanup(h, r);
        require('./native_package_cases.cjs').guardDefinitionCleanup(h, r);
        require('./script_library_cases.cjs').guard(h, r);
        if (r.capabilityAdmission?.some(c => c.outcome === 'unknown')) throw new Blocked('Original capability declaration command unresolved; preserve its exact definition');
        if (r.modelDelivery) {
          const proof = await require('./model_delivery.cjs').retained(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.scriptPublication?.outcome === 'confirmed') {
          const proof = await require('./script_library_cases.cjs').retained(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'deployment-boundary') {
          const proof = require('./deployment_cases.cjs').cleanupBoundary(h, r);
          cleanup.push({ kind: r.kind, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'branding-profile-restore') {
          const proof = await require('./branding_profile.cjs').restore(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'log-retention-restore') {
          const proof = await require('./retention_cases.cjs').restore(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'ordinary-file') {
          if (r.phase === 'deleted') continue;
          const proof = await require('./file_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'delivery-fixture-restore') {
          const proof = await require('./delivery_cases.cjs').restore(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'package-preview-request') {
          const proof = await require('./delivery_cases.cjs').cleanupPreviewRequest(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'requester-preview-request') {
          const proof = await require('./installation_request_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'bound-reference-probe') {
          const proof = await require('./bound_reference_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'runtime-policy-probe') {
          const proof = await require('./runtime_control_cases.cjs').cleanupPolicy(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'native-runtime-request') {
          const proof = await require('./native_runtime_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...proof, ...r, confirmed: true }); continue;
        }
        if (r.kind === 'deployment-review-request') {
          const proof = await require('./deployment_review_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (['native-provider-probe', 'native-package-probe'].includes(r.kind)) {
          const proof = await require('./native_provider_access_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'deployment-review-guard') {
          const proof = await require('./deployment_review_cases.cjs').reconcileGuard(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'package-integrity-probe') throw new Blocked('Original integrity upload/import/request lacks complete owner refusal and disposition; retain exact intent without replay');
        if (r.kind === 'definition-metadata-restore') {
          const proof = await require('./definition_metadata_cases.cjs').restore(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'instance-name-restore') {
          const proof = await require('./instance_cases.cjs').restore(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'portal-identity-session') throw new Blocked('Original same-context identity verification remains incomplete; preserve login journal without replay');
        if (r.kind === 'source-effect-scenario') throw new Blocked('Original source/effect scenario disposition is incomplete; retain exact source/task/target and installation, no guessed teardown or source replay');
        if (r.kind === 'business-record') {
          const proof = await require('./business_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'feedback-ticket') {
          const proof = await require('./feedback_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'lifecycle-admission-probe') {
          const proof = await require('./lifecycle_admission_cases.cjs').cleanup(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'native-admission-probe') {
          const proof = await require('./native_admission.cjs').cleanup(ownerHarness, r);
          r.phase = 'deleted'; persist(); cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.kind === 'member-access-retirement') {
          const proof = await require('./application_authority_cases.cjs').retireAccess(ownerHarness, r);
          cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (r.authorityCommands?.some(command => command.outcome === 'unknown')) throw new Blocked('Original authority assignment command remains unresolved; retain exact original account and command journal');
        if (r.kind === 'role-template' && state.resources.some(child => child.phase !== 'deleted' && child.endpointAuthorityCommands?.some(c => c.outcome === 'unknown' && (c.body.roleTemplateKeys.includes(r.creation?.intended?.key) || c.before?.templateRefs?.some(t => t.key === r.creation?.intended?.key))))) throw new Blocked('Original Endpoint template replacement unresolved; retain exact bound template');
        if (r.availability?.commands.some(command => command.outcome === 'unknown')) throw new Blocked('Original namespace availability command remains unresolved; preserve owner receipt and exact command journal');
        if (r.oauthPolicyCommand && r.oauthPolicyCommand.outcome !== 'confirmed') throw new Blocked('Original OAuth policy command remains unresolved; preserve namespace for owner confirmation');
        if (r.oauthPolicyCommands?.some(command => command.outcome !== 'confirmed')) throw new Blocked('Original access policy command remains unresolved; preserve namespace for owner confirmation');
        if (r.pendingAuthoringSave && r.pendingAuthoringSave.confirmed !== true) throw new Blocked('Original author save remains unresolved; retain its definition and exact command journal');
        if (r.metadataJournal?.commands.some(c => c.outcome === 'unknown')) throw new Blocked('Original definition metadata command remains unresolved; retain exact original identity');
        if (r.definitionRejections?.some(c => c.outcome === 'unknown')) throw new Blocked('Original negative definition creation remains unresolved; retain exact source and command journal');
        require('./authority_retry_cases.cjs').protectCleanup(ownerHarness, r);
        if (r.pendingServiceCommands?.some(command => !command.confirmed)) throw new Blocked('Original service command remains unresolved; retain its exact owner resource and command journal');
        if (r.pendingDatabaseCommands?.some(command => !command.confirmed)) throw new Blocked('Original database command remains unresolved; retain its exact physical target and owner journal');
        if (r.kind === 'database-instance' && require('./storage_admission_cases.cjs').pendingRequests(state, r.id)) throw new Blocked('Original storage approval request remains unresolved; retain its selected database instance and placement');
        if (r.kind === 'service' && state.resources.some(publication => publication.kind === 'publication' && publication.creation?.intended?.service?.id === r.id && publication.pendingServiceCommands?.some(command => !command.confirmed))) throw new Blocked('Original publication command remains unresolved; retain its exact service owner');
        if (r.kind.startsWith('service-graph-')) {
          const graph = require('./service_graph.cjs');
          const proof = await (r.kind === 'service-graph-subscription' ? graph.cleanupSubscription(ownerHarness, r) : graph.cleanupCredential(ownerHarness, r));
          r.phase = 'deleted'; persist(); cleanup.push({ ...r, confirmed: true, ...proof }); continue;
        }
        if (['service', 'publication'].includes(r.kind) && state.resources.some(child => child.kind.startsWith('service-graph-') && child.phase !== 'deleted' && child.serviceId === (r.kind === 'service' ? r.id : r.creation?.intended?.service?.id))) throw new Blocked('Original service graph has unresolved subscription or credential commands');
        if (r.kind === 'service-identity-attempt') throw new Blocked('Service identity attempt is unresolved; retain original response and owner evidence without guessed cleanup');
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
        if (r.kind.startsWith('cas-probe-')) {
          const proof = await require('./cas_identity_cases.cjs').cleanup(ownerHarness, r);
          r.phase = 'deleted'; persist();
          cleanup.push({ ...r, confirmed: true, ...proof });
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
        if (r.creation) {
          if (r.kind === 'service' && state.resources.some(attempt => attempt.kind === 'service-identity-attempt' && attempt.phase !== 'deleted' && attempt.original?.some(value => value.id === r.id))) throw new Blocked('Service identity attempt is unresolved; retain its original fixture for owner reconciliation');
          if (r.kind === 'namespace' && state.resources.some(child => child !== r && child.phase !== 'deleted' && (child.collection?.startsWith('/cas/namespaces/' + r.name + '/') || child.creation?.actorIdentity?.namespace === r.name || child.actorIdentity?.namespace === r.name || child.name === r.name || child.storageAdmissionNamespace === r.name || ['deployment-review-request', 'native-provider-probe'].includes(child.kind) && child.commands?.some(c => c.actorIdentity?.namespace === r.name)))) throw new Blocked('Original namespace has unresolved tracked children; retain their owner evidence before aggregate deletion');
          const proof = await deleteResource(h, cleanupActor, r);
          let retirement;
          if (r.kind === 'namespace') {
            retirement = (await ownerHarness.ok(admin, 'GET', '/panel/namespace-onboardings/' + r.id + '/retirement')).value;
            check('Original namespace owner confirms aggregate retirement', retirement?.namespaceId === r.id && retirement.name === r.name && retirement.phase === 'complete' && retirement.requestId && retirement.expectedVersion > 0 && retirement.revision > 0, retirement);
          }
          r.phase = 'deleted'; persist();
          cleanup.push({ ...r, confirmed: true, ...proof, ...(retirement ? { retirement } : {}) });
          continue;
        }
        if (r.kind === 'namespace-branding') {
          const proof = await require('./branding_cleanup.cjs').resetBranding(h, cleanupActor, r);
          r.phase = 'deleted'; persist(); cleanup.push({ ...r, confirmed: true, ...proof }); continue;
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
    for (const teardown of teardowns.reverse()) await teardown();
    if (state.externalDatabaseFixtures?.length) write('external-fixtures.json', { allDisposed: state.externalDatabaseFixtures.every(r => r.phase === 'deleted'), fixtures: state.externalDatabaseFixtures, trace });
  }
  if (!results.every(x => x.status === 'passed') || state.resources.some(r => r.phase !== 'deleted')) process.exitCode = 2;
}
main().catch(e => { console.error(sanitize({ error: e.name, message: e.message })); process.exitCode = 1; });
