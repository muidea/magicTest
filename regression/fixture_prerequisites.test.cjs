const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('namespace observation budget is limited to exact public creation/replacement commands without retries', async t => {
  const { request } = require('./playwright.cjs'), { ownerRequest } = require('./owner_transport.cjs');
  const sent = [];
  t.mock.method(request, 'newContext', async () => ({
    async fetch(url, options) { sent.push({ url, options }); return { status: () => 200, headers: () => ({}), async text() { return '{"error":null,"value":{}}'; } }; },
    async storageState() { return { cookies: [] }; }, async dispose() {}
  }));
  const actor = { origin: 'https://panel.local.vpc', identity: { account: 'original', namespace: 'panel' }, context: { async cookies() { return []; } } };
  for (const [method, route, expected] of [
    ['POST', '/panel/namespace-onboardings/', 120000], ['PUT', '/panel/namespace-onboardings/7', 120000],
    ['GET', '/panel/namespace-onboardings/7', 30000], ['DELETE', '/panel/namespace-onboardings/7', 30000],
    ['POST', '/panel/namespace-onboardings/7', 30000], ['PUT', '/panel/namespace-onboardings/7/ingress', 30000],
    ['PUT', '/panel/namespace-onboardings/7?other=1', 30000], ['PUT', '/panel/namespace-onboardings/0', 30000],
    ['PUT', '/cas/namespaces/7', 30000], ['PUT', '/panel/application/installations/7', 30000]
  ]) {
    const count = sent.length; await ownerRequest(actor, method, route, {});
    assert.equal(sent.length, count + 1); assert.equal(sent.at(-1).options.timeout, expected);
    assert.equal(sent.at(-1).options.maxRetries, 0); assert.equal(sent.at(-1).options.maxRedirects, 0);
  }
});

test('synchronous namespace creation and replacement observe real responses beyond thirty seconds once and never resend lost commands', { timeout: 60000 }, async () => {
  const http = require('node:http'), { ownerRequest } = require('./owner_transport.cjs');
  const seen = [], timers = new Set();
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks)); seen.push({ method: req.method, route: req.url, body });
    if (body.name.startsWith('lost')) { req.socket.destroy(); return; }
    const timer = setTimeout(() => {
      timers.delete(timer); res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ error: null, value: { id: 7, name: body.name } }));
    }, 31000); timers.add(timer);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const actor = { origin: 'http://127.0.0.1:' + server.address().port,
      identity: { account: 'original', namespace: 'panel' }, context: { async cookies() { return []; } } };
    const commands = [['POST', '/panel/namespace-onboardings/'], ['PUT', '/panel/namespace-onboardings/7']];
    const responses = await Promise.all(commands.map(([method, route]) => ownerRequest(actor, method, route, { name: 'original-' + method })));
    responses.forEach((result, index) => { assert.equal(result.status, 200); assert.deepEqual(result.data.value, { id: 7, name: 'original-' + commands[index][0] }); });
    for (const [method, route] of commands) await assert.rejects(ownerRequest(actor, method, route, { name: 'lost-' + method }));
    const expected = commands.flatMap(([method, route]) => ['original-', 'lost-'].map(prefix => ({ method, route: '/api/v1/web/proxy' + route, body: { name: prefix + method } })));
    const sort = rows => rows.sort((a, b) => (a.method + a.body.name).localeCompare(b.method + b.body.name));
    assert.deepEqual(sort(seen), sort(expected));
  } finally {
    for (const timer of timers) clearTimeout(timer);
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
});

test('bootstrap recovery refuses every original command or password-change intent and only accepts the untouched original stage', () => {
  const { resumeBootstrapAllowed } = require('./delivery_fixture.cjs');
  const original = { stage: 'bootstrap-in-progress', originalCasForms: [], commands: [], resources: [] };
  assert.equal(resumeBootstrapAllowed(original), true);
  for (const mutate of [s => s.stage = 'bootstrapped', s => s.originalCasForms.push({ phase: 'unknown' }),
    s => s.originalCasForms.push({ phase: 'browser-delivered' }), s => s.commands.push({ outcome: 'unknown' }),
    s => s.resources.push({ phase: 'intent' }), s => s.passwordChange = { outcome: 'unknown' }, s => delete s.originalCasForms]) {
    const state = structuredClone(original); mutate(state); assert.equal(resumeBootstrapAllowed(state), false);
  }
});

test('hyphenated scenario names produce owner-valid model package identifiers without changing application names', async () => {
  const { authoring } = require('./authoring_cases.cjs');
  const h = { fs, path, root: path.resolve(__dirname, '..'), state: { prefix: 'rg123abc' },
    async create(route, body, kind) {
      assert.equal(route, '/panel/application/definitions/'); assert.equal(kind, 'definition');
      assert.match(body.pkgPrefix, /^[A-Za-z][A-Za-z0-9]*$/);
      return body;
    } };
  for (const suffix of ['authorization-capacity', 'another-two-part-fixture', 'ordinary']) {
    const body = await authoring.definition(h, suffix);
    assert.equal(body.name, 'rg123abc-' + suffix);
    assert.match(body.uuid, /^[a-f0-9]{32}$/);
  }
});

test('session revision passes the inherited original owner harness to OAuth preparation with only its user replaced', async () => {
  const oauth = require('./oauth_refresh_cases.cjs'), { handlers } = require('./session_revision_cases.cjs');
  const owner = { identity: { namespace: 'original-tenant' } }, originalUser = {}, dedicatedUser = {};
  const base = { tenantAdmin: owner, user: originalUser, state: { password: 'unit-private', prefix: 'unit', resources: [] },
    async createAs(actorName, route) { assert.equal(actorName, 'tenantAdmin'); assert.equal(route, '/cas/namespaces/original-tenant/accounts/'); return { id: 7, account: 'unit-account' }; },
    async login(account, password, namespace) { assert.equal(account, 'unit-account'); assert.equal(namespace, 'original-tenant'); return dedicatedUser; } };
  const h = Object.create(base), previous = oauth.fixture, stop = Error('original OAuth prerequisite reached');
  oauth.fixture = async context => {
    assert.equal(context.tenantAdmin, owner); assert.equal(context.state, base.state);
    assert.equal(context.user, dedicatedUser); assert.equal(h.user, originalUser);
    assert.equal(context.createAs, base.createAs); throw stop;
  };
  try { await assert.rejects(handlers['F010-003'](h), error => error === stop); }
  finally { oauth.fixture = previous; }
});

test('fresh namespace retirement journals the exact bootstrap password-change intent before the original form can submit', async () => {
  const { handlers } = require('./namespace_retirement_cases.cjs');
  const resource = { kind: 'namespace', id: 31 }, snapshots = [], stop = Error('original login interrupted');
  const h = { admin: {}, tenantAdmin: {}, otherTenantAdmin: {}, state: { prefix: 'unit', password: 'unit-private', resources: [resource] },
    persist() { snapshots.push(structuredClone(resource)); }, check(label, passed) { assert.ok(passed, label); },
    async ok() { return { value: {} }; }, async create() { return { id: 31, name: 'original-tenant' }; },
    async anonymous() { return {}; }, async directory() { return [{ account: 'original-bootstrap', status: 2 }]; },
    async login(account, password, namespace, nextPassword, beforeChange) {
      assert.equal(account, 'original-bootstrap'); assert.equal(namespace, 'original-tenant');
      assert.equal(password, h.state.password); assert.notEqual(nextPassword, password);
      assert.equal(snapshots.at(-1).retirementLogin.newPassword, nextPassword);
      assert.equal(snapshots.at(-1).retirementLogin.outcome, 'prepared');
      await beforeChange(); assert.equal(snapshots.at(-1).retirementLogin.outcome, 'password-change-in-progress');
      throw stop;
    } };
  await assert.rejects(handlers['F003-004'](h), error => error === stop);
  assert.equal(resource.retirementLogin.outcome, 'password-change-in-progress');
  assert.equal(resource.retirementSession, undefined);
});
