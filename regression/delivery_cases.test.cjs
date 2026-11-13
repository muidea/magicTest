const { test } = require('node:test');
const assert = require('node:assert/strict');
const { restore } = require('./delivery_cases.cjs');
test('initial denied package cleanup is a missing prerequisite; a wrong package preview still fails its identity assertion', () => {
  class Blocked extends Error {}
  const { initialCleanupPreview } = require('./delivery_cases.cjs');
  const pkg = { id: 7, packageDigest: 'transport' }, preview = { packageId: 7, sourceKind: 'model-package', sourceDigest: 'transport', allowed: true };
  let observations = 0;
  const h = { Blocked, check: (label, good) => assert.ok(good, label), observe: () => observations++ };
  initialCleanupPreview(h, pkg, preview); assert.equal(observations, 0);
  assert.throws(() => initialCleanupPreview(h, pkg, { ...preview, allowed: false, blocker: 'original unfinished request' }), Blocked);
  assert.equal(observations, 1);
  for (const changed of [{ ...preview, packageId: 8 }, { ...preview, sourceDigest: 'artifact' }, { ...preview, allowed: 'false' }])
    assert.throws(() => initialCleanupPreview(h, pkg, changed), assert.AssertionError);
  assert.equal(observations, 1);
});
function fixture() {
  const identity = { account: 'original', namespace: 'panel' }, calls = [];
  const original = { definitionVersion: 1, entities: [{ id: 8, name: 'original', updateTime: 1 }] };
  const r = { app: { id: 7 }, actorIdentity: identity, origin: 'https://panel.test', phase: 'created', commands: [], original, last: original };
  const h = { admin: { identity: structuredClone(identity), origin: r.origin }, Blocked: Error, persist() {},
    async ok(actor, method, route) { calls.push({ method, route }); return { value: structuredClone(original) }; },
    check(label, value) { assert.ok(value, label); } };
  return { h, r, calls };
}
test('delivery restore rejects an unresolved original mutation before any owner command', async () => {
  const f = fixture(); f.r.commands.push({ outcome: 'unknown' });
  await assert.rejects(restore(f.h, f.r), /no replay/); assert.equal(f.calls.length, 0); assert.equal(f.r.phase, 'created');
});
test('delivery restore never overwrites a concurrent draft or changed actor', async () => {
  const f = fixture(); f.r.last = { ...f.r.last, definitionVersion: 2 };
  await assert.rejects(restore(f.h, f.r), /no restoration overwrite/); assert.equal(f.calls.length, 1);
  const g = fixture(); g.h.admin.identity.account = 'other';
  await assert.rejects(restore(g.h, g.r), /actor changed/); assert.equal(g.calls.length, 0);
});
test('delivery no-op restoration proves original semantics without deleting published facts', async () => {
  const f = fixture(); const result = await restore(f.h, f.r);
  assert.equal(f.r.phase, 'deleted'); assert.match(result.proof, /original published fixture retained/);
  assert.ok(f.calls.every(c => c.method === 'GET'));
});
function previewFixture() {
  const {cleanupPreviewRequest}=require('./delivery_cases.cjs');
  const identity={namespace:'panel',account:'original'},origin='https://panel.test';
  const before={id:7,version:1,status:'submitted',operationId:0,instanceKey:'original',deploymentId:'deployment',packageId:3,sourceDigest:'digest',planDigest:'plan',requestedBy:{accountId:4}};
  delete before.operationId; // Actual public DTO omits an unassigned operation.
  let current=structuredClone(before);const calls=[];
  const r={id:7,phase:'created',commands:[],last:structuredClone(before),creation:{actorIdentity:identity,origin,outcome:'accepted',ownershipConfirmed:true},packageDelete:{outcome:'rejected-and-unchanged'}};
  const h={admin:{identity:structuredClone(identity),origin},Blocked:Error,persist(){},
    async ok(actor,method,route){calls.push({method,route});return {value:structuredClone(current)};},
    async api(actor,method,route,body){calls.push({method,route,body});
      if(method==='GET')return {status:404,data:{error:{code:2},value:null}};
      assert.equal(body.expectedVersion,current.version);
      if(route.endsWith('/cancel')){current={...current,version:2,status:'cancelled'};return {status:200,data:{value:structuredClone(current)}};}
      assert.ok(route.endsWith('/cleanup'));return {status:200,data:{value:structuredClone(current)}};},
    good(r){return r.status===200&&!r.data.error;},async directory(){return [];},check(label,value){assert.ok(value,label);}};
  return {h,r,calls,cleanup:()=>cleanupPreviewRequest(h,r),setCurrent(v){current=v;}};
}
test('preview cleanup uses original request cancellation and cleanup with successive owner revisions and independent absence',async()=>{
  const f=previewFixture();await f.cleanup();assert.equal(f.r.phase,'deleted');
  const writes=f.calls.filter(v=>v.method==='POST');assert.equal(writes.length,2);
  assert.ok(writes[0].route.endsWith('/7/cancel'));assert.equal(writes[0].body.expectedVersion,1);
  assert.ok(writes[1].route.endsWith('/7/cleanup'));assert.equal(writes[1].body.expectedVersion,2);
  assert.ok(f.r.commands.every(c=>c.outcome==='confirmed'));
});
test('unknown package deletion/request command and changed original actor block preview cleanup before any I/O',async()=>{
  for(const alter of [f=>f.r.packageDelete.outcome='unknown',f=>f.r.commands.push({outcome:'unknown'}),f=>f.h.admin.identity.account='other',f=>f.r.creation.ownershipConfirmed=false]){
    const f=previewFixture();alter(f);await assert.rejects(f.cleanup(),/unresolved; no replay/);assert.equal(f.calls.length,0);assert.equal(f.r.phase,'created');
  }
});
test('preview cleanup rejects concurrent original request state without issuing a cancellation',async()=>{
  const f=previewFixture();f.setCurrent({...f.r.last,version:2,status:'approved'});
  await assert.rejects(f.cleanup(),/changed concurrently/);assert.equal(f.calls.length,1);assert.equal(f.r.commands.length,0);
});
test('lost preview cancellation response remains journaled unknown and cannot be replaced or replayed',async()=>{
  const f=previewFixture();let writes=0;f.h.api=async()=>{writes++;throw Error('lost original response');};
  await assert.rejects(f.cleanup(),/lost original response/);assert.equal(f.r.commands[0].outcome,'unknown');
  await assert.rejects(f.cleanup(),/no replay/);assert.equal(writes,1);assert.equal(f.r.phase,'created');
});
test('preview cleanup cannot treat authentication failure or a partial directory as original request absence',async()=>{
  for(const mode of ['unauthenticated','directory']){
    const f=previewFixture(),api=f.h.api;f.h.api=async(...args)=>args[1]==='GET'&&mode==='unauthenticated'?{status:401,data:{error:{code:11}}}:api(...args);
    if(mode==='directory')f.h.directory=async()=>{throw Error('directory incomplete');};
    await assert.rejects(f.cleanup(),/independently absent|directory incomplete/);assert.equal(f.r.phase,'created');assert.equal(f.r.commands.at(-1).outcome,'unknown');
  }
});
function refusalFixture() {
  const f=previewFixture(),route='/panel/application/model-packages/3',bytes=Buffer.from('original zip'),hash='sha256:'+require('node:crypto').createHash('sha256').update(bytes).digest('hex');
  f.r.kind='package-preview-request';f.r.creation.intended={packageId:3,expectedDigest:'artifact'};
  const error={code:21,message:'application package has an unfinished deployment request; terminate it before cleanup'};
  const response={status:409,data:{error,value:null}};f.r.packageDelete={route,outcome:'unknown',response};
  const event=(method,route,response)=>({kind:'request',method,route,actor:structuredClone(f.h.admin.identity),origin:f.h.admin.origin,response});
  const preview=allowed=>event('GET',route+'/cleanup-preview',{status:200,data:{value:{packageId:3,sourceDigest:'normalized',allowed,...(!allowed?{blocker:error.message}:{})}}});
  const download=()=>({...event('GET',route+'/content',{status:200,byteLength:bytes.length,digest:hash}),representation:'package-download'});
  const evidence={caseId:'F031-002',status:'failed',trace:[preview(true),download(),preview(false),event('DELETE',route,response),download()]};
  const dependencies={async loadFixture(){return {package:{id:3,artifactDigest:'artifact',packageDigest:'normalized'}};},async readContent(){return {status:200,data:{bytes}};}};
  return {...f,evidence,dependencies,resolve:()=>require('./delivery_cases.cjs').reconcilePreviewRefusal(f.h,f.r,evidence,'sha256:'+'a'.repeat(64),dependencies)};
}
test('exact HTTP409 owner refusal is accepted, while auth, wrong-stage and transport failures cannot impersonate it',()=>{
  const {previewRefusal}=require('./delivery_cases.cjs'),f=refusalFixture();
  assert.equal(previewRefusal(f.r.packageDelete.response),true);
  for(const response of [{status:401,data:{error:{code:11}}},{status:409,data:{error:{code:19,message:'stale'}}},{status:409,data:{error:{code:21,message:'other phase'}}},{status:503,data:{error:{code:15}}}])assert.equal(previewRefusal(response),false);
});
test('original HTTP409 disposition reads exact historical/current package and request, then cleans original without a second package DELETE',async()=>{
  const f=refusalFixture();await f.resolve();assert.equal(f.r.packageDelete.outcome,'rejected-and-unchanged');
  assert.equal(f.r.packageDelete.disposition.requestId,7);assert.equal(f.calls.some(c=>c.method!=='GET'),false);
  await f.cleanup();assert.equal(f.r.phase,'deleted');assert.equal(f.calls.some(c=>c.method==='DELETE'),false);
});
test('original package refusal disposition rejects changed actor, incomplete history, changed bytes and concurrent request without mutation',async()=>{
  for(const mode of ['actor','missing-delete','before-only','different-hash','current-bytes','request','wrong-package']){
    const f=refusalFixture();
    if(mode==='actor')f.h.admin.identity.account='other';
    if(mode==='missing-delete')f.evidence.trace=f.evidence.trace.filter(e=>e.method!=='DELETE');
    if(mode==='before-only')f.evidence.trace.pop();
    if(mode==='different-hash')f.evidence.trace.at(-1).response.digest='sha256:'+'b'.repeat(64);
    if(mode==='current-bytes')f.dependencies.readContent=async()=>({status:200,data:{bytes:Buffer.from('changed zip')}});
    if(mode==='request')f.setCurrent({...f.r.last,version:2});
    if(mode==='wrong-package')f.r.creation.intended.packageId=4;
    await assert.rejects(f.resolve());assert.equal(f.r.packageDelete.outcome,'unknown');assert.equal(f.calls.some(c=>c.method!=='GET'),false);
  }
});
