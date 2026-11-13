const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('./playwright.cjs');
const { brandingAsset } = require('./owner_transport.cjs');
test('brand multipart preserves exact original Host, cookies and bytes; refuses foreign paths and never retries lost writes', async () => {
  const browser = await chromium.launch({ headless: true }), seen = [], records = [], bytes = Buffer.from('finite-PNG-fixture');
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    seen.push({ path: req.url, host: req.headers.host, cookie: req.headers.cookie, body: Buffer.concat(chunks) });
    if (seen.length === 2) { req.socket.destroy(); return; }
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ error: null, value: { namespace: 'a' } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const origin = 'http://a.local.vpc:' + server.address().port, context = await browser.newContext();
    await context.addCookies([{ name: 'session', value: 'original', url: origin, httpOnly: true }]);
    const actor = { identity: { account: 'original', namespace: 'a' }, origin, context }, route = '/panel/namespace-branding/assets/brand-icon', file = { name: 'brand-icon.png', bytes };
    const response = await brandingAsset(actor, route, file, e => records.push(e));
    assert.equal(response.data.value.namespace, 'a'); assert.equal(seen[0].path, '/api/v1/web/proxy' + route); assert.equal(seen[0].host, new URL(origin).host); assert.equal(seen[0].cookie, 'session=original'); assert.ok(seen[0].body.includes(bytes));
    assert.doesNotMatch(JSON.stringify(records), /finite-PNG|session=|"bytes"/);
    for (const invalid of ['//foreign.example/asset', route + '?namespace=b', route + '/', '/panel/namespace-branding/assets/favicon']) await assert.rejects(brandingAsset(actor, invalid, file));
    await assert.rejects(brandingAsset(actor, route, { ...file, name: '../escape.png' }));
    await assert.rejects(brandingAsset(actor, route, { ...file, bytes: Buffer.alloc(1048577) }));
    assert.equal(seen.length, 1);
    await assert.rejects(brandingAsset(actor, route, file)); assert.equal(seen.length, 2);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
});
