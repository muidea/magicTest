// Delivery tests consume immutable owner facts; ZIP inspection is independent.
const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const pages = require('./page_runtime_cases.cjs');
const delivery = require('./model_delivery.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const { packageContent } = require('./owner_transport.cjs');
const base = '/panel/application/definitions/';
// Mirror only the public portable-export contract's exact identity fields.
// Every business field, block, capability and write rule remains compared.
function portableEntities(entities) {
  return structuredClone(entities).map(entity => {
    entity.id = 0; entity.createTime = 0; entity.updateTime = 0;
    entity.icon = ''; entity.application = null; delete entity.uiMeta;
    return entity;
  }).sort((a, b) => {
    const left = a.pkgPath + '/' + a.name, right = b.pkgPath + '/' + b.name;
    return left < right ? -1 : left > right ? 1 : 0;
  });
}
function archive(bytes) {
  return JSON.parse(execFileSync('python3', ['-B', '-c', `import io,json,sys,zipfile,hashlib,posixpath
z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
names=z.namelist()
assert len(names)==len(set(names)) and len(names)<=10000
assert all(not n.startswith('/') and posixpath.normpath(n)==n and '..' not in n.split('/') for n in names)
assert sum(i.file_size for i in z.infolist())<=256*1024*1024
assert z.testzip() is None
checks=json.loads(z.read('checksums.json'))
assert checks['apiVersion']=='magic.checksums/v1'
entries=checks['files']; paths=[e['path'] for e in entries]
assert len(paths)==len(set(paths)) and set(paths)==set(names)-{'checksums.json'}
for e in entries:
 b=z.read(e['path']); assert len(b)==e['size'] and 'sha256:'+hashlib.sha256(b).hexdigest()==e['digest']
manifest=json.loads(z.read('package.json')); c=manifest['content']
print(json.dumps({'manifest':manifest,'metadata':json.loads(z.read(c['application'])),'pages':json.loads(z.read(c['pages'])),
 'assets':json.loads(z.read(c['assets'])) if c.get('assets') else None,
 'referenceData':json.loads(z.read(c['referenceData'])) if c.get('referenceData') else None,
 'entities':[json.loads(z.read(e['path'])) for e in c['entities']],
 'programFiles':{n[len('application/blocks/'):]:__import__('base64').b64encode(z.read(n)).decode() for n in names if n.startswith('application/blocks/')},
 'memberFiles':{n:__import__('base64').b64encode(z.read(n)).decode() for n in names if (n.startswith('assets/') or n.startswith('bootstrap/reference-data/')) and n not in (c.get('assets'), c.get('referenceData'))},
 'files':names}))`], { input: bytes, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, stdio: ['pipe', 'pipe', 'pipe'] }));
}
async function roundtrip(h, f) {
  const result = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
  h.check('Complete original model ZIP is downloaded through the public transport', result.status === 200 && Buffer.isBuffer(result.data.bytes));
  const files = archive(result.data.bytes), m = files.manifest;
  h.check('Independent CRC/checksum reader binds exact model contract, release, complete entity identities and pages to published owner',
    m.apiVersion === 'magic.model-package/v1' && m.application.uuid === f.application.uuid && m.application.key === f.application.name && m.application.modelRevision === f.revision.version &&
    m.content.artifactDigest === f.package.artifactDigest && same(files.pages, f.revision.content.pages) &&
    same(files.metadata.authorization, f.revision.application.authorization) &&
    same(files.entities, portableEntities(f.revision.entities)) && same(files.programFiles, f.revision.content.functionBlocks.files) &&
    (!m.content.assets || same(files.assets, f.revision.content.assets) && f.revision.content.assets.files.every(x => files.memberFiles[x.path] === f.revision.content.packageFiles[x.path])) &&
    (!m.content.referenceData || same(files.referenceData, f.revision.content.referenceData) && f.revision.content.referenceData.files.every(x => files.memberFiles[x.path] === f.revision.content.packageFiles[x.path])), { manifest: m, files: files.files });
  await delivery.importExact(h, f, result.data.bytes);
  f.roundtrip = { manifest: m, files: files.files, transportDigest: 'sha256:' + crypto.createHash('sha256').update(result.data.bytes).digest('hex') };
  h.observe({ kind: 'original-model-roundtrip', ...f.roundtrip });
}
async function model(h) {
  let library, refEntityKey, expectedAsset, expectedRef;
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'completemodel', requestPrefix: 'completemodel-',
    prepareAuthor: async (h, authored) => {
      const author = require('./page_author_cases.cjs').authorFixture;
      library = await a.library(h, authored.app);
      const refEntity = a.newEntity(h, authored.app);
      refEntity.name = 'refDict'; refEntity.showName = '参考字典'; refEntity.blockInfo = []; refEntity.writeRules = null;
      refEntity.serviceExpose = { enabled: false, capabilities: [] };
      refEntity.uniqueConstraints = [{ name: 'uq_completemodel_ref_code', fields: ['code'] }];
      refEntity.fields = refEntity.fields.filter(v => v.name !== 'version').map(v => ({ ...v, spec: { ...v.spec, viewDeclare: ['detail', 'lite'], defaultValue: null } }));
      delete refEntity.createTime; delete refEntity.updateTime; delete refEntity.expectedEntityVersion;
      const currentModel = await a.draft(h, authored.app);
      authored.model = await a.save(h, authored.app, currentModel, [...currentModel.entities, refEntity]);
      refEntityKey = refEntity.pkgPath + '/' + refEntity.name;
      const png = await h.admin.page.screenshot({ clip: { x: 0, y: 0, width: 2, height: 2 }, animations: 'disabled' });
      const refBytes = Buffer.from(JSON.stringify({ schemaVersion: 'magic.application-reference-data/v1',
        records: [{ code: 'RG-COMPLETE-001', name: '完整交付参考行', description: 'ZIP往返验证', sortOrder: 1 }] }));
      const beforeMembers = await author.read(h, authored.app, 'package-members'), nextMembers = structuredClone(beforeMembers.content);
      expectedAsset = { key: 'delivery-bg', path: 'assets/delivery-bg.png', purpose: 'page-image', mime: 'image/png', size: png.length, digest: 'sha256:' + crypto.createHash('sha256').update(png).digest('hex') };
      expectedRef = { key: 'dictionary', path: 'bootstrap/reference-data/dictionary.json', entity: refEntityKey, naturalKey: ['code'], writePolicy: 'upsert', deletePolicy: 'preserve', digest: 'sha256:' + crypto.createHash('sha256').update(refBytes).digest('hex') };
      nextMembers.assets = { schemaVersion: 'magic.application-assets/v1', files: [expectedAsset] };
      nextMembers.referenceData = { schemaVersion: 'magic.application-reference-data-index/v1', files: [expectedRef] };
      nextMembers.files[expectedAsset.path] = png.toString('base64');
      nextMembers.files[expectedRef.path] = refBytes.toString('base64');
      await author.save(h, authored.app, 'package-members', beforeMembers, nextMembers);
      authored.model = await a.draft(h, authored.app);
      authored.pages = await author.read(h, authored.app, 'pages');
    },
    buildEntityViews: (authored, ui) => {
      const sample = authored.model.entities.find(e => e.name === 'sample');
      return { [sample.pkgPath + '/' + sample.name]: pages.explicitView(sample, ui) };
    },
    prepareDelivery: roundtrip });
  let primary;
  try {
    h.check('Formal published program library keeps every exact editable source byte and parameter file', require('./script_library_cases.cjs').frozenLibraryMatches(f.revision, f.application, library));
    h.check('Formal published revision freezes nonempty assets and reference data declarations',
      same(f.revision.content.assets?.files, [expectedAsset]) && same(f.revision.content.referenceData?.files, [expectedRef]));
    for (const i of f.installations) h.check('Real installed receipt consumes the exact frozen package and revision after ZIP import',
      i.sourceDigest === f.package.artifactDigest && i.receipt.revisionId === f.revision.id && i.receipt.revisionDigest === f.package.artifactDigest, i);
    const before = f.revision, current = await a.draft(h, f.application), changed = structuredClone(current.entities);
    changed[0].description = 'Unpublished model delivery edit ' + h.state.prefix;
    await a.save(h, f.application, current, changed);
    h.check('New editable author save leaves original installed frozen revision unchanged', same((await h.ok(h.admin, 'GET', base + f.application.id + '/revisions/' + before.id)).value, before));
  } catch (error) { primary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, f, primary); }
  h.observe({
    kind: 'v1-contract-boundary-aligned',
    caseId: 'F020-001',
    excluded: 'Separate editable-definition reconstruction from imported ZIP remains excluded by initial contract [B].',
  });
}
async function authorization(h) {
  const business = require('./business_cases.cjs'), actions = require('./business_action_cases.cjs');
  const authority = require('./application_authority_cases.cjs'), meta = require('./definition_metadata_cases.cjs');
  const generated = require('./generated_service_cases.cjs'), graph = require('./service_graph.cjs');
  const { endpointTemplates, currentRoleRefusal } = require('./service_contract_cases.cjs');
  const { keyRead } = require('./endpoint_authority_cases.cjs');
  let customAuth, entityKey;
  const prepareAuthor = async (h, authored) => {
    await actions.prepare(h, authored);
    const app = (await h.ok(h.admin, 'GET', base + authored.app.id)).value;
    entityKey = authored.model.entities[0].pkgPath + '/' + authored.model.entities[0].name;
    const rejected = [
      { apiVersion: 'magic.application-authorization/v1', entityData: [] },
      { ...app.authorization, dataAccess: [{ entity: entityKey, operation: 'read' }] },
      { ...app.authorization, roles: [{ key: 'ep.action', name: '禁Endpoint动作', subjectKinds: ['service'], entityActions: [{ entity: entityKey, action: 'acknowledge' }] }] },
      { ...app.authorization, roles: [{ key: 'missing.action', name: '缺失动作', subjectKinds: ['human'], entityActions: [{ entity: entityKey, action: 'missing' }] }] },
    ];
    for (const badAuth of rejected) {
      const res = await h.api(h.admin, 'PUT', base + authored.app.id, meta.command(app, { authorization: badAuth }));
      h.check('Owner rejects old-ACL, endpoint action role or invalid authorization schema before publication', !h.good(res) && res.data?.error?.code === 4 && res.data.value == null, res);
      h.check('Rejected authorization preserves exact original draft', same((await h.ok(h.admin, 'GET', base + authored.app.id)).value, app));
    }
    const authOpts = (await h.ok(h.admin, 'GET', '/panel/application/definitions/authorization-options')).value;
    const humanBuiltin = (authOpts.roles || []).find(r => Array.isArray(r.subjectKinds) && r.subjectKinds.includes('human'));
    const chosenBuiltin = humanBuiltin || authOpts.roles?.[0];
    customAuth = {
      apiVersion: 'magic.application-authorization/v1',
      dataAccess: structuredClone(app.authorization.dataAccess),
      entityActions: [{ entity: entityKey, action: 'acknowledge' }],
      builtinRoles: chosenBuiltin ? [{ module: chosenBuiltin.module, key: chosenBuiltin.key }] : [],
      permissions: [{ key: 'ext.audit', name: '扩展审计', permission: 4 }],
      roles: [{ key: 'ext.approver', name: '扩展业务审批', subjectKinds: ['human'], dataAccess: [{ operation: 'read' }],
        entityActions: [{ entity: entityKey, action: 'acknowledge' }], permissions: ['ext.audit'] }],
      templates: [{ key: 'ext.member', name: '扩展动作模板', subjectType: 'account', roleKeys: ['ext.approver'],
        ...(humanBuiltin ? { builtinRoles: [{ module: humanBuiltin.module, key: humanBuiltin.key }] } : {}) }],
    };
    await h.ok(h.admin, 'PUT', base + authored.app.id, meta.command(app, { authorization: customAuth }));
    authored.model = await a.draft(h, authored.app);
    authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
  };
  const f = await pages.explicitFixture(h, actions.configure, undefined,
    { suffix: 'authdelivery', requestPrefix: 'authdelivery-', prepareAuthor, prepareDelivery: roundtrip });
  let row, extAcc, extAssigned = false, svc, sub, cred, primary;
  try {
    const auth = f.revision.application.authorization;
    h.check('Frozen authorization retains exact builtin dependencies, action and extension definitions',
      auth?.apiVersion === 'magic.application-authorization/v1' && /^sha256:[a-f0-9]{64}$/.test(auth.builtinContractDigest || '') &&
      same(auth.dataAccess.map(v => v.operation).sort(), ['delete', 'read', 'write']) &&
      auth.dataAccess.every(v => same(Object.keys(v), ['operation'])) &&
      same(auth.entityActions, [{ entity: entityKey, action: 'acknowledge' }]) &&
      same(auth.builtinRoles || [], customAuth.builtinRoles || []) && same(auth.builtinTemplates || [], customAuth.builtinTemplates || []) &&
      same(auth.permissions, customAuth.permissions) && same(auth.roles, customAuth.roles) && same(auth.templates, customAuth.templates), auth);
    const outsider = await business.member(h, 'outsider'), manager = await business.member(h, 'manager');
    const roles = await h.directory(h.admin, '/cas/namespaces/panel/roles/');
    const roleTemplates = await h.directory(h.admin, '/cas/namespaces/panel/role-templates/');
    const actionRoleKey = 'entity-action-' + crypto.createHash('sha256').update('/apps/entity-actions' + entityKey + '/acknowledge').digest('hex');
    for (let index = 0; index < f.installations.length; index++) {
      const i = f.installations[index], module = '/applications/' + i.deploymentId, scoped = roles.filter(v => v.module === module);
      h.check('Independent CAS directory registers standard data/action roles and extension role/permission/template for exact installation',
        ['application-data-read', 'application-data-write', 'application-data-delete', actionRoleKey, 'ext.approver']
          .every(key => scoped.filter(v => v.key === key && v.status === 2).length === 1) &&
        scoped.some(v => v.key === 'ext.approver' && v.status === 2 && v.privilege?.some(p => p.module === module && p.uriPath === '/apps/permissions/ext.audit' && p.value === 4)) &&
        roleTemplates.some(t => t.key === 'app-' + i.deploymentId + '-ext.member' && t.status === 2 && t.subjectType === 'account' && t.systemManaged === true), scoped);
      const context = await business.runtime(h, f, index, manager);
      h.denied(await h.api(outsider, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + i.deploymentId), 'Formal registration does not grant an ordinary unassigned account runtime access');
      h.check('Registered installation remains the exact owner identity', context.identity.installationId === String(i.id));
    }
    const ctx0 = await business.runtime(h, f, 0, manager), ctx1 = await business.runtime(h, f, 1, manager);
    row = await actions.create(h, ctx0, f.application.id);
    extAcc = await authority.account(h, 'authdelivery-ext');
    extAcc.resource.scenarioDefinitionId = f.application.id; h.persist();
    const extTplKey = 'app-' + f.installations[0].deploymentId + '-ext.member';
    await h.ok(h.admin, 'PUT', '/cas/namespaces/panel/accounts/' + extAcc.value.id + '/role-templates', { roleTemplateKeys: ['portal-basic-user', extTplKey], applicationScopes: [] });
    extAssigned = true;
    h.denied(await h.api(extAcc.actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + f.installations[0].deploymentId),
      'Extension data/action role does not implicitly grant Portal runtime entry without a Panel access grant');
    h.check('Extension read data role reads the exact authorized installation record while keeping peer instance denied',
      same(await business.record(h, extAcc.actor, row), await business.record(h, manager, row)));
    h.denied(await h.api(extAcc.actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + f.installations[1].deploymentId),
      'Exact installation extension template does not grant peer installation runtime access');
    await actions.command(h, extAcc.actor, row, actions.request(row));
    await actions.dataCommand(h, extAcc.actor, row, 'update', false);
    const all = await generated.snapshot(h), srcUuid = f.installations[0].receipt.runtimeApplicationUuid;
    const getCap = all[generated.capabilities].find(c => c.providerType === 'application' && c.providerKey === srcUuid && c.kind === 'get' && c.status === 1 && !all[generated.bindings].some(b => b.capability?.id === c.id));
    h.check('Installed model advertises unoccupied get capability for Endpoint no-grant verification', !!getCap);
    svc = generated.intent(h, h.state.prefix + '_auth_ep', [getCap.id], srcUuid);
    await generated.converge(h, svc, [getCap.id], '授权边界Endpoint无隐式授权');
    const pub = svc.last.publications[0];
    await generated.mutation(h, svc, 'PUT', generated.publications + pub.id, { service: { id: svc.serviceId }, status: 1, visibleScope: 'panel', allowSubscription: true, requireApproval: false, maxSubscriptions: 2, maxQPS: 0, dailyQuota: 0 }, async r => h.check('Publication permits test subscription', h.good(r)));
    await generated.publish(h, svc);
    sub = await graph.subscribe(h, { service: svc.last.service, publication: svc.last.publications[0], ownerIdentity: structuredClone(h.admin.identity) }, extAcc.actor);
    cred = await graph.credential(h, sub, 'auth-ep-nogrant');
    const ep = (await h.ok(h.admin, 'GET', '/cas/namespaces/panel/endpoints/' + cred.value.endpointId)).value;
    h.check('Endpoint receives zero implicit business/extension/action grants from model installation or account extension role',
      (!ep.templateRefs || ep.templateRefs.length === 0) &&
      ep.effectiveRoles.every(r => r.module === '/modules/kernel/runner' && r.key === 'portal-service-invoker' && !r.module.startsWith('/applications/')), ep);
    const dbg = (await h.ok(extAcc.actor, 'GET', '/portal/service/debug/' + svc.serviceId)).value;
    h.check('Subscribed Endpoint with zero implicit application role is refused by Gateway current-role fence',
      currentRoleRefusal(await keyRead(h.admin.origin, dbg.operations[0].pathTemplate.replace(/\{id\}/g, row.recordId), cred.apiKey)));
    const current = await a.draft(h, f.application), changed = structuredClone(current.entities); changed[0].description = 'Unpublished authorization fixture edit';
    await a.save(h, f.application, current, changed);
    const byRoleId = list => [...list].sort((x, y) => String(x.id).localeCompare(String(y.id)));
    h.check('Editable draft update does not modify frozen authorization or current CAS role directory',
      same((await h.ok(h.admin, 'GET', base + f.application.id + '/revisions/' + f.revision.id)).value, f.revision) &&
      same(byRoleId(await h.directory(h.admin, '/cas/namespaces/panel/roles/')), byRoleId(roles)));
  } catch (error) { primary = error; throw error; }
  finally {
    try {
      if (cred?.resource?.phase === 'created') await graph.retireCredential(h, cred);
      if (sub?.resource?.phase === 'created') await graph.retire(h, sub);
      if (svc?.phase === 'created') await generated.cleanup(h, svc);
      if (extAssigned) await h.api(h.admin, 'PUT', '/cas/namespaces/panel/accounts/' + extAcc.value.id + '/role-templates', { roleTemplateKeys: ['portal-basic-user'], applicationScopes: [] });
      if (row) await business.finishCleanup(h, [row], primary);
    } finally { await pages.disposeExplicitFixture(h, f, primary); }
  }
}
async function upgradeAdmission(h) {
  const review = require('./deployment_review_cases.cjs'), upgrade = require('./model_upgrade_cases.cjs');
  const generated = require('./generated_service_cases.cjs'), author = require('./page_author_cases.cjs').authorFixture;
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'upgradeadmit', requestPrefix: 'upgrade-admit-' });
  const directories = ['/panel/application/deployment-requests/', '/panel/operations/namespaces/panel/application-deployment-operations/'];
  let svc, target, staleReq, primary;
  try {
    const v1Pkg = structuredClone(f.package);
    let latest = { application: f.application, revision: f.revision, package: f.package, resource: f.resource };
    const inst0 = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + f.installations[0].id)).value;
    const inst1 = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + f.installations[1].id)).value;
    const snapshots = [];
    for (const route of directories) snapshots.push(await h.directory(h.admin, route));
    // 1. Same published version refusal + native deployment-package upgrade refusal.
    const sameRes = await h.api(h.admin, 'POST', '/panel/application/installations/' + inst0.id + '/upgrade-preview', { packageId: v1Pkg.id, expectedDigest: v1Pkg.artifactDigest });
    h.check('Same published version is refused at precise upgrade version gate before execution', review.refusal(sameRes, '目标必须是更新的正式发布版本；相同版本重试请恢复原操作，首期不支持降级'), sameRes);
    const nativeReq = await h.api(h.admin, 'POST', '/panel/application/deployment-requests/', {
      sourceKind: 'deployment-package', packageId: v1Pkg.id, expectedDigest: v1Pkg.artifactDigest,
      deploymentId: inst0.deploymentId, instanceKey: inst0.instanceKey, instanceName: inst0.instanceName,
      upgrade: { installationId: inst0.id, previewDigest: 'sha256:' + '0'.repeat(64) }, reason: '原生升级禁止验证',
    });
    h.check('Native deployment-package source cannot enter model upgrade pipeline',
      [200, 400, 409].includes(nativeReq.status) && nativeReq.data?.error?.code === 4 && nativeReq.data.error.message === '原生应用暂不支持此升级流程' && nativeReq.data.value == null, nativeReq);
    // 2. Interface (bound generated-service capability disabled) refusal.
    const all = await generated.snapshot(h), srcUuid = inst0.receipt.runtimeApplicationUuid;
    const getCap = all[generated.capabilities].find(c => c.providerType === 'application' && c.providerKey === srcUuid && c.kind === 'get' && c.status === 1 && !all[generated.bindings].some(b => b.capability?.id === c.id));
    h.check('Installed model has unoccupied get capability for bound interface check', !!getCap);
    svc = generated.intent(h, h.state.prefix + '_admit_svc', [getCap.id], srcUuid);
    await generated.converge(h, svc, [getCap.id], '升级门禁绑定服务');
    const draft1 = await a.draft(h, f.application), noGet = structuredClone(draft1.entities);
    noGet[0].serviceExpose.capabilities = noGet[0].serviceExpose.capabilities.map(c => c.key === 'get' ? { ...c, enabled: false } : c);
    await a.save(h, f.application, draft1, noGet);
    const pkgNoGet = latest = await delivery.publishNext(h, latest);
    const noGetPreview = await h.api(h.admin, 'POST', '/panel/application/installations/' + inst0.id + '/upgrade-preview', { packageId: pkgNoGet.package.id, expectedDigest: pkgNoGet.package.artifactDigest });
    h.check('Removing bound service capability is refused at upgrade preview',
      [200, 400, 409].includes(noGetPreview.status) && [4, 21].includes(noGetPreview.data?.error?.code) && String(noGetPreview.data.error.message || '').includes('不再开放该能力') && noGetPreview.data.value == null, noGetPreview);
    await generated.cleanup(h, svc); svc = null;
    // 3. Write-rule change refusal.
    const draft2 = await a.draft(h, f.application), wrChanged = structuredClone(draft2.entities);
    wrChanged[0].serviceExpose = structuredClone(f.revision.entities[0].serviceExpose);
    wrChanged[0].writeRules = { ...wrChanged[0].writeRules, appendOnly: true };
    await a.save(h, f.application, draft2, wrChanged);
    const pkgWriteRule = latest = await delivery.publishNext(h, latest);
    const wrPreview = await h.api(h.admin, 'POST', '/panel/application/installations/' + inst0.id + '/upgrade-preview', { packageId: pkgWriteRule.package.id, expectedDigest: pkgWriteRule.package.artifactDigest });
    h.check('Incompatible writeRules change is refused before upgrade execution',
      [200, 400, 409].includes(wrPreview.status) && wrPreview.data?.error?.code === 21 && String(wrPreview.data.error.message || '').includes('实体兼容性检查未通过') && wrPreview.data.value == null, wrPreview);
    // 4. Schema change refusal.
    const draft3 = await a.draft(h, f.application), schChanged = structuredClone(draft3.entities);
    schChanged[0].writeRules = structuredClone(f.revision.entities[0].writeRules);
    schChanged[0].fields.push({ name: 'extraNote', showName: '附加字段', type: { name: 'string', isPtr: true }, spec: { viewDeclare: ['detail', 'list'] } });
    await a.save(h, f.application, draft3, schChanged);
    const pkgSchema = latest = await delivery.publishNext(h, latest);
    const schPreview = await h.api(h.admin, 'POST', '/panel/application/installations/' + inst0.id + '/upgrade-preview', { packageId: pkgSchema.package.id, expectedDigest: pkgSchema.package.artifactDigest });
    h.check('Incompatible Schema change is refused before upgrade execution',
      review.refusal(schPreview, '业务 Schema 不一致，首期升级不执行数据迁移；可选择全新安装'), schPreview);
    for (const [index, route] of directories.entries()) h.check('Upgrade preflight refusals create no replacement request or operation', same(await h.directory(h.admin, route), snapshots[index]));
    h.check('Preview refusals preserve exact original installations',
      same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + inst0.id)).value, inst0) &&
      same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + inst1.id)).value, inst1));
    // 5. Compatible revision -> actual approval fence (stale installation version) + lower-version refusal after upgrade.
    const draft4 = await a.draft(h, f.application), restored = structuredClone(draft4.entities);
    restored[0].fields = structuredClone(f.revision.entities[0].fields);
    await a.save(h, f.application, draft4, restored);
    const beforePages = await author.read(h, f.application, 'pages'), nextPages = structuredClone(beforePages.content);
    nextPages.pages[0].title = '升级准入兼容修订';
    await author.save(h, f.application, 'pages', beforePages, nextPages);
    const pkgCompat = latest = await delivery.publishNext(h, latest);
    const preview1 = (await h.ok(h.admin, 'POST', '/panel/application/installations/' + inst1.id + '/upgrade-preview', { packageId: pkgCompat.package.id, expectedDigest: pkgCompat.package.artifactDigest })).value;
    const staleCreated = await h.create('/panel/application/deployment-requests/', {
      sourceKind: 'model-package', packageId: pkgCompat.package.id, expectedDigest: pkgCompat.package.artifactDigest,
      deploymentId: inst1.deploymentId, instanceKey: inst1.instanceKey, instanceName: inst1.instanceName,
      upgrade: { installationId: inst1.id, previewDigest: preview1.previewDigest }, reason: 'Stale approval fence probe',
    }, 'deployment-review-request');
    staleReq = h.state.resources.find(r => r.kind === 'deployment-review-request' && r.id === staleCreated.id);
    staleReq.commands = []; staleReq.last = (await h.ok(h.admin, 'GET', '/panel/application/deployment-requests/' + staleReq.id)).value; h.persist();
    const renamed = (await h.ok(h.admin, 'PUT', '/panel/application/installations/' + inst1.id + '/instance-name', { instanceName: inst1.instanceName + ' 变更', expectedDeploymentVersion: inst1.deploymentVersion })).value;
    h.check('Instance rename advances deployment version cleanly', renamed.deploymentVersion > inst1.deploymentVersion);
    const opts = (await h.ok(h.admin, 'GET', '/panel/operations/namespaces/panel/application-deployment-requests/' + staleReq.id + '/runtime-options')).values;
    const runtimePlacement = { executionInstanceId: opts.find(v => v.kind === 'base').id, gatewayInstanceId: opts.find(v => v.kind === 'gateway').id };
    const staleApprove = await h.api(h.admin, 'POST', '/panel/operations/namespaces/panel/application-deployment-requests/' + staleReq.id + '/approve', { expectedVersion: staleReq.last.version, reason: 'Stale approval must refuse', runtimePlacement });
    h.check('Actual approval fence refuses upgrade when installation progressed after preview',
      [200, 400, 409].includes(staleApprove.status) && [4, 19, 21].includes(staleApprove.data?.error?.code) && String(staleApprove.data.error.message || '').includes('已变化') && staleApprove.data.value == null, staleApprove);
    const restoredName = (await h.ok(h.admin, 'PUT', '/panel/application/installations/' + inst1.id + '/instance-name', { instanceName: inst1.instanceName, expectedDeploymentVersion: renamed.deploymentVersion })).value;
    h.check('Restoring instance display preserves peer identity for clean fixture retirement', restoredName.instanceName === inst1.instanceName && restoredName.deploymentVersion > renamed.deploymentVersion);
    const source = f.pageRequests[0];
    source.modelUpgrade = { phase: 'prepared', source: inst0, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
      definitionId: f.application.id, requestIds: [source.id], installationIds: [String(inst0.id)], fixture: pkgCompat }; h.persist();
    target = await upgrade.createUpgrade(h, source, pkgCompat);
    await review.approve(h, target, [h.admin]);
    if (f.pageGrants?.[0]) {
      f.pageGrants[0].upgradePredecessorInstallation = structuredClone(f.pageGrants[0].installation);
      f.pageGrants[0].installation = target.installation;
    }
    source.modelUpgrade.target = target.installation; source.modelUpgrade.installationIds.push(String(target.installation.id));
    source.modelUpgrade.handoffSource = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + inst0.id)).value;
    source.modelUpgrade.phase = 'rows-disposed'; h.persist();
    const downgradeRes = await h.api(h.admin, 'POST', '/panel/application/installations/' + target.installation.id + '/upgrade-preview', { packageId: v1Pkg.id, expectedDigest: v1Pkg.artifactDigest });
    h.check('Lower published version than current installation is refused as downgrade',
      review.refusal(downgradeRes, '目标必须是更新的正式发布版本；相同版本重试请恢复原操作，首期不支持降级'), downgradeRes);
  } catch (error) { primary = error; throw error; }
  finally {
    try {
      if (svc?.phase === 'created') await generated.cleanup(h, svc);
      if (staleReq && staleReq.phase !== 'deleted') await review.cleanup(h, staleReq);
      if (target && target.phase !== 'deleted') {
        if (f.pageGrants?.[0]?.phase !== 'deleted' && target.installation) {
          f.pageGrants[0].upgradePredecessorInstallation ||= structuredClone(f.pageGrants[0].installation);
          f.pageGrants[0].installation = target.installation;
          h.persist();
          await require('./application_authority_cases.cjs').retireAccess(h, f.pageGrants[0]);
        }
        await review.cleanup(h, target);
        await upgrade.finishSource(h, f.pageRequests[0], target);
      }
    } finally { await pages.disposeExplicitFixture(h, f, primary); }
  }
}
const handlers = { 'F020-001': model, 'F020-004': authorization, 'F033-005': upgradeAdmission };
for (const fn of Object.values(handlers)) { fn.transport = 'owner-api'; fn.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers, archive, roundtrip, portableEntities };
