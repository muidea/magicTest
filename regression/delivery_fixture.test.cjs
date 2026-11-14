const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  isIsolatedNestedDaemon, validateIsolation, validateLocalPlatform, validateFixtureConfig, requireIsolatedDaemon, fixtureManifest, dedicatedDeliveryOnly
} = require('./delivery_fixture.cjs');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
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
test('local-panel mode validates explicit host platform bounds and remains rejected by requireIsolatedDaemon', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'magictest-local-fixture-'));
  try {
    const fakeRoot = path.join(dir, 'platform'), priv = path.join(dir, 'private-fixture'), creds = path.join(dir, 'credentials.json');
    fs.mkdirSync(path.join(fakeRoot, 'services'), { recursive: true });
    fs.writeFileSync(path.join(fakeRoot, 'services/.env'), 'DOMAIN_NAME=local.vpc\n');
    fs.writeFileSync(creds, JSON.stringify({ origin: 'https://panel.local.vpc', account: 'platform-admin', password: 'secret' }));
    const localCfg = { mode: 'local-panel', origin: 'https://panel.local.vpc', platformRoot: fakeRoot, daemonId: 'host-daemon', credentialsFile: creds, privateRoot: priv };
    const localInfo = { ID: 'host-daemon' };
    assert.equal(isIsolatedNestedDaemon(localCfg), false);
    assert.equal(isIsolatedNestedDaemon(config), true);
    validateLocalPlatform(localCfg, localInfo);
    validateFixtureConfig(localCfg, localInfo);
    assert.equal(fixtureManifest({ application: {}, revision: {}, package: {} }, localCfg).fixtureScope, 'local host platform');
    assert.throws(() => validateLocalPlatform({ ...localCfg, origin: 'http://panel.local.vpc' }, localInfo), /canonical HTTPS origin/);
    assert.throws(() => validateLocalPlatform({ ...localCfg, daemonId: 'other' }, localInfo), /daemonId/);
    assert.throws(() => validateLocalPlatform({ ...localCfg, privateRoot: path.join(fakeRoot, 'priv') }, localInfo), /outside platformRoot/);
    assert.throws(() => validateLocalPlatform({ ...localCfg, privateRoot: path.join(os.homedir(), 'codespace/priv') }, localInfo), /outside platformRoot/);
    const cfgFile = path.join(dir, 'local-fixture.json');
    fs.writeFileSync(cfgFile, JSON.stringify(localCfg));
    const h = { fs, deliveryFixtureConfig: cfgFile, Blocked: Error };
    assert.throws(() => requireIsolatedDaemon(h, 'DELIVERY-FIXTURE: nested required', () => JSON.stringify(localInfo)), /DELIVERY-FIXTURE: nested required/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
