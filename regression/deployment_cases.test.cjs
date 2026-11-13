const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { cleanupBoundary } = require('./deployment_cases.cjs');

function fixture(change = {}) {
  const journal = { containerId: 'a'.repeat(64), name: 'magictest-snapshot-123456abcdef', root: '/private/deployment' };
  const resource = { privateRoot: '/private', phase: 'intent', ...change };
  const h = { path, Blocked: Error, persist() {}, fs: { existsSync: () => true, realpathSync: value => value, readFileSync: () => JSON.stringify(journal) } };
  const current = { Id: journal.containerId, Config: { Labels: { 'io.muidea.magictest.snapshot': journal.name } },
    Mounts: [{ Type: 'bind', Source: '/private/deployment/apps/data', Destination: '/fixture' }] };
  const calls = [];
  function command(binary, args) {
    assert.equal(binary, 'docker'); calls.push(args);
    if (args[0] === 'rm') throw Error('Removal must not occur in ownership/unknown-result guard tests');
    return JSON.stringify([current]);
  }
  return { h, resource, current, calls, command };
}

for (const changed of ['id', 'label', 'source', 'destination', 'type', 'extra-mount']) {
  test('snapshot cleanup refuses changed ' + changed + ' before removal', () => {
    const f = fixture();
    if (changed === 'id') f.current.Id = 'b'.repeat(64);
    if (changed === 'label') f.current.Config.Labels = {};
    if (changed === 'source') f.current.Mounts[0].Source = '/foreign';
    if (changed === 'destination') f.current.Mounts[0].Destination = '/foreign';
    if (changed === 'type') f.current.Mounts[0].Type = 'volume';
    if (changed === 'extra-mount') f.current.Mounts.push({ Source: '/foreign' });
    assert.throws(() => cleanupBoundary(f.h, f.resource, f.command), /ownership changed/);
    assert.equal(f.calls.length, 1); assert.equal(f.resource.phase, 'intent');
  });
}
test('snapshot unknown removal is not replayed even when original workload remains', () => {
  const f = fixture({ deletion: { outcome: 'unknown' } });
  assert.throws(() => cleanupBoundary(f.h, f.resource, f.command), /do not replay/);
  assert.equal(f.calls.length, 1); assert.equal(f.resource.phase, 'intent');
});
test('snapshot missing creation receipt stays open without a Docker command', () => {
  const f = fixture(); f.h.fs.existsSync = () => false;
  assert.throws(() => cleanupBoundary(f.h, f.resource, f.command), /remains unknown/);
  assert.equal(f.calls.length, 0); assert.equal(f.resource.phase, 'intent');
});
test('snapshot failed synchronous preparation may close only with explicit pre-dispatch proof', () => {
  const f = fixture({ helperOutput: { beforeWorkloadDispatch: true } }); f.h.fs.existsSync = () => false;
  assert.match(cleanupBoundary(f.h, f.resource, f.command).proof, /before any workload dispatch/);
  assert.equal(f.calls.length, 0); assert.equal(f.resource.phase, 'deleted');
});

test('snapshot original disposed workload accepts a real private-root alias but rejects a foreign journal root before Docker', () => {
  const fs = require('node:fs'), os = require('node:os');
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'magictest-snapshot-alias-'));
  try {
    const real = path.join(parent, 'private'), alias = path.join(parent, 'alias');
    fs.mkdirSync(real); fs.symlinkSync(real, alias);
    const journal = { containerId: 'a'.repeat(64), name: 'magictest-snapshot-123456abcdef', root: path.join(fs.realpathSync(real), 'deployment'), phase: 'disposed' };
    fs.writeFileSync(path.join(real, 'workload-journal.json'), JSON.stringify(journal));
    const h = { fs, path, Blocked: Error, persist() {} }, resource = { privateRoot: alias, phase: 'intent' }, calls = [];
    const command = (binary, args) => {
      assert.equal(binary, 'docker'); assert.deepEqual(args, ['inspect', journal.containerId]); calls.push(args);
      throw Object.assign(Error('Original container absent'), { status: 1, stderr: 'Error: No such container' });
    };
    assert.equal(cleanupBoundary(h, resource, command).originalContainerId, journal.containerId);
    assert.equal(resource.phase, 'deleted'); assert.equal(calls.length, 2);
    fs.writeFileSync(path.join(real, 'workload-journal.json'), JSON.stringify({ ...journal, root: path.join(parent, 'foreign', 'deployment') }));
    resource.phase = 'intent'; calls.length = 0;
    assert.throws(() => cleanupBoundary(h, resource, command), /original exact workload receipt/);
    assert.equal(resource.phase, 'intent'); assert.equal(calls.length, 0);
  } finally { fs.rmSync(parent, { recursive: true }); }
});
