// Real author UI plus independent public owner reads. Never mutate React state.
const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const handlers = {};
const base = '/panel/application/definitions/';
const entityRoute = '/panel/application/definition/entitys/';
const clone = x => structuredClone(x);
const card = (page, title) => page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title').filter({ hasText: new RegExp('^' + title + '$') }) }).last();
const view = (app, entity, action = 'view') => entity ? '/panel/application/definition/entity/' + action + '?aid=' + app.id + '&eid=' + entity.id : '/panel/application/definition/view?aid=' + app.id;
async function open(h, app, entity, action) {
  await h.admin.page.goto(h.admin.origin + view(app, entity, action), { waitUntil: 'networkidle' });
  await h.admin.page.getByRole('tab', { name: entity && action === 'edit' ? '表格编辑' : '实体管理', exact: true }).waitFor({ state: 'visible' }).catch(error => { if (!entity || action === 'edit') throw error; });
}
function treeNode(page, name) { return page.locator('.ant-tree-title').filter({ hasText: new RegExp('^' + name + '$') }); }
async function settle(page) {
  await page.waitForLoadState('networkidle');
  await page.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' });
}
async function emptyDirectory(h, page) {
  const list = card(page, '实体列表');
  // Tree readiness does not prove that the separate table request rendered.
  // Wait for the actual empty-table state, then retain its visible evidence.
  await list.locator('.ant-table-placeholder .ant-empty').waitFor({ state: 'visible' });
  await list.locator('.ant-spin-spinning').waitFor({ state: 'hidden' });
  const text = await list.innerText(), rows = await list.locator('tbody tr[data-row-key]').count();
  const createVisible = await page.getByRole('button', { name: /新增实体$/ }).isVisible();
  const proof = { text, rows, createVisible };
  h.observe({ kind: 'empty-directory-render', ...proof });
  return { valid: /暂无数据|No data/.test(text) && rows === 0 && createVisible, proof };
}
// Some author forms reuse DOM ids. Scope by the rendered field container so
// a modal label cannot resolve to the outer entity form's equally named input.
function formInput(scope, label) {
  return scope.locator('.ant-form-item').filter({ has: scope.page().locator('label').filter({ hasText: new RegExp('^' + label + '$') }) }).locator('input').first();
}
async function screen(h, label) { return h.screenshot(h.admin, label); }

// Intercept the exact UI write once, journal its original bytes before dispatch,
// and require an independent owner confirmation before allowing fixture cleanup.
async function observeAuthorSave(h, app, pathname, trigger, confirm, expectedCode, method = 'PUT') {
  const page = h.admin.page, match = url => url.origin === h.admin.origin && url.pathname === '/api/v1/web/proxy' + pathname;
  let intent, sends = 0;
  const route = async r => {
    if (r.request().method() !== method) return r.continue();
    sends++;
    if (sends > 1) {
      intent.duplicateDispatches = sends; h.persist();
      return r.abort('failed');
    }
    intent = a.journalSave(h, app, pathname, r.request().postDataJSON() || {});
    intent.method = method; h.persist();
    try {
      const response = await r.fetch({ maxRetries: 0 });
      intent.response = { status: response.status(), data: await response.json() }; h.persist();
      await r.fulfill({ response });
    } catch (error) { intent.transportError = error.message; h.persist(); await r.abort('failed'); }
  };
  await page.route(match, route);
  const returned = page.waitForResponse(r => match(new URL(r.url())) && r.request().method() === method, { timeout: 25000 });
  returned.catch(() => {});
  try {
    await trigger(); await returned;
    h.check('UI dispatched exactly one original author command', sends === 1 && !!intent?.response);
    h.check('Original UI write reached the expected owner outcome', expectedCode ? intent.response.data?.error?.code === expectedCode : h.good(intent.response), intent.response);
    await confirm(intent);
    intent.confirmed = true; h.persist();
  } finally { await page.unroute(match, route); }
}

async function single(h, suffix) {
  const app = await a.definition(h, suffix), entity = a.newEntity(h, app);
  const model = await a.save(h, app, await a.draft(h, app), [entity]);
  return { app, model, entity: model.entities[0] };
}

async function tableIDs(h, table, expected, label) {
  const found = [];
  for (let number = 0; number < 30; number++) {
    if (expected.length) await table.locator('tbody tr[data-row-key]').first().waitFor({ state: 'visible' });
    const ids = await table.locator('tbody tr[data-row-key]').evaluateAll(rows => rows.map(r => r.getAttribute('data-row-key')));
    h.check(label + ' renders only original owner entries without duplicates', ids.every(id => expected.includes(id) && !found.includes(id)), { ids, found });
    found.push(...ids);
    const next = table.locator('li.ant-pagination-next');
    if (!await next.count() || await next.evaluate(e => e.classList.contains('ant-pagination-disabled'))) break;
    await next.locator('button').click();
    if (ids.length) await table.locator('tr[data-row-key="' + ids[0] + '"]').waitFor({ state: 'hidden' });
    await settle(h.admin.page);
  }
  h.check(label + ' is complete across all real UI pages', same([...found].sort(), [...expected].sort()), { expected, found });
}

handlers['F012-001'] = async h => {
  const app = await a.definition(h, 'entitydirectory'), parent = a.newEntity(h, app), page = h.admin.page;
  parent.name = 'parent'; parent.showName = '目录父实体';
  for (let i = 0; i < 15; i++) { const field = clone(parent.fields.find(f => f.name === 'description')); field.name = 'extra' + i; field.showName = '扩展字段' + i; field.spec.fieldName = field.name; parent.fields.push(field); }
  await a.library(h, app); parent.blockInfo = [await a.scriptBinding(h)];
  const children = Array.from({ length: 21 }, (_, i) => { const e = a.newEntity(h, app); e.name = 'child' + String.fromCharCode(65 + i); e.showName = '下级实体' + i; e.pkgPath += '/parent'; return e; });
  const folder = a.newEntity(h, app); folder.pkgPath += '/area'; folder.showName = '独立目录实体';
  const model = await a.save(h, app, await a.draft(h, app), [parent, ...children, folder]);
  const original = model.entities.find(e => e.name === 'parent'), other = model.entities.find(e => e.showName === folder.showName);
  await open(h, app); await settle(page);
  await tableIDs(h, card(page, '实体列表'), model.entities.map(e => String(e.id)), 'Root entity directory');
  await treeNode(page, parent.showName).click(); await card(page, '字段信息').waitFor({ state: 'visible' }); await settle(page);
  h.check('Parent with own definition exposes exact original identity', (await card(page, '基础信息').innerText()).includes(parent.showName));
  await tableIDs(h, card(page, '字段信息'), original.fields.map(f => f.name), 'Original field directory');
  await tableIDs(h, card(page, '功能块信息'), original.blockInfo.map(b => String(b.id)), 'Original block directory');
  await tableIDs(h, card(page, '服务开放能力'), original.serviceExpose.capabilities.map(c => c.key), 'Original capability directory');
  await tableIDs(h, card(page, '下级实体'), model.entities.filter(e => e.pkgPath === original.pkgPath + '/' + original.name).map(e => String(e.id)), 'Child entity directory');
  await treeNode(page, 'area').click(); await settle(page);
  h.check('A directory node does not retain unrelated parent definition details', await card(page, '字段信息').count() === 0);
  await tableIDs(h, card(page, '实体列表'), [String(other.id)], 'Separate directory');
  const target = '/api/v1/web/proxy' + entityRoute + original.id;
  const match = url => url.pathname === target;
  let release, fetched, intercepted = 0;
  const held = new Promise(resolve => { fetched = resolve; }), gate = new Promise(resolve => { release = resolve; });
  const delay = async route => {
    intercepted++;
    const response = await route.fetch({ maxRetries: 0 }); fetched(); await gate;
    await route.fulfill({ response });
  };
  await page.route(match, delay);
  try {
    await treeNode(page, parent.showName).click();
    await Promise.race([held, new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('Original parent detail was not intercepted')), 20000); timer.unref(); })]);
    await treeNode(page, folder.showName).click();
    await card(page, '基础信息').locator('.ant-descriptions-item-content').filter({ hasText: folder.showName }).waitFor();
    const late = page.waitForResponse(r => match(new URL(r.url()))); release(); await late; await settle(page);
    h.check('Late original parent response cannot overwrite currently selected other entity', intercepted === 1 && (await card(page, '基础信息').innerText()).includes(folder.showName) && !(await card(page, '基础信息').innerText()).includes(parent.showName));
  } finally { release(); await page.unroute(match, delay); }
  h.check('All browser directory selection/pagination leaves original model unchanged', same(await a.draft(h, app), model));
  await screen(h, 'complete-directory-and-late-selection');
};

handlers['F013-003'] = async h => {
  const { app, model, entity } = await single(h, 'fielddialog'), page = h.admin.page;
  await open(h, app, entity, 'edit');
  const writes = [], watch = r => { if (['PUT', 'POST', 'DELETE'].includes(r.method()) && new URL(r.url()).pathname.includes('/panel/application/')) writes.push(r.method() + ' ' + new URL(r.url()).pathname); };
  page.on('request', watch);
  try {
    await page.getByRole('button', { name: '新增字段', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '新增字段', exact: true });
    await formInput(dialog, '字段名称').fill('cancelledField');
    await dialog.getByRole('button', { name: /^取\s*消$/ }).click();
    await dialog.waitFor({ state: 'hidden' });
    h.check('Cancelling the actual field modal sends no authoring command', writes.length === 0, writes);
    h.check('Cancelled field leaves full original owner draft unchanged', same(await a.draft(h, app), model));
  } finally { page.off('request', watch); }
  const fields = card(page, '字段信息');
  await fields.locator('tr[data-row-key="name"]').getByRole('button', { name: /编\s*辑$/ }).click();
  const dialog = page.getByRole('dialog', { name: '编辑字段', exact: true });
  await formInput(dialog, '显示名称').fill('原字段编辑确认');
  await dialog.getByRole('button', { name: /^保\s*存$/ }).click();
  await dialog.waitFor({ state: 'hidden' });
  h.check('Field confirmation is still local before saving original entity', same(await a.draft(h, app), model));
  let edited;
  await observeAuthorSave(h, app, entityRoute + entity.id,
    () => page.getByRole('button', { name: /^保\s*存$/ }).click(), async () => {
      edited = await a.draft(h, app);
      h.check('Field update preserves original entity, field count and all other fields', edited.entities.length === 1 && edited.entities[0].id === entity.id && edited.entities[0].fields.length === entity.fields.length && edited.entities[0].fields.find(f => f.name === 'name').showName === '原字段编辑确认' && same(edited.entities[0].fields.filter(f => f.name !== 'name'), entity.fields.filter(f => f.name !== 'name')), edited);
    });
  await open(h, app, edited.entities[0], 'edit');
  await fields.locator('tr[data-row-key="name"]').getByRole('button', { name: /编\s*辑$/ }).click();
  const staleDialog = page.getByRole('dialog', { name: '编辑字段', exact: true });
  await formInput(staleDialog, '显示名称').fill('冲突输入必须保留');
  await staleDialog.getByRole('button', { name: /^保\s*存$/ }).click();
  const peer = clone(edited.entities[0]); peer.description = '另一作者已确认的变更';
  const newer = await a.save(h, app, edited, [peer]);
  await observeAuthorSave(h, app, entityRoute + entity.id,
    () => page.getByRole('button', { name: /^保\s*存$/ }).click(), async () => {
      h.check('Stale field save cannot overwrite another author or allocate another entity', same(await a.draft(h, app), newer));
      h.check('Conflict keeps actual user input available', (await fields.locator('tr[data-row-key="name"]').innerText()).includes('冲突输入必须保留'));
    }, 19);
  await screen(h, 'field-conflict');
};

handlers['F012-002'] = async h => {
  const app = await a.definition(h, 'emptyselection'), page = h.admin.page;
  await open(h, app); await settle(page);
  const empty = await emptyDirectory(h, page);
  h.check('Empty real definition shows a current empty entity directory', empty.valid, empty.proof);
  const populated = await a.save(h, app, await a.draft(h, app), [a.newEntity(h, app)]), entity = populated.entities[0];
  await open(h, app);
  await treeNode(page, entity.showName).click(); await card(page, '字段信息').waitFor({ state: 'visible' }); await settle(page);
  h.check('Original selection shows its real original fields', await card(page, '字段信息').isVisible());
  // Model-draft saves upsert their explicit entities; omission does not delete.
  // Exercise the real public entity retirement command along its original ID.
  await open(h, app, entity, 'del');
  await page.getByRole('button', { name: '删除数据实体', exact: true }).click();
  let deleted;
  await observeAuthorSave(h, app, entityRoute + entity.id,
    () => page.getByRole('button', { name: '确认删除', exact: true }).click(), async () => {
      deleted = await a.draft(h, app);
      h.check('Independent owner confirms original entity was removed from exact definition', deleted.applicationId === app.id && deleted.entities.length === 0 && deleted.definitionVersion > populated.definitionVersion, deleted);
      const absent = await h.api(h.admin, 'GET', entityRoute + entity.id);
      h.check('Independent entity owner confirms exact original ID absent', absent.data?.error?.code === 2 && absent.data.value == null, absent);
    }, undefined, 'DELETE');
  await open(h, app); await settle(page);
  const removed = await emptyDirectory(h, page);
  h.check('After deleting original entity, tree and current details contain no stale entity', await treeNode(page, entity.showName).count() === 0 && await card(page, '字段信息').count() === 0 && removed.valid, removed.proof);
  const errors = [], listen = e => errors.push(e.message); page.on('pageerror', listen);
  try {
    await page.goto(h.admin.origin + view(app, entity), { waitUntil: 'networkidle' }); await settle(page);
    h.check('Returning to original deleted entity never restores stale field content', await page.locator('tr[data-row-key="name"]').count() === 0 && errors.length === 0, errors);
    h.check('Independent owner confirms original selection is absent', same(await a.draft(h, app), deleted));
    await screen(h, 'deleted-selection');
  } finally { page.off('pageerror', listen); }
};

handlers['F012-003'] = async h => {
  const app = await a.definition(h, 'entitylayout'), entity = a.newEntity(h, app), page = h.admin.page;
  entity.showName = '长名称实体'.repeat(14); entity.description = '可完整查看的字段功能块与下级实体内容'.repeat(8);
  entity.fields.find(f => f.name === 'name').showName = '长名称字段'.repeat(12);
  await a.library(h, app); entity.blockInfo = [await a.scriptBinding(h)];
  const model = await a.save(h, app, await a.draft(h, app), [entity]);
  const errors = [], listen = e => errors.push(e.message); page.on('pageerror', listen);
  try {
    for (const width of [390, 1366, 1920]) {
      await page.setViewportSize({ width, height: 900 }); await open(h, app);
      const list = card(page, '实体列表'), row = list.locator('tr[data-row-key="' + model.entities[0].id + '"]');
      h.check('Entity list retains full long title at width ' + width, (await row.innerText()).includes(entity.showName));
      await treeNode(page, entity.showName).click(); await card(page, '字段信息').waitFor({ state: 'visible' }); await settle(page);
      for (const title of ['字段信息', '功能块信息', '服务开放能力']) h.check(title + ' remains readable at width ' + width, await card(page, title).isVisible());
      h.check('Long field content is available without truncating owner value', (await card(page, '字段信息').locator('tr[data-row-key="name"]').innerText()).includes(entity.fields.find(f => f.name === 'name').showName));
      const button = page.getByRole('button', { name: /编辑实体$/ });
      await button.scrollIntoViewIfNeeded();
      const geometry = await button.evaluate(e => { const r = e.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2; return { left: r.left, right: r.right, viewport: innerWidth, clickable: e.contains(document.elementFromPoint(x, y)) }; });
      h.check('Entity edit action is inside viewport and not covered at width ' + width, geometry.left >= 0 && geometry.right <= geometry.viewport && geometry.clickable, geometry);
      await screen(h, 'entity-width-' + width);
    }
    h.check('Responsive entity reads have no browser exceptions or owner mutation', errors.length === 0 && same(await a.draft(h, app), model), errors);
  } finally { page.off('pageerror', listen); await page.setViewportSize({ width: 1366, height: 768 }); }
};

handlers['F016-002'] = async h => {
  const app = await a.definition(h, 'librarycancel'), page = h.admin.page;
  const content = await a.library(h, app), entity = a.newEntity(h, app); entity.blockInfo = [await a.scriptBinding(h)];
  const model = await a.save(h, app, await a.draft(h, app), [entity]), route = base + app.id + '/function-blocks';
  const library = (await h.ok(h.admin, 'GET', route)).value;
  const removal = a.journalSave(h, app, route, { expectedDefinitionVersion: library.definitionVersion, content: { schemaVersion: content.schemaVersion, definitions: [], files: {} } });
  const rejected = await h.api(h.admin, 'PUT', route, removal.payload);
  removal.response = rejected; h.persist();
  h.check('Public library owner refuses removal of actually bound script', rejected.data?.error?.code === 4 && /引用无效|不存在/.test(rejected.data.error.message), rejected);
  h.check('Refused library deletion leaves exact original library and binding intact', same((await h.ok(h.admin, 'GET', route)).value, library) && same(await a.draft(h, app), model));
  removal.confirmed = true; h.persist();
  await open(h, app); await page.getByRole('tab', { name: '自定义脚本', exact: true }).click();
  const referenced = page.locator('tr[data-row-key="display"]');
  h.check('Actual author UI disables deleting referenced program', await referenced.getByRole('button', { name: '删除', exact: true }).isDisabled());
  await page.getByRole('button', { name: '添加自定义功能块', exact: true }).click();
  await page.getByLabel('功能名称', { exact: true }).fill('不能保存的脚本草稿');
  await page.getByRole('button', { name: '取消脚本编辑', exact: true }).click();
  h.check('Cancelling real script editor creates no program or binding', same((await h.ok(h.admin, 'GET', route)).value, library) && same(await a.draft(h, app), model));
  await open(h, app, model.entities[0], 'edit');
  await page.getByLabel('显示名', { exact: true }).fill('放弃实体草稿');
  await page.goBack({ waitUntil: 'networkidle' });
  h.check('Cancelling entity draft retains separately saved library and original entity', same((await h.ok(h.admin, 'GET', route)).value, library) && same(await a.draft(h, app), model));
  await screen(h, 'library-cancel');
};

// Failures retain real UI evidence without converting locator/network errors
// into product assertions or discarding the original journal.
for (const [id, handler] of Object.entries(handlers)) handlers[id] = async h => {
  try { await handler(h); }
  catch (error) { try { await screen(h, 'author-ui-error'); } catch {} throw error; }
};
// UI producers still use the original intercepted browser request; independent
// owner reads and API setup select the public one-shot transport in advance.
for (const handler of Object.values(handlers)) handler.transport = 'owner-api';
// A readback/locator error can interrupt confirmation after a known successful
// DELETE. Reconcile that exact acknowledged operation; never send DELETE again.
async function reconcileAuthorDeletion(h, resource) {
  const intent = resource.pendingAuthoringSave, response = intent?.response;
  const entity = response?.data?.value;
  if (resource.collection !== base || !resource.creation?.ownershipConfirmed ||
      !same(h.admin.identity, resource.creation.actorIdentity) || h.admin.origin !== resource.creation.origin ||
      intent?.method !== 'DELETE' || intent.confirmed || !response || !h.good(response) ||
      !Number.isSafeInteger(entity?.id) || entity.id <= 0 || intent.route !== entityRoute + entity.id ||
      entity.application?.id !== resource.id || entity.application.uuid !== resource.creation.response?.data?.value?.uuid) {
    throw new h.Blocked('Author deletion recovery requires the original actor, acknowledged exact entity DELETE and parent identity');
  }
  const app = (await h.ok(h.admin, 'GET', base + resource.id)).value;
  h.check('Recovery reads the exact original parent definition', app.id === resource.id && app.uuid === entity.application.uuid, app);
  const model = await a.draft(h, app);
  h.check('Recovery confirms original entity absent from the original complete model', model.applicationId === app.id && model.applicationUuid === app.uuid && Array.isArray(model.entities) && !model.entities.some(e => e.id === entity.id || e.pkgPath === entity.pkgPath && e.name === entity.name), model);
  const absent = await h.api(h.admin, 'GET', intent.route);
  h.check('Recovery independently confirms original entity ID absent', [200, 404].includes(absent.status) && absent.data?.error?.code === 2 && absent.data.value == null, absent);
  intent.reconciliation = { proof: 'Original acknowledged DELETE plus independent original parent/model/entity reads; no entity DELETE replay', entityId: entity.id, applicationId: app.id, definitionVersion: model.definitionVersion };
  intent.confirmed = true; h.persist();
  return intent.reconciliation;
}
module.exports = { handlers, observeAuthorSave, reconcileAuthorDeletion };
