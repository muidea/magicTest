const { test } = require('node:test');
const assert = require('node:assert/strict');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
test('mixed original business journals route to only their recovery family and keep unrelated unknown writes unchanged', () => {
  const { pendingBusinessReconciliation: select } = require('./cleanup_recovery.cjs');
  const denial = { status: 200, data: { error: { code: 5, message: '读取安装页面需要应用实例运行权限' } } };
  const row = (operation, response, phase = 'created') => ({ kind: 'business-record', phase, commands: [{ outcome: 'unknown', body: { operation }, response }] });
  const update = row('update', denial), create = row('create', { status: 200, data: { value: { id: 'original' } } }),
    lost = row('update'), confirmed = row('create'); confirmed.commands[0].outcome = 'confirmed';
  const cancel = row('update'); cancel.commands[0].body.cancel = true;
  const all = [update, create, lost, confirmed, row('update', denial, 'deleted'), { ...create, kind: 'foreign-resource' }, row('delete', denial), cancel];
  const before = structuredClone(all);
  assert.deepEqual(select(all, 'matrix-write-refusal'), [update]);
  assert.deepEqual(select(all, 'business-create'), [create, cancel]);
  assert.deepEqual(all, before);
  assert.throws(() => select(all, 'guess'), /Unknown/);
});
test('review recovery binds original commands, conditional versions, frozen request and exact installation to immutable cleanup', () => {
  const r = { kind: 'deployment-review-request', id: 7, phase: 'created', commands: [{ outcome: 'unknown', body: { expectedVersion: 2 }, response: { status: 409 } }],
    last: { id: 7, planDigest: 'original' }, installation: { id: 9 }, operation: { id: 7, version: 3 }, placement: { executionInstanceId: 'original-base' } };
  const original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const mutate of [v => v.commands[0].body.expectedVersion++, v => v.commands[0].response.status = 200, v => v.last.planDigest = 'replacement', v => v.installation.id++, v => v.operation.version++, v => v.placement.executionInstanceId = 'replacement']) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
  }
});
test('brand restoration recovery binds exact original profile, last revision, asset journal, actor and origin', () => {
  const resource = { kind: 'branding-profile-restore', collection: '/panel/namespace-branding/', namespace: 'panel', phase: 'created', actorIdentity: { account: 'owner', namespace: 'panel' }, origin: 'https://panel.example', original: { override: { id: 7, resourceVersion: 2 } }, last: { override: { id: 7, resourceVersion: 3 } }, commands: [{ outcome: 'unknown', body: { expectedResourceId: 7, expectedResourceVersion: 3 } }], brandingCommands: [{ outcome: 'unknown', expectedDigest: 'original-bytes' }] };
  const original = { resources: [{ ...structuredClone(resource), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [resource] }, original)[0], resource);
  for (const mutate of [r => r.namespace = 'foreign', r => r.origin = 'https://foreign.example', r => r.actorIdentity.account = 'other', r => r.original.override.id++, r => r.last.override.resourceVersion++, r => r.commands[0].body.expectedResourceId++, r => r.brandingCommands[0].expectedDigest = 'replacement']) {
    const changed = structuredClone(resource); mutate(changed);
    assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
  }
});
test('ordinary-file recovery binds original path, source, bytes and origin to immutable cleanup', () => {
  const r = { kind: 'ordinary-file', id: 7, name: 'original.bin', phase: 'intent', source: 'original-source', relative: 'original/path', path: '/static/share/original.bin', expectedDigest: 'original-digest', expectedSize: 7, origin: 'https://a.example', actorName: 'tenantAdmin', actorIdentity: { account: 'admin', namespace: 'a' } };
  const original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const key of ['source', 'relative', 'path', 'expectedDigest', 'expectedSize', 'origin', 'actorName']) {
    const changed = structuredClone(r); changed[key] = 'replacement';
    assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
  }
});
test('cleanup recovery binds exact immutable owner, origin and credential identity while preserving unknown outcomes', () => {
  const resource = { kind: 'service-graph-credential', collection: '/credentials/', name: 'original', phase: 'created', parentSubscriptionId: 7,
    ownerIdentity: { account: 'admin', namespace: 'tenant-a' }, value: { clientId: 'original-client', credentialId: 8 }, deletion: { outcome: 'unknown' } };
  const state = { resources: [resource] }, original = { resources: [{ ...structuredClone(resource), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup(state, original)[0], resource);
  assert.equal(resource.deletion.outcome, 'unknown');
  for (const mutate of [r => r.value.credentialId++, r => r.ownerIdentity.namespace = 'other', r => r.parentSubscriptionId++, r => r.name = 'replacement']) {
    const changed = structuredClone(state); mutate(changed.resources[0]);
    assert.throws(() => bindOriginalCleanup(changed, original), /differs/);
  }
  assert.throws(() => bindOriginalCleanup(state, { ...original, resources: [...original.resources, ...original.resources] }), /differs/);
  assert.throws(() => bindOriginalCleanup(state, { ...original, resources: original.resources.map(r => ({ ...r, confirmed: true })) }), /differs/);
});
test('DNS recovery accepts only exact pre-connect failure and complete absence; unknown outcome remains original', async () => {
  const { confirmUnsentTemplate } = require('./cleanup_recovery.cjs');
  const identity = { account: 'owner', namespace: 'a' }, origin = 'https://a.local.vpc', collection = '/cas/namespaces/a/role-templates/';
  for (const mode of ['valid', 'timeout', 'wrong-url', 'existing', 'wrong-owner']) {
    const resource = { kind: 'role-template', collection, creation: { actorIdentity: identity, origin, journalId: 'original', outcome: 'unknown', intended: { key: 'original-key' } } };
    const evidence = { caseId: 'F008-002', status: 'blocked', reason: 'apiRequestContext.fetch: getaddrinfo ENOTFOUND a.local.vpc\nCall log:\n  - → POST ' + origin + '/api/v1/web/proxy' + collection + '\n    - content-length: ' + Buffer.byteLength(JSON.stringify(resource.creation.intended)) + '\n' };
    if (mode === 'timeout') evidence.reason = 'Timeout: unknown POST result';
    if (mode === 'wrong-url') evidence.reason = evidence.reason.replace('role-templates', 'accounts');
    const h = { tenantAdmin: { identity: mode === 'wrong-owner' ? { ...identity, namespace: 'b' } : identity, origin }, Blocked: Error, persist() {},
      check(label, condition) { assert.ok(condition, label); }, async directory() { return mode === 'existing' ? [{ key: 'original-key' }] : []; } };
    if (mode === 'valid') { await confirmUnsentTemplate(h, resource, evidence); assert.equal(resource.phase, 'deleted'); assert.equal(resource.creation.outcome, 'unknown'); }
    else { await assert.rejects(confirmUnsentTemplate(h, resource, evidence)); assert.notEqual(resource.phase, 'deleted'); }
  }
});
test('lost credential closes only through original retired parent and independent CAS terminal facts', async () => {
  const { confirmRetiredCredential } = require('./cleanup_recovery.cjs');
  const identity = { account: 'owner', namespace: 'a' }, subscriberRef = { namespace: 'a', accountId: 2, subject: 'account:2' };
  for (const mode of ['valid', 'wrong-name', 'wrong-parent', 'active-client', 'read-failure']) {
    const r = { kind: 'service-graph-credential', collection: '/credentials/', parentSubscriptionId: 7, serviceId: 9, ownerIdentity: identity, actorIdentity: identity, name: 'original', outcome: 'unknown' };
    const parent = { kind: 'service-graph-subscription', id: 7, serviceId: 9, ownerIdentity: identity, collection: '/subscriptions/', requestId: 'original-request', original: { subscriberRef }, confirmed: true, phase: 'deleted', outcome: 'accepted',
      deletion: { outcome: 'accepted', response: { status: 200, data: { error: null, value: { id: 7, service: { id: 9 }, namespace: 'a', subscriberRef, credentials: [{ name: 'original', clientId: 'client-original', credentialId: 3, endpointId: 4 }] } } } } };
    if (mode === 'wrong-name') parent.deletion.response.data.value.credentials[0].name = 'replacement';
    if (mode === 'wrong-parent') parent.id++;
    const calls = [], h = { tenantAdmin: { identity }, Blocked: Error, persist() {}, good: r => r.status === 200 && r.data?.error == null,
      check(label, condition) { assert.ok(condition, label); }, async api(actor, method, route) {
        assert.equal(method, 'GET', 'recovery never reissues or deletes a guessed credential'); calls.push(route);
        if (mode === 'read-failure') return { status: 503, data: { error: { code: 1 } } };
        if (mode === 'active-client' && route.includes('/oauth/clients/')) return { status: 200, data: { error: null, value: { clientId: 'client-original', status: 2 } } };
        return { status: 200, data: { error: { code: 2 }, value: null } };
      } };
    if (mode === 'valid') { await confirmRetiredCredential(h, r, { resources: [parent] }); assert.equal(r.phase, 'deleted'); assert.equal(r.outcome, 'unknown'); assert.equal(r.response, undefined); assert.equal(calls.length, 3); }
    else { await assert.rejects(confirmRetiredCredential(h, r, { resources: [parent] })); assert.notEqual(r.phase, 'deleted'); }
  }
});
test('namespace recovery requires actual owner operation, original DTO and source log without inventing acknowledgement', async () => {
  const { recoverNamespace, recoveredNamespace } = require('./cleanup_recovery.cjs');
  const crypto = require('node:crypto');
  const creationId = 'a'.repeat(32), identity = { account: 'original-admin', namespace: 'panel' }, intended = { name: 'original-tenant', description: 'current run', scope: [], status: 2, startTime: 10, expireTime: 90 };
  const sourceLine = 'namespace provisioning completed namespace=original-tenant creationId=' + creationId + ' elapsed=1s';
  const proof = { name: intended.name, creationId, sourceContainer: 'magiccas', sourceLine, sourceLogSha256: 'sha256:' + crypto.createHash('sha256').update(sourceLine).digest('hex') };
  for (const mode of ['valid', 'wrong-resource', 'changed-input', 'bad-log']) {
    const r = { kind: 'namespace', phase: 'intent', creation: { actorIdentity: identity, origin: 'https://panel.local.vpc', identity: { name: intended.name }, intended: structuredClone(intended), outcome: 'unknown' } };
    const receipt = { creationId, namespaceId: 7, name: intended.name, phase: 'completed', version: 3, namespace: { id: 7, ...intended } };
    if (mode === 'wrong-resource') receipt.namespace.id++;
    if (mode === 'changed-input') receipt.namespace.expireTime++;
    const h = { admin: { identity, origin: r.creation.origin }, Blocked: Error, persist() {}, check(label, condition) { assert.ok(condition, label); },
      async ok(actor, method) { assert.equal(method, 'GET', 'recovery never replays the original POST'); return { value: receipt }; } };
    const actualProof = { ...proof, ...(mode === 'bad-log' ? { sourceLine: sourceLine + ' forged' } : {}) };
    if (mode === 'valid') {
      await recoverNamespace(h, r, actualProof); assert.equal(recoveredNamespace(r), true); assert.equal(r.id, 7);
      assert.equal(r.creation.outcome, 'unknown'); assert.equal(r.creation.response, undefined);
    } else { await assert.rejects(recoverNamespace(h, r, actualProof)); assert.equal(r.id, undefined); }
  }
});
test('compensated unknown namespace requires exact terminal retirement name and independent absence', async () => {
  const { recoverNamespace } = require('./cleanup_recovery.cjs'), crypto = require('node:crypto');
  const creationId = 'a'.repeat(32), requestId = 'b'.repeat(32), identity = { account: 'owner', namespace: 'panel' };
  const sourceLine = 'namespace provisioning completed namespace=original creationId=' + creationId + ' elapsed=1s';
  const retirementLine = 'namespace retirement attempt finished requestId=' + requestId + ' namespaceId=7 phase=completed elapsed=1s failure=""';
  const hash = s => 'sha256:' + crypto.createHash('sha256').update(s).digest('hex');
  const proof = { name: 'original', creationId, sourceContainer: 'magiccas', sourceLine, sourceLogSha256: hash(sourceLine),
    retirement: { namespaceId: 7, expectedVersion: 12, requestId, sourceLine: retirementLine, sourceLogSha256: hash(retirementLine) } };
  for (const mode of ['valid', 'foreign-name', 'pending', 'still-present', 'incomplete-read']) {
    const r = { kind: 'namespace', phase: 'intent', creation: { actorIdentity: identity, origin: 'https://panel.local.vpc', identity: { name: 'original' }, intended: { name: 'original' }, outcome: 'unknown' } };
    const receipt = { namespaceId: 7, requestId, expectedVersion: 12, name: mode === 'foreign-name' ? 'other' : 'original', phase: mode === 'pending' ? 'deleting' : 'completed', version: 4, failure: '' };
    const h = { admin: { identity, origin: r.creation.origin }, Blocked: Error, persist() {}, check(label, condition) { assert.ok(condition, label); },
      async ok(actor, method) { assert.equal(method, 'GET'); return { value: receipt }; },
      async api(actor, method) { assert.equal(method, 'GET'); return mode === 'incomplete-read' ? { status: 503, data: {} } : { status: 200, data: { error: { code: 2 }, value: null } }; },
      async directory() { return mode === 'still-present' ? [{ id: 8, name: 'original' }] : []; } };
    if (mode === 'valid') { await recoverNamespace(h, r, proof); assert.equal(r.phase, 'deleted'); assert.equal(r.creation.outcome, 'unknown'); assert.equal(r.creation.response, undefined); }
    else { await assert.rejects(recoverNamespace(h, r, proof)); assert.equal(r.phase, 'intent'); }
  }
});

test('original subscription cleanup distinguishes two formal requests for the same owner resource', () => {
  const first = { kind: 'service-graph-subscription', id: 177, collection: '/subscriptions/', phase: 'created', requestId: 'original-request-a', serviceId: 9, actorOrigin: 'https://a.local.vpc', receipt: { phase: 'complete', requestId: 'original-request-a' } };
  const second = { ...first, requestId: 'original-request-b', receipt: { phase: 'complete', requestId: 'original-request-b' } };
  const state = { resources: [first, second] }, original = { resources: state.resources.map(r => ({ ...structuredClone(r), confirmed: false })), trace: [] };
  assert.equal(bindOriginalCleanup(state, original).length, 2);
  for (const key of ['requestId', 'serviceId', 'actorOrigin', 'receipt']) {
    const changed = structuredClone(original); changed.resources[0][key] = 'other';
    assert.throws(() => bindOriginalCleanup(state, changed), /differs/);
  }
});

test('retired creator disposition requires immutable account retirement, current absence and real exact tenant manager', async () => {
  const { cleanupRetiredCreator } = require('./cleanup_recovery.cjs');
  for (const mode of ['valid', 'wrong-tenant', 'creator-active', 'unproven-retirement', 'response-lost']) {
    const actorIdentity = { account: 'creator', namespace: 'tenant-a' }, origin = 'https://tenant-a.local.vpc';
    const r = { kind: 'role-template', id: 7, phase: 'created', collection: '/cas/namespaces/tenant-a/role-templates/', creation: { actorIdentity, origin, intended: { key: 'original' }, outcome: 'accepted', response: { status: 200, data: { error: null, value: { id: 7, key: 'original' } } } } };
    const account = { kind: 'account', id: 3, phase: 'deleted', confirmed: true, collection: '/cas/namespaces/tenant-a/accounts/', creation: { intended: { account: 'creator' } }, deletion: { outcome: 'acknowledged', response: { status: 200, data: { error: null, value: { id: 3, account: 'creator' } } } } };
    if (mode === 'unproven-retirement') account.confirmed = false;
    let writes = 0, deleted = false;
    const missing = { status: 200, data: { error: { code: 2 }, value: null } };
    const h = { admin: { identity: { account: 'root', namespace: 'panel' } }, tenantAdmin: { identity: { account: 'admin', namespace: mode === 'wrong-tenant' ? 'tenant-b' : 'tenant-a' }, origin }, Blocked: Error, persist() {}, good: r => r.status === 200 && r.data?.error == null, check(label, ok) { assert.ok(ok, label); }, async api(actor, method, route) {
      if (route.endsWith('/accounts/3')) return mode === 'creator-active' ? { status: 200, data: { error: null, value: { id: 3 } } } : missing;
      if (method === 'GET') return deleted ? missing : r.creation.response;
      assert.deepEqual(actor.identity, h.tenantAdmin.identity); assert.equal(method, 'DELETE'); assert.equal(r.recovery.outcome, 'unknown'); writes++;
      if (mode === 'response-lost') throw Error('response lost');
      deleted = true; return r.creation.response;
    } };
    if (mode === 'valid') { await cleanupRetiredCreator(h, r, { resources: [account] }); assert.equal(r.phase, 'deleted'); assert.equal(r.creation.actorIdentity.account, 'creator'); assert.equal(r.recovery.actorIdentity.account, 'admin'); assert.equal(writes, 1); }
    else { await assert.rejects(cleanupRetiredCreator(h, r, { resources: [account] })); if (mode === 'response-lost') { await assert.rejects(cleanupRetiredCreator(h, r, { resources: [account] })); assert.equal(writes, 1); } else assert.equal(writes, 0); }
  }
});

test('only exact pre-dispatch session refusal plus complete owner absence closes a creation intent', async () => {
  const { confirmProxySessionRefusal } = require('./cleanup_recovery.cjs');
  for (const mode of ['valid', 'namespace', 'timeout', 'generic-503', 'foreign-actor', 'existing-name', 'existing-uuid', 'incomplete-read']) {
    const identity = { account:'original',namespace:'panel' }, uuid = 'a'.repeat(32), intended = {name:'original-resource',uuid};
    const r = {kind:mode==='namespace'?'namespace':'definition',phase:'intent',collection:mode==='namespace'?'/panel/namespace-onboardings/':'/panel/application/definitions/',creation:{journalId:'original',outcome:'unconfirmed',actorIdentity:identity,origin:'https://panel.example.invalid',intended,identity:mode==='namespace'?{name:intended.name}:{uuid},response:{status:503,data:{text:'application session refresh is still in progress; retry shortly\n'}}}};
    if(mode==='timeout') delete r.creation.response;
    if(mode==='generic-503') r.creation.response.data.text='upstream unavailable\n';
    const reads=[],h={Blocked:Error,admin:{identity:mode==='foreign-actor'?{...identity,account:'other'}:identity,origin:r.creation.origin},persist(){},check(label,c){assert.ok(c,label);},async directory(actor,route){reads.push(route);if(mode==='incomplete-read')throw Error('pagination incomplete');return mode==='existing-name'?[{name:intended.name}]:mode==='existing-uuid'?[{uuid}]:[];},api(){throw Error('no write or replay permitted');}};
    if(['valid','namespace'].includes(mode)) {await confirmProxySessionRefusal(h,r);assert.equal(r.phase,'deleted');assert.equal(r.creation.outcome,'unconfirmed');assert.equal(r.reconciliation.noCommandReplayed,true);assert.deepEqual(reads,[mode==='namespace'?'/cas/namespaces/':r.collection]);}
    else {await assert.rejects(confirmProxySessionRefusal(h,r));assert.equal(r.phase,'intent');}
  }
});


test('original failed namespace closes only with terminal owner rollback and independent ID/name absence',async()=>{
 const {confirmRolledBackNamespace}=require('./cleanup_recovery.cjs'),crypto=require('node:crypto');
 for(const mode of ['rolled-back','pending','still-present','wrong-owner']){
  const identity={account:'original',namespace:'panel'},origin='https://panel.example.invalid',creationId='a'.repeat(32),line='namespace provisioning failed namespace=original creationId='+creationId+' stage=administrator';
  const r={kind:'namespace',collection:'/panel/namespace-onboardings/',phase:'intent',creation:{outcome:'unknown',actorIdentity:identity,origin,intended:{name:'original'}}};
  const proof={name:'original',creationId,sourceContainer:'magiccas',sourceLine:line,sourceLogSha256:'sha256:'+crypto.createHash('sha256').update(line).digest('hex')};
  const h={admin:{identity:mode==='wrong-owner'?{...identity,account:'other'}:identity,origin},Blocked:Error,persist(){},check(label,c){assert.ok(c,label);},async ok(){return {value:{creationId,name:'original',namespaceId:7,phase:mode==='pending'?'administrator':'rolled-back',version:2,failure:'original cause'}};},async api(a,m){assert.equal(m,'GET');return mode==='still-present'?{status:200,data:{value:{id:7}}}:{status:200,data:{error:{code:2},value:null}};},async directory(){return [];}};
  if(mode==='rolled-back'){await confirmRolledBackNamespace(h,r,proof);assert.equal(r.phase,'deleted');assert.equal(r.creation.outcome,'unknown');assert.equal(r.reconciliation.noCommandReplayed,true);}
  else{await assert.rejects(confirmRolledBackNamespace(h,r,proof));assert.equal(r.phase,'intent');}
 }
});
test('runtime policy recovery binds immutable conditional commands, full inventory, original installations and retained owner revision', () => {
  const r = { kind: 'runtime-policy-probe', id: 'original-journal', phase: 'created', origin: 'https://original.invalid', policyId: 'policy1',
    actorIdentity: { account: 'original', namespace: 'panel' }, before: [{ id: 'policy1', version: 2 }], last: [{ id: 'policy1', version: 3 }],
    inventory: [{ id: 'gateway1', incarnation: 'original' }], installations: [{ id: 7, receipt: { frozen: true } }], commands: [{ confirmed: false, body: { expectedVersion: 2 }, response: { status: 200 } }] };
  const original = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, original)[0], r);
  for (const mutate of [x => x.origin += '.foreign', x => x.policyId = 'replacement', x => x.actorIdentity.namespace = 'other',
    x => x.before[0].version++, x => x.last[0].version++, x => x.inventory[0].incarnation = 'new', x => x.installations[0].receipt.frozen = false,
    x => x.commands[0].confirmed = true, x => x.commands[0].body.expectedVersion++, x => x.commands[0].response.status = 409]) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs/);
  }
});
test('id-less business, member retirement and source effect cleanup bind one entire original snapshot without inventing ids', () => {
  const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
  for (const kind of ['business-record', 'member-access-retirement', 'source-effect-scenario']) {
    const first = { kind, phase: 'created', origin: 'https://original.invalid',
      actorIdentity: { account: 'original', namespace: 'panel' }, identity: { installationId: '11', deploymentId: 'original' },
      scenarioDefinitionId: 31, installation: { id: 11 }, recordId: '21', targets: [{ id: 41, version: 1 }],
      commands: [{ body: { operationId: 'original' }, outcome: 'unknown', response: { status: 200, data: { error: { code: 2 } } } }] };
    const peer = structuredClone(first); peer.identity.installationId = '12'; peer.installation.id = 12; peer.recordId = '22';
    const original = { resources: [first, peer].map(r => ({ ...structuredClone(r), confirmed: false, error: 'preserved refusal' })), trace: [] };
    assert.deepEqual(bindOriginalCleanup({ resources: [first, peer] }, original), [first, peer]);
    for (const mutate of [r => r.identity.installationId = 'other', r => r.installation.id++, r => r.recordId = 'other',
      r => r.commands[0].body.operationId = 'other', r => r.commands[0].outcome = 'confirmed', r => r.commands[0].response.status = 409,
      r => r.scenarioDefinitionId++, r => r.targets[0].version++, r => r.phase = 'prepared',
      r => r.actorIdentity.account = 'other', r => r.extra = true, r => r.error = 'masked', r => r.confirmed = false]) {
      const changed = structuredClone(first); mutate(changed);
      assert.throws(() => bindOriginalCleanup({ resources: [changed] }, original), /differs from exact original/);
    }
    const duplicate = structuredClone(original); duplicate.resources.push(structuredClone(duplicate.resources[0]));
    assert.throws(() => bindOriginalCleanup({ resources: [first] }, duplicate), /differs from exact original/);
    assert.equal(Object.hasOwn(first, 'id'), false);
  }
});
