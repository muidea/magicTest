// Public document and dashboard consumer scenarios. Missing-response fixtures
// are browser-local and never modify File bytes or owner business facts.
const crypto = require('node:crypto');
const { waitLoginForm } = require('./login_readiness.cjs');
const handlers = {};
const viewports = [{ width: 390, height: 844 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }];
const documents = [{ key: 'privacy', title: '隐私政策' }, { key: 'terms', title: '服务条款' }].map(d => ({ ...d, page: '/legal/' + d.key + '/', content: '/static/share/platform/legal/' + d.key + '.md' }));
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
async function anonymous(h, fn) {
  const context = await h.browser.newContext({ ignoreHTTPSErrors: true, viewport: viewports[1] });
  const page = await context.newPage(), actor = { context, page, origin: h.credentials.origin, identity: { account: 'anonymous', namespace: h.credentials.namespace } };
  try { return await fn(actor); } finally { await context.close(); }
}
async function fits(h, actor, locator, label) {
  h.check(label + ' visible', await locator.isVisible());
  const box = await locator.boundingBox();
  h.check(label + ' fits viewport', box && box.x >= -1 && box.width > 0 && box.x + box.width <= actor.page.viewportSize().width + 1, box);
}
async function returnLogin(h, actor) {
  await actor.page.getByRole('link', { name: '返回登录', exact: true }).click();
  await actor.page.waitForURL(url => /^\/login(?:\/cas)?\/?$/.test(url.pathname));
  await actor.page.locator('input[name=account], #normal_login_account').first().waitFor({ state: 'visible' });
  await actor.page.waitForLoadState('networkidle');
  const session = await h.api(actor, 'GET', '/api/v1/web/session/');
  h.check('Return to login does not invent an authenticated session',
    session.status === 401 || (session.status === 200 && session.data?.error?.code === 11 && !session.data.value), session);
}
async function open(h, actor, doc) {
  const pending = actor.page.waitForResponse(r => new URL(r.url()).pathname === doc.content && r.request().resourceType() === 'fetch');
  pending.catch(() => {});
  await actor.page.goto(actor.origin + doc.page, { waitUntil: 'networkidle' });
  const response = await pending, bytes = await response.body();
  h.check('Actual legal content request succeeds with declared text MIME', response.status() === 200 && /^text\/(plain|markdown)(?:;|$)/i.test(response.headers()['content-type'] || ''), { status: response.status(), contentType: response.headers()['content-type'], path: doc.content, bytes: bytes.length, sha256: digest(bytes) });
  const main = actor.page.getByRole('main', { name: doc.title });
  await main.locator('h1').waitFor({ state: 'visible' });
  h.check('Actual document title renders on the public page', await main.locator('h1').innerText() === doc.title);
  h.check('Successful document renders substantive paragraphs without error fallback', await main.locator('p').count() > 0 && await main.locator('.ant-alert').count() === 0);
  return { main, bytes };
}
handlers['F064-001'] = async h => anonymous(h, async actor => {
  await actor.page.goto(actor.origin + '/login/', { waitUntil: 'networkidle' });
  await waitLoginForm(actor.page);
  for (const doc of documents) {
    const link = actor.page.getByRole('link', { name: doc.title, exact: true });
    h.check('Login exposes exact public legal page link', await link.count() === 1 && await link.getAttribute('href') === doc.page,
      { path: new URL(actor.page.url()).pathname, count: await link.count(), hrefs: await link.evaluateAll(nodes => nodes.map(node => node.getAttribute('href'))) });
    const { bytes, main } = await open(h, actor, doc);
    const independent = await actor.page.evaluate(async path => {
      const r = await fetch(path, { credentials: 'omit', redirect: 'error', cache: 'no-store' });
      return { status: r.status, bytes: Array.from(new Uint8Array(await r.arrayBuffer())) };
    }, doc.content);
    h.check('Independent unauthenticated public read matches the actual page response bytes', independent.status === 200 && digest(Buffer.from(independent.bytes)) === digest(bytes), { path: doc.content, bytes: bytes.length, sha256: digest(bytes), contentStatus: /临时说明|尚待.*确认/.test(bytes.toString('utf8')) ? 'temporary-content-retained-by-user' : 'current-public-content; formal approval not inferred' });
    if (/临时说明|尚待.*确认/.test(bytes.toString('utf8'))) h.check('Retained temporary legal status remains visible', /临时说明|尚待.*确认/.test(await main.innerText()));
    await h.screenshot(actor, doc.key + '-current-public-content');
    await returnLogin(h, actor);
  }
});
handlers['F064-002'] = async h => anonymous(h, async actor => {
  for (const doc of documents) {
    let injected = 0;
    const pattern = url => url.origin === actor.origin && url.pathname === doc.content;
    await actor.page.route(pattern, async route => {
      injected++; await route.fulfill({ status: 404, contentType: 'text/plain', body: 'Current browser missing-document fixture' });
    });
    try {
      await actor.page.goto(actor.origin + doc.page, { waitUntil: 'networkidle' });
      const main = actor.page.getByRole('main', { name: doc.title }), alert = main.locator('.ant-alert');
      await alert.getByText('文档尚未发布，请联系管理员。', { exact: true }).waitFor({ state: 'visible' });
      h.check('Missing-document fixture reaches exact real loader request', injected === 1);
      h.check('Missing document shows explicit unavailable state instead of blank/other legal body', await main.locator('h1,p').count() === 0 && (await alert.innerText()).includes(doc.title), { fixture: 'browser-local HTTP 404; no backend File outage or byte mutation' });
      await fits(h, actor, alert, doc.title + ' unavailable feedback');
      await h.screenshot(actor, doc.key + '-missing');
    } finally { await actor.page.unroute(pattern); }
    const response = actor.page.waitForResponse(r => new URL(r.url()).pathname === doc.content);
    response.catch(() => {});
    await actor.page.getByRole('button', { name: /^重\s*试$/ }).click();
    h.check('Retry reaches actual restored document response', (await response).status() === 200);
    await actor.page.getByRole('main', { name: doc.title }).locator('h1').waitFor({ state: 'visible' });
    h.check('Successful real retry clears missing-document error', await actor.page.getByRole('main', { name: doc.title }).locator('.ant-alert').count() === 0);
  }
});
handlers['F064-003'] = async h => anonymous(h, async actor => {
  for (const viewport of viewports) {
    await actor.page.setViewportSize(viewport);
    for (const doc of documents) {
      const { main, bytes } = await open(h, actor, doc);
      h.check('Layout uses an actual long deployed document', bytes.length > 1000 && await main.locator('h2').count() >= 3, { path: doc.content, bytes: bytes.length });
      await fits(h, actor, main, doc.title + ' reading region');
      for (const heading of await main.locator('h1,h2').all()) {
        await heading.scrollIntoViewIfNeeded(); await fits(h, actor, heading, doc.title + ' heading');
      }
      for (const link of await main.locator('a').all()) {
        const href = await link.getAttribute('href');
        h.check('Rendered document links have explicit safe destinations', /^https:\/\/|^mailto:/.test(href || '') && await link.getAttribute('rel') === 'noopener noreferrer', { href });
      }
      h.check('Long legal document has no horizontal page overflow', await actor.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await actor.page.evaluate(() => scrollTo(0, 0));
      await h.screenshot(actor, doc.key + '-layout-' + viewport.width);
      await returnLogin(h, actor);
    }
  }
});
handlers['F066-003'] = async h => {
  const { createRegistrationFixture, setRegistrationPolicy, submitRegistration, reviewRegistration } = require('./registration_cases.cjs');
  const f = await createRegistrationFixture(h, 'dashboard');
  const actor = await h.login(f.bootstrap.account, h.state.password, f.ns.name, h.state.password + 'D');
  await setRegistrationPolicy(h, f);
  const pendingRoute = '/panel/todos/?status=pending';
  h.check('Dedicated dashboard has a real empty pending owner directory', (await h.directory(actor, pendingRoute)).length === 0);
  const card = () => actor.page.locator('.ant-card').filter({ has: actor.page.locator('.ant-card-head-title').getByText('待办审批', { exact: true }) });
  const load = async () => {
    await actor.page.goto(actor.origin + '/panel/', { waitUntil: 'networkidle' });
    await actor.page.getByRole('heading', { name: '管理概览', exact: true }).waitFor({ state: 'visible' });
    await card().waitFor({ state: 'visible' });
  };
  for (const viewport of viewports) {
    await actor.page.setViewportSize(viewport); await load();
    await card().getByText('暂无待办事项', { exact: true }).waitFor({ state: 'visible' });
    h.check('Real empty dashboard has no placeholder processing actions', await card().getByRole('button').count() === 0);
    await fits(h, actor, card(), 'Empty dashboard card');
    h.check('Empty dashboard does not overflow horizontally', await actor.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await h.screenshot(actor, 'dashboard-empty-' + viewport.width);
    let injected = 0;
    const pattern = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/panel/profile';
    await actor.page.route(pattern, async route => {
      h.check('Controlled dashboard failure only intercepts profile reads', route.request().method() === 'GET');
      injected++; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 15, message: '当前浏览器受控管理概览读取失败' } }) });
    });
    try {
      await load();
      const alert = actor.page.locator('.ant-alert-error');
      await alert.waitFor({ state: 'visible' });
      h.check('Profile loader displays failure from actual intercepted read', injected > 0 && /失败|不可用/.test(await alert.innerText()), { fixture: 'browser-local profile read failure; live owner facts unchanged', injected });
      await fits(h, actor, alert, 'Dashboard failure feedback');
      await h.screenshot(actor, 'dashboard-profile-failure-' + viewport.width);
    } finally { await actor.page.unroute(pattern); }
    await load();
    h.check('Restored live dashboard clears controlled failure', await actor.page.locator('.ant-alert-error').count() === 0);
  }
  const account = h.state.prefix + '-' + 'long'.repeat(12);
  const request = await submitRegistration(h, f, { account, password: h.state.password, displayName: '回归长标题注册申请', email: account + '@example.test', phone: '' });
  h.check('Real registration creates a pending source for the long dashboard item', request.status === 'pending');
  let todo;
  for (let attempt = 0; attempt < 10; attempt++) {
    todo = (await h.directory(actor, pendingRoute)).find(t => t.sourceID === String(request.id) && t.namespace === f.ns.name);
    if (todo) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  h.check('Independent projection contains exact original real registration source and long text', todo?.source === 'magicCas' && todo.categoryKey === 'registration-review' && todo.content.includes(account) && todo.content.length > 48, todo);
  const displayed = todo.content.trim().slice(0, 48) + '...';
  for (const viewport of viewports) {
    await actor.page.setViewportSize(viewport); await load();
    const title = card().getByRole('button', { name: displayed, exact: true });
    await title.waitFor({ state: 'visible' });
    const action = card().getByRole('button', { name: '去处理', exact: true });
    await fits(h, actor, title, 'Long real dashboard title');
    await fits(h, actor, action, 'Long dashboard processing action');
    const titleBox = await title.boundingBox(), actionBox = await action.boundingBox();
    h.check('Long dashboard text and processing action do not cover each other', titleBox.x + titleBox.width <= actionBox.x + 1 || titleBox.y + titleBox.height <= actionBox.y + 1 || actionBox.y + actionBox.height <= titleBox.y + 1, { titleBox, actionBox });
    h.check('Populated dashboard has no horizontal overflow', await actor.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await h.screenshot(actor, 'dashboard-real-long-item-' + viewport.width);
    await action.click();
    await actor.page.waitForURL(url => url.pathname === '/panel/cas/access/' && url.searchParams.get('tab') === 'registration');
    h.check('Processing action targets the exact owner registration screen', new URL(actor.page.url()).origin === actor.origin);
  }
  await reviewRegistration(h, f, request, 'reject');
  const final = (await h.ok(h.admin, 'GET', f.reg + 'accounts/' + request.id)).value;
  h.check('Original registration owner confirms terminal disposition without replacement', final.id === request.id && final.accountId === request.accountId && final.status === 'rejected');
  await h.gone(f.base + 'accounts/', request.accountId);
  let residual = true;
  for (let attempt = 0; attempt < 10; attempt++) {
    residual = (await h.directory(actor, pendingRoute)).some(t => t.sourceID === String(request.id));
    if (!residual) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  h.check('Independent pending projection releases the original disposed source', !residual);
  await load();
  await card().getByText('暂无待办事项', { exact: true }).waitFor({ state: 'visible' });
};
handlers['F055-002'] = async h => {
  const actor = h.tenantAdmin, namespace = h.need('tenantA').name;
  const route = '/panel/namespace-branding/';
  const globalBefore = (await h.ok(h.admin, 'GET', route)).value;
  const before = (await h.ok(actor, 'GET', route)).value;
  h.check('Layout fixture is the exact newly-created tenant with no previous branding override', before.namespace === namespace && before.override == null);
  const body = { platformName: '品牌长名称'.repeat(14), platformShortName: '品牌长名称'.repeat(6), loginTitle: '回归登录品牌长标题', loginSubtitle: '使用当前租户账号继续', footerText: '', primaryColor: '#1677ff', logoAltText: '当前租户回归品牌图标', backgroundPosition: 'center', backgroundOverlayOpacity: null, sloganMode: 'inherit', sloganAltText: '', brandingFeatureMode: 'inherit', brandingFeatureAltText: '', expectedResourceVersion: 0 };
  h.owned(route, { id: '', name: namespace }, 'namespace-branding', 'tenantAdmin');
  const resource = h.state.resources.at(-1);
  resource.layoutWrite = { intended: structuredClone(body), actorIdentity: structuredClone(actor.identity), outcome: 'unknown' }; h.persist();
  let anon;
  try {
  const response = await h.api(actor, 'PUT', route, body);
  resource.layoutWrite.response = response; resource.layoutWrite.outcome = h.good(response) ? 'acknowledged' : 'unconfirmed'; h.persist();
  h.check('Original long-brand command is accepted by current tenant owner', h.good(response), response);
  const saved = (await h.ok(actor, 'GET', route)).value;
  h.check('Independent owner preserves exact long-brand fields', saved.namespace === namespace && saved.override?.platformName === body.platformName && saved.resolved?.platformShortName === body.platformShortName && saved.resolved?.logoAltText === body.logoAltText);
  anon = await h.anonymous(namespace);
  const checkPublic = async current => {
    const publicValue = (await h.ok(current, 'GET', '/api/v1/web/branding/')).value;
    h.check('Actual tenant Host public projection agrees with independent owner', publicValue.namespace === namespace && publicValue.platformName === body.platformName && publicValue.platformShortName === body.platformShortName && publicValue.logoAltText === body.logoAltText);
  };
  const loaded = async (current, locator, label) => {
    await locator.waitFor({ state: 'visible' });
    await locator.evaluate(img => img.decode());
    const info = await locator.evaluate(img => ({ complete: img.complete, width: img.naturalWidth, height: img.naturalHeight, src: img.currentSrc.startsWith('data:') ? 'embedded-image; bytes omitted' : new URL(img.currentSrc || img.src).pathname }));
    h.check(label + ' uses an actually decoded image', info.complete && info.width > 0 && info.height > 0, info);
    await fits(h, current, locator, label);
    return info;
  };
    for (const viewport of viewports) {
      await anon.page.setViewportSize(viewport);
      await anon.page.goto(anon.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
      await checkPublic(anon);
      const name = anon.page.locator('#platform-brand-name');
      await name.getByText(body.platformName, { exact: true }).waitFor();
      h.check('Long original brand name remains complete in the actual login heading', await name.innerText() === body.platformName);
      await fits(h, anon, name, 'Long login brand heading');
      await loaded(anon, anon.page.getByRole('banner', { name: '平台品牌', exact: true }).getByRole('img'), 'Actual login brand icon');
      const artwork = anon.page.locator('img[data-testid="namespace-branding-slogan"],img[data-testid="namespace-branding-feature"]');
      let visibleArtwork = 0;
      for (const img of await artwork.all()) if (await img.isVisible()) { visibleArtwork++; await loaded(anon, img, 'Login artwork'); }
      h.check('Actual login content retains visible deployed artwork at each declared width', visibleArtwork > 0, { width: viewport.width, visibleArtwork });
      const login = anon.page.getByTestId('cas-login-card');
      for (const control of [login.locator('input[name=account]'), login.locator('input[name=password]'), login.getByRole('button', { name: /^登\s*录$/ })]) {
        await control.scrollIntoViewIfNeeded(); await fits(h, anon, control, 'Login control beside brand artwork');
        h.check('Brand content does not cover original login control', await control.evaluate(el => { const r = el.getBoundingClientRect(); const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return !!top && (top === el || el.contains(top)); }));
      }
      h.check('Long-brand login does not overflow viewport', await anon.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
      await h.screenshot(anon, 'long-brand-login-' + viewport.width);
      await actor.page.setViewportSize(viewport);
      for (const path of ['/panel/', '/portal/']) {
        await actor.page.goto(actor.origin + path, { waitUntil: 'networkidle' }); await checkPublic(actor);
        const mark = actor.page.getByRole('button', { name: '返回' + body.platformName + '首页', exact: true });
        await mark.waitFor({ state: 'visible' });
        h.check('Panel and Portal display the same original tenant brand text', await mark.locator('.magic-layout-brand-title').innerText() === body.platformShortName);
        await fits(h, actor, mark, 'Authenticated tenant brand');
        h.observe({ kind: 'authenticated-brand-layout', path, width: viewport.width, elements: await mark.evaluate(el => [el, ...el.children].map(n => { const style = getComputedStyle(n), box = n.getBoundingClientRect(); return { tag: n.tagName, class: n.className, text: n.tagName === 'IMG' ? n.getAttribute('alt') : n.textContent, display: style.display, width: box.width, x: box.x, flex: style.flex, visibility: style.visibility, overflow: style.overflow }; })) });
        await loaded(actor, mark.locator('img'), 'Authenticated tenant icon');
        h.check('Authenticated long brand remains within viewport', await actor.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
        await h.screenshot(actor, 'long-brand-' + path.split('/')[1] + '-' + viewport.width);
      }
    }
    h.check('Unrelated global branding remains exactly unchanged', require('node:util').isDeepStrictEqual((await h.ok(h.admin, 'GET', route)).value, globalBefore));
  } catch (error) {
    if (anon) await h.screenshot(anon, 'long-brand-layout-unresolved');
    await h.screenshot(actor, 'authenticated-brand-layout-unresolved');
    throw error;
  } finally {
    const proof = await require('./branding_cleanup.cjs').resetBranding(h, actor, resource);
    resource.layoutReset = proof; resource.phase = 'deleted'; h.persist();
    const reset = (await h.ok(actor, 'GET', route)).value;
    h.check('Original tenant formal reset restores inherited owner projection', reset.namespace === namespace && reset.override == null && require('node:util').isDeepStrictEqual(reset.resolved, before.resolved));
  }
};
handlers['F055-002'].actors = ['tenantAdmin'];
handlers['F055-002'].transport = 'owner-api';

module.exports = { handlers };
