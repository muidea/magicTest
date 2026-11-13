const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { rejectImport, corrupt, exactRefusal } = require('./artifact_integrity_cases.cjs');
const bytes = Buffer.from('controlled ZIP bytes');
function fixture() {
  const h = { admin: { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.test' },
    Blocked: Error, state: { prefix: 'run', resources: [] }, persist() {}, observe() {}, good: r => r.status === 200 && !r.data.error,
    check(label, value) { assert.ok(value, label); } };
  let writes = 0, reads = 0;
  const deps = { readSnapshot: async () => { reads++; return { packages: [{ id: 1 }] }; },
    upload: async (actor, file) => { writes++; return { status: 200, data: { value: { name: file.name, size: bytes.length,
      digest: 'sha256:' + require('node:crypto').createHash('sha256').update(bytes).digest('hex'), uploadRef: 'a'.repeat(43), purpose: 'application-model-package', expiresAt: Date.now() + 60000 } } }; } };
  h.api = async () => { writes++; return { status: 400, data: { error: { code: 4, message: 'uploaded application model package ZIP is invalid: model package checksum does not match "model.json"' }, value: null } }; };
  return { h, deps, run: () => rejectImport(h, { bytes, mode: 'content', target: 'model.json' }, deps), writes: () => writes, reads: () => reads };
}
test('integrity proof needs exact validation-stage refusal and unchanged complete owner directories', async () => {
  const f = fixture(); await f.run(); assert.equal(f.writes(), 2); assert.equal(f.reads(), 2);
  assert.equal(f.h.state.resources[0].phase, 'deleted');
});
test('auth, unconfirmed compensation and wrong validation stage cannot close original integrity intent', async () => {
  for (const response of [{ status: 401, data: { error: { code: 11 } } },
    { status: 400, data: { error: { code: 4, message: 'uploaded application model package ZIP is invalid: model package checksum does not match "model.json"; bound file disposition is unconfirmed: failure' } } },
    { status: 400, data: { error: { code: 4, message: 'file missing' } } }]) {
    const f = fixture(); f.h.api = async () => response;
    await assert.rejects(f.run()); assert.equal(f.h.state.resources[0].phase, 'intent');
    await assert.rejects(f.run(), /no new upload/); assert.equal(f.writes(), 1);
  }
});
test('unknown upload, lost import and concurrent owner change retain original journal without a new sample', async () => {
  for (const mode of ['upload', 'import', 'directory']) {
    const f = fixture();
    if (mode === 'upload') f.deps.upload = async () => { throw Error('lost upload'); };
    if (mode === 'import') f.h.api = async () => { throw Error('lost import'); };
    if (mode === 'directory') { let reads = 0; f.deps.readSnapshot = async () => ({ packages: [{ id: ++reads }] }); }
    await assert.rejects(f.run()); const count = f.writes();
    await assert.rejects(f.run(), /no new upload/); assert.equal(f.writes(), count);
    assert.equal(f.h.state.resources.length, 1); assert.equal(f.h.state.resources[0].phase, 'intent');
  }
});
test('ZIP variants have valid CRCs and target content or declared digest without changing original input', () => {
  const original = execFileSync('python3', ['-B', '-c', `import io,zipfile,json,hashlib,sys
b=b'original';o=io.BytesIO()
with zipfile.ZipFile(o,'w') as z:
 z.writestr('model.json',b)
 z.writestr('checksums.json',json.dumps({'apiVersion':'magic.checksums/v1','files':[{'path':'model.json','size':len(b),'digest':'sha256:'+hashlib.sha256(b).hexdigest()}]}))
sys.stdout.buffer.write(o.getvalue())`]);
  const copy = Buffer.from(original);
  for (const mode of ['content', 'checksum']) {
    const variant = corrupt(original, mode); assert.equal(variant.target, 'model.json');
    const proof = JSON.parse(execFileSync('python3', ['-B', '-c', `import io,zipfile,json,sys
z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()));assert z.testzip() is None
print(json.dumps({'content':z.read('model.json').decode(),'digest':json.loads(z.read('checksums.json'))['files'][0]['digest']}))`], { input: Buffer.from(variant.bytes, 'base64'), encoding: 'utf8' }));
    assert.equal(proof.content, mode === 'content' ? 'original ' : 'original');
    assert.equal(proof.digest === 'sha256:' + '0'.repeat(64), mode === 'checksum');
  }
  assert.ok(original.equals(copy));
});
test('refusal classification rejects a successful or substituted response despite a matching error', () => {
  const error = { code: 19, message: 'exact' };
  assert.equal(exactRefusal({ status: 409, data: { error, value: null } }, 'exact', 19), true);
  for (const response of [{ status: 503, data: { error } }, { status: 409, data: { error, value: { id: 1 } } }, { status: 401, data: { error } }]) assert.equal(exactRefusal(response, 'exact', 19), false);
});
