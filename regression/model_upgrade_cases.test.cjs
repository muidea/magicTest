const test = require('node:test');
const assert = require('node:assert/strict');
const upgrade = require('./model_upgrade_cases.cjs');
const business = require('./business_cases.cjs');
const { cleanup } = require('./deployment_review_cases.cjs');
const { guard } = require('./scenario_commands.cjs');
function fixture() {
  const admin = { origin: 'https://owner.invalid', identity: { account: 'original', namespace: 'panel' } };
  const source = { id: 11, namespace: 'panel', deploymentId: 'deployment', applicationUuid: 'app', applicationKey: 'app', instanceKey: 'original', instanceName: 'original name',
    sourceDigest: 'sha256:' + 'a'.repeat(64), status: 'ready', updateTime: 10, deploymentVersion: 2,
    receipt: { database: { bindingId: 41, schemaResourceId: 42, databaseResourceId: 43 }, runtimeApplicationUuid: 'old-runtime' } };
  const f = { application: { uuid: 'app', name: 'app' }, package: { id: 2, artifactDigest: 'sha256:' + 'b'.repeat(64), sourceRevisionId: 21 }, revision: { id: 21, version: 2 } };
  const preview = { sourceInstallationId: 11, sourceInstallationVersion: 10, deploymentVersion: 2, sourceDigest: source.sourceDigest,
    targetPackageId: 2, targetDigest: f.package.artifactDigest, sourceVersion: 1, targetVersion: 2, deploymentId: source.deploymentId,
    instanceKey: source.instanceKey, instanceName: source.instanceName, previewDigest: 'sha256:' + 'c'.repeat(64), schemaDigest: 'sha256:' + 'd'.repeat(64), maintenanceRequired: true };
  const r = { id: 31, kind: 'deployment-review-request', commands: [], phase: 'created', installation: structuredClone(source),
    creation: { outcome: 'accepted', ownershipConfirmed: true, origin: admin.origin, actorIdentity: structuredClone(admin.identity) },
    modelUpgrade: { phase: 'prepared', source, preview, origin: admin.origin, actorIdentity: structuredClone(admin.identity), definitionId: 7, requestIds: [31], installationIds: ['11'], fixture: f } };
  const target = { id: 32, kind: 'deployment-review-request', last: { upgrade: preview, planDigest: 'plan' }, operation: { id: 33, planDigest: 'plan' },
    installation: { ...structuredClone(source), id: 12, sourceDigest: preview.targetDigest, previousInstallationId: 11, operationId: 'deployment:33' } };
  Object.assign(target.installation.receipt, { runtimeApplicationUuid: 'new-runtime', deploymentOperationId: 33, revisionId: 21, revisionDigest: preview.targetDigest });
  const history = { ...structuredClone(source), status: 'disabled' };
  delete history.deploymentVersion;
  history.receipt.upgrade = { operationId: 33, planDigest: preview.previewDigest, targetInstallationId: 12, phase: 'completed' };
  const h = { admin, state: { resources: [r] }, Blocked: Error, persist() {}, observe() {}, good: v => v?.status === 200 && !v.data?.error,
    check(message, condition) { assert.ok(condition, message); } };
  h.ok = async (_actor, _method, route) => ({ value: structuredClone(route.endsWith('upgrade-preview') ? preview : source) });
  return { h, r, source, f, preview, target, history };
}
test('upgrade preview binds exact original version, deployment, package and maintenance contract', () => {
  const { source, f, preview } = fixture(); assert.ok(upgrade.previewMatches(source, f, preview));
  for (const change of [{ sourceInstallationId: 12 }, { sourceInstallationVersion: 9 }, { deploymentVersion: 1 }, { sourceDigest: 'other' },
    { targetPackageId: 3 }, { targetDigest: 'other' }, { targetVersion: 1 }, { instanceKey: 'other' }, { instanceName: 'other' },
    { deploymentId: 'other' }, { maintenanceRequired: false }, { previewDigest: '' }, { schemaDigest: '' }])
    assert.equal(upgrade.previewMatches(source, f, { ...preview, ...change }), false);
});
test('completed handoff requires same physical binding and deployment, new runtime and exact original operation proof', () => {
  const { r, target, history } = fixture(); assert.ok(upgrade.handoffMatches(r.modelUpgrade, target, history));
  for (const change of [t => t.installation.previousInstallationId++, t => t.installation.deploymentId = 'foreign',
    t => t.installation.receipt.database.schemaResourceId++, t => t.installation.receipt.runtimeApplicationUuid = 'old-runtime',
    t => t.installation.receipt.revisionId++, t => t.installation.receipt.deploymentOperationId++, t => t.installation.sourceDigest = 'foreign',
    t => t.last.upgrade = { ...t.last.upgrade, previewDigest: 'foreign' }]) {
    const copy = structuredClone(target); change(copy); assert.equal(upgrade.handoffMatches(r.modelUpgrade, copy, history), false);
  }
  for (const change of [h => h.receipt.upgrade.operationId++, h => h.receipt.upgrade.targetInstallationId++,
    h => h.receipt.upgrade.phase = 'switching', h => h.receipt.upgrade.restoreRequested = true, h => h.status = 'ready']) {
    const copy = structuredClone(history); change(copy); assert.equal(upgrade.handoffMatches(r.modelUpgrade, target, copy), false);
  }
});
test('unknown upgrade request is not replayed and protects predecessor, source package, grants and unknown successor request', async () => {
  const { h, r, f } = fixture(); let sends = 0;
  h.create = async () => { sends++; assert.equal(r.modelUpgrade.phase, 'requesting'); throw Error('original create response lost'); };
  await assert.rejects(upgrade.createUpgrade(h, r, f), /response lost/);
  await assert.rejects(upgrade.createUpgrade(h, r, f), /no request replay/); assert.equal(sends, 1);
  for (const dependency of [r, { kind: 'definition', id: 7 }, { kind: 'member-access-retirement', installation: { id: 11 } },
    { kind: 'deployment-review-request', creation: { intended: { upgrade: { installationId: 11 } } } }])
    assert.throws(() => guard(h, dependency), /upgrade lineage remains open/);
  await assert.rejects(cleanup(h, r), /no generic predecessor uninstall/);
  await assert.rejects(business.cleanup(h, { scenarioUpgradeRequestId: r.id }), /obsolete installation fence/);
});
test('changed upgrade actor, duplicate row disposal and missing successor destroy proof never issue cleanup commands', async () => {
  for (const mode of ['actor', 'duplicate', 'no-proof']) {
    const { h, r, target } = fixture(); let writes = 0; h.api = async () => { writes++; throw Error('must not dispatch'); };
    if (mode === 'actor') { h.admin.identity.account = 'foreign'; await assert.rejects(upgrade.createUpgrade(h, r, {}), /Original review intent or command unresolved/); }
    else if (mode === 'duplicate') {
      r.modelUpgrade.phase = 'upgraded';
      await assert.rejects(upgrade.disposeRow(h, {}, { scenarioUpgradeRequestId: r.id, successorDisposition: {} }, {}, r), /duplicate delete/);
    } else await assert.rejects(upgrade.finishSource(h, r, { ...target, creation: structuredClone(r.creation), commands: [] }), /successor destroy/);
    assert.equal(writes, 0); assert.notEqual(r.phase, 'deleted');
  }
});
test('predecessor disposition requires original-row closure, exact successor destroy, independent Schema recycle and unchanged history', async () => {
  for (const mode of ['good', 'open-row', 'missing-schema', 'changed-history', 'historical-current-version', 'current-version-missing', 'current-version-regressed', 'actor-drift']) {
    const { h, r, target, history } = fixture(), j = r.modelUpgrade;
    target.phase = 'deleted'; target.creation = structuredClone(r.creation);
    const retired = { ...structuredClone(target.installation), status: 'uninstalled' };
    retired.receipt.uninstallation = { dataDisposition: 'destroy', finishedAt: 123, authorization: { confirmed: true }, recoveryStatus: 'recycled' };
    target.retiredInstallation = retired;
    const ack = structuredClone(retired); delete ack.deploymentVersion;
    target.commands = [{ route: '/panel/application/installations/12/uninstall', response: { status: 200, data: { value: ack } }, outcome: 'confirmed' }];
    Object.assign(j, { phase: 'rows-disposed', target: target.installation, handoffSource: history, upgradeRequestId: target.id });
    r.last = { id: r.id, status: 'succeeded' }; r.operation = { id: 34, status: 'succeeded' };
    h.state.resources.push({ scenarioUpgradeRequestId: r.id, phase: mode === 'open-row' ? 'created' : 'deleted' });
    h.ok = async (_actor, _method, route) => {
      let value = route.endsWith('/11') ? history : route.endsWith('/12') ? retired : route.includes('deployment-operations') ? r.operation : r.last;
      if (mode === 'changed-history' && route.endsWith('/11')) value = { ...history, sourceDigest: 'foreign' };
      if (mode === 'historical-current-version' && route.endsWith('/11')) value = { ...history, deploymentVersion: 3 };
      if (mode === 'current-version-missing' && route.endsWith('/12')) { value = structuredClone(retired); delete value.deploymentVersion; }
      if (mode === 'current-version-regressed' && route.endsWith('/12')) value = { ...retired, deploymentVersion: 1 };
      if (mode === 'actor-drift' && route.includes('deployment-operations')) h.admin.identity.account = 'other';
      return { value: structuredClone(value) };
    };
    h.directory = async () => mode === 'missing-schema' ? [] : [{ id: 42, status: 'recycled' }];
    h.api = async () => { throw Error('No command replay or second predecessor uninstall allowed'); };
    if (mode === 'good') {
      await upgrade.finishSource(h, r, target); assert.equal(j.phase, 'complete'); assert.equal(r.phase, 'deleted');
      assert.equal(r.retentionProof.predecessorId, 11); assert.equal(r.retentionProof.successorId, 12);
    } else { await assert.rejects(upgrade.finishSource(h, r, target)); assert.notEqual(j.phase, 'complete'); assert.notEqual(r.phase, 'deleted'); }
  }
});
