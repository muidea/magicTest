const test = require('node:test');
const assert = require('node:assert/strict');
const { catalogueMatches } = require('./capability_switch_cases.cjs');
function sample() {
  const f = { package: { artifactDigest: 'sha256:owned' }, revision: { id: 1, entities: [
    { id: 2, name: 'enabled', pkgPath: '/owned', serviceExpose: { enabled: true, capabilities: [{ key: 'get', enabled: true }, { key: 'delete', enabled: false }] } },
    { id: 3, name: 'closed', pkgPath: '/owned', serviceExpose: { enabled: false, capabilities: [{ key: 'get', enabled: true }] } }
  ] } };
  const installation = { namespace: 'panel', applicationKey: 'app', instanceKey: 'instance', sourceDigest: 'sha256:owned', receipt: { revisionId: 1, revisionDigest: 'sha256:owned', runtimeApplicationId: 10, runtimeApplicationUuid: 'original', entities: [
    { definitionEntityId: 2, runtimeEntityId: 20, pkgKey: '/owned/enabled' }, { definitionEntityId: 3, runtimeEntityId: 21, pkgKey: '/owned/closed' }
  ] } };
  const options = { generated: true, source: 'entity', capability: 'get', status: 1, runtimeApplicationID: 10, runtimeApplicationUUID: 'original', runtimeEntityID: 20, runtimeEntityName: 'enabled', runtimeEntityPkgPath: '/owned', runtimeEntityPkgKey: '/owned/enabled' };
  const values = [{ id: 30, key: 'enabled_get', runtimeApplication: { runtimeApplicationUUID: 'original', applicationKey: 'app', instanceKey: 'instance' }, status: 1, kind: 'get', sourceType: 'entity', providerType: 'application', providerKey: 'original', options: JSON.stringify(options) }];
  return { f, installation, values };
}
test('switch catalogue requires exact installation/definition/runtime binding and complete enabled set', () => {
  const { f, installation, values } = sample(); assert.equal(catalogueMatches(f, installation, values, 'panel'), true);
  for (const change of [s => { s.installation.namespace = 'other'; }, s => { s.installation.sourceDigest = 'transport-domain'; },
    s => { s.installation.receipt.revisionId++; }, s => { s.installation.receipt.entities[1].runtimeEntityId = 20; },
    s => { s.installation.receipt.entities[0].definitionEntityId = 88; }, s => { s.installation.receipt.entities.pop(); },
    s => { s.values[0].providerKey = 'foreign'; }, s => { delete s.values[0].runtimeApplication; },
    s => { s.values[0].runtimeApplication.instanceKey = 'foreign'; }, s => { s.values[0].runtimeApplication.runtimeApplicationUUID = 'foreign'; },
    s => { s.values[0].runtimeApplication.applicationKey = 'foreign'; }, s => { s.values[0].options = '{}'; }, s => { s.values[0].options = 'invalid'; },
    s => { s.values.push({ ...s.values[0], id: 31 }); }, s => { s.values = []; },
    s => { s.f.revision.entities[1].serviceExpose.enabled = true; }, s => { s.f.revision.entities[0].serviceExpose.capabilities[1].enabled = true; }]) {
    const s = sample(); change(s); assert.equal(catalogueMatches(s.f, s.installation, s.values, 'panel'), false);
  }
});
test('a capability borrowed from another runtime entity cannot replace an enabled pair or prove the closed entity absent', () => {
  for (const changes of [{ runtimeEntityID: 21 }, { runtimeApplicationID: 11 }, { capability: 'delete' }, { runtimeEntityPkgKey: '/other/enabled' }, { generated: false }]) {
    const { f, installation, values } = sample(); values[0].options = JSON.stringify({ ...JSON.parse(values[0].options), ...changes });
    assert.equal(catalogueMatches(f, installation, values, 'panel'), false);
  }
});
test('published zero definition IDs stay distinct by exact frozen entity keys and runtime receipt IDs', () => {
  const { f, installation, values } = sample();
  for (const e of f.revision.entities) e.id = 0;
  for (const e of installation.receipt.entities) e.definitionEntityId = 0;
  assert.equal(catalogueMatches(f, installation, values, 'panel'), true);
  installation.receipt.entities[1].pkgKey = '/owned/enabled';
  assert.equal(catalogueMatches(f, installation, values, 'panel'), false);
});

test('catalogue scope comes from the original scoped actor and installed projection, never an invented namespace field', () => {
  const { f, installation, values } = sample();
  assert.equal(Object.hasOwn(values[0], 'namespace'), false);
  assert.equal(catalogueMatches(f, installation, values, 'panel'), true);
  for (const scope of [undefined, '', 'other']) assert.equal(catalogueMatches(f, installation, values, scope), false);
});
