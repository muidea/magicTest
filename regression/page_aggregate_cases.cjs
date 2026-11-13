// Frozen aggregates through Apps -> Base; exact owner records stay independent.
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const metrics = [
  { key: 'total', operation: 'count' },
  { key: 'mean', operation: 'average', field: 'sortOrder', includeValidSampleCount: true },
];
function configure(content, entity) {
  const source = { entity, fields: ['id', 'name', 'sortOrder'], authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation', pagination: null };
  content.dataSources.push({ ...source, key: 'totals', mode: 'aggregate', metrics: structuredClone(metrics) },
    { ...source, key: 'groups', mode: 'group', groupBy: ['name'], metrics: [{ key: 'total', operation: 'count' }] });
  content.pages[0].components.push({ key: 'totals', type: 'metric-group', layout: { order: 2, span: 12 },
    dataSources: ['totals'], properties: { metrics: metrics.map(m => m.key) } });
}
async function inspectUnsupported(h, authored, content) {
  const author = require('./page_author_cases.cjs').authorFixture;
  for (const operation of ['sum', 'min', 'max', 'filtered-average']) {
    const candidate = structuredClone(content), source = candidate.dataSources.find(s => s.key === 'totals');
    source.metrics.push({ key: 'unsupported', operation: operation === 'filtered-average' ? 'average' : operation, field: 'sortOrder',
      ...(operation === 'filtered-average' ? { includeValidSampleCount: true, filters: [{ field: 'name', operator: 'eq', value: '__absent_aggregate_fixture_name__' }] } : {}) });
    const checked = (await h.ok(h.admin, 'POST', '/panel/application/definitions/' + authored.app.id + '/pages/check', { expectedDefinitionVersion: authored.pages.definitionVersion, content: candidate })).value;
    h.check('Current public capability preflight declines unsupported ' + operation + ' without a save or a fabricated runtime result', checked?.ready === false && checked.issues?.some(i => i.scope === 'dataSource' && i.dataSourceKey === 'totals' && i.message === '页面渲染与授权数据能力尚未配套：统计仅支持记录计数或未分组的数值均值'), checked);
    h.check('Unsupported aggregate preflight preserves the full original conditional author draft', same(await author.read(h, authored.app, 'pages'), authored.pages));
  }
}
function numericScalar(scalar, integer = false) {
  return !!scalar && ['integer', 'decimal'].includes(scalar.kind) && (!integer || scalar.kind === 'integer') && typeof scalar.number === 'string' && scalar.number.length <= 1024 &&
    /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(scalar.number) && (scalar.kind !== 'integer' || !scalar.number.includes('.'));
}
function numberEquals(scalar, expected, integer = false) {
  if (!numericScalar(scalar, integer)) return false;
  const [whole, fraction = ''] = scalar.number.replace('-', '').split('.'), scale = 10n ** BigInt(fraction.length);
  const numerator = BigInt(whole + fraction) * (scalar.number.startsWith('-') ? -1n : 1n);
  return numerator * BigInt(expected[1]) === BigInt(expected[0]) * scale;
}
function countScalar(value) {
  return value?.kind === 'integer' && typeof value.number === 'string' && /^(0|[1-9][0-9]{0,18})$/.test(value.number) && BigInt(value.number) <= 9223372036854775807n;
}
function decodeAggregate(value, context, sourceKey, definitions, grouped) {
  if (!value || !same(value.identity, context.identity) || value.pageDigest !== context.pageDigest || value.sourceKey !== sourceKey ||
      typeof value.readAt !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value.readAt) || !Number.isFinite(Date.parse(value.readAt)) || new Date(value.readAt).toISOString() !== value.readAt ||
      value.hasMore || value.nextCursor || value.value?.apiVersion !== 'magic.base-value-read/v1' || value.value.error || value.value.rows?.length ||
      value.value.aggregate?.apiVersion !== 'magic.orm-aggregate/v1' || !Array.isArray(value.value.aggregate.rows)) throw Error('Aggregate identity, read completion, protocol or result invalid');
  const rows = value.value.aggregate.rows;
  if (!grouped && rows.length !== 1 || rows.length > 1000) throw Error('Aggregate complete result shape or group budget invalid');
  const names = new Set();
  return rows.map(row => {
    if (!Array.isArray(row.groups) || !Array.isArray(row.metrics) || row.bucketStart ||
        !same(row.groups.map(g => g.key), grouped ? ['name'] : []) ||
        !same(row.metrics.map(m => m.key), definitions.map(m => m.key))) throw Error('Aggregate group or metric projection invalid');
    let name;
    if (grouped) {
      const scalar = row.groups[0].value;
      if (scalar?.kind !== 'string' || typeof scalar.text !== 'string' || names.has(scalar.text)) throw Error('Aggregate group value invalid or repeated');
      names.add(scalar.text); name = scalar.text;
    }
    row.metrics.forEach((item, index) => {
      const def = definitions[index], v = item.value;
      if (def.operation === 'count' ? !countScalar(v) : v?.kind !== 'null' && (!numericScalar(v) || def.operation === 'average' && v.kind !== 'decimal')) throw Error('Aggregate metric scalar invalid');
      if (def.includeValidSampleCount) {
        const n = item.validSampleCount;
        if (!countScalar(n) || (n.number === '0') !== (v.kind === 'null')) throw Error('Aggregate average sample count invalid');
      } else if (item.validSampleCount != null) throw Error('Unexpected aggregate sample count');
    });
    return { name, metrics: Object.fromEntries(row.metrics.map(m => [m.key, m])) };
  });
}
async function aggregates(h) {
  const f = await pages.explicitFixture(h, configure, inspectUnsupported), manager = await business.member(h, 'manager');
  let primary; const owned = [];
  try {
    const context = await business.runtime(h, f, 0, manager);
    const metadata = (await h.ok(manager, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
    context.pageDigest = metadata.installation?.pageDigest;
    h.check('Aggregate sources use exact new immutable installation pages and digest', same(metadata.pages, f.revision.content.pages) && same(metadata.readIdentity, context.identity) && /^sha256:[a-f0-9]{64}$/.test(context.pageDigest));
    const read = async key => {
      const result = await pages.sourceRead(h, manager, context, { sourceKey: key });
      h.check('Actual frozen aggregate succeeds with private no-store semantics', h.good(result) && result.cacheControl?.includes('no-store'), result);
      return decodeAggregate(result.data.value, context, key, key === 'totals' ? metrics : [{ key: 'total', operation: 'count' }], key === 'groups');
    };
    const checkTotals = async count => {
      const m = (await read('totals'))[0].metrics;
      h.check('Exact aggregate count matches independent complete fixture size', numberEquals(m.total.value, [count, 1], true), m);
      if (!count) h.check('Empty mean stays null with zero samples rather than fabricated zero', m.mean.value.kind === 'null' && numberEquals(m.mean.validSampleCount, [0, 1], true), m);
      else h.check('Known zero-inclusive values give exact average and valid-sample denominator', numberEquals(m.mean.value, [3, 2]) && numberEquals(m.mean.validSampleCount, [4, 1], true), m);
    };
    await checkTotals(0); h.check('Empty grouped source has no fabricated group', (await read('groups')).length === 0);
    for (let index = 0; index < 4; index++) {
      const r = await business.create(h, context, index < 2 ? 'aggregate-a' : 'aggregate-b'); owned.push(r);
      await business.execute(h, manager, r, business.request(r, 'update', [{ name: 'sortOrder', value: index }]));
      const owner = await business.record(h, manager, r), expected = { ...r.created, sortOrder: index, version: 2 };
      h.check('Independent business owner confirms complete original row and acknowledged version for aggregate input', h.good(owner) && same(owner.data.value, expected), owner);
    }
    await checkTotals(4);
    const groups = await read('groups'), expectedNames = [...new Set(owned.map(r => r.created.name))].sort();
    h.check('Complete grouped counts equal both original name groups without duplicate primary keys', same(groups.map(g => g.name).sort(), expectedNames) && groups.every(g => numberEquals(g.metrics.total.value, [2, 1], true)), groups);
    const invalid = await pages.sourceRead(h, manager, context, { sourceKey: 'totals', pageSize: 1 });
    h.check('Aggregate pagination misuse reaches precise frozen-source contract refusal without a result', [200, 400].includes(invalid.status) && invalid.data?.error?.code === 4 && invalid.data.error.message === '冻结源身份或授权合同无效' && invalid.data.value == null, invalid);
    await checkTotals(4);
    await business.finishCleanup(h, [...owned].reverse()); owned.length = 0;
    await checkTotals(0); h.check('Formal row deletion removes aggregate groups at the original installation', (await read('groups')).length === 0);
  } catch (error) { primary = error; throw error; }
  finally {
    try { if (owned.length) await business.finishCleanup(h, [...owned].reverse(), primary); }
    finally { await pages.disposeExplicitFixture(h, f, primary); }
  }
  await h.partial('Frozen count/ungrouped average with valid samples, empty/null metrics, grouped counts, independent owner input reads and formal delete effects verified. Sum/min/max and filtered averages are explicitly declined by unchanged public preflight. UTC bucket windows, display precision/timezone, group/point boundaries and cancellation remain unverified.');
}
aggregates.transport = 'owner-api';
module.exports = { handlers: { 'F069-003': aggregates }, configure, decodeAggregate, numberEquals, metrics, inspectUnsupported };
