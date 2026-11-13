const { test } = require('node:test');
const assert = require('node:assert/strict');
const { restore, rename } = require('./instance_cases.cjs');
function fixture() {
  const original = { id: 7, deploymentId: 'original', instanceKey: 'key', instanceName: 'before', deploymentVersion: 1 };
  const r = { id: 7, original, last: original, peer: { id: 8, instanceName: 'peer' }, actorIdentity: { account: 'admin', namespace: 'panel' }, origin: 'https://panel.test', phase: 'created', commands: [] };
  const writes = [], h = { admin: { identity: structuredClone(r.actorIdentity), origin: r.origin }, Blocked: Error, persist() {},
    async ok(actor, method, route) { assert.equal(method, 'GET'); return { value: structuredClone(route.endsWith('/8') ? r.peer : r.last) }; },
    async api(actor, method, route, body) { writes.push({ method, route, body }); throw Error('original response lost'); },
    check(label, value) { assert.ok(value, label); } };
  return { h, r, writes };
}
test('instance rename response loss retains exact original command and refuses replay or restoration', async () => {
  const f = fixture(); await assert.rejects(rename(f.h, f.r, 'after'), /original response lost/);
  assert.equal(f.r.commands[0].outcome, 'unknown'); assert.equal(f.writes[0].body.expectedDeploymentVersion, 1);
  await assert.rejects(rename(f.h, f.r, 'after'), /no replay/);
  await assert.rejects(restore(f.h, f.r), /no replay/); assert.equal(f.writes.length, 1); assert.equal(f.r.phase, 'created');
});
test('instance restore refuses a different actor or concurrent owner revision without mutation', async () => {
  const f = fixture(); f.h.admin.identity.namespace = 'foreign';
  await assert.rejects(restore(f.h, f.r), /actor changed/); assert.equal(f.writes.length, 0);
  const g = fixture(); g.h.ok = async () => ({ value: { ...g.r.last, deploymentVersion: 3 } });
  await assert.rejects(restore(g.h, g.r), /concurrent owner revision/); assert.equal(g.writes.length, 0);
});
