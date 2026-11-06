// Public tenant registration, current controlled access profiles, original IDs.
const handlers = {};
const cas = n => '/cas/namespaces/' + n + '/';
const publicPolicy = '/api/v1/cas/registration/policy/public/';
const publicSubmit = '/api/v1/cas/registration/account/submit/';
const roles = list => (list || []).map(r => r.module + ':' + r.key).sort();
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const policyFields = ['enabled', 'defaultProfileKey', 'requireApproval', 'allowedEmailDomains', 'captchaEnabled', 'status'];
const policyValue = x => Object.fromEntries(policyFields.map(k => [k, x[k]]));

async function fixture(h, suffix) {
  const ns = await h.create('/panel/namespace-onboardings/', { name: h.state.prefix + suffix,
    description: '注册回归独立租户', scope: [], status: 2, startTime: Date.now() - 1000,
    expireTime: Date.now() + 86400000, initialAdminPassword: h.state.password }, 'namespace');
  const base = cas(ns.name), reg = base + 'registration/';
  const accountList = (await h.ok(h.admin, 'GET', base + 'accounts/?_pageSize=100')).values;
  h.check('Dedicated registration tenant starts with exactly one bootstrap account', accountList.length === 1);
  const profiles = await h.ok(h.admin, 'GET', base + 'role-templates/?_pageSize=100');
  if (profiles.pagination?.hasMore || profiles.pagination?.total > profiles.values.length) throw new h.Blocked('Registration profile directory must be read completely');
  const portal = profiles.values.find(p => p.key === 'portal-user' && p.status === 2 && p.systemManaged);
  h.check('Registration consumes an existing controlled portal-user access profile', !!portal && portal.roleRefs.length > 0);
  const p = (await h.ok(h.admin, 'POST', reg + 'profiles/', { key: h.state.prefix + '-' + suffix,
    name: '注册回归初始门户模板', description: '仅引用受控门户用户预设', accessProfileKeys: ['portal-user'], status: 2 })).value;
  h.namespaceDependent(ns.id, reg + 'profiles/', p.id, 'registration-profile');
  const anon = await h.anonymous(ns.name);
  return { ns, base, reg, p, portal, anon, bootstrap: accountList[0] };
}

async function policy(h, f, changes = {}) {
  const desired = { enabled: true, defaultProfileKey: f.p.key, requireApproval: true,
    allowedEmailDomains: [], captchaEnabled: false, status: 2, ...changes };
  await h.ok(h.admin, 'PUT', f.reg + 'policies/', desired);
  const actual = (await h.ok(h.admin, 'GET', f.reg + 'policies/')).value;
  h.check('Registration owner independently persists full intended policy', equal(policyValue(actual), desired));
  const namespace = (await h.ok(h.admin, 'GET', '/cas/namespaces/' + f.ns.id)).value;
  h.check('Public registration targets exact enabled namespace within its active time window', namespace.id === f.ns.id && namespace.name === f.ns.name && namespace.status === 2 && namespace.startTime <= Date.now() && namespace.expireTime > Date.now(), namespace);
  const advertised = (await h.ok(f.anon, 'GET', publicPolicy)).value;
  h.check('Anonymous tenant host advertises exact same policy', equal(policyValue(advertised), desired));
  return actual;
}

function request(h, suffix, emailDomain = 'example.test') {
  const account = h.state.prefix + '-' + suffix;
  return { account, password: h.state.password, displayName: '回归注册 ' + suffix,
    email: account + '@' + emailDomain, phone: '' };
}

async function submit(h, f, payload) {
  h.state.registrationIntents ||= [];
  h.state.registrationIntents.push({ namespace: f.ns.name, account: payload.account }); h.persist();
  const r = (await h.ok(f.anon, 'POST', publicSubmit, payload)).value;
  h.check('Registration response binds immutable account and workflow identities', r.id > 0 && r.accountId > 0 && r.account === payload.account && r.profileKey === f.p.key && equal(r.accessProfileKeys, ['portal-user']));
  h.namespaceDependent(f.ns.id, f.reg + 'accounts/', r.id, 'registration');
  h.namespaceDependent(f.ns.id, f.base + 'accounts/', r.accountId, 'registered-account');
  return r;
}

async function lists(h, f) {
  const accounts = await h.ok(h.admin, 'GET', f.base + 'accounts/?_pageSize=100');
  const registrations = await h.ok(h.admin, 'GET', f.reg + 'accounts/?_pageSize=100');
  return { accounts: directoryValues(h, accounts), registrations: directoryValues(h, registrations) };
}

function directoryValues(h, page) {
  const values = page.values === null && page.pagination?.total === 0 ? [] : page.values;
  if (!Array.isArray(values) || page.pagination?.hasMore || page.pagination?.total > values.length) {
    throw new h.Blocked('Dedicated registration identity directory requires complete reader');
  }
  return values;
}

async function approved(h, f, r) {
  const registration = (await h.ok(h.admin, 'GET', f.reg + 'accounts/' + r.id)).value;
  h.check('Workflow owner confirms original approved registration and profile snapshot', registration.status === 'approved' && registration.accountId === r.accountId && registration.account === r.account && registration.profileKey === f.p.key && equal(registration.accessProfileKeys, ['portal-user']));
  const account = (await h.ok(h.admin, 'GET', f.base + 'accounts/' + r.accountId)).value;
  h.check('Account owner confirms active original subject without human template assignments', account.id === r.accountId && account.account === r.account && account.status === 2 && (account.templateRefs || []).length === 0);
  const bindings = directoryValues(h, await h.ok(h.admin, 'GET', registrationBindingRoute(f.base, r.accountId)));
  registrationAuthority(h, r.accountId, f.portal.roleRefs, bindings);
  h.check('Initial effective roles equal selected protected profile, with no additional management roles', equal(roles(account.effectiveRoles), roles(f.portal.roleRefs)), { expected: roles(f.portal.roleRefs), actual: roles(account.effectiveRoles) });
  const actor = await h.login(r.account, h.state.password, f.ns.name, h.state.password + 'R');
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
  h.denied(await h.api(actor, 'GET', f.base + 'accounts/'), 'Registered portal subject gains no account management authority');
  await h.screenshot(actor, 'registered-' + r.id);
  return { registration, account, actor };
}

function registrationAuthority(h, accountId, roleRefs, bindings) {
  const actual = bindings.map(b => ({ module: b.roleModule, key: b.roleKey }));
  h.check('Authorization owner confirms exact registration-source role bindings for original account',
    bindings.length > 0 && bindings.every(b => b.subjectType === 'account' && b.subjectId === accountId && b.sourceType === 'registration' && b.sourceKey === 'account-registration:' + accountId && b.status === 2 && b.sourceVersion > 0) && equal(roles(actual), roles(roleRefs)),
    { accountId, expectedRoles: roles(roleRefs), bindings });
}

function registrationBindingRoute(base, accountId) {
  const query = new URLSearchParams({ _pageSize: '100', subjectId: String(accountId) + '|=', subjectType: 'account|=' });
  return base + 'subject-role-bindings/?' + query;
}

async function review(h, f, r, action, actor = h.admin) {
  return (await h.ok(actor, 'PUT', f.reg + 'account/' + action + '/' + r.id, { approvalMessage: '回归 ' + action })).value;
}

handlers['F002-001'] = async h => {
  const f = await fixture(h, 'regflow');
  await policy(h, f);
  const accept = await submit(h, f, request(h, 'reg-approve'));
  h.check('Approval policy creates pending request', accept.status === 'pending');
  const pending = (await h.ok(h.admin, 'GET', f.base + 'accounts/' + accept.accountId)).value;
  h.check('Pending account is disabled and has no assigned initial roles', pending.status === 1 && (pending.effectiveRoles || []).length === 0 && (pending.templateRefs || []).length === 0);
  await h.rejectedLogin(accept.account, h.state.password, f.ns.name);
  await review(h, f, accept, 'approve');
  await approved(h, f, accept);
  const reject = await submit(h, f, request(h, 'reg-reject'));
  await review(h, f, reject, 'reject');
  const rejected = (await h.ok(h.admin, 'GET', f.reg + 'accounts/' + reject.id)).value;
  h.check('Rejected request keeps exact workflow identity and result', rejected.id === reject.id && rejected.accountId === reject.accountId && rejected.status === 'rejected');
  await h.gone(f.base + 'accounts/', reject.accountId);
  await h.rejectedLogin(reject.account, h.state.password, f.ns.name);
  await policy(h, f, { requireApproval: false });
  const automatic = await submit(h, f, request(h, 'reg-auto'));
  h.check('No-approval policy converges original request to approved', automatic.status === 'approved' && automatic.approvedBy === 'system');
  await approved(h, f, automatic);
};

handlers['F002-002'] = async h => {
  const f = await fixture(h, 'regclosed');
  await policy(h, f, { enabled: false });
  const before = await lists(h, f);
  const denied = await h.api(f.anon, 'POST', publicSubmit, request(h, 'closed'));
  h.check('Disabled registration rejects at exact policy gate', !h.good(denied) && denied.data?.error?.message === 'registration is disabled', denied);
  h.check('Closed submission creates neither account nor registration', equal(before, await lists(h, f)));
  await policy(h, f);
  const pending = await submit(h, f, request(h, 'forged-review'));
  const member = (await h.ok(h.admin, 'POST', f.base + 'accounts/', { account: h.state.prefix + '-review-member', displayName: '普通门户成员', password: h.state.password, email: '', description: '', roleTemplateKeys: ['portal-user'], status: 2 })).value;
  h.namespaceDependent(f.ns.id, f.base + 'accounts/', member.id, 'ordinary-reviewer');
  const actor = await h.login(member.account, h.state.password, f.ns.name, h.state.password + 'M');
  await h.ok(actor, 'GET', '/system/context/?surface=portal');
  const original = await lists(h, f);
  for (const action of ['approve', 'reject']) h.denied(await h.api(actor, 'PUT', f.reg + 'account/' + action + '/' + pending.id, { approvalMessage: 'MUST NOT REVIEW' }), 'Ordinary same-tenant member cannot ' + action + ' registration');
  h.check('Forged reviews leave exact requests and subjects unchanged', equal(original, await lists(h, f)));
  await review(h, f, pending, 'reject');
};

handlers['F002-003'] = async h => {
  const f = await fixture(h, 'regduplicate');
  await policy(h, f);
  const payload = request(h, 'duplicate'), original = await submit(h, f, payload);
  const before = await lists(h, f);
  const duplicate = await h.api(f.anon, 'POST', publicSubmit, payload);
  h.check('Duplicate applicant returns explicit identity-unavailable error', !h.good(duplicate) && duplicate.data?.error?.message === 'account registration is unavailable', duplicate);
  h.check('Duplicate submit preserves exact original pending account and request', equal(before, await lists(h, f)));
  const localAdmin = await h.login(f.bootstrap.account, h.state.password, f.ns.name, h.state.password + 'A');
  const path = f.reg + 'account/approve/' + original.id;
  const responses = await Promise.all([h.api(h.admin, 'PUT', path, { approvalMessage: 'platform reviewer' }), h.api(localAdmin, 'PUT', path, { approvalMessage: 'tenant reviewer' })]);
  h.check('Two independent administrators race on exact original request', responses.some(h.good));
  for (const response of responses) {
    h.check('Concurrent review returns same approved identity or exact claimed-state refusal', h.good(response) ? response.data.value?.id === original.id && response.data.value?.accountId === original.accountId && response.data.value?.status === 'approved' : ['account registration ' + original.id + ' is no longer pending', 'account registration ' + original.id + ' review is already being resumed'].includes(response.data?.error?.message), response);
  }
  const { account, registration } = await approved(h, f, original);
  const repeated = await review(h, f, original, 'approve', localAdmin);
  h.check('Sequential repeated approval returns original durable result unchanged', equal(repeated, registration));
  const accountAfter = (await h.ok(h.admin, 'GET', f.base + 'accounts/' + original.accountId)).value;
  h.check('Repeated review cannot add another binding or alter current authority', equal(accountAfter, account));
  const after = await lists(h, f);
  h.check('Owner directories contain one original request and one account for applicant', after.registrations.filter(r => r.account === original.account).length === 1 && after.accounts.filter(a => a.account === original.account).length === 1);
};

handlers['F002-004'] = async h => {
  const f = await fixture(h, 'regpolicy');
  const initial = await policy(h, f, { requireApproval: false, allowedEmailDomains: ['example.test'] });
  const before = await lists(h, f);
  const refused = await h.api(f.anon, 'POST', publicSubmit, request(h, 'wrong-domain', 'outside.test'));
  h.check('Nonmatching email is rejected at exact domain gate', !h.good(refused) && refused.data?.error?.message === 'email domain is not allowed', refused);
  h.check('Email domain refusal creates no applicant resources', equal(before, await lists(h, f)));
  const allowed = await submit(h, f, request(h, 'allowed-domain'));
  await approved(h, f, allowed);
  const captcha = await h.api(h.admin, 'PUT', f.reg + 'policies/', { ...policyValue(initial), captchaEnabled: true });
  h.check('Missing real CAPTCHA provider refuses policy enablement explicitly', !h.good(captcha) && captcha.data?.error?.message === 'captcha cannot be enabled until a verification provider is configured', captcha);
  const actual = (await h.ok(h.admin, 'GET', f.reg + 'policies/')).value;
  h.check('Rejected CAPTCHA setting leaves original full policy unchanged', equal(actual, initial));
  h.check('Public policy does not advertise unavailable CAPTCHA', equal(policyValue((await h.ok(f.anon, 'GET', publicPolicy)).value), policyValue(initial)));
};
for (const handler of Object.values(handlers)) handler.actors = ['user', 'tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers, directoryValues, registrationAuthority, registrationBindingRoute };
