// Notification owner commands, tenant projection and actual detail refresh.
const handlers = {};
const collection = '/panel/support/notifications/';
const portal = '/portal/notifications/';
const publicRoute = '/api/v1/system/notifications/';
const payload = (h, suffix, changes = {}) => ({ title: h.state.prefix + '-' + suffix,
  content: '回归通知正文 ' + h.state.prefix + '-' + suffix,
  scope: [h.need('tenantA').name], audience: 'authenticated', status: 1, ...changes });
const owner = async (h, value) => (await h.ok(h.admin, 'GET', collection + value.id)).value;
async function projection(h, actor, route, id) {
  const result = await h.ok(actor, 'GET', route + (id ? '?id=' + id + '&' : '?') + '_pageSize=50');
  if (result.pagination?.hasMore || result.pagination?.total > result.values.length) throw new h.Blocked('Notification projection requires complete page reader');
  return result.values;
}
function visible(h, values, value, expected, label) {
  const matches = values.filter(x => x.id === value.id);
  h.check(label, expected ? matches.length === 1 && matches[0].title === value.title && matches[0].content === value.content && matches[0].createTime === value.createTime : matches.length === 0, { id: value.id, matches });
}
async function show(h, value, label = 'published') {
  await h.user.page.goto(h.user.origin + '/portal/notifications/', { waitUntil: 'networkidle' });
  const title = h.user.page.locator('.ant-list-item-meta-title').filter({ hasText: new RegExp('^' + value.title + '$') });
  await title.waitFor({ state: 'visible', timeout: 15000 });
  await title.click();
  const modal = h.user.page.locator('.ant-modal-content');
  await modal.locator('article').waitFor({ state: 'visible', timeout: 15000 });
  h.check('Portal detail independently refreshes exact title and content', await modal.getByText(value.title, { exact: true }).isVisible() && await modal.getByText(value.content, { exact: true }).isVisible());
  const expectedTime = await h.user.page.evaluate(ms => new Date(ms).toLocaleString('sv-SE'), value.createTime);
  h.check('Portal detail shows actual owner publication time to seconds', (await modal.innerText()).includes(expectedTime));
  await h.screenshot(h.user, 'notification-detail-' + value.id + '-' + label);
  await modal.getByRole('button', { name: /关\s*闭/ }).click();
  await modal.waitFor({ state: 'hidden', timeout: 15000 });
}
async function stale(h, value, message, label) {
  await h.user.page.locator('.ant-list-item-meta-title').filter({ hasText: new RegExp('^' + value.title + '$') }).click();
  const modal = h.user.page.locator('.ant-modal-content');
  await modal.getByText(message, { exact: true }).waitFor({ state: 'visible', timeout: 15000 });
  h.check('Old list item cannot expose cached detail content', await modal.locator('article').count() === 0 && !(await modal.innerText()).includes(value.content));
  await h.screenshot(h.user, 'notification-stale-' + value.id + '-' + label);
  await modal.getByRole('button', { name: /关\s*闭/ }).click();
  await modal.waitFor({ state: 'hidden', timeout: 15000 });
}

handlers['F053-001'] = async h => {
  const body = payload(h, 'notice-lifecycle', { status: 0 });
  const created = await h.create(collection, body, 'notification');
  const initial = await owner(h, created);
  h.check('Owner persists original draft identity and target', initial.id === created.id && initial.namespace === h.credentials.namespace && initial.title === body.title && initial.content === body.content && initial.status === 0 && initial.scope.length === 1 && initial.scope[0] === h.need('tenantA').name);
  visible(h, await projection(h, h.user, portal), initial, false, 'Draft is absent from target portal');
  const edited = { ...body, title: body.title + '-published', content: body.content + '\n编辑后发布', status: 1 };
  await h.ok(h.admin, 'PUT', collection + created.id, edited);
  const current = await owner(h, created);
  h.check('Owner confirms edited original notice with immutable publication time', current.id === created.id && current.title === edited.title && current.content === edited.content && current.status === 1 && current.createTime === initial.createTime && current.updateTime >= initial.updateTime);
  visible(h, await projection(h, h.user, portal), current, true, 'Target portal list matches owner title content and time');
  visible(h, await projection(h, h.user, portal, current.id), current, true, 'Target detail query matches exact owner notice');
  await show(h, current);
};

handlers['F053-002'] = async h => {
  const value = await h.create(collection, payload(h, 'notice-scope'), 'notification');
  visible(h, await projection(h, h.user, portal), value, true, 'Target ordinary member has positive notice visibility');
  for (const actor of [h.admin, h.otherTenantAdmin]) {
    visible(h, await projection(h, actor, portal), value, false, 'Out-of-scope account cannot list notice');
    visible(h, await projection(h, actor, portal, value.id), value, false, 'Guessing exact notice ID cannot cross target scope');
  }
  h.denied(await h.api(h.user, 'GET', collection + value.id), 'Portal-only member cannot bypass detail projection through owner management API');
  const anonymous = await h.anonymous(h.need('tenantA').name);
  visible(h, await projection(h, anonymous, publicRoute), value, false, 'Authenticated-only notice is absent from anonymous list');
  visible(h, await projection(h, anonymous, publicRoute, value.id), value, false, 'Anonymous guessed ID cannot read authenticated notice');
  h.check('Rejected access leaves original owner notice unchanged', JSON.stringify(await owner(h, value)) === JSON.stringify(value));
};

handlers['F053-003'] = async h => {
  const anonymous = await h.anonymous(h.need('tenantA').name);
  for (const audience of ['all', 'authenticated', 'anonymous']) {
    const value = await h.create(collection, payload(h, 'notice-' + audience, { audience }), 'notification');
    for (const [actor, route, expected] of [[anonymous, publicRoute, audience !== 'authenticated'], [h.user, portal, audience !== 'anonymous']]) {
      visible(h, await projection(h, actor, route), value, expected, audience + ' list audience gate');
      visible(h, await projection(h, actor, route, value.id), value, expected, audience + ' detail audience gate');
    }
    for (const route of [portal]) visible(h, await projection(h, h.otherTenantAdmin, route, value.id), value, false, 'Audience never overrides explicit tenant scope');
  }
  const body = payload(h, 'notice-stale');
  const value = await h.create(collection, body, 'notification');
  await show(h, value);
  const unsupported = await h.api(h.admin, 'PUT', collection + value.id, { ...body, expireTime: Date.now() + 60000 });
  h.invalid(unsupported, 'Unsupported notification expiry is explicitly rejected');
  h.check('Rejected expiry preserves exact original notice', JSON.stringify(await owner(h, value)) === JSON.stringify(value));
  let injected = 0;
  const pattern = '**/api/v1/web/proxy/portal/notifications/**';
  const fault = async route => {
    if (new URL(route.request().url()).searchParams.get('id') === String(value.id)) {
      injected++;
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 15, message: 'controlled detail read failure' } }) });
    } else await route.continue();
  };
  await h.user.page.route(pattern, fault);
  try { await stale(h, value, '暂时无法确认通知状态，请关闭后重试', 'read-failure'); }
  finally { await h.user.page.unroute(pattern, fault); }
  h.check('Browser failure actually intercepts requested original detail identity', injected === 1);
  await h.ok(h.admin, 'PUT', collection + value.id, { ...body, status: 2 });
  const offline = await owner(h, value);
  h.check('Owner confirms offline original notice', offline.id === value.id && offline.status === 2);
  visible(h, await projection(h, h.user, portal), value, false, 'Offline notice absent from fresh portal list');
  await stale(h, value, '该通知已下线、删除或不再对当前访问者开放', 'offline');
  await h.ok(h.admin, 'PUT', collection + value.id, body);
  await show(h, value, 'republished');
  await h.remove(collection, value.id); await h.gone(collection, value.id);
  visible(h, await projection(h, h.user, portal, value.id), value, false, 'Deleted original detail identity returns no notice');
  await stale(h, value, '该通知已下线、删除或不再对当前访问者开放', 'deleted');
};
for (const handler of Object.values(handlers)) handler.actors = ['user', 'otherTenantAdmin'];
module.exports = { handlers };
