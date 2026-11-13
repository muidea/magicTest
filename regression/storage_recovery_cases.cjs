// Retain/restore uses the original deployment and storage owner facts. The
// original create identity stays immutable; deletion has its own successor
// intent, receipt and absence proof. Unknown outcomes are never replayed.
const { isDeepStrictEqual: same } = require('node:util');
const review = require('./deployment_review_cases.cjs');
const business = require('./business_cases.cjs');
const authority = require('./application_authority_cases.cjs');
const delivery = require('./model_delivery.cjs');
const installations = '/panel/application/installations/';
const requests = '/panel/application/deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const schemas = '/panel/storage-resources/database-schemas/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(v => v.value);
const projected = value => Object.fromEntries(Object.entries(value || {}).filter(([k]) => k !== 'deploymentVersion'));
const binding = value => Object.fromEntries(['bindingId', 'schemaResourceId', 'databaseResourceId'].map(k => [k, value?.receipt?.database?.[k]]));
const bound = value => Object.values(binding(value)).every(v => Number.isSafeInteger(v) && v > 0);
const absent = response => [200, 404].includes(response?.status) && response.data?.error?.code === 2 && response.data.value == null;
function original(h, r) {
  review.original(h, r);
  const j = r.storageRecovery;
  if (!j || j.origin !== h.admin.origin || !same(j.actorIdentity, h.admin.identity) || j.commands.some(c => c.outcome === 'unknown'))
    throw new h.Blocked('Original retained-storage actor or command unresolved; no replay or replacement teardown');
  return j;
}
function retainMatches(h, before, c, after) {
  const u = after?.receipt?.uninstallation;
  const stable = ['id', 'namespace', 'deploymentId', 'applicationUuid', 'applicationKey', 'sourceDigest', 'runtimeType', 'instanceKey', 'instanceName'];
  return c.method === 'POST' && c.route === installations + before.id + '/uninstall' && c.body?.expectedUpdateTime === before.updateTime &&
    c.body.expectedDigest === before.sourceDigest && c.body.dataDisposition === 'retain' && c.body.confirmation === before.applicationKey &&
    h.good(c.response) && same(projected(c.response.data.value), projected(after)) &&
    stable.every(k => same(before[k], after[k])) && bound(before) && same(before.receipt.database, after.receipt.database) &&
    after.status === 'uninstalled' && after.updateTime > before.updateTime &&
    Number.isSafeInteger(after.deploymentVersion) && after.deploymentVersion >= before.deploymentVersion &&
    u?.dataDisposition === 'retain' && u.recoveryStatus === 'available' && !u.claimedByInstallationId &&
    u.authorization?.confirmed === true && u.finishedAt > 0 && !u.failedStep &&
    u.reason === c.body.reason;
}
async function retain(h, r) {
  const j = original(h, r);
  if (j.phase !== 'prepared') throw new h.Blocked('Original retain already dispatched or wrong phase; no uninstall replay');
  const before = await read(h, installations + r.installation.id);
  if (!review.installationUnchanged(j.source, before) || before.status !== 'ready') throw new h.Blocked('Original ready installation changed before retain');
  original(h, r);
  const c = { method: 'POST', route: installations + before.id + '/uninstall', body: { expectedUpdateTime: before.updateTime,
    expectedDigest: before.sourceDigest, reason: 'Current-run original storage retention', dataDisposition: 'retain', confirmation: before.applicationKey },
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, before, outcome: 'unknown' };
  j.commands.push(c); j.phase = 'retaining'; h.persist();
  try { c.response = await h.api(h.admin, c.method, c.route, c.body); }
  catch (error) { c.transportError = error.message; }
  h.persist(); c.after = await read(h, installations + before.id); h.persist();
  if (same(h.admin.identity, c.actorIdentity) && h.admin.origin === c.origin && retainMatches(h, before, c, c.after)) {
    c.outcome = 'confirmed'; j.retained = c.after; j.phase = 'retained'; h.persist();
  }
  h.check('Original acknowledged retain and complete independent owner confirm available recovery without changing storage binding', c.outcome === 'confirmed', c);
  return c.after;
}
async function options(h, f) {
  const value = await read(h, installations + 'storage-options/?' + new URLSearchParams({ applicationUuid: f.application.uuid, sourceDigest: f.package.artifactDigest }));
  h.check('Formal storage options give an explicit complete recovery-point array', Array.isArray(value?.recoveryPoints));
  return value.recoveryPoints;
}
function pointMatches(source, points) {
  const matching = points.filter(p => p.deploymentId === source.deploymentId);
  return matching.length === 1 && same(matching[0], { deploymentId: source.deploymentId, applicationUuid: source.applicationUuid,
    applicationKey: source.applicationKey, sourceDigest: source.sourceDigest, uninstalledAt: source.receipt.uninstallation.finishedAt,
    resourceVersion: source.updateTime, recoveryStatus: 'available' });
}
async function schema(h, installation, status) {
  const all = await h.directory(h.admin, schemas), matching = all.filter(v => v.id === installation.receipt.database.schemaResourceId);
  h.check('Independent storage owner confirms exact original schema identity and lifecycle state', matching.length === 1 &&
    matching[0].databaseResourceId === installation.receipt.database.databaseResourceId && matching[0].status === status, matching);
  return matching[0];
}
async function createRestore(h, f, source) {
  const j = original(h, source), retained = j.retained;
  if (j.phase !== 'retained' || j.restoreRequestId || !retained || !pointMatches(retained, await options(h, f)) ||
      !review.installationUnchanged(retained, await read(h, installations + retained.id)))
    throw new h.Blocked('Exact available original recovery selection missing or changed; no new restore intent');
  original(h, source);
  j.phase = 'restoring'; h.persist();
  const value = await h.create(requests, { sourceKind: 'model-package', packageId: f.package.id, expectedDigest: f.package.artifactDigest,
    instanceKey: retained.instanceKey, instanceName: retained.instanceName,
    storageProvisioning: { mode: 'restore', recoveryDeploymentId: retained.deploymentId, expectedResourceVersion: retained.updateTime },
    reason: 'Restore only the exact current-run formally retained binding' }, 'deployment-review-request');
  const r = h.state.resources.find(v => v.kind === 'deployment-review-request' && v.id === value.id);
  // Even a failed/unknown create is protected by the source journal phase and
  // the submitted original instance identity; it is never created a second time.
  r.commands = []; r.last = await read(h, requests + r.id);
  j.restoreRequestId = r.id; j.requestIds.push(r.id); delivery.linkRequest(h, f, r); h.persist();
  h.check('Exact original restore request is submitted once with original deployment/key and frozen selection', same(value, r.last) && value.status === 'submitted' &&
    !value.operationId && value.namespace === retained.namespace && value.packageId === f.package.id && value.deploymentId === retained.deploymentId &&
    value.instanceKey === retained.instanceKey && value.instanceName === retained.instanceName && same(value.storageProvisioning, r.creation.intended.storageProvisioning), r.last);
  return r;
}
function restoredMatches(j, r, source) {
  const a = j.source, retained = j.retained, target = r.installation, db = target?.receipt?.database;
  const u = source?.receipt?.uninstallation, auth = target?.receipt?.authorizationRestore;
  if (!target || !bound(target) || target.id === a.id || target.previousInstallationId !== a.id || target.status !== 'ready' ||
      !['namespace', 'deploymentId', 'applicationUuid', 'applicationKey', 'instanceKey', 'instanceName', 'sourceDigest'].every(k => same(a[k], target[k])) ||
      !same(binding(a), binding(target)) || db.provisioningMode !== 'restore' || db.recoveryDeploymentId !== a.deploymentId ||
      db.expectedResourceVersion !== retained.updateTime || source.id !== a.id || source.status !== 'uninstalled' || source.updateTime <= retained.updateTime ||
      !same(source.receipt.database, retained.receipt.database) || u?.dataDisposition !== 'retain' || u.recoveryStatus !== 'claimed' ||
      u.claimedByInstallationId !== target.id || !same({ ...u, recoveryStatus: 'available', claimedByInstallationId: undefined },
        { ...retained.receipt.uninstallation, claimedByInstallationId: undefined })) return false;
  // No broad ignored fields: claim is the only permitted predecessor change.
  const expected = structuredClone(retained);
  expected.updateTime = source.updateTime; delete expected.deploymentVersion;
  expected.receipt.uninstallation = structuredClone(u);
  return review.historicalInstallationUnchanged(expected, source) &&
    Number.isSafeInteger(retained.deploymentVersion) && retained.deploymentVersion > 0 &&
    Number.isSafeInteger(target.deploymentVersion) && target.deploymentVersion > retained.deploymentVersion &&
    target.operationId === 'deployment:' + r.operation.id && target.receipt.deploymentOperationId === r.operation.id &&
    auth?.confirmed === true && auth.intent?.sourceInstallationId === a.id && auth.intent.installationId === target.id &&
    auth.intent.resourceVersion === retained.updateTime && auth.intent.operationId === target.operationId &&
    auth.intent.profile?.installationId === target.id && same(auth.intent.retirement, u.authorization?.intent);
}
async function disposeRow(h, actor, row, context, source) {
  const j = original(h, source);
  if (j.phase !== 'restored' || row.scenarioRecoveryRequestId !== source.id || row.successorDisposition ||
      row.origin !== actor.origin || !same(row.actorIdentity, actor.identity) || row.commands.some(c => c.outcome === 'unknown') ||
      row.identity.installationId !== String(j.source.id) || context.identity.installationId !== String(j.target.id) ||
      context.identity.deploymentId !== row.identity.deploymentId || context.identity.namespace !== row.identity.namespace ||
      context.entity !== row.entity || context.applicationKey !== row.applicationKey || !business.installationMatches(j.fixture, j.target, context.identity) ||
      !review.installationUnchanged(j.target, await read(h, installations + j.target.id)))
    throw new h.Blocked('Exact original row and current restored successor required; no obsolete-fence or repeated delete');
  const before = await business.record(h, actor, { ...context, recordId: row.recordId });
  h.check('Successor independently reads the same complete original business row and version before conditional delete', h.good(before) && same(before.data.value, row.created) && String(before.data.value.version) === row.version, before);
  const current = { ...context, recordId: row.recordId, version: row.version, origin: row.origin, actorIdentity: structuredClone(row.actorIdentity), commands: [], phase: 'created' };
  delete current.ui;
  // Persist before business.execute creates and sends the single delete intent.
  row.successorDisposition = current; h.persist();
  const actorIdentity = structuredClone(actor.identity), origin = actor.origin;
  await business.execute(h, actor, current, business.request(current, 'delete'));
  h.check('Successor delete receipt and independent current owner prove exact original row absence without rewriting original create identity',
    actor.origin === origin && same(actor.identity, actorIdentity) && current.commands.length === 1 && current.commands[0].outcome === 'confirmed' &&
    absent(await business.record(h, actor, current)) && row.commands.every(c => c.body.identity.installationId === String(j.source.id)));
  current.phase = 'deleted'; row.phase = 'deleted'; h.persist();
}
async function finishSource(h, source, target) {
  const j = original(h, source);
  review.original(h, target);
  if (j.phase !== 'rows-disposed' || target.id !== j.restoreRequestId || target.phase !== 'deleted' || !target.retiredInstallation ||
      !same(target.installation, j.target) || !restoredMatches(j, target, j.claimed) ||
      !review.destroyConfirmed(h, target.commands.find(c => c.route === installations + j.target.id + '/uninstall') || {}, target.retiredInstallation, j.target) ||
      h.state.resources.some(v => v.scenarioRecoveryRequestId === source.id && v.phase !== 'deleted'))
    throw new h.Blocked('Original recovery source requires exact claimed successor formal destroy and all original row dispositions');
  const claimed = await read(h, installations + j.source.id), retired = await read(h, installations + j.target.id);
  h.check('Original claimed recovery history remains exact and the same successor independently confirms complete destroy',
    review.historicalInstallationUnchanged(j.claimed, claimed) && review.installationUnchanged(target.retiredInstallation, retired));
  await schema(h, j.target, 'recycled');
  const points = await options(h, j.fixture);
  h.check('Exact consumed original recovery point is unavailable after successor destroy', !points.some(p => p.deploymentId === j.source.deploymentId));
  h.check('Original predecessor delivery request and operation remain durable and unchanged after successor disposal',
    await review.originalHistory(h, source, await read(h, requests + source.id), await read(h, operations + source.operation.id)));
  original(h, source);
  j.phase = 'complete'; source.phase = 'deleted';
  source.retentionProof = { proof: 'Original retain point claimed by exact formally destroyed successor; same schema independently recycled, original point unavailable. Predecessor and all delivery/authorization receipts retained; no second predecessor uninstall.',
    predecessorId: j.source.id, successorId: j.target.id, schemaResourceId: j.target.receipt.database.schemaResourceId };
  h.persist(); return source.retentionProof;
}
async function recovery(h) {
  const pages = require('./page_runtime_cases.cjs');
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'storagerecovery', requestPrefix: 'storage-recovery-' });
  const actor = await business.member(h, 'manager'), source = f.pageRequests[0], peer = f.pageRequests[1];
  let row, peerRow, target, fresh, grant, primary;
  try {
    const originalContext = await business.runtime(h, f, 0, actor), peerContext = await business.runtime(h, f, 1, actor);
    row = await business.create(h, { ...originalContext, scenarioDefinitionId: f.application.id, scenarioRecoveryRequestId: source.id }, 'retained-original');
    peerRow = await business.create(h, { ...peerContext, scenarioDefinitionId: f.application.id }, 'retained-peer');
    const j = source.storageRecovery = { phase: 'prepared', source: structuredClone(source.installation), definitionId: f.application.id,
      requestIds: f.pageRequests.map(r => r.id), installationIds: f.installations.map(i => String(i.id)), commands: [],
      origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
      fixture: { application: f.application, revision: f.revision, package: f.package } };
    h.persist();
    await authority.retireAccess(h, f.pageGrants[0]);
    await retain(h, source);
    const retainedSchema = await schema(h, j.retained, 'disabled');
    h.check('Formal recovery selector binds only the exact original retained deployment/version', pointMatches(j.retained, await options(h, f)));
    fresh = await review.create(h, f, 'storage-new-allocation'); j.requestIds.push(fresh.id); delivery.linkRequest(h, f, fresh); h.persist();
    await review.approve(h, fresh, [h.admin]); j.installationIds.push(String(fresh.installation.id)); h.persist();
    h.check('Independent new allocation uses different deployment/binding/schema and does not consume original point', fresh.installation.deploymentId !== j.source.deploymentId &&
      fresh.installation.receipt.database.bindingId !== binding(j.source).bindingId && fresh.installation.receipt.database.schemaResourceId !== binding(j.source).schemaResourceId &&
      pointMatches(j.retained, await options(h, f)));
    target = await createRestore(h, f, source);
    await review.approve(h, target, [h.admin]); j.installationIds.push(String(target.installation.id)); h.persist();
    j.claimed = await read(h, installations + j.source.id);
    h.check('Independent original source and successor prove one exact storage and authorization restoration handoff', restoredMatches(j, target, j.claimed), { source: j.claimed, target: target.installation });
    j.target = structuredClone(target.installation); j.phase = 'restored'; h.persist();
    const activeSchema = await schema(h, j.target, 'active');
    h.check('Restored original physical schema name and database identity are preserved', activeSchema.name === retainedSchema.name && activeSchema.databaseName === retainedSchema.databaseName);
    h.check('Claimed original point cannot be selected again', !(await options(h, f)).some(p => p.deploymentId === j.source.deploymentId));
    const bindings = await h.directory(h.admin, '/cas/namespaces/panel/subject-role-bindings/?' + new URLSearchParams({ subjectId: f.pageGrants[0].accountId + '|=', subjectType: 'account|=' }));
    h.check('Storage restore does not resurrect the explicitly retired original ordinary member binding', !bindings.some(b => b.status === 2 &&
      (b.roleModule === '/applications/' + j.source.deploymentId || b.applicationAccess?.some(a => a.applicationUuid === j.source.deploymentId))));
    h.inaccessible(await h.api(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + j.target.deploymentId), 'Original independently revoked ordinary account remains unable to enter the restored instance');
    grant = { kind: 'member-access-retirement', phase: 'created', accountId: f.pageGrants[0].accountId, installation: j.target, commands: [], active: false,
      origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity) };
    h.state.resources.push(grant); h.persist(); await authority.accessCommand(h, grant, 'manager', 0);
    const currentFixture = { ...f, installations: [j.target, peer.installation, fresh.installation] }, context = await business.runtime(h, currentFixture, 0, actor);
    h.check('Restored runtime uses owner-issued new installation identity and positive fences while preserving deployment', context.identity.installationId !== row.identity.installationId &&
      context.identity.deploymentId === row.identity.deploymentId && Number.isSafeInteger(context.identity.generation) && context.identity.generation > 0 &&
      Number.isSafeInteger(context.identity.executionEpoch) && context.identity.executionEpoch > 0);
    const stale = await business.record(h, actor, row);
    h.check('Original stale read fence reaches exact owner identity conflict after new current access is granted', [200, 409].includes(stale.status) &&
      stale.data?.error?.code === 19 && stale.data.error.message === '精确安装读取身份已变化' && stale.data.value == null, stale);
    // A separate fresh grant proves isolation; it is never called restoration
    // of the old member binding.
    const freshGrant = { ...grant, installation: fresh.installation, commands: [], assignmentId: undefined, active: false, phase: 'created' };
    h.state.resources.push(freshGrant); h.persist(); await authority.accessCommand(h, freshGrant, 'manager', 0);
    const allocated = await business.runtime(h, currentFixture, 2, actor);
    h.check('New allocation cannot read the original retained primary key', absent(await business.record(h, actor, { ...allocated, recordId: row.recordId })));
    h.check('Unrelated peer preserves complete original business row and installation across retain/restore', same((await business.record(h, actor, peerRow)).data.value, peerRow.created) &&
      review.installationUnchanged(peer.installation, await read(h, installations + peer.installation.id)));
    await disposeRow(h, actor, row, context, source);
    await business.cleanup(h, peerRow);
    await authority.retireAccess(h, grant); await authority.retireAccess(h, freshGrant);
    j.phase = 'rows-disposed'; h.persist();
    await review.cleanup(h, target); await review.cleanup(h, fresh);
    await finishSource(h, source, target);
    h.observe({ kind: 'retained-storage-original-lineage', ...source.retentionProof, originalIdentity: row.identity, successorIdentity: context.identity,
      originalCreate: row.commands[0].receipt, successorDelete: row.successorDisposition.commands[0].receipt });
  } catch (error) { primary = error; throw error; }
  finally {
    if (peerRow?.phase !== 'deleted' && peerRow) await business.finishCleanup(h, [peerRow], primary);
    await pages.disposeExplicitFixture(h, f, primary);
  }
  await h.partial('Original retain/restore binding, exact point/version, schema and complete business data, separate new allocation, revoked-member non-resurrection, new runtime fence, successor reliable delete and formal destroy lineage. Active-member restoration, concurrent claim/stale selection, response-loss recovery, cross-tenant and in-flight/replay matrices remain unverified.');
}
recovery.transport = 'owner-api';
module.exports = { handlers: { 'F048-003': recovery }, retain, retainMatches, pointMatches, restoredMatches, createRestore, disposeRow, finishSource };
