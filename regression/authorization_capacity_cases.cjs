// Declaration counts come from CAS's current initial authorization contract.
// They are not a substitute for JWT or encrypted-session byte budgets.
const { isDeepStrictEqual: same } = require('node:util');
const { authoring } = require('./authoring_cases.cjs');
const metadata = require('./definition_metadata_cases.cjs');
const scenario = require('./scenario_commands.cjs');
const base = '/panel/application/definitions/';
const invalid = 'application authorization definition is invalid, duplicated or exceeds its declared scope';
function declarations(original, count) {
  if (!Number.isInteger(count) || count < 1 || count > 65) throw Error('Finite declared-count fixture required');
  // Fresh empty model only; never discard an installed or published catalogue.
  if (original?.apiVersion !== 'magic.application-authorization/v1' || original.entityActions?.length ||
      ['permissions', 'roles', 'templates', 'builtinRoles', 'builtinTemplates'].some(k => original[k]?.length)) throw Error('Fresh extension-free authorization required');
  const value = structuredClone(original);
  value.permissions = Array.from({ length: count }, (_, i) => ({ key: 'capacity-permission-' + i, name: '容量权限 ' + i, permission: 4 }));
  value.roles = Array.from({ length: count }, (_, i) => ({ key: 'capacity-role-' + i, name: '容量角色 ' + i, subjectKinds: ['human', 'service'], permissions: [value.permissions[i].key] }));
  value.templates = Array.from({ length: count }, (_, i) => ({ key: 'capacity-template-' + i, name: '容量模板 ' + i, subjectType: i % 2 ? 'endpoint' : 'account', roleKeys: [value.roles[i].key] }));
  return value;
}
async function boundary(h, app) {
  const resource = h.state.resources.find(r => r.kind === 'definition' && r.id === app.id && r.creation?.ownershipConfirmed);
  if (!resource || resource.metadataJournal) throw new h.Blocked('Fresh exact original capacity definition required; no boundary replay');
  const original = (await h.ok(h.admin, 'GET', base + app.id)).value;
  h.check('Capacity definition is the exact newly created empty model', same(original, app) && original.runtimeType === 'model-driven');
  const journal = metadata.track(h, original, false);
  for (const count of [63, 64]) {
    const wanted = declarations(original.authorization, count);
    const current = await metadata.write(h, journal, { authorization: wanted });
    h.check('Owner retains every unique permission, role and account/Endpoint template at the declared boundary without truncation', same(current.authorization, wanted));
  }
  for (const field of ['permissions', 'roles', 'templates']) {
    const legal = journal.last, oversized = structuredClone(legal.authorization);
    // Keep all references valid so only this owner's count limit is crossed.
    const extra = declarations(original.authorization, 65)[field][64];
    if (field === 'roles') extra.permissions = [oversized.permissions[0].key];
    if (field === 'templates') extra.roleKeys = [oversized.roles[0].key];
    oversized[field].push(extra);
    await scenario.reject(h, resource, h.admin, 'PUT', base + app.id,
      metadata.command(legal, { authorization: oversized }), [base + app.id, base + app.id + '/model-draft'], { code: 4, message: invalid });
    h.check('Rejected extra declaration preserves the complete legal boundary and its original concurrency revision', same((await h.ok(h.admin, 'GET', base + app.id)).value, legal));
  }
  // Restoring all three to empty demonstrates a legal contraction after each
  // refusal. Unknown writes deliberately stop here and keep the original facts.
  const restored = await metadata.write(h, journal, { authorization: structuredClone(original.authorization) });
  h.check('Formal conditional contraction remains available after count refusals and preserves every other original definition field',
    same({ ...restored, updateTime: original.updateTime }, original));
  journal.capacityDisposition = 'Three exact target-stage count refusals and full unchanged owner reads; original extension-free definition restored through a new conditional command.';
  h.persist();
}
async function capacity(h) {
  await boundary(h, await authoring.definition(h, 'authorization-capacity'));
  await h.partial('CAS-declared extension counts: permissions/roles/templates at63/64, each independent65 refusal, complete owner/draft preservation and formal conditional contraction implemented. Installed instance/action scale, builtin dependency counts, complete JWT/encrypted-session cumulative byte budgets, login/refresh/business at those byte limits and existing-subject retirement remain open; no arbitrary capacity promise.');
}
capacity.transport = 'owner-api';
module.exports = { handlers: { 'F010-005': capacity }, declarations, boundary };
