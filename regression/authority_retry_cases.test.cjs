const { test } = require('node:test');
const assert = require('node:assert/strict');
const { controlledUpstream } = require('./service_graph.cjs');
const { probe, verifyProbe, protectCleanup } = require('./authority_retry_cases.cjs');
const checked = { check(label, condition) { assert.ok(condition, label); } };
function receipt(c) {
  return { marker: c.marker, method: c.method, path: c.method === 'GET' ? '/probe' : '/submit', query: { marker: c.marker },
    body: c.body === undefined ? '' : JSON.stringify(c.body), authorizationPresent: false, namespace: '', extDataPresent: false,
    authorityChallengePresent: false, authorityRejectedPresent: false };
}
function response(c) {
  return { status: c.expectedStatus, data: { fixture: 'controlled-external-upstream', marker: c.marker, method: c.method, body: c.body === undefined ? '' : JSON.stringify(c.body) }, headers: { challenge: null, rejected: null } };
}
test('upstream plans preserve original errors across repeated markers and isolate other requests', async () => {
  const up = controlledUpstream(), marker = 'a'.repeat(24), proof = 'p'.repeat(43);
  up.respond(marker, { status: 409, proof });
  assert.throws(() => up.respond(marker, { status: 200 }), /original/);
  await new Promise(resolve => up.server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + up.server.address().port;
  try {
    for (let i = 0; i < 2; i++) {
      const r = await fetch(origin + '/submit?marker=' + marker, { method: 'POST', headers: { 'X-Magic-Gateway-Authority-Challenge': 'client-forgery' }, body: 'original' });
      assert.equal(r.status, 409); assert.equal(r.headers.get('X-Magic-Gateway-Authority-Rejected'), proof);
      assert.equal((await r.json()).body, 'original');
    }
    assert.equal(up.requests.length, 2); assert.equal(up.requests[0].authorityChallengePresent, true);
    assert.equal(up.requests[0].body, 'original'); assert.equal(up.requests[1].marker, marker);
    const ordinary = await fetch(origin + '/probe?marker=' + 'b'.repeat(24));
    assert.equal(ordinary.status, 200); assert.equal(ordinary.headers.get('X-Magic-Gateway-Authority-Rejected'), null);
    assert.throws(() => up.respond('b'.repeat(24), { status: 401 }), /before dispatch/);
  } finally { up.releaseAll(); up.server.closeAllConnections(); await new Promise(resolve => up.server.close(resolve)); }
});
test('response plans reject unbounded status, header injection and foreign keys before serving', () => {
  for (const value of [{ status: 302 }, { status: 409, proof: 'x\r\nCookie: secret' }, { status: 401, headers: { authorization: 'secret' } }, null]) {
    const up = controlledUpstream(); assert.throws(() => up.respond('a'.repeat(24), value), /Finite/);
  }
  assert.throws(() => controlledUpstream().respond('foreign/path', { status: 200 }), /Finite/);
});
test('browser callback source sends exactly one fetch with original JSON and observes errors without retry', async () => {
  const vm = require('node:vm'), { requestOnce } = require('./authority_retry_cases.cjs'), up = controlledUpstream();
  await new Promise(resolve => up.server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + up.server.address().port;
  try {
    for (const [i, [method, status, forged]] of [['GET', 200, false], ['GET', 401, false], ['GET', 409, true], ['POST', 401, false], ['POST', 409, true]].entries()) {
      const marker = String(i).repeat(24), proof = 'p'.repeat(43); let fetches = 0;
      const args = { route: '/' + (method === 'GET' ? 'probe' : 'submit') + '?marker=' + marker, method,
        ...(method === 'POST' ? { body: { marker, value: 1 } } : {}), proof: forged ? proof : undefined,
        challenge: 'X-Magic-Gateway-Authority-Challenge', rejected: 'X-Magic-Gateway-Authority-Rejected' };
      up.respond(marker, { status, ...(forged ? { proof } : {}) });
      // This is a direct local fixture socket, not a Gateway or Live test.
      const result = await vm.runInNewContext('(' + requestOnce.toString() + ')(args)', { args, JSON, AbortSignal,
        fetch: (route, options) => {
          fetches++; assert.equal(route, args.route); assert.equal(options.redirect, 'error'); assert.equal(options.credentials, 'same-origin');
          assert.equal(options.headers[args.challenge], forged ? proof : undefined);
          assert.equal(options.body, method === 'POST' ? JSON.stringify(args.body) : undefined);
          return fetch(origin + route, options);
        } });
      assert.equal(fetches, 1); assert.equal(result.status, status); assert.equal(result.data.marker, marker);
      assert.equal(result.headers.rejected, forged ? proof : null);
      const rows = up.requests.filter(r => r.marker === marker);
      assert.equal(rows.length, 1); assert.equal(rows[0].body, method === 'POST' ? JSON.stringify(args.body) : '');
      assert.equal(rows[0].authorityChallengePresent, forged);
    }
  } finally { up.releaseAll(); up.server.closeAllConnections(); await new Promise(resolve => up.server.close(resolve)); }
});
test('retry evidence rejects duplicate/missing execution, changed bytes/status/identity and leaked internal authority', () => {
  const c = { method: 'POST', marker: 'a'.repeat(24), expectedStatus: 409, body: { marker: 'a'.repeat(24), value: 1 } };
  c.response = response(c); const received = [receipt(c)]; verifyProbe(checked, c, received);
  for (const mutate of [
    (c, r) => r.push({ ...r[0] }), (c, r) => r.pop(), (c, r) => r[0].body = '{}',
    (c, r) => r[0].path = '/other', (c, r) => r[0].marker = 'foreign', (c, r) => r[0].query.extra = 'scope',
    (c, r) => r[0].method = 'GET', (c, r) => r[0].authorizationPresent = true, (c, r) => r[0].namespace = 'foreign',
    (c, r) => r[0].extDataPresent = true, (c, r) => r[0].authorityChallengePresent = true,
    (c, r) => r[0].authorityRejectedPresent = true, c => c.response.status = 200,
    c => c.response.data.marker = 'different', c => c.response.headers.rejected = 'forgery', c => delete c.response.headers
  ]) { const copy = structuredClone(c), rows = structuredClone(received); mutate(copy, rows); assert.throws(() => verifyProbe(checked, copy, rows)); }
});
function fixture(mode) {
  const identity = { account: 'owner', namespace: 'tenant' }, origin = 'https://tenant.example';
  const service = { id: 7, key: 'original', status: 2, address: 'http://upstream' };
  const ownerValue = structuredClone(service);
  const r = { kind: 'service', id: 7, phase: 'created', creation: { actorIdentity: identity, origin, ownershipConfirmed: true } };
  const f = { service, ownerIdentity: structuredClone(identity), up: { address: service.address, requests: [], respond() {} } };
  let sent = 0, reads = 0;
  const actor = { identity: structuredClone(identity), origin, page: { url: () => origin + '/panel/', async evaluate(fn, args) {
    sent++; const c = r.pendingServiceCommands.at(-1);
    assert.equal(c.confirmed, false); assert.equal(c.serviceId, 7); assert.deepEqual(c.actorIdentity, identity); assert.equal(c.origin, origin);
    assert.equal(c.route, args.route); assert.deepEqual(c.body, args.body);
    if (mode === 'response-loss') throw Error('original response lost');
    f.up.requests.push(receipt(c)); if (mode === 'duplicate') f.up.requests.push(receipt(c));
    return response(c);
  } } };
  const h = { ...checked, Blocked: Error, state: { resources: [r] }, persist() {}, observe() {}, async ok() { reads++; if (mode === 'owner-read-loss' && reads === 2) throw Error('owner read failed'); return { value: structuredClone(ownerValue) }; } };
  return { h, actor, f, r, sent: () => sent };
}
test('original write intent precedes dispatch; response loss, duplicate or failed owner read cannot replay or clean parents', async () => {
  for (const mode of ['confirmed', 'response-loss', 'duplicate', 'owner-read-loss']) {
    const { h, actor, f, r, sent } = fixture(mode), execute = () => probe(h, actor, f, 'POST', 409, true);
    if (mode === 'confirmed') { await execute(); assert.equal(r.pendingServiceCommands[0].confirmed, true); protectCleanup(h, r); }
    else {
      await assert.rejects(execute()); await assert.rejects(execute(), /no replacement request/);
      assert.equal(r.pendingServiceCommands[0].confirmed, false);
      if (mode === 'response-loss') { assert.equal(r.pendingServiceCommands[0].transportError, 'original response lost'); assert.deepEqual(r.pendingServiceCommands[0].received, []); }
      assert.throws(() => protectCleanup(h, r), /no probe replay/);
      assert.throws(() => protectCleanup(h, { kind: 'publication', creation: { intended: { service: { id: 7 } } } }), /no probe replay/);
      protectCleanup(h, { kind: 'service', id: 8 });
    }
    assert.equal(sent(), 1);
  }
});
test('wrong owner, page origin, resource identity or response grammar stops before dispatch', async () => {
  for (const change of [v => v.actor.identity.namespace = 'foreign', v => v.actor.origin = 'https://foreign.example',
    v => v.actor.page.url = () => 'https://foreign.example/', v => v.r.creation.ownershipConfirmed = false,
    v => v.f.service.key = 'foreign', v => v.f.up.address = 'http://foreign-upstream']) {
    const v = fixture('confirmed'); change(v); await assert.rejects(probe(v.h, v.actor, v.f, 'GET', 200)); assert.equal(v.sent(), 0);
  }
  const v = fixture('confirmed'); await assert.rejects(probe(v.h, v.actor, v.f, 'DELETE', 302)); assert.equal(v.sent(), 0);
});
test('cleanup recovery binds exact retry actor, original request body, response and upstream observations', () => {
  const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
  const r = { kind: 'service', id: 7, phase: 'created', pendingServiceCommands: [{ kind: 'authority-retry-probe', method: 'POST', route: '/original', marker: 'original', forgedProof: 'p'.repeat(43), body: { value: 1 }, actorIdentity: { namespace: 'tenant', account: 'owner' }, origin: 'https://tenant.example', confirmed: false, response: { status: 409 }, received: [{ marker: 'original' }] }] };
  const original = { trace: [], resources: [{ ...structuredClone(r), confirmed: false }] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const mutate of [c => c.marker = 'new', c => c.body.value++, c => c.actorIdentity.namespace = 'foreign', c => c.confirmed = true,
    c => c.response.status = 200, c => c.received.pop(), c => c.route = '/replacement', c => c.origin = 'https://foreign.example', c => c.forgedProof = 'replacement']) {
    const copy = structuredClone(r); mutate(copy.pendingServiceCommands[0]); assert.throws(() => bindOriginalCleanup({ resources: [copy] }, original), /differs/);
  }
});
