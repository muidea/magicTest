// Exact current tenant/subject boundaries through formal published services.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const handlers = {};
async function managed(h, actor, f, source = 'managed-services') {
  const marker = crypto.randomBytes(12).toString('hex');
  const result = await h.api(actor, 'GET', '/gateway/' + source + '/' + f.service.key + '/probe?marker=' + marker);
  return { result, marker, received: f.up.requests.filter(r => r.marker === marker) };
}
function managedSuccess(h, probe) {
  h.check('Original authenticated management request reaches the owned external upstream exactly once', probe.result.status === 200 && probe.result.data.marker === probe.marker && probe.received.length === 1 && !probe.received[0].authorizationPresent && !probe.received[0].namespace && !probe.received[0].extDataPresent, probe);
}
// Restrict the copied example to the fixture's declared GET grammar. Never
// execute browser-provided shell text or interpolate a secret into a command.
function copiedProbe(example, origin, key) {
  const match = /^curl --request GET '([^']+)' \\\n  --header 'Authorization: ApiKey <API_KEY>'$/.exec(example);
  if (!match) throw new Error('Copied guide has unexpected request grammar');
  const url = new URL(match[1]);
  if (url.origin !== origin || url.pathname !== '/api/v1/gateway/services/' + key + '/probe' || url.searchParams.get('marker') !== '<marker>' || [...url.searchParams].length !== 1) throw new Error('Copied guide has unexpected tenant, service or parameter identity');
  return url;
}
handlers['F043-001'] = async h => {
  for (const [ownerName, actor] of [['tenantAdmin', h.user], ['otherTenantAdmin', h.otherTenantAdmin]]) {
    const f = await graph.fixture(h, 'copied_guide_' + ownerName.toLowerCase(), {}, ownerName);
    const subscription = await graph.subscribe(h, f, actor), credential = await graph.credential(h, subscription);
    const page = actor.page;
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: actor.origin });
    await page.goto(actor.origin + '/workbench/services/' + f.service.id + '/?source=portal', { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: '接入说明', exact: true }).click();
    const address = actor.origin + '/api/v1/gateway/services/' + f.service.key;
    const code = page.locator('code').filter({ hasText: address });
    await code.waitFor();
    await code.locator('..').getByRole('button', { name: '复制', exact: true }).click();
    h.check('Real clipboard receives current tenant public service address', await page.evaluate(() => navigator.clipboard.readText()) === address);
    const sample = page.locator('.ant-typography').filter({ has: page.locator('pre') });
    await sample.getByRole('button', { name: '复制', exact: true }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    const url = copiedProbe(copied, actor.origin, f.service.key), marker = crypto.randomBytes(12).toString('hex');
    url.searchParams.set('marker', marker);
    const result = await page.evaluate(async ({ url, key }) => {
      const response = await fetch(url, { credentials: 'omit', method: 'GET', headers: { Authorization: 'ApiKey ' + key }, signal: AbortSignal.timeout(15000) });
      return { status: response.status, value: await response.json() };
    }, { url: url.toString(), key: credential.apiKey });
    const received = f.up.requests.filter(r => r.marker === marker);
    h.observe({ kind: 'copied-current-tenant-guide', actor: actor.identity, origin: actor.origin, copied, result, received });
    h.check('Copied original current-Host example calls the actual subscription exactly once without browser cookies', result.status === 200 && result.value.marker === marker && received.length === 1 && received[0].path === '/probe' && !received[0].authorizationPresent, { result, received });
    h.check('Guide hides private controlled upstream and other tenant origin', !copied.includes(f.up.address) && !copied.includes((actor === h.user ? h.otherTenantAdmin : h.user).origin));
    await h.screenshot(actor, 'copied-guide-' + ownerName);
  }
};
handlers['F043-002'] = async h => {
  const f = await graph.fixture(h, 'catalog_guide'), subscription = await graph.subscribe(h, f);
  const page = h.user.page, address = h.user.origin + '/api/v1/gateway/services/' + f.service.key;
  await page.goto(h.user.origin + '/portal/services/', { waitUntil: 'networkidle' });
  const projection = (await h.directory(h.user, '/portal/services/')).find(item => item.id === f.service.id);
  h.check('Formal portal projection includes exact original subscribed service', !!projection && projection.leaseTerm?.status === 2, projection);
  await page.getByPlaceholder('搜索服务', { exact: true }).fill(projection.showName || projection.name);
  const card = page.locator('.ant-list-item').filter({ has: page.getByText(f.service.showName, { exact: true }) });
  await card.waitFor();
  h.check('Portal service catalogue exposes the original subscribed item without cluttering addresses', await card.count() === 1 && !(await card.innerText()).includes('/api/v1/gateway/') && !(await card.innerText()).includes(f.up.address));
  await h.screenshot(h.user, 'portal-service-catalogue');
  const manager = h.tenantAdmin.page;
  await manager.goto(h.tenantAdmin.origin + '/panel/hub/registry/', { waitUntil: 'networkidle' });
  await manager.getByPlaceholder('搜索服务名称', { exact: true }).fill(f.service.name);
  await manager.keyboard.press('Enter');
  const registered = manager.locator('.ant-list-item').filter({ hasText: f.service.name });
  await registered.getByText('已发布', { exact: true }).waitFor();
  await manager.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: h.tenantAdmin.origin });
  await registered.getByRole('button', { name: '复制', exact: true }).click();
  const copiedAddress = await manager.evaluate(() => navigator.clipboard.readText());
  h.observe({ kind: 'panel-published-address-copy', originalServiceId: f.service.id, copiedAddress });
  h.check('Panel published catalogue copies the exact current-Host public address despite visual ellipsis', copiedAddress === h.tenantAdmin.origin + '/api/v1/gateway/services/' + f.service.key && await registered.count() === 1 && !(await registered.innerText()).includes(f.up.address));
  await registered.getByText(f.service.showName, { exact: true }).click();
  const drawer = manager.locator('.ant-drawer-content').filter({ has: manager.locator('.ant-drawer-title').filter({ hasText: /^服务详情$/ }) });
  await drawer.getByText(h.tenantAdmin.origin + '/api/v1/gateway/services/' + f.service.key, { exact: true }).waitFor();
  h.check('Authorized service detail distinguishes private external upstream from public address', (await drawer.innerText()).includes(f.up.address));
  await h.screenshot(h.tenantAdmin, 'panel-published-address');
  await page.goto(h.user.origin + '/workbench/services/' + f.service.id + '/?source=portal', { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: '接入说明', exact: true }).click();
  await page.locator('code').filter({ hasText: address }).waitFor();
  h.check('Subscribed workbench guide shows original public address without private upstream', !(await page.locator('body').innerText()).includes(f.up.address));
  h.check('Directory navigation preserves exact subscription identity', same((await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + subscription.value.id)).value.subscriberRef, subscription.value.subscriberRef));
  await h.screenshot(h.user, 'subscribed-guide-address');
};
handlers['F039-002'] = async h => {
  const bare = { version: '1', operations: [{ key: 'probe', name: 'Undeclared response', method: 'GET', upstreamPath: '/probe', parameters: [{ name: 'marker', in: 'query', required: true, schema: { type: 'string' } }] }] };
  const f = await graph.fixture(h, 'undeclared_format', {}, 'tenantAdmin', bare), subscription = await graph.subscribe(h, f), credential = await graph.credential(h, subscription);
  const metadata = (await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id)).value;
  h.check('Public owner metadata keeps undeclared response schemas absent', !metadata.operations[0].responseBody && !Object.keys(metadata.operations[0].responses || {}).length, metadata);
  const document = await publicExport(h, f, 'undeclared-response-openapi');
  const operation = document.paths['/api/v1/gateway/services/' + f.service.key + '/probe'].get;
  h.check('Downloaded original OpenAPI explicitly reports undeclared response without invented fields', same(operation.responses, { default: { description: '响应格式未声明' } }));
  const page = h.user.page;
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载接口合同', exact: true }).click();
  const download = await pending;
  if (await download.failure()) throw new h.Blocked('Original public contract download failed');
  const bytes = h.fs.readFileSync(await download.path()), value = JSON.parse(bytes);
  h.observe({ kind: 'undeclared-public-contract', value, sha256: 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex') });
  h.check('Public contract export preserves undeclared format and excludes private upstream or credentials', !value.operations[0].responseBody && !Object.keys(value.operations[0].responses || {}).length && !bytes.toString().includes(f.up.address) && !bytes.toString().includes(credential.apiKey) && !bytes.toString().includes('upstreamPath'));
  await graph.succeeds(h, h.user, f, credential);
};
handlers['F046-003'] = async h => {
  const f = await graph.fixture(h, 'management_scope', { dailyQuota: 1 });
  const before = (await h.ok(h.tenantAdmin, 'GET', graph.services + f.service.id)).value;
  await h.ok(h.tenantAdmin, 'GET', '/panel/hub/service/debug/' + f.service.id);
  managedSuccess(h, await managed(h, h.tenantAdmin, f), h.tenantAdmin.identity.namespace);
  const originalCalls = f.up.requests.length;
  for (const actor of [h.user, h.otherTenantAdmin]) {
    h.inaccessible(await h.api(actor, 'GET', '/panel/hub/service/debug/' + f.service.id), 'Ordinary subscriber or foreign manager cannot read management debug metadata');
    const probe = await managed(h, actor, f);
    h.inaccessible(probe.result, 'Management debug requires original current tenant service governance permission');
    h.check('Denied management request never reaches upstream', probe.received.length === 0, probe);
  }
  h.check('All denied management requests leave upstream unchanged', f.up.requests.length === originalCalls);
  h.check('Management admission does not create implicit subscriptions', !(await h.directory(h.tenantAdmin, graph.subscriptions)).some(s => s.service.id === f.service.id));
  h.check('Management debug and refusals preserve exact service owner identity', same((await h.ok(h.tenantAdmin, 'GET', graph.services + f.service.id)).value, before));
  managedSuccess(h, await managed(h, h.tenantAdmin, f), h.tenantAdmin.identity.namespace);
};
async function portalCall(h, actor, f, headers = {}) {
  const marker = crypto.randomBytes(12).toString('hex'), route = '/api/v1/web/proxy/gateway/subscribed-services/' + f.service.key + '/probe?marker=' + marker;
  const result = await actor.page.evaluate(async ({ route, headers }) => {
    const r = await fetch(route, { headers, signal: AbortSignal.timeout(15000) });
    return { status: r.status, data: await r.json() };
  }, { route, headers });
  const received = f.up.requests.filter(r => r.marker === marker);
  h.observe({ kind: 'original-portal-subscription-call', actor: actor.identity, origin: actor.origin, route, headers, result, received });
  return { result, marker, received };
}
handlers['F046-002'] = async h => {
  const f = await graph.fixture(h, 'portal_quota', { dailyQuota: 1 });
  const without = await portalCall(h, h.tenantAdmin, f);
  h.check('Management account on Portal requires its own actual subscription', without.result.status === 403 && /subscription.*unavailable/.test(without.result.data?.error?.message || '') && without.received.length === 0, without);
  for (const actor of [h.tenantAdmin, h.user]) {
    const subscription = await graph.subscribe(h, f, actor);
    h.check('Formal owner acknowledges exact original Portal subscriber', subscription.value.status === 2 && subscription.value.subscriberRef.namespace === actor.identity.namespace);
    const accepted = await portalCall(h, actor, f);
    h.check('Original Portal subscriber has one successful in-quota upstream execution', accepted.result.status === 200 && accepted.result.data.marker === accepted.marker && accepted.received.length === 1, accepted);
    const headers = { 'X-Magic-Management-Debug': 'true', 'X-Mp-Management-Debug': 'true', 'X-Magic-Debug-Source': 'panel', 'X-Mp-Source': 'panel' };
    const refused = await portalCall(h, actor, f, headers);
    h.check('Portal account remains subject to actual daily quota despite management role or forged debug marks', refused.result.status === 429 && /totalizator daily limit exceeded/.test(refused.result.data?.error?.message || '') && refused.received.length === 0, refused);
    h.check('Quota rejection preserves original subscription subject and lease', same((await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + subscription.value.id)).value.subscriberRef, subscription.value.subscriberRef));
  }
  managedSuccess(h, await managed(h, h.tenantAdmin, f));
};
const contract = metadata => ({ apiVersion: metadata.apiVersion, version: metadata.version, digest: metadata.digest, operations: metadata.operations });
async function publicExport(h, f, label) {
  const page = h.user.page;
  await page.goto(h.user.origin + '/workbench/services/' + f.service.id + '/?source=portal', { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: '接入说明', exact: true }).click();
  const completed = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载 OpenAPI', exact: true }).click();
  const download = await completed;
  if (await download.failure()) throw new h.Blocked('Public OpenAPI download failed');
  const bytes = h.fs.readFileSync(await download.path()), value = JSON.parse(bytes);
  h.observe({ kind: 'public-openapi-download', label, filename: download.suggestedFilename(), sha256: 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'), value });
  h.check('Actual public download describes the exact service route and required query parameter', value.openapi === '3.0.3' && value.paths?.['/api/v1/gateway/services/' + f.service.key + '/probe']?.get?.parameters?.some(p => p.name === 'marker' && p.in === 'query' && p.required === true), value);
  h.check('Public download contains no private upstream address or credential', !bytes.toString().includes(f.up.address) && !bytes.toString().includes('clientSecret') && !bytes.toString().includes('upstreamPath'));
  await h.screenshot(h.user, label);
  return value;
}
async function command(h, resource, method, route, body, confirm) {
  const pending = resource.pendingServiceCommands ||= [];
  if (pending.some(c => !c.confirmed)) throw new h.Blocked('Original service command is unresolved; do not replay');
  const c = { method, route, body: structuredClone(body), confirmed: false };
  pending.push(c); h.persist();
  c.response = await h.api(h.tenantAdmin, method, route, body); h.persist();
  await confirm(c.response); c.confirmed = true; h.persist();
}
handlers['F039-003'] = async h => {
  const f = await graph.fixture(h, 'contract_republish'), s = await graph.subscribe(h, f), key = await graph.credential(h, s);
  const read = () => h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id).then(r => r.value);
  const before = await read(), originalDownload = await publicExport(h, f, 'original-published-openapi');
  await graph.succeeds(h, h.user, f, key);
  const current = (await h.ok(h.tenantAdmin, 'GET', graph.services + f.service.id)).value;
  const draft = JSON.parse(current.options).contract;
  draft.version = '2'; draft.operations[0].upstreamPath = '/revised'; draft.operations[0].name = 'Revised controlled probe';
  const serviceResource = h.state.resources.find(r => r.kind === 'service' && r.id === f.service.id);
  const publicationResource = h.state.resources.find(r => r.kind === 'publication' && r.id === f.publication.id);
  await command(h, serviceResource, 'PUT', graph.services + f.service.id, { expectedServiceVersion: current.updateTime, options: JSON.stringify({ contract: draft }) }, async response => {
    h.check('Exact original service draft edit acknowledged', h.good(response), response);
    const after = (await h.ok(h.tenantAdmin, 'GET', graph.services + f.service.id)).value;
    h.check('Independent owner read preserves original service identity and exact edited draft', after.id === current.id && after.key === current.key && same(JSON.parse(after.options).contract, draft));
  });
  h.check('Draft edit preserves complete originally published contract', same(contract(await read()), contract(before)));
  h.check('Real downloaded public document remains unchanged before publication', same(await publicExport(h, f, 'draft-retains-published-openapi'), originalDownload));
  await graph.succeeds(h, h.user, f, key);
  const publishRoute = '/panel/hub/publication/publish/' + f.publication.id;
  await command(h, publicationResource, 'PUT', publishRoute, {}, async response => {
    h.check('Changing a live published contract is explicitly refused until all scopes are disabled', !h.good(response) && /先停用.*发布范围/.test(response.data?.error?.message || ''), response);
    h.check('Rejected publish preserves exact original frozen contract', same(contract(await read()), contract(before)));
  });
  await command(h, publicationResource, 'PUT', graph.publications + f.publication.id, { ...f.payload, status: 3 }, async response => {
    h.check('Formal publication disable acknowledged', h.good(response), response);
    h.check('Independent owner confirms original publication disabled', (await h.ok(h.tenantAdmin, 'GET', graph.publications + f.publication.id)).value.status === 3);
  });
  const denied = await graph.call(h, h.user, f, key.apiKey);
  h.check('Original subscription cannot call while its publication is disabled', [403, 404].includes(denied.status) && !f.up.requests.some(r => r.marker === denied.marker), denied);
  await command(h, publicationResource, 'PUT', publishRoute, {}, async response => {
    h.check('Disabled scope can publish the newly versioned exact original service', h.good(response), response);
    const metadata = (await h.ok(h.tenantAdmin, 'GET', '/panel/hub/service/debug/' + f.service.id)).value;
    h.check('Independent owner metadata freezes the new interface version and digest', metadata.version === '2' && metadata.digest !== before.digest && metadata.apiVersion === before.apiVersion && metadata.operations[0].name === draft.operations[0].name, metadata);
  });
  const after = await read(), nextDownload = await publicExport(h, f, 'revised-published-openapi');
  h.check('Actual public document changes only after successful formal republish', nextDownload.info.version === after.version && after.version === '2' && !same(nextDownload, originalDownload));
  const invoked = await graph.call(h, h.user, f, key.apiKey), received = f.up.requests.filter(r => r.marker === invoked.marker);
  h.check('Original subscription Key consumes newly frozen routing after reenable', invoked.status === 200 && invoked.data.marker === invoked.marker && received.length === 1 && received[0].path === '/revised', { invoked, received });
  const retained = (await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + s.value.id)).value;
  h.check('Republish preserves original subscription subject, lease and identity', retained.id === s.value.id && retained.expireTime === s.value.expireTime && same(retained.subscriberRef, s.value.subscriberRef));
};
handlers['F045-003'] = async h => {
  const a = await graph.fixture(h, 'key_scope_a'), b = await graph.fixture(h, 'key_scope_b');
  const subscription = await graph.subscribe(h, a), credential = await graph.credential(h, subscription);
  await graph.succeeds(h, h.user, a, credential);
  const otherSubscription = await graph.subscribe(h, b), otherCredential = await graph.credential(h, otherSubscription);
  await graph.succeeds(h, h.user, b, otherCredential);
  const denied = await graph.call(h, h.user, b, credential.apiKey);
  h.check('Existing valid service A Key is rejected by existing service B subscription boundary', denied.status === 403 && /subscription credential does not belong to target service/.test(denied.data?.error?.message || ''), denied);
  h.check('Cross-service original Key never reaches upstream', !a.up.requests.some(r => r.marker === denied.marker));
  const marker = crypto.randomBytes(12).toString('hex'), foreign = h.otherTenantAdmin.identity.namespace;
  const route = '/api/v1/gateway/services/' + a.service.key + '/probe?marker=' + marker;
  const response = await h.user.page.evaluate(async ({ route, key, foreign }) => {
    const r = await fetch(route, { credentials: 'omit', headers: { Authorization: 'ApiKey ' + key, 'X-Mp-Namespace': foreign, 'X-Namespace': foreign, 'X-Mp-Entity-Ext-Data': JSON.stringify({ namespace: foreign, actorSubject: 'account:1' }) }, signal: AbortSignal.timeout(15000) });
    return { status: r.status, data: await r.json() };
  }, { route, key: credential.apiKey, foreign });
  const received = a.up.requests.filter(r => r.marker === marker);
  h.observe({ kind: 'forged-service-context-probe', origin: h.user.origin, route, foreign, response, received });
  h.check('Forged tenant context is refused or sanitized before external forwarding', response.status === 200 ? response.data.marker === marker && received.length === 1 && !received[0].namespace : [401, 403, 404].includes(response.status) && received.length === 0, { response, received });
  h.check('No upstream request carries forged namespace or raw identity envelope', received.every(r => r.namespace !== foreign && !r.extDataPresent && !r.authorizationPresent), received);
  await graph.succeeds(h, h.user, a, credential);
  await h.partial('External upstream isolation is proven, but internal upstream verified-tenant propagation requires a formally installed internal capability fixture. Do not infer it from stripped external headers.');
};
for (const handler of Object.values(handlers)) { handler.actors = ['user', 'tenantAdmin', 'otherTenantAdmin']; handler.transport = 'owner-api'; }
module.exports = { handlers, managed, command, copiedProbe };
