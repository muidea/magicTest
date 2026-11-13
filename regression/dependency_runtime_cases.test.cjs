const { test } = require('node:test');
const assert = require('node:assert/strict');
const { input, ownedContainer } = require('./dependency_runtime_cases.cjs');
test('dependency consumer declares actual ready worker endpoint and required/optional nonsecret defaults without extra persistent ownership', () => {
  const h = { state: { prefix: 'original' } }, v = input(h);
  assert.equal(Object.keys(v.contract.volumes).length, 1);
  assert.equal(v.contract.components.worker.mounts, undefined);
  assert.deepEqual(v.contract.components.api.dependsOn, [{ componentRef: 'worker', condition: 'ready', timeoutSeconds: 120 }]);
  assert.ok(v.contract.components.api.command[1].includes('wget -qO /data/dependency.json "$REGRESSION_DEPENDENCY/probe.json"'));
  assert.notEqual(v.contract.parameters.required_label.default, v.contract.parameters.optional_label.default);
  for (const key of Object.keys(v.contract.parameters)) assert.match(key, /^[a-z][a-z0-9_-]{0,63}$/);
  for (const name of ['REGRESSION_REQUIRED', 'REGRESSION_OPTIONAL']) {
    const key = v.contract.components.api.environment[name].parameterRef;
    assert.ok(Object.hasOwn(v.contract.parameters, key));
  }
});
test('dependency observation rejects foreign container image/labels before any exec of application files', () => {
  const id = 'a'.repeat(64), r = { last: { deploymentId: 'original' }, installation: { packagedReceipt: { runtimeApplicationUuid: 'runtime', components: [{ key: 'worker', containerId: id, imageId: 'sha256:original' }] } } };
  const h = { Blocked: Error, check: (m, c) => assert.ok(c, m) };
  const actual = { Id: id, Image: 'sha256:original', State: { Running: true }, Config: { Labels: { 'io.platform.deployment-id': 'original', 'io.platform.runtime.application-uuid': 'runtime' } } };
  let reads = 0;
  const run = (bin, args) => { reads++; assert.equal(bin, 'docker'); assert.deepEqual(args, ['inspect', id]); return JSON.stringify([actual]); };
  assert.equal(ownedContainer(h, r, 'worker', run).Id, id);
  for (const mutate of [v => v.Image = 'foreign', v => v.Id = 'b'.repeat(64), v => v.Config.Labels['io.platform.deployment-id'] = 'foreign', v => v.State.Running = false]) {
    const bad = structuredClone(actual); mutate(bad); assert.throws(() => ownedContainer(h, r, 'worker', () => JSON.stringify([bad])));
  }
  r.installation.packagedReceipt.components.push({ ...r.installation.packagedReceipt.components[0] });
  assert.throws(() => ownedContainer(h, r, 'worker', run), /Exact original/); assert.equal(reads, 1);
});
