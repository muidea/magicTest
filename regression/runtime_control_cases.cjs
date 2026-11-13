const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const { registryUnchanged } = require('./runtime_placement_cases.cjs');
const machine = require('./runtime_machine_transport.cjs');
const instances = '/panel/operations/runtime-placements/instances/';
const policies = '/panel/operations/runtime-placements/policies/';
const ordered = values => [...values].sort((a, b) => a.id.localeCompare(b.id));
async function registry(h) {
  const rows = (await h.ok(h.admin, 'GET', instances)).values;
  h.check('Runtime registry is a complete unique bounded inventory', Array.isArray(rows) && rows.length > 0 && new Set(rows.map(r => r.id)).size === rows.length);
  return ordered(rows);
}
async function policyRows(h) {
  const rows = (await h.ok(h.admin, 'GET', policies)).values;
  h.check('Runtime policy owner supplies its entire unique inventory', Array.isArray(rows) && rows.length > 0 && new Set(rows.map(r => r.id)).size === rows.length && rows.every(r => Number.isSafeInteger(r.version) && r.version > 0));
  return ordered(rows);
}
function actorBound(h, r) {
  if (!same(r.actorIdentity, h.admin.identity) || r.origin !== h.admin.origin) throw new h.Blocked('Original runtime policy actor or origin changed');
}
function original(h, r) {
  actorBound(h, r);
  if (r.commands.some(c => c.confirmed !== true)) throw new h.Blocked('Original runtime policy command unresolved; no replacement write or guessed rollback');
}
async function policyCommand(h, r, body, refusal) {
  original(h, r);
  const intended = r.before.find(p => p.id === r.policyId), last = r.last.find(p => p.id === r.policyId);
  const stale = 'runtime placement policy changed', wrongKind = 'runtime instance kind or namespace admission does not match';
  if (!intended || !last || ![undefined, stale, wrongKind].includes(refusal) ||
      !same(Object.keys(body).sort(), ['executionInstanceId', 'expectedVersion', 'gatewayInstanceId', 'targetNamespace']) ||
      body.targetNamespace !== intended.targetNamespace || body.executionInstanceId !== intended.executionInstanceId ||
      body.gatewayInstanceId !== (refusal === wrongKind ? intended.executionInstanceId : intended.gatewayInstanceId) ||
      body.expectedVersion !== (refusal === stale ? intended.version : last.version))
    throw new h.Blocked('Only original same-target conditional policy and finite version/kind probes are allowed');
  const before = await policyRows(h);
  if (!same(before, r.last)) throw new h.Blocked('Runtime policy inventory changed concurrently; do not overwrite');
  actorBound(h, r);
  const c = { method: 'POST', route: policies, body: structuredClone(body), before, refusal, confirmed: false };
  r.commands.push(c); h.persist();
  try { c.response = await h.api(h.admin, 'POST', policies, body); }
  catch (error) { c.transportError = String(error.message).slice(0, 1000); h.persist(); throw error; }
  h.persist(); c.after = await policyRows(h); h.persist(); actorBound(h, r);
  if (refusal) h.check('Original rejected policy command reaches exact version/kind guard and leaves all policies unchanged',
    [200, 400, 409, 403].includes(c.response.status) && c.response.data?.value == null && c.response.data?.error?.message === refusal && c.response.data.error.code > 0 && same(c.after, before), c);
  else {
    const old = before.find(p => p.id === r.policyId), current = c.after.find(p => p.id === r.policyId);
    h.check('Formal policy same-target conditional write preserves every semantic field and advances only its owner revision',
      h.good(c.response) && same(c.response.data.value, current) && current?.version === old.version + 1 && Number.isSafeInteger(current.updateTime) && current.updateTime >= old.updateTime &&
      same({ ...current, version: old.version, updateTime: old.updateTime }, old) && c.after.length === before.length &&
      before.filter(p => p.id !== old.id).every(p => same(c.after.find(a => a.id === p.id), p)), c);
  }
  c.confirmed = true; r.last = c.after; h.persist(); return c;
}
async function cleanupPolicy(h, r) {
  original(h, r);
  h.check('Original policy semantic state is independently preserved; legitimate owner revisions are retained',
    same(await policyRows(h), r.last) && r.last.length === r.before.length && r.before.every(p => {
      const current = r.last.find(v => v.id === p.id);
      return current && same({ ...current, version: p.version, updateTime: p.updateTime }, p);
    }) && registryUnchanged(r.inventory, await registry(h)));
  for (const i of r.installations) h.check('Original frozen installation remains unchanged at policy journal closure',
    same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
  original(h, r); r.phase = 'deleted'; h.persist();
  return { proof: 'No policy was created/deleted or target changed; exact acknowledged revision and original registry independently preserved. No rollback or command replay.' };
}
async function policy(h) {
  const f = await fixture(h), inventory = await registry(h), before = await policyRows(h), defaults = before.filter(p => p.targetNamespace === '');
  if (defaults.length !== 1) throw new h.Blocked('One exact pre-existing platform default policy is required');
  const p = defaults[0];
  h.check('Original policy targets actual registered Base and Gateway identities', ['base', 'gateway'].every(kind => inventory.some(i => i.id === p[kind === 'base' ? 'executionInstanceId' : 'gatewayInstanceId'] && i.kind === kind && i.status === 'registered' && i.namespaceScope === '*')));
  const installations = [];
  for (const i of f.installations) installations.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value);
  const r = { kind: 'runtime-policy-probe', id: crypto.randomBytes(16).toString('hex'), collection: policies, actorIdentity: structuredClone(h.admin.identity),
    origin: h.admin.origin, policyId: p.id, phase: 'created', before, last: before, inventory, installations, commands: [] };
  h.state.resources.push(r); h.persist();
  const body = { targetNamespace: p.targetNamespace, gatewayInstanceId: p.gatewayInstanceId, executionInstanceId: p.executionInstanceId, expectedVersion: p.version };
  await policyCommand(h, r, body);
  await policyCommand(h, r, body, 'runtime placement policy changed');
  await policyCommand(h, r, { ...body, expectedVersion: p.version + 1, gatewayInstanceId: p.executionInstanceId }, 'runtime instance kind or namespace admission does not match');
  for (const i of installations) h.check('Default policy revision does not rewrite an original installation or its frozen receipt', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
  h.observe({ kind: 'runtime-policy-conditional-owner-proof', journal: r });
  await cleanupPolicy(h, r);
  await h.partial('Isolated original default policy same-target conditional write, stale version and wrong-kind refusal; complete policy/registry and original installation receipts retained. No policy creation or target change. Actual default resolution at a new approval and two-Base/Gateway handoff, drain/revoke/recover and live new business execution remain uncovered.');
}
function binding(h, c, inventory) {
  const rows = inventory.filter(i => i.id === c.instanceId);
  h.check('Independently read Gateway registry retains exact original machine credential and incarnation', rows.length === 1 && rows[0].kind === 'gateway' && rows[0].status === 'registered' &&
    rows[0].incarnation === c.incarnation && rows[0].credentialEndpointId === c.endpointId && rows[0].credentialClientId === c.clientId && Number.isSafeInteger(rows[0].snapshotVersion) && rows[0].snapshotVersion > 0, rows);
  return rows[0];
}
function snapshotProof(h, result, c, inventory, known) {
  const s = result.data?.value, instance = binding(h, c, inventory);
  h.check('Real machine receives a bounded complete original Gateway snapshot with a fresh lease', result.status === 200 && result.data?.error == null &&
    result.contentType.split(';')[0] === 'application/json' && result.cacheControl.includes('no-store') && Number.isSafeInteger(result.byteLength) && result.byteLength > 0 && result.byteLength <= machine.limit &&
    s?.apiVersion === 'magic.gateway-assignment-snapshot/v1' && same(s.gateway, { instanceId: c.instanceId, incarnation: c.incarnation }) &&
    s.complete === true && Array.isArray(s.assignments) && s.assignments.length <= 10000 && Number.isSafeInteger(s.version) && s.version > 0 && s.version <= instance.snapshotVersion &&
    Number.isSafeInteger(s.issuedAt) && s.issuedAt > 0 && s.issuedAt <= Date.now() && Number.isSafeInteger(s.expiresAt) && s.expiresAt > Date.now() && s.expiresAt > s.issuedAt && s.expiresAt - s.issuedAt <= 30000, { ...result, data: { value: { ...s, assignments: s?.assignments?.length } } });
  const keys = s.assignments.map(r => r.target?.namespace + '\0' + r.target?.deploymentId);
  h.check('Machine snapshot carries distinct tenant/deployment rows and lossless known fixture identities',
    s.assignments.every(r => typeof r.target?.namespace === 'string' && r.target.namespace && typeof r.target.deploymentId === 'string' && r.target.deploymentId) &&
    new Set(keys).size === keys.length && known.length >= 2 && known.every(i => {
      const rows = s.assignments.filter(r => r.target?.installationId === i.id && r.target?.deploymentId === i.deploymentId && r.target?.namespace === i.namespace);
      return rows.length === 1 && rows[0].target.runtimeApplicationUuid === i.receipt.runtimeApplicationUuid && rows[0].target.revisionDigest === i.sourceDigest;
    }), { keys, known: known.map(i => i.id) });
  return s;
}
async function snapshots(h) {
  if (!h.runtimeSnapshotConfig) throw new h.Blocked('Private runtimeSnapshotConfig and original deployment-issued Gateway bearer file required');
  const c = machine.loadConfig(h.runtimeSnapshotConfig), f = await fixture(h), before = await registry(h);
  binding(h, c, before);
  const known = [];
  for (const i of f.installations) known.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value);
  const business = require('./business_cases.cjs'), { collection } = require('./business_collection_cases.cjs'), actor = await business.member(h, 'manager'), contexts = [], rows = [];
  for (let index = 0; index < known.length; index++) {
    contexts.push(await business.runtime(h, f, index, actor));
    rows.push(await collection(h, actor, contexts[index]));
  }
  const first = await machine.getSnapshot(c); h.observe({ kind: 'actual-machine-snapshot', configDigest: c.configDigest, instanceId: c.instanceId, response: first });
  snapshotProof(h, first, c, await registry(h), known);
  for (const query of ['?_pageSize=1', '?namespace=panel', '?instanceId=' + encodeURIComponent(c.instanceId)]) {
    const r = await machine.getSnapshot(c, query); h.observe({ kind: 'actual-machine-query-refusal', instanceId: c.instanceId, query, response: r });
    h.check('Real authenticated machine query reaches complete-snapshot selector refusal', r.status === 200 && r.data?.value == null && r.data?.error?.code > 0 && r.data.error.message === 'execution snapshot does not accept query parameters', r);
  }
  const second = await machine.getSnapshot(c), after = await registry(h); snapshotProof(h, second, c, after, known);
  h.check('Machine reads retain original registry configuration and monotone snapshot cursor', registryUnchanged(before, after) && second.data.value.version >= first.data.value.version);
  for (let index = 0; index < known.length; index++) {
    const current = await business.runtime(h, f, index, actor);
    h.check('Original ordinary runtime reads retain exact Gateway snapshot execution fences', second.data.value.assignments.some(r =>
      r.target.installationId === known[index].id && r.target.generation === current.identity.generation && r.target.executionEpoch === current.identity.executionEpoch));
    h.check('Real routed ordinary owner collection and runtime identity remain unchanged', same(current.identity, contexts[index].identity) && same(await collection(h, actor, current), rows[index]));
    h.check('Actual machine reads preserve exact independent original installation', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + known[index].id)).value, known[index]));
  }
  h.observe({ kind: 'machine-snapshot-known-owner-proof', configDigest: c.configDigest, instanceId: c.instanceId, knownInstallations: known.map(i => i.id), firstVersion: first.data.value.version, secondVersion: second.data.value.version, responseBytes: [first.byteLength, second.byteLength] });
  await h.partial('Original deployment-issued Gateway bearer reads real complete-marked snapshots and selector refusals; independent registry binding, two known owner installations and real ordinary routed owner collections retained. Known rows plus complete marker are not an independent proof of every assignment. Actual Gateway Apply/persistent history/route-receipt, Base snapshot, full count/HTTP/persistent/receipt byte boundaries and restart/replay remain uncovered; no machine receipt was submitted.');
}
for (const handler of [policy, snapshots]) { handler.transport = 'owner-api'; handler.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers: { 'F035-004': policy, 'F035-006': snapshots }, policyCommand, cleanupPolicy, binding, snapshotProof };
