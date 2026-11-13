// Only component readiness/endpoint and nonsecret parameter injection are
// exercised here; no fake database, service identity or secret is substituted.
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const native = require('./native_runtime_cases.cjs');
function input(h) {
  const value = native.input(h, false), api = value.contract.components.api;
  value.applicationName = h.state.prefix + '-dependency-runtime';
  value.contract.parameters = {
    required_label: { type: 'string', required: true, default: h.state.prefix + '-required' },
    optional_label: { type: 'string', required: false, default: h.state.prefix + '-optional' }
  };
  const command = 'set -eu\nprintf \'{"marker":"%s","hostname":"%s"}\\n\' "$REGRESSION_MARKER" "$(hostname)" > /tmp/probe.json\nprintf \'user root; events {} http { server { listen 8080; location / { root /tmp; } } }\\n\' > /tmp/regression-nginx.conf\nexec nginx -g "daemon off;" -c /tmp/regression-nginx.conf';
  value.contract.components.worker = { image: api.image, entrypoint: ['/bin/sh'], command: ['-c', command], workingDir: '/tmp', restart: 'no',
    environment: { REGRESSION_MARKER: { literal: h.state.prefix + '-dependency-worker' } }, ports: { http: { containerPort: 8080, protocol: 'http' } },
    readiness: { type: 'http', portRef: 'http', path: '/probe.json', timeoutSeconds: 5, retries: 5 } };
  api.dependsOn = [{ componentRef: 'worker', condition: 'ready', timeoutSeconds: 120 }];
  api.environment.REGRESSION_DEPENDENCY = { componentEndpointRef: { component: 'worker', port: 'http' } };
  api.environment.REGRESSION_REQUIRED = { parameterRef: 'required_label' };
  api.environment.REGRESSION_OPTIONAL = { parameterRef: 'optional_label' };
  api.command[1] = api.command[1].replace('exec nginx ', 'wget -qO /data/dependency.json "$REGRESSION_DEPENDENCY/probe.json"\nexec nginx ');
  return value;
}
function ownedContainer(h, r, key, run = execFileSync) {
  const matches = r.installation.packagedReceipt.components.filter(v => v.key === key);
  if (matches.length !== 1 || !/^[a-f0-9]{64}$/.test(matches[0].containerId || '')) throw new h.Blocked('Exact original dependency container identity required');
  const c = matches[0], actual = JSON.parse(run('docker', ['inspect', c.containerId], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }))[0];
  h.check('Independent Docker container binds exact owner ID/image/deployment/runtime identity', actual.Id === c.containerId && actual.Image === c.imageId && actual.State.Running === true &&
    actual.Config.Labels['io.platform.deployment-id'] === r.last.deploymentId && actual.Config.Labels['io.platform.runtime.application-uuid'] === r.installation.packagedReceipt.runtimeApplicationUuid);
  return actual;
}
async function dependencies(h) {
  const source = await require('./delivery_cases.cjs').fixture(h), before = [];
  for (const i of source.installations) before.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value);
  const value = input(h), pkg = await require('./native_package_cases.cjs').build(h, value);
  const r = await native.install(h, pkg.package, value, 'dependencies');
  // All container operations below are reads of the exact owner-returned IDs.
  // The application itself consumes its injected endpoint during startup.
  const api = ownedContainer(h, r, 'api'), worker = ownedContainer(h, r, 'worker');
  h.check('Two exact components have distinct actual IDs and expected required/optional default injection', api.Id !== worker.Id &&
    api.Config.Env.includes('REGRESSION_REQUIRED=' + value.contract.parameters.required_label.default) && api.Config.Env.includes('REGRESSION_OPTIONAL=' + value.contract.parameters.optional_label.default));
  const readFile = (id, file) => JSON.parse(execFileSync('docker', ['exec', id, 'cat', file], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }));
  const consumed = readFile(api.Id, '/data/dependency.json'), produced = readFile(worker.Id, '/tmp/probe.json');
  h.check('Actual application startup consumed real ready dependency endpoint and exact independently read worker response', same(consumed, produced) &&
    produced.hostname === worker.Config.Hostname && produced.marker === value.contract.components.worker.environment.REGRESSION_MARKER.literal, { consumed, produced });
  h.observe({ kind: 'native-dependency-consumption', requestId: r.id, operationId: r.operation.id, installationId: r.installation.id,
    apiId: api.Id, workerId: worker.Id, produced, consumed });
  await native.cleanup(h, r); await require('./native_provider_access_cases.cjs').cleanup(h, pkg);
  for (const i of before) h.check('Dependency runtime and reviewed cleanup preserve all unrelated installed peers', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
  await h.partial('Real ready component dependency, scoped endpoint consumed by application, required/optional nonsecret parameter defaults and exact two-container retirement implemented. Database/service/secret resources and explicit optional-absence matrix remain open.');
}
dependencies.transport = 'owner-api'; dependencies.requiresOnlyDeliveryFixture = true;
module.exports = { handlers: { 'F024-001': dependencies }, input, ownedContainer };
