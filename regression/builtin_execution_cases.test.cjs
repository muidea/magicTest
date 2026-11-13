const { test } = require('node:test');
const assert = require('node:assert/strict');
const { outputMatches } = require('./builtin_execution_cases.cjs');
test('builtin output assertion requires actual script replacement, primary key, version and all unrelated submitted fields', () => {
  const body = { fields: [{ name: 'name', value: 'Δ' }, { name: 'description', value: 'input' }, { name: 'sortOrder', value: 0 }] };
  const receipt = { id: '9007199254740993', version: '1' }, value = { id: receipt.id, version: 1, name: 'Δ', description: 'Δ', sortOrder: 0 };
  assert.ok(outputMatches(value, body, receipt));
  for (const change of [{ description: 'input' }, { sortOrder: 1 }, { id: '9007199254740992' }, { version: 2 }, { name: 'other' }])
    assert.equal(outputMatches({ ...value, ...change }, body, receipt), false);
});
