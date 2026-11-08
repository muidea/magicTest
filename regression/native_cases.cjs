// Native authoring through the real wizard; shared owner lifecycle keeps the
// original browser POST, independent read and exact-ID cleanup paired.
const { isDeepStrictEqual: same } = require('node:util');
const { execFileSync } = require('node:child_process');
const { createResource } = require('./resource_lifecycle.cjs');
const { readDirectory } = require('./directory.cjs');
const handlers = {}, base = '/panel/application/definitions/';
const imageRoute = '/panel/application/orchestrations/images/resolve';
const card = (page, title) => page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title').filter({ hasText: new RegExp('^' + title + '$') }) }).last();
const field = (scope, label) => scope.locator('.ant-form-item').filter({ has: scope.page().locator('label').filter({ hasText: new RegExp('^' + label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$') }) }).locator('input,textarea').first();
const button = (scope, text) => scope.getByRole('button', { name: text, exact: typeof text === 'string' });
async function settle(page) { await page.waitForLoadState('networkidle'); await page.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' }); }

async function observeNativeCreate(h, trigger) {
  const page = h.admin.page, match = u => u.origin === h.admin.origin && u.pathname === '/api/v1/web/proxy' + base;
  let sends = 0, upstream, app, error, complete;
  const finished = new Promise(resolve => { complete = resolve; });
  const route = async r => {
    if (r.request().method() !== 'POST') return r.continue();
    if (++sends !== 1) { error = new h.Blocked('Duplicate original UI creation suppressed'); await r.abort('failed'); return; }
    try {
      const intended = r.request().postDataJSON();
      const originalRequest = async (actor, method, pathname, body) => {
        if (method !== 'POST') return (h.ownerApi || h.api)(actor, method, pathname, body);
        if (pathname !== base || !same(body, intended) || upstream) throw new h.Blocked('Only the exact original UI POST may be dispatched');
        upstream = await r.fetch({ maxRetries: 0 });
        return { status: upstream.status(), data: await upstream.json() };
      };
      const adapter = { ...h, api: originalRequest, ownerApi: originalRequest };
      app = await createResource(adapter, h.admin, 'admin', base, intended, 'definition');
    } catch (e) { error = e; }
    finally {
      try { if (upstream) await r.fulfill({ response: upstream }); else await r.abort('failed'); }
      finally { complete(); }
    }
  };
  await page.route(match, route);
  let timer;
  try {
    await trigger();
    await Promise.race([finished, new Promise((_, reject) => { timer = setTimeout(() => reject(new h.Blocked('No original wizard creation returned; retain any recorded intent')), 30000); })]);
    if (error) throw error;
    h.check('Exactly one original wizard POST is acknowledged and independently owned', sends === 1 && !!app, app);
    return app;
  } finally { clearTimeout(timer); await page.unroute(match, route); }
}
async function start(h, suffix) {
  const page = h.admin.page, name = h.state.prefix + '-' + suffix;
  await page.goto(h.admin.origin + '/panel/application/orchestration/', { waitUntil: 'networkidle' });
  await button(page, /新建编排$/).click();
  const editor = card(page, '新建原生应用');
  await field(editor, '应用标识').fill(name); await field(editor, '应用名称').fill('回归原生 ' + suffix);
  await field(editor, '发布版本').fill('1.2.3'); await field(editor, '分类').fill('regression');
  await field(editor, '说明').fill('向导原始输入 ' + suffix);
  await button(editor, '下一步').click();
  await card(page, '添加服务组件').waitFor({ state: 'visible' });
  h.check('First component editor opens automatically after basic information', await field(card(page, '添加服务组件'), '组件标识').inputValue() === '');
  return { page, editor, name };
}
async function component(h, key, image) {
  const c = card(h.admin.page, '添加服务组件');
  await field(c, '组件标识').fill(key); await field(c, '镜像').fill(image);
  await field(c, '说明').fill('组件说明 ' + key);
  await field(c, 'Command（每行一个参数）').fill('echo\n' + key);
  await button(c, '保存组件').click(); await c.waitFor({ state: 'hidden' }); await settle(h.admin.page);
}
async function closeUnwritten(h, editor, before, writes) {
  await button(editor, /^关\s*闭$/).click(); await editor.waitFor({ state: 'hidden' });
  h.check('Cancelled wizard sends no definition mutation', writes.length === 0, writes);
  h.check('Complete independent owner directory is unchanged after cancellation', same(await readDirectory(h, h.admin, base), before));
}
function watchWrites(page) {
  const writes = [], watch = r => { const u = new URL(r.url()); if (['POST', 'PUT', 'DELETE'].includes(r.method()) && u.pathname.startsWith('/api/v1/web/proxy' + base)) writes.push(r.method() + ' ' + u.pathname); };
  page.on('request', watch); return { writes, stop: () => page.off('request', watch) };
}
handlers['F021-001'] = async h => {
  const { page, editor, name } = await start(h, 'nativewizard');
  await component(h, 'api', 'example/api:1.0.0');
  await button(editor, /添加服务组件$/).click(); await component(h, 'worker', 'example/worker:2.0.0');
  for (const key of ['api', 'worker']) h.check('Wizard component table retains ' + key, await editor.locator('tr[data-row-key="' + key + '"]').count() === 1);
  await button(editor, '上一步').click();
  h.check('Backward navigation retains all original basic fields', await field(editor, '应用标识').inputValue() === name && await field(editor, '应用名称').inputValue() === '回归原生 nativewizard' && await field(editor, '发布版本').inputValue() === '1.2.3' && await field(editor, '分类').inputValue() === 'regression' && await field(editor, '说明').inputValue() === '向导原始输入 nativewizard');
  await button(editor, '下一步').click(); await button(editor, '下一步').click();
  await button(editor, '上一步').click();
  h.check('Runtime step round trip retains both component rows', await editor.locator('tr[data-row-key]').count() === 2);
  await button(editor, '下一步').click(); await button(editor, '下一步').click();
  await h.screenshot(h.admin, 'native-two-components-before-save');
  const app = await observeNativeCreate(h, () => button(editor, '保存草稿').click());
  const current = (await h.ok(h.admin, 'GET', base + app.id)).value;
  const components = current.orchestration?.contract?.components || {};
  h.check('Independent exact owner preserves basic identity and both original components', current.id === app.id && current.name === name && current.runtimeType === 'packaged-runtime' && current.version === '1.2.3' && current.catalog === 'regression' && current.description === '向导原始输入 nativewizard' && same(Object.keys(components).sort(), ['api', 'worker']) && ['api', 'worker'].every(key => components[key].image === 'example/' + key + ':' + (key === 'api' ? '1.0.0' : '2.0.0') && components[key].description === '组件说明 ' + key && same(components[key].command, ['echo', key])), current);
  await settle(page); await h.screenshot(h.admin, 'native-saved-owner-directory');
};
handlers['F021-002'] = async h => {
  const before = await readDirectory(h, h.admin, base), observer = watchWrites(h.admin.page);
  try {
    const { editor } = await start(h, 'nativecancel');
    await component(h, 'only', 'example/only:1.0.0');
    await editor.locator('tr[data-row-key="only"]').getByRole('button', { name: /^删\s*除$/ }).click();
    h.check('Removing every component blocks progression and exposes no save', await button(editor, '下一步').isDisabled() && await button(editor, '保存草稿').count() === 0 && await editor.locator('tr[data-row-key]').count() === 0);
    const empty = { apiVersion: 'magic.native-orchestration/v1', components: {}, volumes: {}, ingresses: {}, capabilities: { portalEntries: {} } };
    const result = (await h.ok(h.admin, 'POST', '/panel/application/orchestrations/validate-draft', empty)).value;
    h.check('Public draft owner refuses empty components with located diagnostic', result.valid === false && result.issues?.some(i => i.code === 'components.count' && i.fieldPath === 'components' && i.blocking), result);
    await h.screenshot(h.admin, 'native-empty-components-blocked');
    await closeUnwritten(h, editor, before, observer.writes);
  } finally { observer.stop(); }
};

// Project only identity and nonsecret fields from local inspect. Never archive
// raw OCI Env, registry credentials, container config or browser credentials.
function localImage(h, address) {
  let image;
  try { image = JSON.parse(execFileSync('docker', ['image', 'inspect', address], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }))[0]; }
  catch { throw new h.Blocked('LOCAL-IMAGE-FIXTURE: required existing image unavailable: ' + address); }
  const labels = image.Config.Labels || {};
  return { address, ids: [image.Id, ...(image.RepoDigests || []).map(x => x.split('@')[1])], labels: Object.fromEntries(Object.entries(labels).filter(([key]) => key.startsWith('io.platform.'))), labelCount: Object.keys(labels).length, command: image.Config.Cmd || [], entrypoint: image.Config.Entrypoint || [], workingDir: image.Config.WorkingDir || '' };
}
async function resolve(h, fixture) {
  const value = (await h.ok(h.admin, 'POST', imageRoute, { imageAddress: fixture.address })).value;
  h.check('Image resolver confirms exact existing local identity', value.imageAddress === fixture.address && fixture.ids.includes(value.imageDigest), { address: value.imageAddress, digest: value.imageDigest });
  return value;
}
handlers['F022-001'] = async h => {
  const coverage = { environment: false, port: false, volume: false, health: false, startup: false };
  for (const [index, address] of ['postgres:17.7-alpine3.22', 'muidea/magicfile:master'].entries()) {
    const fixture = localImage(h, address), before = await readDirectory(h, h.admin, base), observer = watchWrites(h.admin.page);
    try {
      const { page, editor } = await start(h, 'oci-config-' + index), c = card(page, '添加服务组件');
      await field(c, '组件标识').fill('config'); await field(c, '镜像').fill(address);
      const first = await readSuggestions(h, c);
      h.check('Real local OCI metadata read succeeds for fixture identity', h.good(first) && first.data.value.imageAddress === address && fixture.ids.includes(first.data.value.imageDigest), first);
      const metadata = first.data.value, config = metadata.imageConfig;
      await reread(c).waitFor();
      h.check('Blank startup fields receive actual image suggestions and digest', await field(c, 'Entrypoint（每行一个参数）').inputValue() === (config.entrypoint || []).join('\n') && await field(c, 'Command（每行一个参数）').inputValue() === (config.command || []).join('\n') && await field(c, '工作目录').inputValue() === (config.workingDir || '') && await reread(c).getAttribute('title') === metadata.imageDigest);
      await field(c, 'Command（每行一个参数）').fill('echo\nkeep-user-command'); await field(c, '工作目录').fill('/user-owned');
      await c.getByRole('tab', { name: '环境变量', exact: true }).click();
      const ignored = new Set(['HOME', 'HOSTNAME', 'LANG', 'PATH', 'PWD', 'SHLVL', 'TERM']);
      const expectedEnv = Object.fromEntries((config.environment || []).filter(e => e.hasDefault && !e.sensitive && /^[A-Za-z_][A-Za-z0-9_]*$/.test(e.name) && !ignored.has(e.name)).map(e => [e.name, { literal: e.default || '' }]));
      const names = await c.getByPlaceholder('变量名', { exact: true }).evaluateAll(nodes => nodes.map(n => n.value));
      h.check('Only declared non-sensitive image environment suggestions enter the actual form', same([...names].sort(), Object.keys(expectedEnv).sort()));
      if (names.length) { await c.getByPlaceholder('普通值', { exact: true }).first().fill('user-keeps-original-name'); expectedEnv[names[0]] = { literal: 'user-keeps-original-name' }; coverage.environment = true; }
      await button(c, '添加环境变量').click(); await c.getByPlaceholder('变量名', { exact: true }).last().fill('USER_OPTION'); await c.getByPlaceholder('普通值', { exact: true }).last().fill('0'); expectedEnv.USER_OPTION = { literal: '0' };
      await c.getByRole('tab', { name: '镜像与运行', exact: true }).click();
      const again = await readSuggestions(h, c);
      h.check('Repeated image read retains the exact inspected immutable image identity', h.good(again) && again.data.value.imageDigest === metadata.imageDigest);
      const endpoint = '/api/v1/web/proxy/panel/application/orchestrations/components/validate';
      const pending = page.waitForRequest(r => new URL(r.url()).pathname === endpoint && r.method() === 'POST'); pending.catch(() => {});
      const returned = page.waitForResponse(r => new URL(r.url()).pathname === endpoint && r.request().method() === 'POST'); returned.catch(() => {});
      await button(c, '保存组件').click(); const request = (await pending).postDataJSON(), response = await returned;
      const owner = { status: response.status(), data: await response.json() }, component = request.contract.components.config;
      h.check('Actual component producer and validator accept suggested configuration', h.good(owner) && owner.data.value.valid === true && request.focusComponentKey === 'config', owner);
      h.check('Reread preserves user command, directory and existing environment values without duplicates', same(component.command, ['echo', 'keep-user-command']) && component.workingDir === '/user-owned' && same(component.entrypoint, config.entrypoint || []) && same(component.environment, expectedEnv), component);
      const ports = Object.values(component.ports || {});
      h.check('All declared TCP ports are suggested exactly once', (config.exposedPorts || []).filter(p => p.protocol === 'tcp').every(p => ports.filter(v => v.containerPort === p.port).length === 1), component.ports);
      const mounts = component.mounts || [];
      h.check('All image volumes retain distinct confined local-volume declarations', same(mounts.map(m => m.target).sort(), [...(config.volumes || [])].sort()) && new Set(mounts.map(m => m.volumeRef)).size === mounts.length && mounts.every(m => { const v = request.contract.volumes[m.volumeRef]; return v?.backend === 'localDirectory' && v.scope === 'component' && same(v.consumers, ['config']); }), { mounts, volumes: request.contract.volumes });
      const healthURL = (config.healthcheck?.test || []).join(' ').match(/http:\/\/(?:localhost|127\.0\.0\.1)(?::[0-9]+)?\/[^\s'"`]*/)?.[0];
      if (healthURL) { const url = new URL(healthURL), readiness = component.readiness; h.check('Actual local HTTP image health check seeds the declared readiness port and path', readiness?.type === 'http' && readiness.path === url.pathname && component.ports[readiness.portRef]?.containerPort === Number(url.port || 80) && component.ports[readiness.portRef]?.protocol === 'http', readiness); coverage.health = true; }
      coverage.port ||= ports.length > 0; coverage.volume ||= mounts.length > 0; coverage.startup ||= (component.entrypoint || []).length > 0;
      await h.screenshot(h.admin, 'oci-config-confirmed-' + index); await closeUnwritten(h, editor, before, observer.writes);
    } catch (error) {
      await h.screenshot(h.admin, 'oci-config-' + index + '-unresolved');
      throw error;
    } finally { observer.stop(); }
  }
  h.check('Actual image fixtures cover every required OCI suggestion class', Object.values(coverage).every(Boolean), coverage);
};
handlers['F022-002'] = async h => {
  const plain = localImage(h, 'postgres:17.7-alpine3.22'), platform = localImage(h, 'muidea/magicbase:master');
  if (plain.labelCount !== 0 || platform.labels['io.platform.runtime-provider'] !== 'modelExecution') throw new h.Blocked('LOCAL-IMAGE-FIXTURE: no-label and explicit runtime-provider images required');
  const normal = await resolve(h, plain), builtin = await resolve(h, platform);
  h.check('No-label ordinary image resolves OCI config without platform requirements', !normal.imageConfig.platform && same(normal.imageConfig.command, plain.command) && same(normal.imageConfig.entrypoint, plain.entrypoint));
  h.check('Built-in image uses exact explicit platform labels', same(builtin.imageConfig.platform, { application: platform.labels['io.platform.application'], role: platform.labels['io.platform.role'], runtimeProviderKind: platform.labels['io.platform.runtime-provider'] }), builtin.imageConfig.platform);
};
const reread = scope => scope.locator('button').filter({ hasText: /^重新读取 OCI Config$/ });
async function readSuggestions(h, scope) {
  const pending = h.admin.page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/web/proxy' + imageRoute && r.request().method() === 'POST');
  pending.catch(() => {}); // A failed click must not leave an unhandled read waiter.
  await button(scope, /读取 OCI Config/).click();
  const response = await pending, result = { status: response.status(), data: await response.json() };
  if (h.good(result)) {
    // Ant's loading icon temporarily prefixes the accessible name. Wait for
    // the actual producer to finish rendering, independently of that label.
    const completed = reread(scope);
    await completed.waitFor({ state: 'visible' });
    await completed.locator('.anticon-loading').waitFor({ state: 'hidden' });
    h.check('Completed OCI suggestion producer displays the exact returned image digest', await completed.getAttribute('title') === result.data.value.imageDigest);
  }
  return result;
}
handlers['F022-003'] = async h => {
  const plain = localImage(h, 'postgres:17.7-alpine3.22'), platform = localImage(h, 'muidea/magicbase:master');
  const before = await readDirectory(h, h.admin, base), observer = watchWrites(h.admin.page);
  try {
    const { page, editor } = await start(h, 'imagerecovery'), c = card(page, '添加服务组件');
    await field(c, '组件标识').fill('recovery');
    await field(c, '镜像').fill('regression.invalid/' + h.state.prefix + ':missing');
    const missing = await readSuggestions(h, c);
    h.check('Missing local image reports explicit owner diagnosis', missing.data?.error?.code === 2 && /not prepared in the local docker daemon/.test(missing.data.error.message), missing);
    await page.getByText('deployment image is not prepared in the local docker daemon', { exact: true }).first().waitFor();
    await h.screenshot(h.admin, 'image-missing-diagnostic');
    await field(c, '镜像').fill(plain.address);
    const retried = await readSuggestions(h, c);
    h.check('Switch and retry resolve the current local image', h.good(retried) && retried.data.value.imageAddress === plain.address && plain.ids.includes(retried.data.value.imageDigest), { address: retried.data?.value?.imageAddress, digest: retried.data?.value?.imageDigest });
    await reread(c).waitFor();
    h.check('Retry actually seeded environment, volumes and ports before testing their removal', await c.getByPlaceholder('变量名', { exact: true }).count() > 0 && await c.getByPlaceholder('容器目录', { exact: true }).count() > 0 && await c.getByPlaceholder('端口标识', { exact: true }).count() > 0);
    h.check('Retry fills previously blank startup command', await field(c, 'Command（每行一个参数）').inputValue() === plain.command.join('\n'));
    await field(c, 'Command（每行一个参数）').fill('echo\nkeep-user-input');
    await field(c, '镜像').fill(platform.address);
    await c.getByPlaceholder('变量名', { exact: true }).first().waitFor({ state: 'hidden' });
    h.check('Image change clears all prior unedited suggestions and digest while preserving user input', await field(c, 'Entrypoint（每行一个参数）').inputValue() === '' && await field(c, '工作目录').inputValue() === '' && await c.getByPlaceholder('变量名', { exact: true }).count() === 0 && await c.getByPlaceholder('容器目录', { exact: true }).count() === 0 && await c.getByPlaceholder('端口标识', { exact: true }).count() === 0 && await field(c, 'Command（每行一个参数）').inputValue() === 'echo\nkeep-user-input' && await button(c, /读取 OCI Config/).getAttribute('title') === null);
    await field(c, '镜像').fill(plain.address);
    let release, ready, oldResponse, intercepted = 0;
    const gate = new Promise(resolve => { release = resolve; }), held = new Promise(resolve => { ready = resolve; });
    const match = u => u.origin === h.admin.origin && u.pathname === '/api/v1/web/proxy' + imageRoute;
    const delay = async route => {
      if (route.request().method() !== 'POST' || route.request().postDataJSON().imageAddress !== plain.address) return route.continue();
      intercepted++; oldResponse = await route.fetch({ maxRetries: 0 }); ready(); await gate; await route.fulfill({ response: oldResponse });
    };
    await page.route(match, delay);
    let timer;
    try {
      await button(c, /读取 OCI Config/).click();
      await Promise.race([held, new Promise((_, reject) => { timer = setTimeout(() => reject(new h.Blocked('Original image read not intercepted')), 20000); })]);
      await field(c, '镜像').fill(platform.address);
      const newer = await readSuggestions(h, c);
      h.check('New image resolves before original delayed response', h.good(newer) && newer.data.value.imageAddress === platform.address && platform.ids.includes(newer.data.value.imageDigest));
      await reread(c).waitFor();
      const newForm = await c.locator('input,textarea,.ant-select-selection-item,.ant-switch').evaluateAll(nodes => nodes.map(n => ({ tag: n.tagName, value: n.value, text: n.classList.contains('ant-select-selection-item') ? n.textContent : undefined, checked: n.getAttribute('aria-checked') })));
      const late = page.waitForResponse(r => match(new URL(r.url())) && r.request().postDataJSON()?.imageAddress === plain.address);
      release(); await late; await settle(page);
      h.check('Late old suggestions cannot replace new identity, startup or user edits', intercepted === 1 && await field(c, '镜像').inputValue() === platform.address && await field(c, 'Entrypoint（每行一个参数）').inputValue() === platform.entrypoint.join('\n') && await field(c, 'Command（每行一个参数）').inputValue() === 'echo\nkeep-user-input' && await reread(c).getAttribute('title') === newer.data.value.imageDigest);
      const afterLate = await c.locator('input,textarea,.ant-select-selection-item,.ant-switch').evaluateAll(nodes => nodes.map(n => ({ tag: n.tagName, value: n.value, text: n.classList.contains('ant-select-selection-item') ? n.textContent : undefined, checked: n.getAttribute('aria-checked') })));
      h.check('Every current runtime, environment, volume, port and readiness input survives the late response unchanged', same(newForm, afterLate));
      await h.screenshot(h.admin, 'image-new-result-protected-from-late-old');
    } finally { clearTimeout(timer); release(); await page.unroute(match, delay); }
    await closeUnwritten(h, editor, before, observer.writes);
  } finally { observer.stop(); }
};
handlers['F021-003'] = async h => {
  const before = await readDirectory(h, h.admin, base), observer = watchWrites(h.admin.page);
  const page = h.admin.page;
  let reads = 0;
  const watch = request => { if (new URL(request.url()).pathname === '/api/v1/web/proxy' + imageRoute) reads++; };
  page.on('request', watch);
  try {
    const { editor, name } = await start(h, 'nativeinteraction');
    const plain = localImage(h, 'postgres:17.7-alpine3.22'), platform = localImage(h, 'muidea/magicfile:master');
    await component(h, 'api', plain.address);
    await button(editor, /添加服务组件$/).click(); await component(h, 'worker', platform.address);
    for (const width of [390, 1366, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      const rows = editor.locator('tr[data-row-key]');
      h.check('Component batch is represented by two exact table rows at width ' + width, await rows.count() === 2 && await editor.locator('tr[data-row-key="api"]').count() === 1 && await editor.locator('tr[data-row-key="worker"]').count() === 1);
      await editor.locator('tr[data-row-key="api"]').getByRole('button', { name: /^编\s*辑$/ }).click();
      const c = card(page, '编辑服务组件：api'), literal = 'echo\nkeep-unsaved-' + width;
      await field(c, 'Command（每行一个参数）').fill(literal);
      await c.getByRole('tab', { name: '环境变量', exact: true }).click();
      await c.getByRole('tab', { name: '镜像与运行', exact: true }).click();
      h.check('Unconfirmed component inputs survive tab navigation and step switching is fenced', await field(c, 'Command（每行一个参数）').inputValue() === literal && await button(editor, '上一步').isDisabled() && await button(editor, '下一步').isDisabled());
      const readsBeforeRefresh = reads;
      const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/web/proxy' + base && r.request().method() === 'GET'); response.catch(() => {});
      await button(page, /^刷\s*新$/).click(); await response; await settle(page);
      h.check('Manual list refresh preserves original component input without automatically rereading image', await field(c, 'Command（每行一个参数）').inputValue() === literal && await field(c, '镜像').inputValue() === plain.address && reads === readsBeforeRefresh);
      await h.screenshot(h.admin, 'native-input-refresh-' + width);
      await button(c, '保存组件').click(); await c.waitFor({ state: 'hidden' });
      await button(editor, '上一步').click();
      h.check('Explicit local save and wizard step round trip preserve original basic identity', await field(editor, '应用标识').inputValue() === name);
      await button(editor, '下一步').click();
      await editor.locator('tr[data-row-key="api"]').getByRole('button', { name: /^编\s*辑$/ }).click();
      const reopened = card(page, '编辑服务组件：api');
      h.check('Explicitly saved original component survives step switch and reopen', await field(reopened, 'Command（每行一个参数）').inputValue() === literal);
      await button(reopened, '返回组件列表').click();
      h.check('Wizard and component table stay within viewport at width ' + width, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
      const box = await editor.locator('.ant-table').boundingBox();
      h.check('Component table remains readable with its own bounded horizontal scroll', box && box.width > 200 && box.width <= width, box);
      await h.screenshot(h.admin, 'native-component-table-' + width);
    }
    await editor.locator('tr[data-row-key="api"]').getByRole('button', { name: /^编\s*辑$/ }).click();
    const original = card(page, '编辑服务组件：api');
    const keptCommand = await field(original, 'Command（每行一个参数）').inputValue();
    await field(original, '镜像').fill('regression.invalid/' + h.state.prefix + ':unavailable');
    const refused = await readSuggestions(h, original);
    h.check('Explicit image read failure reports actual resolver error without discarding user input', refused.data?.error?.code === 2 && /not prepared in the local docker daemon/.test(refused.data.error.message) && await field(original, 'Command（每行一个参数）').inputValue() === keptCommand, refused);
    await page.getByText('deployment image is not prepared in the local docker daemon', { exact: true }).first().waitFor();
    await h.screenshot(h.admin, 'native-component-read-error');
    await field(original, '镜像').fill(plain.address);
    let release, reached, timer, deliveries = 0;
    const held = new Promise(resolve => { reached = resolve; }), gate = new Promise(resolve => { release = resolve; });
    const match = url => url.origin === h.admin.origin && url.pathname === '/api/v1/web/proxy' + imageRoute;
    const delay = async route => {
      if (route.request().method() !== 'POST' || route.request().postDataJSON().imageAddress !== plain.address) return route.continue();
      const response = await route.fetch({ maxRetries: 0 }); reached(); await gate;
      await route.fulfill({ response }); deliveries++;
    };
    await page.route(match, delay);
    try {
      await button(original, /读取 OCI Config/).click();
      await Promise.race([held, new Promise((_, reject) => { timer = setTimeout(() => reject(new h.Blocked('Original component OCI request did not reach actual resolver')), 20000); })]);
      await button(original, '返回组件列表').click();
      await editor.locator('tr[data-row-key="worker"]').getByRole('button', { name: /^编\s*辑$/ }).click();
      const current = card(page, '编辑服务组件：worker');
      const snapshot = { image: await field(current, '镜像').inputValue(), command: await field(current, 'Command（每行一个参数）').inputValue() };
      const newer = await readSuggestions(h, current);
      h.check('Selected second component resolves its own image before original first component response', newer.data.value.imageAddress === platform.address && platform.ids.includes(newer.data.value.imageDigest));
      const pending = page.waitForResponse(r => match(new URL(r.url())) && r.request().postDataJSON()?.imageAddress === plain.address); pending.catch(() => {});
      release(); await pending; await settle(page);
      h.check('Late response from first component cannot change second component selection or user input', deliveries === 1 && await field(current, '组件标识').inputValue() === 'worker' && await field(current, '镜像').inputValue() === snapshot.image && await field(current, 'Command（每行一个参数）').inputValue() === snapshot.command && await reread(current).getAttribute('title') === newer.data.value.imageDigest);
      await h.screenshot(h.admin, 'native-late-component-response');
      await button(current, '返回组件列表').click();
    } finally { clearTimeout(timer); release(); await page.unroute(match, delay); }
    await closeUnwritten(h, editor, before, observer.writes);
  } catch (error) {
    h.observe({ kind: 'native-interaction-dom', buttons: await page.locator('button').evaluateAll(nodes => nodes.map(n => ({ text: n.innerText, label: n.getAttribute('aria-label'), title: n.getAttribute('title'), disabled: n.disabled, visible: !!(n.offsetWidth || n.offsetHeight) }))), accessibility: await page.locator('body').ariaSnapshot() });
    await h.screenshot(h.admin, 'native-interaction-unresolved');
    throw error;
  } finally { page.off('request', watch); observer.stop(); }
};

handlers['F026-002'] = async h => {
  const crypto = require('node:crypto'), admission = require('./native_admission.cjs');
  const fixture = localImage(h, 'postgres:17.7-alpine3.22'), collection = '/panel/application/deployment-packages/';
  const before = await readDirectory(h, h.admin, collection);
  const valid = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-build-admission', releaseVersion: '1.2.3',
    contract: { apiVersion: 'magic.native-orchestration/v1', components: { api: { image: fixture.address } } } };
  const preview = (await h.ok(h.admin, 'POST', collection + 'builds/preview', valid)).value;
  h.check('Positive public native preflight resolves real component image and build digest', preview.applicationUuid === valid.applicationUuid && preview.applicationName === valid.applicationName && /^sha256:[a-f0-9]{64}$/.test(preview.buildDigest) && preview.components?.length === 1 && preview.components[0].key === 'api' && fixture.ids.includes(preview.components[0].imageDigest), preview);
  h.check('Positive native preview creates no registered package', same(await readDirectory(h, h.admin, collection), before));
  const invalids = [];
  const missingDependency = structuredClone(valid);
  missingDependency.contract.components.api.dependsOn = [{ componentRef: 'missing', condition: 'started' }];
  invalids.push(['missing-dependency', missingDependency]);
  const missingImage = structuredClone(valid);
  missingImage.contract.components.api.image = 'regression.invalid/' + h.state.prefix + ':missing';
  invalids.push(['missing-image', missingImage]);
  for (const [variant, input] of invalids) {
    const rejected = await h.api(h.admin, 'POST', collection + 'builds/preview', input);
    h.check('Native preview locates the exact ' + variant + ' component error', admission.targetRejection(rejected, variant), rejected);
    await admission.probe(h, { intended: { ...input, expectedBuildDigest: preview.buildDigest }, variant });
  }
  // A structurally invalid dependency cannot enter an owner-valid revision.
  // An unavailable image can: exercise that real draft/publication boundary too.
  const body = JSON.parse(h.fs.readFileSync(h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression/fixture-definition-create-request.json')));
  Object.assign(body, { uuid: missingImage.applicationUuid, name: h.state.prefix + '-invalid-native-revision', pkgPrefix: h.state.prefix + 'nativeadmission', runtimeType: 'packaged-runtime',
    storage: { required: false, engine: '', versionConstraint: '', slots: [] }, orchestration: { contract: missingImage.contract } });
  const app = await h.create(base, body, 'definition');
  const current = (await h.ok(h.admin, 'GET', base + app.id)).value;
  h.check('Independent exact draft retains original unavailable component image', current.id === app.id && current.uuid === body.uuid && current.runtimeType === 'packaged-runtime' && same(current.orchestration.contract, missingImage.contract), current);
  const revisionPreview = await h.api(h.admin, 'POST', base + app.id + '/revisions/preview', { expectedDefinitionVersion: current.updateTime });
  h.check('Formal native revision preview refuses original component image before freezing', admission.targetRejection(revisionPreview, 'missing-image'), revisionPreview);
  h.observe({ kind: 'native-publish-envelope-control', meaning: 'Positive build digest only supplies a nonempty request envelope. It is not the digest of the invalid revision. Assert exact component failure before digest comparison; wrong digest alone cannot pass.' });
  await admission.probe(h, { definitionId: app.id, variant: 'missing-image', intended: { expectedDefinitionVersion: current.updateTime, expectedPreviewDigest: preview.buildDigest, changeLog: '受控缺镜像原生修订准入验证' } });
  h.check('Both build negatives and original revision admission leave complete package owner unchanged', same(await readDirectory(h, h.admin, collection), before));
};
handlers['F026-002'].transport = 'owner-api';


module.exports = { handlers, observeNativeCreate };
