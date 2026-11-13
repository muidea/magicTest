// Negative lifecycle commands bind exact original owner snapshots. An unknown
// result is retained; it never authorizes an activation/retry replay or teardown.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const installations = '/panel/application/installations/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const requests = '/panel/application/deployment-requests/';
function refusal(response, code, message) {
  return [200, 400, 404, 409].includes(response?.status) && response.data?.error?.code === code &&
    response.data.error.message === message && response.data.value == null;
}
function original(h, r) {
  if (r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity) ||
      !Array.isArray(r.reads) || !r.reads.length || !r.before || !r.intended || !r.journalId)
    throw new h.Blocked('Original lifecycle admission actor, snapshots and command required; no replay');
}
async function snapshot(h, reads) {
  const values = {};
  for (const route of reads) values[route] = (await h.ok(h.admin, 'GET', route)).value;
  return values;
}
async function cleanup(h, r) {
  original(h, r);
  if (r.outcome === 'not-sent') return { proof: 'Lifecycle admission intent was not dispatched.' };
  if (!refusal(r.response, r.expected.code, r.expected.message) || !same(r.after, r.before))
    throw new h.Blocked('Original lifecycle command lacks exact stage refusal and unchanged snapshots; no replay');
  const current = await snapshot(h, r.reads);
  if (!same(current, r.before)) throw new h.Blocked('Original lifecycle owner state changed; retain intent for owner disposition');
  r.outcome = 'rejected-and-unchanged'; r.phase = 'deleted'; h.persist();
  return { proof: 'Original exact command refusal and independent owner readbacks preserve both installations, request, operation, allocation and execution budget; no lifecycle command replay.' };
}
async function probe(h, reads, route, intended, code, message) {
  const r = { kind: 'lifecycle-admission-probe', phase: 'intent', origin: h.admin.origin,
    actorIdentity: structuredClone(h.admin.identity), reads: [...reads], route, intended: structuredClone(intended),
    expected: { code, message }, journalId: crypto.randomBytes(16).toString('hex'), outcome: 'not-sent' };
  h.state.resources.push(r); h.persist();
  r.before = await snapshot(h, reads); h.persist();
  r.outcome = 'unknown'; h.persist(); r.response = await h.api(h.admin, 'POST', route, intended); h.persist();
  r.after = await snapshot(h, reads); h.persist();
  h.check('Original lifecycle command reaches exact intended identity/version fence: ' + message, refusal(r.response, code, message), r.response);
  h.check('Rejected lifecycle command preserves independent original resource identities, receipts, allocation and task attempts', same(r.before, r.after));
  await cleanup(h, r);
}
async function mismatches(h) {
  const f = await fixture(h);
  if (f.installations?.length !== 2 || f.deploymentRequests?.length !== 2) throw new h.Blocked('Original dual published delivery fixture required');
  const reads = f.installations.map(v => installations + v.id);
  for (const request of f.deploymentRequests) {
    reads.push(requests + request.id, operations + request.operationId);
  }
  const before = await snapshot(h, reads), first = before[reads[0]], peer = before[reads[1]];
  h.check('Positive original dual installations are ready with exact independent identities and allocated storage',
    first.status === 'ready' && peer.status === 'ready' && first.id !== peer.id && first.deploymentId !== peer.deploymentId &&
    first.receipt?.database?.bindingId > 0 && peer.receipt?.database?.bindingId > 0 && first.updateTime > 1 && peer.updateTime > 1);
  for (const instance of [first, peer]) {
    const body = { expectedDigest: instance.sourceDigest, expectedUpdateTime: instance.updateTime, reason: 'Reject stale original lifecycle identity' };
    await probe(h, reads, installations + instance.id + '/activate', { ...body, expectedDigest: 'sha256:' + '0'.repeat(64) }, 19, 'application installation digest does not match');
    await probe(h, reads, installations + instance.id + '/activate', { ...body, expectedUpdateTime: instance.updateTime - 1 }, 19, 'installation version changed; refresh before operating');
  }
  for (const saved of f.deploymentRequests) {
    const op = before[operations + saved.operationId];
    h.check('Original successful task binds precise installation and persistent execution identity', op.status === 'succeeded' && op.requestId === saved.id && op.attempt > 0 && op.version > 1 &&
      f.installations.some(v => op.receiptRef === 'installation:' + v.id && op.deploymentId === v.deploymentId));
    await probe(h, reads, operations + op.id + '/retry', { expectedVersion: op.version - 1, reason: 'Reject stale exact original task recovery' }, 19, 'application deployment state version does not match');
  }
  h.check('All original installation and delivery owner facts remain unchanged after paired identity/version probes', same(await snapshot(h, reads), before));
}
mismatches.transport = 'owner-api';
module.exports = { handlers: { 'F034-002': mismatches }, refusal, cleanup, probe };
