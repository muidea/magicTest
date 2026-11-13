// Normal source writes invoke the installed builtin. No synthetic HTTP event,
// private table writes or inferred completed-todo history.
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const { authoring: author } = require('./authoring_cases.cjs');
const action = 'regression-todo-sync';
function binding(catalog, namespace) {
  const declaration = catalog.find(v => v.kind === 'todo');
  if (!declaration?.id || !namespace || !['insert', 'update', 'delete'].every(k => declaration.stageInfo?.functions?.[k]))
    throw Error('Formal todo catalogue must declare all source lifecycle hooks');
  const functions = structuredClone(declaration.stageInfo.functions);
  for (const [operation, hook] of Object.entries(functions)) {
    Object.assign(hook.input, { namespace, sourceIDField: 'id', sourceAction: action });
    if (operation !== 'delete') Object.assign(hook.input, { statusField: 'description', pendingStatuses: ['pending'], doneStatuses: ['approved'],
      titleTemplate: '{name}', contentTemplate: '{name}:{description}', route: '' });
  }
  return { id: declaration.id, key: 'todo-source', stageInfo: { functions } };
}
async function prepare(h, authored) {
  const catalog = (await h.ok(h.admin, 'GET', '/panel/application/definition/entity/blocks/')).values;
  const entity = structuredClone(authored.model.entities[0]);
  entity.blockInfo = [binding(catalog, h.admin.identity.namespace)];
  authored.model = await author.save(h, authored.app, await author.draft(h, authored.app), [entity]);
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
function sourceIdentity(r) {
  return [r.identity.runtimeApplicationUuid, r.identity.namespace, r.entity, r.recordId, action].join(':');
}
function matchesSource(t, r) {
  return t.identity === sourceIdentity(r) || t.hostedBy === r.identity.runtimeApplicationUuid &&
    t.sourceEntity === r.entity && t.sourceID === r.recordId;
}
function pendingMatches(values, r, row, original) {
  const matches = values.filter(t => matchesSource(t, r));
  if (matches.length !== 1) return false;
  const t = matches[0];
  return t.id > 0 && t.identity === sourceIdentity(r) && t.namespace === r.identity.namespace &&
    t.hostedBy === r.identity.runtimeApplicationUuid && t.sourceKey === r.identity.runtimeApplicationUuid &&
    t.sourceEntity === r.entity && t.sourceID === r.recordId && t.sourceAction === action && t.status === 'pending' &&
    t.title === row.name && t.content === row.name + ':pending' && t.finishTime === 0 &&
    (!original || t.id === original.id && t.identity === original.identity && t.createTime === original.createTime && t.updateTime >= original.updateTime);
}
async function observe(h, r, row, present = true) {
  const original = r.todoSync.pending;
  let values;
  for (let attempt = 0; attempt < 10; attempt++) {
    values = await h.directory(h.admin, '/panel/todos/');
    if (present ? pendingMatches(values, r, row, original) : !values.some(t => matchesSource(t, r))) break;
    if (attempt < 9) await new Promise(resolve => setTimeout(resolve, 500));
  }
  h.check(present ? 'One durable-source pending projection retains exact identity and current source content' : 'Independent fresh pending projection excludes the exact terminal original source',
    present ? pendingMatches(values, r, row, original) : !values.some(t => matchesSource(t, r)), { source: sourceIdentity(r), values: values.filter(t => matchesSource(t, r)) });
  if (present) r.todoSync.pending = structuredClone(values.find(t => t.identity === sourceIdentity(r)));
  r.todoSync.pendingAbsent = !present;
  h.persist();
}
async function confirmSourceExit(h, r) {
  // Called by ordinary business cleanup before its phase can become deleted.
  // A stale pending item must retain the original installation and grant.
  await observe(h, r, undefined, false);
  r.todoSync.disposition = 'Original reliable source DELETE acknowledged and original business row independently absent; Panel pending absence. Base terminal history not read.';
  h.persist();
}
async function update(h, actor, r, name, status) {
  const current = await business.record(h, actor, r);
  h.check('Original source is readable at its latest acknowledged version before a new update', h.good(current) &&
    String(current.data.value?.id) === r.recordId && String(current.data.value?.version) === r.version, current);
  const before = current.data.value;
  const receipt = await business.execute(h, actor, r, business.request(r, 'update', [{ name: 'name', value: name }, { name: 'description', value: status }]));
  const after = await business.record(h, actor, r);
  h.check('Independent original business owner confirms exact source status and complete sparse update', h.good(after) &&
    same(after.data.value, { ...before, name, description: status, version: Number(receipt.version) }), after);
  return after.data.value;
}
async function synchronize(h) {
  const f = await pages.explicitFixture(h, null, null, { suffix: 'todosync', requestPrefix: 'todo-sync-', prepareAuthor: prepare });
  const actor = await business.member(h, 'manager'), rows = [];
  let primary;
  try {
    for (let index = 0; index < 2; index++) {
      const context = await business.runtime(h, f, index, actor);
      const r = await business.create(h, { ...context, scenarioDefinitionId: f.application.id, todoSync: { phase: 'source-intent' } }, 'todo-source-' + index);
      rows.push(r); h.persist();
      const row = await update(h, actor, r, h.state.prefix + '-todo-' + index, 'pending');
      await observe(h, r, row);
    }
    const [r, peer] = rows, peerBusiness = (await business.record(h, actor, peer)).data.value, peerTodo = structuredClone(peer.todoSync.pending);
    for (const name of [h.state.prefix + '-same-source', h.state.prefix + '-same-source', h.state.prefix + '-new-content']) {
      const row = await update(h, actor, r, name, 'pending');
      await observe(h, r, row);
      h.check('Repeated normal updates preserve peer business source completely', same((await business.record(h, actor, peer)).data.value, peerBusiness));
      await observe(h, peer, peerBusiness);
      h.check('Other installation pending item keeps exact original identity and timestamps', same(peer.todoSync.pending, peerTodo));
    }
    await update(h, actor, r, h.state.prefix + '-done', 'approved');
    await observe(h, r, undefined, false);
    await observe(h, peer, peerBusiness);
    // Reopen the same source to demonstrate identity reuse, then test the
    // reverse lifecycle using the source's reliable DELETE in cleanup.
    const reopened = await update(h, actor, r, h.state.prefix + '-reopened', 'pending');
    await observe(h, r, reopened);
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    if (!rows.some(r => r.phase !== 'deleted')) await pages.disposeExplicitFixture(h, f, primary);
  }
  await h.partial('Real installed todo Update/Delete producers, repeated normal updates of one original source, same Todo ID/content, terminal pending exit/reopen, reliable source cleanup and dual-instance peer preservation implemented. Insert-pending production, exact event redelivery/concurrency and independent Base full terminal-history reads remain open; Panel pending absence is not terminal-storage proof.');
}
synchronize.transport = 'owner-api';
module.exports = { handlers: { 'F052-003': synchronize }, binding, sourceIdentity, matchesSource, pendingMatches, observe, confirmSourceExit, update };
