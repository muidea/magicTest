const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const { runtimeRead } = require('./owner_transport.cjs');
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
const absent = r => [200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
async function member(h, role) {
  h.deliveryActors ||= {};
  if (h.deliveryActors[role]) return h.deliveryActors[role];
  const f = await fixture(h), config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig));
  const dedicated = h.state.fixtures?.businessMembers?.[role];
  const credentials = dedicated || JSON.parse(h.fs.readFileSync(h.path.join(config.privateRoot, 'member-credentials.json')))[role];
  const owned = dedicated && h.state.resources.find(r => r.kind === 'account' && r.id === dedicated.id && r.phase !== 'deleted' && r.creation?.ownershipConfirmed && r.creation.intended.account === dedicated.account && r.collection === '/cas/namespaces/panel/accounts/');
  if (!credentials || (dedicated ? !owned : credentials.id !== f.members?.[role]?.id || credentials.account !== f.members[role].account || credentials.access !== f.members[role].access)) throw new h.Blocked('Original ordinary fixture member identity is incomplete');
  const actor = await h.login(credentials.account, credentials.password, 'panel');
  const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  h.check('Business executor uses original ordinary account without platform administrator identity', session.account?.id === credentials.id && session.account.account === credentials.account && session.homeNamespace === 'panel' && credentials.account !== h.credentials.account);
  actor.subject = session.homeNamespace + '/account:' + credentials.id;
  h.deliveryActors[role] = actor; return actor;
}
async function runtime(h, f, index, actor) {
  const instance = f.installations[index];
  if (!instance) throw new h.Blocked('Installed business fixture is missing');
  const metadata = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + instance.deploymentId)).value;
  const identity = metadata.readIdentity;
  h.check('Runtime owner supplies exact current ordinary-subject installation fence', installationMatches(f, instance, identity), identity);
  const source = f.revision.entities[0], entity = source.pkgPath + '/' + source.name;
  const ui = metadata.entities.find(e => e.entity?.name === source.name && e.entity?.pkgPath === source.pkgPath);
  // Block-bound (protected source) entities correctly advertise the source-write
  // contract; ordinary entities advertise value-write. Both retain the exact
  // protected version field, which is what this check must prove.
  h.check('Runtime metadata retains exact original protected entity and version contract',
    ['magic.entity-value-write/v1', 'magic.entity-source-write/v1'].includes(ui?.businessWrites?.apiVersion) && ui.businessWrites.versionField === 'version', ui);
  h.observe({ kind: 'runtime-business-writes', deploymentId: identity.deploymentId, entity: entity, apiVersion: ui?.businessWrites?.apiVersion, operations: ui?.businessWrites?.operations });
  // Cases may intentionally drop the UI projection before dispatching a write;
  // the contract decision must survive that deletion as a separate fact.
  return { instance, identity, entity, ui, sourceWrites: ui?.businessWrites?.apiVersion === 'magic.entity-source-write/v1', applicationKey: f.application.name };
}
function installationMatches(f, instance, identity) {
  return !!identity && f.package.sourceRevisionId === f.revision.id &&
    instance.receipt.revisionId === f.revision.id && instance.receipt.revisionDigest === f.package.artifactDigest &&
    identity.installationId === String(instance.id) && identity.deploymentId === instance.deploymentId &&
    identity.namespace === 'panel' && identity.runtimeApplicationUuid === instance.receipt.runtimeApplicationUuid &&
    identity.artifactDigest === f.package.artifactDigest;
}
function route(r, operation, queryOnly) {
  const query = '?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId;
  // Block-bound entities use the separate immutable source-write command.
  if (r.sourceWrites || r.ui?.businessWrites?.apiVersion === 'magic.entity-source-write/v1') {
    return '/apps/entity/value/source/' + (queryOnly ? 'receipt' : 'execute') + '/v1/' + query;
  }
  return '/apps/entity/value/write/' + operation + '/' + (queryOnly ? 'receipt' : 'execute') + '/' + query;
}
function inputDigest(request) {
  const id = request.identity;
  // The finite fixture identity must be lossless. Never round arbitrary int64.
  const installation = Number(id.installationId);
  if (!Number.isSafeInteger(installation) || String(installation) !== id.installationId) throw Error('Fixture installation exceeds exact numeric digest budget');
  const wire = { apiVersion: request.apiVersion, operationId: request.operationId,
    identity: { namespace: id.namespace, deploymentId: id.deploymentId, installationId: installation,
      runtimeApplicationUuid: id.runtimeApplicationUuid, generation: id.generation, executionEpoch: id.executionEpoch, artifactDigest: id.artifactDigest },
    entity: request.entity, operation: request.operation, id: request.id, expectedVersion: request.expectedVersion, fields: request.fields };
  return digest(JSON.stringify(wire).replace(/[<>&\u2028\u2029]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')));
}
async function record(h, actor, r, id = r.recordId) {
  return runtimeRead(actor, '/apps/entity/values/' + id + '?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId + '&entity=' + encodeURIComponent(r.entity), r.identity, h.observe);
}
function original(h, actor, r) {
  if (actor.origin !== r.origin || !same(actor.identity, r.actorIdentity) || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original business command or actor remains unresolved; no execute replay');
}
function request(r, operation, fields = [], extra = {}) {
  // Block-bound (protected source) entities only accept the source-write
  // contract; ordinary entities keep the value-write contract.
  const observedVersion = r.ui?.businessWrites?.apiVersion;
  if (process.env.MAGIC_REQUEST_TRACE) console.error('request-contract', JSON.stringify({ observedVersion, sourceWrites: r.sourceWrites, entity: r.entity, deploymentId: r.identity?.deploymentId, hasUi: !!r.ui }));
  const apiVersion = r.sourceWrites || observedVersion === 'magic.entity-source-write/v1' ? 'magic.entity-source-write/v1' : 'magic.entity-value-write/v1';
  return { apiVersion, operationId: crypto.randomBytes(16).toString('hex'), identity: structuredClone(r.identity),
    entity: r.entity, operation, id: operation === 'create' ? '' : r.recordId, expectedVersion: operation === 'create' ? '' : r.version, fields, ...extra };
}
async function execute(h, actor, r, body, repeat = false) {
  original(h, actor, r);
  const c = { body: structuredClone(body), repeatOfConfirmedIntent: repeat, outcome: 'unknown' }; r.commands.push(c); h.persist();
  c.response = await h.api(actor, 'POST', route(r, body.operation, false), body); h.persist();
  h.check('Original reliable business command is acknowledged by public owner', h.good(c.response), c.response);
  const receipt = c.response.data.value;
  h.check('Reliable receipt binds exact original request digest, subject, installation, operation and version', receiptMatches(actor, body, receipt), receipt);
  const resolved = (await h.ok(actor, 'POST', route(r, body.operation, true), receiptRequest(body))).value;
  h.check('Formal receipt query independently confirms exact stable original result', same(resolved, receipt));
  c.receipt = receipt; c.outcome = 'confirmed'; h.persist();
  if (!receipt.canceled) {
    r.recordId = receipt.id; r.version = receipt.version; r.phase = body.operation === 'delete' ? 'delete-acknowledged' : 'created'; h.persist();
  }
  return receipt;
}
function receiptMatches(actor, body, receipt) {
  return !!receipt && receipt.apiVersion === body.apiVersion && receipt.operationId === body.operationId && same(receipt.identity, body.identity) && receipt.inputDigest === inputDigest(body) && receipt.subject === actor.subject && receipt.entity === body.entity && receipt.operation === body.operation &&
    (receipt.canceled ? receipt.id === body.id && receipt.version === body.expectedVersion : body.operation === 'create' ? /^[1-9][0-9]*$/.test(receipt.id) && receipt.version === '1' : receipt.id === body.id && receipt.version === (body.operation === 'update' ? String(BigInt(body.expectedVersion) + 1n) : body.expectedVersion));
}
const receiptRequest = body => { const copy = structuredClone(body); delete copy.cancel; return copy; };
async function reconcile(h, r) {
  const actor = await member(h, r.actorRole);
  if (actor.origin !== r.origin || !same(actor.identity, r.actorIdentity)) throw new h.Blocked('Original business reconciliation actor changed');
  const pending = r.commands.filter(c => c.outcome === 'unknown');
  if (pending.length !== 1 || pending[0].negativeActor) throw new h.Blocked('Business reconciliation requires exactly the original unresolved intent');
  if (pending[0].body.cancel === true) {
    const c = pending[0];
    if (!r.recordId || !h.good(c.response) || !c.response.data.value?.canceled || !receiptMatches(actor, c.body, c.response.data.value)) throw new h.Blocked('Original cancellation has no exact acknowledged durable receipt');
    const resolved = (await h.ok(actor, 'POST', route(r, c.body.operation, true), receiptRequest(c.body))).value;
    const expected = structuredClone(r.created);
    for (const command of r.commands.filter(p => p.outcome === 'confirmed' && p.body.operation === 'update' && !p.receipt.canceled)) for (const field of command.body.fields) {
      if (!Object.hasOwn(field, 'value')) throw new h.Blocked('Cancellation reconciliation only supports the original scalar fixture');
      expected[field.name] = field.value;
    }
    expected.version = Number(r.version);
    h.check('Original cancellation query confirms stable receipt and unchanged complete scalar business record', same(resolved, c.response.data.value) && same((await record(h, actor, r)).data.value, expected));
    c.receipt = resolved; c.outcome = 'confirmed'; c.reconciliation = 'Original cancellation receipt queried with immutable intent and cancel omitted; no execute replay'; h.persist();
    return { operationId: c.body.operationId, recordId: r.recordId, proof: c.reconciliation };
  }
  if (pending[0].body.operation !== 'create') throw new h.Blocked('Original command requires its own confirmed reconciliation path');
  if (r.recordId) {
    const c = pending[0], previous = r.commands.find(p => p.outcome === 'confirmed' && p.body.operationId === c.body.operationId && p.body.operation === 'create');
    if (!previous || inputDigest(previous.body) === inputDigest(c.body) || !payloadConflict(c.response)) throw new h.Blocked('Original payload conflict lacks exact acknowledged refusal and confirmed initial intent');
    const stable = (await h.ok(actor, 'POST', route(r, 'create', true), previous.body)).value;
    const row = await record(h, actor, r);
    h.check('Original conflicting intent was refused and its original receipt and record remain exact', same(stable, previous.receipt) && h.good(row) && same(row.data.value, r.created));
    c.outcome = 'rejected-payload-conflict'; c.reconciliation = 'Original refusal and original-intent receipt confirmed without execute replay'; h.persist();
    return { operationId: c.body.operationId, recordId: r.recordId, proof: c.reconciliation };
  }
  const c = pending[0], resolved = (await h.ok(actor, 'POST', route(r, 'create', true), c.body)).value;
  h.check('Original unresolved create is independently confirmed without execute replay', receiptMatches(actor, c.body, resolved) && (!c.response || h.good(c.response) && same(c.response.data.value, resolved)), resolved);
  const row = await record(h, actor, r, resolved.id);
  h.check('Original allocated record and complete submitted fields are independently confirmed', h.good(row) && String(row.data.value?.id) === resolved.id && String(row.data.value?.version) === resolved.version && c.body.fields.every(f => same(row.data.value[f.name], f.value)), row);
  c.receipt = resolved; c.outcome = 'confirmed'; c.reconciliation = 'Exact original intent queried; no execute replay';
  r.recordId = resolved.id; r.version = resolved.version; r.phase = 'created'; h.persist();
  return { operationId: c.body.operationId, recordId: r.recordId, proof: c.reconciliation };
}
const payloadConflict = response => response?.status === 200 && response.data?.error?.code === 21 && response.data.error.message === '原业务写入身份或输入不匹配' && response.data.value == null;
async function create(h, context, suffix, code, actorRole = 'manager') {
  const actor = await member(h, actorRole);
  const r = { kind: 'business-record', actorRole, phase: 'intent', ...context,
    origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [] };
  // Runtime UI is a read projection, not mutable execution input.
  delete r.ui; h.state.resources.push(r); h.persist();
  const body = request(r, 'create', [{ name: 'code', value: code || 'RG-' + crypto.randomBytes(8).toString('hex').toUpperCase() }, { name: 'name', value: '同名回归业务 ' + suffix }, { name: 'description', value: null }, { name: 'sortOrder', value: 0 }]);
  await execute(h, actor, r, body);
  const response = await record(h, actor, r);
  h.check('Independent exact owner read proves all original submitted values, zero, null and owner version', h.good(response) && String(response.data.value?.id) === r.recordId && String(response.data.value.version) === '1' && body.fields.every(f => same(response.data.value[f.name], f.value)), response);
  r.created = response.data.value; r.createRequest = body; h.persist(); return r;
}
async function cleanup(h, r) {
  if (r.scenarioUpgradeRequestId != null) throw new h.Blocked('Original upgrade business row requires its exact successor disposition; no cleanup under obsolete installation fence');
  if (r.scenarioRecoveryRequestId != null) throw new h.Blocked('Original retained business row requires its exact successor disposition; no cleanup under obsolete installation fence');
  if (r.actionCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original business action result remains unresolved; preserve exact row, caller and installation');
  if (r.constraintCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original field validation command remains unresolved; retain its exact business row and actor');
  if (r.debugCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original instance debug write result remains unresolved; preserve its exact business row and actor');
  const actor = await member(h, r.actorRole); original(h, actor, r);
  if (!r.recordId) throw new h.Blocked('Original business creation has no confirmed owner record identity');
  const current = await record(h, actor, r);
  if (!absent(current)) {
    h.check('Cleanup reads exact original business identity and latest acknowledged owner version', h.good(current) && String(current.data.value.id) === r.recordId && String(current.data.value.version) === r.version, current);
    await execute(h, actor, r, request(r, 'delete'));
  } else if (!r.commands.some(c => c.outcome === 'confirmed' && c.body.operation === 'delete' && c.receipt.id === r.recordId)) throw new h.Blocked('Original business record absent without its confirmed delete receipt');
  h.check('Independent owner confirms original business record absent after exact reliable deletion', absent(await record(h, actor, r)));
  if (r.todoSync) await require('./todo_sync_cases.cjs').confirmSourceExit(h, r);
  r.phase = 'deleted'; h.persist(); return { proof: 'Original ordinary account, exact installation fence, stable delete receipt and independent original-record absence; owner execution receipts retained.' };
}
async function isolation(h, viewerChecks = false, storageChecks = false) {
  const f = await fixture(h), actor = await member(h, 'manager');
  const contexts = await Promise.all([runtime(h, f, 0, actor), runtime(h, f, 1, actor)]);
  h.check('Two installed instances use independent runtime application and physical Schema owner bindings', contexts[0].identity.runtimeApplicationUuid !== contexts[1].identity.runtimeApplicationUuid && contexts[0].instance.receipt.database.schemaResourceId !== contexts[1].instance.receipt.database.schemaResourceId);
  if (storageChecks) {
    const databases = await h.directory(h.admin, '/panel/storage-resources/databases/');
    const schemas = await h.directory(h.admin, '/panel/storage-resources/database-schemas/');
    const bound = contexts.map(c => {
      const binding = c.instance.receipt.database;
      const schema = schemas.find(s => s.id === binding.schemaResourceId);
      const database = databases.find(d => d.id === binding.databaseResourceId);
      h.check('Independent storage owner directory resolves exact installation binding to its logical database and Schema', schema && database && schema.databaseResourceId === database.id && schema.databaseName === database.name && schema.name && schema.status === 'active' && database.status === 'active', { binding, schema, database });
      return { schema, database };
    });
    h.check('Same logical database gives dual instances separate ready physical Schema identities', bound[0].schema.id !== bound[1].schema.id && bound[0].schema.name !== bound[1].schema.name && (bound[0].database.id !== bound[1].database.id || bound[0].database.allocatedSchemaCount >= 2), bound);
  }
  const code = 'RG-' + crypto.randomBytes(8).toString('hex').toUpperCase();
  const first = await create(h, contexts[0], 'shared-name', code), second = await create(h, contexts[1], 'shared-name', code);
  let primary;
  try {
    h.check('Same business unique code can be owned independently by each instance', first.recordId !== second.recordId && first.created.code === second.created.code && first.created.name === second.created.name);
    for (const [r, other] of [[first, second], [second, first]]) h.check('Exact instance read cannot fall back to other instance record with same business code', absent(await record(h, actor, r, other.recordId)));
    await execute(h, actor, first, request(first, 'update', [{ name: 'name', value: '只修改实例一 ' + h.state.prefix }]));
    const a = await record(h, actor, first), b = await record(h, actor, second);
    h.check('Sparse update persists only in original instance and preserves other instance completely', h.good(a) && a.data.value.name === '只修改实例一 ' + h.state.prefix && a.data.value.code === code && a.data.value.description === null && h.good(b) && same(b.data.value, second.created));
    if (viewerChecks) {
      const viewer = await member(h, 'viewer'), v = await runtime(h, f, 0, viewer);
      h.check('Frozen owner declaration opens write capability independently of viewer runtime permission', f.revision.entities[0].serviceExpose.capabilities.some(c => c.key === 'create' && c.enabled) && !v.ui.capabilities?.create);
      const before = await record(h, actor, first);
      const c = { body: request(first, 'update', [{ name: 'name', value: 'MUST NOT CHANGE' }]), outcome: 'unknown', negativeActor: structuredClone(viewer.identity) };
      first.commands.push(c); h.persist(); c.response = await h.api(viewer, 'POST', route(first, 'update', false), c.body); h.persist();
      h.denied(c.response, 'Ordinary viewer cannot write an actually enabled instance capability');
      h.check('Independent authorized owner preserves original record after viewer denial', same(await record(h, actor, first), before));
      c.outcome = 'rejected-authority-and-unchanged'; h.persist();
      const outsider = await member(h, 'outsider');
      for (const target of [first, second]) h.denied(await record(h, outsider, target), 'Original ordinary account without either instance grant cannot read its exact record');
    }
  } catch (error) { primary = error; throw error; }
  finally { await finishCleanup(h, [second, first], primary); }
}
async function finishCleanup(h, records, primary) {
  let cleanupError;
  for (const r of records) try { await cleanup(h, r); }
  catch (error) { cleanupError ||= error; h.observe({ kind: 'business-cleanup-open', recordId: r.recordId, reason: error.message }); }
  if (!primary && cleanupError) throw cleanupError;
}
async function reliable(h) {
  const f = await fixture(h), actor = await member(h, 'manager'), context = await runtime(h, f, 0, actor);
  const r = await create(h, context, 'reliable');
  let primary;
  try {
    const originalReceipt = r.commands[0].receipt;
    h.check('Confirmed identical create replay returns the exact same durable receipt', same(await execute(h, actor, r, r.createRequest, true), originalReceipt));
    const conflict = { ...structuredClone(r.createRequest), fields: r.createRequest.fields.map(field => field.name === 'name' ? { ...field, value: 'MUST NOT CREATE AGAIN' } : field) };
    const c = { body: conflict, outcome: 'unknown' }; r.commands.push(c); h.persist();
    c.response = await h.api(actor, 'POST', route(r, 'create', false), conflict); h.persist();
    const stable = (await h.ok(actor, 'POST', route(r, 'create', true), r.createRequest)).value;
    const unchanged = await record(h, actor, r);
    if (payloadConflict(c.response) && same(stable, originalReceipt) && h.good(unchanged) && same(unchanged.data.value, r.created)) { c.outcome = 'rejected-payload-conflict'; h.persist(); }
    h.check('Same operation with changed payload is rejected while original row and receipt remain unchanged', c.outcome === 'rejected-payload-conflict', c.response);
    await execute(h, actor, r, request(r, 'update', [{ name: 'description', value: '稀疏更新：0/null/原业务码保持' }]));
    const before = (await record(h, actor, r)).data.value;
    const bodies = ['并发甲', '并发乙'].map(name => request(r, 'update', [{ name: 'name', value: name }]));
    const commands = bodies.map(body => ({ body, outcome: 'unknown' })); r.commands.push(...commands); h.persist();
    const responses = await Promise.all(commands.map(c => h.api(actor, 'POST', route(r, 'update', false), c.body)));
    commands.forEach((c, index) => { c.response = responses[index]; }); h.persist();
    const winners = responses.map((response, index) => h.good(response) ? index : -1).filter(index => index >= 0);
    h.check('Concurrent same-version original writes have exactly one committed winner', winners.length === 1 && responses[1 - winners[0]].data?.error?.code === 19, responses);
    const winner = winners[0], receipt = (await h.ok(actor, 'POST', route(r, 'update', true), bodies[winner])).value, current = await record(h, actor, r);
    h.check('Independent receipt and row prove only winning sparse update and one version increment', same(receipt, responses[winner].data.value) && receipt.inputDigest === inputDigest(bodies[winner]) && receipt.subject === actor.subject && h.good(current) && current.data.value.name === bodies[winner].fields[0].value && current.data.value.description === before.description && String(current.data.value.version) === String(BigInt(r.version) + 1n), { receipt, current });
    commands[winner].outcome = 'confirmed'; commands[winner].receipt = receipt; commands[1 - winner].outcome = 'rejected-version-conflict'; r.version = receipt.version; h.persist();
    const cancel = request(r, 'update', [{ name: 'name', value: 'CANCELLED MUST NOT CHANGE' }], { cancel: true });
    const cancelled = await execute(h, actor, r, cancel);
    h.check('Cancel seals original stable intent without changing the actual business record', cancelled.canceled === true && same((await record(h, actor, r)).data.value, current.data.value));
    h.check('Confirmed cancelled intent cannot later execute on replay', same(await execute(h, actor, r, { ...cancel, cancel: false }, true), cancelled));
  } catch (error) { primary = error; throw error; }
  finally { await finishCleanup(h, [r], primary); }
}
const handlers = { 'F032-001': h => isolation(h), 'F019-002': h => isolation(h, true), 'F036-003': h => isolation(h, true), 'F048-001': h => isolation(h, false, true), 'F070-003': reliable };
for (const handler of Object.values(handlers)) handler.transport = 'owner-api';
module.exports = { handlers, member, runtime, route, request, create, execute, cleanup, finishCleanup, record, inputDigest, installationMatches, receiptMatches, receiptRequest, reconcile };
