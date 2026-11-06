const { isDeepStrictEqual: same } = require('node:util');
const collection = '/panel/hub/services/';
function externalService(prefix, suffix) {
  const address = 'https://regression.invalid/api';
  return { key: prefix + '_' + suffix, name: prefix + '_' + suffix, showName: '回归服务身份', description: '仅验证元数据，不调用上游', catalog: 'regression', providerType: 'external', providerKey: '', status: 2, accessMode: 'gateway', address,
    options: JSON.stringify({ debug: { authMode: 'bearer', operations: [{ key: 'probe', name: 'probe', method: 'GET', pathTemplate: address + '/probe', parameters: [] }] } }) };
}
async function serviceIdentity(h) {
  const actor = h.tenantAdmin;
  const original = await h.createAs('tenantAdmin', collection, externalService(h.state.prefix, 'identity'), 'service');
  const peer = await h.createAs('tenantAdmin', collection, externalService(h.state.prefix, 'peer'), 'service');
  const before = (await h.ok(actor, 'GET', collection + original.id)).value;
  const peerBefore = (await h.ok(actor, 'GET', collection + peer.id)).value;
  h.check('Identity test owns two different services in its exact tenant', before.id !== peerBefore.id && before.key !== peerBefore.key && before.namespace === actor.identity.namespace && peerBefore.namespace === actor.identity.namespace);
  const snapshots = [before, peerBefore];
  for (const mutation of [
    { method: 'POST', route: collection, body: { ...externalService(h.state.prefix, 'identity'), name: h.state.prefix + '_replacement', description: 'MUST NOT OVERWRITE' }, code: 7, diagnostic: /service key already exists/i },
    { method: 'PUT', route: collection + before.id, body: { expectedServiceVersion: before.updateTime, key: peerBefore.key, showName: 'MUST NOT OVERWRITE' }, code: 4, diagnostic: /service edit field is not writable: key/i }
  ]) {
    const priorRows = (await h.directory(actor, collection)).filter(r => snapshots.some(s => s.key === r.key));
    h.check('Complete directory contains only the two exact baseline identities', priorRows.length === 2 && snapshots.every(s => priorRows.some(r => same(r, s))), priorRows);
    const r = { kind: 'service-identity-attempt', collection, actor: 'tenantAdmin', actorIdentity: structuredClone(actor.identity), name: before.key, phase: 'intent', original: snapshots, intended: mutation, outcome: 'unknown' };
    h.state.resources.push(r); h.persist();
    const response = await h.api(actor, mutation.method, mutation.route, mutation.body);
    r.response = response; r.id = response.data?.value?.id; h.persist();
    const rows = (await h.directory(actor, collection)).filter(row => snapshots.some(s => s.key === row.key));
    const readbacks = [];
    for (const snapshot of snapshots) readbacks.push((await h.ok(actor, 'GET', collection + snapshot.id)).value);
    r.observed = { rows, readbacks }; h.persist();
    if (response.status === 401 || response.data?.error?.code === 11) throw new h.Blocked('AUTH-INVALID: service mutation did not reach identity validation');
    const rejected = [200, 400, 409, 422].includes(response.status) && response.data?.error?.code === mutation.code && mutation.diagnostic.test(response.data.error.message);
    const unchanged = rows.length === 2 && snapshots.every(s => rows.some(row => same(row, s))) && same(readbacks, snapshots);
    if (rejected && unchanged) { r.outcome = 'rejected-and-unchanged'; r.phase = 'deleted'; h.persist(); }
    h.check('Owner rejects service identity mutation at the declared validation stage', rejected, response);
    h.check('Independent owner reads preserve original and unrelated peer services', unchanged, r.observed);
  }
}
serviceIdentity.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F037-003': serviceIdentity } };
