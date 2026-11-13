const { test } = require('node:test');
const assert = require('node:assert/strict');
const { machineRefusal } = require('./runtime_identity_cases.cjs');
test('runtime impersonation requires exact empty machine-registry403, not login, missing route, or a leaked snapshot', () => {
  assert.ok(machineRefusal({ status: 403, data: { text: '' } }));
  for (const response of [{ status: 401, data: { text: '' } }, { status: 404, data: { text: '' } },
    { status: 403, data: { text: 'upstream denied' } }, { status: 403, data: { text: '', value: { assignments: [] } } }, { status: 403 }])
    assert.equal(machineRefusal(response), false);
});
