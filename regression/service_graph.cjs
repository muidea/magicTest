// Product state remains behind Panel/CAS/Gateway public boundaries. The local
// HTTP server is only an external upstream fixture, never a product substitute.
const http = require('node:http');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const services = '/panel/hub/services/';
const publications = '/panel/hub/publications/';
const subscriptions = '/panel/hub/subscriptions/';
const absent = r => [200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
function originalOwner(h, identity) {
  const owner = [h.tenantAdmin, h.otherTenantAdmin, h.admin].find(actor => actor && same(actor.identity, identity));
  if (!owner) throw new h.Blocked('Exact original service graph owner session unavailable');
  return owner;
}
function track(h, r) { h.state.resources.push(r); h.persist(); return r; }
function controlledUpstream() {
  const held = new Map(), responses = new Map(), requests = [], server = http.createServer(async (req, res) => {
    const body = []; for await (const chunk of req) body.push(chunk);
    const url = new URL(req.url, 'http://fixture');
    const receipt = { method: req.method, path: url.pathname, marker: url.searchParams.get('marker'), body: Buffer.concat(body).toString(), authorizationPresent: !!req.headers.authorization,
      namespace: req.headers['x-mp-namespace'] || '', extDataPresent: !!req.headers['x-mp-entity-ext-data'], contentType: req.headers['content-type'] || '', query: Object.fromEntries(url.searchParams),
      authorityChallengePresent: !!req.headers['x-magic-gateway-authority-challenge'], authorityRejectedPresent: !!req.headers['x-magic-gateway-authority-rejected'] };
    requests.push(receipt);
    const gate = held.get(receipt.marker);
    if (gate) { gate.started(); await gate.wait; held.delete(receipt.marker); }
    res.setHeader('Content-Type', 'application/json');
    const response = responses.get(receipt.marker);
    if (response) {
      res.statusCode = response.status;
      if (response.proof) {
        res.setHeader('X-Magic-Gateway-Authority-Challenge', response.proof);
        res.setHeader('X-Magic-Gateway-Authority-Rejected', response.proof);
      }
    }
    res.end(JSON.stringify({ fixture: 'controlled-external-upstream', marker: receipt.marker, method: req.method, body: receipt.body }));
  });
  return { server, requests,
    respond(marker, response) {
      if (!/^[a-f0-9]{24}$/.test(marker) || responses.has(marker) || requests.some(r => r.marker === marker) ||
          !response || ![200, 401, 409].includes(response.status) || Object.keys(response).some(k => !['status', 'proof'].includes(k)) ||
          response.proof !== undefined && !/^[A-Za-z0-9_-]{43}$/.test(response.proof)) throw Error('Finite original upstream response plan required before dispatch');
      responses.set(marker, structuredClone(response));
    },
    releaseAll() { for (const gate of held.values()) gate.release(); },
    hold(marker) {
      if (held.has(marker)) throw new h.Blocked('Original upstream marker already held');
      const gate = {};
      gate.reached = new Promise(resolve => { gate.started = resolve; });
      gate.wait = new Promise(resolve => { gate.release = resolve; });
      held.set(marker, gate); return gate;
    } };
}
async function upstream(h) {
  if (h.serviceUpstream) return h.serviceUpstream;
  const networks = JSON.parse(execFileSync('docker', ['inspect', 'magicGateway', '--format', '{{json .NetworkSettings.Networks}}'], { encoding: 'utf8' }));
  const gateways = [...new Set(Object.values(networks).map(n => n.Gateway).filter(Boolean))];
  if (gateways.length !== 1) throw new h.Blocked('Controlled upstream requires one actual Gateway Docker bridge address');
  const up = controlledUpstream(), server = up.server;
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, gateways[0], resolve); });
  h.teardowns.push(async () => { up.releaseAll(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); });
  return h.serviceUpstream = { ...up, address: 'http://' + gateways[0] + ':' + server.address().port };
}
async function fixture(h, suffix, policy = {}, ownerName = 'tenantAdmin', contractSpec) {
  const owner = h[ownerName];
  if (!owner) throw new h.Blocked('Missing original service fixture owner ' + ownerName);
  const up = await upstream(h), key = h.state.prefix + '_' + suffix;
  const options = { contract: { version: '1', operations: [{ key: 'probe', name: 'Controlled probe', method: 'GET', upstreamPath: '/probe', parameters: [{ name: 'marker', in: 'query', required: true, schema: { type: 'string' } }], responseBody: { contentType: 'application/json', schema: { type: 'object' } } }] } };
  if (contractSpec) options.contract = structuredClone(contractSpec);
  const service = await h.createAs(ownerName, services, { key, name: key, showName: '正式服务回归 ' + key, catalog: 'regression', description: '本机受控上游夹具', providerType: 'external', status: 2, accessMode: 'gateway', address: up.address, options: JSON.stringify(options) }, 'service');
  const payload = { service: { id: service.id }, status: 1, visibleScope: owner.identity.namespace, allowSubscription: true, requireApproval: false, maxSubscriptions: 10, maxQPS: 0, dailyQuota: 0, ...policy };
  const publication = await h.createAs(ownerName, publications, payload, 'publication');
  const result = await h.ok(owner, 'PUT', '/panel/hub/publication/publish/' + publication.id, {});
  const current = (await h.ok(owner, 'GET', publications + publication.id)).value;
  h.check('Formal publication freezes exact original enabled service for current tenant', result.value.id === publication.id && current.status === 2 && current.service.id === service.id && current.visibleScope === owner.identity.namespace && current.publishedTime > 0, current);
  return { service, ownerIdentity: structuredClone(owner.identity), publication: current, payload: { ...payload, status: 2 }, up };
}
async function subscribe(h, f, actor = h.user) {
  const owner = originalOwner(h, f.ownerIdentity || h.tenantAdmin.identity);
  const requestId = crypto.randomBytes(16).toString('hex');
  const r = track(h, { kind: 'service-graph-subscription', serviceId: f.service.id, collection: subscriptions, actorIdentity: structuredClone(actor.identity), actorOrigin: actor.origin, ownerIdentity: structuredClone(owner.identity), phase: 'intent', requestId, outcome: 'unknown' });
  r.response = await h.api(actor, 'POST', '/portal/service/subscriptions/', { requestId, service: f.service.id, leaseTerm: 1 }); h.persist();
  const receipt = await h.api(actor, 'GET', '/portal/service/subscription-requests/' + requestId + '?service=' + f.service.id);
  r.receipt = receipt; h.persist();
  if (!h.good(receipt) || receipt.data.value?.requestId !== requestId || receipt.data.value.phase !== 'complete') throw new h.Blocked('Original subscription request has no terminal owner receipt; do not replay');
  r.id = receipt.data.value.subscriptionId;
  if (receipt.data.value.errorCode !== 0 && !r.id) { r.outcome = 'rejected'; r.phase = 'deleted'; h.persist(); return { resource: r, response: r.response }; }
  h.check('Original subscription receipt confirms its exact accepted resource', receipt.data.value.errorCode === 0 && Number.isSafeInteger(r.id) && r.id > 0, receipt);
  const value = (await h.ok(owner, 'GET', subscriptions + r.id)).value;
  const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  h.check('Independent subscription owner matches original human, service and namespace', value.id === r.id && value.service.id === f.service.id && value.namespace === actor.identity.namespace && same(value.subscriberRef, { namespace: actor.identity.namespace, subject: 'account:' + session.account.id, accountId: session.account.id }), value);
  r.outcome = 'accepted'; r.phase = 'created'; r.original = value; h.persist();
  return { value, resource: r, response: r.response };
}
async function cleanupSubscription(h, r) {
  if (r.unsubscribe?.outcome === 'unknown') throw new h.Blocked('Original subscriber retirement remains unresolved; no subscription DELETE replay');
  if ((h.state?.resources || []).some(child => child.parentSubscriptionId === r.id && child.phase !== 'deleted' && child.endpointAuthorityCommands?.some(c => c.outcome === 'unknown'))) throw new h.Blocked('Original subscription Endpoint authority remains unresolved; retain its exact subscription');
  const owner = originalOwner(h, r.ownerIdentity);
  if ( r.receipt?.data?.value?.phase !== 'complete' || r.receipt.data.value.errorCode !== 0 || r.id !== r.receipt.data.value.subscriptionId || r.outcome !== 'accepted') throw new h.Blocked('Original subscription requires exact owner and completed original receipt before cleanup');
  const before = await h.api(owner, 'GET', subscriptions + r.id);
  if (absent(before)) return { proof: 'Exact acknowledged original subscription independently absent' };
  h.check('Cleanup reads exact subscription with unchanged original service and subject', h.good(before) && before.data.value.id === r.id && before.data.value.service.id === r.serviceId && same(before.data.value.subscriberRef, r.original.subscriberRef), before);
  if (r.deletion) throw new h.Blocked('Original subscription DELETE unresolved; never replay');
  r.deletion = { outcome: 'unknown' }; h.persist();
  r.deletion.response = await h.api(owner, 'DELETE', subscriptions + r.id); r.deletion.outcome = h.good(r.deletion.response) ? 'accepted' : 'unconfirmed'; h.persist();
  h.check('Owner acknowledges exact original subscription retirement', r.deletion.outcome === 'accepted', r.deletion.response);
  h.check('Independent owner read confirms original subscription absent', absent(await h.api(owner, 'GET', subscriptions + r.id)));
  return { proof: 'Original request receipt, exact owner DELETE and independent absence' };
}
async function retire(h, s) { const proof = await cleanupSubscription(h, s.resource); s.resource.phase = 'deleted'; h.persist(); return proof; }
async function credential(h, s, suffix = 'service-key') {
  const owner = originalOwner(h, s.resource.ownerIdentity);
  const r = track(h, { kind: 'service-graph-credential', serviceId: s.value.service.id, parentSubscriptionId: s.value.id, collection: '/panel/hub/subscription/credentials/', ownerIdentity: structuredClone(owner.identity), actorIdentity: structuredClone(owner.identity), name: h.state.prefix + '-' + suffix, phase: 'intent', outcome: 'unknown' });
  const result = await h.api(owner, 'POST', r.collection, { subscription: s.value.id, name: r.name });
  r.response = result; h.persist();
  h.check('Formal subscription credential returns a one-time API Key', h.good(result) && typeof result.data.apiKey === 'string' && result.data.apiKey.length > 0 && result.data.value?.name === r.name, { status: result.status, error: result.data?.error, value: result.data?.value });
  r.value = result.data.value; r.outcome = 'accepted'; r.phase = 'created'; h.persist();
  const rows = await credentialRows(h, r.collection, s.value.id, owner);
  h.check('Independent non-secret credential directory contains exact issued identity', rows.some(x => x.name === r.name && x.clientId === r.value.clientId && x.credentialId === r.value.credentialId) && !JSON.stringify(rows).includes(result.data.apiKey), rows);
  return { resource: r, apiKey: result.data.apiKey, value: r.value };
}
async function rotate(h, previous) {
  const old = previous.resource, owner = originalOwner(h, old.ownerIdentity);
  if (old.outcome !== 'accepted' || old.phase !== 'created' || old.rotation) throw new h.Blocked('Rotation requires exact original active credential and no unresolved rotation');
  const intended = { name: old.name, replacementName: h.state.prefix + '-replacement', retirePreviousAt: Date.now() + 4000 };
  const r = track(h, { kind: old.kind, serviceId: old.serviceId, parentSubscriptionId: old.parentSubscriptionId, collection: old.collection,
    ownerIdentity: structuredClone(old.ownerIdentity), actorIdentity: structuredClone(old.actorIdentity), name: old.name, phase: 'intent', outcome: 'unknown', rotationIntent: intended });
  old.rotation = { outcome: 'unknown', previousCredentialId: old.value.credentialId, intended }; h.persist();
  const result = await h.api(owner, 'POST', old.collection + old.parentSubscriptionId + '/rotate', intended);
  r.response = result; old.rotation.response = result; h.persist();
  h.check('Formal rotation returns a new secret on the exact original subscription client and Endpoint', h.good(result) && typeof result.data.apiKey === 'string' && result.data.value?.clientId === old.value.clientId && result.data.value.endpointId === old.value.endpointId && result.data.value.name === old.name && result.data.value.credentialId !== old.value.credentialId, { status: result.status, error: result.data?.error, value: result.data?.value });
  r.value = result.data.value; r.outcome = 'accepted'; r.phase = 'created'; old.rotation.outcome = 'acknowledged'; h.persist();
  const rows = await credentialRows(h, r.collection, r.parentSubscriptionId, owner);
  h.check('Independent subscription directory confirms exact replacement metadata without full key', rows.some(row => row.clientId === r.value.clientId && row.credentialId === r.value.credentialId && row.name === old.name) && !JSON.stringify(rows).includes(result.data.apiKey), rows);
  return { resource: r, apiKey: result.data.apiKey, value: r.value, retirePreviousAt: intended.retirePreviousAt };
}
async function retireCredential(h, c) { const proof = await cleanupCredential(h, c.resource); c.resource.phase = 'deleted'; h.persist(); return proof; }
async function credentialRows(h, collection, subscriptionId, owner = h.tenantAdmin) {
  const result = await h.ok(owner, 'GET', collection + '?id=' + subscriptionId + '&_pageSize=100&_pageNum=1');
  const rows = result.values === null && result.pagination?.total === 0 ? [] : result.values;
  if (!Array.isArray(rows) || result.pagination?.total !== rows.length || result.pagination?.hasMore === true) throw new h.Blocked('Credential owner directory is incomplete; do not infer retirement');
  return rows;
}
async function cleanupCredential(h, r) {
  if ((h.state?.resources || []).some(parent => parent.kind === 'service-graph-subscription' && parent.id === r.parentSubscriptionId && parent.unsubscribe?.outcome === 'unknown')) throw new h.Blocked('Original subscriber retirement remains unresolved; retain its original credential');
  if (r.endpointAuthorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original credential Endpoint authority remains unresolved; no retirement');
  const owner = originalOwner(h, r.ownerIdentity);
  if ( r.outcome !== 'accepted' || !r.value?.clientId) throw new h.Blocked('Credential cleanup needs exact acknowledged original identity');
  let rows = await credentialRows(h, r.collection, r.parentSubscriptionId, owner);
  let current = rows.find(x => x.name === r.name);
  if (current?.status === 2) {
    if (r.deletion) throw new h.Blocked('Original service credential retirement unresolved; do not replay');
    r.deletion = { outcome: 'unknown' }; h.persist();
    r.deletion.response = await h.api(owner, 'DELETE', r.collection + r.parentSubscriptionId + '?name=' + encodeURIComponent(r.name));
    r.deletion.outcome = h.good(r.deletion.response) ? 'accepted' : 'unconfirmed'; h.persist();
    h.check('Owner acknowledges original credential retirement', r.deletion.outcome === 'accepted', r.deletion.response);
    rows = await credentialRows(h, r.collection, r.parentSubscriptionId, owner); current = rows.find(x => x.name === r.name);
  }
  h.check('Subscription credential cannot remain active after retirement', !current || current.status !== 2, current);
  const cas = await h.api(owner, 'GET', '/cas/namespaces/' + owner.identity.namespace + '/oauth/clients/' + encodeURIComponent(r.value.clientId));
  h.check('Independent CAS owner confirms original client retired or disabled', absent(cas) || h.good(cas) && cas.data.value.clientId === r.value.clientId && cas.data.value.status !== 2, cas);
  return { proof: 'Formal credential retirement plus independent subscription/CAS reads' };
}
async function call(h, actor, f, key, scheme = 'ApiKey') {
  if (!['ApiKey', 'Bearer'].includes(scheme)) throw new h.Blocked('Unsupported explicit service credential scheme');
  const marker = crypto.randomBytes(12).toString('hex'), route = '/api/v1/gateway/services/' + f.service.key + '/probe?marker=' + marker;
  const result = await actor.page.evaluate(async ({ route, key, scheme }) => {
    const r = await fetch(route, { credentials: 'omit', headers: key ? { Authorization: scheme + ' ' + key } : {}, signal: AbortSignal.timeout(15000) });
    const text = await r.text(); let data; try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 300) }; }
    return { status: r.status, data };
  }, { route, key, scheme });
  h.observe({ kind: 'public-service-call', origin: actor.origin, route, credentials: 'explicit original ' + scheme + ' only; browser cookies omitted', response: result });
  return { ...result, marker };
}
async function succeeds(h, actor, f, c) {
  const result = await call(h, actor, f, c.apiKey, c.scheme), received = f.up.requests.filter(x => x.marker === result.marker);
  h.check('Real Gateway invokes controlled upstream exactly once with the original request marker', result.status === 200 && result.data.marker === result.marker && received.length === 1 && received[0].method === 'GET' && received[0].path === '/probe' && !received[0].authorizationPresent, { response: result, upstream: received });
}
module.exports = { fixture, subscribe, credential, rotate, retireCredential, credentialRows, cleanupSubscription, cleanupCredential, retire, call, succeeds, services, publications, subscriptions, controlledUpstream };
