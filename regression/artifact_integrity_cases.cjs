const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const { packageContent, packageUpload } = require('./owner_transport.cjs');
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
const routes = ['/panel/application/model-packages/', '/panel/application/deployment-packages/',
  '/panel/application/deployment-requests/', '/panel/application/installations/',
  '/panel/operations/namespaces/panel/application-deployment-operations/'];
async function snapshot(h) {
  const result = {};
  for (const route of routes) result[route] = (await h.directory(h.admin, route)).sort((a, b) => a.id - b.id);
  return result;
}
// Repack with valid ZIP CRCs so failures exercise the package checksum owner,
// rather than an invalid archive header or a transport digest mismatch.
function corrupt(bytes, mode) {
  if (!Buffer.isBuffer(bytes) || !['content', 'checksum'].includes(mode)) throw Error('Original ZIP and explicit corruption mode required');
  return JSON.parse(execFileSync('python3', ['-B', '-c', `import io,zipfile,json,sys,base64
original=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
assert original.testzip() is None
files={name:original.read(name) for name in original.namelist()}
checks=json.loads(files['checksums.json']); entry=checks['files'][0]; target=entry['path']
assert target != 'checksums.json' and target in files
if sys.argv[1]=='content': files[target]+=b' '
else:
 entry['digest']='sha256:'+('0' if entry['digest']!='sha256:'+'0'*64 else '1')*64
 files['checksums.json']=json.dumps(checks,separators=(',',':')).encode()
out=io.BytesIO()
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for name,payload in files.items(): z.writestr(name,payload)
assert zipfile.ZipFile(io.BytesIO(out.getvalue())).testzip() is None
print(json.dumps({'bytes':base64.b64encode(out.getvalue()).decode(),'target':target}))`, mode], { input: bytes, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }));
}
function exactRefusal(response, message, code) {
  return [200, 400, 409].includes(response?.status) && response.data?.error?.code === code && response.data.error.message === message && response.data.value == null;
}
async function rejectImport(h, input, { upload = packageUpload, readSnapshot = snapshot } = {}) {
  if (h.state.resources.some(r => r.kind === 'package-integrity-probe' && r.phase !== 'deleted')) throw new h.Blocked('Original integrity command remains unresolved; no new upload or import');
  const before = await readSnapshot(h);
  const r = { kind: 'package-integrity-probe', phase: 'intent', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
    mode: input.mode, name: h.state.prefix + '-corrupt-' + input.mode + '.zip', expectedSize: input.bytes.length, expectedDigest: hash(input.bytes), commands: [] };
  h.state.resources.push(r); h.persist();
  r.upload = { outcome: 'unknown' }; h.persist();
  r.upload.response = await upload(h.admin, { name: r.name, bytes: input.bytes }, h.observe); h.persist();
  const ack = r.upload.response, value = ack.data?.value;
  h.check('File acknowledges exact original corruption bytes, purpose, name and opaque reference before import', h.good(ack) &&
    /^[A-Za-z0-9_-]{43}$/.test(value?.uploadRef || '') && value.name === r.name && value.size === r.expectedSize && value.digest === r.expectedDigest && value.purpose === 'application-model-package' && value.expiresAt > Date.now(), ack);
  r.upload.outcome = 'acknowledged'; r.uploadRef = value.uploadRef; h.persist();
  const c = { route: '/panel/application/model-packages/imports/', body: { uploadRef: r.uploadRef }, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  const after = await readSnapshot(h);
  const message = 'uploaded application model package ZIP is invalid: model package checksum does not match ' + JSON.stringify(input.target);
  h.check('Real importer rejects exact checksum validation, not auth, archive CRC or unconfirmed File compensation', exactRefusal(c.response, message, 4), c.response);
  h.check('Independent complete package, request, installation and operation owner directories remain unchanged', same(after, before));
  c.outcome = 'rejected-and-unchanged'; r.phase = 'deleted';
  r.disposition = { proof: 'Exact pre-registration parse refusal acknowledges owner File compensation; independent complete Panel directories unchanged. No separate File physical-byte absence claim.' };
  h.persist(); return r;
}
async function damaged(h) {
  const f = await fixture(h), route = '/panel/application/model-packages/' + f.package.id;
  const original = await packageContent(h.admin, route + '/content', h.observe);
  h.check('Positive original immutable ZIP is available before controlled corruption', original.status === 200 && Buffer.isBuffer(original.data.bytes));
  for (const mode of ['content', 'checksum']) {
    const input = corrupt(original.data.bytes, mode), bytes = Buffer.from(input.bytes, 'base64');
    h.check('Controlled corruption changes original transport bytes while retaining a CRC-valid ZIP', !bytes.equals(original.data.bytes));
    await rejectImport(h, { mode, target: input.target, bytes });
  }
  const before = await snapshot(h), r = { kind: 'package-integrity-probe', phase: 'intent', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, commands: [] };
  h.state.resources.push(r); h.persist();
  const wrongDigest = 'sha256:' + (f.package.artifactDigest === 'sha256:' + '0'.repeat(64) ? '1' : '0').repeat(64);
  const c = { route: routes[2], body: { sourceKind: 'model-package', packageId: f.package.id, expectedDigest: wrongDigest,
    instanceKey: h.state.prefix + '-corrupt-digest', instanceName: '摘要不匹配不得交付', storageProvisioning: { mode: 'allocate' }, reason: 'Verify original package binding' }, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  h.check('Altered artifact digest is refused at the formal package binding stage', exactRefusal(c.response, 'model installation package binding is invalid', 19), c.response);
  h.check('Independent complete owner directories confirm no request, operation or installation from altered digest', same(await snapshot(h), before));
  c.outcome = 'rejected-and-unchanged'; r.phase = 'deleted'; h.persist();
  const after = await packageContent(h.admin, route + '/content', h.observe);
  h.check('Both corruptions and altered installation digest preserve exact original package and complete ZIP bytes', same((await h.ok(h.admin, 'GET', route)).value, f.package) && after.status === 200 && Buffer.isBuffer(after.data.bytes) && after.data.bytes.equals(original.data.bytes));
}
damaged.transport = 'owner-api';
module.exports = { handlers: { 'F020-002': damaged }, corrupt, rejectImport, exactRefusal };
