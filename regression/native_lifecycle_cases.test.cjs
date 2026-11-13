// Source-only tool checks. All Docker and shell calls below are explicit doubles;
// no actual daemon, browser, platform or published fixture is contacted.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const tool = require('./native_lifecycle_cases.cjs');
const native = require('./native_runtime_cases.cjs');
const labels = { project: 'com.docker.compose.project', service: 'com.docker.compose.service',
  compose: 'com.docker.compose.project.config_files', directory: 'com.docker.compose.project.working_dir',
  deployment: 'io.platform.deployment-id', application: 'io.platform.runtime.application-uuid' };
function container(letter, running = true) {
  return { Id: letter.repeat(64), Name: '/native-0123456789ab-api-' + letter, Image: 'sha256:' + 'f'.repeat(64),
    State: { Running: running, Restarting: false }, Mounts: [{ Type: 'bind', Source: '/owned/' + letter, Destination: '/data', RW: true }],
    Config: { Labels: { [labels.project]: 'native-0123456789ab', [labels.service]: 'api-' + letter,
      [labels.compose]: '/var/app/application-runtime/compose/panel/deployment/' + letter + '/docker-compose.yaml' },
    Entrypoint: ['/bin/sh'], Cmd: ['-c', 'probe'], WorkingDir: '/data', Hostname: letter.repeat(12) },
    NetworkSettings: { Networks: { owned: { Aliases: ['scoped-' + letter] } } } };
}
function fixture(t) {
  const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'magictest-native-lifecycle-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  t.mock.method(os, 'hostname', () => 'a'.repeat(12));
  const config = { platformRoot: '/tmp/platform-executor-offline-tool', dockerDataRoot: '/tmp/docker-data', daemonId: 'offline-tool', containerId: 'a'.repeat(64) };
  const configPath = path.join(root, 'config.json'); fs.writeFileSync(configPath, JSON.stringify(config));
  const scripts = ['stop.sh', 'start.sh'].map(name => {
    const file = path.join(root, name); fs.writeFileSync(file, '# offline source fixture\n');
    return { path: file, canonical: file, sha256: 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') };
  });
  const rows = [container('a'), container('b')], identity = { account: 'platform-admin', namespace: 'panel' };
  const h = { admin: { identity, origin: 'https://panel.local.vpc' }, deliveryFixtureConfig: configPath, Blocked: Error,
    state: { resources: [] }, persist() {}, observe() {}, check: (message, condition) => assert.ok(condition, message),
    ok: async (_actor, _method, route) => ({ value: { route } }) };
  const r = { kind: 'native-lifecycle-probe', phase: 'prepared', origin: h.admin.origin, actorIdentity: structuredClone(identity), config,
    network: 'owned', scripts, privateRoot: root, env: path.join(root, 'runtime.env'), journal: path.join(root, 'resume.json'),
    packageId: 7, nativeIds: [11, 12], before: rows.map((c, i) => ({ id: c.Id, requestId: 11 + i, binding: tool.binding(c), view: { marker: i } })),
    sentinelNonce: 'offline-sentinel', resume: rows.map(c => tool.resume(c, 'owned')), probes: [], commands: [], peers: [], ownerReads: [{ route: '/owner/original', value: { route: '/owner/original' } }] };
  for (const before of r.before) before.sentinel = { marker: r.sentinelNonce, hostname: before.binding.hostname };
  fs.writeFileSync(r.env, 'APPS_NETWORK=owned\n', { mode: 0o600 });
  h.state.resources.push({ kind: 'native-runtime-request', id: 11 }, { kind: 'native-runtime-request', id: 12 }, r);
  const calls = [], run = (bin, args) => {
    calls.push({ bin, args });
    if (bin === 'docker' && args[0] === 'info') return JSON.stringify({ ID: config.daemonId, DockerRootDir: config.dockerDataRoot, Driver: 'overlay2' });
    if (bin === 'docker' && args[0] === 'ps') return rows.map(c => c.Id).join('\n');
    if (bin === 'docker' && args[0] === 'inspect') {
      const c = rows.find(c => c.Id === args[1]);
      if (c) return JSON.stringify([c]);
      throw Object.assign(Error('absent'), { status: 1, stderr: 'No such object' });
    }
    if (bin === 'docker' && args[0] === 'exec') return JSON.stringify(r.before.find(v => v.id === args[1]).sentinel);
    if (bin === 'sh') return '';
    throw Error('Unexpected tool operation: ' + bin + ' ' + args.join(' '));
  };
  t.mock.method(native, 'inspect', (_h, original) => r.before.find(v => v.requestId === original.id).view);
  return { h, r, rows, run, calls, root, configPath };
}
test('aliased TMPDIR accepts canonical lifecycle scratch and rejects linked or foreign roots', t => {
  const f = fixture(t), base = fs.realpathSync(os.tmpdir()), alias = path.join(f.root, 'tmp-alias');
  fs.symlinkSync(base, alias); t.mock.method(os, 'tmpdir', () => alias);
  tool.isolation(f.h, f.r, f.run);
  f.r.privateRoot = path.join(alias, path.basename(f.root));
  assert.throws(() => tool.isolation(f.h, f.r, f.run), /private lifecycle root/);
  f.r.privateRoot = fs.mkdtempSync(path.join(f.root, 'magictest-native-lifecycle-'));
  assert.throws(() => tool.isolation(f.h, f.r, f.run), /private lifecycle root/);
  assert.equal(f.calls.some(v => v.bin === 'sh'), false);
});
test('complete resume tuples require both original IDs once, with no changed or extra owner fields', () => {
  const originals = [tool.resume(container('a'), 'owned'), tool.resume(container('b'), 'owned')];
  tool.assertJournal([...originals].reverse(), originals);
  for (const mutate of [v => v.pop(), v => v.push(v[0]), v => v[1] = v[0], v => v[0].image = 'other',
    v => v[0].compose += '/..', v => v[0].network = 'other', v => v[0].extra = 'unacknowledged']) {
    const v = structuredClone(originals); mutate(v); assert.throws(() => tool.assertJournal(v, originals));
  }
  assert.throws(() => tool.resume(container('a'), 'foreign'), /tuple/);
});
test('all native candidates must match exact IDs, including stopped and forged containers', t => {
  const f = fixture(t); tool.exactTargets(f.run, 'owned', f.rows.map(v => v.Id));
  f.rows.push(container('c', false));
  assert.throws(() => tool.exactTargets(f.run, 'owned', f.r.before.map(v => v.id)), /Entire/);
  tool.exactTargets(f.run, 'owned', f.r.before.map(v => v.id), [f.rows[2].Id]);
  f.rows.push(container('d')); f.rows.at(-1).Config.Labels[labels.project] = 'ordinary-core';
  tool.exactTargets(f.run, 'owned', f.r.before.map(v => v.id), [f.rows[2].Id]);
});
test('wrong daemon, actor, changed helpers or env block before lifecycle write dispatch', t => {
  const f = fixture(t);
  for (const mode of ['actor', 'daemon', 'config', 'source', 'env']) {
    const before = fs.readFileSync(f.configPath), source = fs.readFileSync(f.r.scripts[0].path), env = fs.readFileSync(f.r.env);
    const origin = f.h.admin.origin;
    if (mode === 'actor') f.h.admin.origin = 'https://other.invalid';
    if (mode === 'config') fs.writeFileSync(f.configPath, JSON.stringify({ ...f.r.config, daemonId: 'replacement' }));
    if (mode === 'source') fs.appendFileSync(f.r.scripts[0].path, 'changed');
    if (mode === 'env') fs.writeFileSync(f.r.env, 'APPS_NETWORK=other\n');
    const run = mode === 'daemon' ? (bin, args) => args[0] === 'info' ? JSON.stringify({ ID: 'replacement' }) : f.run(bin, args) : f.run;
    assert.throws(() => tool.dispatch(f.h, f.r, 'stop', run));
    assert.equal(f.r.commands.length, 0);
    fs.writeFileSync(f.configPath, before); fs.writeFileSync(f.r.scripts[0].path, source); fs.writeFileSync(f.r.env, env); f.h.admin.origin = origin;
  }
  assert.equal(f.calls.filter(v => v.bin === 'sh').length, 0);
});
test('helper intent is durable before single positional-argument dispatch; refusal and killed result differ', t => {
  const f = fixture(t); let persisted = false, calls = 0;
  f.h.persist = () => { persisted = true; };
  const run = (bin, args) => {
    if (bin !== 'sh') return f.run(bin, args);
    calls++; assert.equal(persisted, true); assert.equal(f.r.commands.at(-1).outcome, 'unknown');
    assert.equal(args.at(-1), 'remove'); assert.equal(args.at(-2), f.r.journal);
    throw Object.assign(Error('refused'), { status: 1, stderr: 'native runtime ownership could not be verified: ' + 'c'.repeat(64) });
  };
  const refused = tool.dispatch(f.h, f.r, 'remove', run);
  assert.equal(refused.ownershipRefused, true); assert.equal(refused.exitCode, 1); assert.equal(calls, 1);
  const unknown = tool.dispatch(f.h, f.r, 'stop', (bin, args) => {
    if (bin === 'sh') throw Object.assign(Error('killed'), { signal: 'SIGKILL', status: null, stderr: 'private material' });
    return f.run(bin, args);
  });
  assert.equal(unknown.exitCode, undefined); assert.equal(JSON.stringify(unknown).includes('private material'), false);
  assert.throws(() => tool.dispatch(f.h, f.r, 'stop', run), /no replay/);
  assert.throws(() => tool.dispatch(f.h, f.r, 'remove', run), /no replay/); assert.equal(calls, 1);
});
test('five negative variants use unique stopped probe names and preserve untrusted path bytes literally', () => {
  const variants = tool.variants('c'.repeat(32));
  assert.equal(variants.length, 5); assert.equal(new Set(variants.map(v => v.labels[labels.service])).size, 5);
  assert.ok(variants.some(v => v.labels[labels.compose].includes('/../')));
  assert.ok(variants.some(v => v.labels[labels.compose] === '/unrelated/docker-compose.yaml'));
  assert.ok(variants.every(v => /^native-[a-f0-9]{12}$/.test(v.labels[labels.project])));
});
test('lost create acknowledgement is never retried or converted into inferred absence', t => {
  const f = fixture(t); let creates = 0, deletes = 0;
  const run = (bin, args) => {
    if (args[0] === 'create') { creates++; assert.equal(f.r.probes.length, 1); throw Error('lost response'); }
    if (args[0] === 'rm') { deletes++; throw Error('must not remove'); }
    return f.run(bin, args);
  };
  assert.throws(() => tool.createProbe(f.h, f.r, tool.variants('c'.repeat(32))[0], run), /lost/);
  assert.throws(() => tool.removeProbe(f.h, f.r, f.r.probes[0], run), /creation unresolved/);
  assert.equal(creates, 1); assert.equal(deletes, 0); assert.equal(f.r.probes[0].creation.outcome, 'unknown');
});
function acknowledgedProbe(f) {
  const variant = tool.variants('c'.repeat(32))[0];
  const p = { ...variant, id: 'c'.repeat(64), name: variant.labels[labels.project] + '-' + variant.labels[labels.service], image: f.rows[0].Image, creation: { outcome: 'acknowledged' } };
  const c = container('c', false); c.Name = '/' + p.name; c.Config.Labels = structuredClone(p.labels); c.Config.Entrypoint = ['/bin/true']; c.Mounts = [];
  return { p, c };
}
test('negative probe removal requires exact nonce/name/image/network, stopped state and zero mounts', t => {
  const f = fixture(t), { p, c } = acknowledgedProbe(f);
  assert.equal(tool.probeMatches(c, p, 'owned'), true);
  for (const mutate of [v => v.Id = 'd'.repeat(64), v => v.Name += '-other', v => v.Image = 'other',
    v => v.Config.Labels['io.muidea.magictest.native-lifecycle'] = 'foreign', v => v.State.Running = true,
    v => v.Mounts.push({ Type: 'bind' }), v => v.NetworkSettings.Networks.other = {}, v => v.Config.Entrypoint = ['/bin/sh']]) {
    const changed = structuredClone(c); mutate(changed);
    assert.equal(tool.probeMatches(changed, p, 'owned'), false);
    f.rows.push(changed); assert.throws(() => tool.removeProbe(f.h, f.r, p, f.run), /ownership changed|absent/); f.rows.pop();
    assert.equal(p.removal, undefined);
  }
  assert.equal(f.calls.some(v => v.args[0] === 'rm'), false);
});
test('unknown probe removal can confirm exact absence but never resend the delete', t => {
  const f = fixture(t), { p, c } = acknowledgedProbe(f); f.rows.push(c);
  let deletes = 0;
  const run = (bin, args) => {
    if (args[0] === 'rm') { deletes++; f.rows.pop(); throw Error('lost remove response'); }
    return f.run(bin, args);
  };
  assert.throws(() => tool.removeProbe(f.h, f.r, p, run), /lost remove/);
  assert.equal(p.removal.outcome, 'unknown');
  tool.removeProbe(f.h, f.r, p, run); assert.equal(p.removal.outcome, 'confirmed'); assert.equal(deletes, 1);
});
test('stop cleanup resumes both original IDs once, preserves owner facts and closes only after reads', async t => {
  const f = fixture(t); f.r.commands.push({ action: 'stop', exitCode: 0, outcome: 'stopped-and-journaled' });
  for (const c of f.rows) c.State.Running = false;
  fs.writeFileSync(f.r.journal, JSON.stringify(f.r.resume));
  let starts = 0;
  const run = (bin, args) => {
    if (bin === 'sh') { starts++; assert.equal(args.at(-1), 'start'); for (const c of f.rows) c.State.Running = true; fs.unlinkSync(f.r.journal); return ''; }
    return f.run(bin, args);
  };
  await tool.cleanup(f.h, f.r, run); assert.equal(starts, 1); assert.equal(f.r.phase, 'deleted');
  await tool.cleanup(f.h, f.r, run); assert.equal(starts, 1);
});
test('missing/mixed journal, stopped identity drift and unknown stop cannot dispatch recovery', async t => {
  const f = fixture(t);
  for (const mode of ['missing', 'extra', 'duplicate', 'wrong-image', 'identity', 'unknown-stop']) {
    f.r.commands = [{ action: 'stop', ...(mode === 'unknown-stop' ? {} : { exitCode: 0 }), outcome: 'unknown' }];
    const records = structuredClone(f.r.resume);
    if (mode === 'extra') records.push({ ...records[0], id: 'c'.repeat(64) });
    if (mode === 'duplicate') records[1] = records[0];
    if (mode === 'wrong-image') records[0].image = 'foreign';
    if (mode !== 'missing') fs.writeFileSync(f.r.journal, JSON.stringify(records));
    if (mode === 'identity') f.rows[0].Image = 'foreign';
    await assert.rejects(tool.cleanup(f.h, f.r, f.run));
    assert.equal(f.r.phase, 'prepared'); assert.equal(f.calls.some(v => v.bin === 'sh'), false);
    f.rows[0].Image = f.r.before[0].binding.image; if (fs.existsSync(f.r.journal)) fs.unlinkSync(f.r.journal);
  }
});
test('failed/unknown start preserves original journal and resources without replay even when running', async t => {
  const f = fixture(t);
  for (const mode of ['failed', 'unknown', 'journal-retained']) {
    f.r.commands = [{ action: 'stop', exitCode: 0 }, { action: 'start', ...(mode === 'unknown' ? {} : { exitCode: mode === 'failed' ? 1 : 0 }), outcome: 'unknown' }];
    if (mode !== 'unknown') fs.writeFileSync(f.r.journal, JSON.stringify(f.r.resume));
    await assert.rejects(tool.cleanup(f.h, f.r, f.run), /no replay/);
    assert.equal(f.r.phase, 'prepared'); assert.equal(f.calls.some(v => v.bin === 'sh'), false);
    if (fs.existsSync(f.r.journal)) fs.unlinkSync(f.r.journal);
  }
});
test('changed independent owner or original volume data keeps lifecycle closure open', async t => {
  const f = fixture(t);
  f.h.ok = async () => ({ value: { changed: true } });
  await assert.rejects(tool.cleanup(f.h, f.r, f.run), /owner fact/); assert.equal(f.r.phase, 'prepared');
  f.h.ok = async (_actor, _method, route) => ({ value: { route } });
  t.mock.method(native, 'inspect', () => ({ marker: 'changed' }));
  await assert.rejects(tool.cleanup(f.h, f.r, f.run), /volume/); assert.equal(f.r.phase, 'prepared');
});
test('open lifecycle protects both original requests, same package consumers and source cleanup', t => {
  const f = fixture(t);
  for (const resource of [f.r, { kind: 'native-runtime-request', id: 11 }, { kind: 'native-runtime-request', id: 99, creation: { intended: { packageId: 7 } } },
    { kind: 'native-package-probe', package: { id: 7 } }, { kind: 'native-provider-probe', package: { id: 7 } }]) {
    assert.throws(() => tool.guard(f.h, resource), /preserve/);
    assert.throws(() => require('./scenario_commands.cjs').guard(f.h, resource), /preserve/);
  }
  tool.guard(f.h, { kind: 'native-runtime-request', id: 100 }); tool.guard(f.h, { kind: 'native-package-probe', package: { id: 8 } });
  f.r.phase = 'deleted'; tool.guard(f.h, { kind: 'native-runtime-request', id: 11 });
});
test('resumed cleanup binds every original lifecycle identity and command to immutable evidence', t => {
  const { r } = fixture(t), { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
  const evidence = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, evidence)[0], r);
  for (const mutate of [v => v.config.daemonId = 'other', v => v.scripts[0].sha256 = 'other', v => v.privateRoot += '-other',
    v => v.env += '-other', v => v.journal += '-other', v => v.network = 'other', v => v.nativeIds[0] = 99,
    v => v.packageId = 8, v => v.before[0].binding.image = 'other', v => v.before[0].sentinel.marker = 'other',
    v => v.resume[0].id = 'c'.repeat(64), v => v.commands.push({ action: 'stop', outcome: 'unknown' }),
    v => v.probes.push({ creation: { outcome: 'unknown' } }), v => v.ownerReads[0].value = {}, v => v.actorIdentity.account = 'other']) {
    const changed = structuredClone(r); mutate(changed);
    assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /immutable cleanup evidence/);
  }
});
test('actual create arguments never pull, start or mount and acknowledge inherited image labels', t => {
  const f = fixture(t); f.r.probeImageLabels = { 'org.opencontainers.image.source': 'offline-image' };
  const variant = tool.variants('c'.repeat(32))[1]; let creates = 0;
  const run = (bin, args) => {
    if (args[0] === 'create') {
      creates++; assert.equal(f.r.probes.length, 1); assert.equal(f.r.probes[0].creation.outcome, 'unknown');
      assert.ok(args.includes('--pull=never')); assert.equal(args.some(v => ['--mount', '-v', '--privileged'].includes(v)), false);
      assert.ok(args.includes(labels.compose + '=' + variant.labels[labels.compose]));
      const p = f.r.probes[0], c = container('c', false); c.Name = '/' + p.name; c.Config.Labels = structuredClone(p.labels); c.Config.Entrypoint = ['/bin/true']; c.Mounts = [];
      f.rows.push(c); return c.Id + '\n';
    }
    return f.run(bin, args);
  };
  const p = tool.createProbe(f.h, f.r, variant, run);
  assert.equal(p.creation.outcome, 'acknowledged'); assert.equal(p.labels['org.opencontainers.image.source'], 'offline-image'); assert.equal(creates, 1);
});
