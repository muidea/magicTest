// Calculation debug is not execution: this fixture installs the authored
// interpreter binding and independently reads its actual committed output.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
async function prepare(h, authored) {
  await a.library(h, authored.app);
  const entity = structuredClone(authored.model.entities[0]);
  entity.blockInfo = [await a.scriptBinding(h)];
  authored.model = await a.save(h, authored.app, await a.draft(h, authored.app), [entity]);
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
function outputMatches(value, body, receipt) {
  const submitted = Object.fromEntries(body.fields.map(f => [f.name, f.value]));
  return !!value && String(value.id) === receipt.id && String(value.version) === receipt.version &&
    value.description === submitted.name && Object.entries(submitted).every(([k, v]) => k === 'description' || same(value[k], v));
}
async function execute(h) {
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'builtinexecute', requestPrefix: 'builtin-execute-', prepareAuthor: prepare });
  const actor = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, actor), peer = await business.runtime(h, f, 1, actor), rows = [];
  let primary;
  try {
    for (const name of ['真实绑定 Δ <&>', '第二次真实绑定']) {
      const r = { kind: 'business-record', actorRole: 'manager', phase: 'intent', ...context, scenarioDefinitionId: f.application.id,
        origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [] };
      delete r.ui; rows.push(r); h.state.resources.push(r); h.persist();
      const body = business.request(r, 'create', [{ name: 'code', value: 'RG-' + crypto.randomBytes(8).toString('hex').toUpperCase() },
        { name: 'name', value: name }, { name: 'description', value: '必须被正式脚本结果覆盖' }, { name: 'sortOrder', value: 0 }]);
      const receipt = await business.execute(h, actor, r, body), actual = await business.record(h, actor, r);
      h.check('Installed insert interpreter writes its declared output to the exact committed row, without a debug invocation',
        h.good(actual) && outputMatches(actual.data.value, body, receipt), actual);
      r.created = actual.data.value; h.persist();
      await business.execute(h, actor, r, body, true);
      h.check('Confirmed replay does not rerun the insert binding or allocate another business row', same((await business.record(h, actor, r)).data.value, r.created));
      const absent = await business.record(h, actor, { ...peer, recordId: r.recordId });
      h.check('Other installed instance has no derived field or original business row', [200, 404].includes(absent.status) && absent.data?.error?.code === 2 && absent.data.value == null, absent);
    }
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    if (!rows.some(r => r.phase !== 'deleted')) await pages.disposeExplicitFixture(h, f, primary);
  }
  await h.partial('Installed interpreter insert binding, typed scalar inputs/output, actual persisted field, independent ordinary owner reads, confirmed replay and dual-instance isolation implemented. Log/business-code/counter/masking/todo blocks and their update/concurrency matrix still require dedicated producer fixtures.');
}
execute.transport = 'owner-api';
module.exports = { handlers: { 'F015-001': execute }, outputMatches };
