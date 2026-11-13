const { test } = require('node:test');
const assert = require('node:assert/strict');
const { numberEquals, decodeAggregate } = require('./page_aggregate_cases.cjs');
test('aggregate fixture uses the public component properties wire with bounded separate frozen sources', () => {
  const { configure, metrics } = require('./page_aggregate_cases.cjs');
  const content = { dataSources: [], pages: [{ components: [] }] }; configure(content, '/exact/sample');
  assert.deepEqual(content.pages[0].components[0].properties, { metrics: metrics.map(m => m.key) });
  assert.equal(content.pages[0].components[0].metricGroup, undefined);
  assert.equal(content.dataSources[0].entity, '/exact/sample');
  assert.deepEqual(content.dataSources[1].groupBy, ['name']);
  assert.equal(content.dataSources[0].metrics.length, 2);
  assert.equal(content.dataSources[0].pagination, null);
  assert.equal(content.dataSources[1].pagination, null);
});
test('aggregate comparison preserves exact integers and decimal fractions without floating point', () => {
  assert.ok(numberEquals({ kind: 'integer', number: '9007199254740993' }, ['9007199254740993', 1], true));
  assert.ok(!numberEquals({ kind: 'integer', number: '9007199254740993' }, ['9007199254740992', 1], true));
  assert.ok(numberEquals({ kind: 'decimal', number: '1.50000000000000000000' }, [3, 2]));
  assert.ok(numberEquals({ kind: 'decimal', number: '-0.1250' }, [-1, 8]));
  for (const s of [{ kind: 'integer', number: 0 }, { kind: 'integer', number: '1.5' }, { kind: 'decimal', number: 'NaN' }, { kind: 'decimal', number: '1e999999' }, { kind: 'decimal', number: '1'.repeat(1025) }]) assert.equal(numberEquals(s, [0, 1]), false);
});
test('unsupported aggregate preflight needs the exact capability issue and unchanged complete draft', async () => {
  const { configure, inspectUnsupported } = require('./page_aggregate_cases.cjs');
  for (const mode of ['exact', 'unexpected-ready', 'changed-draft', 'different-issue']) {
    const authored = { app: { id: 7 }, pages: { definitionVersion: 8, content: { original: true } } }, content = { dataSources: [], pages: [{ components: [] }] };
    configure(content, '/exact/sample'); const operations = [];
    const h = { admin: {}, check(label, valid) { assert.ok(valid, label); }, async ok(_, method, route, body) {
      if (method === 'GET') { assert.equal(route, '/panel/application/definitions/7/pages'); return { value: mode === 'changed-draft' ? { ...authored.pages, definitionVersion: 9 } : structuredClone(authored.pages) }; }
      assert.equal(method, 'POST'); assert.equal(route, '/panel/application/definitions/7/pages/check'); assert.equal(body.expectedDefinitionVersion, 8);
      const extra = body.content.dataSources.find(s => s.key === 'totals').metrics.at(-1); operations.push(extra.operation);
      return { value: { ready: mode === 'unexpected-ready', issues: [{ scope: 'dataSource', dataSourceKey: 'totals', message: mode === 'different-issue' ? 'dependency failure' : '页面渲染与授权数据能力尚未配套：统计仅支持记录计数或未分组的数值均值' }] } };
    } };
    if (mode === 'exact') { await inspectUnsupported(h, authored, content); assert.deepEqual(operations, ['sum', 'min', 'max', 'average']); }
    else await assert.rejects(inspectUnsupported(h, authored, content));
    assert.equal(content.dataSources[0].metrics.length, 2);
  }
});
test('aggregate decoder rejects foreign identity, incomplete metrics, malformed values and false sample counts', () => {
  const context = { identity: { deploymentId: 'original' }, pageDigest: 'sha256:original' };
  const definitions = [{ key: 'count', operation: 'count' }, { key: 'mean', operation: 'average', includeValidSampleCount: true }];
  const original = { ...structuredClone(context), sourceKey: 'totals', readAt: '2026-11-09T08:00:00.000Z', value: { apiVersion: 'magic.base-value-read/v1', aggregate: { apiVersion: 'magic.orm-aggregate/v1', rows: [{ groups: [], metrics: [
    { key: 'count', value: { kind: 'integer', number: '0' } },
    { key: 'mean', value: { kind: 'null' }, validSampleCount: { kind: 'integer', number: '0' } },
  ] }] } } };
  assert.equal(decodeAggregate(original, context, 'totals', definitions, false).length, 1);
  for (const change of [v => { v.identity.deploymentId = 'other'; }, v => { v.readAt = '2026-02-30T00:00:00.000Z'; }, v => { v.hasMore = true; }, v => { v.value.error = { code: 5 }; }, v => { v.value.aggregate.rows = []; }, v => { v.value.aggregate.rows[0].metrics.pop(); }, v => { v.value.aggregate.rows[0].metrics[0].value.number = '-1'; }, v => { v.value.aggregate.rows[0].metrics[0].value.number = '9223372036854775808'; }, v => { v.value.aggregate.rows[0].metrics[0].value.number = '-0'; }, v => { v.value.aggregate.rows[0].metrics[1].validSampleCount.number = '1'; }, v => { v.value.aggregate.rows[0].metrics[1].value = { kind: 'decimal', number: 'garbage' }; }, v => { const m = v.value.aggregate.rows[0].metrics[1]; m.value = { kind: 'integer', number: '0' }; m.validSampleCount.number = '1'; }]) {
    const invalid = structuredClone(original); change(invalid); assert.throws(() => decodeAggregate(invalid, context, 'totals', definitions, false));
  }
  const grouped = structuredClone(original); grouped.sourceKey = 'groups'; grouped.value.aggregate.rows[0].groups = [{ key: 'name', value: { kind: 'string', text: 'same' } }];
  grouped.value.aggregate.rows.push(structuredClone(grouped.value.aggregate.rows[0]));
  assert.throws(() => decodeAggregate(grouped, context, 'groups', definitions, true), /repeated/);
});
