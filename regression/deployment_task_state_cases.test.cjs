// Explicitly browser-free: local HTTP and locator substitutes test tool safety,
// not the product UI or an actual deployment.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const task = require('./deployment_task_state_cases.cjs');
const review = require('./deployment_review_cases.cjs');
const native = require('./native_runtime_cases.cjs');
const scenario = require('./scenario_commands.cjs');
const { ownerRequest } = require('./owner_transport.cjs');
const operations = '/panel/operations/namespaces/panel/application-deployment-operations/';
const requests = '/panel/application/deployment-requests/';
const installations = '/panel/application/installations/';
function facts(status = 'succeeded') {
  const request = { id: 7, operationId: 8, namespace: 'panel', packageId: 9, instanceKey: 'original', instanceName: 'Original',
    deploymentId: 'deployment', sourceKind: 'deployment-package', planDigest: 'sha256:plan', status, version: 3 };
  const operation = { ...request, id: 8, requestId: 7, version: 5, phase: status === 'failed' ? 'execution' : status === 'cancelled' ? 'terminated' : 'completed',
    attempt: 1, maxAttempts: 3, startTime: 100, failureMessage: status === 'failed' ? 'original exit 23' : '',
    receiptRef: status === 'succeeded' ? 'installation:11' : '', executionResumeMode: 'forward' };
  const r = { kind: 'deployment-review-request', id: 7, phase: 'created', last: structuredClone(request), operation: structuredClone(operation), commands: [],
    creation: { ownershipConfirmed: true, outcome: 'accepted', intended: { packageId: 9, instanceKey: 'original' } } };
  const snapshot = { request, operation, requestDirectory: [request], operationDirectory: [operation, { id: 18, status: 'failed', attempt: 1 }],
    installations: [{ id: 11, deploymentId: 'deployment', status: 'ready' }] };
  return { request, operation, r, snapshot };
}
test('binding rejects foreign original request, plan, namespace, state or durable version', () => {
  const f = facts(); assert.equal(task.bound(f.r, f.request, f.operation), true);
  for (const alter of [v => v.id++, v => v.operationId++, v => v.packageId++, v => v.instanceKey = 'foreign',
    v => v.planDigest = 'other', v => v.namespace = 'other', v => v.sourceKind = 'model-package', v => v.status = 'failed']) {
    const value = structuredClone(f.request); alter(value); assert.equal(task.bound(f.r, value, f.operation), false);
  }
  for (const alter of [v => v.id++, v => v.requestId++, v => v.version++, v => v.version = 0, v => v.version = '5',
    v => v.attempt++, v => v.receiptRef = 'installation:12', v => v.planDigest = 'other', v => v.namespace = 'other']) {
    const value = structuredClone(f.operation); alter(value); assert.equal(task.bound(f.r, f.request, value), false);
  }
  assert.equal(task.bound(f.r, f.request, undefined), false);
});
test('unchanged proof permits only succeeded diagnostic clock drift, preserving every directory and receipt', () => {
  const { snapshot: before } = facts(), after = structuredClone(before);
  after.operation.executionResumeMode = 'cleanup-required'; after.operationDirectory[0].executionResumeMode = 'confirm-only';
  assert.equal(task.unchanged(before, after), true);
  for (const alter of [v => v.request.version++, v => v.operation.version++, v => v.operation.attempt++, v => v.operation.maxAttempts++,
    v => v.operation.leaseUntil = 3, v => v.operation.status = 'failed', v => v.operation.receiptRef = '',
    v => v.installations[0].status = 'disabled', v => v.requestDirectory.push({ id: 70 }),
    v => v.operationDirectory.pop(), v => v.operationDirectory[1].attempt++, v => v.operationDirectory[0].planDigest = 'other']) {
    const value = structuredClone(after); alter(value); assert.equal(task.unchanged(before, value), false);
  }
  const failed = facts('failed').snapshot, changed = structuredClone(failed); changed.operation.executionResumeMode = 'cleanup-required';
  assert.equal(task.unchanged(failed, changed), false);
});
test('negative action selection never sends an actually permitted retry, termination or queued cancellation', () => {
  const failed = facts('failed').operation, success = facts().operation, cancelled = facts('cancelled').operation;
  assert.equal(task.refusal(failed, 'retry', true).code, 19);
  for (const action of ['retry', 'cancel', 'cleanup']) assert.equal(task.refusal(success, action).code, 21);
  for (const action of ['retry', 'cancel']) assert.equal(task.refusal(cancelled, action).code, 21);
  for (const [op, action, stale] of [[failed, 'retry'], [failed, 'cancel'], [{ ...failed, version: 1 }, 'retry', true],
    [{ ...failed, version: '5' }, 'retry', true], [success, 'retry', true], [cancelled, 'cleanup'],
    [{ ...success, status: 'queued' }, 'cancel'], [success, 'delete']]) assert.throws(() => task.refusal(op, action, stale));
});
async function fixture(mode, run, status = 'succeeded') {
  const f = facts(status); let writes = 0, actor, persisted = false;
  const server = http.createServer(async (req, res) => {
    const parts = []; for await (const chunk of req) parts.push(chunk);
    res.setHeader('Content-Type', 'application/json');
    if (req.method === 'GET') {
      const value = structuredClone(f.snapshot);
      if (writes && mode === 'target-changed') { value.operation.attempt++; value.operationDirectory[0].attempt++; }
      if (writes && mode === 'peer-changed') value.operationDirectory[1].attempt++;
      if (writes && mode === 'installation-changed') value.installations[0].status = 'disabled';
      if (writes && mode === 'new-request') value.requestDirectory.push({ id: 70 });
      if (mode === 'missing') value.operationDirectory.shift();
      if (mode === 'duplicate') value.requestDirectory.push(value.request);
      const url = new URL(req.url, actor.origin);
      const route = url.pathname.replace(/^\/api\/v1\/web\/proxy/, '');
      const result = route === requests ? { values: value.requestDirectory } : route === operations ? { values: value.operationDirectory } :
        route === installations ? { values: value.installations } : { value: route === requests + '7' ? value.request : value.operation };
      return res.end(JSON.stringify(result));
    }
    writes++; assert.equal(writes, 1); assert.ok(persisted);
    const c = f.r.scenarioCommands.at(-1), body = JSON.parse(Buffer.concat(parts));
    assert.equal(c.outcome, 'unknown'); assert.deepEqual(body, c.body); assert.equal(c.origin, actor.origin);
    assert.deepEqual(c.actorIdentity, { namespace: 'panel', account: 'original' });
    assert.equal(req.url, '/api/v1/web/proxy' + c.route); assert.equal(req.method, 'POST'); assert.equal(body.expectedVersion, status === 'failed' && req.url.endsWith('/retry') ? 4 : 5);
    if (mode === 'lost') return req.socket.destroy();
    if (mode === 'actor') actor.identity.account = 'replacement';
    if (mode === 'origin') actor.origin = 'http://other.test';
    const error = structuredClone(c.expected);
    if (mode === 'wrong-code') error.code = 19;
    if (mode === 'wrong-message') error.message = 'unrelated fence';
    res.statusCode = mode === 'auth' ? 401 : mode === 'unavailable' ? 503 : 409;
    res.end(JSON.stringify({ error, value: mode === 'value' ? { id: 8 } : null }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  actor = { origin, identity: { namespace: 'panel', account: 'original' }, context: { async cookies() { return []; }, async addCookies() {}, async clearCookies() {} } };
  Object.assign(f.r.creation, { origin, actorIdentity: structuredClone(actor.identity) });
  const h = { admin: actor, state: { resources: [f.r] }, Blocked: Error,
    persist() { if (f.r.scenarioCommands?.length) persisted = true; }, check(label, condition) { assert.ok(condition, label); },
    good: response => response.status === 200 && !response.data.error,
    api: (a, ...args) => ownerRequest(a, ...args),
    async ok(a, ...args) { const response = await this.api(a, ...args); assert.equal(response.status, 200); return response.data; },
    async directory(a, route) { return (await this.ok(a, 'GET', route)).values; } };
  try { await run(h, f.r, () => writes); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
test('actual HTTP exact state/version refusals persist original intent before single dispatch and independent proof', async () => {
  for (const [status, action, stale] of [['succeeded', 'retry'], ['succeeded', 'cancel'], ['succeeded', 'cleanup'],
    ['failed', 'cleanup'], ['failed', 'retry', true], ['cancelled', 'retry'], ['cancelled', 'cancel']]) {
    await fixture('refused', async (h, r, count) => {
      await task.rejectAction(h, r, action, stale); assert.equal(count(), 1);
      assert.equal(r.scenarioCommands[0].outcome, 'rejected-and-unchanged'); scenario.guard(h, r);
    }, status);
  }
});
test('HTTP loss, foreign identity, wrong stage, successful value and concurrent owner changes remain unknown without replay or teardown', async () => {
  for (const mode of ['lost', 'actor', 'origin', 'auth', 'unavailable', 'wrong-code', 'wrong-message', 'value',
    'target-changed', 'peer-changed', 'installation-changed', 'new-request']) {
    await fixture(mode, async (h, r, count) => {
      await assert.rejects(task.rejectAction(h, r, 'retry'));
      assert.equal(r.scenarioCommands[0].outcome, 'unknown', mode); assert.equal(count(), 1);
      assert.throws(() => scenario.guard(h, r), /unresolved/);
      await assert.rejects(task.rejectAction(h, r, 'retry'), /unresolved/);
      await assert.rejects(review.cleanup(h, r), /unresolved/); assert.equal(count(), 1);
    });
  }
});
test('incomplete or duplicate full owner directories stop before any action dispatch', async () => {
  for (const mode of ['missing', 'duplicate']) await fixture(mode, async (h, r, count) => {
    await assert.rejects(task.rejectAction(h, r, 'retry'), /Complete directories/);
    assert.equal(count(), 0); assert.equal(r.scenarioCommands, undefined);
  });
});
test('unexpected UI command is journalled before forwarding and remains unresolved even if the page fails', async () => {
  await fixture('refused', async (h, r, count) => {
    let interceptor, forwarded = false, removed = false;
    h.admin.page = {
      async route(pattern, handler) { assert.equal(pattern, '**/api/v1/web/proxy/panel/operations/**'); interceptor = handler; },
      async unroute(_pattern, handler) { assert.equal(handler, interceptor); removed = true; },
      async setViewportSize() {},
      async goto() {
        await interceptor({ request: () => ({ method: () => 'POST', url: () => h.admin.origin + '/api/v1/web/proxy' + operations + '8/retry',
          postData: () => '{"expectedVersion":5,"reason":"unexpected"}' }),
        async continue() { assert.equal(r.scenarioCommands[0].outcome, 'unknown'); assert.equal(r.scenarioCommands[0].operationId, 8); forwarded = true; } });
        throw Error('page failed after unexpected dispatch');
      }
    };
    await assert.rejects(task.visible(h, r), /page failed/);
    assert.ok(forwarded && removed); assert.equal(count(), 0); // No actual platform command in this tool substitute.
    assert.equal(r.scenarioCommands[0].source, 'unexpected-task-ui-command');
    assert.throws(() => scenario.guard(h, r), /unresolved/);
    await assert.rejects(review.cleanup(h, r), /unresolved/);
  });
});
test('unknown native task action protects terminated task and exact source, including generic cleanup', async () => {
  const f = facts('cancelled'), r = f.r; r.kind = 'native-runtime-request'; r.phase = 'deleted'; r.scenarioCommands = [{ outcome: 'unknown' }];
  const h = { admin: {}, Blocked: Error, state: { resources: [r] }, ok() { throw Error('unexpected read'); }, api() { throw Error('unexpected write'); } };
  assert.throws(() => native.original(h, r), /unresolved/); await assert.rejects(native.cleanup(h, r), /unresolved/);
  for (const kind of ['native-package-probe', 'native-provider-probe']) {
    assert.throws(() => scenario.guard(h, { kind, package: { id: 9 } }), /source package/);
    assert.doesNotThrow(() => scenario.guard(h, { kind, package: { id: 10 } }));
    assert.doesNotThrow(() => scenario.guard(h, { kind }));
  }
  r.scenarioCommands[0].outcome = 'rejected-and-unchanged';
  assert.doesNotThrow(() => scenario.guard(h, { kind: 'native-package-probe', package: { id: 9 } }));
});
test('state presentation checks exact supported actions, original counter and failure, without claiming real UI acceptance', async () => {
  for (const status of ['succeeded', 'failed', 'cancelled']) {
    const { r } = facts(status), buttons = task.expectedButtons(r.operation);
    assert.deepEqual(buttons, status === 'succeeded' ? [] : status === 'failed' ? ['重试', '终止并清理'] : ['清理记录']);
    const h = { check(label, condition) { assert.ok(condition, label); } };
    let mismatch = false;
    const row = { locator(selector) {
      if (selector === 'button') return { allTextContents: async () => mismatch ? [...buttons, 'unexpected'] : buttons };
      assert.equal(selector, '.ant-tag');
      return { filter({ hasText }) {
        const label = { succeeded: '已完成', failed: '失败', cancelled: '已取消' }[status];
        assert.ok(hasText.test(label)); assert.equal(hasText.test('其他'+label), false);
        return { async waitFor() {} };
      } };
    },
      getByText(text) { assert.equal(text, r.operation.failureMessage, 'status must not use a broad phase/status text selector'); return { async waitFor() {} }; },
      async innerText() { return '8 Original 1/3'; } };
    await task.controls(h, r, row); mismatch = true; await assert.rejects(task.controls(h, r, row));
  }
  for (const status of ['queued', 'running']) assert.throws(() => task.expectedButtons(facts(status).operation), /Unobserved/);
});
test('post-refresh task lookup starts from page one and finds exact row without replacing navigation', async () => {
  for (const initialPage of [1, 5]) {
    let page = initialPage, clicks = 0;
    const row = { count: async () => page === 3 ? 1 : 0, async waitFor() { assert.equal(page, 3); } };
    const card = { locator(selector) {
      if (selector.startsWith('tr[')) { assert.equal(selector, 'tr[data-row-key="8"]'); return row; }
      if (selector.startsWith('.ant-spin')) return { first() { return { async waitFor() {} }; } };
      const first = selector.startsWith('.ant-pagination-item-1');
      return { count: async () => first ? Number(page !== 1) : Number(page < 5), async click() { page = first ? 1 : page + 1; clicks++; } };
    } };
    assert.equal(await task.findTaskRow({}, facts().r, card), row); assert.equal(clicks, initialPage === 1 ? 2 : 3);
  }
});
