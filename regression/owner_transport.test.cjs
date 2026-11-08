const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('playwright');
const { ownerRequest } = require('./owner_transport.cjs');
const { feedbackAttachment } = require('./owner_transport.cjs');
test('feedback multipart and binary transport preserves bytes, identity and single-dispatch boundary', async () => {
  const browser = await chromium.launch({ headless: true }), seen = [], records = [];
  const bytes = Buffer.from('PRIVATE-BINARY\0\r\n中文 Δ'), ref = 'bound_' + 'a'.repeat(43);
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    seen.push({ path: req.url, method: req.method, headers: req.headers, body: Buffer.concat(chunks) });
    if (req.method === 'POST') { res.setHeader('Content-Type', 'application/json'); return res.end(JSON.stringify({ error: null, value: { fileRef: ref } })); }
    res.setHeader('Content-Type', 'application/octet-stream'); res.end(bytes);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const origin = 'http://tenant-a.local.vpc:' + server.address().port, context = await browser.newContext();
    await context.addCookies([{ url: origin, name: 'session', value: 'original', httpOnly: true }]);
    const actor = { identity: { account: 'member', namespace: 'tenant-a' }, origin, context }, base = '/portal/feedbacks/19/attachments/';
    const uploaded = await feedbackAttachment(actor, 'POST', base, { name: 'proof.bin', bytes }, x => records.push(x));
    assert.equal(uploaded.data.value.fileRef, ref);
    assert.equal(seen.length, 1); assert.equal(seen[0].headers.host, new URL(origin).host); assert.equal(seen[0].headers.origin, origin); assert.equal(seen[0].headers.cookie, 'session=original');
    assert.match(seen[0].headers['content-type'], /^multipart\/form-data; boundary=/);
    assert.ok(seen[0].body.includes(bytes)); assert.match(seen[0].body.toString(), /name="file"; filename="proof.bin"/);
    const download = await feedbackAttachment(actor, 'GET', base + ref, undefined, x => records.push(x));
    assert.ok(download.data.bytes.equals(bytes)); assert.equal(seen.length, 2);
    assert.doesNotMatch(JSON.stringify(records), /PRIVATE|session=|buffer|"bytes"/);
    for (const route of ['//foreign.invalid/', '/files/bound-files/' + ref, base + '../other', base + ref + '?namespace=other']) await assert.rejects(feedbackAttachment(actor, 'GET', route));
    await assert.rejects(feedbackAttachment(actor, 'POST', base, { name: '../escape', bytes }));
    assert.equal(seen.length, 2);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
});
test('owner request keeps exact virtual Host, original cookies, cookie changes and no redirect or write retry', async () => {
  const browser = await chromium.launch({ headless: true }), seen = [];
  const server = http.createServer(async (req, res) => {
    seen.push({ url: req.url, host: req.headers.host, origin: req.headers.origin, cookie: req.headers.cookie });
    if (req.url.endsWith('/lost')) { req.socket.destroy(); return; }
    if (req.url.endsWith('/redirect')) { res.writeHead(302, { Location: '/foreign', 'Content-Type': 'application/json' }); res.end('{}'); return; }
    res.setHeader('Set-Cookie', req.url.endsWith('/clear') ? 'session=; Path=/; Max-Age=0; HttpOnly' : 'session=rotated; Path=/; HttpOnly; SameSite=Lax');
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ error: null, value: { id: 7 } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const origin = 'http://tenant-a.local.vpc:' + server.address().port, context = await browser.newContext();
    await context.addCookies([{ name: 'session', value: 'original', url: origin, httpOnly: true }, { name: 'foreign', value: 'private-other', url: 'http://tenant-b.local.vpc' }]);
    const actor = { identity: { account: 'member', namespace: 'tenant-a' }, context, origin };
    const result = await ownerRequest(actor, 'POST', '/original/', { name: 'one' });
    assert.equal(result.data.value.id, 7); assert.equal(seen[0].host, new URL(origin).host); assert.equal(seen[0].origin, origin);
    assert.equal(seen[0].cookie, 'session=original');
    assert.equal((await context.cookies(origin)).find(c => c.name === 'session').value, 'rotated');
    const redirect = await ownerRequest(actor, 'POST', '/redirect', {});
    assert.equal(redirect.status, 302); assert.equal(seen.filter(x => x.url === '/foreign').length, 0);
    await assert.rejects(ownerRequest(actor, 'POST', '/lost', {}));
    assert.equal(seen.filter(x => x.url.endsWith('/lost')).length, 1);
    await ownerRequest(actor, 'DELETE', '/clear');
    assert.equal((await context.cookies(origin)).length, 0);
    assert.equal((await context.cookies('http://tenant-b.local.vpc'))[0].value, 'private-other');
    await assert.rejects(ownerRequest(actor, 'POST', '//foreign.invalid/path', {}), /same-origin/);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
});
