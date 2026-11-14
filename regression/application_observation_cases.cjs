// Application observations use their own frozen reader roles. Empty results
// prove authorization/identity only, never that a producer emitted a log/count.
const { isDeepStrictEqual: same } = require('node:util');
const pages = require('./page_runtime_cases.cjs');
const business = require('./business_cases.cjs');
const authority = require('./application_authority_cases.cjs');
const metadata = require('./definition_metadata_cases.cjs');
const { runtimeRead } = require('./owner_transport.cjs');
const readers = [
  { kind: 'operation-logs', permission: 'builtin-operation-logs.read', role: 'application-operation-logs-reader' },
  { kind: 'counters', permission: 'builtin-counters.read', role: 'application-counters-reader' },
];
async function prepare(h, authored) {
  const before = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + authored.app.id)).value;
  const authorization = structuredClone(before.authorization);
  authorization.permissions = readers.map(r => ({ key: r.permission, name: '独立只读 ' + r.kind, permission: 4 }));
  authored.app = await metadata.write(h, metadata.track(h, before, false), { authorization });
  authored.model = await require('./authoring_cases.cjs').authoring.draft(h, authored.app);
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
function validatePage(value, identity, kind, pageNum, pageSize, previous, total) {
  const p = value?.pagination;
  if (!same(value?.identity, identity) || !Array.isArray(value.values) || !p || !Number.isSafeInteger(p.total) || p.total < 0 ||
      p.pageNum !== pageNum || p.pageSize !== pageSize || p.mode || p.after || p.nextCursor || p.hasMore ||
      total !== undefined && p.total !== total || value.values.length !== Math.min(pageSize, Math.max(0, p.total - (pageNum - 1) * pageSize)))
    throw Error('Complete exact application observation page required');
  let last = previous;
  for (const row of value.values) {
    // JSON numbers above2^53 cannot prove an exact Snowflake identity.
    const id = typeof row.id === 'string' && /^[1-9][0-9]*$/.test(row.id) ? BigInt(row.id) : Number.isSafeInteger(row.id) && row.id > 0 ? BigInt(row.id) : 0n;
    if (id === 0n || last !== undefined && id >= last || row.namespace !== identity.namespace || (kind === 'operation-logs' ?
      row.hostedBy !== identity.runtimeApplicationUuid || row.targetNamespace !== identity.namespace :
      row.application?.uuid !== identity.runtimeApplicationUuid || typeof row.value !== 'number' || !Number.isFinite(row.value)))
      throw Error('Observation row crosses the original application/namespace or has an unsafe/repeated identity');
    last = id;
  }
  return { last, total: p.total };
}
async function read(h, actor, context, kind, complete = false) {
  const values = []; let last, total;
  for (let pageNum = 1; pageNum <= 100; pageNum++) {
    const route = '/apps/application/' + kind + '/?' + new URLSearchParams({ application: context.applicationKey,
      deploymentId: context.identity.deploymentId, pageNum: String(pageNum), pageSize: '100' });
    const result = await runtimeRead(actor, route, context.identity, h.observe);
    if (!complete) return result;
    h.check('Independent original observation reader reaches successful exact installed owner', h.good(result), result);
    ({ last, total } = validatePage(result.data.value, context.identity, kind, pageNum, 100, last, total));
    values.push(...result.data.value.values);
    if (values.length === total) return values;
  }
  throw new h.Blocked('Observation read exceeds finite complete-page budget; no absence proof');
}
const denied = r => [200, 401, 403].includes(r?.status) && r.data?.error?.code === 5 && r.data.value == null && !r.data.values?.length;
async function observations(h) {
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'observation', requestPrefix: 'observation-', prepareAuthor: prepare });
  const manager = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, manager), peer = await business.runtime(h, f, 1, manager);
  const base = '/cas/namespaces/panel/', templates = await h.directory(h.admin, base + 'role-templates/');
  const ordinary = templates.find(t => t.key === 'portal-basic-user' && t.systemManaged && t.subjectType === 'account' && t.status === 2);
  h.check('Protected ordinary template and frozen observer permissions are present', ordinary?.roleRefs?.length > 0 &&
    readers.every(r => f.revision.application.authorization.permissions.some(p => p.key === r.permission && p.permission === 4)));
  const roles = await h.directory(h.admin, base + 'roles/'), module = '/applications/' + context.identity.deploymentId;
  for (const reader of readers) h.check('CAS installs separately assignable fixed observation reader without write/delete privileges',
    roles.some(r => r.module === module && r.key === reader.role && r.humanAssignable && r.status === 2 &&
      r.privilege?.some(p => p.module === module && p.uriPath === '/apps/permissions/' + reader.permission && p.value === 4)));
  let primary;
  try {
    for (const reader of readers) h.check('Data manager receives no implicit independent ' + reader.kind + ' authority', denied(await read(h, manager, context, reader.kind)));
    for (const [index, reader] of readers.entries()) {
      const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-observe-' + index, name: '独立应用观察角色', subjectType: 'account', status: 2,
        applicationAccess: [], roleRefs: [...structuredClone(ordinary.roleRefs), { module, key: reader.role }] }, 'role-template');
      const member = await authority.account(h, 'observer-' + index);
      member.resource.scenarioDefinitionId = f.application.id;
      member.resource.scenarioInstallationIds = f.installations.map(i => String(i.id)); h.persist();
      await authority.assign(h, member, group, []);
      let revoked = false;
      try {
        await read(h, member.actor, context, reader.kind, true);
        h.check('One observation role does not imply the other observation reader', denied(await read(h, member.actor, context, readers[1 - index].kind)));
        h.check('Exact observer role does not cross to the second installed instance', denied(await read(h, member.actor, peer, reader.kind)));
        const data = await business.record(h, member.actor, { ...context, recordId: '1' });
        h.check('Observer-only account cannot read ordinary instance business data, even by guessed ID', denied(data), data);
        await require('./business_action_cases.cjs').revoke(h, member, group, ordinary);
        revoked = true;
        h.check('Original logged-in observer loses the exact observation after current CAS role revocation', denied(await read(h, member.actor, context, reader.kind)));
      } finally {
        if (!revoked) await require('./business_action_cases.cjs').revoke(h, member, group, ordinary).catch(() => {});
      }
    }
  } catch (error) { primary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, f, primary); }
  await h.partial('Frozen two fixed observer permissions, installed separate CAS roles, human log/counter positive reads, cross-reader and second-instance refusals, data-role non-implication and current-role revocation implemented. Nonempty real block emissions, Endpoint, cross-tenant and observation write denial remain open; empty observations are not emission proof.');
}
observations.transport = 'owner-api';
module.exports = { handlers: { 'F006-004': observations }, validatePage, denied, readers };
