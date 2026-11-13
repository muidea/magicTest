// Read real immutable package images through the original ordinary session.
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const page = require('./page_runtime_cases.cjs');
const { authorFixture: author } = require('./page_author_cases.cjs');
const business = require('./business_cases.cjs');
const delivery = require('./model_delivery.cjs');
const { packageContent } = require('./owner_transport.cjs');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=', 'base64');
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
function assetMatches(value, asset) {
  return value?.status === 200 && value.mime === asset.mime && value.size === asset.size && value.digest === asset.digest &&
    value.cache === 'private, no-store' && value.nosniff === 'nosniff' && value.error == null;
}
function deniedAssetMatches(value, code, message) {
  return !!value && [200, 400, 403, 404, 409].includes(value.status) && value.mime === 'application/json' &&
    value.error?.code === code && value.error.message === message && value.value == null &&
    value.cache === 'private, no-store' && value.nosniff === 'nosniff';
}
// Exact-identity reads compare against the running binding. The runtime
// projection can briefly expose the successor generation while the deployment
// is still settling, so wait for a stable identity before the first exact read.
async function settledRuntime(h, f, index, actor) {
  let previous = await business.runtime(h, f, index, actor);
  for (let attempt = 0; attempt < 20; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    const next = await business.runtime(h, f, index, actor);
    if (same(next.identity, previous.identity)) return next;
    h.observe({ kind: 'runtime-identity-settling', index, before: previous.identity, after: next.identity });
    previous = next;
  }
  throw new h.Blocked('Runtime identity did not settle within the bounded readiness window');
}
async function assetRead(h, actor, context, key, extra = {}) {
  if (!actor.identity || !actor.context || new URL(actor.page.url()).origin !== actor.origin) throw new h.Blocked('Original ordinary image session must be open on its exact origin');
  const identity = structuredClone(actor.identity), origin = actor.origin;
  const route = '/api/v1/web/proxy/apps/application/assets/' + encodeURIComponent(key) + '?' + new URLSearchParams({ application: context.applicationKey, deploymentId: context.identity.deploymentId, ...extra.query });
  const header = Buffer.from(JSON.stringify(extra.identity || context.identity)).toString('base64url');
  const result = await actor.page.evaluate(async ({ route, header }) => {
    const response = await fetch(route, { method: 'GET', credentials: 'same-origin', redirect: 'error', cache: 'no-store', headers: { Accept: 'image/png, image/jpeg', 'X-Magic-Expected-Installation': header } });
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length > 8 * 1024 * 1024) throw Error('Asset exceeds the public finite image budget');
    const mime = response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase();
    const data = mime === 'application/json' ? JSON.parse(new TextDecoder().decode(bytes)) : {};
    return { ...data, status: response.status, mime, size: bytes.length,
      digest: 'sha256:' + Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join(''),
      cache: response.headers.get('Cache-Control'), nosniff: response.headers.get('X-Content-Type-Options') };
  }, { route, header });
  h.check('Image GET retains original browser actor and exact same origin', same(actor.identity, identity) && actor.origin === origin);
  h.observe({ kind: 'installed-image-original-read', actor: identity, identity: extra.identity || context.identity, route, result });
  return result;
}
function archiveMatches(value, application, assets) {
  return value?.crcValid === true && new Set(value.names).size === value.names.length && value.manifest?.apiVersion === 'magic.model-package/v1' &&
    value.manifest.application?.uuid === application.uuid && value.manifest.application.key === application.name &&
    value.manifest.content?.assets === 'assets/index.json' && value.assets?.schemaVersion === 'magic.application-assets/v1' &&
    assets.every(asset => value.assets.files.filter(f => same(f, asset)).length === 1 &&
      value.files.filter(f => f.path === asset.path && f.digest === asset.digest && f.size === asset.size).length === 1 &&
      value.checksums.files.filter(f => f.path === asset.path && f.digest === asset.digest && f.size === asset.size).length === 1);
}
async function prepare(h, authored) {
  // A native Chromium screenshot supplies actual JPEG bytes without a new dependency.
  const imagePage = await h.admin.context.newPage(); let jpeg;
  try { await imagePage.setViewportSize({ width: 2, height: 2 }); await imagePage.goto('about:blank'); jpeg = await imagePage.screenshot({ type: 'jpeg' }); }
  finally { await imagePage.close(); }
  const before = await author.read(h, authored.app, 'package-members'), members = structuredClone(before.content);
  members.assets ||= { schemaVersion: 'magic.application-assets/v1', files: [] };
  const fixtures = [{ key: 'appearance-png', path: 'assets/appearance-png.png', mime: 'image/png', bytes: png, width: 1, height: 1 },
    { key: 'appearance-jpeg', path: 'assets/appearance-jpeg.jpg', mime: 'image/jpeg', bytes: jpeg, width: 2, height: 2 }];
  authored.imageAssets = fixtures.map(({ bytes, width, height, ...f }) => ({ ...f, purpose: 'page-image', size: bytes.length, digest: digest(bytes) }));
  authored.imageDimensions = Object.fromEntries(fixtures.map(f => [f.key, { width: f.width, height: f.height }]));
  for (const f of fixtures) members.files[f.path] = f.bytes.toString('base64');
  members.assets.files.push(...authored.imageAssets);
  await author.save(h, authored.app, 'package-members', before, members);
  const current = await author.read(h, authored.app, 'pages'), content = structuredClone(current.content), home = content.pages.find(p => p.key === 'home');
  home.appearance = { background: { color: '#eeeeee', image: { mode: 'asset', assetKey: 'appearance-png', size: 'contain', position: 'center', repeat: 'no-repeat' } } };
  home.presentationDefaults = { background: { color: '#112233', image: { mode: 'asset', assetKey: 'appearance-jpeg' } }, borderWidth: 12 };
  home.components.push({ key: 'image-inherit', type: 'text', layout: { span: 12, order: 10 }, dataSources: [], properties: { text: 'image-inherit' } },
    { key: 'image-none', type: 'text', layout: { span: 12, order: 11 }, dataSources: [], properties: { text: 'image-none' }, presentation: { frame: { background: { image: { mode: 'none' } } } } });
  const screen = structuredClone(home); screen.key = 'image-screen'; screen.title = '图片大屏'; screen.routes = ['/image-screen'];
  screen.layout = { type: 'screen', columns: 12, gap: 0, width: 1280, height: 720, scaleMode: 'proportional-fit', theme: 'dark', narrowMode: 'flow' };
  screen.components = screen.components.filter(c => ['image-inherit', 'image-none'].includes(c.key));
  content.pages.push(screen); content.navigation.push(screen.key);
  authored.pages = await author.save(h, authored.app, 'pages', current, content);
}
async function decodeBackground(node) {
  const style = getComputedStyle(node), match = /^url\("(blob:[^"]+)"\)$/.exec(style.backgroundImage);
  if (!match) return { image: style.backgroundImage, color: style.backgroundColor };
  const blob = await (await fetch(match[1])).blob(), bytes = await blob.arrayBuffer(), image = new Image();
  image.src = match[1]; await image.decode();
  return { image: 'decoded-blob', color: style.backgroundColor, mime: blob.type, size: bytes.byteLength,
    digest: 'sha256:' + Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join(''),
    width: image.naturalWidth, height: image.naturalHeight, backgroundSize: style.backgroundSize, position: style.backgroundPosition, repeat: style.backgroundRepeat };
}
async function inspect(h, scope, assets, dimensions, screen, label) {
  const canvas = scope.locator(screen ? '.application-page-screen-stage' : '.application-page-surface');
  const inherited = scope.locator('[data-page-frame="image-inherit"]'), cleared = scope.locator('[data-page-frame="image-none"]');
  for (const node of [canvas, inherited, cleared]) { await node.waitFor(); h.check('One exact original image consumer exists: ' + label, await node.count() === 1); }
  await canvas.page().waitForFunction(() => [...document.querySelectorAll('.application-page-image-feedback[role="status"]')].every(n => n.getClientRects().length === 0));
  // Feedback visibility is not a reliable readiness signal when a frame clips
  // its status element. Wait for each expected background blob explicitly, so a
  // still-loading image cannot be decoded as "none".
  for (const node of [canvas, inherited]) {
    await node.page().waitForFunction(
      (el) => /^url\("blob:/.test(getComputedStyle(el).backgroundImage),
      await node.elementHandle(),
      { timeout: 30000 },
    );
  }
  for (const [node, key, color] of [[canvas, 'appearance-png', 'rgb(238, 238, 238)'], [inherited, 'appearance-jpeg', 'rgb(17, 34, 51)']]) {
    const observed = await node.evaluate(decodeBackground), asset = assets.find(a => a.key === key);
    h.check('Real ' + label + ' background decodes exact frozen ' + key + ' bytes', observed.image === 'decoded-blob' && observed.mime === asset.mime && observed.size === asset.size && observed.digest === asset.digest && observed.color === color && observed.width === dimensions[key].width && observed.height === dimensions[key].height, observed);
    h.check('Real ' + label + ' image placement preserves declared/default semantics', observed.backgroundSize === (key === 'appearance-png' ? 'contain' : 'cover') && observed.position === '50% 50%' && observed.repeat === 'no-repeat', observed);
  }
  const none = await cleared.evaluate(decodeBackground);
  h.check('Explicit none suppresses only inherited image while retaining page default color and border', same(none, { image: 'none', color: 'rgb(17, 34, 51)' }) && await cleared.evaluate(n => getComputedStyle(n).borderTopWidth) === '12px', none);
  if (screen) {
    h.check('Screen shell keeps image on the original stage and dark theme text', await scope.locator('.application-page-surface').evaluate(n => getComputedStyle(n).backgroundImage) === 'none' && await scope.locator('.application-page-screen-dark').evaluate(n => getComputedStyle(n).color) === 'rgb(230, 237, 247)');
  }
}
async function installedImages(h) {
  let assets, dimensions;
  const f = await page.explicitFixture(h, undefined, undefined, { suffix: 'frozenimages', requestPrefix: 'frozen-images-', prepareAuthor: async (h, authored) => {
    await prepare(h, authored); assets = authored.imageAssets; dimensions = authored.imageDimensions;
  }, prepareDelivery: async (h, f) => {
    const zip = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
    h.check('Frozen image roundtrip downloads actual original immutable ZIP', zip.status === 200 && Buffer.isBuffer(zip.data.bytes));
    const code = 'import io,sys,zipfile,json,hashlib\nz=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))\nnames=z.namelist()\nprint(json.dumps({"crcValid":z.testzip() is None,"names":names,"manifest":json.loads(z.read("package.json")),"assets":json.loads(z.read("assets/index.json")),"checksums":json.loads(z.read("checksums.json")),"files":[{"path":p,"size":len(z.read(p)),"digest":"sha256:"+hashlib.sha256(z.read(p)).hexdigest()} for p in names if p in ["assets/appearance-png.png","assets/appearance-jpeg.jpg"]]}))';
    const archive = JSON.parse(execFileSync('python3', ['-B', '-c', code], { input: zip.data.bytes, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }));
    h.check('Original ZIP CRC, exact application, indexed PNG/JPEG bytes and independent checksums all agree', archiveMatches(archive, f.application, assets), archive);
    await delivery.importExact(h, f, zip.data.bytes);
  } });
  let primary;
  try {
    const actor = await business.member(h, 'manager'), contexts = [];
    await actor.page.goto(actor.origin + '/portal/', { waitUntil: 'networkidle' });
    for (let i = 0; i < f.installations.length; i++) {
      const context = await settledRuntime(h, f, i, actor); contexts.push(context);
      const frozen = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
      h.check('Complete ordinary runtime freezes original pages and exact installation identity', same(frozen.pages, f.revision.content.pages) && same(frozen.readIdentity, context.identity));
      for (const asset of assets) h.check('Ordinary original exact installation returns immutable image with private/no-store and nosniff', assetMatches(await assetRead(h, actor, context, asset.key), asset));

    }
    const context = contexts[0];
    for (const [field, changed] of [['installationId', contexts[1].identity.installationId], ['runtimeApplicationUuid', contexts[1].identity.runtimeApplicationUuid], ['artifactDigest', 'sha256:' + '0'.repeat(64)], ['generation', context.identity.generation + 1], ['executionEpoch', context.identity.executionEpoch + 1]]) {
      const response = await assetRead(h, actor, context, assets[0].key, { identity: { ...context.identity, [field]: changed } });
      h.check('Validly encoded forged ' + field + ' reaches exact installation mismatch without image bytes', deniedAssetMatches(response, 19, '精确安装读取身份已变化'), response);
    }
    const missing = await assetRead(h, actor, context, 'missing-original-image');
    h.check('Unknown resource key reaches installed resource owner and returns exact NotFound JSON', deniedAssetMatches(missing, 2, '安装资源 key 不存在'), missing);
    for (const field of ['owner', 'consumer', 'fileRef']) {
      const response = await assetRead(h, actor, context, assets[0].key, { query: { [field]: 'not-an-installed-resource' } });
      h.check('Public installed asset rejects forbidden ' + field + ' selector without image bytes', deniedAssetMatches(response, 4, '安装资源查询包含不允许的参数'), response);
    }
    const before = await author.read(h, f.application, 'package-members'), changed = structuredClone(before.content);
    const replacement = assets[0];
    // A valid larger PNG with an ancillary chunk changes bytes, not the asset key.
    const { sizedPNG } = require('./page_validation_cases.cjs');
    const nextPNG = sizedPNG(png, png.length + 64);
    changed.files[replacement.path] = nextPNG.toString('base64');
    Object.assign(changed.assets.files.find(a => a.key === replacement.key), { size: nextPNG.length, digest: digest(nextPNG) });
    await author.save(h, f.application, 'package-members', before, changed);
    for (const c of contexts) for (const asset of assets) h.check('Unpublished same-key image replacement cannot alter either original installation', assetMatches(await assetRead(h, actor, c, asset.key), asset));
    await delivery.removePackage(h, f);
    for (const [index, c] of contexts.entries()) {
      const current = await business.runtime(h, f, index, actor);
      h.observe({ kind: 'runtime-identity-after-source-removal', index, before: c.identity, after: current.identity });
    }
    for (const [index, c] of contexts.entries()) for (const asset of assets) {
      const value = await assetRead(h, actor, c, asset.key);
      if (!assetMatches(value, asset)) {
        const current = await business.runtime(h, f, index, actor);
        h.observe({ kind: 'runtime-identity-at-failed-read', index, key: asset.key, before: c.identity, after: current.identity, result: value });
      }
      h.check('Formal source ZIP removal preserves exact original installed image bytes', assetMatches(value, asset));
    }
    let rendererError;
    for (const [i, context] of contexts.entries()) {
      for (const width of [1440, 768, 390]) for (const pageKey of ['home', 'image-screen']) {
        await actor.page.setViewportSize({ width, height: 1000 });
        const responses = [], listener = response => {
          const url = new URL(response.url());
          if (url.origin === actor.origin && /^\/api\/v1\/web\/proxy\/apps\/application\/(assets|asset\/query)\//.test(url.pathname)) responses.push({ method: response.request().method(), path: url.pathname, status: response.status(), mime: response.headers()['content-type'] });
        };
        actor.page.on('response', listener);
        try { await actor.page.goto(actor.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?' + new URLSearchParams({ source: 'portal', deploymentId: context.identity.deploymentId, pageKey }), { waitUntil: 'networkidle' }); }
        finally { actor.page.off('response', listener); h.observe({ kind: 'actual-installed-image-network', identity: context.identity, pageKey, width, responses }); }
        try { await inspect(h, actor.page, assets, dimensions, pageKey === 'image-screen', i + '-' + pageKey + '-' + width); }
        catch (error) { rendererError ||= error; h.observe({ kind: 'real-installed-image-consumer-failure', installation: context.identity, pageKey, width, message: error.message }); }
        await h.screenshot(actor, 'frozen-images-' + i + '-' + pageKey + '-' + width);
      }
    }
    if (!rendererError) {
    const failureMatch = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/apps/application/assets/' + assets[0].key && url.searchParams.get('deploymentId') === context.identity.deploymentId;
    let reads = 0;
    await actor.page.route(failureMatch, async route => { h.check('Only a read-only original image GET is fault controlled', route.request().method() === 'GET'); reads++; await route.fulfill({ status: 503, contentType: 'text/plain', body: 'controlled image unavailable' }); });
    try {
      await actor.page.goto(actor.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?' + new URLSearchParams({ source: 'portal', deploymentId: context.identity.deploymentId, pageKey: 'home' }), { waitUntil: 'networkidle' });
      await actor.page.locator('.application-page-surface > .application-page-image-feedback[role="alert"]').waitFor();
      const observed = await actor.page.locator('.application-page-surface').evaluate(decodeBackground);
      h.check('Actual image read failure preserves original fallback color, removes background image and reports failure', reads > 0 && same(observed, { image: 'none', color: 'rgb(238, 238, 238)' }));
      await h.screenshot(actor, 'frozen-images-controlled-read-fallback');
    } finally { await actor.page.unroute(failureMatch); }
    await actor.page.reload({ waitUntil: 'networkidle' });
    await inspect(h, actor.page, assets, dimensions, false, 'after-failure-restored');

    } else h.observe({ kind: 'controlled-image-failure-not-executed', reason: 'Natural original renderer failure must be resolved before injected failure/recovery can be proved' });
    await require('./application_authority_cases.cjs').retireAccess(h, f.pageGrants[0]);
    const denied = await assetRead(h, actor, context, assets[0].key);
    h.check('Original ordinary session loses image access after exact original grant retirement', deniedAssetMatches(denied, 5, '读取安装资源需要实例运行权限'), denied);
    for (const asset of assets) h.check('Retiring one installation never revokes peer image access in the same original session', assetMatches(await assetRead(h, actor, contexts[1], asset.key), asset));
    if (rendererError) throw rendererError;
  } catch (error) { primary = error; throw error; }
  finally { await page.disposeExplicitFixture(h, f, primary); }
  await h.partial('Exact immutable ZIP PNG/JPEG bytes/import, ordinary dual-installation three-width normal/screen rendering, inherited/none images, wrong identity/key/forbidden selectors, unpublished replacement/source removal, actual image GET failure fallback and formal one-instance retirement verified. Cross-tenant fixtures, session switching and controlled late old responses remain unverified.');
}
installedImages.transport = 'owner-api';
installedImages.requiresOnlyDeliveryFixture = true;
module.exports = { handlers: { 'F068-004': installedImages }, assetRead, assetMatches, deniedAssetMatches, archiveMatches };
