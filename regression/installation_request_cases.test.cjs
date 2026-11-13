const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { generated, sourceMatches, cleanup } = require('./installation_request_cases.cjs');
test('model request binds its source ZIP digest separately from the expected artifact digest; native request uses package digest', () => {
  const pkg = { id: 7, artifactDigest: 'artifact', packageDigest: 'zip' }, value = { packageId: 7, sourceKind: 'model-package', sourceDigest: 'zip', modelPackage: structuredClone(pkg) };
  assert.ok(sourceMatches(value, 'model-package', pkg, 'artifact'));
  assert.equal(sourceMatches({ ...value, sourceDigest: 'artifact' }, 'model-package', pkg, 'artifact'), false);
  assert.equal(sourceMatches(value, 'model-package', pkg, 'zip'), false);
  assert.equal(sourceMatches({ ...value, modelPackage: { ...pkg, artifactDigest: 'other' } }, 'model-package', pkg, 'artifact'), false);
  assert.ok(sourceMatches({ packageId: 7, sourceKind: 'deployment-package', sourceDigest: 'zip' }, 'deployment-package', pkg, 'zip'));
});
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
test('automatic request identity is exact tenant-bound, bounded and valid; name alone cannot prove instance identity', () => {
  const key = 'a'.repeat(32), namespace = 'panel', id = crypto.createHash('sha256').update('magic.application-instance/v1\0' + namespace + '\0' + key).digest('hex').slice(0, 32);
  const value = { namespace, instanceKey: key, instanceName: '自动生成实例', deploymentId: id };
  assert.ok(generated(value, namespace));
  for (const mutate of [x => x.instanceKey = 'other', x => x.instanceName = '', x => x.instanceName = 'a'.repeat(129), x => x.instanceName = 'line\nbreak',
    x => x.namespace = 'other', x => x.deploymentId = 'b'.repeat(32)]) {
    const changed = structuredClone(value); mutate(changed); assert.equal(generated(changed, namespace), false);
  }
});
test('requester cleanup never substitutes an administrator, repeats unknown commands or discards original actor evidence', async () => {
  const identity = { account: 'requester', namespace: 'panel' }, origin = 'https://panel.test';
  for (const mode of ['unknown', 'wrong-actor', 'wrong-origin', 'missing-password', 'unconfirmed-account', 'unconfirmed-request']) {
    const r = { phase: 'created', commands: [], requester: { identity: structuredClone(identity), origin, accountId: 9, password: 'private-original' },
      creation: { ownershipConfirmed: true, outcome: 'accepted', actorIdentity: structuredClone(identity), origin } };
    const account = { id: 9, kind: 'account', phase: 'created', collection: '/cas/namespaces/panel/accounts/', creation: { ownershipConfirmed: true, intended: { account: 'requester' } } };
    if (mode === 'unknown') r.commands.push({ outcome: 'unknown' });
    if (mode === 'wrong-actor') r.requester.identity.account = 'replacement';
    if (mode === 'wrong-origin') r.requester.origin = 'https://other.test';
    if (mode === 'missing-password') delete r.requester.password;
    if (mode === 'unconfirmed-account') account.creation.ownershipConfirmed = false;
    if (mode === 'unconfirmed-request') r.creation.outcome = 'unknown';
    let calls = 0;
    await assert.rejects(cleanup({ Blocked: Error, state: { resources: [account] }, async ok() { calls++; }, async login() { calls++; } }, r));
    assert.equal(calls, 0); assert.equal(r.phase, 'created');
  }
});
test('requester recovery binds original principal, last request and commands to immutable cleanup', () => {
  const r = { kind: 'requester-preview-request', id: 7, phase: 'created', requester: { identity: { account: 'original', namespace: 'panel' }, accountId: 9, origin: 'https://panel.test' },
    last: { id: 7, version: 1 }, commands: [] }, original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const mutate of [x => x.requester.identity.account = 'other', x => x.requester.accountId = 8, x => x.last.version++, x => x.commands.push({ outcome: 'unknown' })]) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
  }
});
