// Actual authentication events and Panel mutations, read independently from
// CAS and the operation-log owner. No direct log writes or fabricated events.
const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const serviceRoute = '/panel/hub/services/';
async function changeRoles(h, actor, resource, roleTemplateKeys) {
 if (resource.authorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original authority command is unknown; no role assignment replay');
 const route=resource.collection+resource.id, before=(await h.ok(actor,'GET',route)).value;
 h.check('Audit authority target is exact original acknowledged account',before.id===resource.id&&before.account===resource.creation.intended.account&&actor.identity.namespace===resource.creation.actorIdentity.namespace);
 const command={actorIdentity:structuredClone(actor.identity),origin:actor.origin,route,body:{roleTemplateKeys},before,outcome:'unknown'};
 (resource.authorityCommands ||= []).push(command);h.persist();
 const response=await h.api(actor,'PUT',route+'/role-templates',command.body);command.response=response;h.persist();
 const after=(await h.ok(actor,'GET',route)).value;
 h.check('CAS acknowledges and independently confirms changed exact template sources',h.good(response)&&after.id===before.id&&after.authorityRevision>before.authorityRevision&&same(after.templateRefs.map(r=>r.key).sort(),[...roleTemplateKeys].sort()));
 command.after=after;command.outcome='confirmed';h.persist();return {before,after};
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
 await fresh.page.goto(fresh.origin+'/api/v1/web/auth/logout',{waitUntil:'networkidle'});
 const loggedOut=await h.api(fresh,'GET','/api/v1/web/session/');h.check('Audit sample formally logs out only its new session',loggedOut.status===401||loggedOut.data?.error?.code===11);
 h.check('Original unrelated same-account session survives audit sample logout',h.good(await h.api(original,'GET','/api/v1/web/session/')));
 const desired=[['login_failure','failure'],['login_success','success'],['logout_success','success']];
 const events=await awaitRows(()=>h.directory(h.admin,audit),rows=>desired.every(([type,outcome])=>rows.some(r=>!beforeIDs.has(r.id)&&r.subject===subject&&r.eventType===type&&r.outcome===outcome)));
 const observed=events.filter(r=>!beforeIDs.has(r.id)&&r.subject===subject&&r.createTime>=started-2000);
 for(const [type,outcome] of desired){
  const matching=observed.filter(r=>r.eventType===type&&r.outcome===outcome);
  h.check('Real '+type+' has exact original subject, namespace, source and outcome',matching.length>0&&matching.every(r=>r.namespace===n&&r.actorNamespace===n&&r.actorSubject===subject&&r.remoteAddr&&r.clientId),matching);
 }
 // Platform audit routes are explicitly platform/home scoped; do not switch
 // the observer to a tenant and mistake the intended 403 for missing records.
 // Query only the exact original mutation through the existing owner filter.
 // Growing unrelated audit history must not exhaust the observer budget.
 const operationQuery = '/panel/support/audit/operation?' + new URLSearchParams({operationType:'更新服务',detailMessage:'服务ID:'+service.id+'；标识:'+key,actorNamespace:operationNamespace,actorSubject:operationSubject,targetNamespace:operationNamespace});
 const operations=await awaitRows(()=>h.directory(operationActor,operationQuery,{maxPages:2}),rows=>rows.some(r=>r.operationType==='更新服务'&&r.detailMessage==='服务ID:'+service.id+'；标识:'+key));
 const logs=operations.filter(r=>r.operationType==='更新服务'&&r.detailMessage==='服务ID:'+service.id+'；标识:'+key);
 h.check('Independent operation-log owner correlates the acknowledged exact service update and original actor',logs.length===1&&logs.every(r=>r.eventId&&r.outcome==='succeeded'&&r.actorNamespace===operationNamespace&&r.actorSubject===operationSubject&&r.targetNamespace===operationNamespace&&r.namespace===operationNamespace&&r.address&&r.operationTime>=started-2000),logs);
 const secrets=[h.state.password,original.password,h.user.password,h.credentials.password].filter(v=>typeof v==='string'&&v.length>=8);
 h.check('Observed security and operation records contain no known plaintext regression or management credentials',secrets.every(secret=>!JSON.stringify({observed,logs}).includes(secret)));
 const authority=events.filter(r=>!beforeIDs.has(r.id)&&r.subject==='account:'+target.id&&/role|permission|authority|assignment/.test(r.eventType));
 h.observe({kind:'audit-event-coverage',authentication:desired.map(([eventType])=>eventType),serviceId:service.id,operationEventIds:logs.map(r=>r.eventId),authorityTarget:target.id,authorityRevisionBefore:changed.before.authorityRevision,authorityRevisionAfter:changed.after.authorityRevision,authorityEventCandidates:authority});
 await h.partial('Platform/home operation route verified; tenant operation-log read exposure remains unverified under its declared platform/home restriction. Real failed/successful login, logout, original-session protection, acknowledged service mutation and independent complete CAS/operation-log correlation verified without known credential leakage. Role assignment is independently persisted, but no formal authorization-change audit event contract is identified; retain this gap rather than infer it from token revocation.');
}};
handlers['F057-001'].actors=['tenantAdmin','user'];handlers['F057-001'].transport='owner-api';
module.exports={handlers,changeRoles};
