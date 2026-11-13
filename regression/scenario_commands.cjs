// Journals augment the original fixture resource; they never own product state.
const { isDeepStrictEqual: same } = require('node:util');
function guard(h, r) {
  require('./native_lifecycle_cases.cjs').guard(h, r);
  if (h.state.resources.some(parent => parent.modelUpgrade && parent.modelUpgrade.phase !== 'complete' &&
      (r === parent || r.kind === 'definition' && r.id === parent.modelUpgrade.definitionId ||
        r.kind === 'deployment-review-request' && (parent.modelUpgrade.requestIds.includes(r.id) || r.creation?.intended?.upgrade?.installationId === parent.modelUpgrade.source.id) ||
        r.kind === 'member-access-retirement' && parent.modelUpgrade.installationIds.includes(String(r.installation?.id)))))
    throw new h.Blocked('Original model upgrade lineage remains open; preserve predecessor, successor, grants and definition');
  if (r.scenarioCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original scenario command remains unresolved; preserve its exact resource and actor, no replay');
  if (['native-package-probe', 'native-provider-probe'].includes(r.kind) && r.package?.id != null &&
      h.state.resources.some(child => child.kind === 'native-runtime-request' && child.creation?.intended?.packageId === r.package.id &&
        child.scenarioCommands?.some(c => c.outcome === 'unknown')))
    throw new h.Blocked('Original native task scenario unresolved; retain its exact source package and terminal request history');
  if (h.state.resources.some(parent => parent.storageRecovery && parent.storageRecovery.phase !== 'complete' &&
      (r === parent || r.kind === 'definition' && r.id === parent.storageRecovery.definitionId ||
        r.kind === 'deployment-review-request' && parent.storageRecovery.requestIds.includes(r.id) ||
        r.kind === 'member-access-retirement' && parent.storageRecovery.installationIds.includes(String(r.installation?.id)))))
    throw new h.Blocked('Original retained-storage lineage remains open; preserve exact predecessors, successors, grants and definition');
  if (h.state.resources.some(row => row.endpointScenarioAccountId != null && row.phase !== 'deleted' &&
      ['generated-service-graph', 'service-graph-subscription', 'service-graph-credential'].includes(row.kind) &&
      (r.kind === 'definition' && row.scenarioDefinitionId === r.id ||
        ['member-access-retirement', 'deployment-review-request'].includes(r.kind) && row.scenarioInstallationIds?.includes(String(r.installation?.id)))))
    throw new h.Blocked('Original Endpoint scenario graph remains open; retain its exact definition, grant and installations');
  const template = r.kind === 'role-template' && r.creation?.intended?.key;
  if (template && h.state.resources.some(row => row.kind === 'service-graph-credential' && row.phase !== 'deleted' &&
      row.endpointAuthorityCommands?.some(c => c.body?.roleTemplateKeys?.includes(template) || c.before?.templateRefs?.some(t => t.key === template))))
    throw new h.Blocked('Original Endpoint template remains needed for credential disposition; retain exact template');
  if (h.state.resources.some(row => row.kind === 'account' && row.phase !== 'deleted' && row.scenarioDefinitionId != null &&
      row.authorityCommands?.some(c => c.outcome === 'unknown') && (r.kind === 'definition' && row.scenarioDefinitionId === r.id ||
        ['member-access-retirement', 'deployment-review-request'].includes(r.kind) && row.scenarioInstallationIds?.includes(String(r.installation?.id)))))
    throw new h.Blocked('Original scenario role assignment unresolved; retain exact definition, grant and installations');
  if (h.state.resources.some(row => (row.kind === 'business-record' || row.kind === 'source-effect-scenario' && (!row.dispositionReady || row.commands?.some(c => c.outcome === 'unknown'))) && row.phase !== 'deleted' && row.scenarioDefinitionId != null &&
      (r.kind === 'definition' && row.scenarioDefinitionId === r.id || ['member-access-retirement', 'deployment-review-request'].includes(r.kind) && String(r.installation?.id) === row.identity?.installationId)))
    throw new h.Blocked('Original scenario business row remains open; retain exact definition, grant and installation');
}
async function snapshot(h, actor, routes) {
  const values = {};
  for (const route of routes) values[route] = route.endsWith('/') ? { status: 200, data: { values: await h.directory(actor, route) } } : await h.api(actor, 'GET', route);
  for (const value of Object.values(values)) h.check('Independent scenario snapshot reaches a readable current owner', h.good(value), value);
  return values;
}
async function reject(h, resource, actor, method, route, body, reads, expected) {
  guard(h, resource);
  const ownedBuild = ['native-provider-probe', 'native-package-probe'].includes(resource.kind) && resource.packageAcknowledged === true &&
    resource.origin === h.admin.origin && same(resource.actorIdentity, h.admin.identity) && resource.package?.applicationUuid === resource.applicationUuid &&
    Array.isArray(resource.preexistingIds) && !resource.preexistingIds.includes(resource.package.id) &&
    resource.commands?.some(c => c.method === 'POST' && c.route === '/panel/application/deployment-packages/builds/' && c.body?.applicationUuid === resource.applicationUuid &&
      same(c.actorIdentity, resource.actorIdentity) && c.origin === resource.origin && c.outcome === 'confirmed' && h.good(c.response) && same(c.response.data.value, resource.package));
  if ((!resource.creation?.ownershipConfirmed && !ownedBuild) || actor.origin !== h.admin.origin || !reads.length) throw new h.Blocked('Owned original resource and independent read scope required');
  const identity = structuredClone(actor.identity), origin = actor.origin;
  const c = { method, route, body: structuredClone(body), actorIdentity: identity, origin, expected, reads, before: await snapshot(h, h.admin, reads), outcome: 'unknown' };
  (resource.scenarioCommands ||= []).push(c); h.persist();
  try { c.response = await h.api(actor, method, route, body); }
  catch (error) { c.transportError = error.message; }
  h.persist();
  if (!same(actor.identity, identity) || actor.origin !== origin) throw new h.Blocked('Scenario actor changed; retain original unknown command');
  c.after = await snapshot(h, h.admin, reads); h.persist();
  const response = c.response;
  const refused = [200, 400, 403, 404, 409, 422].includes(response?.status) && response.data?.error?.code === expected.code &&
    (typeof expected.message === 'string' ? response.data.error.message === expected.message : new RegExp(expected.messagePattern).test(response.data.error.message)) && response.data.value == null;
  if (refused && same(c.after, c.before)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Exact target-stage refusal and independent complete owner snapshots prove no side effect', c.outcome === 'rejected-and-unchanged', c);
  return c;
}
module.exports = { guard, snapshot, reject };
