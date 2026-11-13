const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const http = require('node:http');
const { referenceTransfer } = require('./owner_transport.cjs');
const { create, command, cleanup, bytes, view, consumeBody, downloadRoute, handlers } = require('./bound_reference_cases.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
function fixture(mode) {
  const actor = { origin: 'https://unit.invalid', identity: { namespace: 'panel', account: 'original' } }, refs = new Map(), persisted = [], calls = [];
  let current;
  const good = x => x.status === 200 && x.data?.error == null;
  const h = { admin: actor, Blocked: Error, state: { resources: [] }, observe() {}, good,
    persist() { persisted.push(structuredClone(h.state)); }, check(label, condition) { assert.ok(condition, label); },
    async api(a, method, route, body) {
      const r = current || h.state.resources.find(v => v.fileRef && route.includes(v.fileRef.replace('bound_', '')));
      assert.equal(persisted.at(-1).resources.find(v => v.id === r.id).commands.at(-1).confirmed, false);
      const action = r.commands.at(-1).action; calls.push(action);
      if (mode === 'lost-'+action) throw Error('unknown original command');
      const error = action === 'foreign-bind' ? 'upload reference cannot be consumed' : action === 'foreign-delete' ? 'bound file cleanup identity is inconsistent' : action === 'old-bind' ? 'upload reference not found' : null;
      if (error) return { status: 200, data: { value: null, error: { code: 4, message: mode === 'wrong-refusal' ? 'unrelated' : error } } };
      if (action === 'bind') refs.get(r.fileRef).bound = true;
      if (action === 'release') refs.get(r.fileRef).deleted = true;
      const value = { ...view(r), ...(mode === 'wrong-ack' ? { digest: 'foreign' } : {}) };
      return { status: 200, data: { error: null, value, ...(action === 'release' ? { deletionConfirmed: mode !== 'false-delete-proof' } : {}) } };
    } };
  async function transfer(a, method, route, file) {
    assert.equal(a, actor);
    if (method === 'POST') {
      const r = h.state.resources.at(-1); calls.push('upload');
      assert.equal(persisted.at(-1).resources.at(-1).commands[0].confirmed, false);
      if (mode === 'lost-upload') throw Error('unknown upload');
      const ref = crypto.randomBytes(32).toString('base64url'); refs.set('bound_'+ref, { bytes: Buffer.from(file.bytes), bound: false, deleted: false });
      return { status: 200, data: { error: null, value: { uploadRef: ref, name: file.name, size: file.bytes.length, digest: crypto.createHash('sha256').update(file.bytes).digest('hex').replace(/^/,'sha256:'), purpose: 'regression-reference-proof', expiresAt: Date.now()+60000,
        ...(mode === 'wrong-upload' ? { size: 1 } : {}) } } };
    }
    const r = h.state.resources.find(v => v.fileRef && route.includes(v.fileRef)), state = refs.get(r.fileRef);
    if (mode === 'read-loss') throw Error('read result unavailable');
    if (!state.bound || state.deleted && mode !== 'retained-after-delete' || new URL(route, a.origin).searchParams.get('consumer') !== r.consumer)
      return { status: 404, data: { text: mode === 'wrong-404' ? 'SPA\n' : 'bound file not found\n' } };
    return { status: 200, data: { bytes: mode === 'corrupt' ? Buffer.from('wrong') : Buffer.from(state.bytes) } };
  }
  return { h, transfer, refs, calls, persisted, select(r) { current = r; } };
}
async function bound(f) { const r = await create(f.h,'account:7',f.transfer); f.select(r); await command(f.h,r,'bind',f.transfer); return r; }
test('single consumer bound reference rejects foreign consumption/release, retains bytes, and requires complete original release proof', async () => {
  const f = fixture(), r = await bound(f); await command(f.h,r,'foreign-bind',f.transfer); await command(f.h,r,'foreign-delete',f.transfer);
  await command(f.h,r,'release',f.transfer); await command(f.h,r,'old-bind',f.transfer); await cleanup(f.h,r,f.transfer);
  assert.equal(r.phase,'deleted'); assert.deepEqual(f.calls,['upload','bind','foreign-bind','foreign-delete','release','old-bind']); assert.ok(r.commands.every(c=>c.confirmed));
  assert.equal(consumeBody(r).consumer,r.consumer); assert.ok(handlers['F049-004'].requiresOnlyDeliveryFixture);
});
test('one actual reference and a rejected foreign consumer are never counted as two live references', async () => {
  const f=fixture(), r=await bound(f), peer=await bound(f); f.select(r); await command(f.h,r,'foreign-bind',f.transfer); await command(f.h,r,'release',f.transfer);
  assert.notEqual(r.fileRef,peer.fileRef); assert.equal(f.refs.get(peer.fileRef).deleted,false); await bytes(f.h,peer,f.transfer);
  assert.equal(f.refs.size,2,'two independently uploaded owner references, no shared path claim');
});
test('lost original upload remains unresolved without a guessed reference or cleanup write', async () => {
  const f=fixture('lost-upload'); await assert.rejects(create(f.h,'account:7',f.transfer)); const r=f.h.state.resources[0];
  await assert.rejects(cleanup(f.h,r,f.transfer),/unresolved/); assert.deepEqual(f.calls,['upload']); assert.equal(r.fileRef,undefined); assert.equal(r.phase,'intent');
});
test('unknown bind/foreign-bind/foreign-delete/release/old-bind cannot replay or close exact journal', async () => {
  for (const action of ['bind','foreign-bind','foreign-delete','release','old-bind']) {
    const f=fixture('lost-'+action), r=await create(f.h,'account:7',f.transfer); f.select(r);
    if(action!=='bind') await command(f.h,r,'bind',f.transfer);
    if(action==='old-bind') await command(f.h,r,'release',f.transfer);
    await assert.rejects(command(f.h,r,action,f.transfer)); const count=f.calls.length;
    await assert.rejects(command(f.h,r,action,f.transfer),/unresolved/); await assert.rejects(cleanup(f.h,r,f.transfer),/unresolved/);
    assert.equal(f.calls.length,count); assert.notEqual(r.phase,'deleted');
  }
});
test('false upload/bind/deletion acknowledgements and wrong refusal do not prove a lifecycle transition', async () => {
  const a=fixture('wrong-upload'); await assert.rejects(create(a.h,'account:7',a.transfer)); assert.equal(a.h.state.resources[0].commands[0].confirmed,false);
  for (const mode of ['wrong-ack','false-delete-proof','wrong-refusal','retained-after-delete','wrong-404']) {
    const f=fixture(mode),r=await create(f.h,'account:7',f.transfer); f.select(r);
    if(mode==='wrong-ack') await assert.rejects(command(f.h,r,'bind',f.transfer));
    else {await command(f.h,r,'bind',f.transfer); await assert.rejects(command(f.h,r,mode==='wrong-refusal'?'foreign-bind':'release',f.transfer));}
    assert.equal(r.commands.at(-1).confirmed,false); assert.notEqual(r.phase,'deleted');
  }
});
test('corrupt/failed independent byte read and wrong original actor prevent confirmation without another command', async () => {
  for(const mode of ['corrupt','read-loss']) {const f=fixture(mode),r=await create(f.h,'account:7',f.transfer);f.select(r);await assert.rejects(command(f.h,r,'bind',f.transfer));await assert.rejects(cleanup(f.h,r,f.transfer));assert.deepEqual(f.calls,['upload','bind']);}
  const f=fixture(),r=await bound(f); f.h.admin.identity.account='foreign'; const count=f.calls.length; await assert.rejects(command(f.h,r,'release',f.transfer),/unresolved/);assert.equal(f.calls.length,count);
});
test('known pending upload cannot be guessed bound during cleanup and confirmed action cannot be dispatched twice', async () => {
  const f=fixture(),r=await create(f.h,'account:7',f.transfer);f.select(r);await assert.rejects(cleanup(f.h,r,f.transfer),/lacks/);assert.deepEqual(f.calls,['upload']);
  await command(f.h,r,'bind',f.transfer);await assert.rejects(command(f.h,r,'bind',f.transfer),/duplicate/);assert.deepEqual(f.calls,['upload','bind']);
});
test('immutable cleanup evidence binds reference, original consumer/content, actor and every original command', async () => {
  const f=fixture(),r=await bound(f),original={resources:[{...structuredClone(r),confirmed:false}],trace:[]};
  assert.equal(bindOriginalCleanup({resources:[r]},original)[0],r);
  for(const mutate of [x=>x.fileRef+='A',x=>x.consumer='other',x=>x.foreignConsumer='other',x=>x.subject='account:8',x=>x.namespace='other',x=>x.expectedSize++,x=>x.expectedDigest='other',x=>x.origin+='foreign',x=>x.name='other.bin',x=>x.commands[1].body.consumer='other',x=>x.commands[1].confirmed=false]) {
    const changed=structuredClone(r);mutate(changed);assert.throws(()=>bindOriginalCleanup({resources:[changed]},original),/differs/);
  }
});
test('actual local socket transfers one private multipart upload and exact binary bound download using original cookies without Chromium', async t => {
  const seen=[],payload=Buffer.from('Private bound\0\r\n中文 Δ'),ref='bound_'+'a'.repeat(43),events=[];
  const server=http.createServer(async(req,res)=>{const chunks=[];for await(const chunk of req)chunks.push(chunk);seen.push({url:req.url,method:req.method,headers:req.headers,body:Buffer.concat(chunks)});
    if(req.method==='POST'){res.setHeader('Content-Type','application/json');res.end('{"error":null,"value":{"uploadRef":"opaque"}}');}
    else {res.setHeader('Content-Type','application/octet-stream');res.end(payload);}});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const origin='http://panel.local.vpc:'+server.address().port,actor={origin,identity:{account:'original',namespace:'panel'},context:{cookies:async()=>[{name:'session',value:'unit-original-cookie',domain:'panel.local.vpc',path:'/',httpOnly:true,secure:false,expires:-1,sameSite:'Lax'}]}};
  await referenceTransfer(actor,'POST','/files/self/files/upload-references/?purpose=regression-reference-proof',{name:'proof-'+'a'.repeat(16)+'.bin',bytes:payload},e=>events.push(e));
  const result=await referenceTransfer(actor,'GET','/files/bound-files/'+ref+'/download?namespace=panel&consumer=original',undefined,e=>events.push(e));
  assert.ok(result.data.bytes.equals(payload));assert.equal(seen.length,2);assert.ok(seen[0].body.includes(payload));assert.equal(seen[0].headers.cookie,'session=unit-original-cookie');assert.equal(seen[1].headers.host,new URL(origin).host);
  assert.doesNotMatch(JSON.stringify(events),/unit-original-cookie|Private bound|"bytes"/);
  for(const route of ['//foreign/path','/files/bound-files/'+ref+'/download?namespace=panel&consumer=a&consumer=b','/files/bound-files/'+ref+'/download?namespace=panel','/files/bound-files/'+ref+'/download?namespace=panel&consumer=a&extra=1'])await assert.rejects(referenceTransfer(actor,'GET',route));
  await assert.rejects(referenceTransfer(actor,'POST','/files/self/files/upload-references/?purpose=regression-reference-proof',{name:'proof-'+'a'.repeat(16)+'.bin',bytes:Buffer.alloc(65537)}));assert.equal(seen.length,2);
});
test('binary bound transport never follows a redirect or retries an original upload after lost response', async t => {
  let count=0;const server=http.createServer((req,res)=>{count++; if(req.method==='POST')req.socket.destroy();else{res.writeHead(302,{Location:'/must-not-follow'});res.end();}});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const actor={origin:'http://127.0.0.1:'+server.address().port,identity:{account:'original',namespace:'panel'},context:{cookies:async()=>[]}};
  const result=await referenceTransfer(actor,'GET','/files/bound-files/bound_'+'a'.repeat(43)+'/download?namespace=panel&consumer=a');assert.equal(result.status,302);assert.equal(count,1);
  await assert.rejects(referenceTransfer(actor,'POST','/files/self/files/upload-references/?purpose=regression-reference-proof',{name:'proof-'+'a'.repeat(16)+'.bin',bytes:Buffer.from('finite')}));assert.equal(count,2);
});
