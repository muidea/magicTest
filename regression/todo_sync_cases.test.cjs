const test = require('node:test');
const assert = require('node:assert/strict');
const { binding, sourceIdentity, pendingMatches, observe, confirmSourceExit } = require('./todo_sync_cases.cjs');
const { guard } = require('./scenario_commands.cjs');
function fixture() {
  const r = { kind: 'business-record', phase: 'delete-acknowledged', recordId: '9007199254740993', entity: '/source/item', scenarioDefinitionId: 5,
    identity: { runtimeApplicationUuid: 'runtime-a', namespace: 'panel', installationId: '71' }, todoSync: {} };
  const row = { name: 'Δ source' }, value = { id: 42, identity: sourceIdentity(r), namespace: 'panel', hostedBy: 'runtime-a', sourceKey: 'runtime-a',
    sourceEntity: r.entity, sourceID: r.recordId, sourceAction: 'regression-todo-sync', status: 'pending', title: row.name, content: row.name + ':pending', finishTime: 0, createTime: 10, updateTime: 12 };
  const h = { Blocked: Error, admin: {}, state: { resources: [r] }, persist() {}, check(label, condition) { assert.ok(condition, label); } };
  return { h, r, row, value };
}
test('source projection rejects duplicates, foreign binding, rounded IDs and recreated todo identity', () => {
  const { r, row, value } = fixture();
  assert.ok(pendingMatches([value], r, row));
  assert.equal(pendingMatches([value, { ...value, id: 43 }], r, row), false);
  for (const change of [{ id: 0 }, { identity: 'foreign' }, { namespace: 'other' }, { hostedBy: 'runtime-b' }, { sourceKey: 'runtime-b' },
    { sourceID: '9007199254740992' }, { sourceAction: 'other' }, { sourceEntity: '/other/item' }, { status: 'done' }, { title: 'stale' }, { content: 'stale' }, { finishTime: 1 }])
    assert.equal(pendingMatches([{ ...value, ...change }], r, row), false, JSON.stringify(change));
  for (const change of [{ id: 43 }, { createTime: 11 }, { updateTime: 11 }])
    assert.equal(pendingMatches([{ ...value, ...change }], r, row, value), false);
  assert.ok(pendingMatches([{ ...value, updateTime: 13 }], r, row, value));
});
test('pending exit reads actual scoped projection and keeps same-source alternate-action duplicates visible', async () => {
  const { h, r, value } = fixture(); let reads = 0;
  h.directory = async (actor, route) => { assert.equal(actor, h.admin); assert.equal(route, '/panel/todos/'); reads++; return []; };
  await confirmSourceExit(h, r); assert.equal(reads, 1); assert.equal(r.todoSync.pendingAbsent, true);
  assert.equal(pendingMatches([value, { ...value, id: 44, identity: 'other', sourceAction: 'other' }], r, { name: 'Δ source' }), false);
});
test('unreadable todo owner leaves source disposal open and preserves installation dependencies', async () => {
  const { h, r } = fixture(); h.directory = async () => { throw Error('owner read unavailable'); };
  await assert.rejects(confirmSourceExit(h, r), /owner read unavailable/);
  assert.equal(r.todoSync.pendingAbsent, undefined); assert.notEqual(r.phase, 'deleted');
  for (const resource of [{ kind: 'definition', id: 5 }, { kind: 'deployment-review-request', installation: { id: 71 } }, { kind: 'member-access-retirement', installation: { id: 71 } }])
    assert.throws(() => guard(h, resource), /business row remains open/);
});
test('todo binding uses formal typed hooks without mutating catalogue and pins one sourceAction for delete', () => {
  const catalog = [{ id: 'builtin', kind: 'todo', stageInfo: { functions: Object.fromEntries(['insert', 'update', 'delete'].map(k => [k, { eventID: '/todos/sync/', checkType: 'postCheck', input: {} }])) } }];
  const before = structuredClone(catalog), b = binding(catalog, 'panel');
  assert.deepEqual(catalog, before); assert.equal(b.stageInfo.functions.update.input.statusField, 'description');
  for (const hook of Object.values(b.stageInfo.functions)) {
    assert.equal(hook.input.namespace, 'panel'); assert.equal(hook.input.sourceAction, 'regression-todo-sync');
    assert.equal(hook.eventID, '/todos/sync/'); assert.equal(hook.checkType, 'postCheck');
  }
  assert.throws(() => binding([], 'panel'), /Formal todo catalogue/);
});
test('pending observation failure cannot overwrite original stable todo identity', async () => {
  const { h, r } = fixture(); r.todoSync.pending = { id: 42, identity: sourceIdentity(r) };
  const before = structuredClone(r.todoSync.pending); h.directory = async () => { throw Error('projection unavailable'); };
  await assert.rejects(observe(h, r, { name: 'new' }), /projection unavailable/);
  assert.deepEqual(r.todoSync.pending, before);
});
