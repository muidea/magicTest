const graph = require('./service_graph.cjs');
const { isDeepStrictEqual: same } = require('node:util');
const handlers = {};
async function policy(h, accessKind, enabled) {
  const n = h.tenantAdmin.identity.namespace, route = '/cas/namespaces/' + n + '/oauth/server';
  const parent = h.state.resources.find(r => r.kind === 'namespace' && r.name === n && r.phase !== 'deleted');
  if (!parent || parent.oauthPolicyCommands?.some(command => command.outcome !== 'confirmed')) throw new h.Blocked('Policy change requires exact current-run namespace without unresolved commands');
  const before = (await h.ok(h.tenantAdmin, 'GET', route)).value, field = accessKind === 'oauth' ? 'enabled' : 'subscriptionAPIKeyEnabled';
  if (before[field] === enabled) return before;
  const command = { outcome: 'unknown', original: before, intended: { accessKind, enabled, expectedVersion: before.version } };
  (parent.oauthPolicyCommands ||= []).push(command); h.persist();
  command.response = await h.api(h.tenantAdmin, 'PUT', route, command.intended); h.persist();
  h.check('Exact original access policy command acknowledged', h.good(command.response), command.response);
  const after = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  h.check('CAS independently confirms intended switch and preserves other access policy', after.namespace === n && after[field] === enabled && after.version > before.version && after[accessKind === 'oauth' ? 'subscriptionAPIKeyEnabled' : 'enabled'] === before[accessKind === 'oauth' ? 'subscriptionAPIKeyEnabled' : 'enabled'], after);
  command.outcome = 'confirmed'; command.ownerRead = after; h.persist(); return after;
}
async function rejectedCredential(h, s, name, extra, diagnostic) {
  const r = { kind: 'service-graph-credential', serviceId: s.value.service.id, parentSubscriptionId: s.value.id, collection: '/panel/hub/subscription/credentials/',
    ownerIdentity: structuredClone(h.tenantAdmin.identity), actorIdentity: structuredClone(h.tenantAdmin.identity), name, phase: 'intent', outcome: 'unknown', intended: { subscription: s.value.id, name, ...extra } };
  const before = await graph.credentialRows(h, r.collection, r.parentSubscriptionId);
  h.state.resources.push(r); h.persist();
  r.response = await h.api(h.tenantAdmin, 'POST', r.collection, r.intended); h.persist();
  h.check('Rejected key request reaches exact intended policy or field validation', !h.good(r.response) && diagnostic.test(r.response.data?.error?.message || '') && !r.response.data?.apiKey && !r.response.data?.clientSecret, r.response);
  const after = await graph.credentialRows(h, r.collection, r.parentSubscriptionId);
  h.check('Independent complete subscription credential owner read is unchanged after rejection', same(before, after), after);
  r.outcome = 'rejected'; r.phase = 'deleted'; r.proof = 'Explicit target validation refusal and unchanged complete credential directory'; h.persist();
}
async function member(h, suffix) {
  const n = h.tenantAdmin.identity.namespace;
  const account = await h.createAs('tenantAdmin', '/cas/namespaces/' + n + '/accounts/', { account: h.state.prefix + '-' + suffix, displayName: '服务回归成员', password: h.state.password, roleTemplateKeys: ['portal-user'], status: 2 }, 'account');
  return h.login(account.account, h.state.password, n, h.state.password + suffix);
}
function refused(h, r, label) {
  h.check(label, [401, 403, 404].includes(r.status) || [2, 5, 11, 12, 22].includes(r.data?.error?.code), r);
}
handlers['F040-003'] = async h => {
  const f = await graph.fixture(h, 'tenant_boundary');
  h.check('Current namespace portal contains formally published service', (await h.directory(h.user, '/portal/services/', { pageSize: 20 })).some(x => x.id === f.service.id));
  const s = await graph.subscribe(h, f), c = await graph.credential(h, s);
  await h.ok(h.user, 'GET', '/portal/service/debug/' + f.service.id);
  await graph.succeeds(h, h.user, f, c);
  const before = f.up.requests.length;
  h.check('Foreign namespace complete portal omits the original tenant service', !(await h.directory(h.otherTenantAdmin, '/portal/services/', { pageSize: 20 })).some(x => x.id === f.service.id));
  refused(h, await h.api(h.otherTenantAdmin, 'GET', '/portal/service/debug/' + f.service.id), 'Guessing a service ID does not expose another tenant contract');
  refused(h, await graph.call(h, h.otherTenantAdmin, f, c.apiKey), 'Same original valid key addressed through another tenant cannot invoke the service');
  h.check('Foreign request never reaches controlled upstream', f.up.requests.length === before);
  await graph.succeeds(h, h.user, f, c);
};
handlers['F041-003'] = async h => {
  const f = await graph.fixture(h, 'self_approval', { requireApproval: true });
  const s = await graph.subscribe(h, f);
  h.check('Formal owner creates original pending subscription', h.good(s.response) && s.value.status === 5);
  h.denied(await h.api(h.user, 'PUT', graph.subscriptions + 'approve/' + s.value.id, {}), 'Ordinary applicant cannot approve their own subscription');
  const after = (await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + s.value.id)).value;
  h.check('Self-approval rejection leaves exact original pending record unchanged', same(after, s.value));
  const peer = await member(h, 'subscription-peer');
  h.denied(await h.api(peer, 'GET', graph.subscriptions + s.value.id), 'Other ordinary member cannot query private subscription management identity');
  refused(h, await h.api(peer, 'GET', '/portal/service/debug/' + f.service.id), 'Unsubscribed peer cannot obtain protected subscribed service debug metadata');
  h.check('Peer access attempts do not alter original subscription', same((await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + s.value.id)).value, s.value));
  await h.ok(h.tenantAdmin, 'PUT', graph.subscriptions + 'approve/' + s.value.id, {});
  h.check('Authorized owner can approve the exact original pending record', (await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + s.value.id)).value.status === 2);
  const c = await graph.credential(h, s); await graph.succeeds(h, h.user, f, c);
};
handlers['F040-002'] = async h => {
  const f = await graph.fixture(h, 'subscription_capacity', { maxSubscriptions: 1 });
  const peer = await member(h, 'capacity-peer');
  const attempts = await Promise.all([graph.subscribe(h, f, h.user), graph.subscribe(h, f, peer)]);
  const accepted = attempts.filter(x => x.resource.outcome === 'accepted'), rejected = attempts.filter(x => x.resource.outcome === 'rejected');
  h.check('Concurrent original applicants admit exactly one subscription at capacity one', accepted.length === 1 && rejected.length === 1 && !h.good(rejected[0].response), attempts.map(x => ({ outcome: x.resource.outcome, response: x.response })));
  const all = (await h.directory(h.tenantAdmin, graph.subscriptions)).filter(x => x.service.id === f.service.id);
  h.check('Independent complete owner directory proves no capacity overshoot or duplicate', all.length === 1 && all[0].id === accepted[0].value.id && all[0].status === 2, all);
  await graph.retire(h, accepted[0]);
  await h.ok(h.tenantAdmin, 'PUT', graph.publications + f.publication.id, { ...f.payload, requireApproval: true });
  h.check('Owner policy read confirms approval mode at unchanged capacity', (await h.ok(h.tenantAdmin, 'GET', graph.publications + f.publication.id)).value.requireApproval === true);
  const pending = await graph.subscribe(h, f);
  h.check('Policy switch creates an original pending subscription instead of auto-approval', pending.value.status === 5);
  const excess = await graph.subscribe(h, f, peer);
  h.check('Pending subscriptions also consume the declared capacity', excess.resource.outcome === 'rejected' && !h.good(excess.response));
  await h.ok(h.tenantAdmin, 'PUT', graph.subscriptions + 'approve/' + pending.value.id, {});
  h.check('Owner approval activates only the exact original in-capacity subscription', (await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + pending.value.id)).value.status === 2);
};
handlers['F043-003'] = async h => {
  const f = await graph.fixture(h, 'protected_guide'), actor = await member(h, 'guide-member');
  refused(h, await h.api(actor, 'GET', '/portal/service/debug/' + f.service.id), 'Unsubscribed valid member cannot read protected service debug metadata');
  const original = await graph.subscribe(h, f), existing = await graph.credential(h, original);
  const positive = await h.ok(h.user, 'GET', '/portal/service/credentials/?service=' + f.service.id);
  h.check('Original subscribed member sees their existing real credential', positive.values?.some(x => x.clientId === existing.value.clientId));
  const hidden = await h.api(actor, 'GET', '/portal/service/credentials/?service=' + f.service.id);
  h.check('Unsubscribed valid member receives a complete empty credential list while another member owns a real credential', h.good(hidden) && hidden.data.pagination?.total === 0 && Array.isArray(hidden.data.values) && hidden.data.values.length === 0, hidden);
  const s = await graph.subscribe(h, f, actor), c = await graph.credential(h, s);
  await h.ok(actor, 'GET', '/portal/service/debug/' + f.service.id); await graph.succeeds(h, actor, f, c);
  // Disable only this dedicated original account; existing regression actors remain available.
  const n = actor.identity.namespace, accounts = '/cas/namespaces/' + n + '/accounts/';
  const account = (await h.directory(h.tenantAdmin, accounts)).find(x => x.account === actor.identity.account);
  h.check('Disabling targets the dedicated original subscriber account', account?.id > 0);
  await h.ok(h.tenantAdmin, 'PUT', accounts + account.id, { account: account.account, displayName: account.displayName, email: account.email || '', description: account.description || '', status: 1, roleTemplateKeys: ['portal-user'] });
  h.check('Independent CAS account owner confirms unavailable original subscriber', (await h.ok(h.tenantAdmin, 'GET', accounts + account.id)).value.status === 1);
  refused(h, await h.api(actor, 'GET', '/portal/service/debug/' + f.service.id), 'Disabled subscriber cannot retain protected service debug access');
  refused(h, await h.api(actor, 'GET', '/portal/service/credentials/?service=' + f.service.id), 'Disabled subscriber cannot retain service credential visibility');
  const before = f.up.requests.length;
  refused(h, await graph.call(h, actor, f, c.apiKey), 'Original service credential cannot bypass the disabled account security fence');
  h.check('Disabled subscriber command does not reach upstream', f.up.requests.length === before);
};
handlers['F041-002'] = async h => {
  const f = await graph.fixture(h, 'duplicate_subscription'), s = await graph.subscribe(h, f);
  const c = await graph.credential(h, s);
  await graph.succeeds(h, h.user, f, c);
  const duplicate = await graph.subscribe(h, f);
  h.check('A different original request cannot create another active subscription for the same human and service', duplicate.resource.outcome === 'rejected' || duplicate.value?.id === s.value.id, duplicate.response);
  const rows = (await h.directory(h.tenantAdmin, graph.subscriptions)).filter(row => row.service.id === f.service.id);
  h.check('Complete owner directory proves a single exact active subscription', rows.length === 1 && rows[0].id === s.value.id && rows[0].status === 2, rows);
  await graph.succeeds(h, h.user, f, c);
};
handlers['F042-001'] = async h => {
  const f = await graph.fixture(h, 'key_rotation'), s = await graph.subscribe(h, f), c = await graph.credential(h, s);
  h.check('Subscription API Key has the declared opaque sk format', /^sk_[A-Za-z0-9_-]{32}$/.test(c.apiKey));
  h.check('Credential has no independently copied expiry', !c.value.expiresAt);
  await graph.succeeds(h, h.user, f, c);
  const next = await graph.rotate(h, c);
  h.check('Rotation returns a different key in the same opaque format', /^sk_[A-Za-z0-9_-]{32}$/.test(next.apiKey) && next.apiKey !== c.apiKey);
  await graph.succeeds(h, h.user, f, next);
  while (Date.now() <= next.retirePreviousAt + 100) await new Promise(resolve => setTimeout(resolve, Math.min(500, next.retirePreviousAt + 101 - Date.now())));
  const before = f.up.requests.length;
  refused(h, await graph.call(h, h.user, f, c.apiKey), 'Old subscription Key is rejected after actual retirement');
  h.check('Retired original Key does not reach upstream', f.up.requests.length === before);
  const cas = '/cas/namespaces/' + h.tenantAdmin.identity.namespace + '/oauth/clients/' + encodeURIComponent(c.value.clientId) + '/credentials/';
  const rows = await h.directory(h.tenantAdmin, cas);
  h.check('Independent CAS owner proves original secret terminal and exact replacement active', rows.some(row => row.id === c.value.credentialId && ['expired', 'revoked'].includes(row.status)) && rows.some(row => row.id === next.value.credentialId && row.status === 'active') && rows.every(row => !Object.hasOwn(row, 'clientSecret')) && !JSON.stringify(rows).includes(c.apiKey) && !JSON.stringify(rows).includes(next.apiKey), rows);
  c.resource.rotation.outcome = 'confirmed'; c.resource.rotation.replacementCredentialId = next.value.credentialId; c.resource.rotation.proof = 'Original secret independently terminal in CAS; exact replacement tracked for final formal retirement'; c.resource.phase = 'deleted'; h.persist();
  await graph.succeeds(h, h.user, f, next);
  const summary = (await h.ok(h.tenantAdmin, 'GET', graph.subscriptions + s.value.id)).value;
  h.check('Key replacement retains exact original subscription identity, lease and authorization', summary.id === s.value.id && summary.expireTime === s.value.expireTime && same(summary.subscriberRef, s.value.subscriberRef));
};
handlers['F042-002'] = async h => {
  const started = new Date().toISOString();
  const f = await graph.fixture(h, 'key_retirement'), s = await graph.subscribe(h, f), c = await graph.credential(h, s);
  await graph.succeeds(h, h.user, f, c);
  const foreign = await graph.fixture(h, 'foreign_key_target', {}, 'otherTenantAdmin'), before = f.up.requests.length;
  refused(h, await graph.call(h, h.otherTenantAdmin, foreign, c.apiKey), 'Existing usable tenant A Key cannot invoke an existing tenant B service');
  h.check('Foreign Host request reaches neither upstream target', f.up.requests.length === before);
  await graph.succeeds(h, h.user, f, c);
  await graph.retireCredential(h, c);
  const after = f.up.requests.length;
  refused(h, await graph.call(h, h.user, f, c.apiKey), 'Exact original Key cannot invoke after acknowledged retirement');
  h.check('Revoked Key never reaches upstream', f.up.requests.length === after);
  const { execFileSync } = require('node:child_process');
  for (const name of ['magicGateway', 'magicPanel', 'magiccas']) {
    const log = execFileSync('docker', ['logs', '--since', started, name], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] });
    h.check('Observed service log window contains no full Key: ' + name, !log.includes(c.apiKey));
  }
};
async function switches(h, suffix, keyOff) {
  const cas = require('./cas_identity_cases.cjs'), machine = await cas.machine(h, suffix), token = await cas.accepted(h, machine);
  const route = '/cas/namespaces/' + h.tenantAdmin.identity.namespace + '/oauth/server';
  const original = (await h.ok(h.tenantAdmin, 'GET', route)).value;
  const f = await graph.fixture(h, suffix), s = await graph.subscribe(h, f);
  try {
    await policy(h, 'subscription-api-key', true);
    await policy(h, 'oauth', false);
    const deniedToken = await cas.token(h, machine);
    h.check('Disabled OAuth rejects ordinary original client credentials grant', [400, 401, 403].includes(deniedToken.status) && /server|disabled|关闭|接入|enabled/i.test(deniedToken.data.error_description || deniedToken.data.error?.message || ''), deniedToken);
    const introspect = await h.protocol(h.tenantAdmin, 'POST', '/api/v1/cas/oauth/introspect', { token, client_id: machine.owner.value.clientId, client_secret: machine.credential.value.clientSecret, namespace: machine.n, client_namespace: machine.n });
    h.check('OAuth closure also fences the existing ordinary Endpoint token', introspect.status === 200 && introspect.data.active === false || [400, 401, 403].includes(introspect.status), introspect);
    const c = await graph.credential(h, s);
    await graph.succeeds(h, h.user, f, c);
    if (keyOff) {
      await rejectedCredential(h, s, h.state.prefix + '-illegal-expiry', { expiresAt: Date.now() + 10000 }, /unknown field.*expiresAt/);
      await policy(h, 'subscription-api-key', false);
      await rejectedCredential(h, s, h.state.prefix + '-disabled-key', {}, /订阅 API Key 接入未启用/);
      const before = f.up.requests.length;
      refused(h, await graph.call(h, h.user, f, c.apiKey), 'Disabled Key policy fences previously valid Key independently of OAuth');
      h.check('Disabled Key access has no upstream effect', f.up.requests.length === before);
      await policy(h, 'subscription-api-key', true);
      await graph.succeeds(h, h.user, f, c);
    }
  } finally {
    // Each restore is a new guarded owner command, only after prior outcomes
    // are confirmed. Unknown writes remain open instead of being overwritten.
    const parent = h.state.resources.find(r => r.kind === 'namespace' && r.name === machine.n);
    if (!parent.oauthPolicyCommands?.some(command => command.outcome !== 'confirmed')) {
      await policy(h, 'subscription-api-key', original.subscriptionAPIKeyEnabled);
      await policy(h, 'oauth', original.enabled);
    }
  }
}
handlers['F008-002'] = h => switches(h, 'oauth_independence', false);
handlers['F042-003'] = h => switches(h, 'key_policy_independence', true);
for (const fn of Object.values(handlers)) { fn.actors = ['user', 'tenantAdmin', 'otherTenantAdmin']; fn.transport = 'owner-api'; }
module.exports = { handlers, policy };
