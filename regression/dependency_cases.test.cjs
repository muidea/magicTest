const { test } = require('node:test');
const assert = require('node:assert/strict');
const { missingDependencyIssue } = require('./dependency_cases.cjs');
test('dependency validation requires exact missing-reference stage, no accepted digest and one blocking target issue', () => {
  const good = { valid: false, publishable: false, issues: [{ code: 'dependency.componentRef', blocking: true, componentKey: 'api', fieldPath: 'components.api.dependsOn', message: '组件依赖引用无效' }] };
  assert.equal(missingDependencyIssue(good), true);
  for (const change of [v => v.valid = true, v => v.publishable = true, v => v.digest = 'sha256:' + 'a'.repeat(64),
    v => v.issues[0].code = 'unrelated', v => v.issues[0].blocking = false, v => v.issues[0].componentKey = 'other', v => v.issues[0].fieldPath = 'components.api.image',
    v => v.issues[0].message = 'unrelated auth error', v => v.issues.push({ ...v.issues[0] }), v => v.issues = []]) {
    const value = structuredClone(good); change(value); assert.equal(missingDependencyIssue(value), false);
  }
  assert.equal(missingDependencyIssue(undefined), false);
});
