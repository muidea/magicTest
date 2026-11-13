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
const absent = r => [200,404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
async function unsubscribe(h, actor, subscription, credential) {
  const r = subscription.resource, c = credential.resource, owner = h.tenantAdmin;
  if (r.unsubscribe || !same(actor.identity,r.actorIdentity) || actor.origin !== r.actorOrigin || !same(owner.identity,r.ownerIdentity) ||
      r.phase !== 'created' || c.phase !== 'created' || c.parentSubscriptionId !== r.id || c.endpointAuthorityCommands?.some(v => v.outcome === 'unknown')) throw new h.Blocked('Original subscriber retirement or actor unresolved; no replacement DELETE');
  const before = (await h.ok(owner,'GET',graph.subscriptions + r.id)).value;
  h.check('Original subscriber retirement preserves exact active subscription, service and immutable human identity',before.id === r.id && before.service.id === r.serviceId && before.status === 2 && same(before.subscriberRef,r.original.subscriberRef));
  // The Portal resource ID is serviceId; it resolves this actor's subscription.
  const intent = {method:'DELETE',route:'/portal/service/subscriptions/' + r.serviceId,actorIdentity:structuredClone(actor.identity),origin:actor.origin,
    before,credential:structuredClone(credential.value),outcome:'unknown'};
  r.unsubscribe = intent; h.persist();
  intent.response = await h.api(actor,intent.method,intent.route); h.persist();
  h.check('Exact original ordinary subscriber DELETE is acknowledged by public owner',h.good(intent.response),intent.response);
  const current = await h.api(owner,'GET',graph.subscriptions + r.id), all = await h.directory(owner,graph.subscriptions);
  h.check('Independent exact and complete owner reads prove only the original subscription absent',absent(current) && !all.some(v => v.id === r.id || v.service?.id === r.serviceId && same(v.subscriberRef,r.original.subscriberRef)),{current,all});
  const base = '/cas/namespaces/' + owner.identity.namespace + '/', client = await h.api(owner,'GET',base + 'oauth/clients/' + encodeURIComponent(credential.value.clientId));
  const endpoint = await h.api(owner,'GET',base + 'endpoints/' + credential.value.endpointId);
  const credentials = await h.directory(owner,base + 'oauth/clients/' + encodeURIComponent(credential.value.clientId) + '/credentials/');
  h.check('Independent CAS confirms exact original client disabled, Endpoint absent and original credential terminal after subscription aggregate retirement',
    h.good(client) && client.data.value.clientId === credential.value.clientId && client.data.value.status === 1 && absent(endpoint) &&
    credentials.some(v => v.id === credential.value.credentialId && v.clientId === credential.value.clientId && ['revoked','expired'].includes(v.status)) && credentials.every(v => v.status !== 'active'),{client,endpoint,credentials});
  intent.proof = {current,client,endpoint,credentials}; intent.outcome = 'confirmed';
  r.phase = 'deleted'; c.phase = 'deleted'; c.retiredByOriginalSubscription = {subscriptionId:r.id,proof:'Original subscriber acknowledged DELETE; exact independent Panel/CAS terminal facts, no credential DELETE replay.'}; h.persist();
}
handlers['F041-001'] = async h => {
  const approval = await graph.fixture(h,'subscription_approval_lifecycle',{requireApproval:true}), pending = await graph.subscribe(h,approval);
  h.check('Approval service creates original pending subscription without active lease',pending.value.status === 5,pending.value);
  const refused = await portalCall(h,h.user,approval);
  h.check('Pending original subscriber is refused at subscription admission without reaching upstream',refused.result.status === 403 && /subscription.*unavailable/.test(refused.result.data?.error?.message || '') && refused.received.length === 0,refused);
  await command(h,pending.resource,'PUT',graph.subscriptions + 'approve/' + pending.value.id,{},async response => {
    const after = (await h.ok(h.tenantAdmin,'GET',graph.subscriptions + pending.value.id)).value;
    h.check('Owner approval activates only exact original pending service/subscriber and future expiry',h.good(response) && after.id === pending.value.id && after.service.id === approval.service.id && same(after.subscriberRef,pending.value.subscriberRef) && after.status === 2 && after.expireTime > Date.now(),after);
  });
  const approvedKey = await graph.credential(h,pending,'approved-lifecycle-key'); await graph.succeeds(h,h.user,approval,approvedKey);
  const automatic = await graph.fixture(h,'subscription_automatic_lifecycle'), active = await graph.subscribe(h,automatic);
  h.check('No-approval service automatically enables exact original subscription with future expiry',active.value.status === 2 && active.value.expireTime > Date.now(),active.value);
  const automaticKey = await graph.credential(h,active,'automatic-lifecycle-key'); await graph.succeeds(h,h.user,automatic,automaticKey);
  for (const [f,s,key,peer,peerKey] of [[approval,pending,approvedKey,automatic,automaticKey],[automatic,active,automaticKey]]) {
    await unsubscribe(h,h.user,s,key);
    const denied = await graph.call(h,h.user,f,key.apiKey);
    h.check('Original retired subscription Key cannot continue invoking or reach its upstream', [401,403,404].includes(denied.status) && !f.up.requests.some(v => v.marker === denied.marker),denied);
    const portal = (await h.directory(h.user,'/portal/services/')).find(v => v.id === f.service.id);
    h.check('Original service remains visible and no active subscriber lease survives retirement',!!portal && (!portal.leaseTerm || portal.leaseTerm.status !== 2),portal);
    if (peer) await graph.succeeds(h,h.user,peer,peerKey);
  }
  await h.partial('Original pending approval, automatic activation, actual ApiKey invocation, ordinary subscriber retirement and independent Panel/CAS credential/Endpoint terminal facts are verified. Subscription rejection and renewal/credential lifetime propagation remain user-preserved capability gaps; no supported public commands were found, so the whole case is not passed.');
};
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
function quotaBoundary(h, probes, upstream, limit, diagnostic) {
  const markers = new Set(probes.map(p => p.marker));
  h.check('Finite quota burst contains distinct original request identities', markers.size === probes.length && probes.length > limit);
  const accepted = probes.filter(p => p.status === 200), refused = probes.filter(p => p.status === 429 && diagnostic.test(p.data?.error?.message || ''));
  h.check('Burst reaches the exact target quota gate with the declared number of successes and excess refusals', accepted.length === limit && refused.length === probes.length - limit, probes);
  const received = upstream.filter(r => markers.has(r.marker));
  h.check('Independent controlled upstream proves every accepted marker executes exactly once and refused markers have no execution',
    received.length === limit && accepted.every(p => p.data.marker === p.marker && received.filter(r => r.marker === p.marker && r.method === 'GET' && r.path === '/probe' && !r.authorizationPresent).length === 1) &&
    refused.every(p => !received.some(r => r.marker === p.marker)), { probes, received });
}
handlers['F046-001'] = async h => {
  const f = await graph.fixture(h,'management_quota_bypass',{dailyQuota:1}), owner = h.tenantAdmin;
  const subscriptions = async () => (await h.directory(owner,graph.subscriptions)).filter(s => s.service.id === f.service.id);
  h.check('New original management sample has no implicit subscription', (await subscriptions()).length === 0);
  managedSuccess(h,await managed(h,owner,f));
  h.check('Actual management success does not create an implicit subscriber or lease', (await subscriptions()).length === 0);
  const original = await graph.subscribe(h,f,owner), credential = await graph.credential(h,original);
  const baseline = await subscriptions();
  await graph.succeeds(h,owner,f,credential);
  const refused = async () => {
    const response = await graph.call(h,owner,f,credential.apiKey);
    h.check('Same original management account on subscription path reaches the exact exhausted daily quota and no upstream',
      response.status === 429 && /totalizator daily limit exceeded/.test(response.data?.error?.message || '') && !f.up.requests.some(r => r.marker === response.marker),response);
  };
  await refused();
  for (let i=0;i<2;i++) managedSuccess(h,await managed(h,owner,f));
  await refused();
  h.check('Explicit management calls preserve complete original subscription facts and do not restore its daily allowance',same(await subscriptions(),baseline));
  await graph.retireCredential(h,credential);await graph.retire(h,original);
  await h.partial('Original authorized management route succeeds before subscription and after the same account exhausts its actual subscription daily quota; no implicit subscription or quota reset, exact upstream markers and original subscription facts verified. Independent durable management-debug source/audit record is not proven by this route or aggregate metric, so whole F046-001 remains partial.');
};
async function quotaBurst(h, actor, f, credential, count, sameSecond = false) {
  const markers = Array.from({length:count}, () => crypto.randomBytes(12).toString('hex'));
  // Advance the real clock; never change server time or reset a counter.
  if (sameSecond) await actor.page.evaluate(() => new Promise(resolve => setTimeout(resolve, 1050 - Date.now() % 1000)));
  const probes = await actor.page.evaluate(async ({key,service,markers}) => Promise.all(markers.map(async marker => {
    const startedAt = Date.now();
    const response = await fetch('/api/v1/gateway/services/' + service + '/probe?marker=' + marker, {
      credentials:'omit',headers:{Authorization:'ApiKey ' + key},signal:AbortSignal.timeout(15000)
    });
    const data = await response.json();
    return {marker,status:response.status,data,startedAt,completedAt:Date.now()};
  })), {key:credential.apiKey,service:f.service.key,markers});
  h.observe({kind:'finite-original-key-quota-burst',actor:actor.identity,serviceId:f.service.id,subscriptionId:credential.resource.parentSubscriptionId,probes,received:f.up.requests.filter(r => markers.includes(r.marker))});
  if (sameSecond && new Set(probes.flatMap(p => [Math.floor(p.startedAt / 1000),Math.floor(p.completedAt / 1000)])).size !== 1) {
    const error = new h.Blocked('Original QPS burst crossed a real UTC second; admission boundary is not proven, no replacement burst or counter reset');
    error.quotaWindowUnproven = true; throw error;
  }
  return probes;
}
function graphOwner(h, subscription) {
  const owner = [h.admin,h.tenantAdmin,h.otherTenantAdmin].find(a => a && same(a.identity,subscription.resource.ownerIdentity));
  if (!owner) throw new h.Blocked('Exact original subscription owner unavailable');
  return owner;
}
handlers['F045-001'] = async h => {
  const qps = await graph.fixture(h,'qps_boundary',{maxQPS:2}), qpsSubscription = await graph.subscribe(h,qps), qpsKey = await graph.credential(h,qpsSubscription);
  let qpsWindowProven = false;
  try {
    quotaBoundary(h,await quotaBurst(h,h.user,qps,qpsKey,5,true),qps.up.requests,2,/qps exceeded/);
    qpsWindowProven = true;
  } catch (error) {
    if (!error.quotaWindowUnproven) throw error;
    h.observe({kind:'original-qps-window-unproven',reason:error.message,continuation:'Keep original window open; no replacement burst. Continue only independent daily allowance and lifecycle assertions.'});
  }
  // A distinct request in the next natural second, using the same Key.
  await h.user.page.evaluate(() => new Promise(resolve => setTimeout(resolve,1050 - Date.now() % 1000)));
  await graph.succeeds(h,h.user,qps,qpsKey);
  const daily = await graph.fixture(h,'daily_boundary',{dailyQuota:2}), original = await graph.subscribe(h,daily), key = await graph.credential(h,original);
  const originalBaseline = (await h.ok(graphOwner(h,original),'GET',graph.subscriptions + original.value.id)).value;
  const invalid = await graph.call(h,h.user,daily,'sk_' + crypto.randomBytes(24).toString('base64url'));
  h.check('Invalid original credential is rejected before quota admission without upstream effect',invalid.status === 401 && !daily.up.requests.some(r => r.marker === invalid.marker),invalid);
  quotaBoundary(h,await quotaBurst(h,h.user,daily,key,5),daily.up.requests,2,/totalizator daily limit exceeded/);
  const account = await h.createAs('tenantAdmin','/cas/namespaces/' + h.user.identity.namespace + '/accounts/',{
    account:h.state.prefix + '-quota-peer',displayName:'独立订阅配额成员',password:h.state.password,status:2,roleTemplateKeys:['portal-user']
  },'account');
  const peer = await h.login(account.account,h.state.password,h.user.identity.namespace,h.state.password + '-quota-peer');
  const peerSubscription = await graph.subscribe(h,daily,peer), peerKey = await graph.credential(h,peerSubscription);
  const peerBaseline = (await h.ok(graphOwner(h,peerSubscription),'GET',graph.subscriptions + peerSubscription.value.id)).value;
  quotaBoundary(h,await quotaBurst(h,peer,daily,peerKey,5),daily.up.requests,2,/totalizator daily limit exceeded/);
  const foreign = await graph.fixture(h,'foreign_daily_boundary',{dailyQuota:2},'otherTenantAdmin');
  const foreignSubscription = await graph.subscribe(h,foreign,h.otherTenantAdmin), foreignKey = await graph.credential(h,foreignSubscription);
  const foreignBaseline = (await h.ok(graphOwner(h,foreignSubscription),'GET',graph.subscriptions + foreignSubscription.value.id)).value;
  quotaBoundary(h,await quotaBurst(h,h.otherTenantAdmin,foreign,foreignKey,5),foreign.up.requests,2,/totalizator daily limit exceeded/);
  for (const [f,s,c,actor,baseline] of [[daily,original,key,h.user,originalBaseline],[daily,peerSubscription,peerKey,peer,peerBaseline],[foreign,foreignSubscription,foreignKey,h.otherTenantAdmin,foreignBaseline]]) {
    const exhausted = await graph.call(h,actor,f,c.apiKey);
    h.check('Other subscriptions or tenants cannot reset the original exhausted daily budget',exhausted.status === 429 && /totalizator daily limit exceeded/.test(exhausted.data?.error?.message || '') && !f.up.requests.some(r => r.marker === exhausted.marker),exhausted);
    h.check('Quota execution preserves exact original subscription identity and lease',same((await h.ok(graphOwner(h,s),'GET',graph.subscriptions + s.value.id)).value,baseline));
  }
  for (const [s,c] of [[qpsSubscription,qpsKey],[original,key],[peerSubscription,peerKey],[foreignSubscription,foreignKey]]) {
    await graph.retireCredential(h,c); await graph.retire(h,s);
  }
  await h.partial((qpsWindowProven ? 'Single-Gateway same-UTC-second QPS gate verified. ' : 'Original QPS request window crossed a UTC second and remains unproven; no replacement burst or reset. ') + 'Atomic daily admission, finite same-Key requests, a later natural-second successful request, invalid-credential non-consumption and independent subscription/tenant budgets verified by exact quota refusals and real upstream execution. Maximum concurrency is a user-preserved capability gap; multi-Gateway reservation and independent public counter reads are not proven. Natural daily rollover remains a separate special condition.');
};
for (const handler of Object.values(handlers)) { handler.actors = ['user', 'tenantAdmin', 'otherTenantAdmin']; handler.transport = 'owner-api'; }
module.exports = { handlers, managed, command, copiedProbe, unsubscribe, quotaBoundary, quotaBurst };
