const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fixture, cleanupPreviewRequest } = require('./delivery_cases.cjs');
const { publisher, cleanup: cleanupPackage } = require('./native_provider_access_cases.cjs');
const { build } = require('./native_package_cases.cjs');
const { createResource } = require('./resource_lifecycle.cjs');
const base = '/panel/application/deployment-requests/';
const installations = '/panel/application/installations/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
function generated(value, namespace) {
  if (typeof value?.instanceKey !== 'string' || !/^[a-z][a-z0-9-]{30}[a-z0-9]$/.test(value.instanceKey) || typeof value.instanceName !== 'string' ||
      value.instanceName.trim() === '' || [...value.instanceName].length > 128 || /\p{Cc}/u.test(value.instanceName)) return false;
  const id = crypto.createHash('sha256').update('magic.application-instance/v1\0' + namespace + '\0' + value.instanceKey).digest('hex').slice(0, 32);
  return value.namespace === namespace && value.deploymentId === id;
}
function sourceMatches(value, sourceKind, pkg, expectedDigest) {
  return value.packageId === pkg.id && value.sourceKind === sourceKind && value.sourceDigest === pkg.packageDigest &&
    (sourceKind !== 'model-package' || expectedDigest === pkg.artifactDigest && value.modelPackage?.id === pkg.id &&
      value.modelPackage.artifactDigest === pkg.artifactDigest && value.modelPackage.packageDigest === pkg.packageDigest);
}
function original(h, r) {
  const spec = r.requester;
  if (!spec || !r.creation?.ownershipConfirmed || r.creation.outcome !== 'accepted' || !same(spec.identity, r.creation.actorIdentity) ||
      spec.origin !== r.creation.origin || typeof spec.password !== 'string' || !spec.password || r.commands?.some(c => c.outcome === 'unknown'))
    throw new h.Blocked('Original ordinary requester command/credential unresolved; no replacement principal or command replay');
  const accounts = h.state.resources.filter(a => a.kind === 'account' && a.id === spec.accountId && a.phase !== 'deleted' && a.creation?.ownershipConfirmed &&
    a.collection === '/cas/namespaces/' + spec.identity.namespace + '/accounts/' && a.creation.intended.account === spec.identity.account);
  if (accounts.length !== 1) throw new h.Blocked('Original ordinary requester account must remain for exact cleanup');
}
async function cleanup(h, r) {
  original(h, r);
  const spec = r.requester, account = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + spec.identity.namespace + '/accounts/' + spec.accountId)).value;
  h.check('Original requester remains an independently identifiable active CAS account', account.id === spec.accountId && account.account === spec.identity.account && account.status === 2);
  const actor = await h.login(spec.identity.account, spec.password, spec.identity.namespace), session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  h.check('Formal cleanup logs in the same exact original requester, never a substitute administrator', same(actor.identity, spec.identity) && actor.origin === spec.origin &&
    session.account.id === spec.accountId && session.account.account === spec.identity.account && session.homeNamespace === spec.identity.namespace && session.activeNamespace === spec.identity.namespace);
  const scoped = Object.create(h); scoped.admin = actor;
  if (!r.last) {
    const acknowledged = r.creation.response?.data?.value, current = (await h.ok(actor, 'GET', base + r.id)).value;
    h.check('Missing tool post-read is recovered only from exact original acknowledged submitted request and identical current owner',
      acknowledged?.id === r.id && acknowledged.status === 'submitted' && !acknowledged.operationId && same(current, acknowledged));
    r.last = current; h.persist();
  }
  return cleanupPreviewRequest(scoped, r);
}
async function automatic(h) {
  const f = await fixture(h), actor = await publisher(h), session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  const native = await build(h, { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-auto-request', releaseVersion: '1.0.0',
    contract: { apiVersion: 'magic.native-orchestration/v1', components: { api: { image: 'postgres:17.7-alpine3.22' } } } });
  const ownerBefore = { installations: await h.directory(h.admin, installations), operations: await h.directory(h.admin, operations) }, created = [];
  const requester = { identity: structuredClone(actor.identity), origin: actor.origin, accountId: session.account.id, password: actor.password };
  for (const [sourceKind, pkg, expectedDigest] of [['model-package', f.package, f.package.artifactDigest], ['deployment-package', native.package, native.package.packageDigest]]) {
    const body = { sourceKind, packageId: pkg.id, expectedDigest, reason: 'Verify automatic exact instance identity for ordinary requester' };
    if (sourceKind === 'model-package') body.storageProvisioning = { mode: 'allocate' };
    const recorder = Object.create(h);
    recorder.persist = () => {
      for (const resource of h.state.resources.filter(v => v.kind === 'requester-preview-request' && !v.requester && same(v.creation?.actorIdentity, actor.identity) && v.creation.origin === actor.origin)) {
        resource.requester = structuredClone(requester); resource.commands = [];
      }
      h.persist();
    };
    const value = await createResource(recorder, actor, 'installationRequester', base, body, 'requester-preview-request');
    const r = h.state.resources.find(v => v.kind === 'requester-preview-request' && v.id === value.id);
    r.last = (await h.ok(actor, 'GET', base + r.id)).value; h.persist();
    h.check('Ordinary model/native applicant omits instance identity and runtime selection; owner generates valid stable tenant-bound identity without execution',
      !['instanceKey', 'instanceName', 'deploymentId', 'runtimePlacement', 'executionInstanceId', 'gatewayInstanceId'].some(k => Object.hasOwn(r.creation.intended, k)) &&
      same(r.last, value) && generated(value, actor.identity.namespace) && value.status === 'submitted' && !value.operationId &&
      sourceMatches(value, sourceKind, pkg, expectedDigest) &&
      value.requestedBy?.namespace === actor.identity.namespace && value.requestedBy.accountId === session.account.id, value);
    h.check('Independent platform owner reads the exact ordinary requester and generated immutable request', same((await h.ok(h.admin, 'GET', base + r.id)).value, r.last));
    created.push(r);
  }
  h.check('Model and native automatic requests have distinct tenant-wide instance and deployment identities', created[0].last.instanceKey !== created[1].last.instanceKey && created[0].last.deploymentId !== created[1].last.deploymentId);
  h.check('Unapproved automatic applications create no operation or installation', same(await h.directory(h.admin, installations), ownerBefore.installations) && same(await h.directory(h.admin, operations), ownerBefore.operations));
  for (const r of created.reverse()) await cleanup(h, r);
  await cleanupPackage(h, native);
  h.check('Original model package and both original installations remain exact after ordinary requests and cancellation',
    same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + f.package.id)).value, f.package) &&
    same(await h.directory(h.admin, installations), ownerBefore.installations));
}
automatic.transport = 'owner-api';
module.exports = { handlers: { 'F027-001': automatic }, generated, sourceMatches, cleanup, original };
