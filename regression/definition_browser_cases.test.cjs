// These exercise command journaling with Chromium and an isolated HTTP server;
// they are tool checks and never stand in for deployed product verification.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('./playwright.cjs');
const { observeAuthorSave, reconcileAuthorDeletion } = require('./definition_browser_cases.cjs');

test('author UI records exact PUT/DELETE before dispatch and preserves unconfirmed owner outcomes', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const mode of ['update', 'delete', 'conflict', 'false-receipt']) {
      const pathname = '/panel/application/definition/entitys/7';
      const method = mode === 'delete' ? 'DELETE' : 'PUT';
      const payload = { id: 7, expectedEntityVersion: 10, showName: 'original UI input' };
      let current = { id: 7, version: 10 }, commands = 0, persisted;
      const owner = { collection: '/panel/application/definitions/', id: 1, creation: { confirmed: true } };
      const h = { state: { resources: [owner] }, Blocked: Error,
        persist() { persisted = structuredClone(owner.pendingAuthoringSave); },
        good: r => r.status === 200 && r.data.error == null,
        check(label, condition) { assert.ok(condition, label); } };
      const server = http.createServer(async (req, res) => {
        if (req.url === '/') { res.end('<html><body>isolated author tool check</body></html>'); return; }
        if (req.method === 'GET') {
          res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(current)); return;
        }
        commands++;
        assert.equal(req.url, '/api/v1/web/proxy' + pathname);
        assert.equal(req.method, method);
        assert.equal(persisted.confirmed, false, 'original intent is persisted before owner receives command');
        assert.equal(persisted.method, method);
        const chunks = []; for await (const chunk of req) chunks.push(chunk);
        const body = chunks.length ? JSON.parse(Buffer.concat(chunks)) : {};
        assert.deepEqual(persisted.payload, body);
        if (mode === 'update') current = { ...body, version: 11 };
        if (mode === 'delete') current = null;
        const data = mode === 'conflict' ? { error: { code: 19 }, value: null } : { error: null, value: { id: 7 } };
        res.writeHead(mode === 'conflict' ? 409 : 200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
      });
      await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
      const context = await browser.newContext(), page = await context.newPage();
      try {
        const origin = 'http://127.0.0.1:' + server.address().port;
        h.admin = { page, origin };
        await page.goto(origin);
        const trigger = () => page.evaluate(async ({ pathname, method, payload }) => {
          const response = await fetch('/api/v1/web/proxy' + pathname, { method,
            ...(method === 'PUT' ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {}) });
          await response.json();
        }, { pathname, method, payload });
        const confirm = async () => {
          const read = await page.evaluate(pathname => fetch('/api/v1/web/proxy' + pathname).then(r => r.json()), pathname);
          assert.deepEqual(read, mode === 'delete' ? null : mode === 'conflict' ? { id: 7, version: 10 } : { ...payload, version: 11 }, 'independent owner outcome');
        };
        const operation = observeAuthorSave(h, { id: 1 }, pathname, trigger, confirm, mode === 'conflict' ? 19 : undefined, method);
        if (mode === 'false-receipt') await assert.rejects(operation, /independent owner outcome/);
        else await operation;
        assert.equal(commands, 1, 'UI command is dispatched exactly once without retries');
        assert.equal(owner.pendingAuthoringSave.confirmed, mode !== 'false-receipt');
        assert.equal(persisted.confirmed, mode !== 'false-receipt');
        assert.equal(persisted.route, pathname);
      } finally { await context.close(); await new Promise(resolve => server.close(resolve)); }
    }
  } finally { await browser.close(); }
});

test('acknowledged entity deletion recovery uses exact original reads and rejects missing or foreign proof', async () => {
  for (const mode of ['confirmed', 'unknown-delete', 'foreign-actor', 'foreign-parent', 'still-present', 'raw-404']) {
    const actor = { identity: { account: 'author', namespace: 't1' }, origin: 'https://t1.example.invalid' };
    const entity = { id: 7, pkgPath: '/test', name: 'sample', application: { id: 1, uuid: 'original' } };
    const resource = { collection: '/panel/application/definitions/', id: 1,
      creation: { ownershipConfirmed: true, actorIdentity: structuredClone(actor.identity), origin: actor.origin,
        response: { data: { value: { id: 1, uuid: 'original' } } } },
      pendingAuthoringSave: { method: 'DELETE', route: '/panel/application/definition/entitys/7', confirmed: false,
        response: { status: 200, data: { error: null, value: entity } } } };
    if (mode === 'unknown-delete') delete resource.pendingAuthoringSave.response;
    if (mode === 'foreign-actor') actor.identity.namespace = 't2';
    if (mode === 'foreign-parent') entity.application.id = 2;
    const routes = [];
    let persisted = 0;
    const h = { admin: actor, Blocked: Error, persist() { persisted++; },
      good: r => r.status === 200 && r.data.error == null,
      check(label, condition) { assert.ok(condition, label); },
      async api(original, method, route) {
        assert.equal(original, actor); assert.equal(method, 'GET', 'recovery never repeats entity DELETE'); routes.push(route);
        if (route.endsWith('/definitions/1')) return { status: 200, data: { error: null, value: { id: 1, uuid: 'original' } } };
        if (route.endsWith('/model-draft')) return { status: 200, data: { error: null, value: { applicationId: 1, applicationUuid: 'original', definitionVersion: 12, entities: [] } } };
        if (mode === 'still-present') return { status: 200, data: { error: null, value: entity } };
        if (mode === 'raw-404') return { status: 404, data: { text: 'unknown route' } };
        return { status: 200, data: { error: { code: 2 }, value: null } };
      },
      async ok(...args) { const r = await this.api(...args); assert.ok(this.good(r)); return r.data; } };
    if (mode === 'confirmed') {
      const proof = await reconcileAuthorDeletion(h, resource);
      assert.equal(proof.entityId, 7); assert.equal(proof.applicationId, 1);
      assert.equal(persisted, 1); assert.equal(routes.length, 3);
    } else {
      await assert.rejects(reconcileAuthorDeletion(h, resource)); assert.equal(persisted, 0);
      if (['unknown-delete', 'foreign-actor', 'foreign-parent'].includes(mode)) assert.equal(routes.length, 0);
    }
    assert.equal(resource.pendingAuthoringSave.confirmed, mode === 'confirmed');
  }
});
