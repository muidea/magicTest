const { test } = require('node:test');
const assert = require('node:assert/strict');
const { restore } = require('./retention_cases.cjs');
test('global retention restore rejects changed owner, foreign revision and unresolved command without writes', async () => {
  const policies = { securityAudit: { retentionDays: 0 }, operationLog: { retentionDays: 0 } };
  const actorIdentity = { account: 'admin', namespace: 'panel' }, origin = 'https://panel.local.vpc';
  const baseline = { kind: 'log-retention-restore', phase: 'created', actorIdentity, origin, commands: [], original: { resourceVersion: 1, policies }, last: { resourceVersion: 2, policies } };
  for (const mode of ['different-owner', 'foreign-revision', 'unknown-write']) {
    const r = structuredClone(baseline); let writes = 0;
    if (mode === 'unknown-write') r.commands.push({ outcome: 'unknown' });
    const h = { admin: { identity: mode === 'different-owner' ? { ...actorIdentity, account: 'other' } : actorIdentity, origin }, Blocked: Error, persist() {}, check: (label, ok) => assert.ok(ok, label), ok: async (actor, method) => { assert.equal(method, 'GET'); return { value: mode === 'foreign-revision' ? { ...r.last, resourceVersion: 3 } : r.last }; }, api: async () => { writes++; } };
    await assert.rejects(restore(h, r)); assert.equal(writes, 0); assert.equal(r.phase, 'created');
  }
});
test('response-lost conditional restoration is persisted as unknown and never repeated', async () => {
  const r = { kind: 'log-retention-restore', phase: 'created', actorIdentity: { account: 'admin', namespace: 'panel' }, origin: 'https://panel.local.vpc', commands: [], original: { resourceVersion: 1, policies: { securityAudit: { retentionDays: 0 }, operationLog: { retentionDays: 30 } } }, last: { resourceVersion: 2, policies: { securityAudit: { retentionDays: 0 }, operationLog: { retentionDays: 0 } } } };
  let writes = 0, snapshots = [];
  const h = { admin: { identity: r.actorIdentity, origin: r.origin }, Blocked: Error, persist: () => snapshots.push(structuredClone(r)), check: (label, ok) => assert.ok(ok, label), ok: async () => ({ value: r.last }), api: async (actor, method, route, body) => {
    writes++; assert.equal(method, 'PUT'); assert.equal(body.expectedResourceVersion, 2); assert.deepEqual(body.operationLog, r.original.policies.operationLog);
    assert.equal(snapshots.at(-1).commands.at(-1).outcome, 'unknown'); throw Error('original restore response lost');
  } };
  await assert.rejects(restore(h, r), /response lost/);
  await assert.rejects(restore(h, r), /never replay/);
  assert.equal(writes, 1); assert.equal(r.phase, 'created');
});
