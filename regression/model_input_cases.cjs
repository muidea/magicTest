const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const probes = require('./scenario_commands.cjs');
const definitions = '/panel/application/definitions/';
function field(name, type, nullable = false, constraint = '') {
  return { name, showName: name, description: '', type: { name: type, pkgPath: '', isPtr: nullable, elemType: null },
    spec: { fieldName: name, primaryKey: false, valueDeclare: '', viewDeclare: ['detail', 'lite'], constraint, defaultValue: null } };
}
function relation(name, target, multiple = false, owned = false) {
  const f = field(name, target.name, !owned); f.type.pkgPath = target.pkgPath;
  if (multiple) f.type = { name: '', pkgPath: '', isPtr: false, elemType: f.type };
  return f;
}
function modelEntities(entity, mode) {
  const host = structuredClone(entity);
  if (mode === 'types') {
    host.fields.push(field('flag', 'boolean', false), field('amount', 'float64', false), field('occurredAt', 'datetime', true));
    return [host];
  }
  const target = structuredClone(entity); target.id = 0; target.name = 'zzRelationTarget'; target.showName = '引用目标';
  delete target.createTime; delete target.updateTime; delete target.expectedEntityVersion;
  target.uniqueConstraints = target.uniqueConstraints.map(c => ({ ...c, name: c.name + '_target' }));
  host.fields.push(relation('target', target), relation('targets', target, true));
  return [host, target];
}
async function prepare(h, authored, mode) {
  authored.model = await a.save(h, authored.app, await a.draft(h, authored.app), modelEntities(authored.model.entities[0], mode));
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
async function withFixture(h, suffix, mode, run) {
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix, requestPrefix: suffix + '-', prepareAuthor: (h, authored) => prepare(h, authored, mode), buildEntityViews: inputViews });
  const actor = await business.member(h, 'manager'), contexts = [await business.runtime(h, f, 0, actor), await business.runtime(h, f, 1, actor)], rows = [];
  let primary;
  try { await run({ f, actor, contexts, rows }); }
  catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const open = h.state.resources.some(r => r.kind === 'business-record' && r.phase !== 'deleted' && r.scenarioDefinitionId === f.application.id);
    if (open) { h.observe({ kind: 'model-input-disposition-open', definitionId: f.application.id }); if (!primary) throw new h.Blocked('Original typed/relation row disposition remains open'); }
    else await pages.disposeExplicitFixture(h, f, primary);
  }
}
function inputViews(authored, originalUI) {
  const result = {};
  for (const entity of authored.model.entities) {
    const seed = structuredClone(originalUI);
    for (const f of entity.fields.filter(f => !seed.fields.some(v => v.name === f.name))) {
      const type = { boolean: 'boolean', float64: 'number', datetime: 'string' }[f.type.name] || (f.type.elemType ? 'array' : 'object');
      seed.fields.push({ name: f.name, type, required: false, readonly: false, searchable: false, sortable: false,
        ...(f.type.name === 'datetime' ? { format: 'date-time' } : {}) });
    }
    result[entity.pkgPath + '/' + entity.name] = pages.explicitView(entity, seed);
  }
  return result;
}
async function create(h, f, actor, context, rows, fields = [], entity) {
  const r = { kind: 'business-record', phase: 'intent', actorRole: 'manager', ...context, scenarioDefinitionId: f.application.id,
    origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [] };
  delete r.ui; if (entity) r.entity = entity;
  rows.push(r); h.state.resources.push(r); h.persist();
  const body = business.request(r, 'create', [{ name: 'code', value: 'RG-' + crypto.randomBytes(8).toString('hex').toUpperCase() },
    { name: 'name', value: '输入原样本' }, { name: 'description', value: null }, { name: 'sortOrder', value: 0 }, ...fields]);
  await business.execute(h, actor, r, body);
  const result = await business.record(h, actor, r);
  h.check('Independent complete typed/relation owner row binds original generated ID and version', h.good(result) && String(result.data.value.id) === r.recordId && String(result.data.value.version) === r.version, result);
  r.created = result.data.value; r.createRequest = body; h.persist(); return r;
}
function ids(value) {
  const array = value == null ? [] : Array.isArray(value) ? value : [value];
  const found = array.map(v => {
    const id = v?.id;
    if (typeof id !== 'string' && !Number.isSafeInteger(id) || !/^[1-9][0-9]*$/.test(String(id))) throw Error('Unsafe or missing actual relation identity');
    return String(id);
  }).sort();
  if (new Set(found).size !== found.length) throw Error('Duplicate actual relation identity');
  return found;
}
async function rejectedWrite(h, actor, r, body, expected, observed = [r]) {
  if (r.commands.some(c => c.outcome === 'unknown') || r.constraintCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original relation input command unknown; no replay');
  const before = [];
  for (const row of observed) { const v = await business.record(h, actor, row); h.check('Original input rejection starts with readable complete owner row', h.good(v)); before.push(v.data.value); }
  const c = { body: structuredClone(body), outcome: 'unknown' }; (r.constraintCommands ||= []).push(c); h.persist();
  c.response = await h.api(actor, 'POST', business.route(r, body.operation, false), body); h.persist();
  c.query = await h.api(actor, 'POST', business.route(r, body.operation, true), body); h.persist();
  const after = [];
  for (const row of observed) { const v = await business.record(h, actor, row); h.check('Rejected input still has readable complete independent owner row', h.good(v)); after.push(v.data.value); }
  const denied = [200, 400, 404, 409].includes(c.response.status) && c.response.data?.error?.code === expected.code &&
    new RegExp(expected.messagePattern).test(c.response.data.error.message) && c.response.data.value == null;
  if (expected.stage === 'browser-contract') {
    // Apps validates the same immutable input before execute and receipt lookup.
    // This proves an admission refusal, not absence of a durable owner receipt.
    const admission = v => v.status === 200 && v.data?.error?.code === 4 &&
      v.data.error.message === '业务写入请求或精确身份无效' && v.data.value == null;
    if (denied && admission(c.response) && admission(c.query) && same(after, before)) {
      c.outcome = 'rejected-at-browser-contract'; h.persist();
    }
    h.check('Exact browser contract rejects original input and receipt query; original owner rows remain unchanged',
      c.outcome === 'rejected-at-browser-contract', { command: c, before, after });
    return;
  }
  const absent = [200, 404].includes(c.query.status) && c.query.data?.error?.code === 2 && c.query.data.error.message === '原业务写入尚无完成事实；禁止据此自动重发' && c.query.data.value == null;
  if (denied && absent && same(after, before)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Exact relation/form refusal, original completion absence and full owner rows prove no partial effect', c.outcome === 'rejected-and-unchanged', { command: c, before, after });
}
async function scalarTypes(h) {
  await withFixture(h, 'scalartypes', 'types', async ({ f, actor, contexts, rows }) => {
    const initial = [{ name: 'flag', value: false }, { name: 'amount', value: 0 }, { name: 'occurredAt', value: null }];
    const r = await create(h, f, actor, contexts[0], rows, initial);
    h.check('False, numeric zero, nullable time and nullable text survive actual reliable create', initial.every(v => same(r.created[v.name], v.value)) && r.created.description === null && r.created.sortOrder === 0);
    for (const values of [{ description: '', flag: true, amount: 1.25, occurredAt: '2026-01-02T03:04:05.006Z' }, { description: null, flag: false, amount: 0, occurredAt: null }]) {
      await business.execute(h, actor, r, business.request(r, 'update', Object.entries(values).map(([name, value]) => ({ name, value }))));
      const current = (await business.record(h, actor, r)).data.value;
      h.check('Sparse scalar updates preserve original code/key and exact bool/float/text/null; time uses the declared UTC value',
        current.code === r.created.code && String(current.id) === r.recordId && current.description === values.description && current.flag === values.flag && current.amount === values.amount &&
        (values.occurredAt == null ? current.occurredAt === null : Date.parse(current.occurredAt + (/[zZ]|[+-]\d\d:\d\d$/.test(current.occurredAt) ? '' : 'Z')) === Date.parse(values.occurredAt)), current);
    }
    await require('./field_constraint_cases.cjs').reject(h, actor, r, 'flag', 'false', { code: 21, message: '写入标量类型或约束无效: flag' });
  });
  await h.partial('Scalar string/int/nullable/bool/float/UTC installed write subset implemented. Full supported-type inventory, exact large-integer page encoding and actual display matrix remain open.');
}
async function references(h, mode) {
  await withFixture(h, 'relations' + mode, 'relations', async ({ f, actor, contexts, rows }) => {
    const targetEntity = f.revision.entities.find(e => e.name === 'zzRelationTarget');
    h.check('Frozen publication contains exact declared target and host single/collection pointer types', !!targetEntity && f.revision.entities[0].fields.some(v => v.name === 'targets' && v.type.elemType?.isPtr));
    const targetKey = targetEntity.pkgPath + '/' + targetEntity.name;
    const target = await create(h, f, actor, contexts[0], rows, [], targetKey), peer = await create(h, f, actor, contexts[1], rows, [], targetKey);
    const host = await create(h, f, actor, contexts[0], rows, [{ name: 'target', reference: { id: target.recordId } }, { name: 'targets', references: [{ id: target.recordId }] }]);
    h.check('Independent runtime owner resolves original single and collection references only to exact same-installation target', same(ids(host.created.target), [target.recordId]) && same(ids(host.created.targets), [target.recordId]));
    if (mode === 'isolation') {
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'target', reference: { id: peer.recordId } }]), { code: 2, messagePattern: '.+' }, [host, target, peer]);
    } else if (mode === 'boundaries') {
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'target', reference: { id: '9223372036854775807' } }]), { code: 2, messagePattern: '.+' }, [host, target, peer]);
      const duplicate = business.request(host, 'create', [{ name: 'targets', references: [{ id: target.recordId }, { id: target.recordId }] }]);
      await rejectedWrite(h, actor, host, duplicate, { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' }, [host, target, peer]);
      await business.execute(h, actor, host, business.request(host, 'update', [{ name: 'target', value: null }]));
      h.check('Explicit single reference null clears only that relation', (await business.record(h, actor, host)).data.value.target == null);
      const empty = await create(h, f, actor, contexts[0], rows, [{ name: 'target', value: null }, { name: 'targets', references: [] }]);
      h.check('Explicit empty reference collection stays empty', ids(empty.created.targets).length === 0);
    } else if (mode === 'forms') {
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'targets', references: [] }]), { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' }, [host, target, peer]);
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'id', value: 7 }]), { code: 21, messagePattern: '^写入字段未声明、不可写或不是单值: id$' }, [host, target, peer]);
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'name', value: false }]), { code: 21, messagePattern: '^写入标量类型或约束无效: name$' }, [host, target, peer]);
    } else {
      await business.execute(h, actor, host, business.request(host, 'update', [{ name: 'target', value: null }]));
      h.check('Single relation clears without deleting independent target', (await business.record(h, actor, host)).data.value.target == null && same((await business.record(h, actor, target)).data.value, target.created));
    }
    h.check('Original peer target remains exactly unchanged', same((await business.record(h, actor, peer)).data.value, peer.created));
  });
  const limits = { basic: 'Owned containment and full relation delete policy matrix', isolation: 'Another application and actual other-tenant bindings', boundaries: 'Owned/cyclic author graph and all declared delete constraints', forms: 'Declared128-field/48KiB/1024-reference exact boundaries, full failed-batch atomicity and actual form UI' };
  await h.partial('Installed reliable single/reference-collection subset completed. ' + limits[mode] + ' remain open; no fallback to ordinary CRUD.');
}
async function structure(h) {
  const app = await a.definition(h, 'structuregraph'), entities = modelEntities(a.newEntity(h, app), 'relations');
  const before = await a.save(h, app, await a.draft(h, app), entities), owner = h.state.resources.find(r => r.kind === 'definition' && r.id === app.id);
  const host = structuredClone(before.entities[0]), target = before.entities[1];
  // Whole-draft omission is an upsert, never a deletion command. Exercise the
  // real entity DELETE, with the incoming model relation still present.
  const route = '/panel/application/definition/entitys/' + target.id;
  await probes.reject(h, owner, h.admin, 'DELETE', route, undefined,
    [definitions + app.id + '/model-draft'], { code: 4, messagePattern: '引用|关系|目标|relation|实体' });
  h.check('Rejected referenced-structure deletion preserves exact target definition and identity', same(await a.draft(h, app), before) && before.entities.some(v => v.id === target.id));
  const noRefs = structuredClone(before.entities[0]); noRefs.fields = noRefs.fields.filter(v => !['target', 'targets'].includes(v.name));
  const unlinked = await a.save(h, app, before, [noRefs, target]);
  const command = { method: 'DELETE', route, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' };
  owner.scenarioCommands.push(command); h.persist(); command.response = await h.api(h.admin, 'DELETE', route); h.persist();
  const after = await a.draft(h, app);
  h.check('Actual entity DELETE acknowledges only original unreferenced structure and preserves complete host', h.good(command.response) &&
    after.definitionVersion > unlinked.definitionVersion && same(after.entities, unlinked.entities.filter(e => e.id !== target.id)));
  command.outcome = 'confirmed'; h.persist();
  h.check('Formal unreferenced author structure deletion keeps host identity and removes exactly original target', after.entities.length === 1 && after.entities[0].id === host.id);
  await h.partial('Author graph incoming-reference rejection and no-reference removal implemented. Live Base installed/shared-owned structures and other-instance preservation still require dedicated lifecycle fixture.');
}
const handlers = { 'F013-001': scalarTypes, 'F014-001': h => references(h, 'basic'), 'F014-002': h => references(h, 'isolation'), 'F014-003': h => references(h, 'boundaries'), 'F014-004': structure, 'F070-004': h => references(h, 'forms') };
for (const fn of Object.values(handlers)) { fn.transport = 'owner-api'; fn.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers, field, relation, modelEntities, ids, rejectedWrite, withFixture, create, inputViews };
