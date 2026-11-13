// Explicitly browser-free tool tests. Owner substitutes test assertion and
// journal safeguards only; they do not count as platform recovery acceptance.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const recovery = require('./storage_recovery_cases.cjs');
const review = require('./deployment_review_cases.cjs');
const scenario = require('./scenario_commands.cjs');
const business = require('./business_cases.cjs');
function fixture() {
  const admin = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://owner.test' };
  const source = { id: 11, namespace: 'panel', deploymentId: 'deployment', applicationUuid: 'app-uuid', applicationKey: 'app',
    instanceKey: 'original-instance', instanceName: 'Original name', sourceDigest: 'sha256:original', status: 'ready', runtimeType: 'model',
    updateTime: 10, deploymentVersion: 2, receipt: { database: { provisioningMode: 'allocate', bindingId: 41, schemaResourceId: 42, databaseResourceId: 43 } } };
  const retirement = { operationId: 'retain:11', profile: { installationId: 11 } };
  const retained = { ...structuredClone(source), status: 'uninstalled', updateTime: 20, deploymentVersion: 3 };
  retained.receipt.uninstallation = { dataDisposition: 'retain', recoveryStatus: 'available', authorization: { confirmed: true, intent: retirement },
    startedAt: 15, finishedAt: 20, reason: 'Current-run original storage retention', completedSteps: ['database-finalized'] };
  const claimed = structuredClone(retained); claimed.updateTime = 30; delete claimed.deploymentVersion;
  Object.assign(claimed.receipt.uninstallation, { recoveryStatus: 'claimed', claimedByInstallationId: 12 });
  const target = { ...structuredClone(source), id: 12, previousInstallationId: 11, updateTime: 31, deploymentVersion: 4, operationId: 'deployment:23' };
  target.receipt.deploymentOperationId = 23;
  Object.assign(target.receipt.database, { provisioningMode: 'restore', recoveryDeploymentId: 'deployment', expectedResourceVersion: 20 });
  target.receipt.authorizationRestore = { confirmed: true, intent: { sourceInstallationId: 11, installationId: 12, operationId: 'deployment:23',
    resourceVersion: 20, profile: { installationId: 12 }, retirement: structuredClone(retirement) } };
  const identity = { namespace: 'panel', deploymentId: 'deployment', installationId: '11', runtimeApplicationUuid: 'runtime', artifactDigest: 'sha256:original', generation: 1, executionEpoch: 1 };
  const creation = { ownershipConfirmed: true, outcome: 'accepted', origin: admin.origin, actorIdentity: structuredClone(admin.identity), intended: {} };
  const f = { application: { uuid: 'app-uuid', name: 'app' }, package: { id: 1, sourceRevisionId: 2, artifactDigest: 'sha256:original' }, revision: { id: 2 } };
  target.receipt.revisionId = 2; target.receipt.revisionDigest = f.package.artifactDigest; target.receipt.runtimeApplicationUuid = 'runtime-new';
  const r = { id: 21, kind: 'deployment-review-request', phase: 'created', installation: structuredClone(source), creation, commands: [],
    storageRecovery: { phase: 'prepared', source: structuredClone(source), origin: admin.origin, actorIdentity: structuredClone(admin.identity),
      definitionId: 7, requestIds: [21, 22], installationIds: ['11', '13'], commands: [], fixture: f } };
  let sends = 0, reads = 0, current = source;
  const h = { admin, state: { resources: [r] }, Blocked: Error, persist() {}, observe() {},
    good: r => r?.status === 200 && !r.data?.error,
    check: (message, value) => assert.ok(value, message),
    async ok(_actor, _method, route) { reads++; return { value: structuredClone(current) }; },
    async api(_actor, method, route, body) {
      sends++; assert.equal(r.storageRecovery.commands.at(-1).outcome, 'unknown'); assert.equal(r.storageRecovery.phase, 'retaining');
      assert.equal(method, 'POST'); assert.equal(route, '/panel/application/installations/11/uninstall');
      assert.equal(body.dataDisposition, 'retain'); current = retained;
      const ack = structuredClone(retained); delete ack.deploymentVersion;
      return { status: 200, data: { value: ack } };
    } };
  return { h, r, f, source, retained, claimed, target, identity, sends: () => sends, reads: () => reads, setCurrent: v => current = v };
}
function command(f) { const ack = structuredClone(f.retained); delete ack.deploymentVersion; return { method: 'POST',
  route: '/panel/application/installations/11/uninstall', body: { expectedUpdateTime: 10, expectedDigest: 'sha256:original', dataDisposition: 'retain',
    confirmation: 'app', reason: 'Current-run original storage retention' }, response: { status: 200, data: { value: ack } } }; }
test('retain confirms exact acknowledged original command, binding and independent owner; repeat never dispatches', async () => {
  const f = fixture(); await recovery.retain(f.h, f.r);
  assert.equal(f.r.storageRecovery.phase, 'retained'); assert.equal(f.r.storageRecovery.commands[0].outcome, 'confirmed');
  assert.deepEqual(f.r.installation, f.source); // Original installed fact is never overwritten.
  await assert.rejects(recovery.retain(f.h, f.r), /already dispatched/); assert.equal(f.sends(), 1);
});
test('retain confirmation rejects destroyed/claimed/partial receipts and unrelated identity or changed exact intent', () => {
  const f = fixture(), c = command(f); assert.equal(recovery.retainMatches(f.h, f.source, c, f.retained), true);
  for (const alter of [v => v.id++, v => v.instanceKey = 'other', v => v.instanceName = 'other', v => v.sourceDigest = 'other',
    v => v.receipt.database.bindingId++, v => v.receipt.uninstallation.dataDisposition = 'destroy',
    v => v.receipt.uninstallation.recoveryStatus = 'claimed', v => v.receipt.uninstallation.claimedByInstallationId = 12,
    v => v.receipt.uninstallation.failedStep = 'database-finalized', v => v.receipt.uninstallation.finishedAt = 0,
    v => v.receipt.uninstallation.authorization.confirmed = false, v => v.updateTime = 10, v => v.deploymentVersion = 1]) {
    const after = structuredClone(f.retained); alter(after);
    const changed = command(f); changed.response.data.value = structuredClone(after); delete changed.response.data.value.deploymentVersion;
    assert.equal(recovery.retainMatches(f.h, f.source, changed, after), false);
  }
  for (const alter of [v => v.body.expectedUpdateTime++, v => v.body.expectedDigest = 'foreign', v => v.body.dataDisposition = 'destroy',
    v => v.body.confirmation = 'peer', v => v.route = '/panel/application/installations/12/uninstall', v => v.method = 'DELETE']) {
    const changed = command(f); alter(changed); assert.equal(recovery.retainMatches(f.h, f.source, changed, f.retained), false);
  }
});
test('lost retain reply, foreign ack or actor drift leaves original unknown and blocks generic destroy or replay', async () => {
  for (const mode of ['lost', 'foreign', 'actor']) {
    const f = fixture(), api = f.h.api;
    f.h.api = async (...args) => { const response = await api(...args);
      if (mode === 'lost') throw Error('lost reply');
      if (mode === 'foreign') response.data.value.deploymentId = 'other';
      if (mode === 'actor') f.h.admin.identity.account = 'other';
      return response;
    };
    await assert.rejects(recovery.retain(f.h, f.r));
    assert.equal(f.r.storageRecovery.commands[0].outcome, 'unknown');
    await assert.rejects(recovery.retain(f.h, f.r), /unresolved/);
    await assert.rejects(review.cleanup(f.h, f.r), /lineage/);
    assert.equal(f.sends(), 1); assert.equal(f.r.phase, 'created');
  }
});
test('concurrent original installation mutation and mismatched admin block retain before any mutation', async () => {
  for (const mode of ['mutation', 'actor', 'owner']) {
    const f = fixture();
    if (mode === 'mutation') f.setCurrent({ ...f.source, updateTime: 11 });
    if (mode === 'actor') f.h.admin.origin = 'https://other.test';
    if (mode === 'owner') f.r.creation.ownershipConfirmed = false;
    await assert.rejects(recovery.retain(f.h, f.r)); assert.equal(f.sends(), 0);
  }
});
test('available recovery selection requires unique exact original point and resource version', () => {
  const f = fixture(), point = { deploymentId: 'deployment', applicationUuid: 'app-uuid', applicationKey: 'app', sourceDigest: 'sha256:original',
    uninstalledAt: 20, resourceVersion: 20, recoveryStatus: 'available' };
  assert.equal(recovery.pointMatches(f.retained, [point, { ...point, deploymentId: 'peer' }]), true);
  for (const points of [[], [point, point], [{ ...point, resourceVersion: 19 }], [{ ...point, applicationUuid: 'peer' }],
    [{ ...point, recoveryStatus: 'claimed' }], [{ ...point, sourceDigest: 'other' }]]) assert.equal(recovery.pointMatches(f.retained, points), false);
});
test('restore is created with original key/version, journalled and never re-created after lost create acknowledgement', async () => {
  const f = fixture(), j = f.r.storageRecovery;
  j.phase = 'retained'; j.retained = f.retained; f.setCurrent(f.retained);
  f.f.resource = { modelDelivery: { requests: [] } };
  const point = { deploymentId: 'deployment', applicationUuid: 'app-uuid', applicationKey: 'app', sourceDigest: 'sha256:original',
    uninstalledAt: 20, resourceVersion: 20, recoveryStatus: 'available' };
  f.h.ok = async (_a, _m, route) => ({ value: route.includes('storage-options') ? { recoveryPoints: [point] } : f.retained });
  let creates = 0;
  f.h.create = async (_route, body) => {
    creates++; assert.equal(j.phase, 'restoring'); assert.equal(body.instanceKey, f.source.instanceKey);
    assert.equal(body.instanceName, f.source.instanceName); assert.deepEqual(body.storageProvisioning, { mode: 'restore', recoveryDeploymentId: 'deployment', expectedResourceVersion: 20 });
    throw Error('lost create reply');
  };
  await assert.rejects(recovery.createRestore(f.h, f.f, f.r), /lost create reply/);
  await assert.rejects(recovery.createRestore(f.h, f.f, f.r), /no new restore intent/);
  assert.equal(creates, 1); assert.equal(j.phase, 'restoring');
});
test('shared approval confirms the original restore resource version instead of silently assuming allocate', async () => {
  for (const mode of ['restore', 'wrong-mode', 'wrong-version']) {
    const f = fixture(), r = { kind: 'deployment-review-request', id: 24, commands: [], creation: structuredClone(f.r.creation),
      last: { version: 1 } };
    r.creation.intended = { expectedDigest: 'sha256:original', storageProvisioning: { mode: 'restore', recoveryDeploymentId: 'deployment', expectedResourceVersion: 20 } };
    f.h.admin.id = 1;
    const placement = { executionInstanceId: 'base', gatewayInstanceId: 'gateway' };
    const request = { id: 24, version: 2, operationId: 23, packageId: 1, deploymentId: 'deployment', planDigest: 'plan', status: 'succeeded',
      runtimePlacement: placement, resolvedRuntimePlacement: { execution: { instanceId: 'base' }, gateway: { instanceId: 'gateway' } },
      reviewedBy: { accountId: 1, namespace: 'panel' } };
    const op = { id: 23, requestId: 24, packageId: 1, deploymentId: 'deployment', planDigest: 'plan', status: 'succeeded' };
    const installed = structuredClone(f.target);
    if (mode === 'wrong-mode') installed.receipt.database.provisioningMode = 'allocate';
    if (mode === 'wrong-version') installed.receipt.database.expectedResourceVersion++;
    f.h.ok = async (_a, _m, route) => route.endsWith('runtime-options') ? { values: [{ id: 'base', kind: 'base' }, { id: 'gateway', kind: 'gateway' }] } :
      { value: route.includes('application-deployment-operations') ? op : route.includes('installations') ? installed : request };
    f.h.directory = async (_a, route) => route.includes('application-deployment-operations') ? [op] : [installed];
    let approvals = 0;
    f.h.api = async (_a, _m, route, body) => {
      approvals++; assert.equal(route, '/panel/operations/namespaces/panel/application-deployment-requests/24/approve');
      assert.deepEqual(body.runtimePlacement, placement); return { status: 200, data: { value: request } };
    };
    if (mode === 'restore') await review.approve(f.h, r, [f.h.admin]);
    else await assert.rejects(review.approve(f.h, r, [f.h.admin]), /original selected storage intent/);
    assert.equal(approvals, 1);
  }
});
test('restoration proof binds original retained claim, successor and frozen authorization retirement', () => {
  const f = fixture(), j = f.r.storageRecovery, r = { installation: f.target, operation: { id: 23 } }; j.retained = f.retained;
  assert.equal(recovery.restoredMatches(j, r, f.claimed), true);
  for (const alter of [v => v.id = 11, v => v.previousInstallationId = 99, v => v.deploymentId = 'other',
    v => v.receipt.database.bindingId++, v => v.receipt.database.schemaResourceId++, v => v.receipt.database.expectedResourceVersion = 19,
    v => v.receipt.database.recoveryDeploymentId = 'other', v => v.receipt.authorizationRestore.confirmed = false,
    v => v.receipt.authorizationRestore.intent.sourceInstallationId++, v => v.receipt.authorizationRestore.intent.retirement.operationId = 'foreign',
    v => v.receipt.deploymentOperationId++, v => v.receipt.authorizationRestore.intent.operationId = 'foreign',
    v => delete v.deploymentVersion, v => v.deploymentVersion = 3, v => v.deploymentVersion = 2]) {
    const target = structuredClone(f.target); alter(target); assert.equal(recovery.restoredMatches(j, { ...r, installation: target }, f.claimed), false);
  }
  for (const alter of [v => v.receipt.uninstallation.claimedByInstallationId++, v => v.receipt.uninstallation.finishedAt++,
    v => v.receipt.uninstallation.authorization.intent.operationId = 'other', v => v.instanceKey = 'other', v => v.updateTime = 20, v => v.deploymentVersion = 2]) {
    const claimed = structuredClone(f.claimed); alter(claimed); assert.equal(recovery.restoredMatches(j, r, claimed), false);
  }
});
test('open lineage protects original/peer/target requests, grants and definition while unrelated fixtures stay independent', () => {
  const f = fixture(), j = f.r.storageRecovery; j.requestIds.push(24); j.installationIds.push('12');
  const protectedResources = [f.r, { kind: 'definition', id: 7 }, ...[21, 22, 24].map(id => ({ kind: 'deployment-review-request', id })),
    ...[11, 12, 13].map(id => ({ kind: 'member-access-retirement', installation: { id } }))];
  for (const phase of ['prepared', 'retaining', 'retained', 'restoring', 'restored', 'rows-disposed']) {
    j.phase = phase;
    for (const r of protectedResources) assert.throws(() => scenario.guard(f.h, r), /lineage/);
    assert.doesNotThrow(() => scenario.guard(f.h, { kind: 'definition', id: 8 }));
    assert.doesNotThrow(() => scenario.guard(f.h, { kind: 'deployment-review-request', id: 25 }));
  }
  j.phase = 'complete'; for (const r of protectedResources) assert.doesNotThrow(() => scenario.guard(f.h, r));
});
test('old business cleanup never sends under predecessor identity even if retention result is unknown', async () => {
  const f = fixture(); await assert.rejects(business.cleanup(f.h, { scenarioRecoveryRequestId: f.r.id }), /obsolete installation fence/);
  assert.equal(f.reads(), 0); assert.equal(f.sends(), 0);
});
test('successor delete retains original create identity and uses a separate exact durable intent; unknown deletion cannot replay', async t => {
  const record = business.record, execute = business.execute;
  t.after(() => { business.record = record; business.execute = execute; });
  for (const mode of ['valid', 'lost', 'foreign-row', 'foreign-target', 'actor']) {
    const f = fixture(), j = f.r.storageRecovery; j.phase = 'restored'; j.target = f.target; f.setCurrent(f.target);
    const actor = { identity: { account: 'ordinary', namespace: 'panel' }, subject: 'panel/account:3', origin: f.h.admin.origin };
    const original = { id: 99, version: 1, code: 'original', name: 'Original', description: null, sortOrder: 0 };
    const row = { scenarioRecoveryRequestId: f.r.id, identity: f.identity, entity: '/app/row', applicationKey: 'app',
      origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [{ body: { identity: structuredClone(f.identity) }, outcome: 'confirmed' }],
      recordId: '99', version: '1', phase: 'created', created: original };
    const context = { identity: { ...f.identity, installationId: '12', runtimeApplicationUuid: 'runtime-new', generation: 2, executionEpoch: 3 },
      entity: row.entity, applicationKey: 'app' };
    if (mode === 'foreign-target') context.identity.installationId = '13';
    const oldIdentity = structuredClone(row.identity), oldCommands = structuredClone(row.commands);
    let deletes = 0;
    business.record = async () => deletes && mode !== 'lost' ? { status: 404, data: { error: { code: 2 } } } :
      { status: 200, data: { value: mode === 'foreign-row' ? { ...original, code: 'foreign' } : original } };
    business.execute = async (_h, _actor, current, body) => {
      deletes++; assert.equal(row.successorDisposition, current); assert.equal(body.identity.installationId, '12');
      assert.equal(body.id, '99'); assert.equal(body.expectedVersion, '1'); assert.equal(body.operation, 'delete');
      current.commands.push({ body, outcome: 'unknown' });
      if (mode === 'lost') throw Error('lost delete acknowledgement');
      current.commands[0].outcome = 'confirmed';
      if (mode === 'actor') actor.identity.account = 'other';
    };
    if (mode === 'valid') { await recovery.disposeRow(f.h, actor, row, context, f.r); assert.equal(row.phase, 'deleted'); }
    else {
      await assert.rejects(recovery.disposeRow(f.h, actor, row, context, f.r)); assert.equal(row.phase, 'created');
      await assert.rejects(recovery.disposeRow(f.h, actor, row, context, f.r));
    }
    assert.deepEqual(row.identity, oldIdentity); assert.deepEqual(row.commands, oldCommands);
    assert.equal(deletes, ['foreign-row', 'foreign-target'].includes(mode) ? 0 : 1);
  }
});
test('predecessor cannot be disposed with an arbitrary destroyed installation or an open original row', async () => {
  for (const mode of ['foreign-target', 'open-row', 'no-destroy']) {
    const f = fixture(), j = f.r.storageRecovery; j.phase = 'rows-disposed'; j.target = f.target; j.retained = f.retained; j.claimed = f.claimed; j.restoreRequestId = 24;
    const target = { id: 24, creation: structuredClone(f.r.creation), installation: structuredClone(f.target), operation: { id: 23 }, phase: 'deleted', commands: [] };
    if (mode === 'foreign-target') target.installation.id++;
    if (mode === 'open-row') f.h.state.resources.push({ scenarioRecoveryRequestId: f.r.id, phase: 'created' });
    await assert.rejects(recovery.finishSource(f.h, f.r, target)); assert.equal(f.r.phase, 'created'); assert.equal(f.sends(), 0); assert.equal(f.reads(), 0);
  }
});
test('normal retained lineage closes only after original row disposal, exact successor destroy, recycled schema and durable history', async t => {
  const history = review.originalHistory; t.after(() => { review.originalHistory = history; });
  for (const mode of ['valid', 'source-changed', 'target-changed', 'schema-active', 'point-available', 'history-changed', 'open-row']) {
    const f = fixture(), j = f.r.storageRecovery; j.phase = 'rows-disposed'; j.target = f.target; j.retained = f.retained; j.claimed = f.claimed; j.restoreRequestId = 24;
    const retired = { ...structuredClone(f.target), status: 'uninstalled', updateTime: 40, deploymentVersion: 5 };
    retired.receipt.uninstallation = { dataDisposition: 'destroy', recoveryStatus: 'recycled', authorization: { confirmed: true }, finishedAt: 40 };
    const ack = structuredClone(retired); delete ack.deploymentVersion;
    const target = { id: 24, creation: structuredClone(f.r.creation), installation: f.target, operation: { id: 23 }, phase: 'deleted', retiredInstallation: retired,
      commands: [{ route: '/panel/application/installations/12/uninstall', outcome: 'confirmed', response: { status: 200, data: { value: ack } } }] };
    f.r.operation = { id: 25 }; f.r.last = { id: 21 };
    f.h.directory = async () => [{ id: 42, databaseResourceId: 43, status: mode === 'schema-active' ? 'active' : 'recycled' }];
    review.originalHistory = async () => mode !== 'history-changed';
    f.h.ok = async (_actor, _method, route) => {
      if (route.includes('storage-options')) return { value: { recoveryPoints: mode === 'point-available' ? [{ deploymentId: 'deployment' }] : [] } };
      const current = structuredClone(route.endsWith('/11') ? f.claimed : retired);
      if (mode === 'source-changed' && route.endsWith('/11')) current.receipt.uninstallation.claimedByInstallationId++;
      if (mode === 'target-changed' && route.endsWith('/12')) current.receipt.database.bindingId++;
      return { value: current };
    };
    if (mode === 'open-row') f.h.state.resources.push({ scenarioRecoveryRequestId: f.r.id, phase: 'created' });
    if (mode === 'valid') {
      const proof = await recovery.finishSource(f.h, f.r, target);
      assert.equal(proof.predecessorId, 11); assert.equal(proof.successorId, 12); assert.equal(f.r.phase, 'deleted'); assert.equal(j.phase, 'complete');
    } else { await assert.rejects(recovery.finishSource(f.h, f.r, target)); assert.equal(f.r.phase, 'created'); assert.equal(j.phase, 'rows-disposed'); }
    assert.equal(f.sends(), 0); // A retained predecessor is never uninstalled a second time.
  }
});
test('explicit fixture teardown skips already disposed predecessor lineage and retires only remaining peer', async t => {
  const pages = require('./page_runtime_cases.cjs'), authority = require('./application_authority_cases.cjs'), delivery = require('./model_delivery.cjs');
  const saved = { cleanup: review.cleanup, retireAccess: authority.retireAccess, retained: delivery.retained };
  t.after(() => Object.assign(review, { cleanup: saved.cleanup }));
  t.after(() => Object.assign(authority, { retireAccess: saved.retireAccess }));
  t.after(() => Object.assign(delivery, { retained: saved.retained }));
  const f = fixture(), calls = []; f.r.storageRecovery.phase = 'complete'; f.r.phase = 'deleted';
  review.cleanup = async (_h, r) => { assert.equal(r.id, 22); calls.push('peer-request'); };
  authority.retireAccess = async (_h, r) => { assert.equal(r.installation.id, 13); calls.push('peer-grant'); };
  delivery.retained = async () => { calls.push('retained-definition'); };
  await pages.disposeExplicitFixture(f.h, { pageGrants: [{ phase: 'deleted', installation: { id: 11 } }, { installation: { id: 13 } }],
    pageRequests: [f.r, { id: 22 }], resource: { kind: 'definition', id: 7 } });
  assert.deepEqual(calls, ['peer-grant', 'peer-request', 'retained-definition']);
});
