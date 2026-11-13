const { test } = require('node:test');
const assert = require('node:assert/strict');
const { receiptMatches } = require('./namespace_retirement_cases.cjs');
test('namespace retirement proof rejects partial, foreign and incomplete original aggregate receipts', () => {
  const r = { id: 71, name: 'original' }, value = { namespaceId: 71, name: 'original', phase: 'complete', requestId: 'a'.repeat(32), expectedVersion: 4, revision: 6 };
  assert.equal(receiptMatches(r, value), true);
  for (const mutate of [v => v.namespaceId++, v => v.name = 'peer', v => v.phase = 'pending', v => delete v.requestId, v => v.expectedVersion = 0, v => v.revision = 0]) {
    const bad = structuredClone(value); mutate(bad); assert.equal(receiptMatches(r, bad), false);
  }
});
