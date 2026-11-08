// Transport/journal checks use an isolated HTTP owner, never deployed acceptance.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('playwright');
const { observeLostPageSave } = require('./page_author_cases.cjs');
test('page response loss requires original owner content and never replays a PUT', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const mode of ['commit', 'false-receipt', 'before-ack-loss']) {
      const app = { id: 1 }, body = { expectedDefinitionVersion: 10, content: { pages: [{ key: 'original', routes: ['/one'], binding: 'original-binding' }] } };
      let current = { applicationId: 1, definitionVersion: 10, content: {} }, puts = 0, persisted;
      const resource = { collection: '/panel/application/definitions/', id: 1, creation: { ownershipConfirmed: true } };
      const h = { Blocked: Error, state: { resources: [resource] }, persist() { persisted = structuredClone(resource.pendingAuthoringSave); }, good: r => r.status === 200 && r.data.error == null, check(label, condition) { assert.ok(condition, label); } };
      const server = http.createServer(async (req, res) => {
        if (req.url === '/') { res.end('<html><body>page transport fixture</body></html>'); return; }
        res.setHeader('Content-Type', 'application/json');
        if (req.method === 'GET') { res.end(JSON.stringify(current)); return; }
        assert.equal(req.method, 'PUT'); puts++;
        assert.equal(persisted.confirmed, false); assert.deepEqual(persisted.payload, body);
        const chunks = []; for await (const c of req) chunks.push(c);
        assert.deepEqual(JSON.parse(Buffer.concat(chunks)), body);
        if (mode === 'before-ack-loss') { req.socket.destroy(); return; }
        const next = { applicationId: 1, definitionVersion: 11, content: body.content };
        if (mode === 'commit') current = next;
        res.end(JSON.stringify({ error: null, value: next }));
      });
      await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
      const context = await browser.newContext(), page = await context.newPage(), origin = 'http://127.0.0.1:' + server.address().port;
      h.admin = { page, origin };
      try {
        await page.goto(origin);
        let responseLost = false;
        const trigger = () => page.evaluate(async body => {
          try { await fetch('/api/v1/web/proxy/panel/application/definitions/1/pages', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return false; } catch { return true; }
        }, body).then(lost => { responseLost = lost; });
        const confirm = async intent => {
          const value = await page.evaluate(() => fetch('/api/v1/web/proxy/panel/application/definitions/1/pages').then(r => r.json()));
          assert.deepEqual(value, intent.response.data.value, 'original owner independent content');
        };
        const result = observeLostPageSave(h, app, trigger, confirm);
        if (mode === 'commit') await result; else await assert.rejects(result);
        assert.equal(responseLost, true); assert.equal(puts, 1); assert.equal(persisted.confirmed, mode === 'commit');
        assert.deepEqual(persisted.payload, body);
        if (mode === 'before-ack-loss') assert.equal(resource.pendingAuthoringSave.response, undefined);
      } finally { await context.close(); await new Promise(resolve => server.close(resolve)); }
    }
  } finally { await browser.close(); }
});

test('rejected definition recovery requires exact pre-admission rejection and complete original owner absence', async () => {
  const { reconcileRejectedDefinitionCreations } = require('./page_author_cases.cjs');
  for (const mode of ['confirmed', 'missing-response', 'wrong-error', 'unexpected-id', 'foreign-actor', 'still-present', 'incomplete-directory']) {
    const actor = { origin: 'https://panel.example.invalid', identity: { account: 'original', namespace: 'panel' } };
    const r = { kind: 'definition', phase: 'intent', collection: '/panel/application/definitions/', creation: { journalId: 'original', outcome: 'unconfirmed', origin: actor.origin, actorIdentity: structuredClone(actor.identity), intended: { name: 'original-name', uuid: 'original-uuid', pkgPrefix: 'invalid-prefix' }, identity: { uuid: 'original-uuid' }, response: { status: 200, data: { error: { code: 4, message: 'model application package prefix is invalid' }, value: null } } } };
    if (mode === 'missing-response') delete r.creation.response;
    if (mode === 'wrong-error') r.creation.response.data.error.message = 'unknown failure';
    if (mode === 'unexpected-id') r.id = 7;
    if (mode === 'foreign-actor') actor.identity.namespace = 'other';
    let reads = 0;
    const h = { admin: actor, state: { resources: [r] }, Blocked: Error, persist() {}, check(label, condition) { assert.ok(condition, label); },
      async directory(a, route) { assert.equal(a, actor); assert.equal(route, r.collection); reads++; if (mode === 'incomplete-directory') throw Error('incomplete'); return mode === 'still-present' ? [{ id: 7, name: 'original-name', uuid: 'original-uuid' }] : []; } };
    if (mode === 'confirmed') { const proof = await reconcileRejectedDefinitionCreations(h); assert.equal(proof[0].noCommandReplayed, true); assert.equal(r.phase, 'deleted'); }
    else { await assert.rejects(reconcileRejectedDefinitionCreations(h)); assert.equal(r.phase, 'intent'); }
    if (['missing-response', 'wrong-error', 'unexpected-id', 'foreign-actor'].includes(mode)) assert.equal(reads, 0);
  }
});

test('accepted author-write recovery rejects absent receipts, changed identity and different owner content', async () => {
  const { reconcileAcknowledgedAuthorWrites } = require('./page_author_cases.cjs');
  for (const mode of ['confirmed', 'unknown-response', 'wrong-parent', 'foreign-actor', 'different-content', 'later-version']) {
    const actor = { origin: 'https://panel.example.invalid', identity: { account: 'author', namespace: 'panel' } }, app = { id: 7, uuid: 'original', name: 'original-app' }, content = { pages: [{ key: 'home', title: 'committed' }] };
    const r = { kind: 'definition', phase: 'created', collection: '/panel/application/definitions/', id: 7, creation: { actorIdentity: structuredClone(actor.identity), origin: actor.origin, ownershipConfirmed: true, response: { data: { value: app } } }, pendingAuthoringSave: { journalId: 'original-command', method: 'PUT', route: '/panel/application/definitions/7/pages', confirmed: false, payload: { expectedDefinitionVersion: 10, content }, response: { status: 200, data: { error: null, value: { applicationId: 7, applicationUuid: 'original', applicationKey: 'original-app', definitionVersion: 11, content } } } } };
    if (mode === 'unknown-response') delete r.pendingAuthoringSave.response;
    if (mode === 'wrong-parent') r.pendingAuthoringSave.response.data.value.applicationId = 8;
    if (mode === 'foreign-actor') actor.identity.namespace = 'other';
    let reads = 0;
    const h = { admin: actor, state: { resources: [r] }, Blocked: Error, persist() {}, good: q => q.status === 200 && q.data.error == null, check(label, condition) { assert.ok(condition, label); }, async ok(a, method, route) { assert.equal(a, actor); assert.equal(method, 'GET'); reads++; return { value: route.endsWith('/pages') ? { applicationId: 7, applicationUuid: 'original', definitionVersion: mode === 'later-version' ? 12 : 11, content: mode === 'different-content' ? {} : content } : app }; } };
    if (mode === 'confirmed') { const proof = await reconcileAcknowledgedAuthorWrites(h); assert.equal(proof[0].noCommandReplayed, true); assert.equal(r.pendingAuthoringSave.confirmed, true); }
    else { await assert.rejects(reconcileAcknowledgedAuthorWrites(h)); assert.equal(r.pendingAuthoringSave.confirmed, false); }
    if (['unknown-response', 'wrong-parent', 'foreign-actor'].includes(mode)) assert.equal(reads, 0);
  }
});

test('recovery flags reject invalid values and conflicting modes before starting a browser', () => {
  const { spawnSync } = require('node:child_process');
  const path = require('node:path');
  const script = path.join(__dirname, 'standard.cjs');
  for (const flag of ['reconcile-authoring-deletions', 'reconcile-rejected-definitions', 'reconcile-authoring-writes', 'reconcile-authoring-conflicts']) {
    const invalid = spawnSync(process.execPath, [script, '--dry-run', 'true', '--' + flag, 'false'], { encoding: 'utf8' });
    assert.notEqual(invalid.status, 0); assert.match(invalid.stderr, /requires literal true/);
    const conflict = spawnSync(process.execPath, [script, '--dry-run', 'true', '--' + flag, 'true', '--reconcile-cleanup', 'original.json'], { encoding: 'utf8' });
    assert.notEqual(conflict.status, 0); assert.match(conflict.stderr, /exactly one recovery/);
  }
});
