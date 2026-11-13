const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const { command } = require('./service_scope_cases.cjs');
const contract = value => ({ apiVersion: value.apiVersion, version: value.version, digest: value.digest, operations: value.operations });
async function publication(h) {
  const f = await graph.fixture(h, 'publication_availability'), s = await graph.subscribe(h, f), key = await graph.credential(h, s);
  const owner = h.tenantAdmin, read = () => h.ok(owner, 'GET', graph.publications + f.publication.id).then(v => v.value);
  const resource = h.state.resources.find(r => r.kind === 'publication' && r.id === f.publication.id);
  const subscription = (await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value;
  const frozen = (await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value;
  const visible = async actor => (await h.directory(actor, '/portal/services/')).filter(v => v.id === f.service.id);
  h.check('Independent portal collections expose publication only in its declared tenant', (await visible(h.user)).length === 1 && (await visible(h.otherTenantAdmin)).length === 0);
  await graph.succeeds(h, h.user, f, key);
  await command(h, resource, 'PUT', graph.publications + f.publication.id, { ...f.payload, status: 3 }, async result => {
    const current = await read();
    h.check('Formal disable and independent owner bind original publication, service and visibility', h.good(result) && current.id === f.publication.id &&
      current.service.id === f.service.id && current.status === 3 && current.visibleScope === owner.identity.namespace, result);
  });
  h.check('Disabled publication disappears from original and unrelated portal lists', (await visible(h.user)).length === 0 && (await visible(h.otherTenantAdmin)).length === 0);
  const denied = await graph.call(h, h.user, f, key.apiKey);
  h.check('Existing exact subscription Key cannot reach real upstream after publication disable', [403, 404].includes(denied.status) &&
    !f.up.requests.some(v => v.marker === denied.marker), denied);
  h.check('Publication stop preserves entire original subscription and credential owner facts', same((await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value, subscription));
  await command(h, resource, 'PUT', '/panel/hub/publication/publish/' + f.publication.id, {}, async result => {
    const current = await read();
    h.check('Formal re-publication reenables same original service and declared scope', h.good(result) && current.id === f.publication.id && current.status === 2 &&
      current.service.id === f.service.id && current.visibleScope === owner.identity.namespace, result);
  });
  h.check('Reenabled portal retains exact original frozen service contract', (await visible(h.user)).length === 1 &&
    same(contract((await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value), contract(frozen)));
  await graph.succeeds(h, h.user, f, key);
  h.check('Original subscription identity, lease and subject remain unchanged after restart', same((await h.ok(owner, 'GET', graph.subscriptions + s.value.id)).value, subscription));
  await graph.retireCredential(h, key); await graph.retire(h, s);
  await h.partial('Tenant-scoped portal visibility, formal disable/re-publish, existing original Key upstream refusal/recovery, frozen interface and complete original subscription preservation implemented. Visibility edits, new-request refusal and draft replacement remain separate branches. Publication expiry remains the user-preserved capability gap; no invented expiry field.');
}
publication.actors = ['user', 'tenantAdmin', 'otherTenantAdmin']; publication.transport = 'owner-api';
module.exports = { handlers: { 'F040-001': publication } };
