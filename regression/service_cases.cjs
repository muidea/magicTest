const { isDeepStrictEqual: same } = require('node:util');
const collection = '/panel/hub/services/';
function externalService(prefix, suffix) {
  const address = 'https://regression.invalid/api';
  return { key: prefix + '_' + suffix, name: prefix + '_' + suffix, showName: '回归服务身份', description: '仅验证元数据，不调用上游', catalog: 'regression', providerType: 'external', providerKey: '', status: 2, accessMode: 'gateway', address,
    options: JSON.stringify({ debug: { authMode: 'bearer', operations: [{ key: 'probe', name: 'probe', method: 'GET', pathTemplate: address + '/probe', parameters: [] }] } }) };
}
async function serviceIdentity(h) {
  const actor = h.tenantAdmin;
  const original = await h.createAs('tenantAdmin', collection, externalService(h.state.prefix, 'identity'), 'service');
  const peer = await h.createAs('tenantAdmin', collection, externalService(h.state.prefix, 'peer'), 'service');
  const before = (await h.ok(actor, 'GET', collection + original.id)).value;
  const peerBefore = (await h.ok(actor, 'GET', collection + peer.id)).value;
  h.check('Identity test owns two different services in its exact tenant', before.id !== peerBefore.id && before.key !== peerBefore.key && before.namespace === actor.identity.namespace && peerBefore.namespace === actor.identity.namespace);
  const snapshots = [before, peerBefore];
  for (const mutation of [
    { method: 'POST', route: collection, body: { ...externalService(h.state.prefix, 'identity'), name: h.state.prefix + '_replacement', description: 'MUST NOT OVERWRITE' }, code: 7, diagnostic: /service key already exists/i },
    { method: 'PUT', route: collection + before.id, body: { expectedServiceVersion: before.updateTime, key: peerBefore.key, showName: 'MUST NOT OVERWRITE' }, code: 4, diagnostic: /service edit field is not writable: key/i }
  ]) {
    const priorRows = (await h.directory(actor, collection)).filter(r => snapshots.some(s => s.key === r.key));
    h.check('Complete directory contains only the two exact baseline identities', priorRows.length === 2 && snapshots.every(s => priorRows.some(r => same(r, s))), priorRows);
    const r = { kind: 'service-identity-attempt', collection, actor: 'tenantAdmin', actorIdentity: structuredClone(actor.identity), name: before.key, phase: 'intent', original: snapshots, intended: mutation, outcome: 'unknown' };
    h.state.resources.push(r); h.persist();
    const response = await h.api(actor, mutation.method, mutation.route, mutation.body);
    r.response = response; r.id = response.data?.value?.id; h.persist();
    const rows = (await h.directory(actor, collection)).filter(row => snapshots.some(s => s.key === row.key));
    const readbacks = [];
    for (const snapshot of snapshots) readbacks.push((await h.ok(actor, 'GET', collection + snapshot.id)).value);
    r.observed = { rows, readbacks }; h.persist();
    if (response.status === 401 || response.data?.error?.code === 11) throw new h.Blocked('AUTH-INVALID: service mutation did not reach identity validation');
    const rejected = [200, 400, 409, 422].includes(response.status) && response.data?.error?.code === mutation.code && mutation.diagnostic.test(response.data.error.message);
    const unchanged = rows.length === 2 && snapshots.every(s => rows.some(row => same(row, s))) && same(readbacks, snapshots);
    if (rejected && unchanged) { r.outcome = 'rejected-and-unchanged'; r.phase = 'deleted'; h.persist(); }
    h.check('Owner rejects service identity mutation at the declared validation stage', rejected, response);
    h.check('Independent owner reads preserve original and unrelated peer services', unchanged, r.observed);
  }
}
serviceIdentity.actors = ['tenantAdmin'];
async function serviceDisplay(h) {
  const f = await require('./delivery_cases.cjs').fixture(h);
  for (const kind of ['external', 'application']) {
    const body = externalService(h.state.prefix, 'display_' + kind);
    if (kind === 'application') Object.assign(body, { providerType: kind, providerKey: f.installations[0].receipt.runtimeApplicationUuid, address: '', options: '' });
    const value = await h.create(collection, body, 'service');
    const resource = h.state.resources.find(r => r.kind === 'service' && r.id === value.id);
    const before = (await h.ok(h.admin, 'GET', collection + value.id)).value;
    const intended = { expectedServiceVersion: before.updateTime, showName: '中文 服务 / 😀 ' + kind,
      description: '原始描述更新\nUnicode Δ', icon: 'RegressionIcon', catalog: '回归服务分类' };
    const command = { method: 'PUT', route: collection + value.id, body: intended, confirmed: false };
    resource.pendingServiceCommands = [command]; h.persist();
    command.response = await h.api(h.admin, 'PUT', command.route, intended); h.persist();
    const after = (await h.ok(h.admin, 'GET', command.route)).value;
    h.check('Formal internal and external service edits persist all display fields with unchanged source identity', h.good(command.response) && same(command.response.data.value, after) && after.updateTime > before.updateTime &&
      ['showName', 'description', 'icon', 'catalog'].every(k => after[k] === intended[k]) &&
      ['id', 'key', 'name', 'providerType', 'providerKey', 'namespace', 'ownerNamespace', 'sourceId', 'options', 'address', 'status', 'accessMode', 'createTime'].every(k => same(after[k], before[k])), after);
    command.confirmed = true; h.persist();
    const rejected = { method: 'PUT', route: command.route, body: { expectedServiceVersion: after.updateTime, key: h.state.prefix + '_forbidden_' + kind }, confirmed: false };
    resource.pendingServiceCommands.push(rejected); h.persist();
    rejected.response = await h.api(h.admin, rejected.method, rejected.route, rejected.body); h.persist();
    h.check('Identity replacement reaches explicit public command refusal for both service sources', rejected.response.status === 200 && rejected.response.data?.error?.code === 4 && /service edit field is not writable: key/.test(rejected.response.data.error.message) && same((await h.ok(h.admin, 'GET', command.route)).value, after), rejected.response);
    rejected.confirmed = true; h.persist();
    h.check('Complete service directory projects the exact changed display and fixed identity', (await h.directory(h.admin, collection)).some(row => same(row, after)));
  }
}
serviceDisplay.transport = 'owner-api';
const governance = '/panel/hub/services/generated/converge/';
const inventories = [collection, '/panel/hub/capabilitys/', '/panel/hub/serviceCapabilityBindings/', '/panel/hub/publications/'];
async function governanceSnapshot(h) {
  const result = {};
  for (const route of inventories) result[route] = await h.directory(h.admin, route);
  return result;
}
async function rejectOtherSource(h, snapshots, capability) {
  if (h.state.resources.some(r => r.kind === 'service-identity-attempt' && r.phase !== 'deleted' && r.original?.some(s => snapshots.some(v => v.id === s.id)))) throw new h.Blocked('Original governance command unresolved; no convergence replay');
  const before = await governanceSnapshot(h);
  h.check('Complete original governance directories contain exact owned service identities and real capability', snapshots.every(s => before[collection].some(row => same(row, s))) && before[inventories[1]].some(c => same(c, capability)));
  const original = snapshots[0];
  const r = { kind: 'service-identity-attempt', collection, phase: 'intent', outcome: 'unknown', name: original.key,
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, original: snapshots,
    intended: { method: 'POST', route: governance, body: { items: [{ service: { key: original.key, name: original.name, showName: 'MUST NOT OVERWRITE', expectedServiceVersion: original.updateTime },
      capabilityIDs: [capability.id], publication: { status: 1, visibleScope: 'panel', allowSubscription: false, requireApproval: true, maxSubscriptions: 0, maxQPS: 0, dailyQuota: 0 } }] } }, before };
  h.state.resources.push(r); h.persist();
  r.response = await h.api(h.admin, 'POST', governance, r.intended.body); h.persist();
  const after = await governanceSnapshot(h), readbacks = [];
  for (const s of snapshots) readbacks.push((await h.ok(h.admin, 'GET', collection + s.id)).value);
  r.observed = { after, readbacks }; h.persist();
  const rejected = r.response.status === 200 && r.response.data?.error?.code === 7 &&
    r.response.data.error.message === '服务标识 "' + original.key + '" 已被其他应用实例或治理来源使用，请为当前实例设置不同的服务标识';
  const unchanged = same(after, before) && same(readbacks, snapshots);
  if (rejected && unchanged) { r.outcome = 'rejected-and-unchanged'; r.phase = 'deleted'; h.persist(); }
  h.check('Original convergence reaches exact owner cross-source refusal instead of earlier authentication or field rejection', rejected, r.response);
  h.check('Independent complete owner inventories preserve original service, peer, capability, bindings and publications', unchanged, r.observed);
}
async function sourceConflict(h) {
  const f = await require('./delivery_cases.cjs').fixture(h);
  const instances = [];
  for (const i of f.installations) {
    const current = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value;
    h.check('Original fixture installation still identifies the exact ready runtime', current.id === i.id && current.deploymentId === i.deploymentId && current.status === 'ready' && current.receipt.runtimeApplicationUuid === i.receipt.runtimeApplicationUuid);
    instances.push(current);
  }
  const capabilities = await h.directory(h.admin, inventories[1]);
  const candidates = capabilities.filter(c => c.providerType === 'application' && c.providerKey === f.installations[0].receipt.runtimeApplicationUuid && c.kind === 'query' && c.status === 1);
  h.check('Source is one real enabled query capability of the exact formally installed first instance', candidates.length === 1, candidates);
  const source = candidates[0];
  const values = [];
  for (const suffix of ['source_conflict', 'source_peer']) {
    const value = await h.create(collection, externalService(h.state.prefix, suffix), 'service');
    values.push((await h.ok(h.admin, 'GET', collection + value.id)).value);
  }
  await rejectOtherSource(h, values, source);
  for (const i of instances) h.check('Governance refusal preserves both complete original installed instance facts', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
}
sourceConflict.transport = 'owner-api';
function scopedUnavailable(response) {
  return [200, 404].includes(response?.status) && response.data?.error?.code === 2 &&
    typeof response.data.error.message === 'string' && response.data.error.message.length > 0 && response.data.value == null;
}
async function allScopeSnapshots(h) {
  const result = {};
  for (const name of ['admin', 'tenantAdmin', 'otherTenantAdmin']) {
    result[name] = {};
    for (const route of inventories) result[name][route] = [...await h.directory(h[name], route)].sort((a, b) => a.id - b.id);
  }
  return result;
}
async function sourceScope(h) {
  if (h.state.resources.some(r => r.kind === 'service-identity-attempt' && r.phase !== 'deleted')) throw new h.Blocked('Original service governance intent remains unresolved; no new convergence scenario');
  const f = await require('./delivery_cases.cjs').fixture(h), installed = [], sources = [];
  const capabilities = await h.directory(h.admin, inventories[1]);
  for (const i of f.installations) {
    const value = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value;
    h.check('Scope negative uses a real independently ready original installed instance', value.id === i.id && value.status === 'ready' && value.deploymentId === i.deploymentId && value.receipt.runtimeApplicationUuid === i.receipt.runtimeApplicationUuid);
    installed.push(value);
    const candidates = capabilities.filter(c => c.providerType === 'application' && c.providerKey === value.receipt.runtimeApplicationUuid && c.kind === 'query' && c.status === 1);
    h.check('Each scope target has its exact actual enabled runtime query capability', candidates.length === 1, candidates);
    sources.push((await h.ok(h.admin, 'GET', inventories[1] + candidates[0].id)).value);
  }
  for (const [index, actorName] of ['tenantAdmin', 'otherTenantAdmin'].entries()) {
    const actor = h[actorName], source = sources[index];
    const positive = await h.createAs(actorName, collection, externalService(h.state.prefix, 'scope_positive_' + index), 'service');
    h.check('Original other-tenant manager positively owns service write authority in its own exact tenant',
      (await h.ok(actor, 'GET', collection + positive.id)).value.namespace === actor.identity.namespace && actor.identity.namespace !== h.admin.identity.namespace);
    const hidden = await h.api(actor, 'GET', inventories[1] + source.id);
    h.check('Existing original foreign capability is unavailable through the requester scoped owner read, not an authentication/dependency failure', scopedUnavailable(hidden), hidden);
    const before = await allScopeSnapshots(h), key = h.state.prefix + '_scope_forbidden_' + index;
    const r = { kind: 'service-identity-attempt', phase: 'intent', collection, actor: actorName, actorIdentity: structuredClone(actor.identity), origin: actor.origin,
      original: [source], name: key, before, outcome: 'unknown', intended: { method: 'POST', route: governance, body: { items: [{
        service: { key, name: key, showName: '不得汇聚其他租户实例' }, capabilityIDs: [source.id],
        publication: { status: 1, visibleScope: actor.identity.namespace, allowSubscription: false, requireApproval: true, maxSubscriptions: 0, maxQPS: 0, dailyQuota: 0 }
      }] } } };
    h.state.resources.push(r); h.persist(); r.response = await h.api(actor, 'POST', governance, r.intended.body); h.persist();
    const after = await allScopeSnapshots(h), session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
    const target = (await h.ok(h.admin, 'GET', inventories[1] + source.id)).value;
    const rejected = scopedUnavailable(r.response) && same(r.response.data.error, hidden.data.error);
    if (rejected && same(after, before) && same(target, source) && session.account.account === actor.identity.account && session.homeNamespace === actor.identity.namespace && session.activeNamespace === actor.identity.namespace) {
      r.outcome = 'rejected-and-unchanged'; r.phase = 'deleted'; h.persist();
    }
    h.check('Real convergence reaches the same exact scoped capability absence fence and preserves all source/requester/peer governance catalogs and original session', r.outcome === 'rejected-and-unchanged', r.response);
  }
  for (const value of installed) h.check('Both exact original installed instances remain completely unchanged after foreign aggregation attempts',
    same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + value.id)).value, value));
}
sourceScope.transport = 'owner-api'; sourceScope.actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers: { 'F037-003': serviceIdentity, 'F037-001': serviceDisplay, 'F038-002': sourceConflict, 'F038-003': sourceScope }, rejectOtherSource, scopedUnavailable };
