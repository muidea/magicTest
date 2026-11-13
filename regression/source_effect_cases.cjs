// Formal source reception and durable task projections; no synthetic worker,
// direct task writes or helper-signed authority. Unknown original commands hold
// the definition, grants and installations for later owner confirmation.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const libraryOwner = require('./script_library_cases.cjs');
const collection = require('./business_collection_cases.cjs').collection;
const { roundtrip } = require('./delivery_completion_cases.cjs');
const version = 'magic.entity-source-write/v1';
const sourceProgram = `package block
import "context"
func Handle(ctx context.Context, input map[string]any, output map[string]any) error {
 output["items"] = []any{map[string]any{"metric":"first"},map[string]any{"metric":"second"}}
 return ctx.Err()
}`;
const b64 = value => Buffer.from(value).toString('base64');
function targetCode(deploymentId, sourceCode, metric) {
  const bytes = crypto.createHash('sha256').update(JSON.stringify([deploymentId, sourceCode, metric])).digest();
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = 0, value = 0, encoded = '';
  for (const byte of bytes) {
    value = (value << 8) | byte; bits += 8;
    while (bits >= 5) { bits -= 5; encoded += alphabet[(value >>> bits) & 31]; }
  }
  if (bits) encoded += alphabet[(value << (5 - bits)) & 31];
  return 'E-' + encoded;
}
function effectEntities(original, binding) {
  const source = structuredClone(original), target = structuredClone(original);
  target.id = 0; target.name = 'zzDerivedTarget'; target.showName = '派生目标'; target.blockInfo = [];
  delete target.createTime; delete target.updateTime; delete target.expectedEntityVersion;
  target.fields.find(f => f.name === 'code').spec.constraint = 'req,max=64';
  target.uniqueConstraints = [{ name: 'uq_derived_code', fields: ['code'] }];
  source.writeRules = { apiVersion: 'magic.entity-write-rules/v1', appendOnly: true, versionField: 'version' };
  source.uniqueConstraints = [{ name: 'uq_source_code', fields: ['code'] }];
  source.blockInfo = [structuredClone(binding)];
  const block = source.blockInfo[0], fn = block.stageInfo.functions.insert;
  Object.assign(block, { key: 'derive', scriptKey: 'derive' });
  Object.assign(fn, { checkType: 'postCheck', bindScript: null, bindField: '', resultField: '', output: null, executeTimeout: 3000,
    input: { record: '$referenceValue' }, createEffect: { apiVersion: 'magic.script-create-effect/v1', targetEntity: target.pkgPath + '/' + target.name,
      sourceKey: ['code'], resultParameter: 'items', maxRecords: 2, candidateFields: [{ name: 'metric', type: 'string' }],
      identity: { field: 'code', prefix: 'E-', parts: [{ from: 'deployment', field: 'deploymentId' }, { from: 'source', field: 'code' }, { from: 'candidate', field: 'metric' }] },
      fields: [{ field: 'name', value: { from: 'candidate', field: 'metric' } }] } });
  return [source, target];
}
async function prepare(h, authored) {
  const before = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + authored.app.id + '/function-blocks')).value;
  const spec = { key: 'derive', name: '受控来源派生', language: 'go', sourceFiles: ['derive/main.go'], entrypoint: { file: 'derive/main.go', function: 'block.Handle' },
    inputs: [{ name: 'record', type: 'object', required: true }], outputs: [{ name: 'items', type: 'array', required: true }] };
  authored.effectLibrary = { schemaVersion: before.content.schemaVersion, definitions: [{ key: 'derive', definition: 'derive/definition.json' }],
    files: { 'derive/definition.json': b64(JSON.stringify(spec)), 'derive/main.go': b64(sourceProgram) } };
  await libraryOwner.saveLibrary(h, authored.app, authored.effectLibrary);
  authored.model = await a.save(h, authored.app, await a.draft(h, authored.app), effectEntities(authored.model.entities[0], await a.scriptBinding(h)));
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
async function fixture(h, suffix) {
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix, requestPrefix: suffix + '-', prepareAuthor: prepare,
    buildEntityViews: require('./model_input_cases.cjs').inputViews, prepareDelivery: roundtrip });
  const actor = await business.member(h, 'manager'), contexts = [];
  for (const installation of f.installations) {
    const metadata = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + installation.deploymentId)).value;
    h.check('Ordinary source producer receives exact current installed read identity', business.installationMatches(f, installation, metadata.readIdentity));
    const source = f.revision.entities.find(v => v.blockInfo?.some(b => b.key === 'derive'));
    const target = f.revision.entities.find(v => v.name === 'zzDerivedTarget');
    contexts.push({ identity: metadata.readIdentity, applicationKey: f.application.name, entity: source.pkgPath + '/' + source.name,
      targetEntity: target.pkgPath + '/' + target.name, instance: installation });
  }
  return { f, actor, contexts };
}
const route = (r, query) => '/apps/entity/value/source/' + (query ? 'receipt' : 'execute') + '/v1/?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId;
function receiptMatches(actor, body, value) {
  const fact = value?.source;
  return business.receiptMatches(actor, body, value) && !!fact && fact.apiVersion === 'magic.entity-value-source/v1' && same(fact.identity, body.identity) &&
    fact.subject === actor.subject && fact.entity === body.entity && fact.id === value.id && fact.version === value.version &&
    fact.operationId === body.operationId && fact.inputDigest === value.inputDigest &&
    /^sha256:[a-f0-9]{64}$/.test(fact.keyDigest || '') && /^sha256:[a-f0-9]{64}$/.test(fact.payloadDigest || '') &&
    fact.effects?.length === 1 && fact.effects.every(e => e.apiVersion === 'magic.script-effect-execution/v1' && same(e.identity, body.identity) && e.subject === actor.subject &&
      e.sourceEntity === body.entity && e.sourceId === value.id && e.bindingKey === 'derive' && /^[a-f0-9]{32}$/.test(e.intentId || '') &&
      /^sha256:[a-f0-9]{64}$/.test(e.planDigest || '') && /^sha256:[a-f0-9]{64}$/.test(e.sourceDigest || ''));
}
function original(h, actor, r) {
  if (actor.origin !== r.origin || !same(actor.identity, r.actorIdentity) || r.commands.some(c => c.outcome === 'unknown'))
    throw new h.Blocked('Original source command unresolved or producer changed; query exact original receipt, no execute replay');
}
function disabledSourceRefusal(response) {
  return response?.status === 200 && response.data?.error?.code === 2 &&
    response.data.error.message === 'running application not found' && response.data.value == null;
}
function historyVisibilityGap(before, after, originalTasks, currentTasks, response) {
  return Number.isSafeInteger(before?.generation) && Number.isSafeInteger(after?.generation) && after.generation > before.generation &&
    same({ ...before, generation: after.generation }, after) && originalTasks.length > 0 &&
    originalTasks.every(v => v.state === 'completed') && currentTasks.length === 0 &&
    response?.status === 409 && response.data?.error?.code === 19 && response.data.value == null &&
    response.data.error.message === '派生任务要求当前运行安装及相同代际；停用或历史实例暂不可查询';
}
async function observeLifecycleHistory(h, r, current, originalTasks, currentTasks) {
  if (same(originalTasks, currentTasks)) return false;
  const response = await h.api(h.admin, 'POST', '/panel/application/installations/' + r.identity.installationId + '/effects/search',
    { identity: r.identity, cursor: '', limit: 50, state: '' });
  h.check('Changed-generation task visibility is the exact declared historical-query gap, not unexplained task drift',
    historyVisibilityGap(r.identity, current.identity, originalTasks, currentTasks, response), response);
  r.lifecycleHistoryGap = { originalIdentity: r.identity, currentIdentity: current.identity, originalTasks, currentTasks, response,
    qualification: 'Current generation excludes prior tasks; historical lookup explicitly refused. No task deletion or historical preservation acceptance inferred.' }; h.persist();
  h.observe({ kind: 'historical-effect-task-query-capability-gap', ...r.lifecycleHistoryGap }); return true;
}
function lifecycleBaseline(trace, r, request) {
  const commands = request.scenarioCommands || [], activate = commands.at(-1), disable = commands.at(-2), rejected = r.commands.at(-1);
  if (commands.length !== 2 || disable.action !== 'disable' || disable.outcome !== 'confirmed' || activate.action !== 'activate' || !['unknown', 'confirmed'].includes(activate.outcome) ||
      rejected?.outcome !== 'unknown' || !disabledSourceRefusal(rejected.response) || r.commands.slice(0, -1).some(c => c.outcome !== 'confirmed') ||
      !same(disable.after, activate.before) || String(activate.before.id) !== r.identity.installationId)
    throw Error('Exact original disabled-source refusal and acknowledged lifecycle chain required');
  const failed = trace.filter(e => e.kind === 'assertion' && e.passed === false);
  const activationFailure = failed[0]?.message === 'Exact original conditional activate receipt and independent owner preserve runtime/storage identities' && same(failed[0].details, activate);
  const historyFailure = failed[0]?.message === 'Disable/activate and rejected reception keep all original source/target rows and complete task/attempt history' &&
    activate.outcome === 'confirmed' && trace.some(e => e.kind === 'assertion' && e.passed === true && same(e.details, activate));
  if (failed.length !== 1 || !(activationFailure || historyFailure)) throw Error('Original failed lifecycle evidence differs from the retained command');
  const cut = trace.findIndex(e => e.kind === 'request' && e.method === 'POST' && e.route === disable.route && same(e.body, disable.body) && same(e.response, disable.response));
  if (cut < 0 || !trace.slice(cut).some(e => e.kind === 'request' && e.method === 'POST' && e.route === route(r, false) &&
      same(e.actor, r.actorIdentity) && e.origin === r.origin && same(e.body, rejected.body) && same(e.response, rejected.response)))
    throw Error('Original lifecycle/source requests are missing from immutable evidence');
  const before = trace.slice(0, cut), result = {};
  for (const [key, entity] of [['sources', r.entity], ['targets', r.targetEntity]]) {
    const event = before.filter(e => {
      if (e.kind !== 'request' || e.method !== 'GET' || e.origin !== r.origin || !same(e.actor, r.actorIdentity)) return false;
      const u = new URL(e.route, r.origin);
      return u.pathname === '/apps/entity/values/' && u.searchParams.get('application') === r.applicationKey &&
        u.searchParams.get('deploymentId') === r.identity.deploymentId && u.searchParams.get('entity') === entity &&
        u.searchParams.get('_pageNum') === '1' && u.searchParams.get('_pageSize') === '5';
    }).at(-1);
    if (event?.response?.status !== 200) throw Error('Original complete collection snapshot missing');
    const page = require('./business_collection_cases.cjs').decodeCollection(event.response.data, 'offset', 1, 5);
    if (page.rows.length !== page.pagination.total || page.pagination.hasMore) throw Error('Original collection snapshot is incomplete');
    result[key] = page.rows;
  }
  const task = before.filter(e => e.kind === 'request' && e.method === 'POST' && e.route === '/panel/application/installations/' + r.identity.installationId + '/effects/search' &&
    same(e.body?.identity, r.identity) && e.body.cursor === '' && e.body.limit === 50 && ['', '[REDACTED]'].includes(e.body.state)).at(-1);
  if (task?.response?.status !== 200 || task.response.data.error) throw Error('Original task snapshot missing');
  const page = task.response.data.value, { sanitize } = require('./evidence_sanitizer.cjs');
  if (page?.nextCursor !== '' || page.values?.length !== 1 || !same(page.identity, r.identity) ||
      !same(page.values, sanitize([r.task])) && !same(page.values, [r.task]) ||
      !before.some(e => e.kind === 'assertion' && e.passed === true && e.message === 'Durable original task completed with actual attempt and no failure') ||
      !same(result.targets, sanitize(r.targets)) && !same(result.targets, r.targets) ||
      !result.sources.some(v => String(v.id) === r.receipt.id)) throw Error('Original task/source/target baseline incomplete or changed');
  decodeTasks({ ...page, values: [r.task] }, r.identity, page.manager, '');
  // The evidence sanitizer redacts a request field named state. Retain the
  // actual returned task observations; do not reconstruct its original filter
  // or claim historical/unfiltered completeness from that redacted field.
  result.tasks = [r.task]; return result;
}
async function reconcileLifecycle(h, r, evidence, caseSha256) {
  const requests = h.state.resources.filter(v => v.kind === 'deployment-review-request' && v.phase !== 'deleted' && String(v.installation?.id) === r.identity.installationId);
  const parents = h.state.resources.filter(v => v.kind === 'definition' && v.id === r.scenarioDefinitionId && v.modelDelivery?.requests?.includes(requests[0]?.id));
  h.check('Original source recovery binds one owned installation, definition and exact failed case', requests.length === 1 && parents.length === 1 &&
    ['F033-001', 'F071-005'].includes(evidence.caseId) && evidence.status === 'failed' && /^sha256:[a-f0-9]{64}$/.test(caseSha256 || ''));
  const request = requests[0], before = lifecycleBaseline(evidence.trace, r, request), command = request.scenarioCommands.at(-1);
  const actor = await business.member(h, 'manager');
  h.check('Recovery retains original source producer and lifecycle owner', actor.origin === r.origin && same(actor.identity, r.actorIdentity) &&
    command.origin === h.admin.origin && same(command.actorIdentity, h.admin.identity));
  const installation = (await h.ok(h.admin, 'GET', '/panel/application/installations/' + r.identity.installationId)).value;
  h.check('Original acknowledged activation independently confirms current exact installation without replay',
    require('./installation_control_cases.cjs').confirms(h, command.before, command, installation));
  const metadata = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + r.applicationKey + '?deploymentId=' + r.identity.deploymentId)).value;
  const delivery = parents[0].modelDelivery, current = { ...r, instance: installation, identity: metadata.readIdentity };
  h.check('Current owner read identity retains original frozen installation and artifact', business.installationMatches(delivery, installation, current.identity));
  const currentSources = await collection(h, actor, current), currentTargets = await collection(h, actor, { ...current, entity: r.targetEntity });
  const { sanitize } = require('./evidence_sanitizer.cjs');
  const originalSource = currentSources.find(v => String(v.id) === r.receipt.id);
  h.check('Original recorded source fields and privately journaled source/target values remain unchanged after activation',
    same(sanitize(currentSources), before.sources) && same(sanitize(currentTargets), before.targets) && same(currentTargets, r.targets) &&
    !!originalSource && r.commands[0].body.fields.every(v => same(originalSource[v.name], v.value)));
  const historyGap = await observeLifecycleHistory(h, r, current, before.tasks, await tasks(h, current));
  command.outcome = 'confirmed'; request.installation = installation;
  r.commands.at(-1).outcome = historyGap ? 'rejected-source-and-targets-unchanged' : 'rejected-and-unchanged'; r.postLifecycleIdentity = current.identity; r.dispositionReady = true;
  r.lifecycleRecovery = { caseId: evidence.caseId, caseSha256, before, historyGap, noCommandReplayed: true, installationId: installation.id,
    taskScope: 'Original private task/target journal bound to sanitized immutable response plus recorded successful completion assertion; source redacted fields independently compared to original submitted fields. Request filter is not reconstructed. No historical visibility acceptance. Formal destroy owner separately proves retirement safety.' }; h.persist();
  const grants = h.state.resources.filter(v => v.kind === 'member-access-retirement' && v.phase !== 'deleted' && String(v.installation?.id) === r.identity.installationId);
  for (const grant of grants) await require('./application_authority_cases.cjs').retireAccess(h, grant);
  await require('./deployment_review_cases.cjs').cleanup(h, request);
  h.check('Original installation formally destroy-retired after exact source intent reconciliation', request.phase === 'deleted' && request.retiredInstallation?.status === 'uninstalled');
  r.phase = 'deleted'; r.disposition = 'Original acknowledged activation and explicit disabled-source rejection reconciled using immutable source/target snapshots; historical query gap retained. Original grant and installation formally retired with owner proofs, original failed case and recorded task evidence retained.'; h.persist();
  return r.lifecycleRecovery;
}
async function submit(h, actor, r, body) {
  original(h, actor, r);
  const c = { body: structuredClone(body), outcome: 'unknown' }; r.commands.push(c); h.persist();
  // Even when execute loses its response, only the original receipt is queried.
  try { c.response = await h.api(actor, 'POST', route(r, false), body); }
  catch (error) { c.transportError = error.message; }
  h.persist();
  c.query = await h.api(actor, 'POST', route(r, true), body); h.persist();
  h.check('Independent source receipt binds exact original producer, payload, installation, source and durable task intent', h.good(c.query) &&
    receiptMatches(actor, body, c.query.data.value) && (!c.response || h.good(c.response) && same(c.response.data.value, c.query.data.value)), c.query);
  if (actor.origin !== r.origin || !same(actor.identity, r.actorIdentity)) throw new h.Blocked('Original source producer changed during confirmation');
  c.receipt = c.query.data.value; c.outcome = 'confirmed'; r.receipt ||= c.receipt; r.phase = 'created'; h.persist();
  return c.receipt;
}
function decodeTasks(value, identity, manager, cursor) {
  if (!same(value?.identity, identity) || value.manager !== manager || !Array.isArray(value.values) || value.values.length > 50 ||
      typeof value.nextCursor !== 'string' || value.nextCursor && (!/^[a-f0-9]{32}$/.test(value.nextCursor) || value.nextCursor <= cursor || value.nextCursor !== value.values.at(-1)?.intentId) ||
      value.values.some((v, i) => !/^[a-f0-9]{32}$/.test(v.intentId || '') || v.intentId <= (i ? value.values[i - 1].intentId : cursor) ||
        !/^[1-9][0-9]*$/.test(v.version || '') || !/^(0|[1-9][0-9]*)$/.test(v.attempts || '') ||
        !['pending', 'running', 'retry-wait', 'blocked', 'failed', 'completed'].includes(v.state))) throw Error('Complete exact original task page required');
  return value;
}
async function tasks(h, context) {
  const manager = 'panel/account:' + (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account.id;
  let cursor = ''; const rows = [];
  for (let n = 0; n < 100; n++) {
    const result = await h.ok(h.admin, 'POST', '/panel/application/installations/' + context.identity.installationId + '/effects/search', { identity: context.identity, cursor, limit: 50, state: '' });
    const page = decodeTasks(result.value, context.identity, manager, cursor); rows.push(...page.values);
    if (!page.nextCursor) return rows;
    cursor = page.nextCursor;
  }
  throw new h.Blocked('Original task collection exceeds finite read budget; no absence or completion claim');
}
async function completed(h, r) {
  const effect = r.receipt.source.effects[0];
  for (let n = 0; n < 60; n++) {
    const found = (await tasks(h, r)).filter(v => v.intentId === effect.intentId);
    h.check('Independent Panel/Base task projection retains one exact original source and binding intent', found.length === 1 &&
      found[0].subject === effect.subject && found[0].sourceEntity === effect.sourceEntity && found[0].sourceId === effect.sourceId && found[0].bindingKey === effect.bindingKey, found);
    r.task = found[0]; h.persist();
    if (r.task.state === 'completed') {
      h.check('Durable original task completed with actual attempt and no failure', BigInt(r.task.attempts) > 0n && !r.task.errorCode && !r.task.errorMessage && r.task.nextAttemptAt === 0);
      return r.task;
    }
    if (['blocked', 'failed'].includes(r.task.state)) break;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new h.Blocked('Original source task has no confirmed completion; retain exact source/target/grant/installation, no replacement source');
}
async function authorFreeze(h) {
  const { f } = await fixture(h, 'effectfreeze'); let primary;
  try {
    const original = f.revision, draft = await a.draft(h, f.application), changed = structuredClone(draft.entities);
    h.check('Frozen source program retains exact original file bytes and typed array output declaration',
      original.content.functionBlocks.files['derive/main.go'] === b64(sourceProgram) &&
      same(JSON.parse(Buffer.from(original.content.functionBlocks.files['derive/definition.json'], 'base64')).outputs, [{ name: 'items', type: 'array', required: true }]));
    const source = changed.find(v => v.blockInfo?.some(b => b.key === 'derive'));
    source.description = '尚未发布的来源描述';
    await a.save(h, f.application, draft, changed);
    h.check('Draft author edit leaves entire original frozen source, target, program, mapping and installed digests unchanged',
      same((await h.ok(h.admin, 'GET', '/panel/application/definitions/' + f.application.id + '/revisions/' + original.id)).value, original) &&
      f.installations.every(v => v.sourceDigest === f.package.artifactDigest && v.receipt.revisionId === original.id));
    const resource = f.resource, current = await a.draft(h, f.application);
    await require('./scenario_commands.cjs').reject(h, resource, h.admin, 'PUT', '/panel/application/definitions/' + f.application.id + '/model-draft',
      a.command(draft, changed), ['/panel/application/definitions/' + f.application.id + '/model-draft'], { code: 19, messagePattern: '版本|version|changed|conflict' });
    h.check('Stale source draft save preserves complete current owner models', same(await a.draft(h, f.application), current));
  } catch (error) { primary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, f, primary); }
  await h.partial('Pure file program/typed I/O, append-only source and protected target binding author save, full ZIP checksums/import, double installation, stale-save refusal and mutable draft/frozen separation implemented. Real author cancellation, unsupported-consumer deployment and calculation-vs-automatic UI remain open.');
}
async function reception(h, atomic = false, draftMutation = false, lifecycleCase) {
  const suffix = lifecycleCase === 'F033-001' ? 'effectinstall' : lifecycleCase ? 'effectlifecycle' : draftMutation ? 'effectoriginal' : atomic ? 'effecttargets' : 'effectsource';
  const { f, actor, contexts } = await fixture(h, suffix), context = contexts[0], targetContext = { ...context, entity: context.targetEntity };
  if (draftMutation) {
    const route = '/panel/application/definitions/' + f.application.id + '/function-blocks';
    const editable = structuredClone((await h.ok(h.admin, 'GET', route)).value.content);
    h.check('Author draft starts from the exact frozen original program', editable.files['derive/main.go'] === b64(sourceProgram));
    editable.files['derive/main.go'] = b64(sourceProgram.replace('"first"', '"UNPUBLISHED_FIRST"').replace('"second"', '"UNPUBLISHED_SECOND"'));
    await libraryOwner.saveLibrary(h, f.application, editable);
    const before = await a.draft(h, f.application), entities = structuredClone(before.entities);
    entities.find(v => v.name === 'zzDerivedTarget').description = '未发布目标规则说明';
    await a.save(h, f.application, before, entities);
    h.check('Independent author edit and target save preserve every original frozen program, binding and model byte',
      same((await h.ok(h.admin, 'GET', '/panel/application/definitions/' + f.application.id + '/revisions/' + f.revision.id)).value, f.revision));
  }
  const baseline = await collection(h, actor, targetContext), peerTasks = await tasks(h, contexts[1]), peerRows = await collection(h, actor, { ...contexts[1], entity: contexts[1].targetEntity });
  const r = { kind: 'source-effect-scenario', phase: 'intent', scenarioDefinitionId: f.application.id, ...context,
    origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [] };
  h.state.resources.push(r); h.persist();
  const body = business.request(r, 'create', [{ name: 'code', value: 'SRC-' + crypto.randomBytes(8).toString('hex').toUpperCase() },
    { name: 'name', value: '原来源输入' }, { name: 'description', value: null }, { name: 'sortOrder', value: 0 }], { apiVersion: version });
  const receipt = await submit(h, actor, r, body);
  h.check('Confirmed same-input source retry returns the exact original durable receipt', same(await submit(h, actor, r, body), receipt));
  await completed(h, r);
  const source = await business.record(h, actor, { ...context, recordId: receipt.id });
  h.check('Independent actual source row matches original allocated identity and all submitted scalar values', h.good(source) && String(source.data.value.id) === receipt.id &&
    body.fields.every(v => same(source.data.value[v.name], v.value)));
  const after = await collection(h, actor, targetContext), newRows = after.filter(v => !baseline.some(p => String(p.id) === String(v.id)));
  h.check('Completed original task produces exactly two real distinct target primary keys and declared output values', newRows.length === 2 &&
    new Set(newRows.map(v => String(v.id))).size === 2 && new Set(newRows.map(v => v.code)).size === 2 && newRows.every(v => v.code === targetCode(context.identity.deploymentId, source.data.value.code, v.name) && String(v.version) === '1') &&
    same(newRows.map(v => v.name).sort(), ['first', 'second']) && baseline.every(v => after.some(p => same(p, v))), newRows);
  for (const row of newRows) h.check('Independent exact target owner detail matches every complete collection field',
    same((await business.record(h, actor, { ...targetContext, recordId: String(row.id) })).data.value, row));
  r.targets = newRows; h.persist();
  if (!atomic) {
    const c = { body: { ...structuredClone(body), fields: body.fields.map(v => v.name === 'name' ? { ...v, value: 'CONFLICT MUST NOT APPLY' } : v) }, outcome: 'unknown' };
    r.commands.push(c); h.persist(); c.response = await h.api(actor, 'POST', route(r, false), c.body); h.persist();
    const stable = await h.ok(actor, 'POST', route(r, true), body);
    const currentSource = await business.record(h, actor, { ...context, recordId: receipt.id });
    const refused = [200, 409].includes(c.response.status) && c.response.data?.error?.code === 21 && c.response.data.error.message === '原业务写入身份或输入不匹配' && c.response.data.value == null;
    if (refused && same(stable.value, receipt) && h.good(currentSource) && same(currentSource.data.value, source.data.value) &&
        same(await collection(h, actor, targetContext), after)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
    h.check('Exact payload-conflict refusal preserves original source, durable receipt and all actual target effects', c.outcome === 'rejected-and-unchanged', c.response);
  }
  const originalTask = structuredClone(r.task);
  h.check('Source confirmed replay and conflict checks preserve original task identity and completed attempt history', same(await completed(h, r), originalTask));
  if (lifecycleCase) {
    const request = f.pageRequests[0], control = require('./installation_control_cases.cjs').control;
    const beforeTasks = await tasks(h, context), beforeSources = await collection(h, actor, context);
    await control(h, request, 'disable'); f.installations[0] = request.installation;
    const c = { body: business.request(r, 'create', [{ name: 'code', value: 'SRC-' + crypto.randomBytes(8).toString('hex').toUpperCase() },
      ...body.fields.filter(v => v.name !== 'code')], { apiVersion: version }), outcome: 'unknown' };
    r.commands.push(c); h.persist();
    try { c.response = await h.api(actor, 'POST', route(r, false), c.body); }
    catch (error) { c.transportError = error.message; }
    h.persist();
    const denied = c.response;
    // Retain an ambiguous write even if the instance is currently disabled.
    h.check('Disabled original installation refuses source reception at the exact runtime lookup gate', disabledSourceRefusal(denied), denied);
    await control(h, request, 'activate'); f.installations[0] = request.installation;
    const metadata = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
    h.check('Reactivated read identity belongs to the exact original installation and deployment', business.installationMatches(f, request.installation, metadata.readIdentity));
    const current = { ...context, instance: request.installation, identity: metadata.readIdentity };
    const sameData = same(await collection(h, actor, current), beforeSources) &&
      same(await collection(h, actor, { ...current, entity: context.targetEntity }), after);
    h.check('Disable/activate and rejected reception keep all original complete source and target rows unchanged', sameData);
    const historyGap = await observeLifecycleHistory(h, r, current, beforeTasks, await tasks(h, current));
    c.outcome = historyGap ? 'rejected-source-and-targets-unchanged' : 'rejected-and-unchanged'; r.postLifecycleIdentity = current.identity; h.persist();
  }
  h.check('Other actual instance retains entire independent task and target collections', same(await tasks(h, contexts[1]), peerTasks) &&
    same(await collection(h, actor, { ...contexts[1], entity: contexts[1].targetEntity }), peerRows));
  r.dispositionReady = true; h.persist();
  // Append-only data is retired only by the exact installation owner; no
  // ordinary DELETE, direct SQL or data rewrites are used for cleanup.
  await pages.disposeExplicitFixture(h, f);
  h.check('Exact source and target installation destroy finishes through formal owner while retaining source task evidence',
    f.pageRequests.every(v => v.phase === 'deleted' && v.retiredInstallation?.id === v.installation.id && v.retiredInstallation.status === 'uninstalled' &&
      v.retiredInstallation.receipt?.uninstallation?.dataDisposition === 'destroy'));
  r.phase = 'deleted'; r.disposition = 'Completed original source/task and independently read target rows; exact installations formally destroy-retired, immutable journal retained.'; h.persist();
  await h.partial(lifecycleCase ? 'Real dual model installation, completed source/task/target evidence before lifecycle, conditional disable/activate, exact disabled source refusal, full source/target and peer preservation, and formal destroy with storage/authorization receipts implemented. Current task query is generation-scoped; historical-generation visibility is explicitly unavailable and remains unverified. Retain/restore, in-flight lifecycle, full Gateway/File residuals, claimant restart and late-lease fencing remain open.' : draftMutation ? 'Actual author program and target draft changed after installation; original ordinary producer then creates real source/task/targets using frozen original output and precise source/deployment-derived identities, with original subject, confirmed replay/conflict, peer preservation and formal destroy. Acceptance-before-author-edit race, pre-claim role revocation, Endpoint and lease/generation changes remain open.' : atomic ? 'Real committed source→durable completed task→two protected unique target rows, exact owner detail/list, confirmed replay no duplicate, peer preservation and formal destroy implemented. Target batch failure, target relationships, post-commit lost response and repeated owner recovery remain open.' :
    'Reliable original source, same-input confirmed replay, payload conflict, original durable source/task linkage, real derived targets, double-instance preservation and formal destroy implemented. Actual response-loss fault, natural-key duplicate with different operation, Endpoint and cross-tenant/binding forgery remain open.');
}
const handlers = { 'F071-001': authorFreeze, 'F071-002': h => reception(h), 'F071-003': h => reception(h, false, true), 'F071-004': h => reception(h, true), 'F033-001': h => reception(h, true, false, 'F033-001'), 'F071-005': h => reception(h, true, false, 'F071-005') };
for (const handler of Object.values(handlers)) { handler.transport = 'owner-api'; handler.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers, effectEntities, receiptMatches, decodeTasks, submit, route, sourceProgram, targetCode, disabledSourceRefusal, lifecycleBaseline, reconcileLifecycle, historyVisibilityGap };
