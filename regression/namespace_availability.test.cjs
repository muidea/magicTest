const { test } = require('node:test');
const assert = require('node:assert/strict');
const { change, restore } = require('./namespace_availability.cjs');
const identity = { account: 'admin', namespace: 'panel' }, origin = 'https://panel.local.vpc';
const snapshot = { id: 7, name: 'original', status: 2, description: 'original', scope: null, startTime: 10, expireTime: 99, updateTime: 12 };
function setup() {
 const r={kind:'namespace',id:7,name:'original',collection:'/panel/namespace-onboardings/',creation:{actorIdentity:identity,origin}};
 const h={admin:{identity,origin},Blocked:Error,persist(){},good:r=>r.status===200&&!r.data?.error,check:(label,ok)=>assert.ok(ok,label),ok:async()=>({value:snapshot})};
 return {r,h};
}
test('availability response loss persists original intent and prevents restore or command replay',async()=>{
 const {r,h}=setup();let writes=0,persisted;
 h.persist=()=>{persisted=structuredClone(r)};
 h.api=async()=>{writes++;assert.equal(persisted.availability.commands.at(-1).outcome,'unknown');throw Error('response lost');};
 await assert.rejects(change(h,r,snapshot,{...snapshot,status:1}),/response lost/);
 await assert.rejects(change(h,r,snapshot,{...snapshot,status:1}),/without replay/);
 await assert.rejects(restore(h,r),/never repeat/);assert.equal(writes,1);
});
test('availability restore refuses changed actor or concurrent revision without commands',async()=>{
 for(const mode of ['foreign-actor','foreign-revision']){
  const {r,h}=setup();r.availability={original:snapshot,last:{...snapshot,status:1,updateTime:13},commands:[{outcome:'confirmed'}]};
  if(mode==='foreign-actor')h.admin={identity:{...identity,account:'peer'},origin};
  let writes=0;h.api=async()=>{writes++};await assert.rejects(restore(h,r));assert.equal(writes,0);
 }
});
test('availability acknowledgement requires full exact owner read and completed original receipt',async()=>{
 for(const mode of ['exact','wrong-receipt','wrong-read']){
  const {r,h}=setup(),saved={...snapshot,status:1,updateTime:13};
  h.api=async()=>({status:200,data:{error:null,value:saved,operation:{requestId:'a'.repeat(32),namespaceId:mode==='wrong-receipt'?8:7,name:'original',phase:'completed',version:7,namespace:saved}}});
  h.ok=async()=>({value:mode==='wrong-read'?{...saved,status:2}:saved});
  if(mode==='exact'){await change(h,r,snapshot,saved);assert.equal(r.availability.commands[0].outcome,'confirmed');assert.deepEqual(r.availability.last,saved)}
  else{await assert.rejects(change(h,r,snapshot,saved));assert.equal(r.availability.commands[0].outcome,'unknown')}
 }
});

test('ingress recovery uses only terminal exact CAS receipt and never resends an unknown command',async()=>{
 const {reconcileIngress}=require('./namespace_availability.cjs');
 for(const mode of ['exact','foreign-receipt','response-lost']){
  const {r,h}=setup();let writes=0;
  h.ok=async(a,m,url)=>({value:url.includes('/access-updates/')?{namespaceId:mode==='foreign-receipt'?8:7,name:'original',requestId:'a'.repeat(32),phase:'completed',namespace:snapshot}:snapshot});
  h.api=async(a,m,url,body)=>{writes++;assert.equal(m,'PUT');assert.equal(url,'/panel/namespace-onboardings/7/ingress');assert.deepEqual(body,{});assert.equal(r.ingressRecovery.outcome,'unknown');if(mode==='response-lost')throw Error('response lost');return {status:200,data:{error:null,value:snapshot}}};
  if(mode==='exact'){await reconcileIngress(h,r);await reconcileIngress(h,r);assert.equal(writes,1);assert.equal(r.ingressRecovery.outcome,'confirmed')}
  else{await assert.rejects(reconcileIngress(h,r));await assert.rejects(reconcileIngress(h,r));assert.equal(writes,mode==='response-lost'?1:0)}
 }
});
