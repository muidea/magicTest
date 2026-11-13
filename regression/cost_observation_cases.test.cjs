const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { declarations, validatePhase, runPhase } = require('./cost_observation_cases.cjs');
function containers() {
  return ['magicPanel', 'magicbase', 'magiccas', 'postgres'].map((name, i) => ({ name, id: String(i).repeat(64), image: 'sha256:' + 'a'.repeat(64),
    startedAt: '2026-11-10T00:00:00Z', running: true, switches: { MAGIC_PROFILE_WINDOW: name === 'postgres' ? '' : '1s', MAGIC_PROFILE_SAMPLE_EVERY: name === 'magicPanel' ? '1' : '' } }));
}
function observation(phase = 'read') {
  const windows = (phase === 'read' ? ['application-stage', 'base-rpc', 'sql-query'] : ['sql-query']).map((category, i) => ({ kind: 'window', container: i === 0 ? 'magicPanel' : 'magicbase', fullyInsidePhase: true,
    data: { startedAt: new Date((102 + i) * 1000).toISOString(), endedAt: new Date((103 + i) * 1000).toISOString(), boundsMs: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000],
      entries: [{ category, operation: 'QueryEntityValue', calls: 1, errors: 0, totalMs: 2, maxMs: 2, buckets: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0] }] } }));
  const root = { sampleID: 'ma1-1', operation: 'QueryEntityValue', totalMs: 5, stagesMs: { resolve: 2, value: 2 }, rpc: { 'GET /api/v1/value/query/_': { operation: 'GET /api/v1/value/query/_', calls: 1, errors: 0, totalMs: 3 } } };
  const events = phase === 'idle' ? windows : [...windows, { container: 'magicPanel', kind: 'sample', data: root },
    { container: 'magicPanel', kind: 'sample', data: { sampleID: root.sampleID, operation: 'resolveApplicationEntity', totalMs: 3, stagesMs: { binding: 2 } } }];
  const coverage = { fullWindows: windows.length, sampleRecords: phase === 'idle' ? 0 : 2 };
  return { kind: 'result', containers: containers(), tools: { collector: 'sha256:' + 'a'.repeat(64), summarizer: 'sha256:' + 'b'.repeat(64) },
    report: { phase, startedAt: 100, finishedAt: 110, errors: [], events, coverage, statementStatisticsAvailable: false, databaseDelta: [{ valid: true }] },
    summary: { phase, errors: [], coverage, sqlFingerprintAvailable: false, requestSamples: phase === 'idle' ? [] : [{ container: 'magicPanel', sampleID: root.sampleID, rootComplete: true, rootCount: 1, root }] } };
}
test('actual declarations reject missing, repeated, disabled, changed or excessive profile controls', () => {
  assert.equal(declarations(containers()), 1);
  for (const mutate of [r => r.pop(), r => r[1].name = 'magicPanel', r => r[0].running = false, r => r[0].image = 'master',
    r => r[1].switches.MAGIC_PROFILE_WINDOW = '', r => r[1].switches.MAGIC_PROFILE_WINDOW = '60s', r => r[0].switches.MAGIC_PROFILE_SAMPLE_EVERY = '100']) {
    const rows = containers(); mutate(rows); assert.throws(() => declarations(rows));
  }
});
test('one process-local root permits overlapping child costs without summing them or inventing SQL tracing', () => {
  const p = validatePhase(observation(), 'read', { startedAt: 103000, finishedAt: 104000 });
  assert.equal(p.root.data.totalMs, 5); assert.equal(p.summedNestedCost, false); assert.equal(p.perRequestSQLTrace, false);
  assert.equal(validatePhase(observation('idle'), 'idle').root, undefined);
});
test('incomplete original intervals, resets, secrets and mismatched owner summary cannot prove coverage', () => {
  for (const mutate of [r => r.report.errors.push({ operation: 'logs' }), r => r.report.databaseDelta[0].valid = false,
    r => r.report.statementStatisticsReset = true, r => r.summary.sqlFingerprintAvailable = true,
    r => r.report.events[0].data.entries[0].buckets[0]++, r => r.report.events[0].data.entries[0].totalMs = NaN,
    r => r.report.events[0].fullyInsidePhase = false, r => r.report.events[2].data.entries[0].category = 'http-client',
    r => r.report.events.push(structuredClone(r.report.events[0])), r => r.summary.requestSamples[0].rootComplete = false,
    r => r.summary.requestSamples[0].root = { ...r.summary.requestSamples[0].root, totalMs: 99 },
    r => r.report.events[0].data.entries[0].operation = 'secret-regression-value']) {
    const r = observation(); mutate(r); assert.throws(() => validatePhase(r, 'read', { startedAt: 103000, finishedAt: 104000 }, ['secret-regression-value']));
  }
  assert.throws(() => validatePhase(observation(), 'read', { startedAt: 99000, finishedAt: 104000 }));
  assert.throws(() => validatePhase(observation(), 'read', { startedAt: 103000, finishedAt: 111000 }));
});
test('missing, duplicate, foreign or unsampled roots and contaminated idle never become a single request proof', () => {
  for (const mutate of [r => delete r.report.events[3].data.rpc, r => r.report.events.push(structuredClone(r.report.events[3])),
    r => r.report.events[3].container = 'magiccas', r => r.report.events[4].data.sampleID = 'foreign-2',
    r => r.report.events[3].data.operation = 'InsertEntityValue', r => r.report.events[3].data.rpc['GET /api/v1/value/query/_'].calls = 0]) {
    const r = observation(); mutate(r); assert.throws(() => validatePhase(r, 'read'));
  }
  const idle = observation('idle'); idle.report.events.push(observation().report.events[3]);
  assert.throws(() => validatePhase(idle, 'idle'));
});
function harness(mode) {
  let calls = 0, child;
  const h = { root: '/tool', path: require('node:path'), deliveryFixtureConfig: '/private/config', Blocked: Error,
    fs: { readFileSync: () => JSON.stringify({ costObservation: { seconds: 8 } }) } };
  const start = (_cmd, args) => {
    const token = args.at(-1); child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.kill = () => { setImmediate(() => child.emit('close', null, 'SIGKILL')); };
    setImmediate(async () => {
      if (mode === 'spawn') { child.emit('error', Error('spawn unavailable')); return; }
      const ready = { kind: 'ready', token, containers: containers(), startedAt: 100 };
      if (mode === 'token') ready.token = 'foreign';
      if (mode === 'disabled') ready.containers[0].switches.MAGIC_PROFILE_SAMPLE_EVERY = '0';
      child.stdout.write(JSON.stringify(ready) + '\n');
      if (mode === 'duplicate') child.stdout.write(JSON.stringify(ready) + '\n');
      if (mode === 'callback-failure') { await new Promise(resolve => setImmediate(resolve)); }
      else if (mode !== 'late') await new Promise(resolve => setImmediate(resolve));
      const result = { ...observation(), token };
      if (mode === 'drift') result.containers[0].id = 'f'.repeat(64);
      if (mode !== 'missing') child.stdout.write(JSON.stringify(result) + '\n');
      child.stdout.end(); child.emit('close', 0, null);
    });
    return child;
  };
  return { h, start, request: async () => { calls++; if (mode === 'callback-failure') throw Error('original owner unavailable'); return { original: true }; }, calls: () => calls };
}
test('real observer handshake dispatches once and preserves callback failure instead of retrying it', async () => {
  for (const mode of ['success', 'callback-failure', 'missing', 'drift']) {
    const f = harness(mode);
    if (mode === 'success') assert.deepEqual((await runPhase(f.h, 'read', f.request, { start: f.start, pause: async () => {} })).request, { original: true });
    else await assert.rejects(runPhase(f.h, 'read', f.request, { start: f.start, pause: async () => {} }));
    assert.equal(f.calls(), 1);
  }
});
test('bad readiness, spawn failure and a completed interval cannot dispatch a late or duplicate request', async () => {
  for (const mode of ['token', 'disabled', 'duplicate', 'spawn', 'late']) {
    const f = harness(mode);
    await assert.rejects(runPhase(f.h, 'read', f.request, { start: f.start, pause: async () => { if (mode === 'late') await new Promise(resolve => setImmediate(resolve)); } }));
    assert.equal(f.calls(), 0);
  }
});
