// Invoke unchanged platform helpers only in the declared dedicated nested
// daemon. Public Panel commands remain the native installation/lifecycle owner.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const native = require('./native_runtime_cases.cjs');
const { validateIsolation } = require('./delivery_fixture.cjs');
const options = { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 4 * 1024 * 1024 };
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
const labels = { project: 'com.docker.compose.project', service: 'com.docker.compose.service',
  compose: 'com.docker.compose.project.config_files', directory: 'com.docker.compose.project.working_dir',
  deployment: 'io.platform.deployment-id', application: 'io.platform.runtime.application-uuid', nonce: 'io.muidea.magictest.native-lifecycle' };
const inspect = (run, id) => JSON.parse(run('docker', ['inspect', id], options))[0];
const processState = c => ({ running: c.State?.Running, restarting: c.State?.Restarting, status: c.State?.Status,
  startedAt: c.State?.StartedAt, finishedAt: c.State?.FinishedAt, dead: c.State?.Dead, exitCode: c.State?.ExitCode,
  pid: c.State?.Pid, restartCount: c.RestartCount });
const isolationConfig = c => Object.fromEntries(['platformRoot', 'dockerDataRoot', 'daemonId', 'containerId'].map(k => [k, c[k]]));
function binding(c) {
  return { id: c.Id, name: c.Name, image: c.Image, labels: c.Config?.Labels,
    mounts: c.Mounts, networks: Object.keys(c.NetworkSettings?.Networks || {}).sort(), hostname: c.Config?.Hostname,
    entrypoint: c.Config?.Entrypoint, command: c.Config?.Cmd, workingDir: c.Config?.WorkingDir };
}
const peerBinding = c => ({ id: c.Id, name: c.Name, image: c.Image, projectionDigest: hash(JSON.stringify(binding(c))) });
function resume(c, network) {
  const l = c.Config?.Labels;
  const value = { id: c.Id, name: c.Name, image: c.Image, network,
    project: l?.[labels.project], service: l?.[labels.service], compose: l?.[labels.compose] };
  if (!/^[a-f0-9]{64}$/.test(value.id || '') || Object.values(value).some(v => typeof v !== 'string' || !v) ||
      !/^native-[a-f0-9]{12}$/.test(value.project) || !c.NetworkSettings?.Networks?.[network]) throw Error('Exact native resume tuple required');
  return value;
}
function assertJournal(records, originals) {
  if (!Array.isArray(records) || records.length !== 2 || new Set(records.map(v => v.id)).size !== 2 ||
      !same([...records].sort((a, b) => a.id.localeCompare(b.id)), [...originals].sort((a, b) => a.id.localeCompare(b.id))))
    throw Error('Resume journal must contain exactly both original complete native owner tuples');
}
function exactTargets(run, network, ids, extra = []) {
  const rows = String(run('docker', ['ps', '-a', '-q', '--no-trunc', '--filter', 'network=' + network,
    '--filter', 'label=com.docker.compose.project'], options)).trim().split(/\s+/).filter(Boolean);
  const actual = rows.map(id => inspect(run, id)).filter(c => /^native-[a-f0-9]{12}$/.test(c.Config?.Labels?.[labels.project] || '')).map(c => c.Id).sort();
  const expected = [...ids, ...extra].sort();
  if (new Set(actual).size !== actual.length || !same(actual, expected)) throw Error('Entire native candidate set must equal the original exact instances and owned negative probe');
}
function isolation(h, r, run = execFileSync) {
  if (h.admin.origin !== r.origin || !same(h.admin.identity, r.actorIdentity)) throw new h.Blocked('Original native lifecycle actor required');
  const config = JSON.parse(fs.readFileSync(h.deliveryFixtureConfig));
  if (!same(isolationConfig(config), r.config)) throw new h.Blocked('Original dedicated daemon configuration changed');
  validateIsolation(config, JSON.parse(run('docker', ['info', '--format', '{{json .}}'], options)));
  for (const s of r.scripts) if (hash(fs.readFileSync(s.path)) !== s.sha256 || hash(fs.readFileSync(s.canonical)) !== s.sha256)
    throw new h.Blocked('Original formal lifecycle helper source changed');
  if (fs.realpathSync(r.privateRoot) !== r.privateRoot || !r.privateRoot.startsWith(fs.realpathSync(os.tmpdir()) + '/magictest-native-lifecycle-') ||
      path.dirname(r.env) !== r.privateRoot || path.dirname(r.journal) !== r.privateRoot ||
      fs.readFileSync(r.env, 'utf8') !== 'APPS_NETWORK=' + r.network + '\n') throw new h.Blocked('Original private lifecycle root or nonsecret network declaration changed');
}
function dispatch(h, r, action, run = execFileSync) {
  isolation(h, r, run);
  if (!['stop', 'start', 'remove'].includes(action) || r.commands.some(c => !Number.isInteger(c.exitCode)) ||
      action !== 'remove' && r.commands.some(c => c.action === action)) throw new h.Blocked('Original native helper result unresolved or action already dispatched; no replay');
  const command = { action, outcome: 'unknown', startedAt: Date.now() };
  r.commands.push(command); h.persist();
  try {
    // Paths are positional arguments, never interpolated into shell source.
    run('sh', ['-c', '. "$1"; . "$2"; if [ "$5" = start ]; then start_native_application_runtimes "$3" "$4"; else stop_native_application_runtimes "$3" "$4" "$5"; fi',
      'native-lifecycle', r.scripts[0].path, r.scripts[1].path, r.env, r.journal, action], options);
    command.exitCode = 0;
  } catch (error) {
    if (Number.isInteger(error.status) && !error.signal) command.exitCode = error.status;
    // Never export raw helper output (or container Env) into public evidence.
    command.ownershipRefused = command.exitCode === 1 && /native runtime (ownership could not be verified|project identity mismatch): [a-f0-9]{12,64}/.test(String(error.stderr));
    command.errorType = error.name;
  }
  command.finishedAt = Date.now(); h.persist(); return command;
}
function intact(h, r, running, run = execFileSync) {
  const rows = r.before.map(before => {
    const current = inspect(run, before.id);
    h.check('Original native ID, image, labels, mounts and command remain exact', same(binding(current), before.binding));
    h.check('Exact native runtime has expected lifecycle state', current.State?.Running === running && current.State?.Restarting === false);
    return current;
  });
  return rows;
}
async function owners(h, r) {
  for (const item of r.ownerReads) h.check('Independent original owner fact remains unchanged: ' + item.route,
    same((await h.ok(h.admin, 'GET', item.route)).value, item.value));
}
function peers(h, r, run = execFileSync) {
  for (const before of r.peers) {
    const current = inspect(run, before.id);
    h.check('Unrelated core/model peer retains exact image, mounts and process start identity', same({ binding: peerBinding(current), state: processState(current) }, before.value));
  }
}
function probeMatches(current, p, network) {
  return current?.Id === p.id && current.Name === '/' + p.name && current.Image === p.image && current.State?.Running === false &&
    same(current.Config?.Labels, p.labels) && current.Mounts?.length === 0 &&
    same(Object.keys(current.NetworkSettings?.Networks || {}), [network]) && same(current.Config?.Entrypoint, ['/bin/true']);
}
function persistentSentinel(h, r, before, run = execFileSync) {
  const value = JSON.parse(run('docker', ['exec', before.id, 'cat', '/data/lifecycle-sentinel.json'], options));
  h.check('First-start-only sentinel belongs to exact original volume and container hostname', value.marker === r.sentinelNonce && value.hostname === before.binding.hostname);
  return value;
}
function absence(run, id) {
  try { inspect(run, id); return false; }
  catch (error) { if (error.status === 1 && /No such (object|container)/i.test(String(error.stderr))) return true; throw error; }
}
function removeProbe(h, r, p, run = execFileSync) {
  isolation(h, r, run);
  if (!/^[a-f0-9]{64}$/.test(p.id || '') || p.creation.outcome !== 'acknowledged') throw new h.Blocked('Original negative probe creation unresolved; no replay or inferred absence');
  if (!p.removal) {
    const current = inspect(run, p.id);
    if (!probeMatches(current, p, r.network)) throw new h.Blocked('Exact stopped mount-free negative probe ownership changed; no removal');
    p.removal = { outcome: 'unknown' }; h.persist();
    try { run('docker', ['rm', p.id], options); p.removal.acknowledged = true; }
    finally { h.persist(); }
  }
  if (!absence(run, p.id)) throw new h.Blocked('Original negative probe removal not independently confirmed; no replay');
  p.removal.outcome = 'confirmed'; h.persist();
}
function variants(nonce) {
  const application = nonce, project = 'native-' + crypto.createHash('sha256').update('panel\0' + application).digest('hex').slice(0, 12);
  const compose = '/var/app/application-runtime/compose/panel/' + nonce + '/' + application + '/docker-compose.yaml';
  const base = { [labels.project]: project, [labels.service]: 'probe', [labels.compose]: compose,
    [labels.directory]: path.dirname(compose), [labels.deployment]: nonce, [labels.application]: application, [labels.nonce]: nonce };
  return [
    { key: 'outside-root', labels: { ...base, [labels.compose]: '/unrelated/docker-compose.yaml', [labels.directory]: '/unrelated' } },
    { key: 'parent-traversal', labels: { ...base, [labels.compose]: compose.replace('/compose/panel/', '/compose/panel/../panel/') } },
    { key: 'project-identity', labels: { ...base, [labels.application]: application + 'different' } },
    { key: 'working-directory', labels: { ...base, [labels.directory]: path.dirname(compose) + '-other' } },
    { key: 'deployment-identity', labels: { ...base, [labels.deployment]: nonce + 'different' } },
  ].map(v => ({ ...v, labels: { ...v.labels, [labels.service]: 'probe-' + v.key } }));
}
function createProbe(h, r, variant, run = execFileSync) {
  isolation(h, r, run); exactTargets(run, r.network, r.before.map(v => v.id));
  const p = { ...variant, labels: { ...r.probeImageLabels, ...variant.labels }, name: variant.labels[labels.project] + '-' + variant.labels[labels.service], image: r.before[0].binding.image,
    creation: { outcome: 'unknown' } };
  r.probes.push(p); h.persist();
  const args = ['create', '--pull=never', '--name', p.name, '--network', r.network, '--entrypoint', '/bin/true'];
  for (const [key, value] of Object.entries(p.labels)) args.push('--label', key + '=' + value);
  args.push(p.image);
  // No create replay or name-based deletion if Docker acknowledgement is lost.
  p.id = String(run('docker', args, options)).trim(); h.persist();
  if (!/^[a-f0-9]{64}$/.test(p.id) || !probeMatches(inspect(run, p.id), p, r.network)) throw new h.Blocked('Original probe Docker acknowledgement or ownership differs');
  p.creation.outcome = 'acknowledged'; h.persist(); return p;
}
async function cleanup(h, r, run = execFileSync) {
  if (r.phase === 'deleted') return { proof: 'Original native lifecycle already independently restored.' };
  isolation(h, r, run);
  for (const p of r.probes) if (p.removal?.outcome !== 'confirmed') removeProbe(h, r, p, run);
  exactTargets(run, r.network, r.before.map(v => v.id));
  const stop = r.commands.find(v => v.action === 'stop'), start = r.commands.find(v => v.action === 'start');
  if (r.commands.some(v => v.action === 'remove' && !Number.isInteger(v.exitCode))) throw new h.Blocked('Original remove helper result unknown; preserve native resources');
  if (stop) {
    if (!Number.isInteger(stop.exitCode)) throw new h.Blocked('Original stop helper may still execute; no start or replay');
    if (!start) {
      if (!fs.existsSync(r.journal)) throw new h.Blocked('Original stop lacks full resume journal; retain native resources');
      assertJournal(JSON.parse(fs.readFileSync(r.journal)), r.resume);
      // Both the successful test path and recovery resume only original IDs.
      for (const before of r.before) if (!same(binding(inspect(run, before.id)), before.binding)) throw new h.Blocked('Original stopped native identity changed');
      dispatch(h, r, 'start', run);
    }
    const resumed = r.commands.find(v => v.action === 'start');
    if (!Number.isInteger(resumed?.exitCode) || resumed.exitCode !== 0 || fs.existsSync(r.journal)) throw new h.Blocked('Original start result unresolved or failed; no replay, preserve journal and resources');
    intact(h, r, true, run); resumed.outcome = 'confirmed'; stop.outcome = 'confirmed';
  } else intact(h, r, true, run);
  for (const record of r.nativeIds) {
    const original = h.state.resources.find(v => v.kind === 'native-runtime-request' && v.id === record);
    if (!original || !same(native.inspect(h, original, run), r.before.find(v => v.requestId === record).view)) throw new h.Blocked('Original native volume or complete running configuration differs');
    const before = r.before.find(v => v.requestId === record);
    if (!same(persistentSentinel(h, r, before, run), before.sentinel)) throw new h.Blocked('Original first-start-only persistent data differs');
  }
  peers(h, r, run); await owners(h, r);
  r.phase = 'deleted'; h.persist();
  return { proof: 'Exact original native containers running with original volume probe/configuration; owner request/operation/installation and unrelated core/model peers preserved. All acknowledged stopped negative probes independently absent. Formal retain uninstall remains separate; no byte deletion claim.' };
}
function guard(h, resource) {
  if (h.state.resources.some(r => r.kind === 'native-lifecycle-probe' && r.phase !== 'deleted' &&
      (resource === r || resource.kind === 'native-runtime-request' && (r.nativeIds.includes(resource.id) || resource.creation?.intended?.packageId === r.packageId) ||
        ['native-package-probe', 'native-provider-probe'].includes(resource.kind) && resource.package?.id === r.packageId)))
    throw new h.Blocked('Original native lifecycle/probe remains unresolved; preserve exact instances and package');
}
async function prepare(h, run = execFileSync) {
  require('./delivery_fixture.cjs').requireIsolatedDaemon(h, 'DELIVERY-FIXTURE: dedicated nested daemon isolation is required for native runtime lifecycle disruption tests');
  const fixture = await require('./delivery_cases.cjs').fixture(h), config = JSON.parse(fs.readFileSync(h.deliveryFixtureConfig));
  const value = native.input(h, false), sentinelNonce = crypto.randomBytes(16).toString('hex');
  const component = value.contract.components.api;
  component.command[1] = component.command[1].replace('exec nginx',
    'if [ ! -f /data/lifecycle-sentinel.json ]; then printf \'{"marker":"' + sentinelNonce + '","hostname":"%s"}\\n\' "$(hostname)" > /data/lifecycle-sentinel.json; fi\nexec nginx');
  const pkg = await require('./native_package_cases.cjs').build(h, value);
  const instances = [await native.install(h, pkg.package, value, 'lifecycle-first'), await native.install(h, pkg.package, value, 'lifecycle-second')];
  const views = instances.map(v => native.inspect(h, v, run));
  h.check('Lifecycle fixture consists of two distinct original containers and persistent mount roots', views[0].id !== views[1].id && views[0].mounts[0].source !== views[1].mounts[0].source);
  const networkLines = fs.readFileSync(path.join(config.platformRoot, 'services/runtime/core/.env'), 'utf8').split('\n').filter(v => v.startsWith('APPS_NETWORK='));
  if (networkLines.length !== 1 || !/^[A-Za-z0-9_.-]+$/.test(networkLines[0].slice(13))) throw new h.Blocked('Single declared native network required');
  const network = networkLines[0].slice(13), before = instances.map((v, i) => ({ requestId: v.id, id: views[i].id, view: views[i], binding: binding(inspect(run, views[i].id)) }));
  exactTargets(run, network, before.map(v => v.id));
  const scripts = ['native-runtime-stop.sh', 'native-runtime-start.sh'].map(name => {
    const script = path.join(config.platformRoot, 'scripts', name), canonical = path.join(os.homedir(), 'dataspace/magicPlatform/scripts', name), sha256 = hash(fs.readFileSync(canonical));
    if (hash(fs.readFileSync(script)) !== sha256) throw new h.Blocked('Isolated formal helper differs from canonical candidate');
    return { path: script, canonical, sha256 };
  });
  const image = JSON.parse(run('docker', ['image', 'inspect', before[0].binding.image], options))[0];
  if (image.Id !== before[0].binding.image || Object.keys(image.Config?.Volumes || {}).length) throw new h.Blocked('Mount-free already local negative probe image required');
  const privateRoot = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'magictest-native-lifecycle-'));
  const r = { kind: 'native-lifecycle-probe', phase: 'prepared', privateRoot, env: path.join(privateRoot, 'runtime.env'), journal: path.join(privateRoot, 'resume.json'),
    config: isolationConfig(config), network, scripts, sentinelNonce, probeImageLabels: image.Config?.Labels || {}, origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), packageId: pkg.package.id,
    nativeIds: instances.map(v => v.id), before, resume: before.map(v => resume(inspect(run, v.id), network)), probes: [], commands: [], ownerReads: [], peers: [] };
  fs.writeFileSync(r.env, 'APPS_NETWORK=' + network + '\n', { flag: 'wx', mode: 0o600 });
  h.state.resources.push(r); h.persist(); isolation(h, r, run);
  for (const before of r.before) before.sentinel = persistentSentinel(h, r, before, run);
  const routes = instances.flatMap(v => ['/panel/application/deployment-requests/' + v.id,
    '/panel/operations/namespaces/panel/application-deployment-operations/' + v.operation.id, '/panel/application/installations/' + v.installation.id]);
  routes.push(...fixture.installations.map(v => '/panel/application/installations/' + v.id));
  for (const route of routes) r.ownerReads.push({ route, value: (await h.ok(h.admin, 'GET', route)).value });
  const ids = String(run('docker', ['ps', '-a', '-q', '--no-trunc'], options)).trim().split(/\s+/).filter(Boolean);
  for (const id of ids.filter(id => !before.some(v => v.id === id))) {
    const c = inspect(run, id); r.peers.push({ id: c.Id, value: { binding: peerBinding(c), state: processState(c) } });
  }
  if (!r.peers.some(v => v.value.binding.name === '/magicPanel')) throw new h.Blocked('Actual unrelated core peer required');
  h.persist(); return { r, instances, pkg };
}
async function execute(h, negative) {
  const { r, instances, pkg } = await prepare(h);
  let primaryError;
  try {
    if (negative) {
      for (const variant of variants(crypto.randomBytes(16).toString('hex'))) {
        const p = createProbe(h, r, variant);
        exactTargets(execFileSync, r.network, r.before.map(v => v.id), [p.id]);
        const c = dispatch(h, r, 'remove');
        // A refusal alone cannot prove that earlier valid candidates survived.
        intact(h, r, true); peers(h, r); await owners(h, r);
        for (const instance of instances) h.check('Each refusal preserves exact original volume probe and running configuration',
          same(native.inspect(h, instance), r.before.find(v => v.requestId === instance.id).view));
        for (const before of r.before) h.check('Each refusal preserves original first-start-only persistent data', same(persistentSentinel(h, r, before), before.sentinel));
        h.check('Unchanged formal remove helper explicitly refuses entire forged ownership/path candidate set', c.exitCode === 1 && c.ownershipRefused === true);
        c.outcome = 'rejected-and-unchanged'; h.persist(); removeProbe(h, r, p);
      }
    } else {
      const c = dispatch(h, r, 'stop');
      h.check('Formal native stop helper completed', c.exitCode === 0);
      assertJournal(JSON.parse(fs.readFileSync(r.journal)), r.resume);
      intact(h, r, false); peers(h, r); await owners(h, r);
      c.outcome = 'stopped-and-journaled'; h.persist();
    }
  } catch (error) { primaryError = error; r.primaryFailure = { type: error.name }; h.persist(); }
  try { await cleanup(h, r); }
  catch (error) {
    r.recoveryFailure = { type: error.name }; h.persist();
    h.observe({ kind: 'native-lifecycle-recovery-open', primaryFailure: r.primaryFailure, recoveryFailure: r.recoveryFailure });
    if (!primaryError) throw error;
  }
  if (primaryError) throw primaryError;
  await finish(h, r, instances, pkg);
  await h.partial(negative ? 'Implemented formal native remove ownership/path refusal for five real stopped mount-free probes, dual exact runtime/volume and unrelated peer preservation. Full Panel cleanup, reset and every runtime directory gate remain open.'
    : 'Implemented formal native helper stop/resume of both original native containers with complete journal, same ID/image/mount/file and independent owner/core/model peer preservation. Full platform stop/start, ingress drain, in-flight original operations, restart recovery and post-restart business writes remain open.');
}
async function finish(h, r, instances, pkg) {
  if (r.phase !== 'deleted') throw new h.Blocked('Original native lifecycle must be restored before final disposition');
  for (const instance of instances) { guard(h, instance); await native.cleanup(h, instance); peers(h, r); }
  await require('./native_provider_access_cases.cjs').cleanup(h, pkg);
  for (const item of r.ownerReads.filter(v => !instances.some(instance => v.route === '/panel/application/installations/' + instance.installation.id))) {
    const current = (await h.ok(h.admin, 'GET', item.route)).value;
    h.check('Formal source retirement preserves durable request facts through its public history projection and all unrelated owner facts',
      item.route.startsWith('/panel/application/deployment-requests/') ? native.survivingRequest(item.value, current) : same(current, item.value));
  }
  peers(h, r);
}
const ownership = h => execute(h, true), lifecycle = h => execute(h, false);
ownership.transport = lifecycle.transport = 'owner-api';
module.exports = { handlers: { 'F061-002': ownership, 'F061-003': lifecycle }, binding, resume, assertJournal, exactTargets, isolation, dispatch, intact,
  probeMatches, variants, createProbe, removeProbe, cleanup, guard, prepare, finish };
