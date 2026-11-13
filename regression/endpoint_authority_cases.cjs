// Only actual subscribed credentials are used. An issuing administrator's
// session is never forwarded to Gateway as the Endpoint's business authority.
const { request } = require('./playwright.cjs');
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const generated = require('./generated_service_cases.cjs');
const authority = require('./application_authority_cases.cjs');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const { endpointTemplates, currentRoleRefusal } = require('./service_contract_cases.cjs');
const base = '/cas/namespaces/panel/';
async function keyRead(origin, route, apiKey) {
  if (!/^https?:\/\//.test(origin) || !route.startsWith('/api/v1/gateway/services/') || route.startsWith('//') || typeof apiKey !== 'string' || !apiKey) throw Error('Exact public Gateway read and original ApiKey required');
  const url = new URL(route, origin);
  if (url.origin !== origin || url.hash || url.username || url.password || url.pathname + url.search !== route || !url.pathname.startsWith('/api/v1/gateway/services/')) throw Error('Gateway read must retain its original origin and public path');
  const connect = new URL(url);
  if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
  // A new empty API context sends neither browser cookies nor bearer tokens.
  const transport = await request.newContext({ ignoreHTTPSErrors: true });
  try {
    const response = await transport.get(connect.href, { headers: { Host: url.host, Authorization: 'ApiKey ' + apiKey }, maxRedirects: 0, maxRetries: 0, timeout: 15000 });
    return { status: response.status(), data: await response.json() };
  } finally { await transport.dispose(); }
}
function link(h, r, f, accountId) {
  r.scenarioDefinitionId = f.application.id;
  r.scenarioInstallationIds = f.installations.map(i => String(i.id));
  r.endpointScenarioAccountId = accountId;
  h.persist();
}
async function pair(h, member, credentials, status = 2) {
  if (![1, 2].includes(status)) throw Error('Exact CAS enabled/disabled lifecycle state required');
  const session = (await h.ok(member.actor, 'GET', '/api/v1/web/session/')).value;
  h.check('Original subscription human is the exact dedicated account', session.account?.id === member.value.id && session.homeNamespace === 'panel');
  h.check('Same-account test uses two independent original credential/Endpoint identities', credentials.length === 2 && credentials.every(c => c.resource.phase === 'created' && c.resource.outcome === 'accepted') &&
    credentials[0].value.endpointId > 0 && credentials[1].value.endpointId > 0 && credentials[0].value.endpointId !== credentials[1].value.endpointId &&
    credentials[0].value.clientId !== credentials[1].value.clientId && credentials[0].value.credentialId !== credentials[1].value.credentialId);
  const values = [];
  for (const c of credentials) {
    const endpoint = (await h.ok(h.admin, 'GET', base + 'endpoints/' + c.value.endpointId)).value;
    h.check('Independent CAS binds each Endpoint in its expected lifecycle state to the original subscriber account and gateway-read scope', endpoint.id === c.value.endpointId && endpoint.account?.id === member.value.id && endpoint.status === status && endpoint.scope === 'magicrunner.usage.gateway.read', endpoint);
    values.push(endpoint);
  }
  return values;
}
async function contraction(h, member, credentials, before) {
  const c = member.resource.authorityCommands?.at(-1), impact = c?.response?.data?.value?.affectedEndpoints;
  h.check('Original acknowledged account contraction names exactly both previously authorized Endpoints', c?.outcome === 'confirmed' && c.body.applicationScopes?.length === 1 && c.body.applicationScopes[0].applicationAccess.length === 0 &&
    Array.isArray(impact) && impact.length === 2 && credentials.every(v => impact.filter(i => i.id === v.value.endpointId).length === 1));
  const after = await pair(h, member, credentials, 1);
  for (const [i, v] of after.entries()) h.check('CAS contraction disables and advances the original Endpoint authority fence without replacing its account, scope or explicitly assigned read template',
    v.id === before[i].id && v.authorityRevision > before[i].authorityRevision && same(v.templateRefs, before[i].templateRefs) && same(v.effectiveRoles, before[i].effectiveRoles));
  const evidence = { authorityCommandIndex: member.resource.authorityCommands.length - 1, accountId: member.value.id, origin: member.actor.origin, before, after, outcome: 'confirmed' };
  (member.resource.ceilingContractions ||= []).push(evidence); h.persist(); return evidence;
}
async function read(h, member, credential, route, row, allowed, disabled) {
  const manager = await business.member(h, 'manager'), before = await business.record(h, manager, row);
  h.check('Independent ordinary owner reads the exact original row before machine dispatch', h.good(before) && String(before.data.value.id) === row.recordId);
  let endpoint;
  if (disabled) {
    if (allowed || disabled.outcome !== 'confirmed' || disabled.accountId !== member.value.id || disabled.origin !== member.actor.origin ||
        !member.resource?.ceilingContractions?.includes(disabled)) throw new h.Blocked('Original confirmed account-contraction proof required for inactive-key refusal');
    endpoint = (await h.ok(h.admin, 'GET', base + 'endpoints/' + credential.value.endpointId)).value;
    h.check('Independent original CAS confirms this exact subscriber Endpoint is disabled before its old credential probe', endpoint.id === credential.value.endpointId && endpoint.account?.id === member.value.id && endpoint.status === 1 &&
      disabled.after.some(e => e.id === endpoint.id && e.authorityRevision === endpoint.authorityRevision));
  }
  const identity = structuredClone(member.actor.identity), origin = member.actor.origin;
  const probe = { route, method: 'GET', origin, actorIdentity: identity, endpointId: credential.value.endpointId, credentialId: credential.value.credentialId, allowed, expectedGate: disabled ? 'confirmed-account-contraction' : 'current-role', outcome: 'unknown' };
  (credential.resource.authorityReadProbes ||= []).push(probe); h.persist();
  probe.response = await keyRead(origin, route, credential.apiKey); h.persist();
  h.check('Read response belongs to unchanged original caller context', origin === member.actor.origin && same(identity, member.actor.identity));
  h.check(allowed ? 'Original current-role Endpoint reads the complete original business row through real Gateway' : disabled ? 'Original key is precisely inactive after independent CAS contraction proof' : 'Original valid Key reaches the precise current-role gate after Endpoint role contraction',
    allowed ? h.good(probe.response) && same(probe.response.data.value, before.data.value) : disabled ? probe.response.status === 401 && probe.response.data?.error?.code === 5 && probe.response.data.error.message === 'API key is inactive or invalid' && probe.response.data.value == null : currentRoleRefusal(probe.response), probe.response);
  h.check('Machine authority probe preserves the complete independent owner row', same(await business.record(h, manager, row), before));
  if (disabled) h.check('Inactive original Key never reactivates or replaces its independently disabled Endpoint', same((await h.ok(h.admin, 'GET', base + 'endpoints/' + credential.value.endpointId)).value, endpoint));
  probe.outcome = 'confirmed'; h.persist();
}
async function endpoints(h) {
  const f = await fixture(h), manager = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, manager);
  const common = (await h.directory(h.admin, base + 'role-templates/')).filter(t => t.key === 'portal-basic-user' && t.systemManaged && t.status === 2 && t.subjectType === 'account');
  h.check('Dedicated subscriber uses the protected ordinary functional profile', common.length === 1 && common[0].roleRefs?.length > 0);
  const access = [{ applicationUuid: context.identity.deploymentId, accessLevel: 'viewer' }];
  const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-endpoint-ceiling', name: '独立机器账号上限', subjectType: 'account', status: 2, roleRefs: common[0].roleRefs, applicationAccess: access }, 'role-template');
  const m = await authority.account(h, 'endpoint-ceiling'); link(h, m.resource, f, m.value.id);
  await authority.assign(h, m, group, access);
  const template = await h.create(base + 'role-templates/', { key: h.state.prefix + '-endpoint-read', name: '独立Endpoint读取', subjectType: 'endpoint', status: 2, applicationAccess: [], roleRefs: [{ module: '/applications/' + context.identity.deploymentId, key: 'application-data-read' }] }, 'role-template');
  const rows = [], credentials = []; let primary;
  try {
    const row = await business.create(h, context, 'endpoint-ceiling'); rows.push(row);
    const all = await generated.snapshot(h), source = f.installations[0].receipt.runtimeApplicationUuid;
    const caps = all[generated.capabilities].filter(c => c.providerKey === source && c.providerType === 'application' && c.kind === 'get' && c.status === 1);
    h.check('Machine authority fixture selects one exact unoccupied installed GET capability', caps.length === 1 && !all[generated.bindings].some(b => b.capability?.id === caps[0].id));
    const service = generated.intent(h, h.state.prefix + '_endpoint_ceiling', [caps[0].id], source); link(h, service, f, m.value.id);
    await generated.converge(h, service, [caps[0].id], '机器当前角色回归');
    const publication = service.last.publications[0];
    await generated.mutation(h, service, 'PUT', generated.publications + publication.id, { service: { id: service.serviceId }, status: 1, visibleScope: 'panel', allowSubscription: true, requireApproval: false, maxSubscriptions: 2, maxQPS: 0, dailyQuota: 0 }, async (response, current) => {
      h.check('Formal machine fixture publication independently permits ordinary subscription', h.good(response) && current[generated.publications].some(p => p.id === publication.id && p.allowSubscription && !p.requireApproval));
    });
    await generated.publish(h, service);
    const subscription = await graph.subscribe(h, { service: service.last.service, publication: service.last.publications[0], ownerIdentity: structuredClone(h.admin.identity) }, m.actor);
    link(h, subscription.resource, f, m.value.id);
    for (const suffix of ['endpoint-first', 'endpoint-second']) {
      const c = await graph.credential(h, subscription, suffix); link(h, c.resource, f, m.value.id); credentials.push(c);
    }
    await pair(h, m, credentials);
    const contract = (await h.ok(m.actor, 'GET', '/portal/service/debug/' + service.serviceId)).value;
    h.check('Actual public metadata retains the selected exact installed GET operation', contract.operations?.length === 1 && contract.operations[0].key === caps[0].key && contract.operations[0].method === 'GET' && contract.operations[0].pathTemplate.includes('{id}') && contract.operations[0].pathTemplate.startsWith('/api/v1/gateway/services/' + service.key + '/'), contract);
    const route = contract.operations[0].pathTemplate.replace(/\{id\}/g, row.recordId);
    for (const c of credentials) await read(h, m, c, route, row, false);
    await endpointTemplates(h, credentials[0], [template.key]);
    const beforeSecond = (await pair(h, m, credentials))[1];
    await read(h, m, credentials[0], route, row, true);
    await read(h, m, credentials[1], route, row, false);
    await endpointTemplates(h, credentials[1], [template.key]);
    await read(h, m, credentials[1], route, row, true);
    const beforeRevoke = await pair(h, m, credentials);
    await endpointTemplates(h, credentials[0], []);
    h.check('One Endpoint role retirement preserves the complete other Endpoint and original subscriber account identity', same((await pair(h, m, credentials))[1], beforeRevoke[1]) && beforeSecond.account.id === m.value.id);
    await read(h, m, credentials[0], route, row, false);
    await read(h, m, credentials[1], route, row, true);
    await endpointTemplates(h, credentials[0], [template.key]);
    const full = await pair(h, m, credentials);
    await authority.assign(h, m, group, []);
    // CAS revokes credentials and disables affected Endpoints as part of the
    // formal account contraction. Restoration must not resurrect these keys.
    const disabled = await contraction(h, m, credentials, full);
    for (const c of credentials) await read(h, m, c, route, row, false, disabled);
    await authority.assign(h, m, group, access);
    await pair(h, m, credentials, 1);
    for (const c of credentials) await read(h, m, c, route, row, false, disabled);
    // Retire through the original subscription owner, including CAS Endpoint
    // deletion/binding removal; do not manually re-enable retired credentials.
    for (const c of credentials) await graph.retireCredential(h, c);
    await graph.retire(h, subscription);
    await generated.cleanup(h, service);
  } catch (error) { primary = error; throw error; }
  finally { await business.finishCleanup(h, rows.reverse(), primary); }
  await h.partial('Dedicated subscriber with two distinct real ApiKey Endpoints: no implicit read, different current roles, individual Endpoint revocation, account-ceiling contraction with exact impacted/disabled CAS Endpoints and inactive original keys, no credential resurrection after account restoration, independent ordinary owner reads and formal credential/subscription/service retirement implemented. Machine reliable write/delete, account-disable matrix, cross-tenant and concurrent revocation remain open; recorded product defects are not waived.');
}
endpoints.transport = 'owner-api';
module.exports = { handlers: { 'F007-004': endpoints }, keyRead, pair, read, contraction };
