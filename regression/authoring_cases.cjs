// Authoring commands use isolated definitions, never installed business data.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const handlers = {};
const base = '/panel/application/definitions/';
const clone = value => structuredClone(value);
const fixture = (h, name) => JSON.parse(h.fs.readFileSync(h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression/' + name)));
async function definition(h, suffix) {
  const body = fixture(h, 'fixture-definition-create-request.json');
  Object.assign(body, { uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-' + suffix, pkgPrefix: h.state.prefix + suffix.replaceAll('-', '') });
  return h.create(base, body, 'definition');
}
const draft = (h, app) => h.ok(h.admin, 'GET', base + app.id + '/model-draft').then(r => r.value);
function newEntity(h, app) {
  const entity = fixture(h, 'fixture-draft-atomic-save-request.json').entities[0];
  entity.pkgPath = '/' + app.pkgPrefix;
  return entity;
}
function entityCommand(entity) {
  const command = clone(entity);
  delete command.createTime; delete command.updateTime; delete command.application;
  if (entity.updateTime) command.expectedEntityVersion = entity.updateTime;
  return command;
}
function command(before, entities) {
  return { expectedDefinitionVersion: before.definitionVersion,
    baseline: before.entities.map(e => ({ id: e.id, entity: e.pkgPath + '/' + e.name, version: e.updateTime })),
    entities: entities.map(entityCommand) };
}
function journalSave(h, app, route, payload) {
  const owner = h.state.resources.find(r => r.collection === base && r.id === app.id);
  if (!owner?.creation || owner.pendingAuthoringSave && !owner.pendingAuthoringSave.confirmed) throw new h.Blocked('Author save requires an exact owned definition and no unresolved original save');
  owner.pendingAuthoringSave = { journalId: crypto.randomBytes(16).toString('hex'), route, payload: clone(payload), confirmed: false };
  h.persist();
  return owner.pendingAuthoringSave;
}
async function save(h, app, before, entities) {
  const route = base + app.id + '/model-draft', payload = command(before, entities);
  const checked = (await h.ok(h.admin, 'POST', route + '/check', payload)).value;
  h.check('Model check leaves persisted original draft unchanged', same(await draft(h, app), before));
  const intent = journalSave(h, app, route, payload);
  intent.response = await h.ok(h.admin, 'PUT', route, payload); h.persist();
  const after = await draft(h, app);
  h.check('Independent owner read matches the prechecked whole target digest', after.targetDigest === checked.targetDigest && after.definitionVersion > before.definitionVersion && after.applicationId === app.id && after.applicationUuid === app.uuid, after);
  intent.confirmed = true; h.persist();
  return after;
}
async function library(h, app) {
  const route = base + app.id + '/function-blocks';
  const before = (await h.ok(h.admin, 'GET', route)).value;
  const source = 'package block\nimport "context"\nfunc Handle(ctx context.Context,input,output map[string]any) error { output["result"]=input["label"]; return nil }';
  const parameters = [{ name: 'count', type: 'number', required: true }, { name: 'enabled', type: 'boolean', required: true }, { name: 'label', type: 'string', required: true }];
  const spec = { key: 'display', name: '受控绑定', language: 'go', sourceFiles: ['display/main.go'], entrypoint: { file: 'display/main.go', function: 'block.Handle' }, inputs: parameters, outputs: [{ name: 'result', type: 'string', required: true }] };
  const content = { schemaVersion: before.content.schemaVersion, definitions: [{ key: 'display', definition: 'display/definition.json' }], files: {
    'display/definition.json': Buffer.from(JSON.stringify(spec)).toString('base64'), 'display/main.go': Buffer.from(source).toString('base64') } };
  const intent = journalSave(h, app, route, { expectedDefinitionVersion: before.definitionVersion, content });
  intent.response = await h.ok(h.admin, 'PUT', route, intent.payload); h.persist();
  h.check('Independent library read preserves exact source bytes and parameter declarations', same((await h.ok(h.admin, 'GET', route)).value.content, content));
  intent.confirmed = true; h.persist();
  return content;
}
async function scriptBinding(h) {
  const catalog = (await h.ok(h.admin, 'GET', '/panel/application/definition/entity/blocks/')).values;
  const interpreter = catalog.find(x => x.kind === 'scriptInterpreter');
  if (!interpreter) throw new h.Blocked('Formal block catalogue lacks script interpreter');
  const hook = clone(interpreter.stageInfo.functions.insert);
  Object.assign(hook, { eventID: '/interpreter/script', bindScript: null, checkType: 'preCheck', input: { count: 0, enabled: false, label: '$referenceValue.name' }, bindField: 'description', resultField: 'result', executeTimeout: 1000 });
  return { id: interpreter.id, key: 'display-binding', name: '显示映射', scriptKey: 'display', stageInfo: { startup: null, teardown: null, functions: { insert: hook } } };
}

handlers['F018-001'] = async h => {
  const app = await definition(h, 'atomic');
  const content = await library(h, app), entity = newEntity(h, app);
  entity.blockInfo = [await scriptBinding(h)];
  const first = await save(h, app, await draft(h, app), [entity]);
  h.check('Creation assigns a safe positive definition identity and retains binding', first.entities.length === 1 && Number.isSafeInteger(first.entities[0].id) && first.entities[0].id > 0 && same(first.entities[0].blockInfo, entity.blockInfo), first);
  const edited = clone(first.entities[0]); edited.showName = '已编辑原实体'; edited.description = '同一身份原子保存';
  edited.blockInfo[0].stageInfo.functions.insert.input.label = 'edited literal';
  const second = await save(h, app, first, [edited]);
  const current = second.entities[0];
  h.check('Editing preserves definition identity and all fields alongside exact changed binding', second.entities.length === 1 && current.id === edited.id && current.showName === edited.showName && current.description === edited.description && same(current.fields, edited.fields) && same(current.blockInfo, edited.blockInfo), current);
  h.check('Entity command does not rewrite separately saved source library', same((await h.ok(h.admin, 'GET', base + app.id + '/function-blocks')).value.content, content));
};

handlers['F018-002'] = async h => {
  const app = await definition(h, 'conflict'), route = base + app.id + '/model-draft';
  const before = await draft(h, app), entity = newEntity(h, app), payload = command(before, [entity]);
  const firstIntent = journalSave(h, app, route, payload);
  const outcomes = await Promise.all([h.api(h.admin, 'PUT', route, payload), h.api(h.admin, 'PUT', route, payload)]);
  firstIntent.responses = outcomes; h.persist();
  h.check('Exactly one concurrent original-version command commits', outcomes.filter(h.good).length === 1 && outcomes.some(r => r.data?.error?.code === 19), outcomes);
  const first = await draft(h, app);
  h.check('Concurrent save created one exact original entity', first.entities.length === 1 && first.entities[0].name === entity.name && same(first.entities[0].fields, outcomes.find(h.good).data.value.entities[0].fields), first);
  firstIntent.confirmed = true; h.persist();
  const edited = clone(first.entities[0]); edited.showName = '提交后丢失响应';
  const lost = command(first, [edited]), endpoint = '/api/v1/web/proxy' + route;
  const intent = journalSave(h, app, route, lost);
  let intercepted = 0, submitted;
  const pattern = url => url.pathname === endpoint;
  const fault = async r => {
    if (r.request().method() !== 'PUT') return r.continue();
    intercepted++;
    const upstream = await r.fetch({ maxRetries: 0 });
    submitted = { status: upstream.status(), data: await upstream.json() };
    intent.response = submitted; h.persist();
    await r.abort('failed');
  };
  await h.admin.page.route(pattern, fault);
  let responseLost = false;
  try { await h.api(h.admin, 'PUT', route, lost); }
  catch (error) { responseLost = /fetch|network|failed/i.test(error.message); }
  finally { await h.admin.page.unroute(pattern, fault); }
  h.check('One exact owner save committed before its browser response was lost', intercepted === 1 && responseLost && submitted && h.good(submitted), submitted);
  const confirmed = await draft(h, app);
  h.check('Independent original-identity read confirms unknown browser save without replay', confirmed.entities.length === 1 && confirmed.entities[0].id === edited.id && confirmed.entities[0].showName === edited.showName && confirmed.targetDigest === submitted.data.value.targetDigest && confirmed.definitionVersion === submitted.data.value.definitionVersion && same(confirmed.entities[0].fields, first.entities[0].fields), confirmed);
  intent.confirmed = true; h.persist();
};

handlers['F018-003'] = async h => {
  const app = await definition(h, 'autoid'), entity = newEntity(h, app);
  entity.fields.find(f => f.name === 'id').spec.valueDeclare = 'auto';
  const first = await save(h, app, await draft(h, app), [entity]);
  const edited = clone(first.entities[0]); edited.showName = '自增业务主键下的定义编辑';
  edited.fields.find(f => f.name === 'name').showName = '修改后的业务名称';
  const after = await save(h, app, first, [edited]);
  h.check('Business auto key declaration never replaces original entity definition ID', after.entities.length === 1 && after.entities[0].id === first.entities[0].id && after.entities[0].id > 0 && after.entities[0].showName === edited.showName && same(after.entities[0].fields, edited.fields) && after.entities[0].fields.find(f => f.name === 'id').spec.valueDeclare === 'auto', after);
};

handlers['F015-002'] = async h => {
  const app = await definition(h, 'stages'), entity = newEntity(h, app);
  const declarations = (await h.ok(h.admin, 'GET', '/panel/application/definition/entity/blocks/')).values;
  const logger = declarations.find(x => x.kind === 'operationlog');
  if (!logger?.stageInfo.functions['*']) throw new h.Blocked('Formal logger stage declaration unavailable');
  const hook = clone(logger.stageInfo.functions['*']);
  entity.blockInfo = [{ id: logger.id, key: 'log', stageInfo: { functions: { insert: hook } } }];
  const original = await save(h, app, await draft(h, app), [entity]);
  for (const [label, change, diagnostic] of [
    ['unsupported timing', e => { e.blockInfo[0].stageInfo.functions.insert.checkType = 'preCheck'; }, /不支持所选执行时机/],
    ['unsupported operation', e => { e.blockInfo[0].stageInfo.functions = { unknown: hook }; }, /触发操作无效|不支持/],
  ]) {
    const invalid = clone(original.entities[0]); change(invalid);
    for (const [method, suffix] of [['POST', '/check'], ['PUT', '']]) {
      const result = await h.api(h.admin, method, base + app.id + '/model-draft' + suffix, command(original, [invalid]));
      h.check('Owner rejects ' + label + ' at block validation during ' + method, !h.good(result) && result.data?.error?.code === 4 && diagnostic.test(result.data.error.message), result);
      h.check('Rejected block cannot partially change any original model bytes', same(await draft(h, app), original));
    }
  }
};

handlers['F067-004'] = async h => {
  const app = await definition(h, 'pageauth'), route = base + app.id + '/pages';
  const originalModel = await save(h, app, await draft(h, app), [newEntity(h, app)]);
  const before = (await h.ok(h.admin, 'GET', route)).value;
  const content = clone(before.content);
  content.defaultPage = 'home'; content.navigation = ['home'];
  content.dataSources = [{ key: 'records', entity: originalModel.entities[0].pkgPath + '/' + originalModel.entities[0].name, mode: 'list', fields: ['id', 'name'], authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation', pagination: { mode: 'cursor', defaultPageSize: 10, maxPageSize: 100 }, orderBy: [{ field: 'id', direction: 'asc' }] }];
  content.pages = [{ key: 'home', title: '只读能力预检', routes: ['/'], navigation: true, layout: { type: 'responsive-grid', columns: 12, gap: 0 }, routeParameters: [], components: [{ key: 'title', type: 'text', layout: { span: 12, order: 0 }, dataSources: [], properties: { text: '真实作者草稿' } }] }];
  const payload = { expectedDefinitionVersion: before.definitionVersion, content };
  const cas = '/cas/namespaces/' + h.credentials.namespace + '/';
  const template = await h.create(cas + 'role-templates/', { key: h.state.prefix + '-page-reader', name: '回归页面只读作者', description: '复用正式发布负责人读取权限', subjectType: 'account', roleRefs: [{ module: '/modules/kernel/runner', key: 'management-application-publisher' }], applicationAccess: [], status: 2 }, 'role-template');
  const account = await h.create(cas + 'accounts/', { account: h.state.prefix + '-page-reader', displayName: '回归页面只读作者', password: h.state.password, status: 2, roleTemplateKeys: [template.key] }, 'account');
  const reader = await h.login(account.account, h.state.password, h.credentials.namespace, h.state.password + 'P');
  const ordinaryAccount = await h.create(cas + 'accounts/', { account: h.state.prefix + '-page-member', displayName: '同租户无作者权限成员', password: h.state.password, status: 2, roleTemplateKeys: ['portal-basic-user'] }, 'account');
  const ordinary = await h.login(ordinaryAccount.account, h.state.password, h.credentials.namespace, h.state.password + 'M');
  for (const actor of [h.admin, reader]) {
    h.check('Owner read is identical for authorized author and reader', same((await h.ok(actor, 'GET', route)).value, before));
    const report = (await h.ok(actor, 'POST', route + '/check', payload)).value;
    h.check('Public capability evaluation returns a real readiness report', report?.ready === true, report);
    const stale = await h.api(actor, 'POST', route + '/check', { ...payload, expectedDefinitionVersion: before.definitionVersion - 1 });
    h.check('Read-only evaluation rejects stale definition version', stale.data?.error?.code === 19, stale);
    for (const kind of ['entity', 'field']) {
      const invalid = clone(content);
      if (kind === 'entity') invalid.dataSources[0].entity += '_missing';
      else invalid.dataSources[0].fields.push('missing_reference_field');
      const rejected = await h.api(actor, 'POST', route + '/check', { ...payload, content: invalid });
      h.check('Page evaluation rejects an absent original model ' + kind, rejected.data?.error?.code === 4 && (kind === 'entity' ? /实体不存在/.test(rejected.data.error.message) : /missing_reference_field/.test(rejected.data.error.message)), rejected);
      h.check('Rejected reference check leaves original model untouched', same(await draft(h, app), originalModel));
    }
  }
  h.denied(await h.api(reader, 'PUT', route, payload), 'Readonly page check does not grant authoring write permission');
  for (const [method, suffix] of [['GET', ''], ['POST', '/check'], ['PUT', '']]) h.denied(await h.api(ordinary, method, route + suffix, method === 'GET' ? undefined : payload), 'Same namespace member lacks page authoring read/check/write authority');
  for (const actor of [h.user, h.tenantAdmin]) for (const [method, suffix] of [['GET', ''], ['POST', '/check'], ['PUT', '']]) {
    h.inaccessible(await h.api(actor, method, route + suffix, method === 'GET' ? undefined : payload), 'Unauthorized foreign namespace cannot read/check/save author pages');
  }
  h.check('Checking and denied writes leave exact definition and page content unchanged', same((await h.ok(h.admin, 'GET', route)).value, before));
  h.check('All capability checks preserve the exact original model', same(await draft(h, app), originalModel));
  const intent = journalSave(h, app, route, payload);
  intent.response = await h.ok(h.admin, 'PUT', route, payload); h.persist();
  const after = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Authorized author alone saves exact checked page content', after.applicationId === app.id && after.definitionVersion > before.definitionVersion && same(after.content, content), after);
  const savedModel = await draft(h, app);
  h.check('Page save preserves original entity identities and fields', same(savedModel.entities, originalModel.entities));
  intent.confirmed = true; h.persist();
};
handlers['F067-004'].actors = ['user', 'tenantAdmin'];
// API-only commands select one-shot owner transport before execution.
// F018-002 deliberately keeps its original browser response-loss injection.
for (const id of ['F015-002', 'F018-001', 'F018-003', 'F067-004']) handlers[id].transport = 'owner-api';
module.exports = { handlers, authoring: { definition, draft, save, newEntity, library, scriptBinding, journalSave, command } };
