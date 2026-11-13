const { test } = require('node:test');
const assert = require('node:assert/strict');
const { memberProjection, listView, replacedTemplateCounts } = require('./member_directory_cases.cjs');
test('changing a member template updates exact live subject counts while preserving all template definitions', () => {
  const before = [{ id: 1, subjectCount: 6, roleRefs: ['reader'] }, { id: 2, subjectCount: 0, roleRefs: ['reader'] }, { id: 3, subjectCount: 1 }];
  const after = structuredClone(before); after[0].subjectCount--; after[1].subjectCount++;
  assert.equal(replacedTemplateCounts(before, after, before[0], before[1]), true);
  assert.equal(replacedTemplateCounts(before, before, before[0], before[1]), false);
  for (const change of [v => v[0].roleRefs = ['manager'], v => v[1].subjectCount++, v => v.pop()]) {
    const bad = structuredClone(after); change(bad); assert.equal(replacedTemplateCounts(before, bad, before[0], before[1]), false);
  }
});
test('account list excludes only the documented detail privilege projection', () => {
  const detail = { id: 7, account: 'original', effectiveRoles: [{ module: 'portal', key: 'reader' }], effectivePrivileges: [{ path: '/portal' }] };
  const listed = { id: 7, account: 'original', effectiveRoles: [{ module: 'portal', key: 'reader' }] };
  assert.deepEqual(listView(detail), listed);
  assert.notDeepEqual(listView({ ...detail, effectiveRoles: [] }), listed);
  assert.equal(detail.effectivePrivileges.length, 1);
});
test('complete member projection requires its own current template source and exact effective role set', () => {
  const template = { key: 'current', roleRefs: [{ module: 'portal', key: 'reader' }] };
  const account = { id: 7, status: 2, templateRefs: [{ key: 'current' }], effectiveRoles: structuredClone(template.roleRefs) };
  const binding = { id: 8, subjectType: 'account', subjectId: 7, status: 2, sourceType: 'template', sourceKey: 'current', sourceVersion: 1, roleModule: 'portal', roleKey: 'reader' };
  assert.equal(memberProjection(account, [binding], template), true);
  for (const change of [v => v.subjectId++, v => v.sourceKey = 'old', v => v.status = 1, v => v.roleKey = 'manager', v => v.sourceType = 'direct', v => v.sourceVersion = 0]) {
    const bad = structuredClone(binding); change(bad); assert.equal(memberProjection(account, [bad], template), false);
  }
  assert.equal(memberProjection({ ...account, effectiveRoles: [...account.effectiveRoles, { module: 'panel', key: 'admin' }] }, [binding], template), false);
  assert.equal(memberProjection(account, [binding, { ...binding, id: 9 }], template), false);
});
