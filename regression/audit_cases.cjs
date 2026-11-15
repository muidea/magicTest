// Actual authentication events and Panel mutations, read independently from
// CAS and the operation-log owner. No direct log writes or fabricated events.
const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const serviceRoute = '/panel/hub/services/';
const roleKeys = rows => rows.map(r => r.module + ':' + r.key + ':' + r.status).sort();
async function confirmRoleChange(h, actor, resource, command) {
 const route=resource.collection+resource.id, before=command.before;
 if(command.route!==route || !same(command.actorIdentity,actor.identity) || command.origin!==actor.origin ||
    before?.id!==resource.id || before.account!==resource.creation?.intended.account || !h.good(command.response))
  throw new h.Blocked('Original role-source command acknowledgement and actor required; no replacement replay');
 const after=(await h.ok(actor,'GET',route)).value;
 const keys=command.body.roleTemplateKeys, acknowledged=command.response.data?.value;
 const sameRoles=same(roleKeys(before.effectiveRoles||[]),roleKeys(after.effectiveRoles||[]));
 h.check('CAS acknowledges exact current template sources and changes authority revision only when effective roles change',
  after.id===before.id && after.account===before.account &&
  (sameRoles ? after.authorityRevision===before.authorityRevision : after.authorityRevision>before.authorityRevision) &&
  same(after.templateRefs.map(r=>r.key).sort(),[...keys].sort()) &&
  same(acknowledged?.templates?.map(r=>r.key).sort(),[...keys].sort()) &&
  same(roleKeys(acknowledged?.effectiveRoles||[]),roleKeys(after.effectiveRoles||[])));
 command.after=after;command.outcome='confirmed';h.persist();return {before,after};
}
async function changeRoles(h, actor, resource, roleTemplateKeys) {
 if (resource.authorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original authority command is unknown; no role assignment replay');
 const route=resource.collection+resource.id, before=(await h.ok(actor,'GET',route)).value;
 h.check('Audit authority target is exact original acknowledged account',before.id===resource.id&&before.account===resource.creation.intended.account&&actor.identity.namespace===resource.creation.actorIdentity.namespace);
 const command={actorIdentity:structuredClone(actor.identity),origin:actor.origin,route,body:{roleTemplateKeys},before,outcome:'unknown'};
 (resource.authorityCommands ||= []).push(command);h.persist();
 const response=await h.api(actor,'PUT',route+'/role-templates',command.body);command.response=response;h.persist();
 return confirmRoleChange(h,actor,resource,command);
}
async function awaitRows(read, predicate) {
 let rows;
 for(let attempt=0;attempt<15;attempt++){
  rows=await read();if(predicate(rows))return rows;
  if(attempt<14)await new Promise(resolve=>setTimeout(resolve,1000));
 }
 return rows;
}
const handlers={'F057-001':async h=>{
 const original=h.tenantAdmin,n=original.identity.namespace;
 const self=(await h.ok(original,'GET','/api/v1/web/session/')).value,subject='account:'+self.account.id;
 const audit='/cas/namespaces/'+n+'/oauth/audit/';
 const initial=await h.directory(h.admin,audit),beforeIDs=new Set(initial.map(r=>r.id)),started=Date.now();
 await h.rejectedLogin(original.identity.account,original.password+'-wrong-'+crypto.randomBytes(4).toString('hex'),n);
 const fresh=await h.login(original.identity.account,original.password,n);
 const target=await h.createAs('tenantAdmin','/cas/namespaces/'+n+'/accounts/',{account:h.state.prefix+'-audit-target',displayName:'回归审计目标',password:h.state.password,status:2,roleTemplateKeys:['portal-user']},'account');
 const account=h.state.resources.find(r=>r.kind==='account'&&r.id===target.id);
 const changed=await changeRoles(h,original,account,['portal-user','tenant-security-admin']);
 const operationActor=h.admin,operationNamespace=operationActor.identity.namespace;
 const operationSession=(await h.ok(operationActor,'GET','/api/v1/web/session/')).value,operationSubject='account:'+operationSession.account.id;
 const key=h.state.prefix+'_audit';
 const service=await h.createAs('admin',serviceRoute,{key,name:key,showName:'审计服务',catalog:'regression',description:'原审计样本',providerType:'external',providerKey:'',status:2,accessMode:'gateway',address:'https://regression.invalid/api',options:JSON.stringify({debug:{authMode:'bearer',operations:[{key:'probe',name:'probe',method:'GET',pathTemplate:'https://regression.invalid/api/probe',parameters:[]}]}})},'service');
 const resource=h.state.resources.find(r=>r.kind==='service'&&r.id===service.id);
 const current=(await h.ok(operationActor,'GET',serviceRoute+service.id)).value;
 const command={method:'PUT',route:serviceRoute+service.id,body:{expectedServiceVersion:current.updateTime,description:'审计修改 '+key},confirmed:false};
 (resource.pendingServiceCommands ||= []).push(command);h.persist();
 command.response=await h.api(operationActor,'PUT',command.route,command.body);h.persist();
 const after=(await h.ok(operationActor,'GET',command.route)).value;
 h.check('Formal service mutation independently preserves exact resource and new value',h.good(command.response)&&after.id===service.id&&after.key===key&&after.description===command.body.description&&after.updateTime>current.updateTime);
 command.confirmed=true;h.persist();
 const tenantKey=h.state.prefix+'_tenant_audit';
 const tenantService=await h.createAs('tenantAdmin',serviceRoute,{key:tenantKey,name:tenantKey,showName:'租户审计服务',catalog:'regression',description:'原租户审计样本',providerType:'external',providerKey:'',status:2,accessMode:'gateway',address:'https://regression.invalid/api',options:JSON.stringify({debug:{authMode:'bearer',operations:[{key:'probe',name:'probe',method:'GET',pathTemplate:'https://regression.invalid/api/probe',parameters:[]}]}})},'service');
 const tenantResource=h.state.resources.find(r=>r.kind==='service'&&r.id===tenantService.id);
 const tenantCurrent=(await h.ok(original,'GET',serviceRoute+tenantService.id)).value;
 const tenantCommand={method:'PUT',route:serviceRoute+tenantService.id,body:{expectedServiceVersion:tenantCurrent.updateTime,description:'租户审计修改 '+tenantKey},confirmed:false};
 (tenantResource.pendingServiceCommands ||= []).push(tenantCommand);h.persist();
 tenantCommand.response=await h.api(original,'PUT',tenantCommand.route,tenantCommand.body);h.persist();
 const tenantAfter=(await h.ok(original,'GET',tenantCommand.route)).value;
 h.check('Tenant service mutation independently preserves exact resource and new value',h.good(tenantCommand.response)&&tenantAfter.id===tenantService.id&&tenantAfter.key===tenantKey&&tenantAfter.description===tenantCommand.body.description&&tenantAfter.updateTime>tenantCurrent.updateTime);
 tenantCommand.confirmed=true;h.persist();
 await fresh.page.goto(fresh.origin+'/api/v1/web/auth/logout',{waitUntil:'networkidle'});
 const loggedOut=await h.api(fresh,'GET','/api/v1/web/session/');h.check('Audit sample formally logs out only its new session',loggedOut.status===401||loggedOut.data?.error?.code===11);
 h.check('Original unrelated same-account session survives audit sample logout',h.good(await h.api(original,'GET','/api/v1/web/session/')));
 const panelAccess='/panel/support/audit/access';
 const panelOperation='/panel/support/audit/operation';
 const desired=[['login_failure','failure'],['login_success','success'],['logout_success','success']];
 const events=await awaitRows(()=>h.directory(original,panelAccess),rows=>desired.every(([type,outcome])=>rows.some(r=>!beforeIDs.has(r.id)&&r.subject===subject&&r.eventType===type&&r.outcome===outcome))&&rows.some(r=>!beforeIDs.has(r.id)&&r.subject==='account:'+target.id&&r.eventType==='role_assignment_updated'&&r.outcome==='success'));
 const observed=events.filter(r=>!beforeIDs.has(r.id)&&r.subject===subject&&r.createTime>=started-2000);
 for(const [type,outcome] of desired){
  const matching=observed.filter(r=>r.eventType===type&&r.outcome===outcome);
  h.check('Real '+type+' has exact original subject, namespace, source and outcome',matching.length>0&&matching.every(r=>r.namespace===n&&r.actorNamespace===n&&r.actorSubject===subject&&r.remoteAddr&&r.clientId),matching);
 }
 const authority=events.filter(r=>!beforeIDs.has(r.id)&&r.subject==='account:'+target.id&&r.eventType==='role_assignment_updated'&&r.outcome==='success'&&r.createTime>=started-2000);
 const roleDetails=authority.map(r=>{try{return JSON.parse(r.detailJson||'{}');}catch{return {};}});
 h.check('Formal authorization-change audit event records original actor, target, namespace, source and role templates',
  authority.length>0&&authority.every(r=>r.namespace===n&&r.targetNamespace===n&&r.actorNamespace===n&&r.actorSubject===subject&&r.remoteAddr&&r.clientId)&&
  roleDetails.some(d=>d.changed===true&&same([...(d.templateKeys||[])].sort(),['portal-user','tenant-security-admin'])),{authority,roleDetails});
 const casEvents=await h.directory(original,audit);
 h.check('Direct CAS namespace security audit agrees with tenant Panel access audit on recorded authorization change',
  authority.every(a=>casEvents.some(c=>c.id===a.id&&c.eventType===a.eventType&&c.subject===a.subject&&c.namespace===a.namespace)),{authorityCount:authority.length});
 // Platform and tenant audit routes filter strictly within the caller's active namespace.
 const operationQuery = panelOperation + '?' + new URLSearchParams({operationType:'更新服务',detailMessage:'服务ID:'+service.id+'；标识:'+key,actorNamespace:operationNamespace,actorSubject:operationSubject,targetNamespace:operationNamespace});
 const operations=await awaitRows(()=>h.directory(operationActor,operationQuery,{maxPages:2}),rows=>rows.some(r=>r.operationType==='更新服务'&&r.detailMessage==='服务ID:'+service.id+'；标识:'+key));
 const logs=operations.filter(r=>r.operationType==='更新服务'&&r.detailMessage==='服务ID:'+service.id+'；标识:'+key);
 h.check('Independent operation-log owner correlates the acknowledged exact service update and original actor',logs.length===1&&logs.every(r=>r.eventId&&r.outcome==='succeeded'&&r.actorNamespace===operationNamespace&&r.actorSubject===operationSubject&&r.targetNamespace===operationNamespace&&r.namespace===operationNamespace&&r.address&&r.operationTime>=started-2000),logs);
 const tenantOpQuery=panelOperation + '?' + new URLSearchParams({operationType:'更新服务',detailMessage:'服务ID:'+tenantService.id+'；标识:'+tenantKey,actorNamespace:n,actorSubject:subject,targetNamespace:n});
 const tenantOps=await awaitRows(()=>h.directory(original,tenantOpQuery,{maxPages:2}),rows=>rows.some(r=>r.operationType==='更新服务'&&r.detailMessage==='服务ID:'+tenantService.id+'；标识:'+tenantKey));
 const tenantLogs=tenantOps.filter(r=>r.operationType==='更新服务'&&r.detailMessage==='服务ID:'+tenantService.id+'；标识:'+tenantKey);
 h.check('Tenant security admin reads own tenant operation log with complete actor, target and source correlation',tenantLogs.length===1&&tenantLogs.every(r=>r.eventId&&r.outcome==='succeeded'&&r.actorNamespace===n&&r.actorSubject===subject&&r.targetNamespace===n&&r.namespace===n&&r.address&&r.operationTime>=started-2000),tenantLogs);
 const tenantCrossOp=await h.directory(original,operationQuery,{maxPages:2});
 h.check('Tenant security admin cannot read platform operation logs across namespaces',!tenantCrossOp.some(r=>r.namespace===operationNamespace||r.detailMessage==='服务ID:'+service.id+'；标识:'+key),tenantCrossOp);
 const peerAccess=await h.directory(h.otherTenantAdmin,panelAccess,{maxPages:2});
 const peerOp=await h.directory(h.otherTenantAdmin,tenantOpQuery,{maxPages:2});
 h.check('Other tenant security admin is strictly isolated from target tenant security and operation audit logs',
  !peerAccess.some(r=>r.namespace===n||r.targetNamespace===n||r.subject===subject||r.subject==='account:'+target.id)&&
  !peerOp.some(r=>r.namespace===n||r.detailMessage==='服务ID:'+tenantService.id+'；标识:'+tenantKey),{peerAccessCount:peerAccess.length,peerOpCount:peerOp.length});
 const secrets=[h.state.password,original.password,h.user.password,h.credentials.password].filter(v=>typeof v==='string'&&v.length>=8);
 h.check('Observed security and operation records contain no known plaintext regression or management credentials',secrets.every(secret=>!JSON.stringify({observed,authority,logs,tenantLogs}).includes(secret)));
 h.observe({kind:'audit-event-coverage',authentication:desired.map(([eventType])=>eventType),authorization:authority.map(r=>({id:r.id,eventType:r.eventType,subject:r.subject})),serviceId:service.id,tenantServiceId:tenantService.id,operationEventIds:logs.map(r=>r.eventId),tenantOperationEventIds:tenantLogs.map(r=>r.eventId),authorityTarget:target.id,authorityRevisionBefore:changed.before.authorityRevision,authorityRevisionAfter:changed.after.authorityRevision});
}};
handlers['F057-001'].actors=['tenantAdmin','otherTenantAdmin','user'];handlers['F057-001'].transport='owner-api';
module.exports={handlers,changeRoles,confirmRoleChange};
