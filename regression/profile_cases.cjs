// Public CAS authority and Panel profile intersection. No owner-state writes,
// synthetic roles, cached statistics, or credentials borrowed from an admin.
const runner = '/modules/kernel/runner';
const accountModule = '/internal/modules/blocks/account';
const metricsModule = '/internal/modules/blocks/totalizator';
const base = n => '/cas/namespaces/' + n + '/';
const role = (module, key) => ({ module, key });
const profile = role(runner, 'usage-panel-profile-viewer');
const directory = role(accountModule, 'account-viewer');
const metrics = role(metricsModule, 'metrics-viewer');
const has = (rows, ref) => rows.some(row => row.module === ref.module && row.key === ref.key);
const accountCount = value => (value.summary || []).filter(row => row.name === '访问账号');
async function readProfile(h, actor, expected, label) {
  let value;
  for (let attempt = 0; attempt < 10; attempt++) {
    value = (await h.ok(actor, 'GET', '/panel/profile')).value;
    const rows = accountCount(value);
    if (expected === null || rows.length === 1 && rows[0].value === expected) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  const rows = accountCount(value);
  h.check(label, expected === null ? rows.length === 0 : rows.length === 1 && rows[0].value === expected, { expected, summary: value.summary });
  // This fixture grants no other management directory. A profile or metrics
  // role alone must not reveal unrelated counters either.
  if (expected === null) h.check('No unrelated privileged management counters leak through profile/usage grants', value.summary?.length === 0, value);
  return value;
}
async function rendered(h, actor, expected, namespace, label) {
  const context = (await h.ok(actor, 'GET', '/system/context/?surface=panel')).value;
  await actor.page.goto(actor.origin + '/panel/', { waitUntil: 'networkidle' });
  if (context.entryVisibility?.panel === false) {
    const body = await actor.page.locator('body').innerText();
    await h.screenshot(actor, 'profile-panel-entry-denied-' + label.replaceAll(' ', '-'));
    h.check('No-management subject has explicit Panel entry denial and no counters', expected === null && await actor.page.locator('.ant-statistic').count() === 0 && /403|无权|权限|not authorized/i.test(body), { entryVisibility: context.entryVisibility, path: new URL(actor.page.url()).pathname, text: body.slice(0, 1200) });
    return;
  }
  await h.screenshot(actor, 'profile-before-dashboard-assertion-' + label.replaceAll(' ', '-'));
  await actor.page.getByRole('heading', { name: '管理概览', exact: true }).waitFor({ state: 'visible' });
  h.check('Real dashboard displays exact active tenant', await actor.page.locator('[title="' + namespace + '"]').count() > 0);
  const statistic = actor.page.locator('.ant-statistic').filter({ has: actor.page.locator('.ant-statistic-title').getByText('访问账号', { exact: true }) });
  if (expected !== null) await statistic.waitFor({ state: 'visible' });
  h.check(label, expected === null ? await statistic.count() === 0 : await statistic.count() === 1 && (await statistic.locator('.ant-statistic-content-value').innerText()).replace(/,/g, '') === String(expected));
  await h.screenshot(actor, label.replaceAll(' ', '-'));
}
async function currentAuthority(h, namespace, member, refs, keys) {
  const value = (await h.ok(h.admin, 'GET', base(namespace) + 'accounts/' + member.id)).value;
  h.check('CAS owner independently confirms exact original account template sources', value.id === member.id && value.account === member.account && JSON.stringify((value.templateRefs || []).map(r => r.key).sort()) === JSON.stringify([...keys].sort()));
  for (const r of [directory, metrics]) h.check('CAS current effective authority matches ' + r.key, has(value.effectiveRoles || [], r) === refs.includes(r));
}
async function roleMatrix(h) {
  const namespace = h.need('tenantA').name;
  const roles = await h.directory(h.admin, base(namespace) + 'roles/');
  for (const ref of [profile, directory, metrics]) if (!roles.some(r => r.status === 2 && r.module === ref.module && r.key === ref.key)) throw new h.Blocked('Deployment is missing formal enabled builtin role ' + ref.module + ':' + ref.key + '; never synthesize it');
  const combinations = [[], [directory], [metrics], [directory, metrics]];
  const fixtures = [];
  for (const [index, refs] of combinations.entries()) {
    const t = await h.create(base(namespace) + 'role-templates/', { key: h.state.prefix + '-profile-' + index, name: '概览权限组合' + index, description: '目录与指标交集验证', subjectType: 'account', roleRefs: [profile, ...refs], applicationAccess: [], status: 2 }, 'role-template');
    const keys = ['portal-user', t.key];
    const member = await h.create(base(namespace) + 'accounts/', { account: h.state.prefix + '-profile-' + index, displayName: '概览权限成员' + index, password: h.state.password, email: '', description: '', roleTemplateKeys: keys, status: 2 }, 'account');
    fixtures.push({ refs, t, member, keys });
  }
  const accounts = await h.directory(h.tenantAdmin, base(namespace) + 'accounts/');
  for (const [index, f] of fixtures.entries()) {
    await currentAuthority(h, namespace, f.member, f.refs, f.keys);
    const actor = await h.login(f.member.account, h.state.password, namespace, h.state.password + 'P' + index);
    f.actor = actor;
    const count = f.refs.includes(directory) && f.refs.includes(metrics) ? accounts.length : null;
    if (f.refs.includes(directory)) {
      const actual = await h.directory(actor, base(namespace) + 'accounts/');
      h.check('Original directory-only/both subject reads exact independent owner account identities', actual.length === accounts.length && accounts.every(row => actual.some(r => r.id === row.id && r.account === row.account)));
    } else h.denied(await h.api(actor, 'GET', base(namespace) + 'accounts/'), 'No directory grant remains denied through direct API even with metrics authority');
    await readProfile(h, actor, count, 'Four-way server permission intersection ' + index);
    await rendered(h, actor, count, namespace, 'Four-way browser permission intersection ' + index);
  }
  const f = fixtures[3];
  // Revoke each independent permission on the same original session, restoring
  // the acknowledged original template between probes. No replacement login.
  for (const missing of [directory, metrics]) {
    const retained = missing === directory ? metrics : directory;
    const replacement = fixtures[missing === directory ? 2 : 1];
    const keys = ['portal-user', replacement.t.key];
    await h.ok(h.admin, 'PUT', base(namespace) + 'accounts/' + f.member.id + '/role-templates', { roleTemplateKeys: keys });
    await currentAuthority(h, namespace, f.member, [retained], keys);
    const session = (await h.ok(f.actor, 'GET', '/api/v1/web/session/')).value;
    h.check('Authority revocation preserves exact original authenticated subject', session.account.id === f.member.id && session.homeNamespace === namespace && session.activeNamespace === namespace);
    await readProfile(h, f.actor, null, 'Revoked ' + missing.key + ' cannot preserve original management counter');
    await rendered(h, f.actor, null, namespace, 'Browser drops revoked ' + missing.key);
    await h.ok(h.admin, 'PUT', base(namespace) + 'accounts/' + f.member.id + '/role-templates', { roleTemplateKeys: f.keys });
    await currentAuthority(h, namespace, f.member, f.refs, f.keys);
    await readProfile(h, f.actor, accounts.length, 'Formal original assignment restores counter on same session');
  }
}
async function scopeSwitch(h) {
  const actor = await h.login(h.credentials.account, h.credentials.password);
  const original = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  const a = h.need('tenantA').name, b = h.need('tenantB').name;
  const countA = (await h.directory(h.tenantAdmin, base(a) + 'accounts/')).length;
  const countB = (await h.directory(h.otherTenantAdmin, base(b) + 'accounts/')).length;
  h.check('Independent owner fixtures have distinct counts to detect stale tenant data', countA !== countB, { a, b, countA, countB });
  let release, held, timer;
  const gate = new Promise(resolve => { release = resolve; });
  const ready = new Promise((resolve, reject) => { held = resolve; timer = setTimeout(() => reject(new h.Blocked('Original live profile GET was not captured before scope switch')), 30000); });
  ready.catch(() => {});
  let intercepted = false, delayedResponse, settled, routeError;
  const pattern = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/panel/profile';
  const routeHandler = async route => {
    if (intercepted) return route.continue();
    intercepted = true;
    let resolveSettled; settled = new Promise(resolve => { resolveSettled = resolve; });
    try {
      const response = await route.fetch({ timeout: 30000 });
      delayedResponse = { status: response.status(), data: await response.json() };
      held(); clearTimeout(timer);
      await gate;
      try { await route.fulfill({ response }); } catch (error) {
        // A real full-page namespace switch may cancel its old document GET.
        if (!/closed|disposed|canceled|cancelled|intercept|invalid|aborted/i.test(error.message)) routeError = error.message;
      }
    } catch (error) { routeError = error.message; held(); clearTimeout(timer); } finally { resolveSettled(); }
  };
  try {
    await h.ok(actor, 'PUT', '/api/v1/web/session/namespace', { namespace: a });
    await readProfile(h, actor, countA, 'Managed direct profile uses exact first tenant');
    await actor.page.route(pattern, routeHandler);
    await actor.page.goto(actor.origin + '/panel/', { waitUntil: 'domcontentloaded' });
    await ready;
    if (routeError) throw new h.Blocked('Original profile response transport failed: ' + routeError);
    h.check('Delayed result is an actual authorized original tenant owner response', delayedResponse.status === 200 && !delayedResponse.data.error && accountCount(delayedResponse.data.value).length === 1 && accountCount(delayedResponse.data.value)[0].value === countA, delayedResponse);
    await actor.page.locator('.magic-layout-user-area button').first().hover();
    await actor.page.getByText('切换租户空间', { exact: true }).click();
    const dialog = actor.page.getByRole('dialog', { name: '切换当前租户空间' });
    await dialog.locator('.ant-select-selector').click();
    await actor.page.locator('.ant-select-item-option').filter({ hasText: b }).click();
    const switched = actor.page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/web/session/namespace' && r.request().method() === 'PUT');
    await dialog.getByRole('button', { name: /确\s*定/ }).click();
    const response = await switched;
    h.check('Real browser switch acknowledges exact requested tenant', response.status() === 200);
    await actor.page.getByRole('heading', { name: '管理概览', exact: true }).waitFor({ state: 'visible' });
    await actor.page.locator('[title="' + b + '"]').first().waitFor({ state: 'visible' });
    release(); await settled;
    if (routeError) throw new h.Blocked('Delayed original profile response could not settle: ' + routeError);
    await actor.page.waitForLoadState('networkidle');
    const current = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
    h.check('Switch preserves original account/home while changing only verified active scope', current.account.id === original.account.id && current.homeNamespace === original.homeNamespace && current.activeNamespace === b);
    await readProfile(h, actor, countB, 'Post-switch direct API excludes old tenant count');
    const statistic = actor.page.locator('.ant-statistic').filter({ has: actor.page.locator('.ant-statistic-title').getByText('访问账号', { exact: true }) });
    await statistic.waitFor({ state: 'visible' });
    h.check('Late original tenant response cannot replace new tenant dashboard count', (await statistic.locator('.ant-statistic-content-value').innerText()).replace(/,/g, '') === String(countB), { old: countA, current: countB });
    await h.screenshot(actor, 'profile-after-real-tenant-switch-and-late-response');
  } finally {
    clearTimeout(timer); release(); if (settled) await settled;
    await actor.page.unroute(pattern, routeHandler);
    const current = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
    if (current.activeNamespace !== original.activeNamespace) await h.ok(actor, 'PUT', '/api/v1/web/session/namespace', { namespace: original.activeNamespace });
    h.check('Original managed session formally restored after scope probe', (await h.ok(actor, 'GET', '/api/v1/web/session/')).value.activeNamespace === original.activeNamespace);
  }
}
async function governance(h) { await roleMatrix(h); await scopeSwitch(h); }
governance.actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers: { 'F066-002': governance } };
