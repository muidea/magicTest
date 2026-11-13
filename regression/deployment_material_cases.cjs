// Existing deployment owners, real private files and actual local image facts.
// This module never invents application state, migration or update receipts.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const { validateIsolation } = require('./delivery_fixture.cjs');
const native = require('./native_lifecycle_cases.cjs');
const opts = { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 8 * 1024 * 1024 };
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
const configIdentity = c => Object.fromEntries(['platformRoot', 'dockerDataRoot', 'daemonId', 'containerId'].map(k => [k, c[k]]));
const ordered = value => Array.isArray(value) ? value.map(ordered) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])])) : value;
function peers(run = execFileSync) {
  const ids = String(run('docker', ['ps', '-a', '-q', '--no-trunc'], opts)).trim().split(/\s+/).filter(Boolean).sort();
  return ids.map(id => {
    if (!/^[a-f0-9]{64}$/.test(id)) throw Error('Complete daemon container IDs required');
    const c = JSON.parse(run('docker', ['inspect', id], opts))[0];
    if (c.Id !== id) throw Error('Original exact container observation changed');
    return { id, name: c.Name, image: c.Image, running: c.State?.Running, startedAt: c.State?.StartedAt,
      restarting: c.State?.Restarting, pid: c.State?.Pid, restarts: c.RestartCount,
      // No unrelated Env, command, health log or credentials in public evidence.
      bindingDigest: digest(JSON.stringify(ordered({ mounts: [...c.Mounts].sort((a, b) => a.Destination.localeCompare(b.Destination)),
        config: c.Config, networks: c.NetworkSettings?.Networks }))) };
  });
}
function fileFacts(root, names) {
  return Object.fromEntries(names.map(name => {
    const file = path.join(root, name);
    if (path.relative(root, file).startsWith('..') || fs.realpathSync(file) !== file) throw Error('Owned regular fixture paths cannot traverse links or parents');
    const st = fs.lstatSync(file);
    if (!st.isFile() || st.mode & 0o7000) throw Error('Ordinary finite fixture files required');
    return [name, { sha256: digest(fs.readFileSync(file)), size: st.size, mode: st.mode & 0o777, uid: st.uid, gid: st.gid }];
  }));
}
function validate(h, r, run = execFileSync) {
  if (h.admin.origin !== r.origin || !same(h.admin.identity, r.actorIdentity)) throw new h.Blocked('Original deployment material actor required');
  const config = JSON.parse(fs.readFileSync(h.deliveryFixtureConfig));
  if (!same(configIdentity(config), r.config)) throw new h.Blocked('Original isolated deployment identity changed');
  validateIsolation(config, JSON.parse(run('docker', ['info', '--format', '{{json .}}'], opts)));
  if (!r.privateRoot.startsWith(fs.realpathSync(os.tmpdir()) + '/magictest-deployment-material-') || fs.realpathSync(r.privateRoot) !== r.privateRoot ||
      r.root !== path.join(r.privateRoot, 'deployment') || fs.realpathSync(r.root) !== r.root) throw new h.Blocked('Original private deployment root required');
  for (const s of r.sources) if (digest(fs.readFileSync(s.original)) !== s.sha256 || digest(fs.readFileSync(s.copy)) !== s.sha256)
    throw new h.Blocked('Original formal deployment source bytes changed');
}
function dispatch(h, r, key, binary, args, { mode = 'development', expected = 0, diagnostic, env = {} } = {}, run = execFileSync) {
  validate(h, r, run);
  if (r.commands.some(c => c.key === key || !Number.isInteger(c.exitCode))) throw new h.Blocked('Original deployment command unknown or already dispatched; no replay');
  const c = { key, binary, args, mode, expected, outcome: 'unknown', startedAt: Date.now() };
  r.commands.push(c); h.persist(); let output;
  try {
    output = run(binary, args, { ...opts, cwd: r.root, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1',
      MAGIC_DEPLOYMENT_USER_HANDOFF: '1', MAGIC_DEPLOYMENT_MODE: mode,
      MAGIC_DEPLOYMENT_IMAGE_RESOLVE_POLICY: mode === 'development' ? 'local' : 'pull', DOMAIN: '', SERVICES_NETWORK: '', ...env } });
    c.exitCode = 0;
  } catch (error) {
    if (Number.isInteger(error.status) && !error.signal) c.exitCode = error.status;
    output = String(error.stdout || '') + String(error.stderr || ''); c.errorType = error.name;
  }
  c.finishedAt = Date.now();
  // Raw command output can include local material; retain privately, export hash.
  c.outputPath = path.join(r.privateRoot, 'command-' + r.commands.length + '.log');
  fs.writeFileSync(c.outputPath, String(output || ''), { flag: 'wx', mode: 0o600 });
  c.outputDigest = digest(String(output || '')); c.targetDiagnosticMatched = diagnostic ? diagnostic.test(String(output || '')) : true;
  if (Number.isInteger(c.exitCode)) c.outcome = 'process-exited';
  h.persist();
  h.check('Formal deployment command reaches exact declared stage: ' + key, c.exitCode === expected && c.targetDiagnosticMatched, {
    key, expected, exitCode: c.exitCode, targetDiagnosticMatched: c.targetDiagnosticMatched, outputDigest: c.outputDigest });
  return c;
}
async function prepare(h, run = execFileSync) {
  await require('./delivery_cases.cjs').fixture(h);
  const config = JSON.parse(fs.readFileSync(h.deliveryFixtureConfig));
  const privateRoot = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'magictest-deployment-material-')), root = path.join(privateRoot, 'deployment');
  fs.mkdirSync(path.join(root, 'scripts'), { recursive: true, mode: 0o700 });
  fs.mkdirSync(path.join(root, 'services/oem'), { recursive: true, mode: 0o700 });
  const canonical = path.join(os.homedir(), 'dataspace/magicPlatform');
  const names = ['initialize.sh', 'reset.sh', 'backup.sh', 'restore.sh', 'services/oem/oem.json',
    ...fs.readdirSync(path.join(canonical, 'scripts')).filter(v => /\.(sh|py)$/.test(v)).map(v => 'scripts/' + v)];
  const sources = names.map(name => {
    const original = path.join(canonical, name), copy = path.join(root, name), bytes = fs.readFileSync(original);
    fs.writeFileSync(copy, bytes, { flag: 'wx', mode: fs.statSync(original).mode & 0o777 });
    return { original, copy, sha256: digest(bytes) };
  });
  // Finite opaque fixture bytes, explicitly not business rows or owner receipts.
  const inputs = { 'services/.env': Buffer.from('DOMAIN_NAME=local.vpc\nSERVICES_NETWORK=magictest-material\n'),
    'services/data/fixture.bin': crypto.randomBytes(39), 'services/secret/fixture.bin': crypto.randomBytes(32),
    'services/runtime/fixture.bin': crypto.randomBytes(41), 'apps/data/first/fixture.bin': crypto.randomBytes(47),
    'apps/data/second/fixture.bin': crypto.randomBytes(53) };
  for (const [name, bytes] of Object.entries(inputs)) {
    const file = path.join(root, name); fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 }); fs.writeFileSync(file, bytes, { flag: 'wx', mode: 0o600 });
  }
  const r = { kind: 'deployment-material-probe', phase: 'prepared', privateRoot, root, sources, config: configIdentity(config),
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, commands: [], tracked: Object.keys(inputs) };
  r.originalFiles = r.expectedFiles = fileFacts(root, r.tracked); r.originalPeers = peers(run);
  if (!r.originalPeers.some(v => v.name === '/magicPanel')) throw new h.Blocked('Actual unrelated core deployment peer required');
  h.state.resources.push(r); h.persist(); validate(h, r, run); return r;
}
function unchanged(h, r, run = execFileSync) {
  h.check('Actual unrelated deployment containers and startup identity remain exact', same(peers(run), r.originalPeers));
  h.check('Original private fixture bytes, modes and numeric owners match intended final state', same(fileFacts(r.root, r.tracked), r.expectedFiles));
}
function cleanup(h, r, run = execFileSync) {
  validate(h, r, run);
  if (r.commands.some(c => !Number.isInteger(c.exitCode))) throw new h.Blocked('Original deployment command result unknown; preserve private root and original command without replay');
  unchanged(h, r, run); r.phase = 'deleted'; h.persist();
  return { proof: 'No application state changed; original daemon peers and finite private fixture files independently match intended final state. Private snapshots, displaced fixture state and original command logs retained outside repositories; no filesystem deletion or business recovery claim.' };
}
function imageLock(image) {
  return { apiVersion: 'magic.images.lock/v1', images: [{ name: 'magicInstaller', reference: 'docker.io/muidea/magicinstaller', tag: 'master', digest: image.Id }] };
}
function localInstaller(run = execFileSync) {
  const image = JSON.parse(run('docker', ['image', 'inspect', 'docker.io/muidea/magicinstaller:master'], opts))[0];
  if (!/^sha256:[a-f0-9]{64}$/.test(image?.Id || '')) throw Error('Already local exact installer image required; no automatic pull');
  return image;
}
function writeLock(r, lock) { fs.writeFileSync(path.join(r.root, 'services/images.lock.json'), JSON.stringify(lock) + '\n', { mode: 0o600 }); }
function lockPreflight(h, r, image, run = execFileSync) {
  writeLock(r, imageLock(image));
  dispatch(h, r, 'valid-original-image-lock', 'sh', ['-c', '. "$1"; deployment_validate_image_lock "$2"', 'image-lock', path.join(r.root, 'scripts/deployment-mode.sh'), r.root], { mode: 'release' }, run);
  unchanged(h, r, run);
  const lock = imageLock(image);
  const used = new Set([image.Id, ...(image.RepoDigests || []).map(v => v.split('@')[1])]);
  let bad; do { bad = 'sha256:' + crypto.randomBytes(32).toString('hex'); } while (used.has(bad));
  lock.images[0].digest = bad; writeLock(r, lock); r.lock = { actual: image.Id, mismatched: bad }; h.persist();
}
async function isolated(h, callback) {
  const r = await prepare(h); let primary;
  try { await callback(r); }
  catch (error) { primary = error; r.primaryFailure = { type: error.name }; h.persist(); }
  try { h.observe({ kind: 'deployment-material-disposition', ...cleanup(h, r) }); }
  catch (error) { r.cleanupFailure = { type: error.name }; h.persist(); if (!primary) throw error; }
  if (primary) throw primary;
}
async function initialization(h) {
  await isolated(h, async r => {
    lockPreflight(h, r, localInstaller());
    dispatch(h, r, 'initialize-rejects-wrong-locked-digest', 'sh', [path.join(r.root, 'initialize.sh')],
      { mode: 'release', expected: 1, diagnostic: /image lock validation failed: image .* does not match locked digest/ });
    unchanged(h, r);
    dispatch(h, r, 'initialize-rejects-missing-oem', 'sh', [path.join(r.root, 'initialize.sh'), '--oem', path.join(r.privateRoot, 'missing-oem.json')],
      { expected: 1, diagnostic: /OEM configuration is unavailable:/ });
    unchanged(h, r);
  });
  await h.partial('Implemented real local image-lock positive control and exact initialize wrong-lock/missing-OEM refusal before changing opaque fixture data or original deployment peers. Full load, valid initialization, Schema/secret/OEM materialization and ordinary business acceptance remain open.');
}
async function coldSnapshot(h) {
  await isolated(h, async r => {
    const archive = path.join(r.privateRoot, 'snapshot.tgz');
    dispatch(h, r, 'cold-backup', 'sh', [path.join(r.root, 'backup.sh'), '--output', archive]);
    dispatch(h, r, 'independent-snapshot-verification', 'python3', ['-B', path.join(r.root, 'scripts/platform-snapshot.py'), 'verify', '--archive', archive]);
    const manifest = JSON.parse(fs.readFileSync(archive + '.json'));
    h.check('Formal complete snapshot binds exact root, SHA256 and private archive/manifest permissions', manifest.deploymentRoot === r.root &&
      manifest.sha256 === digest(fs.readFileSync(archive)).slice(7) && [archive, archive + '.json'].every(p => (fs.statSync(p).mode & 0o777) === 0o600) &&
      r.tracked.every(name => manifest.files.includes(name)));
    for (const name of r.tracked) fs.writeFileSync(path.join(r.root, name), crypto.randomBytes(61), { mode: 0o600 });
    r.displacedFiles = fileFacts(r.root, r.tracked); h.persist();
    dispatch(h, r, 'restore-refuses-existing-without-replace', 'sh', [path.join(r.root, 'restore.sh'), '--archive', archive],
      { expected: 1, diagnostic: /restore target exists; inspect backup and use --replace/ });
    h.check('Refused restore preserves exact changed fixture state', same(fileFacts(r.root, r.tracked), r.displacedFiles));
    dispatch(h, r, 'same-root-stopped-restore', 'sh', [path.join(r.root, 'restore.sh'), '--archive', archive, '--replace']);
    unchanged(h, r);
    const displaced = fs.readdirSync(r.root).filter(v => v.startsWith('.recovery-old-'));
    h.check('Formal restore retains exactly one displaced-state root', displaced.length === 1);
    h.check('All replaced fixture bytes and numeric owners remain independently recoverable', same(fileFacts(path.join(r.root, displaced[0]), r.tracked), r.displacedFiles));
    r.snapshot = { sha256: digest(fs.readFileSync(archive)), restoredFiles: r.originalFiles, displacedRoot: path.join(r.root, displaced[0]) }; h.persist();
  });
  await h.partial('Implemented formal stopped same-root backup/verify/restore on finite actual files across services and two application directories, full original bytes/modes/numeric owners, existing-target refusal and retained displaced state, original deployment peer preservation. No real database/application/secret identity, undelivered owner event, full stop/start or business recovery claim; those remain open.');
}
function references(text, allowEmpty = false) {
  const values = text.trim().split(/\r?\n/).filter(Boolean);
  if (!values.length && !allowEmpty || values.some(v => !/^[A-Za-z0-9][A-Za-z0-9._:/@-]*$/.test(v))) throw Error('Complete nonempty image-reference output required');
  return [...new Set(values)].sort();
}
function assertInventory(actual, compose, nativeImages) {
  const expected = [...new Set([...compose, ...nativeImages, 'docker.io/muidea/magicinstaller:master'])].sort();
  if (!nativeImages.length || !compose.length || !same(actual, expected)) throw Error('Full formal image discovery must match independent Compose and all native declarations');
}
async function imageInventory(h) {
  const bundle = await native.prepare(h), { r } = bundle; let primary;
  try {
    const output = path.join(r.privateRoot, 'all-images.txt'), script = path.join(r.config.platformRoot, 'scripts/image-refresh.sh');
    const bytes = fs.readFileSync(path.join(os.homedir(), 'dataspace/magicPlatform/scripts/image-refresh.sh'));
    h.check('Actual image discovery uses unchanged candidate owner helper', digest(fs.readFileSync(script)) === digest(bytes));
    execFileSync('sh', ['-c', '. "$1"; deployment_collect_image_references "$2" "$3" "$4" "$5"', 'image-discovery', script,
      output, r.config.platformRoot, path.join(r.config.platformRoot, 'services/.env'), path.join(r.config.platformRoot, 'services/runtime/core/.env')], opts);
    const actual = references(fs.readFileSync(output, 'utf8'));
    // Independently enumerate every actual Compose declaration, excluding native
    // generated Compose files (whose owner is their native-runtime manifests).
    const walk = root => !fs.existsSync(root) ? [] : fs.readdirSync(root, { withFileTypes: true }).flatMap(v => v.isDirectory() ? walk(path.join(root, v.name)) : [path.join(root, v.name)]);
    const nativeManifests = walk(path.join(r.config.platformRoot, 'apps/config')).filter(v => v.endsWith('/native-runtime.json'));
    const nativeImages = nativeManifests.flatMap(v => JSON.parse(fs.readFileSync(v)).components.map(c => c.image));
    const pairs = [['services/compose/core/foundation', 'services/.env'], ['services/compose/entry', 'services/.env'],
      ['services/compose/apm', 'services/.env'], ['services/runtime/core/compose', 'services/runtime/core/.env']];
    const ordinary = walk(path.join(r.config.platformRoot, 'apps/compose')).filter(v => v.endsWith('/docker-compose.yaml') && !r.before.some(b => v.endsWith(b.view.composeFile?.split('/compose/')[1] || '<none>')));
    // App paths carry namespace/deployment/application. Their public runtime
    // environment lives under apps/runtime/<namespace>/<deployment>/.env.
    for (const file of ordinary) {
      const parts = path.relative(path.join(r.config.platformRoot, 'apps/compose'), file).split(path.sep);
      if (nativeManifests.some(v => v.startsWith(path.join(r.config.platformRoot, 'apps/config', parts[0], parts[1]) + '/'))) continue;
      pairs.push([path.relative(r.config.platformRoot, path.dirname(file)), 'apps/runtime/' + parts[0] + '/' + parts[1] + '/.env']);
    }
    const compose = [];
    for (const [directory, env] of pairs) for (const file of walk(path.join(r.config.platformRoot, directory)).filter(v => v.endsWith('/docker-compose.yaml'))) {
      const envFile = path.join(r.config.platformRoot, env);
      if (fs.existsSync(envFile)) compose.push(...references(execFileSync('docker-compose', ['--env-file', envFile, '-f', file, 'config', '--images'], opts), true));
    }
    assertInventory(actual, compose, nativeImages);
    const resolved = actual.map(reference => {
      const image = JSON.parse(execFileSync('docker', ['image', 'inspect', reference], opts))[0];
      if (!/^sha256:[a-f0-9]{64}$/.test(image?.Id || '')) throw new h.Blocked('Discovered image has no actual local image identity');
      return { reference, imageId: image.Id };
    });
    h.observe({ kind: 'complete-actual-deployment-image-inventory', helperDigest: digest(bytes), nativeManifestCount: nativeManifests.length,
      resolved, qualification: 'Real image discovery/local identity only; no pull, replacement, update receipt or full update acceptance.' });
  } catch (error) { primary = error; }
  try { await native.cleanup(h, r); }
  catch (error) { if (!primary) throw error; }
  if (primary) throw primary;
  await native.finish(h, r, bundle.instances, bundle.pkg);
  await h.partial('Implemented formal complete initialized image discovery compared with independently enumerated Compose and native manifests, including two formally installed native instances and actual local image IDs; original owner/core/volume preservation and retain uninstall. Real mutable-tag pull, all-component replacement, update-operation receipts and post-update business remain open.');
}
async function resetPolicy(h) {
  await isolated(h, async r => {
    const image = localInstaller(); lockPreflight(h, r, image);
    const refs = path.join(r.privateRoot, 'local-images.txt'); fs.writeFileSync(refs, 'docker.io/muidea/magicinstaller:master\n', { flag: 'wx', mode: 0o600 });
    dispatch(h, r, 'reset-development-forces-local-image-resolution', 'sh', ['-c', '. "$1"; . "$2"; deployment_set_lifecycle_image_policy reset; [ "$MAGIC_DEPLOYMENT_IMAGE_RESOLVE_POLICY" = local ] || exit 91; deployment_refresh_images "$3"',
      'reset-local-policy', path.join(r.root, 'scripts/deployment-mode.sh'), path.join(r.root, 'scripts/image-refresh.sh'), refs],
    { env: { MAGIC_DEPLOYMENT_IMAGE_RESOLVE_POLICY: 'pull' }, diagnostic: /Using local image: docker.io\/muidea\/magicinstaller:master/ });
    h.check('Formal development reset image policy preserves exact already-local image', localInstaller().Id === image.Id);
    dispatch(h, r, 'release-reset-rejects-actual-wrong-image-digest', 'sh', [path.join(r.root, 'reset.sh')],
      { mode: 'release', expected: 1, diagnostic: /image lock validation failed: image .* does not match locked digest/ });
    unchanged(h, r);
  });
  await h.partial('Implemented formal development reset local-image policy helper with already local image identity, positive actual release lock validation then full reset wrong-digest refusal before teardown and fixture/peer preservation. Whole development reset, full release package coverage, rebuild/reinitialization and business verification remain open.');
}
const handlers = { 'F060-001': initialization, 'F060-002': coldSnapshot, 'F063-001': imageInventory, 'F063-002': resetPolicy };
Object.values(handlers).forEach(handler => { handler.transport = 'owner-api'; });
module.exports = { handlers, peers, fileFacts, validate, dispatch, prepare, unchanged, cleanup, imageLock, localInstaller, lockPreflight, references, assertInventory };
