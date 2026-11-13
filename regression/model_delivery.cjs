// New immutable model fixtures use public publication and delivery owners.
// Retention is an explicit disposition, never a deletion claim.
const { isDeepStrictEqual: same } = require('node:util');
const definitions = '/panel/application/definitions/';
const deliveries = r => r.modelDelivery ? [r.modelDelivery, ...(r.modelDelivery.successors || [])] : [];
function original(h, r) {
  if (r.kind !== 'definition' || !r.creation?.ownershipConfirmed || r.creation.origin !== h.admin.origin ||
      !same(r.creation.actorIdentity, h.admin.identity) || r.pendingAuthoringSave && !r.pendingAuthoringSave.confirmed ||
      deliveries(r).some(d => d.commands.some(c => c.outcome === 'unknown') || d.imports?.some(c => c.outcome !== 'confirmed') || d.packageDisposition?.outcome === 'unknown'))
    throw new h.Blocked('Original model fixture owner or command remains unresolved; no publish/build replay or guessed deletion');
}
async function command(h, r, route, body, read, verify, d = r.modelDelivery) {
  original(h, r);
  if (!deliveries(r).includes(d)) throw new h.Blocked('Model command must belong to its exact tracked publication lineage');
  const actorIdentity = structuredClone(h.admin.identity), origin = h.admin.origin;
  const c = { route, body: structuredClone(body), outcome: 'unknown' };
  d.commands.push(c); h.persist();
  c.response = await h.api(h.admin, 'POST', route, body); h.persist();
  h.check('Original model fixture command is acknowledged', h.good(c.response), c.response);
  c.value = await read(c.response.data.value); h.persist();
  h.check('Independent immutable owner read confirms exact original model fixture command', h.admin.origin === origin && same(h.admin.identity, actorIdentity) && same(c.value, c.response.data.value) && verify(c.value), c.value);
  c.outcome = 'confirmed'; h.persist(); return c.value;
}
async function publish(h, app) {
  await require('./delivery_cases.cjs').fixture(h);
  const r = h.state.resources.find(v => v.kind === 'definition' && v.id === app.id);
  if (!r || r.modelDelivery) throw new h.Blocked('Model publication requires its unique new original definition');
  original(h, r);
  const current = (await h.ok(h.admin, 'GET', definitions + r.id)).value, route = definitions + r.id + '/revisions/';
  const preview = (await h.ok(h.admin, 'POST', route + 'preview', { expectedDefinitionVersion: current.updateTime })).value;
  h.check('Formal model preflight confirms exact owned definition and target digest', preview.compatible === true && preview.definitionVersion === current.updateTime && /^sha256:[a-f0-9]{64}$/.test(preview.digest));
  r.modelDelivery = { commands: [], requests: [] }; h.persist();
  const revision = await command(h, r, route, { expectedDefinitionVersion: preview.definitionVersion, expectedPreviewDigest: preview.digest, changeLog: 'Isolated model contract regression' },
    v => h.ok(h.admin, 'GET', route + v.id).then(x => x.value), v => v.applicationDefinitionId === r.id && v.applicationUuid === app.uuid && v.digest === preview.digest && v.definitionVersion === current.updateTime);
  r.modelDelivery.revision = revision; h.persist();
  const pkg = await command(h, r, route + revision.id + '/model-packages', {},
    v => h.ok(h.admin, 'GET', '/panel/application/model-packages/' + v.id).then(x => x.value), v => v.applicationUuid === app.uuid && v.applicationKey === app.name && v.sourceRevisionId === revision.id && v.status === 'valid');
  r.modelDelivery.package = pkg; h.persist();
  return { application: app, revision, package: pkg, resource: r };
}
async function publishNext(h, f) {
  const r = f.resource; original(h, r);
  const prior = deliveries(r).at(-1), route = definitions + r.id + '/revisions/';
  if (r.phase === 'deleted' || !prior?.revision || !prior.package || !same(f.revision, prior.revision) || !same(f.package, prior.package) ||
      prior.packageDisposition || prior.commands.length !== 2 || !prior.commands.every(c => c.outcome === 'confirmed'))
    throw new h.Blocked('Next publication requires the latest complete immutable predecessor; no stale lineage or publish replay');
  h.check('Original publication and package remain completely unchanged before a new revision',
    same((await h.ok(h.admin, 'GET', route + prior.revision.id)).value, prior.revision) &&
    same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + prior.package.id)).value, prior.package));
  const current = (await h.ok(h.admin, 'GET', definitions + r.id)).value;
  const preview = (await h.ok(h.admin, 'POST', route + 'preview', { expectedDefinitionVersion: current.updateTime })).value;
  h.check('New model publication preflight identifies a changed draft and strictly later revision', current.uuid === r.creation.intended.uuid &&
    current.updateTime > prior.revision.definitionVersion && preview.compatible === true && preview.definitionVersion === current.updateTime &&
    preview.nextVersion > prior.revision.version && /^sha256:[a-f0-9]{64}$/.test(preview.digest) && preview.digest !== prior.revision.digest, preview);
  original(h, r);
  const d = { predecessorRevisionId: prior.revision.id, predecessorPackageId: prior.package.id, commands: [], requests: [] };
  (r.modelDelivery.successors ||= []).push(d); h.persist();
  d.revision = await command(h, r, route, { expectedDefinitionVersion: preview.definitionVersion, expectedPreviewDigest: preview.digest, changeLog: 'Isolated later immutable revision' },
    v => h.ok(h.admin, 'GET', route + v.id).then(x => x.value), v => v.id !== prior.revision.id && v.version === preview.nextVersion &&
      v.applicationDefinitionId === r.id && v.applicationUuid === f.application.uuid && v.definitionVersion === current.updateTime && v.digest === preview.digest, d);
  h.persist();
  d.package = await command(h, r, route + d.revision.id + '/model-packages', {},
    v => h.ok(h.admin, 'GET', '/panel/application/model-packages/' + v.id).then(x => x.value), v => v.id !== prior.package.id &&
      v.applicationUuid === f.application.uuid && v.applicationKey === f.application.name && v.sourceRevisionId === d.revision.id && v.status === 'valid' &&
      v.artifactDigest !== prior.package.artifactDigest, d);
  h.persist();
  return { application: f.application, revision: d.revision, package: d.package, resource: r, delivery: d };
}
async function importExact(h, f, bytes, transfer = require('./owner_transport.cjs').packageUpload, download = require('./owner_transport.cjs').packageContent) {
  const r = f.resource; original(h, r);
  const actorIdentity = structuredClone(h.admin.identity), origin = h.admin.origin;
  const unchangedActor = () => {
    if (!same(h.admin.identity, actorIdentity) || h.admin.origin !== origin) throw new h.Blocked('Original model importer actor changed; no replacement command');
  };
  const p = r.modelDelivery?.package;
  if (!p || !same(f.package, p) || !Buffer.isBuffer(bytes) || !bytes.length || bytes.length > 64 * 1024 * 1024 || r.modelDelivery.packageDisposition) throw new h.Blocked('Original confirmed model ZIP and active source package required');
  const source = await download(h.admin, '/panel/application/model-packages/' + p.id + '/content', h.observe);
  h.check('Positive importer starts from entire independently downloaded original immutable ZIP bytes', source.status === 200 && Buffer.isBuffer(source.data.bytes) && source.data.bytes.equals(bytes));
  const before = await h.directory(h.admin, '/panel/application/model-packages/');
  unchangedActor();
  const c = { outcome: 'unknown', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
    name: h.state.prefix + '-model-roundtrip.zip', digest: 'sha256:' + require('node:crypto').createHash('sha256').update(bytes).digest('hex'), size: bytes.length, upload: { outcome: 'unknown' } };
  (r.modelDelivery.imports ||= []).push(c); h.persist();
  c.upload.response = await transfer(h.admin, { name: c.name, bytes }, h.observe); h.persist();
  unchangedActor();
  const ack = c.upload.response, upload = ack.data?.value;
  h.check('File acknowledges exact original model ZIP size/digest/purpose and live upload reference', h.good(ack) && /^[A-Za-z0-9_-]{43}$/.test(upload?.uploadRef || '') && upload.name === c.name && upload.size === c.size && upload.digest === c.digest && upload.purpose === 'application-model-package' && upload.expiresAt > Date.now(), ack);
  c.upload.outcome = 'confirmed'; c.command = { method: 'POST', route: '/panel/application/model-packages/imports/', body: { uploadRef: upload.uploadRef }, outcome: 'unknown' }; h.persist();
  c.command.response = await h.api(h.admin, c.command.method, c.command.route, c.command.body); h.persist();
  unchangedActor();
  const current = (await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + p.id)).value;
  const after = await download(h.admin, '/panel/application/model-packages/' + p.id + '/content', h.observe);
  unchangedActor();
  h.check('Real importer confirms the exact original model package with complete unchanged directory and ZIP bytes', h.good(c.command.response) && same(c.command.response.data.value, p) && same(current, p) && same(await h.directory(h.admin, '/panel/application/model-packages/'), before) && after.status === 200 && Buffer.isBuffer(after.data.bytes) && after.data.bytes.equals(bytes), c.command.response);
  c.command.outcome = 'confirmed'; c.outcome = 'confirmed'; c.proof = 'Exact original immutable package imported through File upload reference and Panel real owner; duplicate-upload release acknowledged by importer. No independent File physical-byte absence claim.'; h.persist();
}
function linkRequest(h, f, request) {
  const d = f.delivery || f.resource.modelDelivery;
  if (!deliveries(f.resource).includes(d) || !same(d.package, f.package) || request.creation?.intended?.packageId !== f.package.id || !request.creation.ownershipConfirmed || request.kind !== 'deployment-review-request') throw new h.Blocked('Model fixture must retain its exact formal delivery request');
  d.requests.push(request.id); h.persist();
}
const packageAbsent = response => [200, 404].includes(response?.status) && response.data?.error?.code === 2 && response.data.value == null;
function packageRemovalMatches(h, r) {
  const d = r.modelDelivery, c = d?.packageDisposition, p = d?.package;
  return !!c && !!p && c.outcome === 'confirmed' && c.method === 'DELETE' && c.route === '/panel/application/model-packages/' + p.id &&
    c.origin === r.creation.origin && same(c.actorIdentity, r.creation.actorIdentity) && same(c.before, p) &&
    c.preview?.allowed === true && c.preview.packageId === p.id && c.preview.sourceDigest === p.packageDigest &&
    h.good(c.response) && packageAbsent(c.absence) && c.directoryAbsent === true;
}
async function removePackage(h, f) {
  const r = f.resource; original(h, r);
  const d = r.modelDelivery, p = d?.package;
  if (!p || !same(f.package, p) || d.packageDisposition) throw new h.Blocked('Exact original model package removal intent missing or already dispatched; no DELETE replay');
  const route = '/panel/application/model-packages/' + p.id, before = (await h.ok(h.admin, 'GET', route)).value;
  if (!same(before, p)) throw new h.Blocked('Original immutable model package changed; no source cleanup');
  const preview = (await h.ok(h.admin, 'GET', route + '/cleanup-preview')).value;
  h.check('Formal cleanup preview authorizes only the exact original model package transport source', preview.allowed === true && preview.packageId === p.id && preview.sourceDigest === p.packageDigest, preview);
  const c = { method: 'DELETE', route, before, preview, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' };
  d.packageDisposition = c; h.persist(); c.response = await h.api(h.admin, 'DELETE', route); h.persist();
  c.absence = await h.api(h.admin, 'GET', route); c.directoryAbsent = !(await h.directory(h.admin, '/panel/application/model-packages/')).some(v => v.id === p.id); h.persist();
  h.check('Original allowed model package DELETE and independent owner/directory confirm exact absence', h.good(c.response) && packageAbsent(c.absence) && c.directoryAbsent, c.absence);
  c.outcome = 'confirmed'; h.persist();
  h.check('Model package disposition retains complete original ownership and allowed cleanup receipt', packageRemovalMatches(h, r));
  h.observe({ kind: 'original-model-package-disposition', packageId: p.id, artifactDigest: p.artifactDigest, transportSourceDigest: p.packageDigest,
    proof: 'Original acknowledged allowed package cleanup and independent Panel absence; File compensation acknowledged by Panel, no independent physical-byte absence claim.' });
}
async function retainDelivery(h, r, d) {
  if (!d?.revision || !d.package || d.commands.length !== 2 || !d.commands.every(c => c.outcome === 'confirmed')) throw new h.Blocked('Original immutable model publication/build not fully confirmed');
  const [published, built] = d.commands;
  if (published.route !== definitions + r.id + '/revisions/' || built.route !== published.route + d.revision.id + '/model-packages' ||
      published.body.expectedDefinitionVersion !== d.revision.definitionVersion || published.body.expectedPreviewDigest !== d.revision.digest ||
      d.revision.applicationUuid !== r.creation.intended.uuid || d.package.sourceRevisionId !== d.revision.id ||
      !h.good(published.response) || !h.good(built.response) || !same(published.response.data.value, d.revision) ||
      !same(built.response.data.value, d.package) || !same(published.value, d.revision) || !same(built.value, d.package))
    throw new h.Blocked('Retained model facts do not match the exact original publication and build receipts');
  if (h.state.resources.some(v => v.kind === 'deployment-review-request' && v.creation?.intended?.packageId === d.package.id && v.phase !== 'deleted'))
    throw new h.Blocked('Original model package still has an undisposed delivery request');
  for (const id of d.requests) {
    const requests = h.state.resources.filter(v => v.kind === 'deployment-review-request' && v.id === id && v.creation?.intended?.packageId === d.package.id);
    if (requests.length !== 1 || requests[0].phase !== 'deleted') throw new h.Blocked('Original model installation still needs formal lifecycle disposition');
  }
  const revision = (await h.ok(h.admin, 'GET', definitions + r.id + '/revisions/' + d.revision.id)).value;
  if (d.packageDisposition) {
    if (d !== r.modelDelivery) throw new h.Blocked('Successor source removal requires its own exact owner proof; never reuse predecessor deletion');
    h.check('Removed model source retains exact allowed original deletion proof and independent continued absence', packageRemovalMatches(h, r) &&
      packageAbsent(await h.api(h.admin, 'GET', '/panel/application/model-packages/' + d.package.id)));
  } else {
    const pkg = (await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + d.package.id)).value;
    h.check('Retained model fixture preserves exact immutable package and original application identity', same(pkg, d.package) && pkg.applicationUuid === r.creation.intended.uuid);
  }
  h.check('Retained model fixture preserves complete immutable revision and original definition identity', same(revision, d.revision) && revision.applicationDefinitionId === r.id);
  return { retainedDefinitionId: r.id, retainedRevisionId: revision.id,
    ...(d.packageDisposition ? { formallyRemovedPackageId: d.package.id } : { retainedPackageId: d.package.id }),
    proof: d.packageDisposition ? 'Published definition/revision intentionally retained; original package formally removed with exact allowed deletion proof. Original delivery requests separately disposed; no revision deletion or File physical-byte absence claim.' : 'Published definition, revision and package intentionally retained as immutable isolated fixture facts; original delivery requests separately formally disposed. No published fact deletion claim.' };
}
async function retained(h, r) {
  original(h, r);
  const all = deliveries(r), proofs = [];
  for (const [index, d] of all.entries()) {
    if (index && (d.predecessorRevisionId !== all[index - 1].revision?.id || d.predecessorPackageId !== all[index - 1].package?.id ||
        d.revision?.version <= all[index - 1].revision?.version)) throw new h.Blocked('Immutable publication predecessor lineage changed; no retention claim');
    proofs.push(await retainDelivery(h, r, d));
  }
  if (!proofs.length) throw new h.Blocked('Original immutable model publication/build not fully confirmed');
  original(h, r);
  r.phase = 'deleted'; r.retentionProof = { ...proofs[0], ...(proofs.length > 1 ? { successors: proofs.slice(1) } : {}) };
  h.persist(); h.observe({ kind: 'retained-model-delivery-fixture', ...r.retentionProof }); return r.retentionProof;
}
module.exports = { publish, publishNext, deliveries, linkRequest, retained, command, removePackage, packageRemovalMatches, importExact };
