// Dispose the original failed model delivery through its public owners only.
const { isDeepStrictEqual: same } = require('node:util');
const requests = '/panel/application/deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const installations = '/panel/application/installations/';
const packages = '/panel/application/model-packages/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(v => v.value);
function binding(h, r, request, operation, pkg, installation) {
  const approvals = r.commands?.filter(c => c.route === '/panel/operations/namespaces/panel/application-deployment-requests/' + r.id + '/approve' && c.outcome === 'confirmed' && c.response && h.good(c.response));
  const approval = approvals?.length === 1 ? approvals[0] : null;
  const initial = r.creation?.response?.data?.value;
  return r.kind === 'deployment-review-request' && Number.isSafeInteger(r.id) && r.id > 0 && r.creation?.ownershipConfirmed && r.creation.outcome === 'accepted' &&
    r.creation.origin === h.admin.origin && same(r.creation.actorIdentity, h.admin.identity) &&
    request?.id === r.id && initial?.id === r.id && initial.namespace === request.namespace &&
    initial.packageId === request.packageId && initial.sourceDigest === request.sourceDigest && initial.deploymentId === request.deploymentId && initial.instanceKey === request.instanceKey &&
    request.namespace === h.admin.identity.namespace && request.sourceKind === 'model-package' && operation?.sourceKind === request.sourceKind &&
    operation.namespace === request.namespace && request.operationId === operation.id && operation.requestId === r.id &&
    ['packageId', 'deploymentId', 'instanceKey', 'instanceName', 'planDigest'].every(k => same(operation[k], request[k])) &&
    pkg?.status === 'valid' && pkg.id === request.packageId && pkg.id === r.creation.intended?.packageId && pkg.applicationUuid === operation.applicationUuid &&
    pkg.artifactDigest === r.creation.intended.expectedDigest && pkg.packageDigest === request.sourceDigest &&
    !!approval && approval.origin === h.admin.origin && same(approval.actorIdentity, h.admin.identity) &&
    approval.response.data.value?.id === r.id && approval.response.data.value.operationId === operation.id &&
    approval.response.data.value.planDigest === request.planDigest &&
    (!installation || Number.isSafeInteger(installation.id) && installation.id > 0 && Number.isSafeInteger(installation.updateTime) && installation.updateTime > 0 &&
      installation.namespace === request.namespace && installation.deploymentId === request.deploymentId &&
      installation.applicationUuid === operation.applicationUuid && installation.applicationKey === pkg.applicationKey &&
      installation.instanceKey === request.instanceKey && installation.sourceKind === request.sourceKind &&
      installation.runtimeType === 'model-driven' && installation.sourceKey === String(pkg.id) &&
      installation.sourceDigest === pkg.artifactDigest && installation.operationId === 'deployment:' + operation.id &&
      (!operation.receiptRef || operation.receiptRef === 'installation:' + installation.id));
}
function terminated(h, d, response, request, operation) {
  const before = d.operation, original = d.request;
  return !!response && h.good(response) && same(response.data.value, operation) && request.status === 'cancelled' &&
    operation.status === 'cancelled' && operation.phase === 'terminated' && (operation.failureCode ?? 0) === 0 &&
    operation.failureMessage === 'terminated after cleanup: ' + d.termination.body.reason &&
    request.version === original.version + 1 && operation.version === before.version + 1 &&
    ['id', 'requestId', 'packageId', 'namespace', 'applicationUuid', 'deploymentId', 'instanceKey', 'instanceName', 'sourceKind', 'planDigest', 'attempt', 'maxAttempts', 'startTime', 'receiptRef'].every(k => same(operation[k], before[k])) &&
    ['id', 'operationId', 'namespace', 'packageId', 'sourceKind', 'sourceDigest', 'deploymentId', 'instanceKey', 'instanceName', 'planDigest', 'runtimePlacement', 'resolvedRuntimePlacement'].every(k => same(request[k], original[k]));
}
async function cleanup(h, r) {
  if (r.creation?.origin !== h.admin.origin || !same(r.creation?.actorIdentity, h.admin.identity) || r.commands?.some(c => c.outcome === 'unknown'))
    throw new h.Blocked('Failed model disposal requires original actor and confirmed commands; no replay');
  const review = require('./deployment_review_cases.cjs');
  let request = await read(h, requests + r.id), operation = await read(h, operations + request.operationId);
  const pkg = await read(h, packages + request.packageId);
  let d = r.failedModelDisposition;
  if (!d) {
    if (r.installation || request.status !== 'failed' || operation.status !== 'failed' || !binding(h, r, request, operation, pkg))
      throw new h.Blocked('Original failed model request, approval and artifact binding unproven; no teardown');
    const values = await h.directory(h.admin, installations), matches = values.filter(v => v.deploymentId === request.deploymentId);
    const unmaterialized = matches.length === 0 && !operation.receiptRef && !request.upgrade;
    if (matches.length !== 1 && !unmaterialized) throw new h.Blocked('Failed model needs exact original installation or original owner termination without a receipt; no inferred retirement');
    const installed = unmaterialized ? null : await read(h, installations + matches[0].id);
    if (installed && (installed.status !== 'failed' || !binding(h, r, request, operation, pkg, installed)))
      throw new h.Blocked('Failed model installation is foreign or changed; no guessed uninstall');
    d = r.failedModelDisposition = { origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
      request, operation, package: pkg, installation: installed, ...(unmaterialized ? { unmaterialized: true } : {}),
      peers: values.filter(v => v.id !== installed?.id), outcome: 'open' };
    h.persist();
  }
  if (d.origin !== h.admin.origin || !same(d.actorIdentity, h.admin.identity) || !same(pkg, d.package) ||
      !binding(h, r, d.request, d.operation, pkg, d.installation))
    throw new h.Blocked('Original failed model disposal identity changed; no command replay');
  let installed;
  if (d.installation) {
    installed = await read(h, installations + d.installation.id);
    if (!d.uninstall) {
      if (!same(installed, d.installation) || !same(request, d.request) || !same(operation, d.operation))
        throw new h.Blocked('Original failed model changed before conditional destroy');
      d.uninstall = { route: installations + installed.id + '/uninstall', outcome: 'unknown', body: {
        expectedUpdateTime: installed.updateTime, expectedDigest: installed.sourceDigest,
        reason: 'Destroy exact original failed model regression ' + request.instanceKey,
        dataDisposition: 'destroy', confirmation: installed.applicationKey } }; h.persist();
      d.uninstall.response = await h.api(h.admin, 'POST', d.uninstall.route, d.uninstall.body); h.persist();
      installed = await read(h, installations + d.installation.id);
    }
    if (!d.uninstall.response || !review.destroyConfirmed(h, d.uninstall, installed, d.installation))
      throw new h.Blocked('Original failed model destroy is not independently confirmed; no uninstall replay');
    const schemas = await h.directory(h.admin, '/panel/storage-resources/database-schemas/');
    const schemaId = d.installation.receipt?.database?.schemaResourceId;
    h.check('Independent storage owner confirms exact original failed model Schema recycled',
      Number.isSafeInteger(schemaId) && schemaId > 0 && schemas.filter(v => v.id === schemaId && v.status === 'recycled').length === 1);
    d.uninstall.outcome = 'confirmed'; d.retiredInstallation = installed; h.persist();
  } else {
    if (d.unmaterialized !== true || d.operation.receiptRef || d.request.upgrade) throw new h.Blocked('Original pre-installation disposal proof missing');
    const values = await h.directory(h.admin, installations);
    h.check('Complete original installation directory remains absent before formal owner termination; absence alone is not retirement',
      !values.some(v => v.deploymentId === d.request.deploymentId));
  }
  if (!d.termination) {
    request = await read(h, requests + r.id); operation = await read(h, operations + d.operation.id);
    if (!same(request, d.request) || !same(operation, d.operation)) throw new h.Blocked('Original failed task changed before conditional termination');
    d.termination = { route: operations + operation.id + '/cancel', outcome: 'unknown', body: {
      expectedVersion: operation.version, reason: 'Terminate exact original failed model regression ' + request.instanceKey } }; h.persist();
    d.termination.response = await h.api(h.admin, 'POST', d.termination.route, d.termination.body); h.persist();
  }
  request = await read(h, requests + r.id); operation = await read(h, operations + d.operation.id);
  if (!terminated(h, d, d.termination.response, request, operation))
    throw new h.Blocked('Original failed model termination lacks exact independent paired receipt; no cancel replay');
  d.termination.outcome = 'confirmed'; h.persist();
  const values = await h.directory(h.admin, installations);
  if (d.unmaterialized) h.check('Formal original owner termination and independent full directory confirm no materialized installation', !values.some(v => v.deploymentId === d.request.deploymentId));
  const peers = values.filter(v => v.id !== installed?.id);
  h.check('Failed model disposal preserves every original peer installation and its monotone projection revision',
    peers.length === d.peers.length && d.peers.every(v => {
      const matches = peers.filter(p => p.id === v.id); return matches.length === 1 && review.installationUnchanged(v, matches[0]);
    }));
  r.last = request; r.operation = operation; r.phase = 'deleted'; d.outcome = 'confirmed'; h.persist();
  return { proof: d.unmaterialized ? 'Exact original failed model without an installation receipt conditionally terminated by its owner, independently paired request/operation and complete directory absence confirmed with unchanged attempt budget. No uninstall or Schema recycle claim; original failure history retained.' : 'Exact original failed model installation formally destroyed, storage owner confirms Schema recycled, original failed task conditionally terminated with unchanged attempt budget and independent paired receipts. Original installation/task history and source package retained; failure evidence unchanged.' };
}
module.exports = { cleanup, binding, terminated };
