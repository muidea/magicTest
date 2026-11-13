// Provider policy is owned by Panel; CAS owns the original author's roles.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const { packageContent } = require('./owner_transport.cjs');
const packages = '/panel/application/deployment-packages/';
const requests = '/panel/application/deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const installations = '/panel/application/installations/';
// Engine currently maps this exact InvalidAuthority owner result to HTTP401.
// Code/message and a separate live session check distinguish it from login.
const policyDenied = (r, message) => [200, 400, 401, 403].includes(r?.status) && r.data?.error?.code === 5 && r.data.error.message === message && r.data.value == null;
function providerPreview(preview, builtinKind, applicationUuid) {
  const expected = { magicBase: 'modelExecution', magicGateway: 'modelGateway' }[builtinKind];
  return !!expected && preview?.applicationUuid === applicationUuid && preview.applicationName === builtinKind &&
    preview.applicationType === 'internal' && preview.nativeContractVersion === 'magic.native-orchestration/v1' &&
    /^sha256:[a-f0-9]{64}$/.test(preview.buildDigest) && preview.components?.length === 1 &&
    preview.components[0].imageConfig?.platform?.application === builtinKind &&
    preview.components[0].imageConfig.platform.runtimeProviderKind === expected &&
    same(preview.imageConfig, preview.components[0].imageConfig) && preview.imageDigest === preview.components[0].imageDigest;
}
const read = (h, route) => h.ok(h.admin, 'GET', route).then(x => x.value);
async function snapshot(h) {
  const result = {};
  for (const route of [packages, requests, operations, installations]) result[route] = [...await h.directory(h.admin, route)].sort((a, b) => a.id - b.id);
  result.foreignPackages = [...await h.directory(h.tenantAdmin, packages)].sort((a, b) => a.id - b.id);
  result.foreignRequests = [...await h.directory(h.tenantAdmin, requests)].sort((a, b) => a.id - b.id);
  return result;
}
function original(h, r) {
  if (r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity) || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original native provider command unresolved or actor changed; no replay or guessed cleanup');
}
async function command(h, r, actor, method, route, body) {
  original(h, r);
  const c = { method, route, body, actorIdentity: structuredClone(actor.identity), origin: actor.origin, outcome: 'unknown' };
  r.commands.push(c); h.persist();
  c.response = await h.api(actor, method, route, body); h.persist(); return c;
}
async function reject(h, r, actor, method, route, body, message) {
  const before = await snapshot(h), c = await command(h, r, actor, method, route, body), after = await snapshot(h);
  const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  const authenticated = session.account?.account === actor.identity.account && session.homeNamespace === actor.identity.namespace && session.activeNamespace === actor.identity.namespace;
  if (policyDenied(c.response, message) && same(before, after) && authenticated) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Native provider command reaches exact namespace/governance owner fence with all package and delivery directories unchanged', c.outcome === 'rejected-and-unchanged', c.response);
}
async function cleanup(h, r) {
  if (r.scenarioCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original provider scenario command unresolved; retain its original journal');
  if (r.imports?.some(c => c.outcome !== 'confirmed')) throw new h.Blocked('Original native upload/import unresolved; retain exact package and File intent without replay');
  await reconcileBuild(h, r);
  await reconcilePreviewPolicy(h, r);
  original(h, r);
  if (!r.package) {
    if (r.commands.some(c => c.outcome !== 'rejected-and-unchanged')) throw new h.Blocked('Provider probe without a package lacks complete policy-only disposition');
    r.phase = 'deleted'; h.persist(); return { proof: 'All actual provider mutations have exact owner policy refusals and independently unchanged directories; no package registered.' };
  }
  require('./scenario_commands.cjs').guard(h, r);
  if (!r.packageAcknowledged || r.preexistingIds.includes(r.package.id) || r.package.applicationUuid !== r.applicationUuid) throw new h.Blocked('Native package ownership not independently established');
  const route = packages + r.package.id, current = await read(h, route);
  if (!same(current, r.package)) throw new h.Blocked('Original provider package changed; no guessed deletion');
  const preview = (await h.ok(h.admin, 'GET', route + '/cleanup-preview')).value;
  h.check('Original generated provider package has independently allowed reference cleanup', preview.allowed === true && preview.packageId === r.package.id && preview.sourceDigest === r.package.packageDigest, preview);
  const c = await command(h, r, h.admin, 'DELETE', route);
  h.check('Original generated package deletion acknowledged', h.good(c.response), c.response);
  const absent = await h.api(h.admin, 'GET', route);
  h.check('Independent exact owner and complete directory confirm generated provider package absence', [200, 404].includes(absent.status) && absent.data?.error?.code === 2 && absent.data.value == null && !(await h.directory(h.admin, packages)).some(v => v.id === r.package.id), absent);
  c.outcome = 'confirmed'; r.phase = 'deleted'; h.persist();
  return { proof: 'Original generated provider package formally removed after allowed cleanup; exact owner absence and complete directory. File release is acknowledged by Panel, no independent physical-byte absence claim.' };
}
// A successful build response is an original command receipt, even if a later
// tool assertion failed. Confirm that exact receipt; never rebuild as recovery.
async function reconcileBuild(h, r) {
  const pending = r.commands.filter(c => c.outcome === 'unknown');
  if (!pending.length || !r.package) return;
  if (pending.length !== 1 || r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity)) throw new h.Blocked('Original package build actor or pending command ambiguous');
  const c = pending[0], p = r.package;
  if (c.method !== 'POST' || c.route !== packages + 'builds/' || !h.good(c.response) || !same(c.response.data?.value, p) ||
      !same(c.actorIdentity, r.actorIdentity) || c.origin !== r.origin || !Number.isSafeInteger(p.id) || p.id <= 0 ||
      !Array.isArray(r.preexistingIds) || r.preexistingIds.includes(p.id) || p.applicationUuid !== r.applicationUuid ||
      c.body?.applicationUuid !== r.applicationUuid || p.packageDigest !== c.body.expectedBuildDigest ||
      p.releaseVersion !== c.body.releaseVersion || p.applicationName !== (c.body.builtinKind || c.body.applicationName)) throw new h.Blocked('Original build lacks exact acknowledged new-package binding; no replay');
  const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value;
  h.check('Original build receipt has exact current original actor provenance and independently identical package',
    session.account.account === r.actorIdentity.account && session.homeNamespace === r.actorIdentity.namespace &&
    p.uploadedBy?.namespace === session.homeNamespace && p.uploadedBy.accountId === session.account.id &&
    same(await read(h, packages + p.id), p));
  c.outcome = 'confirmed'; r.packageAcknowledged = true;
  c.disposition = { proof: 'Exact original successful build receipt, original pre-command directory and actor provenance independently confirmed. No build replay.' }; h.persist();
}
async function reconcilePreviewPolicy(h, r) {
  const pending = r.commands.filter(c => c.outcome === 'unknown');
  if (!pending.length) return;
  if (!same(r.actorIdentity, h.admin.identity) || r.origin !== h.admin.origin || r.package || pending.length !== 1) throw new h.Blocked('Original provider policy command unresolved; no replay');
  const c = pending[0], message = '运行提供方包要求系统运维或部署治理权限';
  if (c.method !== 'POST' || c.route !== packages + 'builds/preview' || !policyDenied(c.response, message) || !['magicBase', 'magicGateway'].includes(c.body?.builtinKind) || c.body.applicationUuid !== r.applicationUuid || c.actorIdentity?.namespace !== 'panel' || c.origin !== r.origin) throw new h.Blocked('Original provider preview lacks exact nonmutating policy-stage refusal; no replay');
  const accounts = h.state.resources.filter(v => v.kind === 'account' && v.creation?.ownershipConfirmed && v.collection === '/cas/namespaces/panel/accounts/' && v.creation.intended.account === c.actorIdentity.account && v.phase !== 'deleted');
  if (accounts.length !== 1) throw new h.Blocked('Exact original provider author account must remain for independent disposition');
  const account = await read(h, '/cas/namespaces/panel/accounts/' + accounts[0].id);
  h.check('Original nonmutating preview refusal is a current role boundary, with original active CAS author and no generated package', account.id === accounts[0].id && account.account === c.actorIdentity.account && account.status === 2 &&
    account.effectiveRoles?.some(v => v.module === '/modules/kernel/runner' && v.key === 'management-application-publisher') && !account.effectiveRoles.some(v => v.key.startsWith('operations-')) &&
    !(await h.directory(h.admin, packages)).some(v => v.applicationUuid === r.applicationUuid));
  c.disposition = { originalOutcome: c.outcome, proof: 'Exact original InvalidAuthority/code5 provider-governance refusal from nonmutating preview before normalization; independent original active CAS author/roles and generated-package absence. HTTP401 alone is not this proof. No preview or build replay, no original active-session claim.' };
  c.outcome = 'rejected-and-unchanged'; h.persist();
}
async function publisher(h) {
  const base = '/cas/namespaces/panel/', keys = ['management-application-publisher', 'management-namespace-application-operator'], keyPrefix = h.state.prefix + '-native-' + crypto.randomBytes(3).toString('hex');
  const roles = await h.directory(h.admin, base + 'roles/');
  h.check('Current owner catalog contains both human author/requester roles', keys.every(key => roles.some(v => v.key === key && v.module === '/modules/kernel/runner' && v.humanAssignable && v.status === 2)));
  const template = await h.create(base + 'role-templates/', { key: keyPrefix, name: '仅应用发布及申请', subjectType: 'account',
    roleRefs: keys.map(key => ({ module: '/modules/kernel/runner', key })), applicationAccess: [], status: 2 }, 'role-template');
  const account = await h.create(base + 'accounts/', { account: keyPrefix, displayName: '普通原生作者', password: h.state.password,
    status: 2, roleTemplateKeys: ['portal-basic-user', template.key] }, 'account');
  const actor = await h.login(account.account, h.state.password, 'panel', h.state.password + 'N');
  const current = await read(h, base + 'accounts/' + account.id);
  h.check('Independent CAS confirms original default-space author has publisher/requester roles and no operations role', actor.identity.namespace === 'panel' && actor.identity.account === account.account &&
    keys.every(key => current.effectiveRoles?.some(v => v.module === '/modules/kernel/runner' && v.key === key)) && current.effectiveRoles.every(v => !v.key.startsWith('operations-')));
  return actor;
}
async function restricted(h) {
  const f = await fixture(h), actor = await publisher(h), beforePeers = [];
  for (const v of f.installations) beforePeers.push(await read(h, installations + v.id));
  let r = { kind: 'native-provider-probe', phase: 'created', origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), commands: [], applicationUuid: crypto.randomBytes(16).toString('hex') };
  h.state.resources.push(r); h.persist();
  try {
    const ordinary = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-ordinary-native', releaseVersion: '1.0.0',
      contract: { apiVersion: 'magic.native-orchestration/v1', components: { api: { image: 'postgres:17.7-alpine3.22' } } } };
    for (const principal of [actor, h.tenantAdmin]) {
      const value = (await h.ok(principal, 'POST', packages + 'builds/preview', ordinary)).value;
      h.check('Ordinary native author reaches positive real component preflight without operations privilege', value.applicationUuid === ordinary.applicationUuid && value.components?.length === 1 && /^sha256:[a-f0-9]{64}$/.test(value.buildDigest));
    }
    for (const builtinKind of ['magicBase', 'magicGateway']) {
      const body = { builtinKind, applicationUuid: r.applicationUuid, releaseVersion: '1.0.0' };
      for (const [principal, message] of [[actor, '运行提供方包要求系统运维或部署治理权限'], [h.tenantAdmin, '运行提供方包仅允许在 default namespace 管理']]) {
        await reject(h, r, principal, 'POST', packages + 'builds/preview', body, message);
        // Nonempty confirmation permits the actual build command to reach the
        // policy fence. It is deliberately not claimed as a valid build digest.
        await reject(h, r, principal, 'POST', packages + 'builds/', { ...body, expectedBuildDigest: 'sha256:' + '0'.repeat(64) }, message);
      }
    }
    await cleanup(h, r);
    for (const builtinKind of ['magicBase', 'magicGateway']) {
      r = { kind: 'native-provider-probe', phase: 'created', origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), commands: [], applicationUuid: crypto.randomBytes(16).toString('hex') };
      h.state.resources.push(r); h.persist();
      const input = { builtinKind, applicationUuid: r.applicationUuid, releaseVersion: '1.0.0' };
      const positive = await h.api(h.admin, 'POST', packages + 'builds/preview', input);
      if (!h.good(positive)) { h.observe({ kind: 'provider-package-positive-prerequisite', response: positive }); await h.partial('Both provider kinds enforce namespace/governance before build, and ordinary authors retain native preflight. Actual provider package query/request/delete still requires matching existing builtin image/config positive preflight.'); }
      const preview = positive.data.value;
      h.check('Authorized provider positive preflight binds maintained provider contract', providerPreview(preview, builtinKind, r.applicationUuid), preview);
      r.preexistingIds = (await h.directory(h.admin, packages)).map(v => v.id); h.persist();
      const c = await command(h, r, h.admin, 'POST', packages + 'builds/', { ...input, expectedBuildDigest: preview.buildDigest });
      r.package = c.response.data?.value; h.persist();
      h.check('Authorized original provider build returns new exact immutable package', h.good(c.response) && r.package?.applicationUuid === r.applicationUuid && r.package.uploadedBy?.namespace === h.admin.identity.namespace && !r.preexistingIds.includes(r.package.id) && r.package.packageDigest === preview.buildDigest, c.response);
      h.check('Independent exact public package read confirms original generated package', same(await read(h, packages + r.package.id), r.package));
      c.outcome = 'confirmed'; r.packageAcknowledged = true; h.persist();
      const route = packages + r.package.id, bytes = await packageContent(h.admin, route + '/content', h.observe);
      h.check('Authorized positive provider package has real ZIP content', bytes.status === 200 && Buffer.isBuffer(bytes.data.bytes) && bytes.data.bytes.length > 0);
      const message = '运行提供方包要求系统运维或部署治理权限';
      for (const suffix of ['', '/content', '/cleanup-preview']) await reject(h, r, actor, 'GET', route + suffix, undefined, message);
      await reject(h, r, actor, 'DELETE', route, undefined, message);
      await reject(h, r, actor, 'POST', requests, { sourceKind: 'deployment-package', packageId: r.package.id, expectedDigest: r.package.packageDigest,
        instanceKey: h.state.prefix + '-forbidden-provider', instanceName: '不得安装内置提供方', runtimeNamespaces: ['panel'], reason: 'Verify native provider request governance fence' }, message);
      const after = await packageContent(h.admin, route + '/content', h.observe);
      h.check('Every forbidden provider operation preserves exact original ZIP bytes and package', after.status === 200 && Buffer.isBuffer(after.data.bytes) && after.data.bytes.equals(bytes.data.bytes) && same(await read(h, route), r.package));
      await cleanup(h, r);
    }
    for (const [i, v] of f.installations.entries()) h.check('Provider negative probes preserve unrelated original installed instance', same(await read(h, installations + v.id), beforePeers[i]));
  } finally { if (r.phase !== 'deleted') await cleanup(h, r); }
}
async function admission(h) {
  const f = await fixture(h), r = { kind: 'native-provider-probe', phase: 'created', origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), commands: [] };
  h.state.resources.push(r); h.persist();
  try {
    const session = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
    h.check('Original tenant requester starts inside its exact own tenant, outside the requested platform target', session.homeNamespace === h.tenantAdmin.identity.namespace && session.activeNamespace === session.homeNamespace && session.homeNamespace !== 'panel');
    await reject(h, r, h.tenantAdmin, 'PUT', '/api/v1/web/session/namespace', { namespace: 'panel' }, 'target namespace is outside the session management scope');
    const afterSession = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
    h.check('Unauthorized target selection preserves original account, home/active namespace and context version', afterSession.account.id === session.account.id && afterSession.homeNamespace === session.homeNamespace && afterSession.activeNamespace === session.activeNamespace && afterSession.contextVersion === session.contextVersion);
    const before = await snapshot(h), wrongDigest = 'sha256:' + (f.package.artifactDigest === 'sha256:' + '0'.repeat(64) ? '1' : '0').repeat(64);
    const c = await command(h, r, h.admin, 'POST', requests, { sourceKind: 'model-package', packageId: f.package.id, expectedDigest: wrongDigest,
      instanceKey: h.state.prefix + '-invalid-binding', instanceName: '不可替换原制品摘要', storageProvisioning: { mode: 'allocate' }, reason: 'Verify exact immutable installation package binding' });
    if ([200, 400, 409].includes(c.response.status) && c.response.data?.error?.code === 19 && c.response.data.error.message === 'model installation package binding is invalid' && c.response.data.value == null && same(await snapshot(h), before)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
    h.check('Altered installation digest reaches exact owner binding fence without any request, operation or installation', c.outcome === 'rejected-and-unchanged', c.response);
    h.check('Wrong digest preserves immutable original model package', same(await read(h, '/panel/application/model-packages/' + f.package.id), f.package));
  } finally { await cleanup(h, r); }
  // The forbidden builtin path must use real valid packages, not guessed IDs
  // that could be rejected before the provider authorization fence.
  await restricted(h);
}
restricted.transport = 'owner-api'; restricted.actors = ['tenantAdmin'];
admission.transport = 'owner-api'; admission.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F025-002': restricted, 'F027-002': admission }, policyDenied, providerPreview, original, cleanup, reconcileBuild, publisher };
