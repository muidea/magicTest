const { test } = require('node:test');
const assert = require('node:assert/strict');
const { reconcileConflict } = require('./authoring_conflict_recovery.cjs');
function fixture(mode) {
  const actor = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.test' };
  const before = { applicationId: 7, applicationUuid: 'original-uuid', definitionVersion: 21, targetDigest: 'sha256:current-target', entities: [{ id: 9, updateTime: 21, fields: [{ name: 'id' }] }], pages: {} };
  const response = { status: 200, data: { error: { code: 19, message: '模型定义已变更，请刷新后重试' }, value: null } };
  const created = { id: 7, uuid: 'original-uuid', name: 'original-definition' };
  const r = { kind: 'definition', collection: '/panel/application/definitions/', id: 7, phase: 'created', creation: { response: { data: { value: created } }, ownershipConfirmed: true, actorIdentity: structuredClone(actor.identity), origin: actor.origin },
    pendingAuthoringSave: { journalId: 'original-ui-command', route: '/panel/application/definition/entitys/9', method: 'PUT', confirmed: false, response,
      payload: { application: { id: 7 }, expectedDefinitionVersion: 20, expectedEntityVersion: 20 } } };
  const evidence = { caseId: 'F013-003', status: 'blocked', trace: [
    { kind: 'request', origin: actor.origin, actor: structuredClone(actor.identity), method: 'PUT', route: '/panel/application/definitions/7/model-draft', response: { status: 200, data: { value: before } } },
    { kind: 'assertion', message: 'Original UI write reached the expected owner outcome', passed: true, details: structuredClone(response) },
    { kind: 'browser-transport-failure', origin: actor.origin, path: '/api/v1/web/proxy/panel/application/definitions/7/model-draft', method: 'GET', error: 'net::ERR_NETWORK_CHANGED' }
  ] };
  let persisted = 0, calls = [];
  const h = { admin: actor, Blocked: Error, good: r => r.status === 200 && !r.data.error,
    check(label, condition) { assert.ok(condition, label); }, persist() { persisted++; },
    async ok(actual, method, route) {
      assert.equal(method, 'GET'); assert.equal(actual, actor); calls.push(route);
      if (mode === 'actor-changed-during-read') actor.identity.account = 'foreign';
      return { value: route.endsWith('/model-draft') ? { ...before, ...(mode === 'owner-changed' ? { targetDigest: 'foreign-target' } : {}) } : { ...created, ...(mode === 'wrong-owner' ? { uuid: 'foreign' } : {}) } };
    }
  };
  if (mode === 'wrong-actor') actor.origin = 'https://foreign.test';
  if (mode === 'wrong-stage') r.pendingAuthoringSave.response.data.error.code = 4;
  if (mode === 'missing-baseline') evidence.trace.shift();
  if (mode === 'missing-conflict') evidence.trace.splice(1, 1);
  return { h, r, evidence, calls, persisted: () => persisted };
}
test('original acknowledged stale PUT is disposed with exact immutable newer snapshot and independent owner reads, without business writes', async () => {
  const f = fixture(); const result = await reconcileConflict(f.h, f.r, f.evidence, 'sha256:' + 'a'.repeat(64));
  assert.equal(result.originalJournalId, 'original-ui-command'); assert.equal(result.noCommandReplayed, true);
  assert.equal(f.persisted(), 1); assert.equal(f.r.pendingAuthoringSave.confirmed, true); assert.equal(f.calls.length, 2);
});
for (const mode of ['owner-changed', 'wrong-owner', 'wrong-actor', 'wrong-stage', 'missing-baseline', 'missing-conflict', 'actor-changed-during-read']) test('original conflict ' + mode + ' cannot be disposed', async () => {
  const f = fixture(mode); await assert.rejects(reconcileConflict(f.h, f.r, f.evidence, 'sha256:' + 'a'.repeat(64)));
  assert.equal(f.persisted(), 0); assert.equal(f.r.pendingAuthoringSave.confirmed, false);
});
