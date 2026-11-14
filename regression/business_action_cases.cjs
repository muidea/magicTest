// Public frozen actions, original human roles and independent durable owner reads.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const authority = require('./application_authority_cases.cjs');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
function route(r, query = false) {
  // Bearer NormalizeURI maps action/query/ to actions/.
  return (query ? '/apps/entity/actions/' : '/apps/entity/action/execute/') + '?' + new URLSearchParams({ application: r.applicationKey, deploymentId: r.identity.deploymentId });
}
function request(r, extra = {}) {
  return { apiVersion: 'magic.entity-action/v1', operationId: crypto.randomBytes(16).toString('hex'), identity: structuredClone(r.identity),
    entity: r.entity, action: 'acknowledge', id: r.recordId, expectedVersion: r.version, fields: [{ name: 'description', value: '动作原始输入 Δ <&>' }], ...extra };
}
function inputDigest(body) {
  const i = body.identity, installationId = Number(i.installationId);
  if (!Number.isSafeInteger(installationId) || String(installationId) !== i.installationId) throw Error('Action digest cannot round original installation');
  const wire = { apiVersion: body.apiVersion, operationId: body.operationId,
    identity: { namespace: i.namespace, deploymentId: i.deploymentId, installationId, runtimeApplicationUuid: i.runtimeApplicationUuid,
      generation: i.generation, executionEpoch: i.executionEpoch, artifactDigest: i.artifactDigest },
    entity: body.entity, action: body.action, id: body.id, expectedVersion: body.expectedVersion, fields: body.fields };
  return 'sha256:' + hash(JSON.stringify(wire).replace(/[<>&\u2028\u2029]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')));
}
function receiptMatches(actor, body, value) {
  const timestamp = typeof value?.executedAt === 'string' && /^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z$/.exec(value.executedAt);
  const instant = timestamp && Date.parse(value.executedAt);
  return !!value && value.apiVersion === body.apiVersion && value.operationId === body.operationId && same(value.identity, body.identity) &&
    value.inputDigest === inputDigest(body) && value.subject === actor.subject && value.entity === body.entity && value.action === body.action &&
    value.id === body.id && value.version === String(BigInt(body.expectedVersion) + 1n) && value.state === 'acknowledged' &&
    !!timestamp && Number.isFinite(instant) && (!timestamp[2] || !timestamp[2].endsWith('0')) && new Date(instant).toISOString().slice(0, 19) === timestamp[1];
}
function refused(response, code, message) {
  return [200, 400, 403, 404, 409].includes(response?.status) && response.data?.error?.code === code && response.data.error.message === message && response.data.value == null;
}
// A route-level privilege gate (magicBase AddPrivilegeHandler) can refuse a
// business-action call before the owner evaluates its action grant. That path
// returns an explicit 403 with an empty body. It is still a real refusal, not a
// write result: callers must independently confirm the original owner row is
// unchanged and must never treat the refusal as success.
function routeDenied(response) {
  return response?.status === 403 && response.data?.value == null && response.data?.error == null && !String(response.data?.text || '').trim();
}
function guardCleanup(h, resource) {
  const templateKey = resource.creation?.intended?.key;
  if (resource.kind === 'role-template' && templateKey && h.state.resources.some(r => r.kind === 'account' && r.phase !== 'deleted' && r.authorityCommands?.some(c => c.outcome === 'unknown' &&
      (c.retiredTemplateKey === templateKey || c.body?.roleTemplateKeys?.includes(templateKey)))))
    throw new h.Blocked('Original action role assignment or retirement remains unresolved; retain its exact template');
  const rows = h.state.resources.filter(r => r.kind === 'business-record' && r.phase !== 'deleted' && (r.actionCommands?.length || r.actionDefinitionId != null));
  for (const row of rows) {
    const account = resource.kind === 'account' && resource.creation?.intended?.account;
    const namespace = /^\/cas\/namespaces\/([^/]+)\/accounts\/$/.exec(resource.collection || '')?.[1];
    if (resource !== row && (resource.kind === 'definition' && resource.id === row.actionDefinitionId ||
        resource.kind === 'role-template' && [row.actionTemplateId, ...(row.actionTemplateIds || [])].includes(resource.id) ||
        ['deployment-review-request', 'member-access-retirement'].includes(resource.kind) && String(resource.installation?.id) === row.identity.installationId ||
        account && row.actionCommands.some(c => c.actorIdentity?.account === account && c.actorIdentity.namespace === namespace)))
      throw new h.Blocked('Original business action row or command remains open; retain its original actor, role and installation for formal confirmation');
  }
}
function configure(content, entity) {
  const short = entity.split('/').at(-1);
  content.actions = { [short]: ['acknowledge'] };
  const table = content.pages.find(p => p.key === 'home').components.find(c => c.key === 'records');
  table.properties.actions = [short + '.acknowledge']; table.properties.readonly = false;
}
async function prepare(h, authored) {
  const { authoring: a } = require('./authoring_cases.cjs'), { authorFixture: author } = require('./page_author_cases.cjs');
  const entity = structuredClone(authored.model.entities[0]);
  entity.writeRules.state = { field: 'name', initial: 'open', transitions: [{ from: 'open', to: 'acknowledged' }] };
  entity.writeRules.actions = [{ key: 'acknowledge', from: 'open', to: 'acknowledged', inputFields: ['description'] }];
  authored.model = await a.save(h, authored.app, await a.draft(h, authored.app), [entity]);
  authored.pages = await author.read(h, authored.app, 'pages');
}
async function create(h, context, definitionId) {
  const actor = await business.member(h, 'manager');
  const r = { kind: 'business-record', phase: 'intent', actorRole: 'manager', ...context, actionDefinitionId: definitionId,
    origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [], actionCommands: [] };
  delete r.ui; h.state.resources.push(r); h.persist();
  const body = business.request(r, 'create', [{ name: 'code', value: 'RG-' + crypto.randomBytes(8).toString('hex').toUpperCase() },
    { name: 'name', value: 'open' }, { name: 'description', value: null }, { name: 'sortOrder', value: 0 }]);
  await business.execute(h, actor, r, body);
  const row = await business.record(h, actor, r);
  h.check('Independent original owner confirms exact initial action row and complete submitted scalar values', h.good(row) && String(row.data.value.id) === r.recordId && String(row.data.value.version) === r.version && body.fields.every(f => same(row.data.value[f.name], f.value)), row);
  r.created = row.data.value; h.persist(); return r;
}
async function command(h, actor, r, body, expected) {
  if (r.actionCommands.some(c => c.outcome === 'unknown') || r.commands?.some(c => c.outcome === 'unknown') || actor.origin !== r.origin) throw new h.Blocked('Original action unresolved or actor origin changed; no execute replay');
  const actorIdentity = structuredClone(actor.identity), subject = actor.subject;
  const manager = await business.member(h, 'manager'), before = await business.record(h, manager, r);
  h.check('Action starts at exact independently acknowledged original business version', h.good(before) && String(before.data.value.version) === r.version, before);
  const c = { body: structuredClone(body), actorIdentity: structuredClone(actor.identity), subject: actor.subject, outcome: 'unknown' };
  r.actionCommands.push(c); h.persist();
  try { c.response = await h.api(actor, 'POST', route(r), body); }
  catch (error) { c.transportError = error.message; }
  h.persist();
  h.check('Original acting account and subject remain unchanged before querying its durable receipt', same(actor.identity, actorIdentity) && actor.subject === subject && actor.origin === r.origin);
  // Query the exact original input even on a missing response. Never resend unknown execute.
  c.query = await h.api(actor, 'POST', route(r, true), body); h.persist();
  const after = await business.record(h, manager, r);
  h.check('Original action retains the exact acting account and subject through execution and confirmation', same(actor.identity, actorIdentity) && actor.subject === subject && actor.origin === r.origin);
  if (!expected) {
    const receipt = c.query.data?.value;
    if (h.good(c.query) && receiptMatches(actor, body, receipt) && (!c.response || h.good(c.response) && same(c.response.data.value, receipt)) &&
        Number.isSafeInteger(Number(receipt.version)) && h.good(after) && same(after.data.value, { ...before.data.value, name: receipt.state, version: Number(receipt.version), description: body.fields[0].value })) {
      c.receipt = receipt; c.outcome = 'confirmed'; r.version = receipt.version; h.persist();
    }
    h.check('Original action receipt and independent full row confirm exactly one transition with no other field changes', c.outcome === 'confirmed', { command: c, after });
    return c.receipt;
  }
  const routeRefusal = expected.queryRefused === true;
  const responseRefused = refused(c.response, expected.code, expected.message) || routeRefusal && routeDenied(c.response);
  const queryMatches = expected.receipt ? h.good(c.query) && same(c.query.data.value, expected.receipt) :
    expected.queryRefused ? refused(c.query, expected.code, expected.message) || routeDenied(c.query) : refused(c.query, 2, '原业务操作尚无完成事实；禁止据此自动重发');
  if (routeDenied(c.response)) { c.routeDenied = true; h.persist(); }
  if (responseRefused && queryMatches && h.good(after) && same(after.data.value, before.data.value)) {
    c.outcome = 'rejected-and-unchanged'; h.persist();
  }
  h.check('Target action refusal and exact original query preserve complete original owner row', c.outcome === 'rejected-and-unchanged', { command: c, after });
}
async function revoke(h, member, group, ordinary) {
  const r = member.resource;
  if (r.authorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original role assignment unresolved; no revocation replacement');
  const body = { roleTemplateKeys: ['portal-basic-user'], applicationScopes: [] };
  const c = { method: 'PUT', route: '/cas/namespaces/panel/accounts/' + member.value.id + '/role-templates', body, outcome: 'unknown', retiredTemplateKey: group.key };
  (r.authorityCommands ||= []).push(c); h.persist();
  c.response = await h.api(h.admin, c.method, c.route, body); h.persist();
  h.check('Original account role retirement is acknowledged without replacing its identity or session', h.good(c.response), c.response);
  const bindings = await h.directory(h.admin, '/cas/namespaces/panel/subject-role-bindings/?' + new URLSearchParams({ subjectId: member.value.id + '|=', subjectType: 'account|=' }));
  const detail = (await h.ok(h.admin, 'GET', '/cas/namespaces/panel/accounts/' + member.value.id)).value;
  h.check('Independent current CAS facts contain only original ordinary roles and no retired template binding',
    !bindings.some(b => b.status === 2 && b.sourceType === 'template' && b.sourceKey === group.key) &&
    detail.effectiveRoles?.length === ordinary.roleRefs.length && ordinary.roleRefs.every(ref => detail.effectiveRoles.some(role => role.module === ref.module && role.key === ref.key)), { bindings, roles: detail.effectiveRoles });
  c.outcome = 'confirmed'; h.persist();
}
async function dataCommand(h, actor, r, operation, allowed) {
  if (!['update', 'delete'].includes(operation) || actor.origin !== r.origin || r.commands.some(c => c.outcome === 'unknown') || r.actionCommands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original data/action command unresolved or origin changed; no matrix write replay');
  const actorIdentity = structuredClone(actor.identity), subject = actor.subject;
  const manager = await business.member(h, 'manager'), before = await business.record(h, manager, r);
  h.check('Data/action matrix starts from exact independently acknowledged original row and version', h.good(before) && String(before.data.value.id) === r.recordId && String(before.data.value.version) === r.version);
  const body = business.request(r, operation, operation === 'update' ? [{ name: 'sortOrder', value: before.data.value.sortOrder + 1 }] : []);
  const endpoint = '/apps/entity/value/write/' + operation + '/execute/?' + new URLSearchParams({ application: r.applicationKey, deploymentId: r.identity.deploymentId });
  const c = { body, actingIdentity: actorIdentity, subject, outcome: 'unknown' }; r.commands.push(c); h.persist();
  try { c.response = await h.api(actor, 'POST', endpoint, body); }
  catch (error) { c.transportError = error.message; }
  h.persist();
  h.check('Original data actor and subject remain unchanged before querying its durable receipt', same(actor.identity, actorIdentity) && actor.subject === subject && actor.origin === r.origin);
  c.query = await h.api(actor, 'POST', endpoint.replace('/execute/', '/receipt/'), body); h.persist();
  const after = await business.record(h, manager, r);
  h.check('Original data actor and subject remain unchanged through owner confirmation', same(actor.identity, actorIdentity) && actor.subject === subject && actor.origin === r.origin);
  if (allowed) {
    const receipt = c.query.data?.value;
    const rowMatches = operation === 'delete' ? [200, 404].includes(after.status) && after.data?.error?.code === 2 && after.data.value == null : h.good(after) && Number.isSafeInteger(Number(receipt?.version)) &&
      same(after.data.value, { ...before.data.value, sortOrder: body.fields[0].value, version: Number(receipt.version) });
    if (h.good(c.query) && business.receiptMatches(actor, body, receipt) && (!c.response || h.good(c.response) && same(c.response.data.value, receipt)) && rowMatches) {
      c.outcome = 'confirmed'; c.receipt = receipt; r.version = receipt.version; r.phase = operation === 'delete' ? 'delete-acknowledged' : 'created'; h.persist();
    }
  } else {
    h.check('Authorization refusal requires an actual original execute response', !!c.response, c);
    h.denied(c.response, 'Current original role cannot ' + operation + ' an enabled business entity');
    h.denied(c.query, 'Current original role cannot query a forbidden ' + operation + ' completion');
    if (h.good(after) && same(after.data.value, before.data.value)) { c.outcome = 'rejected-authority-and-unchanged'; h.persist(); }
  }
  h.check('Original reliable data command, receipt and independent full owner row agree with current role', c.outcome !== 'unknown', { command: c, after });
}
async function dataMatrix(h, f, context, ordinary, tag, rows) {
  const group = await h.create('/cas/namespaces/panel/role-templates/', { key: h.state.prefix + '-' + tag + '-data', name: '数据权限不隐含动作', subjectType: 'account', status: 2,
    roleRefs: structuredClone(ordinary.roleRefs), applicationAccess: [{ applicationUuid: context.identity.deploymentId, accessLevel: 'manager' }] }, 'role-template');
  const member = await authority.account(h, tag + '-data'), row = await create(h, context, f.application.id); rows.push(row); row.actionTemplateIds = [group.id]; h.persist();
  const denied = { code: 5, message: '当前用户角色未授予此实例的业务动作权限', queryRefused: true };
  for (const level of ['viewer', 'editor', 'manager']) {
    await authority.assign(h, member, group, [{ applicationUuid: context.identity.deploymentId, accessLevel: level }]);
    const current = await business.runtime(h, f, 0, member.actor);
    h.check('Current data-level capabilities and denied action projection agree with explicit CAS scope', current.ui.capabilities.get === true && current.ui.capabilities.update === (level !== 'viewer') && current.ui.capabilities.delete === (level === 'manager') && current.ui.businessActionStatus === 'denied' && !current.ui.businessActions, current.ui);
    const actual = await business.record(h, member.actor, row), independent = await business.record(h, await business.member(h, 'manager'), row);
    h.check('Original scoped data member independently reads the exact owner row', h.good(actual) && h.good(independent) && same(actual.data.value, independent.data.value));
    await command(h, member.actor, row, request(row), denied);
    await dataCommand(h, member.actor, row, 'update', level !== 'viewer');
    const deletion = await create(h, context, f.application.id); rows.push(deletion); deletion.actionTemplateIds = [group.id]; h.persist();
    await dataCommand(h, member.actor, deletion, 'delete', level === 'manager');
  }
  await revoke(h, member, group, ordinary);
  h.denied(await business.record(h, member.actor, row), 'Original no-access session loses business read after formal role retirement');
  await dataCommand(h, member.actor, row, 'update', false);
  await dataCommand(h, member.actor, row, 'delete', false);
  await command(h, member.actor, row, request(row), denied);
}
function exactActionRequest(value, origin, r, query = false) {
  try {
    const url = new URL(value.url()), expected = new URL('/api/v1/web/proxy' + route(r, query), origin), body = value.postDataJSON();
    return value.method() === 'POST' && url.origin === origin && url.pathname === expected.pathname && url.searchParams.size === 2 &&
      url.searchParams.getAll('application').length === 1 && url.searchParams.getAll('deploymentId').length === 1 &&
      url.searchParams.get('application') === r.applicationKey && url.searchParams.get('deploymentId') === r.identity.deploymentId &&
      same(body.identity, r.identity) && body.entity === r.entity && body.action === 'acknowledge' && body.id === r.recordId;
  } catch { return false; }
}
async function actionUI(h, actor, r) {
  const manager = await business.member(h, 'manager'), browser = actor.page;
  for (const width of [390, 1366, 1920]) {
    const target = new URL('/workbench/apps/' + encodeURIComponent(r.applicationKey), actor.origin);
    target.searchParams.set('source', 'portal'); target.searchParams.set('deploymentId', r.identity.deploymentId);
    await browser.setViewportSize({ width, height: width === 390 ? 844 : 1080 });
    await browser.goto(target.href, { waitUntil: 'networkidle' });
    await browser.locator('tbody tr[data-row-key="' + r.recordId + '"]').getByRole('button', { name: '业务操作', exact: true }).click();
    await browser.getByRole('combobox', { name: '业务动作', exact: true }).click();
    // Record the opened dropdown geometry before any click so a clipped or
    // unopened overlay is distinguishable from a product action failure.
    const dropdownDiagnostic = await browser.evaluate(() => {
      const combobox = document.querySelector('[role="combobox"]');
      const dropdown = document.querySelector('.ant-select-dropdown');
      const option = document.querySelector('.ant-select-item-option');
      const style = dropdown ? getComputedStyle(dropdown) : null;
      return {
        expanded: combobox?.getAttribute('aria-expanded'),
        dropdown: dropdown && style ? { rect: dropdown.getBoundingClientRect().toJSON(), display: style.display, visibility: style.visibility, overflow: style.overflow, zIndex: style.zIndex } : null,
        option: option ? { rect: option.getBoundingClientRect().toJSON(), display: getComputedStyle(option).display, visibility: getComputedStyle(option).visibility } : null,
      };
    });
    h.observe({ kind: 'business-action-dropdown-diagnostic', width, ...dropdownDiagnostic });
    await h.screenshot(actor, 'business-action-dropdown-' + width);
    // antd renders a hidden measurement option with the same accessible name;
    // the real, visible choice lives inside the non-hidden dropdown.
    await browser.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option', { hasText: 'acknowledge（open → acknowledged）' }).first().click();
    await browser.getByRole('textbox', { name: '动作参数 description', exact: true }).fill('真实界面动作 ' + width);
    await browser.getByRole('button', { name: '执行业务动作', exact: true }).isEnabled().then(enabled => h.check('Real action form is enabled for current exact role, row state and version', enabled));
    const size = await browser.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
    h.check('Real action panel keeps the document within its actual viewport', size.scroll <= size.viewport + 1, { width, ...size });
    await h.screenshot(actor, 'business-action-ready-' + width);
    // Inspect all widths with no dispatch. Exactly one real click below.
  }
  if (r.actionCommands.some(c => c.outcome === 'unknown') || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original UI action unresolved; no new click');
  const before = await business.record(h, manager, r), captured = [], pending = [];
  let dispatchError;
  h.check('Actual UI action starts from the exact current owner row and version', h.good(before) && String(before.data.value.id) === r.recordId && String(before.data.value.version) === r.version, before);
  const observe = response => {
    const req = response.request();
    if (!exactActionRequest(req, actor.origin, r) && !exactActionRequest(req, actor.origin, r, true)) return;
    const item = { body: req.postDataJSON(), queryOnly: exactActionRequest(req, actor.origin, r, true), status: response.status() }; captured.push(item);
    pending.push(response.json().then(data => { item.data = data; h.persist(); }).catch(error => { item.error = error.message; h.persist(); }));
  };
  const pattern = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/apps/entity/action/execute/';
  const intercept = async interception => {
    const req = interception.request();
    if (!exactActionRequest(req, actor.origin, r) || r.actionCommands.some(c => c.outcome === 'unknown')) { await interception.abort('blockedbyclient'); return; }
    const body = req.postDataJSON();
    try { h.check('Actual action form submits exact original row/version and explicit input once', body.expectedVersion === r.version && same(body.fields, [{ name: 'description', value: '真实界面动作 1920' }])); }
    catch (error) { dispatchError = error; await interception.abort('blockedbyclient'); return; }
    r.actionCommands.push({ body, actorIdentity: structuredClone(actor.identity), subject: actor.subject, outcome: 'unknown', source: 'actual-ui', observedResponses: captured }); h.persist();
    await interception.continue();
  };
  browser.on('response', observe); await browser.route(pattern, intercept);
  try {
    await browser.getByRole('button', { name: '执行业务动作', exact: true }).click();
    try { await browser.getByText('原业务动作已确认', { exact: true }).waitFor(); }
    catch (error) { throw dispatchError || error; }
    await Promise.all(pending);
    const c = r.actionCommands.at(-1);
    if (c?.source !== 'actual-ui' || c.outcome !== 'unknown') throw new h.Blocked('Real UI action has no exact original pre-dispatch journal');
    c.observedResponses = captured; c.query = await h.api(actor, 'POST', route(r, true), c.body); h.persist();
    const after = await business.record(h, manager, r), receipt = c.query.data?.value;
    if (h.good(before) && h.good(c.query) && receiptMatches(actor, c.body, receipt) && Number.isSafeInteger(Number(receipt.version)) &&
        captured.filter(v => !v.queryOnly).length === 1 && captured.some(v => v.queryOnly && v.status === 200 && same(v.data?.value, receipt)) &&
        h.good(after) && same(after.data.value, { ...before.data.value, name: receipt.state, version: Number(receipt.version), description: c.body.fields[0].value })) {
      c.outcome = 'confirmed'; c.receipt = receipt; r.version = receipt.version; h.persist();
    }
    h.check('Actual single-click action, consumer confirmation and independent complete owner row agree', c.outcome === 'confirmed', { command: c, after });
    h.check('Actual displayed operation ID equals the durable original owner receipt', await browser.getByTestId('business-action-operation-id').innerText() === receipt.operationId);
    await browser.getByRole('button', { name: '执行业务动作', exact: true }).isDisabled().then(disabled => h.check('Confirmed terminal state disables the same action in the real consumer', disabled));
    await h.screenshot(actor, 'business-action-confirmed');
  } finally { await browser.unroute(pattern, intercept); browser.off('response', observe); await Promise.all(pending); }
}
async function actions(h, tag) {
  const f = await pages.explicitFixture(h, configure, undefined, { suffix: tag, requestPrefix: tag + '-', prepareAuthor: prepare });
  const manager = await business.member(h, 'manager'), contexts = [await business.runtime(h, f, 0, manager), await business.runtime(h, f, 1, manager)];
  const rows = []; let primary;
  try {
    h.check('Frozen action is declared while ordinary data manager receives denied action projection', f.revision.entities[0].writeRules.actions[0].key === 'acknowledge' && contexts.every(c => c.ui.businessActionStatus === 'denied' && !c.ui.businessActions));
    for (const context of contexts) rows.push(await create(h, context, f.application.id));
    const r = rows[0], peer = rows[1], denied = { code: 5, message: '当前用户角色未授予此实例的业务动作权限', queryRefused: true };
    await command(h, manager, r, request(r), denied);
    const ordinary = (await h.directory(h.admin, '/cas/namespaces/panel/role-templates/')).filter(t => t.key === 'portal-basic-user' && t.systemManaged && t.status === 2 && t.subjectType === 'account');
    const roleKey = 'entity-action-' + hash('/apps/entity-actions' + r.entity + '/acknowledge'), owner = '/applications/' + r.identity.deploymentId;
    const roles = (await h.directory(h.admin, '/cas/namespaces/panel/roles/')).filter(t => t.module === owner && t.key === roleKey && t.status === 2);
    h.check('CAS contains exactly one built-in frozen exact instance action role and ordinary functional profile', roles.length === 1 && ordinary.length === 1 && ordinary[0].roleRefs.length > 0, roles);
    await dataMatrix(h, f, contexts[0], ordinary[0], tag, rows);
    const group = await h.create('/cas/namespaces/panel/role-templates/', { key: h.state.prefix + '-' + tag, name: '仅精确业务动作', subjectType: 'account', status: 2,
      roleRefs: [...structuredClone(ordinary[0].roleRefs), { module: owner, key: roleKey }], applicationAccess: [] }, 'role-template');
    const member = await authority.account(h, tag); r.actionTemplateId = group.id; peer.actionTemplateId = group.id; h.persist();
    await authority.assign(h, member, group, []);
    h.denied(await business.record(h, member.actor, r), 'Only-action role grants no ordinary business read access');
    h.denied(await business.record(h, member.actor, peer), 'Only-action role grants no peer business read access');
    await dataCommand(h, member.actor, r, 'update', false); await dataCommand(h, member.actor, r, 'delete', false);
    await command(h, member.actor, peer, request(peer), denied);
    await command(h, member.actor, r, request(r, { action: 'ungranted-action' }), denied);
    for (const field of ['generation', 'executionEpoch', 'installationId', 'runtimeApplicationUuid', 'artifactDigest']) {
      const identity = structuredClone(r.identity);
      identity[field] = field === 'installationId' ? String(BigInt(identity[field]) + 1n) : field === 'artifactDigest' ? 'sha256:' + (identity[field].slice(-1) === 'a' ? 'b' : 'a').repeat(64) : typeof identity[field] === 'number' ? identity[field] + 1 : identity[field] + '-peer';
      await command(h, member.actor, r, request(r, { identity }), { code: 19, message: '精确安装读取身份已变化', queryRefused: true });
    }
    await business.execute(h, manager, r, business.request(r, 'update', [{ name: 'sortOrder', value: 1 }]));
    await command(h, member.actor, r, request(r, { expectedVersion: '1' }), { code: 19, message: '资源版本冲突' });
    const body = request(r), receipt = await command(h, member.actor, r, body);
    const stable = await command(h, member.actor, r, body);
    h.check('Confirmed identical action replay returns exact original durable receipt without another version advance', same(stable, receipt));
    await command(h, member.actor, r, { ...structuredClone(body), fields: [{ name: 'description', value: 'conflicting input' }] },
      { code: 21, message: '原动作身份或输入不匹配', queryRefused: true });
    h.check('Conflicting input preserves the exact original durable action receipt', same((await h.ok(member.actor, 'POST', route(r, true), body)).value, receipt));
    await command(h, member.actor, r, request(r), { code: 21, message: '动作状态前置条件不满足' });
    h.check('Peer installation complete original row survives all original instance operations', same((await business.record(h, manager, peer)).data.value, peer.created));
    const uiGroup = await h.create('/cas/namespaces/panel/role-templates/', { key: h.state.prefix + '-' + tag + '-ui', name: '动作及精确实例查看', subjectType: 'account', status: 2,
      roleRefs: structuredClone(group.roleRefs), applicationAccess: [{ applicationUuid: r.identity.deploymentId, accessLevel: 'viewer' }] }, 'role-template');
    const uiRow = await create(h, contexts[0], f.application.id); rows.push(uiRow);
    for (const row of rows) { (row.actionTemplateIds ||= []).push(group.id, uiGroup.id); } h.persist();
    await authority.assign(h, member, uiGroup, uiGroup.applicationAccess);
    const projected = await business.runtime(h, f, 0, member.actor);
    h.check('Current reader with explicit action role receives exactly the frozen action form projection', projected.ui.businessActionStatus === 'available' &&
      same(projected.ui.businessActions, { versionField: 'version', stateField: 'name', actions: [{ key: 'acknowledge', from: 'open', to: 'acknowledged', fields: [{ name: 'description', type: 'string', nullable: true }] }] }), projected.ui.businessActions);
    await actionUI(h, member.actor, uiRow);
    await revoke(h, member, uiGroup, ordinary[0]);
    await command(h, member.actor, r, body, denied);
    await command(h, member.actor, uiRow, request(uiRow), denied);
    h.denied(await business.record(h, member.actor, uiRow), 'Original retired action-reader session loses ordinary data access');
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const open = h.state.resources.filter(r => r.kind === 'business-record' && r.phase !== 'deleted' && r.identity?.installationId && f.installations.some(i => String(i.id) === r.identity.installationId));
    if (open.length) {
      h.observe({ kind: 'business-action-original-cleanup-open', count: open.length, reason: 'Keep exact original row/actor/template/installation; primary failure retained' });
      if (!primary) throw new h.Blocked('Original business action disposition unresolved; retain installation');
    } else { await retireCaseTemplates(h, tag); await pages.disposeExplicitFixture(h, f, primary); }
  }
  await h.partial('Frozen action API, data-level and only-action separation, original-session retirement, three-width real action form/single-click receipt/terminal UI, dual-instance refusal and exact receipt/replay/input conflict/stale-version/state guard supported subset completed. Endpoint/cross-tenant/other-action/expired-installation and full lifecycle matrix remain unverified.');
}
const normal = h => actions(h, 'actionnormal'), authorization = h => actions(h, 'actionauthority');
normal.transport = authorization.transport = 'owner-api';
module.exports = { handlers: { 'F070-001': normal, 'F070-002': authorization }, route, request, inputDigest, receiptMatches, refused, routeDenied, guardCleanup, command, configure, exactActionRequest, dataCommand, revoke };

// The installation destroy fence refuses while a user-owned template still
// references application roles. This case owns those templates, so it must
// retire them (after its assignments are revoked) before the destroy step.
async function retireCaseTemplates(h, tag) {
  const rows = await h.directory(h.admin, '/cas/namespaces/panel/role-templates/');
  const exactPrefix = h.state.prefix + '-' + tag;
  for (const template of rows.filter(t => t && !t.systemManaged && typeof t.key === 'string' &&
    (t.key === exactPrefix || t.key.startsWith(exactPrefix + '-')))) {
    const response = await h.api(h.admin, 'DELETE', '/cas/namespaces/panel/role-templates/' + template.id);
    if (!h.good(response)) throw new h.Blocked('Original user-owned template retirement failed before installation destroy: ' + template.key);
  }
}
