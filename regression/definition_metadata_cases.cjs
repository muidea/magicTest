const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const { member } = require('./business_cases.cjs');
const { packageContent } = require('./owner_transport.cjs');
const { execFileSync } = require('node:child_process');
const base = '/panel/application/definitions/';
const fields = ['uuid','name','showName','pkgPrefix','icon','catalog','version','email','author','description','uiMeta','runtimeType','storage','authorization'];
function command(value, changes = {}) {
  return { ...Object.fromEntries(fields.filter(k => Object.hasOwn(value,k)).map(k => [k,structuredClone(value[k])])), ...changes, expectedDefinitionVersion:value.updateTime };
}
const semantics = value => {const copy=structuredClone(value);delete copy.updateTime;return copy;};
function original(h,r) {
  if (!same(h.admin.identity,r.actorIdentity) || h.admin.origin!==r.origin || r.commands.some(c=>c.outcome==='unknown')) throw new h.Blocked('Original metadata command or actor unresolved; no replacement write');
}
async function write(h,r,changes) {
  original(h,r);
  const route=base+r.id, before=(await h.ok(h.admin,'GET',route)).value;
  if(!same(before,r.last))throw new h.Blocked('Original metadata changed concurrently; do not overwrite');
  const c={route,body:command(before,changes),outcome:'unknown'};r.commands.push(c);h.persist();
  c.response=await h.api(h.admin,'PUT',route,c.body);h.persist();
  const current=(await h.ok(h.admin,'GET',route)).value;
  if (!same(h.admin.identity,r.actorIdentity) || h.admin.origin!==r.origin) throw new h.Blocked('Original metadata actor changed; preserve unresolved command');
  if(!h.good(c.response) && same(current,before) && [3,4,5,12,19,21,22].includes(c.response.data?.error?.code)) {c.outcome='rejected-and-unchanged';h.persist();}
  h.check('Original conditional metadata command and independent owner agree on the complete persisted definition',h.good(c.response) && same(current,c.response.data.value) && current.id===r.id && current.uuid===r.original.uuid && current.updateTime>before.updateTime,current);
  h.check('Metadata owner retains every explicitly submitted original and changed field',fields.every(k=>!Object.hasOwn(c.body,k)||same(current[k],c.body[k])),current);
  c.outcome='confirmed';r.last=current;h.persist();
  return current;
}
async function restore(h,r) {
  original(h,r);
  const current=(await h.ok(h.admin,'GET',base+r.id)).value;
  if(!same(current,r.last))throw new h.Blocked('Metadata restoration refuses a concurrent original definition revision');
  if(!same(semantics(current),semantics(r.original)))await write(h,r,Object.fromEntries(fields.filter(k=>Object.hasOwn(r.original,k)).map(k=>[k,structuredClone(r.original[k])])));
  h.check('Independent owner restores original metadata semantics while retaining advanced concurrency revision',same(semantics((await h.ok(h.admin,'GET',base+r.id)).value),semantics(r.original)));
  r.phase='deleted';h.persist();return {proof:'Exact conditional metadata restoration and complete independent owner read; immutable published fixture retained, revision not rewritten.'};
}
function track(h,value,external) {
  const r={kind:external?'definition-metadata-restore':'definition-metadata-command',phase:'created',id:value.id,original:value,last:value,origin:h.admin.origin,actorIdentity:structuredClone(h.admin.identity),commands:[]};
  if(external) h.state.resources.push(r);
  else {
    const parent=h.state.resources.find(v=>v.kind==='definition' && v.id===value.id && v.creation?.ownershipConfirmed);
    if(!parent || parent.metadataJournal)throw new h.Blocked('Metadata command requires the exact original owned definition');
    parent.metadataJournal=r;
  }
  h.persist();return r;
}
async function basic(h) {
  const f=await fixture(h), app=await a.definition(h,'metadata'), r=track(h,app,false);
  const storage=structuredClone(app.storage);storage.slots[0].estimatedConnections=9;
  await write(h,r,{name:h.state.prefix+'-metadata-edited',showName:'已保存模型名称',pkgPrefix:h.state.prefix+'edited',icon:'appstore',storage});
  const draft=await a.draft(h,r.last);
  h.check('Editable definition retains its exact identity and current metadata revision in the model draft',draft.applicationId===app.id && draft.applicationUuid===app.uuid && draft.definitionVersion===r.last.updateTime && draft.entities.length===0,draft);
  const download=await packageContent(h.admin,'/panel/application/model-packages/'+f.package.id+'/content',h.observe);
  h.check('Original frozen package is available as complete ZIP bytes',download.status===200 && Buffer.isBuffer(download.data.bytes));
  const manifest=JSON.parse(execFileSync('python3',['-B','-c','import sys,io,json,zipfile\nz=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))\nm=json.loads(z.read("package.json"))\nprint(json.dumps({k:m[k] for k in ["apiVersion","kind","application"]}))'],{input:download.data.bytes,encoding:'utf8'}));
  h.check('Initial package format stays v1 independently of application release text and published model revision',manifest.apiVersion==='magic.model-package/v1' && manifest.kind==='ApplicationModelPackage' && manifest.application.uuid===f.application.uuid && manifest.application.key===f.application.name && manifest.application.modelRevision===f.revision.version && manifest.application.version===f.revision.application.version.trim().replace(/^v/,''),manifest);
  const actor=await member(h,'manager'), snapshots=[];
  for(const instance of f.installations) snapshots.push({installation:(await h.ok(h.admin,'GET','/panel/application/installations/'+instance.id)).value,
    runtime:(await h.ok(actor,'GET','/apps/application/runtimes/'+f.application.name+'?deploymentId='+instance.deploymentId)).value});
  const current=(await h.ok(h.admin,'GET',base+f.application.id)).value, external=track(h,current,true);
  let primary;
  try {
    const requirement=structuredClone(current.storage);requirement.slots[0].estimatedConnections+=1;
    await write(h,external,{showName:'未发布模型信息 '+h.state.prefix,icon:'appstore',description:'Unpublished metadata only '+h.state.prefix,storage:requirement});
    h.check('Published application revision identity and definition digest remain exact after metadata draft save',same((await h.ok(h.admin,'GET',base+f.application.id+'/revisions/'+f.revision.id)).value,f.revision) && f.revision.version===1);
    h.check('Original model package owner retains the exact frozen package contract',same((await h.ok(h.admin,'GET','/panel/application/model-packages/'+f.package.id)).value,f.package));
    for(const [i,instance] of f.installations.entries()) {
      h.check('Original installation remains unchanged after its own source metadata edit',same((await h.ok(h.admin,'GET','/panel/application/installations/'+instance.id)).value,snapshots[i].installation));
      h.check('Original ordinary member still sees exact frozen runtime metadata, not mutable source metadata',same((await h.ok(actor,'GET','/apps/application/runtimes/'+f.application.name+'?deploymentId='+instance.deploymentId)).value,snapshots[i].runtime));
    }
  } catch(error){primary=error;throw error;}
  finally {try{await restore(h,external);}catch(error){h.observe({kind:'metadata-restoration-open',id:external.id,error:error.message});if(!primary)throw error;}}
}
basic.transport='owner-api';
module.exports={handlers:{'F011-001':basic},write,restore,command,track};
