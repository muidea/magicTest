const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const profile = require('./branding_profile.cjs');
const { resetBranding } = require('./branding_cleanup.cjs');
const { brandingAsset } = require('./owner_transport.cjs');
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
async function publicView(h, actor, expected, label, imageDigest) {
  const view = (await h.ok(actor, 'GET', '/api/v1/web/branding/')).value;
  h.check(label + ' public Host resolves original namespace, name and theme', view.namespace === actor.identity.namespace && view.platformName === expected.platformName && view.primaryColor === expected.primaryColor && same(view.brandIcon, expected.brandIcon));
  await actor.page.goto(actor.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
  const title = actor.page.locator('#platform-brand-name');
  await title.waitFor({ state: 'visible' });
  h.check(label + ' actual login name and theme match independent projection', await title.innerText() === expected.platformName && await actor.page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--magic-primary-color').trim()) === expected.primaryColor);
  if (imageDigest) {
    const image = actor.page.getByRole('banner', { name: '平台品牌', exact: true }).getByRole('img');
    await image.evaluate(node => node.decode());
    const actual = await image.evaluate(async node => {
      const url = new URL(node.currentSrc), response = await fetch(url, { cache: 'no-store', credentials: 'omit', redirect: 'error' });
      const bytes = await response.arrayBuffer(), hash = await crypto.subtle.digest('SHA-256', bytes);
      return { origin: url.origin, path: url.pathname, status: response.status, width: node.naturalWidth, height: node.naturalHeight, digest: 'sha256:' + [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('') };
    });
    h.check(label + ' displayed icon decodes actual same-Host owner bytes', actual.origin === actor.origin && actual.path === expected.brandIcon.url && actual.status === 200 && actual.width === 64 && actual.height === 64 && actual.digest === imageDigest, actual);
  }
  await h.screenshot(actor, 'branding-' + label);
  return view;
}
async function png(h) {
  const context = await h.browser.newContext({ viewport: { width: 64, height: 64 }, deviceScaleFactor: 1 });
  try {
    const page = await context.newPage();
    await page.setContent('<style>body{margin:0;background:#5b21b6}div{width:32px;height:32px;background:#f59e0b}</style><div></div>');
    return await page.screenshot({ type: 'png', animations: 'disabled' });
  } finally { await context.close(); }
}
async function inheritance(h) {
  const global = await profile.read(h, h.admin), a = h.tenantAdmin, b = h.otherTenantAdmin;
  const aBefore = await profile.read(h, a), bBefore = await profile.read(h, b);
  h.check('Brand fixture uses both original new tenants without overrides', aBefore.namespace === h.need('tenantA').name && bBefore.namespace === h.need('tenantB').name && aBefore.override == null && bBefore.override == null && global.namespace === h.admin.identity.namespace);
  const restoration = profile.track(h, h.admin, global);
  h.owned(profile.route, { id: '', name: a.identity.namespace }, 'namespace-branding', 'tenantAdmin');
  const tenant = h.state.resources.at(-1); tenant.actorIdentity = structuredClone(a.identity); tenant.origin = a.origin; tenant.brandingCommands = []; h.persist();
  const observers = { global: await h.anonymous(global.namespace), a: await h.anonymous(a.identity.namespace), b: await h.anonymous(b.identity.namespace) };
  try {
    const configured = await profile.write(h, h.admin, restoration, { ...profile.scalars(global), platformName: h.state.prefix + ' 平台品牌', primaryColor: '#047857' });
    const inheritedA = await profile.read(h, a), inheritedB = await profile.read(h, b);
    for (const [name, actor, view] of [['platform', observers.global, configured], ['tenant-a-inherited', observers.a, inheritedA], ['tenant-b-inherited', observers.b, inheritedB]]) {
      h.check(name + ' owner inherits new global scalar values', view.resolved.platformName === configured.resolved.platformName && view.resolved.primaryColor === configured.resolved.primaryColor);
      await publicView(h, actor, view.resolved, name);
    }
    const values = { ...profile.scalars({}), platformName: h.state.prefix + ' 租户独立品牌', platformShortName: '独立租户', primaryColor: '#5b21b6', logoAltText: '回归独立租户图标', expectedResourceId: 0, expectedResourceVersion: 0 };
    const scalarCommand = { method: 'PUT', route: profile.route, body: values, outcome: 'unknown' }; tenant.brandingCommands.push(scalarCommand); h.persist();
    scalarCommand.response = await h.api(a, 'PUT', profile.route, values); h.persist();
    const own = await profile.read(h, a);
    h.check('Exact tenant scalar command persists name, theme and original revision', h.good(scalarCommand.response) && same(scalarCommand.response.data.value, own) && own.namespace === a.identity.namespace && own.override?.id > 0 && own.override.resourceVersion === 1 && own.override.platformName === values.platformName && own.override.primaryColor === values.primaryColor && same(profile.assets(own), profile.assets(aBefore)));
    scalarCommand.outcome = 'confirmed'; h.persist();
    const bytes = await png(h), expectedDigest = digest(bytes), assetRoute = profile.route + 'assets/brand-icon';
    const upload = { method: 'POST', route: assetRoute, name: 'brand-icon.png', bytes: bytes.toString('base64'), expectedDigest, outcome: 'unknown' }; tenant.brandingCommands.push(upload); h.persist();
    upload.response = await brandingAsset(a, assetRoute, { name: upload.name, bytes }, event => h.observe(event)); h.persist();
    const customized = await profile.read(h, a), icon = customized.override?.brandIcon;
    h.check('Dedicated owner acknowledges exact uploaded PNG and independent tenant icon identity', h.good(upload.response) && same(upload.response.data.value, customized) && customized.namespace === a.identity.namespace && customized.override.id === own.override.id && icon?.sourceNamespace === a.identity.namespace && icon.digest === expectedDigest && icon.width === 64 && icon.height === 64 && icon.mediaType === 'image/png' && icon.size === bytes.length && icon.inherited === false && icon.url.startsWith('/api/v1/web/branding/assets/brand-icon/'));
    upload.outcome = 'confirmed'; h.persist();
    await publicView(h, observers.a, customized.resolved, 'tenant-a-override', expectedDigest);
    h.check('Other tenant metadata and platform owner unchanged by tenant override', same(await profile.read(h, b), inheritedB) && same(await profile.read(h, h.admin), configured));
    await publicView(h, observers.b, inheritedB.resolved, 'tenant-b-unaffected');
    await resetBranding(h, a, tenant);
    tenant.phase = 'deleted'; h.persist();
    const reset = await profile.read(h, a);
    h.check('Formal whole-tenant reset clears scalar and asset override and recovers inheritance', reset.override == null && reset.resolved.platformName === configured.resolved.platformName && reset.resolved.primaryColor === configured.resolved.primaryColor);
    await publicView(h, observers.a, reset.resolved, 'tenant-a-reset');
    const removed = await observers.a.page.evaluate(async path => { const r = await fetch(path, { cache: 'no-store', credentials: 'omit', redirect: 'error' }); return { status: r.status, contentType: r.headers.get('content-type') }; }, icon.url);
    h.check('Original tenant icon public owner route proves asset removal after reset', removed.status === 404, { route: icon.url, ...removed });
    h.check('Reset leaves platform and other tenant exact owner snapshots unchanged', same(await profile.read(h, b), inheritedB) && same(await profile.read(h, h.admin), configured));
  } finally {
    await profile.restore(h, restoration);
  }
  const restored = await profile.read(h, h.admin);
  for (const [name, actor, observer] of [['global-restored', h.admin, observers.global], ['tenant-a-restored', a, observers.a], ['tenant-b-restored', b, observers.b]]) {
    const current = await profile.read(h, actor);
    h.check(name + ' restores original global name and theme on every Host', current.resolved.platformName === restored.resolved.platformName && current.resolved.primaryColor === restored.resolved.primaryColor);
    await publicView(h, observer, current.resolved, name);
  }
}
inheritance.actors = ['tenantAdmin', 'otherTenantAdmin'];
inheritance.transport = 'owner-api';
module.exports = { handlers: { 'F055-001': inheritance } };
