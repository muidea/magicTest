const { test } = require('node:test');
const assert = require('node:assert/strict');
const { original, commandBinding, confirm, inspect, input, retireFailed, survivingRequest, confirmPackageDisposition, expectedExitFailure, failedComponent, layoutIdentity } = require('./native_runtime_cases.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
function fixture() {
  const identity = { account: 'original-admin', namespace: 'panel' }, origin = 'https://panel.test';
  const h = { admin: { identity, origin, id: 9 }, Blocked: Error, state: { prefix: 'rgtest' }, good: r => r?.status === 200 && !r.data?.error,
    check: (m, c) => assert.ok(c, m), observe() {}, persist() {} };
  const r = { kind: 'native-runtime-request', phase: 'created', id: 17,
    creation: { ownershipConfirmed: true, outcome: 'accepted', actorIdentity: structuredClone(identity), origin },
    last: { id: 17, namespace: 'panel', packageId: 2, deploymentId: 'exact-deployment', sourceDigest: 'exact-package', planDigest: 'exact-plan', instanceKey: 'exact-instance', operationId: 21 }, commands: [] };
  return { h, r, identity, origin };
}
test('native uninstall polls the same lifecycle through pending final acknowledgment and preserves unresolved originals', async () => {
  const { settledUninstall } = require('./native_runtime_cases.cjs');
  for (const mode of ['good', 'pending', 'wrong-lifecycle', 'wrong-installation', 'wrong-deployment', 'failed']) {
    const { h, r } = fixture(); r.installation = { id: 30 }; r.uninstallLifecycleId = 'original-uninstall';
    let reads = 0, waits = 0;
    const read = async () => {
      reads++;
      return { id: mode === 'wrong-installation' ? 31 : 30, deploymentId: mode === 'wrong-deployment' ? 'foreign' : r.last.deploymentId,
        status: mode === 'failed' ? 'uninstallFailed' : 'uninstalled', packagedReceipt: { lifecycle: {
          id: mode === 'wrong-lifecycle' ? 'foreign' : r.uninstallLifecycleId, action: 'uninstall',
          status: mode === 'failed' ? 'failed' : 'succeeded', completionPending: mode === 'pending' || reads < 3 } } };
    };
    if (mode === 'good') { const result = await settledUninstall(h, r, read, async () => waits++); assert.equal(result.packagedReceipt.lifecycle.completionPending, false); assert.equal(reads, 3); assert.equal(waits, 2); }
    else if (mode === 'failed') { assert.equal((await settledUninstall(h, r, read, async () => waits++)).status, 'uninstallFailed'); assert.equal(reads, 1); }
    else { await assert.rejects(settledUninstall(h, r, read, async () => waits++), mode === 'pending' ? /final acknowledgment.*budget/ : /identity changed/); assert.equal(reads, mode === 'pending' ? 120 : 1); assert.equal(waits, mode === 'pending' ? 119 : 0); }
    assert.equal(r.phase, 'created'); assert.deepEqual(r.commands, []);
  }
});
test('native lifecycle command confirmation requires original receipt binding and preserves unknown writes without replay', async () => {
  const { h, r, identity, origin } = fixture(); let reads = 0;
  const c = { action: 'approve', origin, actorIdentity: identity, outcome: 'unknown', response: { status: 200, data: { value: structuredClone(r.last) } } };
  h.ok = async () => { reads++; return { value: structuredClone(r.last) }; };
  assert.equal(commandBinding(h, r, c, r.last), true); await confirm(h, r, c); assert.equal(c.outcome, 'confirmed'); assert.equal(reads, 1);
  for (const mode of ['lost', 'other-operation', 'other-deployment', 'other-package', 'other-plan', 'other-origin']) {
    const changed = structuredClone(c); changed.outcome = 'unknown';
    if (mode === 'lost') delete changed.response;
    if (mode === 'other-operation') changed.response.data.value.operationId = 22;
    if (mode === 'other-deployment') changed.response.data.value.deploymentId = 'replacement';
    if (mode === 'other-package') changed.response.data.value.packageId = 3;
    if (mode === 'other-plan') changed.response.data.value.planDigest = 'replacement';
    if (mode === 'other-origin') changed.origin = 'https://foreign.test';
    await assert.rejects(confirm(h, r, changed), /no replay/); assert.equal(changed.outcome, 'unknown');
  }
  r.creation.actorIdentity.account = 'replacement'; assert.throws(() => original(h, r), /original/);
});
test('native Docker observations never read a file under an unverified or foreign component identity', () => {
  const { h, r } = fixture(), id = 'a'.repeat(64);
  r.installation = { id: 30, packagedReceipt: { runtimeApplicationUuid: 'runtime-uuid', components: [{ key: 'api', containerId: id, imageId: 'sha256:image' }] } };
  for (const mode of ['wrong-id', 'wrong-image', 'wrong-deployment', 'wrong-runtime']) {
    const actual = { Id: id, Image: 'sha256:image', Config: { Labels: { 'io.platform.deployment-id': r.last.deploymentId, 'io.platform.runtime.application-uuid': 'runtime-uuid' } } };
    if (mode === 'wrong-id') actual.Id = 'b'.repeat(64);
    if (mode === 'wrong-image') actual.Image = 'other';
    if (mode === 'wrong-deployment') actual.Config.Labels['io.platform.deployment-id'] = 'other';
    if (mode === 'wrong-runtime') actual.Config.Labels['io.platform.runtime.application-uuid'] = 'other';
    let calls = 0;
    assert.throws(() => inspect(h, r, (bin, args) => { calls++; assert.equal(bin, 'docker'); assert.deepEqual(args, ['inspect', id]); return JSON.stringify([actual]); }), /ownership differs/);
    assert.equal(calls, 1);
  }
  r.installation.packagedReceipt.components[0].containerId = '../other';
  assert.throws(() => inspect(h, r, () => { assert.fail('must not dispatch Docker'); }), /original native component ID/);
});
test('native runtime recovery protects exact original input, approval, installation and uninstall lifecycle', () => {
  const { r } = fixture(); r.input = { contract: { components: { api: { image: 'original:master' } } } };
  r.installation = { id: 30 }; r.uninstallLifecycleId = 'exact-uninstall';
  const evidence = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, evidence)[0], r);
  for (const mutate of [x => x.last.operationId = 99, x => x.input.contract.components.api.image = 'other:master', x => x.installation.id = 31, x => x.uninstallLifecycleId = 'other', x => x.commands.push({ outcome: 'unknown' })]) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /differs/);
  }
});
test('native runtime single and dual inputs declare own managed volume, real readiness and stable shell literals', () => {
  const { h } = fixture(), a = input(h, true), b = input(h, false);
  assert.notEqual(a.applicationUuid, b.applicationUuid); assert.equal(a.contract.components.api.workingDir, '/data');
  assert.equal(a.contract.components.api.readiness.path, '/probe.json'); assert.equal(a.contract.components.api.mounts[0].volumeRef, 'data');
  assert.match(a.contract.components.api.command[1], /\$REGRESSION_MARKER/); assert.match(a.contract.components.api.command[1], /\$\(hostname\)/);
  assert.equal(a.contract.ingresses.web.authPolicy, 'none'); assert.equal(b.contract.ingresses, undefined);
});
function failedFixture() {
  const f = fixture(), { h, r } = f;
  r.input = input(h, false); r.input.contract.components.api.command = ['-c', 'exit 23'];
  r.marker = r.input.contract.components.api.environment.REGRESSION_MARKER.literal;
  r.creation.intended = { packageId: 2, expectedDigest: 'exact-package', instanceKey: 'exact-instance' };
  r.last = { ...r.last, sourceKind: 'deployment-package', status: 'failed', instanceName: 'original' };
  r.operation = { id: 21, requestId: r.id, namespace: 'panel', packageId: 2, sourceKind: 'deployment-package',
    applicationUuid: r.input.applicationUuid, deploymentId: r.last.deploymentId, instanceKey: r.last.instanceKey,
    instanceName: r.last.instanceName, planDigest: r.last.planDigest, status: 'failed', phase: 'execution', attempt: 1, maxAttempts: 3,
    failureCode: 6, startTime: 1, finishTime: 2,
    failureMessage: 'native component api did not become ready: container exited before readiness (status exited, exit code 23); container status=exited, exit code=23, restarts=0, OOM killed=false' };
  return f;
}
test('expected native failure cannot pass from unrelated admission, timeout, wrong resource or exhausted attempts', () => {
  const { r } = failedFixture(); assert.equal(expectedExitFailure(r), true);
  for (const mutate of [v => v.operation.phase = 'authorization', v => v.operation.failureCode = 17, v => v.operation.failureMessage = 'timeout',
    v => v.operation.failureMessage = v.operation.failureMessage.replaceAll('23', '1'), v => v.operation.deploymentId = 'foreign',
    v => v.operation.attempt = 4, v => v.operation.receiptRef = 'installation:other', v => v.last.status = 'succeeded']) {
    const bad = structuredClone(r); mutate(bad); assert.equal(expectedExitFailure(bad), false);
  }
});
test('directory observations require exact owner identities before accessing any generated path', () => {
  const r = { last: { namespace: 'panel', deploymentId: 'a'.repeat(32) }, input: { applicationName: 'current-native' } };
  assert.deepEqual(layoutIdentity(r), ['panel', 'a'.repeat(32), 'current-native']);
  for (const mutate of [v => v.last.namespace = '../foreign', v => v.last.deploymentId = '', v => v.last.deploymentId = 'short',
    v => v.input.applicationName = '/absolute', v => v.input.applicationName = '..', v => v.input.applicationName = 'current/../foreign']) {
    const bad = structuredClone(r); mutate(bad); assert.throws(() => layoutIdentity(bad), /safe.*identities/);
  }
});
test('failed component observations select exact original deployment and reject foreign command before any cleanup', () => {
  const { h, r } = failedFixture(), id = 'c'.repeat(64), intended = r.input.contract.components.api;
  const actual = { Id: id, Image: 'sha256:image', Config: { Labels: { 'io.platform.deployment-id': r.last.deploymentId, 'io.platform.runtime.application-uuid': 'a'.repeat(32) },
    Entrypoint: intended.entrypoint, Cmd: intended.command, WorkingDir: intended.workingDir, Env: ['REGRESSION_MARKER=' + r.marker] },
    State: { Status: 'exited', Running: false, ExitCode: 23, OOMKilled: false }, RestartCount: 0, Mounts: [] };
  let reads = 0;
  const run = (bin, args) => { reads++; assert.equal(bin, 'docker'); if (args[0] === 'ps') { assert.equal(args.at(-1), 'label=io.platform.deployment-id=exact-deployment'); return id; } assert.deepEqual(args, ['inspect', id]); return JSON.stringify([actual]); };
  assert.equal(failedComponent(h, r, run).containerId, id); assert.equal(reads, 2);
  actual.Config.Cmd = ['-c', 'foreign-command']; assert.throws(() => failedComponent(h, r, run));
  r.operation.failureMessage = 'unrelated failure'; reads = 0;
  assert.throws(() => failedComponent(h, r, run), /intended nonzero-exit/); assert.equal(reads, 0);
});
test('source package history may change only its explicit removed flag while exact request and package identities survive', () => {
  const before = { id: 1, version: 4, packageRemoved: false, package: { id: 9, packageDigest: 'exact' }, deploymentId: 'original' };
  const after = { ...structuredClone(before), packageRemoved: true };
  assert.equal(survivingRequest(before, after), true);
  const displayOnly = { ...after, package: { ...after.package, preflightReport: '' } };
  assert.equal(survivingRequest(before, displayOnly), true);
  for (const change of [v => v.deploymentId = 'foreign', v => v.package.packageDigest = 'foreign', v => v.version++, v => v.sourceDiagnostic = { code: 'source-unavailable' }]) {
    const bad = structuredClone(after); change(bad); assert.equal(survivingRequest(before, bad), false);
  }
});
test('native linked-package disposition cannot infer abort or deletion from an absent resource without immutable provenance', async () => {
  const { h, r } = fixture(); h.api = () => assert.fail('unproven original disposition must not dispatch');
  h.directory = () => assert.fail('unproven original disposition must not dispatch');
  await assert.rejects(confirmPackageDisposition(h, r, { trace: [] }, 'sha256:' + 'a'.repeat(64), []), /immutable/);
  r.failureRetirement = { beforeOperation: { id: 21 } };
  await assert.rejects(confirmPackageDisposition(h, r, { trace: [], resources: [] }, 'sha256:' + 'a'.repeat(64), [{}]), /differs/);
});
test('failed native retirement uses one original conditional owner abort and confirms unchanged execution budget without replay', async () => {
  const { h, r } = fixture();
  r.input = { applicationUuid: 'original-app' };
  r.creation.intended = { packageId: 2, expectedDigest: 'exact-package', instanceKey: 'exact-instance' };
  const beforeRequest = { ...r.last, sourceKind: 'deployment-package', status: 'failed', version: 4, instanceName: 'original' };
  const beforeOperation = { id: 21, requestId: 17, packageId: 2, namespace: 'panel', sourceKind: 'deployment-package', applicationUuid: 'original-app',
    deploymentId: 'exact-deployment', instanceKey: 'exact-instance', instanceName: 'original', planDigest: 'exact-plan', status: 'failed', version: 3, attempt: 1, maxAttempts: 3, startTime: 1 };
  let writes = 0, request = structuredClone(beforeRequest), operation = structuredClone(beforeOperation);
  h.ok = async (_, method, route) => { assert.equal(method, 'GET'); return { value: structuredClone(route.includes('operations') ? operation : request) }; };
  h.directory = async () => [];
  h.api = async (_, method, route, body) => {
    writes++; assert.equal(method, 'POST'); assert.equal(route, '/panel/operations/namespaces/panel/application-deployment-operations/21/cancel');
    assert.equal(body.expectedVersion, 3);
    // The public Go DTO omits a successful zero failureCode.
    operation = { ...operation, status: 'cancelled', phase: 'terminated', version: 4, failureMessage: 'terminated after cleanup: ' + body.reason };
    request = { ...request, status: 'cancelled', version: 5 };
    return { status: 200, data: { value: structuredClone(operation) } };
  };
  await retireFailed(h, r); assert.equal(writes, 1); assert.equal(r.phase, 'deleted'); assert.equal(r.failureRetirement.beforeOperation.status, 'failed');
  await retireFailed(h, r); assert.equal(writes, 1);
  delete r.failureRetirement.response;
  await assert.rejects(retireFailed(h, r), /no cancel replay/); assert.equal(writes, 1);
  request.deploymentId = 'foreign';
  await assert.rejects(retireFailed(h, r), /binding/); assert.equal(writes, 1);
});
test('native instance identities stay distinct across cases using first/second and preserve the full application UUID', () => {
  const { instanceKey } = require('./native_runtime_cases.cjs'), { h } = fixture();
  const first = { applicationUuid: 'a'.repeat(32) }, next = { applicationUuid: 'b'.repeat(32) };
  assert.notEqual(instanceKey(h, first, 'first'), instanceKey(h, next, 'first'));
  assert.notEqual(instanceKey(h, first, 'first'), instanceKey(h, first, 'second'));
  assert.ok(instanceKey(h, first, 'expected-failure').includes(first.applicationUuid));
  for (const bad of [{ applicationUuid: '' }, { applicationUuid: '../foreign' }]) assert.throws(() => instanceKey(h, bad, 'first'));
  assert.throws(() => instanceKey(h, first, '../foreign'));
  assert.throws(() => instanceKey(h, first, 'first-'));
  assert.throws(() => instanceKey(h, first, 'x'.repeat(64)));
});
test('rejected native fixture recovery binds exact refusal and retained peer without replay or guessed deletion', async () => {
  const { reconcileIdentityRefusal } = require('./native_runtime_cases.cjs');
  for (const mode of ['valid', 'lost', 'auth', 'other-error', 'other-actor', 'live-peer', 'different-peer', 'request-present', 'installation-present', 'wrong-package']) {
    const { h } = fixture();
    const peerInstallation = { id: 31, deploymentId: 'original-peer', namespace: 'panel', instanceKey: 'same-key', applicationUuid: 'a'.repeat(32), status: 'uninstalled', packagedReceipt: { lifecycle: { id: 'original-uninstall', status: 'succeeded' } } };
    const peer = { kind: 'native-runtime-request', phase: 'deleted', installation: { ...peerInstallation }, currentInstallation: structuredClone(peerInstallation), last: { deploymentId: 'original-peer' }, uninstallLifecycleId: 'original-uninstall', creation: { ownershipConfirmed: true, actorIdentity: h.admin.identity, origin: h.admin.origin, intended: { instanceKey: 'same-key' } } };
    const r = { kind: 'native-runtime-request', collection: '/panel/application/deployment-requests/', phase: 'intent', creation: { journalId: 'original-journal', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unconfirmed', intended: { sourceKind: 'deployment-package', instanceKey: 'same-key', packageId: 2, expectedDigest: 'exact' }, response: { status: 500, data: { error: { code: 18, message: 'application deployment identity is inconsistent' }, value: null } } } };
    const pkg = { id: 2, packageDigest: 'exact', applicationUuid: 'b'.repeat(32) };
    h.state.resources = [peer, r];
    h.api = async (_, method, route) => { assert.equal(method, 'GET', 'reconciliation must never dispatch a mutation'); assert.equal(route, '/panel/application/deployment-packages/2'); return { status: 200, data: { error: null, value: structuredClone(pkg) } }; };
    h.ok = async (_, method, route) => { assert.equal(method, 'GET'); return { value: structuredClone(route.includes('deployment-packages') ? pkg : peerInstallation) }; };
    h.directory = async (_, route) => route === '/panel/application/installations/history/' ? [peerInstallation, ...(mode === 'installation-present' ? [{ applicationUuid: pkg.applicationUuid, instanceKey: 'same-key', namespace: 'panel' }] : [])] : mode === 'request-present' ? [{ packageId: 2 }] : [];
    if (mode === 'lost') delete r.creation.response;
    if (mode === 'auth') r.creation.response.status = 401;
    if (mode === 'other-error') r.creation.response.data.error.message = 'other';
    if (mode === 'other-actor') r.creation.actorIdentity.account = 'other';
    if (mode === 'live-peer') peerInstallation.status = 'ready';
    if (mode === 'different-peer') peerInstallation.applicationUuid = 'c'.repeat(32);
    if (mode === 'wrong-package') pkg.packageDigest = 'foreign';
    if (mode === 'valid') { await reconcileIdentityRefusal(h, r); assert.equal(r.phase, 'deleted'); assert.equal(r.creation.outcome, 'unconfirmed'); assert.equal(r.reconciliation.noCommandReplayed, true); }
    else { await assert.rejects(reconcileIdentityRefusal(h, r)); assert.equal(r.phase, 'intent'); }
  }
});

test('native refusal recovery accepts a formally deleted original source only with immutable build and ordered package-only disposition', async () => {
  const { reconcileIdentityRefusal } = require('./native_runtime_cases.cjs'), crypto = require('node:crypto');
  for (const mode of ['valid', 'no-evidence', 'bad-hash', 'changed-journal', 'no-preview', 'reordered', 'foreign-owner', 'wrong-build', 'unknown-delete', 'extra-task', 'read-error', 'request-present', 'peer-active']) {
    const { h } = fixture(), identity = structuredClone(h.admin.identity), origin = h.admin.origin;
    const pkg = { id: 2, applicationUuid: 'b'.repeat(32), packageDigest: 'exact' };
    const response = { status: 200, data: { error: null, value: pkg } };
    const source = { kind: 'native-package-probe', phase: 'deleted', actorIdentity: identity, origin, applicationUuid: pkg.applicationUuid,
      package: pkg, packageAcknowledged: true, preexistingIds: [], commands: [
        { method: 'POST', route: '/panel/application/deployment-packages/builds/', body: { applicationUuid: pkg.applicationUuid, expectedBuildDigest: 'exact' }, actorIdentity: identity, origin, outcome: 'confirmed', response },
        { method: 'DELETE', route: '/panel/application/deployment-packages/2', actorIdentity: identity, origin, outcome: 'confirmed', response } ] };
    const peerInstallation = { id: 31, deploymentId: 'peer', namespace: 'panel', instanceKey: 'same-key', applicationUuid: 'a'.repeat(32), status: 'uninstalled', packagedReceipt: { lifecycle: { id: 'uninstall', status: 'succeeded' } } };
    const peer = { kind: 'native-runtime-request', phase: 'deleted', installation: structuredClone(peerInstallation), currentInstallation: structuredClone(peerInstallation), last: { deploymentId: 'peer' }, uninstallLifecycleId: 'uninstall', creation: { ownershipConfirmed: true, actorIdentity: identity, origin, intended: { instanceKey: 'same-key' } } };
    const r = { kind: 'native-runtime-request', phase: 'intent', collection: '/panel/application/deployment-requests/', creation: { journalId: 'original', actorIdentity: identity, origin, outcome: 'unconfirmed', intended: { sourceKind: 'deployment-package', packageId: 2, expectedDigest: 'exact', instanceKey: 'same-key' }, response: { status: 500, data: { error: { code: 18, message: 'application deployment identity is inconsistent' }, value: null } } } };
    const trace = [ { kind: 'request', actor: identity, origin, method: 'GET', route: '/panel/application/deployment-packages/2/cleanup-preview', response: { status: 200, data: { error: null, value: { allowed: true, packageId: 2, sourceDigest: 'exact', items: ['package', 'deliveryFile'].map(kind => ({ kind, id: 2, action: 'delete' })) } } } },
      { kind: 'request', actor: identity, origin, method: 'DELETE', route: '/panel/application/deployment-packages/2', response } ];
    const evidence = { resources: [{ ...structuredClone(source), confirmed: true }], trace: structuredClone(trace) };
    h.state.resources = [peer, r, structuredClone(source)];
    if (mode === 'no-preview') evidence.trace.shift();
    if (mode === 'reordered') evidence.trace.reverse();
    if (mode === 'foreign-owner') evidence.trace[0].actor = { ...identity, account: 'other' };
    if (mode === 'wrong-build') evidence.resources[0].commands[0].body.expectedBuildDigest = 'wrong';
    if (mode === 'unknown-delete') evidence.resources[0].commands[1].outcome = 'unknown';
    if (mode === 'extra-task') evidence.trace[0].response.data.value.items.push({ kind: 'operation', id: 8, action: 'delete' });
    h.originalCleanupEvidence = evidence; h.originalCleanupBytes = Buffer.from(JSON.stringify(evidence));
    h.originalCleanupSha256 = 'sha256:' + crypto.createHash('sha256').update(h.originalCleanupBytes).digest('hex');
    if (mode === 'no-evidence') delete h.originalCleanupEvidence;
    if (mode === 'bad-hash') h.originalCleanupSha256 = 'sha256:' + '0'.repeat(64);
    if (mode === 'changed-journal') h.state.resources[2].package.packageDigest = 'changed';
    if (mode === 'peer-active') peerInstallation.status = 'ready';
    h.api = async (_, method, route) => { assert.equal(method, 'GET'); assert.equal(route, '/panel/application/deployment-packages/2'); return mode === 'read-error' ? { status: 503, data: {} } : { status: 404, data: { error: { code: 2 }, value: null } }; };
    h.ok = async (_, method, route) => { assert.equal(method, 'GET'); assert.equal(route, '/panel/application/installations/31'); return { value: peerInstallation }; };
    h.directory = async (_, route) => route === '/panel/application/installations/history/' ? [peerInstallation] : mode === 'request-present' ? [{ packageId: 2 }] : [];
    if (mode === 'valid') { await reconcileIdentityRefusal(h, r); assert.equal(r.phase, 'deleted'); assert.equal(r.reconciliation.packageDisposition.originalCleanupSha256, h.originalCleanupSha256); }
    else { await assert.rejects(reconcileIdentityRefusal(h, r), mode); assert.equal(r.phase, 'intent', mode); }
  }
});
