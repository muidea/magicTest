const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createResource, deleteResource } = require('./resource_lifecycle.cjs');
test('business command actual and denied callers survive an unknown write independently of the row creator', () => {
  const { guardFixtureAccountCleanup } = require('./resource_lifecycle.cjs');
  const account = { kind: 'account', collection: '/cas/namespaces/panel/accounts/', creation: { intended: { account: 'ordinary' } } };
  for (const key of ['actingIdentity', 'negativeActor']) {
    const command = { outcome: 'unknown', [key]: { namespace: 'panel', account: 'ordinary' } };
    const row = { kind: 'business-record', phase: 'created', actorIdentity: { namespace: 'panel', account: 'different-creator' }, commands: [command] };
    const h = { Blocked: Error, state: { resources: [account, row] } };
    assert.throws(() => guardFixtureAccountCleanup(h, account), /retain actual caller/);
    command[key].namespace = 'other'; guardFixtureAccountCleanup(h, account);
    command[key].namespace = 'panel'; command.outcome = 'confirmed'; guardFixtureAccountCleanup(h, account);
  }
});
test('pending owned file or feedback protects its original fixture account until formal disposition', () => {
  const { guardFixtureAccountCleanup } = require('./resource_lifecycle.cjs');
  const account = { kind: 'account', collection: '/cas/namespaces/tenant-a/accounts/', creation: { intended: { account: 'member' } } };
  for (const kind of ['ordinary-file', 'feedback-ticket', 'business-record']) {
    const child = { kind, phase: 'created', actorIdentity: { account: 'member', namespace: 'tenant-a' } };
    const h = { Blocked: Error, state: { resources: [account, child] } };
    assert.throws(() => guardFixtureAccountCleanup(h, account), /retain creator/);
    child.actorIdentity.namespace = 'tenant-b'; guardFixtureAccountCleanup(h, account);
    child.actorIdentity.namespace = 'tenant-a'; child.phase = 'deleted'; guardFixtureAccountCleanup(h, account);
  }
});
function fixture(mode) {
  const actor = { identity: { account: 'original', namespace: 'tenant' }, origin: 'https://tenant.invalid' };
  let stored, reads = 0; const commands = [], journal = [];
  const h = { state: { resources: [] }, Blocked: Error,
    check(label, value) { assert.ok(value, label); }, good: r => r.status === 200 && !r.data.error,
    persist() { journal.push(structuredClone(h.state.resources)); },
    async api(actual, method, route, body) {
      assert.equal(actual, actor); commands.push({ method, route });
      if (method === 'POST') {
        assert.equal(journal.at(-1)[0].creation.outcome, 'unknown');
        if (mode === 'reject') return { status: 403, data: { error: { code: 5 } } };
        stored = { ...body, id: 7 };
        if (mode === 'create-lost') throw Error('create response lost');
        return { status: 200, data: { value: mode === 'wrong-identity' ? { ...stored, key: 'unrelated' } : structuredClone(stored) } };
      }
      if (method === 'DELETE') {
        assert.equal(journal.at(-1)[0].deletion.outcome, 'unknown');
        if (mode !== 'delete-unknown') stored = undefined;
        if (mode === 'delete-lost' || mode === 'delete-unknown') throw Error('delete response lost');
        return { status: 200, data: {} };
      }
      if (++reads === 1 && mode === 'first-read-lost') throw Error('first owner read lost');
      if (reads === 1 && mode === 'first-read-unavailable') return { status: 503, data: { error: { code: 1 } } };
      if (mode === 'owner-mismatch') return { status: 200, data: { value: { ...stored, key: 'unrelated' } } };
      return stored ? { status: 200, data: { value: structuredClone(stored) } } : { status: 200, data: { error: { code: 2 }, value: null } };
    },
    async ok(...args) { const r = await h.api(...args); assert.ok(h.good(r)); return r.data; }
  };
  const create = () => createResource(h, actor, 'tenantAdmin', '/services/', { key: 'current-run-key', name: 'current-run-name' }, 'service');
  return { h, actor, commands, journal, create, stored: () => stored };
}
test('successful creation persists exact owner identity before read, and cleanup independently confirms absence', async () => {
  const f = fixture(); await f.create();
  const r = f.h.state.resources[0];
  assert.equal(r.actor, 'tenantAdmin'); assert.equal(r.creation.ownershipConfirmed, true);
  assert.equal(f.journal[2][0].id, 7); assert.equal(f.journal[2][0].creation.ownershipConfirmed, undefined);
  await deleteResource(f.h, f.actor, r);
  assert.equal(f.stored(), undefined);
  assert.deepEqual(f.commands.map(c => c.method), ['POST', 'GET', 'GET', 'DELETE', 'GET']);
});
test('selected owner transport owns the entire lifecycle and a failed write never falls back to browser replay', async () => {
  const f = fixture();
  f.h.ownerApi = f.h.api;
  f.h.api = () => { throw Error('browser transport must not be selected after owner transport'); };
  await f.create();
  await deleteResource(f.h, f.actor, f.h.state.resources[0]);
  assert.deepEqual(f.commands.map(c => c.method), ['POST', 'GET', 'GET', 'DELETE', 'GET']);
  const lost = fixture('create-lost'); lost.h.ownerApi = lost.h.api;
  lost.h.api = () => { throw Error('must not replay'); };
  await assert.rejects(lost.create(), /create response lost/);
  await assert.rejects(lost.create(), /never replay POST/);
  await assert.rejects(deleteResource(lost.h, lost.actor, lost.h.state.resources[0]), /Unconfirmed original creation/);
  assert.equal(lost.commands.length, 1);
  assert.equal(lost.h.state.resources[0].creation.outcome, 'unknown');
});
test('accepted original creation recovers after first read failure and persisted journal reload without replaying POST', async () => {
  for (const mode of ['first-read-lost', 'first-read-unavailable']) {
    const f = fixture(mode);
    await assert.rejects(f.create());
    f.h.state.resources = JSON.parse(JSON.stringify(f.journal.at(-1)));
    const r = f.h.state.resources[0], originalResponse = structuredClone(r.creation.response);
    assert.equal(r.id, 7); assert.equal(r.creation.ownershipConfirmed, undefined);
    await assert.rejects(f.create(), /never replay POST/);
    await deleteResource(f.h, f.actor, r);
    assert.equal(r.creation.ownershipConfirmed, true);
    assert.deepEqual(r.creation.response, originalResponse);
    assert.equal(f.stored(), undefined);
    assert.deepEqual(f.commands, [
      { method: 'POST', route: '/services/' },
      { method: 'GET', route: '/services/7' },
      { method: 'GET', route: '/services/7' },
      { method: 'DELETE', route: '/services/7' },
      { method: 'GET', route: '/services/7' }
    ]);
  }
});
test('an original actor change during recovery owner read blocks DELETE', async () => {
  const f = fixture('first-read-lost'); await assert.rejects(f.create());
  const originalApi = f.h.api;
  f.h.api = async (...args) => {
    const response = await originalApi(...args);
    f.actor.identity.namespace = 'other';
    return response;
  };
  const r = f.h.state.resources[0];
  await assert.rejects(deleteResource(f.h, f.actor, r), /original actor and origin/);
  assert.equal(r.creation.ownershipConfirmed, undefined);
  assert.deepEqual(f.commands.map(c => c.method), ['POST', 'GET', 'GET']);
});
test('recovery rechecks owner identity and actor before admitting a deletion', async () => {
  const f = fixture('owner-mismatch'); await assert.rejects(f.create(), /original created identity/);
  const r = f.h.state.resources[0];
  await assert.rejects(deleteResource(f.h, { ...f.actor, origin: 'https://other.invalid' }, r), /original actor and origin/);
  await assert.rejects(deleteResource(f.h, f.actor, r), /original submitted identity/);
  assert.equal(r.creation.ownershipConfirmed, undefined);
  assert.deepEqual(f.commands.map(c => c.method), ['POST', 'GET', 'GET']);
  assert.ok(f.stored());
});
test('an acknowledged creation independently absent after a failed first read needs no DELETE', async () => {
  const f = fixture('first-read-lost'); await assert.rejects(f.create());
  const originalApi = f.h.api;
  f.h.api = async (actor, method, route) => {
    assert.equal(actor, f.actor); assert.equal(method, 'GET'); assert.equal(route, '/services/7');
    return { status: 404, data: { error: { code: 2 }, value: null } };
  };
  const proof = await deleteResource(f.h, f.actor, f.h.state.resources[0]);
  assert.match(proof.proof, /independently absent/);
  assert.equal(f.commands.filter(c => c.method === 'DELETE').length, 0);
  f.h.api = originalApi;
});
test('recovery does not turn a mismatched saved response ID into deletion authority', async () => {
  const f = fixture('first-read-lost'); await assert.rejects(f.create());
  const r = f.h.state.resources[0]; r.id = 8;
  await assert.rejects(deleteResource(f.h, f.actor, r), /Unconfirmed original creation/);
  assert.deepEqual(f.commands.map(c => c.method), ['POST', 'GET']);
});
test('lost creation, rejection and wrong identity remain open without blind POST or guessed DELETE', async () => {
  for (const mode of ['create-lost', 'reject', 'wrong-identity']) {
    const f = fixture(mode); await assert.rejects(f.create());
    const r = f.h.state.resources[0];
    await assert.rejects(f.create(), /never replay POST/);
    await assert.rejects(deleteResource(f.h, f.actor, r), /Unconfirmed original creation/);
    assert.deepEqual(f.commands.map(c => c.method), ['POST']);
    assert.notEqual(r.phase, 'deleted');
  }
});
test('cleanup rejects changed principal or host before any command', async () => {
  const f = fixture(); await f.create(); const count = f.commands.length;
  for (const changed of [{ ...f.actor, identity: { ...f.actor.identity, namespace: 'other' } }, { ...f.actor, origin: 'https://other.invalid' }]) await assert.rejects(deleteResource(f.h, changed, f.h.state.resources[0]), /original actor and origin/);
  assert.equal(f.commands.length, count);
});
test('lost DELETE response permits exact absence read, and never replays an uncertain deletion', async () => {
  for (const mode of ['delete-lost', 'delete-unknown']) {
    const f = fixture(mode); await f.create(); const r = f.h.state.resources[0];
    await assert.rejects(deleteResource(f.h, f.actor, r), /delete response lost/);
    if (mode === 'delete-lost') await deleteResource(f.h, f.actor, r);
    else await assert.rejects(deleteResource(f.h, f.actor, r), /no command replay/);
    assert.equal(f.commands.filter(c => c.method === 'DELETE').length, 1);
  }
});

test('original creator account remains while any created resource is unresolved', () => {
  const { guardFixtureAccountCleanup } = require('./resource_lifecycle.cjs');
  const account = { kind: 'account', collection: '/cas/namespaces/a/accounts/', creation: { intended: { account: 'delegator' } } };
  const child = { kind: 'role-template', phase: 'created', creation: { actorIdentity: { account: 'delegator', namespace: 'a' } } };
  const h = { state: { resources: [account, child] }, Blocked: Error };
  assert.throws(() => guardFixtureAccountCleanup(h, account), /unresolved created resources/);
  child.phase = 'deleted'; assert.doesNotThrow(() => guardFixtureAccountCleanup(h, account));
});

test('a distinct reviewer account is retained until its original delivery is formally disposed', () => {
  const { guardFixtureAccountCleanup } = require('./resource_lifecycle.cjs');
  const account = { kind: 'account', collection: '/cas/namespaces/panel/accounts/', creation: { intended: { account: 'reviewer' } } };
  const child = { kind: 'deployment-review-request', phase: 'created', commands: [{ outcome: 'confirmed', actorIdentity: { namespace: 'panel', account: 'reviewer' } }] };
  const h = { Blocked: Error, state: { resources: [account, child] } };
  assert.throws(() => guardFixtureAccountCleanup(h, account), /Original reviewer still participates/);
  child.commands[0].actorIdentity.namespace = 'another';
  assert.doesNotThrow(() => guardFixtureAccountCleanup(h, account));
  child.commands[0].actorIdentity.namespace = 'panel'; child.phase = 'deleted';
  assert.doesNotThrow(() => guardFixtureAccountCleanup(h, account));
});

test('a proven in-use refusal permits a later deletion only after the owner proves all bindings gone',async()=>{
 for(const mode of ['unbound','still-bound','generic-error']){
  const actor={identity:{account:'original',namespace:'one'},origin:'https://one.example.invalid'},value={id:7,key:'original',subjectCount:mode==='still-bound'?1:0};
  const refusal={status:200,data:{error:{code:4,message:'role template original is bound by subjects; unbind it before deletion'},value:null}};
  if(mode==='generic-error')refusal.status=503;
  const r={id:7,kind:'role-template',collection:'/cas/namespaces/one/role-templates/',creation:{actorIdentity:actor.identity,origin:actor.origin,outcome:'accepted',intended:{key:'original'},response:{status:200,data:{value}}},deletion:{outcome:'unconfirmed',response:refusal}};
  let deleted=false,writes=0;
  const h={Blocked:Error,persist(){},good:r=>r.status===200 && !r.data.error,check(label,c){assert.ok(c,label);},async directory(){return mode==='still-bound'?[{id:99}]:[];},async api(a,method){if(method==='DELETE'){writes++;deleted=true;return {status:200,data:{value}};}return deleted?{status:200,data:{error:{code:2},value:null}}:{status:200,data:{value}};}};
  if(mode==='unbound'){await deleteResource(h,actor,r);assert.equal(writes,1);assert.deepEqual(r.deletionAttempts[0].original.response,refusal);}
  else {await assert.rejects(deleteResource(h,actor,r));assert.equal(writes,0);}
 }
});
