const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require('./playwright.cjs');
const { parkSessions, readyActor } = require('./session_lifecycle.cjs');
test('case entry renews only the original unauthenticated actor and never turns a dependency failure into a new login',async()=>{
 for(const mode of ['expired','dependency','forbidden','wrong-actor']) {
  const original={identity:{account:'original',namespace:'one'},origin:'https://one.example.invalid',password:'private-test-only'};let reads=0,logins=0;
  const h={user:original,Blocked:Error,observe(){},good:r=>r.status===200 && !r.data.error,async login(){logins++;return {...original,identity:mode==='wrong-actor'?{...original.identity,namespace:'two'}:original.identity};}};
  const read=async()=>++reads===1?{status:mode==='dependency'?503:mode==='forbidden'?403:401,data:{}}:{status:200,data:{value:{account:{account:'original'},homeNamespace:'one'}}};
  if(mode==='expired'){await readyActor(h,'user',read);assert.equal(logins,1);assert.equal(reads,2);}
  else {await assert.rejects(readyActor(h,'user',read));assert.equal(logins,mode==='wrong-actor'?1:0);}
 }
});
test('finished UI polling stops while the original session still makes one explicit owner command', async () => {
  let polls = 0, commands = 0;
  const server = http.createServer((req, res) => {
    if (req.url === '/portal/') {
      res.setHeader('Set-Cookie', 'original=session-bytes; HttpOnly; Path=/');
      res.end('<script>setInterval(()=>fetch("/poll"),30)</script>');
    } else if (req.url === '/poll') { polls++; res.end('read'); }
    else {
      assert.equal(req.headers.cookie, 'original=session-bytes');
      if (req.method === 'POST') commands++;
      res.setHeader('Content-Type', 'application/json'); res.end('{"original":true}');
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext(), page = await context.newPage(), origin = 'http://127.0.0.1:' + server.address().port;
    const actor = { context, page, origin, identity: { account: 'original', namespace: 'one' } };
    let issuedPolls = 0;
    page.on('request', request => { if (new URL(request.url()).pathname === '/poll') issuedPolls++; });
    await page.goto(origin + '/portal/'); await page.waitForFunction(() => performance.getEntriesByType('resource').some(e => e.name.endsWith('/poll')));
    const cookies = await context.cookies(origin);
    assert.equal((await parkSessions([actor]))[0].parked, true);
    // Count issuance: a request sent before navigation can reach the server
    // afterwards, without the parked document issuing another poll.
    assert.ok(issuedPolls > 0);
    const stopped = issuedPolls; await new Promise(resolve => setTimeout(resolve, 150));
    assert.equal(issuedPolls, stopped); assert.deepEqual(await context.cookies(origin), cookies);
    assert.equal(commands, 0, 'parking sends no logout or business command');
    assert.deepEqual(await page.evaluate(() => fetch('/owner', {method:'POST'}).then(r=>r.json())), {original:true});
    assert.equal(commands, 1);
    assert.deepEqual(await parkSessions([actor]), [], 'a parked session is not repeatedly navigated');
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
});
