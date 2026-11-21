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
const { portalBasicProfileSet } = require('./platform_profiles.cjs');
const base = '/cas/namespaces/panel/';
async function keyCall(origin, method, route, apiKey, body) {
  if (!/^https?:\/\//.test(origin) || !route.startsWith('/api/v1/gateway/services/') || route.startsWith('//') || typeof apiKey !== 'string' || !apiKey) throw Error('Exact public Gateway call and original ApiKey required');
  const url = new URL(route, origin);
  if (url.origin !== origin || url.hash || url.username || url.password || url.pathname + url.search !== route || !url.pathname.startsWith('/api/v1/gateway/services/')) throw Error('Gateway call must retain its original origin and public path');
  const connect = new URL(url);
  if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
  // A new empty API context sends neither browser cookies nor bearer tokens.
  const transport = await request.newContext({ ignoreHTTPSErrors: true });
  try {
    const response = await transport.fetch(connect.href, {
      method,
      headers: { Host: url.host, Authorization: 'ApiKey ' + apiKey, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { data: body }),
      maxRedirects: 0, maxRetries: 0, timeout: 15000,
    });
    return { status: response.status(), data: await response.json().catch(() => ({})) };
  } finally { await transport.dispose(); }
}
async function keyRead(origin, route, apiKey) {
  return keyCall(origin, 'GET', route, apiKey);
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
  const common = portalBasicProfileSet(await h.directory(h.admin, base + 'role-templates/'));
  h.check('Dedicated subscriber uses the protected ordinary functional profiles', common.complete && common.roleRefs.length > 0);
  const access = [{ applicationUuid: context.identity.deploymentId, accessLevel: 'manager' }];
  const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-endpoint-ceiling', name: '独立机器账号上限', scene: 'usage', subjectType: 'account', status: 2, roleRefs: common.roleRefs, applicationAccess: access }, 'role-template');
  const m = await authority.account(h, 'endpoint-ceiling'); link(h, m.resource, f, m.value.id);
  await authority.assign(h, m, group, access);
  const template = await h.create(base + 'role-templates/', { key: h.state.prefix + '-endpoint-read', name: '独立Endpoint读取', scene: 'usage', subjectType: 'endpoint', status: 2, applicationAccess: [], roleRefs: [{ module: '/applications/' + context.identity.deploymentId, key: 'application-data-read' }] }, 'role-template');
  const writeTpl = await h.create(base + 'role-templates/', { key: h.state.prefix + '-endpoint-write', name: '独立Endpoint写删', scene: 'usage', subjectType: 'endpoint', status: 2, applicationAccess: [], roleRefs: [
    { module: '/applications/' + context.identity.deploymentId, key: 'application-data-read' },
    { module: '/applications/' + context.identity.deploymentId, key: 'application-data-write' },
    { module: '/applications/' + context.identity.deploymentId, key: 'application-data-delete' },
  ] }, 'role-template');
  const rows = [], credentials = []; let primary;
  try {
    const row = await business.create(h, context, 'endpoint-ceiling'); rows.push(row);
    const all = await generated.snapshot(h), source = f.installations[0].receipt.runtimeApplicationUuid;
    const srcCaps = all[generated.capabilities].filter(c => c.providerKey === source && c.providerType === 'application' && ['get', 'create', 'update', 'delete'].includes(c.kind) && c.status === 1 && !all[generated.bindings].some(b => b.capability?.id === c.id));
    const capByKind = Object.fromEntries(srcCaps.map(c => [c.kind, c]));
    const capIds = ['get', 'create', 'update', 'delete'].map(k => capByKind[k]?.id).filter(Boolean);
    h.check('Machine authority fixture selects all four unoccupied installed capabilities', capIds.length === 4, srcCaps);
    const service = generated.intent(h, h.state.prefix + '_endpoint_ceiling', capIds, source); link(h, service, f, m.value.id);
    await generated.converge(h, service, capIds, '机器当前角色回归');
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
    const opByKind = Object.fromEntries((contract.operations || []).map(o => [capsToKind(o, capByKind), o]));
    h.check('Actual public metadata exposes GET/CREATE/UPDATE/DELETE operations for the Endpoint matrix',
      contract.operations?.length === 4 && ['get', 'create', 'update', 'delete'].every(k => !!opByKind[k] && opByKind[k].pathTemplate.startsWith('/api/v1/gateway/services/' + service.key + '/')), contract);
    const route = opByKind.get.pathTemplate.replace(/\{id\}/g, row.recordId);
    for (const c of credentials) await read(h, m, c, route, row, false);
    await endpointTemplates(h, credentials[0], [template.key]);
    const beforeSecond = (await pair(h, m, credentials))[1];
    await read(h, m, credentials[0], route, row, true);
    await read(h, m, credentials[1], route, row, false);

    // Read-only Endpoint cannot create, update or delete via Gateway.
    const createDenied = await keyCall(h.admin.origin, 'POST', opByKind.create.pathTemplate, credentials[0].apiKey, { code: 'RG-EP-DENY', name: '读Endpoint禁写', description: null, sortOrder: 1 });
    h.check('Read-only Endpoint is denied Gateway reliable create', currentRoleRefusal(createDenied), createDenied);
    const updateDenied = await keyCall(h.admin.origin, 'PUT', opByKind.update.pathTemplate.replace(/\{id\}/g, row.recordId), credentials[0].apiKey, { name: '读Endpoint禁改', version: Number(row.version) });
    h.check('Read-only Endpoint is denied Gateway reliable update', currentRoleRefusal(updateDenied), updateDenied);
    const deleteDenied = await keyCall(h.admin.origin, 'DELETE', opByKind.delete.pathTemplate.replace(/\{id\}/g, row.recordId) + '?expectedVersion=' + row.version, credentials[0].apiKey);
    h.check('Read-only Endpoint is denied Gateway reliable delete', currentRoleRefusal(deleteDenied), deleteDenied);

    // Grant write/delete template to first Endpoint, keep second Endpoint read-only.
    await endpointTemplates(h, credentials[1], [template.key]);
    await endpointTemplates(h, credentials[0], [writeTpl.key]);
    await read(h, m, credentials[1], route, row, true);
    const created = await keyCall(h.admin.origin, 'POST', opByKind.create.pathTemplate, credentials[0].apiKey, { code: 'RG-EP-' + require('node:crypto').randomBytes(4).toString('hex').toUpperCase(), name: 'Endpoint写删样本', description: null, sortOrder: 1 });
    h.check('Write-granted Endpoint executes Gateway reliable create cleanly', created.status === 200 && created.data?.value?.id > 0 && created.data.value.version >= 1, created);
    const epRow = { kind: 'business-record', phase: 'created', actorRole: 'manager', ...context, recordId: String(created.data.value.id), version: String(created.data.value.version), origin: manager.origin, actorIdentity: structuredClone(manager.identity), commands: [] };
    delete epRow.ui; rows.push(epRow); h.state.resources.push(epRow); h.persist();
    h.check('Independent owner reads exact Gateway-created record', same((await business.record(h, manager, epRow)).data.value, created.data.value));
    h.check('Sibling read-only Endpoint cannot update the Gateway-created record', currentRoleRefusal(await keyCall(h.admin.origin, 'PUT', opByKind.update.pathTemplate.replace(/\{id\}/g, epRow.recordId), credentials[1].apiKey, { name: '同账号仅读越权', version: Number(epRow.version) })));
    const updated = await keyCall(h.admin.origin, 'PUT', opByKind.update.pathTemplate.replace(/\{id\}/g, epRow.recordId), credentials[0].apiKey, { name: 'Endpoint更新样本', version: Number(epRow.version) });
    h.check('Write-granted Endpoint executes Gateway reliable update cleanly', updated.status === 200 && String(updated.data?.value?.version) > epRow.version, updated);
    epRow.version = String(updated.data.value.version); h.persist();
    h.check('Independent owner confirms Gateway-updated record fields and version', (await business.record(h, manager, epRow)).data.value.name === 'Endpoint更新样本');
    h.check('Sibling read-only Endpoint cannot delete the Gateway-created record', currentRoleRefusal(await keyCall(h.admin.origin, 'DELETE', opByKind.delete.pathTemplate.replace(/\{id\}/g, epRow.recordId) + '?expectedVersion=' + epRow.version, credentials[1].apiKey)));
    const deleted = await keyCall(h.admin.origin, 'DELETE', opByKind.delete.pathTemplate.replace(/\{id\}/g, epRow.recordId) + '?expectedVersion=' + epRow.version, credentials[0].apiKey);
    h.check('Write-granted Endpoint executes Gateway reliable delete cleanly', deleted.status === 200 && !deleted.data?.error, deleted);
    const absentAfterDelete = await business.record(h, manager, epRow);
    h.check('Independent owner confirms Gateway-deleted record is absent', [200, 404].includes(absentAfterDelete.status) && absentAfterDelete.data?.error?.code === 2, absentAfterDelete);
    epRow.phase = 'deleted'; rows.splice(rows.indexOf(epRow), 1); h.persist();

    // Concurrent revocation + Gateway call.
    await endpointTemplates(h, credentials[0], [template.key]);
    const [concRevoke, concCall] = await Promise.all([
      h.api(h.admin, 'PUT', base + 'endpoints/' + credentials[0].value.endpointId + '/role-templates', { roleTemplateKeys: [] }),
      keyCall(h.admin.origin, 'GET', route, credentials[0].apiKey),
    ]);
    h.check('Concurrent Endpoint revocation settles cleanly without 5xx or stuck state', h.good(concRevoke) && [200, 401, 403, 409].includes(concCall.status), { concRevoke, concCall });
    credentials[0].resource.endpointAuthorityCommands ||= [];
    credentials[0].resource.endpointAuthorityCommands.push({ outcome: 'confirmed', body: { roleTemplateKeys: [] } });
    h.persist();
    await read(h, m, credentials[0], route, row, false);

    // Re-grant first Endpoint, test account-disable matrix, then restore account before ceiling contraction.
    await endpointTemplates(h, credentials[0], [template.key]);
    await read(h, m, credentials[0], route, row, true);
    const curAcc = (await h.ok(h.admin, 'GET', base + 'accounts/' + m.value.id)).value;
    const accKeys = (curAcc.templateRefs || []).map(t => t.key);
    const disabledAccount = (await h.ok(h.admin, 'PUT', base + 'accounts/' + m.value.id, { account: curAcc.account, displayName: curAcc.displayName, email: curAcc.email, description: curAcc.description, status: 1, roleTemplateKeys: accKeys })).value;
    h.check('Subscriber account disablement acknowledged by CAS', disabledAccount.status === 1, disabledAccount);
    for (const c of credentials) {
      const blocked = await keyCall(h.admin.origin, 'GET', route, c.apiKey);
      h.check('Disabling owning subscriber account blocks Endpoint Gateway invocation immediately', [401, 403].includes(blocked.status) && blocked.data?.value == null, blocked);
    }
    const reenabledAccount = (await h.ok(h.admin, 'PUT', base + 'accounts/' + m.value.id, { account: disabledAccount.account, displayName: disabledAccount.displayName, email: disabledAccount.email, description: disabledAccount.description, status: 2, roleTemplateKeys: accKeys })).value;
    h.check('Subscriber account re-enablement acknowledged before ceiling contraction', reenabledAccount.status === 2, reenabledAccount);
    await authority.assign(h, m, group, access);
    m.actor = await h.login(m.value.account, h.state.fixtures.businessMembers['endpoint-ceiling'].password, 'panel');
    await read(h, m, credentials[0], route, row, true);

    if (h.tenantAdmin) {
      h.inaccessible(await h.api(h.tenantAdmin, 'GET', '/portal/service/debug/' + service.serviceId), 'Other tenant admin cannot read panel subscriber debug metadata');
      h.inaccessible(await h.api(h.tenantAdmin, 'GET', base + 'endpoints/' + credentials[0].value.endpointId), 'Other tenant admin cannot read panel Endpoint directory');
    }

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
}
function capsToKind(op, capByKind) {
  return Object.entries(capByKind).find(([, cap]) => cap.key === op.key)?.[0] || op.method?.toLowerCase();
}
endpoints.transport = 'owner-api';
endpoints.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F007-004': endpoints }, keyRead, pair, read, contraction };
