const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { ownerRequest } = require('./owner_transport.cjs');
const { reject, guard } = require('./scenario_commands.cjs');
async function fixture(mode, run) {
  let writes = 0, actor;
  const before = { id: 7, definitionVersion: 3, entities: [{ id: 9, fields: [{ name: 'original' }] }] };
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const part of req) chunks.push(part);
    res.setHeader('Content-Type', 'application/json');
    if (req.method === 'GET') return res.end(JSON.stringify({ value: mode === 'changed' && writes ? { ...before, definitionVersion: 4 } : before }));
    writes++;
    assert.equal(JSON.parse(Buffer.concat(chunks)).expectedDefinitionVersion, 3);
    if (mode === 'lost') return req.socket.destroy();
    if (mode === 'drift') actor.identity.account = 'replacement';
    res.statusCode = mode === 'auth' ? 401 : 400;
    res.end(JSON.stringify({ error: { code: mode === 'auth' ? 11 : 4, message: 'missing relation target' } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  actor = { identity: { namespace: 'panel', account: 'original' }, origin, context: { async cookies() { return []; }, async addCookies() {}, async clearCookies() {} } };
  const r = { kind: 'definition', id: 7, creation: { ownershipConfirmed: true } }, h = {
    admin: actor, state: { resources: [r] }, Blocked: Error, persist() {},
    api: (a, ...args) => ownerRequest(a, ...args), good: v => v?.status === 200 && !v.data.error,
    check: (label, ok) => assert.ok(ok, label) };
  try { await run(h, r, actor, () => writes); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
const probe = (h, r, actor) => reject(h, r, actor, 'PUT', '/model', { expectedDefinitionVersion: 3 }, ['/model'], { code: 4, messagePattern: '^missing relation target$' });
test('real HTTP negative scenario journals before dispatch and confirms target error and complete owner snapshot', async () => {
  await fixture('refused', async (h, r, actor, count) => {
    await probe(h, r, actor); assert.equal(count(), 1); assert.equal(r.scenarioCommands[0].outcome, 'rejected-and-unchanged'); guard(h, r);
  });
});
test('lost response, early authentication and changed full owner snapshot cannot dispose or replay original negative intent', async () => {
  for (const mode of ['lost', 'auth', 'changed']) await fixture(mode, async (h, r, actor, count) => {
    await assert.rejects(probe(h, r, actor)); assert.equal(r.scenarioCommands[0].outcome, 'unknown');
    assert.throws(() => guard(h, r), /unresolved/); await assert.rejects(probe(h, r, actor), /no replay/); assert.equal(count(), 1);
  });
});
test('replacement principal cannot confirm an original scenario refusal', async () => {
  await fixture('drift', async (h, r, actor, count) => {
    await assert.rejects(probe(h, r, actor), /actor changed/); assert.equal(count(), 1); assert.equal(r.scenarioCommands[0].outcome, 'unknown');
  });
});
test('unresolved related row retains original definition and both installation dependencies', () => {
  const h = { Blocked: Error, state: { resources: [{ kind: 'business-record', phase: 'created', scenarioDefinitionId: 7, identity: { installationId: '8' } }] } };
  for (const r of [{ kind: 'definition', id: 7 }, { kind: 'member-access-retirement', installation: { id: 8 } }, { kind: 'deployment-review-request', installation: { id: 8 } }]) assert.throws(() => guard(h, r), /business row remains open/);
  guard(h, { kind: 'definition', id: 9 }); h.state.resources[0].phase = 'deleted'; guard(h, { kind: 'definition', id: 7 });
});
test('unknown original source/task keeps exact definition, grant and installation until independent disposition readiness', () => {
  const source = { kind: 'source-effect-scenario', phase: 'created', scenarioDefinitionId: 7, identity: { installationId: '8' } };
  const h = { Blocked: Error, state: { resources: [source] } };
  for (const r of [{ kind: 'definition', id: 7 }, { kind: 'member-access-retirement', installation: { id: 8 } }, { kind: 'deployment-review-request', installation: { id: 8 } }]) assert.throws(() => guard(h, r), /remains open/);
  guard(h, { kind: 'definition', id: 9 });
  source.dispositionReady = true; guard(h, { kind: 'definition', id: 7 });
});
test('unknown observer role command holds only its original definition, grant and installation until confirmed', () => {
  const account = { kind: 'account', phase: 'created', scenarioDefinitionId: 7, scenarioInstallationIds: ['8'], authorityCommands: [{ outcome: 'unknown' }] };
  const h = { Blocked: Error, state: { resources: [account] } };
  for (const r of [{ kind: 'definition', id: 7 }, { kind: 'member-access-retirement', installation: { id: 8 } }, { kind: 'deployment-review-request', installation: { id: 8 } }])
    assert.throws(() => guard(h, r), /role assignment unresolved/);
  guard(h, { kind: 'definition', id: 9 }); guard(h, { kind: 'deployment-review-request', installation: { id: 9 } });
  account.authorityCommands[0].outcome = 'confirmed'; guard(h, { kind: 'definition', id: 7 });
});
test('native scenario refusal requires exact original acknowledged build actor, origin, input and non-preexisting package before any dispatch', async () => {
  for (const mode of ['valid', 'actor', 'origin', 'uuid', 'preexisting']) await fixture('refused', async (h, r, actor, count) => {
    const pkg = { id: 9, applicationUuid: 'original-uuid' };
    delete r.creation;
    Object.assign(r, { kind: 'native-provider-probe', actorIdentity: structuredClone(actor.identity), origin: actor.origin, applicationUuid: pkg.applicationUuid,
      preexistingIds: [], package: pkg, packageAcknowledged: true, commands: [{ method: 'POST', route: '/panel/application/deployment-packages/builds/',
        actorIdentity: structuredClone(actor.identity), origin: actor.origin, body: { applicationUuid: pkg.applicationUuid }, outcome: 'confirmed', response: { status: 200, data: { value: pkg } } }] });
    if (mode === 'actor') r.commands[0].actorIdentity.account = 'foreign';
    if (mode === 'origin') r.commands[0].origin = 'https://foreign.test';
    if (mode === 'uuid') r.commands[0].body.applicationUuid = 'foreign';
    if (mode === 'preexisting') r.preexistingIds = [pkg.id];
    if (mode === 'valid') { await probe(h, r, actor); assert.equal(count(), 1); }
    else { await assert.rejects(probe(h, r, actor), /Owned original/); assert.equal(count(), 0); }
  });
});
