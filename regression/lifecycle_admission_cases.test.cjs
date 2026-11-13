const { test } = require('node:test');
const assert = require('node:assert/strict');
const { probe, cleanup, refusal } = require('./lifecycle_admission_cases.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.test';
const read = '/panel/application/installations/7';
function harness() {
  let calls = 0;
  const h = { admin: { identity, origin }, state: { resources: [] }, persist() {}, Blocked: Error,
    ok: async () => ({ value: { id: 7, deploymentId: 'original', updateTime: 9 } }),
    check: (m, value) => assert.ok(value, m),
    api: async () => { calls++; return { status: 409, data: { error: { code: 19, message: 'exact conflict' } } }; } };
  return { h, calls: () => calls };
}
test('lifecycle refusal requires exact error stage and never accepts login or generic conflicts', () => {
  const response = { status: 409, data: { error: { code: 19, message: 'exact conflict' } } };
  assert.equal(refusal(response, 19, 'exact conflict'), true);
  assert.equal(refusal({ ...response, status: 401 }, 19, 'exact conflict'), false);
  assert.equal(refusal(response, 21, 'exact conflict'), false);
  assert.equal(refusal(response, 19, 'other stage'), false);
  assert.equal(refusal({ ...response, data: { ...response.data, value: { id: 8 } } }, 19, 'exact conflict'), false);
});
test('exact original rejected lifecycle command cleans by owner reads and cannot replay an unknown command', async () => {
  const { h, calls } = harness();
  await probe(h, [read], read + '/activate', { expectedUpdateTime: 8 }, 19, 'exact conflict');
  const r = h.state.resources[0]; assert.equal(calls(), 1); assert.equal(r.phase, 'deleted');
  await cleanup(h, r); assert.equal(calls(), 1);
  for (const mutate of [v => delete v.response, v => v.response.data.error.message = 'earlier failure', v => v.origin = 'https://other.test', v => v.after[read].deploymentId = 'replacement']) {
    const bad = structuredClone(r); mutate(bad); await assert.rejects(cleanup(h, bad)); assert.equal(calls(), 1);
  }
  h.ok = async () => ({ value: { id: 7, deploymentId: 'replacement', updateTime: 9 } });
  await assert.rejects(cleanup(h, r), /owner state changed/); assert.equal(calls(), 1);
});
test('lifecycle recovery binds immutable original target, version, actor and owner snapshots', async () => {
  const { h } = harness(); await probe(h, [read], read + '/activate', { expectedUpdateTime: 8 }, 19, 'exact conflict');
  const r = h.state.resources[0]; r.phase = 'intent'; const evidence = { trace: [], resources: [{ ...structuredClone(r), confirmed: false }] };
  assert.equal(bindOriginalCleanup(h.state, evidence)[0], r);
  for (const mutate of [v => v.intended.expectedUpdateTime++, v => v.route = '/foreign', v => v.reads.push('/foreign'), v => v.journalId = 'replacement', v => v.before[read].updateTime++, v => v.expected.code = 21]) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /differs/);
  }
});
