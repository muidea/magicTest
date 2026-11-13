const { test } = require('node:test');
const assert = require('node:assert/strict');
const { rejectApproval, exactRefusal, pendingRequests } = require('./storage_admission_cases.cjs');
const expected = { code: 21, message: 'database instance does not satisfy the application storage requirement' };
function fixture(mode) {
  const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.test';
  const value = { id: 7, version: 1, status: 'submitted' };
  const r = { id: 7, last: value, commands: [], creation: { ownershipConfirmed: true, outcome: 'accepted', actorIdentity: identity, origin } };
  let sent = false, writes = 0;
  const h = { admin: { identity: structuredClone(identity), origin }, Blocked: Error, persist() {},
    check(label, condition) { assert.ok(condition, label); },
    async directory(route) { return [{ id: 1, ...(mode === 'drift' && sent && route.includes('installations') ? { status: 'changed' } : {}) }]; },
    async ok(_a, _m, route) {
      if (route.endsWith('/runtime-options')) return { values: [{ kind: 'base', id: 'base' }, { kind: 'gateway', id: 'gateway' }] };
      if (route.endsWith('/session/')) return { value: { account: { account: mode === 'actor' ? 'other' : 'original' }, homeNamespace: 'panel' } };
      return { value: structuredClone(value) };
    },
    async api() {
      writes++; sent = true;
      if (mode === 'lost') throw Error('original response lost');
      return { status: 409, data: { error: mode === 'wrong' ? { code: 21, message: 'unrelated state conflict' } : expected, value: null } };
    } };
  return { h, r, writes: () => writes };
}
test('only exact approval-stage refusal plus unchanged complete owners and original session resolves negative intent', async () => {
  const f = fixture(); await rejectApproval(f.h, f.r, expected);
  assert.equal(f.writes(), 1); assert.equal(f.r.commands[0].outcome, 'rejected-and-unchanged');
  for (const mode of ['lost', 'drift', 'actor', 'wrong']) {
    const f = fixture(mode); await assert.rejects(rejectApproval(f.h, f.r, expected));
    assert.equal(f.writes(), 1); assert.equal(f.r.commands[0].outcome, 'unknown');
    assert.deepEqual(f.r.commands[0].expected, expected);
    assert.deepEqual(f.r.commands[0].originalRequest, f.r.last);
    assert.ok(Object.keys(f.r.commands[0].before).length >= 7);
    await assert.rejects(rejectApproval(f.h, f.r, expected), /no replay/);
    assert.equal(f.writes(), 1);
  }
});
test('storage scope refusal cannot be replaced by HTTP auth failure or a successful resource response', () => {
  assert.ok(exactRefusal({ status: 403, data: { error: { code: 5, message: 'database instance is unavailable to the target namespace' }, value: null } }, { code: 5, message: 'database instance is unavailable to the target namespace' }));
  for (const response of [{ status: 401, data: { error: { code: 11, message: expected.message } } },
    { status: 200, data: { error: expected, value: { id: 1 } } }, { status: 503, data: { error: expected, value: null } }]) assert.equal(exactRefusal(response, expected), false);
});
test('unresolved and uncleaned exact approval requests fence only their selected physical endpoint', () => {
  const state = { resources: [{ storageAdmissionDatabaseId: 3, phase: 'created', commands: [{ outcome: 'unknown' }] }] };
  assert.equal(pendingRequests(state, 3), true); assert.equal(pendingRequests(state, 4), false);
  state.resources[0].commands[0].outcome = 'rejected-and-unchanged';
  assert.equal(pendingRequests(state, 3), true);
  state.resources[0].phase = 'deleted'; assert.equal(pendingRequests(state, 3), false);
});
