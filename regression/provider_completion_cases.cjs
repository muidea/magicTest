const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const provider = require('./native_provider_access_cases.cjs');
const { packageContent } = require('./owner_transport.cjs');
const { archive } = require('./native_package_cases.cjs');
const packages = '/panel/application/deployment-packages/';
async function build(h, builtinKind) {
  await require('./delivery_cases.cjs').fixture(h);
  const input = { builtinKind, applicationUuid: crypto.randomBytes(16).toString('hex'), releaseVersion: '1.0.0' };
  const before = await h.directory(h.admin, packages), preview = (await h.ok(h.admin, 'POST', packages + 'builds/preview', input)).value;
  h.check('Maintained provider preflight resolves exact current image/config and initial startup contract', provider.providerPreview(preview, builtinKind, input.applicationUuid), preview);
  const r = { kind: 'native-provider-probe', phase: 'intent', origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
    applicationUuid: input.applicationUuid, commands: [], preexistingIds: before.map(v => v.id) };
  h.state.resources.push(r); h.persist();
  const c = { method: 'POST', route: packages + 'builds/', body: { ...input, expectedBuildDigest: preview.buildDigest }, origin: h.admin.origin,
    actorIdentity: structuredClone(h.admin.identity), outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, c.method, c.route, c.body); r.package = c.response.data?.value; h.persist();
  await provider.reconcileBuild(h, r);
  h.check('Built provider package is the exact new independently confirmed immutable owner resource', r.packageAcknowledged === true && c.outcome === 'confirmed');
  r.phase = 'created'; h.persist();
  const response = await packageContent(h.admin, packages + r.package.id + '/content', h.observe);
  h.check('Provider download is a real complete original ZIP', response.status === 200 && Buffer.isBuffer(response.data.bytes));
  const files = archive(response.data.bytes), runtime = files['deployment/native-runtime.json'];
  const kind = builtinKind === 'magicBase' ? 'modelExecution' : 'modelGateway', component = builtinKind === 'magicBase' ? 'base' : 'gateway';
  h.check('Frozen provider runtime consumes only maintained runtime startup, exact component image and owned data mount',
    runtime.apiVersion === 'magic.native-runtime/v1' && runtime.applicationRef.uuid === input.applicationUuid &&
    runtime.runtimeProvider?.kind === kind && runtime.runtimeProvider.componentRef === component && runtime.runtimeProvider.startupContract === 'magic.runtime-startup/v1' &&
    runtime.components.length === 1 && runtime.components[0].key === component && runtime.components[0].image?.digest === preview.components[0].imageDigest, runtime);
  return r;
}
async function builtins(h) {
  for (const kind of ['magicBase', 'magicGateway']) {
    const r = await build(h, kind);
    await provider.cleanup(h, r);
  }
  await h.partial('Both maintained provider image/config preflights, exact original immutable package builds, frozen startup identity and formal package cleanup implemented. Actual provider deployment, owner-ready and absence of bootstrap replay remain open.');
}
async function scopes(h) {
  const r = await build(h, 'magicBase'), requests = '/panel/application/deployment-requests/';
  const commands = require('./scenario_commands.cjs');
  try {
    const body = { sourceKind: 'deployment-package', packageId: r.package.id, expectedDigest: r.package.packageDigest,
      instanceKey: h.state.prefix + '-scope-probe', instanceName: '受控提供方范围', reason: 'Verify exact provider scope request admission' };
    for (const [runtimeNamespaces, message] of [[[], '运行提供方必须声明服务空间范围'], [['panel', 'panel'], '服务空间范围无效，不能混用全局范围、重复或空空间'], [['*', 'panel'], '服务空间范围无效，不能混用全局范围、重复或空空间']]) {
      await commands.reject(h, r, h.admin, 'POST', requests, { ...body, runtimeNamespaces }, [packages + r.package.id, requests], { code: 4, message });
    }
    for (const [index, namespaces] of [['single', ['panel']], ['multi', ['panel', h.tenantAdmin.identity.namespace]], ['global', ['*']]]) {
      const before = await h.directory(h.admin, '/panel/application/installations/');
      const value = await h.create(requests, { ...body, instanceKey: h.state.prefix + '-scope-' + index, runtimeNamespaces: namespaces }, 'package-preview-request');
      const resource = h.state.resources.find(v => v.kind === 'package-preview-request' && v.id === value.id);
      resource.commands = []; resource.last = (await h.ok(h.admin, 'GET', requests + value.id)).value; h.persist();
      h.check('Formal scope request freezes exact declared service range without executing an installation',
        same(resource.last, value) && value.status === 'submitted' && !value.operationId && value.runtimeNamespaceScope === [...namespaces].sort().join(',') &&
        same(await h.directory(h.admin, '/panel/application/installations/'), before), value);
      await require('./delivery_cases.cjs').cleanupPreviewRequest(h, resource);
    }
    await provider.cleanup(h, r);
  } catch (error) { h.observe({ kind: 'provider-scope-open', packageId: r.package.id, message: error.message }); throw error; }
  await h.partial('Single/multi/global provider request scope freeze, empty/duplicate/mixed-global refusal and original cancellation/cleanup implemented. Actual deployments, model dispatch and cross-scope runtime refusal remain open.');
}
const handlers = { 'F025-001': builtins, 'F025-003': scopes };
for (const fn of Object.values(handlers)) fn.transport = 'owner-api';
scopes.actors = ['tenantAdmin'];
module.exports = { handlers, build };
