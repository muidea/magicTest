// Current public CAS/BFF contracts. No private state or role-definition writes.
const handlers = {};
const runner = '/modules/kernel/runner';
const authorization = '/internal/modules/kernel/authorization';
const ref = (module, key) => ({ module, key });
const runnerRef = key => ref(runner, key);
const casBase = n => '/cas/namespaces/' + n + '/';
const profile = 'portal-user';
const catalogCollection = '/panel/infra/catalogs/';
const serviceCollection = '/panel/hub/services/';
const rejectedAuthentication = r => r.status === 401 || r.data?.error?.code === 11;
const authoritySets = new Set(['templateRefs', 'effectiveRoles', 'effectivePrivileges', 'roleRefs']);
function canonical(value, key = '') {
  if (Array.isArray(value)) {
    const values = value.map(item => canonical(item));
    return authoritySets.has(key) ? values.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))) : values;
  }
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(name => [name, canonical(value[name], name)]));
  return value;
}

async function exact(h, actor, route, before, message) {
  const after = (await h.ok(actor, 'GET', route)).value;
  h.check(message, JSON.stringify(canonical(after)) === JSON.stringify(canonical(before)));
}

async function template(h, n, suffix, roleRefs, actorName = 'admin') {
  const payload = { key: h.state.prefix + '-' + suffix, name: '回归模板 ' + suffix,
    description: '当前用例受控委派模板', subjectType: 'account', roleRefs, applicationAccess: [], status: 2 };
  const value = await h.createAs(actorName, casBase(n) + 'role-templates/', payload, 'role-template');
  return { value, payload };
}

async function member(h, n, suffix, keys) {
  return h.create(casBase(n) + 'accounts/', { account: h.state.prefix + '-' + suffix,
    displayName: '回归成员 ' + suffix, email: '', description: '', password: h.state.password,
    roleTemplateKeys: keys, status: 2 }, 'account');
}

async function authority(h, n, account, expectedKeys, expectedRoles, absentRoles = []) {
  const value = (await h.ok(h.admin, 'GET', casBase(n) + 'accounts/' + account.id)).value;
  const keys = (value.templateRefs || []).map(x => x.key).sort();
  h.check('CAS independently confirms exact template sources for ' + account.account,
    JSON.stringify(keys) === JSON.stringify([...expectedKeys].sort()), { expectedKeys, actualKeys: keys });
  for (const role of expectedRoles) h.check('CAS effective role contains ' + role.key,
    value.effectiveRoles?.some(x => x.module === role.module && x.key === role.key));
  for (const role of absentRoles) h.check('CAS effective role excludes ' + role.key,
    !value.effectiveRoles?.some(x => x.module === role.module && x.key === role.key));
  return value;
}

async function catalog(h, suffix) {
  return h.createAs('tenantAdmin', catalogCollection,
    { name: h.state.prefix + '-' + suffix, description: '当前授权用例受控分类', parent: null }, 'catalog');
}

async function authenticated(h, actor, label) {
  const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  h.check(label, session.homeNamespace === actor.identity.namespace && session.account.account === actor.identity.account);
}

handlers['F005-001'] = async h => {
  const n = h.need('tenantA').name, base = casBase(n);
  const roles = await h.ok(h.tenantAdmin, 'GET', base + 'roles/?_pageSize=100');
  if (roles.pagination?.hasMore || roles.pagination?.total > roles.values.length) throw new h.Blocked('Current role directory spans pages; complete role reader required before asserting catalogue consistency');
  const originalRole = runnerRef('management-service-manager'), editedRole = runnerRef('management-catalog-manager');
  for (const role of [originalRole, editedRole]) h.check('Role directory exposes exact enabled role ' + role.key,
    roles.values.some(x => x.module === role.module && x.key === role.key && x.status === 2));
  const t = await template(h, n, 'edit-template', [originalRole]);
  const route = base + 'role-templates/' + t.value.id;
  const updated = { ...t.payload, name: '已编辑回归模板', description: '模板已切换分类管理角色', roleRefs: [editedRole] };
  await h.ok(h.admin, 'PUT', route, updated);
  const saved = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Template edit persists exact role composition and new owner revision', saved.key === t.payload.key && saved.name === updated.name && saved.description === updated.description && saved.version > t.value.version && saved.roleRefs?.length === 1 && saved.roleRefs[0].module === editedRole.module && saved.roleRefs[0].key === editedRole.key, saved);
  const account = await member(h, n, 'template-member', [profile]);
  const actor = await h.login(account.account, h.state.password, n, h.state.password + 'T');
  const target = await catalog(h, 'template-target');
  h.denied(await h.api(actor, 'GET', catalogCollection + target.id), 'Member cannot read managed category before template assignment');
  await h.ok(h.admin, 'PUT', base + 'accounts/' + account.id + '/role-templates', { roleTemplateKeys: [profile, t.value.key] });
  await authority(h, n, account, [profile, t.value.key], [editedRole], [originalRole]);
  await authenticated(h, actor, 'Template assignment preserves same original authenticated session');
  const read = (await h.ok(actor, 'GET', catalogCollection + target.id)).value;
  h.check('Assigned member can read exact real category', read.id === target.id && read.name === target.name);
  await h.ok(actor, 'PUT', catalogCollection + target.id, { name: target.name + '-edited', description: '模板分配后真实修改', parent: null });
  const after = (await h.ok(h.tenantAdmin, 'GET', catalogCollection + target.id)).value;
  h.check('Independent owner read proves edited template grants actual write', after.name === target.name + '-edited' && after.description === '模板分配后真实修改');
  h.denied(await h.api(actor, 'GET', serviceCollection), 'Replaced service role is not accidentally granted by template history');
};

handlers['F005-002'] = async h => {
  const n = h.need('tenantA').name, base = casBase(n);
  const low = runnerRef('management-catalog-manager'), high = runnerRef('management-service-manager');
  const delegation = await template(h, n, 'delegator', [ref(authorization, 'role-template-manager'), low]);
  const manager = await member(h, n, 'delegator', [profile, delegation.value.key]);
  const actor = await h.login(manager.account, h.state.password, n, h.state.password + 'D');
  h.limitedTemplateManager = actor;
  const target = await catalog(h, 'delegator-target');
  await h.ok(actor, 'GET', catalogCollection + target.id);
  h.denied(await h.api(actor, 'GET', serviceCollection), 'Limited manager does not own requested higher service authority');
  const allowed = await template(h, n, 'delegated-low', [low], 'limitedTemplateManager');
  const highTemplate = await template(h, n, 'higher-owned', [high]);
  const subject = await member(h, n, 'delegated-member', [profile, allowed.value.key]);
  const route = base + 'role-templates/' + allowed.value.id;
  const templateBefore = (await h.ok(h.admin, 'GET', route)).value;
  const accountBefore = (await h.ok(h.admin, 'GET', base + 'accounts/' + subject.id)).value;
  const ceiling = (response, label) => {
    h.denied(response, label);
    h.check(label + ' reaches CAS functional delegation ceiling', response.data?.error?.message === 'functional delegation exceeds caller authority', response);
  };
  const createPayload = { ...allowed.payload, key: h.state.prefix + '-forbidden-template', roleRefs: [high] };
  const created = await h.api(actor, 'POST', base + 'role-templates/', createPayload);
  if (h.good(created) && created.data.value?.id) h.owned(base + 'role-templates/', created.data.value, 'unexpected-template');
  ceiling(created, 'Cannot create a template above own authority');
  ceiling(await h.api(actor, 'PUT', route, { ...allowed.payload, roleRefs: [low, high] }), 'Cannot enlarge an existing template above own authority');
  ceiling(await h.api(actor, 'POST', base + 'accounts/' + subject.id + '/authority/preview', { roleTemplateKeys: [profile, highTemplate.value.key] }), 'Authority preview cannot escape same delegation ceiling');
  // Avoid the broad portal-user preset here: its unrelated usage-role ceiling
  // would reject before the exact higher role targeted by this test.
  ceiling(await h.api(actor, 'PUT', base + 'accounts/' + subject.id + '/role-templates', { roleTemplateKeys: [highTemplate.value.key] }), 'Cannot assign higher owner template to a member');
  ceiling(await h.api(actor, 'POST', base + 'role-templates/' + highTemplate.value.id + '/synchronize'), 'Template synchronization cannot bypass delegation ceiling');
  await exact(h, h.admin, route, templateBefore, 'Rejected create/edit leaves original low template exact');
  await exact(h, h.admin, base + 'accounts/' + subject.id, accountBefore, 'Rejected assignments leave original member authority exact');
  await authority(h, n, subject, [profile, allowed.value.key], [low], [high]);
  const list = (await h.ok(h.admin, 'GET', base + 'role-templates/?_pageSize=100')).values;
  h.check('Rejected creation leaves no higher template residue', !list.some(x => x.key === createPayload.key));
  await authenticated(h, actor, 'Ceiling refusals preserve original limited manager session');
};

handlers['F005-003'] = async h => {
  const n = h.need('tenantA').name, base = casBase(n);
  const commonRole = runnerRef('management-catalog-manager'), uniqueRole = runnerRef('management-service-manager');
  const first = await template(h, n, 'source-first', [commonRole, uniqueRole]);
  const second = await template(h, n, 'source-second', [commonRole]);
  const account = await member(h, n, 'sources-member', [profile, first.value.key, second.value.key]);
  const actor = await h.login(account.account, h.state.password, n, h.state.password + 'S');
  const target = await catalog(h, 'source-target');
  await h.ok(actor, 'GET', serviceCollection);
  await h.ok(actor, 'GET', catalogCollection + target.id);
  const templateBefore = (await h.ok(h.admin, 'GET', base + 'role-templates/' + first.value.id)).value;
  const refusal = await h.api(h.admin, 'DELETE', base + 'role-templates/' + first.value.id);
  h.check('CAS refuses deletion of an actually bound template', !h.good(refusal) && refusal.data?.error?.message === 'role template ' + first.value.key + ' is bound by subjects; unbind it before deletion', refusal);
  await exact(h, h.admin, base + 'role-templates/' + first.value.id, templateBefore, 'In-use delete refusal preserves original template');
  await authority(h, n, account, [profile, first.value.key, second.value.key], [commonRole, uniqueRole]);
  await h.ok(h.admin, 'PUT', base + 'accounts/' + account.id + '/role-templates', { roleTemplateKeys: [profile, second.value.key] });
  await authority(h, n, account, [profile, second.value.key], [commonRole], [uniqueRole]);
  await authenticated(h, actor, 'Source removal keeps the same original login valid');
  h.denied(await h.api(actor, 'GET', serviceCollection), 'Removed template unique service authority is no longer usable');
  await h.ok(actor, 'PUT', catalogCollection + target.id, { name: target.name, description: '另一模板保持分类修改权', parent: null });
  const beforeFinalRemoval = (await h.ok(h.tenantAdmin, 'GET', catalogCollection + target.id)).value;
  h.check('Overlapping second template preserves actual category write', beforeFinalRemoval.description === '另一模板保持分类修改权');
  await h.remove(base + 'role-templates/', first.value.id);
  await h.gone(base + 'role-templates/', first.value.id);
  await h.ok(h.admin, 'PUT', base + 'accounts/' + account.id + '/role-templates', { roleTemplateKeys: [profile] });
  await authority(h, n, account, [profile], [], [commonRole, uniqueRole]);
  await authenticated(h, actor, 'Final source removal changes authority, not authentication identity');
  h.denied(await h.api(actor, 'PUT', catalogCollection + target.id, { name: 'MUST NOT CHANGE', description: '', parent: null }), 'Final source removal denies category mutation on original session');
  await exact(h, h.tenantAdmin, catalogCollection + target.id, beforeFinalRemoval, 'Owner proves refused post-revocation write did not persist');
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
};

async function casSessions(h, n, account, auditor) {
  const listed = await h.ok(auditor, 'GET', casBase(n) + 'oauth/sessions/?accountId=' + account.id + '&_pageSize=100');
  if (listed.pagination?.hasMore || listed.pagination?.total > listed.values.length) throw new h.Blocked('Dedicated account SSO directory unexpectedly spans pages');
  h.check('CAS session directory stays within exact account and namespace', listed.values.every(x => x.accountId === account.id && x.namespace === n));
  return listed.values;
}

async function currentLogout(h, actor, peer, auditor, account) {
  const namespace = actor.identity.namespace;
  const route = '/api/v1/web/login-sessions/?namespace=' + encodeURIComponent(namespace) + '&accountId=' + account.id + '&_pageSize=100';
  const before = (await h.ok(auditor, 'GET', route)).values;
  h.check('BFF owner proves two original independent sessions before logout', before.length === 2 && before.every(x => x.accountId === account.id && x.namespace === namespace));
  const replay = await h.sessionAtOrigin(actor, actor.origin);
  await authenticated(h, replay, 'Retained original BFF credential works before logout');
  await actor.page.goto(actor.origin + '/api/v1/web/auth/logout', { waitUntil: 'networkidle', timeout: 30000 });
  const expired = await h.api(replay, 'GET', '/api/v1/web/session/');
  h.check('Logout invalidates retained original credential at server owner', rejectedAuthentication(expired), expired);
  const protectedAccess = await h.api(replay, 'GET', '/system/context/?surface=portal');
  h.check('Logged-out original credential cannot invoke previously working protected resource', rejectedAuthentication(protectedAccess), protectedAccess);
  await authenticated(h, peer, 'Other independent original session survives exact logout');
  const after = (await h.ok(auditor, 'GET', route)).values;
  h.check('BFF independently confirms exactly one original session remains', after.length === 1 && before.some(x => x.id === after[0].id));
  const removed = before.filter(x => !after.some(y => x.id === y.id));
  h.check('BFF exact revoked session has an original owner identity', removed.length === 1 && removed[0].id !== after[0].id, { revokedSession: removed[0], survivingSession: after[0] });
}

handlers['F001-001'] = async h => {
  const created = await h.create('/panel/namespace-onboardings/', { name: h.state.prefix + 'first', description: '首次改密与退出独立夹具', scope: [], status: 2, startTime: Date.now() - 1000, expireTime: Date.now() + 86400000, initialAdminPassword: h.state.password }, 'namespace');
  const accounts = (await h.ok(h.admin, 'GET', casBase(created.name) + 'accounts/?_pageSize=100')).values;
  h.check('Fresh tenant has exactly one owner-created bootstrap administrator', accounts.length === 1 && accounts[0].status === 2);
  const account = accounts[0];
  // OAuth management is namespace-local, even for platform governance admins.
  const observerAccount = await member(h, created.name, 'local-auditor', [profile, 'tenant-security-admin']);
  const observer = await h.login(observerAccount.account, h.state.password, created.name, h.state.password + 'A');
  let restricted = false;
  const actor = await h.login(account.account, h.state.password, created.name, h.state.password + 'F', async pending => {
    h.check('First login reaches official mandatory password change form', await pending.page.locator('form[action="/oauth/password/change"]').count() === 1);
    const noSession = await h.api(pending, 'GET', '/api/v1/web/session/');
    h.check('Before first password change no BFF session is usable', rejectedAuthentication(noSession), noSession);
    const protectedAccess = await h.api(pending, 'GET', '/system/context/?surface=portal');
    h.check('Before first password change protected application operation is refused', rejectedAuthentication(protectedAccess), protectedAccess);
    h.check('First password-change transaction creates no CAS SSO session', (await casSessions(h, created.name, account, observer)).length === 0);
    restricted = true;
    await h.screenshot(pending, 'mandatory-password-change');
  });
  h.check('First-login restriction was actually exercised before change', restricted && actor.passwordChanged === true);
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
  const sso = await casSessions(h, created.name, account, observer);
  h.check('CAS independently confirms authenticated first-login account after change', sso.length === 1 && sso[0].account === account.account);
  const peer = await h.login(account.account, actor.password, created.name);
  h.check('Fresh subsequent login no longer requires first password change', peer.passwordChanged !== true);
  await h.screenshot(peer, 'after-password-change');
  await currentLogout(h, actor, peer, observer, account);
  await authenticated(h, h.admin, 'Panel administrator survives first-login tenant logout');
  await authenticated(h, h.otherTenantAdmin, 'Other tenant original session survives first-login logout');
};

handlers['F001-003'] = async h => {
  const n = h.need('tenantA').name;
  const account = await member(h, n, 'session-target', [profile]);
  const before = await casSessions(h, n, account, h.tenantAdmin);
  h.check('New credential target has no preexisting CAS SSO sessions', before.length === 0);
  await h.rejectedLogin(account.account, h.state.password + 'wrong', n);
  h.check('Wrong password does not create a CAS SSO session', (await casSessions(h, n, account, h.tenantAdmin)).length === 0);
  const bff = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/login-sessions/?namespace=' + n + '&accountId=' + account.id + '&_pageSize=100')).values;
  h.check('Wrong password creates no independent BFF owner session', bff.length === 0);
  const actor = await h.login(account.account, h.state.password, n, h.state.password + 'L');
  const peer = await h.login(account.account, actor.password, n);
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
  await currentLogout(h, actor, peer, h.tenantAdmin, account);
  await authenticated(h, h.user, 'Other account original session survives exact session revocation');
};

for (const handler of Object.values(handlers)) handler.actors = ['user', 'tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers };
