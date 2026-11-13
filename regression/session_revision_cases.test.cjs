const { test } = require('node:test');
const assert = require('node:assert/strict');
const { claims } = require('./session_revision_cases.cjs');
test('revision comparison rejects unsafe or nonhuman original JWT projections and preserves exact issued authority revision', () => {
  const token = value => 'header.' + Buffer.from(JSON.stringify(value)).toString('base64url') + '.signature';
  assert.equal(claims(token({ sub: 'account:123', authority_revision: 7 })).authority_revision, 7);
  for (const value of [{ sub: 'endpoint:1', authority_revision: 2 }, { sub: 'account:1', authority_revision: -1 }, { sub: 'account:1' }, { sub: 'account:1', authority_revision: 9007199254740992 }]) assert.throws(() => claims(token(value)));
  assert.throws(() => claims('not-a-token'));
});
