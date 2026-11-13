const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), https = require('node:https');
const { execFileSync } = require('node:child_process');
const { requestAt, prepare } = require('./tls_delivery_cases.cjs');
test('formal modes retain original TLS material; strict transport distinguishes trust, SAN, HTTP failures and bounded reads', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'regression-tls-delivery-test-'));
  const platform = path.join(os.homedir(), 'dataspace/magicPlatform'), original = path.join(root, 'original'), scratch = path.join(root, 'copies');
  fs.mkdirSync(scratch, { mode: 0o700 });
  let server, calls = 0;
  try {
    execFileSync('sh', ['-c', 'set -eu; . "$1"; deployment_materialize_tls local.vpc "$2" "$3"', 'tls-test',
      path.join(platform, 'scripts/deployment-tls.sh'), original, path.join(platform, 'scripts/reload-traefik-tls.sh')],
      { env: { ...process.env, TLS_MODE: 'local-ca' }, stdio: 'pipe' });
    const h = { fs, path, check(label, value) { assert.ok(value, label); } }, prepared = prepare(h, platform, original, scratch);
    assert.equal(prepared.modes.length, 2); assert.ok(prepared.originalUnchanged());
    server = https.createServer({ key: fs.readFileSync(path.join(original, 'tls.key')), cert: fs.readFileSync(path.join(original, 'tls.crt')) }, (request, response) => {
      calls++;
      response.statusCode = request.url === '/failed' ? 503 : 200;
      response.end(request.url === '/large' ? 'x'.repeat(65537) : JSON.stringify({ value: { namespace: request.headers.host.split('.')[0] } }));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port;
    for (const mode of prepared.modes) {
      const result = await requestAt('127.0.0.1', port, 'panel.local.vpc', mode.ca);
      assert.equal(result.status, 200); assert.equal(result.fingerprint, prepared.leafDigest); assert.equal(result.data.value.namespace, 'panel');
    }
    const before = calls;
    await assert.rejects(requestAt('127.0.0.1', port, 'wrong.invalid', prepared.modes[0].ca), error => error.code === 'ERR_TLS_CERT_ALTNAME_INVALID');
    await assert.rejects(requestAt('127.0.0.1', port, 'panel.local.vpc', undefined), error => ['UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'SELF_SIGNED_CERT_IN_CHAIN', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY'].includes(error.code));
    assert.equal(calls, before);
    assert.equal((await requestAt('127.0.0.1', port, 'panel.local.vpc', prepared.modes[0].ca, '/failed')).status, 503);
    await assert.rejects(requestAt('127.0.0.1', port, 'panel.local.vpc', prepared.modes[0].ca, '/large'), /budget exceeded/);
    assert.ok(prepared.originalUnchanged());
  } finally { if (server) await new Promise(resolve => server.close(resolve)); fs.rmSync(root, { recursive: true, force: true }); }
});

test('formal TLS rotation and restoration confirm actual served material and never replay an unresolved reload', async () => {
  const { materialize, digests, applyMaterial } = require('./tls_delivery_cases.cjs');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'tls-rotation-tools-')), platform = path.join(os.homedir(), 'dataspace/magicPlatform');
  const original = path.join(root, 'original'), next = path.join(root, 'next'), managed = path.join(root, 'managed');
  let server, reloads = 0;
  const h = { fs, path, Blocked: Error, persist() {}, check(label, value) { assert.ok(value, label); } };
  try {
    materialize(platform, undefined, original, 'local-ca'); materialize(platform, undefined, next, 'local-ca'); materialize(platform, original, managed);
    server = https.createServer({ key: fs.readFileSync(path.join(managed, 'tls.key')), cert: fs.readFileSync(path.join(managed, 'tls.crt')) }, (req, res) => {
      const namespace = req.headers.host.split('.')[0]; res.statusCode = namespace === 'missing' ? 404 : 200;
      res.end(JSON.stringify(namespace === 'missing' ? {} : { value: { namespace } }));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port, r = { platformRoot: platform, originalRoot: managed, commands: [], unknownHost: 'missing.local.vpc', hosts: ['panel', 'tenant-a', 'tenant-b'].map(namespace => ({ namespace, host: namespace + '.local.vpc', port })) };
    const run = (command, args, options) => {
      if (args[0] === '-c') return execFileSync(command, args, options);
      assert.equal(command, 'sh'); assert.deepEqual(args, [path.join(platform, 'scripts/reload-traefik-tls.sh')]); reloads++;
      server.setSecureContext({ key: fs.readFileSync(path.join(managed, 'tls.key')), cert: fs.readFileSync(path.join(managed, 'tls.crt')) });
      return Buffer.alloc(0);
    };
    await applyMaterial(h, r, next, 'rotate', run); assert.equal(reloads, 1); assert.deepEqual(digests(h, managed), digests(h, next));
    r.commands[0].outcome = 'unknown';
    await applyMaterial(h, r, next, 'rotate', () => assert.fail('unknown reload cannot be replayed'));
    assert.equal(r.commands[0].outcome, 'confirmed-by-current-served-leaf');
    await applyMaterial(h, r, original, 'restore', run); assert.equal(reloads, 2); assert.deepEqual(digests(h, managed), digests(h, original));
    r.commands.push({ stage: 'foreign', outcome: 'unknown' });
    await assert.rejects(applyMaterial(h, r, next, 'foreign', () => assert.fail('no replay')), /never replay/);
    assert.equal(r.commands[2].outcome, 'unknown');
  } finally { if (server) await new Promise(resolve => server.close(resolve)); fs.rmSync(root, { recursive: true, force: true }); }
});

test('TLS restoration guard protects original private backups, actor, daemon, paths and unrelated core runtimes', t => {
  const { materialize, digests, rotationGuard } = require('./tls_delivery_cases.cjs');
  const base = fs.realpathSync(os.tmpdir());
  const root = fs.mkdtempSync(path.join(base, 'tls-guard-tools-')), scratch = fs.mkdtempSync(path.join(base, 'magictest-tls-rotation-')), platform = path.join(os.homedir(), 'dataspace/magicPlatform');
  const managed = path.join(root, 'services/secret/tls'), backup = path.join(scratch, 'original'), candidate = path.join(scratch, 'next');
  const h = { fs, path, Blocked: Error, admin: { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.local.vpc' } };
  try {
    materialize(platform, undefined, managed, 'local-ca'); materialize(platform, managed, backup); materialize(platform, undefined, candidate, 'local-ca');
    const containers = [{ name: '/traefik', id: 'original-ingress', image: 'original-image', running: true, mounts: [{ source: managed, target: '/etc/traefik/tls', type: 'bind', writable: false }] }, { name: '/magicPanel', id: 'original-core', startedAt: 'original-start', running: true }];
    const r = { kind: 'tls-material-restore', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, platformRoot: root, daemonId: 'original-daemon', originalRoot: managed, scratch, backup, candidate,
      originalDigests: digests(h, backup), candidateDigests: digests(h, candidate), containers: structuredClone(containers) };
    const config = { platformRoot: root, daemonId: r.daemonId };
    assert.deepEqual(rotationGuard(h, r, config, containers), r.originalDigests);
    const alias = path.join(root, 'tmp-alias'); fs.symlinkSync(base, alias); t.mock.method(os, 'tmpdir', () => alias);
    assert.deepEqual(rotationGuard(h, r, config, containers), r.originalDigests);
    for (const redirected of [path.join(alias, path.basename(scratch)), path.join(root, path.basename(scratch))]) {
      const changed = { ...r, scratch: redirected, backup: path.join(redirected, 'original'), candidate: path.join(redirected, 'next') };
      assert.throws(() => rotationGuard(h, changed, config, containers), /paths/);
    }
    for (const mutate of [v => v.actorIdentity.account = 'other', v => v.daemonId = 'other', v => v.backup = candidate, v => v.originalRoot = root, v => v.containers[1].startedAt = 'changed', v => v.containers[0].id = 'other']) {
      const changed = structuredClone(r); mutate(changed); assert.throws(() => rotationGuard(h, changed, config, containers));
    }
    fs.chmodSync(path.join(backup, 'tls.key'), 0o644); assert.throws(() => rotationGuard(h, r, config, containers), /backup/); fs.chmodSync(path.join(backup, 'tls.key'), 0o600);
    fs.writeFileSync(path.join(managed, 'tls.crt'), 'foreign material'); assert.throws(() => rotationGuard(h, r, config, containers), /foreign/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); fs.rmSync(scratch, { recursive: true, force: true }); }
});

test('Docker mount and container ordering never changes TLS ownership but actual mount changes do', () => {
  const { canonicalContainers } = require('./tls_delivery_cases.cjs');
  const rows = [{ name: '/traefik', id: 'original', mounts: [{ source: '/one', target: '/a', writable: false }, { source: '/two', target: '/b', writable: true }] }, { name: '/magicPanel', id: 'core', mounts: [] }];
  const reordered = structuredClone(rows).reverse(); reordered[1].mounts.reverse();
  assert.deepEqual(canonicalContainers(rows), canonicalContainers(reordered));
  reordered[1].mounts[0].writable = false;
  assert.notDeepEqual(canonicalContainers(rows), canonicalContainers(reordered));
  assert.equal(rows[0].mounts[0].target, '/a');
});
