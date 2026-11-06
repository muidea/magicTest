const { test } = require('node:test');
const assert = require('node:assert/strict');
const { directoryValues, registrationAuthority } = require('./registration_cases.cjs');
const h = { Blocked: Error };

test('owner empty directory with total zero is readable', () => {
  assert.deepEqual(directoryValues(h, { values: null, pagination: { total: 0 } }), []);
  assert.deepEqual(directoryValues(h, { values: [], pagination: { total: 0 } }), []);
  const rows = [{ id: 7 }];
  assert.equal(directoryValues(h, { values: rows, pagination: { total: 1 } }), rows);
});

test('registration authority uses exact source, subject and protected role set', () => {
  const check = { check(label, condition) { assert.ok(condition, label); } };
  const roleRefs = [{ module: 'runner', key: 'portal-viewer' }];
  const binding = { subjectType: 'account', subjectId: 7, sourceType: 'registration', sourceKey: 'account-registration:7', sourceVersion: 1, status: 2, roleModule: 'runner', roleKey: 'portal-viewer' };
  registrationAuthority(check, 7, roleRefs, [binding]);
  for (const change of [
    { subjectId: 8 }, { subjectType: 'endpoint' }, { sourceType: 'template' },
    { sourceKey: 'account-registration:8' }, { sourceVersion: 0 }, { status: 1 },
    { roleKey: 'management-admin' },
  ]) assert.throws(() => registrationAuthority(check, 7, roleRefs, [{ ...binding, ...change }]));
  assert.throws(() => registrationAuthority(check, 7, roleRefs, []));
  assert.throws(() => registrationAuthority(check, 7, roleRefs, [binding, binding]));
});

test('missing or incomplete registration identity rows never become an empty directory', () => {
  for (const page of [
    { values: null, pagination: { total: 1 } },
    { values: null },
    { pagination: { total: 0 } },
    { values: [], pagination: { total: 1 } },
    { values: [], pagination: { total: 0, hasMore: true } },
  ]) assert.throws(() => directoryValues(h, page), /requires complete reader/);
});
