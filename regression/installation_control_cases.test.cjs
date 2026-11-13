const { test } = require('node:test');
const assert = require('node:assert/strict');
const { control } = require('./installation_control_cases.cjs');
async function probe(mode) {
  let sends = 0;
  const admin = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://owner.test' };
  const before = { id: 7, status: 'ready', updateTime: 11, deploymentVersion: 1, sourceDigest: 'sha256:original', deploymentId: 'original',
    receipt: { database: { bindingId: 41 }, runtimeApplicationUuid: 'original-runtime' } };
  const r = { creation: { ownershipConfirmed: true, actorIdentity: structuredClone(admin.identity), origin: admin.origin }, installation: before, commands: [] };
  const after = { ...structuredClone(before), status: 'disabled', updateTime: 12, disabledAt: 12, reason: 'Current-run original installation disable', deploymentVersion: 2 };
  const h = { admin, Blocked: Error, persist() {}, good: v => v?.status === 200 && !v.data.error,
    check: (message, value) => assert.ok(value, message), async ok() {
      const value = structuredClone(sends ? after : before);
      if (!sends && mode === 'projection-forward') value.deploymentVersion = 2;
      if (!sends && mode === 'projection-backward') value.deploymentVersion = 0;
      if (!sends && mode === 'owner-changed') value.updateTime++;
      return { value };
    },
    async api() { sends++; if (mode === 'lost') throw Error('Response lost');
      const value = structuredClone(after); delete value.deploymentVersion;
      if (mode === 'foreign') value.deploymentId = 'foreign';
      if (mode === 'actor') admin.identity.account = 'other';
      return { status: 200, data: { value } }; } };
  if (['projection-backward', 'owner-changed'].includes(mode)) {
    await assert.rejects(control(h, r, 'disable'), /installation changed/);
    assert.equal(sends, 0); assert.equal(r.scenarioCommands, undefined); return;
  }
  if (mode === 'valid' || mode === 'projection-forward') {
    await control(h, r, 'disable'); assert.deepEqual(r.installation, after); assert.equal(r.scenarioCommands[0].outcome, 'confirmed');
  } else {
    await assert.rejects(control(h, r, 'disable')); assert.equal(r.scenarioCommands[0].outcome, 'unknown');
    await assert.rejects(control(h, r, 'activate'), /unresolved/); assert.deepEqual(r.installation, before);
  }
  assert.equal(sends, 1);
}
test('conditional lifecycle confirms exact original acknowledgement and full independent owner', async () => probe('valid'));
test('aggregate projection advancement permits exact current installation but rollback and owner changes block before dispatch', async () => {
  for (const mode of ['projection-forward', 'projection-backward', 'owner-changed']) await probe(mode);
});
test('lost acknowledgement, foreign deployment or changed original actor retains unknown command and forbids replay', async () => {
  for (const mode of ['lost', 'foreign', 'actor']) await probe(mode);
});
test('activation accepts public omitted zero timestamp but rejects retained, null or malformed disable facts', () => {
  const { confirms } = require('./installation_control_cases.cjs');
  const before = { id: 7, status: 'disabled', updateTime: 11, disabledAt: 11,
    receipt: { database: { bindingId: 41 }, runtimeApplicationUuid: 'original-runtime' } };
  const h = { good: r => r.status === 200 && !r.data.error };
  for (const disabledAt of [undefined, 0, 11, null, '0', false]) {
    const after = { ...structuredClone(before), status: 'ready', updateTime: 12, activatedAt: 12, reason: 'activate' };
    if (disabledAt === undefined) delete after.disabledAt;
    else after.disabledAt = disabledAt;
    const command = { action: 'activate', body: { reason: 'activate' }, response: { status: 200, data: { value: structuredClone(after) } } };
    assert.equal(confirms(h, before, command, after), disabledAt === undefined || disabledAt === 0);
    command.response.data.value.receipt.database.bindingId = 42;
    assert.equal(confirms(h, before, command, after), false);
  }
});
