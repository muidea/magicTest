// CAS owns identities, current authority and credential retirement. Only its
// public commands/read models are used. Credential material stays private.
const { isDeepStrictEqual: same } = require('node:util');
const { sameAuthority } = require('./authority_snapshot.cjs');
const handlers = {};
const base = n => '/cas/namespaces/' + n + '/';
const publicBase = n => '/api/v1/cas/namespaces/' + n + '/';
const machineScope = 'magicrunner.usage.gateway.read';
const absent = r => [200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
const terminal = r => [200, 400, 409, 422].includes(r.status) && [3, 4, 7, 19, 21].includes(r.data?.error?.code);
function journal(h, actor, kind, collection, intended) {
  const r = { kind: 'cas-probe-' + kind, actor: 'tenantAdmin', actorIdentity: structuredClone(actor.identity), origin: actor.origin,
    collection, intended: structuredClone(intended), phase: 'intent', outcome: 'unknown' };
  h.state.resources.push(r); h.persist(); return r;
}
function original(h, r) {
  const actor = h[r.actor];
  if (!actor || !same(actor.identity, r.actorIdentity) || actor.origin !== r.origin) throw new h.Blocked('CAS cleanup requires exact original management actor and origin');
  return actor;
}
async function client(h, payload) {
  const actor = h.tenantAdmin, collection = base(actor.identity.namespace) + 'oauth/clients/';
  const r = journal(h, actor, 'client', collection, payload);
  const reply = await h.api(actor, 'POST', collection, payload);
  r.response = reply; r.id = reply.data?.value?.clientId; r.outcome = h.good(reply) ? 'accepted' : 'unconfirmed'; h.persist();
  h.check('CAS acknowledges exact client configuration and owner namespace', h.good(reply) && typeof r.id === 'string' && r.id.length > 0 && reply.data.value.name === payload.name && reply.data.value.namespace === actor.identity.namespace, reply);
  r.phase = 'created'; h.persist();
  const read = (await h.ok(actor, 'GET', collection + encodeURIComponent(r.id))).value;
  h.check('Independent CAS read confirms created client and endpoint binding', read.clientId === r.id && read.name === payload.name && (read.endpointId ?? 0) === (payload.endpointId || 0) && read.namespace === actor.identity.namespace, read);
  r.ownershipConfirmed = true; h.persist(); return { value: read, resource: r };
}
async function credential(h, owner, payload, rotating) {
  const actor = original(h, owner.resource), collection = owner.resource.collection + encodeURIComponent(owner.value.clientId) + '/credentials/';
  const r = journal(h, actor, 'credential', collection, payload);
  r.clientId = owner.value.clientId; r.parentClient = owner.resource.collection + owner.value.clientId; h.persist();
  const reply = await h.api(actor, 'POST', rotating ? collection + rotating.id + '/rotate' : collection, payload);
  r.response = reply; r.id = reply.data?.value?.id; r.outcome = h.good(reply) ? 'accepted' : 'unconfirmed'; h.persist();
  h.check('CAS acknowledges one credential for the exact original client', h.good(reply) && Number.isSafeInteger(r.id) && r.id > 0 && reply.data.value.clientId === r.clientId && typeof reply.data.value.clientSecret === 'string' && reply.data.value.clientSecret.length > 0, { id: r.id, clientId: r.clientId, status: reply.status, error: reply.data?.error });
  r.phase = 'created'; h.persist();
  const rows = await h.directory(actor, collection), read = rows.find(row => row.id === r.id);
  h.check('Independent credential list confirms identity without returning full secrets', read?.clientId === r.clientId && read.name === payload.name && read.status === 'active' && rows.every(row => !Object.hasOwn(row, 'clientSecret') && !Object.hasOwn(row, 'secretHash') && !JSON.stringify(row).includes(reply.data.value.clientSecret)), rows);
  r.ownershipConfirmed = true; h.persist(); return { value: reply.data.value, resource: r };
}
async function cleanup(h, r) {
  const actor = original(h, r);
  if (r.outcome !== 'accepted' || !r.id || !r.ownershipConfirmed) throw new h.Blocked('Unconfirmed original CAS command; preserve exact intent without replay or guessed deletion');
  if (r.kind === 'cas-probe-client') {
    if (h.state.resources.some(child => child.kind === 'cas-probe-credential' && child.parentClient === r.collection + r.id && child.phase !== 'deleted')) throw new h.Blocked('Original client has unresolved credential commands');
    const route = r.collection + encodeURIComponent(r.id), current = await h.api(actor, 'GET', route);
    if (absent(current)) return { proof: 'Independent original client absence', originalClientId: r.id };
    h.check('Client cleanup targets exact original client namespace and identity', h.good(current) && current.data.value?.clientId === r.id && current.data.value.namespace === r.actorIdentity.namespace, current);
    if (r.deletion) throw new h.Blocked('Original client DELETE remains open; no replay');
    r.deletion = { outcome: 'unknown' }; h.persist();
    r.deletion.response = await h.api(actor, 'DELETE', route); r.deletion.outcome = h.good(r.deletion.response) ? 'accepted' : 'unconfirmed'; h.persist();
    h.check('Original client DELETE acknowledged', r.deletion.outcome === 'accepted', r.deletion.response);
    h.check('Independent CAS read proves exact client absence', absent(await h.api(actor, 'GET', route)));
    return { proof: 'Original client DELETE and independent absence; CAS owns removal of retired credential history' };
  }
  if (r.kind !== 'cas-probe-credential') throw new h.Blocked('Unresolved CAS identity probe remains open');
  let rows = await h.directory(actor, r.collection), read = rows.find(row => row.id === r.id);
  h.check('Retirement observes exact credential of original client', read?.clientId === r.clientId, rows);
  if (!['revoked', 'expired'].includes(read.status)) {
    if (r.deletion) throw new h.Blocked('Original credential revoke remains open; no replay');
    r.deletion = { outcome: 'unknown' }; h.persist();
    r.deletion.response = await h.api(actor, 'DELETE', r.collection + r.id); r.deletion.outcome = h.good(r.deletion.response) ? 'accepted' : 'unconfirmed'; h.persist();
    h.check('Original credential revoke acknowledged', r.deletion.outcome === 'accepted', r.deletion.response);
    rows = await h.directory(actor, r.collection); read = rows.find(row => row.id === r.id);
  }
  h.check('Independent CAS list proves credential cannot remain active', read?.clientId === r.clientId && ['revoked', 'expired'].includes(read.status), read);
  return { proof: 'Independent credential terminal state; immutable history retained until formal parent client removal', terminalCredential: read };
}
async function revoke(h, c) { const proof = await cleanup(h, c.resource); c.resource.phase = 'deleted'; h.persist(); return proof; }
async function machine(h, suffix, editDescription) {
  const n = h.tenantAdmin.identity.namespace;
  await enableOAuth(h);
  const endpointTemplate = await h.createAs('tenantAdmin', base(n) + 'role-templates/', { key: h.state.prefix + '-' + suffix + '-machine', name: '受控机器账号读取',
    description: '复用已登记服务调用角色；不创建角色定义', subjectType: 'endpoint', roleRefs: [{ module: '/modules/kernel/runner', key: 'portal-service-invoker' }], applicationAccess: [], status: 2 }, 'role-template');
  const account = await h.createAs('tenantAdmin', base(n) + 'accounts/', { account: h.state.prefix + '-' + suffix, displayName: '机器凭证回归账号', password: h.state.password,
    status: 2, roleTemplateKeys: ['portal-user', 'tenant-security-admin'] }, 'account');
  const payload = { name: h.state.prefix + '-' + suffix, description: '当前回归独立 Endpoint', status: 2, account: { id: account.id }, roleTemplateKeys: [endpointTemplate.key], scope: machineScope, startTime: Date.now() - 1000, expireTime: Date.now() + 3600000 };
  const endpoint = await h.createAs('tenantAdmin', base(n) + 'endpoints/', payload, 'endpoint');
  if (editDescription) {
    const resource = h.state.resources.find(r => r.id === endpoint.id && r.collection === base(n) + 'endpoints/');
    resource.editIntent = { ...payload, description: editDescription }; h.persist();
    resource.editResponse = await h.api(h.tenantAdmin, 'PUT', base(n) + 'endpoints/' + endpoint.id, resource.editIntent); h.persist();
    h.check('Endpoint edit acknowledged before credential provisioning', h.good(resource.editResponse), resource.editResponse);
  }
  const options = (await h.ok(h.tenantAdmin, 'GET', base(n) + 'endpoints/' + endpoint.id + '/oauth-scope-options/')).values;
  h.check('CAS returns the complete non-paginated scope option contract', Array.isArray(options) && options.every(option => typeof option.scope === 'string' && Array.isArray(option.audiences)), options);
  const audiences = [...new Set(options.filter(option => option.scope === machineScope).flatMap(option => option.audiences || []))];
  if (audiences.length !== 1) throw new h.Blocked('Exact service-invocation scope requires one declared resource audience; no guessed audience');
  const owner = await client(h, { name: h.state.prefix + '-' + suffix, developerName: '', clientType: 'confidential', partyType: 'first_party', authenticationNamespaces: [n], redirectUris: [],
    grantTypes: ['client_credentials'], allowedScopes: machineScope, scopeDescription: '受控服务调用身份', audience: audiences[0], requirePKCE: false, status: 1, description: '独立机器凭证验证', endpointId: endpoint.id });
  const c = await credential(h, owner, { name: h.state.prefix + '-' + suffix + '-active', expiresAt: Date.now() + 1800000 });
  await activateClient(h, owner);
  return { n, account, endpoint, payload, owner, credential: c };
}
async function activateClient(h, owner) {
  const actor = original(h, owner.resource);
  if (owner.resource.enableIntent) throw new h.Blocked('Original client enable command already recorded; no replay');
  // Credential issuance changes the guarded client revision. Enabling uses an
  // independent fresh snapshot, never the pre-issuance creation version.
  owner.value = (await h.ok(actor, 'GET', owner.resource.collection + owner.value.clientId)).value;
  const { clientType, partyType, ...configuration } = owner.resource.intended;
  owner.resource.enableIntent = { ...configuration, endpointId: configuration.endpointId || 0, status: 2, expectedVersion: owner.value.version }; h.persist();
  const enabled = await h.api(actor, 'PUT', owner.resource.collection + owner.value.clientId, owner.resource.enableIntent);
  owner.resource.enableResponse = enabled; h.persist();
  h.check('Client enabled only after first active credential is independently confirmed', h.good(enabled), enabled);
  owner.value = (await h.ok(actor, 'GET', owner.resource.collection + owner.value.clientId)).value;
  h.check('Owner confirms enabled client and advanced conditional version', owner.value.status === 2 && owner.value.version > owner.resource.enableIntent.expectedVersion, owner.value);
  return owner.value;
}
async function token(h, fixture, c = fixture.credential) {
  return h.protocol(h.tenantAdmin, 'POST', '/api/v1/cas/oauth/token', { grant_type: 'client_credentials', client_id: fixture.owner.value.clientId,
    client_secret: c.value.clientSecret, namespace: fixture.n, client_namespace: fixture.n, scope: machineScope });
}
async function introspect(h, fixture, accessToken, c = fixture.credential) {
  return h.protocol(h.tenantAdmin, 'POST', '/api/v1/cas/oauth/introspect', { token: accessToken, token_type_hint: 'access_token', client_id: fixture.owner.value.clientId,
    client_secret: c.value.clientSecret, namespace: fixture.n, client_namespace: fixture.n });
}
async function accepted(h, fixture, c) {
  const reply = await token(h, fixture, c);
  h.check('Exact Endpoint credential obtains a scoped machine token', reply.status === 200 && typeof reply.data.access_token === 'string' && reply.data.token_type?.toLowerCase() === 'bearer' && reply.data.scope?.split(' ').includes(machineScope), reply);
  const read = await introspect(h, fixture, reply.data.access_token, c);
  h.check('Independent cookie-free CAS introspection confirms exact active Endpoint token', read.status === 200 && read.data.active === true && read.data.sub === 'endpoint:' + fixture.endpoint.id && read.data.client_id === fixture.owner.value.clientId, read);
  return reply.data.access_token;
}
async function bearer(h, actor, n, id, accessToken, headers = {}) {
  return h.protocol(actor, 'GET', publicBase(n) + 'accounts/' + id, undefined, { ...headers, Authorization: 'Bearer ' + accessToken });
}
function refused(h, r, label) {
  h.check(label, [400, 401, 403].includes(r.status) && (!!r.data.error || !!r.data.error_description), r);
}
function inactive(h, r, label) {
  h.check(label, (r.status === 200 && r.data.active === false) || ([400, 401, 403].includes(r.status) && !!r.data.error), r);
}
async function endpointFact(h, f, status) {
  const read = (await h.ok(h.tenantAdmin, 'GET', base(f.n) + 'endpoints/' + f.endpoint.id)).value;
  h.check('Independent endpoint read confirms exact account, role, scope and state', read.id === f.endpoint.id && read.account?.id === f.account.id && read.status === status && read.scope === machineScope && read.templateRefs?.some(t => t.key === f.payload.roleTemplateKeys[0]), read);
  return read;
}
async function subscribedMachine(h, f, suffix) {
  const graph = require('./service_graph.cjs');
  const actor = await h.login(f.account.account, h.state.password, f.n, h.state.password + suffix);
  const service = await graph.fixture(h, suffix);
  const subscription = await graph.subscribe(h, service, actor);
  h.check('Original Endpoint account owns a real active service subscription', subscription.value.status === 2 && subscription.value.subscriberRef.accountId === f.account.id);
  const credential = await graph.credential(h, subscription);
  await graph.succeeds(h, actor, service, credential);
  return { actor, service, graph, credential };
}
function serviceRefused(h, response, message) {
  h.check(message, [401, 403, 404].includes(response.status) && response.data.marker == null, response);
}
handlers['F007-001'] = async h => {
  const f = await machine(h, 'endpoint-life', '已编辑 Endpoint 描述');
  const fact = await endpointFact(h, f, 2);
  h.check('Endpoint edit persists without replacing original identity', fact.description === '已编辑 Endpoint 描述');
  const live = await subscribedMachine(h, f, 'endpoint_live');
  const originalToken = await accepted(h, f);
  const beforeUnbound = live.service.up.requests.length;
  const unbound = await live.graph.call(h, live.actor, live.service, originalToken, 'Bearer');
  h.check('Active generic Endpoint is not the formally registered subscription credential', unbound.status === 403 && unbound.data.error?.message === 'subscription credential does not belong to target service', unbound);
  h.check('Unbound generic Endpoint cannot reach upstream despite owning account subscription', live.service.up.requests.length === beforeUnbound);
  const retirePreviousAt = Date.now() + 1500;
  const next = await credential(h, f.owner, { name: h.state.prefix + '-rotated', retirePreviousAt, expiresAt: Date.now() + 1800000 }, f.credential.value);
  const replacementToken = await accepted(h, f, next);
  await live.graph.succeeds(h, live.actor, live.service, live.credential);
  // Actual wall clock retirement, no test-side timestamp or owner state edits.
  while (Date.now() <= retirePreviousAt + 100) await new Promise(resolve => setTimeout(resolve, Math.min(500, retirePreviousAt + 101 - Date.now())));
  refused(h, await token(h, f), 'Rotated old credential is rejected after its actual retirement time');
  const beforeRetiredCall = live.service.up.requests.length;
  serviceRefused(h, await live.graph.call(h, live.actor, live.service, originalToken, 'Bearer'), 'Retired original credential cannot continue invoking the subscribed service with an earlier token');
  h.check('Retired original token does not reach upstream', live.service.up.requests.length === beforeRetiredCall);
  const rows = await h.directory(h.tenantAdmin, f.credential.resource.collection);
  h.check('Owner independently observes original credential no longer active', rows.some(row => row.id === f.credential.value.id && ['expired', 'revoked'].includes(row.status)), rows);
  await revoke(h, next);
  refused(h, await token(h, f, next), 'Explicitly revoked replacement credential cannot mint tokens');
  const afterRevoke = await h.directory(h.tenantAdmin, next.resource.collection);
  h.check('CAS independently confirms exact explicitly revoked replacement credential', afterRevoke.some(row => row.id === next.value.id && row.status === 'revoked'), afterRevoke);
  await live.graph.succeeds(h, live.actor, live.service, live.credential);
  await revoke(h, f.credential);

};
handlers['F007-002'] = async h => {
  const f = await machine(h, 'endpoint-scope');
  const live = await subscribedMachine(h, f, 'endpoint_scope_live'), accessToken = await accepted(h, f);
  const foreign = await live.graph.fixture(h, 'foreign_endpoint_target', {}, 'otherTenantAdmin');
  h.check('Other tenant portal contains its actual independently published target service', (await h.directory(h.otherTenantAdmin, '/portal/services/', { pageSize: 20 })).some(x => x.id === foreign.service.id));
  const beforeUnbound = live.service.up.requests.length;
  const unbound = await live.graph.call(h, live.actor, live.service, accessToken, 'Bearer');
  h.check('Same-tenant active generic Endpoint cannot replace the subscription-bound identity', unbound.status === 403 && unbound.data.error?.message === 'subscription credential does not belong to target service', unbound);
  h.check('Generic unbound request has no upstream effect', live.service.up.requests.length === beforeUnbound);
  const beforeCross = foreign.up.requests.length;
  serviceRefused(h, await live.graph.call(h, h.otherTenantAdmin, foreign, accessToken, 'Bearer'), 'Original tenant Endpoint token cannot invoke the existing foreign tenant service');
  serviceRefused(h, await live.graph.call(h, h.otherTenantAdmin, foreign, live.credential.apiKey), 'Actual usable original subscription credential also cannot invoke the existing foreign tenant service');
  h.check('Cross-tenant request never reaches the real controlled upstream', foreign.up.requests.length === beforeCross);
  await live.graph.succeeds(h, live.actor, live.service, live.credential);
  const target = (await h.ok(h.otherTenantAdmin, 'GET', '/api/v1/web/session/')).value.account;
  // Probe both the original Host and actual other-tenant Host, with hostile
  // selectors. No BFF cookies are sent on either request.
  for (const actor of [h.tenantAdmin, h.otherTenantAdmin]) {
    const response = await bearer(h, actor, h.otherTenantAdmin.identity.namespace, target.id, accessToken, { 'X-Namespace': h.otherTenantAdmin.identity.namespace });
    h.check('CAS resource audience/authentication gate rejects cookie-free service token', [401, 403].includes(response.status), response);
    h.check('Cross-tenant request returns no protected target value', response.data.value == null, response);
  }
  await accepted(h, f);
  const current = (await h.ok(h.otherTenantAdmin, 'GET', base(h.otherTenantAdmin.identity.namespace) + 'accounts/' + target.id)).value;
  h.check('Independent other-tenant owner still exposes original target to its authorized admin', current.id === target.id && current.account === target.account);

};
handlers['F007-003'] = async h => {
  const f = await machine(h, 'endpoint-invalid'), before = await endpointFact(h, f, 2), accessToken = await accepted(h, f);
  const collection = base(f.n) + 'endpoints/', attempt = journal(h, h.tenantAdmin, 'duplicate', collection, f.payload);
  attempt.original = before; h.persist();
  const response = await h.api(h.tenantAdmin, 'POST', collection, f.payload); attempt.response = response; h.persist();
  const rows = (await h.directory(h.tenantAdmin, collection)).filter(row => row.name === f.payload.name);
  const after = (await h.ok(h.tenantAdmin, 'GET', collection + f.endpoint.id)).value;
  if (terminal(response) && response.data.error.code === 7 && rows.length === 1 && sameAuthority(before, after)) { attempt.outcome = 'rejected-unchanged'; attempt.phase = 'deleted'; h.persist(); }
  h.check('Duplicate Endpoint rejected at identity validation with explicit diagnostic', terminal(response) && response.data.error.code === 7 && /already exists|duplicate/i.test(response.data.error.message), response);
  h.check('Complete directory and exact owner read prove no duplicate or overwrite', rows.length === 1 && rows[0].id === f.endpoint.id && sameAuthority(before, after), { rows, after });
  await h.ok(h.tenantAdmin, 'PUT', collection + f.endpoint.id, { ...f.payload, status: 1 });
  await endpointFact(h, f, 1);
  refused(h, await token(h, f), 'Disabled Endpoint cannot mint a new machine token with original credential');
  inactive(h, await introspect(h, f, accessToken), 'Disabled Endpoint cannot continue using an earlier machine token');
  await h.ok(h.otherTenantAdmin, 'GET', '/system/context/?surface=portal');
};
handlers['F004-001'] = async h => {
  const f = await machine(h, 'account-life'), route = base(f.n) + 'accounts/' + f.account.id;
  const firstLogin = await h.login(f.account.account, h.state.password, f.n, h.state.password + 'Q');
  h.check('Account replacement preserves explicit current human template assignments', Array.isArray(f.account.templateRefs) && f.account.templateRefs.length === 2);
  await h.ok(h.tenantAdmin, 'PUT', route, { account: f.account.account, displayName: '已编辑回归账号', email: 'regression@example.invalid', description: '账号生命周期独立夹具', status: 2,
    roleTemplateKeys: f.account.templateRefs.map(t => t.key) });
  const saved = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  h.check('Account edit and current authority persist under same original identity', saved.id === f.account.id && saved.account === f.account.account && saved.displayName === '已编辑回归账号' && saved.email === 'regression@example.invalid' && saved.templateRefs?.some(t => t.key === 'tenant-security-admin'), saved);
  // Full account replacement reapplies explicit authority. Establish positive
  // original-subject sessions/tokens after that command so its security fence
  // cannot be mistaken for the later password-reset result.
  const actor = await h.login(f.account.account, firstLogin.password, f.n);
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
  const tokenBefore = await accepted(h, f);
  const newPassword = h.state.password + 'R';
  await h.ok(h.tenantAdmin, 'PUT', route + '/password', { password: newPassword });
  await h.rejectedLogin(f.account.account, actor.password, f.n);
  const oldSession = await h.api(actor, 'GET', '/api/v1/web/session/');
  h.check('Reset retires the preexisting account BFF session', oldSession.status === 401 || oldSession.data?.error?.code === 11, oldSession);
  const endpointAfterReset = await introspect(h, f, tokenBefore);
  inactive(h, endpointAfterReset, 'Password reset invalidates already-issued Endpoint token through original account cutoff');
  const fresh = await h.login(f.account.account, newPassword, f.n, newPassword + 'F');
  h.check('Management password reset requires an authenticated password change', fresh.passwordChanged === true);
  await h.ok(fresh, 'GET', '/system/context/?surface=portal');
  const freshEndpointToken = await accepted(h, f);
  await h.ok(h.tenantAdmin, 'PUT', route, { account: f.account.account, displayName: saved.displayName, email: saved.email, description: saved.description, status: 1,
    roleTemplateKeys: saved.templateRefs.map(t => t.key) });
  const disabled = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  h.check('Independent account read confirms disabled identity and retained role projection', disabled.id === f.account.id && disabled.status === 1 && disabled.templateRefs?.some(t => t.key === 'tenant-security-admin'), disabled);
  await h.rejectedLogin(f.account.account, fresh.password, f.n);
  const session = await h.api(fresh, 'GET', '/api/v1/web/session/');
  h.check('Disabling account retires its preexisting BFF session', session.status === 401 || session.data?.error?.code === 11, session);
  inactive(h, await introspect(h, f, freshEndpointToken), 'Disabled owning account fences Endpoint token that was valid immediately before disabling');
  refused(h, await token(h, f), 'Disabled owning account fences Endpoint token issuance');
  for (const peer of [h.user, h.tenantAdmin, h.otherTenantAdmin, h.admin]) await h.ok(peer, 'GET', '/system/context/?surface=portal');
};
handlers['F008-003'] = async h => {
  const n = h.tenantAdmin.identity.namespace;
  await enableOAuth(h);
  const c = await client(h, { name: h.state.prefix + '-oauth-no-secret', developerName: '', clientType: 'confidential', partyType: 'first_party', authenticationNamespaces: [n],
    redirectUris: [h.tenantAdmin.origin + '/portal/'], grantTypes: ['authorization_code'], allowedScopes: 'openid profile', scopeDescription: '授权回调负例', audience: 'api://management', requirePKCE: true, status: 1, description: '无凭据机密客户端' });
  h.check('Confidential client has no preexisting credentials', (await h.directory(h.tenantAdmin, c.resource.collection + c.value.clientId + '/credentials/')).length === 0);
  const redirectClient = await client(h, { ...c.resource.intended, name: h.state.prefix + '-oauth-redirect', clientType: 'public', status: 2 });
  const params = new URLSearchParams({ response_type: 'code', client_id: redirectClient.value.clientId, redirect_uri: 'https://regression.invalid/unregistered', scope: 'openid profile', state: h.state.prefix, nonce: h.state.prefix + '-nonce',
    code_challenge: 'a'.repeat(43), code_challenge_method: 'S256', namespace: n, client_namespace: n });
  const badRedirect = await h.publicGet(h.tenantAdmin, '/api/v1/cas/oauth/authorize?' + params);
  h.check('Unregistered redirect rejected without navigation to attacker callback', badRedirect.status === 400 && !badRedirect.location && /redirect/i.test(JSON.stringify(badRedirect.data)), badRedirect);
  const missing = await h.protocol(h.tenantAdmin, 'POST', '/api/v1/cas/oauth/token', { grant_type: 'authorization_code', client_id: c.value.clientId, code: 'unissued-regression-code',
    redirect_uri: c.value.redirectUris[0], code_verifier: 'b'.repeat(43), namespace: n, client_namespace: n });
  h.check('Credential-free confidential client cannot enter token exchange', missing.status === 400 && missing.data.error === 'unauthorized_client', missing);
  const { clientType, partyType, ...configuration } = c.resource.intended;
  c.resource.enableAttempt = { ...configuration, endpointId: 0, status: 2, expectedVersion: c.value.version }; h.persist();
  c.resource.enableAttemptResponse = await h.api(h.tenantAdmin, 'PUT', c.resource.collection + c.value.clientId, c.resource.enableAttempt); h.persist();
  h.check('CAS refuses enabling a confidential client without exactly one active credential', terminal(c.resource.enableAttemptResponse) && /requires exactly one active credential/.test(c.resource.enableAttemptResponse.data.error.message), c.resource.enableAttemptResponse);
  const current = (await h.ok(h.tenantAdmin, 'GET', c.resource.collection + c.value.clientId)).value;
  h.check('Rejected OAuth requests preserve exact original client and create no credentials', same(current, c.value) && (await h.directory(h.tenantAdmin, c.resource.collection + c.value.clientId + '/credentials/')).length === 0, current);
};
handlers['F057-002'] = async h => {
  const own = (await h.ok(h.user, 'GET', '/api/v1/web/session/')).value;
  const peer = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
  const other = (await h.ok(h.otherTenantAdmin, 'GET', '/api/v1/web/session/')).value;
  const subject = 'account:' + own.account.id, peerSubject = 'account:' + peer.account.id, otherSubject = 'account:' + other.account.id;
  const namespace = h.user.identity.namespace, otherNamespace = h.otherTenantAdmin.identity.namespace;
  const personal = '/api/v1/web/security-audit/';
  const allowed = new Set(['login_success', 'login_failure', 'logout_success', 'logout_failure']);
  const rows = await h.directory(h.user, personal);
  h.check('Current ordinary account has its actual successful login in own audit', rows.some(r => r.subject === subject && r.namespace === namespace && r.eventType === 'login_success' && r.outcome === 'success'));
  h.check('Complete personal audit is confined to original account, namespace and authentication events', rows.every(r => r.subject === subject && r.namespace === namespace && allowed.has(r.eventType)));
  const audit = base(namespace) + 'oauth/audit/';
  const owner = await h.directory(h.admin, audit + '?subject=' + encodeURIComponent(subject));
  h.check('Independent authorized CAS owner confirms exact original personal events', rows.every(r => owner.some(v => v.id === r.id && same(v, r))));
  const peers = await h.directory(h.admin, audit + '?subject=' + encodeURIComponent(peerSubject));
  const foreign = await h.directory(h.admin, base(otherNamespace) + 'oauth/audit/?subject=' + encodeURIComponent(otherSubject));
  const p = peers.find(r => r.subject === peerSubject && r.namespace === namespace && r.eventType === 'login_success');
  const f = foreign.find(r => r.subject === otherSubject && r.namespace === otherNamespace && r.eventType === 'login_success');
  h.check('Other-subject and other-tenant audit records actually exist before isolation probes', !!p && !!f, { peerId: p?.id, foreignId: f?.id });
  for (const target of [p, f]) {
    const query = new URLSearchParams({ namespace: target.namespace, subject: target.subject, eventType: 'token_issued', id: String(target.id) });
    const forged = await h.directory(h.user, personal + '?' + query);
    h.check('Forged personal audit filters cannot reveal the exact foreign record or privileged events', forged.every(r => r.subject === subject && r.namespace === namespace && allowed.has(r.eventType) && r.id !== target.id), { targetId: target.id, observedIds: forged.map(r => r.id) });
  }
  for (const [actor, path] of [
    [h.user, audit + '?subject=' + encodeURIComponent(peerSubject)],
    [h.user, audit + '?id=' + p.id],
    [h.user, base(otherNamespace) + 'oauth/audit/?id=' + f.id],
    [h.tenantAdmin, base(otherNamespace) + 'oauth/audit/?id=' + f.id],
    [h.otherTenantAdmin, audit + '?id=' + p.id],
  ]) h.denied(await h.api(actor, 'GET', path), 'Original authenticated principal cannot read management audit outside its authority');
  const after = await h.directory(h.user, personal);
  h.check('Rejected probes do not pollute original personal audit with another subject', after.every(r => r.subject === subject && r.namespace === namespace && allowed.has(r.eventType)) && rows.every(r => after.some(v => v.id === r.id && same(v, r))));
};

for (const handler of Object.values(handlers)) { handler.actors = ['user', 'tenantAdmin', 'otherTenantAdmin']; handler.transport = 'owner-api'; }
async function reconcile(h) {
  const proof = [];
  for (const r of h.state.resources.filter(r => r.phase !== 'deleted')) {
    if (r.kind === 'cas-probe-client' && r.outcome === 'unconfirmed' && !r.id && r.response?.data?.error?.code === 4 && /^oauth client audience is unavailable to selected scopes:/.test(r.response.data.error.message)) {
      const actor = original(h, r), rows = await h.directory(actor, r.collection);
      h.check('Complete OAuth directory confirms rejected original client name absent', !rows.some(row => row.name === r.intended.name), rows);
      r.reconciliation = { proof: 'Original terminal audience validation rejection and independent complete client-name absence; no POST replay', name: r.intended.name };
      r.phase = 'deleted'; h.persist(); proof.push(r.reconciliation);
    }
    if (r.kind === 'endpoint' && r.creation?.response?.data?.error?.code === 4 && r.creation.response.data.value == null && /is not a endpoint template$/.test(r.creation.response.data.error.message)) {
      const actor = h[r.actor];
      if (!actor || !same(actor.identity, r.creation.actorIdentity) || actor.origin !== r.creation.origin || r.id) throw new h.Blocked('Rejected original Endpoint intent does not match actor or rejection');
      const rows = await h.directory(actor, r.collection);
      h.check('Complete owner directory confirms rejected original Endpoint name absent', !rows.some(row => row.name === r.creation.intended.name), rows);
      r.reconciliation = { proof: 'Original terminal template-type rejection and independent complete exact-name absence; no command replay', name: r.creation.intended.name };
      r.phase = 'deleted'; h.persist(); proof.push(r.reconciliation);
    }
    if (r.kind === 'cas-probe-client' && r.outcome === 'accepted' && !r.ownershipConfirmed) {
      const actor = original(h, r), read = (await h.ok(actor, 'GET', r.collection + encodeURIComponent(r.id))).value;
      h.check('Read-only reconciliation binds original acknowledged client to exact owner and configuration', r.response?.data?.value?.clientId === r.id && read.clientId === r.id && read.name === r.intended.name && read.namespace === r.actorIdentity.namespace && (read.endpointId ?? 0) === (r.intended.endpointId || 0) && read.clientType === r.intended.clientType && same(read.grantTypes, r.intended.grantTypes), read);
      r.ownershipConfirmed = true; h.persist(); proof.push({ originalClientId: r.id, proof: 'Original acknowledgement and independent exact client read; formal cleanup still required' });
    }
  }
  return proof;
}
async function enableOAuth(h) {
  const actor = h.tenantAdmin, n = actor.identity.namespace, route = base(n) + 'oauth/server';
  const before = (await h.ok(actor, 'GET', route)).value;
  if (before.enabled === true) return before;
  const parent = h.state.resources.find(r => r.kind === 'namespace' && r.name === n && r.phase !== 'deleted');
  if (!parent) throw new h.Blocked('OAuth policy change requires an exact current-run namespace fixture');
  if (parent.oauthPolicyCommand) throw new h.Blocked('Original OAuth policy command remains unresolved; no replay');
  parent.oauthPolicyCommand = { original: before, intended: { enabled: true, expectedVersion: before.version }, outcome: 'unknown' }; h.persist();
  const response = await h.api(actor, 'PUT', route, parent.oauthPolicyCommand.intended);
  parent.oauthPolicyCommand.response = response; h.persist();
  h.check('Explicit OAuth enablement acknowledged under original version', h.good(response), response);
  const after = (await h.ok(actor, 'GET', route)).value;
  h.check('CAS independently confirms enabled OAuth in exact fixture namespace', after.enabled === true && after.version > before.version, after);
  parent.oauthPolicyCommand.outcome = 'confirmed'; h.persist(); return after;
}
module.exports = { handlers, cleanup, client, credential, reconcile, enableOAuth, machine, token, accepted, activateClient };
