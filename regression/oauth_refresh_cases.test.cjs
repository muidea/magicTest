const { test } = require('node:test');
const assert = require('node:assert/strict');
const { command } = require('./oauth_refresh_cases.cjs');
test('unknown original OAuth mutation is persisted and is never replayed', async () => {
  let dispatched = 0, saved;
  const f = { n: 'a', owner: { value: { clientId: 'client-a' }, resource: {} } };
  const h = { Blocked: Error, user: {}, persist() { saved = structuredClone(f.owner.resource); }, protocol: async (actor, method, endpoint, form) => {
    dispatched++; assert.equal(saved.protocolCommands[0].outcome, 'unknown');
    assert.deepEqual(saved.protocolCommands[0].form, form);
    throw Error('original response lost');
  } };
  await assert.rejects(command(h, f, 'rotate', '/api/v1/cas/oauth/token', { refresh_token: 'private-original' }), /response lost/);
  await assert.rejects(command(h, f, 'rotate', '/api/v1/cas/oauth/token', { refresh_token: 'private-original' }), /no replay/);
  assert.equal(dispatched, 1);
});
test('write-ahead failure prevents OAuth dispatch, and concurrent labels retain separate original intents', async () => {
  const f = { n: 'a', owner: { value: { clientId: 'client-a' }, resource: {} } };
  let calls = 0;
  const h = { Blocked: Error, user: {}, persist() { throw Error('disk unavailable'); }, protocol: async () => { calls++; } };
  await assert.rejects(command(h, f, 'first', '/api/v1/cas/oauth/token', {}), /disk/);
  assert.equal(calls, 0);
  h.persist = () => {};
  h.protocol = async () => { calls++; return { status: 400, data: { error: 'invalid_grant' } }; };
  const result = await Promise.all([command(h, f, 'parallel-a', '/api/v1/cas/oauth/token', {}), command(h, f, 'parallel-b', '/api/v1/cas/oauth/token', {})]);
  assert.equal(calls, 2); assert.equal(result.length, 2);
  assert.ok(f.owner.resource.protocolCommands.slice(1).every(r => r.outcome === 'response-received'));
});
