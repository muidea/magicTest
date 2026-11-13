const {test}=require('node:test');
const assert=require('node:assert/strict');
const {command,write,restore}=require('./definition_metadata_cases.cjs');
test('metadata DTO excludes owner workflow/read facts and keeps its original concurrency revision',()=>{
 const dto=command({id:7,uuid:'original',name:'app',updateTime:11,createTime:1,deployment:{phase:'running'},functionBlocks:['not-inline'],storage:{required:true}},{showName:'new'});
 assert.deepEqual(dto,{uuid:'original',name:'app',showName:'new',storage:{required:true},expectedDefinitionVersion:11});
});
test('lost metadata response preserves original intent and prevents both write replay and guessed restoration',async()=>{
 const actor={identity:{account:'original',namespace:'panel'},origin:'https://panel.example.invalid'},before={id:7,uuid:'a'.repeat(32),name:'app',updateTime:11};
 const r={id:7,original:before,last:before,actorIdentity:actor.identity,origin:actor.origin,commands:[]};let commands=0;
 const h={admin:actor,Blocked:Error,persist(){},async ok(){return {value:before};},async api(){commands++;throw Error('lost response');}};
 await assert.rejects(write(h,r,{showName:'new'}),/lost response/);
 assert.equal(r.commands[0].body.expectedDefinitionVersion,11);assert.equal(r.commands[0].outcome,'unknown');
 await assert.rejects(write(h,r,{showName:'replacement'}),/no replacement write/);
 await assert.rejects(restore(h,r),/no replacement write/);assert.equal(commands,1);
});
test('invalid creates preserve every definition independently of same-run legitimate models and directory order',async()=>{
 const {handlers}=require('./standard_cases.cjs');
 const original={id:7,uuid:'a'.repeat(32),name:'rg-model',description:'original'};
 const peer={id:8,uuid:'b'.repeat(32),name:'rg-metadata-edited',description:'legitimate same-run model'};
 const base='/panel/application/definitions/';
 for(const change of ['none','added','removed','modified','original-modified']){
  let reads=0,writes=0;
  const h={state:{prefix:'rg',fixtures:{model:original},resources:[{kind:'definition',id:7,creation:{ownershipConfirmed:true}}]},admin:{},root:'/workspace/magicTest',persist(){},Blocked:Error,
   path:require('node:path'),fs:{readFileSync(){return JSON.stringify({storage:{required:false}});}},
   async directory(){reads++;if(reads===1)return structuredClone([original,peer]);
    if(reads>3&&change==='added')return [original,peer,{id:9,name:'other'}];
    if(reads>3&&change==='removed')return [original];
    if(reads>3&&change==='modified')return [original,{...peer,description:'changed'}];
    return structuredClone([peer,original]);},
   async ok(actor,method,route){assert.equal(method,'GET');assert.equal(route,base+7);return {value:change==='original-modified'&&reads>3?{...original,description:'changed'}:structuredClone(original)};},
   async api(actor,method,route){assert.equal(method,'POST');assert.equal(route,base);writes++;return {status:200,data:{error:{code:writes===1?7:4,message:writes===2?'model application package prefix is invalid':'only PostgreSQL application storage is supported'},value:null}};},
   good(){return false;},invalid(r){assert.equal(r.data.error.code,4);},check(label,value){assert.ok(value,label);}};
  if(change==='none')await handlers['F011-002'](h);
  else await assert.rejects(handlers['F011-002'](h),/preserves every original definition|preserve the complete original directory|original model remains exact/);
  assert.equal(writes,3);assert.equal(reads,change==='none'?5:4);
 }
});
test('invalid definition creation retains original unknown intent and never accepts an earlier authentication refusal',async()=>{
 const {handlers}=require('./standard_cases.cjs'),model={id:7,uuid:'a'.repeat(32),name:'rg-model'};
 for(const mode of ['lost','auth']){
  let writes=0;
  const resource={kind:'definition',id:7,creation:{ownershipConfirmed:true}};
  const h={state:{prefix:'rg',fixtures:{model},resources:[resource]},admin:{},root:'/workspace/magicTest',path:require('node:path'),
   fs:{readFileSync(){return '{}';}},persist(){},Blocked:Error,async directory(){return [model];},async ok(){return {value:model};},
   async api(){writes++;if(mode==='lost')throw Error('lost original response');return {status:401,data:{error:{code:11},value:null}};},
   good(){return false;},check(label,value){assert.ok(value,label);}};
  await assert.rejects(handlers['F011-002'](h),mode==='lost'?/lost original response/:/exact duplicate\/prefix\/storage/);
  assert.equal(resource.definitionRejections[0].outcome,'unknown');
  await assert.rejects(handlers['F011-002'](h),/no replay/);assert.equal(writes,1);
 }
});
