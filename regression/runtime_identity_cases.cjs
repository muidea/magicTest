const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const { registryUnchanged } = require('./runtime_placement_cases.cjs');
const snapshot = '/panel/runtime-execution/snapshot/';
// The Bearer registry deliberately returns an empty403 for a wrong subject
// kind/scope before any instance snapshot is projected. A401 is not proof.
const machineRefusal = response => response?.status === 403 &&
  !!response.data && Object.keys(response.data).length === 1 && response.data.text === '';
async function identities(h) {
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
  const after = (await h.ok(h.admin, 'GET', registryRoute)).values;
  const ordered = rows => [...rows].sort((a, b) => a.id.localeCompare(b.id));
  h.check('Read-only impersonation probes preserve runtime configuration and monotone control observation revisions', registryUnchanged(ordered(before), ordered(after)));
  for (const i of installations) h.check('Wrong runtime identity never changes an original installation', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
  await h.partial('Active human/admin and foreign-tenant human cannot impersonate the machine snapshot reader, including forged instance/namespace/pagination selectors; independent sessions, registry and installations retained. Real wrong machine credential binding and signed out-of-scope Endpoint probes remain open.');
}
identities.transport = 'owner-api'; identities.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F035-003': identities }, machineRefusal };
