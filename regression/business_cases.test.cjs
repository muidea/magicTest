const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execute, cleanup, inputDigest, installationMatches, receiptMatches, receiptRequest, reconcile } = require('./business_cases.cjs');
function fixture() {
  const actor = { origin: 'https://tenant.test', identity: { account: 'ordinary', namespace: 'tenant' }, subject: 'account:3' };
  const identity = { namespace: 'tenant', deploymentId: 'a'.repeat(32), installationId: '9007199254740991', runtimeApplicationUuid: 'runtime', generation: 1, executionEpoch: 2, artifactDigest: 'sha256:' + 'b'.repeat(64) };
  const body = { apiVersion: 'magic.entity-value-write/v1', operationId: 'c'.repeat(32), identity, entity: '/example/item', operation: 'create', id: '', expectedVersion: '', fields: [{ name: 'name', value: '<>&\u2028' }] };
  const r = { actorIdentity: structuredClone(actor.identity), origin: actor.origin, actorRole: 'manager', identity, applicationKey: 'fixture', commands: [], phase: 'intent' };
  let writes = 0;
  const h = { deliveryActors: { manager: actor }, Blocked: Error, persist() {}, async api() { writes++; throw Error('original response lost'); } };
  return { actor, body, r, h, writes: () => writes };
}
test('business command retains original stable identity after response loss and never executes or cleans by guessing', async () => {
  const f = fixture(); await assert.rejects(execute(f.h, f.actor, f.r, f.body), /original response lost/);
  assert.equal(f.r.commands[0].outcome, 'unknown'); assert.equal(f.r.commands[0].body.operationId, f.body.operationId);
  await assert.rejects(execute(f.h, f.actor, f.r, f.body), /no execute replay/);
  await assert.rejects(cleanup(f.h, f.r), /no execute replay/); assert.equal(f.writes(), 1);
});
test('business execution refuses a changed original principal before any owner command', async () => {
  const f = fixture(); f.actor.identity.account = 'other';
  await assert.rejects(execute(f.h, f.actor, f.r, f.body), /actor remains unresolved/); assert.equal(f.writes(), 0);
});
test('business digest uses the same immutable intent for cancel and execute and refuses rounded installation identities', () => {
  const f = fixture(); assert.equal(inputDigest(f.body), inputDigest({ ...f.body, cancel: true }));
  assert.notEqual(inputDigest(f.body), inputDigest({ ...f.body, fields: [{ name: 'name', value: 'other' }] }));
  assert.throws(() => inputDigest({ ...f.body, identity: { ...f.body.identity, installationId: '9007199254740993' } }), /exact numeric digest budget/);
});
test('runtime fence binds the installed artifact and source revision independently of the definition digest', () => {
  const f = { revision: { id: 12, digest: 'definition' }, package: { sourceRevisionId: 12, artifactDigest: 'artifact' } };
  const instance = { id: 34, deploymentId: 'deployment', receipt: { revisionId: 12, revisionDigest: 'artifact', runtimeApplicationUuid: 'runtime' } };
  const identity = { installationId: '34', deploymentId: 'deployment', namespace: 'panel', runtimeApplicationUuid: 'runtime', artifactDigest: 'artifact' };
  assert.equal(installationMatches(f, instance, identity), true);
  assert.equal(installationMatches(f, instance, { ...identity, artifactDigest: 'definition' }), false);
  assert.equal(installationMatches(f, { ...instance, receipt: { ...instance.receipt, revisionId: 13 } }, identity), false);
});
test('durable receipt subject includes the original namespace and cannot match a bare account or foreign tenant', () => {
  const f = fixture(); f.actor.subject = 'tenant/account:3';
  const receipt = { ...f.body, inputDigest: inputDigest(f.body), subject: 'tenant/account:3', id: '8', version: '1' };
  assert.equal(receiptMatches(f.actor, f.body, receipt), true);
  for (const subject of ['account:3', 'foreign/account:3']) assert.equal(receiptMatches(f.actor, f.body, { ...receipt, subject }), false);
});
test('original reconciliation refuses ambiguous commands or changed actor without querying or executing', async () => {
  const f = fixture(); f.r.commands = [0, 1].map(() => ({ body: f.body, outcome: 'unknown' }));
  await assert.rejects(reconcile(f.h, f.r), /exactly the original/);
  f.r.commands.pop(); f.actor.identity.namespace = 'foreign';
  await assert.rejects(reconcile(f.h, f.r), /actor changed/); assert.equal(f.writes(), 0);
});
test('receipt lookup omits the execution cancellation flag while preserving the complete immutable intent', () => {
  const { body } = fixture(), cancel = { ...body, cancel: true }, lookup = receiptRequest(cancel);
  assert.deepEqual(lookup, body); assert.equal(cancel.cancel, true); assert.equal(inputDigest(lookup), inputDigest(cancel));
});
test('unresolved instance debug write preserves original business record without issuing cleanup commands', async () => {
  const f = fixture(); f.r.debugCommands = [{ outcome: 'unknown' }];
  await assert.rejects(cleanup(f.h, f.r), /instance debug write result remains unresolved/);
  assert.equal(f.writes(), 0);
});
