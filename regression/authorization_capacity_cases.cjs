// Declaration counts come from CAS's current initial authorization contract.
// They are not a substitute for JWT or encrypted-session byte budgets.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { authoring } = require('./authoring_cases.cjs');
const metadata = require('./definition_metadata_cases.cjs');
const scenario = require('./scenario_commands.cjs');
const { PORTAL_BASIC_KEYS, portalBasicProfileSet } = require('./platform_profiles.cjs');
const oauth = require('./oauth_refresh_cases.cjs');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
const { waitLoginForm } = require('./login_readiness.cjs');
const base = '/panel/application/definitions/';
const invalid = 'application authorization definition is invalid, duplicated or exceeds its declared scope';
function declarations(original, count) {
  if (!Number.isInteger(count) || count < 1 || count > 65) throw Error('Finite declared-count fixture required');
  // Fresh empty model only; never discard an installed or published catalogue.
  if (original?.apiVersion !== 'magic.application-authorization/v1' || original.entityActions?.length ||
      ['permissions', 'roles', 'templates', 'builtinRoles', 'builtinTemplates'].some(k => original[k]?.length)) throw Error('Fresh extension-free authorization required');
  const value = structuredClone(original);
  value.permissions = Array.from({ length: count }, (_, i) => ({ key: 'capacity-permission-' + i, name: '容量权限 ' + i, permission: 4 }));
  value.roles = Array.from({ length: count }, (_, i) => ({ key: 'capacity-role-' + i, name: '容量角色 ' + i, scene: 'usage', subjectKinds: ['human', 'service'], permissions: [value.permissions[i].key] }));
  value.templates = Array.from({ length: count }, (_, i) => ({ key: 'capacity-template-' + i, name: '容量模板 ' + i, scene: 'usage', subjectType: i % 2 ? 'endpoint' : 'account', roleKeys: [value.roles[i].key] }));
  return value;
}
async function boundary(h, app) {
  const resource = h.state.resources.find(r => r.kind === 'definition' && r.id === app.id && r.creation?.ownershipConfirmed);
  if (!resource || resource.metadataJournal) throw new h.Blocked('Fresh exact original capacity definition required; no boundary replay');
  const original = (await h.ok(h.admin, 'GET', base + app.id)).value;
  h.check('Capacity definition is the exact newly created empty model', same(original, app) && original.runtimeType === 'model-driven');
  const journal = metadata.track(h, original, false);
  for (const count of [63, 64]) {
    const wanted = declarations(original.authorization, count);
    const current = await metadata.write(h, journal, { authorization: wanted });
    h.check('Owner retains every unique permission, role and account/Endpoint template at the declared boundary without truncation', same(current.authorization, wanted));
  }
  for (const field of ['permissions', 'roles', 'templates']) {
    const legal = journal.last, oversized = structuredClone(legal.authorization);
    // Keep all references valid so only this owner's count limit is crossed.
    const extra = declarations(original.authorization, 65)[field][64];
    if (field === 'roles') extra.permissions = [oversized.permissions[0].key];
    if (field === 'templates') extra.roleKeys = [oversized.roles[0].key];
    oversized[field].push(extra);
    await scenario.reject(h, resource, h.admin, 'PUT', base + app.id,
      metadata.command(legal, { authorization: oversized }), [base + app.id, base + app.id + '/model-draft'], { code: 4, message: invalid });
    h.check('Rejected extra declaration preserves the complete legal boundary and its original concurrency revision', same((await h.ok(h.admin, 'GET', base + app.id)).value, legal));
  }
  // Restoring all three to empty demonstrates a legal contraction after each
  // refusal. Unknown writes deliberately stop here and keep the original facts.
  const restored = await metadata.write(h, journal, { authorization: structuredClone(original.authorization) });
  h.check('Formal conditional contraction remains available after count refusals and preserves every other original definition field',
    same({ ...restored, updateTime: original.updateTime }, original));
  journal.capacityDisposition = 'Three exact target-stage count refusals and full unchanged owner reads; original extension-free definition restored through a new conditional command.';
  h.persist();
}
async function declaredExtensionLimits(h, app) {
  const resource = h.state.resources.find(r => r.kind === 'definition' && r.id === app.id && r.creation?.ownershipConfirmed);
  const original = (await h.ok(h.admin, 'GET', base + app.id)).value;
  h.check('Owner starts with 3 canonical standard dataAccess entries',
    same(original.authorization?.dataAccess, [{ operation: 'delete' }, { operation: 'read' }, { operation: 'write' }]), original);

  const overAccess = structuredClone(original.authorization);
  overAccess.dataAccess.push({ operation: 'read' });
  await scenario.reject(h, resource, h.admin, 'PUT', base + app.id,
    metadata.command(original, { authorization: overAccess }), [base + app.id, base + app.id + '/model-draft'], { code: 4, message: invalid });

  const makeEntity = (idx, actionCount) => {
    const entity = authoring.newEntity(h, app);
    entity.name = 'capentity' + idx;
    entity.showName = '容量动作实体 ' + idx;
    entity.uniqueConstraints = [{ name: 'uq_' + app.pkgPrefix + '_c' + idx + '_code', fields: ['code'] }];
    entity.writeRules.state = { field: 'name', initial: 'open', transitions: [{ from: 'open', to: 'done' }] };
    entity.writeRules.actions = Array.from({ length: actionCount }, (_, i) => ({
      key: 'act-' + String(i).padStart(2, '0'),
      from: 'open',
      to: 'done',
      inputFields: ['description'],
    }));
    return entity;
  };

  const draft0 = await authoring.draft(h, app);
  const entities4 = [0, 1, 2, 3].map(idx => makeEntity(idx, 64));
  const saved256 = await authoring.save(h, app, draft0, entities4);
  const after256 = (await h.ok(h.admin, 'GET', base + app.id)).value;
  h.check('Owner freezes and retains maximum 256 unique entityActions across model entities without truncation',
    after256.authorization?.entityActions?.length === 256 &&
    new Set(after256.authorization.entityActions.map(a => a.entity + '/' + a.action)).size === 256,
    { count: after256.authorization?.entityActions?.length });

  const overEntity = saved256.entities.map((e, i) => i === 0 ? {
    ...structuredClone(e),
    writeRules: {
      ...structuredClone(e.writeRules),
      actions: [...e.writeRules.actions, { key: 'act-64', from: 'open', to: 'done', inputFields: ['description'] }],
    },
  } : structuredClone(e));
  await scenario.reject(h, resource, h.admin, 'PUT', base + app.id + '/model-draft',
    authoring.command(saved256, overEntity), [base + app.id, base + app.id + '/model-draft'], { code: 4, message: '实体动作超过限额' });

  const overTotal = [...saved256.entities.map(e => structuredClone(e)), makeEntity(4, 1)];
  await scenario.reject(h, resource, h.admin, 'PUT', base + app.id + '/model-draft',
    authoring.command(saved256, overTotal), [base + app.id, base + app.id + '/model-draft'], { code: 4, message: invalid });

  h.check('Rejected 65-action entity and 257-action app drafts preserve all 256 entityActions unchanged',
    same((await h.ok(h.admin, 'GET', base + app.id)).value, after256));

  const cleared = saved256.entities.map(e => {
    const copy = structuredClone(e);
    delete copy.writeRules.state;
    delete copy.writeRules.actions;
    return copy;
  });
  await authoring.save(h, app, saved256, cleared);
  const contracted = (await h.ok(h.admin, 'GET', base + app.id)).value;
  h.check('Model contraction cleans entityActions back to empty while preserving 3 dataAccess levels',
    contracted.authorization?.entityActions?.length === 0 &&
    same(contracted.authorization?.dataAccess, [{ operation: 'delete' }, { operation: 'read' }, { operation: 'write' }]),
    contracted.authorization);
}

async function measuredTokenAndCookieBoundary(h) {
  const f = await require('./delivery_cases.cjs').fixture(h);
  const templates = await h.directory(h.admin, '/cas/namespaces/panel/role-templates/');
  const allAccountProfiles = templates
    .filter(t => t.systemManaged && t.subjectType === 'account' && t.status === 2)
    .map(t => t.key)
    .sort();
  const ordinary = portalBasicProfileSet(templates);
  h.check('Panel namespace supplies complete account system profiles and portal baseline', allAccountProfiles.length >= 20 && ordinary.complete, allAccountProfiles);
  const instScopes = f.installations.map(i => ({ applicationUuid: i.deploymentId, accessLevel: 'manager' }));
  const usageTpl = await h.create('/cas/namespaces/panel/role-templates/', {
    key: h.state.prefix + '-cap-usage', name: '容量全量实例上限模板', scene: 'usage', subjectType: 'account',
    status: 2, roleRefs: structuredClone(ordinary.roleRefs), applicationAccess: instScopes,
  }, 'role-template');
  const assignedKeys = [...new Set([...allAccountProfiles, usageTpl.key])];
  const capAccount = await h.create('/cas/namespaces/panel/accounts/', {
    account: h.state.prefix + '-cap-full', displayName: '全量档案与实例容量主体',
    password: h.state.password, status: 2, roleTemplateKeys: assignedKeys,
  }, 'account');
  await h.ok(h.admin, 'PUT', '/cas/namespaces/panel/accounts/' + capAccount.id + '/role-templates', {
    roleTemplateKeys: assignedKeys,
    applicationScopes: [{ templateKey: usageTpl.key, applicationAccess: instScopes }],
  });
  const capDetail = (await h.ok(h.admin, 'GET', '/cas/namespaces/panel/accounts/' + capAccount.id)).value;
  h.check('All assigned profiles and roles persisted without silent truncation',
    assignedKeys.every(k => capDetail.templateRefs?.some(t => t.key === k)) && (capDetail.effectiveRoles?.length || 0) > 0, capDetail);

  const capActor = await h.login(capAccount.account, h.state.password, 'panel', h.state.password + 'Cap');
  const cookies = await capActor.context.cookies(capActor.origin);
  const cookieHeaderBytes = Buffer.byteLength(cookies.map(c => c.name + '=' + c.value).join('; '), 'utf8');
  h.check('Browser BFF session Cookie header fits strictly within 4096-byte browser cookie budget',
    cookies.length > 0 && cookieHeaderBytes > 0 && cookieHeaderBytes < 4096, { cookieCount: cookies.length, cookieHeaderBytes });

  const sessionVal = (await h.ok(capActor, 'GET', '/api/v1/web/session/')).value;
  h.check('Full-profile subject loads Web session cleanly', sessionVal.account?.id === capAccount.id, sessionVal);
  const rtMeta = (await h.ok(capActor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + f.installations[0].deploymentId)).value;
  h.check('Full-profile subject enters assigned installed application runtime cleanly',
    rtMeta?.readIdentity?.deploymentId === f.installations[0].deploymentId, rtMeta);

  // Measure real full-scope RS256 OAuth JWT & Refresh JWT bytes from CAS in panel using h.admin.
  const clientsBase = '/cas/namespaces/panel/oauth/clients/';
  const existingClients = await h.directory(h.admin, clientsBase);
  const bffClient = existingClients.find(c => c.partyType === 'first_party' && typeof c.allowedScopes === 'string' && c.allowedScopes.includes('magiccas.') && c.allowedScopes.includes('magicrunner.'));
  const targetScopes = bffClient?.allowedScopes || 'openid profile';
  const targetAudience = bffClient?.audience || 'api://management';
  const redirect = capActor.origin + '/portal/';
  const clientRes = await h.api(h.admin, 'POST', clientsBase, {
    name: h.state.prefix + '-cap-jwt', developerName: '', clientType: 'confidential', partyType: 'first_party',
    authenticationNamespaces: ['panel'], redirectUris: [redirect], grantTypes: ['authorization_code', 'refresh_token'],
    allowedScopes: targetScopes, scopeDescription: '容量真实JWT字节测量', audience: targetAudience, requirePKCE: true,
    status: 1, description: 'F010-005 JWT/Session Byte Boundary Measurement',
  });
  h.check('Capacity OAuth client created in panel cleanly', h.good(clientRes) && !!clientRes.data?.value?.clientId, clientRes);
  const clientId = clientRes.data.value.clientId;
  let credId;
  try {
    const credRes = await h.api(h.admin, 'POST', clientsBase + encodeURIComponent(clientId) + '/credentials/', {
      name: h.state.prefix + '-cap-jwt-secret', expiresAt: Date.now() + 1800000,
    });
    h.check('Capacity OAuth credential issued', h.good(credRes) && Number.isSafeInteger(credRes.data?.value?.id) && !!credRes.data.value.clientSecret, credRes);
    credId = credRes.data.value.id;
    const clientSecret = credRes.data.value.clientSecret;
    const latestClient = (await h.ok(h.admin, 'GET', clientsBase + encodeURIComponent(clientId))).value;
    await h.ok(h.admin, 'PUT', clientsBase + encodeURIComponent(clientId), {
      name: h.state.prefix + '-cap-jwt', developerName: '', authenticationNamespaces: ['panel'],
      redirectUris: [redirect], grantTypes: ['authorization_code', 'refresh_token'],
      allowedScopes: targetScopes, scopeDescription: '容量真实JWT字节测量', audience: targetAudience,
      requirePKCE: true, status: 2, description: 'F010-005 JWT/Session Byte Boundary Measurement',
      endpointId: 0, expectedVersion: latestClient.version,
    });
    const formCred = { client_id: clientId, client_secret: clientSecret, namespace: 'panel', client_namespace: 'panel' };

    const verifier = crypto.randomBytes(32).toString('base64url'), state = crypto.randomBytes(24).toString('base64url'), nonce = crypto.randomBytes(24).toString('base64url');
    const params = new URLSearchParams({ response_type: 'code', client_id: clientId, redirect_uri: redirect,
      scope: targetScopes, state, nonce, code_challenge: crypto.createHash('sha256').update(verifier).digest('base64url'),
      code_challenge_method: 'S256', namespace: 'panel', client_namespace: 'panel' });
    const page = await capActor.context.newPage();
    let code;
    try {
      await withOriginalCasForms({ ...capActor, page }, { journal: h.state.originalCasForms ||= [], persist: h.persist, record: h.observe }, async () => {
        await page.goto(capActor.origin + '/api/v1/cas/oauth/authorize?' + params, { waitUntil: 'networkidle', timeout: 45000 });
        if (new URL(page.url()).pathname === '/login/cas') {
          const form = await waitLoginForm(page);
          await form.account.fill(capActor.identity.account); await form.password.fill(capActor.password);
          await form.submit.click();
        }
        await page.waitForURL(url => url.origin + url.pathname === redirect && url.searchParams.has('code'), { timeout: 30000 });
      });
      code = new URL(page.url()).searchParams.get('code');
    } finally { await page.close(); }

    const tokenRes = await h.protocol(capActor, 'POST', '/api/v1/cas/oauth/token', {
      ...formCred, grant_type: 'authorization_code', code, redirect_uri: redirect, code_verifier: verifier,
    });
    h.check('Full-profile OAuth token exchange succeeds', tokenRes.status === 200 && typeof tokenRes.data?.access_token === 'string' && typeof tokenRes.data?.refresh_token === 'string', tokenRes);
    const jwtBytes = Buffer.byteLength(tokenRes.data.access_token, 'utf8');
    const claimsRaw = Buffer.from(tokenRes.data.access_token.split('.')[1], 'base64url');
    const claims = JSON.parse(claimsRaw);
    const refreshRes = await h.protocol(capActor, 'POST', '/api/v1/cas/oauth/token', {
      ...formCred, grant_type: 'refresh_token', refresh_token: tokenRes.data.refresh_token,
    });
    h.check('Full-profile OAuth refresh succeeds with complete claims', refreshRes.status === 200 && typeof refreshRes.data?.access_token === 'string', refreshRes);
    const refreshedJwtBytes = Buffer.byteLength(refreshRes.data.access_token, 'utf8');
    const revokeRes = await h.protocol(capActor, 'POST', '/api/v1/cas/oauth/revoke', {
      ...formCred, token: refreshRes.data.refresh_token, token_type_hint: 'refresh_token',
    });
    h.check('Capacity test refresh family revokes cleanly', revokeRes.status === 200);
    h.check('Existing platform admin session remains healthy after capacity boundary & revocation', h.good(await h.api(h.admin, 'GET', '/api/v1/web/session/')));
    h.observe({
      kind: 'authorization-capacity-byte-measurements',
      profileCount: assignedKeys.length,
      effectiveRoleCount: (capDetail.effectiveRoles || []).length,
      permissionIdCount: Array.isArray(claims.permission_ids) ? claims.permission_ids.length : 0,
      authorizationGrantCount: Array.isArray(claims.authorization_grants) ? claims.authorization_grants.length : 0,
      scopeCount: typeof claims.scope === 'string' && claims.scope ? claims.scope.split(/\s+/).length : 0,
      cookieCount: cookies.length,
      cookieHeaderBytes,
      jwtBytes,
      claimsBytes: claimsRaw.length,
      refreshedJwtBytes,
      usedBffScopeCeiling: !!bffClient,
    });
  } finally {
    if (credId) await h.api(h.admin, 'DELETE', clientsBase + encodeURIComponent(clientId) + '/credentials/' + credId).catch(() => {});
    await h.api(h.admin, 'DELETE', clientsBase + encodeURIComponent(clientId)).catch(() => {});
  }
}

async function capacity(h) {
  await boundary(h, await authoring.definition(h, 'authorization-capacity'));
  await declaredExtensionLimits(h, await authoring.definition(h, 'authorization-capacity-ext'));
  await measuredTokenAndCookieBoundary(h);
  h.observe({
    kind: 'special-branches-deferred',
    caseId: 'F010-005',
    classification: '[C]',
    note: 'Extreme multi-instance / proxy-buffer saturation belongs to special [C] (isolated-daemon); CAS v1 declared limits (dataAccess 3/4, entityActions 256/257, permissions/roles/templates 64/65), full-profile + multi-instance JWT & BFF cookie byte measurements, refresh, business call and safe revocation verified.',
  });
}
capacity.transport = 'owner-api';
capacity.requiresOnlyDeliveryFixture = true;
module.exports = { handlers: { 'F010-005': capacity }, declarations, boundary, declaredExtensionLimits };
