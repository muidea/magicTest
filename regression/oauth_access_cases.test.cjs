const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { verifiedAccess } = require('./oauth_access_cases.cjs');
test('actual RSA signature and exact audience/subject/tenant/current authority/time are required before using access claims', () => {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const key = { ...publicKey.export({ format: 'jwk' }), kid: 'test-kid', use: 'sig', alg: 'RS256' };
  const expected = { issuer: 'https://a.test', namespace: 'a', subject: 'account:7', clientId: 'client-a', audiences: ['api://management'], scope: 'openid profile' };
  const claims = { iss: expected.issuer, sub: expected.subject, client_id: expected.clientId, client_namespace: 'a', namespace: 'a', active_namespace: 'a', scope: expected.scope, aud: expected.audiences, namespace_scope: ['a'], authority_revision: 3, exp: 1200, iat: 900, jti: 'one' };
  const signed = c => {
    const data = Buffer.from(JSON.stringify({ alg: 'RS256', kid: 'test-kid' })).toString('base64url') + '.' + Buffer.from(JSON.stringify(c)).toString('base64url');
    return data + '.' + crypto.sign('RSA-SHA256', Buffer.from(data), privateKey).toString('base64url');
  };
  assert.deepEqual(verifiedAccess(signed(claims), { keys: [key] }, expected, 1000), claims);
  for (const patch of [{ sub: 'account:8' }, { namespace: 'b' }, { client_namespace: 'b' }, { active_namespace: 'b' }, { iss: 'https://b.test' }, { client_id: 'client-b' }, { aud: 'api://management' }, { aud: ['api://other'] }, { authority_revision: 0 }, { exp: 999 }, { iat: 1100 }, { scope: 'cas.accounts.write' }]) assert.equal(verifiedAccess(signed({ ...claims, ...patch }), { keys: [key] }, expected, 1000), null);
  const original = signed(claims).split('.'); original[1] = Buffer.from(JSON.stringify({ ...claims, sub: 'account:8' })).toString('base64url');
  assert.equal(verifiedAccess(original.join('.'), { keys: [key] }, { ...expected, subject: 'account:8' }, 1000), null);
  assert.equal(verifiedAccess(signed(claims), { keys: [key, key] }, expected, 1000), null);
});
