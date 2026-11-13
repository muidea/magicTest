// Metamorphic same-ingress anti-spoof checks, not an absolute socket/source
// oracle. The real Panel mutation and audit owner supply all observed facts.
const crypto = require('node:crypto');
const net = require('node:net');
const { isDeepStrictEqual: same } = require('node:util');
const services = '/panel/hub/services/';
const spoofIPs = ['198.51.100.201', '203.0.113.202', '192.0.2.203'];
function sourceHeaders(variant, foreign) {
  if (!['control', 'single', 'chain'].includes(variant) || !foreign || !/^[A-Za-z0-9_-]{1,128}$/.test(foreign.namespace) || !/^account:[1-9][0-9]{0,18}$/.test(foreign.subject)) throw Error('Finite source probe variant and original foreign identity required');
  if (variant === 'control') return {};
  return { 'X-Forwarded-For': variant === 'single' ? spoofIPs[0] : spoofIPs.join(', '), 'X-Real-IP': spoofIPs[1],
    Forwarded: 'for=' + spoofIPs[2] + ';proto=https', 'X-Mp-Namespace': foreign.namespace, 'X-Namespace': foreign.namespace,
    'X-Mp-Entity-Ext-Data': JSON.stringify({ namespace: foreign.namespace, actorNamespace: foreign.namespace, actorSubject: foreign.subject }) };
}
async function mutationOnce({ origin, route, body, headers }) {
  if (location.origin !== origin || !/^\/api\/v1\/web\/proxy\/panel\/hub\/services\/[1-9][0-9]*$/.test(route)) throw Error('Original same-origin service mutation required');
  const r = await fetch(route, { method: 'PUT', credentials: 'same-origin', redirect: 'error',
    headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body), signal: AbortSignal.timeout(30000) });
  const text = await r.text(); let data;
  try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; }
  return { status: r.status, data };
}
function operationQuery(resource, actor, subject) {
  return '/panel/support/audit/operation?' + new URLSearchParams({ operationType: '更新服务', detailMessage: '服务ID:' + resource.id + '；标识:' + resource.creation.intended.key,
    actorNamespace: actor.identity.namespace, actorSubject: subject, targetNamespace: actor.identity.namespace });
}
function verifyAudit(h, c, rows, secrets = []) {
  h.check('Exact original service update has one new independent audit event', rows.length === 1, rows);
  const r = rows[0];
  h.check('Audit event retains original authenticated actor, home/target namespace, operation and resource identity',
    r.eventId && !c.beforeEventIds.includes(r.eventId) && r.operationType === '更新服务' && r.detailMessage === '服务ID:' + c.serviceId + '；标识:' + c.serviceKey &&
    r.outcome === 'succeeded' && r.actorNamespace === c.actorIdentity.namespace && r.actorSubject === c.subject &&
    r.targetNamespace === c.actorIdentity.namespace && r.namespace === c.actorIdentity.namespace && r.operationTime >= c.startedAt - 2000, rows);
  h.check('Observed source is a real non-placeholder IP and contains none of the caller spoof addresses',
    typeof r.address === 'string' && net.isIP(r.address) > 0 && !['0.0.0.0', '::', '::ffff:0.0.0.0'].includes(r.address) && !spoofIPs.some(ip => r.address.includes(ip)), rows);
  h.check('Exact observed audit event excludes known plaintext regression credentials',
    secrets.filter(v => typeof v === 'string' && v.length >= 8).every(v => !JSON.stringify(rows).includes(v)), rows);
  return r;
}
async function newEvents(h, observer, query, beforeEventIds) {
  let rows = [];
  for (let attempt = 0; attempt < 15; attempt++) {
    rows = (await h.directory(observer, query, { maxPages: 2 })).filter(r => !beforeEventIds.includes(r.eventId));
    if (rows.length) return rows;
    if (attempt < 14) await new Promise(resolve => setTimeout(resolve, 1000));
  }
  return rows; // Missing delivery is a failed assertion, never success.
}
async function mutate(h, actor, resource, subject, variant, foreign, secrets = []) {
  if (resource.kind !== 'service' || resource.collection !== services || resource.phase !== 'created' || !resource.creation?.ownershipConfirmed ||
      !same(resource.creation.actorIdentity, actor.identity) || resource.creation.origin !== actor.origin ||
      resource.pendingServiceCommands?.some(c => !c.confirmed) || new URL(actor.page.url()).origin !== actor.origin || !/^account:[1-9][0-9]{0,18}$/.test(subject)) throw new h.Blocked('Original audit resource, actor, origin or command unresolved; no replacement mutation');
  const headers = sourceHeaders(variant, foreign), route = services + resource.id, query = operationQuery(resource, actor, subject);
  const before = (await h.ok(actor, 'GET', route)).value;
  h.check('Exact original service is independently read before source probe', before.id === resource.id && before.key === resource.creation.intended.key, before);
  const initial = await h.directory(h.admin, query, { maxPages: 2 });
  h.check('Audit baseline contains unique owner event identities', initial.every(r => typeof r.eventId === 'string' && r.eventId) && new Set(initial.map(r => r.eventId)).size === initial.length, initial);
  const c = { kind: 'audit-source-mutation', actorIdentity: structuredClone(actor.identity), origin: actor.origin, subject, variant, foreign: structuredClone(foreign),
    serviceId: resource.id, serviceKey: before.key, method: 'PUT', route, headers, before,
    body: { expectedServiceVersion: before.updateTime, description: '来源审计 ' + crypto.randomBytes(12).toString('hex') },
    query, beforeEventIds: initial.map(r => r.eventId), startedAt: Date.now(), confirmed: false };
  (resource.pendingServiceCommands ||= []).push(c); h.persist();
  try { c.response = await actor.page.evaluate(mutationOnce, { origin: c.origin, route: '/api/v1/web/proxy' + route, body: c.body, headers }); }
  catch (error) { c.transportError = String(error.message).slice(0, 2000); h.persist(); throw error; }
  h.persist();
  c.after = (await h.ok(actor, 'GET', route)).value; h.persist();
  const { description: oldDescription, updateTime: oldTime, ...oldRest } = before;
  const { description: newDescription, updateTime: newTime, ...newRest } = c.after;
  h.check('Acknowledged original conditional write changes only description and owner revision',
    h.good(c.response) && c.response.data.value?.id === resource.id && c.response.data.value.key === before.key &&
    newDescription === c.body.description && newTime > oldTime && same(oldRest, newRest) &&
    same(actor.identity, c.actorIdentity) && actor.origin === c.origin && new URL(actor.page.url()).origin === c.origin, { before, after: c.after, response: c.response });
  c.auditRows = await newEvents(h, h.admin, query, c.beforeEventIds); h.persist();
  c.audit = verifyAudit(h, c, c.auditRows, secrets);
  c.confirmed = true; h.persist(); h.observe({ kind: 'original-source-header-audit', command: c });
  return c;
}
function compareSources(h, commands) {
  const controls = commands.filter(c => c.variant === 'control'), forgeries = commands.filter(c => c.variant !== 'control');
  h.check('Source comparison has three distinct controls bracketing two distinct forgeries',
    commands.length === 5 && same(commands.map(c => c.variant), ['control', 'single', 'control', 'chain', 'control']) &&
    commands.every(c => c.confirmed === true) && new Set(commands.map(c => c.audit.eventId)).size === 5 &&
    commands.every(c => same(c.actorIdentity, commands[0].actorIdentity) && c.origin === commands[0].origin && c.serviceId === commands[0].serviceId), commands);
  if (!controls.every(c => c.audit.address === controls[0].audit.address)) throw new h.Blocked('Control ingress source changed; attribution is unknown, no mutation replay or absolute source claim');
  h.check('Caller forwarding and identity headers cannot change the real same-ingress audit source', forgeries.every(c => c.audit.address === controls[0].audit.address), commands);
}
async function sourceAudit(h) {
  const actor = h.admin, self = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  const foreignSession = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
  const subject = 'account:' + self.account.id, foreign = { namespace: h.tenantAdmin.identity.namespace, subject: 'account:' + foreignSession.account.id };
  h.check('Forgery names an independently authenticated different real tenant', foreign.namespace !== actor.identity.namespace && Number.isSafeInteger(self.account.id) && self.account.id > 0 && Number.isSafeInteger(foreignSession.account.id) && foreignSession.account.id > 0);
  const created = [];
  for (const suffix of ['audit_source_primary', 'audit_source_peer']) {
    const key = h.state.prefix + '_' + suffix;
    const options = { contract: { version: '1', operations: [{ key: 'probe', name: 'Source metadata fixture', method: 'GET', upstreamPath: '/probe', responseBody: { contentType: 'application/json', schema: { type: 'object' } } }] } };
    const value = await h.createAs('admin', services, { key, name: key, showName: '来源审计 ' + suffix, catalog: 'regression', description: '来源控制', providerType: 'external', status: 2, accessMode: 'gateway', address: 'https://regression.invalid/api', options: JSON.stringify(options) }, 'service');
    created.push(h.state.resources.find(r => r.kind === 'service' && r.id === value.id));
  }
  const [resource, peer] = created, peerBefore = (await h.ok(actor, 'GET', services + peer.id)).value, commands = [];
  const secrets = [h.state.password, h.credentials.password, actor.password, h.tenantAdmin.password];
  for (const variant of ['control', 'single', 'control', 'chain', 'control']) {
    commands.push(await mutate(h, actor, resource, subject, variant, foreign, secrets));
    h.check('Independent peer service remains exactly unchanged after each original source probe', same((await h.ok(actor, 'GET', services + peer.id)).value, peerBefore));
  }
  compareSources(h, commands);
  const all = await h.directory(h.admin, commands[0].query, { maxPages: 2 });
  h.check('Complete exact owner query preserves each original independent event once', all.length === 5 && commands.every(c => all.filter(r => r.eventId === c.audit.eventId).length === 1), all);
  for (const c of commands) verifyAudit(h, c, all.filter(r => r.eventId === c.audit.eventId), secrets);
  h.check('Original and foreign real sessions survive header forgeries', h.good(await h.api(actor, 'GET', '/api/v1/web/session/')) && h.good(await h.api(h.tenantAdmin, 'GET', '/api/v1/web/session/')));
  await h.partial('Same-ingress platform/home operation-audit anti-spoof source and original-actor invariants only; real conditional writes, independent owner effects, peer preservation and exact audit events. Empirical controls are not an absolute source/socket oracle. Direct/trusted/invalid-forwarded chains, independent source networks, CAS login and Gateway security events, tenant audit read exposure and concurrency/restart recovery remain uncovered.');
}
sourceAudit.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F057-004': sourceAudit }, sourceHeaders, mutationOnce, verifyAudit, mutate, compareSources };
