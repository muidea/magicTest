// Offline tool tests: all Docker/shell exchanges are explicit test doubles.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const tool = require('./deployment_material_cases.cjs');
function fixture(t) {
  const privateRoot = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'magictest-deployment-material-'));
  t.after(() => fs.rmSync(privateRoot, { recursive: true, force: true }));
  t.mock.method(os, 'hostname', () => 'a'.repeat(12));
  const root = path.join(privateRoot, 'deployment'); fs.mkdirSync(root);
  const original = path.join(privateRoot, 'formal-source'); fs.writeFileSync(original, '# offline source fixture\n');
  const copy = path.join(root, 'formal-source'); fs.copyFileSync(original, copy);
  const data = path.join(root, 'fixture.bin'); fs.writeFileSync(data, Buffer.from([0, 255, 1, 128]), { mode: 0o600 });
  const config = { platformRoot: '/tmp/platform-executor-offline-material', dockerDataRoot: '/tmp/docker-data', daemonId: 'offline-daemon', containerId: 'a'.repeat(64) };
  const configFile = path.join(privateRoot, 'config.json'); fs.writeFileSync(configFile, JSON.stringify(config));
  const h = { admin: { origin: 'https://panel.local.vpc', identity: { namespace: 'panel', account: 'platform-admin' } },
    deliveryFixtureConfig: configFile, Blocked: Error, state: { resources: [] }, persist() {}, observe() {}, check: (m, c) => assert.ok(c, m) };
  const row = { Id: 'b'.repeat(64), Name: '/magicPanel', Image: 'sha256:' + 'c'.repeat(64), State: { Running: true, Restarting: false, StartedAt: '2026-11-10T00:00:00Z', Pid: 10 },
    Mounts: [], Config: { Env: ['PRIVATE_VALUE=private-env-material'] }, NetworkSettings: { Networks: { ordinary: {} } }, RestartCount: 0 };
  const calls = [], run = (bin, args) => {
    calls.push({ bin, args });
    if (bin === 'docker' && args[0] === 'info') return JSON.stringify({ ID: config.daemonId, DockerRootDir: config.dockerDataRoot, Driver: 'overlay2' });
    if (bin === 'docker' && args[0] === 'ps') return row.Id + '\n';
    if (bin === 'docker' && args[0] === 'inspect') return JSON.stringify([row]);
    if (bin === 'docker' && args[0] === 'image') return JSON.stringify([{ Id: row.Image, RepoDigests: ['repo@' + row.Image] }]);
    throw Error('Unexpected offline exchange');
  };
  const r = { kind: 'deployment-material-probe', phase: 'prepared', privateRoot, root, config,
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
    sources: [{ original, copy, sha256: 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(original)).digest('hex') }],
    commands: [], tracked: ['fixture.bin'] };
  r.originalFiles = r.expectedFiles = tool.fileFacts(root, r.tracked); r.originalPeers = tool.peers(run); h.state.resources.push(r);
  return { h, r, run, calls, row, configFile, data };
}
test('finite file facts include binary bytes, mode and exact numeric ownership without leaking data', t => {
  const f = fixture(t), actual = tool.fileFacts(f.r.root, f.r.tracked)['fixture.bin'];
  assert.equal(actual.mode, 0o600); assert.equal(actual.uid, process.getuid()); assert.equal(actual.gid, process.getgid()); assert.equal(actual.size, 4);
  assert.match(actual.sha256, /^sha256:[a-f0-9]{64}$/);
  fs.writeFileSync(f.data, 'changed'); assert.notDeepEqual(tool.fileFacts(f.r.root, f.r.tracked), f.r.originalFiles);
});
test('aliased TMPDIR permits canonical scratch but never a linked or foreign root', t => {
  const f = fixture(t), base = fs.realpathSync(os.tmpdir()), alias = path.join(f.r.privateRoot, 'tmp-alias');
  fs.symlinkSync(base, alias); t.mock.method(os, 'tmpdir', () => alias);
  tool.validate(f.h, f.r, f.run);
  const original = f.r.privateRoot;
  f.r.privateRoot = path.join(alias, path.basename(original));
  assert.throws(() => tool.validate(f.h, f.r, f.run), /private deployment root/);
  f.r.privateRoot = original;
  const foreign = fs.mkdtempSync(path.join(original, 'magictest-deployment-material-'));
  f.r.privateRoot = foreign;
  assert.throws(() => tool.validate(f.h, f.r, f.run), /private deployment root/);
});
test('file evidence refuses symbolic links, parent traversal and privilege bits', t => {
  const f = fixture(t); fs.symlinkSync(f.data, path.join(f.r.root, 'linked'));
  assert.throws(() => tool.fileFacts(f.r.root, ['linked']), /traverse/);
  assert.throws(() => tool.fileFacts(f.r.root, ['../formal-source']), /traverse/);
  fs.chmodSync(f.data, 0o4600); assert.throws(() => tool.fileFacts(f.r.root, f.r.tracked), /Ordinary/);
});
test('peer observations bind actual identity and private config hash while omitting raw Env', t => {
  const f = fixture(t), before = tool.peers(f.run);
  assert.equal(JSON.stringify(before).includes('private-env-material'), false);
  f.row.Config.Env = ['PRIVATE_VALUE=other']; assert.notDeepEqual(tool.peers(f.run), before);
  f.row.Id = 'short'; assert.throws(() => tool.peers(f.run), /Complete daemon/);
});
test('peer binding ignores Docker mount and object-key order while retaining every config, mount and network value', t => {
  const f = fixture(t);
  f.row.Mounts = [{ Destination: '/a', Source: '/one', RW: false }, { Destination: '/b', Source: '/two', RW: true }];
  f.row.Config.Labels = { second: 'two', first: 'one' };
  const before = tool.peers(f.run);
  f.row.Mounts.reverse(); f.row.Config.Labels = { first: 'one', second: 'two' };
  f.row.Config = Object.fromEntries(Object.entries(f.row.Config).reverse());
  assert.deepEqual(tool.peers(f.run), before);
  for (const mutate of [r => r.Mounts[0].Source = '/foreign', r => r.Mounts[0].RW = false,
    r => r.Config.Labels.first = 'changed', r => r.Config.Env.reverse().push('ADDED=value'),
    r => r.NetworkSettings.Networks.ordinary.IPAddress = 'changed', r => r.State.StartedAt = 'changed',
    r => r.State.Pid++, r => r.RestartCount++]) {
    const saved = structuredClone(f.row); mutate(f.row); assert.notDeepEqual(tool.peers(f.run), before);
    Object.keys(f.row).forEach(key => delete f.row[key]); Object.assign(f.row, saved);
  }
});
test('changed source, actor, daemon or root blocks before a formal command intent', t => {
  const f = fixture(t), origin = f.h.admin.origin, bytes = fs.readFileSync(f.r.sources[0].copy);
  f.h.admin.origin = 'https://other.invalid'; assert.throws(() => tool.dispatch(f.h, f.r, 'actor', 'sh', [], {}, f.run)); f.h.admin.origin = origin;
  fs.appendFileSync(f.r.sources[0].copy, '# changed'); assert.throws(() => tool.dispatch(f.h, f.r, 'source', 'sh', [], {}, f.run)); fs.writeFileSync(f.r.sources[0].copy, bytes);
  const run = (bin, args) => args[0] === 'info' ? JSON.stringify({ ID: 'replacement' }) : f.run(bin, args);
  assert.throws(() => tool.dispatch(f.h, f.r, 'daemon', 'sh', [], {}, run));
  const root = f.r.root; f.r.root = f.r.privateRoot; assert.throws(() => tool.dispatch(f.h, f.r, 'root', 'sh', [], {}, f.run)); f.r.root = root;
  assert.equal(f.r.commands.length, 0); assert.equal(f.calls.some(v => v.bin === 'sh'), false);
});
test('formal command persists once before dispatch and accepts only the declared exact refusal', t => {
  const f = fixture(t); let persisted = false, sent = 0;
  f.h.persist = () => { persisted = true; };
  const run = (bin, args, options) => {
    if (bin !== 'sh') return f.run(bin, args);
    sent++; assert.equal(persisted, true); assert.equal(f.r.commands[0].outcome, 'unknown');
    assert.equal(options.env.MAGIC_DEPLOYMENT_MODE, 'release'); assert.equal(options.env.MAGIC_DEPLOYMENT_IMAGE_RESOLVE_POLICY, 'pull');
    throw Object.assign(Error('refusal'), { status: 1, stderr: 'image lock validation failed: exact stage private-material' });
  };
  const c = tool.dispatch(f.h, f.r, 'original', 'sh', ['formal'], { mode: 'release', expected: 1, diagnostic: /image lock validation failed:/ }, run);
  assert.equal(c.targetDiagnosticMatched, true); assert.equal(c.outcome, 'process-exited'); assert.equal(sent, 1);
  assert.equal(fs.statSync(c.outputPath).mode & 0o777, 0o600); assert.equal(JSON.stringify(c).includes('private-material'), false);
  assert.throws(() => tool.dispatch(f.h, f.r, 'original', 'sh', [], {}, run), /no replay/); assert.equal(sent, 1);
});
test('earlier dependency errors or wrong status never become target-stage rejection proof', t => {
  const f = fixture(t);
  for (const [status, diagnostic] of [[1, 'jq is required'], [2, 'required target stage']]) {
    const run = (bin, args) => { if (bin === 'sh') throw Object.assign(Error('failed'), { status, stderr: diagnostic }); return f.run(bin, args); };
    assert.throws(() => tool.dispatch(f.h, f.r, 'negative-' + status, 'sh', [], { expected: 1, diagnostic: /required target stage/ }, run), /exact declared stage/);
  }
});
test('killed or lost formal commands stay unknown and cannot replay or close cleanup', t => {
  const f = fixture(t); let sent = 0;
  const run = (bin, args) => { if (bin === 'sh') { sent++; throw Object.assign(Error('killed'), { signal: 'SIGKILL' }); } return f.run(bin, args); };
  assert.throws(() => tool.dispatch(f.h, f.r, 'original', 'sh', [], {}, run));
  assert.equal(f.r.commands[0].outcome, 'unknown');
  assert.throws(() => tool.dispatch(f.h, f.r, 'replacement', 'sh', [], {}, run), /no replay/);
  assert.throws(() => tool.cleanup(f.h, f.r, f.run), /without replay/); assert.equal(sent, 1); assert.equal(f.r.phase, 'prepared');
});
test('cleanup confirms only exact original peers and expected file bytes/modes/owners', t => {
  const f = fixture(t); f.r.commands.push({ key: 'original', exitCode: 0, outcome: 'process-exited' });
  f.row.State.Pid++; assert.throws(() => tool.cleanup(f.h, f.r, f.run), /containers/); f.row.State.Pid--;
  fs.chmodSync(f.data, 0o640); assert.throws(() => tool.cleanup(f.h, f.r, f.run), /fixture bytes/); fs.chmodSync(f.data, 0o600);
  assert.match(tool.cleanup(f.h, f.r, f.run).proof, /independently/); assert.equal(f.r.phase, 'deleted'); assert.equal(fs.existsSync(f.data), true);
});
test('lock positive control is based on an actual local immutable image, never a fabricated image ID', t => {
  const f = fixture(t), image = tool.localInstaller(f.run), lock = tool.imageLock(image);
  assert.equal(lock.apiVersion, 'magic.images.lock/v1'); assert.equal(lock.images[0].digest, image.Id);
  assert.equal(lock.images[0].reference, 'docker.io/muidea/magicinstaller'); assert.equal(lock.images[0].tag, 'master');
  assert.equal(f.calls.some(v => ['pull', 'build', 'tag', 'run'].includes(v.args[0])), false);
  assert.throws(() => tool.localInstaller(() => JSON.stringify([{ Id: 'master' }])), /Already local/);
});
test('bad lock preflight follows successful actual-lock control and never reuses any actual digest', t => {
  const f = fixture(t), image = tool.localInstaller(f.run); let calls = 0;
  const run = (bin, args) => { if (bin === 'sh') { calls++; const lock = JSON.parse(fs.readFileSync(path.join(f.r.root, 'services/images.lock.json'))); assert.equal(lock.images[0].digest, image.Id); return ''; } return f.run(bin, args); };
  fs.mkdirSync(path.join(f.r.root, 'services'));
  tool.lockPreflight(f.h, f.r, image, run); assert.equal(calls, 1); assert.equal(f.r.lock.actual, image.Id);
  assert.notEqual(f.r.lock.mismatched, image.Id); assert.match(f.r.lock.mismatched, /^sha256:[a-f0-9]{64}$/);
});
test('failed positive lock control cannot proceed to a manufactured wrong-digest negative', t => {
  const f = fixture(t), image = tool.localInstaller(f.run); fs.mkdirSync(path.join(f.r.root, 'services'));
  const run = (bin, args) => { if (bin === 'sh') throw Object.assign(Error('missing toolchain'), { status: 1, stderr: 'helper unavailable' }); return f.run(bin, args); };
  assert.throws(() => tool.lockPreflight(f.h, f.r, image, run)); assert.equal(f.r.lock, undefined);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.r.root, 'services/images.lock.json'))).images[0].digest, image.Id);
});
test('complete image inventory deduplicates references but refuses omissions, extras and empty declarations', () => {
  assert.deepEqual(tool.references('', true), []); // Disabled profile-only Compose output is legitimately empty.
  const actual = tool.references('native:master\ncore:master\nnative:master\ndocker.io/muidea/magicinstaller:master\n');
  tool.assertInventory(actual, ['core:master'], ['native:master', 'native:master']);
  for (const values of [actual.slice(1), [...actual, 'stray:master'], []]) assert.throws(() => tool.assertInventory(values, ['core:master'], ['native:master']));
  assert.throws(() => tool.assertInventory(actual, [], ['native:master'])); assert.throws(() => tool.assertInventory(actual, ['core:master'], []));
  for (const value of ['', 'repo:tag\nsecret value', '--invalid', 'repo:tag;command']) assert.throws(() => tool.references(value));
});
test('recovered cleanup binds exact daemon/root/source/commands and retained original/displaced facts', t => {
  const { r } = fixture(t), { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
  r.displacedFiles = { exact: true }; r.snapshot = { sha256: 'original' }; r.lock = { actual: 'original', mismatched: 'negative' };
  const evidence = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, evidence)[0], r);
  for (const mutate of [v => v.config.daemonId = 'foreign', v => v.root += '-other', v => v.sources[0].sha256 = 'foreign',
    v => v.commands.push({ key: 'unknown', outcome: 'unknown' }), v => v.originalFiles['fixture.bin'].sha256 = 'other',
    v => v.expectedFiles['fixture.bin'].mode = 0o777, v => v.originalPeers[0].id = 'other', v => v.displacedFiles = {},
    v => v.snapshot.sha256 = 'other', v => v.lock.actual = 'other']) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /immutable cleanup evidence/);
  }
});
test('native final disposition cannot run until exact lifecycle recovery is complete', async () => {
  const native = require('./native_lifecycle_cases.cjs');
  await assert.rejects(native.finish({ Blocked: Error }, { phase: 'prepared' }, [], {}), /restored before/);
});
