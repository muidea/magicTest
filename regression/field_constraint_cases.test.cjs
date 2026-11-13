const { test } = require('node:test');
const assert = require('node:assert/strict');
const business = require('./business_cases.cjs');
const { reject } = require('./field_constraint_cases.cjs');
test('field validation requires exact refusal stage, exact original receipt absence and complete unchanged record', async () => {
  const realRead = business.record;
  try {
    for (const mode of ['valid', 'auth', 'wrong-field', 'wrong-code', 'receipt-present', 'receipt-error', 'row-changed', 'lost', 'actor-changed']) {
      const actor = { origin: 'https://example.invalid', identity: { account: 'ordinary', namespace: 'tenant' } };
      const r = { origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [], recordId: '7', version: '1', identity: { deploymentId: 'original' }, applicationKey: 'original-app' };
      let writes = 0, reads = 0;
      business.record = async () => ({ status: 200, data: { value: { id: 7, version: 1, name: mode === 'row-changed' && reads++ ? 'unexpected' : 'original', description: null } } });
      const expected = { code: 21, message: '写入标量类型或约束无效: name' };
      const h = { Blocked: Error, persist() {}, good: v => v.status === 200 && !v.data.error,
        check(label, value) { assert.ok(value, label); }, async api(original, method, route, body) {
          assert.equal(original, actor); assert.equal(method, 'POST'); assert.equal(body.id, '7'); assert.equal(body.expectedVersion, '1');
          if (route.includes('/execute/')) {
            writes++;
            if (mode === 'lost') throw Error('original response lost');
            return { status: mode === 'auth' ? 401 : 200, data: { error: { code: mode === 'wrong-code' ? 4 : 21, message: mode === 'wrong-field' ? '写入标量类型或约束无效: other' : expected.message }, value: null } };
          }
          assert.match(route, /\/receipt\//); assert.equal(body.operationId, r.constraintCommands[0].body.operationId);
          if (mode === 'receipt-present') return { status: 200, data: { value: { id: '8' } } };
          return { status: mode === 'receipt-error' ? 503 : 200, data: { error: { code: 2, message: '原业务写入尚无完成事实；禁止据此自动重发' }, value: null } };
        } };
      if (mode === 'actor-changed') actor.identity.account = 'replacement';
      if (mode === 'valid') { await reject(h, actor, r, 'name', null, expected); assert.equal(r.constraintCommands[0].outcome, 'rejected-and-unchanged'); }
      else {
        await assert.rejects(reject(h, actor, r, 'name', null, expected));
        const count = writes;
        await assert.rejects(reject(h, actor, r, 'name', null, expected), /no replacement write/);
        await assert.rejects(business.cleanup(h, r), mode === 'actor-changed' ? /fixture|readFile|owner|actor|undefined/i : /validation command remains unresolved/);
        assert.equal(writes, count);
      }
      assert.equal(writes, mode === 'actor-changed' ? 0 : 1);
    }
  } finally { business.record = realRead; }
});
