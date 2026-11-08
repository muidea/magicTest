const { test } = require('node:test');
const assert = require('node:assert/strict');
const { subscribe, cleanupSubscription, cleanupCredential, rotate, call, succeeds } = require('./service_graph.cjs');
const { chromium } = require('playwright');
function harness(mode) {
  const requests = [], actor = { identity: { account: 'member', namespace: 'test' }, origin: 'https://test.example' };
  const subject = { namespace: 'test', subject: 'account:3', accountId: 3 };
  const current = { id: 8, service: { id: 7 }, namespace: 'test', subscriberRef: subject, status: 2 };
  let persisted, deleted = false;
  const h = { user: actor, tenantAdmin: { identity: { account: 'admin', namespace: 'test' } }, state: { resources: [] }, Blocked: Error,
    persist() { persisted = structuredClone(h.state.resources); },
    check(label, value) { assert.ok(value, label); }, good: r => r.status === 200 && !r.data?.error,
    async api(who, method, route, body) {
      requests.push({ method, route });
      if (method === 'POST') { assert.equal(persisted.at(-1).outcome, 'unknown'); if (mode === 'transport-loss') throw Error('response lost'); return { status: 200, data: {} }; }
      if (route.includes('subscription-requests')) return { status: 200, data: { value: { requestId: body?.requestId || h.state.resources.at(-1).requestId, phase: mode === 'pending' ? 'external' : 'complete', subscriptionId: 8, errorCode: 0 } } };
      if (method === 'DELETE') { assert.equal(persisted.at(-1).deletion.outcome, 'unknown'); if (mode === 'delete-lost') throw Error('delete lost'); deleted = true; return { status: 200, data: { value: current } }; }
      return deleted ? { status: 200, data: { error: { code: 2 }, value: null } } : { status: 200, data: { value: current } };
    },
    async ok(who, method, route) { return { value: route.includes('/session/') ? { account: { id: 3 } } : { ...current, ...(mode === 'wrong-subject' ? { subscriberRef: { ...subject, accountId: 99 } } : {}) } }; }
  };
  return { h, requests };
}
test('formal original subscription receipt and subject gate cleanup without command replay', async () => {
  const f = harness(); const s = await subscribe(f.h, { service: { id: 7 } });
  await cleanupSubscription(f.h, s.resource);
  assert.equal(f.requests.filter(x => x.method === 'POST').length, 1);
  assert.equal(f.requests.filter(x => x.method === 'DELETE').length, 1);
  for (const mode of ['transport-loss', 'pending', 'wrong-subject']) {
    const f = harness(mode); await assert.rejects(subscribe(f.h, { service: { id: 7 } }));
    await assert.rejects(cleanupSubscription(f.h, f.h.state.resources[0]));
    assert.equal(f.requests.filter(x => x.method === 'POST').length, 1);
    assert.equal(f.requests.filter(x => x.method === 'DELETE').length, 0);
  }
  const lost = harness('delete-lost'), s2 = await subscribe(lost.h, { service: { id: 7 } });
  await assert.rejects(cleanupSubscription(lost.h, s2.resource));
  await assert.rejects(cleanupSubscription(lost.h, s2.resource));
  assert.equal(lost.requests.filter(x => x.method === 'DELETE').length, 1);
});
test('real browser service call omits BFF cookies and success needs independent upstream proof', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext(), page = await context.newPage(), origin = 'https://test.example';
    await context.addCookies([{ name: 'session', value: 'private-session', url: origin }]);
    let observed;
    const f = { service: { key: 'original' }, up: { requests: [] } };
    await page.route('**/*', async route => {
      const r = route.request(), url = new URL(r.url());
      if (!url.pathname.startsWith('/api/')) return route.fulfill({ body: 'isolated fixture' });
      observed = await r.allHeaders();
      const marker = url.searchParams.get('marker');
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ marker }) });
    });
    await page.goto(origin);
    const h = { observe() {}, check(label, value) { assert.ok(value, label); } }, actor = { page, origin };
    const response = await call(h, actor, f, 'private-key');
    assert.equal(response.status, 200); assert.equal(observed.cookie, undefined); assert.equal(observed.authorization, 'ApiKey private-key');
    await assert.rejects(succeeds(h, actor, f, { apiKey: 'private-key' }), /upstream exactly once/);
  } finally { await browser.close(); }
});
test('rotation response loss preserves both original intents and cannot authorize guessed retirement', async () => {
  const owner = { account: 'admin', namespace: 'tenant-a' };
  const previous = { resource: { kind: 'service-graph-credential', serviceId: 7, parentSubscriptionId: 8, collection: '/panel/hub/subscription/credentials/',
    ownerIdentity: owner, actorIdentity: owner, name: 'original-key', phase: 'created', outcome: 'accepted', value: { credentialId: 3, clientId: 'original-client', endpointId: 9 } } };
  const calls = [];
  const h = { tenantAdmin: { identity: structuredClone(owner) }, state: { prefix: 'test', resources: [previous.resource] }, Blocked: Error,
    persist() {}, check(label, value) { assert.ok(value, label); }, good: r => r.status === 200 && !r.data?.error,
    async api(actor, method, route) {
      calls.push({ method, route });
      assert.equal(previous.resource.rotation.outcome, 'unknown');
      assert.equal(h.state.resources.at(-1).outcome, 'unknown');
      throw Error('original rotation response lost');
    } };
  await assert.rejects(rotate(h, previous), /response lost/);
  await assert.rejects(rotate(h, previous), /unresolved rotation/);
  await assert.rejects(cleanupCredential(h, h.state.resources.at(-1)), /exact acknowledged original/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'POST');
  assert.equal(previous.resource.phase, 'created');
});
test('subscription retains its real second-tenant owner and cleanup refuses a different owner session', async () => {
  const f = harness(), second = { identity: { account: 'admin', namespace: 'second' } };
  f.h.otherTenantAdmin = second;
  // The test owner projection must match the original second-tenant subject.
  const oldOK = f.h.ok;
  f.h.ok = async (...args) => {
    const value = await oldOK(...args);
    if (!args[2].includes('/session/')) {
      assert.equal(args[0], second);
      value.value.namespace = 'second'; value.value.subscriberRef.namespace = 'second';
    }
    return value;
  };
  f.h.user.identity.namespace = 'second';
  const s = await subscribe(f.h, { service: { id: 7 }, ownerIdentity: second.identity });
  assert.deepEqual(s.resource.ownerIdentity, second.identity);
  delete f.h.otherTenantAdmin;
  await assert.rejects(cleanupSubscription(f.h, s.resource), /Exact original.*owner session/);
  assert.equal(f.requests.filter(r => r.method === 'DELETE').length, 0);
});
