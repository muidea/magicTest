const { waitLoginForm, waitLoginError, observeLogin } = require('./login_readiness.cjs');
const crypto = require('node:crypto');
const { isDeepStrictEqual } = require('node:util');
const { sameAuthority, sameAccounts } = require('./authority_snapshot.cjs');
const { negativeBrandWrite, negativeCreate } = require('./negative_mutations.cjs');
const handlers = {};
const fixturesDir = h => h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression');
const accountBase = h => '/cas/namespaces/' + h.state.fixtures.tenantA.name + '/accounts/';
const definitionBase = '/panel/application/definitions/';
const policy = '/panel/session-policy/';
const retention = '/panel/operations/log-retention/';
async function same(h, actor, route, before, label) { const after = (await h.ok(actor, 'GET', route)).value; h.check(label, JSON.stringify(after) === JSON.stringify(before)); }
async function model(h) {
  if (!h.state.fixtures.model) {
    const body = JSON.parse(h.fs.readFileSync(h.path.join(fixturesDir(h), 'fixture-definition-create-request.json')));
    Object.assign(body, { uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-model', showName: '常规回归模型', pkgPrefix: h.state.prefix });
    h.state.fixtures.model = await h.create(definitionBase, body, 'definition'); h.persist();
  }
  return (await h.ok(h.admin, 'GET', definitionBase + h.state.fixtures.model.id)).value;
}
handlers['F003-001'] = async h => {
  const n = h.need('tenantA');
  const original = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + n.id)).value;
  const resource = h.state.resources.find(r => r.kind === 'namespace' && r.id === n.id && r.name === n.name);
  const availability = require('./namespace_availability.cjs');
  const panelPeer = await h.login(h.credentials.account, h.credentials.password);
  const unaffected = [h.admin, panelPeer, h.otherTenantAdmin];
  const targetActors = [h.user, h.tenantAdmin];
  const anonymous = await h.anonymous(n.name), unavailableProbes = [];
  const protectedContext = '/system/context/?surface=portal';
  for (const actor of targetActors) {
    await h.ok(actor, 'GET', protectedContext);
    await h.ok(actor, 'GET', '/api/v1/web/session/');
  }
  const assertUnrelatedSessions = async () => {
    for (const actor of unaffected) {
      const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
      h.check('Unrelated original login survives namespace mutation', session.homeNamespace === actor.identity.namespace && session.account.account === actor.identity.account);
    }
  };
  let current = original;
  try {
    for (const status of [1, 2]) {
      const saved = await availability.change(h, resource, current, { ...current, description: '常规回归空间编辑', scope: [], status });
      await assertUnrelatedSessions();
      current = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + n.id)).value;
      h.check('Space settings independently persisted', current.description === '常规回归空间编辑' && current.status === status && saved.id === n.id);
      let entry = await h.publicGet(anonymous, '/api/v1/web/session/');
      for (let retry = 0; retry < 5 && (status === 1 ? entry.status !== 404 : entry.status === 404); retry++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        entry = await h.publicGet(anonymous, '/api/v1/web/session/');
      }
      h.check('Watched tenant BFF entry converges to acknowledged availability before credential assertions', status === 1 ? entry.status === 404 : entry.status !== 404, entry);
      if (status === 1) {
        // The user requires HTTP 404 for every request to an unavailable tenant.
        // Probe representative route families; do not infer this from one BFF URL.
        for (const route of ['/', '/portal/', '/api/v1/web/session/', '/api/v1/cas/registration/policy/public/', '/.well-known/openid-configuration', '/api/v1/system/notifications/', '/api/v1/regression-unknown/']) {
          const response = await h.publicGet(anonymous, route);
          unavailableProbes.push({ route, status: response.status });
        }
      }
      for (const actor of targetActors) {
        const access = await h.publicGet(actor, '/api/v1/web/proxy' + protectedContext);
        const authenticationDenied = access.status === 401 || [5, 11, 12, 22].includes(access.data?.error?.code);
        // Disabled namespaces withdraw their ingress. The same live route was
        // proved above; 404 here proves entry withdrawal, not token revocation.
        if (status === 1) unavailableProbes.push({ route: protectedContext, actor: actor.identity, status: access.status });
        else {
          h.check('Reenable does not revive target old credentials', authenticationDenied, access);
          const oldSession = await h.publicGet(actor, '/api/v1/web/session/');
          h.check('Reenabled BFF rejects original target session', oldSession.status === 401 || [5, 11, 12, 22].includes(oldSession.data?.error?.code), oldSession);
        }
      }
      if (status === 2) {
        const fresh = await h.login(h.user.identity.account, h.user.password, n.name);
        const freshAccess = await h.api(fresh, 'GET', protectedContext);
        h.check('Reenabled namespace accepts fresh login', h.good(freshAccess));
        await assertUnrelatedSessions();
      }
    }
    const list = (await h.ok(h.admin, 'GET', '/cas/namespaces/?_pageSize=100')).values;
    h.check('Namespace directory contains exact resource', list.some(x => x.id === n.id && x.name === n.name));
    h.check('Unavailable tenant uniformly returns HTTP 404 across public pages, BFF, CAS, discovery, notices and unknown routes', unavailableProbes.length === 9 && unavailableProbes.every(x => x.status === 404), unavailableProbes);
  } finally {
    await h.authorizedAdmin();
    await availability.restore(h, resource);
  }
};
handlers['F003-001'].transport = 'owner-api';
handlers['F003-002'] = async h => {
  const root = (await h.ok(h.admin, 'GET', '/cas/namespaces/?_pageSize=100')).values.find(x => x.name === h.credentials.namespace);
  for (const actor of [h.user, h.tenantAdmin]) {
    h.denied(await h.api(actor, 'PUT', '/panel/namespace-onboardings/' + root.id, { expectedVersion: root.updateTime, description: 'Forbidden change', scope: ['*'], status: root.status, startTime: root.startTime, expireTime: root.expireTime }), 'Ordinary namespace cannot manage platform root');
  }
  await same(h, h.admin, '/cas/namespaces/' + root.id, root, 'Root namespace remains exact');
};
handlers['F004-002'] = async h => {
  const a = h.need('tenantA'), b = h.need('tenantB');
  const rows = (await h.ok(h.tenantAdmin, 'GET', '/cas/namespaces/' + a.name + '/accounts/?_pageSize=100')).values;
  h.check('Managed namespace administrator sees own member', rows.some(x => x.id === h.state.fixtures.user.id));
  h.denied(await h.api(h.tenantAdmin, 'GET', '/cas/namespaces/' + b.name + '/accounts/'), 'Other namespace directory denied');
  const targets = [];
  for (const n of [a, b]) {
    const collection = '/cas/namespaces/' + n.name + '/accounts/';
    const target = await h.create(collection, { account: h.state.prefix + '-scope-' + n.name.slice(-1), displayName: '范围核对账号', password: h.state.password, email: '', description: '', status: 2, roleTemplateKeys: ['portal-user'] }, 'account');
    const before = (await h.ok(h.admin, 'GET', collection + target.id)).value;
    targets.push({ n, collection, target, before });
  }
  for (const { n, collection, target, before } of targets) {
    const payload = { account: before.account, displayName: '已核对管理范围', email: before.email || '', description: '常规回归账号管理范围', status: before.status, roleTemplateKeys: ['portal-user'] };
    const response = await h.api(h.tenantAdmin, 'PUT', collection + target.id, payload);
    if (n.id === a.id) {
      h.check('Authorized namespace administrator can update own account resource', h.good(response), response);
      const after = (await h.ok(h.admin, 'GET', collection + target.id)).value;
      h.check('CAS independently persists in-scope change and original ownership', after.id === before.id && after.account === before.account && after.namespace === before.namespace && after.displayName === payload.displayName && after.description === payload.description, after);
    } else {
      h.denied(response, 'Same original administrator cannot mutate other namespace account');
      const after = (await h.ok(h.admin, 'GET', collection + target.id)).value;
      h.check('Outside account remains exactly unchanged', sameAuthority(before, after));
    }
  }
  const session = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
  h.check('Account original namespace unchanged', session.homeNamespace === a.name);
};
handlers['F004-003'] = async h => {
  const body = { account: h.need('user').account, displayName: 'Duplicate test', password: h.state.password, status: 2, roleTemplateKeys: ['portal-user'] };
  const before = await h.directory(h.admin, accountBase(h));
  for (const [index, payload] of [body, { ...body, account: '' }, { ...body, account: h.state.prefix + '-invalid', password: '' }].entries()) {
    const r = await h.api(h.admin, 'POST', accountBase(h), payload);
    if (h.good(r) && r.data.value?.id) h.owned(accountBase(h), r.data.value, 'unexpected-account');
    if (index === 0) h.check('Duplicate account explicitly rejected by CAS', r.status === 200 && [6, 7].includes(r.data.error?.code) && r.data.error.message === 'Account ' + body.account + ' already exists' && r.data.value == null, r);
    else h.invalid(r, 'Empty account/empty password rejected');
    h.check('Response does not expose submitted password', !JSON.stringify(r).includes(h.state.password));
  }
  const after = await h.directory(h.admin, accountBase(h));
  h.check('No duplicate or invalid accounts created', sameAccounts(before, after));
};
handlers['F010-002'] = async h => {
  const other = h.need('tenantB').name;
  const r = await h.api(h.user, 'GET', '/cas/namespaces/' + other + '/accounts/?namespace=' + other, undefined, { 'X-Namespace': other, 'X-Magic-Subject': 'account:1', 'X-Magic-Ext-Data': JSON.stringify({ namespace: other, actorSubject: 'account:1' }), 'X-Magic-Management-Debug': 'true' });
  h.denied(r, 'Forged namespace and identity headers do not grant authority');
  const session = (await h.ok(h.user, 'GET', '/api/v1/web/session/')).value;
  h.check('Original namespace remains authoritative', session.homeNamespace === h.need('tenantA').name);
};
handlers['F011-002'] = async h => {
  const m = await model(h), body = JSON.parse(h.fs.readFileSync(h.path.join(fixturesDir(h), 'fixture-definition-create-request.json')));
  const snapshot = rows => [...rows].sort((a, b) => a.id - b.id);
  const before = await h.directory(h.admin, definitionBase);
  const parent = h.state.resources.find(r => r.kind === 'definition' && r.id === m.id && r.creation?.ownershipConfirmed);
  if (!parent || parent.definitionRejections?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original definition rejection intent unresolved or owner not confirmed; no replay');
  for (const [payload, code, message] of [
    [{ ...body, uuid: m.uuid, name: m.name }, 7],
    [{ ...body, uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-bad', pkgPrefix: '../invalid' }, 4, 'model application package prefix is invalid'],
    [{ ...body, uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-nostorage', storage: { required: true, engine: '', slots: [] } }, 4, 'only PostgreSQL application storage is supported']
  ]) {
    const command = { route: definitionBase, body: payload, outcome: 'unknown' };
    (parent.definitionRejections ||= []).push(command); h.persist();
    const r = await h.api(h.admin, 'POST', definitionBase, payload);
    command.response = r; h.persist();
    if (h.good(r) && r.data.value?.id) h.owned(definitionBase, r.data.value, 'unexpected-definition');
    const unchanged = isDeepStrictEqual(snapshot(before), snapshot(await h.directory(h.admin, definitionBase))) && isDeepStrictEqual((await h.ok(h.admin, 'GET', definitionBase + m.id)).value, m);
    const targetRejected = [200, 400].includes(r.status) && r.data?.error?.code === code && (!message || r.data.error.message === message) && r.data.value == null;
    if (targetRejected && unchanged) { command.outcome = 'rejected-and-unchanged'; h.persist(); }
    h.check('Invalid create reaches its exact duplicate/prefix/storage owner validation and preserves every original definition', command.outcome === 'rejected-and-unchanged', r);
  }
  const after = await h.directory(h.admin, definitionBase);
  h.check('Rejected definitions preserve the complete original directory, including other legitimate cases', isDeepStrictEqual(snapshot(before), snapshot(after)));
  h.check('Independent original model remains exact after rejected creates', isDeepStrictEqual((await h.ok(h.admin, 'GET', definitionBase + m.id)).value, m));
};
handlers['F011-003'] = async h => {
  const m = await model(h), before = (await h.ok(h.admin, 'GET', definitionBase + m.id)).value;
  for (const actor of [h.user, h.tenantAdmin]) {
    h.inaccessible(await h.api(actor, 'GET', definitionBase + m.id), 'Cross namespace definition not readable');
    h.inaccessible(await h.api(actor, 'PUT', definitionBase + m.id, { expectedDefinitionVersion: m.updateTime, description: 'MUST NOT PERSIST' }), 'Unauthorized definition edit denied');
  }
  await same(h, h.admin, definitionBase + m.id, before, 'Rejected edits preserve definition');
};
handlers['F016-003'] = async h => {
  const m = await model(h), route = definitionBase + m.id + '/function-blocks', before = (await h.ok(h.admin, 'GET', route)).value;
  const cas = '/cas/namespaces/' + h.credentials.namespace + '/';
  const template = await h.create(cas + 'role-templates/', { key: h.state.prefix + '-publisher', name: '回归只读应用作者', description: '复用应用发布负责人，仅读取应用库和模型草稿，不授予定义编辑权', subjectType: 'account', roleRefs: [{ module: '/modules/kernel/runner', key: 'management-application-publisher' }], applicationAccess: [], status: 2 }, 'role-template');
  const account = await h.create(cas + 'accounts/', { account: h.state.prefix + '-reader', displayName: '回归应用库只读成员', password: h.state.password, status: 2, roleTemplateKeys: [template.key] }, 'account');
  const reader = await h.login(account.account, h.state.password, h.credentials.namespace, h.state.password + 'R');
  const readable = (await h.ok(reader, 'GET', route)).value;
  h.check('Same namespace readonly subject can read actual library', JSON.stringify(readable) === JSON.stringify(before));
  const draftRoute = definitionBase + m.id + '/model-draft';
  const draft = (await h.ok(h.admin, 'GET', draftRoute)).value;
  const payload = JSON.parse(h.fs.readFileSync(h.path.join(fixturesDir(h), 'fixture-draft-atomic-save-request.json')));
  payload.expectedDefinitionVersion = before.definitionVersion;
  payload.entities[0].pkgPath = '/' + h.state.prefix;
  for (const actor of [reader, h.user, h.tenantAdmin]) {
    h.inaccessible(await h.api(actor, 'PUT', route, { expectedDefinitionVersion: before.definitionVersion, content: before.content }), 'Readonly/other namespace cannot edit script library');
    h.inaccessible(await h.api(actor, 'PUT', draftRoute, payload), 'Binding/model-draft save does not bypass definition editing authority');
  }
  await same(h, h.admin, route, before, 'Library is unchanged');
  await same(h, h.admin, draftRoute, draft, 'Rejected binding saves leave complete model draft unchanged');
};
handlers['F037-002'] = async h => {
  const n = h.need('tenantA'), collection = '/panel/hub/services/';
  // This case protects governance versus subscription authority. It never
  // invokes the upstream, so registration needs no external running service.
  const address = 'https://regression.invalid/api';
  const service = await h.createAs('tenantAdmin', collection, { key: h.state.prefix + '_auth', name: h.state.prefix + '_auth', showName: '回归服务权限', description: '受控服务定义；本用例不调用上游', catalog: 'regression', providerType: 'external', providerKey: '', status: 2, accessMode: 'gateway', address, options: JSON.stringify({ debug: { authMode: 'bearer', operations: [{ key: 'probe', name: 'probe', method: 'GET', pathTemplate: address + '/probe', parameters: [] }] } }) }, 'service');
  const publication = await h.createAs('tenantAdmin', '/panel/hub/publications/', { service: { id: service.id }, status: 1, visibleScope: n.name, allowSubscription: true, requireApproval: false, maxSubscriptions: 0, maxQPS: 0, dailyQuota: 0 }, 'publication');
  await h.ok(h.tenantAdmin, 'PUT', '/panel/hub/publication/publish/' + publication.id);
  const visible = (await h.ok(h.user, 'GET', '/portal/services/?_pageSize=100')).values;
  h.check('Original ordinary user sees the actual published service', visible.some(x => x.id === service.id));
  const requestId = crypto.randomBytes(16).toString('hex');
  h.state.fixtures.subscriptionRequest = { requestId, service: service.id, namespace: n.name }; h.persist();
  const subscribed = await h.ok(h.user, 'POST', '/portal/service/subscriptions/', { requestId, service: service.id, leaseTerm: 1 });
  h.check('Original ordinary user receives active subscription', subscribed.value?.id === service.id && subscribed.value?.leaseTerm?.status === 2, subscribed);
  const subscriptions = (await h.ok(h.tenantAdmin, 'GET', '/panel/hub/subscriptions/?_pageSize=100')).values;
  const subscription = subscriptions.find(x => x.service?.id === service.id && x.subscriberRef?.accountId === h.need('user').id && x.namespace === n.name);
  h.check('Owner independently confirms exact ordinary subscriber and service', subscription?.status === 2, subscription);
  h.owned('/panel/hub/subscriptions/', subscription, 'subscription', 'tenantAdmin');
  const before = (await h.ok(h.tenantAdmin, 'GET', collection + service.id)).value;
  h.denied(await h.api(h.user, 'PUT', collection + service.id, { showName: 'MUST NOT CHANGE', description: before.description, icon: before.icon, catalog: before.catalog, address: before.address, options: before.options, expectedServiceVersion: before.updateTime }), 'Subscription never grants service definition editing');
  h.denied(await h.api(h.user, 'DELETE', collection + service.id), 'Subscription never grants service definition deletion');
  await same(h, h.tenantAdmin, collection + service.id, before, 'Rejected subscriber writes preserve real service definition');
  const retained = (await h.ok(h.tenantAdmin, 'GET', '/panel/hub/subscriptions/' + subscription.id)).value;
  h.check('Rejected governance requests preserve original active subscription', retained.id === subscription.id && retained.status === 2 && retained.subscriberRef?.accountId === h.need('user').id);
};
handlers['F047-003'] = async h => {
  const db = (await h.ok(h.admin, 'GET', '/panel/operations/database-instances/?_pageSize=100')).values[0];
  if (!db) throw new h.Blocked('No current configured database resource');
  for (const actor of [h.user, h.tenantAdmin]) {
    h.denied(await h.api(actor, 'GET', '/panel/operations/database-instances/' + db.id), 'Database details denied without resource permission');
    h.denied(await h.api(actor, 'GET', '/panel/operations/database-instances/' + db.id + '/explorer/settings'), 'Sensitive resource configuration denied');
  }
  h.check('Resource catalog does not expose password', !db.password || db.password === '******');
};
handlers['F055-003'] = async h => {
  const route = '/panel/namespace-branding/', n = h.need('tenantA');
  const before = (await h.ok(h.admin, 'GET', route)).value;
  const own = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  h.check('New tenant branding has no preexisting override', own.namespace === n.name && own.override == null);
  // Register cleanup intent before the write: an unknown write result still needs owner cleanup.
  h.owned(route, { id: '', name: n.name }, 'namespace-branding', 'tenantAdmin');
  const body = { platformName: h.state.prefix + ' 回归品牌', platformShortName: '回归', loginTitle: '回归登录', loginSubtitle: '', footerText: '', primaryColor: '#1677ff', logoAltText: '', backgroundPosition: 'center', backgroundOverlayOpacity: null, sloganMode: 'inherit', sloganAltText: '', brandingFeatureMode: 'inherit', brandingFeatureAltText: '', expectedResourceVersion: 0 };
  await h.ok(h.tenantAdmin, 'PUT', route, body);
  const saved = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  h.check('Tenant customizer successfully changes only own brand', saved.namespace === n.name && saved.override?.platformName === body.platformName && saved.resolved?.platformName === body.platformName);
  h.denied(await h.api(h.user, 'PUT', route, { ...body, expectedResourceVersion: saved.override.resourceVersion }), 'Ordinary tenant member cannot edit branding with valid payload');
  // Query/header hints are not target selection. Prove the result stays local,
  // then address the actual platform host with the unmodified original session.
  const hinted = await negativeBrandWrite(h, h.tenantAdmin, route, before, { ...body, expectedResourceVersion: saved.override.resourceVersion }, { requestRoute: route + '?namespace=' + encodeURIComponent(h.credentials.namespace), headers: { 'X-Namespace': h.credentials.namespace }, permittedNamespace: n.name });
  if (h.good(hinted)) h.check('Forged target hints cannot expand branding namespace', hinted.data.value?.namespace === n.name && hinted.data.value?.override?.namespace === n.name);
  else h.denied(hinted, 'Forged target hints rejected');
  await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/');
  const addressed = await h.sessionAtOrigin(h.tenantAdmin, h.admin.origin);
  const globalWrite = await negativeBrandWrite(h, addressed, route, before, { ...body, platformName: h.state.prefix + '-forbidden-global-' + crypto.randomBytes(6).toString('hex'), expectedResourceId: before.override?.id || 0, expectedResourceVersion: before.override?.resourceVersion || 0 });
  h.check('Original tenant session cannot edit actual platform global branding', [401, 403].includes(globalWrite.status) || [5, 11, 12, 22].includes(globalWrite.data?.error?.code), globalWrite);
  const surviving = (await h.ok(h.tenantAdmin, 'GET', '/api/v1/web/session/')).value;
  h.check('Original tenant session remains valid at its own host', surviving.homeNamespace === n.name && surviving.account.account === h.tenantAdmin.identity.account);
  const after = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  h.check('Own brand remains confined to original namespace', after.namespace === n.name && after.override?.platformName === body.platformName);
  await same(h, h.admin, route, before, 'Global branding remains exact');
};
handlers['F056-002'] = async h => {
  const before = (await h.ok(h.admin, 'GET', policy)).value;
  for (const timeoutMinutes of [0, -1, 999999999]) h.invalid(await h.api(h.admin, 'PUT', policy, { timeoutMinutes, expectedResourceVersion: before.override?.resourceVersion || 0 }), 'Invalid session duration rejected');
  h.invalid(await h.api(h.admin, 'PUT', policy, { timeoutMinutes: 120, expectedResourceVersion: 922337203685477 }), 'Stale resource version rejected');
  await same(h, h.admin, policy, before, 'Invalid duration/version does not change effective policy');
};
handlers['F056-003'] = async h => {
  const before = (await h.ok(h.admin, 'GET', policy)).value;
  h.denied(await h.api(h.user, 'PUT', policy, { timeoutMinutes: 120, expectedResourceVersion: 0 }), 'Ordinary subject cannot save session policy');
  await same(h, h.admin, policy, before, 'Unauthorized policy changes do not change effective policy');
};
handlers['F058-003'] = async h => {
  const before = (await h.ok(h.admin, 'GET', retention)).value;
  for (const actor of [h.user, h.tenantAdmin]) h.denied(await h.api(actor, 'PUT', retention, { expectedResourceVersion: 0, policies: [] }), 'Non-default namespace / unprivileged subject cannot change global retention');
  await same(h, h.admin, retention, before, 'Global retention remains exact');
};
handlers['F051-003'] = async h => {
  const collection = '/panel/infra/catalogs/';
  const c = await h.create(collection, { name: h.state.prefix + '-catalog', description: 'temporary regression', parent: null }, 'catalog');
  const cas = '/cas/namespaces/' + h.credentials.namespace + '/';
  const roles = await h.directory(h.admin, cas + 'roles/');
  // Public Base permission bits: read=4, write=2, delete=8.
  const catalogPrivileges = role => role.privilege?.filter(p => p.module === '/modules/kernel/runner' && p.uriPath === '/panel/catalogs/') || [];
  const readerRole = roles.find(role => role.module === '/modules/kernel/runner' && role.key === 'management-catalog-viewer' && role.humanAssignable && role.status === 2 && catalogPrivileges(role).some(p => p.value & 4) && !catalogPrivileges(role).some(p => p.value & (2 | 8)));
  if (!readerRole) {
    h.denied(await negativeCreate(h, h.user, collection, { name: h.state.prefix + '-forbidden-' + crypto.randomBytes(6).toString('hex'), description: '', parent: null }, 'catalog'), 'Unprivileged subject cannot write category');
    h.denied(await h.api(h.user, 'PUT', collection + c.id, { name: 'MUST NOT CHANGE', description: c.description, parent: null }), 'Unprivileged subject cannot write category');
    await same(h, h.admin, collection + c.id, c, 'Rejected writes leave category unchanged');
    await h.partial('DELIVERY-CATALOG-READER: complete current CAS catalogue lacks the source-declared Runner catalog reader. Require a paired candidate and formal Installer/CAS synchronization proof; do not create roles through ordinary HTTP or replay initialization.');
  }
  const template = await h.create(cas + 'role-templates/', { key: h.state.prefix + '-catalog-reader', name: '回归分类只读成员', description: '复用owner声明的分类只读角色', subjectType: 'account', roleRefs: [{ module: readerRole.module, key: readerRole.key }], applicationAccess: [], status: 2 }, 'role-template');
  const account = await h.create(cas + 'accounts/', { account: h.state.prefix + '-catalog-reader', displayName: '回归分类只读成员', password: h.state.password, status: 2, roleTemplateKeys: [template.key] }, 'account');
  const reader = await h.login(account.account, h.state.password, h.credentials.namespace, h.state.password + 'C');
  const rows = (await h.ok(reader, 'GET', collection + '?_pageSize=100')).values;
  h.check('Same namespace readonly subject sees exact category', rows.some(x => x.id === c.id && x.name === c.name));
  await h.ok(reader, 'GET', collection + c.id);
  h.denied(await h.api(reader, 'DELETE', collection + c.id), 'Same namespace readonly subject cannot delete category');
  h.denied(await negativeCreate(h, reader, collection, { name: h.state.prefix + '-forbidden-' + crypto.randomBytes(6).toString('hex'), description: '', parent: null }, 'catalog'), 'Same namespace readonly subject cannot write category');
  h.denied(await h.api(reader, 'PUT', collection + c.id, { name: 'MUST NOT CHANGE', description: c.description, parent: null }), 'Same namespace readonly subject cannot write category');
  const after = (await h.ok(h.admin, 'GET', collection + c.id)).value;
  h.check('Unauthorized writes preserve category name', after.name === c.name);
};
for (const id of ['F003-001', 'F003-002', 'F004-002', 'F004-003', 'F010-002', 'F011-003', 'F016-003', 'F047-003', 'F051-003', 'F055-003', 'F056-003', 'F058-003']) handlers[id].actors = ['user', 'tenantAdmin'];
handlers['F003-001'].actors = ['user', 'tenantAdmin', 'otherTenantAdmin'];
handlers['F037-002'].actors = ['user', 'tenantAdmin'];

handlers['F001-002'] = async h => {
  const actor = h.admin, observed = [];
  const watch = request => { const pathname = new URL(request.url()).pathname; if (pathname.startsWith('/oauth/') || pathname === '/api/v1/web/auth/login') observed.push(pathname); };
  const cookies = async () => (await actor.context.cookies(actor.origin)).filter(x => x.httpOnly).map(x => [x.name, x.value]).sort((a, b) => a[0].localeCompare(b[0]));
  const before = await cookies();
  h.check('Original BFF session has protected cookies', before.length > 0);
  actor.page.on('request', watch);
  try {
    for (let cycle = 0; cycle < 3; cycle++) for (const surface of ['panel', 'portal']) {
      await actor.page.goto(actor.origin + '/' + surface + '/', { waitUntil: 'networkidle', timeout: 30000 });
      h.check('Switch reaches requested ' + surface, new URL(actor.page.url()).pathname.startsWith('/' + surface));
      h.check('Switch never presents login credentials', await actor.page.locator('input[name=password]').count() === 0);
      const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
      h.check('Switch preserves original account and tenant', session.account.account === actor.identity.account && session.homeNamespace === actor.identity.namespace);
    }
    h.check('No new OAuth authorization transaction during six switches', observed.length === 0, observed);
    h.check('BFF session cookies are reused during switches', JSON.stringify(before) === JSON.stringify(await cookies()));
    await h.screenshot(actor, 'shared-session');
  } finally { actor.page.off('request', watch); }
};

async function fits(h, page, locator, label) {
  await locator.waitFor({ state: 'visible', timeout: 30000 });
  h.check(label + ' is visible', await locator.isVisible());
  const box = await locator.boundingBox(), width = page.viewportSize().width;
  h.check(label + ' fits viewport width', box && box.x >= -1 && box.width > 0 && box.x + box.width <= width + 1, box);
}
handlers['F001-004'] = async h => {
  for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    const context = await h.browser.newContext({ ignoreHTTPSErrors: true, viewport });
    const page = await context.newPage(), actor = { context, page, origin: h.user.origin };
    try { await observeLogin(actor, {
      record: h.observe,
      capture: () => h.screenshot(actor, 'login-layout-unresolved-' + viewport.width),
    }, async () => {
      await page.goto(actor.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle', timeout: 30000 });
      const { account, password, submit } = await waitLoginForm(page);
      await fits(h, page, account, 'Account field'); await fits(h, page, password, 'Password field'); await fits(h, page, submit, 'Login button');
      await account.fill(h.user.identity.account); await password.fill(h.state.password + '-wrong');
      const rejected = page.waitForResponse(r => new URL(r.url()).pathname === '/oauth/login' && r.request().method() === 'POST');
      rejected.catch(() => {}); // Navigation failure must not leave an unhandled observer promise.
      await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), submit.click()]); await rejected;
      await waitLoginForm(page);
      h.check('Wrong-password form remains on login page', !['/panel', '/portal'].some(p => new URL(page.url()).pathname.startsWith(p)) && await submit.isVisible());
      const error = await waitLoginError(page);
      await fits(h, page, error, 'Login error');
      h.check('Login error page has no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await h.screenshot(actor, 'error-' + viewport.width);
      await account.fill(h.user.identity.account); await password.fill(h.user.password);
      await submit.click(); await page.waitForURL(u => u.pathname.startsWith('/portal'), { timeout: 30000 });
      await page.waitForLoadState('networkidle');
      const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
      h.check('Viewport login creates correct user session', session.account.account === h.user.identity.account && session.homeNamespace === h.user.identity.namespace);
      await h.screenshot(actor, 'success-' + viewport.width);
    }); } finally { await context.close(); }
  }
};
handlers['F001-004'].actors = ['user'];

handlers['F065-003'] = async h => {
  const actor = h.user, directory = await h.ok(actor, 'GET', '/portal/applications/');
  const rows = directory.values === null && directory.pagination?.total === 0 ? [] : directory.values;
  if (!Array.isArray(rows) || rows.some(x => x.applicationKind !== 'builtin')) throw new h.Blocked('Empty-portal fixture must have no installed user applications');
  for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    await actor.page.setViewportSize(viewport);
    await actor.page.goto(actor.origin + '/portal/', { waitUntil: 'networkidle', timeout: 30000 });
    const card = actor.page.locator('.ant-card').filter({ has: actor.page.getByText('我的应用', { exact: true }) }).first();
    const empty = card.getByText('当前租户空间暂无已安装并启用的应用', { exact: true });
    await empty.waitFor({ state: 'visible', timeout: 10000 });
    await fits(h, actor.page, card, 'Applications card'); await fits(h, actor.page, empty, 'Empty applications feedback');
    h.check('Empty portal has no horizontal overflow', await actor.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await h.screenshot(actor, 'empty-' + viewport.width);
    const pattern = '**/api/v1/web/proxy/portal/applications/**'; let injected = 0;
    await actor.page.route(pattern, async route => { injected++; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 15, message: '回归验证：应用列表暂不可用' } }) }); });
    try {
      await actor.page.reload({ waitUntil: 'networkidle', timeout: 30000 });
      const alert = card.locator('.ant-alert'); await alert.waitFor({ state: 'visible', timeout: 10000 });
      h.check('Actual application list request reached controlled browser network failure', injected > 0);
      h.check('Unavailable state is explicit', /加载|不可用|失败|503|服务/.test(await alert.innerText()));
      h.check('Network failure does not claim a successful empty list', await empty.count() === 0);
      await fits(h, actor.page, alert, 'Applications failure feedback');
      await h.screenshot(actor, 'failure-' + viewport.width);
    } finally { await actor.page.unroute(pattern); }
    await actor.page.reload({ waitUntil: 'networkidle', timeout: 30000 });
    await empty.waitFor({ state: 'visible', timeout: 10000 });
    h.check('Reload retries live owner and clears stale failure', await card.locator('.ant-alert').count() === 0);
  }
};
handlers['F065-003'].actors = ['user'];
Object.assign(handlers, require('./identity_cases.cjs').handlers);
Object.assign(handlers, require('./registration_cases.cjs').handlers);
Object.assign(handlers, require('./session_cases.cjs').handlers);
Object.assign(handlers, require('./script_cases.cjs').handlers);
Object.assign(handlers, require('./notification_cases.cjs').handlers);
Object.assign(handlers, require('./service_cases.cjs').handlers);
Object.assign(handlers, require('./authoring_cases.cjs').handlers);
Object.assign(handlers, require('./catalog_cases.cjs').handlers);
Object.assign(handlers, require('./definition_browser_cases.cjs').handlers);
Object.assign(handlers, require('./native_cases.cjs').handlers);
Object.assign(handlers, require('./page_author_cases.cjs').handlers);
Object.assign(handlers, require('./cas_identity_cases.cjs').handlers);
Object.assign(handlers, require('./public_ui_cases.cjs').handlers);
Object.assign(handlers, require('./todo_cases.cjs').handlers);
Object.assign(handlers, require('./service_governance_cases.cjs').handlers);
Object.assign(handlers, require('./service_scope_cases.cjs').handlers);
Object.assign(handlers, require('./service_debug_cases.cjs').handlers);
Object.assign(handlers, require('./feedback_cases.cjs').handlers);
Object.assign(handlers, require('./file_cases.cjs').handlers);
Object.assign(handlers, require('./callback_cases.cjs').handlers);
Object.assign(handlers, require('./retention_cases.cjs').handlers);
Object.assign(handlers, require('./ingress_cases.cjs').handlers);
Object.assign(handlers, require('./audit_cases.cjs').handlers);
Object.assign(handlers, require('./oauth_refresh_cases.cjs').handlers);
Object.assign(handlers, require('./oauth_access_cases.cjs').handlers);
Object.assign(handlers, require('./file_boundary_cases.cjs').handlers);
Object.assign(handlers, require('./database_cases.cjs').handlers);
Object.assign(handlers, require('./profile_cases.cjs').handlers);
Object.assign(handlers, require('./page_validation_cases.cjs').handlers);
Object.assign(handlers, require('./branding_cases.cjs').handlers);
Object.assign(handlers, require('./deployment_cases.cjs').handlers);
Object.assign(handlers, require('./delivery_cases.cjs').handlers);
Object.assign(handlers, require('./artifact_integrity_cases.cjs').handlers);
Object.assign(handlers, require('./deployment_review_cases.cjs').handlers);
Object.assign(handlers, require('./native_provider_access_cases.cjs').handlers);
Object.assign(handlers, require('./native_package_cases.cjs').handlers);
Object.assign(handlers, require('./native_validation_cases.cjs').handlers);
Object.assign(handlers, require('./native_runtime_cases.cjs').handlers);
Object.assign(handlers, require('./script_library_cases.cjs').handlers);
Object.assign(handlers, require('./installation_request_cases.cjs').handlers);
Object.assign(handlers, require('./instance_cases.cjs').handlers);
Object.assign(handlers, require('./business_cases.cjs').handlers);
Object.assign(handlers, require('./business_collection_cases.cjs').handlers);
Object.assign(handlers, require('./installed_icon_cases.cjs').handlers);
Object.assign(handlers, require('./dependency_cases.cjs').handlers);
Object.assign(handlers, require('./application_authority_cases.cjs').handlers);
Object.assign(handlers, require('./definition_metadata_cases.cjs').handlers);
Object.assign(handlers, require('./deployment_progress_cases.cjs').handlers);
Object.assign(handlers, require('./member_directory_cases.cjs').handlers);
Object.assign(handlers, require('./lifecycle_admission_cases.cjs').handlers);
Object.assign(handlers, require('./portal_overview_cases.cjs').handlers);
Object.assign(handlers, require('./approval_state_cases.cjs').handlers);
Object.assign(handlers, require('./field_constraint_cases.cjs').handlers);
Object.assign(handlers, require('./storage_admission_cases.cjs').handlers);
Object.assign(handlers, require('./tls_delivery_cases.cjs').handlers);
Object.assign(handlers, require('./entity_capability_cases.cjs').handlers);
Object.assign(handlers, require('./capability_switch_cases.cjs').handlers);
Object.assign(handlers, require('./generated_service_cases.cjs').handlers);
Object.assign(handlers, require('./service_contract_cases.cjs').handlers);
Object.assign(handlers, require('./page_runtime_cases.cjs').handlers);
Object.assign(handlers, require('./page_appearance_cases.cjs').handlers);
Object.assign(handlers, require('./page_image_cases.cjs').handlers);
Object.assign(handlers, require('./page_aggregate_cases.cjs').handlers);
Object.assign(handlers, require('./installation_summary_cases.cjs').handlers);
Object.assign(handlers, require('./runtime_placement_cases.cjs').handlers);
Object.assign(handlers, require('./page_source_cases.cjs').handlers);
Object.assign(handlers, require('./page_refresh_cases.cjs').handlers);
Object.assign(handlers, require('./business_action_cases.cjs').handlers);
Object.assign(handlers, require('./model_input_cases.cjs').handlers);
Object.assign(handlers, require('./delivery_completion_cases.cjs').handlers);
Object.assign(handlers, require('./provider_completion_cases.cjs').handlers);
Object.assign(handlers, require('./dependency_runtime_cases.cjs').handlers);
Object.assign(handlers, require('./session_revision_cases.cjs').handlers);
Object.assign(handlers, require('./namespace_retirement_cases.cjs').handlers);
Object.assign(handlers, require('./service_publication_cases.cjs').handlers);
Object.assign(handlers, require('./source_effect_cases.cjs').handlers);
Object.assign(handlers, require('./portal_identity_cases.cjs').handlers);
Object.assign(handlers, require('./builtin_execution_cases.cjs').handlers);
Object.assign(handlers, require('./application_observation_cases.cjs').handlers);
Object.assign(handlers, require('./runtime_identity_cases.cjs').handlers);
Object.assign(handlers, require('./authorization_capacity_cases.cjs').handlers);
Object.assign(handlers, require('./endpoint_authority_cases.cjs').handlers);
Object.assign(handlers, require('./storage_recovery_cases.cjs').handlers);
Object.assign(handlers, require('./deployment_task_state_cases.cjs').handlers);
Object.assign(handlers, require('./todo_sync_cases.cjs').handlers);
Object.assign(handlers, require('./model_upgrade_cases.cjs').handlers);
Object.assign(handlers, require('./cost_observation_cases.cjs').handlers);
Object.assign(handlers, require('./native_lifecycle_cases.cjs').handlers);
Object.assign(handlers, require('./deployment_material_cases.cjs').handlers);
Object.assign(handlers, require('./authority_retry_cases.cjs').handlers);
Object.assign(handlers, require('./audit_source_cases.cjs').handlers);
Object.assign(handlers, require('./runtime_control_cases.cjs').handlers);
Object.assign(handlers, require('./bound_reference_cases.cjs').handlers);
Object.assign(handlers, require('./audit_admission_cases.cjs').handlers);
module.exports = { handlers };
