const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { boundary, declarations } = require('./authorization_capacity_cases.cjs');
const { ownerRequest } = require('./owner_transport.cjs');
const { guard } = require('./scenario_commands.cjs');
const original = { id: 7, uuid: 'a'.repeat(32), name: 'capacity', showName: '容量', runtimeType: 'model-driven', updateTime: 10,
  authorization: { apiVersion: 'magic.application-authorization/v1', dataAccess: [{ operation: 'read' }, { operation: 'write' }, { operation: 'delete' }], entityActions: [] } };
test('capacity declarations retain initial contract and complete references without modifying their original model', () => {
  const before = structuredClone(original);
  const value = declarations(original.authorization, 64);
  assert.equal(value.permissions.length, 64); assert.equal(value.roles.length, 64); assert.equal(value.templates.length, 64);
  assert.equal(new Set(value.permissions.map(p => p.key)).size, 64);
  for (const [i, r] of value.roles.entries()) assert.deepEqual(r.permissions, [value.permissions[i].key]);
  assert.deepEqual(original, before);
  for (const count of [-1, 0, 66, 1.5]) assert.throws(() => declarations(original.authorization, count));
  assert.throws(() => declarations({ ...original.authorization, permissions: [{ key: 'existing' }] }, 64), /extension-free/);
});
async function fixture(mode, run) {
  let value = structuredClone(original), writes = [];
  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    assert.ok(req.url.startsWith('/api/v1/web/proxy/panel/application/definitions/7'));
    if (req.method === 'GET') return res.end(JSON.stringify({ value: req.url.endsWith('/model-draft') ? { applicationId: 7, definitionVersion: value.updateTime, entities: [] } : value }));
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks)); writes.push(body);
    assert.equal(body.expectedDefinitionVersion, value.updateTime);
    assert.equal(body.id, undefined);
    if (mode === 'lost-first' || mode === 'lost-refusal' && writes.length === 3) return req.socket.destroy();
    if (['permissions', 'roles', 'templates'].some(k => body.authorization[k]?.length > 64)) {
      if (mode === 'changed-refusal') value = { ...value, showName: 'concurrent change' };
      res.statusCode = mode === 'auth-refusal' ? 401 : 400;
      return res.end(JSON.stringify({ error: { code: mode === 'auth-refusal' ? 11 : 4, message: 'application authorization definition is invalid, duplicated or exceeds its declared scope' } }));
    }
    const { expectedDefinitionVersion, ...fields } = body;
    value = { ...value, ...fields, updateTime: value.updateTime + 1 };
    if (mode === 'truncated') value.authorization.roles.pop();
    if (mode === 'actor-drift') actor.identity.account = 'replacement';
    res.end(JSON.stringify({ value }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const actor = { identity: { account: 'original', namespace: 'panel' }, origin: 'http://127.0.0.1:' + server.address().port,
    context: { async cookies() { return []; }, async addCookies() {}, async clearCookies() {} } };
  const r = { kind: 'definition', id: 7, phase: 'created', creation: { ownershipConfirmed: true } };
  const h = { admin: actor, state: { resources: [r] }, Blocked: Error, persist() {}, good: r => r.status === 200 && !r.data.error,
    api: (...args) => ownerRequest(...args), check(label, valid) { assert.ok(valid, label); }, async ok(...args) { const r = await h.api(...args); assert.ok(h.good(r)); return r.data; } };
  try { await run(h, r, () => writes, () => value); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
test('HTTP tool flow records original conditional identities and checks each independent count refusal before legitimate contraction', async () => {
  await fixture('exact', async (h, r, writes, value) => {
    await boundary(h, structuredClone(original));
    assert.equal(writes().length, 6);
    assert.deepEqual(writes().slice(0, 2).map(v => v.authorization.permissions.length), [63, 64]);
    assert.deepEqual(r.scenarioCommands.map(c => c.outcome), Array(3).fill('rejected-and-unchanged'));
    assert.deepEqual(r.scenarioCommands.map(c => ['permissions', 'roles', 'templates'].map(k => c.body.authorization[k].length)), [[65, 64, 64], [64, 65, 64], [64, 64, 65]]);
    assert.deepEqual(value(), { ...original, updateTime: 13 });
    await assert.rejects(boundary(h, structuredClone(original)), /no boundary replay/); assert.equal(writes().length, 6);
  });
});
test('lost or wrongly attributed capacity writes keep original intent and never restore or replay', async () => {
  for (const mode of ['lost-first', 'lost-refusal', 'auth-refusal', 'changed-refusal', 'truncated', 'actor-drift']) await fixture(mode, async (h, r, writes) => {
    await assert.rejects(boundary(h, structuredClone(original)));
    const count = writes().length;
    assert.ok(r.metadataJournal.commands.some(c => c.outcome === 'unknown') || r.scenarioCommands.some(c => c.outcome === 'unknown'));
    if (r.scenarioCommands) assert.throws(() => guard(h, r), /unresolved/);
    await assert.rejects(boundary(h, structuredClone(original)), /no boundary replay/);
    assert.equal(writes().length, count);
    assert.equal(writes().some(v => v.authorization.permissions?.length === 0), false);
  });
});
