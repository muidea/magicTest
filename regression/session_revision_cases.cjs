// Online CAS validation is the authority. Decoded JWT fields below are only
// compared after that independent positive check, never used to grant access.
const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const oauth = require('./oauth_refresh_cases.cjs');
const { PORTAL_CORE_KEY, PORTAL_BASIC_KEYS, TENANT_OPS_ACCOUNTS_KEY } = require('./platform_profiles.cjs');
function claims(token) {
  const parts = token?.split('.');
  if (parts?.length !== 3) throw Error('Original issued JWT required');
  const value = JSON.parse(Buffer.from(parts[1], 'base64url'));
  if (!Number.isSafeInteger(value.authority_revision) || value.authority_revision < 0 || !/^account:[1-9][0-9]*$/.test(value.sub || '')) throw Error('Original human authority revision required');
  return value;
}
async function revisions(h) {
  const owner = h.tenantAdmin, namespace = owner.identity.namespace, collection = '/cas/namespaces/' + namespace + '/accounts/';
  const account = await h.createAs('tenantAdmin', collection, { account: h.state.prefix + '-revision-human', displayName: '权限修订独立账号',
    password: h.state.password, status: 2, roleTemplateKeys: [PORTAL_CORE_KEY, TENANT_OPS_ACCOUNTS_KEY] }, 'account');
  const resource = h.state.resources.find(r => r.kind === 'account' && r.id === account.id && r.collection === collection);
  const actor = await h.login(account.account, h.state.password, namespace), context = Object.create(h);
  context.user = actor;
  const f = await oauth.fixture(context, 'revision-online');
  const before = await oauth.authorization(context, f, 'before-revision'), original = claims(before.access_token);
  h.check('Independently active original token binds precise new ordinary account and namespace', (await oauth.inspect(context, f, before.access_token, 'access_token')).active === true &&
    original.sub === 'account:' + account.id && original.namespace === namespace);
  const changed = await require('./audit_cases.cjs').changeRoles(h, owner, resource, [PORTAL_CORE_KEY]);
  h.check('Actual CAS role contraction advances this original account authority revision', changed.after.authorityRevision > changed.before.authorityRevision &&
    changed.after.authorityRevision > original.authority_revision && changed.after.effectiveRoles.length < changed.before.effectiveRoles.length);
  const stale = await oauth.inspect(context, f, before.access_token, 'access_token');
  h.check('Online original JWT inspection returns inactive after owner revision change, distinct from 401 or dependency failure', stale.active === false);
  const current = await oauth.authorization(context, f, 'after-revision'), next = claims(current.access_token);
  h.check('Fresh formal authorization uses current exact authority revision and original human subject', next.sub === original.sub && next.namespace === namespace &&
    next.authority_revision === changed.after.authorityRevision && (await oauth.inspect(context, f, current.access_token, 'access_token')).active === true);
  h.check('Read-only token inspection does not change current persisted account authority', same((await h.ok(owner, 'GET', collection + account.id)).value, changed.after));
  // Retire both exact families through the original client; raw values remain
  // in private protocol journal, never in public observations.
  for (const [label, pair] of [['before', before], ['after', current]]) {
    const reply = await oauth.command(context, f, 'retire-' + label, '/api/v1/cas/oauth/revoke', { ...oauth.identityForm(f), token: pair.refresh_token, token_type_hint: 'refresh_token' });
    h.check('Formal exact original family revocation acknowledged', reply.status === 200);
    h.check('Independent owner confirms original family inactive', !(await oauth.inspect(context, f, pair.refresh_token)).active);
  }
  // 1) Ordinary 401 client authentication failure is distinct from online revision invalidation (active: false).
  const badSecret = await h.protocol(actor, 'POST', '/api/v1/cas/oauth/introspect', {
    client_id: f.owner.value.clientId, client_secret: 'wrong-' + crypto.randomBytes(8).toString('hex'),
    namespace: namespace, client_namespace: namespace, token: current.access_token, token_type_hint: 'access_token',
  });
  h.check('Bad OAuth client secret yields ordinary 401, distinct from stale authority revision active:false',
    badSecret.status === 401, badSecret);

  // 2) Isolated per-account password lockout after 5 failed attempts without affecting other accounts.
  const lockAcct = await h.createAs('tenantAdmin', collection, { account: h.state.prefix + '-lockout-human',
    displayName: '五次失败锁定校验账号', password: h.state.password, status: 2, roleTemplateKeys: PORTAL_BASIC_KEYS }, 'account');
  const lockBefore = Date.now();
  for (let i = 1; i <= 5; i++) {
    await h.rejectedLogin(lockAcct.account, h.state.password + '-wrong-' + i, namespace);
  }
  // 6th attempt uses the CORRECT password — must still be rejected as locked out!
  await h.rejectedLogin(lockAcct.account, h.state.password, namespace);
  let auditRows = [];
  for (let attempt = 0; attempt < 15; attempt++) {
    auditRows = (await h.directory(owner, '/cas/namespaces/' + namespace + '/oauth/audit/'))
      .filter(r => r.subject === 'account:' + lockAcct.id && r.createTime >= lockBefore - 2000 && r.eventType === 'login_failure');
    if (auditRows.some(r => JSON.stringify(r).includes('account locked'))) break;
    if (attempt < 14) await new Promise(resolve => setTimeout(resolve, 1000));
  }
  h.check('Locked account rejects valid 6th login and records explicit account locked audit failure',
    auditRows.some(r => r.outcome === 'failure' && JSON.stringify(r).includes('account locked')), auditRows);
  const unrelatedLogin = await h.login(account.account, actor.password, namespace);
  h.check('Unrelated account login succeeds without tripping source rate limiter', h.good(await h.api(unrelatedLogin, 'GET', '/api/v1/web/session/')));

  h.observe({
    kind: 'special-branches-deferred',
    caseId: 'F010-003',
    classification: '[C]',
    note: 'Configured source-IP login rate limit threshold, CAS restart with oauth.loginRate.enabled=false and natural block expiry require isolated-daemon + natural-time tracked in special [C]; authority revision invalidation, ordinary 401 distinction and isolated 5-attempt per-account lockout verified.',
  });
}
revisions.actors = ['tenantAdmin', 'user']; revisions.transport = 'owner-api';
module.exports = { handlers: { 'F010-003': revisions }, claims };
