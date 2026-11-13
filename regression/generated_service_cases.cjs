// Formal generated-service governance. Source capabilities remain owned by
// their installed application; the tool only edits its own service graph.
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const services = '/panel/hub/services/', bindings = '/panel/hub/serviceCapabilityBindings/', publications = '/panel/hub/publications/';
const capabilities = '/panel/hub/capabilitys/', convergeRoute = services + 'generated/converge/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(r => r.value);
const absent = r => [200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
const contract = m => ({ apiVersion: m.apiVersion, version: m.version, digest: m.digest, operations: m.operations });
async function snapshot(h) {
  const value = {};
  for (const route of [services, bindings, publications, capabilities]) value[route] = await h.directory(h.admin, route, { pageSize: 2 });
  return value;
}
function original(h, r) {
  if (r.kind !== 'generated-service-graph' || r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity) ||
      r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original generated-service command or owner unresolved; no repeat or guessed deletion');
}
function ownedSlice(all, id) {
  return { service: all[services].find(v => v.id === id), bindings: all[bindings].filter(v => v.service?.id === id), publications: all[publications].filter(v => v.service?.id === id) };
}
function confirms(value, observed, item, source) {
  const s = value?.service, p = value?.publication;
  return s?.id > 0 && s.key === item.service.key && s.name === item.service.name && s.namespace === 'panel' && s.providerType === 'application' && s.providerKey === source &&
    p?.id > 0 && p.service?.id === s.id && p.namespace === 'panel' && same(observed.service, s) &&
    observed.publications.length === 1 && same(observed.publications[0], p) &&
    value.bindings?.length === item.capabilityIDs.length && observed.bindings.length === item.capabilityIDs.length &&
    item.capabilityIDs.every((id, i) => value.bindings.some(b => b.capability?.id === id && b.service?.id === s.id && b.enabled === true && b.sort === i + 1 && observed.bindings.some(v => same(v, b))));
}
async function mutation(h, r, method, route, body, verify) {
  original(h, r);
  const c = { method, route, body: structuredClone(body), outcome: 'unknown' }; r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, method, route, body); h.persist();
  const all = await snapshot(h);
  await verify(c.response, all);
  c.outcome = 'confirmed'; if (r.serviceId) r.last = ownedSlice(all, r.serviceId); h.persist();
  return c.response.data;
}
function intent(h, key, ids, source) {
  const r = { kind: 'generated-service-graph', key, source, capabilityIDs: [...ids], phase: 'intent',
    origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), commands: [] };
  h.state.resources.push(r); h.persist(); return r;
}
function item(r, ids, label = '原始生成服务') {
  return { service: { key: r.key, name: r.key, showName: label, ...(r.last ? { expectedServiceVersion: r.last.service.updateTime } : {}) }, capabilityIDs: ids,
    publication: { status: 1, visibleScope: 'panel', allowSubscription: false, requireApproval: true, maxSubscriptions: 0, maxQPS: 0, dailyQuota: 0 } };
}
async function converge(h, r, ids, label) {
  const intended = item(r, ids, label);
  await mutation(h, r, 'POST', convergeRoute, { items: [intended] }, async (response, all) => {
    const values = response.data?.values;
    h.check('Original convergence has one acknowledged result independently confirmed by complete owner inventories', h.good(response) && values?.length === 1 && confirms(values[0], ownedSlice(all, values[0].service?.id), intended, r.source), response);
    r.serviceId = values[0].service.id; r.capabilityIDs = [...ids]; r.phase = 'created';
  });
  return r;
}
async function publish(h, r) {
  const id = r.last.publications[0].id;
  await mutation(h, r, 'PUT', '/panel/hub/publication/publish/' + id, {}, async (response, all) => {
    const p = all[publications].find(v => v.id === id);
    h.check('Formal publication freezes the exact owned generated service', h.good(response) && response.data.value?.id === id && p?.status === 2 && p.service?.id === r.serviceId && p.publishedTime > 0, response);
  });
  return contract(await read(h, '/panel/hub/service/debug/' + r.serviceId));
}
async function occupied(h, r, id) {
  const before = await snapshot(h), intended = item(r, [id]);
  original(h, r);
  const c = { method: 'POST', route: convergeRoute, body: { items: [intended] }, outcome: 'unknown' }; r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, c.method, c.route, c.body); h.persist();
  const after = await snapshot(h);
  const refused = [200, 400, 409].includes(c.response.status) && c.response.data?.error?.code === 7 && c.response.data.error.message === 'capability already belongs to another service' && c.response.data.value == null;
  if (refused && same(after, before)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Competing service reaches exact occupied-capability guard and preserves every complete owner directory', c.outcome === 'rejected-and-unchanged', c.response);
}
async function cleanup(h, r) {
  original(h, r);
  if (r.endpointScenarioAccountId != null && (h.state?.resources || []).some(child => child.serviceId === r.serviceId && child.phase !== 'deleted' && child.kind?.startsWith('service-graph-')))
    throw new h.Blocked('Original Endpoint scenario subscription or credential remains open; retain its service graph');
  if ((h.state?.resources || []).some(child => child.serviceId === r.serviceId && child.phase !== 'deleted' && child.endpointAuthorityCommands?.some(c => c.outcome === 'unknown'))) throw new h.Blocked('Original generated-service Endpoint authority remains unresolved; retain its graph');
  if (!r.serviceId) {
    if (!r.commands.length || !r.commands.every(c => c.outcome === 'rejected-and-unchanged') || (await snapshot(h))[services].some(v => v.key === r.key)) throw new h.Blocked('Original generated-service creation has no proven disposition');
    r.phase = 'deleted'; h.persist(); return { proof: 'Exact semantic refusal and complete owner inventory exclude the original service key; no DELETE issued.' };
  }
  const before = await snapshot(h);
  if (!same(ownedSlice(before, r.serviceId), r.last) || r.last.service?.key !== r.key || r.last.service?.providerKey !== r.source) throw new h.Blocked('Original owned generated service changed; no cascade retirement');
  if (r.deletion) throw new h.Blocked('Original service cascade DELETE unresolved; no replay');
  r.deletion = { method: 'DELETE', route: services + r.serviceId, outcome: 'unknown' }; h.persist();
  r.deletion.response = await h.api(h.admin, 'DELETE', r.deletion.route); h.persist();
  const after = await snapshot(h), exact = await h.api(h.admin, 'GET', r.deletion.route);
  h.check('Original public service cascade retirement is acknowledged and independently absent with all owned bindings/publications', h.good(r.deletion.response) && absent(exact) && !after[services].some(v => v.id === r.serviceId || v.key === r.key) && !after[bindings].some(v => v.service?.id === r.serviceId) && !after[publications].some(v => v.service?.id === r.serviceId), exact);
  h.check('Generated service retirement preserves the complete original source capability inventory', same(before[capabilities], after[capabilities]));
  r.deletion.outcome = 'confirmed'; r.phase = 'deleted'; h.persist();
  return { proof: 'Exact acknowledged public service DELETE and independent service/binding/publication absence; complete source capabilities unchanged. No private writes or source capability deletion.' };
}
async function governance(h) {
  const f = await fixture(h), before = await snapshot(h);
  const instance = await read(h, '/panel/application/installations/' + f.installations[0].id);
  h.check('Governance source is the exact original ready installed model', instance.status === 'ready' && instance.id === f.installations[0].id &&
    instance.deploymentId === f.installations[0].deploymentId && instance.sourceDigest === f.package.artifactDigest &&
    instance.receipt?.runtimeApplicationUuid === f.installations[0].receipt.runtimeApplicationUuid && instance.receipt.revisionId === f.revision.id);
  const source = instance.receipt.runtimeApplicationUuid;
  const available = before[capabilities].filter(c => c.providerType === 'application' && c.providerKey === source && c.status === 1);
  h.check('Complete source catalogue exceeds the explicitly exercised page budget', available.length > 2 && new Set(available.map(v => v.id)).size === available.length);
  const chosen = ['query', 'get'].map(kind => available.filter(c => c.kind === kind));
  h.check('Each desired read capability has one exact unoccupied source identity', chosen.every(rows => rows.length === 1 && !before[bindings].some(b => b.capability?.id === rows[0].id)));
  const ids = chosen.map(rows => rows[0].id), primary = intent(h, h.state.prefix + '_generated', ids, source), peer = intent(h, h.state.prefix + '_generated_peer', [ids[1]], source);
  h.check('New independent governance keys are absent before dispatch', !before[services].some(s => s.key === primary.key || s.key === peer.key));
  await converge(h, primary, ids);
  const first = structuredClone(primary.last);
  await converge(h, primary, ids, '同来源再次汇聚');
  h.check('Repeated same-source convergence reuses exact original service/publication/binding identities without duplicate children', primary.serviceId === first.service.id && primary.last.publications[0].id === first.publications[0].id && same(primary.last.bindings.map(v => v.id).sort(), first.bindings.map(v => v.id).sort()));
  const frozen = await publish(h, primary);
  await converge(h, primary, ids, '已发布服务展示更新');
  h.check('Same-source display edit leaves the original frozen execution contract intact', same(contract(await read(h, '/panel/hub/service/debug/' + primary.serviceId)), frozen));
  await occupied(h, peer, ids[1]);
  const p = primary.last.publications[0];
  await mutation(h, primary, 'PUT', publications + p.id, { ...item(primary, ids).publication, service: { id: primary.serviceId }, status: 3 }, async (response, all) => {
    h.check('Exact original generated publication is formally disabled', h.good(response) && all[publications].some(v => v.id === p.id && v.status === 3));
  });
  await occupied(h, peer, ids[1]);
  const released = primary.last.bindings.find(v => v.capability.id === ids[1]);
  await mutation(h, primary, 'DELETE', bindings + released.id, undefined, async (response, all) => {
    h.check('Formal disabled-publication unbind releases only the selected exact original capability', h.good(response) && !all[bindings].some(v => v.id === released.id) && all[bindings].some(v => v.service?.id === primary.serviceId && v.capability?.id === ids[0]));
  });
  await converge(h, primary, [ids[0]], '正式缩减后的服务');
  const next = await publish(h, primary);
  h.check('Explicit unbind/edit/republish produces the reduced frozen operation set with a new digest', frozen.operations.length === 2 && next.operations.length === 1 && next.digest !== frozen.digest && next.operations[0].key === available.find(v => v.id === ids[0]).key);
  await converge(h, peer, [ids[1]], '正式释放后的新服务'); await publish(h, peer);
  await cleanup(h, peer); await cleanup(h, primary);
  h.check('Complete governance lifecycle preserves original installed source and every capability', same(await read(h, '/panel/application/installations/' + instance.id), instance) && same((await snapshot(h))[capabilities], before[capabilities]));
}
governance.transport = 'owner-api';
module.exports = { handlers: { 'F038-001': governance }, confirms, original, cleanup, ownedSlice, snapshot, converge, publish, intent, mutation, capabilities, services, bindings, publications };
