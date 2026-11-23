// Reassess frozen evidence without running browsers or overwriting its source.
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { acceptancePolicy, assessSample } = require('./live-login-regression.cjs');
function reassess(source, namespaces) {
  assert.ok(['magic.login.regression/v2', 'magic.login.regression/v3'].includes(source.schema), 'UnsupportedEvidence');
  assert.ok(Array.isArray(namespaces) && namespaces.length && new Set(namespaces).size === namespaces.length, 'ExpectedNamespacesRequired');
  assert.ok(Number.isInteger(source.sequential) && source.sequential >= 1 && source.sequential <= 40, 'InvalidSequentialPlan');
  assert.deepEqual(source.concurrency, [2, 5, 10], 'UnexpectedConcurrencyPlan');
  assert.ok(Array.isArray(source.samples) && Array.isArray(source.incompleteTenants), 'InvalidSamples');
  const expected = new Set();
  for (const namespace of namespaces) {
    for (const [group, count] of [['sequential', source.sequential], ...source.concurrency.map(n => ['parallel-' + n, n])]) {
      for (let index = 0; index < count; index++) expected.add(JSON.stringify([namespace, group, index]));
    }
  }
  const seen = new Set();
  const samples = source.samples.map(sample => {
    const key = JSON.stringify([sample.namespace, sample.group, sample.index]);
    assert.ok(expected.has(key) && !seen.has(key), 'DuplicateOrUnexpectedSample');
    seen.add(key);
    return { namespace: sample.namespace, group: sample.group, index: sample.index,
      originalAssessment: { passed: sample.passed, dimensions: sample.dimensions }, ...assessSample(sample) };
  });
  const counts = { passed: 0, failed: 0, blocked: 0 };
  for (const sample of samples) counts[sample.status]++;
  const complete = seen.size === expected.size && source.incompleteTenants.length === 0;
  return { schema: 'magic.login.reassessment/v1', acceptancePolicy, newLiveExecution: false,
    candidateFingerprint: source.candidateFingerprint, originalStartedAt: source.startedAt, originalFinishedAt: source.finishedAt,
    namespaces, expectedSamples: expected.size, complete, counts, passed: complete && samples.every(s => s.passed), samples };
}
function main() {
  const [input, output, namespaceList] = process.argv.slice(2);
  assert.ok(input && output && namespaceList, 'Usage: node reassess-login-regression.cjs SOURCE OUTPUT panel,t001');
  const bytes = fs.readFileSync(input);
  const hash = content => 'sha256:' + crypto.createHash('sha256').update(content).digest('hex');
  const result = { ...reassess(JSON.parse(bytes), namespaceList.split(',')), assessedAt: new Date().toISOString(),
    sourceDigest: hash(bytes), toolDigest: hash(fs.readFileSync(__filename)), policyToolDigest: hash(fs.readFileSync(require.resolve('./live-login-regression.cjs'))) };
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  console.log(JSON.stringify({ passed: result.passed, complete: result.complete, counts: result.counts, newLiveExecution: false }));
  if (!result.passed) process.exitCode = 1;
}
if (require.main === module) main();
module.exports = { reassess };
