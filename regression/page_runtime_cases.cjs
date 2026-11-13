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
  await h.partial('Frozen primary-key source pagination, original cursor subject/installation isolation, malformed/oversize cursor, page-size limit and real installed list verified. Shared filters, selectors, composite sort ties and natural cursor expiry require separate frozen fixtures and remain unverified.');
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
async function readAuthority(h) {
  const f = await explicitFixture(h), manager = await business.member(h, 'manager');
  const context = await business.runtime(h, f, 0, manager), peer = await business.runtime(h, f, 1, manager);
  const metadata = (await h.ok(manager, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
  context.pageDigest = metadata.installation?.pageDigest;
  h.check('Page read authority uses exact frozen installation source and digest', same(metadata.readIdentity, context.identity) && /^sha256:[a-f0-9]{64}$/.test(context.pageDigest) && metadata.pages.dataSources.some(s => s.key === 'records' && same(s.fields, ['id', 'name']) && same(s.orderBy, [{ field: 'id', direction: 'asc' }])));
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
    h.denied(await read(), 'Ordinary unassigned account cannot read frozen page source');
    await authority.assign(h, member, group, access);
    const observed = await scanPages(h, actor, context);
    h.check('Exact viewer scope exposes the actual owned primary key and display value', observed.rows.some(v => v.id === row.recordId && v.name === row.created.name));
    for (const value of observed.rows) {
      const owner = await business.record(h, manager, { ...context, recordId: value.id });
      h.check('Independent original business owner confirms each authorized frozen source row', h.good(owner) && String(owner.data.value.id) === value.id && owner.data.value.name === value.name);
    }
    h.denied(await sourceRead(h, actor, peer, { sourceKey: 'records', pageSize: 5 }), 'Viewer scope on installationA does not expose installationB page source');
    for (const identity of [{ ...context.identity, artifactDigest: 'sha256:' + '0'.repeat(64) }, { ...context.identity, generation: context.identity.generation + 1 }, { ...context.identity, executionEpoch: context.identity.executionEpoch + 1 }, peer.identity]) {
      const response = await sourceRead(h, actor, { ...context, identity }, { sourceKey: 'records', pageSize: 5 });
      h.check('Wrong frozen identity or generation is explicitly refused without page data', [200, 400, 409].includes(response.status) && [4, 19, 21].includes(response.data?.error?.code) && response.data.value == null, response);
    }
    await authority.assign(h, member, group, []);
    h.denied(await read(), 'Formal current scope removal rejects new frozen source reads using the original session');
    h.check('All source refusals preserve the complete original business record', same((await business.record(h, manager, row)).data.value, row.created));
    const currentPeer = await business.runtime(h, f, 1, manager);
    h.check('Source scope changes preserve the independent peer installation fence', same(currentPeer.identity, peer.identity));
  } catch (error) { primary = error; throw error; }
  finally {
    try { if (row) await business.finishCleanup(h, [row], primary); }
    finally { await disposeExplicitFixture(h, f, primary); }
  }
  await h.partial('Original ordinary account unassigned/read/revoked source access, independent per-key owner reads and exact installation/digest/generation fences verified. Endpoint source roles, aggregate/options/labels and server-return-before-revocation or late browser response windows remain unverified.');
}
readAuthority.transport = 'owner-api';
module.exports = { handlers: { 'F069-002': cursors, 'F069-004': readAuthority }, decodePage, sourceRead, scanPages, explicitView, explicitFixture, disposeExplicitFixture, frozenPages };
