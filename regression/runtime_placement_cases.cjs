// Normal placement acceptance follows the approved original model request.
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const review = require('./deployment_review_cases.cjs');
const business = require('./business_cases.cjs');
const authority = require('./application_authority_cases.cjs');
const registryRoute = '/panel/operations/runtime-placements/instances/';
const installRoute = '/panel/application/installations/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(r => r.value);
async function registry(h) {
  // This owner endpoint guarantees its entire bounded inventory or an error;
  // it is not the paginated business directory contract.
  const values = (await h.ok(h.admin, 'GET', registryRoute)).values;
  h.check('Runtime owner supplies a complete unique inventory with current immutable instance identities',
    Array.isArray(values) && values.length > 0 && new Set(values.map(v => v.id)).size === values.length &&
    values.every(v => typeof v.id === 'string' && v.id && ['base', 'gateway'].includes(v.kind) && Number.isSafeInteger(v.version) && v.version > 0));
  return [...values].sort((a, b) => a.id.localeCompare(b.id));
}
function placementMatches(r, inventory) {
  const approved = r.commands?.filter(c => c.route?.endsWith('/approve') && c.outcome === 'confirmed'), req = r.last, op = r.operation, i = r.installation;
  if (approved?.length !== 1 || !req || !op || !i || !same(approved[0].body.runtimePlacement, r.placement) || !same(req.runtimePlacement, r.placement)) return false;
  const resolved = req.resolvedRuntimePlacement;
  if (!resolved || !['execution', 'gateway'].every(kind => {
    const target = resolved[kind], intended = r.placement[kind === 'execution' ? 'executionInstanceId' : 'gatewayInstanceId'];
    const current = inventory.filter(v => v.id === intended);
    return current.length === 1 && current[0].kind === (kind === 'execution' ? 'base' : 'gateway') && current[0].status === 'registered' &&
      typeof current[0].incarnation === 'string' && current[0].incarnation.length > 0 && target?.instanceId === intended &&
      target.instanceVersion === current[0].version && target.resolutionSource === 'explicit';
  })) return false;
  const ack = approved[0].response?.data?.value;
  return ack?.id === r.id && ack.operationId === op.id && same(ack.runtimePlacement, req.runtimePlacement) && same(ack.resolvedRuntimePlacement, resolved) &&
    ack.planDigest === req.planDigest && req.id === r.id && req.status === 'succeeded' && req.operationId === op.id &&
    op.requestId === r.id && op.packageId === req.packageId && op.deploymentId === req.deploymentId && op.planDigest === req.planDigest &&
    op.status === 'succeeded' && op.phase === 'complete' && op.receiptRef === 'installation:' + i.id && op.attempt > 0 &&
    i.status === 'ready' && i.namespace === req.namespace && i.deploymentId === req.deploymentId && i.applicationUuid === op.applicationUuid &&
    i.sourceDigest === r.creation?.intended?.expectedDigest && i.operationId === 'deployment:' + op.id &&
    i.receipt?.deploymentOperationId === op.id;
}
function registryUnchanged(before, after) {
  const dynamic = ['assignmentVersion', 'snapshotVersion', 'appliedSnapshotVersion', 'updateTime'];
  const fixed = v => Object.fromEntries(Object.entries(v).filter(([key]) => !dynamic.includes(key)));
  return before.length === after.length && before.every((v, index) => v.id === after[index].id && same(fixed(v), fixed(after[index])) &&
    dynamic.every(key => Number.isSafeInteger(v[key]) && v[key] >= 0 && Number.isSafeInteger(after[index][key]) && after[index][key] >= v[key]));
}
async function placement(h) {
  const f = await fixture(h), actor = await business.member(h, 'manager'), peers = [];
  for (const value of f.installations) peers.push(await read(h, installRoute + value.id));
  const beforeRegistry = await registry(h), r = await review.create(h, f, 'route-placement');
  h.admin.id = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account.id;
  let grant, row, primary;
  try {
    await review.approve(h, r, [h.admin]);
    h.check('Explicit approved Base/Gateway choices, resolved registry revisions and original durable installation receipt agree',
      placementMatches(r, beforeRegistry), { request: r.last, operation: r.operation, installation: r.installation });
    const accountId = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value.account.id;
    grant = { kind: 'member-access-retirement', phase: 'created', accountId, installation: r.installation, commands: [], active: false,
      origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity) };
    h.state.resources.push(grant); h.persist(); await authority.accessCommand(h, grant, 'manager', 0);
    const current = { ...f, installations: [r.installation] }, context = await business.runtime(h, current, 0, actor);
    h.check('Actual routed runtime returns current exact original installation execution fences',
      Number.isSafeInteger(context.identity.generation) && context.identity.generation > 0 && Number.isSafeInteger(context.identity.executionEpoch) && context.identity.executionEpoch > 0);
    row = await business.create(h, context, 'explicit-placement');
    const name = h.state.prefix + '-placement-updated';
    await business.execute(h, actor, row, business.request(row, 'update', [{ name: 'name', value: name }]));
    const actual = await business.record(h, actor, row);
    h.check('Independent routed owner read proves the exact approved installation persisted only the reliable update',
      h.good(actual) && String(actual.data.value.id) === row.recordId && String(actual.data.value.version) === row.version &&
      same({ ...actual.data.value, name: row.created.name, version: row.created.version }, row.created) && actual.data.value.name === name, actual);
    for (let index = 0; index < f.installations.length; index++) {
      const peer = await business.runtime(h, f, index, actor);
      const absent = await business.record(h, actor, { ...peer, recordId: row.recordId });
      h.check('Original model peer cannot read the new installation owned row', [200, 404].includes(absent.status) && absent.data?.error?.code === 2 && absent.data.value == null, absent);
    }
    h.check('Business execution preserves the complete original succeeded approval and operation',
      same(await read(h, '/panel/application/deployment-requests/' + r.id), r.last) &&
      same(await read(h, '/panel/operations/namespaces/panel/application-deployment-operations/' + r.operation.id), r.operation));
    h.observe({ kind: 'explicit-runtime-placement-owner-proof', requestId: r.id, operationId: r.operation.id, installationId: r.installation.id,
      placement: r.placement, resolved: r.last.resolvedRuntimePlacement, runtimeIdentity: context.identity,
      businessOperations: row.commands.map(c => ({ operationId: c.body.operationId, receipt: c.receipt })) });
  } catch (error) { primary = error; throw error; }
  finally {
    if (row) await business.finishCleanup(h, [row], primary);
    const openRows = h.state.resources.filter(v => v.kind === 'business-record' && v.identity?.installationId === String(r.installation?.id) && v.phase !== 'deleted');
    if (openRows.length) {
      h.observe({ kind: 'placement-original-business-cleanup-open', installationId: r.installation.id, count: openRows.length });
      if (!primary) throw new h.Blocked('Original placed business row disposition unresolved; retain grant and installation');
    } else {
      if (grant) await authority.retireAccess(h, grant);
      await review.cleanup(h, r);
    }
  }
  h.check('Formal exact destroy preserves original runtime registry configuration while control observation cursors remain monotone', registryUnchanged(beforeRegistry, await registry(h)));
  for (const peer of peers) h.check('Normal placement, business writes and destruction leave every original peer installation unchanged', same(await read(h, installRoute + peer.id), peer));
  h.check('Original immutable source package and revision remain unchanged after independent placement acceptance',
    same(await read(h, '/panel/application/model-packages/' + f.package.id), f.package) &&
    same(await read(h, '/panel/application/definitions/' + f.application.id + '/revisions/' + f.revision.id), f.revision));
}
placement.transport = 'owner-api';
module.exports = { handlers: { 'F035-001': placement }, placementMatches, registryUnchanged };
