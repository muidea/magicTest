// Independently sample real owner operations; never fabricate intermediate phases.
const { fixture } = require('./delivery_cases.cjs');
const model = require('./deployment_review_cases.cjs');
const native = require('./native_runtime_cases.cjs');
const { build } = require('./native_package_cases.cjs');
const { cleanup: removePackage } = require('./native_provider_access_cases.cjs');
function project(request, operation) {
  return { requestId: request.id, operationId: operation.id, operationRequestId: operation.requestId,
    packageId: operation.packageId, deploymentId: operation.deploymentId, planDigest: operation.planDigest,
    status: operation.status, phase: operation.phase, attempt: operation.attempt, maxAttempts: operation.maxAttempts,
    version: operation.version, startTime: operation.startTime, finishTime: operation.finishTime, receiptRef: operation.receiptRef };
}
function matches(samples, r) {
  const op = r.operation, instance = r.installation;
  return samples.length > 0 && samples.every(v => v.requestId === r.id && v.operationRequestId === r.id &&
    v.operationId === op.id && v.packageId === r.last.packageId && v.deploymentId === instance.deploymentId && v.planDigest === r.last.planDigest &&
    ['queued', 'running', 'succeeded'].includes(v.status) && typeof v.phase === 'string' && v.phase.length > 0 &&
    Number.isSafeInteger(v.version) && v.version > 0 && Number.isSafeInteger(v.attempt) && v.attempt >= 0 && v.attempt <= v.maxAttempts) &&
    samples.every((v, i) => !i || v.version >= samples[i - 1].version && v.attempt >= samples[i - 1].attempt) &&
    op.status === 'succeeded' && op.phase === 'complete' && op.attempt > 0 && op.finishTime >= op.startTime && op.startTime > 0 &&
    op.receiptRef === 'installation:' + instance.id && samples.at(-1).status === 'succeeded';
}
async function progress(h) {
  const f = await fixture(h), modelSamples = [], nativeSamples = [];
  const observe = (kind, samples) => (request, operation) => {
    const sample = project(request, operation); samples.push(sample);
    h.observe({ kind: 'original-deployment-progress', sourceKind: kind, sample });
  };
  const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value; h.admin.id = session.account.id;
  const m = await model.create(h, f, 'model-progress');
  let modelError;
  try {
    await model.approve(h, m, [h.admin], { observeOperation: observe('model-package', modelSamples) });
    h.check('Real model task phases, attempts, monotonic owner revisions and final installation receipt agree', matches(modelSamples, m), modelSamples);
  } catch (error) { modelError = error; throw error; }
  finally {
    try { await model.cleanup(h, m); }
    catch (error) { h.observe({ kind: 'original-progress-cleanup-open', requestId: m.id, error: error.message }); if (!modelError) throw error; }
  }
  const value = native.input(h, false), pkg = await build(h, value);
  let n, nativeError;
  try {
    n = await native.install(h, pkg.package, value, 'progress', observe('deployment-package', nativeSamples));
    h.check('Real native task phases, attempts, monotonic owner revisions and final installation receipt agree', matches(nativeSamples, n), nativeSamples);
    h.check('Native final owner receipt matches independently verified live component', native.inspect(h, n).probeFile.marker === n.marker);
  } catch (error) { nativeError = error; throw error; }
  finally {
    try {
      // A failed install remains journaled even when install() did not return.
      // Global exact-resource cleanup then reconciles it before its package.
      if (n) { await native.cleanup(h, n); await removePackage(h, pkg); }
    } catch (error) { h.observe({ kind: 'original-progress-cleanup-open', requestId: n?.id, error: error.message }); if (!nativeError) throw error; }
  }
  if (![modelSamples, nativeSamples].every(samples => samples.some(v => ['queued', 'running'].includes(v.status))))
    await h.partial('Both exact original model/native tasks and final runtime receipts verified and formally retired. At least one task finished before nonterminal phase observation; no intermediate progress invented.');
}
progress.transport = 'owner-api';
module.exports = { handlers: { 'F029-001': progress }, project, matches };
