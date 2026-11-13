// A File reference is currently exclusive to one consumer. Do not mistake
// public sharing or equal content for two independently held legal references.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { referenceTransfer } = require('./owner_transport.cjs');
const uploadRoute = '/files/self/files/upload-references/?purpose=regression-reference-proof';
const purpose = 'regression-reference-proof';
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
function original(h, r) {
  if (!same(h.admin.identity, r.actorIdentity) || h.admin.origin !== r.origin || r.commands.some(c => c.confirmed !== true))
    throw new h.Blocked('Original File reference actor or command unresolved; no upload/consume/delete replay');
}
function view(r) { return { fileRef: r.fileRef, name: r.name, size: r.expectedSize, digest: r.expectedDigest, namespace: r.namespace, purpose }; }
function consumeRoute(r) { return '/files/upload-references/' + r.fileRef.slice(6) + '/consume'; }
function consumeBody(r, consumer = r.consumer) {
  return { namespace: r.namespace, ownerNamespace: r.namespace, ownerSubject: r.subject, purpose, consumer,
    expectedName: r.name, expectedSize: r.expectedSize, expectedDigest: r.expectedDigest };
}
function downloadRoute(r, consumer = r.consumer) { return '/files/bound-files/' + r.fileRef + '/download?' + new URLSearchParams({ namespace: r.namespace, consumer }); }
function deleteRoute(r, consumer = r.consumer) { return '/files/bound-files/' + r.fileRef + '?' + new URLSearchParams({ namespace: r.namespace, consumer, expectedDigest: r.expectedDigest }); }
async function bytes(h, r, transfer = referenceTransfer) {
  const result = await transfer(h.admin, 'GET', downloadRoute(r), undefined, h.observe);
  h.check('Independent original bound consumer reads exact immutable File bytes', result.status === 200 && Buffer.isBuffer(result.data?.bytes) &&
    result.data.bytes.length === r.expectedSize && hash(result.data.bytes) === r.expectedDigest, { status: result.status, size: result.data.bytes?.length });
  return result;
}
async function missing(h, r, transfer = referenceTransfer) {
  const result = await transfer(h.admin, 'GET', downloadRoute(r), undefined, h.observe);
  h.check('Exact original released reference has the File owner not-found response and no downloadable body', result.status === 404 && result.data?.text === 'bound file not found\n', result);
}
async function create(h, subject, transfer = referenceTransfer) {
  if (!/^account:[1-9][0-9]*$/.test(subject)) throw new h.Blocked('Original real account subject required');
  const suffix = crypto.randomBytes(8).toString('hex'), payload = Buffer.concat([Buffer.from('Private bound reference '+suffix+' 中文 Δ\0'), crypto.randomBytes(17)]);
  const r = { kind: 'bound-reference-probe', id: crypto.randomBytes(16).toString('hex'), phase: 'intent', origin: h.admin.origin,
    actorIdentity: structuredClone(h.admin.identity), namespace: h.admin.identity.namespace, subject, name: 'proof-'+suffix+'.bin',
    consumer: 'regression-'+suffix, foreignConsumer: 'foreign-'+suffix, expectedSize: payload.length, expectedDigest: hash(payload), commands: [] };
  h.state.resources.push(r); h.persist();
  const c = { action: 'upload', route: uploadRoute, confirmed: false, name: r.name, size: r.expectedSize, digest: r.expectedDigest };
  r.commands.push(c); h.persist(); c.response = await transfer(h.admin, 'POST', uploadRoute, { name: r.name, bytes: payload }, h.observe); h.persist();
  const v = c.response.data?.value;
  h.check('Formal private reference upload acknowledges original name, content, purpose, expiry and fresh opaque identity', h.good(c.response) &&
    /^[A-Za-z0-9_-]{43}$/.test(v?.uploadRef || '') && v.name === r.name && v.size === r.expectedSize && v.digest === r.expectedDigest && v.purpose === purpose &&
    Number.isSafeInteger(v.expiresAt) && v.expiresAt > Date.now(), { ...c.response, data: { ...c.response.data, value: { ...v, uploadRef: '[REDACTED]' } } });
  r.fileRef = 'bound_' + v.uploadRef; c.confirmed = true; r.phase = 'uploaded'; h.persist(); return r;
}
async function command(h, r, action, transfer = referenceTransfer) {
  original(h, r);
  if (!r.fileRef || !['bind', 'foreign-bind', 'foreign-delete', 'release', 'old-bind'].includes(action) || r.commands.some(c => c.action === action) ||
      (action === 'bind' ? r.phase !== 'uploaded' : action === 'old-bind' ? r.phase !== 'released' : r.phase !== 'bound'))
    throw new h.Blocked('Exact original single-reference lifecycle action required; no duplicate command');
  const method = ['release', 'foreign-delete'].includes(action) ? 'DELETE' : 'POST';
  const route = method === 'DELETE' ? deleteRoute(r, action === 'foreign-delete' ? r.foreignConsumer : r.consumer) : consumeRoute(r);
  const body = method === 'POST' ? consumeBody(r, action === 'foreign-bind' ? r.foreignConsumer : r.consumer) : undefined;
  const c = { action, method, route, body, confirmed: false }; r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, method, route, body); h.persist();
  if (action === 'bind') {
    h.check('File owner acknowledges exact immutable original consumer binding', h.good(c.response) && same(c.response.data.value, view(r)), c.response);
    await bytes(h, r, transfer); r.phase = 'bound';
  } else if (action === 'release') {
    h.check('Formal original consumer release proves exact complete deletion', h.good(c.response) && c.response.data.deletionConfirmed === true && same(c.response.data.value, view(r)), c.response);
    await missing(h, r, transfer); r.phase = 'released';
  } else {
    const message = action === 'foreign-bind' ? 'upload reference cannot be consumed' : action === 'foreign-delete' ? 'bound file cleanup identity is inconsistent' : 'upload reference not found';
    h.check('Original cross-consumer/retired-reference request reaches exact File lifecycle guard', c.response.status === 200 && c.response.data?.value == null &&
      c.response.data?.error?.code > 0 && c.response.data.error.message === message, c.response);
    if (action === 'old-bind') await missing(h, r, transfer); else await bytes(h, r, transfer);
  }
  if (!same(h.admin.identity, r.actorIdentity) || h.admin.origin !== r.origin) throw new h.Blocked('Original File actor changed during command confirmation');
  c.confirmed = true; h.persist(); return c;
}
async function cleanup(h, r, transfer = referenceTransfer) {
  original(h, r);
  if (r.phase === 'bound') await command(h, r, 'release', transfer);
  if (r.phase !== 'released' || !r.commands.some(c => c.action === 'release' && c.confirmed && c.response?.data?.deletionConfirmed === true))
    throw new h.Blocked('Original reference lacks exact acknowledged release proof; no guessed bind or DELETE');
  await missing(h, r, transfer); original(h, r); r.phase = 'deleted'; h.persist();
  return { proof: 'Single original consumer release acknowledges exact full identity and deletionConfirmed; independent original bound-download NotFound. No filesystem proof or multi-reference lifecycle claimed.' };
}
async function references(h) {
  await require('./delivery_cases.cjs').fixture(h);
  const account = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account;
  h.check('File protocol owner uses exact original human account in its home namespace', account?.account === h.admin.identity.account && Number.isSafeInteger(account.id) && account.id > 0);
  const target = await create(h, 'account:'+account.id), peer = await create(h, 'account:'+account.id);
  await command(h, target, 'bind'); await command(h, peer, 'bind');
  const beforePeer = view(peer);
  await command(h, target, 'foreign-bind');
  const denied = await referenceTransfer(h.admin, 'GET', downloadRoute(target, target.foreignConsumer), undefined, h.observe);
  h.check('Actual second consumer cannot download original bound bytes', denied.status === 404 && denied.data?.text === 'bound file not found\n', denied);
  await bytes(h, target);
  await command(h, target, 'foreign-delete'); await bytes(h, peer);
  await command(h, target, 'release'); await command(h, target, 'old-bind');
  h.check('Single-reference release leaves independent original peer identity unchanged', same(view(peer), beforePeer)); await bytes(h, peer);
  h.observe({ kind: 'exclusive-bound-reference-lifecycle-proof', target: { fileRef: target.fileRef, commands: target.commands }, peer: beforePeer,
    qualification: 'Exactly one legal consumer; refused foreign consumer is not a second live reference. Independent peer is not shared physical content.' });
  await cleanup(h, target); await cleanup(h, peer);
  await h.partial('Exclusive File binding, foreign consume/download/release refusal with original-byte preservation, exact original single-consumer deletionConfirmed/NotFound, old-reference consume refusal and independent peer preservation. No public multi-legal-reference acquire/release contract exists in inspected candidate; shared last-reference semantics, exact concurrent acquire/release and lost-deletion response recovery remain open.');
}
references.transport = 'owner-api'; references.requiresOnlyDeliveryFixture = true;
module.exports = { handlers: { 'F049-004': references }, create, command, cleanup, bytes, missing, view, consumeBody, downloadRoute, deleteRoute };
