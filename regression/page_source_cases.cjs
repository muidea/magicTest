// Exercise the exact frozen page provider before/after author and source changes.
const { isDeepStrictEqual: same } = require('node:util');
const page = require('./page_runtime_cases.cjs');
const business = require('./business_cases.cjs');
const delivery = require('./model_delivery.cjs');
const { authorFixture: author } = require('./page_author_cases.cjs');
function configure(content, entity) {
  const list = content.dataSources.find(s => s.key === 'records');
  content.dataSources.push({ ...structuredClone(list), key: 'choices', mode: 'options' });
  content.dataSources.push({ key: 'detail', entity, mode: 'detail', fields: ['id', 'name'],
    authorization: list.authorization, instanceScope: list.instanceScope, record: { idField: 'id', parameter: 'id' } });
  content.navigation.push('detail');
  content.pages.push({ key: 'detail', title: '冻结详情', routes: ['/detail/:id'], navigation: true, routeParameters: ['id'],
    layout: { type: 'responsive-grid', columns: 12, gap: 0 },
    components: [{ key: 'record-detail', type: 'entity-summary', layout: { span: 12, order: 0 }, dataSources: ['detail'],
      properties: { entity, fields: ['id', 'name'] } }] });
}
function sourceRows(value, context, sourceKey) {
  if (!['records', 'choices', 'detail'].includes(sourceKey)) throw Error('Exact declared source required');
  if (sourceKey === 'detail' && (value?.hasMore || value?.nextCursor)) throw Error('Frozen detail cannot carry pagination');
  return page.decodePage(value, context, sourceKey === 'detail' ? 1 : 10, sourceKey);
}
async function metadata(h, f, index, actor) {
  const context = await business.runtime(h, f, index, actor);
  const value = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
  h.check('Current ordinary runtime returns exact frozen pages and original installation identity', same(value.pages, f.revision.content.pages) &&
    same(value.readIdentity, context.identity) && /^sha256:[a-f0-9]{64}$/.test(value.installation?.pageDigest));
  context.pageDigest = value.installation.pageDigest; return context;
}
async function sources(h, actor, context, row) {
  for (const key of ['records', 'choices', 'detail']) {
    const body = { sourceKey: key, ...(key === 'detail' ? { recordId: row.recordId } : { pageSize: 10 }) };
    const result = await page.sourceRead(h, actor, context, body);
    h.check('Actual exact frozen ' + key + ' read succeeds with no private caching', h.good(result) && result.cacheControl?.includes('no-store'), result);
    h.check('Frozen ' + key + ' projection contains only the original owner primary key and displayed name',
      same(sourceRows(result.data.value, context, key), [{ id: row.recordId, name: row.created.name }]), result.data.value);
    h.check('Independent complete original business owner row agrees with frozen source projection', same((await business.record(h, actor, row)).data.value, row.created));
  }
}
async function render(h, actor, f, context, row, key, width, phase) {
  const browser = actor.page; await browser.setViewportSize({ width, height: 900 });
  const response = browser.waitForResponse(r => {
    const url = new URL(r.url()), request = r.request();
    return request.method() === 'POST' && url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/apps/page/sources/' &&
      url.searchParams.get('application') === f.application.name && url.searchParams.get('deploymentId') === context.identity.deploymentId && request.postDataJSON()?.sourceKey === (key === 'home' ? 'records' : 'detail');
  }); response.catch(() => {});
  const target = new URL('/workbench/apps/' + encodeURIComponent(f.application.name), actor.origin);
  for (const [name, value] of Object.entries({ source: 'portal', deploymentId: context.identity.deploymentId, pageKey: key, ...(key === 'detail' ? { recordId: row.recordId } : {}) })) target.searchParams.set(name, value);
  await browser.goto(target.href, { waitUntil: 'networkidle' });
  const actual = await response, value = await actual.json();
  h.check('Actual installed ' + key + ' renderer receives the exact frozen original source', actual.status() === 200 && !value.error &&
    same(sourceRows(value.value, context, key === 'home' ? 'records' : 'detail'), [{ id: row.recordId, name: row.created.name }]), value);
  await browser.getByText(row.created.name, { exact: true }).waitFor();
  if (key === 'home') await browser.locator('tbody tr[data-row-key="' + row.recordId + '"]').waitFor();
  const size = await browser.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
  h.check('Actual frozen ' + key + ' entry keeps its document within the viewport', size.scroll <= size.viewport + 1, { width, ...size });
  await h.screenshot(actor, 'frozen-source-' + key + '-' + width + '-' + phase);
}
async function frozenSources(h) {
  const f = await page.explicitFixture(h, configure, undefined, { suffix: 'pagesources', requestPrefix: 'page-source-' });
  const actor = await business.member(h, 'manager'), contexts = [], rows = [];
  let primary;
  try {
    for (let index = 0; index < 2; index++) {
      const context = await metadata(h, f, index, actor); contexts.push(context);
      const row = await business.create(h, context, 'frozen-source-' + index); rows.push(row);
      await sources(h, actor, context, row);
    }
    for (const width of [1440, 1024, 390]) for (const key of ['home', 'detail']) await render(h, actor, f, contexts[0], rows[0], key, width, 'before-source-removal');
    const draft = await author.read(h, f.application, 'pages'), changed = structuredClone(draft.content);
    changed.pages[0].components[0].properties.text = 'Unpublished author change ' + h.state.prefix;
    await author.save(h, f.application, 'pages', draft, changed);
    for (let index = 0; index < 2; index++) {
      h.check('Unpublished author page edit preserves original installed frozen metadata/digest', same(await metadata(h, f, index, actor), contexts[index]));
      await sources(h, actor, contexts[index], rows[index]);
    }
    const before = [];
    for (const request of f.pageRequests) before.push({ installation: (await h.ok(h.admin, 'GET', '/panel/application/installations/' + request.installation.id)).value,
      operation: (await h.ok(h.admin, 'GET', '/panel/operations/namespaces/panel/application-deployment-operations/' + request.operation.id)).value });
    await delivery.removePackage(h, f);
    for (let index = 0; index < 2; index++) {
      const request = f.pageRequests[index];
      h.check('Formal source package removal preserves entire original installed resource and durable operation',
        same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + request.installation.id)).value, before[index].installation) &&
        same((await h.ok(h.admin, 'GET', '/panel/operations/namespaces/panel/application-deployment-operations/' + request.operation.id)).value, before[index].operation));
      h.check('Package cleanup preserves complete original installed page metadata and fence', same(await metadata(h, f, index, actor), contexts[index]));
      await sources(h, actor, contexts[index], rows[index]);
    }
    await render(h, actor, f, contexts[0], rows[0], 'home', 1440, 'after-source-removal');
    await render(h, actor, f, contexts[0], rows[0], 'detail', 1440, 'after-source-removal');
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const ids = new Set(f.installations.map(v => String(v.id)));
    const open = h.state.resources.filter(v => v.kind === 'business-record' && ids.has(v.identity?.installationId) && v.phase !== 'deleted');
    if (open.length) {
      h.observe({ kind: 'original-frozen-source-business-cleanup-open', count: open.length });
      if (!primary) throw new h.Blocked('Original page source row disposition unresolved; retain installation');
    } else await page.disposeExplicitFixture(h, f, primary);
  }
  await h.partial('Exact frozen list/detail/options and ordinary independent owner rows, dual installation identities, three-width real list/detail entry, unpublished author isolation and source package removal survival verified. Separate entity fallback and UI option-selection consumer remain unverified.');
}
frozenSources.transport = 'owner-api';
module.exports = { handlers: { 'F069-001': frozenSources }, configure, sourceRows };
