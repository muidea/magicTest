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
  const pages = require('./page_runtime_cases.cjs'), author = require('./page_author_cases.cjs').authorFixture;
  const f = await pages.explicitFixture(h, null, null, { suffix: 'modelupgrade', requestPrefix: 'model-upgrade-' });
  const actor = await business.member(h, 'manager'), source = f.pageRequests[0], grant = f.pageGrants[0];
  let row, peerRow, target, primary;
  try {
    const context = await business.runtime(h, f, 0, actor), peer = await business.runtime(h, f, 1, actor);
    row = await business.create(h, { ...context, scenarioDefinitionId: f.application.id }, 'upgrade-original');
    peerRow = await business.create(h, { ...peer, scenarioDefinitionId: f.application.id }, 'upgrade-peer');
    const beforePages = await author.read(h, f.application, 'pages'), content = structuredClone(beforePages.content);
    content.pages[0].title = '新冻结维护窗口页面';
    await author.save(h, f.application, 'pages', beforePages, content);
    const next = await delivery.publishNext(h, f);
    const j = { phase: 'prepared', source: await read(h, installations + source.installation.id), actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
      definitionId: f.application.id, requestIds: [source.id], installationIds: [String(source.installation.id)], fixture: { application: next.application, revision: next.revision, package: next.package } };
    source.modelUpgrade = j; row.scenarioUpgradeRequestId = source.id; h.persist();
    j.originalAssignment = (await h.directory(h.admin, installations + j.source.id + '/assignments/')).find(v => v.id === grant.assignmentId);
    h.check('Original active member assignment belongs to exact predecessor before maintenance', j.originalAssignment?.installationId === j.source.id &&
      j.originalAssignment.subjectId === grant.accountId && j.originalAssignment.accessLevel === 'manager', j.originalAssignment);
    target = await createUpgrade(h, source, next);
    await review.approve(h, target, [h.admin]);
    j.target = target.installation; j.installationIds.push(String(j.target.id)); j.handoffSource = await read(h, installations + j.source.id); h.persist();
    h.check('Real maintenance upgrade preserves deployment and physical Schema while switching runtime identity with complete predecessor handoff receipt', handoffMatches(j, target, j.handoffSource), { source: j.handoffSource, target: j.target });
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
    h.observe({ kind: 'model-upgrade-current-runtime', identity: successorContext.identity, runtime: pageView });
    await disposeRow(h, actor, row, successorContext, source);
    await business.cleanup(h, peerRow);
    await authority.retireAccess(h, grant); j.phase = 'rows-disposed'; h.persist();
    await review.cleanup(h, target); await finishSource(h, source, target);
  } catch (error) { primary = error; throw error; }
  finally {
    if (peerRow && peerRow.phase !== 'deleted') await business.finishCleanup(h, [peerRow], primary);
    await pages.disposeExplicitFixture(h, f, primary);
  }
  await h.partial('Same-definition newer immutable revision, formal upgrade preview/request/approval, exact completed predecessor handoff, preserved deployment/Schema and original member with new runtime identity, complete original business read/write/delete, peer preservation and successor-only destroy lineage implemented. Nonempty reference data preservation, compatible services/publications/subscriptions/Keys and full maintenance route/drain evidence remain open.');
}
upgrade.transport = 'owner-api';
module.exports = { handlers: { 'F033-004': upgrade }, previewMatches, handoffMatches, createUpgrade, disposeRow, finishSource };
