const test = require('node:test');
const assert = require('node:assert/strict');
const { binding, cleanup, terminated } = require('./model_failure_cleanup.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
function fixture() {
  const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.test';
  let request = { id: 7, operationId: 8, namespace: 'panel', packageId: 9, sourceKind: 'model-package', sourceDigest: 'transport-digest',
    deploymentId: 'original', instanceKey: 'original-instance', instanceName: 'Original', planDigest: 'plan', status: 'failed', version: 4 };
  let operation = { id: 8, requestId: 7, namespace: 'panel', packageId: 9, sourceKind: 'model-package', applicationUuid: 'app',
    deploymentId: 'original', instanceKey: 'original-instance', instanceName: 'Original', planDigest: 'plan', status: 'failed', version: 6,
    phase: 'model-execution', failureCode: 5, attempt: 1, maxAttempts: 3, startTime: 10 };
  const pkg = { id: 9, status: 'valid', applicationUuid: 'app', applicationKey: 'app-key', artifactDigest: 'artifact-digest', packageDigest: 'transport-digest' };
  let installation = { id: 11, namespace: 'panel', deploymentId: 'original', applicationUuid: 'app', applicationKey: 'app-key', instanceKey: request.instanceKey,
    sourceKind: 'model-package', runtimeType: 'model-driven', sourceKey: '9', sourceDigest: 'artifact-digest', operationId: 'deployment:8', status: 'failed',
    updateTime: 20, deploymentVersion: 1, receipt: { database: { bindingId: 12, schemaResourceId: 13 } } };
  const peer = { id: 22, deploymentId: 'peer', deploymentVersion: 2, status: 'ready' }, writes = [];
  const r = { kind: 'deployment-review-request', id: 7, phase: 'created', creation: { ownershipConfirmed: true, outcome: 'accepted', origin, actorIdentity: identity,
    intended: { packageId: 9, expectedDigest: 'artifact-digest' }, response: { status: 200, data: { value: { ...request, status: 'submitted', operationId: undefined } } } },
    commands: [{ route: '/panel/operations/namespaces/panel/application-deployment-requests/7/approve', outcome: 'confirmed', origin, actorIdentity: identity,
      response: { status: 200, data: { value: { ...request, status: 'approved' } } } }] };
  const h = { admin: { identity: structuredClone(identity), origin }, Blocked: Error, persist() {},
    good: v => v.status === 200 && !v.data.error, check: (label, condition) => assert.ok(condition, label),
    async ok(_a, _m, route) {
      return { value: structuredClone(route.includes('model-packages/') ? pkg : route.includes('installations/') ? installation : route.includes('application-deployment-operations/') ? operation : request) };
    }, async directory(_a, route) { return structuredClone(route.includes('database-schemas') ? [{ id: 13, status: installation.status === 'uninstalled' ? 'recycled' : 'active' }] : [installation, peer]); },
    async api(_a, method, route, body) {
      assert.equal(method, 'POST'); writes.push({ route, body });
      if (route.endsWith('/uninstall')) {
        assert.equal(body.expectedUpdateTime, installation.updateTime); assert.equal(body.expectedDigest, 'artifact-digest');
        installation = { ...installation, status: 'uninstalled', updateTime: 21, receipt: { ...installation.receipt,
          uninstallation: { dataDisposition: 'destroy', finishedAt: 30, authorization: { confirmed: true }, recoveryStatus: 'recycled' } } };
        return { status: 200, data: { value: structuredClone(installation) } };
      }
      assert.equal(route, '/panel/operations/namespaces/panel/application-deployment-operations/8/cancel'); assert.equal(body.expectedVersion, operation.version);
      request = { ...request, status: 'cancelled', version: request.version + 1 };
      operation = { ...operation, status: 'cancelled', phase: 'terminated', version: operation.version + 1, failureCode: 0, failureMessage: 'terminated after cleanup: ' + body.reason };
      return { status: 200, data: { value: structuredClone(operation) } };
    } };
  return { h, r, pkg, writes, request: () => request, operation: () => operation, installation: () => installation };
}
test('failed model binding separates transport and artifact digests and rejects borrowed approval, installation and actor', () => {
  const f = fixture(); assert.ok(binding(f.h, f.r, f.request(), f.operation(), f.pkg, f.installation()));
  for (const change of [f => f.h.admin.identity.account = 'other', f => f.r.commands[0].response.data.value.operationId = 99,
    f => f.pkg.packageDigest = f.pkg.artifactDigest, f => f.pkg.applicationUuid = 'foreign', f => f.installation().sourceKey = 'foreign',
    f => f.installation().operationId = 'deployment:other', f => f.installation().deploymentId = 'other', f => f.request().instanceKey = 'foreign',
    f => f.r.commands[0].origin = 'https://other.test', f => f.operation().receiptRef = 'installation:foreign']) {
    const g = fixture(); change(g); assert.equal(binding(g.h, g.r, g.request(), g.operation(), g.pkg, g.installation()), false);
  }
});
test('failed model cleanup destroys only exact original installation then terminates original task without resetting its attempt budget', async () => {
  const f = fixture(); await cleanup(f.h, f.r);
  assert.equal(f.r.phase, 'deleted'); assert.equal(f.writes.length, 2);
  assert.equal(f.r.failedModelDisposition.outcome, 'confirmed'); assert.equal(f.operation().attempt, 1); assert.equal(f.operation().maxAttempts, 3);
  await cleanup(f.h, f.r); assert.equal(f.writes.length, 2);
  const d = f.r.failedModelDisposition;
  assert.ok(terminated(f.h, d, d.termination.response, f.request(), f.operation()));
  assert.equal(terminated(f.h, d, undefined, f.request(), f.operation()), false);
  assert.equal(terminated(f.h, d, d.termination.response, f.request(), { ...f.operation(), attempt: 2 }), false);
});
test('unknown original uninstall or termination never replays and remains open for independent owner disposition', async () => {
  for (const suffix of ['/uninstall', '/cancel']) {
    const f = fixture(), original = f.h.api;
    f.h.api = async (...args) => { const response = await original(...args); if (args[2].endsWith(suffix)) throw Error('lost original response'); return response; };
    await assert.rejects(cleanup(f.h, f.r), /lost original/); const count = f.writes.length;
    await assert.rejects(cleanup(f.h, f.r), /no .*replay/); assert.equal(f.writes.length, count); assert.equal(f.r.phase, 'created');
  }
});
test('foreign state or incomplete original installation directory blocks all failed model mutations', async () => {
  for (const change of [f => f.r.creation.origin = 'https://other.test', f => f.r.commands.push({ outcome: 'unknown' }),
    f => f.operation().status = 'running', f => f.installation().status = 'ready', f => f.installation().sourceDigest = 'foreign',
    f => { f.operation().receiptRef = 'installation:11'; f.h.directory = async () => []; }]) {
    const f = fixture(); change(f); await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.writes.length, 0);
  }
});
test('no-installation failure requires formal original owner termination, never directory absence alone', async () => {
  for (const mode of ['exact', 'refused', 'lost', 'upgrade', 'receipt']) {
    const f = fixture(), originalDirectory = f.h.directory, originalApi = f.h.api;
    f.h.directory = async (...args) => (await originalDirectory(...args)).filter(v => v.id !== 11);
    if (mode === 'upgrade') f.request().upgrade = { sourceInstallationId: 11 };
    if (mode === 'receipt') f.operation().receiptRef = 'installation:11';
    f.h.api = async (...args) => {
      assert.ok(args[2].endsWith('/cancel'), 'absence must never invent an uninstall target');
      if (mode === 'refused') { f.writes.push({ route: args[2] }); return { status: 409, data: { error: { code: 21 }, value: null } }; }
      const response = await originalApi(...args);
      if (mode === 'lost') throw Error('lost original termination');
      return response;
    };
    if (mode === 'exact') {
      await cleanup(f.h, f.r); assert.equal(f.r.phase, 'deleted'); assert.equal(f.writes.length, 1);
      assert.equal(f.r.failedModelDisposition.unmaterialized, true); assert.equal(f.r.failedModelDisposition.uninstall, undefined);
      assert.equal(f.operation().attempt, 1); assert.equal(f.operation().maxAttempts, 3);
    } else {
      await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.r.phase, 'created');
      const count = f.writes.length;
      if (['refused', 'lost'].includes(mode)) await assert.rejects(cleanup(f.h, f.r), /no cancel replay/);
      assert.equal(f.writes.length, count); assert.equal(count, ['refused', 'lost'].includes(mode) ? 1 : 0);
    }
  }
});
test('failed model recovery binds its entire original disposal journal to immutable cleanup evidence', async () => {
  const f = fixture(); await cleanup(f.h, f.r); f.r.phase = 'created';
  const evidence = { trace: [], resources: [{ ...structuredClone(f.r), confirmed: false }] };
  assert.equal(bindOriginalCleanup({ resources: [f.r] }, evidence)[0], f.r);
  for (const change of [v => v.failedModelDisposition.installation.id++, v => v.failedModelDisposition.request.planDigest = 'foreign',
    v => v.failedModelDisposition.termination.body.expectedVersion++]) {
    const changed = structuredClone(f.r); change(changed);
    assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /differs/);
  }
});
