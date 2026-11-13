const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validateIsolation, fixtureManifest, dedicatedDeliveryOnly } = require('./delivery_fixture.cjs');
test('only a new homogeneous explicitly isolated delivery selection can omit unrelated generic tenant fixtures', () => {
  const handlers = { dedicated: Object.assign(() => {}, { requiresOnlyDeliveryFixture: true }), generic: () => {}, actor: Object.assign(() => {}, { requiresOnlyDeliveryFixture: true, actors: ['user'] }) };
  const selected = [{ id: 'dedicated' }], state = { resources: [], fixtures: {} };
  assert.equal(dedicatedDeliveryOnly(selected, handlers, '/private/fixture.json', state), true);
  for (const cases of [[], [...selected, { id: 'generic' }], [{ id: 'missing' }], [{ id: 'actor' }]]) assert.equal(dedicatedDeliveryOnly(cases, handlers, '/private/fixture.json', state), false);
  for (const config of [undefined, '', ' ']) assert.equal(dedicatedDeliveryOnly(selected, handlers, config, state), false);
  for (const existing of [{ resources: [{ kind: 'namespace', phase: 'intent' }], fixtures: {} }, { resources: [], fixtures: { tenantA: { id: 7 } } }]) assert.equal(dedicatedDeliveryOnly(selected, handlers, '/private/fixture.json', existing), false);
});
const config = { platformRoot: '/tmp/platform-executor-fixture/isolated-host/platform',
  dockerDataRoot: '/tmp/platform-executor-fixture/isolated-host/docker-data',
  daemonId: 'original-isolated-daemon', containerId: 'a'.repeat(64) };
const info = { ID: config.daemonId, DockerRootDir: config.dockerDataRoot, Driver: 'overlay2' };
test('delivery fixture admits only the original nested daemon and exact owned root', () => {
  validateIsolation(config, info, 'a'.repeat(12));
  for (const changed of [
    { ID: 'shared-daemon' }, { DockerRootDir: '/var/lib/docker' }, { Driver: 'vfs' }
  ]) assert.throws(() => validateIsolation(config, { ...info, ...changed }, 'a'.repeat(12)), /Dedicated nested daemon/);
  for (const changed of [
    { platformRoot: '/home/operator/dataspace/magicPlatform' },
    { platformRoot: '/tmp/platform-executor-fixture/../live' },
    { dockerDataRoot: '/foreign/docker-data' }, { containerId: 'partial' }
  ]) assert.throws(() => validateIsolation({ ...config, ...changed }, info, 'a'.repeat(12)), /Dedicated nested daemon/);
  assert.throws(() => validateIsolation(config, info, 'foreign-host'), /Dedicated nested daemon/);
});
test('private executable fixture preserves frozen authorization declarations without evidence redaction', () => {
  const state = { application: { authorization: { schemaVersion: 'initial', roles: [] } }, revision: { content: { pages: { dataSources: [{ authorization: 'validated-tenant-and-instance-and-entity-permissions' }] } } }, package: { authorizationCatalogDigest: 'original' } };
  const input = JSON.parse(JSON.stringify(fixtureManifest(state, config)));
  assert.deepEqual(input.application, state.application);
  assert.deepEqual(input.revision, state.revision); assert.deepEqual(input.package, state.package);
});
