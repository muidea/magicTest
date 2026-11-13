const { test } = require('node:test');
const assert = require('node:assert/strict');
const { placementMatches, registryUnchanged } = require('./runtime_placement_cases.cjs');
function fixture() {
  const placement = { executionInstanceId: 'base1', gatewayInstanceId: 'gateway1' };
  const resolved = { execution: { instanceId: 'base1', instanceVersion: 4, resolutionSource: 'explicit' }, gateway: { instanceId: 'gateway1', instanceVersion: 5, resolutionSource: 'explicit' } };
  const req = { id: 7, operationId: 8, packageId: 9, namespace: 'panel', deploymentId: 'deployment1', planDigest: 'original', status: 'succeeded', runtimePlacement: placement, resolvedRuntimePlacement: resolved };
  const r = { id: 7, placement, last: req, creation: { intended: { expectedDigest: 'source1' } },
    commands: [{ route: '/original/approve', outcome: 'confirmed', body: { runtimePlacement: placement }, response: { data: { value: structuredClone(req) } } }],
    operation: { id: 8, requestId: 7, packageId: 9, deploymentId: 'deployment1', planDigest: 'original', applicationUuid: 'application1', status: 'succeeded', phase: 'complete', receiptRef: 'installation:10', attempt: 1 },
    installation: { id: 10, namespace: 'panel', status: 'ready', deploymentId: 'deployment1', applicationUuid: 'application1', sourceDigest: 'source1', operationId: 'deployment:8', receipt: { deploymentOperationId: 8 } } };
  const inventory = [{ id: 'base1', kind: 'base', status: 'registered', version: 4, incarnation: 'base-boot', address: 'http://base', assignmentVersion: 1, snapshotVersion: 2, appliedSnapshotVersion: 0, updateTime: 100 },
    { id: 'gateway1', kind: 'gateway', status: 'registered', version: 5, incarnation: 'gateway-boot', address: 'http://gateway', assignmentVersion: 1, snapshotVersion: 2, appliedSnapshotVersion: 2, updateTime: 100 }];
  return { r, inventory };
}
test('placement acceptance requires exact original approval, resolved registry revisions and durable task/installation binding', () => {
  const original = fixture(); assert.equal(placementMatches(original.r, original.inventory), true);
  for (const mutate of [x => x.r.commands.push(structuredClone(x.r.commands[0])), x => x.r.commands[0].outcome = 'unknown',
    x => x.r.commands[0].body.runtimePlacement = { executionInstanceId: 'foreign' }, x => x.r.last.resolvedRuntimePlacement.execution.instanceId = 'foreign',
    x => x.r.last.resolvedRuntimePlacement.gateway.instanceVersion++, x => x.r.last.resolvedRuntimePlacement.execution.resolutionSource = 'platformDefault',
    x => x.inventory.push(structuredClone(x.inventory[0])), x => x.inventory[0].kind = 'gateway', x => x.inventory[1].incarnation = '',
    x => x.inventory[0].status = 'stopped', x => x.r.commands[0].response.data.value.planDigest = 'foreign',
    x => x.r.operation.requestId++, x => x.r.operation.packageId++, x => x.r.operation.deploymentId = 'foreign', x => x.r.operation.planDigest = 'foreign',
    x => x.r.operation.status = 'running', x => x.r.operation.phase = 'execution', x => x.r.operation.attempt = 0,
    x => x.r.operation.receiptRef = 'installation:11', x => x.r.installation.deploymentId = 'foreign',
    x => x.r.installation.namespace = 'foreign', x => x.r.installation.sourceDigest = 'foreign', x => x.r.installation.applicationUuid = 'foreign',
    x => x.r.installation.operationId = 'deployment:9', x => x.r.installation.receipt.deploymentOperationId++, x => delete x.r.installation.receipt]) {
    const changed = structuredClone(original); mutate(changed); assert.equal(placementMatches(changed.r, changed.inventory), false);
  }
});
test('normal assignment lifecycle may advance control observation cursors but cannot alter registry configuration or regress counters', () => {
  const { inventory } = fixture(), after = structuredClone(inventory);
  after[0].assignmentVersion++; after[0].snapshotVersion++; after[1].snapshotVersion++; after[1].appliedSnapshotVersion++; after[1].updateTime++;
  assert.equal(registryUnchanged(inventory, after), true);
  for (const mutate of [x => x.pop(), x => x.reverse(), x => x[0].address = 'foreign', x => x[0].incarnation = 'new-boot',
    x => x[0].version++, x => x[0].namespaceScope = '*', x => x[0].credentialEndpointId = 7, x => x[0].assignmentVersion = 0,
    x => x[0].snapshotVersion = NaN, x => x[1].appliedSnapshotVersion = 1, x => x[0].updateTime = 99]) {
    const changed = structuredClone(after); mutate(changed); assert.equal(registryUnchanged(inventory, changed), false);
  }
});
