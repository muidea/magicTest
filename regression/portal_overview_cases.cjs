// Portal UI is a consumer of current-subject projections, never their owner.
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const feedback = require('./feedback_cases.cjs');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const widths = [1440, 1024, 390];
const card = (page, title) => page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title').getByText(title, { exact: true }) });
function applicationTarget(actor, entry) {
  if (!entry || entry.entryEnabled !== true || entry.entryMode !== 'workbench' || !entry.key || !/^[a-f0-9]{32}$/.test(entry.deploymentId)) throw Error('Exact enabled model workbench entry required');
  const url = new URL('/workbench/apps/' + encodeURIComponent(entry.key), actor.origin);
  url.searchParams.set('source', 'portal'); url.searchParams.set('deploymentId', entry.deploymentId);
  return url;
}
function sameTarget(actual, expected) {
  const a = new URL(actual), e = new URL(expected);
  return a.origin === e.origin && a.pathname.replace(/\/$/, '') === e.pathname.replace(/\/$/, '') && same([...a.searchParams].sort(), [...e.searchParams].sort()) && !a.hash;
}
async function openApplication(h, actor, entry, rows) {
  const name = entry.showName || entry.name, panel = card(actor.page, '我的应用');
  h.check('Navigation retains one exact original owner application entry', rows.applications.filter(row => same(row, entry)).length === 1);
  const preview = panel.getByRole('button', { name, exact: true }), count = await preview.count();
  h.check('Original overview application preview is unique when present', count === 0 || count === 1);
  if (count === 1) return preview.click();
  h.check('Original application omitted from preview has a complete larger owner directory', rows.applications.length > 4);
  // RightOutlined contributes an accessible name; match the visible button
  // text and independently known complete count instead of omitting its icon.
  const all = panel.getByRole('button').filter({ hasText: new RegExp('^查看全部\\s*\\(' + rows.applications.length + '\\)$') });
  h.check('Original application view-all button uniquely retains complete owner count', await all.count() === 1);
  await all.click();
  const target = new URL('/portal/applications/', actor.origin);
  await actor.page.waitForURL(url => sameTarget(url, target));
  await actor.page.waitForFunction(() => document.querySelectorAll('.ant-spin-spinning').length === 0, {}, { timeout: 60000 });
  const resource = actor.page.locator('.magic-resource-card').filter({ has: actor.page.getByText(name, { exact: true }) });
  // This page loads with Skeleton rather than Spin; a missing spinner does
  // not prove that the asynchronously refreshed application list is ready.
  await resource.waitFor({ state: 'visible' });
  h.check('Full application list contains one exact original entry card', await resource.count() === 1);
  await resource.getByRole('button', { name: '进入应用', exact: true }).click();
}
async function projection(h, actor) {
  const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  h.check('Original ordinary portal subject and tenant match the current session', session.account?.account === actor.identity.account && session.homeNamespace === actor.identity.namespace && session.activeNamespace === actor.identity.namespace);
  const rows = {};
  for (const [key, route] of Object.entries({ applications: '/portal/applications/', services: '/portal/services/', notifications: '/portal/notifications/', feedbacks: '/portal/feedbacks/' }))
    rows[key] = await h.directory(actor, route, key === 'applications' ? { idFormat: 'string' } : key === 'notifications' ? { pageSize: 50 } : key === 'services' ? { pageSize: 20 } : {});
  h.check('Portal application identity matches its exact deployment or runtime source', rows.applications.every(entry =>
    typeof entry.sourceID === 'string' && /^[1-9][0-9]{0,18}$/.test(entry.sourceID) && BigInt(entry.sourceID) <= 9223372036854775807n &&
    (entry.deploymentId ? /^[a-f0-9]{32}$/.test(entry.deploymentId) && entry.id === entry.deploymentId : entry.id === entry.sourceID)));
  h.check('Each complete current-subject portal projection has unique owner identities', Object.values(rows).every(values => values.every(v => v.id != null) && new Set(values.map(v => String(v.id))).size === values.length));
  h.observe({ kind: 'portal-overview-independent-projections', actor: actor.identity, rows });
  return rows;
}
async function metric(h, actor, title, count) {
  const value = actor.page.getByLabel('门户概览', { exact: true }).locator(':scope > div').filter({ hasText: title }).locator('strong');
  await value.waitFor({ state: 'visible' });
  let actual;
  for (let attempt = 0; attempt < 20; attempt++) {
    actual = await value.innerText();
    if (actual === String(count)) break;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  h.check('Visible ' + title + ' count equals complete current-subject owner projection', actual === String(count), { actor: actor.identity, title, count, actual });
}
async function home(h, actor, rows, width, label) {
  await actor.page.setViewportSize({ width, height: 900 });
  await actor.page.goto(actor.origin + '/portal/', { waitUntil: 'networkidle' });
  await actor.page.getByRole('heading', { name: '门户工作台', exact: true }).waitFor();
  await actor.page.waitForFunction(() => document.querySelectorAll('.ant-spin-spinning').length === 0, {}, { timeout: 60000 });
  await metric(h, actor, '我的应用', rows.applications.length);
  await metric(h, actor, '服务中心', rows.services.length);
  await metric(h, actor, '反馈工单', rows.feedbacks.length);
  const noticeCount = (await card(actor.page, '通知中心').getByRole('button', { name: /查看全部/ }).innerText()).replace(/\s/g, '');
  h.check('Notification preview total equals the independent complete scoped directory', noticeCount === '查看全部' + (rows.notifications.length ? '（' + rows.notifications.length + '）' : ''), { expected: rows.notifications.length, actual: noticeCount });
  await actor.page.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
  h.check('Loaded portal sections do not disguise owner read failures as empty counts', await actor.page.locator('.ant-card .ant-alert').count() === 0);
  const overflow = await actor.page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
  h.check('Portal at declared width keeps its document within the viewport', overflow.scroll <= overflow.viewport + 1, { width, ...overflow });
  await h.screenshot(actor, 'portal-overview-' + label + '-' + width);
}
async function overview(h) {
  const f = await fixture(h);
  h.portalOverviewManager = await business.member(h, 'manager');
  const originalSubject = h.portalOverviewManager.subject;
  const manager = await require('./session_lifecycle.cjs').readyActor(h, 'portalOverviewManager', h.api);
  const managerSession = (await h.ok(manager, 'GET', '/api/v1/web/session/')).value;
  h.check('Renewed overview manager retains the independently verified original business subject',
    originalSubject === managerSession.homeNamespace + '/account:' + managerSession.account?.id);
  manager.subject = originalSubject;
  h.deliveryActors.manager = manager;
  const service = await graph.fixture(h, 'portal_overview');
  const subscription = await graph.subscribe(h, service);
  h.check('Nonempty overview service is enabled for the original ordinary subscriber', subscription.value?.status === 2 && subscription.value.service.id === service.service.id);
  const ticket = await feedback.ticket(h, 'overview');
  const notice = await h.create('/panel/support/notifications/', { title: h.state.prefix + '-overview-notice', content: '门户概览原始通知 ' + h.state.prefix,
    scope: [h.user.identity.namespace], audience: 'authenticated', status: 1 }, 'notification');
  const originalNotice = (await h.ok(h.admin, 'GET', '/panel/support/notifications/' + notice.id)).value;
  const rows = await projection(h, h.user), managerRows = await projection(h, manager);
  h.check('Ordinary member projections contain the exact subscribed service, own private ticket and scoped notice',
    rows.services.some(v => v.id === service.service.id && v.leaseTerm?.status === 2 && v.leaseTerm.startTime === subscription.value.startTime && v.leaseTerm.expireTime === subscription.value.expireTime) &&
    rows.feedbacks.some(v => v.id === ticket.id && v.submitter?.account === h.user.identity.account && v.title === ticket.intended.title) &&
    rows.notifications.some(v => v.id === notice.id && v.title === originalNotice.title && v.content === originalNotice.content), rows);
  h.check('Different original ordinary subject has no private ticket or foreign notice', !managerRows.feedbacks.some(v => v.id === ticket.id) && !managerRows.notifications.some(v => v.id === notice.id));
  const entries = f.installations.map(i => managerRows.applications.filter(v => v.deploymentId === i.deploymentId && v.applicationUuid === f.application.uuid && v.sourceID === String(i.receipt.runtimeApplicationId)));
  h.check('Nonempty application overview contains each exact original installation once', entries.every(v => v.length === 1), entries);
  for (const width of widths) {
    await home(h, h.user, rows, width, 'ordinary');
    const serviceCard = card(h.user.page, '服务中心');
    // The overview displays four status-sorted entries. A full run can have
    // many earlier subscriptions; select our original service through the
    // actual home search instead of assuming the newest item is in that slice.
    h.observe({ kind: 'portal-overview-unfiltered-service-preview', width,
      originalServiceId: service.service.id,
      visible: await serviceCard.locator('.ant-list-item').allTextContents() });
    await serviceCard.getByPlaceholder('搜索服务', { exact: true }).fill(service.service.showName);
    const item = serviceCard.locator('.ant-list-item').filter({ hasText: service.service.showName });
    await item.waitFor();
    h.check('Real overview search selects the independently confirmed original subscribed service', await item.count() === 1 && await serviceCard.locator('.ant-list-item').count() === 1);
    await item.getByRole('button', { name: /(?:^|\s)查看$/ }).click();
    const serviceModal = h.user.page.getByRole('dialog', { name: '服务详情', exact: true });
    await serviceModal.getByText(service.service.showName, { exact: true }).waitFor();
    h.check('Overview service detail retains original owner name and description', (await serviceModal.innerText()).includes(service.service.description));
    await serviceModal.getByRole('button', { name: 'Close', exact: true }).click();
    await item.getByRole('button', { name: /(?:^|\s)进入服务$/ }).click();
    const serviceURL = new URL('/workbench/services/' + service.service.id + '?source=portal', h.user.origin);
    await h.user.page.waitForURL(url => sameTarget(url, serviceURL));
    await h.user.page.locator('button').filter({ hasText: /^发送请求$/ }).waitFor();
    h.check('Original overview enters the exact authorized subscribed service', sameTarget(h.user.page.url(), serviceURL));
    await h.screenshot(h.user, 'portal-overview-service-' + width);
    await home(h, h.user, rows, width, 'notice');
    await card(h.user.page, '通知中心').getByText(notice.title, { exact: true }).click();
    const notification = h.user.page.locator('.ant-modal-content').filter({ hasText: notice.title });
    await notification.locator('article').waitFor();
    h.check('Overview notification detail independently refreshes original owner bytes', await notification.getByText(originalNotice.title, { exact: true }).isVisible() && await notification.getByText(originalNotice.content, { exact: true }).isVisible());
    await h.screenshot(h.user, 'portal-overview-notice-detail-' + width);
    await notification.getByRole('button', { name: /关\s*闭/ }).click();
    const feedbackRow = card(h.user.page, '需求与反馈').locator('.ant-list-item').filter({ hasText: ticket.intended.title });
    await feedbackRow.getByRole('link', { name: '查看详情', exact: true }).click();
    const feedbackURL = new URL('/portal/feedback?id=' + ticket.id, h.user.origin);
    await h.user.page.waitForURL(url => sameTarget(url, feedbackURL));
    await h.user.page.getByRole('heading', { name: '工单详情：' + ticket.intended.title, exact: true }).waitFor();
    const feedbackContent = h.user.page.getByText(ticket.intended.content, { exact: true });
    await feedbackContent.waitFor({ state: 'visible' });
    h.check('Original feedback navigation preserves original ticket and content', sameTarget(h.user.page.url(), feedbackURL) && await feedbackContent.isVisible(), { actualURL: h.user.page.url(), expectedURL: feedbackURL.href });
    await h.screenshot(h.user, 'portal-overview-feedback-' + width);
    await home(h, manager, managerRows, width, 'installed');
    for (const [index, [entry]] of entries.entries()) {
      if (index) await home(h, manager, managerRows, width, 'second-instance');
      // The fixture's instance display names are independent, even when both
      // instances use the same application key and model definition.
      const target = applicationTarget(manager, entry);
      await openApplication(h, manager, entry, managerRows);
      await manager.page.waitForURL(url => sameTarget(url, target));
      const runtime = await business.runtime(h, f, index, manager);
      h.check('Portal navigation and independent runtime owner select the same original installation', sameTarget(manager.page.url(), target) && runtime.identity.deploymentId === entry.deploymentId && entry.applicationUuid === f.application.uuid && entry.sourceID === String(f.installations[index].receipt.runtimeApplicationId));
      await manager.page.getByText('回归页面原始说明', { exact: true }).waitFor();
      await manager.page.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
      await h.screenshot(manager, 'portal-overview-application-' + index + '-' + width);
    }
  }
  h.check('Portal overview navigation leaves both complete subject projections and original notice unchanged',
    same(await projection(h, h.user), rows) && same(await projection(h, manager), managerRows) && same((await h.ok(h.admin, 'GET', '/panel/support/notifications/' + notice.id)).value, originalNotice));
  await graph.retire(h, subscription);
  await feedback.cleanup(h, ticket);
}
overview.actors = ['user', 'tenantAdmin']; overview.transport = 'owner-api';
module.exports = { handlers: { 'F065-001': overview }, applicationTarget, sameTarget, projection, home, openApplication };
