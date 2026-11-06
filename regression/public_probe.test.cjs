const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('playwright');
const { publicGet } = require('./public_probe.cjs');

test('public GET records the first hop, original Cookie and Location without following redirects', async () => {
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push({ route: req.url, cookie: req.headers.cookie });
    if (req.url.startsWith('/api/v1/web/proxy/')) res.writeHead(302, { Location: '/missing' });
    else if (/^\/redirect\//.test(req.url)) res.writeHead(Number(req.url.split('/')[2]), { Location: '/missing' });
    else if (req.url === '/missing') res.writeHead(404);
    else res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end('isolated fixture');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const context = await browser.newContext();
    const origin = 'http://127.0.0.1:' + server.address().port;
    await context.addCookies([{ name: 'original-session', value: 'isolated-cookie', url: origin, httpOnly: true }]);
    const page = await context.newPage(); await page.goto(origin);
    const actor = { page, context, origin };
    assert.equal((await publicGet(actor, '/missing')).status, 404);
    for (const status of [301, 302, 307, 308]) {
      const before = seen.length;
      const result = await publicGet(actor, '/redirect/' + status);
      assert.equal(result.status, status);
      assert.equal(result.location, '/missing');
      assert.equal(result.url, origin + '/redirect/' + status);
      assert.equal(result.status === 404, false);
      assert.deepEqual(seen.slice(before), [{ route: '/redirect/' + status, cookie: 'original-session=isolated-cookie' }]);
    }
    const proxyRoute = '/api/v1/web/proxy/system/context/?surface=portal';
    const beforeProxy = seen.length;
    const proxy = await publicGet(actor, proxyRoute);
    assert.equal(proxy.status, 302); assert.equal(proxy.location, '/missing');
    assert.deepEqual(seen.slice(beforeProxy), [{ route: proxyRoute, cookie: 'original-session=isolated-cookie' }]);
    for (const route of ['//attacker.invalid/probe', '/\\attacker.invalid/probe', 'https://attacker.invalid/', '/missing#fragment']) await assert.rejects(publicGet(actor, route), /same-origin/);
    await assert.rejects(publicGet({ ...actor, origin: 'http://other.invalid' }, '/missing'), /same-origin/);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
});
