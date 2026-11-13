const { test } = require('node:test');
const assert = require('node:assert/strict');
const { modelSummaryMatches } = require('./installation_summary_cases.cjs');
const { settledDrawerGeometry } = require('./installation_summary_cases.cjs');
test('drawer geometry waits through empty pre-animation state and moving viewport entry, without accepting persistent overflow', async () => {
  const fits = { viewport: 1440, scroll: 1440, left: 760, right: 1440, moving: false };
  const samples = [0, 1, 2, 3].map(() => ({ ...fits, left: 1440, right: 2120 }));
  samples.push({ ...fits, moving: true }, { ...fits, moving: true }, fits, fits, fits);
  let reads = 0, elapsed = 0;
  const result = await settledDrawerGeometry(async () => samples[Math.min(reads++, samples.length - 1)], async () => elapsed += 30, () => elapsed, 1000);
  assert.equal(result.settled, true); assert.equal(reads, 9);
  for (const bad of [{ ...fits, left: 1440, right: 2120 }, { ...fits, scroll: 1600 }, { ...fits, moving: true }]) {
    reads = 0; elapsed = 0;
    const result = await settledDrawerGeometry(async () => { reads++; return bad; }, async () => elapsed += 30, () => elapsed, 90);
    assert.equal(result.settled, false); assert.equal(reads, 4); assert.equal(elapsed, 90);
  }
});
test('summary evidence cannot join foreign runtime, artifact or storage facts or call a failed receipt healthy', () => {
  const f = { application: { uuid: 'a'.repeat(32) }, revision: { id: 3 }, package: { sourceRevisionId: 3, artifactDigest: 'sha256:original' } };
  const value = { id: 7, status: 'ready', runtimeType: 'model-driven', sourceKind: 'model-package', namespace: 'panel',
    deploymentId: 'd'.repeat(32), applicationUuid: f.application.uuid, sourceDigest: f.package.artifactDigest,
    receipt: { revisionId: 3, revisionDigest: f.package.artifactDigest, storageRequired: true, runtimeApplicationId: 9,
      runtimeApplicationUuid: 'b'.repeat(32), completedSteps: ['storage', 'runtime'],
      database: { provisioningMode: 'allocate', bindingId: 10, databaseResourceId: 11, schemaResourceId: 12 } } };
  const identity = { namespace: 'panel', installationId: '7', deploymentId: value.deploymentId,
    runtimeApplicationUuid: value.receipt.runtimeApplicationUuid, artifactDigest: f.package.artifactDigest };
  const database = { id: 11, name: 'db', status: 'active' }, schema = { id: 12, name: 'instance', databaseResourceId: 11, databaseName: 'db', status: 'active' };
  const initial = { f, value, identity, database, schema };
  const matches = x => modelSummaryMatches(x.f, x.value, x.identity, x.database, x.schema);
  assert.equal(matches(initial), true);
  for (const mutate of [x => x.value.id++, x => x.value.applicationUuid = 'foreign', x => x.value.sourceDigest = 'foreign',
    x => x.value.status = 'failed', x => x.value.runtimeType = 'packaged-runtime', x => x.value.namespace = 'foreign',
    x => x.value.sourceKind = 'deployment-package', x => x.value.failure = 'failed', x => x.value.receiptDiagnostic = { nextAction: 'retry' },
    x => x.identity.deploymentId = 'foreign', x => x.identity.runtimeApplicationUuid = 'foreign', x => x.identity.artifactDigest = 'foreign',
    x => x.f.package.sourceRevisionId++, x => x.value.receipt.revisionDigest = 'foreign', x => x.value.receipt.runtimeApplicationId = 0,
    x => x.value.receipt.runtimeApplicationUuid = 'unbound', x => x.value.receipt.storageRequired = false,
    x => x.value.receipt.completedSteps = [], x => x.value.receipt.completedSteps.push('storage'),
    x => x.value.receipt.database.bindingId = 0, x => x.value.receipt.database.provisioningMode = 'restore',
    x => x.schema.id++, x => x.schema.databaseResourceId++, x => x.database.id++, x => x.schema.databaseName = 'foreign',
    x => x.schema.status = 'recycled', x => x.database.status = 'deleted', x => x.schema.name = '', x => delete x.schema,
    x => delete x.database, x => delete x.value.receipt]) {
    const changed = structuredClone(initial); mutate(changed); assert.equal(matches(changed), false);
  }
});
