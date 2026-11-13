const { test } = require('node:test');
const assert = require('node:assert/strict');
const actions = require('./business_action_cases.cjs');
const identity = { namespace: 'panel', deploymentId: 'a'.repeat(32), installationId: '9007199254740991', runtimeApplicationUuid: 'runtime', generation: 1, executionEpoch: 2, artifactDigest: 'sha256:' + 'b'.repeat(64) };
const row = () => ({ kind: 'business-record', phase: 'created', applicationKey: 'action-fixture', identity: structuredClone(identity), entity: '/test/record', recordId: '9223372036854775001', version: '9007199254740993', actionDefinitionId: 31, actionTemplateId: 32,
  actionCommands: [{ outcome: 'unknown', actorIdentity: { namespace: 'panel', account: 'original-action' } }] });
test('action query uses the actual normalized public route and preserves precise selectors', () => {
  const r = row(); r.applicationKey = 'app & Δ';
  for (const query of [true, false]) {
    const url = new URL(actions.route(r, query), 'https://original.invalid');
    assert.equal(url.pathname, query ? '/apps/entity/actions/' : '/apps/entity/action/execute/');
    assert.deepEqual([...url.searchParams], [['application', r.applicationKey], ['deploymentId', identity.deploymentId]]);
  }
});
test('receipt matching rejects independent identity, input, subject, time and int64 mutations', () => {
  const body = actions.request(row()), actor = { subject: 'panel/account:42' };
  const receipt = { apiVersion: body.apiVersion, operationId: body.operationId, identity: structuredClone(identity), inputDigest: actions.inputDigest(body), entity: body.entity, action: body.action, id: body.id, version: '9007199254740994', state: 'acknowledged', subject: actor.subject, executedAt: '2026-11-10T00:00:00.123456789Z' };
  assert.equal(actions.receiptMatches(actor, body, receipt), true);
  for (const patch of [{ id: '9223372036854775000' }, { version: '9007199254740992' }, { state: 'open' }, { subject: 'panel/account:43' }, { executedAt: 'invalid' }, { executedAt: '2026-02-31T00:00:00Z' }, { executedAt: '2026-11-10T00:00:00.1230Z' }, { executedAt: '2026-11-10T08:00:00+08:00' }, { inputDigest: 'sha256:' + '0'.repeat(64) }, { identity: { ...identity, executionEpoch: 1 } }, { operationId: 'c'.repeat(32) }, { action: 'other' }, { entity: '/test/peer' }]) assert.equal(actions.receiptMatches(actor, body, { ...receipt, ...patch }), false);
  for (const patch of [{ fields: [{ name: 'description', value: 'different' }] }, { expectedVersion: '9007199254740992' }, { identity: { ...identity, deploymentId: 'c'.repeat(32) } }]) assert.notEqual(actions.inputDigest({ ...body, ...patch }), receipt.inputDigest);
  assert.throws(() => actions.inputDigest({ ...body, identity: { ...identity, installationId: '9007199254740993' } }), /cannot round/);
});
test('action cleanup preserves exact actor, role, definition and both installation dependencies until original row disposition', () => {
  const r = row(), h = { state: { resources: [r] }, Blocked: Error };
  const dependencies = [{ kind: 'definition', id: 31 }, { kind: 'role-template', id: 32 },
    { kind: 'member-access-retirement', installation: { id: Number(identity.installationId) } },
    { kind: 'deployment-review-request', installation: { id: Number(identity.installationId) } },
    { kind: 'account', collection: '/cas/namespaces/panel/accounts/', creation: { intended: { account: 'original-action' } } }];
  for (const resource of dependencies) assert.throws(() => actions.guardCleanup(h, resource), /retain its original actor/);
  actions.guardCleanup(h, { ...dependencies[4], collection: '/cas/namespaces/peer/accounts/' });
  actions.guardCleanup(h, { kind: 'role-template', id: 33 });
  r.actionCommands[0].outcome = 'confirmed';
  for (const resource of dependencies) assert.throws(() => actions.guardCleanup(h, resource), /remains open/);
  r.phase = 'deleted'; for (const resource of dependencies) actions.guardCleanup(h, resource);
});
test('unresolved action blocks ordinary business row cleanup before any request or login', async () => {
  let touched = 0;
  const h = { Blocked: Error, login() { touched++; }, api() { touched++; } };
  await assert.rejects(require('./business_cases.cjs').cleanup(h, row()), /action result remains unresolved/);
  assert.equal(touched, 0);
});
test('unresolved original action is never resent by a new command attempt', async () => {
  let persisted = 0, sent = 0;
  const h = { Blocked: Error, persist() { persisted++; }, api() { sent++; } };
  const r = row(); r.origin = 'https://original.invalid';
  await assert.rejects(actions.command(h, { origin: r.origin }, r, actions.request(r)), /no execute replay/);
  assert.equal(sent, 0); assert.equal(persisted, 0);
});
test('refusal cannot be proved by authentication failure, generic error or successful-looking partial response', () => {
  const response = { status: 200, data: { error: { code: 21, message: '动作状态前置条件不满足' } } };
  assert.equal(actions.refused(response, 21, response.data.error.message), true);
  for (const other of [{ ...response, status: 401 }, { status: 200, data: { error: { code: 5, message: '动作状态前置条件不满足' } } }, { status: 200, data: { ...response.data, value: {} } }, { status: 200, data: { error: { code: 21, message: 'other' } } }]) assert.equal(actions.refused(other, 21, response.data.error.message), false);
});
test('real UI action observation excludes forged installation, peer origin, repeated selectors and non-action writes', () => {
  const r = row(), origin = 'https://panel.local.vpc', body = actions.request(r);
  for (const query of [false, true]) {
    const url = origin + '/api/v1/web/proxy' + actions.route(r, query);
    const req = (overrides = {}) => ({ method: () => 'POST', url: () => url, postDataJSON: () => body, ...overrides });
    assert.equal(actions.exactActionRequest(req(), origin, r, query), true);
    for (const patch of [{ method: () => 'GET' }, { url: () => url.replace('panel.local.vpc', 'peer.local.vpc') }, { url: () => url + '&application=peer' },
      { url: () => url + '&deploymentId=' + r.identity.deploymentId }, { url: () => url.replace('/apps/entity/', '/apps/entity/value/write/') },
      { postDataJSON: () => ({ ...body, identity: { ...identity, executionEpoch: 3 } }) }, { postDataJSON: () => ({ ...body, id: '22' }) },
      { postDataJSON: () => ({ ...body, action: 'other' }) }, { postDataJSON: () => { throw Error('not JSON'); } }]) assert.equal(actions.exactActionRequest(req(patch), origin, r, query), false);
  }
});
test('additional matrix templates and new original action rows remain protected before first action dispatch', () => {
  const r = row(); r.actionCommands = []; r.actionTemplateIds = [41, 42];
  const h = { state: { resources: [r] }, Blocked: Error };
  for (const id of [32, 41, 42]) assert.throws(() => actions.guardCleanup(h, { kind: 'role-template', id }), /remains open/);
  assert.throws(() => actions.guardCleanup(h, { kind: 'deployment-review-request', installation: { id: Number(identity.installationId) } }), /remains open/);
  actions.guardCleanup(h, { kind: 'role-template', id: 43 });
});
test('unknown role assignment or retirement protects its exact template even after original rows were disposed', () => {
  const template = { kind: 'role-template', creation: { intended: { key: 'original' } } };
  for (const command of [{ outcome: 'unknown', retiredTemplateKey: 'original' }, { outcome: 'unknown', body: { roleTemplateKeys: ['portal-basic-user', 'original'] } }]) {
    const h = { state: { resources: [{ kind: 'account', phase: 'created', authorityCommands: [command] }] }, Blocked: Error };
    assert.throws(() => actions.guardCleanup(h, template), /retirement remains unresolved/);
    actions.guardCleanup(h, { kind: 'role-template', creation: { intended: { key: 'other' } } });
    command.outcome = 'confirmed'; actions.guardCleanup(h, template);
  }
});
const http = require('node:http');
const { ownerRequest } = require('./owner_transport.cjs');
async function realOwner(mode, run) {
  let origin, actor, current = { id: 21, code: 'original-code', name: 'open', description: null, sortOrder: 0, version: 1 }, writes = 0, queries = 0, receipt;
  const server = http.createServer(async (req, res) => {
    const payload = []; for await (const part of req) payload.push(part);
    const input = payload.length ? JSON.parse(Buffer.concat(payload)) : null;
    const url = new URL(req.url, origin);
    const send = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
    if (req.method === 'GET' && url.pathname === '/api/v1/web/proxy/apps/entity/values/21') return send(current ? { value: current } : { error: { code: 2, message: 'not found' } });
    assert.equal(req.method, 'POST');
    if (url.pathname.startsWith('/api/v1/web/proxy/apps/entity/value/write/')) {
      const write = url.pathname.endsWith('/execute/');
      if (write) {
        writes++;
        if (mode === 'not-committed') { req.socket.destroy(); return; }
        receipt = { apiVersion: input.apiVersion, operationId: input.operationId, identity: input.identity,
          inputDigest: require('./business_cases.cjs').inputDigest(input), subject: actor.subject, entity: input.entity,
          operation: input.operation, id: input.id, version: input.operation === 'update' ? '2' : '1' };
        current = input.operation === 'delete' ? null : { ...current, sortOrder: mode === 'partial-row' ? 42 : input.fields[0].value, version: 2 };
        if (mode === 'lost' || mode === 'drift') {
          if (mode === 'drift') actor.identity.account = 'peer';
          req.socket.destroy(); return;
        }
      } else queries++;
      return send(receipt ? { value: receipt } : { error: { code: 2, message: 'not committed' } });
    }
    if (url.pathname === '/api/v1/web/proxy/apps/entity/action/execute/') {
      writes++;
      if (mode === 'not-committed') { req.socket.destroy(); return; }
      if (mode === 'wrong-refusal') { res.statusCode = 401; send({ error: { code: 11, message: 'login required' } }); return; }
      receipt = { apiVersion: input.apiVersion, operationId: input.operationId, identity: input.identity, inputDigest: actions.inputDigest(input),
        entity: input.entity, action: input.action, id: input.id, version: '2', state: 'acknowledged', subject: actor.subject, executedAt: '2026-11-10T00:00:00.123456789Z' };
      current = { ...current, name: 'acknowledged', version: 2, description: mode === 'partial-row' ? 'incorrect persisted input' : input.fields[0].value };
      if (mode === 'wrong-subject') receipt.subject = 'panel/account:other';
      if (mode === 'lost' || mode === 'drift') {
        if (mode === 'drift') actor.identity.account = 'peer';
        req.socket.destroy(); return;
      }
      send({ value: receipt }); return;
    }
    assert.equal(url.pathname, '/api/v1/web/proxy/apps/entity/actions/'); queries++;
    if (mode === 'wrong-refusal') { res.statusCode = 401; send({ error: { code: 11, message: 'login required' } }); return; }
    send(receipt ? { value: receipt } : { error: { code: 2, message: '原业务操作尚无完成事实；禁止据此自动重发' } });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); origin = 'http://127.0.0.1:' + server.address().port;
  actor = { origin, identity: { namespace: 'panel', account: 'original' }, subject: 'panel/account:42', context: { async cookies() { return []; }, async addCookies() {}, async clearCookies() {} } };
  const r = row(); r.identity.installationId = '7'; r.recordId = '21'; r.version = '1'; r.origin = origin; r.actorRole = 'manager'; r.actorIdentity = structuredClone(actor.identity); r.actionCommands = []; r.commands = [];
  const journal = [], h = { deliveryActors: { manager: actor }, state: { resources: [r] }, Blocked: Error,
    good: response => response?.status === 200 && !response.data.error, persist() { journal.push(structuredClone(r)); }, observe() {},
    check(label, ok) { assert.ok(ok, label); }, api: (caller, method, route, body) => ownerRequest(caller, method, route, body) };
  try { await run({ h, actor, r, stats: () => ({ writes, queries, current }), journal }); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
test('one actual HTTP action commit with lost response is confirmed by original query and independent full row without replay', async () => {
  await realOwner('lost', async ({ h, actor, r, stats, journal }) => {
    const body = actions.request(r), receipt = await actions.command(h, actor, r, body);
    assert.equal(receipt.operationId, body.operationId); assert.equal(r.version, '2');
    assert.equal(stats().writes, 1); assert.equal(stats().queries, 1); assert.equal(r.actionCommands[0].outcome, 'confirmed');
    assert.ok(r.actionCommands[0].transportError);
    assert.equal(journal.find(s => s.actionCommands.length)?.actionCommands[0].outcome, 'unknown');
  });
});
test('real HTTP missing completion, wrong subject or partial persisted row retain unknown command and block replay/cleanup', async () => {
  for (const mode of ['not-committed', 'wrong-subject', 'partial-row']) await realOwner(mode, async ({ h, actor, r, stats }) => {
    await assert.rejects(actions.command(h, actor, r, actions.request(r)), /exactly one transition/);
    assert.equal(r.actionCommands[0].outcome, 'unknown'); assert.equal(r.version, '1');
    await assert.rejects(actions.command(h, actor, r, actions.request(r)), /no execute replay/);
    await assert.rejects(require('./business_cases.cjs').cleanup(h, r), /action result remains unresolved/);
    assert.equal(stats().writes, 1); assert.equal(stats().queries, 1);
  });
});
test('real HTTP authentication failure cannot satisfy a target business-rule refusal', async () => {
  await realOwner('wrong-refusal', async ({ h, actor, r, stats }) => {
    await assert.rejects(actions.command(h, actor, r, actions.request(r), { code: 21, message: '动作状态前置条件不满足' }), /Target action refusal/);
    assert.equal(r.actionCommands[0].outcome, 'unknown'); assert.equal(stats().current.name, 'open');
  });
});
test('real HTTP loss followed by actor drift cannot query original receipt using a replacement principal', async () => {
  await realOwner('drift', async ({ h, actor, r, stats }) => {
    await assert.rejects(actions.command(h, actor, r, actions.request(r)), /remain unchanged before querying/);
    assert.equal(stats().writes, 1); assert.equal(stats().queries, 0); assert.equal(r.actionCommands[0].outcome, 'unknown');
  });
});
test('data matrix confirms one real HTTP update or delete after lost response using original receipt and independent owner read', async () => {
  for (const operation of ['update', 'delete']) await realOwner('lost', async ({ h, actor, r, stats, journal }) => {
    await actions.dataCommand(h, actor, r, operation, true);
    assert.equal(r.commands[0].outcome, 'confirmed'); assert.ok(r.commands[0].transportError);
    assert.equal(stats().writes, 1); assert.equal(stats().queries, 1);
    assert.equal(r.phase, operation === 'delete' ? 'delete-acknowledged' : 'created');
    assert.equal(operation === 'delete' ? stats().current : stats().current.sortOrder, operation === 'delete' ? null : 1);
    assert.equal(journal.find(s => s.commands.length).commands[0].outcome, 'unknown');
  });
});
test('data matrix retains unknown completion or inconsistent full row and forbids another execute or cleanup', async () => {
  for (const mode of ['not-committed', 'partial-row']) await realOwner(mode, async ({ h, actor, r, stats }) => {
    await assert.rejects(actions.dataCommand(h, actor, r, 'update', true), /independent full owner row/);
    assert.equal(r.commands[0].outcome, 'unknown');
    await assert.rejects(actions.dataCommand(h, actor, r, 'update', true), /no matrix write replay/);
    await assert.rejects(require('./business_cases.cjs').cleanup(h, r), /no execute replay/);
    assert.equal(stats().writes, 1); assert.equal(stats().queries, 1);
  });
});
test('data matrix never queries a lost-response operation with a replacement actor or changed origin', async () => {
  await realOwner('drift', async ({ h, actor, r, stats }) => {
    await assert.rejects(actions.dataCommand(h, actor, r, 'update', true), /remain unchanged before querying/);
    assert.equal(r.commands[0].outcome, 'unknown'); assert.equal(stats().writes, 1); assert.equal(stats().queries, 0);
  });
  await realOwner('lost', async ({ h, actor, r, stats }) => {
    actor.origin += '/replacement';
    await assert.rejects(actions.dataCommand(h, actor, r, 'delete', true), /origin changed/);
    assert.equal(stats().writes, 0); assert.equal(stats().queries, 0);
  });
});
test('route-level privilege denial is a refusal only for an explicit empty 403', () => {
  assert.equal(actions.routeDenied({ status: 403, data: { text: '' } }), true);
  assert.equal(actions.routeDenied({ status: 403, data: {} }), true);
  assert.equal(actions.routeDenied({ status: 403, data: { error: { code: 5, message: 'owner refusal' } } }), false);
  assert.equal(actions.routeDenied({ status: 401, data: { text: '' } }), false);
  assert.equal(actions.routeDenied({ status: 403, data: { text: 'forbidden' } }), false);
  assert.equal(actions.routeDenied({ status: 403, data: { text: '', value: { id: 1 } } }), false);
  assert.equal(actions.routeDenied(null), false);
});
