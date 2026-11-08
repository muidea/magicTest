// Isolated transport checks protect the journal; Live owner proof is separate.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('playwright');
const { observeNativeCreate } = require('./native_cases.cjs');

test('native UI journals one original POST and retains mismatched or unreadable owner outcomes', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const mode of ['accepted', 'wrong-identity', 'read-failure', 'transport-loss']) {
      const resources = [], payload = { name: 'original', runtimeType: 'packaged-runtime', orchestration: { contract: { components: { api: { image: 'example:1' } } } } };
      let persisted, posts = 0, reads = 0;
      const h = { state: { resources }, Blocked: Error, persist() { persisted = structuredClone(resources); },
        good: r => r.status === 200 && r.data.error == null,
        check(label, condition) { assert.ok(condition, label); } };
      const server = http.createServer(async (req, res) => {
        if (req.url === '/') { res.end('<html><body>isolated native tool test</body></html>'); return; }
        res.setHeader('Content-Type', 'application/json');
        if (req.method === 'POST') {
          posts++;
          assert.equal(persisted.length, 1); assert.equal(persisted[0].creation.outcome, 'unknown');
          assert.deepEqual(persisted[0].creation.intended, payload);
          const bytes = []; for await (const chunk of req) bytes.push(chunk);
          assert.deepEqual(JSON.parse(Buffer.concat(bytes)), payload);
          if (mode === 'transport-loss') { req.socket.destroy(); return; }
        } else { reads++; }
        res.end(JSON.stringify(mode === 'read-failure' && req.method === 'GET' ? { error: { code: 2 }, value: null } : { error: null, value: { ...payload, id: 7, ...(mode === 'wrong-identity' ? { name: 'foreign' } : {}) } }));
      });
      await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
      const context = await browser.newContext(), page = await context.newPage(), origin = 'http://127.0.0.1:' + server.address().port;
      try {
        h.admin = { origin, page, identity: { account: 'original', namespace: 'panel' } };
        h.api = async (actor, method, route) => {
          assert.equal(method, 'GET', 'adapter never emits a second POST');
          return page.evaluate(async route => { const r = await fetch('/api/v1/web/proxy' + route); return { status: r.status, data: await r.json() }; }, route);
        };
        h.ownerApi = async (...args) => {
          assert.equal(args[1], 'GET', 'shared owner transport must not replace the original intercepted UI POST');
          return h.api(...args);
        };
        h.ok = async (...args) => { const r = await h.api(...args); h.check('owner read', h.good(r)); return r.data; };
        await page.goto(origin);
        const result = observeNativeCreate(h, () => page.evaluate(async payload => {
          try { await fetch('/api/v1/web/proxy/panel/application/definitions/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); } catch {}
        }, payload));
        if (mode === 'accepted') { assert.equal((await result).id, 7); assert.equal(resources[0].creation.ownershipConfirmed, true); }
        else { await assert.rejects(result); assert.notEqual(resources[0].creation.ownershipConfirmed, true); }
        assert.equal(posts, 1); assert.equal(resources.length, 1);
        assert.deepEqual(persisted[0].creation.intended, payload);
        assert.equal(reads, ['accepted', 'read-failure'].includes(mode) ? 1 : 0);
        assert.equal(resources[0].phase, mode === 'transport-loss' ? 'intent' : 'created');
      } finally { await context.close(); await new Promise(resolve => server.close(resolve)); }
    }
  } finally { await browser.close(); }
});
