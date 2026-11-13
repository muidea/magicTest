const { test } = require('node:test');
const assert = require('node:assert/strict');
const { forbidReview } = require('./approval_state_cases.cjs');
test('cancel proof distinguishes target writes from concurrent unrelated recovery without dropping owner facts', () => {
  const { confirmCancelledReview } = require('./approval_state_cases.cjs');
  class Blocked extends Error {}
  const observed = [], h = { Blocked, observe(e) { observed.push(e); }, check(label, passed) { assert.ok(passed, label); } };
  const before = { request: { id: 17, version: 1, status: 'submitted' }, operations: [{ id: 9, executionResumeMode: 'confirm' }], installations: [{ id: 5 }] };
  const drift = structuredClone(before); drift.operations[0].executionResumeMode = 'resume';
  assert.throws(() => confirmCancelledReview(h, before, drift, []), Blocked);
  assert.deepEqual(observed[0].before, before); assert.deepEqual(observed[0].after, drift);
  for (const change of [s => s.request.version++, s => s.request.status = 'rejected']) {
    const after = structuredClone(drift); change(after);
    assert.throws(() => confirmCancelledReview(h, before, after, []), assert.AssertionError);
  }
  assert.throws(() => confirmCancelledReview(h, before, drift, ['POST /original/reject']), assert.AssertionError);
  confirmCancelledReview(h, before, structuredClone(before), []);
});
function fixture(mode, status = 'cancelled') {
  const admin = { origin: 'https://panel.example.invalid', identity: { namespace: 'panel', account: 'original-reviewer' } };
  const current = { id: 17, status, version: 3, deploymentId: 'a'.repeat(32) };
  const r = { id: 17, last: structuredClone(current), commands: [], creation: { outcome: 'accepted', ownershipConfirmed: true, origin: admin.origin, actorIdentity: structuredClone(admin.identity) } };
  let writes = 0;
  const h = { admin, Blocked: Error, persist() {}, check: (label, condition) => assert.ok(condition, label),
    async ok() { return { value: structuredClone(current) }; },
    async directory() { return writes && mode === 'new-operation' ? [{ id: 999 }] : []; },
    async api() {
      writes++;
      if (mode === 'lost') throw Error('original response lost');
      if (mode === 'mutated') current.version++;
      const code = mode === 'auth' ? 11 : mode === 'stale' ? 19 : 21;
      return { status: mode === 'outage' ? 503 : mode === 'auth' ? 401 : 200,
        data: { error: { code, message: 'application deployment request cannot be reviewed' }, value: null } };
    } };
  return { h, r, writes: () => writes };
}
test('terminal review proof requires the exact state fence and complete unchanged owner facts', async () => {
  for (const status of ['cancelled', 'rejected', 'succeeded']) for (const action of ['approve', 'reject']) {
    const f = fixture('good', status); await forbidReview(f.h, f.r, action, { executionInstanceId: 'base', gatewayInstanceId: 'gateway' });
    assert.equal(f.r.commands[0].outcome, 'rejected-and-unchanged'); assert.equal(f.writes(), 1);
  }
  for (const mode of ['auth', 'stale', 'outage', 'mutated', 'new-operation', 'lost']) {
    const f = fixture(mode);
    await assert.rejects(forbidReview(f.h, f.r, 'approve', {}));
    assert.equal(f.r.commands[0].outcome, 'unknown');
    await assert.rejects(forbidReview(f.h, f.r, 'approve', {}), /unresolved/);
    assert.equal(f.writes(), 1, 'An unproved or lost original command is never replayed');
  }
});
test('a wrong reviewer, concurrent request change or nonterminal state cannot issue a terminal probe', async () => {
  for (const change of [f => { f.h.admin.identity.account = 'other'; }, f => { f.r.last.version--; }, f => { f.r.last.status = 'submitted'; }]) {
    const f = fixture('good'); change(f);
    await assert.rejects(forbidReview(f.h, f.r, 'reject', {})); assert.equal(f.writes(), 0);
  }
});
