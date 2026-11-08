const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('playwright');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
async function fixture(action) {
  const seen = [], captured = [], journal = [], records = [];
  let lose = false;
  const form = (path, extra = '') => `<form method="post" action="${path}"><input name="namespace" value="tenant-a"><input name="transaction" value="PRIVATE-TX"><input name="csrf_token" value="PRIVATE-CSRF"><input name="account" value="member"><input name="password" value="PRIVATE+密 码&=">${extra}<button type="submit">submit</button></form>`;
  const server = http.createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk;
    if (req.method === 'POST') {
      seen.push({ path: req.url, body, headers: req.headers });
      if (lose) return req.socket.destroy();
      const change = req.url === '/oauth/password/change';
      res.writeHead(302, { Location: change ? '/portal/' : '/change', 'Set-Cookie': `session=${change ? 'changed' : 'logged'}; Path=/; HttpOnly; SameSite=Lax` });
      return res.end();
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(req.url === '/change' ? form('/oauth/password/change', '<input name="password_confirm" value="PRIVATE+密 码&=">') : req.url === '/portal/' ? '<div>Original portal</div>' : form('/oauth/login'));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ executablePath: process.env.MAGICTEST_CHROME || chromium.executablePath(), headless: true, args: ['--no-proxy-server', '--host-resolver-rules=MAP *.local.vpc 127.0.0.1'] });
  try {
    const origin = 'http://tenant-a.local.vpc:' + server.address().port;
    const context = await browser.newContext(), page = await context.newPage();
    await context.addCookies([{ url: origin, name: 'session', value: 'original', httpOnly: true }, { url: 'http://tenant-b.local.vpc', name: 'foreign', value: 'PRIVATE-OTHER' }]);
    page.on('request', req => { if (req.method() === 'POST') captured.push(req.postData()); });
    const actor = { origin, context, page, identity: { namespace: 'tenant-a', account: 'member' } };
    await page.goto(origin + '/login/cas');
    const submit = () => Promise.all([page.waitForNavigation({ waitUntil: 'load', timeout: 4000 }), page.locator('button').click({ timeout: 4000 })]);
    await action({ actor, page, context, origin, seen, captured, journal, records, submit, lose: () => { lose = true; }, hooks: { journal, persist() {}, record: x => records.push(x) } });
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
}
test('real original forms keep exact bytes, Host, Origin, Cookie, redirects and browser cookie changes', async () => fixture(async f => {
  let persisted = 0;
  await withOriginalCasForms(f.actor, { ...f.hooks, persist() { persisted++; if (persisted === 1) assert.equal(f.seen.length, 0); } }, async () => {
    await f.submit(); assert.equal(new URL(f.page.url()).pathname, '/change');
    await f.submit(); assert.equal(new URL(f.page.url()).pathname, '/portal/');
  });
  assert.equal(f.seen.length, 2);
  assert.deepEqual(f.seen.map(x => x.body), f.captured);
  assert.equal(f.seen[0].headers.host, new URL(f.origin).host);
  assert.equal(f.seen[0].headers.origin, f.origin);
  assert.equal(f.seen[0].headers.cookie, 'session=original');
  assert.equal(f.seen[1].headers.cookie, 'session=logged');
  assert.equal((await f.context.cookies(f.origin))[0].value, 'changed');
  assert.ok(f.journal.every(x => x.phase === 'browser-delivered'));
  assert.deepEqual(f.journal.map(x => Buffer.from(x.bodyBase64, 'base64').toString()), f.captured);
  assert.doesNotMatch(JSON.stringify(f.records), /PRIVATE|password=|csrf_token|cookie|headers|transaction/);
}));
test('response loss remains unknown and original command is never replayed', async () => fixture(async f => {
  f.lose();
  await assert.rejects(withOriginalCasForms(f.actor, f.hooks, f.submit));
  assert.equal(f.seen.length, 1); assert.equal(f.journal[0].phase, 'unknown');
}));
test('failed write-ahead persistence prevents dispatch', async () => fixture(async f => {
  await assert.rejects(withOriginalCasForms(f.actor, { ...f.hooks, persist() { throw Error('durable journal unavailable'); } }, f.submit), /durable journal unavailable/);
  assert.equal(f.seen.length, 0);
}));
test('different actor, wrong namespace and unexpected OAuth command never dispatch', async () => {
  for (const variant of ['actor', 'namespace', 'path']) await fixture(async f => {
    await assert.rejects(withOriginalCasForms(f.actor, f.hooks, async () => {
      if (variant === 'actor') f.actor.identity.account = 'other';
      if (variant === 'namespace') await f.page.locator('[name=namespace]').fill('tenant-b');
      if (variant === 'path') await f.page.locator('form').evaluate(el => el.action = '/oauth/revoke');
      await f.submit();
    }), /Refused/);
    assert.equal(f.seen.length, 0);
  });
});
test('second submission of same original path is refused without a second command', async () => fixture(async f => {
  await assert.rejects(withOriginalCasForms(f.actor, f.hooks, async () => {
    await f.submit(); await f.page.goto(f.origin + '/login/cas'); await f.submit();
  }), /duplicate/);
  assert.equal(f.seen.length, 1); assert.equal(f.journal.length, 1);
}));
test('identity mutation during journal persistence prevents dispatch', async () => fixture(async f => {
  await assert.rejects(withOriginalCasForms(f.actor, { ...f.hooks, persist() { f.actor.origin = f.origin.replace('tenant-a', 'tenant-b'); } }, f.submit), /actor changed/);
  assert.equal(f.seen.length, 0);
}));
