const { test } = require('node:test');
const assert = require('node:assert/strict');
const { project, matches } = require('./deployment_progress_cases.cjs');
test('progress cannot join foreign tasks, regress owner facts or invent final installation proof', () => {
  const r = { id: 7, last: { packageId: 8, planDigest: 'original-plan' }, installation: { id: 10, deploymentId: 'original-deployment' },
    operation: { id: 9, requestId: 7, packageId: 8, deploymentId: 'original-deployment', planDigest: 'original-plan',
      status: 'succeeded', phase: 'complete', attempt: 1, maxAttempts: 3, version: 8, startTime: 100, finishTime: 200, receiptRef: 'installation:10' } };
  const samples = [project({ id: 7 }, { ...r.operation, version: 2, status: 'running', phase: 'install', finishTime: 0, receiptRef: '' }), project({ id: 7 }, r.operation)];
  assert.equal(matches(samples, r), true);
  for (const change of [v => v[0].operationId++, v => v[0].operationRequestId++, v => v[0].requestId++, v => v[0].deploymentId = 'foreign',
    v => v[0].packageId++, v => v[0].planDigest = 'foreign', v => v[0].version = 9, v => v[0].attempt = 2,
    v => v[1].status = 'running', v => v[0].phase = '', v => v[0].status = 'failed']) {
    const altered = structuredClone(samples); change(altered); assert.equal(matches(altered, r), false);
  }
  for (const change of [v => v.operation.receiptRef = 'installation:11', v => v.operation.finishTime = 99, v => v.operation.phase = 'install', v => v.operation.attempt = 0]) {
    const altered = structuredClone(r); change(altered); assert.equal(matches(samples, altered), false);
  }
  assert.equal(matches([], r), false);
});
