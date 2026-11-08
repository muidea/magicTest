const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const http = require('node:http');
const { transfer, digest, multipart, budget } = require('./file_stream_transport.cjs');
const hash = b => 'sha256:' + crypto.createHash('sha256').update(b).digest('hex');
async function fixture(callback, action) {
  const server = http.createServer(callback); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const jar = [{ name: 'owner', value: 'original', domain: 'owner.local.vpc', path: '/' }];
  const actor = { origin: 'http://owner.local.vpc:' + server.address().port, identity: { account: 'ordinary', namespace: 'owner' }, context: {
    async cookies() { return structuredClone(jar); }, async addCookies(values) { for (const value of values) { const index = jar.findIndex(c => c.name === value.name && c.path === value.path); if (index >= 0) jar[index] = value; else jar.push(value); } },
    async clearCookies(value) { const index = jar.findIndex(c => c.name === value.name && c.path === value.path); if (index >= 0) jar.splice(index, 1); }
  } };
  try { await action(actor, jar); } finally { await new Promise(resolve => server.close(resolve)); }
}
test('streamed multipart preserves content boundary above former 10 MiB tool cap and reads full binary digest with current cookies', async () => {
  const size = 11 * 1024 * 1024 + 3, expected = Buffer.alloc(size);
  for (let offset = 0; offset < size; offset += 65536) for (let i = 0; i < Math.min(65536, size - offset); i++) expected[offset + i] = i % 251;
  let posts = 0, gets = 0; const events = [];
  await fixture(async (req, res) => {
    assert.equal(req.headers.host.split(':')[0], 'owner.local.vpc'); assert.equal(req.headers.origin, 'http://' + req.headers.host);
    if (req.method === 'POST') {
      posts++; assert.equal(req.headers.cookie, 'owner=original');
      const chunks = []; for await (const chunk of req) chunks.push(chunk); const body = Buffer.concat(chunks);
      assert.equal(body.length, +req.headers['content-length']);
      const start = body.indexOf('\r\n\r\n') + 4, boundary = req.headers['content-type'].split('boundary=')[1], tail = Buffer.byteLength('\r\n--' + boundary + '--\r\n');
      assert.ok(body.subarray(start, body.length - tail).equals(expected));
      res.setHeader('Set-Cookie', ['owner=rotated; HttpOnly; Path=/; SameSite=Lax', 'expired=; Max-Age=0; Path=/']);
      res.end(JSON.stringify({ value: { name: 'original.bin', token: 'original-token' } }));
    } else {
      gets++; assert.equal(req.headers.cookie, 'owner=rotated');
      res.setHeader('Content-Type', 'application/octet-stream'); res.end(expected);
    }
  }, async (actor, jar) => {
    const response = await transfer(actor, 'POST', '/files/self/files/upload/?key-name=file&filePath=original', { name: 'original.bin', size }, e => events.push(e));
    assert.equal(response.data.value.name, 'original.bin'); assert.equal(jar[0].value, 'rotated'); assert.equal(jar[0].domain, 'owner.local.vpc');
    const read = await transfer(actor, 'GET', '/files/self/files/download/?fileToken=original-token', undefined, e => events.push(e));
    assert.equal(read.data.byteLength, size); assert.equal(read.data.digest, hash(expected)); assert.equal(digest(size), hash(expected));
    assert.equal(events.length, 2); assert.ok(!JSON.stringify(events).includes('owner=original')); assert.equal(events[0].contentBytes, size);
  });
  assert.equal(posts, 1); assert.equal(gets, 1);
});
test('empty content is a real zero-byte multipart part and streaming download, not a missing file', async () => {
  const body = Buffer.concat([...multipart(0, 'empty.bin')]);
  assert.ok(body.includes('filename="empty.bin"')); assert.equal(digest(0), hash(Buffer.alloc(0)));
  await fixture((req, res) => { res.setHeader('Content-Type', 'application/octet-stream'); res.end(); }, async actor => {
    const read = await transfer(actor, 'GET', '/files/self/files/download/?fileToken=empty'); assert.equal(read.data.byteLength, 0); assert.equal(read.data.digest, digest(0));
  });
});
test('unknown writes are dispatched once, redirects are returned without following, invalid routes and budgets send nothing', async () => {
  let calls = 0;
  await fixture(async (req, res) => {
    calls++; if (req.url.includes('drop')) { req.socket.destroy(); return; }
    res.statusCode = 307; res.setHeader('Location', '/must-not-follow'); res.end(JSON.stringify({ error: { code: 4, message: 'upload rejected' } }));
  }, async actor => {
    const upload = { name: 'original.bin', size: 4 };
    await assert.rejects(transfer(actor, 'POST', '/files/self/files/upload/?key-name=file&filePath=drop', upload)); assert.equal(calls, 1);
    const rejected = await transfer(actor, 'POST', '/files/self/files/upload/?key-name=file&filePath=redirect', upload); assert.equal(rejected.status, 307); assert.equal(calls, 2);
    for (const route of ['//other.invalid/files/self/files/upload/?key-name=file', '/files/upload/?key-name=file', '/files/self/files/upload/?key-name=wrong', '/files/self/files/upload/?key-name=file#fragment']) await assert.rejects(transfer(actor, 'POST', route, upload));
    for (const size of [-1, 0.5, NaN, budget + 1]) await assert.rejects(transfer(actor, 'POST', '/files/self/files/upload/?key-name=file', { ...upload, size }));
    assert.equal(calls, 2);
  });
});
