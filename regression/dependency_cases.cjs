// Dependency admission is checked at each public consumer before execution.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const admission = require('./native_admission.cjs');
const packages = '/panel/application/deployment-packages/';
function missingDependencyIssue(value) {
  const issue = value?.issues?.[0];
  return value?.valid === false && value.publishable === false && !value.digest && value.issues.length === 1 &&
    issue.code === 'dependency.componentRef' && issue.blocking === true && issue.componentKey === 'api' && issue.fieldPath === 'components.api.dependsOn' &&
    issue.message === '组件依赖引用无效';
}
async function missing(h) {
  const input = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-dependency', releaseVersion: '1.0.0',
    contract: { apiVersion: 'magic.native-orchestration/v1', components: { api: { image: 'postgres:17.7-alpine3.22' } } } };
  const before = await h.directory(h.admin, packages);
  const positive = (await h.ok(h.admin, 'POST', packages + 'builds/preview', input)).value;
  h.check('Positive dependency control resolves the actual local image and exact component before negative probes',
    positive.applicationUuid === input.applicationUuid && positive.applicationName === input.applicationName &&
    positive.nativeContractVersion === input.contract.apiVersion && /^sha256:[a-f0-9]{64}$/.test(positive.buildDigest) &&
    positive.components?.length === 1 && positive.components[0].key === 'api' && /^sha256:[a-f0-9]{64}$/.test(positive.components[0].imageDigest));
  const invalid = structuredClone(input);
  invalid.contract.components.api.dependsOn = [{ componentRef: 'missing', condition: 'started' }];
  const draft = await h.ok(h.admin, 'POST', '/panel/application/orchestrations/validate-draft', invalid.contract);
  h.check('Real draft validator identifies only the missing component dependency', missingDependencyIssue(draft.value), draft);
  const preview = await h.api(h.admin, 'POST', packages + 'builds/preview', invalid);
  h.check('Real build preview rejects the exact missing dependency before registration', admission.targetRejection(preview, 'missing-dependency'), preview);
  // The valid digest supplies an envelope, never a claim of valid bad content.
  await admission.probe(h, { intended: { ...invalid, expectedBuildDigest: positive.buildDigest }, variant: 'missing-dependency' });
  h.check('Draft, preview and actual build refusals preserve the complete original package directory', same(await h.directory(h.admin, packages), before));
}
async function dependencies(h) {
  await missing(h);
  // Reuse the same real approval fence as storage admission: a registered
  // disabled resource, then its exact dedicated foreign-namespace placement.
  // It journals, independently reads and disposes each original request.
  await require('./storage_admission_cases.cjs').handlers['F048-002'](h);
}
dependencies.transport = 'owner-api';
dependencies.actors = ['tenantAdmin'];
module.exports = { handlers: { 'F024-002': dependencies }, missingDependencyIssue };
