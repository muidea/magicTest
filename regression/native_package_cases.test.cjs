const { test } = require('node:test');
const assert = require('node:assert/strict');
const { repeat, importExact } = require('./native_package_cases.cjs');
const { cleanup } = require('./native_provider_access_cases.cjs');
test('native import fails before upload on unknown command/import, changed actor or changed ZIP; cleanup retains unconfirmed File intent', async () => {
  const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.test', bytes = Buffer.from('original ZIP');
  const digest = 'sha256:' + require('node:crypto').createHash('sha256').update(bytes).digest('hex');
  for (const mode of ['unknown-import', 'unknown-build', 'changed-actor', 'changed-origin', 'changed-bytes']) {
    const r = { phase: 'created', packageAcknowledged: true, actorIdentity: structuredClone(identity), origin, package: { id: 7, packageDigest: digest }, commands: [] };
    if (mode === 'unknown-import') r.imports = [{ outcome: 'unknown', upload: { outcome: 'unknown' } }];
    if (mode === 'unknown-build') r.commands.push({ outcome: 'unknown' });
    if (mode === 'changed-actor') r.actorIdentity.account = 'replacement';
    if (mode === 'changed-origin') r.origin = 'https://other.test';
    let calls = 0;
    const h = { admin: { identity, origin }, Blocked: Error, async directory() { calls++; }, async api() { calls++; } };
    await assert.rejects(importExact(h, r, mode === 'changed-bytes' ? Buffer.from('other') : bytes, async () => { calls++; }));
    if (mode === 'unknown-import') { await assert.rejects(cleanup(h, r)); assert.equal(r.phase, 'created'); }
    assert.equal(calls, 0);
  }
});
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
test('unknown native author draft save protects original definition until formal command confirmation', () => {
  const { guardDefinitionCleanup } = require('./native_package_cases.cjs');
  const r = { nativePackageDraftCommands: [{ outcome: 'unknown' }] };
  assert.throws(() => guardDefinitionCleanup({ Blocked: Error }, r), /unresolved/);
  r.nativePackageDraftCommands[0].outcome = 'confirmed'; guardDefinitionCleanup({ Blocked: Error }, r);
});
test('intentional package duplicate never retries an unknown original or switches its actor', async () => {
  const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.test';
  for (const mode of ['unconfirmed', 'unknown', 'changed-actor', 'changed-origin', 'wrong-receipt']) {
    const r = { kind: 'native-package-probe', packageAcknowledged: true, actorIdentity: structuredClone(identity), origin,
      package: { id: 7 }, commands: [{ method: 'POST', route: '/panel/application/deployment-packages/builds/', outcome: 'confirmed', response: { status: 200, data: { error: null, value: { id: 7 } } } }] };
    if (mode === 'unconfirmed') r.packageAcknowledged = false;
    if (mode === 'unknown') r.commands.push({ outcome: 'unknown' });
    if (mode === 'changed-actor') r.actorIdentity.account = 'replacement';
    if (mode === 'changed-origin') r.origin = 'https://other.test';
    if (mode === 'wrong-receipt') r.commands[0].response.data.value.id = 8;
    let calls = 0;
    const h = { admin: { identity, origin }, Blocked: Error, good: x => x.status === 200 && !x.data.error,
      async directory() { calls++; }, async api() { calls++; } };
    await assert.rejects(repeat(h, r)); assert.equal(calls, 0); assert.equal(r.commands[0].outcome, 'confirmed');
  }
});
test('native package recovery binds original command, complete package and pre-command ownership', () => {
  const r = { kind: 'native-package-probe', phase: 'created', applicationUuid: 'exact', preexistingIds: [1], packageAcknowledged: true,
    package: { id: 7, applicationUuid: 'exact', packageDigest: 'original' }, commands: [{ body: { expectedBuildDigest: 'original' }, outcome: 'unknown' }] };
  const original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const mutate of [x => x.package.id = 8, x => x.package.packageDigest = 'other', x => x.preexistingIds.push(7), x => x.commands[0].body.expectedBuildDigest = 'other', x => x.applicationUuid = 'other', x => x.imports = [{ outcome: 'unknown' }]]) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
  }
});
