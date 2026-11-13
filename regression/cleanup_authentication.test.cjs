const { test } = require('node:test'), assert = require('node:assert/strict');
const { renewCleanupOwners } = require('./cleanup_authentication.cjs');
function fixture() {
  const actor = { identity: { account: 'original', namespace: 'a' }, origin: 'https://a.example', password: 'original-private-password' };
  const r = { kind: 'ordinary-file', actorName: 'user', actorIdentity: structuredClone(actor.identity), origin: actor.origin, deletion: { outcome: 'acknowledged', response: { id: 7 } } }, events = [], logins = [];
  const valid = a => ({ status: 200, data: { error: null, value: { homeNamespace: a.identity.namespace, account: { account: a.identity.account } } } });
  const h = { user: actor, Blocked: Error, observe: e => events.push(e), good: r => r.status === 200 && r.data?.error == null,
    login: async (account, password, namespace) => { logins.push({ account, password, namespace }); return structuredClone(actor); } };
  return { actor, r, h, events, logins, valid };
}
test('cleanup renews only the original expired actor session and preserves acknowledged or unknown business journals', async () => {
  for (const outcome of ['acknowledged', 'unknown']) {
    const f = fixture(); f.r.deletion.outcome = outcome; const before = structuredClone(f.r); let reads = 0;
    await renewCleanupOwners(f.h, f.r, async (a, m, route) => { assert.equal(m, 'GET'); assert.equal(route, '/api/v1/web/session/'); return reads++ === 0 ? { status: 401, data: {} } : f.valid(a); });
    assert.equal(reads, 2); assert.equal(f.logins.length, 1); assert.deepEqual(f.logins[0], { account: f.actor.identity.account, password: f.actor.password, namespace: 'a' }); assert.deepEqual(f.r, before); assert.doesNotMatch(JSON.stringify(f.events), /original-private-password/);
  }
});
test('cleanup never reauthenticates generic dependency failures, concealed tenants or permission rejection', async () => {
  for (const response of [{ status: 503, data: {} }, { status: 404, data: {} }, { status: 403, data: { error: { code: 12 } } }]) {
    const f = fixture(); await assert.rejects(renewCleanupOwners(f.h, f.r, async () => response), /session unavailable/); assert.equal(f.logins.length, 0);
  }
});
test('cleanup rejects altered original actor/origin, wrong returned subject and unresolved fresh login without retry loops', async () => {
  for (const mode of ['actor', 'origin', 'wrong-session', 'fresh-failure', 'wrong-login']) {
    const f = fixture();
    if (mode === 'actor') f.r.actorIdentity.account = 'other';
    if (mode === 'origin') f.r.origin = 'https://foreign.example';
    if (mode === 'wrong-login') f.h.login = async () => { f.logins.push({}); return { ...f.actor, identity: { ...f.actor.identity, account: 'other' } }; };
    await assert.rejects(renewCleanupOwners(f.h, f.r, async () => mode === 'wrong-session' ? { status: 200, data: { error: null, value: { homeNamespace: 'a', account: { account: 'other' } } } } : { status: 401, data: {} }));
    assert.ok(f.logins.length <= 1);
  }
});
test('feedback cleanup checks both exact creator and manager sessions before existing owner disposition', async () => {
  const f = fixture(); f.h.tenantAdmin = { ...structuredClone(f.actor), identity: { account: 'manager', namespace: 'a' } };
  const spec = name => ({ actorName: name, identity: structuredClone(f.h[name].identity), origin: f.h[name].origin });
  const r = { kind: 'feedback-ticket', creator: spec('user'), manager: spec('tenantAdmin') }, seen = [];
  await renewCleanupOwners(f.h, r, async a => { seen.push(a.identity.account); return f.valid(a); });
  assert.deepEqual(seen, ['original', 'manager']); assert.equal(f.logins.length, 0);
});
test('CAS client and credential cleanup renews the original tenant manager without issuing any credential command', async () => {
  for (const kind of ['cas-probe-client', 'cas-probe-credential']) {
    const f = fixture(); f.h.tenantAdmin = f.h.user;
    const r = { kind, actor: 'tenantAdmin', actorIdentity: f.r.actorIdentity, origin: f.r.origin, outcome: 'accepted' }; let reads = 0;
    await renewCleanupOwners(f.h, r, async a => reads++ === 0 ? { status: 200, data: { error: { code: 11 } } } : f.valid(a));
    assert.equal(f.logins.length, 1); assert.equal(reads, 2); assert.equal(r.outcome, 'accepted');
  }
});

test('restoring a limited creator uses its original acknowledged form and exact owned account',async()=>{
 const {restoreScopedCreator}=require('./cleanup_authentication.cjs');
 for(const mode of ['original','missing-account','password-changed','wrong-session']){
  const identity={account:'limited',namespace:'one'},origin='https://one.example.invalid',pending=[{actor:'limitedTemplateManager',phase:'created',collection:'/cas/namespaces/one/role-templates/',creation:{actorIdentity:identity,origin}}];
  const form={actor:identity,origin,path:'/oauth/login',phase:'browser-delivered',status:302,bodyBase64:Buffer.from(new URLSearchParams({account:'limited',namespace:'one',password:'original-private'}).toString()).toString('base64')};
  const account={id:7,kind:'account',phase:'created',collection:'/cas/namespaces/one/accounts/',creation:{ownershipConfirmed:true,intended:{account:'limited'}}};let logins=0;
  const h={Blocked:Error,state:{resources:mode==='missing-account'?[]:[account],originalCasForms:[form,...(mode==='password-changed'?[{...form,path:'/oauth/password/change'}]:[])]},observe(){},async login(name,password,ns){logins++;assert.equal(name,'limited');assert.equal(password,'original-private');assert.equal(ns,'one');return {identity,origin};},async ok(){return {value:{account:{id:mode==='wrong-session'?8:7},homeNamespace:'one'}};}};
  if(mode==='original'){await restoreScopedCreator(h,pending);assert.equal(logins,1);assert.deepEqual(h.limitedTemplateManager.identity,identity);}
  else {await assert.rejects(restoreScopedCreator(h,pending));assert.equal(h.limitedTemplateManager,undefined);if(mode!=='wrong-session')assert.equal(logins,0);}
 }
});
