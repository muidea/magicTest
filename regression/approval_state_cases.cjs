// UI actions consume the request owner's actual state; they never authorize it.
const { isDeepStrictEqual: same } = require('node:util');
const model = require('./deployment_review_cases.cjs');
const { fixture, requestCommand } = require('./delivery_cases.cjs');
const requests = '/panel/application/deployment-requests/';
const reviews = '/panel/operations/namespaces/panel/application-deployment-requests/';
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const installations = '/panel/application/installations/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(r => r.value);
async function snapshot(h, r) {
  const state = { request: await read(h, requests + r.id) };
  for (const route of [operations, installations]) state[route] = (await h.directory(h.admin, route)).sort((a, b) => a.id - b.id);
  return state;
}
function confirmCancelledReview(h, before, after, writes) {
  h.check('Cancelling review forms sends no review write', writes.length === 0, writes);
  h.check('Cancelling review forms preserves the exact original request', same(before.request, after.request), { before: before.request, after: after.request });
  if (!same(before, after)) {
    h.observe({ kind: 'review-cancel-owner-snapshot-drift', before, after, writes });
    throw new h.Blocked('Unrelated owner snapshots changed during cancellation observation; no stable no-effect proof');
  }
  h.check('Cancelling review forms preserves all independently read owner snapshots', true);
}
async function reject(h, r) {
  model.original(h, r);
  const before = await snapshot(h, r);
  const c = { route: reviews + r.id + '/reject', body: { expectedVersion: r.last.version, reason: 'State-specific review acceptance' }, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  const after = await snapshot(h, r);
  h.check('Rejected original request advances only its owner version with no operation or installation', h.good(c.response) && same(c.response.data.value, after.request) &&
    after.request.id === r.id && after.request.status === 'rejected' && !after.request.operationId && after.request.version === r.last.version + 1 &&
    same(after[operations], before[operations]) && same(after[installations], before[installations]), after);
  c.outcome = 'confirmed'; r.last = after.request; h.persist();
}
async function forbidReview(h, r, action, runtimePlacement) {
  model.original(h, r);
  if (!['approve', 'reject'].includes(action)) throw new h.Blocked('Only formal approval or rejection probes are supported');
  if (!['rejected', 'cancelled', 'succeeded'].includes(r.last.status)) throw new h.Blocked('Exact original terminal request required before forbidden review');
  const before = await snapshot(h, r);
  if (!same(before.request, r.last)) throw new h.Blocked('Original request changed before terminal review; no replacement');
  const c = { route: reviews + r.id + '/' + action, body: { expectedVersion: r.last.version, reason: 'Terminal original request cannot be reviewed again', ...(action === 'approve' ? { runtimePlacement } : {}) }, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  const after = await snapshot(h, r);
  // Require the state fence, not an earlier authentication or stale-version error.
  if (model.refusal(c.response, 'application deployment request cannot be reviewed') && same(before, after)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Original terminal ' + r.last.status + ' refuses ' + action + ' at exact owner state fence without any effect', c.outcome === 'rejected-and-unchanged', c.response);
}
async function row(h, r) {
  const page = h.admin.page;
  await page.goto(h.admin.origin + '/panel/operations/deployment-approval/', { waitUntil: 'networkidle' });
  const table = page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title').getByText('应用部署审批', { exact: true }) });
  await table.waitFor(); await table.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
  const target = table.locator('tr[data-row-key="' + r.id + '"]');
  for (let count = 0; count < 30 && !(await target.count()); count++) {
    const next = table.locator('.ant-pagination-next:not(.ant-pagination-disabled) button');
    if (!await next.count()) break;
    await next.click(); await table.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
  }
  await target.waitFor(); return target;
}
async function controls(h, r) {
  const target = await row(h, r);
  const expected = r.last.status === 'submitted' ? ['批准', '驳回'] : r.last.operationId ? [] : ['清理记录'];
  const actual = await target.locator('button').allTextContents();
  h.check('Actual approval row exposes exactly the owner-permitted actions for ' + r.last.status, same(actual.map(v => v.replace(/\s/g, '')).filter(Boolean).sort(), expected.sort()), { requestId: r.id, status: r.last.status, actual });
  const text = { submitted: '待审批', rejected: '已驳回', cancelled: '已取消', succeeded: '已完成' }[r.last.status];
  await target.getByText(text, { exact: true }).waitFor();
  return target;
}
async function states(h) {
  const f = await fixture(h), peers = await Promise.all(f.installations.map(i => read(h, installations + i.id)));
  const r = await model.create(h, f, 'review-state-rejected'), cancelled = await model.create(h, f, 'review-state-cancelled');
  let approved, primary;
  try {
    const before = await snapshot(h, r), page = h.admin.page;
    const writes = [], watch = request => { if (['POST', 'PUT', 'DELETE'].includes(request.method()) && new URL(request.url()).pathname.includes('application-deployment-requests/')) writes.push(request.method() + ' ' + new URL(request.url()).pathname); };
    page.on('request', watch);
    try {
      for (const width of [1440, 1024, 390]) {
        await page.setViewportSize({ width, height: 900 });
        const target = await controls(h, r);
        for (const action of ['批准', '驳回']) {
          await target.getByRole('button', { name: action === '批准' ? /^批\s*准$/ : /^驳\s*回$/ }).click();
          const dialog = page.getByRole('dialog', { name: action + '部署申请', exact: true });
          const reason = h.state.prefix + ' 长审批原因 ' + '保持原输入内容。'.repeat(50);
          const field = dialog.getByLabel('审批原因', { exact: true }); await field.fill(reason);
          await page.waitForTimeout(1100);
          await page.setViewportSize({ width: width + 1, height: 900 }); await page.setViewportSize({ width, height: 900 });
          h.check('Long original review input remains through idle time and responsive rerenders', await field.inputValue() === reason, { requestId: r.id, width, action });
          await h.screenshot(h.admin, 'approval-' + action + '-' + width);
          await dialog.getByRole('button', { name: /^取\s*消$/ }).click(); await dialog.waitFor({ state: 'hidden' });
        }
      }
      confirmCancelledReview(h, before, await snapshot(h, r), writes);
    } finally { page.off('request', watch); }
    const options = (await h.ok(h.admin, 'GET', reviews + r.id + '/runtime-options')).values;
    const bases = options.filter(v => v.kind === 'base'), gateways = options.filter(v => v.kind === 'gateway');
    if (bases.length !== 1 || gateways.length !== 1) throw new h.Blocked('Unambiguous isolated runtime placement required for terminal state probe');
    const placement = { executionInstanceId: bases[0].id, gatewayInstanceId: gateways[0].id };
    await reject(h, r); await requestCommand(h, cancelled, 'cancel');
    approved = await model.create(h, f, 'review-state-approved');
    const session = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value; h.admin.id = session.account.id;
    await model.approve(h, approved, [h.admin]);
    for (const terminal of [r, cancelled, approved]) {
      for (const width of [1440, 1024, 390]) {
        await h.admin.page.setViewportSize({ width, height: 900 }); await controls(h, terminal);
        await h.screenshot(h.admin, 'approval-state-' + terminal.last.status + '-' + width);
      }
      for (const action of ['approve', 'reject']) await forbidReview(h, terminal, action, placement);
    }
    h.check('Review decisions and refusal probes preserve both original installed peers and the exact published package',
      same(await Promise.all(f.installations.map(i => read(h, installations + i.id))), peers) && same(await read(h, '/panel/application/model-packages/' + f.package.id), f.package));
  } catch (error) { primary = error; throw error; }
  finally {
    let cleanupError;
    for (const resource of [approved, cancelled, r].filter(Boolean)) if (resource.phase !== 'deleted') {
      try { await model.cleanup(h, resource); }
      catch (error) { h.observe({ kind: 'approval-state-cleanup-open', requestId: resource.id, error: error.message }); cleanupError ||= error; }
    }
    await h.admin.page.setViewportSize({ width: 1366, height: 768 });
    if (!primary && cleanupError) throw cleanupError;
  }
}
states.transport = 'owner-api';
module.exports = { handlers: { 'F028-003': states }, forbidReview, confirmCancelledReview };
