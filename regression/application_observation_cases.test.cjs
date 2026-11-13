const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validatePage, denied } = require('./application_observation_cases.cjs');
test('application observation pagination rejects incomplete, unsafe, repeated or foreign rows instead of claiming an empty result', () => {
  const identity = { namespace: 'panel', runtimeApplicationUuid: 'runtime' };
  const v = { identity, pagination: { total: 1, pageNum: 1, pageSize: 100 }, values: [{ id: '9007199254740993', namespace: 'panel', hostedBy: 'runtime', targetNamespace: 'panel' }] };
  assert.equal(validatePage(v, identity, 'operation-logs', 1, 100, undefined).last, 9007199254740993n);
  for (const change of [x => x.values = [], x => x.identity.namespace = 'foreign', x => x.values[0].hostedBy = 'other',
    x => x.values[0].id = 9007199254740992, x => x.pagination.hasMore = true, x => x.pagination.total = 101]) {
    const bad = structuredClone(v); change(bad); assert.throws(() => validatePage(bad, identity, 'operation-logs', 1, 100, undefined));
  }
  assert.throws(() => validatePage(v, identity, 'operation-logs', 1, 100, 9007199254740993n));
  assert.throws(() => validatePage(v, identity, 'operation-logs', 1, 100, undefined, 2));
  const two = structuredClone(v); two.pagination.total = 2;
  two.values.push({ ...two.values[0], id: '8' });
  assert.equal(validatePage(two, identity, 'operation-logs', 1, 100, undefined).last, 8n);
  two.values.reverse(); assert.throws(() => validatePage(two, identity, 'operation-logs', 1, 100, undefined));
});
test('observation authority proof rejects generic login, absent routes and error responses carrying data', () => {
  assert.ok(denied({ status: 401, data: { error: { code: 5 } } }));
  for (const r of [{ status: 401, data: { error: { code: 11 } } }, { status: 404, data: {} }, { status: 403, data: { error: { code: 5 }, value: { id: 1 } } }]) assert.equal(denied(r), false);
});
