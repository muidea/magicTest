// Panel policy commands and BFF-owned session facts; no clock manipulation.
const handlers = {};
const route = '/panel/session-policy/';
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const semantics = value => ({ timeout: value.resolved.timeoutMinutes, source: value.resolved.sourceNamespace,
  inherited: value.resolved.inherited, override: value.override?.timeoutMinutes ?? null });
const read = async (h, actor) => (await h.ok(actor, 'GET', route)).value;

async function restoreSessionPolicy(h, resource) {
  const current = await read(h, h.admin);
  if (!same(current, resource.restored || resource.original)) {
    const expected = resource.written;
    h.check('Restore only the exact policy revision written by this test', expected && same(current.override, expected.override) && same(current.resolved, expected.resolved), { current, expected });
    if (resource.original.override) await h.ok(h.admin, 'PUT', route, {
      timeoutMinutes: resource.original.override.timeoutMinutes,
      expectedResourceVersion: current.override.resourceVersion });
    else await h.ok(h.admin, 'DELETE', route);
  }
  const restored = await read(h, h.admin);
  h.check('Independent policy owner read proves original platform semantics restored', same(semantics(restored), semantics(resource.original)), { original: resource.original, restored });
  resource.phase = 'restored'; resource.restored = restored; h.persist();
  return restored;
}

async function sessions(h, actor) {
  const self = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  const result = await h.ok(actor, 'GET', '/api/v1/web/login-sessions/?namespace=' + encodeURIComponent(self.homeNamespace) + '&accountId=' + self.account.id + '&_pageSize=100');
  if (result.pagination?.hasMore || result.pagination?.total > result.values.length) throw new h.Blocked('Exact session directory requires a complete page reader');
  h.check('BFF session directory is confined to original account and home namespace', result.values.every(x => x.accountId === self.account.id && x.namespace === self.homeNamespace));
  return result.values;
}

async function fresh(h, actor, minutes) {
  const before = await sessions(h, actor), started = Date.now();
  const created = await h.login(actor.identity.account, actor.password, actor.identity.namespace);
  const ended = Date.now(), after = await sessions(h, actor);
  const added = after.filter(x => !before.some(y => y.id === x.id));
  h.check('Independent owner read identifies exactly one newly created session', added.length === 1, added);
  const value = added[0], duration = minutes * 60000;
  h.check('New BFF session has actual expiry under effective current policy', value.createTime >= started - 2000 && value.createTime <= ended + 2000 && value.expiresAt >= started + duration - 2000 && value.expiresAt <= ended + duration + 2000, { minutes, started, ended, session: value });
  return { actor: created, value };
}

async function unchanged(h, actor, original) {
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
  const after = (await sessions(h, actor)).find(x => x.id === original.id);
  h.check('Original session remains usable with its exact original expiry', same(after, original), { original, after });
}

handlers['F056-001'] = async h => {
  const original = await read(h, h.admin), aBefore = await read(h, h.tenantAdmin), bBefore = await read(h, h.otherTenantAdmin);
  h.check('Dedicated tenant policies begin without overrides', !aBefore.override && !bBefore.override);
  const platformMinutes = original.resolved.timeoutMinutes === 90 ? 120 : 90;
  const resource = { kind: 'session-policy-restore', collection: route, id: original.namespace, original, phase: 'created' };
  h.state.resources.push(resource); h.persist();
  try {
    // Save intent before the command. An unknown write cannot be blindly replayed.
    resource.intended = { timeoutMinutes: platformMinutes, expectedResourceVersion: original.override?.resourceVersion || 0 }; h.persist();
    resource.written = (await h.ok(h.admin, 'PUT', route, resource.intended)).value; h.persist();
    h.check('Platform default saves exact duration and source', resource.written.resolved.timeoutMinutes === platformMinutes && resource.written.resolved.sourceNamespace === h.credentials.namespace && !resource.written.resolved.inherited);
    for (const actor of [h.tenantAdmin, h.otherTenantAdmin]) {
      const inherited = await read(h, actor);
      h.check('Each dedicated tenant inherits the platform default', !inherited.override && inherited.resolved.inherited && inherited.resolved.sourceNamespace === h.credentials.namespace && inherited.resolved.timeoutMinutes === platformMinutes);
    }
    await fresh(h, h.admin, platformMinutes);
    const oldA = await fresh(h, h.tenantAdmin, platformMinutes);
    const b = (await h.ok(h.otherTenantAdmin, 'PUT', route, { timeoutMinutes: 180, expectedResourceVersion: 0 })).value;
    h.check('Second tenant has independent explicit policy', b.override?.timeoutMinutes === 180 && !b.resolved.inherited && b.resolved.sourceNamespace === h.otherTenantAdmin.identity.namespace);
    const oldB = await fresh(h, h.otherTenantAdmin, 180);
    const a = (await h.ok(h.tenantAdmin, 'PUT', route, { timeoutMinutes: 45, expectedResourceVersion: 0 })).value;
    h.check('Tenant override saves exact duration and own source', a.override?.timeoutMinutes === 45 && a.resolved.timeoutMinutes === 45 && !a.resolved.inherited && a.resolved.sourceNamespace === h.tenantAdmin.identity.namespace);
    await unchanged(h, oldA.actor, oldA.value);
    await fresh(h, h.tenantAdmin, 45);
    h.check('Tenant override leaves other tenant policy unchanged', same(await read(h, h.otherTenantAdmin), b));
    await unchanged(h, oldB.actor, oldB.value);
    const reset = (await h.ok(h.tenantAdmin, 'DELETE', route)).value;
    h.check('Reset returns to exact platform inheritance', !reset.override && reset.resolved.inherited && reset.resolved.timeoutMinutes === platformMinutes && reset.resolved.sourceNamespace === h.credentials.namespace);
    await fresh(h, h.tenantAdmin, platformMinutes);
    await unchanged(h, oldA.actor, oldA.value);
    await unchanged(h, oldB.actor, oldB.value);
    await h.ok(h.otherTenantAdmin, 'DELETE', route);
    h.check('Second tenant override is formally removed', !(await read(h, h.otherTenantAdmin)).override);
  } finally {
    await restoreSessionPolicy(h, resource);
  }
  const inherited = await read(h, h.tenantAdmin);
  h.check('Tenant inheritance observes restored original platform duration', !inherited.override && inherited.resolved.timeoutMinutes === original.resolved.timeoutMinutes && inherited.resolved.sourceNamespace === original.resolved.sourceNamespace);
};
handlers['F056-001'].actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers, restoreSessionPolicy };
