// Exercise the fault window with real Chromium routing and an isolated HTTP
// owner. These are tool checks, never product Live acceptance.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('./playwright.cjs');
const { handlers } = require('./authoring_cases.cjs');

test('lost-response handler confirms one actual commit, rejects false owner evidence, and preserves unresolved intent', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const mode of ['commit', 'false-receipt']) {
      let puts = 0, persisted = 0;
      let current = { applicationId: 1, applicationUuid: 'test', definitionVersion: 10, targetDigest: 'original', entities: [], pages: {} };
      const server = http.createServer(async (req, res) => {
        if (req.url === '/') { res.end('<html><body>isolated tool fixture</body></html>'); return; }
        const chunks = []; for await (const chunk of req) chunks.push(chunk);
        let body = {}; if (chunks.length) body = JSON.parse(Buffer.concat(chunks));
        let status = 200, data;
        if (req.method === 'GET') data = { error: null, value: current };
        else {
          assert.equal(req.method, 'PUT'); puts++;
          if (body.expectedDefinitionVersion !== current.definitionVersion) {
            status = 409; data = { error: { code: 19, message: 'owner version conflict' } };
          } else {
            persisted++;
            const next = { ...current, definitionVersion: current.definitionVersion + 1,
              targetDigest: 'target-' + persisted,
              entities: body.entities.map(e => ({ ...e, id: e.id || 7, updateTime: current.definitionVersion + 1 })) };
            data = { error: null, value: next };
            // The third PUT is the intentionally lost response. A fabricated
            // acknowledgement must never replace the independent original read.
            if (mode === 'commit' || puts < 3) current = next;
          }
        }
        res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data));
      });
      await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
      const context = await browser.newContext(), page = await context.newPage();
      try {
        const origin = 'http://127.0.0.1:' + server.address().port;
        await page.goto(origin);
        let writes = 0;
        const h = { fs, path, root: path.resolve(__dirname, '..'), admin: { page, origin }, Blocked: Error,
          state: { prefix: 'unit', resources: [] }, persist() { writes++; },
          check(label, condition) { assert.ok(condition, label); },
          good: r => r.status === 200 && r.data.error == null,
          async create(collection, body) { const app = { ...body, id: 1, uuid: 'test' }; h.state.resources.push({ collection, id: 1, creation: { intended: body } }); return app; },
          async api(actor, method, route, body) {
            assert.equal(actor, h.admin);
            return page.evaluate(async ({ method, route, body }) => {
              const response = await fetch('/api/v1/web/proxy' + route, { method,
                ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
              return { status: response.status, data: await response.json() };
            }, { method, route, body });
          },
          async ok(actor, method, route, body) { const r = await h.api(actor, method, route, body); assert.ok(h.good(r)); return r.data; },
        };
        if (mode === 'commit') await handlers['F018-002'](h);
        else await assert.rejects(handlers['F018-002'](h), /Independent original-identity read/);
        assert.equal(puts, 3, 'two conflict contenders plus exactly one lost-response write; no replay');
        assert.equal(current.entities.length, 1);
        const intent = h.state.resources[0].pendingAuthoringSave;
        assert.ok(intent.journalId && writes > 0);
        assert.equal(intent.payload.entities[0].id, 7);
        assert.equal(intent.confirmed, mode === 'commit');
        assert.equal(intent.response.data.value.entities[0].showName, '提交后丢失响应');
      } finally { await context.close(); await new Promise(resolve => server.close(resolve)); }
    }
  } finally { await browser.close(); }
});
