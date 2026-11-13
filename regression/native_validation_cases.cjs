// Exercise the real draft validator, preview and actual build admission. The
// private literal is compared before evidence sanitization, never logged itself.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { probe } = require('./native_admission.cjs');
const { build } = require('./native_package_cases.cjs');
const { cleanup } = require('./native_provider_access_cases.cjs');
const packages = '/panel/application/deployment-packages/';
function variants(original, secret) {
  const values = [];
  function add(name, variant, code, fieldPath, messages, change) {
    const input = structuredClone(original); change(input.contract);
    values.push({ name, variant, code, fieldPath, messages, input });
  }
  for (const [name, containerPort, protocol] of [['port-zero', 0, 'tcp'], ['port-overflow', 65536, 'http'], ['port-protocol', 8080, 'udp']])
    add(name, 'invalid-port', 'component.port', ['components.api.ports.bad'], ['组件端口声明无效，仅支持 HTTP/TCP'], c => { c.components.api.ports = { bad: { containerPort, protocol } }; });
  add('port-duplicate', 'duplicate-port', 'component.portDuplicate', ['components.api.ports.first', 'components.api.ports.second'],
    ['组件端口与 first 重复', '组件端口与 second 重复'], c => { c.components.api.ports = { first: { containerPort: 8080, protocol: 'http' }, second: { containerPort: 8080, protocol: 'tcp' } }; });
  for (const [name, target] of [['relative', 'data'], ['traversal', '/data/../outside'], ['root', '/'], ['proc', '/proc/probe'], ['sys', '/sys/probe'], ['dev', '/dev/probe'], ['runtime', '/run/probe'], ['docker-socket', '/var/run/docker.sock']])
    add('mount-' + name, 'unsafe-mount', 'mount.target', ['components.api.mounts'], ['挂载目标必须是安全的规范绝对路径'], c => { c.components.api.mounts[0].target = target; });
  add('secret-literal', 'sensitive-literal', 'environment.secret', ['components.api.environment.DATABASE_PASSWORD'], ['敏感环境变量必须使用 secretRef'], c => { c.components.api.environment = { DATABASE_PASSWORD: { literal: secret } }; });
  return values;
}
function preciseIssue(view, v) {
  if (view?.valid !== false || view.publishable !== false || (view.digest || '') !== '' || view.issues?.length !== 1) return false;
  const issue = view.issues[0];
  if (issue.code !== v.code || issue.componentKey !== 'api' || issue.blocking !== true || !v.fieldPath.includes(issue.fieldPath) || !v.messages.includes(issue.message)) return false;
  if (v.variant === 'duplicate-port') return issue.fieldPath.endsWith('.first') ? issue.message === '组件端口与 second 重复' : issue.message === '组件端口与 first 重复';
  return true;
}
function rawSecretAbsent(response, secret) { return !JSON.stringify(response).includes(secret); }
async function configuration(h) {
  const input = { applicationUuid: crypto.randomBytes(16).toString('hex'), applicationName: h.state.prefix + '-native-config', releaseVersion: '1.0.0',
    contract: { apiVersion: 'magic.native-orchestration/v1', volumes: { data: { backend: 'localDirectory', scope: 'component', accessMode: 'singleWriter', consumers: ['api'], capacity: 1048576 } },
      components: { api: { image: 'postgres:17.7-alpine3.22', ports: { low: { containerPort: 1, protocol: 'tcp' }, high: { containerPort: 65535, protocol: 'http' } }, mounts: [{ volumeRef: 'data', target: '/data' }] } } } };
  const control = (await h.ok(h.admin, 'POST', '/panel/application/orchestrations/validate-draft', input.contract)).value;
  h.check('Positive draft accepts port boundaries and managed logical-volume mount', control.valid === true && control.publishable === false && control.issues?.length === 0 && same(control.normalized?.components, input.contract.components));
  const positive = await build(h, input), digest = positive.commands[0].body.expectedBuildDigest;
  const original = await h.directory(h.admin, packages);
  h.state.fixtures.nativeValidationProbeSecret = crypto.randomBytes(24).toString('hex'); h.persist();
  const secret = h.state.fixtures.nativeValidationProbeSecret, echoed = [];
  for (const v of variants(input, secret)) {
    const draft = await h.api(h.admin, 'POST', '/panel/application/orchestrations/validate-draft', v.input.contract);
    h.check('Draft validator reaches exact ' + v.name + ' field diagnostic', h.good(draft) && preciseIssue(draft.data.value, v));
    if (!rawSecretAbsent(draft, secret)) echoed.push(v.name + ':draft');
    const preview = await h.api(h.admin, 'POST', packages + 'builds/preview', v.input);
    h.check('Preview rejects exact ' + v.name + ' before package generation', require('./native_admission.cjs').targetRejection(preview, v.variant), preview);
    if (!rawSecretAbsent(preview, secret)) echoed.push(v.name + ':preview');
    // A valid control digest is only a nonempty command envelope; this is not a
    // claim that invalid content has a valid preview digest.
    const receipt = await probe(h, { intended: { ...v.input, expectedBuildDigest: digest }, variant: v.variant });
    if (!rawSecretAbsent(receipt.response, secret)) echoed.push(v.name + ':build');
    h.check('Rejected ' + v.name + ' leaves complete original package catalog unchanged', same(await h.directory(h.admin, packages), original));
  }
  await cleanup(h, positive);
  h.check('Private sensitive literal is absent from every raw validator/preview/build response before report sanitization', echoed.length === 0, { echoStages: echoed });
}
configuration.transport = 'owner-api';
module.exports = { handlers: { 'F023-002': configuration }, variants, preciseIssue, rawSecretAbsent };
