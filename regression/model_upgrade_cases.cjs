// Same-deployment maintenance upgrade. The predecessor remains immutable
// history; only the current successor is destroyed after exact row disposition.
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const review = require('./deployment_review_cases.cjs');
const delivery = require('./model_delivery.cjs');
const authority = require('./application_authority_cases.cjs');
const installations = '/panel/application/installations/';
const requests = '/panel/application/deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(v => v.value);
const absent = r => [200, 404].includes(r?.status) && r.data?.error?.code === 2 && r.data.value == null;
const binding = v => Object.fromEntries(['bindingId', 'schemaResourceId', 'databaseResourceId'].map(k => [k, v?.receipt?.database?.[k]]));
function original(h, source) {
  review.original(h, source);
  const j = source.modelUpgrade;
  if (!j || j.origin !== h.admin.origin || !same(j.actorIdentity, h.admin.identity))
    throw new h.Blocked('Original upgrade actor or lineage unresolved; no replacement command or predecessor uninstall');
  return j;
}
function previewMatches(source, f, p) {
  return p?.sourceInstallationId === source.id && p.sourceInstallationVersion === source.updateTime && p.deploymentVersion === source.deploymentVersion &&
    p.sourceDigest === source.sourceDigest && p.targetPackageId === f.package.id && p.targetDigest === f.package.artifactDigest &&
    p.sourceVersion > 0 && p.targetVersion === f.revision.version && p.targetVersion > p.sourceVersion &&
    p.deploymentId === source.deploymentId && p.instanceKey === source.instanceKey && p.instanceName === source.instanceName &&
    /^sha256:[a-f0-9]{64}$/.test(p.previewDigest) && /^sha256:[a-f0-9]{64}$/.test(p.schemaDigest) && p.maintenanceRequired === true;
}
function handoffMatches(j, target, source) {
  const a = j.source, p = j.preview, t = target.installation, u = source?.receipt?.upgrade;
  return !!t && t.id !== a.id && t.previousInstallationId === a.id && t.status === 'ready' && source.id === a.id && source.status === 'disabled' &&
    ['namespace', 'deploymentId', 'applicationUuid', 'applicationKey', 'instanceKey', 'instanceName'].every(k => t[k] === a[k] && source[k] === a[k]) &&
    Object.values(binding(a)).every(v => Number.isSafeInteger(v) && v > 0) && same(binding(a), binding(t)) && same(binding(a), binding(source)) &&
    source.sourceDigest === a.sourceDigest && source.receipt.runtimeApplicationUuid === a.receipt.runtimeApplicationUuid &&
    typeof t.receipt.runtimeApplicationUuid === 'string' && t.receipt.runtimeApplicationUuid.length > 0 &&
    t.receipt.runtimeApplicationUuid !== a.receipt.runtimeApplicationUuid && t.sourceDigest === p.targetDigest &&
    t.receipt.revisionId === j.fixture.revision.id && t.receipt.revisionDigest === p.targetDigest &&
    t.operationId === 'deployment:' + target.operation.id && t.receipt.deploymentOperationId === target.operation.id &&
    u?.operationId === target.operation.id && u.planDigest === p.previewDigest && u.targetInstallationId === t.id && u.phase === 'completed' &&
    !u.restoreRequested && target.last.upgrade?.previewDigest === p.previewDigest && target.operation.planDigest === target.last.planDigest;
}
async function createUpgrade(h, source, f) {
  const j = original(h, source);
  if (j.phase !== 'prepared' || j.upgradeRequestId || !review.installationUnchanged(j.source, await read(h, installations + j.source.id)))
    throw new h.Blocked('Original upgrade already dispatched or installation changed; no request replay');
  j.preview = await readPreview(h, j.source, f); h.persist();
  original(h, source); j.phase = 'requesting'; h.persist();
  const value = await h.create(requests, { sourceKind: 'model-package', packageId: f.package.id, expectedDigest: f.package.artifactDigest,
    deploymentId: j.source.deploymentId, instanceKey: j.source.instanceKey, instanceName: j.source.instanceName,
    upgrade: { installationId: j.source.id, previewDigest: j.preview.previewDigest }, reason: 'Current-run original same-Schema maintenance upgrade' }, 'deployment-review-request');
  const r = h.state.resources.find(v => v.kind === 'deployment-review-request' && v.id === value.id);
  r.commands = []; r.last = await read(h, requests + r.id); j.upgradeRequestId = r.id; j.requestIds.push(r.id); delivery.linkRequest(h, f, r); h.persist();
  h.check('Formal upgrade request freezes exact original preview and deployment without a new instance', same(r.last, value) &&
    value.status === 'submitted' && !value.operationId && value.deploymentId === j.source.deploymentId && value.packageId === f.package.id &&
    same(value.upgrade, j.preview), value);
  return r;
}
async function readPreview(h, source, f) {
  const p = (await h.ok(h.admin, 'POST', installations + source.id + '/upgrade-preview', { packageId: f.package.id, expectedDigest: f.package.artifactDigest })).value;
  h.check('Formal upgrade preview freezes exact predecessor, newer publication and same-deployment maintenance window', previewMatches(source, f, p), p);
  return p;
}
async function disposeRow(h, actor, row, context, source) {
  const j = original(h, source);
  if (j.phase !== 'upgraded' || row.scenarioUpgradeRequestId !== source.id || row.successorDisposition || row.commands.some(c => c.outcome === 'unknown') ||
      actor.origin !== row.origin || !same(actor.identity, row.actorIdentity) || row.identity.installationId !== String(j.source.id) ||
      context.identity.installationId !== String(j.target.id) || context.identity.deploymentId !== row.identity.deploymentId ||
      context.identity.runtimeApplicationUuid !== j.target.receipt.runtimeApplicationUuid || context.identity.namespace !== row.identity.namespace || context.entity !== row.entity ||
      context.applicationKey !== row.applicationKey || !business.installationMatches(j.fixture, j.target, context.identity) ||
      !review.installationUnchanged(j.target, await read(h, installations + j.target.id)))
    throw new h.Blocked('Exact original row and current upgraded successor required; no obsolete-fence or duplicate delete');
  const before = await business.record(h, actor, { ...context, recordId: row.recordId });
  h.check('Upgraded owner reads the entire original business record and version before any new write', h.good(before) && same(before.data.value, row.created), before);
  const current = { ...context, recordId: row.recordId, version: row.version, origin: row.origin, actorIdentity: structuredClone(row.actorIdentity), commands: [], phase: 'created' };
  delete current.ui; row.successorDisposition = current; h.persist();
  const receipt = await business.execute(h, actor, current, business.request(current, 'update', [{ name: 'name', value: row.created.name + ' upgraded' }]));
  h.check('Current ordinary member continues reliable writes after upgrade with unrelated original fields intact',
    same((await business.record(h, actor, current)).data.value, { ...row.created, name: row.created.name + ' upgraded', version: Number(receipt.version) }));
  await business.execute(h, actor, current, business.request(current, 'delete'));
  h.check('Current successor delete and independent original-ID absence preserve immutable predecessor command identities',
    absent(await business.record(h, actor, current)) && row.commands.every(c => c.outcome === 'confirmed' && c.body.identity.installationId === String(j.source.id)));
  current.phase = 'deleted'; row.phase = 'deleted'; h.persist();
}
async function finishSource(h, source, target) {
  const j = original(h, source); review.original(h, target);
  const retired = target.retiredInstallation, uninstall = target.commands.find(c => c.route === installations + j.target?.id + '/uninstall');
  if (j.phase !== 'rows-disposed' || target.id !== j.upgradeRequestId || target.phase !== 'deleted' ||
      !same(target.installation, j.target) || !handoffMatches(j, target, j.handoffSource) ||
      !review.destroyConfirmed(h, uninstall || {}, retired || {}, j.target) ||
      h.state.resources.some(r => r.scenarioUpgradeRequestId === source.id && r.phase !== 'deleted'))
    throw new h.Blocked('Original upgrade predecessor requires exact successor destroy and complete original-row dispositions');
  h.check('Independent original history and current successor confirm exact completed handoff and formal destroy',
    review.historicalInstallationUnchanged(j.handoffSource, await read(h, installations + j.source.id)) &&
    review.installationUnchanged(retired, await read(h, installations + j.target.id)));
  const schemas = await h.directory(h.admin, '/panel/storage-resources/database-schemas/');
  h.check('Independent storage owner confirms original shared Schema recycled only after successor destroy',
    schemas.some(s => s.id === j.source.receipt.database.schemaResourceId && s.status === 'recycled'));
  h.check('Original predecessor request and operation remain unchanged as durable history',
    await review.originalHistory(h, source, await read(h, requests + source.id), await read(h, operations + source.operation.id)));
  original(h, source);
  j.phase = 'complete'; source.phase = 'deleted'; source.retentionProof = { predecessorId: j.source.id, successorId: j.target.id,
    proof: 'Completed original upgrade handoff to exact formally destroyed successor; independent shared Schema recycled. Predecessor installation and original commands/history retained; no second predecessor uninstall.' };
  h.persist(); return source.retentionProof;
}
async function upgrade(h) {
  const crypto = require('node:crypto'), pages = require('./page_runtime_cases.cjs'), author = require('./page_author_cases.cjs').authorFixture;
  const generated = require('./generated_service_cases.cjs'), graph = require('./service_graph.cjs');
  const { endpointTemplates } = require('./service_contract_cases.cjs'), { keyRead } = require('./endpoint_authority_cases.cjs');
  const authoring = require('./authoring_cases.cjs').authoring;
  let refEntityKey;
  const prepareAuthor = async (h, authored) => {
    authored.model = await authoring.draft(h, authored.app);
    const baseEntity = authored.model.entities[0];
    const refEntity = structuredClone(baseEntity);
    refEntity.id = 0; refEntity.name = 'zzRefDictionary'; refEntity.showName = '参考字典';
    refEntity.blockInfo = []; refEntity.writeRules = null;
    refEntity.serviceExpose = { enabled: false, capabilities: [] };
    refEntity.uniqueConstraints = [{ name: 'uq_ref_dictionary_code', fields: ['code'] }];
    refEntity.fields = refEntity.fields.filter(v => v.name !== 'version').map(v => ({
      ...v, spec: { ...v.spec, viewDeclare: ['detail', 'lite'], defaultValue: null },
    }));
    delete refEntity.createTime; delete refEntity.updateTime; delete refEntity.expectedEntityVersion;
    authored.model = await authoring.save(h, authored.app, authored.model, [...authored.model.entities, refEntity]);
    refEntityKey = refEntity.pkgPath + '/' + refEntity.name;
    const v1Bytes = Buffer.from(JSON.stringify({ schemaVersion: 'magic.application-reference-data/v1',
      records: [{ code: 'RG-REF-001', name: '初始参考字典', description: '初始参考说明', sortOrder: 1 }] }));
    const beforeMembers = await author.read(h, authored.app, 'package-members');
    const nextMembers = structuredClone(beforeMembers.content);
    nextMembers.referenceData = { schemaVersion: 'magic.application-reference-data-index/v1', files: [{
      key: 'dictionary', path: 'bootstrap/reference-data/dictionary.json', entity: refEntityKey, naturalKey: ['code'],
      writePolicy: 'upsert', deletePolicy: 'preserve', digest: 'sha256:' + crypto.createHash('sha256').update(v1Bytes).digest('hex'),
    }] };
    nextMembers.files['bootstrap/reference-data/dictionary.json'] = v1Bytes.toString('base64');
    await author.save(h, authored.app, 'package-members', beforeMembers, nextMembers);
    const beforePages = await author.read(h, authored.app, 'pages'), nextPages = structuredClone(beforePages.content);
    const sampleSource = nextPages.dataSources.find(s => s.key === 'records');
    nextPages.dataSources.push({ ...structuredClone(sampleSource), key: 'refRecords', entity: refEntityKey, fields: ['id', 'name'] });
    await author.save(h, authored.app, 'pages', beforePages, nextPages);
    authored.model = await authoring.draft(h, authored.app);
    authored.pages = await author.read(h, authored.app, 'pages');
  };
  const f = await pages.explicitFixture(h, null, null, { suffix: 'modelupgrade', requestPrefix: 'model-upgrade-', prepareAuthor });
  const actor = await business.member(h, 'manager'), source = f.pageRequests[0], grant = f.pageGrants[0];
  let row, peerRow, target, svc, sub, cred, primary;
  try {
    const context = await business.runtime(h, f, 0, actor), peer = await business.runtime(h, f, 1, actor);
    const meta0 = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
    const refContext = { ...context, entity: refEntityKey, pageDigest: meta0.installation.pageDigest };
    const seededRes = await pages.sourceRead(h, actor, refContext, { sourceKey: 'refRecords', pageSize: 10 });
    h.check('V1 installation materializes the single seeded reference data row automatically', h.good(seededRes), seededRes);
    const seededRows = pages.decodePage(seededRes.data.value, refContext, 10, 'refRecords');
    h.check('V1 seeded reference data contains exact single initial record', seededRows.length === 1 && seededRows[0].name === '初始参考字典', seededRows);
    const preRefId = seededRows[0].id;
    row = await business.create(h, { ...context, scenarioUpgradeRequestId: source.id, scenarioDefinitionId: f.application.id }, 'upgrade-original');
    peerRow = await business.create(h, { ...peer, scenarioDefinitionId: f.application.id }, 'upgrade-peer');
    // Prepare compatible generated service (including create on writeRules entity) + publication + subscription + ApiKey before upgrade.
    const allCaps = await generated.snapshot(h), srcUuid = source.installation.receipt.runtimeApplicationUuid;
    const getCap = allCaps[generated.capabilities].find(c => c.providerType === 'application' && c.providerKey === srcUuid && c.kind === 'get' && c.status === 1 && !allCaps[generated.bindings].some(b => b.capability?.id === c.id));
    const createCap = allCaps[generated.capabilities].find(c => c.providerType === 'application' && c.providerKey === srcUuid && c.kind === 'create' && c.status === 1 && !allCaps[generated.bindings].some(b => b.capability?.id === c.id));
    h.check('Upgrade fixture finds unoccupied get and create capabilities for compatible service handoff', !!getCap && !!createCap);
    const handoffCapIds = [getCap.id, createCap.id];
    svc = generated.intent(h, h.state.prefix + '_upgrade_svc', handoffCapIds, srcUuid);
    await generated.converge(h, svc, handoffCapIds, '升级兼容生成服务');
    const pub0 = svc.last.publications[0];
    await generated.mutation(h, svc, 'PUT', generated.publications + pub0.id, { service: { id: svc.serviceId }, status: 1, visibleScope: 'panel', allowSubscription: true, requireApproval: false, maxSubscriptions: 2, maxQPS: 0, dailyQuota: 0 }, async r => h.check('Publication allows upgrade-test subscription', h.good(r)));
    await generated.publish(h, svc);
    const ordinary = (await h.directory(h.admin, '/cas/namespaces/panel/role-templates/')).find(t => t.key === 'portal-basic-user' && t.systemManaged && t.status === 2 && t.subjectType === 'account');
    const access = [{ applicationUuid: source.installation.deploymentId, accessLevel: 'manager' }];
    const group = await h.create('/cas/namespaces/panel/role-templates/', { key: h.state.prefix + '-upgrade-svc', name: '升级服务账号范围', subjectType: 'account', status: 2, roleRefs: ordinary.roleRefs, applicationAccess: access }, 'role-template');
    const m = await authority.account(h, 'upgrade-svc');
    await authority.assign(h, m, group, access);
    const epTemplate = await h.create('/cas/namespaces/panel/role-templates/', { key: h.state.prefix + '-upgrade-ep', name: '升级Endpoint读取', subjectType: 'endpoint', status: 2, applicationAccess: [],
      roleRefs: [{ module: '/applications/' + source.installation.deploymentId, key: 'application-data-read' }] }, 'role-template');
    sub = await graph.subscribe(h, { service: svc.last.service, publication: svc.last.publications[0], ownerIdentity: structuredClone(h.admin.identity) }, m.actor);
    cred = await graph.credential(h, sub, 'upgrade-svc-key');
    await endpointTemplates(h, cred, [epTemplate.key]);
    const dbg = (await h.ok(m.actor, 'GET', '/portal/service/debug/' + svc.serviceId)).value;
    const getOp = dbg.operations.find(o => o.method === 'GET' && o.pathTemplate.includes('{id}'));
    h.check('Upgrade service debug exposes get operation', !!getOp, dbg);
    const opGetPath = getOp.pathTemplate.replace(/\{id\}/g, row.recordId);
    const preGateway = await keyRead(h.admin.origin, opGetPath, cred.apiKey);
    h.check('Pre-upgrade Gateway call succeeds with exact original ApiKey', h.good(preGateway) && same(preGateway.data.value, row.created), preGateway);
    const beforePages = await author.read(h, f.application, 'pages'), content = structuredClone(beforePages.content);
    content.pages[0].title = '新冻结维护窗口页面';
    await author.save(h, f.application, 'pages', beforePages, content);
    const v2MembersBefore = await author.read(h, f.application, 'package-members'), v2Members = structuredClone(v2MembersBefore.content);
    const v2Bytes = Buffer.from(JSON.stringify({ schemaVersion: 'magic.application-reference-data/v1',
      records: [{ code: 'RG-REF-001', name: 'V2不应覆盖', description: 'V2说明1', sortOrder: 1 }, { code: 'RG-REF-002', name: 'V2新增不重导', description: 'V2说明2', sortOrder: 2 }] }));
    v2Members.referenceData = { schemaVersion: 'magic.application-reference-data-index/v1', files: [{
      key: 'dictionary', path: 'bootstrap/reference-data/dictionary.json', entity: refEntityKey, naturalKey: ['code'],
      writePolicy: 'upsert', deletePolicy: 'preserve', digest: 'sha256:' + crypto.createHash('sha256').update(v2Bytes).digest('hex'),
    }] };
    v2Members.files['bootstrap/reference-data/dictionary.json'] = v2Bytes.toString('base64');
    await author.save(h, f.application, 'package-members', v2MembersBefore, v2Members);
    const next = await delivery.publishNext(h, f);
    const j = { phase: 'prepared', source: await read(h, installations + source.installation.id), actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
      definitionId: f.application.id, requestIds: [source.id], installationIds: [String(source.installation.id)], fixture: { application: next.application, revision: next.revision, package: next.package } };
    source.modelUpgrade = j; row.scenarioUpgradeRequestId = source.id; h.persist();
    j.originalAssignment = (await h.directory(h.admin, installations + j.source.id + '/assignments/')).find(v => v.id === grant.assignmentId);
    h.check('Original active member assignment belongs to exact predecessor before maintenance', j.originalAssignment?.installationId === j.source.id &&
      j.originalAssignment.subjectId === grant.accountId && j.originalAssignment.accessLevel === 'manager', j.originalAssignment);
    target = await createUpgrade(h, source, next);
    h.check('Upgrade preview binds referenceDataPolicy=preserve-existing and exact compatible service handoff',
      target.last.upgrade.referenceDataPolicy === 'preserve-existing' &&
      target.last.upgrade.serviceHandoffs?.length === 1 && target.last.upgrade.serviceHandoffs[0].service?.id === svc.serviceId &&
      target.last.upgrade.serviceHandoffs[0].bindings?.length === handoffCapIds.length, target.last.upgrade);
    const maintenanceTrail = [];
    await review.approve(h, target, [h.admin], { observeOperation: (_req, op) => maintenanceTrail.push({ status: op.status, currentStep: op.currentStep }) });
    h.observe({ kind: 'model-upgrade-maintenance-trail', trail: maintenanceTrail });
    j.target = target.installation; j.installationIds.push(String(j.target.id)); j.handoffSource = await read(h, installations + j.source.id); h.persist();
    h.check('Real maintenance upgrade preserves deployment and physical Schema while switching runtime identity with complete predecessor handoff receipt',
      handoffMatches(j, target, j.handoffSource) && Array.isArray(j.target.receipt.completedSteps) && j.target.receipt.completedSteps.includes('reference-data-preserved'),
      { source: j.handoffSource, target: j.target });
    // Verify stale predecessor runtime/generation identity fails closed after maintenance drain.
    const drained = await business.record(h, actor, { ...context, recordId: row.recordId });
    h.check('Drained predecessor runtime identity is refused after route handoff', !h.good(drained) && drained.data?.value == null, drained);
    const assignments = await h.directory(h.admin, installations + j.target.id + '/assignments/'), moved = assignments.filter(v => v.id === grant.assignmentId);
    const expected = { ...j.originalAssignment, installationId: j.target.id, updateTime: moved[0]?.updateTime };
    h.check('Exact original member assignment is transferred to successor without granting a replacement membership', moved.length === 1 &&
      moved[0].updateTime >= j.originalAssignment.updateTime && same(moved[0], expected), assignments);
    grant.upgradePredecessorInstallation = structuredClone(grant.installation); grant.installation = j.target; j.phase = 'upgraded'; h.persist();
    const current = { ...next, installations: [j.target] }, successorContext = await business.runtime(h, current, 0, actor);
    const pageView = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + next.application.name + '?deploymentId=' + j.target.deploymentId)).value;
    const peerView = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + f.installations[1].deploymentId)).value;
    h.check('Actual ordinary runtime serves complete newer frozen pages while peer keeps original frozen pages',
      same(pageView.pages, next.revision.content.pages) && same(peerView.pages, f.revision.content.pages) &&
      !same(pageView.pages, peerView.pages) && same(pageView.readIdentity, successorContext.identity));
    h.check('Unrelated instance keeps its exact installation and complete original business row throughout maintenance',
      review.installationUnchanged(f.installations[1], await read(h, installations + f.installations[1].id)) && same((await business.record(h, actor, peerRow)).data.value, peerRow.created));
    // Verify existing reference data is preserved and V2 reference data does not overwrite or insert.
    const refSuccessorCtx = { ...successorContext, entity: refEntityKey, pageDigest: pageView.installation.pageDigest };
    const postRefRes = await pages.sourceRead(h, actor, refSuccessorCtx, { sourceKey: 'refRecords', pageSize: 10 });
    h.check('Post-upgrade reference data source read succeeds', h.good(postRefRes), postRefRes);
    const postRefRows = pages.decodePage(postRefRes.data.value, refSuccessorCtx, 10, 'refRecords');
    const postRows = (await pages.scanPages(h, actor, { ...successorContext, pageDigest: pageView.installation.pageDigest })).rows;
    h.check('Upgraded runtime preserves exact V1 reference data without V2 overwrite or duplicate insert',
      postRefRows.length === 1 && postRefRows[0].id === preRefId && postRefRows[0].name === '初始参考字典' &&
      postRows.length === 1 && postRows[0].id === row.recordId, { postRefRows, postRows });
    // Verify compatible generated service, publication, subscription and existing ApiKey seamlessly hand off.
    const svcAfter = await read(h, generated.services + svc.serviceId), pubAfter = await read(h, generated.publications + svc.last.publications[0].id);
    const subAfter = await read(h, graph.subscriptions + sub.value.id), epAfter = await read(h, '/cas/namespaces/panel/endpoints/' + cred.value.endpointId);
    h.check('Compatible service, publication, subscription and Endpoint survive upgrade with successor provider binding',
      svcAfter.id === svc.serviceId && svcAfter.providerKey === j.target.receipt.runtimeApplicationUuid &&
      pubAfter.id === pub0.id && pubAfter.status === 2 && subAfter.id === sub.value.id && subAfter.status === 2 &&
      epAfter.id === cred.value.endpointId && epAfter.status === 2, { svcAfter, pubAfter, subAfter, epAfter });
    svc.last = generated.ownedSlice(await generated.snapshot(h), svc.serviceId); h.persist();
    const postGateway = await keyRead(h.admin.origin, opGetPath, cred.apiKey);
    h.check('Same pre-upgrade ApiKey continues serving through Gateway without re-subscribing',
      h.good(postGateway) && same(postGateway.data.value, row.created), postGateway);
    h.observe({ kind: 'model-upgrade-current-runtime', identity: successorContext.identity, runtime: pageView });
    await disposeRow(h, actor, row, successorContext, source);
    await business.cleanup(h, peerRow);
    await graph.retireCredential(h, cred); await graph.retire(h, sub);
    svc.source = j.target.receipt.runtimeApplicationUuid;
    svc.last = generated.ownedSlice(await generated.snapshot(h), svc.serviceId); h.persist();
    await generated.cleanup(h, svc);
    await h.ok(h.admin, 'PUT', '/cas/namespaces/panel/accounts/' + m.value.id + '/role-templates', { roleTemplateKeys: [ordinary.key], applicationScopes: [] });
    for (const tmpl of [epTemplate, group]) {
      await h.ok(h.admin, 'DELETE', '/cas/namespaces/panel/role-templates/' + tmpl.id);
      const tracked = h.state.resources.find(v => v.kind === 'role-template' && v.id === tmpl.id);
      if (tracked) { tracked.phase = 'deleted'; h.persist(); }
    }
    await authority.retireAccess(h, grant); j.phase = 'rows-disposed'; h.persist();
    await review.cleanup(h, target); await finishSource(h, source, target);
  } catch (error) { primary = error; throw error; }
  finally {
    try {
      if (cred?.resource?.phase === 'created' && !primary) await graph.retireCredential(h, cred);
      if (sub?.resource?.phase === 'created' && !primary) await graph.retire(h, sub);
      if (svc?.phase === 'created' && !primary) await generated.cleanup(h, svc);
    } finally {
      if (peerRow && peerRow.phase !== 'deleted') await business.finishCleanup(h, [peerRow], primary);
      await pages.disposeExplicitFixture(h, f, primary);
    }
  }
}
upgrade.transport = 'owner-api';
module.exports = { handlers: { 'F033-004': upgrade }, previewMatches, handoffMatches, createUpgrade, disposeRow, finishSource };
