const test = require('node:test');
const assert = require('node:assert/strict');
const { sourceRows, configure } = require('./page_source_cases.cjs');
test('frozen source projections bind the declared source without rewriting identity or accepting detail pagination', () => {
  const context = { identity: { installationId: '7', deploymentId: 'original' }, pageDigest: 'sha256:original' };
  const value = { identity: structuredClone(context.identity), sourceKey: 'choices', pageDigest: context.pageDigest,
    readAt: '2026-11-09T10:00:00.000Z', value: { apiVersion: 'magic.base-value-read/v1', rows: [{ fields: [
      { key: 'id', value: { kind: 'integer', number: '9223372036854775807' } }, { key: 'name', value: { kind: 'string', text: 'original' } },
    ] }] } };
  assert.deepEqual(sourceRows(value, context, 'choices'), [{ id: '9223372036854775807', name: 'original' }]);
  for (const mutate of [v => v.sourceKey = 'records', v => v.identity.installationId = '8', v => v.pageDigest = 'foreign',
    v => v.value.rows[0].fields[0].value.number = '9223372036854775808', v => v.value.rows[0].fields.push({ key: 'undeclared' })]) {
    const changed = structuredClone(value); mutate(changed); assert.throws(() => sourceRows(changed, context, 'choices'));
  }
  const detail = { ...structuredClone(value), sourceKey: 'detail' };
  assert.deepEqual(sourceRows(detail, context, 'detail'), sourceRows(value, context, 'choices'));
  for (const extra of [{ hasMore: true }, { nextCursor: 'foreign' }]) assert.throws(() => sourceRows({ ...detail, ...extra }, context, 'detail'), /pagination/);
  assert.throws(() => sourceRows(value, context, 'unknown'), /declared source/);
});
test('detail wire omits cursor pagination and exact record identity while list/options retain independent cursor declarations', () => {
  const records = { key: 'records', entity: '/sample/record', mode: 'list', fields: ['id', 'name'],
    authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation',
    pagination: { mode: 'cursor', defaultPageSize: 10, maxPageSize: 100 } };
  const c = { dataSources: [structuredClone(records)], pages: [], navigation: ['home'] };
  configure(c, records.entity);
  assert.deepEqual(c.dataSources[0], records);
  assert.equal(c.dataSources[1].mode, 'options'); assert.notEqual(c.dataSources[1].pagination, c.dataSources[0].pagination);
  assert.equal(Object.hasOwn(c.dataSources[2], 'pagination'), false); assert.deepEqual(c.dataSources[2].record, { idField: 'id', parameter: 'id' });
  assert.deepEqual(c.pages[0].routeParameters, ['id']);
  assert.deepEqual(c.pages[0].routes, ['/detail/:id']);
  assert.deepEqual(c.pages[0].components[0].dataSources, ['detail']);
});
