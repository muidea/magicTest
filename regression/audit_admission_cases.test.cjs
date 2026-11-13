const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { topology, hold, mutate, handlers } = require('./audit_admission_cases.cjs');
test('audit admission service uses the formal display metadata and external operation contract before target lock setup', () => {
  const { serviceInput } = require('./audit_admission_cases.cjs');
  const value=serviceInput('original','123abc');
  assert.ok(value.showName.trim());assert.equal(value.catalog,'regression');
  assert.equal(value.name,value.key);assert.equal(value.providerType,'external');
  for(const key of ['providerKind','type','version','tags'])assert.equal(Object.hasOwn(value,key),false);
  const options=JSON.parse(value.options);assert.equal(options.debug,undefined);
  assert.equal(options.contract.operations[0].upstreamPath,'/probe');
  assert.equal(options.contract.operations[0].method,'GET');
});

function topologyFixture(change = c => c) {
  const config = { platformRoot:'/tmp/platform-executor-unit/host/platform', dockerDataRoot:'/tmp/platform-executor-unit/host/docker-data', daemonId:'isolated-original', containerId:'a'.repeat(64) };
  const info = { ID:config.daemonId, DockerRootDir:config.dockerDataRoot, Driver:'overlay2' };
  const c = change({ Name:'/magicPanel',Id:'b'.repeat(64),Image:'sha256:'+'c'.repeat(64),State:{Running:true,Restarting:false,StartedAt:'2026-11-01T00:00:00Z'},RestartCount:0,Config:{User:'',Env:[]},Mounts:[{Type:'bind',RW:true,Source:config.platformRoot+'/services/data/panel',Destination:'/var/app/data'}] });
  const calls = [];
  const run = (binary,args) => { calls.push([binary,args]); return JSON.stringify(args[0]==='info'?info:[c]); };
  return {config,info,c,calls,run};
}
function inspect(f) {
  const original=os.hostname;os.hostname=()=>f.config.containerId.slice(0,12);
  try{return topology(f.config,f.run);}finally{os.hostname=original;}
}
test('original nested daemon, running Panel identity and most specific persistent bind are required without invoking Docker', () => {
  const f=topologyFixture(), b=inspect(f);
  assert.equal(b.lockRoot,f.config.platformRoot+'/services/data/panel/deployment-runtime/.operation-audit');assert.equal(b.uid,0);assert.equal(f.calls.length,2);
  assert.ok(handlers['F057-005'].requiresOnlyDeliveryFixture);
  const specific=topologyFixture(c=>{c.Config.User='1000:1001';c.Mounts.push({Type:'bind',RW:true,Source:f.config.platformRoot+'/runtime',Destination:'/var/app/data/deployment-runtime'});return c;});
  assert.equal(inspect(specific).uid,1000);assert.equal(inspect(specific).lockRoot,f.config.platformRoot+'/runtime/.operation-audit');
  for(const change of [c=>({...c,RestartCount:undefined}),c=>({...c,Mounts:[...c.Mounts,...c.Mounts]}),c=>({...c,Id:'short'}),c=>({...c,Image:'tag'}),c=>({...c,State:{...c.State,Running:false}}),c=>({...c,State:{...c.State,Restarting:true}}),c=>({...c,Config:{User:'named'}}),c=>({...c,Config:{Env:['MAGIC_DEPLOYMENT_EXECUTOR_RUNTIME_ROOT=/tmp/../owner']}}),c=>({...c,Mounts:c.Mounts.map(m=>({...m,RW:false}))}),c=>({...c,Mounts:c.Mounts.map(m=>({...m,Source:'/foreign/data'}))}),c=>({...c,Mounts:c.Mounts.map(m=>({...m,Type:'volume'}))})])assert.throws(()=>inspect(topologyFixture(change)));
  const wrong=topologyFixture();wrong.info.ID='another';assert.throws(()=>inspect(wrong),/Dedicated nested daemon/);
});
function localRoot(t) {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'audit-admission-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const lockRoot=path.join(root,'.operation-audit');fs.mkdirSync(lockRoot,{mode:0o700});const file=path.join(lockRoot,'admission.lock');fs.writeFileSync(file,'original bytes',{mode:0o600});
  return {lockRoot,uid:process.getuid(),file};
}
test('real local read-only helper holds original inode, invokes callback once and releases exactly its own lock', async t => {
  const b=localRoot(t),before=fs.statSync(b.file);let count=0,checkHeld;
  const proof=await hold({Blocked:Error},b,async (ready,held)=>{count++;checkHeld=held;held();assert.equal(ready.lock.inode,before.ino);return 'independent-result';});
  assert.equal(count,1);assert.equal(proof.value,'independent-result');assert.deepEqual(proof.released,{...proof.ready,kind:'released'});
  assert.equal(fs.statSync(b.file).ino,before.ino);assert.equal(fs.readFileSync(b.file,'utf8'),'original bytes');assert.throws(checkHeld,/ended before dispatch/);
});
test('callback failure still releases own original holder and cannot become successful business proof', async t => {
  const b=localRoot(t);await assert.rejects(hold({Blocked:Error},b,async()=>{throw Error('original command unknown');}),/original command unknown/);
  const next=await hold({Blocked:Error},b,async()=>true);assert.equal(next.value,true);assert.equal(fs.readFileSync(b.file,'utf8'),'original bytes');
});
function fakeStart(mode) {
  return (binary,args)=>{
    const c=new EventEmitter();c.stdout=new PassThrough();c.stderr=new PassThrough();c.stdin=new PassThrough();c.exitCode=null;
    let closed=false;const close=code=>{if(closed)return;closed=true;c.exitCode=code;c.stdout.end();c.emit('close',code,null);};c.kill=()=>{setImmediate(()=>close(2));};
    const correlation=args.at(-1),ready={kind:'ready',correlation,directory:{device:1,inode:2,uid:process.getuid(),mode:0o700},lock:{device:1,inode:3,uid:process.getuid(),mode:0o600}};
    const emit=v=>c.stdout.write(JSON.stringify(v)+'\n');
    c.stdin.on('data',()=>{emit({...ready,kind:'released',...(mode==='changed-release'?{lock:{...ready.lock,inode:4}}:{})});close(0);});
    setImmediate(()=>{
      if(mode==='early-exit')return close(2);
      if(mode==='wrong-correlation')return emit({...ready,correlation:'foreign'});
      if(mode==='wrong-uid')return emit({...ready,lock:{...ready.lock,uid:process.getuid()+1}});
      if(mode==='wrong-mode')return emit({...ready,lock:{...ready.lock,mode:0o644}});
      if(mode==='invalid-inode')return emit({...ready,lock:{...ready.lock,inode:0}});
      if(mode==='released-first')return emit({...ready,kind:'released'});
      emit(ready);if(mode==='duplicate-ready')emit(ready);
      if(mode==='ready-then-exit')close(2);
    });return c;
  };
}
test('mismatched, reordered or duplicate helper proofs never dispatch a callback or claim a successful release', async t => {
  const b=localRoot(t);
  for(const mode of ['early-exit','wrong-correlation','wrong-uid','wrong-mode','invalid-inode','released-first','duplicate-ready','ready-then-exit']){
    let dispatched=0;await assert.rejects(hold({Blocked:Error},b,async()=>{dispatched++;},fakeStart(mode)));assert.equal(dispatched,0,mode);
  }
  await assert.rejects(hold({Blocked:Error},b,async()=>true,fakeStart('changed-release')),/protocol|unconfirmed/);
});
function fixture(mode,refused=true) {
  const actor={origin:'https://unit.invalid',identity:{namespace:'panel',account:'original'}},original={id:7,key:'owned',description:'original',updateTime:100,other:{frozen:true}};
  let value=structuredClone(original),writes=0,reads=0;const saves=[],rows=[];
  const r={kind:'service',id:7,phase:'created',collection:'/panel/hub/services/',creation:{ownershipConfirmed:true,actorIdentity:structuredClone(actor.identity),origin:actor.origin,intended:{key:'owned'}}};
  const h={admin:actor,Blocked:Error,good:x=>x.status===200&&!x.data.error,state:{resources:[r]},persist(){saves.push(structuredClone(r));},check(label,c){assert.ok(c,label);},
    async ok(){reads++;return {value:structuredClone(value)};},
    async directory(){return structuredClone(rows);},
    async api(a,method,route,body){writes++;assert.equal(saves.at(-1).pendingServiceCommands.at(-1).confirmed,false);assert.equal(body.expectedServiceVersion,100);
      if(mode==='lost')throw Error('original transport unknown');
      if(refused){if(mode==='business-drift')value.description='drift';if(mode==='extra-audit')rows.push({eventId:'a'.repeat(32)});return {status:200,data:{value:null,error:{code:1,message:mode==='wrong-refusal'?'unrelated conflict':'操作日志正在处理，请稍后重试'}}};}
      value={...value,description:body.description,updateTime:101};rows.push({eventId:'a'.repeat(32),outcome:'succeeded',actorSubject:'account:7',account:'account:7',actorNamespace:'panel',targetNamespace:'panel',namespace:'panel',operationType:'更新服务',detailMessage:'服务ID:7；标识:owned',resourceType:'/modules/kernel/panel',address:'192.0.2.1',operationTime:Date.now(),...(mode==='wrong-audit'?{resourceType:'panel'}:{})});
      if(mode==='owner-drift')value.other.frozen=false;
      if(mode==='changed-actor')actor.identity.account='foreign';
      return {status:200,data:{error:null,value:structuredClone(value)}};
    }};
  return {h,r,rows,saves,original,get writes(){return writes;},get reads(){return reads;}};
}
test('exact admission refusal proves full original business and audit baseline preserved with persisted intent', async () => {
  const f=fixture();let held=0;const c=await mutate(f.h,f.r,'account:7','refused-new',true,()=>held++);
  assert.equal(held,1);assert.equal(f.writes,1);assert.equal(c.confirmed,true);assert.deepEqual(c.after,f.original);assert.equal(c.beforeEventIds.length,0);
});
test('unrelated refusal, business drift and new audit events leave command unresolved without replay', async () => {
  for(const mode of ['wrong-refusal','business-drift','extra-audit','lost']){
    const f=fixture(mode);await assert.rejects(mutate(f.h,f.r,'account:7','refused-new',true,()=>{}));assert.equal(f.r.pendingServiceCommands[0].confirmed,false);
    await assert.rejects(mutate(f.h,f.r,'account:7','different-body',true,()=>{}),/unresolved/);assert.equal(f.writes,1);
  }
});
test('ended holder after independent baseline, missing holder and changed original actor block before dispatch', async () => {
  const f=fixture();await assert.rejects(mutate(f.h,f.r,'account:7','new',true,()=>{throw Error('holder ended');}),/holder ended/);assert.equal(f.reads,1);assert.equal(f.writes,0);assert.equal(f.r.pendingServiceCommands,undefined);
  await assert.rejects(mutate(f.h,f.r,'account:7','new',true),/holder proof/);assert.equal(f.writes,0);
  f.h.admin.identity.account='foreign';await assert.rejects(mutate(f.h,f.r,'account:7','new',false),/unresolved/);assert.equal(f.writes,0);
});
test('new post-release command uses original conditional version and exact independent durable audit owner contract', async () => {
  const f=fixture(undefined,false),c=await mutate(f.h,f.r,'account:7','accepted-new',false);
  assert.equal(c.confirmed,true);assert.equal(c.body.expectedServiceVersion,100);assert.equal(c.after.updateTime,101);assert.equal(c.auditRows.length,1);assert.equal(f.writes,1);
});
test('wrong durable audit contract, unrelated full-owner drift or changed actor cannot confirm a committed result', async () => {
  for(const mode of ['wrong-audit','owner-drift','changed-actor']){
    const f=fixture(mode,false);await assert.rejects(mutate(f.h,f.r,'account:7','accepted-new',false));assert.equal(f.r.pendingServiceCommands[0].confirmed,false);assert.equal(f.writes,1);
  }
});
test('duplicate or missing original audit baseline identity blocks before any business command', async () => {
  for(const rows of [[{eventId:'same'},{eventId:'same'}],[{}]]){
    const f=fixture();f.rows.push(...rows);await assert.rejects(mutate(f.h,f.r,'account:7','new',true,()=>{}),/baseline/);assert.equal(f.writes,0);assert.equal(f.r.pendingServiceCommands,undefined);
  }
});
