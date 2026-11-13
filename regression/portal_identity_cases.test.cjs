const { test } = require('node:test');
const assert = require('node:assert/strict');
const { switchActor } = require('./portal_identity_cases.cjs');
test('same-context login switch refuses unknown original commands and foreign context/tenant before logout or credentials', async () => {
  const context = {}, page = { goto: () => assert.fail('must not start logout') }, origin = 'https://panel.test';
  const current = { context, page, origin, identity: { namespace: 'panel', account: 'A' } }, target = { context: {}, page: {}, origin, identity: { namespace: 'panel', account: 'B' } };
  const h = { Blocked: Error, persist: () => assert.fail('must not record a replacement intent'), api: () => assert.fail('must not dispatch') };
  for (const journal of [{ context: {}, page, commands: [] }, { context, page: {}, commands: [] }, { context, page, commands: [{ outcome: 'unknown' }] }])
    await assert.rejects(switchActor(h, current, target, journal), /cannot be replayed/);
  await assert.rejects(switchActor(h, current, { ...target, origin: 'https://foreign.test' }, { context, page, commands: [] }));
  await assert.rejects(switchActor(h, current, { ...target, identity: { namespace: 'foreign', account: 'B' } }, { context, page, commands: [] }));
});
