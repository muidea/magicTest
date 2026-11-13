// Native runtime acceptance uses only formal Panel commands. Docker is read
// only: inspect exact IDs returned by the owner and read the probe's own file.
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const { sanitize } = require('./evidence_sanitizer.cjs');
const { build } = require('./native_package_cases.cjs');
const { cleanup: removePackage } = require('./native_provider_access_cases.cjs');
const { cleanupPreviewRequest } = require('./delivery_cases.cjs');
const requests = '/panel/application/deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const reviews = '/panel/operations/namespaces/panel/application-deployment-requests/';
const installations = '/panel/application/installations/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(v => v.value);
const pause = () => new Promise(resolve => setTimeout(resolve, 1000));
function original(h, r) {
  if (r.scenarioCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original native task scenario command unresolved; no retirement or replay');
  if (!r.creation?.ownershipConfirmed || r.creation.outcome !== 'accepted' || !same(r.creation.actorIdentity, h.admin.identity) || r.creation.origin !== h.admin.origin)
    throw new h.Blocked('Native runtime requires exact original acknowledged request and actor');
}
function commandBinding(h, r, c, value) {
  const ack = c.response?.data?.value;
  if (!h.good(c.response) || !ack || c.origin !== h.admin.origin || !same(c.actorIdentity, h.admin.identity)) return false;
  if (c.action === 'approve') return ack.id === r.id && ack.operationId > 0 && value.id === r.id && value.operationId === ack.operationId &&
    ['namespace', 'packageId', 'sourceDigest', 'instanceKey', 'deploymentId', 'planDigest'].every(k => same(ack[k], value[k]));
  const op = ack.packagedReceipt?.lifecycle, current = value.packagedReceipt?.lifecycle;
  return ack.id === r.installation?.id && value.id === ack.id && value.deploymentId === r.last.deploymentId &&
    ['namespace', 'applicationUuid', 'sourceDigest'].every(k => same(ack[k], r.installation[k]) && same(value[k], r.installation[k])) &&
    op?.action === 'uninstall' && op.id && current?.id === op.id && current.action === 'uninstall' &&
    current.requestVersion === op.requestVersion && current.reason === op.reason && same(current.requestedBy, op.requestedBy) &&
    (c.action === 'uninstall' ? op.requestVersion === c.body.expectedUpdateTime && op.reason === c.body.reason && op.requestedBy?.accountId === h.admin.id
      : c.action === 'lifecycle-review' && current.id === r.uninstallLifecycleId && current.reviewReason === c.body.reason && current.reviewedBy?.accountId === h.admin.id);
}
async function confirm(h, r, c) {
  original(h, r);
  const value = await read(h, c.action === 'approve' ? requests + r.id : installations + r.installation.id);
  if (!commandBinding(h, r, c, value)) throw new h.Blocked('Original native runtime command lacks matching acknowledgement and independent owner binding; no replay');
  c.outcome = 'confirmed';
  if (c.action === 'approve') r.last = value;
  else { r.currentInstallation = value; r.uninstallLifecycleId = value.packagedReceipt.lifecycle.id; }
  h.persist(); return value;
}
async function command(h, r, action, route, body) {
  original(h, r);
  if (r.commands.some(c => c.outcome !== 'confirmed')) throw new h.Blocked('Unresolved original native runtime write; no further command');
  const c = { action, route, body, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, 'POST', route, body); h.persist();
  return confirm(h, r, c);
}
async function settle(h, r, observeOperation = () => {}) {
  original(h, r);
  if (!r.last.operationId) throw new h.Blocked('Native request has no original operation');
  for (let n = 0; n < 120; n++) {
    r.operation = await read(h, operations + r.last.operationId); r.last = await read(h, requests + r.id); h.persist();
    observeOperation(r.last, r.operation);
    if (['succeeded', 'failed', 'cancelled'].includes(r.operation.status)) break;
    await pause();
  }
  h.check('Original native request and operation succeed with same exact plan and at least one real execution attempt', r.operation.status === 'succeeded' && r.last.status === 'succeeded' &&
    r.operation.requestId === r.id && r.operation.deploymentId === r.last.deploymentId && r.operation.planDigest === r.last.planDigest && r.operation.attempt > 0 && r.operation.finishTime >= r.operation.startTime, r.operation);
  const matches = (await h.directory(h.admin, installations)).filter(v => v.deploymentId === r.last.deploymentId);
  h.check('Complete owner directory contains one exact ready native installation', matches.length === 1 && matches[0].status === 'ready' && matches[0].runtimeType === 'packaged-runtime' && matches[0].sourceDigest === r.creation.intended.expectedDigest, matches);
  r.installation = await read(h, installations + matches[0].id); h.persist();
  h.check('Native receipt binds actual running components, local volume and completed runtime/ingress phases', r.installation.packagedReceipt?.ready === true &&
    r.installation.packagedReceipt.operationId === r.operation.id && same(r.installation.packagedReceipt.components?.map(c => c.key).sort(), Object.keys(r.input.contract.components).sort()) && r.installation.packagedReceipt.components.every(c => c.running === true) &&
    r.installation.packagedReceipt.volumes?.length === 1 && r.installation.packagedReceipt.volumes[0].prepared === true && r.installation.packagedReceipt.volumes[0].mounted === true, r.installation.packagedReceipt);
  return r.installation;
}
function inspect(h, r, run = execFileSync) {
  original(h, r);
  const component = r.installation?.packagedReceipt?.components?.find(v => v.key === 'api');
  if (!/^[a-f0-9]{64}$/.test(component?.containerId || '')) throw new h.Blocked('Exact original native component ID required before Docker read');
  const actual = JSON.parse(run('docker', ['inspect', component.containerId], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }))[0];
  if (actual.Id !== component.containerId || actual.Image !== component.imageId || actual.Config?.Labels?.['io.platform.deployment-id'] !== r.last.deploymentId ||
      actual.Config.Labels['io.platform.runtime.application-uuid'] !== r.installation.packagedReceipt.runtimeApplicationUuid)
    throw new h.Blocked('Native Docker identity or ownership differs from exact original owner receipt');
  const value = { id: actual.Id, imageId: actual.Image, name: actual.Name, running: actual.State?.Running,
    entrypoint: actual.Config.Entrypoint, command: actual.Config.Cmd, workingDir: actual.Config.WorkingDir,
    environment: actual.Config.Env.filter(v => v.startsWith('REGRESSION_MARKER=')),
    mounts: actual.Mounts.map(v => ({ type: v.Type, source: v.Source, destination: v.Destination, rw: v.RW })),
    networks: Object.entries(actual.NetworkSettings.Networks).map(([name, v]) => ({ name, aliases: v.Aliases || [] })),
    composeFile: actual.Config.Labels['com.docker.compose.project.config_files'] };
  h.check('Owner-provided native component is really running with exact configured entrypoint, command, directory and nonsecret Env', value.running === true &&
    same(value.entrypoint, r.input.contract.components.api.entrypoint) && same(value.command, r.input.contract.components.api.command) &&
    value.workingDir === '/data' && same(value.environment, ['REGRESSION_MARKER=' + r.marker]));
  h.check('Native runtime has exactly its declared writable managed mount and scoped service alias', value.mounts.length === 1 && value.mounts[0].type === 'bind' && value.mounts[0].destination === '/data' &&
    value.mounts[0].rw === true && value.mounts[0].source.includes('/apps/data/') && value.networks.length > 0 && value.networks.every(v => v.aliases.includes(value.name.slice(1)) && !v.aliases.includes('api')), value);
  const file = JSON.parse(run('docker', ['exec', component.containerId, 'cat', '/data/probe.json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }));
  h.check('Actual startup wrote exact configured value and concrete container hostname into its owned persistent volume', file.marker === r.marker && file.hostname === actual.Config.Hostname && file.hostname.length > 0);
  value.probeFile = file; h.observe({ kind: 'native-owned-runtime-read', value }); return value;
}
async function absentComponent(h, component, run = execFileSync) {
  if (!/^[a-f0-9]{64}$/.test(component.containerId || '')) throw new h.Blocked('Original exact native container ID missing');
  let absent = false;
  try { run('docker', ['inspect', component.containerId], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }); }
  catch (e) { absent = e.status === 1 && /No such (object|container)/i.test(String(e.stderr)); }
  h.check('Independent Docker read confirms original exact native container removed', absent, { containerId: component.containerId });
}
async function settledUninstall(h, r, readCurrent = () => read(h, installations + r.installation.id), wait = pause) {
  for (let n = 0; n < 120; n++) {
    const current = await readCurrent(), lifecycle = current.packagedReceipt?.lifecycle;
    if (current.id !== r.installation.id || current.deploymentId !== r.last.deploymentId || lifecycle?.id !== r.uninstallLifecycleId || lifecycle.action !== 'uninstall')
      throw new h.Blocked('Original native uninstall observation identity changed; no lifecycle replay');
    r.currentInstallation = current; h.persist();
    if (current.status === 'uninstallFailed' || current.status === 'uninstalled' && lifecycle.status === 'succeeded' && lifecycle.completionPending === false) return current;
    if (n < 119) await wait();
  }
  throw new h.Blocked('Original native uninstall final acknowledgment not observed within finite120-read budget; retain exact lifecycle');
}
async function cleanup(h, r) {
  if (r.phase === 'intent' && r.id == null) return reconcileIdentityRefusal(h, r);
  original(h, r);
  for (const c of r.commands.filter(v => v.outcome !== 'confirmed')) await confirm(h, r, c);
  r.last = await read(h, requests + r.id); h.persist();
  if (!r.last.operationId) return cleanupPreviewRequest(h, r);
  const currentOperation = await read(h, operations + r.last.operationId);
  if (!r.installation && (currentOperation.status === 'failed' || r.failureRetirement)) return retireFailed(h, r);
  if (!r.installation) await settle(h, r);
  let current = await read(h, installations + r.installation.id);
  if (!r.commands.some(c => c.action === 'uninstall')) {
    if (current.status !== 'ready' || !same(current, r.installation)) throw new h.Blocked('Original native installation changed before formal uninstall');
    current = await command(h, r, 'uninstall', installations + current.id + '/uninstall', { expectedUpdateTime: current.updateTime, expectedDigest: current.sourceDigest,
      reason: 'Release exact native regression instance ' + r.last.instanceKey, dataDisposition: 'retain', confirmation: current.applicationKey });
  }
  if (current.packagedReceipt?.lifecycle?.id !== r.uninstallLifecycleId) throw new h.Blocked('Original native uninstall operation identity changed');
  if (!r.commands.some(c => c.action === 'lifecycle-review')) {
    if (current.status !== 'uninstallRequested' || current.packagedReceipt.lifecycle.status !== 'awaitingApproval') throw new h.Blocked('Original native uninstall is not awaiting its required platform review');
    current = await command(h, r, 'lifecycle-review', '/panel/operations/namespaces/panel/application-installations/' + current.id + '/lifecycle-review',
      { expectedUpdateTime: current.updateTime, approve: true, reason: 'Approve exact native regression cleanup ' + r.last.instanceKey });
  }
  current = await settledUninstall(h, r);
  const receipt = current.packagedReceipt, lifecycle = receipt?.lifecycle;
  h.check('Formal platform-reviewed native uninstall completes exact lifecycle and explicitly retains each owned volume', current.status === 'uninstalled' &&
    current.deploymentId === r.last.deploymentId && lifecycle?.id === r.uninstallLifecycleId && lifecycle.action === 'uninstall' && lifecycle.status === 'succeeded' && !lifecycle.completionPending && !lifecycle.diagnostic &&
    receipt.components?.length === r.installation.packagedReceipt.components.length && receipt.components.every(v => v.removed === true && v.running === false) &&
    receipt.volumes?.length === 1 && receipt.volumes[0].retained === true && receipt.volumes[0].mounted === false, receipt);
  for (const c of r.installation.packagedReceipt.components) await absentComponent(h, c);
  h.check('Native cleanup retains exact successful request and operation as durable owner evidence', same(await read(h, requests + r.id), r.last) && same(await read(h, operations + r.operation.id), r.operation));
  r.phase = 'deleted'; r.retainedVolumes = receipt.volumes; h.persist();
  return { proof: 'Exact native instance uninstalled with required platform review; original component IDs absent. Owned local data volumes intentionally retained by formal native lifecycle contract; no directory deletion or physical-byte absence claim.', retainedVolumes: receipt.volumes };
}
function failedBinding(r, request, operation) {
  return request.id === r.id && request.operationId === operation.id && operation.requestId === r.id &&
    request.sourceKind === 'deployment-package' && operation.sourceKind === request.sourceKind && request.namespace === r.creation.actorIdentity.namespace &&
    operation.namespace === request.namespace && operation.applicationUuid === r.input.applicationUuid && request.sourceDigest === r.creation.intended.expectedDigest &&
    ['packageId', 'deploymentId', 'instanceKey', 'instanceName', 'planDigest'].every(k => same(operation[k], request[k])) &&
    request.packageId === r.creation.intended.packageId && request.instanceKey === r.creation.intended.instanceKey;
}
function terminationMatches(h, r, c, request, operation) {
  const before = c.beforeOperation, originalRequest = c.beforeRequest;
  return c.origin === h.admin.origin && same(c.actorIdentity, h.admin.identity) && h.good(c.response) &&
    same(c.response.data?.value, operation) && failedBinding(r, request, operation) && failedBinding(r, originalRequest, before) &&
    before.status === 'failed' && originalRequest.status === 'failed' && operation.status === 'cancelled' && operation.phase === 'terminated' &&
    request.status === 'cancelled' && operation.version === before.version + 1 && request.version === originalRequest.version + 1 &&
    (operation.failureCode ?? 0) === 0 && operation.failureMessage === 'terminated after cleanup: ' + c.body.reason && !operation.receiptRef &&
    ['id', 'requestId', 'packageId', 'namespace', 'applicationUuid', 'deploymentId', 'instanceKey', 'instanceName', 'planDigest', 'attempt', 'maxAttempts', 'startTime'].every(k => same(operation[k], before[k]));
}
async function retireFailed(h, r) {
  original(h, r);
  if (r.installation || r.commands.some(c => c.outcome !== 'confirmed')) throw new h.Blocked('Failed native retirement requires original confirmed approval without an installation');
  let request = await read(h, requests + r.id), operation = await read(h, operations + request.operationId);
  const siblings = await h.directory(h.admin, installations);
  if (!failedBinding(r, request, operation) || siblings.some(v => v.deploymentId === request.deploymentId))
    throw new h.Blocked('Original failed native operation binding or absence of installation unproven; no abort');
  let c = r.failureRetirement;
  if (!c) {
    if (request.status !== 'failed' || operation.status !== 'failed' || operation.receiptRef) throw new h.Blocked('Original native operation is not a failed uninstalled delivery');
    c = r.failureRetirement = { origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
      beforeRequest: request, beforeOperation: operation, route: operations + operation.id + '/cancel',
      body: { expectedVersion: operation.version, reason: 'Terminate exact failed native regression ' + request.instanceKey }, outcome: 'unknown' };
    h.persist(); c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
    request = await read(h, requests + r.id); operation = await read(h, operations + operation.id);
  }
  if (!terminationMatches(h, r, c, request, operation)) throw new h.Blocked('Original native termination not independently acknowledged; no cancel replay');
  h.check('Formal owner abort confirms exact failed native operation terminated with unchanged attempt budget and paired cancelled request', true, { request, operation });
  h.check('Complete independent installation directory excludes exact aborted deployment and preserves all original peer installations', same(await h.directory(h.admin, installations), siblings));
  c.outcome = 'confirmed'; r.last = request; r.operation = operation; r.phase = 'deleted'; h.persist();
  return { proof: 'Original exact failed native operation formally terminated; owner abort acknowledges original plan component removal. Request and operation retained with unchanged attempt budget and independent absence of matching installation; no physical-volume destruction claim.' };
}
async function confirmPackageDisposition(h, r, evidence, evidenceSha256, containers) {
  original(h, r);
  const c = r.failureRetirement, trace = evidence?.trace;
  if (!c || !Array.isArray(trace) || !/^sha256:[a-f0-9]{64}$/.test(evidenceSha256 || '') || !Array.isArray(containers) || containers.length !== 1)
    throw new h.Blocked('Original native abort and immutable cleanup/diagnosis proof required');
  const old = evidence.resources?.find(v => v.kind === r.kind && v.id === r.id);
  if (!old || !same(sanitize(old.failureRetirement), sanitize(c))) throw new h.Blocked('Original native abort differs from immutable failed cleanup');
  const owned = t => t.kind === 'request' && same(t.actor, h.admin.identity) && t.origin === h.admin.origin;
  const request = trace.find(t => owned(t) && t.method === 'GET' && t.route === requests + r.id && t.response?.data?.value?.status === 'cancelled');
  const operation = trace.find(t => owned(t) && t.method === 'GET' && t.route === operations + c.beforeOperation.id && t.response?.data?.value?.status === 'cancelled');
  if (!request || !operation || !terminationMatches(h, r, c, request.response.data.value, operation.response.data.value))
    throw new h.Blocked('Immutable cleanup does not prove paired original owner abort before package cleanup');
  const packageRoute = '/panel/application/deployment-packages/' + c.beforeRequest.packageId;
  const preview = trace.find(t => owned(t) && t.method === 'GET' && t.route === packageRoute + '/cleanup-preview' &&
    t.response?.data?.value?.allowed === true && t.response.data.value.sourceDigest === c.beforeRequest.sourceDigest);
  const removed = trace.find(t => owned(t) && t.method === 'DELETE' && t.route === packageRoute && h.good(t.response) &&
    t.response.data?.value?.id === c.beforeRequest.packageId && t.response.data.value.packageDigest === c.beforeRequest.sourceDigest);
  if (!preview || !removed || trace.indexOf(preview) >= trace.indexOf(removed) ||
    !['request', 'operation'].every(kind => preview.response.data.value.items.some(v => v.kind === kind && v.id === (kind === 'request' ? r.id : c.beforeOperation.id) && v.status === 'cancelled' && v.action === 'delete')))
    throw new h.Blocked('Original package owner lacks exact planned and acknowledged cancelled-record disposition');
  for (const route of [requests + r.id, operations + c.beforeOperation.id, packageRoute]) {
    const value = await h.api(h.admin, 'GET', route);
    h.check('Independent owner confirms exact linked retired task/package absent', [200, 404].includes(value.status) && value.data?.error?.code === 2 && value.data.value == null, value);
  }
  for (const route of [requests, operations]) h.check('Complete owner directory excludes original linked retired task',
    !(await h.directory(h.admin, route)).some(v => v.id === (route === requests ? r.id : c.beforeOperation.id)));
  h.check('Complete installation owner has no aborted original deployment', !(await h.directory(h.admin, installations)).some(v => v.deploymentId === c.beforeRequest.deploymentId));
  const container = containers[0];
  if (container.requestId !== r.id || container.operationId !== c.beforeOperation.id || container.deploymentId !== c.beforeRequest.deploymentId || container.intendedConfigurationMatched !== true)
    throw new h.Blocked('Original failed component diagnosis identity mismatch');
  await absentComponent(h, { containerId: container.containerId });
  r.packageDisposition = { evidenceSha256, packageId: c.beforeRequest.packageId, operationId: c.beforeOperation.id,
    containerId: container.containerId, proof: 'Exact acknowledged owner abort, paired immutable cancelled reads and package cleanup preview/DELETE formally disposed cancelled delivery records. Independent exact/complete owner reads and original Docker ID absence; failed evidence retained, no command replay or physical-volume destruction claim.' };
  c.outcome = 'confirmed-via-package-owner'; r.phase = 'deleted'; h.persist(); return r.packageDisposition;
}
async function reconcileIdentityRefusal(h, r) {
  const c = r.creation, response = c?.response, intended = c?.intended;
  if (r.kind !== 'native-runtime-request' || r.collection !== requests || r.phase !== 'intent' || r.id != null ||
      c?.outcome !== 'unconfirmed' || !same(c.actorIdentity, h.admin.identity) || c.origin !== h.admin.origin ||
      intended?.sourceKind !== 'deployment-package' || !intended.instanceKey || !intended.packageId || !intended.expectedDigest ||
      response?.status !== 500 || !same(response.data, { error: { code: 18, message: 'application deployment identity is inconsistent' }, value: null }))
    throw new h.Blocked('Exact original rejected native identity required; unknown or unrelated writes remain open');
  const packageRoute = '/panel/application/deployment-packages/' + intended.packageId;
  const packageRead = await h.api(h.admin, 'GET', packageRoute);
  let pkg, packageDisposition;
  if (h.good(packageRead)) pkg = packageRead.data.value;
  else {
    const evidence = h.originalCleanupEvidence, digest = h.originalCleanupSha256, bytes = h.originalCleanupBytes;
    const missing = [200, 404].includes(packageRead.status) && packageRead.data?.error?.code === 2 && packageRead.data.value == null;
    if (!missing || !Array.isArray(evidence?.trace) || !/^sha256:[a-f0-9]{64}$/.test(digest || '') ||
        !Buffer.isBuffer(bytes) || digest !== 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex') || !same(JSON.parse(bytes), evidence))
      throw new h.Blocked('Deleted native package requires exact immutable original cleanup proof; failed reads are not absence');
    const matches = evidence.resources?.filter(v => v.kind === 'native-package-probe' && v.package?.id === intended.packageId &&
      v.confirmed === true && v.phase === 'deleted' && v.packageAcknowledged === true && v.applicationUuid === v.package.applicationUuid &&
      v.package.packageDigest === intended.expectedDigest && same(v.actorIdentity, c.actorIdentity) && v.origin === c.origin);
    if (matches?.length !== 1) throw new h.Blocked('Original cleaned package owner identity is not uniquely acknowledged');
    const source = matches[0];
    const current = h.state.resources.filter(v => v.kind === source.kind && v.package?.id === intended.packageId);
    // Compare the safety-bearing build and delete journal, including original bytes/digest and actor.
    if (current.length !== 1 || !['phase', 'origin', 'actorIdentity', 'applicationUuid', 'package', 'packageAcknowledged', 'commands', 'preexistingIds'].every(k => same(sanitize(current[0][k]), sanitize(source[k]))))
      throw new h.Blocked('Current package journal differs from immutable original cleanup');
    const owned = t => t.kind === 'request' && same(t.actor, c.actorIdentity) && t.origin === c.origin;
    const trace = evidence.trace;
    const preview = trace.findIndex(t => owned(t) && t.method === 'GET' && t.route === packageRoute + '/cleanup-preview' &&
      h.good(t.response) && t.response.data.value?.allowed === true && t.response.data.value.sourceDigest === intended.expectedDigest &&
      t.response.data.value.packageId === intended.packageId && Array.isArray(t.response.data.value.items) &&
      t.response.data.value.items.every(v => ['package', 'deliveryFile'].includes(v.kind) && v.id === intended.packageId && v.action === 'delete') &&
      ['package', 'deliveryFile'].every(kind => t.response.data.value.items.some(v => v.kind === kind)));
    const removed = trace.findIndex(t => owned(t) && t.method === 'DELETE' && t.route === packageRoute && h.good(t.response) && same(sanitize(t.response.data.value), sanitize(source.package)));
    const build = source.commands.filter(v => v.method === 'POST' && v.route === '/panel/application/deployment-packages/builds/' &&
      v.outcome === 'confirmed' && same(v.actorIdentity, c.actorIdentity) && v.origin === c.origin && h.good(v.response) &&
      v.body.applicationUuid === source.applicationUuid && v.body.expectedBuildDigest === intended.expectedDigest && same(sanitize(v.response.data.value), sanitize(source.package)));
    const deletion = source.commands.filter(v => v.method === 'DELETE' && v.route === packageRoute && v.outcome === 'confirmed' &&
      same(v.actorIdentity, c.actorIdentity) && v.origin === c.origin && h.good(v.response) && same(sanitize(v.response.data.value), sanitize(source.package)));
    h.check('Immutable original build and ordered package-only cleanup prove the exact deleted source',
      build.length === 1 && deletion.length === 1 && preview >= 0 && removed > preview && Array.isArray(source.preexistingIds) && !source.preexistingIds.includes(intended.packageId));
    pkg = source.package;
    packageDisposition = { originalCleanupSha256: digest, proof: 'Original acknowledged build and package-only cleanup preview/DELETE; current exact package absence. No command replay.' };
  }
  h.check('Original rejected intent still binds the exact immutable native package', pkg.id === intended.packageId && pkg.packageDigest === intended.expectedDigest && /^[a-f0-9]{32}$/.test(pkg.applicationUuid));
  const peers = h.state.resources.filter(v => v !== r && v.kind === r.kind && v.phase === 'deleted' &&
    v.creation?.ownershipConfirmed && v.creation.intended?.instanceKey === intended.instanceKey &&
    same(v.creation.actorIdentity, c.actorIdentity) && v.creation.origin === c.origin &&
    v.currentInstallation?.status === 'uninstalled' && v.installation?.applicationUuid !== pkg.applicationUuid);
  h.check('Original run retained one acknowledged retired peer with the conflicting key and a different application UUID', peers.length === 1);
  const peer = peers[0], current = await read(h, installations + peer.installation.id);
  h.check('Independent owner confirms the exact retained peer identity and successful uninstall',
    current.id === peer.installation.id && current.deploymentId === peer.last.deploymentId && current.instanceKey === intended.instanceKey &&
    current.namespace === c.actorIdentity.namespace && current.applicationUuid === peer.installation.applicationUuid &&
    current.status === 'uninstalled' && current.packagedReceipt?.lifecycle?.id === peer.uninstallLifecycleId && current.packagedReceipt.lifecycle.status === 'succeeded');
  for (const route of [requests, operations]) {
    const rows = await h.directory(h.admin, route);
    h.check('Complete owner directory contains no request or operation for the original rejected package and key',
      !rows.some(v => v.packageId === intended.packageId || v.sourceDigest === intended.expectedDigest && v.instanceKey === intended.instanceKey));
  }
  const rows = await h.directory(h.admin, installations + 'history/');
  h.check('Complete owner installation history excludes the rejected exact application/key while retaining the exact retired peer',
    !rows.some(v => v.applicationUuid === pkg.applicationUuid && v.instanceKey === intended.instanceKey && v.namespace === c.actorIdentity.namespace) &&
    rows.filter(v => v.id === current.id && v.deploymentId === current.deploymentId && v.status === 'uninstalled').length === 1);
  if (!same(c.actorIdentity, h.admin.identity) || c.origin !== h.admin.origin) throw new h.Blocked('Original rejection actor changed during reconciliation');
  r.reconciliation = { kind: 'native-identity-refused-before-request-creation', originalJournalId: c.journalId,
    packageId: pkg.id, applicationUuid: pkg.applicationUuid, packageDisposition, peerInstallationId: current.id, peerDeploymentId: current.deploymentId,
    noCommandReplayed: true, proof: 'Exact identity refusal precedes request insertion; original immutable source and retired conflicting peer independently confirmed, complete request/operation/installation directories exclude rejected creation. Failed evidence and peer retained.' };
  r.phase = 'deleted'; h.persist(); return r.reconciliation;
}
function instanceKey(h, value, suffix) {
  const key = h.state.prefix + '-' + value.applicationUuid + '-' + suffix;
  if (!/^[a-f0-9]{32}$/.test(value.applicationUuid || '') || !/^[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(key))
    throw new h.Blocked('Native fixture requires an exact application UUID and safe instance key within the owner budget');
  return key;
}
function input(h, ingress) {
  // The managed volume excludes nginx's unprivileged worker. Keep its owner
  // permissions intact and explicitly run
  // this contained probe's nginx worker as its already-root startup identity.
  const command = 'set -eu\nprintf \'{"marker":"%s","hostname":"%s"}\\n\' "$REGRESSION_MARKER" "$(hostname)" > /data/probe.json\nprintf \'user root; events {} http { server { listen 8080; location / { root /data; } } }\\n\' > /data/nginx.conf\nexec nginx -g "daemon off;" -c /data/nginx.conf';
  const value = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-native-runtime-' + (ingress ? 'single' : 'dual'), releaseVersion: '1.0.0',
    contract: { apiVersion: 'magic.native-orchestration/v1', volumes: { data: { backend: 'localDirectory', scope: 'component', accessMode: 'singleWriter', consumers: ['api'], capacity: 1048576 } },
      components: { api: { image: 'muidea/magicwebportal:master', entrypoint: ['/bin/sh'], command: ['-c', command], workingDir: '/data', restart: 'no',
        environment: { REGRESSION_MARKER: { literal: h.state.prefix + '-native-probe' } }, ports: { http: { containerPort: 8080, protocol: 'http' } },
        readiness: { type: 'http', portRef: 'http', path: '/probe.json', timeoutSeconds: 5, retries: 5 }, mounts: [{ volumeRef: 'data', target: '/data' }] } } } };
  if (ingress) value.contract.ingresses = { web: { componentRef: 'api', portRef: 'http', hostnamePolicy: 'targetNamespaceDefault', pathPrefix: '/' + h.state.prefix + '-native-probe', pathHandling: 'stripPrefix', tlsPolicy: 'required', authPolicy: 'none' } };
  return value;
}
async function approveRequest(h, pkg, value, suffix) {
  if (pkg.applicationUuid !== value.applicationUuid) throw new h.Blocked('Native fixture package differs from its exact frozen application UUID');
  const key = instanceKey(h, value, suffix);
  const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value;
  h.admin.id = session.account.id;
  const v = await h.create(requests, { sourceKind: 'deployment-package', packageId: pkg.id, expectedDigest: pkg.packageDigest,
    instanceKey: key, instanceName: '原生运行验证 ' + suffix, reason: 'Check exact native configuration and isolation' }, 'native-runtime-request');
  const r = h.state.resources.find(vv => vv.kind === 'native-runtime-request' && vv.id === v.id);
  Object.assign(r, { input: structuredClone(value), marker: value.contract.components.api.environment.REGRESSION_MARKER.literal, commands: [], last: v }); h.persist();
  r.last = await read(h, requests + r.id); h.persist();
  h.check('Native request independently binds exact immutable source and original tenant before execution', same(r.last, v) && v.status === 'submitted' && !v.operationId && v.sourceKind === 'deployment-package' && v.sourceDigest === pkg.packageDigest && v.namespace === h.admin.identity.namespace);
  await command(h, r, 'approve', reviews + r.id + '/approve', { expectedVersion: r.last.version, reason: 'Approve exact current-run native configuration' });
  return r;
}
async function install(h, pkg, value, suffix, observeOperation) {
  const r = await approveRequest(h, pkg, value, suffix);
  await settle(h, r, observeOperation); return r;
}
async function run(h, dual, observeLayout = () => {}) {
  const f = await require('./delivery_cases.cjs').fixture(h), peers = [];
  for (const v of f.installations) peers.push(await read(h, installations + v.id));
  const value = input(h, !dual), pkg = await build(h, value), first = await install(h, pkg.package, value, dual ? 'first' : 'single');
  const a = inspect(h, first);
  observeLayout(first, a);
  if (dual) {
    const second = await install(h, pkg.package, value, 'second'), b = inspect(h, second);
    observeLayout(second, b);
    h.check('Same native package creates different tenant-bound installations, actual containers, scoped names and persistent mount roots', first.installation.id !== second.installation.id &&
      first.last.deploymentId !== second.last.deploymentId && a.id !== b.id && a.name !== b.name && a.mounts[0].source !== b.mounts[0].source &&
      a.probeFile.hostname !== b.probeFile.hostname && a.networks.every(n => !n.aliases.includes(b.name.slice(1))) && b.networks.every(n => !n.aliases.includes(a.name.slice(1))));
    h.check('Starting second instance preserves exact first runtime configuration and owned file', same(inspect(h, first), a));
    await cleanup(h, first);
    h.check('Uninstalling first instance preserves exact second container, mount and file', same(inspect(h, second), b));
    await cleanup(h, second);
  } else {
    const actor = await h.anonymous(h.admin.identity.namespace), route = value.contract.ingresses.web.pathPrefix + '/probe.json';
    let response;
    for (let n = 0; n < 20; n++) { response = await h.publicGet(actor, route); if (response.status === 200 && same(response.data, a.probeFile)) break; await pause(); }
    h.check('Actual tenant HTTPS ingress routes to exact mounted runtime probe and matches independent Docker read', response?.status === 200 && same(response.data, a.probeFile), response);
    await cleanup(h, first);
  }
  for (const [i, peer] of peers.entries()) h.check('Native runtime lifecycle preserves exact preexisting model peer installation ' + i, same(await read(h, installations + peer.id), peer));
  await removePackage(h, pkg);
}
const single = h => run(h, false), dual = h => run(h, true);
async function uninstallReview(h) {
  await run(h, true);
  await h.partial('Two actual native consumers, original platform-reviewed retain uninstall, exact Docker component absence, declared retained/unmounted volume receipts and peer runtime/file preservation implemented. Destroy disposition, shared application authorization owner retirement and full CAS/route/injected-copy residual reads remain open.');
}
async function packageSurvival(h) {
  const f = await require('./delivery_cases.cjs').fixture(h), peers = [];
  for (const peer of f.installations) peers.push(await read(h, installations + peer.id));
  const value = input(h, true), pkg = await build(h, value);
  const r = await install(h, pkg.package, value, 'package-survival');
  const before = inspect(h, r), installed = await read(h, installations + r.installation.id);
  const actor = await h.anonymous(h.admin.identity.namespace);
  const route = value.contract.ingresses.web.pathPrefix + '/probe.json';
  const call = async () => {
    let response;
    for (let n = 0; n < 20; n++) {
      response = await h.publicGet(actor, route);
      if (response.status === 200 && same(response.data, before.probeFile)) break;
      await pause();
    }
    h.check('Original tenant HTTPS service returns exact owned persistent data', response?.status === 200 && same(response.data, before.probeFile), response);
  };
  await call();
  // This helper requires an allowed owner preview, journals one exact DELETE
  // and independently proves absence. An unknown DELETE is never replayed.
  const disposition = await removePackage(h, pkg);
  h.observe({ kind: 'source-package-retired-with-live-installation', packageId: pkg.package.id,
    installationId: r.installation.id, requestId: r.id, operationId: r.operation.id, ...disposition });
  h.check('Removing source package preserves exact installation and successful durable delivery identities',
    same(await read(h, installations + installed.id), installed) && survivingRequest(r.last, await read(h, requests + r.id)) &&
    same(await read(h, operations + r.operation.id), r.operation));
  h.check('Exact original container, image, mount, configuration and persisted file survive source package removal', same(inspect(h, r), before));
  await call();
  for (const peer of peers) h.check('Package cleanup preserves unrelated exact installed model peer', same(await read(h, installations + peer.id), peer));
  await cleanup(h, r);
}
function survivingRequest(before, after) {
  if (before.packageRemoved !== false || after.packageRemoved !== true || before.sourceDiagnostic || after.sourceDiagnostic) return false;
  // The history view retains the declared display identity, not deleted File
  // references or generated preflight material. Compare every request fact and
  // the exact source-snapshot identity defined by its public history contract.
  const project = value => { const result = { ...value }; delete result.package; delete result.packageRemoved; return result; };
  return same(project(before), project(after)) && before.package && after.package &&
    ['id', 'applicationUuid', 'applicationName', 'releaseVersion', 'packageDigest', 'icon'].every(k => same(before.package[k], after.package[k]));
}
function expectedExitFailure(r) {
  const op = r.operation;
  return failedBinding(r, r.last, op) && r.last.status === 'failed' && op.status === 'failed' && op.phase === 'execution' &&
    op.attempt > 0 && op.attempt <= op.maxAttempts && op.failureCode === 6 && !op.receiptRef &&
    op.finishTime >= op.startTime && op.startTime > 0 &&
    /^native component api did not become ready: container exited before readiness \(status exited, exit code 23\); container status=exited, exit code=23, restarts=0, OOM killed=false$/.test(op.failureMessage);
}
function failedComponent(h, r, run = execFileSync) {
  original(h, r);
  if (!expectedExitFailure(r)) throw new h.Blocked('Exact intended nonzero-exit native failure required before Docker observation');
  const ids = run('docker', ['ps', '-aq', '--no-trunc', '--filter', 'label=io.platform.deployment-id=' + r.last.deploymentId], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim().split(/\s+/).filter(Boolean);
  if (ids.length !== 1 || !/^[a-f0-9]{64}$/.test(ids[0])) throw new h.Blocked('Exact original failed native component directory required');
  const c = JSON.parse(run('docker', ['inspect', ids[0]], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }))[0];
  const intended = r.input.contract.components.api;
  h.check('Independent Docker owner confirms exact intended component, failed startup and immutable deployment labels',
    c.Id === ids[0] && c.Config?.Labels?.['io.platform.deployment-id'] === r.last.deploymentId &&
    /^[a-f0-9]{32}$/.test(c.Config.Labels['io.platform.runtime.application-uuid'] || '') &&
    same(c.Config.Entrypoint, intended.entrypoint) && same(c.Config.Cmd, intended.command) && c.Config.WorkingDir === intended.workingDir &&
    c.State.Status === 'exited' && c.State.Running === false && c.State.ExitCode === 23 && c.State.OOMKilled === false && c.RestartCount === 0 &&
    c.Config.Env.includes('REGRESSION_MARKER=' + r.marker));
  const value = { containerId: c.Id, imageId: c.Image, deploymentId: r.last.deploymentId, state: c.State.Status, exitCode: c.State.ExitCode,
    mountRoots: c.Mounts.map(v => ({ source: v.Source, destination: v.Destination })) };
  r.failureObservation = value; h.persist(); h.observe({ kind: 'expected-native-startup-failure', value }); return value;
}
async function failedCleanup(h, observeFailure = async () => {}, observeTerminated = async () => {}) {
  const f = await require('./delivery_cases.cjs').fixture(h), peers = [];
  for (const peer of f.installations) peers.push(await read(h, installations + peer.id));
  const value = input(h, false);
  value.applicationName = h.state.prefix + '-expected-native-failure';
  value.contract.components.api.command = ['-c', 'exit 23'];
  const pkg = await build(h, value), r = await approveRequest(h, pkg.package, value, 'expected-failure');
  for (let n = 0; n < 120; n++) {
    r.operation = await read(h, operations + r.last.operationId); r.last = await read(h, requests + r.id); h.persist();
    if (['failed', 'cancelled', 'succeeded'].includes(r.operation.status) && r.last.status === r.operation.status) break;
    await pause();
  }
  h.observe({ kind: 'original-intended-native-failure-history', request: r.last, operation: r.operation });
  h.check('Actual approved delivery fails at intended nonzero-exit component readiness with original plan and execution budget', expectedExitFailure(r), r.operation);
  const component = failedComponent(h, r);
  const failure = structuredClone(r.operation);
  await observeFailure(r, component);
  await retireFailed(h, r);
  await absentComponent(h, component);
  await observeTerminated(r, component, failure);
  const preview = (await h.ok(h.admin, 'GET', '/panel/application/deployment-packages/' + pkg.package.id + '/cleanup-preview')).value;
  h.check('Owner cleanup preview allows deletion of exact cancelled task and paired request after formal component retirement',
    preview.allowed === true && preview.sourceDigest === pkg.package.packageDigest &&
    ['request', 'operation'].every(kind => preview.items.some(v => v.kind === kind && v.id === (kind === 'request' ? r.id : failure.id) && v.status === 'cancelled' && v.action === 'delete')), preview);
  await removePackage(h, pkg);
  for (const [route, id] of [[requests, r.id], [operations, failure.id]]) {
    const absent = await h.api(h.admin, 'GET', route + id);
    h.check('Independent exact owner and complete directory confirm original terminal delivery record removed',
      [200, 404].includes(absent.status) && absent.data?.error?.code === 2 && absent.data.value == null && !(await h.directory(h.admin, route)).some(v => v.id === id), absent);
  }
  h.check('No installation was created for the exact original failed delivery', !(await h.directory(h.admin, installations)).some(v => v.deploymentId === r.last.deploymentId));
  for (const peer of peers) h.check('Expected native failure and retirement preserve unrelated original model installation', same(await read(h, installations + peer.id), peer));
  h.observe({ kind: 'original-expected-failure-disposition', originalFailure: failure, container: component, requestId: r.id,
    proof: 'Original acknowledged failed task cancelled and exact container absent; allowed package cleanup removed terminal task and paired request. Failure history retained in immutable case evidence; no retry or budget reset, owned volume intentionally retained.' });
}
function layoutIdentity(r) {
  const segments = [r.last?.namespace, r.last?.deploymentId, r.input?.applicationName];
  if (segments.some(v => typeof v !== 'string' || !/^[A-Za-z0-9_-]+$/.test(v)) || !/^[a-f0-9]{32}$/.test(segments[1]))
    throw Error('Exact safe namespace, deployment and application path identities required');
  return segments;
}
function directoryLayout(h, config, r, view) {
  original(h, r);
  const [namespace, deploymentId, application] = layoutIdentity(r), roots = {};
  for (const category of ['config', 'compose', 'data', 'log', 'temp', 'runtime']) {
    const root = h.path.join(config.platformRoot, 'apps', category, namespace, deploymentId);
    const exists = h.fs.existsSync(root);
    if (exists) h.check('Existing exact owned application category has no symlink escape: ' + category,
      h.fs.realpathSync(root) === root && h.fs.statSync(root).isDirectory());
    roots[category] = { root, exists };
  }
  h.check('Actual native instance owns separate runtime/config/compose/data categories', ['runtime', 'config', 'compose', 'data'].every(v => roots[v].exists));
  const compose = h.path.join(roots.compose.root, application, 'docker-compose.yaml');
  const definition = h.path.join(roots.config.root, application, 'native-runtime.json');
  h.check('Actual Compose label projects the exact original namespace/deployment/application file',
    view.composeFile === '/var/app/application-runtime/compose/' + [namespace, deploymentId, application, 'docker-compose.yaml'].join('/') &&
    h.fs.realpathSync(compose) === compose && h.fs.statSync(compose).isFile());
  const frozen = JSON.parse(h.fs.readFileSync(definition)), component = frozen.components?.find(v => v.key === 'api');
  h.check('Generated native runtime config independently binds exact intended command and frozen actual image', frozen.apiVersion === 'magic.native-runtime/v1' &&
    same(component?.command, r.input.contract.components.api.command) && same(component?.entrypoint, r.input.contract.components.api.entrypoint) && component.imageDigest === view.imageId);
  const volume = h.path.join(roots.data.root, application, 'volumes/data');
  h.check('Actual native mount belongs only to exact original deployment data category', view.mounts.length === 1 && view.mounts[0].source === volume &&
    h.fs.realpathSync(volume) === volume && h.fs.statSync(volume).isDirectory());
  h.observe({ kind: 'exact-native-directory-layout', installationId: r.installation.id, deploymentId, namespace, application, roots,
    composeFile: compose, definitionFile: definition, volume, qualification: 'Metadata and generated nonsecret configuration only. Unused categories may be created lazily; no receipt/credential content read and no directory mutation.' });
  return roots;
}
function coreLayout(h, config, run = execFileSync) {
  const c = JSON.parse(run('docker', ['inspect', 'magicPanel'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }))[0];
  const projected = c.Mounts.filter(v => ['/var/app/config', '/var/app/data', '/var/app/log', '/var/app/temp', '/var/app/data/deployment-runtime'].includes(v.Destination) || v.Destination.startsWith('/var/app/application-runtime/'))
    .map(v => ({ source: v.Source, target: v.Destination, type: v.Type, writable: v.RW })).sort((a, b) => a.target.localeCompare(b.target));
  for (const [target, source] of [['/var/app/config', 'services/runtime/core/config/magicPanel'], ['/var/app/data', 'services/data/magicPanel'],
    ['/var/app/log', 'services/log/magicPanel'], ['/var/app/temp', 'services/temp/magicPanel'], ['/var/app/data/deployment-runtime', 'apps/runtime'],
    ...['config', 'compose', 'data', 'log', 'temp'].map(v => ['/var/app/application-runtime/' + v, 'apps/' + v])])
    h.check('Core Panel projects exact category without conflating application and platform owner: ' + target,
      projected.some(v => v.target === target && v.type === 'bind' && v.source === h.path.join(config.platformRoot, source)));
  return { id: c.Id, imageId: c.Image, mounts: projected };
}
async function directories(h) {
  await require('./delivery_cases.cjs').fixture(h);
  const config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig)), core = coreLayout(h, config), layouts = [];
  await run(h, true, (r, view) => layouts.push(directoryLayout(h, config, r, view)));
  h.check('Two native installations have distinct roots in every functional category', layouts.length === 2 && Object.keys(layouts[0]).every(v => layouts[0][v].root !== layouts[1][v].root));
  h.check('Normal dual native install/uninstall preserves exact core identity and service/application mount projections', same(coreLayout(h, config), core));
  h.observe({ kind: 'platform-core-category-layout', value: core, qualification: 'Exact core identity and public Docker mount metadata only; no credential content read.' });
}
uninstallReview.transport = single.transport = dual.transport = packageSurvival.transport = failedCleanup.transport = directories.transport = 'owner-api';
module.exports = { handlers: { 'F023-001': single, 'F023-003': dual, 'F033-002': uninstallReview, 'F031-001': packageSurvival, 'F030-001': failedCleanup, 'F061-001': directories }, original, commandBinding, confirm, inspect, cleanup, settledUninstall, input, install, approveRequest, retireFailed, failedBinding, terminationMatches, survivingRequest, confirmPackageDisposition, expectedExitFailure, failedComponent, failedCleanup, layoutIdentity, directoryLayout, instanceKey, reconcileIdentityRefusal };
