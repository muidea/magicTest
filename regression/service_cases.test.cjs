const { test } = require('node:test');
const assert = require('node:assert/strict');
const { handlers } = require('./service_cases.cjs');
function fixture(mode) {
  const rows = [], calls = [];
  const actor = { identity: { account: 'tenant-admin', namespace: 'test' } };
  const h = { tenantAdmin: actor, state: { prefix: 'run', resources: [] }, Blocked: Error,
    check(label, condition) { assert.ok(condition, label); }, persist() {},
    async createAs(name, collection, body) { assert.equal(name, 'tenantAdmin'); const r = { ...body, id: rows.length + 1, namespace: 'test', updateTime: 100 }; rows.push(r); return structuredClone(r); },
    async ok(actual, method, route) { assert.equal(actual, actor); assert.equal(method, 'GET'); return { value: structuredClone(rows.find(r => route.endsWith('/' + r.id))) }; },
    async directory(actual) { assert.equal(actual, actor); return structuredClone(rows); },
    async api(actual, method) {
      assert.equal(actual, actor); calls.push(method);
      const intent = h.state.resources.at(-1); assert.equal(intent.phase, 'intent');
      if (mode === 'response-lost') throw Error('response lost');
      if (mode === 'overwrite') rows[0].description = 'MUST NOT OVERWRITE';
      if (mode === 'accepted') { const value = { ...rows[0], id: 3 }; rows.push(value); return { status: 200, data: { value } }; }
      if (mode === 'earlier-reject') return { status: 403, data: { error: { code: 5, message: 'denied' } } };
      return { status: method === 'PUT' ? 400 : 200, data: { error: { code: method === 'PUT' ? 4 : 7, message: method === 'PUT' ? 'service edit field is not writable: key' : 'service key already exists' } } };
    }
  };
  return { h, calls };
}
test('service identity handler proves duplicate and immutable field rejection with two unchanged owner resources', async () => {
  const f = fixture(); await handlers['F037-003'](f.h);
  assert.deepEqual(f.calls, ['POST', 'PUT']);
  assert.equal(f.h.state.resources.length, 2);
  assert.ok(f.h.state.resources.every(r => r.phase === 'deleted' && r.outcome === 'rejected-and-unchanged'));
});
test('service handler detects false positives and retains unknown or successful mutation identities', async () => {
  for (const mode of ['response-lost', 'overwrite', 'accepted', 'earlier-reject']) {
    const f = fixture(mode); await assert.rejects(handlers['F037-003'](f.h));
    const r = f.h.state.resources.at(-1); assert.notEqual(r.phase, 'deleted');
    assert.equal(f.calls.length, 1);
    if (mode === 'accepted') assert.equal(r.id, 3);
    if (mode === 'overwrite') assert.equal(r.observed.readbacks[0].description, 'MUST NOT OVERWRITE');
  }
});
