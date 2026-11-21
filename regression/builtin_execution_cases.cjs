// Calculation debug is not execution: this fixture installs the authored
// interpreter binding and independently reads its actual committed output.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const pages = require('./page_runtime_cases.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const { portalBasicProfileSet } = require('./platform_profiles.cjs');
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
  await extraBuiltinBlocks(h);
}
async function extraBuiltinBlocks(h) {
  const obs = require('./application_observation_cases.cjs');
  const authority = require('./application_authority_cases.cjs');
  const { collection } = require('./business_collection_cases.cjs');
  const clone = v => structuredClone(v);
  const f = await pages.explicitFixture(h, undefined, undefined, {
    suffix: 'builtinfull', requestPrefix: 'builtin-full-',
    prepareAuthor: async (h, authored) => {
      await obs.prepare(h, authored);
      const baseRoute = '/panel/application/definitions/' + authored.app.id + '/function-blocks';
      const beforeLib = (await h.ok(h.admin, 'GET', baseRoute)).value;
      const source = 'package block\nimport "context"\nfunc Handle(ctx context.Context,input,output map[string]any) error { output["result"]=input["label"]; return nil }';
      const spec = { key: 'display', name: '内置全量脚本', language: 'go', sourceFiles: ['display/main.go'], entrypoint: { file: 'display/main.go', function: 'block.Handle' },
        inputs: [{ name: 'count', type: 'number', required: true }, { name: 'enabled', type: 'boolean', required: true }, { name: 'label', type: 'string', required: true }],
        outputs: [{ name: 'result', type: 'string', required: true }] };
      const content = { schemaVersion: beforeLib.content.schemaVersion, definitions: [{ key: 'display', definition: 'display/definition.json' }],
        files: { 'display/definition.json': Buffer.from(JSON.stringify(spec)).toString('base64'), 'display/main.go': Buffer.from(source).toString('base64') } };
      await h.ok(h.admin, 'PUT', baseRoute, { expectedDefinitionVersion: beforeLib.definitionVersion, content });
      const latestModel = await a.draft(h, authored.app);
      const entity = clone(latestModel.entities[0]);
      const catalog = (await h.ok(h.admin, 'GET', '/panel/application/definition/entity/blocks/')).values;
      const interp = clone(catalog.find(x => x.kind === 'scriptInterpreter'));
      const insertHook = clone(interp.stageInfo.functions.insert);
      Object.assign(insertHook, { eventID: '/interpreter/script', bindScript: null, checkType: 'preCheck',
        input: { count: 1, enabled: true, label: '$referenceValue.name' }, bindField: 'description', resultField: 'result', executeTimeout: 1000 });
      const updateHook = clone(insertHook);
      updateHook.input = { count: 2, enabled: true, label: '$referenceValue.name' };
      const cg = clone(catalog.find(x => x.kind === 'codeGenerator'));
      cg.stageInfo.startup.input.namespace = h.admin.identity.namespace;
      cg.stageInfo.teardown.input.namespace = h.admin.identity.namespace;
      cg.stageInfo.functions.insert.input.namespace = '$referenceExtData.namespace';
      for (const fn of [cg.stageInfo.startup, cg.stageInfo.teardown, cg.stageInfo.functions.insert]) {
        fn.input.owner = 'builtin-cg';
      }
      cg.stageInfo.startup.input.name = '内置编码'; cg.stageInfo.startup.input.pattern = 'CG-{fixed(4):1}'; cg.stageInfo.startup.input.initValue = 'CG-0001';
      cg.stageInfo.functions.insert.bindField = 'code'; cg.stageInfo.functions.insert.input.bindField = 'code';
      const mk = clone(catalog.find(x => x.kind === 'masking'));
      for (const st of Object.values(mk.stageInfo.functions || {})) { st.bindField = 'name'; st.input.maskValue = '***MASKED***'; st.input.bindField = 'name'; }
      const opLog = entity.blockInfo.find(b => b.key === 'log');
      if (opLog?.stageInfo?.functions?.insert) opLog.stageInfo.functions.update = clone(opLog.stageInfo.functions.insert);
      entity.blockInfo.push(
        { id: cg.id, key: 'cg-code', name: '自动编码', stageInfo: cg.stageInfo },
        { id: interp.id, key: 'script-desc', name: '脚本映射', scriptKey: 'display', stageInfo: { startup: null, teardown: null, functions: { insert: insertHook, update: updateHook } } },
        { id: mk.id, key: 'mask-name', name: '姓名脱敏', stageInfo: mk.stageInfo },
      );
      authored.model = await a.save(h, authored.app, latestModel, [entity]);
      authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
    },
  });
  const actor = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, actor);
  const casBase = '/cas/namespaces/panel/';
  const templates = await h.directory(h.admin, casBase + 'role-templates/');
  const ordinary = portalBasicProfileSet(templates);
  h.check('Protected ordinary profiles are present for builtin observation fixture', ordinary.complete);
  const roleMod = '/applications/' + context.identity.deploymentId;
  const obsRefs = obs.readers.map(r => ({ module: roleMod, key: r.role }));
  const group = await h.create(casBase + 'role-templates/', {
    key: h.state.prefix + '-builtin-obs', name: '全量内置观察', scene: 'operations', subjectType: 'account', status: 2, applicationAccess: [],
    roleRefs: obsRefs,
  }, 'role-template');
  const member = await authority.account(h, 'builtin-obs');
  member.resource.scenarioDefinitionId = f.application.id;
  member.resource.scenarioInstallationIds = f.installations.map(i => String(i.id)); h.persist();
  await authority.assign(h, member, group, [], { expectedRoles: [...ordinary.roleRefs, ...obsRefs] });
  const rows = []; let primary;
  try {
    // 1. Concurrent creates exercise codeGenerator uniqueness, scriptInterpreter insert, masking on query/filter, operationlog & totalizator.
    const batch = ['并发内置-A', '并发内置-B'].map((nm, idx) => {
      const r = { kind: 'business-record', actorRole: 'manager', phase: 'intent', ...context, scenarioDefinitionId: f.application.id,
        origin: actor.origin, actorIdentity: clone(actor.identity), commands: [] };
      delete r.ui; rows.push(r); h.state.resources.push(r); h.persist();
      const body = business.request(r, 'create', [
        { name: 'code', value: 'SEED-' + idx }, { name: 'name', value: nm }, { name: 'description', value: 'raw' }, { name: 'sortOrder', value: idx },
      ]);
      return business.execute(h, actor, r, body).then(() => ({ r, nm }));
    });
    const created = await Promise.all(batch);
    const codes = [];
    for (const { r, nm } of created) {
      const rec = (await business.record(h, actor, r)).data.value;
      r.created = rec; h.persist(); codes.push(rec.code);
      h.check('codeGenerator assigns sequence code, scriptInterpreter sets description from submitted name, and masking obscures queried name',
        /^CG-\d{4}$/.test(rec.code) && rec.description === nm && rec.name === '***MASKED***', rec);
    }
    h.check('Concurrent inserts allocate strictly distinct generated business codes', new Set(codes).size === 2, codes);
    const listRows = await collection(h, actor, context);
    h.check('Collection filter read also applies masking PostCheck to every record',
      listRows.length === 2 && listRows.every(v => v.name === '***MASKED***'), listRows);

    // 2. Concurrent same-version updates exercise scriptInterpreter update stage and version conflict fence cleanly.
    const target = created[0].r;
    const updBodies = ['更新成功-U1', '冲突更新-U2'].map(nm => ({
      r: target, body: business.request(target, 'update', [{ name: 'name', value: nm }, { name: 'description', value: 'raw' }]), nm,
    }));
    const updRoutes = updBodies.map(u => '/apps/entity/value/write/update/execute/?application=' + encodeURIComponent(target.applicationKey) + '&deploymentId=' + target.identity.deploymentId);
    const updCmds = updBodies.map((u, i) => ({ route: updRoutes[i], body: u.body, outcome: 'unknown' }));
    target.commands.push(...updCmds); h.persist();
    await Promise.all(updCmds.map((c, i) => h.api(actor, 'POST', updRoutes[i], updBodies[i].body).then(res => { c.response = res; })));
    const wonIdx = updCmds.findIndex(c => h.good(c.response));
    const lostIdx = 1 - wonIdx;
    h.check('Concurrent updates accept one version and reject stale rival',
      wonIdx >= 0 && !h.good(updCmds[lostIdx].response) && updCmds[lostIdx].response.data?.error?.code === 19, updCmds);
    updCmds[wonIdx].outcome = 'confirmed'; updCmds[wonIdx].receipt = updCmds[wonIdx].response.data.value;
    updCmds[lostIdx].outcome = 'rejected-conflict';
    target.version = updCmds[wonIdx].receipt.version; h.persist();
    const afterUpd = (await business.record(h, actor, target)).data.value;
    h.check('scriptInterpreter update stage transforms description while masking keeps name masked on read',
      afterUpd.description === updBodies[wonIdx].nm && afterUpd.name === '***MASKED***' && String(afterUpd.version) === target.version, afterUpd);

    // 3. Independent owner reads confirm operationlog & totalizator emissions.
    const logs = await obs.read(h, member.actor, context, 'operation-logs', true);
    const counters = await obs.read(h, member.actor, context, 'counters', true);
    h.check('Operation logs and totalizator counters record concurrent creates and confirmed update',
      logs.length >= 3 && counters.length >= 1, { logsCount: logs.length, counters });
  } catch (error) { primary = error; throw error; }
  finally {
    try { await require('./business_action_cases.cjs').revoke(h, member, group, ordinary); } catch {}
    await business.finishCleanup(h, [...rows].reverse(), primary);
    if (!rows.some(r => r.phase !== 'deleted')) await pages.disposeExplicitFixture(h, f, primary);
  }
}
execute.transport = 'owner-api';
module.exports = { handlers: { 'F015-001': execute }, outputMatches };
