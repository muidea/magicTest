const {test}=require('node:test'),assert=require('node:assert/strict');
const {changeRoles}=require('./audit_cases.cjs');
test('audit authority change persists original command before dispatch and never repeats a lost response',async()=>{
 const actor={identity:{account:'admin',namespace:'a'},origin:'https://a.local.vpc'},resource={kind:'account',id:7,collection:'/cas/namespaces/a/accounts/',creation:{intended:{account:'subject'},actorIdentity:actor.identity}};
 let writes=0,persisted;
 const h={Blocked:Error,check:(label,ok)=>assert.ok(ok,label),persist:()=>{persisted=structuredClone(resource)},ok:async()=>({value:{id:7,account:'subject',authorityRevision:1}}),api:async(a,m,route,body)=>{writes++;assert.equal(m,'PUT');assert.equal(route,resource.collection+'7/role-templates');assert.equal(persisted.authorityCommands[0].outcome,'unknown');assert.deepEqual(body,{roleTemplateKeys:['portal-user']});throw Error('response lost')}};
 await assert.rejects(changeRoles(h,actor,resource,['portal-user']),/response lost/);await assert.rejects(changeRoles(h,actor,resource,['portal-user']),/no role assignment replay/);assert.equal(writes,1);
});
