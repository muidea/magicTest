const { test } = require('node:test');
const assert = require('node:assert/strict');
const { sameAuthority, sameAccounts } = require('./authority_snapshot.cjs');
const account = () => ({ id: 17, account: 'member', status: 2, authorityRevision: 4,
  templateRefs: [{ key: 'portal-user', version: 1 }, { key: 'security-admin', version: 3 }],
  effectiveRoles: [{ module: 'cas', key: 'reader' }, { module: 'runner', key: 'editor' }],
  effectivePrivileges: [{ module: 'cas', uriPath: '/accounts/', value: 1 }, { module: 'runner', uriPath: '/models/', value: 3 }],
  orderedSteps: ['first', 'second'] });
test('CAS account and authority collections allow order changes without mutating either response', () => {
  const before = [account(), { ...account(), id: 18 }], original = structuredClone(before);
  const after = structuredClone(before).reverse();
  for (const item of after) for (const key of ['templateRefs', 'effectiveRoles', 'effectivePrivileges']) item[key].reverse();
  assert.ok(sameAccounts(before, after)); assert.deepEqual(before, original);
  assert.ok(sameAuthority({ roleRefs: [{ key: 'a', module: 'b' }] }, { roleRefs: [{ module: 'b', key: 'a' }] }));
});
test('account changes, duplicates, removed fields and changed revisions are never normalized away', () => {
  const before = account();
  const changes = [a => a.id++, a => a.status = 1, a => a.authorityRevision++, a => a.account = 'other',
    a => a.templateRefs.pop(), a => a.templateRefs.push(a.templateRefs[0]), a => a.templateRefs[0].version++,
    a => a.effectivePrivileges[0].value++, a => a.effectiveRoles[0].module = 'other',
    a => delete a.status, a => a.newField = true, a => a.orderedSteps.reverse()];
  for (const change of changes) { const after = structuredClone(before); change(after); assert.equal(sameAuthority(before, after), false); }
  assert.equal(sameAccounts([before], [before, { ...before, id: 18 }]), false);
  assert.equal(sameAccounts([before], []), false);
  for (const rows of [[before, before], [{ ...before, id: Number.MAX_SAFE_INTEGER + 1 }], [null], null]) assert.throws(() => sameAccounts([before], rows));
});
test('only top-level CAS authority fields have unordered semantics', () => {
  const before = { effectiveRoles: [{ key: 'role', ordered: [1, 2] }], nested: { roleRefs: ['a', 'b'] } };
  for (const change of [a => a.effectiveRoles[0].ordered.reverse(), a => a.nested.roleRefs.reverse()]) {
    const after = structuredClone(before); change(after); assert.equal(sameAuthority(before, after), false);
  }
  assert.equal(sameAuthority({}, { templateRefs: [] }), false);
});
