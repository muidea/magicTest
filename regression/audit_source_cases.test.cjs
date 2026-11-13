const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const vm = require('node:vm');
const { sourceHeaders, mutationOnce, verifyAudit, mutate, compareSources } = require('./audit_source_cases.cjs');
const checked = { Blocked: Error, check(label, value) { assert.ok(value, label); } };
const foreign = { namespace: 'foreign', subject: 'account:9' };
function event(c) {
  return { eventId: 'new-event', operationType: '更新服务', detailMessage: '服务ID:' + c.serviceId + '；标识:' + c.serviceKey,
    outcome: 'succeeded', actorNamespace: c.actorIdentity.namespace, actorSubject: c.subject, targetNamespace: c.actorIdentity.namespace,
    namespace: c.actorIdentity.namespace, operationTime: c.startedAt, address: '127.0.0.1' };
}
test('source probe grammar creates only finite forwarding and asserted identity headers without credentials', () => {
  assert.deepEqual(sourceHeaders('control', foreign), {});
  for (const variant of ['single', 'chain']) {
    const headers = sourceHeaders(variant, foreign);
    assert.equal(headers['X-Mp-Namespace'], 'foreign');
    assert.equal(JSON.parse(headers['X-Mp-Entity-Ext-Data']).actorSubject, 'account:9');
    assert.equal(Object.keys(headers).length, 6);
    assert.ok(!Object.keys(headers).some(k => /cookie|authorization|host|origin/i.test(k)));
  }
  for (const [variant, identity] of [['arbitrary', foreign], ['single', { namespace: 'foreign\r\nHost:other', subject: 'account:9' }], ['single', { ...foreign, subject: 'endpoint:9' }], ['single', null]]) assert.throws(() => sourceHeaders(variant, identity));
});
test('mutation callback source sends exact bytes once with original headers and never follows redirects or retries lost responses', async () => {
  const seen = [], server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    seen.push({ path: req.url, method: req.method, headers: req.headers, body: Buffer.concat(chunks).toString() });
    if (req.url.endsWith('/8')) { req.socket.destroy(); return; }
    if (req.url.endsWith('/9')) { res.writeHead(307, { Location: '/must-not-follow' }); res.end(); return; }
    res.end(JSON.stringify({ value: { id: 7 } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const execute = args => vm.runInNewContext('(' + mutationOnce.toString() + ')(args)', { args, location: { origin }, JSON, AbortSignal,
    fetch: (route, options) => { assert.equal(options.credentials, 'same-origin'); assert.equal(options.redirect, 'error'); return fetch(origin + route, options); } });
  const args = { origin, route: '/api/v1/web/proxy/panel/hub/services/7', body: { expectedServiceVersion: 12, description: '原样 中文' }, headers: sourceHeaders('chain', foreign) };
  try {
    assert.equal((await execute(args)).data.value.id, 7);
    assert.equal(seen.length, 1); assert.equal(seen[0].method, 'PUT'); assert.equal(seen[0].body, JSON.stringify(args.body));
    assert.equal(seen[0].headers['x-forwarded-for'], args.headers['X-Forwarded-For']);
    assert.equal(seen[0].headers['x-mp-entity-ext-data'], args.headers['X-Mp-Entity-Ext-Data']);
    await assert.rejects(execute({ ...args, route: args.route.slice(0, -1) + '8' }));
    await assert.rejects(execute({ ...args, route: args.route.slice(0, -1) + '9' }));
    assert.equal(seen.length, 3); assert.ok(!seen.some(r => r.path === '/must-not-follow'));
    for (const bad of [{ ...args, origin: 'https://foreign.example' }, { ...args, route: '//foreign.example/7' }, { ...args, route: args.route + '?namespace=foreign' }]) await assert.rejects(execute(bad));
    assert.equal(seen.length, 3);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
test('audit proof rejects missing/duplicate events, wrong actor/tenant/resource, old IDs, spoof/default sources and leaked secrets', () => {
  const c = { serviceId: 7, serviceKey: 'original', subject: 'account:2', actorIdentity: { namespace: 'panel' }, beforeEventIds: ['old-event'], startedAt: Date.now() };
  const rows = [event(c)]; verifyAudit(checked, c, rows, ['test-password']);
  for (const change of [r => r.pop(), r => r.push({ ...r[0] }), r => r[0].eventId = 'old-event', r => r[0].actorSubject = foreign.subject,
    r => r[0].actorNamespace = 'foreign', r => r[0].namespace = 'foreign', r => r[0].targetNamespace = 'foreign',
    r => r[0].detailMessage = 'another-resource', r => r[0].outcome = 'failed', r => r[0].address = '0.0.0.0', r => r[0].address = '198.51.100.201',
    r => r[0].address = '::ffff:203.0.113.202', r => r[0].address = 'not-an-ip', r => r[0].operationTime = c.startedAt - 10000, r => r[0].private = 'test-password']) {
    const copy = structuredClone(rows); change(copy); assert.throws(() => verifyAudit(checked, c, copy, ['test-password']));
  }
});
function fixture(mode = 'success') {
  const identity = { namespace: 'panel', account: 'admin' }, origin = 'https://panel.example';
  const r = { kind: 'service', id: 7, collection: '/panel/hub/services/', phase: 'created', creation: { ownershipConfirmed: true, intended: { key: 'original' }, actorIdentity: structuredClone(identity), origin } };
  let stored = { id: 7, key: 'original', description: 'before', updateTime: 10, options: '{}' }, writes = 0, reads = 0; const logs = [];
  const actor = { identity: structuredClone(identity), origin, page: { url: () => origin + '/panel/', async evaluate(fn, args) {
    writes++; const c = r.pendingServiceCommands.at(-1);
    assert.equal(c.confirmed, false); assert.deepEqual(c.body, args.body); assert.deepEqual(c.headers, args.headers);
    assert.equal(c.route, '/panel/hub/services/7'); assert.equal(c.body.expectedServiceVersion, stored.updateTime);
    stored = { ...stored, description: args.body.description, updateTime: stored.updateTime + 1 };
    logs.push({ ...event(c), eventId: 'event-' + writes });
    if (mode === 'wrong-audit') logs.at(-1).actorSubject = foreign.subject;
    if (mode === 'response-loss') throw Error('original response lost');
    if (mode === 'actor-drift') actor.identity.namespace = 'foreign';
    return { status: 200, data: { value: structuredClone(stored) } };
  } } };
  const h = { ...checked, admin: actor, state: { resources: [r] }, persist() {}, observe() {}, good: r => r.status === 200 && !r.data?.error,
    async ok() { if (++reads === 2 && mode === 'owner-loss') throw Error('owner read lost'); return { value: structuredClone(stored) }; },
    async directory() { return structuredClone(logs); } };
  return { h, actor, r, writes: () => writes };
}
test('source mutation persists original intent and proof; unknown response, owner or audit failures never repeat writes', async () => {
  for (const mode of ['success', 'response-loss', 'owner-loss', 'wrong-audit', 'actor-drift']) {
    const v = fixture(mode), execute = () => mutate(v.h, v.actor, v.r, 'account:2', 'single', foreign);
    if (mode === 'success') { const c = await execute(); assert.equal(c.confirmed, true); assert.equal(c.audit.eventId, 'event-1'); }
    else { await assert.rejects(execute()); assert.equal(v.r.pendingServiceCommands[0].confirmed, false); await assert.rejects(execute(), /no replacement mutation/); }
    if (mode === 'response-loss') assert.equal(v.r.pendingServiceCommands[0].transportError, 'original response lost');
    assert.equal(v.writes(), 1);
  }
});
test('wrong original identity, route or ownership confirmation blocks before mutation', async () => {
  for (const change of [v => v.actor.origin = 'https://foreign.example', v => v.actor.identity.account = 'other', v => v.r.creation.ownershipConfirmed = false,
    v => v.r.collection = '/foreign/', v => v.r.creation.intended.key = 'foreign', v => v.actor.page.url = () => 'https://foreign.example/']) {
    const v = fixture(); change(v); await assert.rejects(mutate(v.h, v.actor, v.r, 'account:2', 'control', foreign)); assert.equal(v.writes(), 0);
  }
});
test('source comparison requires bracketing controls, original identities and five distinct confirmed events', () => {
  const rows = ['control', 'single', 'control', 'chain', 'control'].map((variant, i) => ({ variant, confirmed: true, actorIdentity: { namespace: 'panel', account: 'admin' }, origin: 'https://panel.example', serviceId: 7, audit: { eventId: 'event-' + i, address: '127.0.0.1' } }));
  compareSources(checked, rows);
  for (const change of [r => r[1].audit.address = '192.0.2.204', r => r[2].audit.address = '192.0.2.204', r => r[0].confirmed = false, r => r[4].audit.eventId = r[0].audit.eventId,
    r => r[1].actorIdentity.namespace = 'foreign', r => r[1].serviceId++, r => r[1].variant = 'control', r => r.pop()]) {
    const copy = structuredClone(rows); change(copy); assert.throws(() => compareSources(checked, copy));
  }
});
test('immutable cleanup binding protects original source headers, event set, body, actor and transport failure', () => {
  const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
  const r = { kind: 'service', id: 7, phase: 'created', pendingServiceCommands: [{ kind: 'audit-source-mutation', actorIdentity: { namespace: 'panel', account: 'admin' }, headers: sourceHeaders('chain', foreign), beforeEventIds: ['baseline'], body: { expectedServiceVersion: 12, description: 'original' }, transportError: 'original lost response', confirmed: false }] };
  const original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const change of [c => c.headers['X-Forwarded-For'] = 'new-source', c => c.beforeEventIds.pop(), c => c.body.expectedServiceVersion++, c => c.actorIdentity.namespace = 'foreign', c => c.confirmed = true, c => delete c.transportError]) {
    const copy = structuredClone(r); change(copy.pendingServiceCommands[0]); assert.throws(() => bindOriginalCleanup({ resources: [copy] }, original));
  }
});
