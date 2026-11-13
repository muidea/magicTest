const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { submit, decodeTasks, targetCode, effectEntities } = require('./source_effect_cases.cjs');
const business = require('./business_cases.cjs');
const { ownerRequest } = require('./owner_transport.cjs');
test('historical-task gap requires exact generation-only advance, terminal original tasks and precise owner refusal', () => {
  const { historyVisibilityGap } = require('./source_effect_cases.cjs');
  const before = { installationId: '7', generation: 2, executionEpoch: 1 }, after = { ...before, generation: 4 };
  const tasks = [{ state: 'completed' }], response = { status: 409, data: { error: { code: 19, message: '派生任务要求当前运行安装及相同代际；停用或历史实例暂不可查询' } } };
  assert.equal(historyVisibilityGap(before, after, tasks, [], response), true);
  for (const [identity, original, current, res] of [
    [before, tasks, [], response], [{ ...after, installationId: '8' }, tasks, [], response],
    [{ ...after, executionEpoch: 2 }, tasks, [], response], [after, [], [], response],
    [after, [{ state: 'running' }], [], response], [after, tasks, tasks, response],
    [after, tasks, [], { ...response, status: 503 }],
    [after, tasks, [], { status: 409, data: { error: { code: 19, message: 'other conflict' } } }],
    [after, tasks, [], { ...response, data: { ...response.data, value: { leaked: true } } }],
  ]) assert.equal(historyVisibilityGap(before, identity, original, current, res), false);
});
test('original lifecycle recovery uses complete immutable owner baselines and rejects drift, wrong actors or truncated history', () => {
  const { lifecycleBaseline } = require('./source_effect_cases.cjs');
  const identity = { installationId: '7', deploymentId: 'a'.repeat(32), generation: 2 }, actor = { account: 'original', namespace: 'panel' };
  const response = { status: 200, data: { error: { code: 2, message: 'running application not found' } } };
  const r = { identity, origin: 'https://panel.test', actorIdentity: actor, applicationKey: 'app', entity: '/app/source', targetEntity: '/app/target',
    commands: [{ outcome: 'confirmed' }, { body: { operationId: 'original-refused' }, response, outcome: 'unknown' }],
    receipt: { id: '21' }, task: { intentId: 'a'.repeat(32), version: '1', attempts: '1', state: 'completed' }, targets: [{ id: 31 }] };
  const disable = { action: 'disable', method: 'POST', route: '/panel/application/installations/7/disable', body: { expectedUpdateTime: 1 }, response: { status: 200 }, after: { id: 7, status: 'disabled' }, outcome: 'confirmed' };
  const activate = { action: 'activate', before: disable.after, outcome: 'unknown' }, request = { scenarioCommands: [disable, activate] };
  const collection = (entity, rows) => ({ kind: 'request', method: 'GET', actor, origin: r.origin,
    route: '/apps/entity/values/?application=app&deploymentId=' + identity.deploymentId + '&entity=' + encodeURIComponent(entity) + '&_pageNum=1&_pageSize=5',
    response: { status: 200, data: { values: rows, pagination: { total: rows.length, pageSize: 5, pageNum: 1 } } } });
  const trace = [collection(r.entity, [{ id: 21 }]), collection(r.targetEntity, r.targets),
    { kind: 'request', method: 'POST', route: '/panel/application/installations/7/effects/search', body: { identity, cursor: '', limit: 50, state: '' },
      response: { status: 200, data: { value: { manager: 'panel/account:1', identity, values: [r.task], nextCursor: '' } } } },
    { kind: 'assertion', passed: true, message: 'Durable original task completed with actual attempt and no failure' },
    { kind: 'request', method: 'POST', route: disable.route, body: disable.body, response: disable.response },
    { kind: 'request', method: 'POST', route: require('./source_effect_cases.cjs').route(r, false), actor, origin: r.origin, body: r.commands[1].body, response },
    { kind: 'assertion', passed: false, message: 'Exact original conditional activate receipt and independent owner preserve runtime/storage identities', details: activate }];
  assert.deepEqual(lifecycleBaseline(trace, r, request), { sources: [{ id: 21 }], targets: [{ id: 31 }], tasks: [r.task] });
  for (const alter of [t => t[0].response.data.pagination.total++, t => t[1].response.data.values[0].id++,
    t => t[2].response.data.value.nextCursor = 'b'.repeat(32), t => t[5].actor.account = 'other',
    t => t[5].body.operationId = 'replacement', t => t[6].details.before.id = 8, t => t[3].passed = false]) {
    const copy = structuredClone(trace); alter(copy); assert.throws(() => lifecycleBaseline(copy, r, request));
  }
});
test('disabled source gate accepts only exact no-runtime envelope, never generic errors or a receipt', () => {
  const { disabledSourceRefusal } = require('./source_effect_cases.cjs');
  const response = { status: 200, data: { error: { code: 2, message: 'running application not found' } } };
  assert.equal(disabledSourceRefusal(response), true);
  for (const alter of [v => v.status = 404, v => v.status = 403, v => v.data.error.code = 21,
    v => v.data.error.message = 'other not found', v => v.data.value = { operationId: 'unexpected' }, v => delete v.data.error]) {
    const value = structuredClone(response); alter(value); assert.equal(disabledSourceRefusal(value), false);
  }
  assert.equal(disabledSourceRefusal(undefined), false);
});
test('all actual source-effect handlers request distinct per-run fixture names before any author write', async t => {
  const pages = require('./page_runtime_cases.cjs'), { handlers } = require('./source_effect_cases.cjs'), names = [];
  t.mock.method(pages, 'explicitFixture', async (_h, _a, _b, options) => {
    names.push(options.suffix); throw Error('captured before author write');
  });
  for (const handler of Object.values(handlers)) await assert.rejects(handler({}), /captured before author write/);
  assert.equal(names.length, 6); assert.equal(new Set(names).size, names.length);
});
test('independent target identity calculation binds deployment, original natural source and candidate without ambiguous joins', () => {
  const parts = ['a'.repeat(32), 'SOURCE', 'first'];
  const expected = execFileSync('python3', ['-B', '-c', 'import json,hashlib,base64,sys;print("E-"+base64.b32encode(hashlib.sha256(json.dumps(json.loads(sys.argv[1]),separators=(",",":")).encode()).digest()).decode().rstrip("="))', JSON.stringify(parts)], { encoding: 'utf8' }).trim();
  assert.equal(targetCode(...parts), expected);
  assert.notEqual(targetCode('a', 'b|c', 'd'), targetCode('a', 'b', 'c|d'));
  assert.notEqual(targetCode(...parts), targetCode('b'.repeat(32), parts[1], parts[2]));
});
test('task collection rejects foreign identity, truncation signals, unsafe counters, repeated or reversed continuation', () => {
  const identity = { installationId: '7' }, manager = 'panel/account:1', cursor = '';
  const value = { identity, manager, nextCursor: '', values: [{ intentId: 'a'.repeat(32), version: '1', attempts: '1', state: 'completed' }] };
  assert.deepEqual(decodeTasks(value, identity, manager, cursor), value);
  for (const mutate of [v => v.identity.installationId = '8', v => v.manager = 'foreign', v => delete v.values, v => v.values.push(v.values[0]),
    v => v.values[0].version = '0', v => v.values[0].attempts = '-1', v => v.values[0].state = 'unknown', v => v.nextCursor = 'b'.repeat(32), v => delete v.nextCursor]) {
    const bad = structuredClone(value); mutate(bad); assert.throws(() => decodeTasks(bad, identity, manager, cursor));
  }
  assert.throws(() => decodeTasks(value, identity, manager, 'b'.repeat(32)));
});
async function originalSource(mode, run) {
  let writes = 0, receipt;
  const server = http.createServer(async (req, res) => {
    for await (const chunk of req) void chunk;
    res.setHeader('Content-Type', 'application/json');
    if (req.url.includes('/execute/')) { writes++; return req.socket.destroy(); }
    const value = structuredClone(receipt);
    if (mode === 'foreign') value.subject = 'panel/account:2';
    if (mode === 'missing-intent') value.source.effects = [];
    res.end(JSON.stringify({ value }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port, actor = { origin, identity: { account: 'original', namespace: 'panel' }, subject: 'panel/account:1',
    context: { async cookies() { return []; }, async addCookies() {}, async clearCookies() {} } };
  const identity = { namespace: 'panel', deploymentId: 'a'.repeat(32), installationId: '7', runtimeApplicationUuid: 'runtime', generation: 1, executionEpoch: 1, artifactDigest: 'sha256:' + 'b'.repeat(64) };
  const r = { origin, actorIdentity: structuredClone(actor.identity), commands: [], identity, applicationKey: 'source', entity: '/source/reading' };
  const body = business.request(r, 'create', [{ name: 'code', value: 'SRC' }], { apiVersion: 'magic.entity-source-write/v1' });
  receipt = { apiVersion: body.apiVersion, operationId: body.operationId, identity, entity: body.entity, operation: 'create', id: '101', version: '1', subject: actor.subject, inputDigest: business.inputDigest(body) };
  receipt.source = { apiVersion: 'magic.entity-value-source/v1', identity, operationId: body.operationId, inputDigest: receipt.inputDigest, subject: actor.subject, entity: body.entity, id: '101', version: '1', keyDigest: 'sha256:' + 'c'.repeat(64), payloadDigest: 'sha256:' + 'd'.repeat(64),
    effects: [{ apiVersion: 'magic.script-effect-execution/v1', identity, intentId: 'e'.repeat(32), subject: actor.subject, sourceEntity: body.entity, sourceId: '101', bindingKey: 'derive', planDigest: 'sha256:' + 'f'.repeat(64), sourceDigest: 'sha256:' + '1'.repeat(64) }] };
  const h = { Blocked: Error, api: (a, ...args) => ownerRequest(a, ...args), good: v => v?.status === 200 && !v.data.error, check: (m, c) => assert.ok(c, m), persist() {} };
  try { await run(h, actor, r, body, () => writes); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
test('lost real HTTP source response is confirmed only by exact original durable receipt without execute replay', async () => {
  await originalSource('valid', async (h, actor, r, body, writes) => {
    await submit(h, actor, r, body); assert.equal(writes(), 1); assert.equal(r.commands[0].outcome, 'confirmed');
    assert.equal(r.commands[0].receipt.source.effects[0].sourceId, '101');
  });
});
test('foreign subject or absent source intent leaves original lost command unknown and forbids further source dispatch', async () => {
  for (const mode of ['foreign', 'missing-intent']) await originalSource(mode, async (h, actor, r, body, writes) => {
    await assert.rejects(submit(h, actor, r, body)); assert.equal(r.commands[0].outcome, 'unknown');
    await assert.rejects(submit(h, actor, r, body), /no execute replay/); assert.equal(writes(), 1);
  });
});
test('effect fixture keeps original input unchanged, separately names target and strips target business-code pattern', () => {
  const entity = { id: 1, name: 'source', pkgPath: '/sample', fields: [{ name: 'code', spec: { constraint: 'req,regex=old' } }], writeRules: { versionField: 'version', immutable: ['code'] } };
  const binding = { stageInfo: { functions: { insert: {} } } }, before = structuredClone(entity);
  const [source, target] = effectEntities(entity, binding);
  const persisted = { ...entity, id: 17, createTime: 21, updateTime: 31, expectedEntityVersion: 31 };
  const expanded = effectEntities(persisted, binding);
  const payload = require('./authoring_cases.cjs').authoring.command({ definitionVersion: 41, entities: [persisted] }, expanded);
  assert.equal(payload.entities[0].id, 17); assert.equal(payload.entities[0].expectedEntityVersion, 31);
  assert.equal(payload.entities[1].id, 0); assert.equal(payload.entities[1].expectedEntityVersion, undefined);
  assert.equal(expanded[1].createTime, undefined); assert.equal(persisted.updateTime, 31);
  assert.deepEqual(entity, before); assert.notEqual(source.name, target.name);
  assert.equal(source.writeRules.appendOnly, true); assert.deepEqual(target.blockInfo, []);
  assert.equal(target.fields[0].spec.constraint, 'req,max=64');
});
