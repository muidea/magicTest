// CAS owns access-update receipts; Panel owns ingress projection. Journal each
// exact conditional command before dispatch, and never replay an unknown write.
const { isDeepStrictEqual: same } = require('node:util');
const fields = value => ({ description: value.description, scope: value.scope || [], status: value.status, startTime: value.startTime, expireTime: value.expireTime });
function original(h, r) {
  if (r?.kind !== 'namespace' || !r.id || !same(h.admin?.identity, r.creation?.actorIdentity) || h.admin.origin !== r.creation.origin) throw new h.Blocked('Namespace availability requires exact original resource, actor and origin');
}
async function change(h, r, current, desired) {
  original(h, r);
  const journal = r.availability ||= { original: structuredClone(current), last: structuredClone(current), commands: [] };
  if (journal.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original namespace availability write remains unknown; query its owner receipt without replay');
  if (!same(current, journal.last) || current.id !== r.id || current.name !== r.name) throw new h.Blocked('Namespace owner revision differs from the exact last confirmed original snapshot');
  const c = { actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, body: { expectedVersion: current.updateTime, ...fields(desired) }, outcome: 'unknown' };
  journal.commands.push(c); h.persist();
  const response = await h.api(h.admin, 'PUT', r.collection + r.id, c.body);
  c.response = response; h.persist();
  if (!h.good(response)) throw new h.Blocked('Original namespace update has no accepted exact receipt; preserve its response without replay');
  const saved = response.data.value, receipt = response.data.operation;
  const after = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + r.id)).value;
  h.check('Formal availability receipt binds the exact original namespace and completed operation', saved?.id === r.id && saved.name === r.name && receipt?.namespaceId === r.id && receipt.name === r.name && receipt.phase === 'completed' && /^[a-f0-9]{32}$/.test(receipt.requestId || '') && receipt.version > 0 && same(receipt.namespace, saved) && saved.updateTime > current.updateTime && same(fields(saved), fields(desired)) && same(after, saved), response);
  c.outcome = 'confirmed'; journal.last = after; h.persist();
  return after;
}
async function restore(h, r) {
  original(h, r);
  const journal = r.availability;
  if (!journal) return;
  if (journal.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Unknown original namespace command blocks restore; never repeat the PUT');
  const current = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + r.id)).value;
  if (!same(current, journal.last)) throw new h.Blocked('Concurrent namespace revision prevents restoration; never overwrite another owner change');
  if (!same(fields(current), fields(journal.original))) await change(h, r, current, journal.original);
  const after = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + r.id)).value;
  h.check('Original namespace settings independently restored through its public owner', after.id === r.id && same(fields(after), fields(journal.original)));
  journal.restored = true; h.persist();
}
async function reconcileIngress(h, r) {
  original(h, r);
  const before = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + r.id)).value;
  const operation = (await h.ok(h.admin, 'GET', '/cas/namespace/access-updates/' + r.id)).value;
  h.check('Ingress recovery binds exact current original CAS terminal access receipt', before.id === r.id && before.name === r.name && operation.namespaceId === r.id && operation.name === r.name && operation.phase === 'completed' && /^[a-f0-9]{32}$/.test(operation.requestId || '') && same(operation.namespace, before));
  if (r.ingressRecovery) {
    if (r.ingressRecovery.outcome !== 'confirmed') throw new h.Blocked('Original ingress recovery remains unknown; no repeated command');
    h.check('Confirmed ingress recovery still has the exact original owner snapshot', same(r.ingressRecovery.before, before));
    return;
  }
  r.ingressRecovery = { before, operation, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' }; h.persist();
  const response = await h.api(h.admin, 'PUT', r.collection + r.id + '/ingress', {});
  r.ingressRecovery.response = response; h.persist();
  h.check('Formal ingress-only recovery acknowledges the unchanged original namespace', h.good(response) && same(response.data.value, before));
  const after = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + r.id)).value;
  h.check('Independent CAS owner confirms ingress recovery did not replay the namespace mutation', same(after, before));
  r.ingressRecovery.outcome = 'confirmed'; h.persist();
}
module.exports = { change, restore, reconcileIngress };
