const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const { runtimeRead } = require('./owner_transport.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const safeId = id => Number.isSafeInteger(id) && id > 0;
const compareId = (a, b) => BigInt(a.id) < BigInt(b.id) ? -1 : BigInt(a.id) > BigInt(b.id) ? 1 : 0;
function decodeCollection(result, mode, pageNum, size, total) {
  const p = result?.pagination;
  if (result?.error || !p || !Number.isSafeInteger(p.total) || p.total < 0 || p.pageSize !== size || p.pageNum !== pageNum ||
      total !== undefined && p.total !== total || (mode === 'cursor' ? p.mode !== mode : !!p.mode) ||
      p.hasMore != null && typeof p.hasMore !== 'boolean') throw Error('Exact owner collection pagination or stable total invalid');
  const rows = result.values === null && p.total === 0 ? [] : result.values;
  if (!Array.isArray(rows) || rows.length > size || rows.some(r => !r || !safeId(r.id)) || new Set(rows.map(r => r.id)).size !== rows.length ||
      p.hasMore === true && (rows.length !== size || !/^[1-9][0-9]*$/.test(p.nextCursor) || p.nextCursor !== String(rows.at(-1).id)) ||
      p.hasMore !== true && !!p.nextCursor) throw Error('Owner collection is malformed, duplicated, unsafe or has an invalid continuation');
  return { rows, pagination: p };
}
async function collection(h, actor, context, mode = 'offset', size = 5, read = runtimeRead) {
  if (!['offset', 'cursor'].includes(mode) || !Number.isSafeInteger(size) || size < 1 || size > 100) throw new h.Blocked('Explicit finite owner collection budget required');
  const actorIdentity = structuredClone(actor.identity), origin = actor.origin, installation = structuredClone(context.identity);
  const route = new URL('/apps/entity/values/', actor.origin);
  for (const [k, v] of Object.entries({ application: context.applicationKey, deploymentId: installation.deploymentId, entity: context.entity,
    _pageSize: size, _needTotal: true, _sortFilter: JSON.stringify({ fieldName: 'id', ascFlag: true }) })) route.searchParams.set(k, String(v));
  if (mode === 'cursor') route.searchParams.set('_paginationMode', 'cursor');
  const rows = [], cursors = new Set(); let after, total;
  for (let i = 1; i <= 200; i++) {
    const original = () => {
      if (!same(actor.identity, actorIdentity) || actor.origin !== origin || !same(context.identity, installation)) throw new h.Blocked('Original collection actor or installation changed; stop reading');
    };
    original(); route.searchParams.set('_pageNum', String(mode === 'cursor' ? 1 : i));
    if (after) route.searchParams.set('_after', after);
    const response = await read(actor, route.pathname + route.search, installation, h.observe); original();
    h.check('Public collection is read under the exact original installation and ordinary actor', h.good(response), response);
    const page = decodeCollection(response.data, mode, mode === 'cursor' ? 1 : i, size, total); total ??= page.pagination.total;
    if (total > size * 200 || rows.length + page.rows.length > total || page.rows.some((row, index) => index ? compareId(page.rows[index - 1], row) >= 0 : rows.length && compareId(rows.at(-1), row) >= 0)) throw new h.Blocked('Collection changed, repeated identities or exceeded its explicit finite read budget');
    rows.push(...page.rows);
    if (rows.length === total) {
      if (page.pagination.hasMore) throw new h.Blocked('Owner continuation contradicts the complete total');
      return rows;
    }
    if (page.rows.length !== size || mode === 'cursor' && !page.pagination.hasMore) throw new h.Blocked('Owner collection ended before its declared total');
    if (mode === 'cursor') {
      after = page.pagination.nextCursor;
      if (cursors.has(after)) throw new h.Blocked('Owner cursor repeated');
      cursors.add(after);
    }
  }
  throw new h.Blocked('Collection budget exhausted; no claim of complete data or absence');
}
async function completeRows(h, actor, context, expected) {
  for (const mode of ['offset', 'cursor']) {
    const rows = await collection(h, actor, context, mode);
    h.check('Complete ' + mode + ' list equals every expected full original owner row exactly once', same(rows, [...expected].sort(compareId)), { rows, expected });
    for (const row of rows) h.check('Independent exact detail agrees with every list field and actual owner primary key',
      same((await business.record(h, actor, { ...context, recordId: String(row.id) })).data.value, row));
  }
}
async function crud(h) {
  const f = await fixture(h), actor = await business.member(h, 'manager');
  const contexts = await Promise.all([business.runtime(h, f, 0, actor), business.runtime(h, f, 1, actor)]);
  const before = []; for (const context of contexts) before.push(await collection(h, actor, context));
  const records = []; let primary;
  try {
    for (let i = 0; i < 2; i++) records.push(await business.create(h, contexts[i], 'collection-peer'));
    for (let i = 0; i < 2; i++) await completeRows(h, actor, contexts[i], [...before[i], records[i].created]);
    const row = records[0], fields = [{ name: 'name', value: '列表完整更新 ' + h.state.prefix }, { name: 'description', value: '' }, { name: 'sortOrder', value: 0 }];
    await business.execute(h, actor, row, business.request(row, 'update', fields));
    const expected = { ...row.created, ...Object.fromEntries(fields.map(f => [f.name, f.value])), version: Number(row.version) };
    h.check('Sparse scalar update preserves every other original field and exactly advances its owner version', same((await business.record(h, actor, row)).data.value, expected));
    await completeRows(h, actor, contexts[0], [...before[0], expected]);
    await completeRows(h, actor, contexts[1], [...before[1], records[1].created]);
    await business.cleanup(h, row); await completeRows(h, actor, contexts[0], before[0]);
    await completeRows(h, actor, contexts[1], [...before[1], records[1].created]);
    const protectedDirect = await h.api(actor, 'POST', '/apps/entity/values/?application=' + encodeURIComponent(contexts[0].applicationKey) +
      '&deploymentId=' + contexts[0].identity.deploymentId + '&entity=' + encodeURIComponent(contexts[0].entity),
    { code: 'RG-' + crypto.randomBytes(4).toString('hex').toUpperCase(), name: 'protected-direct-deny', description: null, sortOrder: 0 });
    h.check('Protected entity continues rejecting ordinary direct POST without reliable downgrade',
      [200, 400, 409].includes(protectedDirect.status) && protectedDirect.data?.error?.code === 21 &&
      protectedDirect.data.error.message === '公开受保护写入必须使用可靠业务写入合同' && protectedDirect.data.value == null, protectedDirect);
    await completeRows(h, actor, contexts[0], before[0]);
  } catch (error) { primary = error; throw error; }
  finally { await business.finishCleanup(h, records.filter(r => r.phase !== 'deleted').reverse(), primary); }
  for (let i = 0; i < 2; i++) await completeRows(h, actor, contexts[i], before[i]);

  const modelInputs = require('./model_input_cases.cjs');
  await modelInputs.withFixture(h, 'collectionrel', 'relations', async ({ f: rf, actor: rActor, contexts: rContexts, rows }) => {
    const targetEntity = rf.revision.entities.find(e => e.name === 'zzRelationTarget');
    const targetKey = targetEntity.pkgPath + '/' + targetEntity.name;
    const t1 = await modelInputs.create(h, rf, rActor, rContexts[0], rows, [], targetKey);
    const t2 = await modelInputs.create(h, rf, rActor, rContexts[0], rows, [], targetKey);
    const peerTarget = await modelInputs.create(h, rf, rActor, rContexts[1], rows, [], targetKey);
    const refs = [{ id: t1.recordId }, { id: t2.recordId }].sort((x, y) => x.id < y.id ? -1 : x.id > y.id ? 1 : 0);
    const host = await modelInputs.create(h, rf, rActor, rContexts[0], rows, [{ name: 'target', reference: { id: t1.recordId } }, { name: 'targets', references: refs }]);
    await completeRows(h, rActor, rContexts[0], [host.created]);
    await business.execute(h, rActor, host, business.request(host, 'update', [{ name: 'target', reference: { id: t2.recordId } }]));
    const updated = (await business.record(h, rActor, host)).data.value;
    h.check('Relationship reliable update advances owner version and preserves target collection',
      String(updated.version) === host.version && same(modelInputs.ids(updated.target), [t2.recordId]) && same(modelInputs.ids(updated.targets), refs.map(v => v.id)));
    await completeRows(h, rActor, rContexts[0], [updated]);
    await business.execute(h, rActor, host, business.request(host, 'update', [{ name: 'target', value: null }]));
    const cleared = (await business.record(h, rActor, host)).data.value;
    h.check('Relationship clear removes only single reference while preserving targets and independent target rows',
      cleared.target == null && same(modelInputs.ids(cleared.targets), refs.map(v => v.id)) &&
      same((await business.record(h, rActor, t1)).data.value, t1.created) &&
      same((await business.record(h, rActor, t2)).data.value, t2.created) &&
      same((await business.record(h, rActor, peerTarget)).data.value, peerTarget.created));
    await completeRows(h, rActor, rContexts[0], [cleared]);
  });

  const pages = require('./page_runtime_cases.cjs');
  const unprotected = await pages.explicitFixture(h, null, null, {
    suffix: 'unprotectedcrud',
    requestPrefix: 'unprotected-crud-',
    prepareAuthor: async (h, authored) => {
      const current = await a.draft(h, authored.app);
      const entities = current.entities.map(e => { const copy = structuredClone(e); delete copy.writeRules; return copy; });
      authored.model = await a.save(h, authored.app, current, entities);
      authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
    },
  });
  let uPrimary;
  try {
    const uActor = await business.member(h, 'manager');
    const entity = unprotected.revision.entities[0], entityKey = entity.pkgPath + '/' + entity.name;
    const deploymentId = unprotected.installations[0].deploymentId;
    const runtime = (await h.ok(uActor, 'GET', '/apps/application/runtimes/' + encodeURIComponent(unprotected.application.name) + '?deploymentId=' + deploymentId)).value;
    const ui = runtime.entities.find(e => e.entity?.name === entity.name && e.entity?.pkgPath === entity.pkgPath);
    h.check('Separate unprotected fixture advertises no protected business-write protocol', !ui?.businessWrites, ui);
    const uContext = { applicationKey: unprotected.application.name, entity: entityKey, identity: runtime.readIdentity };
    await completeRows(h, uActor, uContext, []);
    const q = '?application=' + encodeURIComponent(uContext.applicationKey) + '&deploymentId=' + deploymentId + '&entity=' + encodeURIComponent(entityKey);
    const code = 'RG-' + crypto.randomBytes(6).toString('hex').toUpperCase();
    const inserted = await h.api(uActor, 'POST', '/apps/entity/values/' + q, { code, name: '无保护直接写入 ' + h.state.prefix, description: null, sortOrder: 0, version: 1 });
    h.check('Separate unprotected ordinary fixture supports direct owner POST create', h.good(inserted) && safeId(inserted.data.value?.id), inserted);
    const createdRow = inserted.data.value, recordId = String(createdRow.id);
    try {
      await completeRows(h, uActor, uContext, [createdRow]);
      const modified = await h.api(uActor, 'PUT', '/apps/entity/values/' + recordId + q, { id: createdRow.id, code, name: '无保护直接更新 ' + h.state.prefix, description: 'ordinary', sortOrder: 3, version: 1 });
      h.check('Separate unprotected ordinary fixture supports direct owner PUT update', h.good(modified) && modified.data.value?.name === '无保护直接更新 ' + h.state.prefix, modified);
      await completeRows(h, uActor, uContext, [modified.data.value]);
    } finally {
      const removed = await h.api(uActor, 'DELETE', '/apps/entity/values/' + recordId + q);
      h.check('Separate unprotected ordinary fixture supports direct owner DELETE', h.good(removed), removed);
    }
    await completeRows(h, uActor, uContext, []);
  } catch (error) { uPrimary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, unprotected, uPrimary); }
}
function compositeSource(content) {
  const source = content.dataSources.find(s => s.key === 'records');
  source.fields = ['id', 'name', 'sortOrder'];
  source.orderBy = [{ field: 'sortOrder', direction: 'asc' }, { field: 'id', direction: 'asc' }];
  source.filters = [{ parameter: 'bucket', field: 'sortOrder', operator: 'eq', kind: 'integer', required: false }];
  content.pages.find(p => p.key === 'home').components.find(c => c.key === 'records').properties.filters = ['sortOrder'];
}
function decodeComposite(value, context, size) {
  if (!value || !same(value.identity, context.identity) || value.pageDigest !== context.pageDigest || value.sourceKey !== 'records' ||
      value.value?.apiVersion !== 'magic.base-value-read/v1' || value.value.error || value.value.aggregate ||
      typeof value.readAt !== 'string' || !Number.isFinite(Date.parse(value.readAt)) || new Date(value.readAt).toISOString() !== value.readAt ||
      value.hasMore != null && typeof value.hasMore !== 'boolean' ||
      (value.hasMore ? typeof value.nextCursor !== 'string' || !value.nextCursor || value.nextCursor.length > 48 * 1024 : !!value.nextCursor)) throw Error('Frozen composite result identity, completion time or continuation invalid');
  const rows = value.value.rows || [];
  if (!Array.isArray(rows) || rows.length > size || value.hasMore && rows.length !== size) throw Error('Frozen composite rows incomplete');
  return rows.map(row => {
    if (!Array.isArray(row.fields) || row.fields.length !== 3 || new Set(row.fields.map(f => f.key)).size !== 3) throw Error('Complete composite projection required');
    const fields = Object.fromEntries(row.fields.map(f => [f.key, f.value])), { id, name, sortOrder } = fields;
    if (id?.kind !== 'integer' || typeof id.number !== 'string' || !/^[1-9][0-9]*$/.test(id.number) || BigInt(id.number) > 9223372036854775807n ||
        name?.kind !== 'string' || name.text !== undefined && typeof name.text !== 'string' || sortOrder?.kind !== 'integer' || !/^[0-2]$/.test(sortOrder.number)) throw Error('Composite exact primary key or typed fixture scalar invalid');
    return { id: id.number, name: name.text || '', sortOrder: Number(sortOrder.number) };
  });
}
const compareComposite = (a, b) => a.sortOrder - b.sortOrder || compareId(a, b);
async function scanComposite(h, actor, context, parameters = []) {
  const page = require('./page_runtime_cases.cjs'), rows = [], tokens = new Set(); let cursor, first;
  for (let i = 0; i < 200; i++) {
    const result = await page.sourceRead(h, actor, context, { sourceKey: 'records', pageSize: 3, parameters, ...(cursor ? { cursor } : {}) });
    h.check('Original composite frozen page read succeeds and disables private caching', h.good(result) && result.cacheControl?.includes('no-store'), result);
    const next = decodeComposite(result.data.value, context, 3);
    h.check('Composite keyset order advances strictly across sort ties and page boundaries', next.every((r, i) => i ? compareComposite(next[i - 1], r) < 0 : !rows.length || compareComposite(rows.at(-1), r) < 0));
    rows.push(...next); first ||= result.data.value;
    if (!result.data.value.hasMore) return { rows, first };
    cursor = result.data.value.nextCursor;
    if (tokens.has(cursor)) throw new h.Blocked('Original composite continuation repeats');
    tokens.add(cursor);
  }
  throw new h.Blocked('Composite page budget exhausted; not a complete dataset proof');
}
function decodeTypedRow(row) {
  if (!Array.isArray(row.fields) || row.fields.length !== 6) throw Error('Complete typed projection required');
  const fields = Object.fromEntries(row.fields.map(f => [f.key, f.value]));
  const { id, sortOrder, flag, amount, occurredAt } = fields;
  if (id?.kind !== 'integer' || !/^[1-9][0-9]*$/.test(id.number || '') ||
      sortOrder?.kind !== 'integer' || !/^-?(0|[1-9][0-9]*)$/.test(sortOrder.number || '') ||
      flag?.kind !== 'boolean' || (flag.boolean !== undefined && typeof flag.boolean !== 'boolean') ||
      amount?.kind !== 'decimal' && amount?.kind !== 'integer' ||
      occurredAt?.kind !== 'datetime' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$/.test(occurredAt.text || '')) {
    throw Error('Paginated typed projection scalar invalid');
  }
  return { id: id.number, sortOrder: sortOrder.number, flag: Boolean(flag.boolean), amount: amount.number, occurredAt: occurredAt.text };
}
async function pagination(h) {
  const { modelEntities, inputViews } = require('./model_input_cases.cjs'), { authoring } = require('./authoring_cases.cjs');
  const page = require('./page_runtime_cases.cjs'), f = await page.explicitFixture(h, (content, entity) => {
    compositeSource(content);
    content.dataSources.push({
      key: 'typedRecords', mode: 'list', entity, fields: ['id', 'sortOrder', 'flag', 'amount', 'occurredAt', 'name'],
      authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation',
      pagination: { mode: 'cursor', defaultPageSize: 10, maxPageSize: 50 }, orderBy: [{ field: 'id', direction: 'asc' }],
    });
  }, undefined, {
    suffix: 'compositecursor', requestPrefix: 'composite-cursor-',
    prepareAuthor: async (h2, authored) => {
      const current = await authoring.draft(h2, authored.app);
      authored.model = await authoring.save(h2, authored.app, current, modelEntities(current.entities[0], 'types'));
      authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h2, authored.app, 'pages');
    },
    buildEntityViews: inputViews,
  });
  const actor = await business.member(h, 'manager'), contexts = [], records = []; let primary;
  try {
    for (let i = 0; i < 2; i++) {
      const context = await business.runtime(h, f, i, actor);
      context.pageDigest = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value.installation.pageDigest;
      contexts.push(context);
    }
    h.check('New isolated composite fixture starts empty in both exact installations', (await collection(h, actor, contexts[0])).length === 0 && (await collection(h, actor, contexts[1])).length === 0);
    for (let i = 0; i < 12; i++) {
      const r = await business.create(h, contexts[0], 'same-composite-name'); records.push(r);
      const updates = [{ name: 'flag', value: i % 2 === 0 }, { name: 'amount', value: 1.25 + i }, { name: 'occurredAt', value: '2026-10-14T0' + (i % 10) + ':00:00.000Z' }];
      if (i % 3) updates.push({ name: 'sortOrder', value: i % 3 });
      await business.execute(h, actor, r, business.request(r, 'update', updates));
    }
    const typedResult = await page.sourceRead(h, actor, contexts[0], { sourceKey: 'typedRecords', pageSize: 20 });
    h.check('Paginated typed projection preserves exact bool/decimal/UTC/int64 scalars',
      h.good(typedResult) && typedResult.data.value.value.rows.length === 12 &&
      typedResult.data.value.value.rows.map(decodeTypedRow).every(v => v.occurredAt.endsWith('Z')), typedResult);
    const expected = [];
    for (const r of records) {
      const result = await business.record(h, actor, r);
      h.check('Independent original owner read resolves exact updated scalar values and version', h.good(result) && String(result.data.value.id) === r.recordId && String(result.data.value.version) === r.version);
      expected.push({ id: r.recordId, name: result.data.value.name, sortOrder: result.data.value.sortOrder });
    }
    expected.sort(compareComposite);
    const all = await scanComposite(h, actor, contexts[0]);
    h.check('All12 independently owned records appear once across composite sort ties', same(all.rows, expected) && !!all.first.nextCursor, { actual: all.rows, expected });
    const parameters = bucket => [{ name: 'bucket', value: { kind: 'integer', number: String(bucket) } }];
    for (const bucket of [0, 1, 2]) h.check('Fresh filter starts its own complete keyset without retaining previous page cursor', same((await scanComposite(h, actor, contexts[0], parameters(bucket))).rows, expected.filter(r => r.sortOrder === bucket)));
    for (const [target, body] of [
      [contexts[0], { cursor: 'invalid-original-composite-cursor' }],
      [contexts[1], { cursor: all.first.nextCursor }],
      [contexts[0], { cursor: all.first.nextCursor, parameters: parameters(1) }],
      [contexts[0], { cursor: all.first.nextCursor, pageSize: 2 }],
    ]) {
      const result = await page.sourceRead(h, actor, target, { sourceKey: 'records', pageSize: 3, ...body });
      h.check('Malformed, foreign-installation or changed-filter/page-size original signed cursor is rejected', [200, 400, 409].includes(result.status) && [4, 19, 21].includes(result.data?.error?.code) && result.data.value == null, result);
    }
    h.check('Independent fresh complete pages and untouched peer survive all cursor refusals', same((await scanComposite(h, actor, contexts[0])).rows, expected) && (await collection(h, actor, contexts[1])).length === 0);
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...records].reverse(), primary);
    const ids = new Set(f.installations.map(v => String(v.id)));
    if (h.state.resources.some(r => r.kind === 'business-record' && ids.has(r.identity?.installationId) && r.phase !== 'deleted')) {
      if (!primary) throw new h.Blocked('Original composite business write remains unresolved; preserve installation');
    } else await page.disposeExplicitFixture(h, f, primary);
  }
  await require('./field_constraint_cases.cjs').handlers['F013-002'](h);
  await h.partial('Composite signed keyset, sort ties, typed bool/decimal/UTC/int64 paginated projections, exact filter changes and malformed/installation/filter/page-size refusals, plus original field boundary/readonly/null/empty/zero errors and unchanged-row proof verified. Natural cursor expiry and relation collection projection boundaries remain unverified [C]. Static controlled data does not claim a concurrent snapshot.');
}
const handlers = { 'F036-001': crud, 'F036-002': pagination };
for (const handler of Object.values(handlers)) { handler.transport = 'owner-api'; handler.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers, decodeCollection, collection, completeRows, compositeSource, decodeComposite, compareComposite };
