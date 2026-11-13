const { test } = require('node:test');
const assert = require('node:assert/strict');
const { applicationTarget, sameTarget, projection } = require('./portal_overview_cases.cjs');
test('original application navigation uses preview or real view-all and rejects ambiguous or absent identities', async () => {
  const { openApplication } = require('./portal_overview_cases.cjs');
  for (const mode of ['preview', 'full-list', 'duplicate-preview', 'missing-owner', 'small-preview-missing', 'duplicate-card', 'missing-card']) {
    const events = [], entry = { id: 'original', showName: 'Original instance' };
    const rows = { applications: [entry, ...Array.from({ length: mode === 'small-preview-missing' ? 1 : 5 }, (_, i) => ({ id: 'peer-' + i }))] };
    if (mode === 'missing-owner') rows.applications.shift();
    const page = { locator(selector) { return { filter() { return selector === '.magic-resource-card' ? resource : panel; }, getByText() { return {}; } }; },
      getByText(name, options) { assert.equal(name, entry.showName); assert.equal(options.exact, true); return {}; },
      async waitForURL(predicate) { assert.equal(predicate(new URL('https://panel.test/portal/applications/')), true); assert.equal(predicate(new URL('https://foreign.test/portal/applications/')), false); events.push('list-route'); },
      async waitForFunction() { events.push('list-loaded'); }, goto() { throw Error('Direct navigation forbidden'); } };
    const preview = { async count() { return mode === 'preview' ? 1 : mode === 'duplicate-preview' ? 2 : 0; }, async click() { events.push('original-preview'); } };
    const panel = { getByRole(role, options) {
      assert.equal(role, 'button');
      if (options) { assert.equal(options.exact, true); assert.equal(options.name, entry.showName); return preview; }
      return { filter({ hasText }) {
        assert.ok(hasText.test('查看全部 (6)'));
        for (const invalid of ['查看全部 (5)', '查看全部 (60)', '其他查看全部 (6)', '查看全部 (6) 其他']) assert.equal(hasText.test(invalid), false);
        return { async count() { return 1; }, async click() { events.push('view-all'); } };
      } };
    } };
    const resource = { async waitFor(options) { assert.deepEqual(options, { state: 'visible' }); events.push('original-card-visible'); }, async count() { return mode === 'duplicate-card' ? 2 : mode === 'missing-card' ? 0 : 1; }, getByRole(role, options) {
      assert.equal(role, 'button'); assert.deepEqual(options, { name: '进入应用', exact: true }); return { async click() { events.push('original-full-list'); } };
    } };
    const h = { check(label, condition) { assert.ok(condition, label); } }, actor = { origin: 'https://panel.test', page };
    if (['preview', 'full-list'].includes(mode)) {
      await openApplication(h, actor, entry, rows);
      assert.deepEqual(events, mode === 'preview' ? ['original-preview'] : ['view-all', 'list-route', 'list-loaded', 'original-card-visible', 'original-full-list']);
    } else { await assert.rejects(openApplication(h, actor, entry, rows)); assert.equal(events.some(event => ['original-preview', 'original-full-list'].includes(event)), false); }
  }
});
test('overview navigation never silently resolves a relative destination', () => {
  const actor = { origin: 'https://panel.example.test' };
  const entry = { entryEnabled: true, entryMode: 'workbench', key: 'model', deploymentId: 'a'.repeat(32) };
  const target = applicationTarget(actor, entry);
  assert.throws(() => sameTarget('/wrong', target.href), /Invalid URL/);
});
test('exact overview target compares all current installation query material', () => {
  const target = applicationTarget({ origin: 'https://panel.example.test' }, { entryEnabled: true, entryMode: 'workbench', key: 'model', deploymentId: 'a'.repeat(32) });
  assert.equal(sameTarget(target, target), true);
  assert.equal(sameTarget(target.href.replace('panel.', 'other.'), target), false);
  assert.equal(sameTarget(target.href.replace('a'.repeat(32), 'b'.repeat(32)), target), false);
  assert.equal(sameTarget(target.href + '&other=1', target), false);
  assert.equal(sameTarget(target.href + '#stale', target), false);
  for (const changes of [{ entryEnabled: false }, { entryMode: 'ingress' }, { deploymentId: '../another' }]) assert.throws(() => applicationTarget({ origin: 'https://panel.example.test' }, { entryEnabled: true, entryMode: 'workbench', key: 'model', deploymentId: 'a'.repeat(32), ...changes }), /Exact enabled/);
});
test('overview projection never treats a wrong session or duplicate directory as complete', async () => {
  const actor = { identity: { account: 'ordinary', namespace: 'tenant' } };
  for (const mode of ['wrong-account', 'wrong-tenant', 'duplicate', 'missing-id', 'read-error', 'good']) {
    let reads = 0;
    const h = { check(label, condition) { assert.ok(condition, label); }, observe() {},
      async ok() { return { value: { account: { account: mode === 'wrong-account' ? 'admin' : 'ordinary' }, homeNamespace: 'tenant', activeNamespace: mode === 'wrong-tenant' ? 'other' : 'tenant' } }; },
      async directory() { reads++; if (mode === 'read-error') throw Error('owner unavailable'); return mode === 'duplicate' ? [{ id: '1', sourceID: '1' }, { id: '1', sourceID: '1' }] : mode === 'missing-id' ? [{}] : [{ id: '1', sourceID: '1' }]; } };
    if (mode === 'good') { assert.equal(Object.keys(await projection(h, actor)).length, 4); assert.equal(reads, 4); }
    else { await assert.rejects(projection(h, actor), mode === 'read-error' ? /owner unavailable/ : /Original ordinary|unique owner|application identity/); if (mode.startsWith('wrong')) assert.equal(reads, 0); }
  }
});

test('overview requests notification owner page budget and exact Portal deployment/source IDs without relaxing other directories', async () => {
  const { readDirectory } = require('./directory.cjs');
  const actor = { origin: 'https://tenant.example.invalid', identity: { account: 'ordinary', namespace: 'tenant' } };
  const calls = [];
  const h = { Blocked: Error, check(label, condition) { assert.ok(condition, label); }, observe() {},
    async ok(_, method, route) {
      assert.equal(method, 'GET');
      if (route === '/api/v1/web/session/') return { value: { account: { account: 'ordinary' }, homeNamespace: 'tenant', activeNamespace: 'tenant' } };
      const url = new URL(route, actor.origin), pageSize = Number(url.searchParams.get('_pageSize')), pageNum = Number(url.searchParams.get('_pageNum'));
      calls.push({ route: url.pathname, pageSize, pageNum });
      if (url.pathname === '/portal/notifications/') return { pagination: { total: 51, pageSize: Math.min(pageSize, 50), pageNum }, values: Array.from({ length: pageNum === 1 ? 50 : 1 }, (_, i) => ({ id: (pageNum - 1) * 50 + i + 1 })) };
      return { pagination: { total: url.pathname === '/portal/applications/' ? 2 : 1, pageSize, pageNum }, values: url.pathname === '/portal/applications/' ? [{ id: 'a'.repeat(32), deploymentId: 'a'.repeat(32), sourceID: '9007199254740993' }, { id: '9007199254740995', sourceID: '9007199254740995' }] : [{ id: 1 }] };
    },
    directory(principal, route, options) { return readDirectory(this, principal, route, options); } };
  const result = await projection(h, actor);
  assert.equal(result.notifications.length, 51);
  assert.equal(calls.find(c => c.route === '/portal/services/').pageSize, 20);
  assert.equal(result.applications[0].id, 'a'.repeat(32));
  assert.deepEqual(calls.filter(c => c.route === '/portal/notifications/').map(c => [c.pageSize, c.pageNum]), [[50, 1], [50, 2]]);
});

test('overview refuses mismatched deployment and runtime source identities', async () => {
  for (const entry of [{ id: '1', sourceID: '1', deploymentId: 'a'.repeat(32) }, { id: 'a'.repeat(32), sourceID: '1', deploymentId: 'b'.repeat(32) }, { id: '2', sourceID: '1' }, { id: '1', sourceID: '01' }]) {
    const h = { check(label, condition) { assert.ok(condition, label); }, observe() {},
      async ok() { return { value: { account: { account: 'ordinary' }, homeNamespace: 'tenant', activeNamespace: 'tenant' } }; },
      async directory(_, route) { return route === '/portal/applications/' ? [entry] : []; } };
    await assert.rejects(projection(h, { identity: { account: 'ordinary', namespace: 'tenant' } }), /application identity/);
  }
});
