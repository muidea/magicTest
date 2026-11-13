// Real author UI and public conditional owner commands; no React state writes.
const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const { authoring: a } = require('./authoring_cases.cjs');
const { observeAuthorSave } = require('./definition_browser_cases.cjs');
const handlers = {}, base = '/panel/application/definitions/';
const route = (app, member) => base + app.id + '/' + member;
const read = (h, app, member) => h.ok(h.admin, 'GET', route(app, member)).then(r => r.value);
const btn = (scope, text) => scope.getByRole('button', { name: text, exact: typeof text === 'string' });
async function identity(h, app, value) { h.check('Draft owner returns the exact original application identity', value.applicationId === app.id && value.applicationUuid === app.uuid && value.applicationKey === app.name, { id: value.applicationId, uuid: value.applicationUuid, key: value.applicationKey, version: value.definitionVersion }); }
async function save(h, app, member, before, content, actor = h.admin) {
  const pathname = route(app, member), payload = { expectedDefinitionVersion: before.definitionVersion, content };
  const intent = a.journalSave(h, app, pathname, payload);
  intent.method = 'PUT'; intent.before = structuredClone(before); h.persist();
  intent.response = await h.api(actor, 'PUT', pathname, payload); h.persist();
  h.check('Original conditional ' + member + ' command succeeds', h.good(intent.response), intent.response);
  const current = await read(h, app, member); await identity(h, app, current);
  h.check('Independent owner confirms complete original saved content and advanced version', current.definitionVersion > before.definitionVersion && current.definitionVersion === intent.response.data.value.definitionVersion && same(current.content, content), current);
  intent.confirmed = true; h.persist(); return current;
}
async function fixture(h, suffix) {
  const app = await a.definition(h, suffix), entity = a.newEntity(h, app);
  const model = await a.save(h, app, await a.draft(h, app), [entity]), current = await read(h, app, 'pages'), content = structuredClone(current.content);
  const key = model.entities[0].pkgPath + '/' + model.entities[0].name;
  content.defaultPage = 'home'; content.navigation = ['home'];
  content.dataSources = [{ key: 'records', entity: key, mode: 'list', fields: ['id', 'name'], authorization: 'validated-tenant-and-instance-and-entity-permissions', instanceScope: 'current-installation', pagination: { mode: 'cursor', defaultPageSize: 10, maxPageSize: 100 }, orderBy: [{ field: 'id', direction: 'asc' }] }];
  content.pages = [{ key: 'home', title: '原始作者页面', routes: ['/'], navigation: true, layout: { type: 'responsive-grid', columns: 12, gap: 0 }, routeParameters: [], components: [{ key: 'intro', type: 'text', layout: { span: 12, order: 0 }, dataSources: [], properties: { text: '回归页面原始说明' } }, { key: 'records', type: 'entity-table', layout: { span: 12, order: 1 }, dataSources: ['records'], properties: { entity: key, columns: ['id', 'name'], readonly: true } }] }];
  return { app, model, pages: await save(h, app, 'pages', current, content) };
}
async function open(h, app) {
  const page = h.admin.page;
  await page.goto(h.admin.origin + '/panel/application/definition/view?aid=' + app.id, { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: '页面设计', exact: true }).click();
  await page.locator('tr[data-row-key="home"]').getByRole('button', { name: /设计$/ }).click();
  const dialog = page.getByRole('dialog'); await dialog.waitFor();
  await dismissNotifications(h);
  await btn(dialog, '关闭页面设计器').click({ trial: true });
  if (await btn(dialog, '← 返回页面属性').isVisible()) await btn(dialog, '← 返回页面属性').click();
  await dialog.getByRole('textbox', { name: '页面标题', exact: true }).waitFor();
  await dialog.getByRole('textbox', { name: '页面标题', exact: true }).isEnabled().then(enabled => h.check('Page editor exposes the original editable page', enabled));
  return dialog;
}
async function dismissNotifications(h) {
  const page = h.admin.page, close = page.locator('.ant-notification-notice-close:visible');
  for (let count = 0; count < 10 && await close.count(); count++) {
    // Pin this control: a notification may expire between inspection and click.
    const control = await close.first().elementHandle();
    if (!control) continue;
    try {
      h.check('Record and dismiss a visible notification through its real close control', true, { text: await control.evaluate(node => node.parentElement?.innerText || '') });
      try { await control.click({ timeout: 2000 }); }
      catch (error) { if (await control.isVisible()) throw error; }
    } finally { await control.dispose(); }
  }
}
async function confirmDialog(h, action, accept, pattern) {
  await dismissNotifications(h);
  let message;
  const listen = async dialog => { message = dialog.message(); if (accept) await dialog.accept(); else await dialog.dismiss(); };
  h.admin.page.once('dialog', listen);
  try { await action(); h.check('Real browser confirmation describes the unsaved operation', !!message && pattern.test(message), { message, accepted: accept }); }
  finally { h.admin.page.off('dialog', listen); }
}
function watch(h, pathname, method = 'PUT') {
  const writes = [], listen = r => { if (new URL(r.url()).pathname === '/api/v1/web/proxy' + pathname && r.method() === method) writes.push({ method, pathname }); };
  h.admin.page.on('request', listen); return { writes, stop: () => h.admin.page.off('request', listen) };
}
async function synchronized(h, dialog) {
  await dialog.getByText('已与保存草稿同步', { exact: true }).waitFor();
  await dismissNotifications(h);
  await btn(dialog, '关闭页面设计器').click({ trial: true });
}
async function uiSave(h, app, member, trigger) {
  let current;
  await observeAuthorSave(h, app, route(app, member), trigger, async intent => {
    current = await read(h, app, member); await identity(h, app, current);
    h.check('UI original owner write commits its complete content once', current.definitionVersion === intent.response.data.value.definitionVersion && current.definitionVersion > intent.payload.expectedDefinitionVersion && same(current.content, intent.payload.content), current);
  });
  return current;
}
// Lose only the response to the one original accepted UI command. The journal
// and independent owner result remain available; never replay an unknown PUT.
async function observeLostPageSave(h, app, trigger, confirm) {
  const page = h.admin.page, pathname = route(app, 'pages'), match = u => u.origin === h.admin.origin && u.pathname === '/api/v1/web/proxy' + pathname;
  let intent, sends = 0, complete, error;
  const finished = new Promise(resolve => { complete = resolve; });
  const intercept = async r => {
    if (r.request().method() !== 'PUT') return r.continue();
    if (++sends !== 1) { error = new h.Blocked('Duplicate original page save suppressed'); await r.abort('failed'); return; }
    intent = a.journalSave(h, app, pathname, r.request().postDataJSON()); intent.method = 'PUT'; h.persist();
    try { const response = await r.fetch({ maxRetries: 0 }); intent.response = { status: response.status(), data: await response.json() }; h.persist(); }
    catch (e) { intent.transportError = e.message; error = e; h.persist(); }
    finally { try { await r.abort('failed'); } finally { complete(); } }
  };
  await page.route(match, intercept); let timer;
  try {
    await trigger(); await Promise.race([finished, new Promise((_, reject) => { timer = setTimeout(() => reject(new h.Blocked('Original page save result missing; retain the command journal')), 30000); })]);
    if (error) throw error;
    h.check('Exactly one original page save committed before browser response loss', sends === 1 && h.good(intent.response), intent.response);
    await confirm(intent);
    h.check('Owner/UI reconciliation never repeats the original page write', sends === 1);
    intent.confirmed = true; h.persist();
  } finally { clearTimeout(timer); await page.unroute(match, intercept); }
}
handlers['F067-002'] = async h => {
  const { app, model, pages } = await fixture(h, 'pagesave'), members = await read(h, app, 'package-members');
  let dialog = await open(h, app), observer = watch(h, route(app, 'pages'));
  try {
    await dialog.getByLabel('页面标题', { exact: true }).fill('未保存页面输入');
    await dialog.getByText('有未保存的修改', { exact: true }).waitFor();
    await confirmDialog(h, () => btn(dialog, '关闭页面设计器').click(), false, /未保存.*页面修改/);
    h.check('Declining leave retains the real unsaved page input', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === '未保存页面输入');
    await confirmDialog(h, () => btn(dialog, '关闭页面设计器').click(), true, /未保存.*页面修改/);
    await dialog.waitFor({ state: 'hidden' });
    h.check('Cancelling unsaved page dispatches no page command', observer.writes.length === 0, observer.writes);
    h.check('Independent owner retains exact original page and bindings after cancel', same(await read(h, app, 'pages'), pages));
  } finally { observer.stop(); }
  dialog = await open(h, app);
  await dialog.getByLabel('页面标题', { exact: true }).fill('同版本作者原输入');
  const peer = await h.login(h.credentials.account, h.credentials.password), peerContent = structuredClone(pages.content);
  peerContent.pages[0].description = '第二作者已确认的更新';
  const newer = await save(h, app, 'pages', pages, peerContent, peer);
  await observeAuthorSave(h, app, route(app, 'pages'), () => btn(dialog, '保存页面').click(), async () => {
    h.check('Stale original author cannot partially overwrite peer page or bindings', same(await read(h, app, 'pages'), newer));
    h.check('Version conflict preserves the original real UI input', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === '同版本作者原输入');
    await dialog.getByText('保存结果待核对', { exact: true }).waitFor();
    h.check('Conflict blocks another write until explicit read confirmation', await btn(dialog, '保存页面').isDisabled());
    await h.screenshot(h.admin, 'page-conflict-input-kept');
  }, 19);
  await confirmDialog(h, () => btn(dialog, '重新读取已保存草稿').click(), true, /丢弃未保存/); await synchronized(h, dialog);
  h.check('Explicit read restores exact peer page without replay', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === newer.content.pages[0].title);
  await dialog.getByLabel('页面标题', { exact: true }).fill('原保存已提交但响应丢失');
  await dialog.getByLabel('页面路由', { exact: true }).fill('/\n/confirmed-after-loss');
  await observeLostPageSave(h, app, () => btn(dialog, '保存页面').click(), async intent => {
    await dialog.getByText('保存结果待核对', { exact: true }).waitFor();
    h.check('Unknown browser result blocks repeat save and closing until explicit read', await btn(dialog, '保存页面').isDisabled() && await btn(dialog, '关闭页面设计器').isDisabled());
    const confirmed = await read(h, app, 'pages'); await identity(h, app, confirmed);
    h.check('Independent original owner confirms full committed page, route and binding bytes', confirmed.definitionVersion === intent.response.data.value.definitionVersion && confirmed.definitionVersion > newer.definitionVersion && same(confirmed.content, intent.payload.content) && confirmed.content.pages[0].title === '原保存已提交但响应丢失' && same(confirmed.content.pages[0].routes, ['/', '/confirmed-after-loss']) && same(confirmed.content.dataSources, pages.content.dataSources));
    await h.screenshot(h.admin, 'page-lost-response-owner-confirmed');
    await confirmDialog(h, () => btn(dialog, '重新读取已保存草稿').click(), true, /丢弃未保存/); await synchronized(h, dialog);
    h.check('Read-only UI recovery shows the one committed original page', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === confirmed.content.pages[0].title && await btn(dialog, '保存页面').isEnabled());
    h.check('UI recovery preserves the original owner version and content', same(await read(h, app, 'pages'), confirmed));
  });
  h.check('Page cancellation/conflict/unknown recovery preserves model and independently saved members', same((await a.draft(h, app)).entities, model.entities) && same((await read(h, app, 'package-members')).content, members.content));
  await btn(dialog, '关闭页面设计器').click(); await dialog.waitFor({ state: 'hidden' });
};
async function rejectedRemoval(h, app, expected) {
  const proposed = structuredClone(expected.content), asset = proposed.assets.files.find(a => a.key === 'test-image');
  proposed.assets.files = proposed.assets.files.filter(a => a.key !== asset.key); delete proposed.files[asset.path];
  const pathname = route(app, 'package-members'), payload = { expectedDefinitionVersion: expected.definitionVersion, content: proposed };
  const intent = a.journalSave(h, app, pathname, payload); intent.response = await h.api(h.admin, 'PUT', pathname, payload); h.persist();
  h.check('Owner independently rejects exact referenced image removal', intent.response.data?.error?.code === 4 && intent.response.data.error.message.includes(asset.key), intent.response);
  h.check('Rejected actual owner removal retains all original image bytes', same(await read(h, app, 'package-members'), expected));
  intent.confirmed = true; h.persist();
}
handlers['F068-003'] = async h => {
  const { app, model, pages } = await fixture(h, 'pageimage');
  let dialog = await open(h, app);
  await dialog.getByText('页面图片资源', { exact: true }).click();
  const png = await h.admin.page.screenshot({ clip: { x: 0, y: 0, width: 2, height: 2 }, animations: 'disabled' });
  await dialog.getByLabel('图片资源标识', { exact: true }).fill('test-image');
  await dialog.locator('input[type=file]').setInputFiles({ name: 'regression.png', mimeType: 'image/png', buffer: png });
  let members = await uiSave(h, app, 'package-members', () => btn(dialog, '保存图片资源').click());
  const asset = members.content.assets.files.find(a => a.key === 'test-image');
  h.check('Independent member owner stores exact decoded PNG size/digest/bytes', asset?.purpose === 'page-image' && asset.mime === 'image/png' && asset.size === png.length && asset.digest === 'sha256:' + crypto.createHash('sha256').update(png).digest('hex') && Buffer.from(members.content.files[asset.path], 'base64').equals(png), asset);
  await synchronized(h, dialog);
  await dialog.getByLabel('页面背景背景图片', { exact: true }).selectOption('test-image');
  await dialog.getByLabel('页面标题', { exact: true }).fill('图片已保存但页面取消');
  await confirmDialog(h, () => btn(dialog, '关闭页面设计器').click(), true, /未保存.*页面修改/); await dialog.waitFor({ state: 'hidden' });
  h.check('Cancelling page does not roll back the independently saved image', same(await read(h, app, 'package-members'), members));
  h.check('Unsaved page reference and title do not reach original page owner', same((await read(h, app, 'pages')).content, pages.content));
  dialog = await open(h, app); await dialog.getByText('页面图片资源', { exact: true }).click();
  await dialog.getByLabel('页面背景背景图片', { exact: true }).selectOption('test-image');
  let bound = await uiSave(h, app, 'pages', () => btn(dialog, '保存页面').click()); await synchronized(h, dialog);
  h.check('Independent page owner confirms original saved image reference', bound.content.pages[0].appearance?.background?.image?.assetKey === asset.key);
  const rejectUI = async () => {
    const observer = watch(h, route(app, 'package-members'));
    try {
      await btn(dialog, '确认删除图片').click();
      await dialog.getByText('此图片仍被页面引用，请先清除全部引用并保存页面', { exact: true }).waitFor();
      h.check('Actual image deletion confirmation rechecks current page references before writing', observer.writes.length === 0, observer.writes);
      h.check('Local guard preserves all independently saved image bytes and page bindings', same((await read(h, app, 'package-members')).content, members.content) && same(await read(h, app, 'pages'), bound));
    } finally { observer.stop(); }
  };
  await btn(dialog, '删除 test-image').click(); await rejectUI();
  members = await read(h, app, 'package-members'); await rejectedRemoval(h, app, members);
  await dialog.getByLabel('页面背景背景图片', { exact: true }).selectOption('');
  await uiSave(h, app, 'pages', () => btn(dialog, '保存页面').click()); await synchronized(h, dialog);
  await btn(dialog, '取消删除').click(); await btn(dialog, '删除 test-image').click();
  // Preview was opened while no page referenced the image; introduce and save
  // a new reference before confirming that same pending deletion.
  await dialog.getByLabel('页面背景背景图片', { exact: true }).selectOption('test-image');
  bound = await uiSave(h, app, 'pages', () => btn(dialog, '保存页面').click()); await synchronized(h, dialog);
  await rejectUI(); members = await read(h, app, 'package-members'); await rejectedRemoval(h, app, members);
  await h.screenshot(h.admin, 'image-confirmation-rechecks-new-reference');
  await dialog.getByLabel('页面背景背景图片', { exact: true }).selectOption('');
  const cleared = await uiSave(h, app, 'pages', () => btn(dialog, '保存页面').click()); await synchronized(h, dialog);
  const released = await uiSave(h, app, 'package-members', () => btn(dialog, '确认删除图片').click()); await synchronized(h, dialog);
  h.check('Formal exact owner removal releases only original unreferenced image', !released.content.assets.files.some(a => a.key === asset.key) && !(asset.path in released.content.files));
  h.check('Resource release preserves the cleared page and original model identities', same((await read(h, app, 'pages')).content, cleared.content) && same((await a.draft(h, app)).entities, model.entities));
  await h.screenshot(h.admin, 'image-released-after-all-page-references-cleared');
  await btn(dialog, '关闭页面设计器').click(); await dialog.waitFor({ state: 'hidden' });
};
// Author history is exercised through real controls before immutable delivery.
function editedAuthorContent(before, title, text) {
  const current = structuredClone(before), home = current.pages.find(p => p.key === 'home');
  if (!home || home.components.length !== 2 || !home.components.some(c => c.key === 'intro' && c.type === 'text') || !home.components.some(c => c.key === 'records' && c.type === 'entity-table')) throw Error('Exact original two-component page required');
  home.title = title; home.routes = ['/', '/author-confirmed'];
  home.components = ['records', 'intro'].map((key, index) => {
    const c = home.components.find(c => c.key === key);
    c.layout.order = index + 1;
    if (key === 'intro') c.properties.text = text;
    return c;
  });
  return current;
}
async function selectAuthorComponent(h, dialog, key) {
  const control = btn(dialog, '选择组件 ' + key);
  const geometry = await control.evaluate(node => {
    const r = node.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return { visibleWidth: r.width, visibleHeight: r.height, centerHitsControl: hit === node || node.contains(hit), hitTag: hit?.tagName, hitClass: hit?.className };
  });
  h.observe({ kind: 'author-component-pointer-geometry', componentKey: key, geometry });
  // Exercise the real accessible button with keyboard input. Pointer coverage
  // remains a separate recorded observation; never use force-click or DOM state.
  await control.focus(); await control.press('Enter');
  h.check('Real keyboard selection activates only the exact original component', await control.getAttribute('aria-pressed') === 'true');
}
async function prepareAuthorMain(h, authored) {
  const before = authored.pages, title = '正式作者回归 ' + h.state.prefix, text = '<script>仅显示作者文本</script>';
  let dialog = await open(h, authored.app);
  await dialog.getByLabel('页面标题', { exact: true }).fill(title);
  await dismissNotifications(h);
  await btn(dialog, /^撤\s*销$/).click();
  h.check('Real author undo restores the original title without an owner write', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === before.content.pages[0].title && same(await read(h, authored.app, 'pages'), before));
  await dismissNotifications(h);
  await btn(dialog, /^重\s*做$/).click();
  h.check('Real author redo restores the unsaved exact title', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === title);
  await dialog.getByLabel('页面路由', { exact: true }).fill('/\n/author-confirmed');
  await selectAuthorComponent(h, dialog, 'intro');
  await dialog.getByLabel('属性 text', { exact: true }).fill(text);
  await btn(dialog, '下移 intro').click();
  h.check('Real keyboard-accessible component move changes visible order with no owner write', same(await dialog.locator('[aria-label^="选择组件 "]').evaluateAll(nodes => nodes.map(n => n.getAttribute('aria-label'))), ['选择组件 records', '选择组件 intro']) && same(await read(h, authored.app, 'pages'), before));
  const saved = await uiSave(h, authored.app, 'pages', () => btn(dialog, '保存页面').click());
  h.check('Original conditional UI save persists every exact changed field and preserves all bindings, navigation and peer metadata', same(saved.content, editedAuthorContent(before.content, title, text)));
  await synchronized(h, dialog); await h.screenshot(h.admin, 'author-history-order-saved');
  await btn(dialog, '关闭页面设计器').click(); await dialog.waitFor({ state: 'hidden' });
  dialog = await open(h, authored.app);
  h.check('Reopening actual author UI reads original saved title and route', await dialog.getByLabel('页面标题', { exact: true }).inputValue() === title && await dialog.getByLabel('页面路由', { exact: true }).inputValue() === '/\n/author-confirmed');
  await selectAuthorComponent(h, dialog, 'intro');
  h.check('Reopening preserves exact escaped component text and saved full owner content', await dialog.getByLabel('属性 text', { exact: true }).inputValue() === text && same(await read(h, authored.app, 'pages'), saved));
  await btn(dialog, '关闭页面设计器').click(); await dialog.waitFor({ state: 'hidden' });
  authored.pages = saved;
}
handlers['F067-001'] = async h => {
  const runtime = require('./page_runtime_cases.cjs'), business = require('./business_cases.cjs');
  const f = await runtime.explicitFixture(h, undefined, undefined, { suffix: 'pageauthor', requestPrefix: 'page-author-', prepareAuthor: prepareAuthorMain });
  let primary;
  try {
    const actor = await business.member(h, 'manager'), snapshots = [];
    for (const installation of f.installations) {
      const route = '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + installation.deploymentId;
      const value = (await h.ok(actor, 'GET', route)).value;
      h.check('Ordinary runtime consumes complete exact frozen author pages in each distinct installation', same(value.pages, f.revision.content.pages) && value.readIdentity.installationId === String(installation.id) && value.readIdentity.deploymentId === installation.deploymentId && value.readIdentity.runtimeApplicationUuid === installation.receipt.runtimeApplicationUuid);
      snapshots.push({ route, value });
    }
    const current = await read(h, f.application, 'pages'), changed = structuredClone(current.content);
    changed.pages[0].title = '未发布作者标题';
    await save(h, f.application, 'pages', current, changed);
    for (const snapshot of snapshots) h.check('Unpublished author change preserves full original installed runtime pages and fence', same((await h.ok(actor, 'GET', snapshot.route)).value, snapshot.value));
    h.check('Independent immutable revision still contains exact published author title, route and component history result', same((await h.ok(h.admin, 'GET', route(f.application, 'revisions/' + f.revision.id))).value, f.revision));
  } catch (error) { primary = error; throw error; }
  finally { await runtime.disposeExplicitFixture(h, f, primary); }
  await h.partial('Real author title/routes, undo/redo, component text/order, exact conditional save and reopen, readonly ready preflight, publication, dual installation and ordinary frozen runtime metadata verified. UI initial-page creation/navigation/action binding and formal ZIP import consumers remain unverified.');
};
// Only a proven pre-admission rejection can close a creation intent without a
// resource ID. No generic error or directory absence proves an unknown POST.
async function reconcileRejectedDefinitionCreations(h) {
  const pending = h.state.resources.filter(r => r.phase === 'intent' && r.kind === 'definition');
  if (!pending.length) throw new h.Blocked('No original rejected definition creation to reconcile');
  const proof = [];
  for (const r of pending) {
    const c = r.creation, response = c?.response, intended = c?.intended;
    if (r.collection !== base || r.id != null || c?.outcome !== 'unconfirmed' || response?.status !== 200 || response.data?.error?.code !== 4 || response.data.error.message !== 'model application package prefix is invalid' || response.data.value != null || !intended?.uuid || c.identity?.uuid !== intended.uuid || !intended.pkgPrefix?.includes('-') || !same(h.admin.identity, c.actorIdentity) || h.admin.origin !== c.origin) throw new h.Blocked('Missing exact original pre-admission rejection; retain intent without replay or guessed deletion');
    const rows = await h.directory(h.admin, base);
    if (!same(h.admin.identity, c.actorIdentity) || h.admin.origin !== c.origin) throw new h.Blocked('Original actor changed during reconciliation');
    h.check('Complete original owner directory independently excludes the rejected UUID and name', !rows.some(v => v.uuid === intended.uuid || v.name === intended.name));
    r.reconciliation = { originalJournalId: c.journalId, outcome: 'terminal-pre-admission-rejection', ownerDirectoryComplete: true, uuid: intended.uuid, name: intended.name, noCommandReplayed: true };
    r.phase = 'deleted'; h.persist(); proof.push(r.reconciliation);
  }
  return proof;
}
async function reconcileRejectedPageWrite(h, r, evidence, evidenceSha256) {
  const { sanitize } = require('./evidence_sanitizer.cjs'), c = r.pendingAuthoringSave, created = r.creation?.response?.data?.value;
  const views = c?.payload?.content?.entityViews, keys = Object.keys(views || {});
  const view = keys.length === 1 && views[keys[0]], message = c?.response?.data?.error?.message;
  const layoutRefusal = !!view?.detail?.layout && message === 'entityViews ' + keys[0] + ': 首批不支持 detail 自定义 layout';
  const primaryRefusal = view?.entity?.primaryKey === 'id' && view.fields?.filter(f => f.name === 'id').length === 1 && view.fields.find(f => f.name === 'id').readonly === false && message === 'entityViews ' + keys[0] + ' 字段 id 放宽或改变模型约束';
  const invalidMetrics = c?.payload?.content?.pages?.flatMap(p => p.components || []).filter(component => component.type === 'metric-group' && component.properties === undefined && Array.isArray(component.metricGroup?.metrics));
  const metricsRefusal = invalidMetrics?.length === 1 && message === '定义 JSON 缺少字段 "properties"';
  if (r.kind !== 'definition' || r.phase === 'deleted' || r.collection !== base || !r.creation?.ownershipConfirmed || !created || created.id !== r.id || c?.confirmed !== false || c.route !== route(created, 'pages') || c.response?.status !== 400 || c.response.data?.error?.code !== 4 || c.response.data.value != null || !(layoutRefusal || primaryRefusal || metricsRefusal) || !same(h.admin.identity, r.creation.actorIdentity) || h.admin.origin !== r.creation.origin || !/^sha256:[a-f0-9]{64}$/.test(evidenceSha256)) throw new h.Blocked('Rejected page save requires exact original pre-write layout, primary constraint or component properties refusal and original author');
  const writes = (evidence.trace || []).map((v, index) => ({ v, index })).filter(({ v }) => v.kind === 'request' && v.method === 'PUT' && v.route === c.route && v.origin === h.admin.origin && same(v.actor, h.admin.identity) && same(v.body, sanitize(c.payload)) && same(v.response, sanitize(c.response)));
  if (writes.length !== 1) throw new h.Blocked('Original rejected page save is not uniquely bound to immutable case evidence');
  const before = evidence.trace.slice(0, writes[0].index).filter(v => v.kind === 'request' && v.method === 'GET' && v.route === c.route && v.origin === h.admin.origin && same(v.actor, h.admin.identity) && h.good(v.response)).at(-1)?.response.data.value;
  if (before?.applicationId !== r.id || before.applicationUuid !== created.uuid || before.applicationKey !== created.name || before.definitionVersion !== c.payload.expectedDefinitionVersion) throw new h.Blocked('Original pre-save page owner read is missing or changed');
  const current = await read(h, created, 'pages');
  h.check('Original rejected page write preserves exact conditional owner version and complete retained public page evidence', same(sanitize(current), before) && current.definitionVersion === c.payload.expectedDefinitionVersion, current);
  c.disposition = { evidenceSha256, originalJournalId: c.journalId, outcome: 'rejected-before-owner-write', definitionVersion: current.definitionVersion, noCommandReplayed: true };
  c.confirmed = true; h.persist(); return c.disposition;
}
// This current page DTO omits a nil detail-source pagination field. Preserve
// the original journal; accept only that exact acknowledged representation.
function acknowledgedPageContent(content) {
  const current = structuredClone(content);
  for (const source of current?.dataSources || [])
    if (source.mode === 'detail' && source.pagination === null) delete source.pagination;
  return current;
}
async function reconcileAcknowledgedAuthorWrites(h) {
  const pending = h.state.resources.filter(r => r.phase !== 'deleted' && r.pendingAuthoringSave?.confirmed === false);
  if (!pending.length) throw new h.Blocked('No original unconfirmed acknowledged author write');
  const proof = [];
  for (const r of pending) {
    if (r.pendingAuthoringSave.route === base + r.id) {
      proof.push(await require('./installed_icon_cases.cjs').reconcileImageUpload(h, r));
      continue;
    }
    const intent = r.pendingAuthoringSave, created = r.creation?.response?.data?.value, response = intent.response;
    if (r.kind !== 'definition' || r.collection !== base || !created || !r.creation.ownershipConfirmed || created.id !== r.id || !same(h.admin.identity, r.creation.actorIdentity) || h.admin.origin !== r.creation.origin || intent.method !== 'PUT' || !['pages', 'package-members'].some(member => intent.route === route(created, member)) || !response || !h.good(response) || response.data.value?.applicationId !== r.id || response.data.value.applicationUuid !== created.uuid || response.data.value.applicationKey !== created.name || response.data.value.definitionVersion <= intent.payload.expectedDefinitionVersion || !same(response.data.value.content, intent.route === route(created, 'pages') ? acknowledgedPageContent(intent.payload.content) : intent.payload.content)) throw new h.Blocked('No exact original accepted author-write proof; retain journal without replay');
    const app = (await h.ok(h.admin, 'GET', base + r.id)).value;
    h.check('Original author write still belongs to the original exact definition', app.id === r.id && app.uuid === created.uuid && app.name === created.name);
    const current = (await h.ok(h.admin, 'GET', intent.route)).value;
    h.check('Independent original owner confirms the complete acknowledged original save', current.applicationId === r.id && current.applicationUuid === created.uuid && current.definitionVersion === response.data.value.definitionVersion && same(current.content, response.data.value.content));
    if (!same(h.admin.identity, r.creation.actorIdentity) || h.admin.origin !== r.creation.origin) throw new h.Blocked('Original actor changed during acknowledged-write read');
    intent.reconciliation = { originalJournalId: intent.journalId, applicationId: r.id, applicationUuid: created.uuid, version: current.definitionVersion, omittedDetailNullPagination: !same(intent.payload.content, response.data.value.content), contentDigest: 'sha256:' + crypto.createHash('sha256').update(JSON.stringify(current.content)).digest('hex'), noCommandReplayed: true };
    intent.confirmed = true; h.persist(); proof.push(intent.reconciliation);
  }
  return proof;
}
module.exports = { handlers, observeLostPageSave, reconcileRejectedDefinitionCreations, reconcileAcknowledgedAuthorWrites, reconcileRejectedPageWrite,
  editedAuthorContent, authorFixture: { fixture, read, save } };
