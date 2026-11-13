const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { loadConfig, privateFile, getSnapshot, limit } = require('./runtime_machine_transport.cjs');
function inputs(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-machine-unit-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const tokenFile = path.join(root, 'token'), filename = path.join(root, 'config');
  fs.writeFileSync(tokenFile, 'unit-original-bearer\n', { mode: 0o600 });
  const c = { origin: 'http://127.0.0.1:12345', instanceId: 'gateway1', incarnation: 'boot1', endpointId: 7, clientId: 'client1', tokenFile };
  const save = value => fs.writeFileSync(filename, JSON.stringify(value), { mode: 0o600 }); save(c);
  return { root, filename, tokenFile, c, save };
}
async function server(t, handle) {
  const s = http.createServer(handle); await new Promise(resolve => s.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { s.closeAllConnections(); s.close(resolve); }));
  return 'http://127.0.0.1:' + s.address().port;
}
test('private machine input is exact, outside repositories and digest-bound without credential evidence', t => {
  const f = inputs(t), c = loadConfig(f.filename);
  assert.equal(c.token, 'unit-original-bearer');
  assert.equal(c.configDigest, 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(f.filename)).digest('hex'));
  assert.throws(() => privateFile('relative', 1), /outside/);
  assert.throws(() => privateFile(path.join(os.homedir(), 'codespace', 'private-test'), 1), /outside/);
  for (const mutate of [v => v.extra = 'forbidden', v => delete v.incarnation, v => v.endpointId = 0, v => v.endpointId = '7',
    v => v.instanceId = 'bad\nheader', v => v.origin += '/', v => v.origin = 'http://user:pass@localhost', v => v.origin = 'file:///tmp', v => v.tokenFile = null]) {
    const changed = structuredClone(f.c); mutate(changed); f.save(changed); assert.throws(() => loadConfig(f.filename));
  }
});
test('unsafe mode, file bounds and symlink inputs cannot load original machine bearer', t => {
  const f = inputs(t);
  fs.chmodSync(f.filename, 0o644); assert.throws(() => loadConfig(f.filename), /private configuration/); fs.chmodSync(f.filename, 0o600);
  fs.chmodSync(f.tokenFile, 0o640); assert.throws(() => loadConfig(f.filename), /unsafe/); fs.chmodSync(f.tokenFile, 0o600);
  const link = path.join(f.root, 'link'); fs.symlinkSync(f.tokenFile, link); f.save({ ...f.c, tokenFile: link }); assert.throws(() => loadConfig(f.filename), /unsafe/);
  f.save(f.c);
  for (const bytes of ['', 'Bearer secret', 'unit-original-bearer\nsecond', 'a'.repeat(65537)]) {
    fs.writeFileSync(f.tokenFile, bytes); assert.throws(() => loadConfig(f.filename));
  }
  fs.writeFileSync(f.filename, ' '.repeat(8193)); assert.throws(() => loadConfig(f.filename), /private configuration/);
  assert.throws(() => privateFile(f.root, 8192), /unsafe/);
});
test('foreign UID is rejected by file gate without opening a socket', t => {
  const f = inputs(t), original = process.getuid;
  try { process.getuid = () => original() + 1; assert.throws(() => loadConfig(f.filename), /private configuration/); }
  finally { process.getuid = original; }
});
test('actual local HTTP receives one original GET and bearer, no cookie; body bytes and digest are exact', async t => {
  const f = inputs(t), body = Buffer.from(JSON.stringify({ value: { label: '真实字节' }, error: null })), calls = [];
  const origin = await server(t, (req, res) => { calls.push({ method: req.method, url: req.url, headers: req.headers }); res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(body); });
  f.save({ ...f.c, origin }); const c = loadConfig(f.filename), r = await getSnapshot(c, '?_pageSize=1');
  assert.equal(calls.length, 1); assert.equal(calls[0].method, 'GET'); assert.equal(calls[0].url, '/api/v1/panel/runtime-execution/snapshot/?_pageSize=1');
  assert.equal(calls[0].headers.authorization, 'Bearer unit-original-bearer'); assert.equal(calls[0].headers.cookie, undefined);
  assert.equal(r.byteLength, body.length); assert.equal(r.sha256, 'sha256:' + crypto.createHash('sha256').update(body).digest('hex')); assert.equal(r.data.value.label, '真实字节');
  assert.throws(() => getSnapshot(c, '?arbitrary=1'), /finite/);
});
test('local.vpc ingress keeps original Host while resolving only to loopback', async t => {
  const f = inputs(t); let host;
  const origin = (await server(t, (req, res) => { host = req.headers.host; res.end('{}'); })).replace('127.0.0.1', 'panel.local.vpc');
  f.save({ ...f.c, origin }); await getSnapshot(loadConfig(f.filename)); assert.equal(host, new URL(origin).host);
});
test('redirect is refused with no follow and no repeated original request', async t => {
  const f = inputs(t); let calls = 0;
  const origin = await server(t, (req, res) => { calls++; res.writeHead(302, { Location: '/must-not-follow' }); res.end(); }); f.save({ ...f.c, origin });
  await assert.rejects(getSnapshot(loadConfig(f.filename)), /no retry/); assert.equal(calls, 1);
});
test('response loss and body/header credential echoes stay fixed diagnostics without retry', async t => {
  const f = inputs(t);
  for (const mode of ['lost', 'body', 'content-type', 'cache-control']) {
    let calls = 0;
    const origin = await server(t, (req, res) => { calls++;
      if (mode === 'lost') { res.writeHead(200, { 'Content-Length': 100 }); res.flushHeaders(); res.socket.destroy(); }
      else { if (mode !== 'body') res.setHeader(mode, 'unit-original-bearer'); res.end(mode === 'body' ? '{"secret":"unit-original-bearer"}' : '{}'); }
    }); f.save({ ...f.c, origin });
    await assert.rejects(getSnapshot(loadConfig(f.filename)), e => !e.message.includes('unit-original-bearer') && /no retry/.test(e.message)); assert.equal(calls, 1);
  }
});
test('16MiB envelope body accepted exactly; overflow rejected while streaming without retry', async t => {
  const f = inputs(t);
  for (const extra of [0, 1]) {
    let calls = 0; const body = Buffer.alloc(limit + extra, 32); body.write('{}');
    const origin = await server(t, (req, res) => { calls++; res.end(body); }); f.save({ ...f.c, origin });
    if (extra) await assert.rejects(getSnapshot(loadConfig(f.filename)), /no retry/);
    else { const result = await getSnapshot(loadConfig(f.filename)); assert.equal(result.byteLength, limit); assert.deepEqual(result.data, {}); }
    assert.equal(calls, 1);
  }
});
test('whole-request deadline ends a stalled response with one request and no retry', { timeout: 20000 }, async t => {
  const f = inputs(t); let calls = 0;
  const origin = await server(t, (req, res) => { calls++; res.writeHead(200); res.write(' '); }); f.save({ ...f.c, origin });
  await assert.rejects(getSnapshot(loadConfig(f.filename)), /no retry/); assert.equal(calls, 1);
});
