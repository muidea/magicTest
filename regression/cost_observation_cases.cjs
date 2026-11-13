// Real enabled cost windows from a dedicated candidate. Sampling is local to
// one process; database statistics and nested costs never become a SQL trace.
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const { randomBytes } = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const roots = ['FilterEntityValues', 'QueryEntityValue', 'InsertEntityValue', 'UpdateEntityValue', 'DeleteEntityValue', 'resolveApplicationEntity'];
const categories = ['http-client', 'base-rpc', 'sql-query', 'sql-execute', 'transaction', 'application-stage', 'connection-acquire', 'query-phase', 'overflow'];
const finite = n => typeof n === 'number' && Number.isFinite(n) && n >= 0;
const count = n => Number.isSafeInteger(n) && n >= 0;
function declarations(rows) {
  if (!Array.isArray(rows) || rows.length < 4 || rows.length > 16 || new Set(rows.map(v => v.name)).size !== rows.length ||
      !['magicPanel', 'magicbase', 'magiccas', 'postgres'].every(n => rows.some(v => v.name === n)) ||
      rows.some(v => !/^[a-f0-9]{64}$/.test(v.id) || !/^sha256:[a-f0-9]{64}$/.test(v.image) || !v.running || !Number.isFinite(Date.parse(v.startedAt))))
    throw Error('Complete actual candidate container identities required');
  const windows = rows.filter(v => v.name !== 'postgres').map(v => {
    const text = v.switches?.MAGIC_PROFILE_WINDOW;
    if (!/^(?:[1-9]|10)s$/.test(text)) throw Error('Enabled bounded 1-10s profile windows required; no automatic reconfiguration');
    return Number(text.slice(0, -1));
  });
  if (rows.find(v => v.name === 'magicPanel').switches?.MAGIC_PROFILE_SAMPLE_EVERY !== '1')
    throw Error('Actual Panel must declare every-request sampling for exact single-request proof');
  return Math.max(...windows);
}
function validatePhase(result, phase, request, secrets = []) {
  const r = result?.report, s = result?.summary;
  declarations(result?.containers);
  if (result.kind !== 'result' || !r || !s || r.phase !== phase || s.phase !== phase || !finite(r.startedAt) || !finite(r.finishedAt) ||
      r.finishedAt <= r.startedAt || r.finishedAt - r.startedAt > 150 || r.errors?.length !== 0 || s.errors?.length !== 0 ||
      !Array.isArray(r.events) || !Array.isArray(r.databaseDelta) || !r.databaseDelta.length || r.databaseDelta.some(v => v.valid !== true) ||
      typeof r.statementStatisticsAvailable !== 'boolean' || r.statementStatisticsReset ||
      !Object.values(result.tools || {}).every(v => /^sha256:[a-f0-9]{64}$/.test(v)) || Object.keys(result.tools || {}).length !== 2)
    throw Error('Complete error-free original cost interval and paired formal helpers required');
  if (request && !(r.startedAt * 1000 <= request.startedAt && request.startedAt <= request.finishedAt && request.finishedAt <= r.finishedAt * 1000))
    throw Error('Actual original request must complete wholly inside its captured phase');
  const text = JSON.stringify(result);
  if (secrets.filter(v => typeof v === 'string' && v.length >= 8).some(v => text.includes(v)))
    throw Error('Cost observation contains original credentials or business input; do not export it');
  const allSamples = [], full = [], intervals = new Map();
  for (const e of r.events) {
    if (!result.containers.some(c => c.name === e.container) || !['window', 'sample'].includes(e.kind)) throw Error('Unknown observation process or record kind');
    const d = e.data;
    if (e.kind === 'sample') {
      if (e.container !== 'magicPanel' || !/^[a-z0-9]+-[a-f0-9]+$/.test(d.sampleID) ||
          !(roots.includes(d.operation) || ['resolveApplicationRuntimes', 'resolveModelStorage', 'resolveModelExecution'].includes(d.operation)) ||
          !finite(d.totalMs) || !d.stagesMs || Object.entries(d.stagesMs).some(([k, v]) => !/^[A-Za-z][A-Za-z0-9]{0,70}$/.test(k) || !finite(v)) ||
          d.eventWaitMs !== undefined && !finite(d.eventWaitMs)) throw Error('Invalid bounded process-local request sample');
      if (d.rpc !== undefined && (!d.rpc || Object.entries(d.rpc).some(([k, v]) => k !== v.operation ||
          !/^[A-Za-z][A-Za-z0-9_:/{}. -]{0,190}$/.test(k) || !count(v.calls) || !count(v.errors) || v.errors > v.calls || !finite(v.totalMs))))
        throw Error('Invalid original RPC counters; no inferred totals');
      allSamples.push(e); continue;
    }
    const begin = Date.parse(d.startedAt) / 1000, end = Date.parse(d.endedAt) / 1000;
    if (!finite(begin) || !finite(end) || begin >= end || !same(d.boundsMs, [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000]) ||
        !Array.isArray(d.entries) || d.entries.length > 129 ||
        e.fullyInsidePhase !== (begin >= r.startedAt && end <= r.finishedAt)) throw Error('Exact bounded original window required');
    for (const v of d.entries) if (!categories.includes(v.category) || !/^[A-Za-z0-9_:/{}. -]{1,190}$/.test(v.operation) ||
        !count(v.calls) || !count(v.errors) || v.errors > v.calls || !finite(v.totalMs) || !finite(v.maxMs) ||
        !Array.isArray(v.buckets) || v.buckets.length !== 11 || !v.buckets.every(count) || v.buckets.reduce((a, b) => a + b, 0) !== v.calls)
      throw Error('Malformed or incomplete cost histogram');
    if (e.fullyInsidePhase) {
      const previous = intervals.get(e.container) || [];
      if (previous.some(v => begin < v.end && end > v.begin)) throw Error('Duplicate or overlapping process windows cannot be counted twice');
      previous.push({ begin, end }); intervals.set(e.container, previous); full.push(e);
    }
  }
  const actualRoots = allSamples.filter(e => e.data.rpc !== undefined);
  if (phase === 'idle' ? allSamples.length !== 0 : actualRoots.length !== 1 || actualRoots[0].data.operation !== 'QueryEntityValue' ||
      allSamples.some(e => e.data.sampleID !== actualRoots[0].data.sampleID) || Object.values(actualRoots[0].data.rpc).reduce((n, v) => n + v.calls, 0) < 1)
    throw Error('Original idle must have no foreground sample and read must have one exact complete QueryEntityValue root');
  if (!full.length || phase === 'read' && !['application-stage', 'base-rpc', 'sql-query'].every(category =>
      full.some(e => e.data.entries.some(v => v.category === category && v.calls > 0))))
    throw Error('Complete enabled process windows and real observed categories required');
  if (!same(s.coverage, r.coverage) || r.coverage.fullWindows !== full.length || r.coverage.sampleRecords !== allSamples.length ||
      s.requestSamples?.length !== actualRoots.length || s.requestSamples?.some(v => !v.rootComplete || v.rootCount !== 1 ||
        v.sampleID !== actualRoots[0]?.data.sampleID || v.container !== 'magicPanel' || !same(v.root, actualRoots[0]?.data)) ||
      s.sqlFingerprintAvailable !== r.statementStatisticsAvailable)
    throw Error('Formal summary must retain original process-local roots, category coverage and explicit SQL availability');
  return { fullWindows: full.length, root: actualRoots[0], perRequestSQLTrace: false, summedNestedCost: false };
}
async function runPhase(h, phase, callback, { start = spawn, pause = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  const token = randomBytes(16).toString('hex'), config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig));
  const seconds = config.costObservation?.seconds;
  if (!Number.isSafeInteger(seconds) || seconds < 8 || seconds > 40) throw new h.Blocked('Explicit bounded costObservation.seconds8-40 and actual enabled containers required');
  let ready, result, callbackTask, protocolError, closed = false, outputBytes = 0;
  const child = start('python3', ['-B', '-u', h.path.join(h.root, 'regression/cost_observation.py'), '--config', h.deliveryFixtureConfig,
    '--phase', phase, '--seconds', String(seconds), '--token', token], { stdio: ['ignore', 'pipe', 'pipe'] });
  // Neither raw helper errors nor unrelated container logs enter public evidence.
  child.stderr.on('data', () => {});
  const lines = createInterface({ input: child.stdout });
  const timer = setTimeout(() => { protocolError ||= Error('Original observation helper deadline; no request replay'); child.kill('SIGKILL'); }, 170000);
  lines.on('line', line => {
    try {
      if (protocolError) return;
      outputBytes += Buffer.byteLength(line);
      if (outputBytes > 8 * 1024 * 1024) throw Error('Finite cost observation output budget exceeded');
      const value = JSON.parse(line);
      if (value.kind === 'unavailable' && /^[A-Za-z]{1,60}$/.test(value.errorType))
        throw Error('Original cost observer unavailable: ' + value.errorType + (value.errorType === 'ObservationUnavailable' && /^[A-Za-z0-9 -]{1,160}$/.test(value.reason) ? ': ' + value.reason : ''));
      if (value.token !== token) throw Error('Original observation phase token mismatch');
      if (value.kind === 'ready' && !ready && !result) {
        const window = declarations(value.containers);
        if (seconds < window * 3 + 2 || !finite(value.startedAt)) throw Error('At least three bounded original windows required');
        ready = value;
        // Attach rejection handling now; helper completion never retries a read.
        callbackTask = Promise.resolve().then(async () => {
          // Move the single request past the leading partial process window.
          if (callback) await pause(window * 1000 + 100);
          if (protocolError || closed || result) throw Error('Original observation ended before request dispatch; no late request');
          return callback?.();
        }).then(value => ({ value }), error => ({ error }));
      } else if (value.kind === 'result' && ready && !result && same(value.containers, ready.containers) && value.report?.startedAt === ready.startedAt) result = value;
      else throw Error('Original observation readiness/result duplicated, changed or out of order');
    } catch (error) { protocolError ||= error; child.kill('SIGKILL'); }
  });
  let exit;
  try { exit = await new Promise((resolve, reject) => { child.once('error', reject); child.once('close', (code, signal) => { closed = true; resolve({ code, signal }); }); }); }
  finally { clearTimeout(timer); lines.close(); }
  const outcome = await callbackTask;
  if (outcome?.error) throw outcome.error;
  if (protocolError || exit.code !== 0 || exit.signal || !ready || !result) throw new h.Blocked(protocolError?.message || 'Original cost observer unavailable; no request replay or zero-cost claim');
  return { result, request: outcome?.value };
}
async function costs(h) {
  const f = await fixture(h);
  const config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig));
  if (!config.costObservation) throw new h.Blocked('Dedicated actual cost observation declarations are required; no production profile changes');
  const actor = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, actor);
  let row, primary;
  try {
    row = await business.create(h, { ...context, scenarioDefinitionId: f.application.id }, 'cost-original');
    const identity = structuredClone(actor.identity), origin = actor.origin, original = structuredClone(row.created);
    const secrets = [h.credentials.password, h.state.password, actor.password, original.code, original.name];
    const journal = { actorIdentity: identity, origin, identity: structuredClone(row.identity), recordId: row.recordId, phases: [] };
    (h.state.fixtures.costObservationAttempts ||= []).push(journal); h.persist();
    const idle = await runPhase(h, 'idle');
    journal.phases.push({ phase: 'idle', observation: idle.result }); h.persist();
    const idleProof = validatePhase(idle.result, 'idle', undefined, secrets);
    h.observe({ kind: 'actual-cost-idle-phase', observation: idle.result, idleProof });
    const measured = await runPhase(h, 'read', async () => {
      if (!same(actor.identity, identity) || actor.origin !== origin) throw new h.Blocked('Original cost reader changed before dispatch');
      const startedAt = Date.now(), response = await business.record(h, actor, row), finishedAt = Date.now();
      h.check('The one actual measured request reads the entire exact original ordinary business row', h.good(response) && same(response.data.value, original));
      return { startedAt, finishedAt };
    });
    journal.phases.push({ phase: 'read', observation: measured.result, request: measured.request }); h.persist();
    const readProof = validatePhase(measured.result, 'read', measured.request, secrets);
    h.check('Idle and actual request use identical original running containers, images, startup switches and formal tools',
      same(idle.result.containers, measured.result.containers) && same(idle.result.tools, measured.result.tools));
    h.check('Independent owner read after observation preserves complete original data, version, actor and installation',
      same(actor.identity, identity) && actor.origin === origin && same((await business.record(h, actor, row)).data.value, original) &&
      same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + context.instance.id)).value, context.instance));
    h.observe({ kind: 'actual-cost-observation', idle: idle.result, read: measured.result, request: measured.request,
      idleProof, readProof, qualification: 'Process-local single ordinary read sample; configured aggregate categories only. SQL counters include the observer and background work, nested/RPC costs overlap. No per-request SQL trace, subtraction-derived exact costs or capacity claim.' });
  } catch (error) { primary = error; throw error; }
  finally { if (row) await business.finishCleanup(h, [row], primary); }
  await h.partial('Actual enabled declarations and stable container/image/start identity, idle and one real QueryEntityValue interval, complete process histograms, exact unique local root/RPC correlation, explicit SQL fingerprint availability and original-row preservation/cleanup implemented. On/off restoration, HTTP route/pprof access fences, optional APM and full monitoring scope remain open.');
}
costs.transport = 'owner-api';
module.exports = { handlers: { 'F059-002': costs }, declarations, validatePhase, runPhase };
