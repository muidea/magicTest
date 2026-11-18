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
  // Attach image background + screen canvas so F068-001 verifies image backgrounds, failure fallback and screen canvas cleanly.
  const png = await browser.screenshot({ clip: { x: 0, y: 0, width: 2, height: 2 }, animations: 'disabled' });
  const mBefore = await author.read(h, authored.app, 'package-members'), mNext = structuredClone(mBefore.content);
  mNext.assets ||= { schemaVersion: 'magic.application-assets/v1', files: [] };
  const imgDigest = 'sha256:' + require('node:crypto').createHash('sha256').update(png).digest('hex');
  authored.screenAsset = { key: 'appearance-bg', path: 'assets/appearance-bg.png', purpose: 'page-image', mime: 'image/png', size: png.length, digest: imgDigest };
  mNext.files[authored.screenAsset.path] = png.toString('base64');
  mNext.assets.files.push(authored.screenAsset);
  await author.save(h, authored.app, 'package-members', mBefore, mNext);
  const pBefore = await author.read(h, authored.app, 'pages'), pNext = structuredClone(pBefore.content);
  const screenPage = { key: 'appearance-screen', title: '外观大屏', routes: ['/appearance-screen'], navigation: true,
    layout: { type: 'screen', columns: 12, gap: 0, width: 1280, height: 720, scaleMode: 'proportional-fit', theme: 'dark', narrowMode: 'flow' },
    routeParameters: [], appearance: { background: { color: '#eeeeee', image: { mode: 'asset', assetKey: 'appearance-bg', size: 'contain', position: 'center', repeat: 'no-repeat' } } },
    components: [{ key: 'screen-text', type: 'text', layout: { span: 12, order: 1 }, dataSources: [], properties: { text: 'appearance-screen' } }] };
  pNext.pages.push(screenPage); pNext.navigation.push(screenPage.key);
  authored.pages = await author.save(h, authored.app, 'pages', pBefore, pNext);
  authored.model = await require('./authoring_cases.cjs').authoring.draft(h, authored.app);
}
async function appearance(h) {
  let screenAsset;
  const f = await page.explicitFixture(h, undefined, undefined, { suffix: 'appearance', requestPrefix: 'appearance-',
    prepareAuthor: async (h2, authored) => { await prepare(h2, authored); screenAsset = authored.screenAsset; },
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
    // Verify screen canvas + asset image background + controlled GET failure fallback on installation 0.
    const ctx0 = await business.runtime(h, f, 0, actor);
    await actor.page.setViewportSize({ width: 1440, height: 1000 });
    await actor.page.goto(actor.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?' + new URLSearchParams({ source: 'portal', deploymentId: ctx0.identity.deploymentId, pageKey: 'appearance-screen' }), { waitUntil: 'networkidle' });
    const stage = actor.page.locator('.application-page-screen-stage');
    await stage.waitFor();
    await actor.page.waitForFunction(el => /^url\("blob:/.test(getComputedStyle(el).backgroundImage), await stage.elementHandle(), { timeout: 30000 });
    const darkColor = await actor.page.locator('.application-page-screen-dark').evaluate(n => getComputedStyle(n).color);
    h.check('Appearance screen canvas renders dark theme and background blob cleanly', darkColor === 'rgb(230, 237, 247)', { darkColor });
    const failMatch = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/apps/application/assets/' + screenAsset.key && url.searchParams.get('deploymentId') === ctx0.identity.deploymentId;
    let failCount = 0;
    await actor.page.route(failMatch, async r => { failCount++; await r.fulfill({ status: 503, contentType: 'text/plain', body: 'controlled appearance image unavailable' }); });
    try {
      await actor.page.goto(actor.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?' + new URLSearchParams({ source: 'portal', deploymentId: ctx0.identity.deploymentId, pageKey: 'appearance-screen' }), { waitUntil: 'networkidle' });
      await actor.page.locator('.application-page-image-feedback[role="alert"]').waitFor({ timeout: 30000 });
      const bgAfterFail = await stage.evaluate(n => getComputedStyle(n).backgroundImage);
      h.check('Appearance image GET failure falls back cleanly and reports alert', failCount > 0 && bgAfterFail === 'none', { failCount, bgAfterFail });
    } finally { await actor.page.unroute(failMatch); }
    const current = await author.read(h, f.application, 'pages'), changed = structuredClone(current.content);
    changed.pages.find(p => p.key === 'home').presentationDefaults.background.color = '#ffffff';
    await author.save(h, f.application, 'pages', current, changed);
    for (const installation of f.installations) {
      const value = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + installation.deploymentId)).value;
      h.check('Unpublished appearance edit cannot change either original installation', same(value.pages, f.revision.content.pages));
    }
  } catch (error) { primary = error; throw error; }
  finally { await page.disposeExplicitFixture(h, f, primary); }
}
appearance.transport = 'owner-api';
appearance.requiresOnlyDeliveryFixture = true;
module.exports = { handlers: { 'F068-001': appearance }, observedAppearanceMatches };
