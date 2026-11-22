const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const probes = require('./scenario_commands.cjs');
const { PORTAL_BASIC_KEYS, portalBasicProfileSet } = require('./platform_profiles.cjs');
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
  const configure = mode === 'relations' ? content => {
    const records = content.dataSources.find(s => s.key === 'records');
    records.fields = [...new Set([...(records.fields || []), 'target', 'targets'])];
    records.pagination = { ...(records.pagination || { mode: 'cursor', defaultPageSize: 10 }), maxPageSize: 50 };
  } : undefined;
  const f = await pages.explicitFixture(h, configure, undefined, { suffix, requestPrefix: suffix + '-', prepareAuthor: (h, authored) => prepare(h, authored, mode), buildEntityViews: inputViews });
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
    const seed = structuredClone(originalUI), rels = [];
    for (const f of entity.fields) {
      const relType = f.type?.elemType || f.type;
      if (relType?.pkgPath) rels.push({
        field: f.name, targetEntity: relType.pkgPath + '/' + relType.name,
        multiple: !!f.type?.elemType, mode: 'reference', valueField: 'id', labelField: 'name', readonly: false,
      });
      if (!seed.fields.some(v => v.name === f.name)) {
        const type = { boolean: 'boolean', float64: 'number', datetime: 'string' }[f.type?.name] || (f.type?.elemType ? 'array' : 'object');
        seed.fields.push({ name: f.name, type, required: false, readonly: false, searchable: false, sortable: false,
          ...(f.type?.name === 'datetime' ? { format: 'date-time' } : {}) });
      }
    }
    const view = pages.explicitView(entity, seed);
    if (rels.length) view.relations = rels;
    result[entity.pkgPath + '/' + entity.name] = view;
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
  const { authoring: author } = require('./authoring_cases.cjs');
  const page = require('./page_runtime_cases.cjs');
  const scalarFields = ['id', 'code', 'name', 'description', 'sortOrder', 'version', 'flag', 'amount', 'occurredAt'];
  const editFields = ['code', 'name', 'description', 'sortOrder', 'flag', 'amount', 'occurredAt'];
  const formFields = ['code', 'name', 'description', 'sortOrder', 'flag', 'amount', 'occurredAt'];
  let scalarEntityKey;
  const f = await page.explicitFixture(h, (content, entity) => {
    scalarEntityKey = entity;
    const records = content.dataSources.find(s => s.key === 'records');
    records.fields = [...scalarFields];
    const table = content.pages[0].components.find(c => c.key === 'records');
    table.properties.columns = [...editFields, 'id'];
    content.actions = { sample: ['create'] };
    content.navigation.push('editor');
    content.pages.push({
      key: 'editor',
      title: '标量表单',
      routes: ['/records/new'],
      navigation: true,
      layout: { type: 'grouped-form', columns: 12, gap: 16 },
      routeParameters: [],
      components: [{
        key: 'scalar-form',
        type: 'entity-form',
        layout: { span: 12, order: 0 },
        dataSources: [],
        properties: { entity, mode: 'create', sections: [{ title: '全标量字段', fields: formFields }] },
      }],
    });
  }, undefined, {
    suffix: 'scalartypes',
    requestPrefix: 'scalartypes-',
    prepareAuthor: async (h, authored) => {
      const current = await author.draft(h, authored.app);
      authored.model = await author.save(h, authored.app, current, modelEntities(current.entities[0], 'types'));
      authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
    },
    buildEntityViews: inputViews,
  });
  const actor = await business.member(h, 'manager');
  const contexts = await Promise.all([0, 1].map(i => business.runtime(h, f, i, actor)));
  const rows = [];
  let primary;
  try {
    const view = f.revision.content.pages.entityViews[scalarEntityKey];
    const fieldTypes = Object.fromEntries(f.revision.entities[0].fields.map(v => [v.name, v.type.name]));
    const uiTypes = Object.fromEntries(view.fields.map(v => [v.name, v.format || v.type]));
    h.check('Full supported scalar inventory covers integer, exact string, boolean, float and UTC date-time declarations',
      fieldTypes.id === 'int64' && fieldTypes.sortOrder === 'int64' && fieldTypes.code === 'string' &&
      fieldTypes.flag === 'boolean' && fieldTypes.amount === 'float64' && fieldTypes.occurredAt === 'datetime' &&
      uiTypes.sortOrder === 'integer' && uiTypes.flag === 'boolean' && uiTypes.amount === 'number' && uiTypes.occurredAt === 'date-time',
      { fieldTypes, uiTypes });

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

    // Real form UI create + boundary raw int64 encoding beyond JS safe integer range.
    const browser = actor.page, bigToken = '9007199254740993';
    const editorUrl = new URL('/workbench/apps/' + encodeURIComponent(f.application.name), actor.origin);
    for (const [k, v] of Object.entries({ source: 'portal', deploymentId: contexts[0].identity.deploymentId, pageKey: 'editor' })) editorUrl.searchParams.set(k, v);
    await browser.setViewportSize({ width: 1440, height: 900 });
    await browser.goto(editorUrl.href, { waitUntil: 'networkidle' });
    const uiCode = 'RG-INT64-' + crypto.randomBytes(4).toString('hex').toUpperCase();
    await browser.getByRole('textbox', { name: '写入字段 code', exact: true }).fill(uiCode);
    await browser.getByRole('textbox', { name: '写入字段 name', exact: true }).fill('大整数界面样本 ' + h.state.prefix);
    await browser.getByRole('textbox', { name: '写入字段 sortOrder', exact: true }).fill(bigToken);
    await browser.getByRole('combobox', { name: '写入字段 flag', exact: true }).click();
    await browser.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: /^是$/ }).click();
    await browser.getByRole('textbox', { name: '写入字段 amount', exact: true }).fill('12.5');
    await browser.getByRole('textbox', { name: '写入字段 occurredAt', exact: true }).fill('2026-01-02T03:04:05.006Z');
    let submittedWire = '';
    const watchWrite = req => {
      const u = new URL(req.url());
      if (req.method() === 'POST' && u.pathname === '/api/v1/web/proxy/apps/entity/value/write/create/execute/') submittedWire = req.postData() || '';
    };
    browser.on('request', watchWrite);
    await browser.getByRole('button', { name: '创建记录', exact: true }).click();
    await browser.getByText('原业务写入已确认', { exact: true }).waitFor();
    browser.off('request', watchWrite);
    const receiptText = await browser.getByTestId('business-write-operation-id').innerText();
    const uiRecordId = receiptText.match(/记录：([1-9][0-9]*)/)?.[1];
    h.check('Form UI sends unrounded 64-bit integer wire token and exact boolean without JS precision loss',
      !!uiRecordId && submittedWire.includes('"value":' + bigToken) && submittedWire.includes('"name":"flag","value":true'), { submittedWire, receiptText });
    const uiRow = { kind: 'business-record', actorRole: 'manager', phase: 'created', ...contexts[0], origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [], recordId: uiRecordId, version: '1' };
    delete uiRow.ui; h.state.resources.push(uiRow); rows.push(uiRow); h.persist();
    const uiOwner = await business.record(h, actor, uiRow);
    h.check('Independent business owner confirms UI-created boolean flag true',
      h.good(uiOwner) && uiOwner.data.value.flag === true && uiOwner.data.value.amount === 12.5, uiOwner);

    // Verify exact int64 boundary tokens (-2^63, 2^63-1) and lossless frozen page projection.
    const meta = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + encodeURIComponent(f.application.name) + '?deploymentId=' + contexts[0].identity.deploymentId)).value;
    contexts[0].pageDigest = meta.installation.pageDigest;
    const pageRead = await page.sourceRead(h, actor, contexts[0], { sourceKey: 'records', pageSize: 10 });
    const uiProj = (pageRead.data.value?.value?.rows || []).find(row => row.fields.find(fld => fld.key === 'id')?.value?.number === uiRecordId);
    const sortProj = uiProj?.fields.find(fld => fld.key === 'sortOrder')?.value;
    h.check('Frozen page projection encodes exact unsafe 64-bit integer token cleanly', h.good(pageRead) && sortProj?.kind === 'integer' && sortProj.number === bigToken, sortProj);

    const homeUrl = new URL('/workbench/apps/' + encodeURIComponent(f.application.name), actor.origin);
    for (const [k, v] of Object.entries({ source: 'portal', deploymentId: contexts[0].identity.deploymentId, pageKey: 'home' })) homeUrl.searchParams.set(k, v);
    await browser.goto(homeUrl.href, { waitUntil: 'networkidle' });
    await browser.locator('tbody tr[data-row-key="' + uiRecordId + '"]').waitFor();
    const rowText = await browser.locator('tbody tr[data-row-key="' + uiRecordId + '"]').innerText();
    h.check('Rendered frozen table displays exact 64-bit integer, boolean, decimal and null markers accurately',
      rowText.includes(bigToken) && rowText.includes('12.5') && rowText.includes(uiCode) && /\btrue\b|是/.test(rowText), rowText);

    // Also probe -2^63 and 2^63-1 over exact raw JSON body in same browser session.
    for (const boundary of ['-9223372036854775808', '9223372036854775807']) {
      const req = business.request(uiRow, 'update', [{ name: 'sortOrder', value: '__BIG__' }]);
      const rawBody = JSON.stringify(req).replace('"__BIG__"', boundary);
      const res = await browser.evaluate(async ({ url, body }) => {
        const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, credentials: 'include' });
        return { status: resp.status, text: await resp.text() };
      }, { url: '/api/v1/web/proxy' + business.route(uiRow, 'update', false), body: rawBody });
      const parsed = JSON.parse(res.text);
      h.check('Boundary signed int64 update succeeds: ' + boundary, res.status === 200 && !parsed.error && parsed.value?.version, parsed);
      uiRow.version = parsed.value.version;
      const checkPage = await page.sourceRead(h, actor, contexts[0], { sourceKey: 'records', pageSize: 10 });
      const checkRow = (checkPage.data.value?.value?.rows || []).find(row => row.fields.find(fld => fld.key === 'id')?.value?.number === uiRecordId);
      h.check('Frozen page projection returns exact signed int64 boundary token: ' + boundary, checkRow?.fields.find(fld => fld.key === 'sortOrder')?.value?.number === boundary, checkRow);
    }
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const idsSet = new Set(f.installations.map(v => String(v.id)));
    if (h.state.resources.some(r => r.kind === 'business-record' && idsSet.has(r.identity?.installationId) && r.phase !== 'deleted')) {
      if (!primary) throw new h.Blocked('Scalar type business record cleanup incomplete; preserve installation');
    } else await page.disposeExplicitFixture(h, f, primary);
  }
}
async function withFormRelationsFixture(h, run) {
  const { authoring: author } = require('./authoring_cases.cjs'), page = require('./page_runtime_cases.cjs');
  const formFields = ['code', 'name', 'description', 'target'];
  const f = await page.explicitFixture(h, (content, entity) => {
    const targetKey = entity.replace(/\/[^/]+$/, '/zzRelationTarget');
    content.actions = { sample: ['create'] };
    const records = content.dataSources.find(s => s.key === 'records');
    records.fields = [...new Set([...(records.fields || []), 'target', 'targets'])];
    records.pagination = { ...(records.pagination || { mode: 'cursor', defaultPageSize: 10 }), maxPageSize: 50 };
    content.dataSources.push({
      key: 'targetChoices', entity: targetKey, mode: 'options', fields: ['id', 'name'],
      authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation',
      pagination: { mode: 'cursor', defaultPageSize: 20, maxPageSize: 100 }, orderBy: [{ field: 'id', direction: 'asc' }],
    });
    content.navigation.push('editor');
    content.pages.push({
      key: 'editor', title: '关系表单', routes: ['/relations/new'], navigation: true,
      layout: { type: 'grouped-form', columns: 12, gap: 16 }, routeParameters: [],
      components: [{
        key: 'relation-form', type: 'entity-form', layout: { span: 12, order: 0 }, dataSources: ['targetChoices'],
        properties: { entity, mode: 'create', sections: [{ title: '关联输入', fields: formFields }] },
      }],
    });
  }, undefined, {
    suffix: 'relationsforms',
    requestPrefix: 'relationsforms-',
    prepareAuthor: async (h, authored) => {
      const current = await author.draft(h, authored.app);
      authored.model = await author.save(h, authored.app, current, modelEntities(current.entities[0], 'relations'));
      authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
    },
    buildEntityViews: inputViews,
  });
  const actor = await business.member(h, 'manager');
  const contexts = await Promise.all([0, 1].map(i => business.runtime(h, f, i, actor)));
  const rows = []; let primary;
  try { await run({ f, actor, contexts, rows }); }
  catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const idsSet = new Set(f.installations.map(v => String(v.id)));
    if (h.state.resources.some(r => r.kind === 'business-record' && idsSet.has(r.identity?.installationId) && r.phase !== 'deleted')) {
      if (!primary) throw new h.Blocked('Relations form business record cleanup incomplete; preserve installation');
    } else await page.disposeExplicitFixture(h, f, primary);
  }
}
async function tenantIsolationCheck(h, f, actor, host, target, peer, targetKey) {
  if (!h.tenantAdmin) throw new h.Blocked('Cross-tenant relation isolation requires tenantAdmin actor');
  const { packageContent, packageUpload } = require('./owner_transport.cjs');
  const ns = h.tenantAdmin.identity.namespace;
  const zip = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
  h.check('Download original model ZIP for cross-tenant import', zip.status === 200 && Buffer.isBuffer(zip.data.bytes));
  const up = await packageUpload(h.tenantAdmin, { name: h.state.prefix + '-iso-tenant.zip', bytes: zip.data.bytes }, h.observe);
  h.check('Other tenant uploads model ZIP cleanly', h.good(up) && !!up.data?.value?.uploadRef, up);
  const imp = await h.ok(h.tenantAdmin, 'POST', '/panel/application/model-packages/imports/', { uploadRef: up.data.value.uploadRef });
  const tPkg = imp.value;
  let tInstall, tMember, tTemplate, tAccount, tRow;
  try {
    const req = (await h.ok(h.tenantAdmin, 'POST', '/panel/application/deployment-requests/', {
      sourceKind: 'model-package', packageId: tPkg.id, expectedDigest: tPkg.artifactDigest,
      instanceKey: h.state.prefix + '-isotenant', instanceName: '跨租户隔离验证',
      storageProvisioning: { mode: 'allocate' }, reason: 'F014-002 cross-tenant relation check',
    })).value;
    const ops = '/panel/operations/namespaces/' + ns + '/application-deployment-requests/' + req.id;
    const opts = (await h.ok(h.admin, 'GET', ops + '/runtime-options')).values;
    const approved = (await h.ok(h.admin, 'POST', ops + '/approve', {
      expectedVersion: req.version, reason: 'Approve cross-tenant isolation probe',
      runtimePlacement: { executionInstanceId: opts.find(v => v.kind === 'base').id, gatewayInstanceId: opts.find(v => v.kind === 'gateway').id },
    })).value;
    let op;
    for (let i = 0; i < 120; i++) {
      op = (await h.ok(h.admin, 'GET', '/panel/operations/namespaces/' + ns + '/application-deployment-operations/' + approved.operationId)).value;
      if (['succeeded', 'failed', 'cancelled'].includes(op.status)) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    h.check('Other-tenant installation succeeds cleanly', op?.status === 'succeeded', op);
    tInstall = (await h.directory(h.tenantAdmin, '/panel/application/installations/')).find(v => v.deploymentId === req.deploymentId);
    h.check('Other-tenant installation is ready', tInstall?.status === 'ready', tInstall);
    const tplPrefix = '/cas/namespaces/' + ns + '/';
    const basicTpl = portalBasicProfileSet(await h.directory(h.tenantAdmin, tplPrefix + 'role-templates/'));
    h.check('Tenant namespace exposes built-in user role-templates', basicTpl.complete);
    tTemplate = await h.createAs('tenantAdmin', tplPrefix + 'role-templates/', {
      key: h.state.prefix + '-isotenant-mgr', name: '跨租户隔离成员', scene: 'usage', subjectType: 'account', status: 2,
      roleRefs: structuredClone(basicTpl.roleRefs), applicationAccess: [{ applicationUuid: tInstall.deploymentId, accessLevel: 'manager' }],
    }, 'role-template');
    tAccount = await h.createAs('tenantAdmin', tplPrefix + 'accounts/', {
      account: h.state.prefix + '-iso-member', displayName: '跨租户成员', password: h.state.password,
      status: 2, roleTemplateKeys: [...PORTAL_BASIC_KEYS, tTemplate.key],
    }, 'account');
    await h.ok(h.tenantAdmin, 'PUT', tplPrefix + 'accounts/' + tAccount.id + '/role-templates', {
      roleTemplateKeys: [...PORTAL_BASIC_KEYS, tTemplate.key],
      applicationScopes: [{ templateKey: tTemplate.key, applicationAccess: [{ applicationUuid: tInstall.deploymentId, accessLevel: 'manager' }] }],
    });
    tMember = await h.login(tAccount.account, h.state.password, ns, h.state.password + '-tm');
    const tSession = (await h.ok(tMember, 'GET', '/api/v1/web/session/')).value;
    tMember.subject = tSession.homeNamespace + '/account:' + tAccount.id;
    const tMeta = (await h.ok(tMember, 'GET', '/apps/application/runtimes/' + tPkg.applicationKey + '?deploymentId=' + tInstall.deploymentId)).value;
    const tCtx = { applicationKey: tPkg.applicationKey, entity: targetKey, identity: tMeta.readIdentity, ui: tMeta.entities.find(e => e.entity?.pkgPath + '/' + e.entity?.name === targetKey) };
    tRow = { kind: 'business-record', actorRole: 'tenant-iso', phase: 'intent', ...tCtx, origin: tMember.origin, actorIdentity: structuredClone(tMember.identity), commands: [] };
    delete tRow.ui;
    const tCreate = business.request(tRow, 'create', [{ name: 'code', value: 'RG-' + crypto.randomBytes(6).toString('hex').toUpperCase() }, { name: 'name', value: '跨租户目标' }, { name: 'description', value: null }, { name: 'sortOrder', value: 0 }]);
    const tAck = await h.api(tMember, 'POST', business.route(tRow, 'create', false), tCreate);
    h.check('Other-tenant target record created for cross-tenant rejection check', h.good(tAck) && !!tAck.data?.value?.id, tAck);
    tRow.recordId = tAck.data.value.id; tRow.version = tAck.data.value.version; tRow.phase = 'created';
    await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'target', reference: { id: tRow.recordId } }]), { code: 2, messagePattern: '.+' }, [host, target, peer]);
  } finally {
    if (tRow?.recordId && tMember) await h.api(tMember, 'POST', business.route(tRow, 'delete', false), business.request(tRow, 'delete')).catch(() => {});
    if (tInstall) {
      const fresh = (await h.api(h.tenantAdmin, 'GET', '/panel/application/installations/' + tInstall.id)).data?.value || tInstall;
      const unRes = await h.api(h.tenantAdmin, 'POST', '/panel/application/installations/' + fresh.id + '/uninstall', {
        expectedUpdateTime: fresh.updateTime, expectedDigest: fresh.sourceDigest,
        reason: 'F014-002 cleanup', dataDisposition: 'destroy', confirmation: fresh.applicationKey,
      });
      const schemaId = unRes.data?.value?.receipt?.database?.schemaResourceId || fresh.receipt?.database?.schemaResourceId;
      if (schemaId) {
        const purgeRoute = '/panel/operations/namespaces/' + ns + '/database-schemas/' + schemaId + '/purge';
        const pre = (await h.api(h.admin, 'GET', purgeRoute)).data?.value;
        if (pre?.eligible) await h.api(h.admin, 'POST', purgeRoute, { expectedResourceVersion: pre.expectedResourceVersion, reason: 'F014-002 cleanup', confirmation: pre.confirmation }).catch(() => {});
      }
    }
    if (tPkg) await h.api(h.tenantAdmin, 'DELETE', '/panel/application/model-packages/' + tPkg.id).catch(() => {});
  }
}
async function references(h, mode) {
  const runner = mode === 'forms' ? withFormRelationsFixture : (h, fn) => withFixture(h, 'relations' + mode, 'relations', fn);
  await runner(h, async ({ f, actor, contexts, rows }) => {
    const targetEntity = f.revision.entities.find(e => e.name === 'zzRelationTarget');
    h.check('Frozen publication contains exact declared target and host single/collection pointer types', !!targetEntity && f.revision.entities[0].fields.some(v => v.name === 'targets' && v.type.elemType?.isPtr));
    const targetKey = targetEntity.pkgPath + '/' + targetEntity.name;
    const target = await create(h, f, actor, contexts[0], rows, [], targetKey), peer = await create(h, f, actor, contexts[1], rows, [], targetKey);
    const host = await create(h, f, actor, contexts[0], rows, [{ name: 'target', reference: { id: target.recordId } }, { name: 'targets', references: [{ id: target.recordId }] }]);
    h.check('Independent runtime owner resolves original single and collection references only to exact same-installation target', same(ids(host.created.target), [target.recordId]) && same(ids(host.created.targets), [target.recordId]));
    if (mode === 'isolation') {
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'target', reference: { id: peer.recordId } }]), { code: 2, messagePattern: '.+' }, [host, target, peer]);
      const otherApp = await require('./delivery_cases.cjs').fixture(h);
      const otherCtx = await business.runtime(h, otherApp, 0, actor);
      const otherRow = await business.create(h, otherCtx, 'iso-otherapp');
      try {
        await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'target', reference: { id: otherRow.recordId } }]), { code: 2, messagePattern: '.+' }, [host, target, peer]);
      } finally { await business.finishCleanup(h, [otherRow]); }
      await tenantIsolationCheck(h, f, actor, host, target, peer, targetKey);
    } else if (mode === 'boundaries') {
      await rejectedWrite(h, actor, target, business.request(target, 'delete'), { code: 21, messagePattern: '^记录仍被引用，禁止删除$' }, [host, target, peer]);
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

      // Exact 128 vs 129 fields boundary.
      await rejectedWrite(h, actor, host, business.request(host, 'update', Array.from({ length: 129 }, (_, i) => ({ name: 'f' + i, value: 'x' }))),
        { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' }, [host, target, peer]);
      await rejectedWrite(h, actor, host, business.request(host, 'update', Array.from({ length: 128 }, (_, i) => ({ name: 'f' + i, value: 'x' }))),
        { code: 21, messagePattern: '^写入字段未声明、不可写或不是单值: f0$' }, [host, target, peer]);

      // Exact 48KiB (49152 vs 49153 bytes) field budget boundary.
      // bytes = len("description")(11) + len(JSON("\"a...\"")) = 11 + 2 + N = 49152 => N = 49139
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'description', value: 'a'.repeat(49140) }]),
        { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' }, [host, target, peer]);
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'description', value: 'a'.repeat(49139) }]),
        { code: 21, messagePattern: '^写入标量类型或约束无效: description$' }, [host, target, peer]);

      // Exact 1024 vs 1025 sorted reference count boundary.
      const mkIds = n => Array.from({ length: n }, (_, i) => ({ id: String(100000 + i) }));
      await rejectedWrite(h, actor, host, business.request(host, 'create', [{ name: 'targets', references: mkIds(1025) }]),
        { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' }, [host, target, peer]);
      await rejectedWrite(h, actor, host, business.request(host, 'create', [{ name: 'code', value: 'RG-REF1024' }, { name: 'name', value: 'ref1024' }, { name: 'targets', references: mkIds(1024) }]),
        { code: 2, messagePattern: '.+' }, [host, target, peer]);

      // Multi-field failed-batch atomicity: valid target/targets + invalid description commits zero rows.
      const beforeRows = await require('./business_collection_cases.cjs').collection(h, actor, contexts[0]);
      await rejectedWrite(h, actor, host, business.request(host, 'create', [
        { name: 'code', value: 'RG-ATOMIC-' + crypto.randomBytes(4).toString('hex').toUpperCase() },
        { name: 'name', value: '失败原子性样本' },
        { name: 'description', value: 'x'.repeat(2001) },
        { name: 'target', reference: { id: target.recordId } },
        { name: 'targets', references: [{ id: target.recordId }] },
      ]), { code: 21, messagePattern: '^写入标量类型或约束无效: description$' }, [host, target, peer]);
      h.check('Failed multi-field create leaves host collection completely unchanged',
        same(await require('./business_collection_cases.cjs').collection(h, actor, contexts[0]), beforeRows));

      // Actual Form UI create round-trip via FrozenEntityForm / PageReferenceSetInput.
      const browser = actor.page, formUrl = new URL('/workbench/apps/' + encodeURIComponent(f.application.name), actor.origin);
      for (const [k, v] of Object.entries({ source: 'portal', deploymentId: contexts[0].identity.deploymentId, pageKey: 'editor' })) formUrl.searchParams.set(k, v);
      await browser.setViewportSize({ width: 1440, height: 900 });
      await browser.goto(formUrl.href, { waitUntil: 'networkidle' });
      const uiCode = 'RG-UIFORM-' + crypto.randomBytes(4).toString('hex').toUpperCase();
      await browser.getByRole('textbox', { name: '写入字段 code', exact: true }).fill(uiCode);
      await browser.getByRole('textbox', { name: '写入字段 name', exact: true }).fill('关系表单UI样本 ' + h.state.prefix);
      await browser.getByRole('combobox', { name: '写入字段 target', exact: true }).click();
      await browser.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option', { hasText: target.created.name }).first().click();
      await browser.getByRole('button', { name: '创建记录', exact: true }).click();
      await browser.getByText('原业务写入已确认', { exact: true }).waitFor();
      const uiRecordId = (await browser.getByTestId('business-write-operation-id').innerText()).match(/记录：([1-9][0-9]*)/)?.[1];
      h.check('Actual form UI commits single-reference record cleanly', !!uiRecordId);
      const uiRow = { kind: 'business-record', actorRole: 'manager', phase: 'created', ...contexts[0], origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [], recordId: uiRecordId, version: '1' };
      delete uiRow.ui; h.state.resources.push(uiRow); rows.push(uiRow); h.persist();
      const fetched = (await business.record(h, actor, uiRow)).data.value;
      h.check('Independent owner confirms form-created single-reference link',
        fetched.code === uiCode && same(ids(fetched.target), [target.recordId]), fetched);
    } else {
      await rejectedWrite(h, actor, target, business.request(target, 'delete'), { code: 21, messagePattern: '^记录仍被引用，禁止删除$' }, [host, target, peer]);
      await rejectedWrite(h, actor, host, business.request(host, 'update', [{ name: 'targets', references: [] }]), { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' }, [host, target, peer]);
      await business.execute(h, actor, host, business.request(host, 'update', [{ name: 'target', value: null }]));
      h.check('Single relation clears without deleting independent target', (await business.record(h, actor, host)).data.value.target == null && same((await business.record(h, actor, target)).data.value, target.created));
      await business.execute(h, actor, host, business.request(host, 'delete'));
      await business.execute(h, actor, target, business.request(target, 'delete'));
      h.check('After deleting incoming referrer host, independent target deletion succeeds cleanly',
        (await business.record(h, actor, host)).data.value == null && (await business.record(h, actor, target)).data.value == null);
    }
    h.check('Original peer target remains exactly unchanged', same((await business.record(h, actor, peer)).data.value, peer.created));
  });
  if (mode === 'boundaries') await relationGraphBoundaries(h);
  if (mode === 'basic' || mode === 'boundaries') {
    h.observe({
      kind: 'v1-contract-boundary-aligned',
      caseId: mode === 'basic' ? 'F014-001' : 'F014-003',
      excluded: 'Owned nested write objects remain excluded by initial writeRules contract [B].',
    });
  }
}
async function relationGraphBoundaries(h) {
  const app = await a.definition(h, 'relgraph'), before = await a.draft(h, app);
  const hostBase = () => structuredClone(a.newEntity(h, app));
  const targetBase = () => { const e = hostBase(); e.name = 'zzGraphTarget'; e.showName = '图目标'; return e; };
  const route = definitions + app.id + '/model-draft';
  const invalidDrafts = [
    () => { const n = hostBase(); n.fields.push(relation('selfOwned', n, false, true)); return [n]; },
    () => { const n = hostBase(); n.fields.push(relation('selfRefs', n, true, false)); return [n]; },
    () => { const x = hostBase(), y = targetBase(); x.fields.push(relation('t', y, false, false)); y.fields.push(relation('h', x, false, false)); return [x, y]; },
    () => { const x = hostBase(), y = targetBase(); x.fields.push(relation('t', y, false, false)); y.fields.push(relation('h', x, false, true)); return [x, y]; },
    () => { const x = hostBase(), y = targetBase(); y.fields = y.fields.map(f => ({ ...f, spec: { ...f.spec, primaryKey: false } })); x.fields.push(relation('t', y, false, false)); return [x, y]; },
    () => { const x = hostBase(), y = targetBase(); y.pkgPath = '/foreignpkg'; x.fields.push(relation('t', y, false, false)); return [x, y]; },
  ];
  for (const buildEntities of invalidDrafts) {
    const res = await h.api(h.admin, 'PUT', route, a.command(before, buildEntities()));
    h.check('Invalid author relation graph is explicitly refused without saving draft',
      !h.good(res) && [4, 18, 21].includes(res.data?.error?.code) && res.data.value == null, res);
  }
  h.check('Rejected relation graph probes leave author draft unchanged', same(await a.draft(h, app), before));
  await pages.explicitFixture(h, content => {
    const records = content.dataSources.find(s => s.key === 'records');
    records.fields = [...new Set([...(records.fields || []), 'parent'])];
  }, undefined, {
    suffix: 'selfptr', requestPrefix: 'selfptr-',
    prepareAuthor: async (h, authored) => {
      const entity = structuredClone(authored.model.entities[0]);
      entity.fields.push(relation('parent', entity, false, false));
      authored.model = await a.save(h, authored.app, await a.draft(h, authored.app), [entity]);
      authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
    },
    buildEntityViews: inputViews,
  }).then(async fx => {
    const actor = await business.member(h, 'manager'), ctx = await business.runtime(h, fx, 0, actor), rows = [];
    let primary;
    try {
      const root = await create(h, fx, actor, ctx, rows, [{ name: 'parent', value: null }]);
      const child = await create(h, fx, actor, ctx, rows, [{ name: 'parent', reference: { id: root.recordId } }]);
      h.check('Single-pointer self-reference resolves child parent to exact root identity', same(ids(child.created.parent), [root.recordId]), child.created);
      await rejectedWrite(h, actor, root, business.request(root, 'delete'), { code: 21, messagePattern: '^记录仍被引用，禁止删除$' }, [root, child]);
    } catch (error) { primary = error; throw error; }
    finally {
      await business.finishCleanup(h, [...rows].reverse(), primary);
      if (!rows.some(r => r.phase !== 'deleted')) await pages.disposeExplicitFixture(h, fx, primary);
    }
  });
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
  const delivery = require('./model_delivery.cjs'), review = require('./deployment_review_cases.cjs');
  const fx = await pages.explicitFixture(h, content => {
    const records = content.dataSources.find(s => s.key === 'records');
    records.fields = [...new Set([...(records.fields || []), 'target', 'targets'])];
    records.pagination = { ...(records.pagination || { mode: 'cursor', defaultPageSize: 10 }), maxPageSize: 50 };
  }, undefined, {
    suffix: 'strlife', requestPrefix: 'str-life-',
    prepareAuthor: (h, authored) => prepare(h, authored, 'relations'),
    buildEntityViews: inputViews,
  });
  const actor = await business.member(h, 'manager'), peerCtx = await business.runtime(h, fx, 1, actor), rows = [];
  let primary;
  try {
    const targetEntity = fx.revision.entities.find(e => e.name === 'zzRelationTarget');
    const peerTarget = await create(h, fx, actor, peerCtx, rows, [], targetEntity.pkgPath + '/' + targetEntity.name);
    const peerHost = await create(h, fx, actor, peerCtx, rows, [{ name: 'target', reference: { id: peerTarget.recordId } }]);
    const pAuthor = require('./page_author_cases.cjs').authorFixture;
    const pBefore = await pAuthor.read(h, fx.application, 'pages');
    const pDetached = structuredClone(pBefore.content);
    pDetached.entityViews = {};
    const pRecs0 = pDetached.dataSources.find(s => s.key === 'records');
    if (pRecs0) pRecs0.fields = pRecs0.fields.filter(n => n !== 'target' && n !== 'targets');
    await pAuthor.save(h, fx.application, 'pages', pBefore, pDetached);
    const v1Draft = await a.draft(h, fx.application);
    const strippedHost = structuredClone(v1Draft.entities[0]);
    strippedHost.fields = strippedHost.fields.filter(v => !['target', 'targets'].includes(v.name));
    await a.save(h, fx.application, v1Draft, [strippedHost, v1Draft.entities[1]]);
    await h.ok(h.admin, 'DELETE', '/panel/application/definition/entitys/' + v1Draft.entities[1].id);
    const pMid = await pAuthor.read(h, fx.application, 'pages');
    const pNext = structuredClone(pBefore.content);
    delete pNext.entityViews[targetEntity.pkgPath + '/' + targetEntity.name];
    const pRecs = pNext.dataSources.find(s => s.key === 'records');
    if (pRecs) pRecs.fields = pRecs.fields.filter(n => n !== 'target' && n !== 'targets');
    const hostView = pNext.entityViews[strippedHost.pkgPath + '/' + strippedHost.name];
    if (hostView) {
      delete hostView.relations;
      hostView.fields = hostView.fields.filter(f => f.name !== 'target' && f.name !== 'targets');
    }
    await pAuthor.save(h, fx.application, 'pages', pMid, pNext);
    const v2 = await delivery.publishNext(h, fx);
    const upRefused = await h.api(h.admin, 'POST', '/panel/application/installations/' + fx.installations[0].id + '/upgrade-preview',
      { packageId: v2.package.id, expectedDigest: v2.package.artifactDigest });
    h.check('Installed v2 entity-removal upgrade preview is explicitly refused by Panel schema contract',
      !h.good(upRefused) && upRefused.data?.error?.code === 21 && /业务 Schema 不一致/.test(upRefused.data.error.message || '') && upRefused.data.value == null, upRefused);
    h.check('Refused entity-removal upgrade preserves peer installation data and records intact',
      same((await business.record(h, actor, peerHost)).data.value, peerHost.created) &&
      same((await business.record(h, actor, peerTarget)).data.value, peerTarget.created));
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    if (!rows.some(r => r.phase !== 'deleted')) await pages.disposeExplicitFixture(h, fx, primary);
  }
  h.observe({
    kind: 'v1-contract-boundary-aligned',
    caseId: 'F014-004',
    excluded: 'Initial contract freezes model storage schema without live entity drop/migration [B].',
  });
}
const handlers = { 'F013-001': scalarTypes, 'F014-001': h => references(h, 'basic'), 'F014-002': h => references(h, 'isolation'), 'F014-003': h => references(h, 'boundaries'), 'F014-004': structure, 'F070-004': h => references(h, 'forms') };
for (const fn of Object.values(handlers)) { fn.transport = 'owner-api'; fn.requiresOnlyDeliveryFixture = true; }
handlers['F014-002'].actors = ['tenantAdmin'];
module.exports = { handlers, field, relation, modelEntities, ids, rejectedWrite, withFixture, create, inputViews };
