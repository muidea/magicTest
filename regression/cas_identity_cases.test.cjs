const { test } = require('node:test');
const assert = require('node:assert/strict');
const { cleanup, client, credential, activateClient } = require('./cas_identity_cases.cjs');
const clone = structuredClone;
function fixture(mode) {
  const actor = { identity: { account: 'original', namespace: 'tenant-a' }, origin: 'https://tenant-a.test' };
  const calls = [], rows = []; let saved;
  const h = { tenantAdmin: actor, Blocked: Error, state: { resources: [] }, persist() {},
    check(label, condition) { assert.ok(condition, label); }, good: r => r.status === 200 && !r.data.error,
    async api(actual, method, route, body) {
      assert.equal(actual, actor); calls.push({ method, route });
      const intent = h.state.resources.at(-1);
      if (method === 'POST') {
        assert.equal(intent.outcome, 'unknown', 'write intent is durable before transport');
        if (mode === 'response-lost') throw Error('response lost');
        if (route.endsWith('/credentials/')) {
          const value = { id: 22, clientId: saved.clientId, clientSecret: 'private-credential-bytes', name: body.name };
          rows.push({ id: 22, clientId: saved.clientId, name: body.name, status: 'active', ...(mode === 'leaked-list' ? { clientSecret: value.clientSecret } : {}) });
          return { status: 200, data: { value } };
        }
        saved = { ...body, clientId: 'opaque-client-id', namespace: 'tenant-a', endpointId: 17 };
        return { status: 200, data: { value: clone(saved) } };
      }
      if (method === 'GET') return saved ? { status: 200, data: { value: { ...clone(saved), ...(mode === 'wrong-owner' ? { namespace: 'tenant-b' } : {}) } } } : { status: 200, data: { error: { code: 2 }, value: null } };
      assert.equal(method, 'DELETE');
      assert.ok(h.state.resources.some(r => r.deletion?.outcome === 'unknown'), 'DELETE/revoke intent precedes transport');
      if (mode === 'delete-lost') throw Error('delete response lost');
      if (route.includes('/credentials/')) rows[0].status = 'revoked'; else saved = null;
      return { status: 200, data: {} };
    },
    async ok(actual, method, route) { const r = await h.api(actual, method, route); assert.ok(h.good(r)); return r.data; },
    async directory(actual) { assert.equal(actual, actor); return clone(rows); }
  };
  return { h, actor, calls, rows, payload: { name: 'current-run-client', endpointId: 17 } };
}
test('opaque client ID and credential owner reads govern retirement, with immutable credential history', async () => {
  const f = fixture(), c = await client(f.h, f.payload), secret = await credential(f.h, c, { name: 'current-secret' });
  assert.equal(c.resource.id, 'opaque-client-id');
  const proof = await cleanup(f.h, secret.resource); secret.resource.phase = 'deleted';
  assert.equal(proof.terminalCredential.status, 'revoked');
  assert.equal(f.rows.length, 1, 'revoke retains owner history');
  await cleanup(f.h, c.resource);
  assert.ok(f.calls.some(c => c.method === 'DELETE' && c.route.endsWith('/opaque-client-id')));
});
test('unknown client POST remains open and cleanup never guesses a returned identity', async () => {
  const f = fixture('response-lost'); await assert.rejects(client(f.h, f.payload), /response lost/);
  const r = f.h.state.resources[0]; assert.equal(r.outcome, 'unknown');
  await assert.rejects(cleanup(f.h, r), /Unconfirmed/); assert.equal(f.calls.length, 1);
});
test('owner mismatch fails before cleanup mutation', async () => {
  const f = fixture(), c = await client(f.h, f.payload);
  f.actor.identity.namespace = 'tenant-b';
  const count = f.calls.length;
  await assert.rejects(cleanup(f.h, c.resource), /exact original/); assert.equal(f.calls.length, count);
});
test('unknown DELETE is never reissued when original client remains visible', async () => {
  const f = fixture('delete-lost'), c = await client(f.h, f.payload);
  await assert.rejects(cleanup(f.h, c.resource), /response lost/);
  await assert.rejects(cleanup(f.h, c.resource), /no replay/);
  assert.equal(f.calls.filter(c => c.method === 'DELETE').length, 1);
});
test('client cleanup cannot hide unresolved child credential creation', async () => {
  const f = fixture(), c = await client(f.h, f.payload);
  f.h.state.resources.push({ kind: 'cas-probe-credential', parentClient: c.resource.collection + c.resource.id, phase: 'intent' });
  await assert.rejects(cleanup(f.h, c.resource), /unresolved credential/);
  assert.equal(f.calls.filter(c => c.method === 'DELETE').length, 0);
});
test('credential read failures do not permit unconfirmed cleanup', async () => {
  const f = fixture('leaked-list'), c = await client(f.h, f.payload);
  await assert.rejects(credential(f.h, c, { name: 'must-not-leak' }), /without returning full secrets/);
  const r = f.h.state.resources.at(-1);
  assert.equal(r.id, 22); assert.equal(r.outcome, 'accepted'); assert.notEqual(r.ownershipConfirmed, true);
  await assert.rejects(cleanup(f.h, r), /Unconfirmed/);
});
test('non-Endpoint client activation sends the complete conditional owner contract and does not repeat an attempt', async () => {
  const actor = { identity: { account: 'admin', namespace: 'a' }, origin: 'https://a.example' };
  const owner = { value: { clientId: 'client-a' }, resource: { actor: 'tenantAdmin', actorIdentity: structuredClone(actor.identity), origin: actor.origin, collection: '/cas/namespaces/a/oauth/clients/', intended: { name: 'a', clientType: 'confidential', partyType: 'first_party', status: 1 } } };
  let writes = 0;
  const h = { tenantAdmin: actor, Blocked: Error, persist() {}, check: (label, ok) => assert.ok(ok, label), good: r => r.status === 200 && !r.data.error,
    ok: async () => ({ value: { clientId: 'client-a', version: writes ? 5 : 4, status: writes ? 2 : 1 } }),
    api: async (a, method, route, body) => {
      writes++; assert.equal(a, actor); assert.equal(method, 'PUT'); assert.equal(route, owner.resource.collection + 'client-a');
      assert.equal(body.endpointId, 0); assert.equal(body.expectedVersion, 4); assert.equal(body.status, 2);
      assert.equal(body.clientType, undefined); assert.equal(body.partyType, undefined);
      return { status: 200, data: {} };
    } };
  await activateClient(h, owner);
  await assert.rejects(activateClient(h, owner), /no replay/);
  assert.equal(writes, 1);
});
