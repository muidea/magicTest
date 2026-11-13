// Immutable native package delivery through Panel and File's public consumers.
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const { packageContent, deploymentPackageUpload } = require('./owner_transport.cjs');
const { cleanup, reconcileBuild } = require('./native_provider_access_cases.cjs');
const base = '/panel/application/deployment-packages/';
const definitions = '/panel/application/definitions/';
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
async function content(h, p) {
  const response = await packageContent(h.admin, base + p.id + '/content', h.observe);
  h.check('Exact immutable native package download matches its full transport digest', response.status === 200 && Buffer.isBuffer(response.data.bytes) && hash(response.data.bytes) === p.packageDigest);
  return response.data.bytes;
}
async function build(h, input) {
  const before = await h.directory(h.admin, base), preview = (await h.ok(h.admin, 'POST', base + 'builds/preview', input)).value;
  h.check('Positive native preflight preserves exact application, components and initial contract', preview.applicationUuid === input.applicationUuid &&
    preview.applicationName === input.applicationName && preview.nativeContractVersion === input.contract.apiVersion &&
    same(preview.components?.map(v => v.key).sort(), Object.keys(input.contract.components).sort()) && /^sha256:[a-f0-9]{64}$/.test(preview.buildDigest));
  h.check('Preflight does not register or replace any original package', same(await h.directory(h.admin, base), before));
  const r = { kind: 'native-package-probe', phase: 'intent', origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
    applicationUuid: input.applicationUuid, preexistingIds: before.map(v => v.id), commands: [] };
  h.state.resources.push(r); h.persist();
  const c = { method: 'POST', route: base + 'builds/', body: { ...input, expectedBuildDigest: preview.buildDigest },
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, c.method, c.route, c.body);
  r.package = c.response.data?.value; h.persist();
  await reconcileBuild(h, r);
  h.check('Original acknowledged build independently owns exactly one new immutable native package', r.packageAcknowledged === true && c.outcome === 'confirmed');
  r.phase = 'created'; h.persist(); return r;
}
async function repeat(h, r) {
  if (!r.packageAcknowledged || r.commands.some(c => c.outcome === 'unknown') || !same(r.actorIdentity, h.admin.identity) || r.origin !== h.admin.origin)
    throw new h.Blocked('Repeat scenario requires the exact already-confirmed original build; unknown writes cannot be retried');
  const first = r.commands[0];
  if (first.method !== 'POST' || first.route !== base + 'builds/' || !h.good(first.response) || !same(first.response.data?.value, r.package))
    throw new h.Blocked('Repeat scenario lacks its exact successful initial build receipt');
  const before = await h.directory(h.admin, base), bytes = await content(h, r.package);
  const c = { method: first.method, route: first.route, body: structuredClone(first.body), actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
    scenario: 'intentional-exact-duplicate-after-original-confirmed', outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, c.method, c.route, c.body); h.persist();
  const current = (await h.ok(h.admin, 'GET', base + r.package.id)).value;
  h.check('Exact acknowledged duplicate returns original package identity and all immutable fields, with no directory or ZIP replacement', h.good(c.response) &&
    same(c.response.data.value, r.package) && same(current, r.package) && same(await h.directory(h.admin, base), before) && (await content(h, r.package)).equals(bytes));
  c.outcome = 'confirmed'; h.persist(); return bytes;
}
function archive(bytes) {
  return JSON.parse(execFileSync('python3', ['-B', '-c', `import io,json,sys,zipfile
z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
assert z.testzip() is None
print(json.dumps({name:json.loads(z.read(name)) for name in ['package.json','release/release.json','deployment/app.json','deployment/native-runtime.json']}))`], { input: bytes, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }));
}
async function importExact(h, r, bytes, upload = deploymentPackageUpload) {
  if (!r.packageAcknowledged || r.imports?.some(c => c.outcome !== 'confirmed') || r.commands.some(c => c.outcome === 'unknown') ||
      !same(r.actorIdentity, h.admin.identity) || r.origin !== h.admin.origin || hash(bytes) !== r.package.packageDigest)
    throw new h.Blocked('Native import requires exact confirmed package, original actor and complete original bytes; unknown import cannot be replayed');
  const before = await h.directory(h.admin, base), c = { outcome: 'unknown', name: h.state.prefix + '-native-roundtrip.zip', digest: hash(bytes), size: bytes.length,
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, upload: { outcome: 'unknown' } };
  (r.imports ||= []).push(c); h.persist();
  c.upload.response = await upload(h.admin, { name: c.name, bytes }, h.observe); h.persist();
  const ack = c.upload.response, value = ack.data?.value;
  h.check('File acknowledges exact original native ZIP upload reference and purpose before importer dispatch', h.good(ack) &&
    /^[A-Za-z0-9_-]{43}$/.test(value?.uploadRef || '') && value.name === c.name && value.digest === c.digest && value.size === c.size && value.purpose === 'application-deployment-package' && value.expiresAt > Date.now(), ack);
  c.upload.outcome = 'confirmed'; c.command = { method: 'POST', route: base + 'imports/', body: { uploadRef: value.uploadRef }, outcome: 'unknown' }; h.persist();
  c.command.response = await h.api(h.admin, 'POST', c.command.route, c.command.body); h.persist();
  h.check('Real native importer confirms exact original immutable package and unchanged directory/ZIP after consuming upload reference', h.good(c.command.response) &&
    same(c.command.response.data.value, r.package) && same((await h.ok(h.admin, 'GET', base + r.package.id)).value, r.package) &&
    same(await h.directory(h.admin, base), before) && (await content(h, r.package)).equals(bytes), c.command.response);
  c.command.outcome = 'confirmed'; c.outcome = 'confirmed';
  c.proof = 'Exact upload purpose/digest/size and real owner import receipt; importer acknowledges duplicate-upload release. No independent File physical-byte absence claim.'; h.persist();
}
async function roundtrip(h) {
  const input = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-native-roundtrip', releaseVersion: '1.2.3', icon: 'appstore',
    contract: { apiVersion: 'magic.native-orchestration/v1', components: { api: { image: 'postgres:17.7-alpine3.22' },
      worker: { image: 'postgres:17.7-alpine3.22', command: ['postgres', '--version'], dependsOn: [{ componentRef: 'api', condition: 'started', timeoutSeconds: 120 }] } } } };
  const r = await build(h, input), bytes = await content(h, r.package), files = archive(bytes), runtime = files['deployment/native-runtime.json'];
  h.check('Downloaded multi-component archive preserves initial native format, application release, built-in icon and exact dependency declaration without model pkgPrefix',
    runtime.apiVersion === 'magic.native-runtime/v1' && runtime.applicationRef.uuid === input.applicationUuid && runtime.applicationRef.name === input.applicationName &&
    files['release/release.json'].version === input.releaseVersion && files['deployment/app.json'].runtime.application.icon === input.icon && r.package.icon === input.icon &&
    runtime.components.length === 2 && same(runtime.components.find(v => v.key === 'worker')?.dependsOn, input.contract.components.worker.dependsOn) &&
    !Object.hasOwn(input, 'pkgPrefix'), files);
  await importExact(h, r, bytes);
  await cleanup(h, r);
}
async function repeated(h) {
  const input = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-native-repeat', releaseVersion: '1.0.0',
    contract: { apiVersion: 'magic.native-orchestration/v1', components: {
      api: { image: 'postgres:17.7-alpine3.22', environment: { REGRESSION_MARKER: { literal: 'original' } } },
      worker: { image: 'postgres:17.7-alpine3.22', command: ['postgres', '--version'] }
    } } };
  const draftBody = JSON.parse(h.fs.readFileSync(h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression/fixture-definition-create-request.json')));
  Object.assign(draftBody, { uuid: input.applicationUuid, name: input.applicationName, pkgPrefix: h.state.prefix + 'nativepkg', showName: '原生重复构包草稿', runtimeType: 'packaged-runtime', version: input.releaseVersion,
    storage: { required: false, engine: '', versionConstraint: '', slots: [] }, orchestration: { contract: structuredClone(input.contract) } });
  const app = await h.create(definitions, draftBody, 'definition'), draft = (await h.ok(h.admin, 'GET', definitions + app.id)).value;
  h.check('Same native package revision is grounded in a real independently saved native definition draft', draft.uuid === input.applicationUuid && draft.name === input.applicationName &&
    draft.version === input.releaseVersion && draft.runtimeType === 'packaged-runtime' && same(draft.orchestration?.contract, input.contract));
  const first = await build(h, input), originalBytes = await repeat(h, first), changed = structuredClone(input);
  changed.releaseVersion = '1.0.1'; changed.contract.components.api.environment.REGRESSION_MARKER.literal = 'changed';
  await saveNativeDraft(h, draft, changed);
  const second = await build(h, changed), secondBytes = await repeat(h, second);
  h.check('Changed native content and application release create a new package identity/digest without overwriting original', first.package.id !== second.package.id &&
    first.package.packageDigest !== second.package.packageDigest && second.package.applicationUuid === first.package.applicationUuid &&
    second.package.releaseVersion === changed.releaseVersion && same((await h.ok(h.admin, 'GET', base + first.package.id)).value, first.package) &&
    (await content(h, first.package)).equals(originalBytes) && !originalBytes.equals(secondBytes));
  for (const [bytes, source] of [[originalBytes, input], [secondBytes, changed]]) {
    const files = archive(bytes), runtime = files['deployment/native-runtime.json'], release = files['release/release.json'];
    h.check('Each frozen archive independently preserves exact component input, release and initial runtime format', runtime.apiVersion === 'magic.native-runtime/v1' &&
      runtime.applicationRef.uuid === source.applicationUuid && runtime.applicationRef.name === source.applicationName && release.version === source.releaseVersion &&
      runtime.components.length === 2 && runtime.components.find(v => v.key === 'api')?.environment?.REGRESSION_MARKER?.literal === source.contract.components.api.environment.REGRESSION_MARKER.literal &&
      same(runtime.components.find(v => v.key === 'worker')?.command, source.contract.components.worker.command), files);
  }
  await cleanup(h, second);
  h.check('Removing changed package preserves exact original package and complete original ZIP', same((await h.ok(h.admin, 'GET', base + first.package.id)).value, first.package) && (await content(h, first.package)).equals(originalBytes));
  await cleanup(h, first);
}
function guardDefinitionCleanup(h, r) {
  if (r.nativePackageDraftCommands?.some(c => c.outcome !== 'confirmed')) throw new h.Blocked('Original native draft save unresolved; retain exact authoring identity without delete or write replay');
}
async function saveNativeDraft(h, current, input) {
  const owner = h.state.resources.find(r => r.kind === 'definition' && r.id === current.id && r.creation?.ownershipConfirmed);
  if (!owner || owner.creation.origin !== h.admin.origin || !same(owner.creation.actorIdentity, h.admin.identity)) throw new h.Blocked('Native package draft requires exact formally owned authoring resource');
  guardDefinitionCleanup(h, owner);
  const fields = ['uuid', 'name', 'showName', 'pkgPrefix', 'icon', 'catalog', 'version', 'email', 'author', 'description', 'uiMeta', 'runtimeType', 'storage', 'authorization', 'orchestration'];
  const body = { ...Object.fromEntries(fields.filter(k => Object.hasOwn(current, k)).map(k => [k, structuredClone(current[k])])),
    version: input.releaseVersion, orchestration: { contract: structuredClone(input.contract) }, expectedDefinitionVersion: current.updateTime };
  const c = { method: 'PUT', route: definitions + current.id, body, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' };
  (owner.nativePackageDraftCommands ||= []).push(c); h.persist();
  c.response = await h.api(h.admin, 'PUT', c.route, body); h.persist();
  const after = (await h.ok(h.admin, 'GET', c.route)).value;
  h.check('Conditional native draft save and independent owner persist exact changed component content and application release while keeping original author identity', h.good(c.response) &&
    same(c.response.data.value, after) && after.id === current.id && after.uuid === current.uuid && after.name === current.name && after.version === input.releaseVersion &&
    after.updateTime > current.updateTime && same(after.orchestration?.contract, input.contract));
  c.outcome = 'confirmed'; h.persist(); return after;
}
repeated.transport = 'owner-api';
roundtrip.transport = 'owner-api';
module.exports = { handlers: { 'F026-001': roundtrip, 'F026-003': repeated }, build, repeat, archive, importExact, guardDefinitionCleanup };
