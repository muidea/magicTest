const { test } = require('node:test');
const assert = require('node:assert/strict');
const { authorizationVariant, runControls } = require('./callback_cases.cjs');
const origin = 'https://tenant-a.local.vpc';
function original() {
  const url = new URL('/oauth/authorize', origin);
  url.search = new URLSearchParams({ response_type: 'code', state: 'server-state', nonce: 'server-nonce', client_id: 'first-party-bff', redirect_uri: origin + '/api/v1/web/auth/callback', code_challenge: 'original-s256-challenge', code_challenge_method: 'S256', scope: 'openid profile', client_namespace: 'panel' });
  return url;
}
test('nonce probe changes only the original nonce and preserves all other transaction material', () => {
  const before = original();
  assert.equal(authorizationVariant(before.href, origin, 'normal').href, before.href);
  const changed = authorizationVariant(before.href, origin, 'nonce');
  assert.notEqual(changed.searchParams.get('nonce'), before.searchParams.get('nonce'));
  assert.equal(changed.origin, before.origin); assert.equal(changed.pathname, before.pathname);
  changed.searchParams.set('nonce', before.searchParams.get('nonce'));
  assert.equal(changed.href, before.href);
});
test('state and S256 controls change exactly one original field while retaining every other parameter', () => {
  for (const [mode, field] of [['state', 'state'], ['pkce', 'code_challenge']]) {
    const before = original(), changed = authorizationVariant(before.href, origin, mode);
    assert.notEqual(changed.searchParams.get(field), before.searchParams.get(field));
    assert.match(changed.searchParams.get(field), /^[A-Za-z0-9_-]{43}$/);
    changed.searchParams.set(field, before.searchParams.get(field));
    assert.equal(changed.href, before.href);
  }
});
test('later tool or cleanup interruption cannot replace an already confirmed callback defect with a blocked result', async () => {
  const observation = [], security = Error('confirmed security failure'), interrupted = Error('later network interruption');
  const h = { state: { callbackProbes: [] }, observe: r => observation.push(r), check: (label, ok) => { if (!ok) throw security; } };
  await assert.rejects(runControls(h, async (h, mode) => {
    if (mode === 'state') throw interrupted;
    return { mode, passed: mode === 'normal' };
  }), e => e === security);
  assert.equal(observation[0].reason, interrupted.message);
  assert.equal(observation[0].observed.find(r => r.mode === 'nonce').passed, false);
  h.state.callbackProbes = [];
  await assert.rejects(runControls(h, async () => { throw interrupted; }), e => e === interrupted);
});
test('probe rejects foreign origin, ambiguous or missing state/nonce and wrong PKCE before dispatch', () => {
  for (const alter of [u => { u.hostname = 'tenant-b.local.vpc'; }, u => { u.pathname = '/api/v1/web/session/'; }, u => u.searchParams.append('state', 'other'), u => u.searchParams.delete('nonce'), u => u.searchParams.set('nonce', ''), u => u.searchParams.set('code_challenge_method', 'plain'), u => u.searchParams.set('redirect_uri', 'https://attacker.invalid/callback')]) {
    const url = original(); alter(url); assert.throws(() => authorizationVariant(url.href, origin, 'nonce'));
  }
  assert.throws(() => authorizationVariant(original().href, origin, 'unknown'));
});

test('real redirect chain preserves original BFF cookies and observes the exact selected authorization variant', async () => {
  const http = require('node:http'), { chromium } = require('./playwright.cjs');
  const { withOriginalAuthorizationEntry } = require('./callback_cases.cjs');
  let origin, journal, seen = [], persisted;
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, origin);
    if (url.pathname === '/api/v1/web/auth/login') {
      assert.equal(persisted.entry.outcome, 'unknown');
      const authorize = new URL('/oauth/authorize', origin);
      authorize.search = new URLSearchParams({ response_type: 'code', state: 'original-state', nonce: 'original-nonce', client_id: 'original-bff', redirect_uri: origin + '/api/v1/web/auth/callback', code_challenge: 'original-challenge', code_challenge_method: 'S256' });
      res.writeHead(302, { Location: authorize.href, 'Set-Cookie': 'pending=original-browser; Path=/; HttpOnly' }); return res.end();
    }
    if (url.pathname === '/oauth/authorize') {
      assert.equal(persisted.authorizations[0].outcome, 'prepared');
      seen.push({ nonce: url.searchParams.get('nonce'), state: url.searchParams.get('state'), challenge: url.searchParams.get('code_challenge'), cookie: req.headers.cookie });
      res.writeHead(302, { Location: origin + '/api/v1/web/auth/callback?' + new URLSearchParams({ code: 'original-code', state: url.searchParams.get('state') }) }); return res.end();
    }
    if (url.pathname === '/api/v1/web/auth/callback') { res.writeHead(302, { Location: '/portal/' }); return res.end(); }
    res.end('Original portal');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = 'http://tenant-a.local.vpc:' + server.address().port;
  const browser = await chromium.launch({ executablePath: process.env.MAGICTEST_CHROME || chromium.executablePath(), headless: true, args: ['--no-proxy-server', '--host-resolver-rules=MAP *.local.vpc 127.0.0.1'] });
  try {
    for (const mode of ['normal', 'nonce', 'state', 'pkce']) {
      const context = await browser.newContext(), page = await context.newPage();
      const actor = { origin, context, page, identity: { account: 'member', namespace: 'tenant-a' } };
      journal = { authorizations: [], callbacks: [] }; persisted = null;
      await withOriginalAuthorizationEntry(actor, mode, { journal, persist: () => { persisted = structuredClone(journal); } }, () => page.goto(origin + '/api/v1/web/auth/login', { waitUntil: 'networkidle' }));
      assert.equal(journal.authorizations.length, 1); assert.equal(journal.authorizations[0].observations, 1); assert.equal(journal.authorizations[0].outcome, 'response-received');
      assert.equal(journal.callbacks.length, 1); assert.equal(journal.callbacks[0].status, 302);
      assert.equal(seen.at(-1).cookie, 'pending=original-browser');
      if (mode === 'nonce') assert.notEqual(seen.at(-1).nonce, 'original-nonce'); else assert.equal(seen.at(-1).nonce, 'original-nonce');
      if (mode === 'state') assert.notEqual(seen.at(-1).state, 'original-state'); else assert.equal(seen.at(-1).state, 'original-state');
      if (mode === 'pkce') assert.notEqual(seen.at(-1).challenge, 'original-challenge'); else assert.equal(seen.at(-1).challenge, 'original-challenge');
      assert.equal(new URL(journal.callbacks[0].originalURL).searchParams.get('state'), seen.at(-1).state);
      await context.close();
    }
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
});
