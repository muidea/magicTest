// Observe actual owner states and the real task UI. Normal deployment tasks
// expose state/counters/diagnostics, not the placement owner's allowedActions.
const { isDeepStrictEqual: same } = require('node:util');
const review = require('./deployment_review_cases.cjs');
const native = require('./native_runtime_cases.cjs');
const scenario = require('./scenario_commands.cjs');
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const requests = '/panel/application/deployment-requests/';
const installations = '/panel/application/installations/';
const read = (h, route) => h.ok(h.admin, 'GET', route).then(v => v.value);
const sorted = rows => [...rows].sort((a, b) => a.id - b.id);
const sameOperation = (a, b) => review.successfulOperationFactsMatch(a, b);
function bound(r, request, operation) {
  return Number.isSafeInteger(r.id) && r.id > 0 && Number.isSafeInteger(operation?.id) && operation.id > 0 &&
    Number.isSafeInteger(operation.version) && operation.version > 0 &&
    request?.id === r.id && request.operationId === operation.id && operation.requestId === r.id &&
    request.namespace === 'panel' && operation.namespace === request.namespace && request.packageId === r.creation?.intended?.packageId &&
    operation.packageId === request.packageId && request.instanceKey === r.creation?.intended?.instanceKey &&
    ['deploymentId', 'instanceKey', 'instanceName', 'sourceKind', 'planDigest'].every(k => same(request[k], operation[k])) &&
    request.status === operation.status && ['succeeded', 'failed', 'cancelled'].includes(operation.status) &&
    operation.id === r.operation?.id && sameOperation(r.operation, operation) && same(r.last, request);
}
function original(h, r) {
  scenario.guard(h, r);
  if (r.kind === 'native-runtime-request') native.original(h, r);
  else review.original(h, r);
}
async function snapshot(h, r) {
  const request = await read(h, requests + r.id), operation = await read(h, operations + r.operation.id);
  h.check('State-specific task observation binds exact original request, frozen intent and durable operation', bound(r, request, operation), { request, operation });
  const value = { request, operation, installations: sorted(await h.directory(h.admin, installations)),
    operationDirectory: sorted(await h.directory(h.admin, operations)), requestDirectory: sorted(await h.directory(h.admin, requests)) };
  const requestRows = value.requestDirectory.filter(v => v.id === r.id), operationRows = value.operationDirectory.filter(v => v.id === operation.id);
  h.check('Complete directories contain exactly the independently read original request and operation',
    requestRows.length === 1 && same(requestRows[0], request) && operationRows.length === 1 && sameOperation(operationRows[0], operation), value);
  return value;
}
function unchanged(before, after) {
  return same(before.request, after.request) && sameOperation(before.operation, after.operation) && same(before.installations, after.installations) &&
    same(before.requestDirectory, after.requestDirectory) && before.operationDirectory.length === after.operationDirectory.length &&
    before.operationDirectory.every((v, i) => v.id === after.operationDirectory[i].id && sameOperation(v, after.operationDirectory[i]));
}
function refusal(operation, action, stale) {
  if (stale && action === 'retry' && operation.status === 'failed' && Number.isSafeInteger(operation.version) && operation.version > 1)
    return { code: 19, message: 'application deployment state version does not match' };
  if (stale) throw Error('Stale-version probe requires an actually failed task with a positive preceding version');
  if (action === 'cleanup' && ['failed', 'succeeded'].includes(operation.status))
    return { code: 21, message: 'only a fully cancelled deployment operation without an installation receipt can be cleaned' };
  if (action === 'retry' && ['succeeded', 'cancelled'].includes(operation.status))
    return { code: 21, message: 'application deployment operation cannot be retried' };
  if (action === 'cancel' && ['succeeded', 'cancelled'].includes(operation.status) && operation.startTime > 0)
    return { code: 21, message: 'only deployment operations with no execution history can be cancelled' };
  // Never send an action that may actually retry or terminate the fixture.
  throw Error('Only exact proven forbidden task actions are supported');
}
async function rejectAction(h, r, action, stale = false) {
  original(h, r);
  const expected = refusal(r.operation, action, stale), before = await snapshot(h, r);
  original(h, r);
  const c = { method: 'POST', route: operations + r.operation.id + '/' + action,
    body: { expectedVersion: before.operation.version - (stale ? 1 : 0), reason: 'Verify original task state action fence' }, expected,
    origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), before, outcome: 'unknown' };
  (r.scenarioCommands ||= []).push(c); h.persist();
  try { c.response = await h.api(h.admin, c.method, c.route, c.body); }
  catch (error) { c.transportError = error.message; }
  h.persist();
  if (h.admin.origin !== c.origin || !same(h.admin.identity, c.actorIdentity))
    throw new h.Blocked('Original task actor changed; retain unresolved command without replay');
  c.after = await snapshot(h, r); h.persist();
  const response = c.response;
  if (h.admin.origin === c.origin && same(h.admin.identity, c.actorIdentity) &&
      [200, 400, 409].includes(response?.status) && response.data?.error?.code === expected.code &&
      response.data.error.message === expected.message && response.data.value == null && unchanged(before, c.after)) {
    c.outcome = 'rejected-and-unchanged'; h.persist();
  }
  h.check('Actual task action reaches the precise owner state/version fence without changing any original authority', c.outcome === 'rejected-and-unchanged', c);
}
function expectedButtons(operation) {
  if (operation.status === 'succeeded') return [];
  if (operation.sourceKind === 'deployment-package' && operation.status === 'failed' && operation.phase === 'execution' &&
      operation.attempt > 0 && operation.attempt < operation.maxAttempts && !operation.receiptRef && !operation.recoveryHistory?.length)
    return ['重试', '终止并清理'];
  if (operation.sourceKind === 'deployment-package' && operation.status === 'cancelled' && operation.phase === 'terminated' && !operation.receiptRef)
    return ['清理记录'];
  throw Error('Unobserved task state requires its own real owner fixture');
}
async function findTaskRow(h, r, card) {
  const row = card.locator('tr[data-row-key="' + r.operation.id + '"]');
  // Refresh may reset or retain pagination. Search from page one without a
  // navigation that would replace the refresh response we are validating.
  if (!await row.count()) {
    const first = card.locator('.ant-pagination-item-1:not(.ant-pagination-item-active)');
    if (await first.count()) { await first.click(); await card.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' }); }
  }
  for (let n = 0; n < 100 && !await row.count(); n++) {
    const next = card.locator('.ant-pagination-next:not(.ant-pagination-disabled) button');
    if (!await next.count()) break;
    await next.click(); await card.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
  }
  await row.waitFor(); return row;
}
async function taskRow(h, r) {
  const page = h.admin.page;
  await page.goto(h.admin.origin + '/panel/operations/deployment-tasks/', { waitUntil: 'networkidle' });
  const card = page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title').getByText('应用部署任务', { exact: true }) });
  await card.waitFor(); await card.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
  return { card, row: await findTaskRow(h, r, card) };
}
const labels = { succeeded: '已完成', failed: '失败', cancelled: '已取消' };
async function controls(h, r, target) {
  const actual = (await target.locator('button').allTextContents()).map(v => v.replace(/\s/g, '')).filter(Boolean).sort();
  h.check('Real task row exposes exactly supported actions for its independently read current original state', same(actual, expectedButtons(r.operation).sort()), { id: r.operation.id, actual, operation: r.operation });
  await target.locator('.ant-tag').filter({ hasText: new RegExp('^' + labels[r.operation.status] + '$') }).waitFor();
  h.check('Task row retains original task ID, instance and actual attempt budget', (await target.innerText()).includes(String(r.operation.id)) &&
    (await target.innerText()).includes(r.operation.instanceName || r.operation.instanceKey) &&
    (await target.innerText()).includes(r.operation.attempt + '/' + r.operation.maxAttempts));
  if (r.operation.status === 'failed') await target.getByText(r.operation.failureMessage, { exact: true }).waitFor();
}
async function visible(h, r) {
  original(h, r);
  const before = await snapshot(h, r), page = h.admin.page, writes = [];
  const pattern = '**/api/v1/web/proxy/panel/operations/**';
  const watch = async route => {
    const request = route.request(), url = new URL(request.url());
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method()) && url.pathname.includes('/application-deployment-operations/')) {
      // Opening/discarding these forms must not dispatch. If the UI does send
      // a command, preserve it before forwarding and forbid guessed cleanup.
      const c = { method: request.method(), route: url.pathname.replace(/^\/api\/v1\/web\/proxy/, '') + url.search,
        bodyText: request.postData(), origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
        requestId: r.id, operationId: r.operation.id, before, outcome: 'unknown', source: 'unexpected-task-ui-command' };
      writes.push(c); (r.scenarioCommands ||= []).push(c); h.persist();
    }
    await route.continue();
  };
  await page.route(pattern, watch);
  try {
    for (const width of [1440, 1024, 390]) {
      await page.setViewportSize({ width, height: 900 });
      let { card, row } = await taskRow(h, r); await controls(h, r, row);
      // Await the actual owner-backed manual refresh; an idle spinner alone
      // cannot prove that a refresh request was dispatched.
      const observed = page.waitForResponse(response => {
        const url = new URL(response.url());
        return response.request().method() === 'GET' && url.origin === h.admin.origin && url.pathname === '/api/v1/web/proxy/panel/operations/application-deployment-operations/';
      }); observed.catch(() => {});
      await card.getByRole('button', { name: /^刷\s*新$/ }).click();
      const response = await observed;
      h.check('Manual task refresh reaches actual operations owner successfully', response.status() === 200 && !(await response.json()).error);
      await card.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
      row = await findTaskRow(h, r, card); await controls(h, r, row);
      for (const action of expectedButtons(r.operation)) {
        await row.getByRole('button', { name: action === '重试' ? /^重\s*试$/ : action, exact: true }).click();
        const title = { '重试': '重试部署任务', '终止并清理': '终止并清理部署任务', '清理记录': '清理部署记录' }[action];
        const label = { '重试': '重试原因', '终止并清理': '终止原因', '清理记录': '清理原因' }[action];
        const dialog = page.getByRole('dialog', { name: title, exact: true }), input = dialog.getByLabel(label, { exact: true });
        const reason = h.state.prefix + ' 原任务输入保持 ' + '保持输入与原任务身份。'.repeat(30);
        await input.fill(reason); await page.waitForTimeout(1100);
        await page.setViewportSize({ width: width + 1, height: 900 }); await page.setViewportSize({ width, height: 900 });
        h.check('Original task operation reason survives idle time and responsive rerender', await input.inputValue() === reason, { operationId: r.operation.id, width, action });
        await h.screenshot(h.admin, 'task-action-' + r.operation.id + '-' + action + '-' + width);
        await dialog.getByRole('button', { name: /^返\s*回$/ }).click(); await dialog.waitFor({ state: 'hidden' });
      }
      await h.screenshot(h.admin, 'task-state-' + r.operation.id + '-' + r.operation.status + '-' + width);
    }
    h.check('Manual refresh and discarded forms send no operation command and preserve all original owner facts', writes.length === 0 && unchanged(before, await snapshot(h, r)), writes);
  } finally { await page.unroute(pattern, watch); }
}
async function states(h) {
  const f = await require('./delivery_cases.cjs').fixture(h), peers = [];
  for (const installed of f.installations) peers.push(await read(h, installations + installed.id));
  const r = await review.create(h, f, 'task-state-success');
  h.admin.id = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account.id;
  let primary;
  try {
    await review.approve(h, r, [h.admin]);
    await visible(h, r);
    for (const action of ['retry', 'cancel', 'cleanup']) await rejectAction(h, r, action);
  } catch (error) { primary = error; throw error; }
  finally {
    try { scenario.guard(h, r); await review.cleanup(h, r); }
    catch (error) { h.observe({ kind: 'task-state-original-cleanup-open', requestId: r.id, message: error.message }); if (!primary) throw error; }
  }
  await native.failedCleanup(h, async failed => {
    await visible(h, failed);
    await rejectAction(h, failed, 'cleanup');
    await rejectAction(h, failed, 'retry', true);
  }, async terminated => {
    await visible(h, terminated);
    for (const action of ['retry', 'cancel']) await rejectAction(h, terminated, action);
  });
  for (const peer of peers) h.check('Task actions and exact termination preserve unrelated original installed peers', same(await read(h, installations + peer.id), peer));
  await h.partial('Actual successful model, intended native exit23 failure and the same formally terminated task: exact UI actions, diagnostic/counters, three widths, manual owner refresh and preserved discarded inputs, exact state/stale-version refusals, original formal termination and source cleanup. Waiting/running windows, actual allowed retry, exhausted/paused authorization/Schema diagnostic actions and late responses switching task selection remain unverified.');
}
states.transport = 'owner-api';
module.exports = { handlers: { 'F029-003': states }, bound, snapshot, unchanged, refusal, rejectAction, expectedButtons, controls, visible, findTaskRow };
