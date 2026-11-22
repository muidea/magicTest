const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const { command } = require('./service_scope_cases.cjs');
const contract = value => ({ apiVersion: value.apiVersion, version: value.version, digest: value.digest, operations: value.operations });
async function adminCommand(h, resource, method, route, body, confirm) {
  const pending = resource.pendingServiceCommands ||= [];
  if (pending.some(c => !c.confirmed)) throw new h.Blocked('Original service command is unresolved; do not replay');
  const c = { method, route, body: structuredClone(body), confirmed: false };
  pending.push(c); h.persist();
  c.response = await h.api(h.admin, method, route, body); h.persist();
  await confirm(c.response); c.confirmed = true; h.persist();
}
async function refuseDisabledSubscription(h, actor, f, owner) {
  const requestId = crypto.randomBytes(16).toString('hex');
  const before = await h.directory(owner, graph.subscriptions);
  const response = await h.api(actor, 'POST', '/portal/service/subscriptions/', { requestId, service: f.service.id, leaseTerm: 1 });
  const receipt = await h.api(actor, 'GET', '/portal/service/subscription-requests/' + requestId + '?service=' + f.service.id);
  const rejected = !h.good(response) && (receipt.status === 404 || receipt.data?.error?.code === 2 || receipt.data?.value?.phase === 'complete' && receipt.data.value.errorCode !== 0 && !receipt.data.value.subscriptionId);
  h.check('Disabled publication rejects new subscription request without creating a subscription', rejected && same(await h.directory(owner, graph.subscriptions), before), { response, receipt });
}
async function publishedCount(h, actor) {
  const value = (await h.ok(actor, 'GET', '/panel/profile')).value;
  const rows = (value.summary || []).filter(row => row.name === '服务发布');
  h.check('Management profile exposes single published service count', rows.length === 1 && Number.isInteger(rows[0].value) && rows[0].value >= 0, value);
  return rows[0]?.value ?? -1;
}
async function publication(h) {
  const owner = h.tenantAdmin, basePublished = await publishedCount(h, owner);
  const f = await graph.fixture(h, 'publication_availability'), s = await graph.subscribe(h, f), key = await graph.credential(h, s);
  h.check('Management overview counts newly published service', await publishedCount(h, owner) === basePublished + 1);
  const read = () => h.ok(owner, 'GET', graph.publications + f.publication.id).then(v => v.value);
  const serviceResource = h.state.resources.find(r => r.kind === 'service' && r.id === f.service.id);
  const resource = h.state.resources.find(r => r.kind === 'publication' && r.id === f.publication.id);
  const subscription = (await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value;
  const frozen = (await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value;
  const visible = async (actor, svc = f.service) => (await h.directory(actor, '/portal/services/')).filter(v => v.id === svc.id || (svc.showName && v.name === svc.showName));
  h.check('Independent portal collections expose publication only in its declared tenant', (await visible(h.user)).length === 1 && (await visible(h.otherTenantAdmin)).length === 0);
  await graph.succeeds(h, h.user, f, key);
  await command(h, resource, 'PUT', graph.publications + f.publication.id, { ...f.payload, status: 3 }, async result => {
    const current = await read();
    h.check('Formal disable and independent owner bind original publication, service and visibility', h.good(result) && current.id === f.publication.id &&
      current.service.id === f.service.id && current.status === 3 && current.visibleScope === owner.identity.namespace, result);
  });
  h.check('Disabled publication disappears from original and unrelated portal lists', (await visible(h.user)).length === 0 && (await visible(h.otherTenantAdmin)).length === 0);
  h.check('Management overview drops disabled publication from published count', await publishedCount(h, owner) === basePublished);
  const denied = await graph.call(h, h.user, f, key.apiKey);
  h.check('Existing exact subscription Key cannot reach real upstream after publication disable', [403, 404].includes(denied.status) &&
    !f.up.requests.some(v => v.marker === denied.marker), denied);
  await refuseDisabledSubscription(h, owner, f, owner);
  h.check('Publication stop preserves entire original subscription and credential owner facts', same((await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value, subscription));
  await command(h, resource, 'PUT', '/panel/hub/publication/publish/' + f.publication.id, {}, async result => {
    const current = await read();
    h.check('Formal re-publication reenables same original service and declared scope', h.good(result) && current.id === f.publication.id && current.status === 2 &&
      current.service.id === f.service.id && current.visibleScope === owner.identity.namespace, result);
  });
  h.check('Management overview restores republished service in published count', await publishedCount(h, owner) === basePublished + 1);
  h.check('Reenabled portal retains exact original frozen service contract', (await visible(h.user)).length === 1 &&
    same(contract((await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value), contract(frozen)));
  await graph.succeeds(h, h.user, f, key);
  h.check('Original subscription identity, lease and subject remain unchanged after restart', same((await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value, subscription));
  const peerNamespace = h.otherTenantAdmin.identity.namespace;
  await command(h, resource, 'PUT', graph.publications + f.publication.id, { ...f.payload, status: 2, visibleScope: peerNamespace }, async result => {
    const current = await read();
    h.check('Single-tenant admin cannot move publication outside verified namespace scope', !h.good(result) &&
      result.data?.error?.code === 5 && current.visibleScope === owner.identity.namespace, result);
  });
  const vis = await graph.fixture(h, 'publication_visibility', {}, 'admin');
  const visResource = h.state.resources.find(r => r.kind === 'publication' && r.id === vis.publication.id);
  const readVis = () => h.ok(h.admin, 'GET', graph.publications + vis.publication.id).then(v => v.value);
  h.check('Platform-owned publication in admin namespace is hidden from tenant portals initially',
    (await visible(h.user, vis.service)).length === 0 && (await visible(h.otherTenantAdmin, vis.service)).length === 0);
  await adminCommand(h, visResource, 'PUT', graph.publications + vis.publication.id, { ...vis.payload, status: 2, visibleScope: owner.identity.namespace }, async result => {
    const current = await readVis();
    h.check('Visibility scope edit exposes publication in original tenant namespace', h.good(result) && current.id === vis.publication.id && current.visibleScope === owner.identity.namespace, result);
  });
  h.check('Updated visibility scope exposes publication only to declared tenant portal',
    (await visible(h.user, vis.service)).length === 1 && (await visible(h.otherTenantAdmin, vis.service)).length === 0);
  h.check('Management overview excludes cross-tenant publication projections from tenant published count',
    await publishedCount(h, owner) === basePublished + 1);
  await adminCommand(h, visResource, 'PUT', graph.publications + vis.publication.id, { ...vis.payload, status: 2, visibleScope: peerNamespace }, async result => {
    const current = await readVis();
    h.check('Visibility scope edit moves publication to declared peer namespace', h.good(result) && current.id === vis.publication.id && current.visibleScope === peerNamespace, result);
  });
  h.check('Updated visibility scope switches portal listing to peer namespace',
    (await visible(h.user, vis.service)).length === 0 && (await visible(h.otherTenantAdmin, vis.service)).length === 1);
  await adminCommand(h, visResource, 'PUT', graph.publications + vis.publication.id, { ...vis.payload, status: 2, visibleScope: owner.identity.namespace }, async result => {
    const current = await readVis();
    h.check('Restoring visibility scope returns publication to original tenant namespace', h.good(result) && current.id === vis.publication.id && current.visibleScope === owner.identity.namespace, result);
  });
  h.check('Restored visibility scope restores portal listing in original namespace',
    (await visible(h.user, vis.service)).length === 1 && (await visible(h.otherTenantAdmin, vis.service)).length === 0);
  const currentService = (await h.ok(owner, 'GET', graph.services + f.service.id)).value;
  const draft = JSON.parse(currentService.options).contract;
  draft.version = '2'; draft.operations[0].upstreamPath = '/revised'; draft.operations[0].name = 'Revised controlled probe';
  await command(h, serviceResource, 'PUT', graph.services + f.service.id, { expectedServiceVersion: currentService.updateTime, options: JSON.stringify({ contract: draft }) }, async result => {
    h.check('Service draft replacement edit acknowledged without changing published contract', h.good(result) &&
      same(contract((await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value), contract(frozen)), result);
  });
  await graph.succeeds(h, h.user, f, key);
  await command(h, resource, 'PUT', graph.publications + f.publication.id, { ...f.payload, status: 3 }, async result => {
    h.check('Disable publication before republishing modified service draft', h.good(result) && (await read()).status === 3, result);
  });
  await command(h, resource, 'PUT', '/panel/hub/publication/publish/' + f.publication.id, {}, async result => {
    const current = await read(), nextContract = (await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value;
    h.check('Republish activates revised draft contract while keeping publication enabled', h.good(result) && current.status === 2 &&
      nextContract.version === '2' && nextContract.digest !== frozen.digest && nextContract.operations[0].name === draft.operations[0].name, { result, nextContract });
  });
  const revisedCall = await graph.call(h, h.user, f, key.apiKey), received = f.up.requests.filter(v => v.marker === revisedCall.marker);
  h.check('Existing valid subscription Key uses newly republished contract', revisedCall.status === 200 && revisedCall.data.marker === revisedCall.marker &&
    received.length === 1 && received[0].path === '/revised', { revisedCall, received });
  h.check('Republish preserves original subscription identity, lease and subject', same((await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value, subscription));
  await graph.retireCredential(h, key); await graph.retire(h, s);
}
publication.actors = ['admin', 'user', 'tenantAdmin', 'otherTenantAdmin']; publication.transport = 'owner-api';
module.exports = { handlers: { 'F040-001': publication } };
