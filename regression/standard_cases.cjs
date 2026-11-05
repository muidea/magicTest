const crypto = require('node:crypto');
const handlers = {};
const fixturesDir = h => h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression');
const accountBase = h => '/cas/namespaces/' + h.state.fixtures.tenantA.name + '/accounts/';
const definitionBase = '/panel/application/definitions/';
const policy = '/panel/session-policy/';
const retention = '/panel/operations/log-retention/';
async function same(h, actor, route, before, label) { const after = (await h.ok(actor, 'GET', route)).value; h.check(label, JSON.stringify(after) === JSON.stringify(before)); }
async function model(h) {
  if (!h.state.fixtures.model) {
    const body = JSON.parse(h.fs.readFileSync(h.path.join(fixturesDir(h), 'fixture-definition-create-request.json')));
    Object.assign(body, { uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-model', showName: '常规回归模型', pkgPrefix: h.state.prefix });
    h.state.fixtures.model = await h.create(definitionBase, body, 'definition'); h.persist();
  }
  return (await h.ok(h.admin, 'GET', definitionBase + h.state.fixtures.model.id)).value;
}
handlers['F003-001'] = async h => {
  const n = h.need('tenantA');
  const original = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + n.id)).value;
  const panelPeer = await h.login(h.credentials.account, h.credentials.password);
  const unaffected = [h.admin, panelPeer, h.otherTenantAdmin];
  const assertUnrelatedSessions = async () => {
    for (const actor of unaffected) {
      const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
      h.check('Unrelated original login survives namespace mutation', session.homeNamespace === actor.identity.namespace && session.account.account === actor.identity.account);
    }
  };
  let current = original;
  try {
    for (const status of [1, 2]) {
      const saved = (await h.ok(h.admin, 'PUT', '/panel/namespace-onboardings/' + n.id, { expectedVersion: current.updateTime, description: '常规回归空间编辑', scope: [], status, startTime: current.startTime, expireTime: current.expireTime })).value;
      await assertUnrelatedSessions();
      current = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + n.id)).value;
      h.check('Space settings independently persisted', current.description === '常规回归空间编辑' && current.status === status && saved.id === n.id);
      const access = await h.api(h.user, 'GET', '/system/context/?surface=portal');
      h.check('Target old session remains invalid after disable or reenable', access.status === 401 || [5, 11, 12, 22].includes(access.data?.error?.code));
      if (status === 2) {
        const fresh = await h.login(h.user.identity.account, h.user.password, n.name);
        const freshAccess = await h.api(fresh, 'GET', '/system/context/?surface=portal');
        h.check('Reenabled namespace accepts fresh login', h.good(freshAccess));
      }
    }
    const list = (await h.ok(h.admin, 'GET', '/cas/namespaces/?_pageSize=100')).values;
    h.check('Namespace directory contains exact resource', list.some(x => x.id === n.id && x.name === n.name));
  } finally {
    await h.authorizedAdmin();
    current = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + n.id)).value;
    if (current.status !== original.status) {
      await h.ok(h.admin, 'PUT', '/panel/namespace-onboardings/' + n.id, { expectedVersion: current.updateTime, description: original.description, scope: original.scope || [], status: original.status, startTime: original.startTime, expireTime: original.expireTime });
      await h.authorizedAdmin();
      const restored = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + n.id)).value;
      h.check('Original namespace restored through owner', restored.id === n.id && restored.status === original.status);
    }
  }
};
handlers['F003-002'] = async h => {
  const root = (await h.ok(h.admin, 'GET', '/cas/namespaces/?_pageSize=100')).values.find(x => x.name === h.credentials.namespace);
  for (const actor of [h.user, h.tenantAdmin]) {
    h.denied(await h.api(actor, 'PUT', '/panel/namespace-onboardings/' + root.id, { expectedVersion: root.updateTime, description: 'Forbidden change', scope: ['*'], status: root.status, startTime: root.startTime, expireTime: root.expireTime }), 'Ordinary namespace cannot manage platform root');
  }
  await same(h, h.admin, '/cas/namespaces/' + root.id, root, 'Root namespace remains exact');
};
handlers['F004-002'] = async h => {
  const a = h.need('tenantA'), b = h.need('tenantB');
  const rows = (await h.ok(h.tenantAdmin, 'GET', '/cas/namespaces/' + a.name + '/accounts/?_pageSize=100')).values;
  h.check('Managed namespace administrator sees own member', rows.some(x => x.id === h.state.fixtures.user.id));
  h.denied(await h.api(h.tenantAdmin, 'GET', '/cas/namespaces/' + b.name + '/accounts/'), 'Other namespace directory denied');
  const session = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
  h.check('Account original namespace unchanged', session.homeNamespace === a.name);
  await h.partial('Account directory isolation verified; in-scope account mutation and out-of-scope mutation still need paired verification.');
};
handlers['F004-003'] = async h => {
  const body = { account: h.need('user').account, displayName: 'Duplicate test', password: h.state.password, status: 2, roleTemplateKeys: ['portal-user'] };
  const before = (await h.ok(h.admin, 'GET', accountBase(h) + '?_pageSize=100')).values;
  for (const [index, payload] of [body, { ...body, account: '' }, { ...body, account: h.state.prefix + '-invalid', password: '' }].entries()) {
    const r = await h.api(h.admin, 'POST', accountBase(h), payload);
    if (h.good(r) && r.data.value?.id) h.owned(accountBase(h), r.data.value, 'unexpected-account');
    if (index === 0) h.check('Duplicate account explicitly rejected by CAS', r.status === 200 && [6, 7].includes(r.data.error?.code) && r.data.error.message === 'Account ' + body.account + ' already exists' && r.data.value == null, r);
    else h.invalid(r, 'Empty account/empty password rejected');
    h.check('Response does not expose submitted password', !JSON.stringify(r).includes(h.state.password));
  }
  const after = (await h.ok(h.admin, 'GET', accountBase(h) + '?_pageSize=100')).values;
  h.check('No duplicate or invalid accounts created', JSON.stringify(before) === JSON.stringify(after));
};
handlers['F010-002'] = async h => {
  const other = h.need('tenantB').name;
  const r = await h.api(h.user, 'GET', '/cas/namespaces/' + other + '/accounts/?namespace=' + other, undefined, { 'X-Namespace': other, 'X-Magic-Subject': 'account:1', 'X-Magic-Ext-Data': JSON.stringify({ namespace: other, actorSubject: 'account:1' }), 'X-Magic-Management-Debug': 'true' });
  h.denied(r, 'Forged namespace and identity headers do not grant authority');
  const session = (await h.ok(h.user, 'GET', '/api/v1/web/session/')).value;
  h.check('Original namespace remains authoritative', session.homeNamespace === h.need('tenantA').name);
};
handlers['F011-002'] = async h => {
  const m = await model(h), body = JSON.parse(h.fs.readFileSync(h.path.join(fixturesDir(h), 'fixture-definition-create-request.json')));
  for (const payload of [ { ...body, uuid: m.uuid, name: m.name }, { ...body, uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-bad', pkgPrefix: '../invalid' }, { ...body, uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-nostorage', storage: { required: true, engine: '', slots: [] } } ]) {
    const r = await h.api(h.admin, 'POST', definitionBase, payload);
    if (h.good(r) && r.data.value?.id) h.owned(definitionBase, r.data.value, 'unexpected-definition');
    h.invalid(r, 'Invalid prefix, duplicate identity or required storage rejected');
  }
  const rows = (await h.ok(h.admin, 'GET', definitionBase + '?_pageSize=100')).values;
  h.check('Only one legal definition persisted', rows.filter(x => x.name.startsWith(h.state.prefix)).length === 1);
};
handlers['F011-003'] = async h => {
  const m = await model(h), before = (await h.ok(h.admin, 'GET', definitionBase + m.id)).value;
  for (const actor of [h.user, h.tenantAdmin]) {
    h.inaccessible(await h.api(actor, 'GET', definitionBase + m.id), 'Cross namespace definition not readable');
    h.inaccessible(await h.api(actor, 'PUT', definitionBase + m.id, { expectedDefinitionVersion: m.updateTime, description: 'MUST NOT PERSIST' }), 'Unauthorized definition edit denied');
  }
  await same(h, h.admin, definitionBase + m.id, before, 'Rejected edits preserve definition');
};
handlers['F018-002'] = async h => {
  const m = await model(h), route = definitionBase + m.id + '/model-draft';
  const payload = JSON.parse(h.fs.readFileSync(h.path.join(fixturesDir(h), 'fixture-draft-atomic-save-request.json')));
  payload.expectedDefinitionVersion = m.updateTime;
  payload.entities[0].pkgPath = '/' + h.state.prefix;
  const outcomes = await Promise.all([h.api(h.admin, 'PUT', route, payload), h.api(h.admin, 'PUT', route, payload)]);
  h.check('Exactly one same-version concurrent atomic save succeeds', outcomes.filter(h.good).length === 1, outcomes);
  const read = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Entity and bindings independently preserved', read.entities.length === 1 && read.entities[0].fields.length === payload.entities[0].fields.length && read.entities[0].pkgPath === '/' + h.state.prefix);
};
handlers['F016-003'] = async h => {
  const m = await model(h), route = definitionBase + m.id + '/function-blocks', before = (await h.ok(h.admin, 'GET', route)).value;
  for (const actor of [h.user, h.tenantAdmin]) h.inaccessible(await h.api(actor, 'PUT', route, { expectedDefinitionVersion: before.definitionVersion, content: before.content }), 'Readonly/other namespace cannot edit script library');
  await same(h, h.admin, route, before, 'Library is unchanged');
  await h.partial('Cross-namespace library write rejected; a same-namespace readonly author and binding-save bypass fixture are still required.');
};
handlers['F037-002'] = async h => {
  // A real owned service is necessary to prove resource authorization, not only collection denial.
  await h.partial('No current owned published service and ordinary subscriber fixture; collection denial alone is insufficient.');
};
handlers['F047-003'] = async h => {
  const db = (await h.ok(h.admin, 'GET', '/panel/operations/database-instances/?_pageSize=100')).values[0];
  if (!db) throw new h.Blocked('No current configured database resource');
  for (const actor of [h.user, h.tenantAdmin]) {
    h.denied(await h.api(actor, 'GET', '/panel/operations/database-instances/' + db.id), 'Database details denied without resource permission');
    h.denied(await h.api(actor, 'GET', '/panel/operations/database-instances/' + db.id + '/explorer/settings'), 'Sensitive resource configuration denied');
  }
  h.check('Resource catalog does not expose password', !db.password || db.password === '******');
};
handlers['F055-003'] = async h => {
  const before = (await h.ok(h.admin, 'GET', '/panel/namespace-branding/')).value;
  h.denied(await h.api(h.user, 'PUT', '/panel/namespace-branding/?namespace=panel', { displayName: 'Forbidden global brand', expectedResourceVersion: before.override?.resourceVersion || 0 }), 'Ordinary tenant cannot edit global branding');
  await same(h, h.admin, '/panel/namespace-branding/', before, 'Global branding remains exact');
  await h.partial('Ordinary user write rejected; tenant customizer with a proved successful own-tenant branding operation is still required.');
};
handlers['F056-002'] = async h => {
  const before = (await h.ok(h.admin, 'GET', policy)).value;
  for (const timeoutMinutes of [0, -1, 999999999]) h.invalid(await h.api(h.admin, 'PUT', policy, { timeoutMinutes, expectedResourceVersion: before.override?.resourceVersion || 0 }), 'Invalid session duration rejected');
  h.invalid(await h.api(h.admin, 'PUT', policy, { timeoutMinutes: 120, expectedResourceVersion: 922337203685477 }), 'Stale resource version rejected');
  await same(h, h.admin, policy, before, 'Invalid duration/version does not change effective policy');
};
handlers['F056-003'] = async h => {
  const before = (await h.ok(h.admin, 'GET', policy)).value;
  h.denied(await h.api(h.user, 'PUT', policy, { timeoutMinutes: 120, expectedResourceVersion: 0 }), 'Ordinary subject cannot save session policy');
  await same(h, h.admin, policy, before, 'Unauthorized policy changes do not change effective policy');
};
handlers['F058-003'] = async h => {
  const before = (await h.ok(h.admin, 'GET', retention)).value;
  for (const actor of [h.user, h.tenantAdmin]) h.denied(await h.api(actor, 'PUT', retention, { expectedResourceVersion: 0, policies: [] }), 'Non-default namespace / unprivileged subject cannot change global retention');
  await same(h, h.admin, retention, before, 'Global retention remains exact');
};
handlers['F051-003'] = async h => {
  const collection = '/panel/infra/catalogs/';
  const c = await h.create(collection, { name: h.state.prefix + '-catalog', description: 'temporary regression', parentID: 0 }, 'catalog');
  for (const [method, route, body] of [['POST', collection, { name: h.state.prefix + '-forbidden' }], ['PUT', collection + c.id, { name: 'MUST NOT CHANGE' }]]) h.denied(await h.api(h.user, method, route, body), 'Readonly subject cannot write category');
  const after = (await h.ok(h.admin, 'GET', collection + c.id)).value;
  h.check('Unauthorized writes preserve category name', after.name === c.name);
  await h.partial('Unprivileged category writes rejected; a same-tenant subject with successful catalog reads and denied writes is still required.');
};
for (const id of ['F003-001', 'F003-002', 'F004-002', 'F004-003', 'F010-002', 'F011-003', 'F016-003', 'F047-003', 'F051-003', 'F055-003', 'F056-003', 'F058-003']) handlers[id].actors = ['user', 'tenantAdmin'];
handlers['F003-001'].actors = ['user', 'tenantAdmin', 'otherTenantAdmin'];

handlers['F001-002'] = async h => {
  const actor = h.admin, observed = [];
  const watch = request => { const pathname = new URL(request.url()).pathname; if (pathname.startsWith('/oauth/') || pathname === '/api/v1/web/auth/login') observed.push(pathname); };
  const cookies = async () => (await actor.context.cookies(actor.origin)).filter(x => x.httpOnly).map(x => [x.name, x.value]).sort((a, b) => a[0].localeCompare(b[0]));
  const before = await cookies();
  h.check('Original BFF session has protected cookies', before.length > 0);
  actor.page.on('request', watch);
  try {
    for (let cycle = 0; cycle < 3; cycle++) for (const surface of ['panel', 'portal']) {
      await actor.page.goto(actor.origin + '/' + surface + '/', { waitUntil: 'networkidle', timeout: 30000 });
      h.check('Switch reaches requested ' + surface, new URL(actor.page.url()).pathname.startsWith('/' + surface));
      h.check('Switch never presents login credentials', await actor.page.locator('input[name=password]').count() === 0);
      const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
      h.check('Switch preserves original account and tenant', session.account.account === actor.identity.account && session.homeNamespace === actor.identity.namespace);
    }
    h.check('No new OAuth authorization transaction during six switches', observed.length === 0, observed);
    h.check('BFF session cookies are reused during switches', JSON.stringify(before) === JSON.stringify(await cookies()));
    await h.screenshot(actor, 'shared-session');
  } finally { actor.page.off('request', watch); }
};

async function fits(h, page, locator, label) {
  h.check(label + ' is visible', await locator.isVisible());
  const box = await locator.boundingBox(), width = page.viewportSize().width;
  h.check(label + ' fits viewport width', box && box.x >= -1 && box.width > 0 && box.x + box.width <= width + 1, box);
}
handlers['F001-004'] = async h => {
  for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    const context = await h.browser.newContext({ ignoreHTTPSErrors: true, viewport });
    const page = await context.newPage(), actor = { context, page, origin: h.user.origin };
    try {
      await page.goto(actor.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle', timeout: 30000 });
      const account = page.locator('input[name=account]'), password = page.locator('input[name=password]'), submit = page.locator('form[action="/oauth/login"] button[type=submit]');
      await fits(h, page, account, 'Account field'); await fits(h, page, password, 'Password field'); await fits(h, page, submit, 'Login button');
      await account.fill(h.user.identity.account); await password.fill(h.state.password + '-wrong');
      const rejected = page.waitForResponse(r => new URL(r.url()).pathname === '/oauth/login' && r.request().method() === 'POST');
      await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), submit.click()]); await rejected;
      await password.waitFor({ state: 'visible' });
      h.check('Wrong-password form remains on login page', !['/panel', '/portal'].some(p => new URL(page.url()).pathname.startsWith(p)) && await submit.isVisible());
      const error = page.locator('[role=alert], .ant-alert, .error, .error-message, .cas-error').filter({ hasText: /密码|错误|失败|invalid|incorrect/i }).first();
      await error.waitFor({ state: 'visible', timeout: 5000 });
      await fits(h, page, error, 'Login error');
      h.check('Login error page has no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await h.screenshot(actor, 'error-' + viewport.width);
      await account.fill(h.user.identity.account); await password.fill(h.user.password);
      await submit.click(); await page.waitForURL(u => u.pathname.startsWith('/portal'), { timeout: 30000 });
      await page.waitForLoadState('networkidle');
      const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
      h.check('Viewport login creates correct user session', session.account.account === h.user.identity.account && session.homeNamespace === h.user.identity.namespace);
      await h.screenshot(actor, 'success-' + viewport.width);
    } finally { await context.close(); }
  }
};
handlers['F001-004'].actors = ['user'];

handlers['F065-003'] = async h => {
  const actor = h.user, directory = await h.ok(actor, 'GET', '/portal/applications/');
  const rows = directory.values === null && directory.pagination?.total === 0 ? [] : directory.values;
  if (!Array.isArray(rows) || rows.some(x => x.applicationKind !== 'builtin')) throw new h.Blocked('Empty-portal fixture must have no installed user applications');
  for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    await actor.page.setViewportSize(viewport);
    await actor.page.goto(actor.origin + '/portal/', { waitUntil: 'networkidle', timeout: 30000 });
    const card = actor.page.locator('.ant-card').filter({ has: actor.page.getByText('我的应用', { exact: true }) }).first();
    const empty = card.getByText('当前租户空间暂无已安装并启用的应用', { exact: true });
    await empty.waitFor({ state: 'visible', timeout: 10000 });
    await fits(h, actor.page, card, 'Applications card'); await fits(h, actor.page, empty, 'Empty applications feedback');
    h.check('Empty portal has no horizontal overflow', await actor.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await h.screenshot(actor, 'empty-' + viewport.width);
    const pattern = '**/api/v1/web/proxy/portal/applications/**'; let injected = 0;
    await actor.page.route(pattern, async route => { injected++; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 15, message: '回归验证：应用列表暂不可用' } }) }); });
    try {
      await actor.page.reload({ waitUntil: 'networkidle', timeout: 30000 });
      const alert = card.locator('.ant-alert'); await alert.waitFor({ state: 'visible', timeout: 10000 });
      h.check('Actual application list request reached controlled browser network failure', injected > 0);
      h.check('Unavailable state is explicit', /加载|不可用|失败|503|服务/.test(await alert.innerText()));
      h.check('Network failure does not claim a successful empty list', await empty.count() === 0);
      await fits(h, actor.page, alert, 'Applications failure feedback');
      await h.screenshot(actor, 'failure-' + viewport.width);
    } finally { await actor.page.unroute(pattern); }
    await actor.page.reload({ waitUntil: 'networkidle', timeout: 30000 });
    await empty.waitFor({ state: 'visible', timeout: 10000 });
    h.check('Reload retries live owner and clears stale failure', await card.locator('.ant-alert').count() === 0);
  }
};
handlers['F065-003'].actors = ['user'];
module.exports = { handlers };
