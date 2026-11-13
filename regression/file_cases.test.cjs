const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('./playwright.cjs');
const { cleanup } = require('./file_cases.cjs');
const { fileTransfer } = require('./owner_transport.cjs');
class Blocked extends Error {}
test('owner-proven deletion recovery rejects unacknowledged, wrong physical identity or tampered log before any read or write', async () => {
  const actor = { origin: 'https://a.example', identity: { account: 'admin', namespace: 'a' } };
  const r = { visibility: 'public', id: 7, token: 'original', name: 'proof.bin', path: '/static/share/original/proof.bin', actorName: 'tenantAdmin', actorIdentity: actor.identity, origin: actor.origin, creation: { outcome: 'confirmed' }, deletion: { outcome: 'acknowledged', response: { status: 200, data: { value: { id: 7, token: 'original', name: 'proof.bin', path: '/static/share/original/proof.bin' } } } } };
  const line = '2026/11/08 03:16:02 WARN failed to serve static file path=/share/original/proof.bin err="open /var/app/data/static/share/original/proof.bin: no such file or directory"';
  const proof = { kind: 'magicfile-static-missing', sourceContainer: 'magicFile', fileID: 7, namespace: 'a', originalPath: r.path, rootDirectory: '/var/app/data/static', sourceLine: line, sourceLogSha256: 'sha256:' + require('node:crypto').createHash('sha256').update(line).digest('hex') };
  let calls = 0;
  const h = { tenantAdmin: actor, Blocked, persist() {}, good: result => result.status === 200 && !result.data.error, api: async () => { calls++; throw Error('must not issue request'); } };
  for (const alter of [x => x.fileID++, x => x.namespace = 'b', x => x.originalPath += 'replacement', x => x.sourceLine = x.sourceLine.replace('no such file or directory', 'permission denied'), x => x.sourceLogSha256 = 'tampered']) {
    const changed = structuredClone(proof); alter(changed);
    await assert.rejects(require('./file_cases.cjs').reconcileOwnerDeletedFile(h, r, changed), /requires acknowledged exact DELETE/);
  }
  const unknown = structuredClone(r); unknown.deletion.outcome = 'unknown';
  await assert.rejects(require('./file_cases.cjs').reconcileOwnerDeletedFile(h, unknown, proof), /requires acknowledged exact DELETE/);
  assert.equal(calls, 0);
});
test('explicit original disposition preserves the HTTP500 defect and sends only reads; accessible bytes still block disposition', async () => {
  for (const status of [500, 200]) {
    const methods = [], ownerReads = [];
    const server = http.createServer((req, res) => { methods.push(req.method); res.statusCode = status; if (status === 200) res.setHeader('Content-Type', 'application/octet-stream'); res.end(status === 200 ? 'still accessible' : ''); });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const actor = { origin: 'http://a.local.vpc:' + server.address().port, identity: { account: 'admin', namespace: 'a' }, context: { cookies: async () => [] } };
    const r = { phase: 'created', visibility: 'public', base: '/files/', source: 'original', view: '/files/view/?fileToken=original', download: '/files/static/share/original/proof.bin?fileToken=original', id: 7, token: 'original', name: 'proof.bin', path: '/static/share/original/proof.bin', actorName: 'tenantAdmin', actorIdentity: actor.identity, origin: actor.origin, creation: { outcome: 'confirmed' }, deletion: { outcome: 'acknowledged', response: { status: 200, data: { value: { id: 7, token: 'original', name: 'proof.bin', path: '/static/share/original/proof.bin' } } } } };
    const line = '2026/11/08 03:16:02 WARN failed to serve static file path=/share/original/proof.bin err="open /var/app/data/static/share/original/proof.bin: no such file or directory"';
    const proof = { kind: 'magicfile-static-missing', sourceContainer: 'magicFile', fileID: 7, namespace: 'a', originalPath: r.path, rootDirectory: '/var/app/data/static', sourceLine: line, sourceLogSha256: 'sha256:' + require('node:crypto').createHash('sha256').update(line).digest('hex') };
    const h = { tenantAdmin: actor, Blocked, persist() {}, observe() {}, good: result => result.status === 200 && !result.data.error, check: (label, ok) => assert.ok(ok, label), api: async (actor, method, route) => { assert.equal(method, 'GET'); ownerReads.push(route); return { status: 200, data: { error: { code: 2 }, value: null } }; } };
    try {
      if (status === 500) {
        const result = await require('./file_cases.cjs').reconcileOwnerDeletedFile(h, r, proof);
        assert.equal(r.phase, 'deleted'); assert.equal(result.functionalRouteDefectOpen, true); assert.equal(result.byteRouteStatus, 500);
      } else { await assert.rejects(require('./file_cases.cjs').reconcileOwnerDeletedFile(h, r, proof), /returns no content/); assert.equal(r.phase, 'created'); }
      assert.deepEqual(methods, ['GET']); assert.equal(ownerReads.length, 2); assert.equal(r.deletion.outcome, 'acknowledged');
    } finally { await new Promise(resolve => server.close(resolve)); }
  }
});
test('public file route preflight rejects SPA fallback before creating any file', async () => {
  let requests = 0, writes = 0, closed = false;
  const server = http.createServer((req, res) => { requests++; if (req.method !== 'GET') writes++; res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><html>portal</html>'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const { request } = require('./playwright.cjs');
  const context = await request.newContext();
  const origin = 'http://tenant-a.local.vpc:' + server.address().port;
  const h = { tenantAdmin: { origin, identity: { namespace: 'tenant-a' } }, browser: { newContext: async () => ({ cookies: (...args) => context.storageState().then(s => s.cookies), close: async () => { closed = true; } }) }, check: (label, ok) => assert.ok(ok, label) };
  try {
    await assert.rejects(require('./file_cases.cjs').handlers['F049-001'](h), /before any upload/);
    assert.equal(requests, 1); assert.equal(writes, 0); assert.ok(closed);
  } finally { await context.dispose(); await new Promise(resolve => server.close(resolve)); }
});
test('ordinary file cleanup rejects unresolved upload, wrong owner, missing original ID and response-lost DELETE', async () => {
  const actor = { origin: 'https://tenant-a.example', identity: { account: 'member', namespace: 'tenant-a' } };
  const r = { id: 19, name: 'proof.bin', token: 'original', path: '/static/private/proof.bin', base: '/files/self/files/', actorName: 'user', origin: actor.origin, actorIdentity: structuredClone(actor.identity), creation: { outcome: 'confirmed' }, phase: 'created' };
  let deletes = 0;
  const h = { user: actor, Blocked, persist() {}, good: r => r.status === 200 && !r.data.error, check: (_, x) => assert.ok(x), api: async (actor, method) => {
    if (method === 'DELETE') { deletes++; throw Error('original DELETE response lost'); }
    return { status: 200, data: { value: { id: r.id, token: r.token, path: r.path, name: r.name } } };
  } };
  for (const mutate of [x => x.creation.outcome = 'unknown', x => x.id = undefined, x => x.actorIdentity.namespace = 'other']) {
    const changed = structuredClone(r); mutate(changed); await assert.rejects(cleanup(h, changed)); assert.equal(deletes, 0);
  }
  await assert.rejects(cleanup(h, r), /original DELETE response lost/); assert.equal(deletes, 1); assert.equal(r.deletion.outcome, 'unknown');
  await assert.rejects(cleanup(h, r), /never replay/); assert.equal(deletes, 1); assert.equal(r.phase, 'created');
});
test('ordinary binary transport distinguishes public cookie-free reads and never follows or retries writes', async () => {
  const seen = [], bytes = Buffer.from([0, 255, 128, 10]);
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    seen.push({ path: req.url, cookie: req.headers.cookie, body: Buffer.concat(chunks) });
    if (req.method === 'POST') { req.socket.destroy(); return; }
    res.setHeader('Content-Type', 'application/octet-stream'); res.end(bytes);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const origin = 'http://tenant-a.local.vpc:' + server.address().port, context = await browser.newContext();
    const actor = { origin, context, identity: { account: 'anonymous', namespace: 'tenant-a' } };
    const result = await fileTransfer(actor, 'GET', '/static/share/proof.bin'); assert.ok(result.data.bytes.equals(bytes)); assert.equal(seen[0].cookie, undefined);
    await context.addCookies([{ url: origin, name: 'session', value: 'private-owner', httpOnly: true }]);
    await assert.rejects(fileTransfer(actor, 'GET', '/static/share/proof.bin'), /without cookies/);
    await assert.rejects(fileTransfer(actor, 'POST', '/files/self/files/upload/?key-name=file&filePath=original', { name: 'original.bin', bytes }));
    assert.equal(seen.length, 2); assert.equal(seen[1].cookie, 'session=private-owner'); assert.ok(seen[1].body.includes(bytes));
    for (const path of ['//other.invalid/static/share/a', '/files/bound-files/a/download', '/files/self/files/download/#other']) await assert.rejects(fileTransfer(actor, 'GET', path));
    assert.equal(seen.length, 2);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
});
