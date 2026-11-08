const { test } = require('node:test');
const assert = require('node:assert/strict');
const { duplicate, connectionFailure } = require('./database_cases.cjs');
const { reconcileDatabaseCommands } = require('./database_cases.cjs');
test('original placement acknowledgement reconciles only against the complete unchanged owner directory without replay', async () => {
  for (const mode of ['exact', 'changed', 'wrong-command']) {
    const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.invalid';
    const value = { id: 5, instance: { id: 7 }, namespace: 'owned', mode: 'dedicated', status: 'active', resourceVersion: 2 };
    const resource = { id: 7, kind: 'database-instance', collection: '/panel/operations/database-instances/', creation: { actorIdentity: identity, origin, response: { status: 200, data: { value: { id: 7 } } } },
      pendingDatabaseCommands: [{ route: '/panel/operations/namespace-storage-placements/5', body: { instanceId: 7, namespace: 'owned', mode: 'dedicated', status: 'active', expectedResourceVersion: 1 }, response: { status: 200, data: { value } }, confirmed: false }] };
    let reads = 0;
    const h = { admin: { identity, origin }, Blocked: Error, good: r => r.status === 200 && r.data.error == null,
      check(label, condition) { assert.ok(condition, label); }, persist() {},
      async directory() { reads++; return [{ ...value, ...(mode === 'changed' ? { namespace: 'other' } : {}) }]; } };
    if (mode === 'wrong-command') resource.pendingDatabaseCommands[0].body.instanceId = 8;
    if (mode === 'exact') { await reconcileDatabaseCommands(h, resource); assert.ok(resource.pendingDatabaseCommands[0].confirmed); }
    else { await assert.rejects(reconcileDatabaseCommands(h, resource)); assert.equal(resource.pendingDatabaseCommands[0].confirmed, false); }
    assert.equal(reads, mode === 'wrong-command' ? 0 : 1);
  }
});
test('database boundary acceptance requires the real uniqueness and network stages', () => {
  assert.ok(duplicate({ status: 409, data: { error: { code: 7, message: '该数据库端点已登记，请使用现有数据库实例' }, value: null } }));
  for (const code of [4, 5, 11, 12, 15, 19, 22]) assert.ok(!duplicate({ status: 200, data: { error: { code, message: '数据库端点已登记' } } }));
  assert.ok(connectionFailure({ status: 200, data: { error: { code: 15, message: 'dial tcp 127.0.0.1:9: connect: connection refused' }, value: null } }));
  for (const message of ['database instance private storage capability is unavailable', 'storage credential contract is invalid', 'database explorer host is incomplete', 'authority denied', 'request timeout']) assert.ok(!connectionFailure({ status: 200, data: { error: { code: 15, message }, value: null } }));
  for (const code of [5, 11, 12, 22]) assert.ok(!connectionFailure({ status: 403, data: { error: { code, message: 'failed to connect' } } }));
  assert.ok(!connectionFailure({ status: 200, data: { error: { code: 15, message: 'failed to connect' }, value: { overview: {} } } }));
});
