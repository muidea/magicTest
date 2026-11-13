// Downloaded contracts and clipboard examples are inputs, never shell programs.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const graph = require('./service_graph.cjs');
const generated = require('./generated_service_cases.cjs');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const schemaKeys = ['type','format','title','description','nullable','readOnly','writeOnly','required','minimum','maximum','minLength','maxLength','minItems','maxItems','pattern','default','enum'];
const currentRoleRefusal = response => response.status === 401 && response.data?.error?.code === 5 && response.data.error.message === '当前角色未授予此资源权限' && response.data.value == null;
function publicSchema(schema) {
  if (!schema) return undefined;
  const out = Object.fromEntries(schemaKeys.filter(k => schema[k] !== undefined).map(k => [k, schema[k]]));
  if (schema.items) out.items = publicSchema(schema.items);
  if (schema.properties) out.properties = Object.fromEntries(Object.entries(schema.properties).map(([k,v]) => [k,publicSchema(v)]));
  return out;
}
function copiedRequest(text, origin, serviceKey, operation) {
  const lines = text.split(' \\\n');
  const first = /^curl --request (GET|POST) '([^'\r\n]+)'$/.exec(lines.shift() || '');
  if (!first || first[1] !== operation.method || lines.shift() !== "  --header 'Authorization: ApiKey <API_KEY>'") throw Error('Copied service guide has unexpected request grammar');
  const url = new URL(first[2]), route = operation.pathTemplate.replace('/gateway/managed-services/', '/gateway/services/');
  const template = new URL(route, origin);
  const parts = template.pathname.split('/'), actual = url.pathname.split('/');
  if (url.origin !== origin || url.username || url.password || url.hash || !template.pathname.startsWith('/api/v1/gateway/services/' + serviceKey + '/') ||
      parts.length !== actual.length || parts.some((p,i) => /^\{[^}]+\}$/.test(decodeURIComponent(p)) ? decodeURIComponent(actual[i]) !== '<' + decodeURIComponent(p).slice(1,-1) + '>' && actual[i] !== '1' : p !== actual[i])) throw Error('Copied service guide has unexpected tenant, service or operation path');
  const allowed = new Set((operation.parameters || []).filter(p => p.in === 'query').map(p => p.name));
  if ([...url.searchParams.keys()].some(k => !allowed.has(k)) || (operation.parameters || []).some(p => p.in === 'query' && p.required && !url.searchParams.has(p.name))) throw Error('Copied service guide has unexpected query parameters');
  let body;
  if (operation.requestBody) {
    if (operation.requestBody.contentType !== 'application/json' || lines.shift() !== "  --header 'Content-Type: application/json'") throw Error('Copied guide has unsupported body encoding');
    const raw = /^  --data-raw '([^']*)'$/.exec(lines.shift() || '');
    // JSON may be pretty printed; parse bytes inside one quoted argument only.
    if (!raw) throw Error('Copied guide has unexpected JSON body grammar');
    body = JSON.parse(raw[1]);
  }
  if (lines.length) throw Error('Copied guide has trailing shell text or headers');
  return { url, method:first[1], body };
}
function matchesSchema(value, schema) {
  if (!schema) return true;
  if (value === null) return schema.nullable === true;
  if (schema.enum && !schema.enum.some(v => same(v,value))) return false;
  switch(schema.type) {
    case 'object': return typeof value === 'object' && !Array.isArray(value) && (schema.required || []).every(k => Object.hasOwn(value,k)) && Object.entries(schema.properties || {}).every(([k,s]) => !Object.hasOwn(value,k) || matchesSchema(value[k],s));
    case 'array': return Array.isArray(value) && (schema.minItems === undefined || value.length >= schema.minItems) && (schema.maxItems === undefined || value.length <= schema.maxItems) && value.every(v => matchesSchema(v,schema.items));
    case 'integer': case 'number': return typeof value === 'number' && Number.isFinite(value) && (schema.type !== 'integer' || Number.isSafeInteger(value)) && (schema.minimum === undefined || value >= schema.minimum) && (schema.maximum === undefined || value <= schema.maximum);
    case 'string': return typeof value === 'string' && (schema.minLength === undefined || [...value].length >= schema.minLength) && (schema.maxLength === undefined || [...value].length <= schema.maxLength) && (!schema.pattern || new RegExp(schema.pattern,'u').test(value));
    case 'boolean': return typeof value === 'boolean';
    case undefined: return true;
    default: throw Error('Fixture schema vocabulary is not covered: ' + schema.type);
  }
}
async function endpointTemplates(h, credential, keys) {
  const r = credential.resource, owner = [h.admin,h.tenantAdmin,h.otherTenantAdmin].find(a => a && same(a.identity,r.ownerIdentity));
  if (!owner || r.phase !== 'created' || r.outcome !== 'accepted' || r.value?.endpointId !== credential.value.endpointId ||
      (r.endpointAuthorityOrigin && r.endpointAuthorityOrigin !== owner.origin) ||
      r.endpointAuthorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original Endpoint template command or owner unresolved; no replacement replay');
  r.endpointAuthorityOrigin ||= owner.origin;
  const base = '/cas/namespaces/' + owner.identity.namespace + '/', route = base + 'endpoints/' + r.value.endpointId;
  const before = (await h.ok(owner,'GET',route)).value;
  const query = base + 'subject-role-bindings/?' + new URLSearchParams({subjectId:r.value.endpointId + '|=',subjectType:'endpoint|='});
  const originalBindings = await h.directory(owner,query);
  const c = {method:'PUT',route:route + '/role-templates',body:{roleTemplateKeys:[...keys]},before,originalBindings,outcome:'unknown'};
  (r.endpointAuthorityCommands ||= []).push(c); h.persist();
  c.response = await h.api(owner,c.method,c.route,c.body); h.persist();
  h.check('Formal exact Endpoint template replacement acknowledged',h.good(c.response),c.response);
  const after = (await h.ok(owner,'GET',route)).value, bindings = await h.directory(owner,query);
  const templateRows = bindings.filter(b => b.sourceType === 'template' && b.status === 2);
  const independent = originalBindings.filter(b => b.sourceType !== 'template');
  h.check('Independent CAS preserves original Endpoint, account ceiling, subscription source and gateway OAuth scope while replacing only selected templates',
    before.id === r.value.endpointId && after.id === before.id && after.account?.id === before.account?.id && after.status === 2 && after.scope === before.scope &&
    same((after.templateRefs || []).map(t => t.key).sort(),[...keys].sort()) && keys.every(k => templateRows.some(b => b.sourceKey === k)) && templateRows.every(b => keys.includes(b.sourceKey)) &&
    same(bindings.filter(b => b.sourceType !== 'template'),independent),{after,bindings});
  c.after = after; c.bindings = bindings; c.outcome = 'confirmed'; h.persist();
}
async function reconcileEndpointTemplateRefusal(h, r) {
  const pending = r.endpointAuthorityCommands?.filter(c => c.outcome === 'unknown');
  const owner = [h.admin, h.tenantAdmin, h.otherTenantAdmin].find(a => a && same(a.identity, r.ownerIdentity));
  if (!owner || r.kind !== 'service-graph-credential' || r.phase !== 'created' || r.outcome !== 'accepted' || pending?.length !== 1 || r.endpointAuthorityOrigin !== owner.origin) throw new h.Blocked('Endpoint refusal recovery requires original credential, template intent and owner');
  const c = pending[0], base = '/cas/namespaces/' + owner.identity.namespace + '/', route = base + 'endpoints/' + r.value.endpointId;
  if (c.method !== 'PUT' || c.route !== route + '/role-templates' || c.body.roleTemplateKeys.length !== 1 || c.before?.id !== r.value.endpointId || !Array.isArray(c.originalBindings) || c.response?.status !== 200 || c.response.data?.error?.code !== 5 || c.response.data.value != null) throw new h.Blocked('Original Endpoint template refusal identity is incomplete');
  const templates = await h.directory(owner, base + 'role-templates/'), matches = templates.filter(t => t.key === c.body.roleTemplateKeys[0] && t.status === 2 && t.subjectType === 'endpoint');
  const tracked = h.state.resources.filter(t => t.kind === 'role-template' && t.phase !== 'deleted' && t.collection === base + 'role-templates/' && t.creation?.ownershipConfirmed && t.creation.origin === owner.origin && same(t.creation.actorIdentity, owner.identity) && t.creation.intended.key === c.body.roleTemplateKeys[0]);
  h.check('Original selected Endpoint template retains exact rejected role from the acknowledged account-ceiling refusal', tracked.length === 1 && matches.length === 1 && matches[0].id === tracked[0].id && same(matches[0].roleRefs, tracked[0].creation.intended.roleRefs) && matches[0].roleRefs?.some(ref => c.response.data.error.message === 'endpoint role ' + ref.module + '/' + ref.key + ' exceeds account authority'), matches);
  const endpoint = (await h.ok(owner, 'GET', route)).value;
  const bindings = await h.directory(owner, base + 'subject-role-bindings/?' + new URLSearchParams({ subjectId: r.value.endpointId + '|=', subjectType: 'endpoint|=' }));
  h.check('Formal owner confirms complete original Endpoint and all independent bindings unchanged after account-ceiling refusal', same(endpoint, c.before) && same(bindings, c.originalBindings), { endpoint, bindings });
  const account = (await h.ok(owner, 'GET', base + 'accounts/' + endpoint.account.id)).value;
  const accountBindings = await h.directory(owner, base + 'subject-role-bindings/?' + new URLSearchParams({ subjectId: endpoint.account.id + '|=', subjectType: 'account|=' }));
  h.check('Independent account owner reads retain the original Endpoint account identity and exact binding subject',
    account.id === c.before.account.id && account.account === c.before.account.account && accountBindings.every(b => b.subjectId === account.id && b.subjectType === 'account'), { account, accountBindings });
  c.disposition = { proof: 'Exact original account-ceiling refusal before template replacement, independently unchanged complete Endpoint and bindings; no command replay. Original failed result retained.', endpoint, bindings, template: matches[0], account, accountBindings };
  c.outcome = 'rejected-account-ceiling-and-unchanged'; h.persist(); return { endpointId: r.value.endpointId, proof: c.disposition.proof };
}
async function download(h, actor, name) {
  const pending = actor.page.waitForEvent('download');
  await actor.page.getByRole('button',{name,exact:true}).click();
  const file = await pending;
  if (await file.failure()) throw new h.Blocked('Original service document download failed');
  const bytes = h.fs.readFileSync(await file.path()), value = JSON.parse(bytes);
  h.observe({kind:'actual-service-document',filename:file.suggestedFilename(),sha256:'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'),value});
  return {value,text:bytes.toString()};
}
function verifyDocument(h, document, metadata) {
  h.check('Actual OpenAPI document contains exactly the original frozen operation set',document.openapi === '3.0.3' && document.info.version === metadata.version && Object.values(document.paths).flatMap(p => Object.keys(p)).length === metadata.operations.length,document);
  for (const op of metadata.operations) {
    const path = op.pathTemplate.replace('/gateway/managed-services/','/gateway/services/'), entry = document.paths[path]?.[op.method.toLowerCase()];
    h.check('Downloaded method/path and public request schema match the exact frozen owner contract',!!entry && entry.operationId === metadata.serviceKey + '.' + op.key &&
      (op.parameters || []).every(p => entry.parameters.some(v => v.name === p.name && v.in === p.in && v.required === (p.in === 'path' || p.required) && same(v.schema,publicSchema(p.schema) || {type:'string'}))) &&
      (!op.requestBody || same(entry.requestBody?.content[op.requestBody.contentType]?.schema,publicSchema(op.requestBody.schema))),{operation:op,entry});
    const responses = op.responses || (op.responseBody ? {'200':op.responseBody} : {});
    for (const [status,response] of Object.entries(responses)) h.check('Downloaded response schema matches the frozen owner declaration',same(entry.responses[status]?.content?.[response.contentType || 'application/json']?.schema,publicSchema(response.schema)));
  }
}
async function guide(h, actor, service, metadata, credential, substitute, verify, label) {
  const page = actor.page;
  await page.context().grantPermissions(['clipboard-read','clipboard-write'],{origin:actor.origin});
  await page.goto(actor.origin + '/workbench/services/' + service.id + '/?source=portal',{waitUntil:'networkidle'});
  await page.getByRole('tab',{name:'接入说明',exact:true}).click();
  await page.locator('pre').waitFor();
  const openapi = await download(h,actor,'下载 OpenAPI'), contract = await download(h,actor,'下载接口合同');
  verifyDocument(h,openapi.value,metadata);
  h.check('Downloaded public contract retains exact original digest and operations without private transport or secrets',contract.value.digest === metadata.digest && same(contract.value.operations,metadata.operations.map(({upstreamPath,...op}) => ({...op,pathTemplate:op.pathTemplate.replace('/gateway/managed-services/','/gateway/services/')}))) &&
    [openapi.text,contract.text].every(text => !text.includes(credential.apiKey) && !text.includes('clientSecret') && !text.includes('upstreamPath')));
  for (const [i,op] of metadata.operations.entries()) {
    if (i) {
      await page.getByRole('combobox',{name:'调用示例操作',exact:true}).press('ArrowDown');
      await page.getByTitle(op.method + ' ' + (op.showName || op.name),{exact:true}).click();
    }
    const sample = page.locator('.ant-typography').filter({has:page.locator('pre')});
    await sample.getByRole('button',{name:'复制',exact:true}).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText()), parsed = copiedRequest(copied,actor.origin,service.key,op);
    await substitute(parsed,op);
    h.check('Actual example body satisfies its frozen public schema before sending',!op.requestBody || matchesSchema(parsed.body,op.requestBody.schema));
    const result = await invoke(actor,parsed,credential.apiKey);
    h.observe({kind:'actual-copied-service-call',label,operation:op.key,example:copied,url:parsed.url.toString(),body:parsed.body,result});
    const response = op.responses?.[String(result.status)] || (result.status === 200 ? op.responseBody : undefined);
    h.check('Actual copied sample reaches the intended successful public operation and declared JSON response',result.status === 200 && (!response || matchesSchema(result.data,response.schema)),result);
    await verify(parsed,op,result);
  }
  await h.screenshot(actor,label);
}
async function invoke(actor, parsed, apiKey) {
  return actor.page.evaluate(async ({url,method,body,apiKey}) => {
    const response = await fetch(url,{method,credentials:'omit',headers:{Authorization:'ApiKey ' + apiKey,...(body === undefined ? {} : {'Content-Type':'application/json'})},...(body === undefined ? {} : {body:JSON.stringify(body)}),signal:AbortSignal.timeout(15000)});
    const text = await response.text(); let data; try {data=JSON.parse(text);} catch {data={text:text.slice(0,500)};}
    return {status:response.status,data};
  },{url:parsed.url.toString(),method:parsed.method,body:parsed.body,apiKey});
}
async function documentedReader(h, context) {
  const authority = require('./application_authority_cases.cjs'), base = '/cas/namespaces/panel/';
  const ordinary = (await h.directory(h.admin, base + 'role-templates/')).filter(t =>
    t.key === 'portal-basic-user' && t.systemManaged && t.subjectType === 'account' && t.status === 2);
  h.check('Documented subscriber uses one existing ordinary functional profile', ordinary.length === 1 && ordinary[0].roleRefs?.length > 0);
  const role = { module: '/applications/' + context.identity.deploymentId, key: 'application-data-read' };
  const refs = [...new Map([...ordinary[0].roleRefs, role].map(ref => [JSON.stringify([ref.module, ref.key]), structuredClone(ref)])).values()];
  const access = [{ applicationUuid: context.identity.deploymentId, accessLevel: 'viewer' }];
  const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-documented-reader', name: '接口文档普通读取账号',
    subjectType: 'account', status: 2, roleRefs: refs, applicationAccess: access }, 'role-template');
  const member = await authority.account(h, 'documented-reader');
  await authority.assign(h, member, group, access);
  return member.actor;
}
async function contracts(h) {
  const external = await graph.fixture(h,'openapi_external',{},'tenantAdmin',{version:'1',operations:[
    {key:'probe',name:'Documented GET',method:'GET',upstreamPath:'/probe',parameters:[{name:'marker',in:'query',required:true,schema:{type:'string',minLength:1,maxLength:64}}],responseBody:{contentType:'application/json',schema:{type:'object',required:['marker','method'],properties:{marker:{type:'string'},method:{type:'string'}}}}},
    {key:'submit',name:'Documented POST',method:'POST',upstreamPath:'/submit',parameters:[{name:'marker',in:'query',required:true,schema:{type:'string',minLength:1,maxLength:64}}],requestBody:{contentType:'application/json',required:true,schema:{type:'object',required:['count','enabled'],properties:{count:{type:'integer',minimum:0,maximum:3},enabled:{type:'boolean'}}},example:{count:0,enabled:false}},responseBody:{contentType:'application/json',schema:{type:'object',required:['marker','method','body'],properties:{marker:{type:'string'},method:{type:'string'},body:{type:'string'}}}}}
  ]});
  const externalSub = await graph.subscribe(h,external), externalKey = await graph.credential(h,externalSub);
  const externalMetadata = (await h.ok(h.user,'GET','/portal/service/debug/' + external.service.id)).value;
  const externalOwner = (await h.ok(h.tenantAdmin,'GET',graph.services + external.service.id)).value;
  const externalOptions = JSON.parse(externalOwner.options), externalContract = externalOptions.publishedContract;
  h.check('Independent formal owner retains original author contract and exact published routing snapshot', externalOwner.id === external.service.id && externalOwner.key === external.service.key &&
    same(externalOptions.contract, JSON.parse(external.service.options).contract) && externalOptions.publishedAddress === external.up.address && externalContract?.serviceKey === external.service.key &&
    same(externalContract.operations.map(({ upstreamPath, ...op }) => op), externalMetadata.operations));
  await guide(h,h.user,external.service,externalMetadata,externalKey,async parsed => {parsed.url.searchParams.set('marker',crypto.randomBytes(12).toString('hex'));},async (parsed,op,result) => {
    const received = external.up.requests.filter(r => r.marker === parsed.url.searchParams.get('marker'));
    const original = externalContract.operations.filter(v => v.key === op.key);
    h.check('Downloaded external sample reaches controlled real upstream exactly once with original method/query/body and no forwarded caller credential',original.length === 1 && received.length === 1 && received[0].method === op.method && op.method === original[0].method && received[0].path === original[0].upstreamPath && !received[0].authorizationPresent && result.data.marker === received[0].marker &&
      (parsed.body === undefined || same(JSON.parse(received[0].body),parsed.body)),received);
  },'external-openapi-copied-samples');
  const f = await fixture(h), manager = await business.member(h,'manager'), context = await business.runtime(h,f,0,manager), rows = [];
  let primary, credential;
  try {
    const { installationUnchanged } = require('./deployment_review_cases.cjs');
    const installationBefore = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + f.installations[0].id)).value;
    h.check('Documentation fixture starts from the exact ready installation and frozen artifact identity',
      installationBefore?.status === 'ready' && business.installationMatches(f, installationBefore, context.identity));
    const reader = await documentedReader(h, context);
    const row = await business.create(h,context,'documented-internal-get'); rows.push(row);
    const before = await generated.snapshot(h), source = f.installations[0].receipt.runtimeApplicationUuid;
    const caps = before[generated.capabilities].filter(c => c.providerKey === source && c.providerType === 'application' && c.kind === 'get' && c.status === 1);
    h.check('Internal documentation selects one exact original installed unoccupied GET capability',caps.length === 1 && !before[generated.bindings].some(b => b.capability?.id === caps[0].id));
    const r = generated.intent(h,h.state.prefix + '_openapi_internal',[caps[0].id],source);
    await generated.converge(h,r,[caps[0].id],'内部文档真实调用');
    const p = r.last.publications[0];
    await generated.mutation(h,r,'PUT',generated.publications + p.id,{service:{id:r.serviceId},status:1,visibleScope:'panel',allowSubscription:true,requireApproval:false,maxSubscriptions:2,maxQPS:0,dailyQuota:0},async (response,all) => {
      h.check('Original internal publication independently permits ordinary subscriptions',h.good(response) && all[generated.publications].some(v => v.id === p.id && v.allowSubscription && !v.requireApproval));
    });
    await generated.publish(h,r);
    const internal = {service:r.last.service,publication:r.last.publications[0],ownerIdentity:structuredClone(h.admin.identity)};
    const template = await h.create('/cas/namespaces/panel/role-templates/',{key:h.state.prefix + '-documented-endpoint-read',name:'内部文档读取角色',subjectType:'endpoint',status:2,applicationAccess:[],roleRefs:[{module:'/applications/' + context.identity.deploymentId,key:'application-data-read'}]},'role-template');
    const subscription = await graph.subscribe(h,internal,reader); credential = await graph.credential(h,subscription,'internal-guide');
    const endpoint = (await h.ok(h.admin,'GET','/cas/namespaces/panel/endpoints/' + credential.value.endpointId)).value;
    const self = (await h.ok(reader,'GET','/api/v1/web/session/')).value;
    h.check('Internal Key belongs to original ordinary member ceiling and initially has no implicit application role',endpoint.account?.id === self.account.id && !(endpoint.effectiveRoles || []).some(v => v.module === '/applications/' + context.identity.deploymentId),endpoint);
    const metadata = (await h.ok(reader,'GET','/portal/service/debug/' + internal.service.id)).value;
    h.check('Internal frozen interface describes only the selected installed GET capability',metadata.operations.length === 1 && metadata.operations[0].method === 'GET' && metadata.operations[0].key === caps[0].key,metadata);
    const target = new URL(metadata.operations[0].pathTemplate.replace(/\{id\}/g,row.recordId),reader.origin);
    const parsed = {url:target,method:'GET'};
    const refused = await invoke(reader,parsed,credential.apiKey);
    h.check('Original valid subscribed Key is rejected by exact application current-role gate before explicit Endpoint grant',currentRoleRefusal(refused),refused);
    await endpointTemplates(h,credential,[template.key]);
    await guide(h,reader,internal.service,metadata,credential,async request => {
      request.url.pathname = request.url.pathname.replace(/%3Cid%3E|\{id\}/gi,row.recordId);
      // Numeric examples are placeholders, not the original owned record ID.
      const parts = metadata.operations[0].pathTemplate.split('/');
      const actual = request.url.pathname.split('/');
      parts.forEach((part,i) => {if(part === '{id}') actual[i] = row.recordId;}); request.url.pathname = actual.join('/');
    },async (_,op,result) => {
      const original = await business.record(h,manager,row);
      h.check('Real internal copied sample equals independent ordinary-member owner record and original primary key',h.good(original) && same(result.data.value,original.data.value) && String(result.data.value.id) === row.recordId,{result,original});
    },'internal-openapi-copied-sample');
    await endpointTemplates(h,credential,[]);
    const revoked = await invoke(reader,parsed,credential.apiKey);
    h.check('Same original ApiKey loses internal data access immediately after exact Endpoint template revocation',currentRoleRefusal(revoked),revoked);
    await graph.retireCredential(h,credential);
    await graph.retire(h,subscription);
    await generated.cleanup(h,r);
    h.check('Documented internal lifecycle preserves exact original installed source',installationUnchanged(installationBefore,(await h.ok(h.admin,'GET','/panel/application/installations/' + f.installations[0].id)).value));
  } catch(error) {primary=error;throw error;}
  finally {
    try {
      if (credential?.resource.phase === 'created' && credential.resource.endpointAuthorityCommands?.at(-1)?.outcome === 'confirmed' && credential.resource.endpointAuthorityCommands.at(-1).body.roleTemplateKeys.length) await endpointTemplates(h,credential,[]);
    } catch(error) {h.observe({kind:'original-endpoint-template-revocation-open',message:error.message});if(!primary)throw error;}
    finally {await business.finishCleanup(h,rows.reverse(),primary);}
  }
}
contracts.actors = ['user','tenantAdmin']; contracts.transport = 'owner-api';
module.exports = {handlers:{'F039-001':contracts},copiedRequest,matchesSchema,publicSchema,endpointTemplates,verifyDocument,currentRoleRefusal,reconcileEndpointTemplateRefusal,documentedReader};
