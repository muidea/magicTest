// Reject allocation through the real review command before any execution.
const { isDeepStrictEqual: same } = require('node:util');
const review = require('./deployment_review_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const instances = '/panel/operations/database-instances/';
const placements = '/panel/operations/namespace-storage-placements/';
const requests = '/panel/application/deployment-requests/';
const reviews = '/panel/operations/namespaces/panel/application-deployment-requests/';
const directories = [requests, '/panel/operations/namespaces/panel/application-deployment-operations/',
  '/panel/application/installations/', '/panel/storage-resources/databases/',
  '/panel/storage-resources/database-schemas/', instances, placements];
const sorted = rows => [...rows].sort((a, b) => String(a.id).localeCompare(String(b.id)));
async function snapshot(h) {
  const result = {};
  for (const route of directories) result[route] = sorted(await h.directory(h.admin, route));
  return result;
}
function exactRefusal(response, expected) {
  return [200, 400, 401, 403, 409].includes(response?.status) && response.data?.error?.code === expected.code &&
    response.data.error.message === expected.message && response.data.value == null;
}
function pendingRequests(state, id) {
  return state.resources.some(r => r.storageAdmissionDatabaseId === id && r.phase !== 'deleted');
}
async function rejectApproval(h, r, expected) {
  review.original(h, r);
  const options = (await h.ok(h.admin, 'GET', reviews + r.id + '/runtime-options')).values;
  const bases = options.filter(v => v.kind === 'base'), gateways = options.filter(v => v.kind === 'gateway');
  h.check('Actual approval has one unambiguous valid execution and gateway choice', bases.length === 1 && gateways.length === 1, options);
  const before = await snapshot(h), original = (await h.ok(h.admin, 'GET', requests + r.id)).value;
  h.check('Negative storage approval starts from the exact submitted owned request', same(original, r.last) && original.status === 'submitted' && !original.operationId);
  const c = { route: reviews + r.id + '/approve', body: { expectedVersion: original.version,
    runtimePlacement: { executionInstanceId: bases[0].id, gatewayInstanceId: gateways[0].id }, reason: 'Reject only the original ineligible storage selection' },
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown',
    expected: structuredClone(expected), originalRequest: original, before };
  r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  const current = (await h.ok(h.admin, 'GET', requests + r.id)).value, after = await snapshot(h);
  c.after = after; c.observedRequest = current; h.persist();
  const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value;
  const preserved = same(current, original) && same(after, before);
  const authenticated = session.account?.account === h.admin.identity.account && session.homeNamespace === h.admin.identity.namespace;
  // A known refusal and complete unchanged facts dispose this exact intent.
  // Any missing read, unknown reply or different refusal leaves it unresolved.
  if (exactRefusal(c.response, expected) && preserved && authenticated) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Real approval reaches the exact storage state or tenant scope fence and preserves all owner directories', c.outcome === 'rejected-and-unchanged', c.response);
}
async function storage(h) {
  const f = await fixture(h), baseline = await snapshot(h), target = h.need('tenantA').name;
  const payload = { name: h.state.prefix + '-admission-db', catalog: 'regression', engine: 'postgresql', engineVersion: '17', address: '127.0.0.1:9',
    administrator: 'regression_unused', password: h.state.password, description: 'Owned disabled metadata for pre-execution storage refusal',
    cpuMillis: 1000, memoryBytes: 1024 ** 3, databaseLimit: 1, status: 'disabled', healthStatus: 'unknown' };
  if (baseline[instances].some(v => v.engine === payload.engine && v.address === payload.address)) throw new h.Blocked('Boundary endpoint already registered; do not reuse another resource');
  const db = await h.create(instances, payload, 'database-instance');
  const owned = h.state.resources.find(r => r.kind === 'database-instance' && r.id === db.id);
  owned.storageAdmissionNamespace = target; h.persist();
  const original = (await h.ok(h.admin, 'GET', instances + db.id)).value;
  h.check('Original disabled endpoint has zero allocations and no exposed credential', original.status === 'disabled' && original.allocatedDatabaseCount === 0 && original.resourceVersion === 1 && !JSON.stringify(original).includes(payload.password));
  let primary;
  try {
    for (const [suffix, expected] of [['disabled', { code: 21, message: 'database instance does not satisfy the application storage requirement' }],
      ['foreign', { code: 5, message: 'database instance is unavailable to the target namespace' }]]) {
      if (suffix === 'foreign') {
        const rows = await h.directory(h.admin, placements), own = rows.filter(v => v.instance?.id === db.id);
        h.check('Owned endpoint has exactly one auto-created shared placement', own.length === 1 && own[0].namespace === '' && own[0].mode === 'shared');
        const c = { route: placements + own[0].id, body: { namespace: target, instanceId: db.id, mode: 'dedicated', status: 'active', expectedResourceVersion: own[0].resourceVersion }, confirmed: false };
        (owned.pendingDatabaseCommands ||= []).push(c); h.persist();
        c.response = await h.api(h.admin, 'PUT', c.route, c.body); h.persist();
        const after = (await h.directory(h.admin, placements)).filter(v => v.id === own[0].id);
        h.check('Independent placement owner confirms exact original dedicated namespace selection', h.good(c.response) && after.length === 1 && same(after[0], c.response.data.value) && after[0].instance?.id === db.id && after[0].namespace === target && after[0].mode === 'dedicated' && after[0].status === 'active' && after[0].resourceVersion === own[0].resourceVersion + 1);
        c.confirmed = true; h.persist();
      }
      const r = await review.create(h, f, 'storage-' + suffix, { mode: 'specified', databaseInstanceId: db.id });
      r.storageAdmissionDatabaseId = db.id; h.persist();
      try { await rejectApproval(h, r, expected); }
      finally { if (!r.commands.some(c => c.outcome === 'unknown')) await review.cleanup(h, r); }
    }
  } catch (error) { primary = error; throw error; }
  finally {
    // Unknown approval must retain both request and selected physical owner.
    const pending = pendingRequests(h.state, db.id);
    if (!pending && !owned.pendingDatabaseCommands?.some(c => !c.confirmed)) {
      try {
        await h.remove(instances, db.id);
        const after = await snapshot(h);
        // Report only identity-level differences so a residual audit row is
        // distinguishable from a leaked placement/instance without dumping rows.
        const diff = {};
        for (const route of directories) {
          const missing = baseline[route].filter(v => !after[route].some(x => x.id === v.id)).map(v => v.id);
          const added = after[route].filter(v => !baseline[route].some(x => x.id === v.id)).map(v => v.id);
          if (missing.length || added.length) diff[route] = { missing, added };
        }
        h.check('Formal endpoint cleanup removes only its auto-owned placement; all original delivery and storage directories remain exact', same(after, baseline), { diff });
      } catch (error) { h.observe({ kind: 'storage-admission-cleanup-open', id: db.id, error: error.message }); if (!primary) throw error; }
    }
  }
}
storage.transport = 'owner-api';
storage.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F048-002': storage }, rejectApproval, exactRefusal, pendingRequests };
