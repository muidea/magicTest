const { test } = require('node:test');
const assert = require('node:assert/strict');
const { handlers } = require('./service_cases.cjs');
test('foreign capability scope proof excludes missing authentication, forbidden management, dependency errors and returned resources', () => {
  const { scopedUnavailable } = require('./service_cases.cjs');
  const response = { status: 404, data: { error: { code: 2, message: 'exact owner absence' }, value: null } };
  assert.ok(scopedUnavailable(response));
  for (const mutate of [x => x.status = 401, x => x.status = 403, x => x.status = 503, x => x.data.error.code = 5,
    x => x.data.error.code = 11, x => x.data.error.message = '', x => x.data.value = { id: 7 }]) {
    const changed = structuredClone(response); mutate(changed); assert.equal(scopedUnavailable(changed), false);
  }
});
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
test('governance source conflict requires target-stage rejection and unchanged complete inventories; unknown writes cannot replay', async () => {
  const { rejectOtherSource } = require('./service_cases.cjs');
  const routes = ['/panel/hub/services/', '/panel/hub/capabilitys/', '/panel/hub/serviceCapabilityBindings/', '/panel/hub/publications/'];
  for (const mode of ['refused', 'lost', 'early', 'changed']) {
    const originals = [{ id: 1, key: 'original', name: 'original', updateTime: 7 }, { id: 2, key: 'peer' }], cap = { id: 3, key: 'real-query' };
    let sent = 0;
    const rows = { [routes[0]]: originals, [routes[1]]: [cap], [routes[2]]: [], [routes[3]]: [] };
    const h = { admin: { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.example.invalid' }, state: { resources: [] }, Blocked: Error, persist() {},
      check(label, c) { assert.ok(c, label); }, async directory(_, route) { return structuredClone(rows[route]); },
      async ok(_, method, route) { return { value: structuredClone(originals.find(v => route.endsWith('/' + v.id))) }; },
      async api(_, method, route) {
        sent++; assert.equal(method, 'POST'); assert.equal(route, '/panel/hub/services/generated/converge/');
        assert.equal(h.state.resources.at(-1).outcome, 'unknown');
        if (mode === 'lost') throw Error('lost response');
        if (mode === 'changed') rows[routes[2]].push({ id: 99 });
        return { status: mode === 'early' ? 403 : 200, data: { error: { code: mode === 'early' ? 5 : 7, message: '服务标识 "original" 已被其他应用实例或治理来源使用，请为当前实例设置不同的服务标识' } } };
      }
    };
    if (mode === 'refused') { await rejectOtherSource(h, originals, cap); assert.equal(h.state.resources[0].phase, 'deleted'); }
    else {
      await assert.rejects(rejectOtherSource(h, originals, cap)); assert.equal(h.state.resources[0].phase, 'intent');
      await assert.rejects(rejectOtherSource(h, originals, cap), /no convergence replay/);
    }
    assert.equal(sent, 1);
  }
});
