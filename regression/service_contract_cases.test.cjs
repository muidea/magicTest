const { test } = require('node:test');
const assert = require('node:assert/strict');
const { copiedRequest, matchesSchema, endpointTemplates } = require('./service_contract_cases.cjs');
const graph = require('./service_graph.cjs');
const generated = require('./generated_service_cases.cjs');
test('documented subscriber declares its exact read role with ordinary functional roles and a viewer instance scope', async t => {
  const { documentedReader } = require('./service_contract_cases.cjs'), authority = require('./application_authority_cases.cjs');
  const deploymentId = 'a'.repeat(32), actor = { identity: { account: 'ordinary-reader', namespace: 'panel' } }, events = [];
  const role = { module: '/applications/' + deploymentId, key: 'application-data-read' };
  const ordinary = { key: 'portal-basic-user', systemManaged: true, subjectType: 'account', status: 2,
    roleRefs: [{ module: '/modules/kernel/runner', key: 'portal-service-invoker' }, role] };
  let created;
  const member = { actor, value: { id: 7 }, resource: { kind: 'account' } };
  t.mock.method(authority, 'account', async (_, suffix) => { assert.equal(suffix, 'documented-reader'); events.push('account'); return member; });
  t.mock.method(authority, 'assign', async (_, value, group, access) => {
    assert.equal(value, member); assert.equal(group, created); assert.deepEqual(access, [{ applicationUuid: deploymentId, accessLevel: 'viewer' }]); events.push('assign');
  });
  const h = { admin: {}, state: { prefix: 'original' }, check(label, condition) { assert.ok(condition, label); },
    async directory(_, route) { assert.equal(route, '/cas/namespaces/panel/role-templates/'); return [ordinary]; },
    async create(route, body, kind) { assert.equal(route, '/cas/namespaces/panel/role-templates/'); assert.equal(kind, 'role-template'); events.push('template'); created = body; return body; } };
  assert.equal(await documentedReader(h, { identity: { deploymentId } }), actor);
  assert.deepEqual(events, ['template', 'account', 'assign']);
  assert.deepEqual(created.roleRefs, ordinary.roleRefs); assert.equal(created.subjectType, 'account');
  assert.equal(created.roleRefs.some(r => /write|delete|manager|admin/.test(r.key)), false);
  h.directory = async () => [];
  await assert.rejects(documentedReader(h, { identity: { deploymentId } })); assert.deepEqual(events, ['template', 'account', 'assign']);
});
test('Endpoint account-ceiling refusal disposition requires exact original template and complete unchanged Endpoint bindings', async () => {
  const { reconcileEndpointTemplateRefusal } = require('./service_contract_cases.cjs');
  for (const mode of ['exact', 'changed-endpoint', 'changed-bindings', 'changed-template', 'unowned-template', 'unknown-response', 'changed-author', 'wrong-account', 'foreign-account-binding']) {
    const owner = { identity: { account: 'owner', namespace: 'panel' }, origin: 'https://panel.test' }, role = { module: '/applications/original', key: 'application-data-read' };
    const before = { id: 7, account: { id: 42 }, authorityRevision: 3 }, bindings = [{ subjectId: 7, sourceType: 'subscription', sourceKey: 'original' }];
    const c = { outcome: 'unknown', method: 'PUT', route: '/cas/namespaces/panel/endpoints/7/role-templates', body: { roleTemplateKeys: ['original-template'] }, before, originalBindings: bindings, response: { status: 200, data: { error: { code: 5, message: 'endpoint role ' + role.module + '/' + role.key + ' exceeds account authority' } } } };
    const template = { id: 9, key: 'original-template', status: 2, subjectType: 'endpoint', roleRefs: [role] }, tracked = { kind: 'role-template', phase: 'created', id: 9, collection: '/cas/namespaces/panel/role-templates/', creation: { ownershipConfirmed: true, origin: owner.origin, actorIdentity: structuredClone(owner.identity), intended: { key: template.key, roleRefs: [role] } } };
    const r = { kind: 'service-graph-credential', phase: 'created', outcome: 'accepted', value: { endpointId: 7 }, ownerIdentity: structuredClone(owner.identity), endpointAuthorityOrigin: owner.origin, endpointAuthorityCommands: [c] };
    if (mode === 'changed-author') owner.identity.account = 'another';
    if (mode === 'unknown-response') c.response.status = 503;
    if (mode === 'unowned-template') tracked.creation.ownershipConfirmed = false;
    let writes = 0;
    const h = { admin: owner, state: { resources: [tracked, r] }, Blocked: Error, persist() { writes++; }, check(label, valid) { assert.ok(valid, label); },
      async directory(_, route) {
        if (new URL(route, owner.origin).searchParams.get('subjectType') === 'account|=') return [{ subjectId: mode === 'foreign-account-binding' ? 43 : 42, subjectType: 'account', roleModule: role.module, roleKey: 'application-manager' }];
        return route.includes('subject-role-bindings') ? mode === 'changed-bindings' ? [] : bindings : [{ ...template, roleRefs: mode === 'changed-template' ? [] : template.roleRefs }];
      },
      async ok(_, method, route) { assert.equal(method, 'GET'); if (route === '/cas/namespaces/panel/accounts/42') return { value: { id: mode === 'wrong-account' ? 43 : 42 } }; assert.equal(route, '/cas/namespaces/panel/endpoints/7'); return { value: { ...before, authorityRevision: mode === 'changed-endpoint' ? 4 : 3 } }; } };
    if (mode === 'exact') { await reconcileEndpointTemplateRefusal(h, r); assert.equal(c.outcome, 'rejected-account-ceiling-and-unchanged'); assert.equal(writes, 1); assert.equal(c.response.data.error.code, 5); }
    else { await assert.rejects(reconcileEndpointTemplateRefusal(h, r)); assert.equal(c.outcome, 'unknown'); assert.equal(writes, 0); }
  }
});
test('current-role refusal proves the exact owner stage and rejects ordinary credential or dependency failures', () => {
  const { currentRoleRefusal } = require('./service_contract_cases.cjs');
  const response = { status: 401, data: { error: { code: 5, message: '当前角色未授予此资源权限' } } };
  assert.equal(currentRoleRefusal(response), true);
  for (const invalid of [{ ...response, status: 403 }, { ...response, status: 503 }, { status: 401, data: { error: { code: 5, message: 'API key is inactive or invalid' } } }, { status: 401, data: { error: { code: 11, message: '当前角色未授予此资源权限' } } }, { ...response, data: { ...response.data, value: { leaked: true } } }]) assert.equal(currentRoleRefusal(invalid), false);
});
test('clipboard parser accepts only the exact public service operation and finite GET/POST grammar', () => {
  const origin = 'https://tenant.example', op = {method:'GET',pathTemplate:'/api/v1/gateway/services/owned/get/{id}',parameters:[{in:'path',name:'id',required:true}]};
  const text = "curl --request GET 'https://tenant.example/api/v1/gateway/services/owned/get/%3Cid%3E' \\\n  --header 'Authorization: ApiKey <API_KEY>'";
  assert.equal(copiedRequest(text,origin,'owned',op).url.pathname,'/api/v1/gateway/services/owned/get/%3Cid%3E');
  for (const bad of [text.replace('tenant.example','foreign.example'),text.replace('/owned/','/other/'),text.replace('/get/','/delete/'),text.replace('%3Cid%3E','42'),text + '; env',text.replace('GET','DELETE'),text.replace("' \\\n","?secret=unexpected' \\\n")]) assert.throws(() => copiedRequest(bad,origin,'owned',op));
  const post = {method:'POST',pathTemplate:'/api/v1/gateway/services/owned/submit',requestBody:{contentType:'application/json'}};
  const body = "curl --request POST 'https://tenant.example/api/v1/gateway/services/owned/submit' \\\n  --header 'Authorization: ApiKey <API_KEY>' \\\n  --header 'Content-Type: application/json' \\\n  --data-raw '{\"count\":0,\"enabled\":false}'";
  assert.deepEqual(copiedRequest(body,origin,'owned',post).body,{count:0,enabled:false});
  assert.deepEqual(copiedRequest(body.replace('{"count":0,"enabled":false}','{\n  "count": 0,\n  "enabled": false\n}'),origin,'owned',post).body,{count:0,enabled:false});
  for (const bad of [body + '\n$(env)',body.replace("application/json'","text/plain'"),body.replace('false','false; env')]) assert.throws(() => copiedRequest(bad,origin,'owned',post));
});
test('documented fixture schemas reject missing required values, wrong types and numeric/collection boundaries without dropping zero/false', () => {
  const schema = {type:'object',required:['count','enabled','tags'],properties:{count:{type:'integer',minimum:0,maximum:3},enabled:{type:'boolean'},tags:{type:'array',minItems:1,maxItems:2,items:{type:'string',minLength:1,maxLength:3}}}};
  const value = {count:0,enabled:false,tags:['ok']};
  assert.equal(matchesSchema(value,schema),true);
  for (const bad of [{...value,count:4},{...value,count:0.5},{...value,enabled:0},{...value,tags:[]},{...value,tags:['long']},{...value,tags:['a','b','c']},{count:0,tags:['ok']},null]) assert.equal(matchesSchema(bad,schema),false);
  assert.equal(matchesSchema(null,{type:'string',nullable:true}),true);
  assert.equal(matchesSchema('foreign',{type:'string',enum:['owned']}),false);
});
test('Endpoint template response loss freezes original command and prevents every parent retirement or replacement', async () => {
  const identity = {account:'original',namespace:'panel'}, owner = {identity,origin:'https://panel.example'}, r = {kind:'service-graph-credential',phase:'created',outcome:'accepted',value:{endpointId:7,clientId:'original'},ownerIdentity:identity,serviceId:3,parentSubscriptionId:4};
  const credential = {resource:r,value:r.value}, events = [];
  const h = {admin:owner,state:{resources:[r]},Blocked:Error,persist(){},async ok(){return {value:{id:7,account:{id:42},scope:'gateway.read'}};},async directory(){return [];},async api(_,method,route,body){events.push({method,route,body});assert.equal(r.endpointAuthorityCommands[0].outcome,'unknown');throw Error('original response lost');}};
  await assert.rejects(endpointTemplates(h,credential,['exact-read']),/original response lost/);
  assert.deepEqual(r.endpointAuthorityCommands[0].body.roleTemplateKeys,['exact-read']);
  await assert.rejects(endpointTemplates(h,credential,[]),/no replacement replay/);
  await assert.rejects(graph.cleanupCredential(h,r),/no retirement/);
  await assert.rejects(graph.cleanupSubscription(h,{id:4}),/retain its exact subscription/);
  await assert.rejects(generated.cleanup(h,{kind:'generated-service-graph',origin:owner.origin,actorIdentity:identity,commands:[],serviceId:3}),/retain its graph/);
  assert.equal(events.length,1);
});
test('Endpoint assignment needs independent exact account and subscription-source preservation; failed confirmation cannot permit revoke replay', async () => {
  for (const mode of ['confirmed','account-changed','subscription-source-changed','read-failed']) {
    const identity={account:'owner',namespace:'panel'},owner={identity,origin:'https://panel.example'},r={kind:'service-graph-credential',phase:'created',outcome:'accepted',value:{endpointId:7},ownerIdentity:identity};
    const subscription={subjectId:7,subjectType:'endpoint',sourceType:'subscription',sourceKey:'original-service',status:2},before={id:7,account:{id:42},scope:'gateway.read',status:2,templateRefs:[]};
    let writes=0,reads=0;
    const h={admin:owner,Blocked:Error,persist(){},check(label,value){assert.ok(value,label);},good(v){return v.status===200;},
      async ok(){reads++;if(writes && mode==='read-failed')throw Error('independent owner unavailable');return {value:writes?{...before,account:{id:mode==='account-changed'?43:42},templateRefs:[{key:'owned-read'}]}:before};},
      async directory(){return writes?[{...subscription,sourceKey:mode==='subscription-source-changed'?'foreign':subscription.sourceKey},{subjectId:7,sourceType:'template',sourceKey:'owned-read',status:2}]:[subscription];},
      async api(){writes++;return {status:200,data:{value:{}}};}};
    const c={resource:r,value:r.value};
    if(mode==='confirmed'){await endpointTemplates(h,c,['owned-read']);assert.equal(r.endpointAuthorityCommands[0].outcome,'confirmed');}
    else {await assert.rejects(endpointTemplates(h,c,['owned-read']));assert.equal(r.endpointAuthorityCommands[0].outcome,'unknown');await assert.rejects(endpointTemplates(h,c,[]),/no replacement replay/);}
    assert.equal(writes,1);assert.equal(reads,2);
  }
});
