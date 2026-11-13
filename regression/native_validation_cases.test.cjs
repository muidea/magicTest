const { test } = require('node:test');
const assert = require('node:assert/strict');
const { variants, preciseIssue, rawSecretAbsent } = require('./native_validation_cases.cjs');
const { targetRejection } = require('./native_admission.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
const { sanitize } = require('./evidence_sanitizer.cjs');
const original = { contract: { components: { api: { image: 'postgres:17.7-alpine3.22', mounts: [{ volumeRef: 'data', target: '/data' }] } } } };
test('native configuration matrix preserves control input and rejects authentication, earlier stages, foreign values and unrelated issues', () => {
  const copy = structuredClone(original), values = variants(original, 'private-literal');
  assert.deepEqual(original, copy); assert.equal(values.length, 13);
  for (const v of values) {
    const issue = { code: v.code, componentKey: 'api', fieldPath: v.fieldPath[0], message: v.variant === 'duplicate-port' ? '组件端口与 second 重复' : v.messages[0], blocking: true };
    const view = { valid: false, publishable: false, digest: '', issues: [issue] };
    assert.equal(preciseIssue(view, v), true);
    for (const change of [x => x.valid = true, x => x.publishable = true, x => x.digest = 'unrelated', x => x.issues[0].code = 'wrong-stage', x => x.issues[0].fieldPath = 'unrelated', x => x.issues[0].message = 'unrelated', x => x.issues.push(issue)]) {
      const other = structuredClone(view); change(other); assert.equal(preciseIssue(other, v), false);
    }
    const response = { status: 400, data: { error: { code: 4, message: issue.fieldPath + ': ' + issue.message } } };
    assert.equal(targetRejection(response, v.variant), true);
    assert.equal(targetRejection({ ...response, status: 401 }, v.variant), false);
    assert.equal(targetRejection({ ...response, data: { ...response.data, value: { id: 17 } } }, v.variant), false);
    assert.equal(targetRejection({ status: 400, data: { error: { code: 4, message: '生成前必须完成应用包预检确认' } } }, v.variant), false);
  }
});
test('secret echo is checked on raw response even when evidence sanitizer would hide it', () => {
  const secret = 'private-literal', response = { data: { value: { normalized: { environment: { DATABASE_PASSWORD: { literal: secret } } } } } };
  assert.equal(rawSecretAbsent(response, secret), false);
  assert.equal(rawSecretAbsent(sanitize(response), secret), true);
  assert.equal(rawSecretAbsent({ data: { error: { code: 4, message: '敏感环境变量必须使用 secretRef' } } }, secret), true);
});
test('native rejection recovery binds original payload, stage, actor, receipt and complete before/after owner state', () => {
  const r = { kind: 'native-admission-probe', phase: 'intent', actor: 'admin', actorIdentity: { account: 'original' }, origin: 'https://panel.test',
    route: '/panel/application/deployment-packages/builds/', variant: 'sensitive-literal', journalId: 'original-intent', outcome: 'unknown',
    intended: variants(original, 'private-literal').at(-1).input, before: { packages: [] } };
  const originalEvidence = sanitize({ resources: [{ ...structuredClone(r), confirmed: false }], trace: [] });
  assert.equal(bindOriginalCleanup({ resources: [r] }, originalEvidence)[0], r);
  for (const mutate of [x => x.route += 'preview', x => x.variant = 'invalid-port', x => x.journalId = 'replacement', x => x.outcome = 'rejected-before-registration', x => x.before.packages.push({ id: 17 }), x => x.intended.contract.components.api.image = 'different:1', x => x.response = { status: 400 }, x => x.after = { packages: [] }]) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, originalEvidence), /differs/);
  }
});
