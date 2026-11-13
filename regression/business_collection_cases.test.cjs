const { test } = require('node:test');
const assert = require('node:assert/strict');
const { decodeCollection, collection, decodeComposite, compareComposite } = require('./business_collection_cases.cjs');
const data = (rows, page = {}) => ({ values: rows, pagination: { total: 3, pageSize: 2, pageNum: 1, mode: 'cursor', ...page } });
test('owner collection decoder rejects truncated or contradictory cursors, unsafe IDs and changed totals', () => {
  const valid = data([{ id: 1 }, { id: 2 }], { hasMore: true, nextCursor: '2' });
  assert.equal(decodeCollection(valid, 'cursor', 1, 2).rows.length, 2);
  for (const invalid of [
    { ...valid, error: { code: 4 } }, data(null), data([{ id: 1 }, { id: 1 }]), data([{ id: 9007199254740992 }]),
    data([{ id: 1 }], { hasMore: true, nextCursor: '1' }), data([{ id: 1 }, { id: 2 }], { hasMore: true, nextCursor: '1' }),
    data([{ id: 1 }, { id: 2 }], { nextCursor: '2' }), data([{ id: 1 }], { pageNum: 2 }),
  ]) assert.throws(() => decodeCollection(invalid, 'cursor', 1, 2));
  assert.throws(() => decodeCollection(valid, 'cursor', 1, 2, 4));
});
function harness() {
  const actor = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.test' };
  const context = { applicationKey: 'sample', entity: '/sample/item', identity: { deploymentId: 'd'.repeat(32) } };
  const h = { Blocked: Error, observe() {}, good: r => r.status === 200 && !r.data.error, check(message, ok) { assert.ok(ok, message); } };
  return { actor, context, h };
}
test('owner collection preserves installation, filters and original actor while walking real primary cursor', async () => {
  const { h, actor, context } = harness(); const routes = [];
  const rows = await collection(h, actor, context, 'cursor', 2, async (actual, route, identity) => {
    assert.equal(actual, actor); assert.deepEqual(identity, context.identity);
    const url = new URL(route, actor.origin); routes.push(url);
    assert.equal(url.searchParams.get('entity'), context.entity); assert.equal(url.searchParams.get('deploymentId'), context.identity.deploymentId);
    return { status: 200, data: routes.length === 1 ? data([{ id: 1 }, { id: 2 }], { hasMore: true, nextCursor: '2' }) : data([{ id: 3 }]) };
  });
  assert.deepEqual(rows.map(r => r.id), [1, 2, 3]); assert.equal(routes[1].searchParams.get('_after'), '2');
});
test('collection refuses missing tail, repeated identities and actor drift instead of proving completeness', async () => {
  for (const mode of ['missing', 'duplicate', 'actor', 'installation']) {
    const { h, actor, context } = harness(); let calls = 0;
    await assert.rejects(collection(h, actor, context, 'cursor', 2, async () => {
      calls++;
      if (mode === 'actor') actor.identity.account = 'other';
      if (mode === 'installation') context.identity.deploymentId = 'other';
      return { status: 200, data: calls === 1 ? data([{ id: 1 }, { id: 2 }], { hasMore: mode !== 'missing', ...(mode === 'missing' ? {} : { nextCursor: '2' }) }) : data([{ id: 2 }]) };
    }), /ended|repeated|actor or installation/);
    assert.ok(calls <= 2);
  }
});
function frozen() {
  const context = { identity: { installationId: '1' }, pageDigest: 'digest' };
  const row = id => ({ fields: [{ key: 'id', value: { kind: 'integer', number: id } }, { key: 'name', value: { kind: 'string', text: 'same' } }, { key: 'sortOrder', value: { kind: 'integer', number: '0' } }] });
  const value = { identity: context.identity, pageDigest: context.pageDigest, sourceKey: 'records', readAt: '2026-11-09T00:00:00.000Z', value: { apiVersion: 'magic.base-value-read/v1', rows: [row('9007199254740993'), row('9007199254740994')] } };
  return { context, value };
}
test('composite source decoder preserves exact large IDs and rejects wrong identity, partial projections and malformed completion', () => {
  const { context, value } = frozen(), rows = decodeComposite(value, context, 3);
  assert.deepEqual(rows.map(r => r.id), ['9007199254740993', '9007199254740994']); assert.equal(compareComposite(...rows), -1);
  for (const change of [v => v.identity.installationId = '2', v => v.value.error = { code: 4 }, v => v.readAt = 'invalid',
    v => v.value.rows = {}, v => v.value.rows[0].fields.pop(), v => v.value.rows[0].fields[1].key = 'id',
    v => v.hasMore = true, v => v.nextCursor = 'unexpected']) {
    const copy = structuredClone(value); change(copy); assert.throws(() => decodeComposite(copy, context, 3));
  }
});
