const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const http = require('node:http');
const { referenceTransfer } = require('./owner_transport.cjs');
const { create, command, cleanup, sourceView, consumeBody, bindSourceBody, downloadRoute, handlers } = require('./bound_reference_cases.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');

function fixture(mode) {
  const actor = { origin: 'https://unit.invalid', identity: { namespace: 'panel', account: 'original' } };
  const targetApp = { id: 101, uuid: '11111111111111111111111111111111', updateTime: 5001 };
  const peerApp = { id: 102, uuid: '22222222222222222222222222222222', updateTime: 5002 };
  const refs = new Map(), persisted = [], calls = [];
  let current;
  const good = x => x.status === 200 && x.data?.error == null;
  const h = {
    admin: actor, Blocked: Error, state: { resources: [] }, observe() {}, good,
    persist() { persisted.push(structuredClone(h.state)); },
    check(label, condition) { assert.ok(condition, label); },
    async api(a, method, route, body) {
      const r = current || h.state.resources.find(v => v.fileRef && route.includes(v.fileRef.slice(6)));
      const action = r.commands.at(-1).action;
      calls.push(action);
      if (mode === 'lost-' + action) throw Error('unknown original command');
      if (action === 'service-guard') {
        assert.equal(method === 'POST' || method === 'DELETE', true);
        return { status: mode === 'human-consume-allowed' ? 200 : 403, data: { error: { code: 403, message: 'forbidden' } } };
      }
      if (action === 'wrong-purpose-bind') {
        return { status: 409, data: { value: null, error: { code: 21, message: '源码绑定未确认：upload reference cannot be consumed' } } };
      }
      if (action === 'mismatch-bind') {
        const status = mode === 'mismatch-500' ? 500 : 409;
        const code = mode === 'mismatch-500' ? 18 : 19;
        return { status, data: { value: null, error: { code, message: '源码绑定未确认：upload reference does not match expected content' } } };
      }
      if (action === 'foreign-bind') {
        return { status: 409, data: { value: null, error: { code: 21, message: mode === 'wrong-refusal' ? 'unrelated' : '源码绑定未确认：upload reference cannot be consumed' } } };
      }
      const ref = refs.get(r.fileRef);
      ref.bound = true;
      const value = { ...sourceView(r), ...(mode === 'wrong-ack' ? { source: { uri: 'local:foreign', digest: 'foreign', size: 1 } } : {}) };
      return { status: 200, data: { error: null, value } };
    },
  };
  async function transfer(a, method, route, file) {
    assert.equal(a, actor);
    if (method === 'POST') {
      const purpose = new URL(route, a.origin).searchParams.get('purpose') || 'application-function-source';
      calls.push('upload');
      assert.equal(persisted.at(-1).resources.at(-1).commands.at(-1).confirmed, false);
      if (mode === 'lost-upload') throw Error('unknown upload');
      const ref = crypto.randomBytes(32).toString('base64url');
      refs.set('bound_' + ref, { bytes: Buffer.from(file.bytes), bound: false, purpose });
      return {
        status: 200,
        data: {
          error: null,
          value: {
            uploadRef: ref, name: file.name, size: file.bytes.length,
            digest: 'sha256:' + crypto.createHash('sha256').update(file.bytes).digest('hex'),
            purpose, expiresAt: Date.now() + 60000,
            ...(mode === 'wrong-upload' ? { size: 1 } : {}),
          },
        },
      };
    }
    calls.push('download-guard');
    return { status: mode === 'human-download-allowed' ? 200 : 403, data: { text: 'forbidden' } };
  }
  return { h, transfer, targetApp, peerApp, refs, calls, persisted, select(r) { current = r; } };
}

async function bound(f) {
  const r = await create(f.h, 'account:7', f.targetApp, f.peerApp, {}, f.transfer);
  f.select(r);
  await command(f.h, r, 'service-guard', f.transfer);
  await command(f.h, r, 'mismatch-bind', f.transfer);
  await command(f.h, r, 'bind', f.transfer);
  return r;
}

test('Panel owner consumes bounded upload, blocks human direct Service routes, and rejects foreign consumer while keeping independent peer', async () => {
  const f = fixture();
  const r = await bound(f);
  await command(f.h, r, 'foreign-bind', f.transfer);
  const peer = await create(f.h, 'account:7', f.peerApp, f.targetApp, {}, f.transfer);
  f.select(peer);
  await command(f.h, peer, 'bind', f.transfer);
  await cleanup(f.h, r);
  await cleanup(f.h, peer);
  assert.equal(r.phase, 'deleted');
  assert.equal(peer.phase, 'deleted');
  assert.deepEqual(f.calls, ['upload', 'service-guard', 'download-guard', 'service-guard', 'mismatch-bind', 'bind', 'foreign-bind', 'upload', 'bind']);
  assert.ok(r.commands.every(c => c.confirmed));
  assert.equal(consumeBody(r).consumer, 'panel:function-block-source:' + f.targetApp.uuid);
  assert.equal(bindSourceBody(r).expectedDefinitionVersion, f.targetApp.updateTime);
  assert.ok(handlers['F049-004'].requiresOnlyDeliveryFixture);
});

test('unknown upload/service-guard/mismatch-bind/bind/foreign-bind cannot replay and human 200 leak on Service route is rejected', async () => {
  const leak = fixture('human-consume-allowed');
  const leakRef = await create(leak.h, 'account:7', leak.targetApp, leak.peerApp, {}, leak.transfer);
  leak.select(leakRef);
  await assert.rejects(command(leak.h, leakRef, 'service-guard', leak.transfer));

  const lost = fixture('lost-upload');
  await assert.rejects(create(lost.h, 'account:7', lost.targetApp, lost.peerApp, {}, lost.transfer));
  assert.equal(lost.h.state.resources[0].phase, 'intent');

  for (const action of ['bind', 'foreign-bind']) {
    const f = fixture('lost-' + action);
    const r = await create(f.h, 'account:7', f.targetApp, f.peerApp, {}, f.transfer);
    f.select(r);
    if (action !== 'bind') await command(f.h, r, 'bind', f.transfer);
    await assert.rejects(command(f.h, r, action, f.transfer));
    const count = f.calls.length;
    await assert.rejects(command(f.h, r, action, f.transfer), /unresolved/);
    await assert.rejects(cleanup(f.h, r), /unresolved/);
    assert.equal(f.calls.length, count);
  }
});

test('false upload/bind acknowledgement or wrong refusal never passes and immutable cleanup evidence binds exact fields', async () => {
  const a = fixture('wrong-upload');
  await assert.rejects(create(a.h, 'account:7', a.targetApp, a.peerApp, {}, a.transfer));
  assert.equal(a.h.state.resources[0].commands[0].confirmed, false);

  for (const mode of ['wrong-ack', 'wrong-refusal', 'mismatch-500']) {
    const f = fixture(mode);
    const r = await create(f.h, 'account:7', f.targetApp, f.peerApp, {}, f.transfer);
    f.select(r);
    if (mode === 'wrong-ack') await assert.rejects(command(f.h, r, 'bind', f.transfer));
    else if (mode === 'mismatch-500') await assert.rejects(command(f.h, r, 'mismatch-bind', f.transfer));
    else { await command(f.h, r, 'bind', f.transfer); await assert.rejects(command(f.h, r, 'foreign-bind', f.transfer)); }
    assert.equal(r.commands.at(-1).confirmed, false);
  }

  const f = fixture(), r = await bound(f);
  const original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  const changed = structuredClone(r);
  changed.consumer = 'other';
  assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
});

test('actual local socket transfers one private multipart upload and rejects oversized upload without Chromium', async t => {
  const seen = [], payload = Buffer.from('package main\n// 中文 Δ\n');
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    seen.push({ url: req.url, method: req.method, headers: req.headers, body: Buffer.concat(chunks) });
    res.setHeader('Content-Type', 'application/json');
    res.end('{"error":null,"value":{"uploadRef":"opaque"}}');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const origin = 'http://panel.local.vpc:' + server.address().port;
  const actor = {
    origin,
    identity: { account: 'original', namespace: 'panel' },
    context: { cookies: async () => [{ name: 'session', value: 'unit-original-cookie', domain: 'panel.local.vpc', path: '/', httpOnly: true, secure: false, expires: -1, sameSite: 'Lax' }] },
  };
  await referenceTransfer(actor, 'POST', '/files/self/files/upload-references/?purpose=application-function-source', { name: 'proof-0123456789abcdef.go', bytes: payload });
  assert.equal(seen.length, 1);
  assert.ok(seen[0].body.includes(payload));
  assert.equal(seen[0].headers.cookie, 'session=unit-original-cookie');
  await assert.rejects(referenceTransfer(actor, 'POST', '/files/self/files/upload-references/?purpose=application-function-source', { name: 'proof-0123456789abcdef.go', bytes: Buffer.alloc(65537) }));
  assert.equal(seen.length, 1);
  assert.ok(downloadRoute({ fileRef: 'bound_' + 'a'.repeat(43), namespace: 'panel' }, 'orig').includes('consumer=orig'));
});
