// The private journal records intent before a command. A local journal ID is
// not a server idempotency key or proof that an unknown write did not commit.
const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const absent = response => [200, 404].includes(response.status) && response.data?.error?.code === 2 && response.data.value == null;
const validID = value => Number.isSafeInteger(value) && value > 0;
const ownerRequest = (h, ...args) => (h.ownerApi || h.api)(...args);
function originalActor(h, actor, r) {
  if (!same(actor?.identity, r.creation.actorIdentity) || actor?.origin !== r.creation.origin) throw new h.Blocked('Tracked resource requires its original actor and origin');
}
function readRoute(r) { return r.kind === 'namespace' ? '/cas/namespaces/' + r.id : r.collection + r.id; }
const identityKey = intended => ['uuid', 'key', 'account', 'name'].find(key => typeof intended[key] === 'string' && intended[key]);
function acknowledgedCreation(h, r) {
  if (require('./cleanup_recovery.cjs').recoveredNamespace(r)) return true;
  const response = r.creation.response, key = identityKey(r.creation.intended);
  return r.creation.outcome === 'accepted' && response && h.good(response) && validID(r.id) && response.data.value?.id === r.id && (!key || response.data.value[key] === r.creation.intended[key]);
}
async function createResource(h, actor, actorName, collection, intended, kind) {
  if (!actor?.identity || !actor.origin || !collection.startsWith('/') || collection.startsWith('//') || !collection.endsWith('/') || /[?#]/.test(collection)) throw new h.Blocked('Creation requires an original actor and exact owner collection');
  const key = identityKey(intended);
  // Publications and other relation-owned records have no display identity;
  // their full submitted DTO is the identity of the local intent.
  const identity = key ? { [key]: intended[key] } : structuredClone(intended);
  if (h.state.resources.some(r => r.phase !== 'deleted' && r.collection === collection && r.creation && same(r.creation.actorIdentity, actor.identity) && r.creation.origin === actor.origin && same(r.creation.identity, identity))) throw new h.Blocked('Original creation remains open; query the owner operation, never replay POST');
  const r = { collection, kind, ...(actorName !== 'admin' ? { actor: actorName } : {}), name: intended.name || intended.account || intended.key,
    phase: 'intent', creation: { journalId: crypto.randomBytes(16).toString('hex'), actorIdentity: structuredClone(actor.identity), origin: actor.origin, identity, intended: structuredClone(intended), outcome: 'not-sent' } };
  h.state.resources.push(r); h.persist();
  r.creation.outcome = 'unknown'; h.persist();
  const response = await ownerRequest(h, actor, 'POST', collection, intended);
  r.creation.response = response;
  const value = response.data?.value;
  r.creation.outcome = h.good(response) ? 'accepted' : 'unconfirmed';
  if (h.good(response) && validID(value?.id)) { r.id = value.id; r.phase = 'created'; }
  h.persist(); // Persist returned identity even if the following assertion fails.
  h.check('Creation acknowledged the exact submitted identity', h.good(response) && validID(r.id) && (!key || value[key] === intended[key]), response);
  originalActor(h, actor, r);
  const ownerRead = await ownerRequest(h, actor, 'GET', readRoute(r));
  h.check('Independent owner read succeeds', h.good(ownerRead), ownerRead);
  const current = ownerRead.data.value;
  originalActor(h, actor, r);
  h.check('Independent owner read confirms the original created identity', current?.id === r.id && (!key || current[key] === intended[key]), current);
  r.creation.ownershipConfirmed = true; h.persist();
  return value;
}
async function deleteResource(h, actor, r) {
  originalActor(h, actor, r);
  // A failed first GET does not make an acknowledged exact creation unknown.
  // Re-read that original identity, including after a journal reload; neither
  // the local phase nor a matching directory name authorizes a guessed DELETE.
  if (!acknowledgedCreation(h, r)) throw new h.Blocked('Unconfirmed original creation; retain intent without guessed deletion');
  const route = readRoute(r), current = await ownerRequest(h, actor, 'GET', route);
  originalActor(h, actor, r);
  if (absent(current)) return { proof: 'Acknowledged exact original created identity independently absent' };
  h.check('Deletion reads the exact original owner resource', h.good(current) && current.data.value?.id === r.id, current);
  if (!r.creation.ownershipConfirmed) {
    const key = identityKey(r.creation.intended);
    h.check('Recovery confirms the original submitted identity', !key || current.data.value[key] === r.creation.intended[key], current);
    r.creation.ownershipConfirmed = true; h.persist();
  }
  if (r.deletion) throw new h.Blocked('Original DELETE result remains open; no command replay without an owner receipt');
  r.deletion = { journalId: crypto.randomBytes(16).toString('hex'), outcome: 'unknown' }; h.persist();
  const response = await ownerRequest(h, actor, 'DELETE', r.collection + r.id);
  r.deletion.response = response; r.deletion.outcome = h.good(response) ? 'acknowledged' : 'unconfirmed'; h.persist();
  h.check('Original DELETE is acknowledged', h.good(response), response);
  const after = await ownerRequest(h, actor, 'GET', route);
  originalActor(h, actor, r);
  h.check('Original owner independently confirms deletion', absent(after), after);
  return { proof: 'Original creation, journaled DELETE and independent exact owner absence' };
}
function guardFixtureAccountCleanup(h, r) {
  if (r.kind !== 'account') return;
  const namespace = /^\/cas\/namespaces\/([^/]+)\/accounts\/$/.exec(r.collection)?.[1];
  const account = r.creation?.intended?.account;
  if (namespace && account && h.state.resources.some(child => child !== r && child.phase !== 'deleted' && child.creation?.actorIdentity?.namespace === namespace && child.creation.actorIdentity.account === account)) throw new h.Blocked('Original account still owns unresolved created resources; retain its identity for formal cleanup');
  if (namespace && account && h.state.resources.some(child => child !== r && child.phase !== 'deleted' && ['ordinary-file', 'feedback-ticket'].includes(child.kind) && child.actorIdentity?.namespace === namespace && child.actorIdentity.account === account)) throw new h.Blocked('Original account owns an unresolved file or feedback; retain creator for formal recovery and cleanup');
}
module.exports = { createResource, deleteResource, guardFixtureAccountCleanup };
