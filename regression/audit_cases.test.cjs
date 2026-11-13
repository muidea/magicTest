const {test}=require('node:test'),assert=require('node:assert/strict');
const {changeRoles,confirmRoleChange}=require('./audit_cases.cjs');
test('audit authority change persists original command before dispatch and never repeats a lost response',async()=>{
 const actor={identity:{account:'admin',namespace:'a'},origin:'https://a.local.vpc'},resource={kind:'account',id:7,collection:'/cas/namespaces/a/accounts/',creation:{intended:{account:'subject'},actorIdentity:actor.identity}};
 let writes=0,persisted;
 const h={Blocked:Error,check:(label,ok)=>assert.ok(ok,label),persist:()=>{persisted=structuredClone(resource)},ok:async()=>({value:{id:7,account:'subject',authorityRevision:1}}),api:async(a,m,route,body)=>{writes++;assert.equal(m,'PUT');assert.equal(route,resource.collection+'7/role-templates');assert.equal(persisted.authorityCommands[0].outcome,'unknown');assert.deepEqual(body,{roleTemplateKeys:['portal-user']});throw Error('response lost')}};
 await assert.rejects(changeRoles(h,actor,resource,['portal-user']),/response lost/);await assert.rejects(changeRoles(h,actor,resource,['portal-user']),/no role assignment replay/);assert.equal(writes,1);
});
test('acknowledged template-source replacement with identical effective roles keeps authority revision and is confirmed without another write',async()=>{
 const actor={identity:{account:'admin',namespace:'a'},origin:'https://a.local.vpc'};
 const resource={id:7,collection:'/cas/namespaces/a/accounts/',creation:{intended:{account:'subject'}}};
 const roles=[{module:'portal',key:'reader',status:2}];
 const before={id:7,account:'subject',authorityRevision:2,templateRefs:[{key:'first'}],effectiveRoles:roles};
 const after={...structuredClone(before),templateRefs:[{key:'second'}]};
 const command={route:resource.collection+'7',actorIdentity:actor.identity,origin:actor.origin,before,body:{roleTemplateKeys:['second']},outcome:'unknown',response:{status:200,data:{value:{templates:[{key:'second'}],effectiveRoles:roles}}}};
 const h={Blocked:Error,persist(){},good:r=>r.status===200&&!r.data.error,check:(m,c)=>assert.ok(c,m),ok:async()=>({value:after}),api:()=>assert.fail('confirmation may not replay assignment')};
 await confirmRoleChange(h,actor,resource,command);assert.equal(command.outcome,'confirmed');
 after.effectiveRoles=[...roles,{module:'panel',key:'manager',status:2}];command.outcome='unknown';
 await assert.rejects(confirmRoleChange(h,actor,resource,command));assert.equal(command.outcome,'unknown');
 after.effectiveRoles=roles;delete command.response;
 await assert.rejects(confirmRoleChange(h,actor,resource,command));assert.equal(command.outcome,'unknown');
});
