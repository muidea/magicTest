// Online CAS validation is the authority. Decoded JWT fields below are only
// compared after that independent positive check, never used to grant access.
const { isDeepStrictEqual: same } = require('node:util');
const oauth = require('./oauth_refresh_cases.cjs');
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
    password: h.state.password, status: 2, roleTemplateKeys: ['portal-user', 'tenant-security-admin'] }, 'account');
  const resource = h.state.resources.find(r => r.kind === 'account' && r.id === account.id && r.collection === collection);
  const actor = await h.login(account.account, h.state.password, namespace), context = Object.create(h);
  context.user = actor;
  const f = await oauth.fixture(context, 'revision-online');
  const before = await oauth.authorization(context, f, 'before-revision'), original = claims(before.access_token);
  h.check('Independently active original token binds precise new ordinary account and namespace', (await oauth.inspect(context, f, before.access_token, 'access_token')).active === true &&
    original.sub === 'account:' + account.id && original.namespace === namespace);
  const changed = await require('./audit_cases.cjs').changeRoles(h, owner, resource, ['portal-user']);
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
  await h.partial('Dedicated human current-role contraction, old JWT online invalidation, new code grant using exact current authority revision and original-family retirement implemented. Configured tenant/source rate limits, disabled-limit password lockout and natural block expiry remain open; no offline JWT revocation claim.');
}
revisions.actors = ['tenantAdmin', 'user']; revisions.transport = 'owner-api';
module.exports = { handlers: { 'F010-003': revisions }, claims };
