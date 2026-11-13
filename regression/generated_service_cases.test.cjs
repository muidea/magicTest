const test = require('node:test');
const assert = require('node:assert/strict');
const { confirms, original, cleanup, ownedSlice, services, bindings, publications, capabilities } = require('./generated_service_cases.cjs');
test('generated result requires exact complete service/publication/binding/source facts', () => {
  const item = { service: { key: 'owned', name: 'owned' }, capabilityIDs: [5, 6] }, source = 'a'.repeat(32);
  const value = { service: { id: 3, key: 'owned', name: 'owned', namespace: 'panel', providerType: 'application', providerKey: source },
    publication: { id: 4, namespace: 'panel', service: { id: 3 } }, bindings: [5, 6].map((id, index) => ({ id: 10 + index, capability: { id }, service: { id: 3 }, enabled: true, sort: index + 1 })) };
  const observed = { service: value.service, publications: [value.publication], bindings: value.bindings };
  assert.equal(confirms(value, observed, item, source), true);
  for (const change of [v => { v.service.providerKey = 'b'.repeat(32); }, v => { v.bindings[0].enabled = false; }, v => { v.bindings[0].sort = 2; }, v => { v.publication.service.id = 99; }, v => { v.bindings.pop(); }]) {
    const copy = structuredClone(value); change(copy); assert.equal(confirms(copy, observed, item, source), false);
  }
  assert.equal(confirms(value, { ...observed, bindings: observed.bindings.slice(0, 1) }, item, source), false);
  assert.equal(confirms(value, { ...observed, publications: [...observed.publications, value.publication] }, item, source), false);
});
test('unknown generated command and wrong original actor block retirement before any owner read or mutation', async () => {
  const identity = { account: 'original', namespace: 'panel' }, r = { kind: 'generated-service-graph', origin: 'https://panel.example', actorIdentity: identity, commands: [] };
  const h = { admin: { origin: r.origin, identity }, Blocked: Error, directory() { throw Error('must not read'); }, api() { throw Error('must not dispatch'); } };
  original(h, r);
  for (const changed of [{ ...r, commands: [{ outcome: 'unknown' }] }, { ...r, origin: 'https://other.example' }, { ...r, actorIdentity: { ...identity, account: 'replacement' } }])
    await assert.rejects(cleanup(h, changed), /unresolved/);
});
test('generated cascade unknown DELETE is never repeated even after an independent absence', async () => {
  const identity = { account: 'original', namespace: 'panel' }, all = { [services]: [{ id: 3, key: 'owned', providerKey: 'source' }], [bindings]: [], [publications]: [], [capabilities]: [] };
  const r = { kind: 'generated-service-graph', origin: 'https://panel.example', actorIdentity: identity, commands: [], key: 'owned', source: 'source', serviceId: 3, last: ownedSlice(all, 3), deletion: { outcome: 'unknown' } };
  let writes = 0;
  const h = { admin: { origin: r.origin, identity }, Blocked: Error, async directory(_, route) { return all[route]; }, async api() { writes++; } };
  await assert.rejects(cleanup(h, r), /DELETE unresolved/); assert.equal(writes, 0);
});
