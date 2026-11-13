const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const { authoring: a } = require('./authoring_cases.cjs');
const { validateIsolation } = require('./delivery_fixture.cjs');
const { packageContent } = require('./owner_transport.cjs');
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
async function fixture(h) {
  if (!h.deliveryFixtureConfig) throw new h.Blocked('DELIVERY-FIXTURE: dedicated isolated deployment and published public-owner fixture are required');
  const config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig));
  validateIsolation(config, JSON.parse(execFileSync('docker', ['info', '--format', '{{json .}}'], { encoding: 'utf8' })));
  const manifestPath = h.path.join(config.privateRoot, 'fixture-manifest.json'), bytes = h.fs.readFileSync(manifestPath), manifest = JSON.parse(bytes);
  if (manifest.daemonId !== config.daemonId || manifest.status !== 'published' || h.admin.origin !== 'https://panel.local.vpc' ||
      h.admin.identity.account !== 'platform-admin' || h.admin.identity.namespace !== 'panel') throw new h.Blocked('Exact isolated fixture daemon and original author are required');
  const revisionRoute = '/panel/application/definitions/' + manifest.application.id + '/revisions/' + manifest.revision.id;
  h.check('Independent published fixture revision exactly matches immutable input', same((await h.ok(h.admin, 'GET', revisionRoute)).value, manifest.revision));
  h.check('Independent fixture package exactly matches immutable input', same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + manifest.package.id)).value, manifest.package));
  h.observe({ kind: 'external-published-fixture', manifestDigest: digest(bytes), daemonId: config.daemonId,
    applicationId: manifest.application.id, revisionId: manifest.revision.id, packageId: manifest.package.id,
    disposition: 'Original published fixture retained privately in dedicated deployment; current-run commands must restore their own changes. Not a deletion proof.' });
  return manifest;
}
function original(h, r) {
  if (h.admin.origin !== r.origin || !same(h.admin.identity, r.actorIdentity) || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original delivery fixture mutation remains unresolved or actor changed; no replay');
}
async function save(h, r, entities) {
  original(h, r);
  const before = await a.draft(h, r.app);
  if (!same(before, r.last)) throw new h.Blocked('Published fixture draft changed concurrently; never overwrite');
  const route = '/panel/application/definitions/' + r.app.id + '/model-draft', payload = a.command(before, entities);
  const checked = (await h.ok(h.admin, 'POST', route + '/check', payload)).value;
  h.check('Draft check preserves complete original model', same(await a.draft(h, r.app), before));
  const c = { route, payload, outcome: 'unknown' }; r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, 'PUT', route, payload); h.persist();
  const current = await a.draft(h, r.app);
  h.check('Fixture conditional write and independent owner confirm exact target digest', h.good(c.response) && current.targetDigest === checked.targetDigest &&
    current.definitionVersion === c.response.data.value.definitionVersion && current.definitionVersion > before.definitionVersion, current);
  c.outcome = 'confirmed'; r.last = current; h.persist(); return current;
}
function semanticEntities(entities) {
  return entities.map(entity => { const copy = structuredClone(entity); delete copy.createTime; delete copy.updateTime; delete copy.expectedEntityVersion; return copy; });
}
async function restore(h, r) {
  original(h, r);
  const current = await a.draft(h, r.app);
  if (!same(current, r.last)) throw new h.Blocked('External fixture draft revision differs from exact acknowledged state; no restoration overwrite');
  if (!same(semanticEntities(current.entities), semanticEntities(r.original.entities))) await save(h, r, r.original.entities.map(entity => {
    const restored = structuredClone(entity), latest = current.entities.find(e => e.id === entity.id);
    if (!latest) throw new h.Blocked('Original fixture entity identity is missing');
    restored.updateTime = latest.updateTime; return restored;
  }));
  const after = await a.draft(h, r.app);
  h.check('Independent fixture read proves original entity semantics restored with original identities', same(semanticEntities(after.entities), semanticEntities(r.original.entities)));
  r.phase = 'deleted'; r.restored = after; h.persist();
  return { proof: 'Current-run conditional model edits restored through owner; original published fixture retained, original resource versions not rewritten.' };
}
async function frozenDraft(h) {
  const f = await fixture(h), app = f.application;
  const downloadRoute = '/panel/application/model-packages/' + f.package.id + '/content';
  const before = await packageContent(h.admin, downloadRoute, h.observe);
  h.check('Original frozen package download returns ZIP bytes with a recorded independent transport digest', before.status === 200 && Buffer.isBuffer(before.data.bytes) && before.data.bytes.subarray(0, 4).toString('hex') === '504b0304', { status: before.status, transportDigest: before.data.bytes && digest(before.data.bytes), normalizedPackageDigest: f.package.packageDigest });
  const zip = JSON.parse(execFileSync('python3', ['-B', '-c', 'import sys,io,zipfile,json\nz=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))\nprint(json.dumps({"crcValid":z.testzip() is None,"files":z.namelist()}))'], { input: before.data.bytes, encoding: 'utf8' }));
  h.check('Independent ZIP reader verifies complete original archive CRCs', zip.crcValid === true && zip.files.length > 0, zip);
  const model = await a.draft(h, app), r = { kind: 'delivery-fixture-restore', phase: 'created', app,
    origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), original: model, last: model, commands: [] };
  h.state.resources.push(r); h.persist();
  try {
    const entities = structuredClone(model.entities); entities[0].description = 'Unpublished draft ' + h.state.prefix;
    await save(h, r, entities);
    h.check('Original frozen revision remains byte-for-byte identical after draft edit', same((await h.ok(h.admin, 'GET', '/panel/application/definitions/' + app.id + '/revisions/' + f.revision.id)).value, f.revision));
    const after = await packageContent(h.admin, downloadRoute, h.observe);
    h.check('Original package bytes and owner metadata remain immutable after draft edit', after.status === 200 && Buffer.isBuffer(after.data.bytes) && after.data.bytes.equals(before.data.bytes) && same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + f.package.id)).value, f.package));
    const latest = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + app.id)).value;
    const preview = (await h.ok(h.admin, 'POST', '/panel/application/definitions/' + app.id + '/revisions/preview', { expectedDefinitionVersion: latest.updateTime })).value;
    h.check('New draft requires a new immutable revision and has a different frozen digest', preview.nextVersion === f.revision.version + 1 && preview.digest !== f.revision.digest && preview.definitionVersion === latest.updateTime, preview);
  } finally { await restore(h, r); }
}
frozenDraft.transport = 'owner-api';
const requests = '/panel/application/deployment-requests/';
const unfinishedRequest = 'application package has an unfinished deployment request; terminate it before cleanup';
const previewRefusal = response => [200, 400, 409].includes(response?.status) && response.data?.error?.code === 21 && response.data.error.message === unfinishedRequest && response.data.value == null;
// The public request DTO omits operationId while it has no approved operation.
const noOperation = value => !Object.hasOwn(value, 'operationId') || value.operationId === 0;
function requestActor(h, r) {
  if (!same(h.admin.identity, r.creation?.actorIdentity) || h.admin.origin !== r.creation?.origin ||
      r.creation.outcome !== 'accepted' || !r.creation.ownershipConfirmed || r.commands?.some(c => c.outcome === 'unknown') ||
      (r.packageDelete && r.packageDelete.outcome !== 'rejected-and-unchanged')) throw new h.Blocked('Original preview request, actor or package deletion unresolved; no replay');
}
async function requestCommand(h, r, action) {
  requestActor(h, r);
  const current = (await h.ok(h.admin, 'GET', requests + r.id)).value;
  if (!same(current, r.last)) throw new h.Blocked('Original preview request changed concurrently; retain exact request');
  const c = { route: requests + r.id + '/' + action, body: { expectedVersion: current.version, reason: 'Clean exact preview regression request' }, outcome: 'unknown' };
  (r.commands ||= []).push(c); h.persist();
  c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  h.check('Original conditional request command acknowledged exact original request', h.good(c.response) && c.response.data.value?.id === r.id, c.response);
  if (action === 'cancel') {
    const after = (await h.ok(h.admin, 'GET', requests + r.id)).value;
    h.check('Independent original request confirms cancellation without installation execution', same(after, c.response.data.value) && after.status === 'cancelled' &&
      after.version === current.version + 1 && noOperation(after) && after.instanceKey === current.instanceKey && after.deploymentId === current.deploymentId &&
      after.packageId === current.packageId && after.sourceDigest === current.sourceDigest && after.planDigest === current.planDigest && same(after.requestedBy, current.requestedBy), after);
    r.last = after;
  } else {
    const after = await h.api(h.admin, 'GET', requests + r.id);
    h.check('Original cleaned request is independently absent, not merely hidden by an authentication failure', [200, 404].includes(after.status) && after.data?.error?.code === 2 && after.data.value == null, after);
    h.check('Complete owner request directory independently excludes exact cleaned request', !(await h.directory(h.admin, requests)).some(v => v.id === r.id));
  }
  c.outcome = 'confirmed'; h.persist();
}
async function cleanupPreviewRequest(h, r) {
  requestActor(h, r);
  if (!r.last || r.last.id !== r.id || !noOperation(r.last) || !['submitted', 'cancelled'].includes(r.last.status)) throw new h.Blocked('Original preview request is not independently cancellable/cleanable');
  if (r.last.status === 'submitted') await requestCommand(h, r, 'cancel');
  await requestCommand(h, r, 'cleanup');
  r.phase = 'deleted'; h.persist();
  return { proof: 'Original requester cancelled and cleaned exact unapproved request with conditional versions; independent exact absence and complete directory. Published package and installations retained.' };
}
async function reconcilePreviewRefusal(h, r, evidence, caseSha256, { loadFixture = fixture, readContent = packageContent } = {}) {
  const route = '/panel/application/model-packages/' + r.creation?.intended?.packageId;
  if (r.kind !== 'package-preview-request' || !same(h.admin.identity, r.creation?.actorIdentity) || h.admin.origin !== r.creation?.origin ||
      r.creation.outcome !== 'accepted' || !r.creation.ownershipConfirmed || r.commands?.length || r.packageDelete?.outcome !== 'unknown' ||
      r.packageDelete.route !== route || !previewRefusal(r.packageDelete.response) || !/^sha256:[a-f0-9]{64}$/.test(caseSha256 || '') ||
      !['F031-002', 'F031-003'].includes(evidence?.caseId) || evidence.status !== 'failed') throw new h.Blocked('Original package refusal needs exact immutable failed-case, command, actor and owner receipt; no guessed disposition');
  const trace = evidence.trace || [], commands = trace.filter(e => e.kind === 'request' && e.method === 'DELETE');
  const previews = trace.filter(e => e.kind === 'request' && e.method === 'GET' && e.route === route + '/cleanup-preview');
  const downloads = trace.filter(e => e.kind === 'request' && e.method === 'GET' && e.route === route + '/content' && e.representation === 'package-download');
  h.check('Immutable original case proves one exact terminal refusal after allowed and blocked previews, with unchanged ZIP reads on both sides',
    commands.length === 1 && commands[0].route === route && same(commands[0].actor, h.admin.identity) && commands[0].origin === h.admin.origin && same(commands[0].response, r.packageDelete.response) &&
    previews.length === 2 && previews[0].response?.data?.value?.allowed === true && previews[1].response?.data?.value?.allowed === false && previews[1].response.data.value.blocker === unfinishedRequest &&
    downloads.length === 2 && downloads.every(e => same(e.actor, h.admin.identity) && e.origin === h.admin.origin && e.response?.status === 200) &&
    downloads[0].response.byteLength > 0 && /^sha256:[a-f0-9]{64}$/.test(downloads[0].response.digest || '') && same(downloads[0].response, downloads[1].response) &&
    trace.indexOf(previews[0]) < trace.indexOf(previews[1]) && trace.indexOf(previews[1]) < trace.indexOf(commands[0]) && trace.indexOf(downloads[0]) < trace.indexOf(commands[0]) && trace.indexOf(downloads[1]) > trace.indexOf(commands[0]));
  const f = await loadFixture(h);
  h.check('Exact original request intent binds the independently verified immutable fixture package', f.package.id === r.creation.intended.packageId && r.creation.intended.expectedDigest === f.package.artifactDigest &&
    previews.every(e => e.response.data.value.packageId === f.package.id && e.response.data.value.sourceDigest === f.package.packageDigest));
  const current = await readContent(h.admin, route + '/content', h.observe);
  h.check('Independent original ZIP bytes still equal both immutable historical reads after the known refusal', current.status === 200 && Buffer.isBuffer(current.data.bytes) && current.data.bytes.length === downloads[0].response.byteLength && digest(current.data.bytes) === downloads[0].response.digest);
  h.check('Original request still has exact acknowledged submitted identity and revision before formal cleanup', r.last?.id === r.id && r.last.packageId === f.package.id && r.last.status === 'submitted' && noOperation(r.last) && same((await h.ok(h.admin, 'GET', requests + r.id)).value, r.last));
  r.packageDelete.disposition = { originalOutcome: r.packageDelete.outcome, caseId: evidence.caseId, caseSha256, requestId: r.id, zipDigest: downloads[0].response.digest,
    proof: 'Exact original terminal owner refusal, immutable package and historical/current ZIP identity, unchanged original request; no package DELETE replay.' };
  r.packageDelete.outcome = 'rejected-and-unchanged'; h.persist();
}
function initialCleanupPreview(h, pkg, preview) {
  h.check('Initial cleanup preview binds exact original package identity and boolean decision',
    preview?.packageId === pkg.id && preview.sourceKind === 'model-package' && preview.sourceDigest === pkg.packageDigest && typeof preview.allowed === 'boolean', preview);
  if (!preview.allowed || preview.blocker) {
    h.observe({ kind: 'package-cleanup-initial-prerequisite-blocked', packageId: pkg.id, preview });
    throw new h.Blocked('Initial source package cleanup is unavailable before this case adds any reference: ' + (preview.blocker || 'owner preview denied'));
  }
}
async function previewRace(h) {
  const f = await fixture(h), route = '/panel/application/model-packages/' + f.package.id;
  const installed = [], authority = [], operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
  for (const instance of f.installations || []) installed.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + instance.id)).value);
  for (const request of f.deploymentRequests || []) {
    authority.push({ route: requests + request.id, value: (await h.ok(h.admin, 'GET', requests + request.id)).value });
    authority.push({ route: operations + request.operationId, value: (await h.ok(h.admin, 'GET', operations + request.operationId)).value });
  }
  h.check('Preview race retains two independent installed instances and their successful delivery authority', installed.length === 2 && authority.length === 4 && authority.every(v => v.value.status === 'succeeded'));
  const before = await packageContent(h.admin, route + '/content', h.observe);
  h.check('Original package bytes are available before any preview probe', before.status === 200 && Buffer.isBuffer(before.data.bytes));
  const preview = (await h.ok(h.admin, 'GET', route + '/cleanup-preview')).value;
  initialCleanupPreview(h, f.package, preview);
  const request = await h.create(requests, { sourceKind: 'model-package', packageId: f.package.id, expectedDigest: f.package.artifactDigest,
    instanceKey: h.state.prefix + '-preview', instanceName: '预览后新增引用', storageProvisioning: { mode: 'allocate' }, reason: 'Verify cleanup rechecks a newly submitted reference' }, 'package-preview-request');
  const r = h.state.resources.find(v => v.kind === 'package-preview-request' && v.id === request.id);
  r.commands = []; r.last = (await h.ok(h.admin, 'GET', requests + request.id)).value; h.persist();
  let primary;
  try {
    h.check('Original request independently references exact package after allowed preview with no execution', same(r.last, request) && request.status === 'submitted' && noOperation(request) &&
      request.packageId === f.package.id && request.sourceKind === 'model-package' && request.sourceDigest === f.package.packageDigest && request.namespace === 'panel' && request.instanceKey === h.state.prefix + '-preview', request);
    const changed = (await h.ok(h.admin, 'GET', route + '/cleanup-preview')).value;
    const blocker = unfinishedRequest;
    h.check('New preview observes the new unfinished reference without granting deletion', changed.allowed === false && changed.blocker === blocker && changed.packageId === f.package.id, changed);
    r.packageDelete = { route, outcome: 'unknown' }; h.persist();
    const response = await h.api(h.admin, 'DELETE', route); r.packageDelete.response = response; h.persist();
    const originalPackage = (await h.ok(h.admin, 'GET', route)).value;
    const bytes = await packageContent(h.admin, route + '/content', h.observe);
    const exactRefusal = previewRefusal(response);
    if (exactRefusal && same(originalPackage, f.package) && bytes.status === 200 && Buffer.isBuffer(bytes.data.bytes) && bytes.data.bytes.equals(before.data.bytes)) { r.packageDelete.outcome = 'rejected-and-unchanged'; h.persist(); }
    h.check('Actual DELETE rechecks exact unfinished reference and preserves complete original package and ZIP bytes', r.packageDelete.outcome === 'rejected-and-unchanged', response);
    h.check('Refused package delete preserves the complete exact original new request', same((await h.ok(h.admin, 'GET', requests + request.id)).value, request));
    for (const [i, instance] of installed.entries()) h.check('Actual refused delete leaves original installed instance unchanged ' + i, same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + instance.id)).value, instance));
    for (const entry of authority) h.check('Actual refused delete retains original successful delivery authority', same((await h.ok(h.admin, 'GET', entry.route)).value, entry.value));
    h.check('No installation or operation was created for the new unapproved reference', !(await h.directory(h.admin, '/panel/application/installations/')).some(v => v.deploymentId === request.deploymentId) && !(await h.directory(h.admin, operations)).some(v => v.requestId === request.id));
  } catch (error) { primary = error; throw error; }
  finally { try { await cleanupPreviewRequest(h, r); } catch (error) { h.observe({ kind: 'preview-request-cleanup-open', id: r.id, error: error.message }); if (!primary) throw error; } }
  const restored = (await h.ok(h.admin, 'GET', route + '/cleanup-preview')).value;
  h.check('Original package cleanup preview becomes allowed after formal original request cleanup', restored.allowed === true && same(restored, preview), restored);
}
previewRace.transport = 'owner-api';
module.exports = { handlers: { 'F020-003': frozenDraft, 'F031-002': previewRace, 'F031-003': previewRace }, fixture, save, restore, semanticEntities, cleanupPreviewRequest, requestCommand, reconcilePreviewRefusal, previewRefusal, initialCleanupPreview };
