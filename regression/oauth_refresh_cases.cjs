// CAS owns authorization codes, refresh-family rotation and revocation.
// Raw credentials and original request/response bodies are private state only.
const crypto = require('node:crypto');
const { client, credential, enableOAuth, activateClient } = require('./cas_identity_cases.cjs');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
const { waitLoginForm } = require('./login_readiness.cjs');

async function command(h, fixture, label, endpoint, form) {
  const r = fixture.owner.resource;
  if ((r.protocolCommands || []).some(c => c.label === label)) throw new h.Blocked('Original OAuth command already recorded; no replay: ' + label);
  const entry = { label, endpoint, form: structuredClone(form), clientId: fixture.owner.value.clientId, namespace: fixture.n, outcome: 'unknown' };
  (r.protocolCommands ||= []).push(entry); h.persist();
  const response = await h.protocol(h.user, 'POST', endpoint, form);
  entry.response = response; entry.outcome = 'response-received'; h.persist();
  return response;
}
const identityForm = f => ({ client_id: f.owner.value.clientId, client_secret: f.credential.value.clientSecret, namespace: f.n, client_namespace: f.n });
const refresh = (h, f, label, value, extra = {}) => command(h, f, label, '/api/v1/cas/oauth/token', { ...identityForm(f), grant_type: 'refresh_token', refresh_token: value, ...extra });
async function inspect(h, f, value, kind = 'refresh_token') {
  const response = await h.protocol(h.user, 'POST', '/api/v1/cas/oauth/introspect', { ...identityForm(f), token: value, token_type_hint: kind });
  h.check('Independent no-cookie CAS introspection acknowledges original client', response.status === 200 && typeof response.data.active === 'boolean', response);
  return response.data;
}
function issued(h, response, previous) {
  h.check('CAS issues one distinct access/refresh pair with bounded expiry and original scope', response.status === 200 && response.data.token_type?.toLowerCase() === 'bearer' && typeof response.data.access_token === 'string' && typeof response.data.refresh_token === 'string' && response.data.refresh_token.length >= 32 && response.data.expires_in > 0 && response.data.scope === 'openid profile' && (!previous || response.data.refresh_token !== previous), response);
  return response.data;
}
function rejected(h, response, error, label) {
  h.check(label, response.status === 400 && response.data.error === error && !response.data.access_token && !response.data.refresh_token, response);
}
async function authorization(h, f, label) {
  const owner = f.owner.resource;
  if ((owner.authorizations || []).some(a => a.label === label)) throw new h.Blocked('Original OAuth authorization already recorded; no replay');
  const verifier = crypto.randomBytes(32).toString('base64url'), state = crypto.randomBytes(24).toString('base64url'), nonce = crypto.randomBytes(24).toString('base64url');
  const params = new URLSearchParams({ response_type: 'code', client_id: f.owner.value.clientId, redirect_uri: f.redirect, scope: 'openid profile', state, nonce, code_challenge: crypto.createHash('sha256').update(verifier).digest('base64url'), code_challenge_method: 'S256', namespace: f.n, client_namespace: f.n });
  const entry = { label, verifier, state, nonce, route: '/api/v1/cas/oauth/authorize?' + params, outcome: 'unknown' };
  (owner.authorizations ||= []).push(entry); h.persist();
  const page = await h.user.context.newPage(), actor = { ...h.user, page };
  try {
    await withOriginalCasForms(actor, { journal: h.state.originalCasForms ||= [], persist: h.persist, record: h.observe }, async () => {
      await page.goto(actor.origin + entry.route, { waitUntil: 'networkidle', timeout: 45000 });
      if (new URL(page.url()).pathname === '/login/cas') {
        const form = await waitLoginForm(page);
        await form.account.fill(actor.identity.account); await form.password.fill(actor.password);
        await form.submit.click();
      }
      await page.waitForURL(url => url.origin + url.pathname === f.redirect && (url.searchParams.has('code') || url.searchParams.has('error')), { timeout: 30000 });
    });
    const returned = new URL(page.url());
    entry.returned = returned.href; entry.outcome = 'callback-received'; h.persist();
    h.check('Real CAS S256 authorization returns one code to exact registered callback and original state', returned.origin + returned.pathname === f.redirect && returned.searchParams.getAll('code').length === 1 && !!returned.searchParams.get('code') && returned.searchParams.get('state') === state && !returned.searchParams.has('error'));
    const response = await command(h, f, label + '-exchange', '/api/v1/cas/oauth/token', { ...identityForm(f), grant_type: 'authorization_code', code: returned.searchParams.get('code'), redirect_uri: f.redirect, code_verifier: verifier });
    const result = issued(h, response);
    const profile = await inspect(h, f, result.refresh_token);
    h.check('Independent original refresh family belongs to actual ordinary subject and tenant', profile.active && profile.sub === f.subject && profile.client_id === f.owner.value.clientId && profile.namespace === f.n && profile.username === h.user.identity.account && profile.exp > Date.now() / 1000, profile);
    return result;
  } finally { await page.close(); }
}
async function readAudit(h, f, predicate) {
  let rows;
  for (let attempt = 0; attempt < 15; attempt++) {
    rows = await h.directory(h.tenantAdmin, '/cas/namespaces/' + f.n + '/oauth/audit/?clientId=' + encodeURIComponent(f.owner.value.clientId));
    if (predicate(rows)) return rows;
    if (attempt < 14) await new Promise(resolve => setTimeout(resolve, 1000));
  }
  return rows;
}
async function fixture(h, suffix = 'refresh') {
  await enableOAuth(h);
  const n = h.user.identity.namespace, subject = 'account:' + (await h.ok(h.user, 'GET', '/api/v1/web/session/')).value.account.id;
  const redirect = h.user.origin + '/portal/';
  const owner = await client(h, { name: h.state.prefix + '-' + suffix, developerName: '', clientType: 'confidential', partyType: 'first_party', authenticationNamespaces: [n], redirectUris: [redirect], grantTypes: ['authorization_code', 'refresh_token'], allowedScopes: 'openid profile', scopeDescription: '独立刷新族验证', audience: 'api://management', requirePKCE: true, status: 1, description: '当前普通账号正式授权；无业务扩权' });
  const secret = await credential(h, owner, { name: h.state.prefix + '-' + suffix + '-secret', expiresAt: Date.now() + 1800000 });
  await activateClient(h, owner);
  return { n, subject, redirect, owner, credential: secret };
}
const handlers = { 'F001-005': async h => {
  const f = await fixture(h), { n, subject, owner } = f;
  const a = await authorization(h, f, 'replay');
  const b = issued(h, await refresh(h, f, 'rotate', a.refresh_token), a.refresh_token);
  h.check('Consumed original refresh is inactive without mutating the current family', !(await inspect(h, f, a.refresh_token)).active && (await inspect(h, f, b.refresh_token)).active);
  rejected(h, await refresh(h, f, 'consumed-replay', a.refresh_token), 'invalid_grant', 'Actual consumed-token replay is invalid_grant without new credentials');
  h.check('Independent current-family read proves replay revoked its replacement', !(await inspect(h, f, b.refresh_token)).active);
  rejected(h, await refresh(h, f, 'revoked-family', b.refresh_token), 'invalid_grant', 'Replay-retired replacement cannot rotate again');
  const audit = await readAudit(h, f, rows => rows.some(r => r.eventType === 'refresh_replay' && r.outcome === 'denied'));
  const originalGrant = audit.find(r => r.eventType === 'token_issued' && r.subject === subject && JSON.parse(r.detailJson || '{}').grantType === 'authorization_code');
  const rotation = audit.find(r => r.eventType === 'token_issued' && r.subject === subject && JSON.parse(r.detailJson || '{}').grantType === 'refresh_token');
  const family = originalGrant && JSON.parse(originalGrant.detailJson).familyId;
  h.check('CAS audit correlates real code exchange, rotation and replay to the same original family', !!family && !!rotation && JSON.parse(rotation.detailJson).familyId === family && audit.some(r => r.eventType === 'refresh_replay' && r.outcome === 'denied' && r.subject === family && JSON.parse(r.detailJson || '{}').familyId === family) && audit.every(r => r.namespace === n && r.clientId === owner.value.clientId));
  const c = await authorization(h, f, 'concurrent');
  rejected(h, await command(h, f, 'missing-refresh', '/api/v1/cas/oauth/token', { ...identityForm(f), grant_type: 'refresh_token' }), 'invalid_request', 'Missing refresh parameter is invalid_request, separate from retired grant');
  h.check('Parameter rejection preserves independently active original family', (await inspect(h, f, c.refresh_token)).active);
  const concurrent = await Promise.allSettled([refresh(h, f, 'concurrent-a', c.refresh_token), refresh(h, f, 'concurrent-b', c.refresh_token)]);
  if (concurrent.some(r => r.status !== 'fulfilled')) throw new h.Blocked('Original concurrent refresh response unknown; no token replay');
  const responses = concurrent.map(r => r.value), successes = responses.filter(r => r.status === 200);
  h.check('Concurrent original refresh has exactly one acknowledged winner', successes.length === 1);
  const winner = issued(h, successes[0], c.refresh_token);
  rejected(h, responses.find(r => r !== successes[0]), 'invalid_grant', 'Concurrent loser does not issue an extra pair');
  // A loser may observe the consumed-token replay index after the winner
  // commits; that formally revokes the whole family. Retire using the current
  // known winner, then prove inactive without asserting a scheduling order.
  const concurrencyActive = (await inspect(h, f, winner.refresh_token)).active;
  const revokeConcurrent = await command(h, f, 'revoke-concurrent', '/api/v1/cas/oauth/revoke', { ...identityForm(f), token: winner.refresh_token, token_type_hint: 'refresh_token' });
  h.check('Formal current-family revocation acknowledged after concurrency', revokeConcurrent.status === 200);
  h.check('No concurrent winner remains usable after formal disposition', !(await inspect(h, f, winner.refresh_token)).active);
  const d = await authorization(h, f, 'explicit-revoke');
  h.check('Independent new authorization remains usable after other family replay', (await inspect(h, f, d.refresh_token)).active);
  const revoke = await command(h, f, 'explicit-revoke', '/api/v1/cas/oauth/revoke', { ...identityForm(f), token: d.refresh_token, token_type_hint: 'refresh_token' });
  h.check('Original client explicitly revokes its exact active refresh family', revoke.status === 200);
  h.check('Independent read confirms explicitly revoked family inactive', !(await inspect(h, f, d.refresh_token)).active);
  rejected(h, await refresh(h, f, 'explicit-revoked-refresh', d.refresh_token), 'invalid_grant', 'Explicitly revoked original grant cannot mint credentials');
  for (const actor of [h.user, h.tenantAdmin, h.otherTenantAdmin, h.admin]) await h.ok(actor, 'GET', '/api/v1/web/session/');
  h.observe({ kind: 'refresh-family-coverage', subject, namespace: n, clientId: owner.value.clientId, authorizationGrants: 3, concurrentWinners: 1, concurrentWinnerActiveBeforeDisposition: concurrencyActive, auditFamilyId: family, lifecycle: 'All tracked original families inactive; formal credential/client cleanup follows. Natural expiry and CAS5xx are separate special branches.' });
} };
handlers['F001-005'].actors = ['user', 'tenantAdmin', 'otherTenantAdmin'];
handlers['F001-005'].transport = 'owner-api';
module.exports = { handlers, command, authorization, fixture, identityForm, inspect };
