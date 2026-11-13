const { test } = require('node:test');
const assert = require('node:assert/strict');
const { assign, reconcile } = require('./application_authority_cases.cjs');
const { guardFixtureAccountCleanup } = require('./resource_lifecycle.cjs');
const { finishCleanup } = require('./business_cases.cjs');
test('explicit original retirement resume keeps key/epoch and refuses actor drift, lost recovery or a new operation', async () => {
  const { resumeRejectedRetirement } = require('./application_authority_cases.cjs');
  for (const mode of ['exact', 'completed', 'actor', 'key', 'epoch', 'foreign-installation', 'wrong-error', 'lost']) {
    const actor = { origin: 'https://panel.test', identity: { account: 'original', namespace: 'panel' } };
    const before = { id: 9, installationId: 7, deploymentId: 'original', namespace: 'panel', revisionDigest: 'digest', accountId: 3,
      assignmentId: 8, accessLevel: '', expectedEpoch: 1, submissionId: 'a'.repeat(32), requestKey: 'b'.repeat(64),
      requestedBy: { namespace: 'panel', subject: 'account:1' }, status: 'prepared', version: 1, createTime: 10, updateTime: 10 };
    const c = { route: '/panel/application/installations/7/access-retirements/', outcome: 'unknown', body: {
      submissionId: before.submissionId, accountId: 3, assignmentId: 8, expectedEpoch: 1, accessLevel: '' },
      response: { status: 200, data: { value: before } }, execution: {
        route: '/panel/application/installations/7/access-operations/9/retire', body: { expectedVersion: 1, resumeOriginal: false },
        response: { status: 409, data: { error: { code: 19, message: 'application lifecycle changed before commit' } } } } };
    const r = { origin: actor.origin, actorIdentity: structuredClone(actor.identity), active: true, accountId: 3, assignmentId: 8,
      installation: { id: 7, deploymentId: 'original', sourceDigest: 'digest' }, commands: [{ outcome: 'confirmed', completed: {
        status: 'completed', accessLevel: 'manager', assignmentId: 8, requestedBy: before.requestedBy } }, c] };
    let current = structuredClone(before), writes = 0;
    const h = { admin: actor, Blocked: Error, persist() {}, good: x => !!x && x.status === 200 && !x.data.error,
      check: (label, value) => assert.ok(value, label), async ok() { return { value: structuredClone(current) }; },
      async api(_, method, route, body) {
        writes++; assert.equal(method, 'POST'); assert.equal(route, c.execution.route);
        assert.deepEqual(body, { expectedVersion: current.version, resumeOriginal: true });
        current = { ...current, status: 'completed', version: 4, updateTime: 20 };
        if (mode === 'lost') throw Error('lost recovery response');
        return { status: 200, data: { value: structuredClone(current) } };
      } };
    if (mode === 'completed') current = { ...current, status: 'completed', version: 4, updateTime: 20 };
    if (mode === 'actor') actor.identity.account = 'other';
    if (mode === 'key') current.requestKey = 'c'.repeat(64);
    if (mode === 'epoch') current.expectedEpoch++;
    if (mode === 'foreign-installation') current.installationId++;
    if (mode === 'wrong-error') c.execution.response.data.error.message = 'another conflict';
    if (['exact', 'completed'].includes(mode)) {
      await resumeRejectedRetirement(h, r); assert.equal(c.outcome, 'confirmed'); assert.equal(r.active, false);
      await resumeRejectedRetirement(h, r); assert.equal(writes, mode === 'exact' ? 1 : 0);
    } else if (mode === 'wrong-error') {
      await resumeRejectedRetirement(h, r); assert.equal(writes, 0); assert.equal(c.outcome, 'unknown');
    } else {
      await assert.rejects(resumeRejectedRetirement(h, r));
      if (mode === 'lost') await assert.rejects(resumeRejectedRetirement(h, r), /no resume replay/);
      assert.equal(writes, mode === 'lost' ? 1 : 0); assert.equal(c.outcome, 'unknown');
    }
  }
});
test('matrix refusal disposition requires original receipt absence and unchanged complete owner facts', async t => {
  const business = require('./business_cases.cjs'), { reconcileMatrixWriteRefusal } = require('./application_authority_cases.cjs');
  for (const mode of ['exact', 'receipt-exists', 'receipt-read-failed', 'changed-row', 'changed-caller', 'changed-create-receipt', 'transport-unknown', 'extra-command']) {
    const manager = { origin: 'https://panel.test', identity: { account: 'manager', namespace: 'panel' } }, actor = { origin: manager.origin, identity: { account: 'writer', namespace: 'panel' } };
    const identity = { namespace: 'panel', deploymentId: 'a'.repeat(32) }, created = { id: 7, version: 1, name: 'original' };
    const create = { operation: 'create', identity, operationId: 'b'.repeat(32) }, receipt = { id: '7', version: '1', identity };
    const c = { outcome: 'unknown', actingIdentity: structuredClone(actor.identity), body: { operation: 'update', operationId: 'c'.repeat(32), identity, entity: '/sample', id: '7', expectedVersion: '1' }, response: { status: 200, data: { error: { code: 5, message: '读取安装页面需要应用实例运行权限' } } } };
    const r = { kind: 'business-record', phase: 'created', actorRole: 'manager', origin: manager.origin, actorIdentity: manager.identity, recordId: '7', version: '1', entity: '/sample', applicationKey: 'app', identity, created, createRequest: create, commands: [{ outcome: 'confirmed', body: create, receipt }, c] };
    if (mode === 'changed-caller') c.actingIdentity.account = 'another';
    if (mode === 'transport-unknown') c.response.status = 503;
    if (mode === 'extra-command') r.commands.push({ outcome: 'confirmed' });
    t.mock.method(business, 'member', async (_, role) => role === 'manager' ? manager : actor);
    t.mock.method(business, 'record', async () => ({ status: 200, data: { value: { ...created, version: mode === 'changed-row' ? 2 : 1 } } }));
    t.mock.method(business, 'receiptMatches', () => true);
    let calls = 0, persisted = 0;
    const h = { Blocked: Error, persist() { persisted++; }, check(label, valid) { assert.ok(valid, label); }, good: response => response.status === 200 && !response.data.error,
      async api(who, method, route, body) { calls++; assert.equal(who, actor); assert.equal(method, 'POST'); assert.ok(route.includes('/update/receipt/')); assert.deepEqual(body, c.body); return mode === 'receipt-exists' ? { status: 200, data: { value: receipt } } : { status: mode === 'receipt-read-failed' ? 503 : 200, data: { error: { code: 2, message: '原业务写入尚无完成事实；禁止据此自动重发' } } }; },
      async ok(who, method, route, body) { assert.equal(who, manager); assert.equal(method, 'POST'); assert.ok(route.includes('/create/receipt/')); assert.deepEqual(body, create); return { value: { ...receipt, version: mode === 'changed-create-receipt' ? '2' : '1' } }; } };
    if (mode === 'exact') { await reconcileMatrixWriteRefusal(h, r); assert.equal(c.outcome, 'rejected-before-write-and-unchanged'); assert.equal(calls, 1); assert.equal(persisted, 1); assert.equal(c.response.data.error.code, 5); }
    else { await assert.rejects(reconcileMatrixWriteRefusal(h, r)); assert.equal(c.outcome, 'unknown'); assert.equal(persisted, 0); }
    t.mock.restoreAll();
  }
});
test('empty member scope uses the current omitted wire field without accepting unexpected retained scopes', async () => {
  for (const mode of ['empty-omitted', 'unexpected-scope', 'nonempty-missing', 'nonempty-exact']) {
    const access = mode.startsWith('nonempty') ? [{ applicationUuid: 'a'.repeat(32), accessLevel: 'viewer' }] : [];
    const group = { key: 'exact-template', roleRefs: [{ module: '/app', key: 'read' }] }, member = { value: { id: 42 }, resource: {} };
    const binding = { subjectType: 'account', subjectId: 42, sourceType: 'template', sourceKey: group.key, status: 2 };
    if (mode === 'unexpected-scope') binding.applicationAccess = [{ applicationUuid: 'b'.repeat(32), accessLevel: 'manager' }];
    if (mode === 'nonempty-exact') binding.applicationAccess = access;
    const h = { admin: {}, Blocked: Error, persist() {}, check: (label, valid) => assert.ok(valid, label), good: r => r.status === 200 && !r.data.error,
      async api() { return { status: 200, data: {} }; }, async directory() { return [binding]; }, async ok() { return { value: { effectiveRoles: group.roleRefs } }; } };
    if (mode === 'empty-omitted' || mode === 'nonempty-exact') { await assign(h, member, group, access); assert.equal(member.resource.authorityCommands[0].outcome, 'confirmed'); }
    else { await assert.rejects(assign(h, member, group, access), /member-selected scopes/); assert.equal(member.resource.authorityCommands[0].outcome, 'unknown'); }
  }
});
test('data role matrix retains original command after response loss and never dispatches a replacement', async t => {
  const business = require('./business_cases.cjs'), { matrixWrite } = require('./application_authority_cases.cjs');
  t.mock.method(business, 'record', async () => ({ status: 200, data: { value: { id: 7, version: 1, name: 'original' } } }));
  const actor = { identity: { account: 'ordinary', namespace: 'panel' } }, r = { phase: 'created', recordId: '7', version: '1', commands: [], applicationKey: 'app', identity: { deploymentId: 'a'.repeat(32) } };
  let sent = 0;
  const h = { deliveryActors: { manager: {} }, Blocked: Error, check: (label, value) => assert.ok(value, label), good: r => r.status === 200 && !r.data.error, persist() {},
    async api(_, method, route, body) { sent++; assert.equal(r.commands[0].outcome, 'unknown'); assert.equal(r.commands[0].body.operationId, body.operationId); throw Error('original response lost'); } };
  await assert.rejects(matrixWrite(h, { role: 'writer', actor }, r, 'update', true), /original response lost/);
  await assert.rejects(matrixWrite(h, { role: 'writer', actor }, r, 'update', true), /no write replay/);
  assert.equal(sent, 1); assert.equal(r.commands[0].outcome, 'unknown'); assert.deepEqual(r.commands[0].actingIdentity, actor.identity);
  const account = { kind: 'account', collection: '/cas/namespaces/panel/accounts/', creation: { intended: { account: 'ordinary' } } };
  assert.throws(() => guardFixtureAccountCleanup({ Blocked: Error, state: { resources: [account, { ...r, kind: 'business-record' }] } }, account), /retain actual caller/);
});
test('data role matrix never marks authority refusal confirmed when owner changed or session expired', async t => {
  const business = require('./business_cases.cjs'), { matrixWrite } = require('./application_authority_cases.cjs');
  for (const mode of ['unchanged', 'changed', 'expired']) {
    let reads = 0;
    t.mock.method(business, 'record', async () => ({ status: 200, data: { value: { id: 7, version: mode === 'changed' && reads++ ? 2 : 1, name: 'original' } } }));
    const actor = { identity: { account: 'ordinary', namespace: 'panel' } }, r = { phase: 'created', recordId: '7', version: '1', commands: [], applicationKey: 'app', identity: { deploymentId: 'a'.repeat(32) } };
    const h = { deliveryActors: { manager: {} }, Blocked: Error, check: (label, value) => assert.ok(value, label), good: r => r.status === 200 && !r.data.error, persist() {},
      denied(response) { assert.equal(response.status, 403, 'must prove authenticated authority refusal'); },
      async api() { return { status: mode === 'expired' ? 401 : 403, data: { error: { code: 12 } } }; } };
    const action = matrixWrite(h, { role: 'reader', actor }, r, 'delete', false);
    if (mode === 'unchanged') { await action; assert.equal(r.commands[0].outcome, 'rejected-authority-and-unchanged'); }
    else { await assert.rejects(action, /owner row|authority refusal/); assert.equal(r.commands[0].outcome, 'unknown'); }
    t.mock.restoreAll();
  }
});
test('member scope response loss preserves exact original command and forbids a second replacement', async () => {
  const member = { value: { id: 42 }, resource: {} }, group = { key: 'controlled' }, access = [{ applicationUuid: 'a'.repeat(32), accessLevel: 'editor' }];
  let dispatched = 0;
  const h = { admin: {}, Blocked: Error, persist() {}, async api() { dispatched++; throw Error('response lost'); } };
  await assert.rejects(assign(h, member, group, access), /response lost/);
  assert.deepEqual(member.resource.authorityCommands[0].body.applicationScopes[0].applicationAccess, access);
  assert.equal(member.resource.authorityCommands[0].outcome, 'unknown');
  await assert.rejects(assign(h, member, group, access), /no role replacement replay/); assert.equal(dispatched, 1);
});
test('cleanup preserves the first business failure and records every unresolved original row', async () => {
  const events = [], actor = { origin: 'https://example.test', identity: { account: 'original', namespace: 'tenant' } };
  const h = { deliveryActors: { manager: actor }, Blocked: Error, observe: e => events.push(e) };
  const rows = ['1', '2'].map(recordId => ({ recordId, actorRole: 'manager', origin: actor.origin, actorIdentity: actor.identity, commands: [{ outcome: 'unknown' }] }));
  await finishCleanup(h, rows, Error('first actual failure'));
  assert.equal(events.length, 2); assert.deepEqual(events.map(e => e.recordId), ['1', '2']);
  await assert.rejects(finishCleanup(h, rows), /no execute replay/);
});
test('unknown member assignment protects the original account and cannot be reconciled by a new actor', async () => {
  const resource = {kind:'account',id:42,phase:'created',collection:'/cas/namespaces/panel/accounts/',
    creation:{ownershipConfirmed:true,actorIdentity:{account:'original',namespace:'panel'},origin:'https://panel.example.invalid'},
    authorityCommands:[{outcome:'unknown'}]};
  const h = {Blocked:Error,state:{resources:[resource]},admin:{identity:{account:'replacement',namespace:'panel'},origin:'https://panel.example.invalid'},api(){throw Error('must not dispatch');}};
  assert.throws(()=>guardFixtureAccountCleanup(h,resource),/scope assignment remains unresolved/);
  await assert.rejects(reconcile(h,resource),/exact owned account and original administrator/);
  assert.equal(resource.authorityCommands[0].outcome,'unknown');
});
test('direct application access freezes original submission before dispatch and preserves its account after response loss', async () => {
  const { accessCommand, retireAccess } = require('./application_authority_cases.cjs');
  const actor = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.example.invalid' };
  const account = { kind: 'account', id: 42 }, resource = { kind: 'member-access-retirement', phase: 'created', accountId: 42,
    installation: { id: 7, deploymentId: 'a'.repeat(32) }, commands: [], actorIdentity: actor.identity, origin: actor.origin };
  let sent = 0;
  const h = { admin: actor, Blocked: Error, state: { resources: [account, resource] }, persist() {},
    check(label, value) { assert.ok(value, label); },
    async ok() { return { value: { namespace: 'panel', accountId: 42, deploymentId: 'a'.repeat(32), epoch: 9 } }; },
    async api(_, method, route, body) {
      sent++; assert.equal(resource.commands[0].outcome, 'unknown'); assert.equal(resource.commands[0].body.submissionId, body.submissionId);
      assert.equal(body.expectedEpoch, 9); assert.equal(route, '/panel/application/installations/7/access-operations/');
      throw Error('lost original grant response');
    }
  };
  await assert.rejects(accessCommand(h, resource, 'editor', 0), /lost original grant response/);
  await assert.rejects(accessCommand(h, resource, 'editor', 0), /no grant or retirement replay/);
  await assert.rejects(retireAccess(h, resource), /retain account and operation/);
  assert.throws(() => guardFixtureAccountCleanup(h, account), /unresolved direct access operation/);
  assert.equal(sent, 1); assert.equal(resource.phase, 'created');
});
test('retirement field rejection disposition requires original submission absence and unchanged exact assignment and epoch', async () => {
  const { reconcileRejectedRetirement } = require('./application_authority_cases.cjs');
  for (const mode of ['refused-before-intent', 'transport-unknown', 'owner-intent-exists', 'epoch-changed', 'assignment-changed']) {
    const requestedBy = { namespace: 'panel', subject: 'account:3', accountId: 3 };
    const c = { outcome: 'unknown', route: '/panel/application/installations/7/access-retirements/', body: { submissionId: 'a'.repeat(32), assignmentId: 19, accountId: 42, accessLevel: '', reason: 'not-allowed', expectedEpoch: 1 },
      response: { status: mode === 'transport-unknown' ? 503 : 400, data: { error: { code: 4, message: 'application access original submission is incomplete' } } } };
    const r = { installation: { id: 7, deploymentId: 'd'.repeat(32) }, accountId: 42, assignmentId: 19,
      commands: [{ outcome: 'confirmed', body: { reason: 'original grant' }, completed: { status: 'completed', accessLevel: 'editor', assignmentId: 19, requestedBy } }, c] };
    const h = { admin: {}, persist() {}, check(label, value) { assert.ok(value, label); },
      async api(_, method) { assert.equal(method, 'GET'); return mode === 'owner-intent-exists' ? { status: 200, data: { value: { id: 99 } } } : { status: 404, data: { error: { code: 2 } } }; },
      async directory() { return [{ id: 19, installationId: 7, subjectId: 42, accessLevel: mode === 'assignment-changed' ? 'manager' : 'editor', reason: 'original grant', assignedBy: requestedBy }]; },
      async ok() { return { value: { epoch: mode === 'epoch-changed' ? 2 : 1, accountId: 42, deploymentId: 'd'.repeat(32) } }; }
    };
    if (mode === 'refused-before-intent') { await reconcileRejectedRetirement(h, r); assert.equal(c.outcome, 'rejected-before-intent'); assert.equal(c.response.status, 400); }
    else if (mode === 'transport-unknown') { await reconcileRejectedRetirement(h, r); assert.equal(c.outcome, 'unknown'); }
    else { await assert.rejects(reconcileRejectedRetirement(h, r)); assert.equal(c.outcome, 'unknown'); }
  }
});
test('exact NotApplied retirement conflict can be disposed only by the original actor and unchanged owner facts without replay', async () => {
  const { reconcileRejectedRetirement } = require('./application_authority_cases.cjs');
  for (const mode of ['good', 'wrong-actor', 'grant-changed', 'intent-exists', 'assignment-changed', 'epoch-changed', 'namespace-changed', 'other-conflict', 'execution-unknown']) {
    const actor = { account: 'original', namespace: 'panel' }, requestedBy = { namespace: 'panel', subject: 'account:3', accountId: 3 };
    const completed = { id: 8, status: 'completed', namespace: 'panel', accountId: 42, installationId: 7, deploymentId: 'd'.repeat(32),
      assignmentId: 19, accessLevel: 'editor', requestedBy, submissionId: 'b'.repeat(32) };
    const c = { outcome: 'unknown', route: '/panel/application/installations/7/access-retirements/', body: {
      submissionId: 'a'.repeat(32), assignmentId: 19, accountId: 42, accessLevel: '', reason: '', expectedEpoch: 1 },
      response: { status: 409, data: { error: { code: 19, message: mode === 'other-conflict' ? 'another conflict' : 'application lifecycle changed before commit' } } } };
    if (mode === 'execution-unknown') c.execution = { outcome: 'unknown' };
    const r = { origin: 'https://panel.invalid', actorIdentity: structuredClone(actor), installation: { id: 7, deploymentId: completed.deploymentId },
      accountId: 42, assignmentId: 19, commands: [{ outcome: 'confirmed', body: { reason: 'original grant' }, completed }, c] };
    let reads = 0;
    const h = { admin: { origin: r.origin, identity: { ...actor, ...(mode === 'wrong-actor' ? { account: 'other' } : {}) } }, persist() {}, check(label, value) { assert.ok(value, label); },
      async ok(_, method, route) { assert.equal(method, 'GET'); reads++;
        return { value: route.includes('submissionId=') ? { ...completed, ...(mode === 'grant-changed' ? { status: 'unknown' } : {}) } :
          { namespace: mode === 'namespace-changed' ? 'other' : 'panel', epoch: mode === 'epoch-changed' ? 2 : 1, accountId: 42, deploymentId: completed.deploymentId } }; },
      async api(_, method, route) { assert.equal(method, 'GET'); assert.equal(route, '/panel/application/installations/7/access-operations/?submissionId=' + c.body.submissionId); reads++;
        return mode === 'intent-exists' ? { status: 200, data: { value: { id: 99 } } } : { status: 404, data: { error: { code: 2 }, value: null } }; },
      async directory() { reads++; return [{ id: 19, installationId: 7, subjectId: 42, accessLevel: mode === 'assignment-changed' ? 'manager' : 'editor', reason: 'original grant', assignedBy: requestedBy }]; } };
    if (mode === 'good') { await reconcileRejectedRetirement(h, r); assert.equal(c.outcome, 'rejected-before-intent'); assert.deepEqual(c.disposition.originalGrant, completed); assert.equal(c.response.status, 409); }
    else if (['other-conflict', 'execution-unknown'].includes(mode)) { await reconcileRejectedRetirement(h, r); assert.equal(c.outcome, 'unknown'); assert.equal(reads, 0); }
    else { await assert.rejects(reconcileRejectedRetirement(h, r)); assert.equal(c.outcome, 'unknown'); }
  }
});
