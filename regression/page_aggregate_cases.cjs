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
  await verifyTimeBucket(h);
  h.observe({
    kind: 'v1-contract-boundary-aligned',
    caseId: 'F069-003',
    excluded: 'Sum/min/max and filtered averages declined by initial preflight [B]; >1000-row SQL saturation tracked in special suite [C].',
  });
}
function configureWithBuckets(content, entity) {
  configure(content, entity);
  content.timezone = 'Asia/Shanghai';
  content.navigation.push('static');
  content.pages.push({
    key: 'static',
    title: '静态离开目标',
    routes: ['/static'],
    navigation: true,
    routeParameters: [],
    layout: { type: 'responsive-grid', columns: 12, gap: 0 },
    components: [{ key: 'static-text', type: 'text', layout: { span: 12, order: 0 }, dataSources: [], properties: { text: '已离开统计页' } }],
  });
  content.dataSources.push({
    key: 'buckets',
    mode: 'time-bucket',
    entity,
    fields: ['occurredAt', 'sortOrder'],
    authorization: 'validated-tenant-and-instance-and-entity-permissions',
    instanceScope: 'current-installation',
    pagination: null,
    timeWindow: { field: 'occurredAt', defaultHours: 24, maxHours: 24, bounds: '[from,to)', timezone: 'UTC' },
    bucket: { field: 'occurredAt', interval: 'hour', maxBuckets: 24, maxPoints: 24 },
    metrics: [{ key: 'sortOrder', operation: 'average', field: 'sortOrder', includeValidSampleCount: true }],
  });
  content.pages[0].components.push({
    key: 'hourly-trend',
    type: 'time-series-chart',
    layout: { span: 12, order: 4 },
    dataSources: ['buckets'],
    properties: { timeField: 'occurredAt', metrics: [{ field: 'sortOrder' }], bucket: 'hour', aggregation: 'average', connectNulls: false },
  });
}
async function verifyBucketBoundaries(h, authored, content) {
  for (const mutate of [
    c => { c.timezone = 'Invalid/Zone'; },
    c => { c.dataSources.find(s => s.key === 'buckets').bucket.maxBuckets = 23; },
    c => { c.dataSources.find(s => s.key === 'buckets').bucket.maxPoints = 23; },
    c => { c.dataSources.find(s => s.key === 'groups').groupBy = []; },
  ]) {
    const candidate = structuredClone(content);
    mutate(candidate);
    const response = await h.api(h.admin, 'POST', '/panel/application/definitions/' + authored.app.id + '/pages/check', { expectedDefinitionVersion: authored.pages.definitionVersion, content: candidate });
    const checked = response.data?.value;
    const refused = response.status === 400 && response.data?.error != null || response.status === 200 && checked?.ready === false && Array.isArray(checked.issues) && checked.issues.length > 0;
    h.check('Authoring preflight declines invalid timezone, bucket/point budget or empty grouping before save', refused, response);
  }
}
async function verifyTimeBucket(h) {
  const { field, inputViews } = require('./model_input_cases.cjs');
  const { authoring } = require('./authoring_cases.cjs');
  const prepareBucket = async (h2, authored) => {
    const current = await authoring.draft(h2, authored.app);
    const entity = structuredClone(current.entities[0]);
    entity.fields.push(field('occurredAt', 'datetime', true));
    authored.model = await authoring.save(h2, authored.app, current, [entity]);
    authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h2, authored.app, 'pages');
  };
  const f = await pages.explicitFixture(h, configureWithBuckets, verifyBucketBoundaries, {
    suffix: 'aggbuckets',
    requestPrefix: 'agg-buckets-',
    prepareAuthor: prepareBucket,
    buildEntityViews: inputViews,
  });
  const manager = await business.member(h, 'manager');
  const context = { ...(await business.runtime(h, f, 0, manager)), pageDigest: f.installations[0].receipt.pageDigest };
  const rows = [];
  let primary;
  try {
    const from = '2026-10-14T00:00:00.000Z';
    const to = '2026-10-14T03:00:00.000Z';
    const base = await pages.sourceRead(h, manager, context, { sourceKey: 'buckets', from, to });
    h.check('Empty UTC [from,to) hourly bucket query returns three null-metric buckets with zero valid samples',
      h.good(base) && base.data.value?.value?.aggregate?.rows?.length === 3 &&
      base.data.value.value.aggregate.rows.every((row, idx) =>
        Date.parse(row.bucketStart) === Date.parse('2026-10-14T0' + idx + ':00:00Z') &&
        row.metrics?.[0]?.key === 'sortOrder' && row.metrics[0].value?.kind === 'null' && row.metrics[0].validSampleCount?.number === '0'), base);

    const samples = [
      ['b0-a', 10, '2026-10-14T00:15:00Z'],
      ['b0-b', 20, '2026-10-14T00:45:00Z'],
      ['b2-a', 30, '2026-10-14T02:10:00Z'],
      ['outside-to', 999, '2026-10-14T03:00:00Z'],
    ];
    for (const [label, sortOrder, occurredAt] of samples) {
      const r = await business.create(h, context, label);
      rows.push(r);
      await business.execute(h, manager, r, business.request(r, 'update', [
        { name: 'sortOrder', value: sortOrder },
        { name: 'occurredAt', value: occurredAt },
      ]));
      r.created = (await business.record(h, manager, r)).data.value;
    }

    const populated = await pages.sourceRead(h, manager, context, { sourceKey: 'buckets', from, to });
    const bRows = populated.data?.value?.value?.aggregate?.rows || [];
    h.check('Populated UTC hourly buckets aggregate per-hour means with valid samples, leave empty hours null, and exclude right-open [from,to) boundary',
      h.good(populated) && bRows.length === 3 &&
      numberEquals(bRows[0].metrics[0].value, [15n, 1n]) && bRows[0].metrics[0].validSampleCount?.number === '2' &&
      bRows[1].metrics[0].value?.kind === 'null' && bRows[1].metrics[0].validSampleCount?.number === '0' &&
      numberEquals(bRows[2].metrics[0].value, [30n, 1n]) && bRows[2].metrics[0].validSampleCount?.number === '1', bRows);

    for (const badWindow of [
      { sourceKey: 'buckets', from: to, to: from },
      { sourceKey: 'buckets', from: '2026-10-14T00:00:00.000001Z', to },
      { sourceKey: 'buckets', from: '2026-10-14T00:00:00.000Z', to: '2026-10-15T01:00:00.000Z' },
    ]) {
      const rejected = await pages.sourceRead(h, manager, context, badWindow);
      h.check('Invalid time-bucket range, sub-millisecond precision or budget overrun is refused before execution', !h.good(rejected) && rejected.data?.error != null, { badWindow, rejected });
    }

    const browser = manager.page;
    const appUrl = new URL('/workbench/apps/' + encodeURIComponent(f.application.name), manager.origin);
    appUrl.searchParams.set('source', 'portal');
    appUrl.searchParams.set('deploymentId', context.identity.deploymentId);
    appUrl.searchParams.set('pageKey', 'home');
    await browser.setViewportSize({ width: 1440, height: 900 });
    await browser.goto(appUrl.href, { waitUntil: 'networkidle' });
    await browser.locator('details.application-page-time-range summary').click();
    await browser.getByLabel('趋势开始时间 UTC', { exact: true }).fill(from);
    await browser.getByLabel('趋势结束时间 UTC', { exact: true }).fill(to);
    const utcRead = browser.waitForRequest(req => {
      try {
        const u = new URL(req.url());
        return req.method() === 'POST' && u.pathname === '/api/v1/web/proxy/apps/page/sources/' && req.postDataJSON()?.sourceKey === 'buckets' && req.postDataJSON()?.from === from;
      } catch { return false; }
    }, { timeout: 20000 }); utcRead.catch(() => {});
    const utcDone = browser.waitForResponse(res => res.request().method() === 'POST' && new URL(res.url()).pathname === '/api/v1/web/proxy/apps/page/sources/' && res.request().postDataJSON()?.sourceKey === 'buckets' && res.request().postDataJSON()?.from === from, { timeout: 20000 }); utcDone.catch(() => {});
    await browser.getByRole('button', { name: '应用时间范围', exact: true }).click();
    await utcRead; await utcDone;
    await browser.locator('details.application-page-hourly-details summary').click();
    const detailsText = await browser.locator('details.application-page-hourly-details').innerText();
    h.check('Non-UTC Asia/Shanghai page timezone renders CST hourly bucket labels while sending exact UTC [from,to) bounds',
      detailsText.includes('小时起点 Asia/Shanghai') && detailsText.includes('2026-10-14 08:00:00.000 Asia/Shanghai') && detailsText.includes('2026-10-14 10:00:00.000 Asia/Shanghai'), detailsText);
    await h.screenshot(manager, 'aggregate-shanghai-timezone');

    // Verify in-flight aggregate cancellation when leaving the page.
    let heldSeen, holdRelease, holdOutcome = 'pending';
    const heldPromise = new Promise(resolve => { heldSeen = resolve; });
    const holdGate = new Promise(resolve => { holdRelease = resolve; });
    const matchBucket = '**/api/v1/web/proxy/apps/page/sources/**';
    const holdHandler = async route => {
      const req = route.request();
      if (req.method() === 'POST' && req.postDataJSON()?.sourceKey === 'buckets') {
        try {
          const response = await route.fetch({ maxRetries: 0 });
          heldSeen();
          await holdGate;
          try { await route.fulfill({ response }); holdOutcome = 'released'; }
          catch { holdOutcome = 'aborted'; }
        } catch { holdOutcome = 'fetch-error'; heldSeen(); }
        return;
      }
      await route.continue();
    };
    await browser.route(matchBucket, holdHandler);
    try {
      await browser.getByRole('button', { name: '最近完整小时', exact: true }).click();
      await heldPromise;
      await browser.locator('.application-page-navigation').getByRole('button', { name: '静态离开目标', exact: true }).click();
      await browser.getByText('已离开统计页', { exact: true }).waitFor();
      holdRelease();
      await browser.waitForTimeout(300);
      h.check('Navigating away aborts or safely discards in-flight aggregate request without rendering stale metrics',
        ['aborted', 'released'].includes(holdOutcome) && await browser.locator('details.application-page-hourly-details').count() === 0, holdOutcome);
    } finally {
      holdRelease?.();
      await browser.unroute(matchBucket, holdHandler);
    }

    await business.execute(h, manager, rows[0], business.request(rows[0], 'delete'));
    rows[0].phase = 'deleted';
    h.persist();
    const afterDelete = await pages.sourceRead(h, manager, context, { sourceKey: 'buckets', from, to });
    const dRows = afterDelete.data?.value?.value?.aggregate?.rows || [];
    h.check('Formal business delete shifts exact hourly bucket average and decrements valid sample count',
      h.good(afterDelete) && dRows.length === 3 &&
      numberEquals(dRows[0].metrics[0].value, [20n, 1n]) && dRows[0].metrics[0].validSampleCount?.number === '1', dRows);
  } catch (error) { primary = error; throw error; }
  finally {
    try { await business.finishCleanup(h, rows.reverse(), primary); }
    catch (err) { if (!primary) primary = err; }
    await pages.disposeExplicitFixture(h, f, primary);
  }
}
aggregates.transport = 'owner-api';
module.exports = { handlers: { 'F069-003': aggregates }, configure, decodeAggregate, numberEquals, metrics, inspectUnsupported };
