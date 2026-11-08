// Category names are independent strings in application/service definitions.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const collection = '/panel/infra/catalogs/';
async function categoryNames(h) {
  const label = h.state.prefix + '-category';
  const parent = await h.createAs('tenantAdmin', collection, { name: label, description: '原分类', parent: null }, 'catalog');
  const child = await h.createAs('tenantAdmin', collection, { name: label + '-child', description: '原子分类', parent: { id: parent.id, name: label } }, 'catalog');
  const peer = await h.createAs('tenantAdmin', collection, { name: label + '-peer', description: '同名规则验证', parent: null }, 'catalog');
  await h.ok(h.tenantAdmin, 'PUT', collection + peer.id, { name: label, description: peer.description, parent: null });
  const rows = await h.directory(h.tenantAdmin, collection);
  h.check('Two independent IDs may have the same category display name', rows.filter(r => r.name === label).length === 2 && rows.some(r => r.id === parent.id) && rows.some(r => r.id === peer.id), rows);
  const currentChild = (await h.ok(h.tenantAdmin, 'GET', collection + child.id)).value;
  h.check('Hierarchy retains exact parent identity and name', currentChild.parent?.id === parent.id && currentChild.parent.name === label && currentChild.name === child.name, currentChild);
  const foreign = await h.createAs('otherTenantAdmin', collection, { name: label, description: '独立其他租户目录', parent: null }, 'catalog');
  const foreignBefore = (await h.ok(h.otherTenantAdmin, 'GET', collection + foreign.id)).value;
  for (const [actor, expected, excluded] of [[h.tenantAdmin, [parent.id, child.id, peer.id], [foreign.id]], [h.otherTenantAdmin, [foreign.id], [parent.id, child.id, peer.id]], [h.admin, [], [parent.id, child.id, peer.id, foreign.id]]]) {
    const directory = await h.directory(actor, collection);
    h.check('Category selection only includes current tenant owner records', expected.every(id => directory.some(r => r.id === id)) && excluded.every(id => !directory.some(r => r.id === id)), { identity: actor.identity, expected, excluded, ids: directory.map(r => r.id) });
  }
  const body = JSON.parse(h.fs.readFileSync(h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression/fixture-definition-create-request.json')));
  Object.assign(body, { uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-catalog-app', pkgPrefix: h.state.prefix + 'catalog', catalog: label });
  const application = await h.createAs('tenantAdmin', '/panel/application/definitions/', body, 'definition');
  const address = 'https://regression.invalid/catalog';
  const options = JSON.stringify({ debug: { authMode: 'bearer', operations: [{ key: 'probe', name: 'probe', method: 'GET', pathTemplate: address + '/probe', parameters: [] }] } });
  const service = await h.createAs('tenantAdmin', '/panel/hub/services/', { key: h.state.prefix + '_catalog', name: h.state.prefix + '_catalog', showName: '分类名称回归', description: '不调用上游', catalog: label, providerType: 'external', providerKey: '', status: 2, accessMode: 'gateway', address, options }, 'service');
  const readReferences = async () => {
    const app = (await h.ok(h.tenantAdmin, 'GET', '/panel/application/definitions/' + application.id)).value;
    const svc = (await h.ok(h.tenantAdmin, 'GET', '/panel/hub/services/' + service.id)).value;
    h.check('Original application and service retain independent category name strings', app.id === application.id && svc.id === service.id && app.catalog === label && svc.catalog === label, { application: app, service: svc });
    const apps = await h.directory(h.tenantAdmin, '/panel/application/definitions/');
    const services = await h.directory(h.tenantAdmin, '/panel/hub/services/');
    h.check('Fresh directories preserve resource identity and original category display text', apps.some(r => r.id === app.id && r.catalog === label) && services.some(r => r.id === svc.id && r.catalog === label));
  };
  await readReferences();
  await h.ok(h.tenantAdmin, 'PUT', collection + parent.id, { name: label + '-renamed', description: '分类改名', parent: null });
  h.check('Category rename retains original directory ID', (await h.ok(h.tenantAdmin, 'GET', collection + parent.id)).value.name === label + '-renamed');
  await readReferences();
  await h.remove(collection, child.id);
  await h.remove(collection, parent.id);
  await h.remove(collection, peer.id);
  h.check('All exact original category IDs are absent from current tenant directory', (await h.directory(h.tenantAdmin, collection)).every(r => ![parent.id, child.id, peer.id].includes(r.id)));
  await readReferences();
  h.check('Deleting local name directory preserves unrelated same-name foreign category', same((await h.ok(h.otherTenantAdmin, 'GET', collection + foreign.id)).value, foreignBefore));
}
categoryNames.actors = ['tenantAdmin', 'otherTenantAdmin'];
async function categoryAndTags(h) {
  const actor = h.tenantAdmin, label = h.state.prefix + '-named-category', renamed = label + '-edited';
  const category = await h.createAs('tenantAdmin', collection, { name: label, description: '分类初始说明', parent: null }, 'catalog');
  const tracked = h.state.resources.find(r => r.collection === collection && r.id === category.id);
  tracked.categoryEdit = { payload: { name: renamed, description: '分类更新说明', parent: null }, outcome: 'unknown' }; h.persist();
  tracked.categoryEdit.response = await h.api(actor, 'PUT', collection + category.id, tracked.categoryEdit.payload); h.persist();
  h.check('Original category edit succeeds once', h.good(tracked.categoryEdit.response), tracked.categoryEdit.response);
  const current = (await h.ok(actor, 'GET', collection + category.id)).value;
  h.check('Independent category owner preserves ID and complete edited name/description', current.id === category.id && current.name === renamed && current.description === tracked.categoryEdit.payload.description && current.parent == null, current);
  tracked.categoryEdit.outcome = 'confirmed'; h.persist();
  const body = JSON.parse(h.fs.readFileSync(h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression/fixture-definition-create-request.json')));
  Object.assign(body, { uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-category-display', showName: h.state.prefix + '分类展示应用', pkgPrefix: h.state.prefix + 'categorydisplay', catalog: renamed });
  const app = await h.createAs('tenantAdmin', '/panel/application/definitions/', body, 'definition');
  const address = 'https://regression.invalid/category-display';
  const service = await h.createAs('tenantAdmin', '/panel/hub/services/', { key: h.state.prefix + '_category_display', name: h.state.prefix + '_category_display', showName: h.state.prefix + '分类展示服务', description: '仅元数据，不调用上游', catalog: renamed, providerType: 'external', providerKey: '', status: 2, accessMode: 'gateway', address,
    options: JSON.stringify({ debug: { authMode: 'bearer', operations: [{ key: 'probe', name: 'probe', method: 'GET', pathTemplate: address + '/probe', parameters: [] }] } }) }, 'service');
  const references = async () => {
    for (const [base, value] of [['/panel/application/definitions/', app], ['/panel/hub/services/', service]]) {
      const read = (await h.ok(actor, 'GET', base + value.id)).value;
      h.check('Original application/service uses the edited category name string', read.id === value.id && read.catalog === renamed && typeof read.catalog === 'string', read);
    }
  };
  await references();
  const page = actor.page;
  await page.goto(actor.origin + '/panel/application/definition/', { waitUntil: 'networkidle' });
  // The definition directory supports list/grid views. Scope to the actual
  // resource row/card rather than accepting a matching category elsewhere.
  const appView = page.locator('tr.ant-table-row, .ant-card').filter({ hasText: app.showName }).last();
  try { await appView.waitFor(); }
  catch (error) { await h.screenshot(actor, 'application-category-unresolved'); throw error; }
  h.check('Real application directory displays its exact configured category name', (await appView.innerText()).includes(renamed));
  await h.screenshot(actor, 'application-category-name');
  await page.goto(actor.origin + '/panel/hub/registry/', { waitUntil: 'networkidle' });
  // Earlier full-suite fixtures can put this exact service beyond page one.
  // Use the real server search before selecting the original resource card.
  await page.getByPlaceholder('搜索服务名称', { exact: true }).fill(service.name);
  await page.keyboard.press('Enter');
  const svcView = page.locator('.ant-list-item').filter({ hasText: service.name });
  try { await svcView.waitFor(); }
  catch (error) { await h.screenshot(actor, 'service-category-unresolved'); throw error; }
  h.check('Service search selects exactly one original named resource', await svcView.count() === 1 && (await svcView.innerText()).includes(service.showName));
  h.check('Real service directory displays its exact configured category name', (await svcView.innerText()).includes(renamed));
  await h.screenshot(actor, 'service-category-name');
  const files = require('./file_cases.cjs'), file = await files.createFile(h, 'tenantAdmin', 'private');
  const tags = ['独立文件标签', renamed + '-file-only'];
  const fileRoute = '/files/' + file.id + '?' + new URLSearchParams({ fileSource: file.source });
  file.tagEdit = { payload: { tags }, outcome: 'unknown' }; h.persist();
  file.tagEdit.response = await h.api(actor, 'PUT', fileRoute, file.tagEdit.payload); h.persist();
  h.check('File owner accepts separate string tags on original private file', h.good(file.tagEdit.response), file.tagEdit.response);
  const tagged = (await h.ok(actor, 'GET', fileRoute)).value;
  h.check('Independent exact ID and token reads preserve the independent tag strings and original file identity', tagged.id === file.id && tagged.token === file.token && tagged.path === file.path && tagged.name === file.name && same(tagged.tags, tags) && same((await h.ok(actor, 'GET', file.view)).value, tagged), tagged);
  file.tagEdit.outcome = 'confirmed'; h.persist();
  h.check('File tag creation does not create or mutate the category directory', same((await h.ok(actor, 'GET', collection + category.id)).value, current) && !(await h.directory(actor, collection)).some(row => tags.includes(row.name)));
  await page.goto(actor.origin + '/panel/infra/file/', { waitUntil: 'networkidle' });
  const parts = file.path.split('/').filter(Boolean); let path = '/static';
  for (const part of parts.slice(1, -1)) {
    path += '/' + part;
    const row = page.locator('tr[data-row-key=' + JSON.stringify('dir-' + path) + ']');
    await row.waitFor(); await row.click();
  }
  const row = page.locator('tr[data-row-key="file-' + file.id + '"]'); await row.waitFor();
  const detailResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/web/proxy/files/' + file.id && r.request().method() === 'GET'); detailResponse.catch(() => {});
  try {
    await row.getByRole('button').filter({ has: page.locator('[aria-label="eye"]') }).click();
    const response = await detailResponse, data = await response.json();
    h.observe({ kind: 'original-file-detail-ui-response', fileID: file.id, status: response.status(), value: data.value, error: data.error });
    await page.waitForLoadState('networkidle');
    await h.screenshot(actor, 'file-detail-after-original-click');
    const context = (await h.ok(actor, 'GET', '/system/context/?surface=panel')).value;
    h.observe({ kind: 'original-file-detail-ui-context', fileID: file.id, areaVisibility: context.areaVisibility, visibleDrawerTitles: await page.locator('.ant-drawer-title').allTextContents(), visibleModalTitles: await page.locator('.ant-modal-title').allTextContents() });
  } catch (error) { await h.screenshot(actor, 'file-detail-ui-unresolved'); throw error; }
  const drawer = page.locator('.ant-drawer-content').filter({ hasText: file.name });
  try { await drawer.waitFor({ timeout: 10000 }); }
  catch (error) { await h.screenshot(actor, 'file-detail-drawer-unresolved'); throw error; }
  await drawer.locator('.ant-descriptions').getByText(file.name, { exact: true }).waitFor();
  const visible = await drawer.innerText(), tagsShown = tags.every(tag => visible.includes(tag));
  h.observe({ kind: 'original-file-tag-presentation', fileID: file.id, categoryID: category.id, tags, fileTagsShown: tagsShown, visibleText: visible });
  await h.screenshot(actor, 'file-independent-tags');
  // Dispose the exact original file and name directory before reporting a
  // missing presentation; keep product failure distinct from cleanup.
  await files.cleanup(h, file);
  await h.remove(collection, category.id);
  h.check('Original category is absent after formal cleanup', !(await h.directory(actor, collection)).some(row => row.id === category.id));
  await references();
  h.check('Actual file detail displays every independently persisted file tag', tagsShown, { fileID: file.id, tags, visible });
}
categoryAndTags.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F051-001': categoryAndTags, 'F051-002': categoryNames } };
