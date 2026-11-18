// Read installed frozen page sources through the original ordinary browser.
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
function decodePage(value, context, pageSize, sourceKey = 'records') {
  if (!value || !same(value.identity, context.identity) || value.sourceKey !== sourceKey || value.pageDigest !== context.pageDigest ||
      value.value?.apiVersion !== 'magic.base-value-read/v1' || value.value.error || value.value.aggregate ||
      typeof value.readAt !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value.readAt) ||
      !Number.isFinite(Date.parse(value.readAt)) || new Date(value.readAt).toISOString() !== value.readAt ||
      value.hasMore != null && typeof value.hasMore !== 'boolean' ||
      value.hasMore === true && (typeof value.nextCursor !== 'string' || !value.nextCursor || value.nextCursor.length > 48 * 1024) ||
      value.hasMore !== true && !!value.nextCursor ||
      value.value.rows != null && !Array.isArray(value.value.rows)) throw Error('Frozen page response identity, result, completion time or cursor invalid');
  const rows = value.value.rows || [];
  if (rows.length > pageSize || value.hasMore && rows.length !== pageSize) throw Error('Frozen page size or continuation is incomplete');
  return rows.map(row => {
    if (!Array.isArray(row.fields) || row.fields.length !== 2 || new Set(row.fields.map(f => f.key)).size !== 2) throw Error('Frozen row projection invalid');
    const id = row.fields.find(f => f.key === 'id')?.value, name = row.fields.find(f => f.key === 'name')?.value;
    if (id?.kind !== 'integer' || typeof id.number !== 'string' || !/^[1-9][0-9]{0,18}$/.test(id.number) || BigInt(id.number) > 9223372036854775807n || name?.kind !== 'string' || name.text !== undefined && typeof name.text !== 'string') throw Error('Frozen row primary key or scalar invalid');
    return { id: id.number, name: name.text || '' };
  });
}
async function sourceRead(h, actor, context, body) {
  const url = new URL('/api/v1/web/proxy/apps/page/sources/', actor.origin);
  url.searchParams.set('application', context.applicationKey); url.searchParams.set('deploymentId', context.instance.deploymentId);
  const result = await actor.page.evaluate(async ({ url, body, header }) => {
    if (new URL(url).origin !== location.origin) throw Error('Page source actor origin changed');
    const r = await fetch(url, { method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: { 'Content-Type': 'application/json', 'X-Magic-Expected-Installation': header }, body: JSON.stringify(body), signal: AbortSignal.timeout(20000) });
    return { status: r.status, data: await r.json(), cacheControl: r.headers.get('cache-control') };
  }, { url: url.href, body, header: Buffer.from(JSON.stringify(context.identity)).toString('base64url') });
  h.observe({ kind: 'frozen-page-source-original-read', actor: actor.identity, identity: context.identity, route: url.pathname + url.search, body, result });
  return result;
}
async function scanPages(h, actor, context, pageSize = 5, read = sourceRead) {
  const rows = [], cursors = new Set(); let cursor, first;
  for (let i = 0; i < 200; i++) {
    const result = await read(h, actor, context, { sourceKey: 'records', pageSize, ...(cursor ? { cursor } : {}) });
    h.check('Actual frozen source page succeeds without an owner error or private cache', h.good(result) && result.cacheControl?.includes('no-store'), result);
    let page;
    try { page = decodePage(result.data.value, context, pageSize); }
    catch (error) { h.check(error.message, false, result); throw error; }
    const ids = new Set(rows.map(r => r.id));
    h.check('Frozen keyset pages contain unique strictly increasing actual primary keys', page.every((r, index) => !ids.has(r.id) && (index ? BigInt(r.id) > BigInt(page[index - 1].id) : !rows.length || BigInt(r.id) > BigInt(rows.at(-1).id))) && new Set(page.map(r => r.id)).size === page.length, page);
    rows.push(...page); first ||= result.data.value;
    if (!result.data.value.hasMore) return { rows, first };
    cursor = result.data.value.nextCursor;
    h.check('Frozen source never repeats an earlier continuation cursor', !cursors.has(cursor)); cursors.add(cursor);
  }
  throw new h.Blocked('Original frozen source exceeded the finite200-page tool read budget; no claim of complete collection');
}
async function cursors(h) {
  const f = await fixture(h), manager = await business.member(h, 'manager'), viewer = await business.member(h, 'viewer');
  const context = await business.runtime(h, f, 0, manager), other = await business.runtime(h, f, 1, manager);
  const metadata = (await h.ok(manager, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
  context.pageDigest = metadata.installation?.pageDigest;
  h.check('Original installed page contract is frozen and uses the fixture exact declared primary-key cursor source', same(metadata.readIdentity, context.identity) && /^sha256:[a-f0-9]{64}$/.test(context.pageDigest) && same(metadata.pages, f.revision.content.pages) && metadata.pages.dataSources.some(s => s.key === 'records' && same(s.fields, ['id', 'name']) && same(s.orderBy, [{ field: 'id', direction: 'asc' }]) && s.pagination.defaultPageSize === 10 && s.pagination.maxPageSize === 100));
  const baseline = await scanPages(h, manager, context), rows = [];
  let primary;
  try {
    for (let i = 0; i < 12; i++) rows.push(await business.create(h, context, 'cursor-same-name'));
    const observed = await scanPages(h, manager, context), expected = [...baseline.rows, ...rows.map(r => ({ id: r.recordId, name: r.created.name }))].sort((a, b) => BigInt(a.id) < BigInt(b.id) ? -1 : 1);
    h.check('Complete frozen pages equal original baseline and all12 owned reliable records exactly once', same(observed.rows, expected) && !!observed.first.nextCursor, { observed: observed.rows, expected });
    for (const row of observed.rows) {
      const owned = await business.record(h, manager, { ...context, recordId: row.id });
      h.check('Independent exact business owner confirms every frozen page primary key and displayed value', h.good(owned) && String(owned.data.value.id) === row.id && owned.data.value.name === row.name, { row, owned });
    }
    const reject = async (actor, target, body) => {
      const r = await sourceRead(h, actor, target, body);
      h.check('Invalid original cursor request is explicitly rejected with no page rows', [200, 400, 409].includes(r.status) && [4, 19, 21].includes(r.data?.error?.code) && r.data.value == null, r);
    };
    await reject(manager, context, { sourceKey: 'records', pageSize: 5, cursor: 'invalid-original-cursor' });
    await reject(manager, context, { sourceKey: 'records', pageSize: 101 });
    await reject(manager, context, { sourceKey: 'records', pageSize: 5, cursor: 'x'.repeat(48 * 1024 + 1) });
    await reject(manager, other, { sourceKey: 'records', pageSize: 5, cursor: observed.first.nextCursor });
    await reject(viewer, context, { sourceKey: 'records', pageSize: 5, cursor: observed.first.nextCursor });
    h.check('Fresh read after all cursor refusals retains complete original dataset', same((await scanPages(h, manager, context)).rows, expected));
    const rendered = manager.page.waitForResponse(response => {
      const url = new URL(response.url());
      return response.request().method() === 'POST' && url.origin === manager.origin && url.pathname === '/api/v1/web/proxy/apps/page/sources/' && url.searchParams.get('application') === f.application.name && url.searchParams.get('deploymentId') === context.identity.deploymentId;
    }); rendered.catch(() => {});
    await manager.page.goto(manager.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?source=portal&deploymentId=' + context.identity.deploymentId, { waitUntil: 'networkidle' });
    const browserResponse = await rendered, browserPage = await browserResponse.json();
    h.check('Actual installed renderer requests and receives the same frozen source first10 rows', browserResponse.status() === 200 && !browserPage.error && same(decodePage(browserPage.value, context, 10), expected.slice(0, 10)));
    await manager.page.getByText('回归页面原始说明', { exact: true }).waitFor();
    await manager.page.locator('tbody tr[data-row-key="' + expected[0].id + '"]').waitFor();
    await h.screenshot(manager, 'installed-frozen-source-list');
  } catch (error) { primary = error; throw error; }
  finally { await business.finishCleanup(h, [...rows].reverse(), primary); }
  await compositeFilterAndSelectorCursors(h, manager);
  h.observe({
    kind: 'special-branches-deferred',
    caseId: 'F069-002',
    classification: '[C]',
    note: 'Natural wall-clock cursor expiry is tracked in the natural-time special suite [C].',
  });
}
async function compositeFilterAndSelectorCursors(h, manager) {
  let entityKey;
  const fx = await explicitFixture(h, (content, entity) => {
    entityKey = entity;
    content.dataSources.push(
      {
        key: 'filteredSorted', entity, mode: 'list', fields: ['id', 'code', 'name', 'sortOrder'],
        authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation',
        pagination: { mode: 'cursor', defaultPageSize: 2, maxPageSize: 10 },
        orderBy: [{ field: 'sortOrder', direction: 'asc' }, { field: 'id', direction: 'asc' }],
        filters: [{ parameter: 'code', field: 'code', operator: 'eq', kind: 'string', required: false, maxValues: 16 }],
      },
      {
        key: 'nameChoices', entity, mode: 'options', fields: ['id', 'name'],
        authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation',
        pagination: { mode: 'cursor', defaultPageSize: 2, maxPageSize: 10 },
        orderBy: [{ field: 'id', direction: 'asc' }],
      },
    );
  }, undefined, { suffix: 'pagecomp', requestPrefix: 'pagecomp-' });
  const ctx = await business.runtime(h, fx, 0, manager), rows = [];
  ctx.pageDigest = (await h.ok(manager, 'GET', '/apps/application/runtimes/' + fx.application.name + '?deploymentId=' + ctx.identity.deploymentId)).value.installation?.pageDigest;
  let primary;
  try {
    for (const sortOrder of [10, 5, 10, 20]) {
      const r = { kind: 'business-record', actorRole: 'manager', phase: 'intent', ...ctx, scenarioDefinitionId: fx.application.id,
        origin: manager.origin, actorIdentity: structuredClone(manager.identity), commands: [] };
      delete r.ui; rows.push(r); h.state.resources.push(r); h.persist();
      const body = business.request(r, 'create', [
        { name: 'code', value: 'RG-' + require('node:crypto').randomBytes(8).toString('hex').toUpperCase() },
        { name: 'name', value: '复合分页样本-' + sortOrder }, { name: 'description', value: null }, { name: 'sortOrder', value: sortOrder },
      ]);
      await business.execute(h, manager, r, body);
      r.created = (await business.record(h, manager, r)).data.value; h.persist();
    }
    const collected = [], seenCursors = new Set(); let cursor;
    for (let i = 0; i < 10; i++) {
      const res = await sourceRead(h, manager, ctx, { sourceKey: 'filteredSorted', pageSize: 2, ...(cursor ? { cursor } : {}) });
      h.check('Composite sort page succeeds', h.good(res), res);
      const val = res.data.value;
      for (const row of val.value?.rows || []) {
        collected.push({
          id: row.fields.find(x => x.key === 'id')?.value?.number,
          code: row.fields.find(x => x.key === 'code')?.value?.text,
          sortOrder: Number(row.fields.find(x => x.key === 'sortOrder')?.value?.number),
        });
      }
      if (!val.hasMore) break;
      h.check('Composite cursor is fresh', val.nextCursor && !seenCursors.has(val.nextCursor));
      seenCursors.add(val.nextCursor); cursor = val.nextCursor;
    }
    const expectedIds = [...rows].sort((a, b) => (a.created.sortOrder - b.created.sortOrder) || (BigInt(a.recordId) < BigInt(b.recordId) ? -1 : 1)).map(r => r.recordId);
    h.check('Composite sort tie-breaks cleanly across cursor pages by (sortOrder ASC, id ASC)', same(collected.map(v => v.id), expectedIds), { collected, expectedIds });
    const targetRow = rows[2].created;
    const filtered = await sourceRead(h, manager, ctx, { sourceKey: 'filteredSorted', pageSize: 10, parameters: [{ name: 'code', value: { kind: 'string', text: targetRow.code } }] });
    const fRows = filtered.data.value?.value?.rows || [];
    h.check('Shared eq filter returns exact matching business row only', h.good(filtered) && fRows.length === 1 && fRows[0].fields.find(x => x.key === 'id')?.value?.number === String(targetRow.id), filtered);
    const badFilter = await sourceRead(h, manager, ctx, { sourceKey: 'filteredSorted', pageSize: 10, parameters: [{ name: 'name', value: { kind: 'string', text: 'nope' } }] });
    h.check('Undeclared filter field is explicitly rejected', [200, 400, 409].includes(badFilter.status) && badFilter.data?.error?.code > 0 && badFilter.data.value == null, badFilter);
    const optionsIds = []; cursor = undefined;
    for (let i = 0; i < 10; i++) {
      const opt = await sourceRead(h, manager, ctx, { sourceKey: 'nameChoices', pageSize: 2, ...(cursor ? { cursor } : {}) });
      h.check('Options selector page succeeds', h.good(opt), opt);
      const val = opt.data.value;
      for (const row of val.value?.rows || []) optionsIds.push(row.fields.find(x => x.key === 'id')?.value?.number);
      if (!val.hasMore) break;
      cursor = val.nextCursor;
    }
    h.check('Options selector cursor scan returns all rows in monotonic primary-key order',
      same(optionsIds, rows.map(r => r.recordId).sort((a, b) => BigInt(a) < BigInt(b) ? -1 : 1)), optionsIds);
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    if (!rows.some(r => r.phase !== 'deleted')) await disposeExplicitFixture(h, fx, primary);
  }
}
cursors.transport = 'owner-api';
function explicitView(entity, ui) {
  const primary = entity.fields.filter(f => f.spec?.primaryKey);
  if (primary.length !== 1 || primary[0].name !== ui.entity?.primaryKey || primary[0].spec.valueDeclare !== 'snowflake' ||
      !same(entity.fields.map(f => f.name).sort(), ui.fields.map(f => f.name).sort())) throw Error('Explicit fixture view requires the exact authored snowflake model and complete runtime field set');
  const view = Object.fromEntries(['capabilities', 'fields'].map(k => [k, structuredClone(ui[k])]));
  // The author page catalog marks owner-allocated keys read-only. Runtime
  // fallback presentation is not the source of the new model's constraints.
  view.fields.find(f => f.name === primary[0].name).readonly = true;
  view.entity = { name: entity.name, showName: entity.showName, pkgPath: entity.pkgPath, primaryKey: primary[0].name };
  return view;
}
function frozenPages(content, app) {
  return { ...structuredClone(content), applicationKey: app.name, applicationUuid: app.uuid, modelRevision: 1 };
}
async function explicitFixture(h, configurePages, inspectAuthor, options = {}) {
  const source = await fixture(h), manager = await business.member(h, 'manager');
  const original = await business.runtime(h, source, 0, manager);
  const { authorFixture: author } = require('./page_author_cases.cjs'), delivery = require('./model_delivery.cjs'), review = require('./deployment_review_cases.cjs'), authority = require('./application_authority_cases.cjs');
  const authored = await author.fixture(h, options.suffix || (configurePages ? 'pageaggregate' : 'pageexplicit'));
  if (options.prepareAuthor) await options.prepareAuthor(h, authored);
  const entity = authored.model.entities[0], key = entity.pkgPath + '/' + entity.name;
  const content = structuredClone(authored.pages.content);
  content.entityViews = options.buildEntityViews ? options.buildEntityViews(authored, original.ui) : { [key]: explicitView(entity, original.ui) };
  if (configurePages) configurePages(content, key);
  if (inspectAuthor) await inspectAuthor(h, authored, content);
  const checked = (await h.ok(h.admin, 'POST', '/panel/application/definitions/' + authored.app.id + '/pages/check', { expectedDefinitionVersion: authored.pages.definitionVersion, content })).value;
  h.check('Explicit new page reaches ready public preflight without changing its complete original draft', checked?.ready === true && same(await author.read(h, authored.app, 'pages'), authored.pages), checked);
  await author.save(h, authored.app, 'pages', authored.pages, content);
  const f = await delivery.publish(h, authored.app);
  if (options.prepareDelivery) await options.prepareDelivery(h, f);
  f.installations = []; f.pageRequests = []; f.pageGrants = [];
  h.check('Independent new revision freezes explicit view and publication identity without changing original accepted-empty-view fixture', same(f.revision.content.pages, frozenPages(content, authored.app)) && source.revision.content.pages.entityViews && Object.keys(source.revision.content.pages.entityViews).length === 0);
  h.admin.id = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account.id;
  for (let index = 0; index < 2; index++) {
    const r = await review.create(h, f, (options.requestPrefix || (configurePages ? 'page-aggregate-' : 'page-explicit-')) + index); delivery.linkRequest(h, f, r); f.pageRequests.push(r);
    await review.approve(h, r, [h.admin]); f.installations.push(r.installation);
  }
  const accountId = (await h.ok(manager, 'GET', '/api/v1/web/session/')).value.account.id;
  for (const installation of f.installations) {
    const r = { kind: 'member-access-retirement', phase: 'created', accountId, installation, commands: [], active: false, origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity) };
    h.state.resources.push(r); f.pageGrants.push(r); h.persist();
    await authority.accessCommand(h, r, 'manager', 0);
  }
  return f;
}
async function disposeExplicitFixture(h, f, primary) {
  try {
    for (const r of [...f.pageGrants, ...f.pageRequests, f.resource]) require('./scenario_commands.cjs').guard(h, r);
    for (const grant of [...f.pageGrants].reverse().filter(r => r.phase !== 'deleted')) await require('./application_authority_cases.cjs').retireAccess(h, grant);
    for (const request of [...f.pageRequests].reverse().filter(r => r.phase !== 'deleted')) await require('./deployment_review_cases.cjs').cleanup(h, request);
    await require('./model_delivery.cjs').retained(h, f.resource);
  } catch (error) { h.observe({ kind: 'explicit-page-original-cleanup-open', message: error.message }); if (!primary) throw error; }
}
function configureReadAuthority(content, entity) {
  content.dataSources.push(
    {
      key: 'totals',
      mode: 'aggregate',
      entity,
      fields: ['id', 'sortOrder'],
      authorization: 'validated-tenant-and-instance-and-entity-permissions',
      instanceScope: 'current-installation',
      pagination: null,
      metrics: [
        { key: 'total', operation: 'count' },
        { key: 'avgSort', operation: 'average', field: 'sortOrder', includeValidSampleCount: true },
      ],
    },
    {
      key: 'choices',
      mode: 'options',
      entity,
      fields: ['id', 'name'],
      authorization: 'validated-tenant-and-instance-and-entity-permissions',
      instanceScope: 'current-installation',
      pagination: { mode: 'cursor', defaultPageSize: 5, maxPageSize: 10 },
      orderBy: [{ field: 'id', direction: 'asc' }],
    },
  );
  content.pages[0].components.push(
    { key: 'authority-totals', type: 'metric-group', layout: { order: 2, span: 12 }, dataSources: ['totals'], properties: { metrics: ['total', 'avgSort'] } },
    { key: 'authority-choices', type: 'entity-table', layout: { order: 3, span: 12 }, dataSources: ['choices'], properties: { entity, columns: ['id', 'name'], readonly: true } },
  );
}
async function readAuthority(h) {
  const f = await explicitFixture(h, configureReadAuthority, undefined, { suffix: 'pagereadauth', requestPrefix: 'page-read-auth-' }), manager = await business.member(h, 'manager');
  const context = await business.runtime(h, f, 0, manager), peer = await business.runtime(h, f, 1, manager);
  const metadata = (await h.ok(manager, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
  context.pageDigest = metadata.installation?.pageDigest;
  h.check('Page read authority uses exact frozen installation source and digest', same(metadata.readIdentity, context.identity) && /^sha256:[a-f0-9]{64}$/.test(context.pageDigest) &&
    metadata.pages.dataSources.some(s => s.key === 'records' && same(s.fields, ['id', 'name']) && same(s.orderBy, [{ field: 'id', direction: 'asc' }])) &&
    metadata.pages.dataSources.some(s => s.key === 'totals' && s.mode === 'aggregate') &&
    metadata.pages.dataSources.some(s => s.key === 'choices' && s.mode === 'options'));
  const authority = require('./application_authority_cases.cjs');
  const ordinary = (await h.directory(h.admin, '/cas/namespaces/panel/role-templates/')).find(t => t.key === 'portal-basic-user' && t.systemManaged && t.status === 2 && t.subjectType === 'account');
  h.check('Page source test starts from ordinary functional roles only', ordinary?.roleRefs?.length > 0);
  const access = [{ applicationUuid: context.identity.deploymentId, accessLevel: 'viewer' }];
  const group = await h.create('/cas/namespaces/panel/role-templates/', { key: h.state.prefix + '-page-source-reader', name: '冻结页面读取范围', subjectType: 'account', status: 2, roleRefs: ordinary.roleRefs, applicationAccess: access }, 'role-template');
  const member = await authority.account(h, 'page-source-reader'), actor = member.actor;
  let row, primary;
  try {
    row = await business.create(h, context, 'page-read-authority');
    const read = () => sourceRead(h, actor, context, { sourceKey: 'records', pageSize: 5 });
    const readTotals = () => sourceRead(h, actor, context, { sourceKey: 'totals' });
    const readChoices = () => sourceRead(h, actor, context, { sourceKey: 'choices', pageSize: 5 });
    h.denied(await read(), 'Ordinary unassigned account cannot read frozen page list source');
    h.denied(await readTotals(), 'Ordinary unassigned account cannot read frozen aggregate source');
    h.denied(await readChoices(), 'Ordinary unassigned account cannot read frozen options source');
    await authority.assign(h, member, group, access);
    const observed = await scanPages(h, actor, context);
    h.check('Exact viewer scope exposes the actual owned primary key and display value', observed.rows.some(v => v.id === row.recordId && v.name === row.created.name));
    for (const value of observed.rows) {
      const owner = await business.record(h, manager, { ...context, recordId: value.id });
      h.check('Independent original business owner confirms each authorized frozen source row', h.good(owner) && String(owner.data.value.id) === value.id && owner.data.value.name === value.name);
    }
    const totalsRes = await readTotals();
    const aggMetrics = totalsRes.data?.value?.value?.aggregate?.rows?.[0]?.metrics || [];
    h.check('Exact viewer scope reads aggregate source metrics matching owned count and sample count',
      h.good(totalsRes) && totalsRes.data.value.sourceKey === 'totals' &&
      aggMetrics.some(m => m.key === 'total' && m.value?.number === '1') &&
      aggMetrics.some(m => m.key === 'avgSort' && m.validSampleCount?.number === '1'), totalsRes);
    const choicesRes = await readChoices();
    const choiceRows = choicesRes.status === 200 && h.good(choicesRes) ? decodePage(choicesRes.data.value, context, 5, 'choices') : [];
    h.check('Exact viewer scope reads options source rows matching owned record key and name',
      h.good(choicesRes) && choiceRows.some(v => v.id === row.recordId && v.name === row.created.name), choicesRes);
    h.denied(await sourceRead(h, actor, peer, { sourceKey: 'records', pageSize: 5 }), 'Viewer scope on installationA does not expose installationB page source');
    h.denied(await sourceRead(h, actor, peer, { sourceKey: 'totals' }), 'Viewer scope on installationA does not expose installationB aggregate source');
    h.denied(await sourceRead(h, actor, peer, { sourceKey: 'choices', pageSize: 5 }), 'Viewer scope on installationA does not expose installationB options source');
    for (const identity of [{ ...context.identity, artifactDigest: 'sha256:' + '0'.repeat(64) }, { ...context.identity, generation: context.identity.generation + 1 }, { ...context.identity, executionEpoch: context.identity.executionEpoch + 1 }, peer.identity]) {
      const response = await sourceRead(h, actor, { ...context, identity }, { sourceKey: 'records', pageSize: 5 });
      h.check('Wrong frozen identity or generation is explicitly refused without page data', [200, 400, 409].includes(response.status) && [4, 19, 21].includes(response.data?.error?.code) && response.data.value == null, response);
    }
    await authority.assign(h, member, group, []);
    h.denied(await read(), 'Formal current scope removal rejects new frozen source reads using the original session');
    h.denied(await readTotals(), 'Formal current scope removal rejects new frozen aggregate reads using the original session');
    h.denied(await readChoices(), 'Formal current scope removal rejects new frozen options reads using the original session');
    h.check('All source refusals preserve the complete original business record', same((await business.record(h, manager, row)).data.value, row.created));
    const currentPeer = await business.runtime(h, f, 1, manager);
    h.check('Source scope changes preserve the independent peer installation fence', same(currentPeer.identity, peer.identity));
  } catch (error) { primary = error; throw error; }
  finally {
    try { if (row) await business.finishCleanup(h, [row], primary); }
    finally { await disposeExplicitFixture(h, f, primary); }
  }
  h.observe({
    kind: 'v1-contract-boundary-aligned',
    caseId: 'F069-004',
    excluded: 'Endpoint page-source access excluded by initial contract [B]; relation labels and fault windows tracked in special suite [C].',
  });
}
readAuthority.transport = 'owner-api';
module.exports = { handlers: { 'F069-002': cursors, 'F069-004': readAuthority }, decodePage, sourceRead, scanPages, explicitView, explicitFixture, disposeExplicitFixture, frozenPages };
