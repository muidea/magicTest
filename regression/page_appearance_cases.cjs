// Inspect the real shared renderer; never inject computed styles or defaults.
const { isDeepStrictEqual: same } = require('node:util');
const page = require('./page_runtime_cases.cjs');
const { authorFixture: author } = require('./page_author_cases.cjs');
const business = require('./business_cases.cjs');
const delivery = require('./model_delivery.cjs');
const { packageContent } = require('./owner_transport.cjs');
const frames = [
  { key: 'appearance-inherit', color: 'rgb(17, 34, 51)', border: '12px' },
  { key: 'appearance-clear', color: 'rgba(0, 0, 0, 0)', border: '0px' },
  { key: 'appearance-alpha', color: 'rgba(68, 85, 102, 0.5)', border: '12px' },
];
function observedAppearanceMatches(value) {
  return value?.background === 'rgb(238, 238, 238)' && Array.isArray(value.frames) && value.frames.length === frames.length &&
    frames.every((f, i) => same(value.frames[i], { ...f, text: f.key })) && value.visible === true;
}
async function inspect(h, scope, label) {
  const surface = scope.locator('.application-page-surface');
  await surface.waitFor();
  h.check('Appearance scope has exactly one original canvas', await surface.count() === 1);
  const result = await surface.evaluate((node, keys) => ({
    background: getComputedStyle(node).backgroundColor,
    visible: node.getBoundingClientRect().width > 0,
    frames: keys.map(key => {
      const matches = node.querySelectorAll('[data-page-frame="' + key + '"]');
      if (matches.length !== 1) return { key, count: matches.length };
      const frame = matches[0], style = getComputedStyle(frame);
      return { key, color: style.backgroundColor, border: style.borderTopWidth, text: frame.textContent.trim() };
    }),
  }), frames.map(f => f.key));
  h.check('Real ' + label + ' canvas and component inheritance preserve exact colors, boundary borders and text', observedAppearanceMatches(result), result);
  return result;
}
async function prepare(h, authored) {
  const before = authored.pages, content = structuredClone(before.content), home = content.pages.find(p => p.key === 'home');
  home.appearance = { background: { color: '#eeeeee' } };
  home.presentationDefaults = { background: { color: '#112233' }, borderWidth: 12 };
  home.components.push(...frames.map((f, i) => ({ key: f.key, type: 'text', layout: { span: 12, order: 10 + i }, dataSources: [], properties: { text: f.key },
    ...(i ? { presentation: { frame: { background: { color: i === 1 ? 'transparent' : '#44556680' }, borderWidth: i === 1 ? 0 : 12 } } } : {}) })));
  let saved = await author.save(h, authored.app, 'pages', before, content);
  const inherited = structuredClone(saved.content);
  delete inherited.pages.find(p => p.key === 'home').components.find(c => c.key === 'appearance-clear').presentation;
  saved = await author.save(h, authored.app, 'pages', saved, inherited);
  h.check('Clearing component override leaves it omitted, preserves every other authored property and retains page defaults',
    same(saved.content, inherited) && !Object.hasOwn(saved.content.pages.find(p => p.key === 'home').components.find(c => c.key === 'appearance-clear'), 'presentation'));
  authored.pages = await author.save(h, authored.app, 'pages', saved, content);
  const browser = h.admin.page;
  await browser.setViewportSize({ width: 1440, height: 1000 });
  await browser.goto(h.admin.origin + '/panel/application/definition/view?aid=' + authored.app.id, { waitUntil: 'networkidle' });
  await browser.getByRole('tab', { name: '页面设计', exact: true }).click();
  await browser.locator('tr[data-row-key="home"]').getByRole('button', { name: /设计$/ }).click();
  const dialog = browser.getByRole('dialog'); await dialog.waitFor();
  const colorInput = dialog.getByLabel('页面背景背景色', { exact: true });
  h.check('Actual appearance control reads the exact saved original page color', await colorInput.inputValue() === '#eeeeee');
  await colorInput.fill('');
  h.check('Clearing actual local appearance field never writes an unsaved default to owner', await colorInput.inputValue() === '' && same(await author.read(h, authored.app, 'pages'), authored.pages));
  for (const color of ['#ededed', '#eeeeee']) {
    const beforeUI = authored.pages, expected = structuredClone(beforeUI.content);
    expected.pages.find(p => p.key === 'home').appearance.background.color = color;
    await colorInput.fill(color);
    await require('./definition_browser_cases.cjs').observeAuthorSave(h, authored.app, '/panel/application/definitions/' + authored.app.id + '/pages',
      () => dialog.getByRole('button', { name: '保存页面', exact: true }).click(), async intent => {
        const current = await author.read(h, authored.app, 'pages');
        h.check('Actual appearance field conditional save preserves complete original page contract', intent.payload.expectedDefinitionVersion === beforeUI.definitionVersion && same(intent.payload.content, expected) &&
          same(current.content, expected) && current.definitionVersion > beforeUI.definitionVersion && current.definitionVersion === intent.response.data.value.definitionVersion, current);
        authored.pages = current;
      });
    await dialog.getByText('已与保存草稿同步', { exact: true }).waitFor();
    h.check('Actual appearance input reflects its independently confirmed saved value', await colorInput.inputValue() === color);
  }
  for (const viewport of ['desktop', 'tablet', 'mobile']) {
    await dialog.getByLabel('预览视口', { exact: true }).selectOption(viewport);
    await inspect(h, dialog, 'author-' + viewport);
    await h.screenshot(h.admin, 'appearance-author-' + viewport);
  }
  h.check('Rendering the author previews never writes computed defaults back to owner', same(await author.read(h, authored.app, 'pages'), authored.pages));
  await dialog.getByRole('button', { name: '关闭页面设计器', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
}
async function appearance(h) {
  const f = await page.explicitFixture(h, undefined, undefined, { suffix: 'appearance', requestPrefix: 'appearance-', prepareAuthor: prepare,
    prepareDelivery: async (h, f) => {
      const zip = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
      h.check('Appearance roundtrip downloads the real original immutable ZIP', zip.status === 200 && Buffer.isBuffer(zip.data.bytes));
      await delivery.importExact(h, f, zip.data.bytes);
    } });
  let primary;
  try {
    const actor = await business.member(h, 'manager');
    for (let i = 0; i < f.installations.length; i++) {
      const context = await business.runtime(h, f, i, actor);
      const read = async () => (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
      const frozen = await read();
      h.check('Ordinary original installation reads the complete exact frozen appearance contract', same(frozen.readIdentity, context.identity) && same(frozen.pages, f.revision.content.pages));
      for (const width of [1440, 768, 390]) {
        await actor.page.setViewportSize({ width, height: 1000 });
        await actor.page.goto(actor.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?source=portal&deploymentId=' + context.identity.deploymentId, { waitUntil: 'networkidle' });
        await actor.page.locator('[data-page-frame="appearance-alpha"]').waitFor();
        await inspect(h, actor.page, 'installed-' + i + '-' + width);
        await h.screenshot(actor, 'appearance-installed-' + i + '-' + width);
      }
      h.check('Three real renderer widths preserve the entire original owner projection', same(await read(), frozen));
    }
    const current = await author.read(h, f.application, 'pages'), changed = structuredClone(current.content);
    changed.pages.find(p => p.key === 'home').presentationDefaults.background.color = '#ffffff';
    await author.save(h, f.application, 'pages', current, changed);
    for (const installation of f.installations) {
      const value = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + installation.deploymentId)).value;
      h.check('Unpublished appearance edit cannot change either original installation', same(value.pages, f.revision.content.pages));
    }
  } catch (error) { primary = error; throw error; }
  finally { await page.disposeExplicitFixture(h, f, primary); }
  await h.partial('Scalar appearance inheritance/clear/restore, actual background field local clear/conditional save/restore, transparent/six/eight-digit colors,0/12px borders, three author previews, real ZIP import, dual ordinary installations at three widths and unpublished isolation verified. Image backgrounds/failure fallback and screen canvas remain unverified in this scalar executor.');
}
appearance.transport = 'owner-api';
appearance.requiresOnlyDeliveryFixture = true;
module.exports = { handlers: { 'F068-001': appearance }, observedAppearanceMatches };
