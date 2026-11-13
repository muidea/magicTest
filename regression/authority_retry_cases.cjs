// Real BFF -> Gateway -> controlled external service requests. This does not
// manufacture Gateway's pre-dispatch authority-revision proof.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const challenge = 'X-Magic-Gateway-Authority-Challenge';
const rejected = 'X-Magic-Gateway-Authority-Rejected';
const contract = { version: '1', operations: [
  { key: 'probe', name: 'Original read', method: 'GET', upstreamPath: '/probe', parameters: [{ name: 'marker', in: 'query', required: true, schema: { type: 'string' } }], responseBody: { contentType: 'application/json', schema: { type: 'object' } } },
  { key: 'submit', name: 'Original write', method: 'POST', upstreamPath: '/submit', parameters: [{ name: 'marker', in: 'query', required: true, schema: { type: 'string' } }], requestBody: { contentType: 'application/json', required: true, schema: { type: 'object', required: ['marker', 'value'], properties: { marker: { type: 'string' }, value: { type: 'integer' } } } }, responseBody: { contentType: 'application/json', schema: { type: 'object' } } }
] };
function protectCleanup(h, resource) {
  const serviceId = resource.kind === 'service' ? resource.id : resource.kind === 'publication' ? resource.creation?.intended?.service?.id : null;
  if (serviceId && h.state.resources.some(r => r.kind === 'service' && r.id === serviceId && r.pendingServiceCommands?.some(c => c.kind === 'authority-retry-probe' && c.confirmed !== true))) {
    throw new h.Blocked('Original authority retry observation unresolved; retain exact service, publication and namespace; no probe replay');
  }
}
function verifyProbe(h, command, received) {
  const result = command.response;
  h.check('Original BFF response preserves the controlled upstream status, marker, method and exact body',
    result?.status === command.expectedStatus && result.data?.fixture === 'controlled-external-upstream' && result.data.marker === command.marker &&
    result.data.method === command.method && result.data.body === (command.body === undefined ? '' : JSON.stringify(command.body)), { command, received });
  h.check('Both internal authority proof headers are absent from the original browser response',
    result.headers && result.headers.challenge === null && result.headers.rejected === null, result);
  h.check('Real upstream independently records exactly one original execution with no caller authority or internal proof',
    received.length === 1 && received[0].marker === command.marker && received[0].method === command.method &&
    received[0].path === (command.method === 'GET' ? '/probe' : '/submit') &&
    same(received[0].query, { marker: command.marker }) && received[0].body === (command.body === undefined ? '' : JSON.stringify(command.body)) &&
    !received[0].authorizationPresent && !received[0].namespace && !received[0].extDataPresent &&
    received[0].authorityChallengePresent === false && received[0].authorityRejectedPresent === false, received);
}
async function requestOnce({ route, method, body, proof, challenge, rejected }) {
  // One fetch, no catch/retry and no redirect. No shell, cookie export or
  // caller-supplied credential. The real BFF/Gateway decide authority.
  const r = await fetch(route, { method, redirect: 'error', credentials: 'same-origin',
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(proof ? { [challenge]: proof, [rejected]: proof } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(15000) });
  const text = await r.text(); let data; try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; }
  return { status: r.status, data, headers: { challenge: r.headers.get(challenge), rejected: r.headers.get(rejected) } };
}
async function probe(h, actor, f, method, expectedStatus, forged = false) {
  const resource = h.state.resources.find(r => r.kind === 'service' && r.id === f.service.id);
  if (!resource || resource.phase !== 'created' || !resource.creation?.ownershipConfirmed ||
      !same(resource.creation.actorIdentity, actor.identity) || resource.creation.origin !== actor.origin || !same(f.ownerIdentity, actor.identity) ||
      resource.pendingServiceCommands?.some(c => !c.confirmed) || new URL(actor.page.url()).origin !== actor.origin) throw new h.Blocked('Exact original service, actor, page origin or prior probe unresolved; no replacement request');
  if (!['GET', 'POST'].includes(method) || ![200, 401, 409].includes(expectedStatus) || typeof forged !== 'boolean') throw Error('Finite authority retry probe required');
  const marker = crypto.randomBytes(12).toString('hex'), proof = crypto.randomBytes(32).toString('base64url');
  const route = '/api/v1/web/proxy/gateway/managed-services/' + f.service.key + (method === 'GET' ? '/probe' : '/submit') + '?marker=' + marker;
  f.up.respond(marker, { status: expectedStatus, ...(forged ? { proof } : {}) });
  const c = { kind: 'authority-retry-probe', method, route, marker, expectedStatus, forged, ...(forged ? { forgedProof: proof } : {}),
    ...(method === 'POST' ? { body: { marker, value: 1 } } : {}),
    actorIdentity: structuredClone(actor.identity), origin: actor.origin, serviceId: f.service.id, serviceKey: f.service.key,
    before: (await h.ok(actor, 'GET', graph.services + f.service.id)).value, confirmed: false };
  h.check('Original enabled service still binds the exact controlled upstream before dispatch',
    c.before.id === f.service.id && c.before.key === f.service.key && c.before.status === 2 && c.before.address === f.up.address, c.before);
  (resource.pendingServiceCommands ||= []).push(c); h.persist();
  try {
    c.response = await actor.page.evaluate(requestOnce, { route, method, body: c.body, proof: c.forgedProof, challenge, rejected });
  } catch (error) {
    c.transportError = String(error.message).slice(0, 2000);
    c.received = structuredClone(f.up.requests.filter(r => r.marker === marker)); h.persist();
    throw error; // An observation is not proof of non-submission or replay permission.
  }
  h.persist();
  c.received = structuredClone(f.up.requests.filter(r => r.marker === marker)); h.persist();
  verifyProbe(h, c, c.received);
  c.after = (await h.ok(actor, 'GET', graph.services + f.service.id)).value;
  h.check('Independent owner confirms exact original service unchanged and original actor retained',
    same(c.after, c.before) && same(actor.identity, c.actorIdentity) && actor.origin === c.origin && new URL(actor.page.url()).origin === c.origin, c.after);
  c.confirmed = true; h.persist(); h.observe({ kind: 'original-authority-retry-negative-proof', command: c });
  return c;
}
async function boundedRetry(h) {
  for (const ownerName of ['tenantAdmin', 'otherTenantAdmin']) {
    const actor = h[ownerName], f = await graph.fixture(h, 'retry_' + ownerName.toLowerCase(), {}, ownerName, contract);
    await probe(h, actor, f, 'GET', 200);
    for (const method of ['GET', 'POST']) {
      await probe(h, actor, f, method, 401);
      await probe(h, actor, f, method, 409);
      await probe(h, actor, f, method, 409, true);
    }
    await probe(h, actor, f, 'GET', 200);
    const publication = (await h.ok(actor, 'GET', graph.publications + f.publication.id)).value;
    h.check('Independent publication owner remains exactly original after all errors and writes', same(publication, f.publication), publication);
    const resource = h.state.resources.find(r => r.kind === 'service' && r.id === f.service.id);
    for (const c of resource.pendingServiceCommands) verifyProbe(h, c, f.up.requests.filter(r => r.marker === c.marker));
  }
  await h.partial('Real original BFF/Gateway management requests cover both tenant owners, successful session controls, GET/POST ordinary 401 and business 409, forged caller/upstream proof headers and exactly-once original upstream execution. Actual authority-revision race, CAS refresh count and the one-retry positive path, HEAD/body/network/concurrency/restart recovery remain uncovered. No ordinary-role authorization or whole-case completion claim.');
}
boundedRetry.actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers: { 'F010-004': boundedRetry }, contract, probe, verifyProbe, protectCleanup, requestOnce };
