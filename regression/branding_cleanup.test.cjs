const { test } = require('node:test');
const assert = require('node:assert/strict');
const { resetBranding } = require('./branding_cleanup.cjs');
const busy = { status: 200, data: { error: { code: 21, message: '租户空间安装或删除操作正在进行，请稍后重试' }, value: null } };
function fixture(responses) {
  const actor = { identity: { account: 'admin', namespace: 'original' }, origin: 'https://original.test' };
  const resource = { kind: 'namespace-branding', collection: '/panel/namespace-branding/', id: '', name: 'original', phase: 'created' };
  let override = { platformName: 'current-run' }; const deletes = [];
  const h = { Blocked: Error, state: { resources: [resource, { kind: 'namespace', name: 'original', phase: 'created', creation: { ownershipConfirmed: true } }] }, persist() {}, good: r => r.status === 200 && !r.data.error,
    check(label, ok) { assert.ok(ok, label); }, async ok(actual, method) { assert.equal(actual, actor); assert.equal(method, 'GET'); return { value: { namespace: 'original', override } }; },
    async api(actual, method) {
      assert.equal(actual, actor); assert.equal(method, 'DELETE'); assert.equal(resource.brandingReset.attempts.at(-1).outcome, 'unknown');
      deletes.push(method); const r = responses.shift(); if (r instanceof Error) throw r;
      if (h.good(r)) override = null; return r;
    } };
  return { h, actor, resource, deletes };
}
test('only exact admission rejection permits a bounded subsequent reset', async () => {
  const f = fixture([busy, { status: 200, data: { error: null } }]);
  await resetBranding(f.h, f.actor, f.resource, async () => {});
  assert.equal(f.deletes.length, 2); assert.equal(f.resource.brandingReset.attempts[0].outcome, 'rejected-before-admission');
});
test('response loss and generic failures remain open without mutation replay', async () => {
  for (const response of [Error('response lost'), { status: 200, data: { error: { code: 21, message: 'different operation' } } }, { status: 503, data: {} }]) {
    const f = fixture([response]); await assert.rejects(resetBranding(f.h, f.actor, f.resource, async () => {}));
    await assert.rejects(resetBranding(f.h, f.actor, f.resource, async () => {}), /no replay/); assert.equal(f.deletes.length, 1);
  }
});
test('persistent admission contention retains resource after explicit budget', async () => {
  const f = fixture([busy, busy, busy, busy]);
  await assert.rejects(resetBranding(f.h, f.actor, f.resource, async () => {}), /remained busy/);
  assert.equal(f.deletes.length, 4); assert.equal(f.resource.phase, 'created');
});
test('foreign tenant identity cannot reset another tracked brand', async () => {
  const f = fixture([]); f.actor.identity.namespace = 'foreign';
  await assert.rejects(resetBranding(f.h, f.actor, f.resource), /original tracked/); assert.equal(f.deletes.length, 0);
});
test('unknown tenant scalar or asset upload and changed original origin cannot be hidden by reset', async () => {
  for (const mode of ['scalar', 'asset', 'origin']) {
    const f = fixture([]);
    if (mode === 'origin') { f.resource.actorIdentity = structuredClone(f.actor.identity); f.resource.origin = 'https://foreign.test'; }
    else f.resource.brandingCommands = [{ method: mode === 'scalar' ? 'PUT' : 'POST', outcome: 'unknown' }];
    await assert.rejects(resetBranding(f.h, f.actor, f.resource)); assert.equal(f.deletes.length, 0);
  }
});
