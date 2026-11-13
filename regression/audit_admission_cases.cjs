// An admission-lock conflict is not queue exhaustion or a capacity boundary.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, execFileSync } = require('node:child_process');
const { createInterface } = require('node:readline');
const { isDeepStrictEqual: same } = require('node:util');
const { validateIsolation } = require('./delivery_fixture.cjs');
const services = '/panel/hub/services/';
const opts = { encoding: 'utf8', stdio: ['ignore','pipe','pipe'], timeout: 15000, maxBuffer: 2*1024*1024 };
function topology(config, run = execFileSync) {
  validateIsolation(config, JSON.parse(run('docker', ['info','--format','{{json .}}'], opts)));
  const rows = JSON.parse(run('docker', ['inspect','magicPanel'], opts)), c = rows[0];
  if (rows.length !== 1 || c?.Name !== '/magicPanel' || !/^[a-f0-9]{64}$/.test(c.Id || '') || !/^sha256:[a-f0-9]{64}$/.test(c.Image || '') ||
      !c.State?.Running || c.State.Restarting || !Number.isFinite(Date.parse(c.State.StartedAt)) || !Number.isSafeInteger(c.RestartCount) || c.RestartCount<0) throw Error('Exact running original Panel required');
  const values = (c.Config?.Env || []).filter(v => v.startsWith('MAGIC_DEPLOYMENT_EXECUTOR_RUNTIME_ROOT='));
  if (values.length > 1) throw Error('Ambiguous original Panel runtime root');
  const root = values.length ? values[0].slice(values[0].indexOf('=')+1) : '/var/app/data/deployment-runtime';
  if (!path.isAbsolute(root) || path.resolve(root) !== root || root === '/') throw Error('Canonical original Panel runtime root required');
  const candidates = (c.Mounts || []).filter(m => root === m.Destination || root.startsWith(m.Destination.replace(/\/$/,'')+'/')).sort((a,b)=>b.Destination.length-a.Destination.length);
  const m = candidates[0];
  if (!m || candidates[1]?.Destination===m.Destination || !path.isAbsolute(m.Destination) || path.resolve(m.Destination)!==m.Destination || m.Type !== 'bind' || !m.RW || !path.isAbsolute(m.Source) || path.resolve(m.Source) !== m.Source || !m.Source.startsWith(config.platformRoot+'/'))
    throw Error('Original isolated writable persistent bind mount required');
  const lockRoot = path.join(m.Source, path.relative(m.Destination, root), '.operation-audit');
  const user = c.Config?.User || '0'; if (!/^\d+(?::\d+)?$/.test(user)) throw Error('Exact numeric original owner UID required');
  const uid = Number(user.split(':')[0]); if (!Number.isSafeInteger(uid)) throw Error('Exact original UID required');
  return { id: c.Id, image: c.Image, startedAt: c.State.StartedAt, restartCount: c.RestartCount, mount: { source:m.Source,destination:m.Destination }, root, lockRoot, uid };
}
async function hold(h, binding, callback, start = spawn) {
  if (fs.realpathSync(binding.lockRoot) !== binding.lockRoot) throw new h.Blocked('Original admission root must be directly accessible without symlinks');
  const correlation=crypto.randomBytes(16).toString('hex'), child=start('python3',['-B',path.join(__dirname,'audit_admission_lock.py'),'--root',binding.lockRoot,'--uid',String(binding.uid),'--correlation',correlation],{stdio:['pipe','pipe','pipe']});
  let ready,released,problem,callbackTask,closed=false,releaseSent=false,size=0;
  child.stderr.on('data',()=>{}); child.stdin.on('error',()=>{});
  const lines=createInterface({input:child.stdout});
  const timer=setTimeout(()=>{problem ||= Error('Original admission helper deadline; no business replay');child.kill('SIGKILL');},95000);
  lines.on('line',line=>{try{
    size+=Buffer.byteLength(line); if(size>8192)throw Error('Finite admission helper protocol exceeded');
    const v=JSON.parse(line); if(v.correlation!==correlation)throw Error('Original admission helper identity changed');
    if(v.kind==='ready'&&!ready&&!released){
      const valid = (facts,mode) => facts && Object.keys(facts).length===4 && Number.isSafeInteger(facts.device) && facts.device>=0 && Number.isSafeInteger(facts.inode) && facts.inode>0 && facts.uid===binding.uid && facts.mode===mode;
      if(!valid(v.directory,0o700)||!valid(v.lock,0o600))throw Error('Exact original admission inode/owner/mode proof required');
      ready=v;
      const held = () => { if(closed||problem||releaseSent||released||(child.exitCode!=null))throw new h.Blocked('Original admission helper ended before dispatch; no late request'); };
      callbackTask=Promise.resolve().then(()=>{held();return callback(v,held);})
        .then(value=>({value}),error=>({error})).then(outcome=>{if(!closed){releaseSent=true;child.stdin.end('release:'+correlation+'\n');}return outcome;});
    }else if(v.kind==='released'&&ready&&releaseSent&&!released&&same(v.lock,ready.lock)&&same(v.directory,ready.directory)) released=v;
    else throw Error('Original admission protocol unavailable or out of order');
  }catch(error){problem ||= error;child.kill('SIGKILL');}});
  let exit;
  try{exit=await new Promise(resolve=>{child.once('error',()=>{problem ||= Error('Admission helper launch unavailable');resolve({code:null});});child.once('close',(code,signal)=>{closed=true;resolve({code,signal});});});}
  finally{clearTimeout(timer);lines.close();}
  const outcome=await callbackTask;
  if(outcome?.error)throw outcome.error;
  if(problem||exit.code!==0||exit.signal||!ready||!released)throw new h.Blocked(problem?.message||'Original admission helper disposition unconfirmed; no request replay');
  return {ready,released,value:outcome?.value};
}
function query(r, subject) { return '/panel/support/audit/operation?'+new URLSearchParams({operationType:'更新服务',detailMessage:'服务ID:'+r.id+'；标识:'+r.creation.intended.key,actorNamespace:r.creation.actorIdentity.namespace,actorSubject:subject,targetNamespace:r.creation.actorIdentity.namespace}); }
function original(h,r) {
  if (!r.creation?.ownershipConfirmed || r.collection!==services || r.phase!=='created' || !same(r.creation.actorIdentity,h.admin.identity) || r.creation.origin!==h.admin.origin || r.pendingServiceCommands?.some(c=>!c.confirmed))
    throw new h.Blocked('Original service owner or audit admission command unresolved; no replacement write');
}
async function mutate(h,r,subject,description,refused,held) {
  original(h,r);
  if(refused && typeof held!=='function')throw new h.Blocked('Original live admission holder proof required');
  const before=(await h.ok(h.admin,'GET',services+r.id)).value,route=services+r.id,auditQuery=query(r,subject),events=await h.directory(h.admin,auditQuery,{maxPages:2});
  if (!events.every(v=>typeof v.eventId==='string'&&v.eventId) || new Set(events.map(v=>v.eventId)).size!==events.length) throw new h.Blocked('Complete original audit baseline identities required');
  const c={kind:'audit-admission-command',actorIdentity:structuredClone(h.admin.identity),origin:h.admin.origin,subject,before,route,method:'PUT',body:{expectedServiceVersion:before.updateTime,description},refused,auditQuery,beforeEventIds:events.map(v=>v.eventId),startedAt:Date.now(),confirmed:false};
  if(refused)held(); original(h,r);
  (r.pendingServiceCommands ||= []).push(c);h.persist(); c.response=await h.api(h.admin,'PUT',route,c.body);h.persist();
  c.after=(await h.ok(h.admin,'GET',route)).value;h.persist();
  if(refused){
    h.check('Actual original request reaches the persistent admission lock guard before business execution',c.response.status===200&&c.response.data?.value==null&&c.response.data?.error?.code>0&&c.response.data.error.message==='操作日志正在处理，请稍后重试'&&same(c.after,before),c);
    c.auditRows=await h.directory(h.admin,auditQuery,{maxPages:2});h.persist();
    h.check('Refused pre-admission request creates no new exact service audit event',same(c.auditRows,events));
  }else{
    h.check('New independent command acknowledges exact original service mutation and full owner result',h.good(c.response)&&same(c.response.data.value,c.after)&&c.after.description===description&&c.after.updateTime>before.updateTime&&same({...c.after,description:before.description,updateTime:before.updateTime},before),c);
    for(let n=0;n<15;n++){c.auditRows=(await h.directory(h.admin,auditQuery,{maxPages:2})).filter(v=>!c.beforeEventIds.includes(v.eventId));h.persist();if(c.auditRows.length)break;if(n<14)await new Promise(resolve=>setTimeout(resolve,1000));}
    const row=c.auditRows[0];h.check('Independent durable audit owner records the actual newly committed service exactly once with original actor and result',c.auditRows.length===1&&/^[a-f0-9]{32}$/.test(row?.eventId||'')&&row.outcome==='succeeded'&&row.actorSubject===subject&&row.account===subject&&row.actorNamespace===c.actorIdentity.namespace&&row.targetNamespace===c.actorIdentity.namespace&&row.namespace===c.actorIdentity.namespace&&row.operationType==='更新服务'&&row.detailMessage==='服务ID:'+r.id+'；标识:'+r.creation.intended.key&&row.resourceType==='/modules/kernel/panel'&&typeof row.address==='string'&&row.address.length>0&&row.operationTime>=c.startedAt-2000,c.auditRows);
  }
  if(!same(h.admin.identity,c.actorIdentity)||h.admin.origin!==c.origin)throw new h.Blocked('Original service actor changed');
  c.confirmed=true;h.persist();return c;
}
function serviceInput(prefix,suffix) {
  const key=prefix+'_admission_'+suffix;
  return {key,name:key,showName:'接纳审计 '+suffix,catalog:'regression',description:'original '+suffix,
    providerType:'external',providerKey:'',status:2,accessMode:'gateway',address:'https://regression.invalid/api',
    options:JSON.stringify({contract:{version:'1',operations:[{key:'probe',name:'probe',method:'GET',upstreamPath:'/probe',responseBody:{contentType:'application/json',schema:{type:'object'}}}]}})};
}
async function admissions(h) {
  await require('./delivery_cases.cjs').fixture(h);
  const config=JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig)), binding=topology(config),account=(await h.ok(h.admin,'GET','/api/v1/web/session/')).value.account;
  h.check('Audit contention uses original platform home account',account?.account===h.admin.identity.account&&Number.isSafeInteger(account.id)&&account.id>0);
  const suffix=crypto.randomBytes(8).toString('hex'),service=await h.create(services,serviceInput(h.state.prefix,suffix),'service');
  const r=h.state.resources.find(v=>v.kind==='service'&&v.id===service.id),peer=(await h.ok(h.admin,'GET',services+r.id)).value;
  const attempt={serviceId:r.id,actorIdentity:structuredClone(h.admin.identity),origin:h.admin.origin,binding,phase:'planned'};
  (h.state.fixtures.auditAdmissionAttempts ||= []).push(attempt);h.persist();
  const proof=await hold(h,binding,async (ready,held)=>{
    attempt.ready=ready;attempt.phase='held';h.persist();
    return mutate(h,r,'account:'+account.id,'refused '+suffix,true,()=>{
      held();
      if(!same(topology(config),binding))throw new h.Blocked('Original Panel deployment changed before admission dispatch; no replacement command');
      held();
    });
  });
  attempt.released=proof.released;attempt.phase='released';h.persist();
  h.check('Read-only test holder releases the exact original deployment/owner inode without restart',same(topology(config),binding));
  h.check('Original rejected command leaves entire service unchanged',same((await h.ok(h.admin,'GET',services+r.id)).value,peer));
  const accepted=await mutate(h,r,'account:'+account.id,'accepted '+suffix,false);
  h.check('Post-release command is a distinct new intent, never a replay of the rejected body',accepted.body.description!==proof.value.body.description&&same(accepted.before,proof.value.after));
  h.observe({kind:'actual-admission-contention-subset',attempt,refused:proof.value,accepted,qualification:'Existing admission flock contention and normal committed-result truth only; no full-queue, 16KiB boundary or CAS reservation proof.'});
  await h.partial('Real isolated Panel admission flock contention refuses the exact original conditional service command before business execution; full service and audit baseline preserved. Original inode/holder released, a different new command commits and has a unique independent durable owner audit event. Queue count/envelope boundaries, CAS reserved slots, filesystem failure, post-commit failure/restart replay and retention acceptance remain uncovered.');
}
admissions.transport='owner-api';admissions.requiresOnlyDeliveryFixture=true;
module.exports={handlers:{'F057-005':admissions},topology,hold,mutate,serviceInput};
