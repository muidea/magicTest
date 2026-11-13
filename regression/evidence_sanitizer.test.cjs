const { test } = require('node:test');
const assert = require('node:assert/strict');
const { sanitize } = require('./evidence_sanitizer.cjs');
test('temporary bound-upload capability is redacted while byte size and package digests stay diagnostic', () => {
  assert.deepEqual(sanitize({ uploadRef: 'sensitive', upload_ref: 'sensitive', digest: 'sha256:original', size: 12 }),
    { uploadRef: '[REDACTED]', upload_ref: '[REDACTED]', digest: 'sha256:original', size: 12 });
});
test('OAuth form and response credentials are redacted while numeric owner errors remain diagnostic', () => {
  const result = sanitize({ form: { code: 'private-code', state: 'private-state', nonce: 'private-nonce', transaction: 'private-tx', code_verifier: 'private-verifier', refresh_token: 'private-refresh' }, response: { error: { code: 19, message: 'conflict' } }, route: '/callback?code=private-code&state=private-state' });
  assert.doesNotMatch(JSON.stringify(result), /private-/);
  assert.equal(result.response.error.code, 19);
  assert.equal(result.response.error.message, 'conflict');
});
test('embedded File owner token errors preserve numeric codes, diagnostics and unrelated digests', () => {
  const token = 'a'.repeat(64), digest = 'b'.repeat(64);
  const result = sanitize({ error: { code: 2, message: 'NotFound filter [name:token,value:' + token + '] file absent; digest sha256:' + digest } });
  assert.equal(result.error.code, 2);
  assert.equal(result.error.message, 'NotFound filter [name:token,value:[REDACTED-FILE-TOKEN]] file absent; digest sha256:' + digest);
  assert.doesNotMatch(JSON.stringify(result), new RegExp(token));
});
