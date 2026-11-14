// Bound File upload references are consumed and released only by authenticated
// service owners (e.g. Panel). Human callers upload to /files/self/files/upload-references/
// and never bypass Service-only /files/upload-references/:ref/consume or /files/bound-files/.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const { packageContent, packageUpload, referenceTransfer } = require('./owner_transport.cjs');
const sourcePurpose = 'application-function-block-source';
const wrongPurposeTag = 'regression-reference-proof';
const uploadRouteFor = (purpose = sourcePurpose) => '/files/self/files/upload-references/?' + new URLSearchParams({ purpose });
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
function original(h, r) {
  if (!same(h.admin.identity, r.actorIdentity) || h.admin.origin !== r.origin || r.commands.some(c => c.confirmed !== true))
    throw new h.Blocked('Original File reference actor or command unresolved; no upload or bind replay');
}
function consumeRoute(r) { return '/files/upload-references/' + r.fileRef.slice(6) + '/consume'; }
function consumeBody(r, consumer = r.consumer) {
  return { namespace: r.namespace, ownerNamespace: r.namespace, ownerSubject: r.subject, purpose: r.purpose || sourcePurpose, consumer,
    expectedName: r.name, expectedSize: r.expectedSize, expectedDigest: r.expectedDigest };
}
function downloadRoute(r, consumer = r.consumer) { return '/files/bound-files/' + r.fileRef + '/download?' + new URLSearchParams({ namespace: r.namespace, consumer }); }
function deleteRoute(r, consumer = r.consumer) { return '/files/bound-files/' + r.fileRef + '?' + new URLSearchParams({ namespace: r.namespace, consumer, expectedDigest: r.expectedDigest }); }
function bindSourceRoute(definitionId) { return '/panel/application/definitions/' + definitionId + '/function-blocks/sources'; }
function bindSourceBody(r, overrides = {}) {
  return {
    expectedDefinitionVersion: overrides.expectedDefinitionVersion ?? r.definitionVersion,
    uploadRef: r.fileRef.slice(6),
    name: overrides.name ?? r.name,
    size: overrides.size ?? r.expectedSize,
    digest: overrides.digest ?? r.expectedDigest,
  };
}
function sourceView(r) {
  return {
    applicationId: r.definitionId,
    applicationUuid: r.definitionUuid,
    definitionVersion: r.definitionVersion,
    source: { uri: 'local:' + r.fileRef, digest: r.expectedDigest, size: r.expectedSize },
  };
}
function wrongDigestFor(digest) {
  const hex = 'sha256:' + '0'.repeat(64);
  return digest === hex ? 'sha256:' + '1'.repeat(64) : hex;
}
async function create(h, subject, app, peerApp, opts = {}, transfer = referenceTransfer) {
  if (!/^account:[1-9][0-9]*$/.test(subject)) throw new h.Blocked('Original real account subject required');
  if (!app?.id || !app?.uuid || !app?.updateTime || !peerApp?.uuid || !peerApp?.id || !peerApp?.updateTime)
    throw new h.Blocked('Original target and peer Panel definitions required');
  const suffix = crypto.randomBytes(8).toString('hex');
  const purpose = opts.purpose || sourcePurpose;
  const payload = Buffer.from('package main\n// '+suffix+' 中文 Δ\nfunc Handle() string { return "ok" }\n', 'utf8');
  const r = {
    kind: 'bound-reference-probe', id: crypto.randomBytes(16).toString('hex'), phase: 'intent', origin: h.admin.origin,
    actorIdentity: structuredClone(h.admin.identity), namespace: h.admin.identity.namespace, subject, purpose,
    definitionId: app.id, definitionUuid: app.uuid, definitionVersion: app.updateTime,
    peerDefinitionId: peerApp.id, peerDefinitionUuid: peerApp.uuid, peerDefinitionVersion: peerApp.updateTime,
    name: 'proof-' + suffix + '.go', consumer: 'panel:function-block-source:' + app.uuid,
    foreignConsumer: 'panel:function-block-source:' + peerApp.uuid,
    expectedSize: payload.length, expectedDigest: hash(payload), commands: [],
  };
  h.state.resources.push(r); h.persist();
  const route = uploadRouteFor(purpose);
  const c = { action: 'upload', route, confirmed: false, name: r.name, size: r.expectedSize, digest: r.expectedDigest };
  r.commands.push(c); h.persist();
  c.response = await transfer(h.admin, 'POST', route, { name: r.name, bytes: payload }, h.observe); h.persist();
  const v = c.response.data?.value;
  h.check('Formal private reference upload acknowledges original name, content, purpose, expiry and fresh opaque identity', h.good(c.response) &&
    /^[A-Za-z0-9_-]{43}$/.test(v?.uploadRef || '') && v.name === r.name && v.size === r.expectedSize && v.digest === r.expectedDigest && v.purpose === purpose &&
    Number.isSafeInteger(v.expiresAt) && v.expiresAt > Date.now(), { ...c.response, data: { ...c.response.data, value: { ...v, uploadRef: '[REDACTED]' } } });
  r.fileRef = 'bound_' + v.uploadRef; c.confirmed = true; r.phase = 'uploaded'; h.persist();
  return r;
}
async function command(h, r, action, transfer = referenceTransfer) {
  original(h, r);
  const allowed = ['service-guard', 'wrong-purpose-bind', 'mismatch-bind', 'bind', 'foreign-bind'];
  if (!r.fileRef || !allowed.includes(action) || r.commands.some(c => c.action === action))
    throw new h.Blocked('Exact original Panel bound-reference action required; no duplicate command');
  if (action === 'foreign-bind' ? r.phase !== 'bound' : r.phase !== 'uploaded')
    throw new h.Blocked('Original bound-reference phase does not permit action ' + action);

  if (action === 'service-guard') {
    const c = { action, method: 'POST', route: consumeRoute(r), body: consumeBody(r), confirmed: false };
    r.commands.push(c); h.persist();
    const consumeRes = await h.api(h.admin, 'POST', c.route, c.body);
    const downloadRes = await transfer(h.admin, 'GET', downloadRoute(r), undefined, h.observe);
    const deleteRes = await h.api(h.admin, 'DELETE', deleteRoute(r));
    c.response = { consume: consumeRes, download: { status: downloadRes.status }, delete: deleteRes };
    h.persist();
    h.check('Direct human session is rejected on Service-only File consume/bound-download/bound-delete routes',
      consumeRes?.status === 403 && downloadRes?.status === 403 && deleteRes?.status === 403, c.response);
    if (!same(h.admin.identity, r.actorIdentity) || h.admin.origin !== r.origin) throw new h.Blocked('Original File actor changed during service-guard probe');
    c.confirmed = true; h.persist(); return c;
  }

  const defId = action === 'foreign-bind' ? r.peerDefinitionId : r.definitionId;
  const defVersion = action === 'foreign-bind' ? r.peerDefinitionVersion : r.definitionVersion;
  const body = bindSourceBody(r, {
    expectedDefinitionVersion: defVersion,
    ...(action === 'mismatch-bind' ? { digest: wrongDigestFor(r.expectedDigest) } : {}),
  });
  const c = { action, method: 'POST', route: bindSourceRoute(defId), body, confirmed: false };
  r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();

  if (action === 'bind') {
    h.check('Panel owner consumes and binds original upload reference to exact definition consumer',
      h.good(c.response) && same(c.response.data.value, sourceView(r)), c.response);
    r.phase = 'bound';
  } else {
    const msg = c.response?.data?.error?.message || '';
    const expected = action === 'mismatch-bind' ? 'upload reference does not match expected content' : 'upload reference cannot be consumed';
    h.check('Panel/File owner refuses cross-consumer, mismatched or wrong-purpose upload reference without mutating binding',
      c.response?.status === 200 && c.response.data?.value == null && c.response.data?.error?.code > 0 && msg.includes(expected), c.response);
  }
  if (!same(h.admin.identity, r.actorIdentity) || h.admin.origin !== r.origin) throw new h.Blocked('Original File actor changed during command confirmation');
  c.confirmed = true; h.persist(); return c;
}
async function cleanup(h, r) {
  original(h, r);
  const bound = r.commands.some(c => c.action === 'bind' && c.confirmed);
  if (!bound && r.purpose === sourcePurpose)
    throw new h.Blocked('Original reference lacks exact Panel owner consume receipt');
  r.phase = 'deleted'; h.persist();
  return { proof: 'Human upload consumed by Panel Service owner with exclusive definition consumer, Service-only File routes verified 403 against human session, foreign-consumer/mismatch/wrong-purpose bind refused. Multi-reference share/decrement contract remains unimplemented.' };
}
async function references(h) {
  const f = await require('./delivery_cases.cjs').fixture(h);
  const account = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account;
  h.check('File protocol owner uses exact original human account in its home namespace',
    account?.account === h.admin.identity.account && Number.isSafeInteger(account.id) && account.id > 0);

  const targetApp = await a.definition(h, 'ref-target');
  const peerApp = await a.definition(h, 'ref-peer');
  const subject = 'account:' + account.id;

  const wrongRef = await create(h, subject, targetApp, peerApp, { purpose: wrongPurposeTag });
  const target = await create(h, subject, targetApp, peerApp);
  const peer = await create(h, subject, peerApp, targetApp);

  await command(h, target, 'service-guard');
  await command(h, wrongRef, 'wrong-purpose-bind');
  await command(h, target, 'mismatch-bind');
  await command(h, target, 'bind');
  await command(h, peer, 'bind');
  await command(h, target, 'foreign-bind');

  // Verify model-package owner consume/duplicate-release + immutable bytes read on fixture package.
  const pkgRoute = '/panel/application/model-packages/' + f.package.id;
  const originalZip = await packageContent(h.admin, pkgRoute + '/content', h.observe);
  h.check('Immutable fixture ZIP is readable before package upload-reference round-trip',
    originalZip.status === 200 && Buffer.isBuffer(originalZip.data?.bytes));
  const pkgUploadAck = await packageUpload(h.admin, { name: h.state.prefix + '-bound-roundtrip.zip', bytes: originalZip.data.bytes }, h.observe);
  const pkgRef = pkgUploadAck.data?.value;
  h.check('Model-package bounded upload acknowledges exact digest and opaque ref',
    h.good(pkgUploadAck) && /^[A-Za-z0-9_-]{43}$/.test(pkgRef?.uploadRef || '') && pkgRef.purpose === 'application-model-package' && pkgRef.digest === hash(originalZip.data.bytes), pkgUploadAck);
  const imported = await h.api(h.admin, 'POST', '/panel/application/model-packages/imports/', { uploadRef: pkgRef.uploadRef });
  h.check('Panel importer consumes package upload reference and retains exact immutable package bytes',
    h.good(imported) && same(imported.data.value, f.package), imported);
  const afterZip = await packageContent(h.admin, pkgRoute + '/content', h.observe);
  h.check('Immutable package ZIP bytes remain identical after duplicate import consume and release',
    afterZip.status === 200 && Buffer.isBuffer(afterZip.data?.bytes) && afterZip.data.bytes.equals(originalZip.data.bytes));

  h.observe({
    kind: 'exclusive-bound-reference-lifecycle-proof',
    target: { fileRef: target.fileRef, commands: target.commands },
    peer: { fileRef: peer.fileRef, commands: peer.commands },
    qualification: 'Bound references consumed through authentic Panel Service owner routes; direct human calls to Service-only File consume/download/delete blocked at 403.',
  });
  await cleanup(h, wrongRef);
  await cleanup(h, target);
  await cleanup(h, peer);
  await h.partial('Authentic Panel Service owner consumption of /files/self/files/upload-references/ (function-block source bind + model-package import), Service-only File consume/download/delete 403 human guard, foreign-consumer/mismatch/wrong-purpose refusal, and independent peer preservation. No public multi-legal-reference acquire/release contract exists in inspected candidate; shared last-reference semantics, exact concurrent acquire/release and lost-deletion response recovery remain open.');
}
references.transport = 'owner-api';
references.requiresOnlyDeliveryFixture = true;
module.exports = {
  handlers: { 'F049-004': references },
  create, command, cleanup, sourceView, consumeBody, consumeRoute, downloadRoute, deleteRoute, bindSourceRoute, bindSourceBody,
};
