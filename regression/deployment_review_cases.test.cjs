const { test } = require('node:test');
const assert = require('node:assert/strict');
const { cleanup, rejectUnchanged, refusal, destroyConfirmed, reviewConflict, reconcileGuard } = require('./deployment_review_cases.cjs');
test('terminal history permits only declared clock-dependent diagnostic projection drift', () => {
  const { successfulOperationFactsMatch } = require('./deployment_review_cases.cjs');
  const before = { id: 7, requestId: 7, status: 'succeeded', version: 9, attempt: 1, maxAttempts: 3,
    receiptRef: 'installation:11', planDigest: 'original', updateTime: 10, executionResumeMode: 'forward' };
  const after = { ...before, executionResumeMode: 'cleanup-required' };
  assert.equal(successfulOperationFactsMatch(before, after), true);
  assert.equal(before.executionResumeMode, 'forward');
  for (const alter of [v => { v.id++; }, v => { v.requestId++; }, v => { v.version++; }, v => { v.attempt++; },
    v => { v.maxAttempts++; }, v => { v.receiptRef = 'installation:12'; }, v => { v.planDigest = 'other'; },
    v => { v.updateTime++; }, v => { v.status = 'failed'; }, v => { v.executionResumeMode = 'unknown'; },
    v => { delete v.executionResumeMode; }, v => { v.extra = true; }]) {
    const changed = structuredClone(after); alter(changed);
    assert.equal(successfulOperationFactsMatch(before, changed), false);
  }
  for (const status of ['running', 'failed', 'cancelled']) assert.equal(successfulOperationFactsMatch({ ...before, status }, { ...after, status }), false);
});
test('uninstall snapshot accepts only monotone read-projection version with every original resource fact unchanged', () => {
  const { installationUnchanged } = require('./deployment_review_cases.cjs');
  const before = { id: 7, deploymentId: 'original', deploymentVersion: 7, updateTime: 10, status: 'ready', sourceDigest: 'digest', receipt: { database: { bindingId: 1 } } };
  assert.equal(installationUnchanged(before, { ...before, deploymentVersion: 9 }), true);
  for (const alter of [v => { v.deploymentVersion = 6; }, v => { delete v.deploymentVersion; }, v => { v.deploymentId = 'other'; }, v => { v.updateTime++; }, v => { v.status = 'disabled'; }, v => { v.sourceDigest = 'other'; }, v => { v.receipt.database.bindingId = 2; }]) {
    const after = structuredClone(before); alter(after); assert.equal(installationUnchanged(before, after), false);
  }
});
test('historical predecessor reads require exact facts and no current deployment projection', () => {
  const { historicalInstallationUnchanged, installationUnchanged } = require('./deployment_review_cases.cjs');
  const before = { id: 7, deploymentId: 'original', status: 'disabled', updateTime: 10,
    receipt: { upgrade: { targetInstallationId: 8, phase: 'completed' }, database: { bindingId: 1 } } };
  assert.equal(historicalInstallationUnchanged(before, structuredClone(before)), true);
  assert.equal(installationUnchanged(before, before), false, 'historical reads cannot substitute for the current version fence');
  for (const alter of [v => { v.deploymentVersion = 11; }, v => { v.id++; }, v => { v.deploymentId = 'other'; },
    v => { v.updateTime++; }, v => { v.receipt.upgrade.targetInstallationId++; }, v => { v.receipt.database.bindingId++; },
    v => { v.extra = true; }]) {
    const changed = structuredClone(before); alter(changed);
    assert.equal(historicalInstallationUnchanged(before, changed), false);
  }
  assert.equal(historicalInstallationUnchanged({ ...before, deploymentVersion: 11 }, before), false);
  assert.equal(historicalInstallationUnchanged(undefined, before), false);
});
function fixture() {
  const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.test';
  const value = { id: 7, version: 1, status: 'submitted', deploymentId: 'exact' };
  const r = { id: 7, commands: [], last: structuredClone(value), phase: 'created', creation: { ownershipConfirmed: true, outcome: 'accepted', actorIdentity: identity, origin } };
  let writes = 0, reads = 0;
  const h = { admin: { identity: structuredClone(identity), origin }, Blocked: Error, persist() {},
    good: x => x.status === 200 && !x.data.error, check(label, condition) { assert.ok(condition, label); },
    async directory() { return [structuredClone(value)]; },
    async ok() { reads++; return { value: structuredClone(value) }; },
    async api() { writes++; return { status: 409, data: { error: { code: 21, message: 'exact state guard' }, value: null } }; } };
  return { h, r, value, writes: () => writes, reads: () => reads };
}
test('pending authorization uninstall refusal requires exact original linked intent and unchanged owner before a new conditional cleanup', async () => {
  for (const mode of ['exact', 'changed', 'foreign-link', 'wrong-error']) {
    const f = fixture(), installed = { id: 9, deploymentId: 'exact', status: 'ready', updateTime: 10, sourceDigest: 'digest', applicationKey: 'app', deploymentVersion: 2 };
    f.r.installation = installed;
    f.r.last.operationId = 7;
    const command = { outcome: 'unknown', route: '/panel/application/installations/9/uninstall', origin: f.h.admin.origin, actorIdentity: f.h.admin.identity,
      body: { expectedUpdateTime: 10, expectedDigest: 'digest', dataDisposition: 'destroy', confirmation: 'app' },
      response: { status: 409, data: { error: { code: 19, message: 'unfinished authorization operation blocks this change: /panel/application/accessOperation' } } } };
    f.r.commands.push(command);
    f.h.state = { resources: [{ kind: 'member-access-retirement', origin: f.h.admin.origin, actorIdentity: f.h.admin.identity,
      installation: { id: mode === 'foreign-link' ? 10 : 9 }, assignmentId: 4, commands: [{ body: { accessLevel: '', assignmentId: 4 },
        response: { data: { value: { installationId: 9 } } }, execution: { response: { status: 409, data: { error: { code: 19, message: 'application lifecycle changed before commit' } } } } }] }] };
    f.h.ok = async (_a, _m, route) => ({ value: route.includes('installations') ? { ...installed, updateTime: mode === 'changed' ? 11 : 10 } : f.r.last });
    if (mode === 'wrong-error') command.response.data.error.message = 'different';
    // Stop at the next normal teardown gate; classification itself sends no write.
    f.h.api = async () => { throw Error('next independent cleanup command'); };
    await assert.rejects(cleanup(f.h, f.r));
    assert.equal(command.outcome, mode === 'exact' ? 'rejected-before-intent' : 'unknown');
  }
});
test('cleanup guard needs target state refusal and complete unchanged directories; auth or concurrent writes cannot pass', async () => {
  const positive = fixture(); await rejectUnchanged(positive.h, positive.r, '/panel/application/deployment-requests/7/cleanup', 'exact state guard');
  assert.equal(positive.r.commands[0].outcome, 'rejected-and-unchanged');
  for (const mode of ['auth', 'state', 'lost']) {
    const f = fixture();
    if (mode === 'auth') f.h.api = async () => ({ status: 401, data: { error: { code: 11 }, value: null } });
    if (mode === 'state') { let calls = 0; f.h.directory = async () => [{ id: ++calls }]; }
    if (mode === 'lost') f.h.api = async () => { throw Error('lost original reply'); };
    await assert.rejects(rejectUnchanged(f.h, f.r, '/panel/application/deployment-requests/7/cleanup', 'exact state guard'));
    assert.equal(f.r.commands[0].outcome, 'unknown');
    await assert.rejects(cleanup(f.h, f.r), /no replay/);
  }
});
test('unresolved original review or changed identity blocks every teardown read and mutation', async () => {
  for (const alter of [f => f.r.commands.push({ outcome: 'unknown' }), f => f.h.admin.identity.account = 'other', f => f.r.creation.ownershipConfirmed = false]) {
    const f = fixture(); alter(f); await assert.rejects(cleanup(f.h, f.r), /no replay/);
    assert.equal(f.reads(), 0); assert.equal(f.writes(), 0); assert.equal(f.r.phase, 'created');
  }
});
test('unapproved request changed by another reviewer is retained without cancellation', async () => {
  const f = fixture(); f.value.version++;
  await assert.rejects(cleanup(f.h, f.r), /changed concurrently/);
  assert.equal(f.writes(), 0);
});
test('original installed fixture with a concurrent edit cannot be destroyed', async () => {
  const f = fixture(); f.value.operationId = 7; f.r.installation = { id: 9, status: 'ready', deploymentId: 'exact', updateTime: 1 };
  f.h.ok = async (_actor, _method, route) => ({ value: route.includes('installations') ? { ...f.r.installation, updateTime: 2 } : f.value });
  await assert.rejects(cleanup(f.h, f.r), /changed before formal destroy/);
  assert.equal(f.writes(), 0);
});
test('state refusal matcher does not accept authorization, unrelated guard or ambiguous value', () => {
  assert.ok(refusal({ status: 409, data: { error: { code: 21, message: 'guard' }, value: null } }, 'guard'));
  for (const response of [{ status: 401, data: { error: { code: 21, message: 'guard' }, value: null } },
    { status: 409, data: { error: { code: 21, message: 'different' }, value: null } },
    { status: 409, data: { error: { code: 21, message: 'guard' }, value: { id: 1 } } }]) assert.equal(refusal(response, 'guard'), false);
});

test('destroy confirmation accounts only for the read projection field and preserves retirement semantics', () => {
  const f = fixture(), installed = { id: 9, deploymentId: 'exact', sourceDigest: 'digest' };
  const value = { ...installed, status: 'uninstalled', receipt: { uninstallation: { authorization: { confirmed: true, intent: { requestKey: 'original' } }, dataDisposition: 'destroy', finishedAt: 3, recoveryStatus: 'recycled' } } };
  const c = { response: { status: 200, data: { value: structuredClone(value) } } }, current = { ...structuredClone(value), deploymentVersion: 11 };
  assert.ok(destroyConfirmed(f.h, c, current, installed));
  for (const mutate of [v => v.receipt.uninstallation.authorization.confirmed = false, v => v.deploymentId = 'peer', v => v.receipt.uninstallation.failedStep = 'database-finalized', v => v.receipt.uninstallation.recoveryStatus = 'available', v => v.receipt.uninstallation.finishedAt = 0]) {
    const changed = structuredClone(current); mutate(changed); assert.equal(destroyConfirmed(f.h, c, changed, installed), false);
  }
});
test('concurrent review accepts only the exact control-lock or terminal state conflict, never arbitrary HTTP409', () => {
  for (const message of ['application deployment request cannot be reviewed', 'application lifecycle is busy; refresh before retrying']) assert.ok(reviewConflict({ status: 409, data: { error: { code: 21, message }, value: null } }));
  assert.equal(reviewConflict({ status: 409, data: { error: { code: 21, message: 'a different error' }, value: null } }), false);
});
test('old cleanup refusal can be disposed only with unchanged exact successful target version', async () => {
  const f = fixture(); f.r.last.operationId = 7; f.r.last.status = 'succeeded'; f.r.last.planDigest = 'plan';
  f.r.commands.push({ route: '/panel/operations/namespaces/panel/application-deployment-operations/7/cleanup', body: { expectedVersion: 3 }, outcome: 'unknown', response: { status: 409, data: { error: { code: 21, message: 'only a fully cancelled deployment operation without an installation receipt can be cleaned' }, value: null } } });
  const op = { id: 7, requestId: 7, deploymentId: 'exact', planDigest: 'plan', status: 'succeeded', version: 4 };
  f.h.ok = async (_a, _m, route) => ({ value: structuredClone(route.includes('application-deployment-operations') ? op : f.r.last) });
  await assert.rejects(reconcileGuard(f.h, f.r)); assert.equal(f.r.commands[0].outcome, 'unknown'); assert.equal(f.writes(), 0);
  op.version = 3; await reconcileGuard(f.h, f.r); assert.equal(f.r.phase, 'deleted'); assert.equal(f.writes(), 0);
});
test('separate public request and operation reads can cross completion without inventing a failed delivery', async () => {
  const { settle } = require('./deployment_review_cases.cjs'), f = fixture(); let requestReads = 0;
  const request = { id: 7, operationId: 7, packageId: 3, deploymentId: 'exact', planDigest: 'plan', status: 'succeeded' };
  const op = { id: 7, requestId: 7, packageId: 3, deploymentId: 'exact', planDigest: 'plan', status: 'succeeded' };
  const installed = { id: 9, deploymentId: 'exact', sourceDigest: 'digest', status: 'ready' };
  f.r.creation.intended = { expectedDigest: 'digest' };
  f.h.ok = async (_a, _m, route) => ({ value: route.includes('installations') ? installed : route.includes('application-deployment-operations') ? op : { ...request, status: ++requestReads === 1 ? 'executing' : 'succeeded' } });
  f.h.directory = async () => [installed];
  await settle(f.h, f.r); assert.equal(requestReads, 2); assert.equal(f.r.last.status, 'succeeded'); assert.equal(f.writes(), 0);
});

test('removed model source history needs exact original package deletion and unchanged delivery, not an ignored field set', async () => {
  const { originalHistory, removedSourceRequest } = require('./deployment_review_cases.cjs');
  for (const mode of ['confirmed', 'missing-owner', 'wrong-actor', 'unconfirmed-delete', 'wrong-delete-digest', 'request-version', 'request-plan', 'source-identity', 'operation-changed', 'package-present', 'revision-changed', 'missing-parent', 'duplicate-parent']) {
    const actor = { origin: 'https://panel.test', identity: { account: 'author', namespace: 'panel' } };
    const pkg = { id: 31, sourceRevisionId: 3, applicationUuid: 'owned', applicationKey: 'app', packageDigest: 'sha256:zip', artifactDigest: 'sha256:artifact', createdBy: { accountId: 1 }, createTime: 100, updateTime: 100 };
    const revision = { id: 3, applicationDefinitionId: 7, applicationUuid: 'owned', content: { pages: [] } };
    const deletion = { outcome: 'confirmed', method: 'DELETE', route: '/panel/application/model-packages/31', origin: actor.origin, actorIdentity: structuredClone(actor.identity), before: structuredClone(pkg), preview: { allowed: true, packageId: 31, sourceDigest: pkg.packageDigest }, response: { status: 200, data: { value: {} } }, absence: { status: 404, data: { error: { code: 2 } } }, directoryAbsent: true };
    const parent = { kind: 'definition', id: 7, creation: { ownershipConfirmed: true, origin: actor.origin, actorIdentity: structuredClone(actor.identity), intended: { uuid: 'owned' } }, modelDelivery: { package: pkg, revision, requests: [11], packageDisposition: deletion } };
    const r = { id: 11, last: { id: 11, version: 4, status: 'succeeded', sourceKind: 'model-package', packageId: 31, packageRemoved: false, modelPackage: structuredClone(pkg), planDigest: 'original' }, operation: { id: 12, version: 7, status: 'succeeded' } };
    const before = structuredClone(r.last), current = removedSourceRequest(before), operation = structuredClone(r.operation), resources = [parent];
    if (mode === 'missing-owner') parent.creation.ownershipConfirmed = false;
    if (mode === 'wrong-actor') parent.creation.actorIdentity.account = 'other';
    if (mode === 'unconfirmed-delete') deletion.outcome = 'unknown';
    if (mode === 'wrong-delete-digest') deletion.preview.sourceDigest = 'foreign';
    if (mode === 'request-version') current.version++;
    if (mode === 'request-plan') current.planDigest = 'foreign';
    if (mode === 'source-identity') current.modelPackage.applicationUuid = 'foreign';
    if (mode === 'operation-changed') operation.version++;
    if (mode === 'missing-parent') resources.pop();
    if (mode === 'duplicate-parent') resources.push(structuredClone(parent));
    let reads = 0;
    const h = { admin: actor, state: { resources }, persist() {}, good: r => r.status === 200 && !r.data.error,
      async api(a, method, route) { assert.equal(a, actor); assert.equal(method, 'GET'); assert.equal(route, '/panel/application/model-packages/31'); reads++; return mode === 'package-present' ? { status: 200, data: { value: pkg } } : deletion.absence; },
      async ok(a, method, route) { assert.equal(a, actor); assert.equal(method, 'GET'); assert.equal(route, '/panel/application/definitions/7/revisions/3'); reads++; return { value: mode === 'revision-changed' ? { ...revision, content: {} } : revision }; }
    };
    assert.equal(await originalHistory(h, r, current, operation), mode === 'confirmed', mode);
    assert.deepEqual(r.last, before, 'original successful request is never rewritten');
    if (mode === 'confirmed') { assert.equal(r.sourceRemovalHistoryProof.noCommandReplayed, true); assert.equal(reads, 2); }
    else assert.equal(r.sourceRemovalHistoryProof, undefined);
  }
});
