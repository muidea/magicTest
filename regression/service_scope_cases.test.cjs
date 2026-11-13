const { test } = require('node:test');
const assert = require('node:assert/strict');
const { command } = require('./service_scope_cases.cjs');
const { quotaBoundary, quotaBurst } = require('./service_scope_cases.cjs');
test('quota boundary requires exact admission refusals and independently proves once-only upstream execution', () => {
  const probes = Array.from({length:5},(_,i) => ({marker:String(i),status:i < 2 ? 200 : 429,data:i < 2 ? {marker:String(i)} : {error:{message:'totalizator daily limit exceeded'}}}));
  const upstream = probes.slice(0,2).map(p => ({marker:p.marker,method:'GET',path:'/probe',authorizationPresent:false}));
  const h = {check(label,condition) {assert.ok(condition,label);}};
  quotaBoundary(h,probes,upstream,2,/totalizator daily limit exceeded/);
  for (const mutate of [
    (p,u) => {p[2].status=403; p[2].data.error.message='subscription unavailable';},
    (p,u) => {u.push({...u[0]});},
    (p,u) => {u[1].marker=p[2].marker;},
    (p,u) => {p[1].data.marker='other-request';},
    (p,u) => {p[4].marker=p[3].marker;},
    (p,u) => {u[0].authorizationPresent=true;}
  ]) {
    const p=structuredClone(probes),u=structuredClone(upstream);mutate(p,u);
    assert.throws(() => quotaBoundary(h,p,u,2,/totalizator daily limit exceeded/));
  }
});
test('QPS observation crossing a real second is blocked after one burst without resetting or replaying',async () => {
  let bursts=0,waits=0; const observed=[];
  const actor={identity:{namespace:'a',account:'member'},page:{async evaluate(fn,args) {
    if(!args){waits++;return;}
    bursts++;
    return args.markers.map(marker=>({marker,status:200,data:{marker},startedAt:1999,completedAt:2001}));
  }}};
  const h={Blocked:Error,observe:e=>observed.push(e)},f={service:{id:7,key:'original'},up:{requests:[]}},c={apiKey:'test-only',resource:{parentSubscriptionId:9}};
  await assert.rejects(quotaBurst(h,actor,f,c,5,true),/crossed a real UTC second/);
  assert.equal(bursts,1);assert.equal(waits,1);
  assert.equal(observed[0].serviceId,7);assert.equal(observed[0].subscriptionId,9);
  assert.equal(new Set(observed[0].probes.map(p=>p.marker)).size,5);
});
test('service commands persist original intent and never replay after response loss or failed independent confirmation', async () => {
  for (const mode of ['accepted', 'response-loss', 'owner-read-failed']) {
    const resource = {}, requests = [], h = { Blocked: Error, tenantAdmin: { identity: { account: 'owner', namespace: 'a' } }, persist() {},
      async api(actor, method, route, body) {
        assert.equal(resource.pendingServiceCommands.length, 1);
        assert.equal(resource.pendingServiceCommands[0].confirmed, false);
        assert.deepEqual(resource.pendingServiceCommands[0].body, body);
        requests.push({ method, route, body });
        if (mode === 'response-loss') throw Error('original response lost');
        return { status: 200, data: { value: { id: 7 } } };
      } };
    const execute = () => command(h, resource, 'PUT', '/services/7', { expectedServiceVersion: 12, options: 'original-bytes' }, async response => {
      assert.equal(response.data.value.id, 7);
      if (mode === 'owner-read-failed') throw Error('independent owner read failed');
    });
    if (mode === 'accepted') { await execute(); assert.equal(resource.pendingServiceCommands[0].confirmed, true); }
    else {
      await assert.rejects(execute());
      await assert.rejects(execute(), /unresolved/);
      assert.equal(resource.pendingServiceCommands[0].confirmed, false);
    }
    assert.equal(requests.length, 1);
  }
});
const { copiedProbe } = require('./service_scope_cases.cjs');
test('copied guide parser rejects foreign hosts, substituted resources and shell fragments', () => {
  const example = "curl --request GET 'https://a.example/api/v1/gateway/services/target/probe?marker=%3Cmarker%3E' \\\n  --header 'Authorization: ApiKey <API_KEY>'";
  assert.equal(copiedProbe(example, 'https://a.example', 'target').searchParams.get('marker'), '<marker>');
  for (const invalid of [example.replace('a.example', 'b.example'), example.replace('/target/', '/foreign/'), example + '; env', example.replace('GET', 'DELETE'), example.replace('%3Cmarker%3E', 'fixed')]) assert.throws(() => copiedProbe(invalid, 'https://a.example', 'target'));
});
test('ordinary unsubscribe freezes original service ID and unknown result blocks subscriber, credential and parent cleanup', async () => {
  const {unsubscribe}=require('./service_scope_cases.cjs'),graph=require('./service_graph.cjs');
  const identity={account:'subscriber',namespace:'tenant'},ownerIdentity={account:'owner',namespace:'tenant'},actor={identity,origin:'https://tenant.example'};
  const ref={namespace:'tenant',subject:'account:42',accountId:42},r={kind:'service-graph-subscription',phase:'created',id:7,serviceId:19,actorIdentity:identity,actorOrigin:actor.origin,ownerIdentity,original:{subscriberRef:ref}};
  const credential={value:{credentialId:3,clientId:'original-client',endpointId:5},resource:{kind:'service-graph-credential',phase:'created',parentSubscriptionId:7}};
  let writes=0;
  const h={tenantAdmin:{identity:ownerIdentity},state:{resources:[r,credential.resource]},Blocked:Error,persist(){},good(){return true;},check(label,value){assert.ok(value,label);},async ok(){return {value:{id:7,service:{id:19},status:2,subscriberRef:ref}};},async api(_,method,route){writes++;assert.equal(method,'DELETE');assert.equal(route,'/portal/service/subscriptions/19');assert.equal(r.unsubscribe.outcome,'unknown');throw Error('original subscriber response lost');}};
  await assert.rejects(unsubscribe(h,actor,{resource:r},credential),/original subscriber response lost/);
  await assert.rejects(unsubscribe(h,actor,{resource:r},credential),/no replacement DELETE/);
  await assert.rejects(graph.cleanupCredential(h,credential.resource),/retain its original credential/);
  await assert.rejects(graph.cleanupSubscription(h,r),/no subscription DELETE replay/);
  assert.equal(writes,1);assert.equal(r.phase,'created');assert.equal(credential.resource.phase,'created');
});
test('subscriber DELETE acknowledgement alone cannot close resources without exact independent CAS retirement facts', async () => {
  const {unsubscribe}=require('./service_scope_cases.cjs');
  for(const mode of ['confirmed','endpoint-still-exists','client-still-active','credential-still-active']) {
    const identity={account:'subscriber',namespace:'tenant'},ownerIdentity={account:'owner',namespace:'tenant'},actor={identity,origin:'https://tenant.example'},ref={namespace:'tenant',subject:'account:42',accountId:42};
    const r={phase:'created',id:7,serviceId:19,actorIdentity:identity,actorOrigin:actor.origin,ownerIdentity,original:{subscriberRef:ref}},c={value:{credentialId:3,clientId:'original-client',endpointId:5},resource:{phase:'created',parentSubscriptionId:7}};
    const missing={status:404,data:{error:{code:2},value:null}};let writes=0;
    const h={tenantAdmin:{identity:ownerIdentity},Blocked:Error,persist(){},good(v){return v.status===200&&!v.data?.error;},check(label,value){assert.ok(value,label);},async ok(){return {value:{id:7,service:{id:19},status:2,subscriberRef:ref}};},
      async directory(_,route){return route.endsWith('/credentials/')?[{id:3,clientId:'original-client',status:mode==='credential-still-active'?'active':'revoked'}]:[{id:8,service:{id:20},subscriberRef:ref}];},
      async api(_,method,route){if(method==='DELETE'){writes++;return {status:200,data:{value:{id:19}}};}if(route.includes('/oauth/clients/'))return {status:200,data:{value:{clientId:'original-client',status:mode==='client-still-active'?2:1}}};if(route.includes('/endpoints/')&&mode==='endpoint-still-exists')return {status:200,data:{value:{id:5}}};return missing;}};
    if(mode==='confirmed'){await unsubscribe(h,actor,{resource:r},c);assert.equal(r.phase,'deleted');assert.equal(c.resource.phase,'deleted');assert.equal(r.unsubscribe.outcome,'confirmed');}
    else{await assert.rejects(unsubscribe(h,actor,{resource:r},c));assert.equal(r.unsubscribe.outcome,'unknown');assert.equal(r.phase,'created');assert.equal(c.resource.phase,'created');}
    assert.equal(writes,1);
  }
});
