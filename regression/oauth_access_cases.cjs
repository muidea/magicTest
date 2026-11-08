const crypto = require('node:crypto');
const refresh = require('./oauth_refresh_cases.cjs');
const identities = require('./cas_identity_cases.cjs');

// Verify with the actual issuer's public key before interpreting any claims.
function verifiedAccess(token, jwks, expected, now = Date.now() / 1000) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const header = JSON.parse(Buffer.from(parts[0], 'base64url'));
    const keys = jwks.keys.filter(k => k.kid === header.kid && k.kty === 'RSA' && (!k.alg || k.alg === 'RS256') && (!k.use || k.use === 'sig'));
    if (header.alg !== 'RS256' || !header.kid || keys.length !== 1 || !crypto.verify('RSA-SHA256', Buffer.from(parts[0] + '.' + parts[1]), crypto.createPublicKey({ key: keys[0], format: 'jwk' }), Buffer.from(parts[2], 'base64url'))) return null;
    const c = JSON.parse(Buffer.from(parts[1], 'base64url'));
    if (c.iss !== expected.issuer || c.sub !== expected.subject || c.client_id !== expected.clientId || c.client_namespace !== expected.namespace || c.namespace !== expected.namespace || c.active_namespace !== expected.namespace || c.scope !== expected.scope || !Array.isArray(c.aud) || c.aud.length !== expected.audiences.length || !expected.audiences.every(a => c.aud.includes(a)) || !Array.isArray(c.namespace_scope) || !c.namespace_scope.includes(expected.namespace) || !Number.isSafeInteger(c.authority_revision) || c.authority_revision <= 0 || !Number.isSafeInteger(c.exp) || !Number.isSafeInteger(c.iat) || c.iat > now + 5 || c.exp <= now || c.exp <= c.iat || !c.jti) return null;
    return c;
  } catch { return null; }
}
async function verify(h, f, token, subject, scope) {
  const discovery = await h.publicGet(h.user, '/.well-known/openid-configuration');
  h.check('Actual tenant discovery binds issuer and canonical public JWKS', discovery.status === 200 && discovery.data.issuer === h.user.origin && discovery.data.jwks_uri === h.user.origin + '/api/v1/cas/oauth/jwks');
  const jwks = await h.protocol(h.user, 'GET', '/api/v1/cas/oauth/jwks');
  h.check('Public issuer returns its actual signing-key set', jwks.status === 200 && Array.isArray(jwks.data.keys) && jwks.data.keys.length > 0);
  const claims = verifiedAccess(token, jwks.data, { issuer: discovery.data.issuer, subject, namespace: f.n, clientId: f.owner.value.clientId, scope, audiences: f.owner.value.audience.split(/\s+/) });
  h.check('Actual access token signature, issuer, audience, subject, namespace, scope, current authority and expiry match the exact grant', !!claims);
  const read = await refresh.inspect(h, f, token, 'access_token');
  h.check('Independent CAS validates the same active original token identity and lifetime', read.active && read.sub === subject && read.client_id === claims.client_id && read.namespace === claims.namespace && read.iss === claims.iss && read.exp === claims.exp && read.iat === claims.iat && read.jti === claims.jti && read.scope === claims.scope);
  h.observe({ kind: 'oauth-access-verification', clientId: claims.client_id, subject, namespace: claims.namespace, issuer: claims.iss, audience: claims.aud, scope: claims.scope, authorityRevision: claims.authority_revision, expiresAt: claims.exp, signingKeySource: discovery.data.jwks_uri });
  return claims;
}
async function retireCredential(h, f) {
  const proof = await identities.cleanup(h, f.credential.resource);
  f.credential.resource.phase = 'deleted'; h.persist();
  return proof;
}
function noPair(h, response, code, label) {
  h.check(label, response.status === 400 && response.data.error === code && !response.data.access_token && !response.data.refresh_token && !response.data.id_token, response);
}
const handlers = { 'F008-001': async h => {
  const human = await refresh.fixture(h, 'oauth-access'), pair = await refresh.authorization(h, human, 'access');
  const account = (await h.ok(h.tenantAdmin, 'GET', '/cas/namespaces/' + human.n + '/accounts/' + human.subject.slice('account:'.length))).value;
  const humanClaims = await verify(h, human, pair.access_token, human.subject, 'openid profile');
  // Opaque functional permission proofs accompany the current subject even
  // for identity scopes. Effective scope and application grants remain the
  // independent ceilings; do not equate those proofs with a new grant.
  h.check('Identity-only human grant matches current CAS revision without application authorization grants', humanClaims.authority_revision === account.authorityRevision && !(humanClaims.authorization_grants || []).length);
  const outsideScope = await h.protocol(h.user, 'GET', '/api/v1/cas/namespaces/' + human.n + '/accounts/' + account.id, undefined, { Authorization: 'Bearer ' + pair.access_token });
  h.check('Identity-only token cannot read management account data despite current functional permission proofs', outsideScope.status === 403 && outsideScope.data.value == null, outsideScope);
  const userinfo = await h.protocol(h.user, 'GET', '/api/v1/cas/oauth/userinfo', undefined, { Authorization: 'Bearer ' + pair.access_token });
  h.check('OIDC UserInfo resolves the exact original ordinary account and tenant', userinfo.status === 200 && userinfo.data.sub === human.subject && userinfo.data.namespace === human.n && userinfo.data.preferred_username === h.user.identity.account);
  const unauthorizedMachine = await refresh.command(h, human, 'undeclared-client-credentials', '/api/v1/cas/oauth/token', { ...refresh.identityForm(human), grant_type: 'client_credentials', scope: 'openid profile' });
  noPair(h, unauthorizedMachine, 'unauthorized_client', 'Authorization-code client cannot invoke its undeclared machine grant');
  const m = await identities.machine(h, 'oauth-machine');
  const machineScope = m.owner.value.allowedScopes;
  const machinePair = await refresh.command(h, m, 'machine-access', '/api/v1/cas/oauth/token', { ...refresh.identityForm(m), grant_type: 'client_credentials', scope: machineScope });
  h.check('Actual declared machine grant issues only an access token', machinePair.status === 200 && typeof machinePair.data.access_token === 'string' && !machinePair.data.refresh_token && !machinePair.data.id_token);
  const machineClaims = await verify(h, m, machinePair.data.access_token, 'endpoint:' + m.endpoint.id, machineScope);
  const endpoint = (await h.ok(h.tenantAdmin, 'GET', '/cas/namespaces/' + m.n + '/endpoints/' + m.endpoint.id)).value;
  h.check('Machine identity retains exact Endpoint and account and current role revision', machineClaims.endpoint_id === m.endpoint.id && machineClaims.account_id === m.account.id && machineClaims.authority_revision === endpoint.authorityRevision && endpoint.templateRefs.some(t => m.payload.roleTemplateKeys.includes(t.key)));
  const unauthorizedCode = await refresh.command(h, m, 'undeclared-code', '/api/v1/cas/oauth/token', { ...refresh.identityForm(m), grant_type: 'authorization_code', code: 'unissued-controlled-code', redirect_uri: human.redirect, code_verifier: crypto.randomBytes(32).toString('base64url') });
  noPair(h, unauthorizedCode, 'unauthorized_client', 'Machine client cannot enter its undeclared user authorization-code grant');
  await retireCredential(h, human);
  const humanDenied = await refresh.command(h, human, 'retired-human-secret', '/api/v1/cas/oauth/token', { ...refresh.identityForm(human), grant_type: 'refresh_token', refresh_token: pair.refresh_token });
  h.check('Revoked original human client credential cannot continue its active refresh family', [400, 401].includes(humanDenied.status) && humanDenied.data.error === 'invalid_client' && !humanDenied.data.access_token && !humanDenied.data.refresh_token, humanDenied);
  await retireCredential(h, m);
  const machineDenied = await refresh.command(h, m, 'retired-machine-secret', '/api/v1/cas/oauth/token', { ...refresh.identityForm(m), grant_type: 'client_credentials', scope: machineScope });
  h.check('Revoked original machine client credential cannot issue a new token', [400, 401].includes(machineDenied.status) && machineDenied.data.error === 'invalid_client' && !machineDenied.data.access_token, machineDenied);
  for (const actor of [h.user, h.tenantAdmin, h.otherTenantAdmin, h.admin]) await h.ok(actor, 'GET', '/api/v1/web/session/');
} };
handlers['F008-001'].actors = ['user', 'tenantAdmin', 'otherTenantAdmin'];
handlers['F008-001'].transport = 'owner-api';
module.exports = { handlers, verifiedAccess };
