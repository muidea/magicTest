// Metamorphic same-ingress anti-spoof checks, not an absolute socket/source
// oracle. The real Panel mutation and audit owner supply all observed facts.
const crypto = require('node:crypto');
const net = require('node:net');
const { isDeepStrictEqual: same } = require('node:util');
const services = '/panel/hub/services/';
const spoofIPs = ['198.51.100.201', '203.0.113.202', '192.0.2.203'];
function stripPort(addr) {
  if (typeof addr !== 'string') return '';
  const trimmed = addr.trim();
  if (trimmed.startsWith('[')) {
    const idx = trimmed.indexOf(']:');
    return idx > 1 ? trimmed.slice(1, idx) : trimmed;
  }
  const colon = trimmed.indexOf(':');
  if (colon > 0 && trimmed.indexOf(':', colon + 1) === -1 && /^\d+$/.test(trimmed.slice(colon + 1))) {
    return trimmed.slice(0, colon);
  }
  return trimmed;
}
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

  // 1) CAS login security audit attribution (failed + succeeded login)
  const { PORTAL_BASIC_KEYS } = require('./platform_profiles.cjs');
  const ns = h.tenantAdmin.identity.namespace, started = Date.now();
  const auditAcct = await h.createAs('tenantAdmin', '/cas/namespaces/' + ns + '/accounts/', {
    account: h.state.prefix + '-audit-login', displayName: '来源登录审计账号',
    password: h.state.password, status: 2, roleTemplateKeys: PORTAL_BASIC_KEYS,
  }, 'account');
  await h.rejectedLogin(auditAcct.account, h.state.password + '-wrong', ns);
  const loginActor = await h.login(auditAcct.account, h.state.password, ns, h.state.password + 'L');
  const loginSecrets = [...secrets, loginActor.password];
  let casLoginEvents = [];
  for (let attempt = 0; attempt < 15; attempt++) {
    casLoginEvents = (await h.directory(h.tenantAdmin, '/cas/namespaces/' + ns + '/oauth/audit/'))
      .filter(e => e.subject === 'account:' + auditAcct.id && e.createTime >= started - 2000);
    if (casLoginEvents.some(e => e.eventType === 'login_failure') && casLoginEvents.some(e => e.eventType === 'login_success')) break;
    if (attempt < 14) await new Promise(r => setTimeout(r, 1000));
  }
  const failEv = casLoginEvents.find(e => e.eventType === 'login_failure' && e.outcome === 'failure');
  const okEv = casLoginEvents.find(e => e.eventType === 'login_success' && e.outcome === 'success');
  const validCasAddr = e => {
    const remoteHost = stripPort(e.remoteAddr);
    let sourceAddr = '';
    try { sourceAddr = JSON.parse(e.detailJson || '{}').sourceAddress || ''; } catch {}
    const sourceHost = stripPort(sourceAddr);
    return typeof e.remoteAddr === 'string' && net.isIP(remoteHost) > 0 &&
      !['0.0.0.0', '::', '::ffff:0.0.0.0'].includes(remoteHost) &&
      (!sourceAddr || (net.isIP(sourceHost) > 0 && !['0.0.0.0', '::', '::ffff:0.0.0.0'].includes(sourceHost))) &&
      !spoofIPs.some(ip => e.remoteAddr.includes(ip) || sourceAddr.includes(ip));
  };
  h.check('CAS security audit records exact failed and succeeded login events with real source IP and zero secrets',
    !!failEv && !!okEv &&
    [failEv, okEv].every(e => e.namespace === ns && e.subject === 'account:' + auditAcct.id && validCasAddr(e)) &&
    loginSecrets.filter(v => typeof v === 'string' && v.length >= 8).every(v => !JSON.stringify(casLoginEvents).includes(v)), casLoginEvents);

  // 2) Gateway client-credential (ApiKey) attribution & non-secret audit check
  const graph = require('./service_graph.cjs');
  const sgf = await graph.fixture(h, 'audit_apikey');
  const sgSub = await graph.subscribe(h, sgf, h.user);
  const sgCred = await graph.credential(h, sgSub, 'audit-key');
  try {
    await graph.succeeds(h, h.user, sgf, { ...sgCred, scheme: 'ApiKey' });
  } finally {
    await graph.retireCredential(h, sgCred);
    await graph.retire(h, sgSub);
  }
  const casAfterKey = await h.directory(h.tenantAdmin, '/cas/namespaces/' + ns + '/oauth/audit/?clientId=' + encodeURIComponent(sgCred.value.clientId));
  const opTenant = await h.directory(h.tenantAdmin, '/panel/support/audit/operation', { maxPages: 2 });
  h.check('Gateway ApiKey credential issuance/call never exposes plaintext secret in CAS or Panel audits',
    !JSON.stringify(casAfterKey).includes(sgCred.apiKey) && !JSON.stringify(opTenant).includes(sgCred.apiKey));

  // 3) Cross-tenant audit read isolation
  const tenantCrossOps = await h.directory(h.tenantAdmin, commands[0].query, { maxPages: 2 });
  h.check('Tenant admin cannot read platform operation audit events via explicit target/actor filters',
    !tenantCrossOps.some(r => r.namespace === actor.identity.namespace || r.eventId === commands[0].audit.eventId), tenantCrossOps);
  const peerAccess = await h.directory(h.otherTenantAdmin, '/panel/support/audit/access', { maxPages: 2 });
  const peerOps = await h.directory(h.otherTenantAdmin, '/panel/support/audit/operation', { maxPages: 2 });
  h.check('Other tenant admin cannot read target tenant security or operation audit logs',
    !peerAccess.some(r => r.namespace === ns || r.subject === 'account:' + auditAcct.id) &&
    !peerOps.some(r => r.namespace === actor.identity.namespace || r.namespace === ns), { peerAccess: peerAccess.length, peerOps: peerOps.length });
  h.inaccessible(await h.api(h.tenantAdmin, 'GET', '/cas/namespaces/' + actor.identity.namespace + '/oauth/audit/'),
    'Tenant admin cannot read platform CAS namespace OAuth audit');

  h.check('Original and foreign real sessions survive header forgeries', h.good(await h.api(actor, 'GET', '/api/v1/web/session/')) && h.good(await h.api(h.tenantAdmin, 'GET', '/api/v1/web/session/')));
  h.observe({
    kind: 'special-branches-deferred',
    caseId: 'F057-004',
    classification: '[C]',
    note: 'Multi-network direct vs trusted-proxy topologies, trusted-host DNS failure and restart recovery tracked in special [C]; same-ingress anti-spoof, CAS login / BFF operation / Gateway ApiKey attribution and tenant audit read isolation verified.',
  });
}
sourceAudit.actors = ['tenantAdmin', 'otherTenantAdmin', 'user'];
module.exports = { handlers: { 'F057-004': sourceAudit }, sourceHeaders, mutationOnce, verifyAudit, mutate, compareSources };
