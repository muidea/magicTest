const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { keyRead, pair, read, contraction } = require('./endpoint_authority_cases.cjs');
const { ownerRequest } = require('./owner_transport.cjs');
const { guard } = require('./scenario_commands.cjs');
const { guardFixtureAccountCleanup } = require('./resource_lifecycle.cjs');
const generated = require('./generated_service_cases.cjs');
test('real HTTP machine read sends only original ApiKey, omits cookies, and never follows redirects or retries a lost response', async () => {
  let requests = [], target = 0;
  const server = http.createServer((req, res) => {
    requests.push({ route: req.url, authorization: req.headers.authorization, cookie: req.headers.cookie, method: req.method });
    if (req.url.endsWith('/lost')) return req.socket.destroy();
    if (req.url.endsWith('/redirect')) { res.writeHead(302, { Location: '/foreign' }); return res.end('{}'); }
    if (req.url === '/foreign') target++;
    res.setHeader('Content-Type', 'application/json'); res.end('{"value":{"id":"42"}}');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port, route = '/api/v1/gateway/services/owned/get/42';
  try {
    assert.deepEqual(await keyRead(origin, route, 'original-test-key'), { status: 200, data: { value: { id: '42' } } });
    assert.equal((await keyRead(origin, route + '/redirect', 'original-test-key')).status, 302);
    await assert.rejects(keyRead(origin, route + '/lost', 'original-test-key'));
    assert.equal(target, 0); assert.equal(requests.length, 3);
    assert.ok(requests.every(r => r.authorization === 'ApiKey original-test-key' && !r.cookie && r.method === 'GET'));
    for (const bad of ['https://foreign.test/api/v1/gateway/services/x', '//foreign.test/path', '/panel/private', '/api/v1/gateway/services/../private', route + '#secret', '/api/v1/gateway/services/a/../../other']) await assert.rejects(keyRead(origin, bad, 'original-test-key'));
    assert.equal(requests.length, 3);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
test('same-account Endpoint matrix rejects shared identities, wrong subscriber, scope, disabled status and incomplete owner projection', async () => {
  for (const mode of ['exact', 'same-endpoint', 'same-client', 'same-credential', 'foreign-account', 'foreign-session', 'scope', 'disabled', 'missing']) {
    const m = { value: { id: 42 }, actor: {} }, credentials = [7, 8].map(id => ({ value: { endpointId: id, clientId: 'client-' + id, credentialId: id + 10 }, resource: { phase: 'created', outcome: 'accepted' } }));
    for (const [type, field] of [['same-endpoint', 'endpointId'], ['same-client', 'clientId'], ['same-credential', 'credentialId']]) if (mode === type) credentials[1].value[field] = credentials[0].value[field];
    const h = { admin: {}, check(label, valid) { assert.ok(valid, label); }, async ok(actor, method, route) {
      assert.equal(method, 'GET');
      if (route === '/api/v1/web/session/') return { value: { account: { id: mode === 'foreign-session' ? 43 : 42 }, homeNamespace: 'panel' } };
      return { value: { id: mode === 'missing' ? 0 : Number(route.split('/').at(-1)), account: { id: mode === 'foreign-account' ? 43 : 42 }, status: mode === 'disabled' ? 1 : 2, scope: mode === 'scope' ? 'magicrunner.usage.apps.data.write' : 'magicrunner.usage.gateway.read' } };
    } };
    if (mode === 'exact') assert.equal((await pair(h, m, credentials)).length, 2);
    else await assert.rejects(pair(h, m, credentials));
  }
});
test('machine probes require exact current-role refusal or full positive row and independent unchanged owner; inactive keys require prior CAS contraction proof', async () => {
  for (const mode of ['allow', 'deny', 'early401', 'truncated', 'changed-owner', 'lost', 'actor-drift', 'inactive-unproved', 'inactive-proved', 'endpoint-reactivated']) {
    let publicReads = 0, ownerReads = 0;
    const originalRow = { id: '42', version: '1', code: 'owned', name: 'original' };
    const endpoint = { id: 7, account: { id: 43 }, authorityRevision: 3, status: 1 };
    const server = http.createServer((req, res) => {
      res.setHeader('Content-Type', 'application/json');
      if (req.url.startsWith('/api/v1/web/proxy/cas/')) return res.end(JSON.stringify({ value: mode === 'endpoint-reactivated' && publicReads ? { ...endpoint, status: 2 } : endpoint }));
      if (req.url.startsWith('/api/v1/web/proxy/apps/')) {
        ownerReads++; assert.ok(req.headers['x-magic-expected-installation']);
        return res.end(JSON.stringify({ value: mode === 'changed-owner' && ownerReads > 1 ? { ...originalRow, name: 'foreign' } : originalRow }));
      }
      publicReads++; assert.equal(c.resource.authorityReadProbes.at(-1).outcome, 'unknown');
      assert.equal(req.headers.authorization, 'ApiKey tool-test-key'); assert.equal(req.headers.cookie, undefined);
      if (mode === 'lost') return req.socket.destroy();
      if (mode === 'actor-drift') m.actor.identity.account = 'replacement';
      if (['deny', 'early401'].includes(mode)) {
        res.statusCode = 401; return res.end(JSON.stringify({ error: { code: mode === 'deny' ? 5 : 11, message: mode === 'deny' ? '当前角色未授予此资源权限' : 'credential invalid' } }));
      }
      if (mode.startsWith('inactive-') || mode === 'endpoint-reactivated') { res.statusCode = 401; return res.end(JSON.stringify({ error: { code: 5, message: 'API key is inactive or invalid' } })); }
      res.end(JSON.stringify({ value: mode === 'truncated' ? { id: '42' } : originalRow }));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = 'http://127.0.0.1:' + server.address().port, actor = account => ({ identity: { namespace: 'panel', account }, origin,
      context: { async cookies() { return []; }, async clearCookies() {}, async addCookies() {} } });
    const disabled = { outcome: 'confirmed', accountId: 43, origin, after: [endpoint] };
    const m = { actor: actor('subscriber'), value: { id: 43 }, resource: { ceilingContractions: [disabled] } }, c = { apiKey: 'tool-test-key', value: { endpointId: 7, credentialId: 8 }, resource: {} };
    const row = { recordId: '42', applicationKey: 'owned', entity: '/owned/record', identity: { namespace: 'panel', installationId: '9', deploymentId: 'd'.repeat(32), runtimeApplicationUuid: 'u'.repeat(32), generation: 1, executionEpoch: 1, artifactDigest: 'sha256:' + 'a'.repeat(64) } };
    const h = { admin: actor('owner'), deliveryActors: { manager: actor('manager') }, persist() {}, observe() {}, good: v => v.status === 200 && !v.data.error, check(label, valid) { assert.ok(valid, label); },
      async ok(...args) { const response = await ownerRequest(...args); assert.ok(h.good(response)); return response.data; } };
    try {
      const usesProof = ['inactive-proved', 'endpoint-reactivated'].includes(mode);
      const run = read(h, m, c, '/api/v1/gateway/services/owned/get/42', row, !['deny', 'early401', 'inactive-unproved', 'inactive-proved', 'endpoint-reactivated'].includes(mode), usesProof ? disabled : undefined);
      if (['allow', 'deny', 'inactive-proved'].includes(mode)) { await run; assert.equal(c.resource.authorityReadProbes[0].outcome, 'confirmed'); }
      else { await assert.rejects(run); assert.equal(c.resource.authorityReadProbes[0].outcome, 'unknown'); }
      assert.equal(publicReads, 1); assert.equal(c.resource.authorityReadProbes[0].actorIdentity.account, 'subscriber');
      assert.equal(JSON.stringify(c.resource).includes('tool-test-key'), false);
    } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  }
});
test('account contraction needs exact acknowledged impacted set, independent disabled Endpoints and advanced original authority fences', async () => {
  for (const mode of ['exact', 'missing-impact', 'foreign-impact', 'enabled', 'same-revision', 'replaced-template', 'unknown-command']) {
    const credentials = [7, 8].map(id => ({ value: { endpointId: id, clientId: 'client-' + id, credentialId: id + 10 }, resource: { phase: 'created', outcome: 'accepted' } }));
    const before = credentials.map(c => ({ id: c.value.endpointId, account: { id: 43 }, status: 2, scope: 'magicrunner.usage.gateway.read', authorityRevision: 2, templateRefs: [{ key: 'owned-read' }], effectiveRoles: [{ module: '/applications/owned', key: 'application-data-read' }] }));
    const command = { outcome: mode === 'unknown-command' ? 'unknown' : 'confirmed', body: { applicationScopes: [{ applicationAccess: [] }] }, response: { data: { value: { affectedEndpoints: mode === 'missing-impact' ? [] : [{ id: 7 }, { id: mode === 'foreign-impact' ? 99 : 8 }] } } } };
    const member = { value: { id: 43 }, actor: { origin: 'https://panel.test' }, resource: { authorityCommands: [command] } };
    const h = { admin: {}, persist() {}, check(label, valid) { assert.ok(valid, label); }, async ok(_, method, route) {
      assert.equal(method, 'GET');
      if (route === '/api/v1/web/session/') return { value: { account: { id: 43 }, homeNamespace: 'panel' } };
      const original = before.find(e => e.id === Number(route.split('/').at(-1)));
      return { value: { ...original, status: mode === 'enabled' ? 2 : 1, authorityRevision: mode === 'same-revision' ? 2 : 3, templateRefs: mode === 'replaced-template' ? [] : original.templateRefs } };
    } };
    if (mode === 'exact') { const proof = await contraction(h, member, credentials, before); assert.equal(proof.outcome, 'confirmed'); assert.equal(member.resource.ceilingContractions.length, 1); }
    else { await assert.rejects(contraction(h, member, credentials, before)); assert.equal(member.resource.ceilingContractions, undefined); }
  }
});
test('open original Endpoint scenario retains only its own subscriber, definition and installation dependencies', async () => {
  const owner = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.test' };
  const account = { kind: 'account', id: 42, phase: 'created', collection: '/cas/namespaces/panel/accounts/', creation: { intended: { account: 'subscriber' } }, endpointScenarioAccountId: 42 };
  const graph = { kind: 'generated-service-graph', serviceId: 3, phase: 'created', commands: [], origin: owner.origin, actorIdentity: owner.identity, endpointScenarioAccountId: 42, scenarioDefinitionId: 7, scenarioInstallationIds: ['8', '9'] };
  const child = { kind: 'service-graph-credential', phase: 'intent', serviceId: 3 };
  const h = { admin: owner, Blocked: Error, state: { resources: [account, graph, child] } };
  assert.throws(() => guardFixtureAccountCleanup(h, account), /retain actual subject/);
  for (const r of [{ kind: 'definition', id: 7 }, { kind: 'member-access-retirement', installation: { id: 8 } }, { kind: 'deployment-review-request', installation: { id: 9 } }]) assert.throws(() => guard(h, r), /Endpoint scenario graph/);
  guard(h, { kind: 'definition', id: 99 });
  await assert.rejects(generated.cleanup(h, graph), /retain its service graph/);
  graph.phase = 'deleted'; child.phase = 'deleted';
  guardFixtureAccountCleanup(h, account); guard(h, { kind: 'definition', id: 7 });
  const subscription = { kind: 'service-graph-subscription', phase: 'intent', actorIdentity: { account: 'subscriber', namespace: 'panel' } };
  h.state.resources.push(subscription);
  assert.throws(() => guardFixtureAccountCleanup(h, account), /retain actual subject/);
  subscription.actorIdentity.namespace = 'foreign'; guardFixtureAccountCleanup(h, account);
});
test('unknown Endpoint replacement preserves both proposed and original templates until credential owner disposition', () => {
  const child = { kind: 'service-graph-credential', phase: 'created', endpointAuthorityCommands: [{ outcome: 'unknown', body: { roleTemplateKeys: ['proposed'] }, before: { templateRefs: [{ key: 'original' }] } }] };
  const h = { Blocked: Error, state: { resources: [child] } };
  for (const key of ['original', 'proposed']) assert.throws(() => guard(h, { kind: 'role-template', creation: { intended: { key } } }), /retain exact template/);
  guard(h, { kind: 'role-template', creation: { intended: { key: 'unrelated' } } });
  child.phase = 'deleted'; guard(h, { kind: 'role-template', creation: { intended: { key: 'original' } } });
});
