// Public delivery decisions, exact request journals and paired owner teardown.
const { isDeepStrictEqual: same } = require('node:util');
const { fixture, cleanupPreviewRequest, requestCommand } = require('./delivery_cases.cjs');
const { sanitize } = require('./evidence_sanitizer.cjs');
const requests = '/panel/application/deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const reviews = '/panel/operations/namespaces/panel/application-deployment-requests/';
const installations = '/panel/application/installations/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(x => x.value);
const sorted = rows => [...rows].sort((a, b) => a.id - b.id);
const refusal = (r, message, code = 21) => [200, 400, 409].includes(r?.status) && r.data?.error?.code === code && r.data.error.message === message && r.data.value == null;
const reviewConflict = response => refusal(response, 'application deployment request cannot be reviewed') || refusal(response, 'application lifecycle is busy; refresh before retrying');
function actionValue(value) { const copy = structuredClone(value); delete copy.deploymentVersion; return copy; }
function installationUnchanged(before, after) {
  return Number.isSafeInteger(before?.deploymentVersion) && before.deploymentVersion > 0 && Number.isSafeInteger(after?.deploymentVersion) &&
    after.deploymentVersion >= before.deploymentVersion && same(actionValue(before), actionValue(after));
}
function historicalInstallationUnchanged(before, after) {
  // Panel only projects the deployment version on its current installation.
  // A predecessor is immutable history, not an alternate current projection.
  return !!before && !!after && !Object.hasOwn(before, 'deploymentVersion') &&
    !Object.hasOwn(after, 'deploymentVersion') && same(before, after);
}
function destroyConfirmed(h, c, after, installed) {
  const receipt = after.receipt?.uninstallation;
  return h.good(c.response) && same(sanitize(actionValue(c.response.data.value)), sanitize(actionValue(after))) && Number.isSafeInteger(after.deploymentVersion) && after.deploymentVersion > 0 &&
    after.status === 'uninstalled' && after.id === installed.id && after.deploymentId === installed.deploymentId && after.sourceDigest === installed.sourceDigest &&
    receipt?.dataDisposition === 'destroy' && receipt.finishedAt > 0 && !receipt.failedStep && receipt.authorization?.confirmed === true && receipt.recoveryStatus === 'recycled';
}
async function snapshot(h) {
  const result = {};
  for (const route of [requests, operations, installations]) result[route] = sorted(await h.directory(h.admin, route));
  return result;
}
function original(h, r) {
  if (r.scenarioCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original task scenario command unresolved; no replay or guessed teardown');
  if (!r.creation?.ownershipConfirmed || r.creation.outcome !== 'accepted' || r.creation.origin !== h.admin.origin || !same(r.creation.actorIdentity, h.admin.identity) || r.commands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original review intent or command unresolved; no replay or guessed teardown');
}
async function create(h, f, suffix, storageProvisioning = { mode: 'allocate' }) {
  const value = await h.create(requests, { sourceKind: 'model-package', packageId: f.package.id, expectedDigest: f.package.artifactDigest,
    instanceKey: h.state.prefix + '-' + suffix, instanceName: '审批回归 ' + suffix,
    storageProvisioning, reason: 'Verify public conditional review and exact delivery identity' }, 'deployment-review-request');
  const r = h.state.resources.find(v => v.kind === 'deployment-review-request' && v.id === value.id);
  r.commands = []; r.last = await read(h, requests + r.id); h.persist();
  h.check('New exact request is submitted without an operation or installed resource', same(r.last, value) && value.status === 'submitted' && !value.operationId && value.packageId === f.package.id && value.namespace === 'panel');
  return r;
}
async function command(h, r, actor, route, body) {
  original(h, r);
  const c = { route, body, actorIdentity: structuredClone(actor.identity), origin: actor.origin, outcome: 'unknown' };
  r.commands.push(c); h.persist();
  c.response = await h.api(actor, 'POST', route, body); h.persist(); return c;
}
async function rejectUnchanged(h, r, route, message) {
  const before = await snapshot(h), current = await read(h, requests + r.id);
  const version = route.startsWith(operations) ? (await read(h, route.slice(0, -'/cleanup'.length))).version : current.version;
  const c = await command(h, r, h.admin, route, { expectedVersion: version, reason: 'Guard live delivery authority from premature record cleanup' });
  const after = await snapshot(h);
  if (refusal(c.response, message) && same(before, after) && same(await read(h, requests + r.id), current)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Cleanup reaches exact owner state guard and preserves complete original delivery directories', c.outcome === 'rejected-and-unchanged', c.response);
}
async function settle(h, r, observeOperation = () => {}) {
  original(h, r);
  for (let n = 0; n < 180; n++) {
    r.last = await read(h, requests + r.id);
    if (!r.last.operationId) throw new h.Blocked('Approved request has no original operation; retain exact identity');
    r.operation = await read(h, operations + r.last.operationId); h.persist();
    observeOperation(r.last, r.operation);
    // The two public reads are not an atomic snapshot. Operation completion
    // can race the preceding request read; confirm the request again before
    // deciding that the pair disagrees.
    if (r.operation.status === 'succeeded' && r.last.status !== 'succeeded') { r.last = await read(h, requests + r.id); h.persist(); }
    if (['failed', 'cancelled'].includes(r.operation.status) || r.operation.status === 'succeeded' && r.last.status === 'succeeded') break;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  h.check('Exact approved operation and request finish successfully without replacement or retry', r.last.status === 'succeeded' && r.operation.status === 'succeeded' && r.operation.requestId === r.id && r.operation.packageId === r.last.packageId && r.operation.deploymentId === r.last.deploymentId && r.operation.planDigest === r.last.planDigest, r.operation);
  const owned = (await h.directory(h.admin, installations)).filter(v => v.deploymentId === r.last.deploymentId);
  h.check('Complete owner directory contains one ready installation for the single original delivery', owned.length === 1 && owned[0].status === 'ready' && owned[0].sourceDigest === r.creation.intended.expectedDigest, owned);
  r.installation = await read(h, installations + owned[0].id); h.persist();
  return r.installation;
}
async function runningOperation(h, r) {
  let current;
  for (let n = 0; n < 100; n++) {
    current = await read(h, operations + r.last.operationId);
    if (current.status !== 'queued') break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return current;
}
function removedSourceRequest(before) {
  if (before?.sourceKind !== 'model-package' || before.status !== 'succeeded' || before.packageRemoved !== false || !before.modelPackage) return undefined;
  const value = structuredClone(before);
  value.packageRemoved = true;
  delete value.modelPackage.sourceRevisionId;
  Object.assign(value.modelPackage, { createdBy: null, createTime: 0, updateTime: 0 });
  return value;
}
function successfulOperationFactsMatch(before, after) {
  if (same(before, after)) return true;
  const modes = ['forward', 'confirm-only', 'cleanup-required'];
  if (before?.status !== 'succeeded' || after?.status !== 'succeeded' ||
      !modes.includes(before.executionResumeMode) || !modes.includes(after.executionResumeMode)) return false;
  // Panel computes this diagnostic against the current clock on every read.
  // Keep all persisted facts (including versions, attempt and receipt) exact.
  return same({ ...before, executionResumeMode: after.executionResumeMode }, after);
}
async function originalHistory(h, r, current, operation) {
  if (!successfulOperationFactsMatch(r.operation, operation)) return false;
  if (same(current, r.last)) return true;
  const expected = removedSourceRequest(r.last), parents = h.state.resources.filter(v => v.kind === 'definition' && v.modelDelivery?.package?.id === r.last.packageId && v.modelDelivery.requests?.includes(r.id));
  if (!expected || !same(current, expected) || parents.length !== 1) return false;
  const parent = parents[0], d = parent.modelDelivery, delivery = require('./model_delivery.cjs');
  if (!parent.creation?.ownershipConfirmed || parent.creation.origin !== h.admin.origin || !same(parent.creation.actorIdentity, h.admin.identity) ||
      !delivery.packageRemovalMatches(h, parent) || !same(r.last.modelPackage, d.package) || d.package.sourceRevisionId !== d.revision?.id ||
      d.revision.applicationDefinitionId !== parent.id || d.revision.applicationUuid !== parent.creation.intended.uuid ||
      d.package.applicationUuid !== d.revision.applicationUuid) return false;
  const absence = await h.api(h.admin, 'GET', '/panel/application/model-packages/' + d.package.id);
  if (![200, 404].includes(absence.status) || absence.data?.error?.code !== 2 || absence.data.value != null) return false;
  const revision = await read(h, '/panel/application/definitions/' + parent.id + '/revisions/' + d.revision.id);
  if (!same(revision, d.revision)) return false;
  r.sourceRemovalHistoryProof = { packageId: d.package.id, packageAbsent: true, originalRequest: structuredClone(r.last),
    currentRequest: structuredClone(current), originalOperationUnchanged: true, revisionUnchanged: true, noCommandReplayed: true };
  h.persist(); return true;
}
async function cleanup(h, r) {
  if (r.modelUpgrade && r.modelUpgrade.phase !== 'complete') throw new h.Blocked('Original upgrade predecessor requires its exact completed successor disposition; no generic predecessor uninstall');
  if (r.storageRecovery && r.storageRecovery.phase !== 'complete') throw new h.Blocked('Original retained-storage lineage remains open; no generic predecessor destroy');
  await reconcile(h, r);
  original(h, r);
  const current = await read(h, requests + r.id);
  if (r.failedModelDisposition || current.status === 'failed' && current.sourceKind === 'model-package' && !r.installation)
    return require('./model_failure_cleanup.cjs').cleanup(h, r);
  if (!current.operationId) {
    if (!same(current, r.last)) throw new h.Blocked('Original unapproved review changed concurrently');
    if (current.status === 'rejected') {
      await requestCommand(h, r, 'cleanup'); r.phase = 'deleted'; h.persist();
      return { proof: 'Exact rejected request formally cleaned; independent exact absence and complete directory.' };
    }
    return cleanupPreviewRequest(h, r);
  }
  if (!r.installation) await settle(h, r);
  const installed = await read(h, installations + r.installation.id);
  let c = r.commands.find(v => v.route === installations + installed.id + '/uninstall' && v.outcome !== 'rejected-before-intent');
  if (!c) {
    if (!installationUnchanged(r.installation, installed) || installed.deploymentId !== current.deploymentId || installed.status !== 'ready') throw new h.Blocked('Exact approved installation changed before formal destroy; no guessed uninstall');
    c = await command(h, r, h.admin, installations + installed.id + '/uninstall', { expectedUpdateTime: installed.updateTime, expectedDigest: installed.sourceDigest,
      reason: 'Release only current-run conditional approval fixture', dataDisposition: 'destroy', confirmation: installed.applicationKey });
  }
  const after = await read(h, installations + installed.id), receipt = after.receipt?.uninstallation;
  h.check('Formal destroy and independent exact owner confirm complete retirement, authorization and recycled storage', destroyConfirmed(h, c, after, r.installation), after);
  c.outcome = 'confirmed'; r.retiredInstallation = after; h.persist();
  const schemas = await h.directory(h.admin, '/panel/storage-resources/database-schemas/');
  h.check('Independent storage directory confirms exact installation schema recycled', schemas.some(v => v.id === installed.receipt.database.schemaResourceId && v.status === 'recycled'), schemas);
  h.check('Successful original operation and request remain as durable delivery proof after uninstall', await originalHistory(h, r, await read(h, requests + r.id), await read(h, operations + r.operation.id)));
  r.phase = 'deleted'; h.persist();
  return { proof: 'Exact current-run model installation formally destroyed and storage recycled. Successful request, operation, installation and uninstall receipts intentionally retained as owner history; no historical deletion claim.' };
}
async function placement(h, r) {
  const options = (await h.ok(h.admin, 'GET', reviews + r.id + '/runtime-options')).values;
  const bases = options.filter(v => v.kind === 'base'), gateways = options.filter(v => v.kind === 'gateway');
  h.check('Approval explicitly chooses current available Base and Gateway from public options', bases.length === 1 && gateways.length === 1, options);
  return { executionInstanceId: bases[0].id, gatewayInstanceId: gateways[0].id };
}
async function approve(h, r, actors, { probeCleanup = false, probeCancel = false, observeOperation } = {}) {
  const runtimePlacement = await placement(h, r), body = { expectedVersion: r.last.version, reason: 'Approve exact frozen review fixture', runtimePlacement };
  original(h, r);
  // Persist both original intents before dispatch. Promise.all must observe both
  // replies even when one fails; never abandon a still-running mutation.
  const commands = actors.map(actor => ({ route: reviews + r.id + '/approve', body: structuredClone(body), actorIdentity: structuredClone(actor.identity), origin: actor.origin, outcome: 'unknown' }));
  r.commands.push(...commands); h.persist();
  const replies = await Promise.allSettled(commands.map(async (c, i) => { c.response = await h.api(actors[i], 'POST', c.route, c.body); h.persist(); }));
  if (replies.some(v => v.status === 'rejected')) throw new h.Blocked('Original concurrent approval transport unresolved; retain both intents without replay');
  const accepted = commands.filter(c => h.good(c.response));
  const refused = commands.filter(c => reviewConflict(c.response));
  r.last = await read(h, requests + r.id); h.persist();
  if (accepted.length === 1 && refused.length === actors.length - 1 && accepted[0].response.data.value.id === r.id && r.last.operationId === accepted[0].response.data.value.operationId) {
    for (const c of commands) c.outcome = h.good(c.response) ? 'confirmed' : 'rejected-and-unchanged'; h.persist();
  }
  h.check('Same-version reviewers produce exactly one accepted approval and exact state or control-lock conflict for every other command', accepted.length === 1 && refused.length === actors.length - 1 && accepted[0].response.data.value.id === r.id && r.last.operationId === accepted[0].response.data.value.operationId && r.last.reviewedBy?.accountId === actors[commands.indexOf(accepted[0])].id && r.last.reviewedBy?.namespace === 'panel',
    commands.map(c => ({ actor: c.actorIdentity, response: c.response })));
  for (const c of commands) c.outcome = h.good(c.response) ? 'confirmed' : 'rejected-and-unchanged';
  r.placement = runtimePlacement; h.persist();
  if (probeCleanup) {
    const route = operations + r.last.operationId, before = await runningOperation(h, r);
    if (before.status === 'running') {
      const c = await command(h, r, h.admin, route + '/cleanup', { expectedVersion: before.version, reason: 'Verify original in-progress operation cannot lose execution authority' });
      const after = await read(h, route);
      const binding = ['id', 'requestId', 'namespace', 'packageId', 'deploymentId', 'instanceKey', 'applicationUuid', 'planDigest'];
      // Execution may advance naturally during this rejected command. Its
      // durable identity must survive; a completed operation cannot prove the
      // in-progress timing requirement by itself.
      const stateRefused = refusal(c.response, 'only a fully cancelled deployment operation without an installation receipt can be cleaned');
      const versionRefused = refusal(c.response, 'application deployment state version does not match', 19);
      if ((stateRefused || versionRefused) && binding.every(key => same(before[key], after[key]))) {
        c.outcome = 'rejected-and-original-authority-retained'; h.persist();
      }
      h.check('Premature cleanup is rejected at the original operation state fence and retains its exact execution authority', c.outcome === 'rejected-and-original-authority-retained', c.response);
      r.executionCleanupGuard = { before, after, stateFenceReached: stateRefused, observedInProgressOnBothSides: stateRefused && after.status === 'running' }; h.persist();
      h.observe({ kind: 'real-in-progress-cleanup-guard', ...r.executionCleanupGuard });
    } else { r.executionCleanupGuard = { before, observedInProgressOnBothSides: false }; h.persist(); }
  }
  if (probeCancel) {
    const before = await runningOperation(h, r), requestBefore = await read(h, requests + r.id);
    if (before.status === 'running') {
      const c = await command(h, r, h.admin, requests + r.id + '/cancel', { expectedVersion: requestBefore.version, reason: 'Verify original running delivery cannot be withdrawn as an unexecuted request' });
      const after = await read(h, operations + r.last.operationId), requestAfter = await read(h, requests + r.id);
      const stateRefused = refusal(c.response, 'application deployment request cannot be cancelled') || refusal(c.response, 'application lifecycle is busy; refresh before retrying');
      const versionRefused = refusal(c.response, 'application deployment state version does not match', 19);
      const binding = ['id', 'namespace', 'packageId', 'deploymentId', 'instanceKey', 'sourceDigest', 'planDigest', 'operationId'];
      if ((stateRefused || versionRefused) && binding.every(key => same(requestBefore[key], requestAfter[key])) && after.id === before.id && after.requestId === r.id && after.planDigest === before.planDigest) {
        c.outcome = 'rejected-and-original-authority-retained'; h.persist();
      }
      h.check('Actual concurrent withdrawal is refused without revoking or replacing original executing authority', c.outcome === 'rejected-and-original-authority-retained', c.response);
      r.executingCancelGuard = { before, after, requestBefore, requestAfter, stateFenceReached: stateRefused, observedRunningOnBothSides: stateRefused && after.status === 'running' }; h.persist();
      h.observe({ kind: 'real-executing-withdrawal-guard', ...r.executingCancelGuard });
    } else { r.executingCancelGuard = { before, observedRunningOnBothSides: false }; h.persist(); }
  }
  const ops = (await h.directory(h.admin, operations)).filter(v => v.requestId === r.id);
  h.check('Independent complete operation directory contains exactly one operation with original request identity', ops.length === 1 && ops[0].id === r.last.operationId && ops[0].deploymentId === r.last.deploymentId, ops);
  await settle(h, r, observeOperation);
  const storage = r.creation.intended.storageProvisioning || { mode: 'allocate' }, database = r.installation.receipt.database;
  h.check('Successful delivery preserves frozen explicit approval choices and original selected storage intent', same(r.last.runtimePlacement, runtimePlacement) && r.last.resolvedRuntimePlacement?.execution.instanceId === runtimePlacement.executionInstanceId && r.last.resolvedRuntimePlacement?.gateway.instanceId === runtimePlacement.gatewayInstanceId &&
    database?.provisioningMode === storage.mode && database.bindingId > 0 && database.schemaResourceId > 0 &&
    (storage.mode !== 'restore' || database.recoveryDeploymentId === storage.recoveryDeploymentId && database.expectedResourceVersion === storage.expectedResourceVersion), { request: r.last, receipt: r.installation.receipt });
}
async function reconcile(h, r) {
  const pending = r.commands?.filter(c => c.outcome === 'unknown') || [];
  if (!pending.length) return;
  if (r.creation?.origin !== h.admin.origin || !same(r.creation?.actorIdentity, h.admin.identity) || !r.creation?.ownershipConfirmed) throw new h.Blocked('Original review recovery actor or owner proof changed');
  if (pending.length === 1 && r.installation && refusal(pending[0].response, 'unfinished authorization operation blocks this change: /panel/application/accessOperation', 19)) {
    const c = pending[0], linked = h.state.resources.filter(v => v.kind === 'member-access-retirement' && v.installation.id === r.installation.id &&
      v.origin === h.admin.origin && same(v.actorIdentity, h.admin.identity) && v.commands.some(command => command.execution?.response?.status === 409 &&
        command.execution.response.data?.error?.code === 19 && command.execution.response.data.error.message === 'application lifecycle changed before commit' &&
        command.body.accessLevel === '' && command.body.assignmentId === v.assignmentId && command.response?.data?.value?.installationId === r.installation.id));
    if (c.route !== installations + r.installation.id + '/uninstall' || c.origin !== h.admin.origin || !same(c.actorIdentity, h.admin.identity) || linked.length !== 1 ||
        c.body.expectedUpdateTime !== r.installation.updateTime || c.body.expectedDigest !== r.installation.sourceDigest || c.body.dataDisposition !== 'destroy' || c.body.confirmation !== r.installation.applicationKey)
      throw new h.Blocked('Original blocked uninstall lacks its exact authorization retirement binding');
    const current = await read(h, installations + r.installation.id), request = await read(h, requests + r.id);
    h.check('Explicit pending-authorization uninstall refusal preserves complete original ready installation and request',
      current.status === 'ready' && installationUnchanged(r.installation, current) && same(request, r.last));
    c.outcome = 'rejected-before-intent'; c.disposition = { proof: 'Exact owner NotApplied pending-authorization gate and independently unchanged full installation/request; original rejection retained. Subsequent cleanup requires its own current owner fences.', installation: current, request };
    h.persist(); return;
  }
  if (pending.some(c => !c.response || !(h.good(c.response) || reviewConflict(c.response)))) throw new h.Blocked('Original review intent or command unresolved; no replay or guessed teardown');
  const current = await read(h, requests + r.id);
  if (pending.every(c => c.route === reviews + r.id + '/approve')) {
    const accepted = pending.filter(c => h.good(c.response)), refused = pending.filter(c => reviewConflict(c.response));
    if (accepted.length !== 1 || accepted.length + refused.length !== pending.length) throw new h.Blocked('Original review responses do not prove exactly one approval; no replay');
    const ack = accepted[0].response.data.value;
    for (const key of ['id', 'namespace', 'packageId', 'deploymentId', 'instanceKey', 'sourceDigest', 'planDigest', 'operationId', 'requestedBy', 'reviewedBy', 'runtimePlacement', 'resolvedRuntimePlacement']) h.check('Original approved binding independently preserved: ' + key, same(ack[key], current[key]));
    const ops = (await h.directory(h.admin, operations)).filter(v => v.requestId === r.id);
    h.check('Original concurrent responses and independent directory confirm one exact operation', ops.length === 1 && ops[0].id === ack.operationId && ops[0].planDigest === ack.planDigest && ops[0].deploymentId === ack.deploymentId);
    for (const c of pending) { c.disposition = { originalOutcome: c.outcome, proof: 'Exact terminal approval/control-lock refusal, independent original frozen request and unique operation; no approval replay.' }; c.outcome = h.good(c.response) ? 'confirmed' : 'rejected-and-unchanged'; }
    r.last = current; h.persist(); return;
  }
  if (pending.length === 1 && r.installation && pending[0].route === installations + r.installation.id + '/uninstall') {
    const c = pending[0], after = await read(h, installations + r.installation.id);
    h.check('Original acknowledged destroy is independently confirmed without a second uninstall', destroyConfirmed(h, c, after, r.installation));
    c.disposition = { originalOutcome: c.outcome, proof: 'Original acknowledged terminal uninstall and current exact owner receipt including authorization and storage; action response omits read-only deploymentVersion. No uninstall replay.' };
    c.outcome = 'confirmed'; r.retiredInstallation = after; h.persist(); return;
  }
  throw new h.Blocked('Original review command needs an exact supported owner disposition; no replay');
}
async function reconcileGuard(h, r) {
  if (!same(r.creation?.actorIdentity, h.admin.identity) || r.creation?.origin !== h.admin.origin || !same(await read(h, requests + r.id), r.last)) throw new h.Blocked('Original cleanup guard actor or exact request changed');
  for (const c of r.commands) {
    if (c.outcome !== 'unknown') continue;
    const opRoute = operations + r.last.operationId;
    if (c.route !== opRoute + '/cleanup' || !refusal(c.response, 'only a fully cancelled deployment operation without an installation receipt can be cleaned')) throw new h.Blocked('Original cleanup guard has no exact terminal owner refusal');
    const op = await read(h, opRoute);
    h.check('Original refused cleanup preserves exact successful operation, original version, request, deployment and plan', op.status === 'succeeded' && op.id === r.last.operationId && op.version === c.body.expectedVersion && op.requestId === r.id && op.deploymentId === r.last.deploymentId && op.planDigest === r.last.planDigest);
    c.disposition = { originalOutcome: c.outcome, proof: 'Exact original terminal cleanup refusal and unchanged target request/operation version. Unrelated asynchronous deliveries caused broad snapshot drift; no cleanup replay.' };
    c.outcome = 'rejected-and-unchanged'; h.persist();
  }
  r.phase = 'deleted'; h.persist(); return { proof: 'Original target successful delivery authority independently retained after explicit refused cleanup; no replay.' };
}
async function peerSnapshot(h, f) {
  return Promise.all(f.installations.map(v => read(h, installations + v.id)));
}
async function reviewer(h) {
  const base = '/cas/namespaces/panel/', key = 'operations-application-deployment-reviewer';
  const roles = await h.directory(h.admin, base + 'roles/');
  h.check('Current owner registered human review role is available', roles.some(v => v.module === '/modules/kernel/runner' && v.key === key && v.humanAssignable && v.status === 2));
  const template = await h.create(base + 'role-templates/', { key: h.state.prefix + '-reviewer', name: '并发审批人', subjectType: 'account',
    roleRefs: [{ module: '/modules/kernel/runner', key }], applicationAccess: [], status: 2 }, 'role-template');
  const account = await h.create(base + 'accounts/', { account: h.state.prefix + '-reviewer', displayName: '独立审批人', password: h.state.password,
    roleTemplateKeys: ['portal-basic-user', template.key], status: 2 }, 'account');
  const actor = await h.login(account.account, h.state.password, 'panel', h.state.password + 'R'); actor.id = account.id;
  const current = await read(h, base + 'accounts/' + account.id);
  h.check('Independent CAS confirms distinct current reviewer account and effective owner role', actor.identity.account !== h.admin.identity.account && current.effectiveRoles?.some(v => v.module === '/modules/kernel/runner' && v.key === key));
  return actor;
}
async function decisions(h) {
  const f = await fixture(h), peers = await peerSnapshot(h, f), rejected = await create(h, f, 'reject');
  try {
    const before = await snapshot(h), c = await command(h, rejected, h.admin, reviews + rejected.id + '/reject', { expectedVersion: rejected.last.version, reason: 'Reject isolated fixture without provisioning' });
    rejected.last = await read(h, requests + rejected.id); h.persist();
    h.check('Formal rejection independently persists exact request and creates no execution', h.good(c.response) && same(c.response.data.value, rejected.last) && rejected.last.status === 'rejected' && !rejected.last.operationId && rejected.last.version === rejected.creation.response.data.value.version + 1, rejected.last);
    const after = await snapshot(h);
    h.check('Rejected request creates neither operation nor installation', same(before[operations], after[operations]) && same(before[installations], after[installations]));
    c.outcome = 'confirmed'; h.persist();
  } finally { await cleanup(h, rejected); }
  const approved = await create(h, f, 'approve');
  try { const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value; h.admin.id = session.account.id; await approve(h, approved, [h.admin]); }
  finally { await cleanup(h, approved); }
  h.check('Approval and rejection preserve both original peer instances and immutable package', same(await peerSnapshot(h, f), peers) && same(await read(h, '/panel/application/model-packages/' + f.package.id), f.package));
}
async function concurrent(h) {
  const f = await fixture(h), peers = await peerSnapshot(h, f), second = await reviewer(h);
  const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value; h.admin.id = session.account.id;
  const r = await create(h, f, 'concurrent');
  try { await approve(h, r, [h.admin, second]); }
  finally { await cleanup(h, r); }
  h.check('Concurrent approval and exact formal destroy preserve both unrelated original instances', same(await peerSnapshot(h, f), peers));
}
async function duplicateAndWithdraw(h) {
  const f = await fixture(h), peers = await peerSnapshot(h, f), first = await create(h, f, 'withdraw-first');
  let second;
  try {
    const before = await snapshot(h), repeat = await command(h, first, h.admin, requests, first.creation.intended);
    repeat.repeatOfConfirmedCreation = first.creation.journalId; h.persist();
    h.check('Deliberate repeated acknowledged intent returns exact original request, not a new identity', h.good(repeat.response) && same(repeat.response.data.value, first.last), repeat.response);
    h.check('Independent complete request, operation and installation directories are unchanged by same-intent repetition', same(await snapshot(h), before));
    repeat.outcome = 'confirmed'; h.persist();
    second = await create(h, f, 'withdraw-second');
    h.check('Same package accepts distinct legal instance intentions without deduplicating them together', second.id !== first.id && second.last.deploymentId !== first.last.deploymentId && second.last.instanceKey !== first.last.instanceKey && second.last.packageId === first.last.packageId);
    const runtimePlacement = await placement(h, second);
    await requestCommand(h, first, 'cancel');
    const cancelled = structuredClone(first.last), c = await command(h, first, h.admin, reviews + first.id + '/approve', { expectedVersion: cancelled.version, reason: 'Cancelled original request must never enter delivery', runtimePlacement });
    if (refusal(c.response, 'application deployment request cannot be reviewed') && same(await read(h, requests + first.id), cancelled) && !(await h.directory(h.admin, operations)).some(v => v.requestId === first.id) && !(await h.directory(h.admin, installations)).some(v => v.deploymentId === cancelled.deploymentId)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
    h.check('Original formally withdrawn request cannot be approved or create any execution/installation', c.outcome === 'rejected-and-unchanged', c.response);
    await cleanup(h, first);
    const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value; h.admin.id = session.account.id;
    await approve(h, second, [h.admin], { probeCancel: true });
    if (!second.executingCancelGuard?.observedRunningOnBothSides) await h.partial('Same-intent repetition, independent instance request and pre-execution withdrawal verified. Original running delivery finished before withdrawal concurrency could be observed on both sides.');
  } finally {
    if (second && second.phase !== 'deleted') await cleanup(h, second);
    if (first.phase !== 'deleted') await cleanup(h, first);
  }
  h.check('Duplicate and withdrawal probes preserve both unrelated original installed instances', same(await peerSnapshot(h, f), peers));
}
async function cleanupGuards(h) {
  const f = await fixture(h), r = await create(h, f, 'cleanup-guard');
  try {
    await rejectUnchanged(h, r, requests + r.id + '/cleanup', 'deployment request with an execution task must be cleaned from the deployment task');
    for (const saved of f.deploymentRequests) {
      const current = await read(h, requests + saved.id), op = await read(h, operations + current.operationId);
      const guard = { kind: 'deployment-review-guard', phase: 'created', creation: { ownershipConfirmed: true, outcome: 'accepted', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin }, commands: [], id: current.id, last: current };
      h.state.resources.push(guard); h.persist();
      await rejectUnchanged(h, guard, operations + op.id + '/cleanup', 'only a fully cancelled deployment operation without an installation receipt can be cleaned');
      await rejectUnchanged(h, guard, requests + current.id + '/cleanup', 'deployment request with an execution task must be cleaned from the deployment task');
      guard.phase = 'deleted'; h.persist();
    }
    const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value; h.admin.id = session.account.id;
    await approve(h, r, [h.admin], { probeCleanup: true });
    if (!r.executionCleanupGuard?.observedInProgressOnBothSides) await h.partial('Submitted and successful runtime-proof cleanup guards verified, but the original operation finished before the in-progress cleanup probe could be proven on both sides.');
  } finally { await cleanup(h, r); }
}
for (const fn of [decisions, concurrent, cleanupGuards, duplicateAndWithdraw]) fn.transport = 'owner-api';
module.exports = { handlers: { 'F027-003': duplicateAndWithdraw, 'F028-001': decisions, 'F028-002': concurrent, 'F030-002': cleanupGuards }, cleanup, originalHistory, successfulOperationFactsMatch, removedSourceRequest, refusal, original, approve, rejectUnchanged, reconcileGuard, destroyConfirmed, reviewConflict, settle, create, installationUnchanged, historicalInstallationUnchanged };
