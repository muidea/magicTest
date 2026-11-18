const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const { registryUnchanged } = require('./runtime_placement_cases.cjs');
const identities = require('./cas_identity_cases.cjs');
const snapshot = '/panel/runtime-execution/snapshot/';
const bindCredential = '/panel/operations/runtime-placements/instance-credentials/';
// The Bearer registry deliberately returns an empty403 for a wrong subject
// kind/scope before any instance snapshot is projected. A401 is not proof.
const machineRefusal = response => response?.status === 403 &&
  !!response.data && Object.keys(response.data).length === 1 && response.data.text === '';
async function bearerSnapshotProbe(h, route, accessToken) {
  const result = await h.admin.page.evaluate(async ({ route, accessToken }) => {
    const response = await fetch(route, {
      method: 'GET', credentials: 'omit', redirect: 'error', cache: 'no-store',
      headers: { Authorization: 'Bearer ' + accessToken }, signal: AbortSignal.timeout(30000)
    });
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { text }; }
    return { status: response.status, data };
  }, { route: '/api/v1' + route, accessToken });
  h.observe({ kind: 'runtime-machine-bearer-probe', origin: h.admin.origin, route, status: result.status, data: result.data });
  return result;
}
async function identitiesCase(h) {
  const f = await fixture(h), registryRoute = '/panel/operations/runtime-placements/instances/';
  const before = (await h.ok(h.admin, 'GET', registryRoute)).values;
  h.check('Actual runtime registry contains nonempty unique registered identities', Array.isArray(before) && before.length > 0 && new Set(before.map(v => v.id)).size === before.length);
  const installations = [];
  for (const i of f.installations) installations.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value);
  for (const actor of [h.admin, h.tenantAdmin]) {
    const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
    for (const route of [snapshot, snapshot + '?instanceId=' + encodeURIComponent(before[0].id), snapshot + '?namespace=panel', snapshot + '?_pageSize=1']) {
      const denied = await h.api(actor, 'GET', route);
      h.check('Current human login cannot impersonate a runtime machine or select another snapshot; no projection is exposed', machineRefusal(denied), denied);
    }
    h.check('Machine-only refusals preserve the same independent active human session', same((await h.ok(actor, 'GET', '/api/v1/web/session/')).value, session));
  }
  const m = await identities.machine(h, 'runtime-probe');
  try {
    const pair = await identities.token(h, m);
    h.check('Control fixture issues an actual signed out-of-scope CAS Endpoint Bearer token', pair.status === 200 && typeof pair.data?.access_token === 'string', pair);
    const headers = { Authorization: 'Bearer ' + pair.data.access_token };
    for (const route of [snapshot, snapshot + '?instanceId=' + encodeURIComponent(before[0].id), snapshot + '?namespace=panel', '/panel/runtime-execution/notification/']) {
      const denied = await bearerSnapshotProbe(h, route, pair.data.access_token);
      h.check('Signed out-of-scope Endpoint token cannot impersonate a platform runtime reader or inspect snapshots', machineRefusal(denied), { route, denied });
    }
    const baseInstance = before.find(v => v.kind === 'base');
    const gatewayInstance = before.find(v => v.kind === 'gateway');
    h.check('Live placement registry includes both Base and Gateway instances', !!baseInstance && !!gatewayInstance);
    const baseBind = await h.api(h.admin, 'POST', bindCredential, {
      instanceId: baseInstance.id, incarnation: 'probe-' + h.state.prefix, endpointId: m.endpoint.id, clientId: m.owner.value.clientId, expectedVersion: baseInstance.version
    });
    h.check('Wrong runtime kind (Base) cannot enroll a Gateway execution credential', !h.good(baseBind), baseBind);
    const wrongGatewayBind = await h.api(h.admin, 'POST', bindCredential, {
      instanceId: gatewayInstance.id, incarnation: (gatewayInstance.incarnation || 'probe') + '-wrong', endpointId: m.endpoint.id, clientId: m.owner.value.clientId, expectedVersion: gatewayInstance.version
    });
    h.check('Wrong Endpoint/incarnation credential binding on existing Gateway is rejected without mutation', !h.good(wrongGatewayBind), wrongGatewayBind);
    const foreignBind = await h.api(h.tenantAdmin, 'POST', bindCredential, {
      instanceId: gatewayInstance.id, incarnation: 'probe-' + h.state.prefix, endpointId: m.endpoint.id, clientId: m.owner.value.clientId, expectedVersion: gatewayInstance.version
    });
    h.inaccessible(foreignBind, 'Tenant admin cannot bind platform runtime instance credentials');
  } finally {
    await identities.cleanup(h, m.credential.resource);
    m.credential.resource.phase = 'deleted'; h.persist();
  }
  const after = (await h.ok(h.admin, 'GET', registryRoute)).values;
  const ordered = rows => [...rows].sort((a, b) => a.id.localeCompare(b.id));
  h.check('Read-only and rejected binding probes preserve runtime configuration and monotone control observation revisions', registryUnchanged(ordered(before), ordered(after)));
  for (const i of installations) h.check('Wrong runtime identity never changes an original installation', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
}
identitiesCase.transport = 'owner-api'; identitiesCase.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F035-003': identitiesCase }, machineRefusal };
