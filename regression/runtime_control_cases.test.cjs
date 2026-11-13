const { test } = require('node:test');
const assert = require('node:assert/strict');
const { handlers, policyCommand, cleanupPolicy, binding, snapshotProof } = require('./runtime_control_cases.cjs');
const policies = '/panel/operations/runtime-placements/policies/';
function policyFixture(mode) {
  const before = [{ id: 'policy1', targetNamespace: '', gatewayInstanceId: 'gateway1', executionInstanceId: 'base1', version: 2, createTime: 10, updateTime: 20 }];
  const inventory = [{ id: 'gateway1', assignmentVersion: 1, snapshotVersion: 1, appliedSnapshotVersion: 1, updateTime: 20 }], installations = [{ id: 9, receipt: { frozen: true } }];
  const r = { kind: 'runtime-policy-probe', id: 'journal1', policyId: 'policy1', origin: 'https://unit.invalid', actorIdentity: { account: 'original' },
    commands: [], before, last: structuredClone(before), inventory, installations, phase: 'created' };
  let owner = structuredClone(before), writes = 0, reads = 0; const persisted = [];
  const h = { admin: { origin: r.origin, identity: structuredClone(r.actorIdentity) }, Blocked: Error,
    persist() { persisted.push(structuredClone(r)); }, check(label, condition) { assert.ok(condition, label); }, good: x => x.status === 200 && x.data.error == null,
    async ok(actor, method, route) {
      assert.equal(method, 'GET'); reads++;
      if (route === policies) { if (mode === 'read-failed' && writes) throw Error('owner unavailable'); return { values: structuredClone(owner) }; }
      if (route.endsWith('instances/')) return { values: structuredClone(inventory) };
      if (route.endsWith('/9')) return { value: mode === 'installation-drift' ? { id: 9, receipt: {} } : structuredClone(installations[0]) };
      throw Error('unexpected owner route');
    },
    async api(actor, method, route, body) {
      assert.equal(method, 'POST'); assert.equal(route, policies); writes++;
      assert.equal(persisted.at(-1).commands.at(-1).confirmed, false, 'intent persisted before command');
      if (mode === 'lost') throw Error('original response lost');
      const message = body.gatewayInstanceId === 'base1' ? 'runtime instance kind or namespace admission does not match' : body.expectedVersion !== owner[0].version ? 'runtime placement policy changed' : null;
      if (message) return { status: 200, data: { value: null, error: { code: 4, message: mode === 'wrong-refusal' ? 'unrelated' : message } } };
      owner[0] = { ...owner[0], version: owner[0].version + 1, updateTime: 21 };
      if (mode === 'semantic-drift') owner[0].gatewayInstanceId = 'foreign';
      return { status: 200, data: { error: null, value: { ...owner[0], ...(mode === 'wrong-ack' ? { version: 999 } : {}) } } };
    } };
  return { h, r, body: { targetNamespace: '', gatewayInstanceId: 'gateway1', executionInstanceId: 'base1', expectedVersion: 2 }, persisted,
    writes: () => writes, reads: () => reads, drift: () => owner[0].version++ };
}
test('formal same-target conditional revision, stale version and wrong-kind commands retain independent owner truth', async () => {
  const { h, r, body, writes } = policyFixture(); await policyCommand(h, r, body);
  await policyCommand(h, r, body, 'runtime placement policy changed');
  await policyCommand(h, r, { ...body, expectedVersion: 3, gatewayInstanceId: 'base1' }, 'runtime instance kind or namespace admission does not match');
  await cleanupPolicy(h, r); assert.equal(writes(), 3); assert.equal(r.last[0].version, 3); assert.equal(r.before[0].version, 2);
  assert.equal(r.phase, 'deleted'); assert.ok(r.commands.every(c => c.confirmed));
});
test('unknown transport, owner read loss, false acknowledgement and semantic change retain original command without replay or guessed rollback', async () => {
  for (const mode of ['lost', 'read-failed', 'wrong-ack', 'semantic-drift']) {
    const f = policyFixture(mode); await assert.rejects(policyCommand(f.h, f.r, f.body)); assert.equal(f.r.commands[0].confirmed, false);
    await assert.rejects(policyCommand(f.h, f.r, f.body), /unresolved/); await assert.rejects(cleanupPolicy(f.h, f.r), /unresolved/);
    assert.equal(f.writes(), 1); assert.equal(f.r.phase, 'created');
  }
});
test('concurrent policy drift and wrong original actor block before dispatch', async () => {
  for (const mode of ['drift', 'actor', 'origin']) {
    const f = policyFixture(); if (mode === 'drift') f.drift(); if (mode === 'actor') f.h.admin.identity.account = 'foreign'; if (mode === 'origin') f.h.admin.origin += '.foreign';
    await assert.rejects(policyCommand(f.h, f.r, f.body)); assert.equal(f.writes(), 0); assert.equal(f.r.commands.length, 0);
  }
});
test('wrong refusal and post-command installation drift cannot close journal', async () => {
  const f = policyFixture('wrong-refusal'); await policyCommand(f.h, f.r, f.body); await assert.rejects(policyCommand(f.h, f.r, f.body, 'runtime placement policy changed')); assert.equal(f.r.commands[1].confirmed, false);
  const g = policyFixture('installation-drift'); await policyCommand(g.h, g.r, g.body); await assert.rejects(cleanupPolicy(g.h, g.r)); assert.equal(g.r.phase, 'created'); assert.equal(g.writes(), 1);
});
test('policy probe cannot mutate original targets or silently create a new scope', async () => {
  for (const mutate of [b => b.targetNamespace = 'other', b => b.executionInstanceId = 'other', b => b.gatewayInstanceId = 'other',
    b => b.expectedVersion = 0, b => b.expectedVersion++, b => b.extra = true]) {
    const f = policyFixture(); mutate(f.body); await assert.rejects(policyCommand(f.h, f.r, f.body), /Only original/);
    assert.equal(f.writes(), 0); assert.equal(f.reads(), 0); assert.equal(f.r.commands.length, 0);
  }
});
function snapshotFixture() {
  const c = { instanceId: 'gateway1', incarnation: 'boot1', endpointId: 7, clientId: 'original-client' };
  const inventory = [{ id: 'gateway1', kind: 'gateway', status: 'registered', incarnation: 'boot1', credentialEndpointId: 7, credentialClientId: 'original-client', snapshotVersion: 20 }];
  const known = [1, 2].map(id => ({ id, namespace: 'panel', deploymentId: 'deployment' + id, sourceDigest: 'sha256:source' + id, receipt: { runtimeApplicationUuid: 'runtime' + id } }));
  const now = Date.now(), snapshot = { apiVersion: 'magic.gateway-assignment-snapshot/v1', gateway: { instanceId: 'gateway1', incarnation: 'boot1' }, version: 19, complete: true, issuedAt: now - 100, expiresAt: now + 29900,
    assignments: known.map(i => ({ target: { namespace: i.namespace, deploymentId: i.deploymentId, installationId: i.id, runtimeApplicationUuid: i.receipt.runtimeApplicationUuid, revisionDigest: i.sourceDigest } })) };
  const result = { status: 200, contentType: 'application/json', cacheControl: 'no-store', byteLength: 2048, data: { error: null, value: snapshot } };
  const h = { check(label, condition) { assert.ok(condition, label); } }; return { h, c, inventory, known, result };
}
test('snapshot proves only complete marker, exact original machine binding, fresh lease and two known owner rows', () => {
  const f = snapshotFixture(); assert.equal(snapshotProof(f.h, f.result, f.c, f.inventory, f.known), f.result.data.value);
  for (const mutate of [x => x.inventory[0].incarnation = 'other', x => x.inventory[0].kind = 'base', x => x.inventory[0].credentialEndpointId++, x => x.inventory[0].credentialClientId = 'other',
    x => x.inventory[0].snapshotVersion = '20', x => x.inventory.push(structuredClone(x.inventory[0])), x => x.inventory[0].status = 'stopped']) {
    const g = snapshotFixture(); mutate(g); assert.throws(() => binding(g.h, g.c, g.inventory));
  }
});
test('future/fractional/stale leases, partial snapshots, wrong rows and over-budget envelopes cannot prove known assignment presence', () => {
  const mutations = [s => s.complete = false, s => s.version = 21, s => s.version = 1.5, s => s.issuedAt = Date.now() + 60000,
    s => s.expiresAt = Date.now() - 1, s => s.issuedAt = 1.5, s => s.expiresAt = 1.5, s => s.expiresAt += 30001,
    s => s.gateway.incarnation = 'other', s => s.assignments.pop(), s => s.assignments.push(structuredClone(s.assignments[0])),
    s => s.assignments[0].target.installationId++, s => s.assignments[0].target.namespace = 'other', s => s.assignments[0].target.revisionDigest = 'other',
    s => s.assignments[0].target.runtimeApplicationUuid = 'other', s => s.assignments = Array(10001).fill(s.assignments[0])];
  for (const mutate of mutations) { const f = snapshotFixture(); mutate(f.result.data.value); assert.throws(() => snapshotProof(f.h, f.result, f.c, f.inventory, f.known)); }
  for (const mutate of [x => x.result.byteLength = 16 * 1024 * 1024 + 1, x => x.result.status = 403, x => x.result.cacheControl = 'public', x => x.result.data.error = { code: 5 }, x => x.result.contentType = 'text/html']) {
    const f = snapshotFixture(); mutate(f); assert.throws(() => snapshotProof(f.h, f.result, f.c, f.inventory, f.known));
  }
});
test('two runtime-control cases register as public-owner subsets and do not call machine transport without explicit private inputs', async () => {
  assert.deepEqual(Object.keys(handlers), ['F035-004', 'F035-006']); assert.equal(handlers['F035-006'].transport, 'owner-api');
  await assert.rejects(handlers['F035-006']({ Blocked: Error }), /private|Private/);
});
