// Application observations use their own frozen reader roles. Empty results
// prove authorization/identity only, never that a producer emitted a log/count.
const { isDeepStrictEqual: same } = require('node:util');
const pages = require('./page_runtime_cases.cjs');
const business = require('./business_cases.cjs');
const authority = require('./application_authority_cases.cjs');
const metadata = require('./definition_metadata_cases.cjs');
const { runtimeRead } = require('./owner_transport.cjs');
const readers = [
  { kind: 'operation-logs', permission: 'builtin-operation-logs.read', role: 'application-operation-logs-reader' },
  { kind: 'counters', permission: 'builtin-counters.read', role: 'application-counters-reader' },
];
async function prepare(h, authored) {
  const before = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + authored.app.id)).value;
  const authorization = structuredClone(before.authorization);
  authorization.permissions = readers.map(r => ({ key: r.permission, name: '独立只读 ' + r.kind, permission: 4 }));
  authored.app = await metadata.write(h, metadata.track(h, before, false), { authorization });
  const { authoring } = require('./authoring_cases.cjs');
  const declarations = (await h.ok(h.admin, 'GET', '/panel/application/definition/entity/blocks/')).values;
  const logger = declarations.find(x => x.kind === 'operationlog'), counter = declarations.find(x => x.kind === 'totalizator');
  const current = await authoring.draft(h, authored.app);
  const entity = structuredClone(current.entities[0]), owner = entity.pkgPath + '/' + entity.name, trigger = owner + '/:id';
  const logHook = structuredClone(logger.stageInfo.functions['*']), cStage = structuredClone(counter.stageInfo);
  cStage.startup.input = { ...cStage.startup.input, name: '观察统计', unit: '条', owner, trigger, period: [1, 2, 3, 4], namespace: '*' };
  cStage.functions.insert.input = { ...cStage.functions.insert.input, owner, trigger, action: 'insert', namespace: '$referenceExtData.namespace' };
  cStage.functions.delete.input = { ...cStage.functions.delete.input, owner, trigger, action: 'delete', namespace: '$referenceExtData.namespace' };
  cStage.teardown.input = { ...cStage.teardown.input, name: '观察统计', unit: '条', owner, trigger, period: [1, 2, 3, 4], namespace: '*' };
  entity.blockInfo = [
    { id: logger.id, key: 'log', stageInfo: { functions: { insert: logHook, delete: logHook } } },
    { id: counter.id, key: 'counter', stageInfo: cStage },
  ];
  authored.model = await authoring.save(h, authored.app, current, [entity]);
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
function validatePage(value, identity, kind, pageNum, pageSize, previous, total) {
  const p = value?.pagination;
  if (!same(value?.identity, identity) || !Array.isArray(value.values) || !p || !Number.isSafeInteger(p.total) || p.total < 0 ||
      p.pageNum !== pageNum || p.pageSize !== pageSize || p.mode || p.after || p.nextCursor || p.hasMore ||
      total !== undefined && p.total !== total || value.values.length !== Math.min(pageSize, Math.max(0, p.total - (pageNum - 1) * pageSize)))
    throw Error('Complete exact application observation page required');
  let last = previous;
  for (const row of value.values) {
    // JSON numbers above2^53 cannot prove an exact Snowflake identity.
    const id = typeof row.id === 'string' && /^[1-9][0-9]*$/.test(row.id) ? BigInt(row.id) : Number.isSafeInteger(row.id) && row.id > 0 ? BigInt(row.id) : 0n;
    if (id === 0n || last !== undefined && id >= last || row.namespace !== identity.namespace || (kind === 'operation-logs' ?
      row.hostedBy !== identity.runtimeApplicationUuid || row.targetNamespace !== identity.namespace :
      row.application?.uuid !== identity.runtimeApplicationUuid || typeof row.value !== 'number' || !Number.isFinite(row.value)))
      throw Error('Observation row crosses the original application/namespace or has an unsafe/repeated identity');
    last = id;
  }
  return { last, total: p.total };
}
async function read(h, actor, context, kind, complete = false) {
  const values = []; let last, total;
  for (let pageNum = 1; pageNum <= 100; pageNum++) {
    const route = '/apps/application/' + kind + '/?' + new URLSearchParams({ application: context.applicationKey,
      deploymentId: context.identity.deploymentId, pageNum: String(pageNum), pageSize: '100' });
    const result = await runtimeRead(actor, route, context.identity, h.observe);
    if (!complete) return result;
    h.check('Independent original observation reader reaches successful exact installed owner', h.good(result), result);
    ({ last, total } = validatePage(result.data.value, context.identity, kind, pageNum, 100, last, total));
    values.push(...result.data.value.values);
    if (values.length === total) return values;
  }
  throw new h.Blocked('Observation read exceeds finite complete-page budget; no absence proof');
}
const denied = r => [200, 401, 403].includes(r?.status) && r.data?.error?.code === 5 && r.data.value == null && !r.data.values?.length;
async function bearerRead(origin, route, identity, token) {
  const { request } = require('./playwright.cjs');
  const url = new URL('/api/v1' + route, origin), connect = new URL(url);
  if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
  const wire = Object.fromEntries(['namespace', 'deploymentId', 'installationId', 'runtimeApplicationUuid', 'generation', 'executionEpoch', 'artifactDigest'].map(k => [k, identity[k]]));
  const transport = await request.newContext({ ignoreHTTPSErrors: true });
  try {
    const response = await transport.get(connect.href, {
      headers: { Host: url.host, Authorization: 'Bearer ' + token, 'X-Magic-Expected-Installation': Buffer.from(JSON.stringify(wire)).toString('base64url') },
      maxRedirects: 0, maxRetries: 0, timeout: 15000,
    });
    return { status: response.status(), data: await response.json().catch(() => ({})) };
  } finally { await transport.dispose(); }
}
async function observations(h) {
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'observation', requestPrefix: 'observation-', prepareAuthor: prepare });
  const manager = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, manager), peer = await business.runtime(h, f, 1, manager);
  const base = '/cas/namespaces/panel/', templates = await h.directory(h.admin, base + 'role-templates/');
  const ordinary = templates.find(t => t.key === 'portal-basic-user' && t.systemManaged && t.subjectType === 'account' && t.status === 2);
  h.check('Protected ordinary template and frozen observer permissions are present', ordinary?.roleRefs?.length > 0 &&
    readers.every(r => f.revision.application.authorization.permissions.some(p => p.key === r.permission && p.permission === 4)));
  const roles = await h.directory(h.admin, base + 'roles/'), module = '/applications/' + context.identity.deploymentId;
  for (const reader of readers) h.check('CAS installs separately assignable fixed observation reader without write/delete privileges',
    roles.some(r => r.module === module && r.key === reader.role && r.humanAssignable && r.status === 2 &&
      r.privilege?.some(p => p.module === module && p.uriPath === '/apps/permissions/' + reader.permission && p.value === 4)));
  let primary;
  try {
    const emitted = await business.create(h, context, 'observation-emit');
    await business.finishCleanup(h, [emitted], undefined);
    for (const reader of readers) h.check('Data manager receives no implicit independent ' + reader.kind + ' authority', denied(await read(h, manager, context, reader.kind)));
    for (const [index, reader] of readers.entries()) {
      const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-observe-' + index, name: '独立应用观察角色', subjectType: 'account', status: 2,
        applicationAccess: [], roleRefs: [...structuredClone(ordinary.roleRefs), { module, key: reader.role }] }, 'role-template');
      const member = await authority.account(h, 'observer-' + index);
      member.resource.scenarioDefinitionId = f.application.id;
      member.resource.scenarioInstallationIds = f.installations.map(i => String(i.id)); h.persist();
      await authority.assign(h, member, group, []);
      let revoked = false, epClientId, epCredId;
      try {
        const rows = await read(h, member.actor, context, reader.kind, true);
        h.check('Real emitted blocks produce nonempty ' + reader.kind + ' entries for exact instance', rows.length >= 1, rows);
        h.check('One observation role does not imply the other observation reader', denied(await read(h, member.actor, context, readers[1 - index].kind)));
        h.check('Exact observer role does not cross to the second installed instance', denied(await read(h, member.actor, peer, reader.kind)));
        if (h.tenantAdmin) {
          const cross = await runtimeRead(h.tenantAdmin, '/apps/application/' + reader.kind + '/?' + new URLSearchParams({ application: context.applicationKey, deploymentId: context.identity.deploymentId, pageNum: '1', pageSize: '100' }), context.identity, h.observe);
          h.check('Other tenant administrator cannot read panel observation target', !h.good(cross) && cross.data?.value == null, cross);
        }
        for (const method of ['POST', 'PUT', 'DELETE']) {
          const writeRes = await h.api(member.actor, method, '/apps/application/' + reader.kind + '/?' + new URLSearchParams({ application: context.applicationKey, deploymentId: context.identity.deploymentId }));
          h.check('Observation target rejects write method ' + method, !h.good(writeRes) && writeRes.data?.value == null, writeRes);
        }
        const data = await business.record(h, member.actor, { ...context, recordId: '1' });
        h.check('Observer-only account cannot read ordinary instance business data, even by guessed ID', denied(data), data);

        // Independent Endpoint OAuth token observation read + revocation.
        const epTpl = await h.create(base + 'role-templates/', { key: h.state.prefix + '-ep-observe-' + index, name: '端点观察只读', subjectType: 'endpoint', status: 2,
          applicationAccess: [], roleRefs: [{ module, key: reader.role }] }, 'role-template');
        const ep = await h.create(base + 'endpoints/', { name: h.state.prefix + '-ep-obs-' + index, description: '独立观察Endpoint', status: 2,
          account: { id: member.value.id }, roleTemplateKeys: [epTpl.key], scope: 'magicrunner.usage.apps.data.read', startTime: Date.now() - 1000, expireTime: Date.now() + 3600000 }, 'endpoint');
        const scopeOptions = (await h.ok(h.admin, 'GET', base + 'endpoints/' + ep.id + '/oauth-scope-options/')).values;
        const audiences = [...new Set(scopeOptions.filter(o => o.scope === 'magicrunner.usage.apps.data.read').flatMap(o => o.audiences || []))];
        h.check('Panel observation scope resolves exact Endpoint OAuth audience', audiences.length === 1, scopeOptions);
        const clientSpec = {
          name: h.state.prefix + '-ep-obs-client-' + index, developerName: '', clientType: 'confidential', partyType: 'first_party',
          authenticationNamespaces: ['panel'], redirectUris: [], grantTypes: ['client_credentials'],
          allowedScopes: 'magicrunner.usage.apps.data.read', scopeDescription: '应用观察读取', audience: audiences[0],
          requirePKCE: false, status: 1, description: '独立观察客户端', endpointId: ep.id,
        };
        const createdClient = (await h.ok(h.admin, 'POST', base + 'oauth/clients/', clientSpec)).value;
        epClientId = createdClient.clientId;
        const createdCred = (await h.ok(h.admin, 'POST', base + 'oauth/clients/' + encodeURIComponent(epClientId) + '/credentials/', { name: h.state.prefix + '-obs-secret-' + index, expiresAt: Date.now() + 1800000 })).value;
        epCredId = createdCred.id;
        const latestClient = (await h.ok(h.admin, 'GET', base + 'oauth/clients/' + encodeURIComponent(epClientId))).value;
        const updateSpec = {
          name: clientSpec.name, developerName: clientSpec.developerName, authenticationNamespaces: clientSpec.authenticationNamespaces,
          redirectUris: clientSpec.redirectUris, grantTypes: clientSpec.grantTypes, allowedScopes: clientSpec.allowedScopes,
          scopeDescription: clientSpec.scopeDescription, audience: clientSpec.audience, requirePKCE: clientSpec.requirePKCE,
          status: 2, description: clientSpec.description, endpointId: clientSpec.endpointId,
          expectedVersion: latestClient.version,
        };
        await h.ok(h.admin, 'PUT', base + 'oauth/clients/' + encodeURIComponent(epClientId), updateSpec);
        const tok = await h.protocol(h.admin, 'POST', '/api/v1/cas/oauth/token', {
          grant_type: 'client_credentials', client_id: epClientId, client_secret: createdCred.clientSecret,
          namespace: 'panel', client_namespace: 'panel', scope: 'magicrunner.usage.apps.data.read',
        });
        h.check('Observation Endpoint OAuth client receives Bearer token cleanly', tok.status === 200 && typeof tok.data?.access_token === 'string', tok);
        const obsRoute = '/apps/application/' + reader.kind + '/?' + new URLSearchParams({ application: context.applicationKey, deploymentId: context.identity.deploymentId, pageNum: '1', pageSize: '100' });
        const epRead = await bearerRead(h.admin.origin, obsRoute, context.identity, tok.data.access_token);
        h.check('Cookie-free Endpoint Bearer token reads exact emitted ' + reader.kind + ' entries', h.good(epRead) && epRead.data.value.values.length >= 1, epRead);
        validatePage(epRead.data.value, context.identity, reader.kind, 1, 100);
        const epWrongKind = await bearerRead(h.admin.origin, '/apps/application/' + readers[1 - index].kind + '/?' + new URLSearchParams({ application: context.applicationKey, deploymentId: context.identity.deploymentId, pageNum: '1', pageSize: '100' }), context.identity, tok.data.access_token);
        h.check('Endpoint token with one observer role is denied the other observer target', denied(epWrongKind), epWrongKind);
        const epWrongPeer = await bearerRead(h.admin.origin, '/apps/application/' + reader.kind + '/?' + new URLSearchParams({ application: peer.applicationKey, deploymentId: peer.identity.deploymentId, pageNum: '1', pageSize: '100' }), peer.identity, tok.data.access_token);
        h.check('Endpoint observation token cannot cross to peer installation', denied(epWrongPeer), epWrongPeer);
        await h.ok(h.admin, 'PUT', base + 'endpoints/' + ep.id + '/role-templates', { roleTemplateKeys: [] });
        const epRevoked = await bearerRead(h.admin.origin, obsRoute, context.identity, tok.data.access_token);
        h.check('Endpoint Bearer token loses observation read after role-template revocation', denied(epRevoked), epRevoked);

        await require('./business_action_cases.cjs').revoke(h, member, group, ordinary);
        revoked = true;
        h.check('Original logged-in observer loses the exact observation after current CAS role revocation', denied(await read(h, member.actor, context, reader.kind)));
      } finally {
        if (epClientId && epCredId) await h.api(h.admin, 'DELETE', base + 'oauth/clients/' + encodeURIComponent(epClientId) + '/credentials/' + epCredId).catch(() => {});
        if (epClientId) await h.api(h.admin, 'DELETE', base + 'oauth/clients/' + encodeURIComponent(epClientId)).catch(() => {});
        if (!revoked) await require('./business_action_cases.cjs').revoke(h, member, group, ordinary).catch(() => {});
      }
    }
  } catch (error) { primary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, f, primary); }
}
observations.transport = 'owner-api';
observations.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F006-004': observations }, validatePage, denied, readers, prepare, read };
