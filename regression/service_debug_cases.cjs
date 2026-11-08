// Actual debugger UI requests are paired with independently received HTTP bytes.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const handlers = {};
const query = [{ name: 'marker', in: 'query', required: true, schema: { type: 'string' } }];
const initialBody = { label: 'initial-json-sample', count: 0, enabled: false };
const spec = { version: '1', operations: [
  { key: 'echo', name: 'JSON echo', method: 'POST', upstreamPath: '/echo', parameters: query,
    requestBody: { contentType: 'application/json', required: true, schema: { type: 'object', required: ['label', 'count', 'enabled'], properties: { label: { type: 'string' }, count: { type: 'integer' }, enabled: { type: 'boolean' } } }, example: initialBody },
    responseBody: { contentType: 'application/json', schema: { type: 'object' } } },
  { key: 'slow', name: 'Slow original', method: 'GET', upstreamPath: '/slow', parameters: query, responseBody: { contentType: 'application/json', schema: { type: 'object' } } },
  { key: 'fast', name: 'Current fast', method: 'GET', upstreamPath: '/fast', parameters: query, responseBody: { contentType: 'application/json', schema: { type: 'object' } } },
] };
async function prepare(h, suffix) {
  const f = await graph.fixture(h, suffix, {}, 'tenantAdmin', spec);
  await graph.subscribe(h, f);
  const page = h.user.page;
  await page.goto(h.user.origin + '/workbench/services/' + f.service.id + '/?source=portal', { waitUntil: 'networkidle' });
  await page.locator('button').filter({ hasText: /^发送请求$/ }).waitFor();
  return { f, page };
}
const parameter = page => page.locator('tr[data-row-key="query:marker"] textarea');
const send = page => page.locator('button').filter({ hasText: /^发送请求$/ });
async function editJSON(page, value) {
  const editor = page.locator('.monaco-editor').filter({ has: page.locator('textarea.inputarea') }).first();
  // Paste through Monaco's native clipboard handler; insertText can trigger
  // auto-closing pairs and leave an extra closing brace in the model.
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(page.url()).origin });
  await page.evaluate(text => navigator.clipboard.writeText(text), value);
  await editor.locator('textarea.inputarea').focus();
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.press('ControlOrMeta+V');
}
async function choose(page, name) {
  const item = page.getByRole('menuitem').filter({ hasText: name });
  // Ant switches the actual control at lg=992. Wait for the control for the
  // requested viewport; a transient old render must not select the other branch.
  if (page.viewportSize().width >= 992) {
    await item.waitFor({ state: 'visible' }); await item.click();
  }
  else {
    const select = page.locator('.ant-select').filter({ has: page.getByRole('combobox', { name: '服务操作', exact: true }) });
    await select.locator('.ant-select-selector').click();
    await page.locator('.ant-select-item-option').filter({ hasText: name }).click();
  }
}
async function invoke(h, f, page, marker, path, body) {
  await parameter(page).fill(marker);
  const pending = page.waitForResponse(r => new URL(r.url()).pathname.includes('/gateway/subscribed-services/' + f.service.key + '/') && new URL(r.url()).searchParams.get('marker') === marker);
  pending.catch(() => {});
  let response;
  try { await send(page).click(); response = await pending; }
  catch (error) {
    h.observe({ kind: 'debugger-unresolved-input', marker, path, alerts: await page.locator('.ant-alert,.ant-form-item-explain-error').allTextContents(),
      buttons: await page.locator('button').evaluateAll(nodes => nodes.map(n => ({ text: n.innerText, label: n.getAttribute('aria-label'), disabled: n.disabled, visible: !!(n.offsetWidth || n.offsetHeight) }))), accessibility: await page.locator('body').ariaSnapshot(),
      editorText: (await page.locator('.monaco-editor').allTextContents()).map(s => s.slice(0, 5000)) });
    await h.screenshot(h.user, 'unresolved-debug-' + crypto.createHash('sha256').update(marker).digest('hex').slice(0, 8));
    throw error;
  }
  const value = await response.json();
  const received = f.up.requests.filter(r => r.marker === marker);
  h.observe({ kind: 'debugger-ui-response', marker, status: response.status(), value, received });
  h.check('Real original debugger request reaches exact HTTP operation once with encoded marker', response.status() === 200 && value.marker === marker && received.length === 1 && received[0].path === path && received[0].query.marker === marker, { value, received });
  if (body) h.check('Independent upstream receives exact edited JSON including zero and false', received[0].method === 'POST' && received[0].contentType.startsWith('application/json') && same(JSON.parse(received[0].body), body), received);
  await page.getByText('HTTP 200', { exact: true }).waitFor();
  h.check('Debugger shows real response timing', await page.getByText(/^\d+ ms$/, { exact: true }).count() > 0);
  return value;
}
handlers['F044-001'] = async h => {
  const { f, page } = await prepare(h, 'json_debug');
  const editor = page.locator('.monaco-editor').first();
  h.check('JSON body editor is seeded from the actual published interface example', (await editor.innerText()).includes(initialBody.label) && (await editor.innerText()).includes('false'));
  const body = { label: 'edited / ? & 中文', count: 0, enabled: false };
  await editJSON(page, JSON.stringify(body, null, 2));
  await invoke(h, f, page, 'marker / ? & 中文 ' + crypto.randomBytes(6).toString('hex'), '/echo', body);
  await h.screenshot(h.user, 'actual-json-debug-response');
};
handlers['F044-002'] = async h => {
  const { f, page } = await prepare(h, 'invalid_cancel_debug');
  const before = f.up.requests.length;
  await parameter(page).fill('invalid-json-marker'); await editJSON(page, '{invalid'); await send(page).click();
  await page.locator('.ant-alert-error').waitFor();
  h.check('Malformed body is rejected before any upstream call', f.up.requests.length === before);
  await editJSON(page, JSON.stringify(initialBody)); await parameter(page).fill(''); await send(page).click();
  await page.getByText('请填写marker', { exact: true }).waitFor();
  h.check('Missing required query is rejected before any upstream call', f.up.requests.length === before);
  await choose(page, 'Slow original');
  const original = crypto.randomBytes(10).toString('hex'), gate = f.up.hold(original);
  const canceled = [], observeFailure = request => {
    if (new URL(request.url()).searchParams.get('marker') === original) canceled.push(request.failure()?.errorText);
  };
  page.on('requestfailed', observeFailure);
  const current = crypto.randomBytes(10).toString('hex');
  try {
    await parameter(page).fill(original); await send(page).click();
    const timeout = setTimeout(() => gate.started(), 10000);
    try { await gate.reached; } finally { clearTimeout(timeout); }
    h.check('Original slow debugger request actually reached controlled upstream before cancellation', f.up.requests.some(r => r.marker === original && r.path === '/slow'));
    // Operation change is the debugger's formal transport cancellation path.
    await choose(page, 'Current fast');
    await invoke(h, f, page, current, '/fast');
    h.check('Original browser transport is canceled after operation change', canceled.some(error => /ABORTED|CANCELED/.test(error)), canceled);
  } finally { gate.release(); page.off('requestfailed', observeFailure); }
  await new Promise(resolve => setTimeout(resolve, 300));
  await page.getByRole('tab', { name: /^执行记录/ }).click();
  const records = page.getByRole('tabpanel', { name: /^执行记录/ });
  const rows = records.locator('tr.ant-table-row');
  h.check('Canceled original operation cannot append a late execution record over the current request', await rows.count() === 1 && (await rows.innerText()).includes('fast') && !(await rows.innerText()).includes('slow'));
  await rows.locator('.ant-table-row-expand-icon').click();
  const values = await records.locator('textarea[readonly]').evaluateAll(nodes => nodes.map(n => n.value));
  h.check('Expanded current record contains its exact response without the canceled marker', values.some(v => v.includes(current)) && values.every(v => !v.includes(original)), values);
  await h.screenshot(h.user, 'invalid-and-canceled-debug-original');
};
handlers['F044-003'] = async h => {
  const { f, page } = await prepare(h, 'responsive_debug');
  const long = '长响应 / ? & '.repeat(180) + 'END-OF-ORIGINAL';
  for (const width of [390, 1366, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await choose(page, 'JSON echo');
    await editJSON(page, JSON.stringify({ label: long, count: 0, enabled: false }));
    await invoke(h, f, page, 'width-' + width + '-' + crypto.randomBytes(6).toString('hex'), '/echo', { label: long, count: 0, enabled: false });
    const request = page.getByText('请求参数', { exact: true }).locator('xpath=ancestor::section[1]');
    const response = page.getByRole('tab', { name: '响应结果', exact: true }).locator('xpath=ancestor::section[1]');
    const a = await request.boundingBox(), b = await response.boundingBox();
    h.check('Request and response use nonoverlapping readable layout at width ' + width, a && b && a.width > 200 && b.width > 200 && (width >= 1400 ? b.x >= a.x + a.width - 1 : b.y >= a.y + a.height - 1), { a, b });
    await page.getByRole('tab', { name: '接口格式', exact: true }).click();
    await page.getByRole('button', { name: '下载 OpenAPI', exact: true }).waitFor();
    await page.getByRole('tab', { name: '接入说明', exact: true }).click();
    const address = h.user.origin + '/api/v1/gateway/services/' + f.service.key;
    h.check('Current tenant guide remains accessible at width ' + width, (await page.locator('body').innerText()).includes(address));
    h.check('Long request, response and guide do not overflow viewport', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
    await h.screenshot(h.user, 'debug-layout-' + width);
    await page.getByRole('tab', { name: '在线调试', exact: true }).click();
    await choose(page, 'Current fast'); await parameter(page).waitFor();
  }
};
for (const handler of Object.values(handlers)) { handler.actors = ['user', 'tenantAdmin']; handler.transport = 'owner-api'; }
module.exports = { handlers };
