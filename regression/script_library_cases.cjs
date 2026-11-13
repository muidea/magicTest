// A new published definition is a retained fixture, not a deletable draft.
const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const definitions = '/panel/application/definitions/';
const b64 = s => Buffer.from(s).toString('base64');
const decode = s => Buffer.from(s, 'base64').toString();
function frozenLibraryMatches(revision, app, content) {
  const library = revision.content?.functionBlocks, index = library?.index;
  return index?.schemaVersion === content.schemaVersion && index.applicationKey === app.name && index.applicationUuid === app.uuid &&
    index.modelRevision === revision.version && same(index.definitions, content.definitions) &&
    Object.keys(library.files).length === Object.keys(content.files).length + 1 &&
    Object.entries(content.files).every(([name, bytes]) => library.files[name] === bytes) &&
    same(JSON.parse(decode(library.files['index.json'])), index);
}
async function saveLibrary(h, app, content) {
  const route = definitions + app.id + '/function-blocks', before = (await h.ok(h.admin, 'GET', route)).value;
  const c = a.journalSave(h, app, route, { expectedDefinitionVersion: before.definitionVersion, content });
  c.response = await h.ok(h.admin, 'PUT', route, c.payload); h.persist();
  const after = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Conditional script library command and independent reentry preserve every source/parameter file', after.definitionVersion > before.definitionVersion && same(after.content, content));
  c.confirmed = true; h.persist(); return after;
}
function guard(h, r) {
  if (r.scriptPublication && r.scriptPublication.outcome !== 'confirmed') throw new h.Blocked('Original script publication unresolved; retain author identity without DELETE or publication replay');
}
async function retained(h, r) {
  guard(h, r);
  const p = r.scriptPublication;
  if (!r.creation?.ownershipConfirmed || r.creation.origin !== h.admin.origin || !same(r.creation.actorIdentity, h.admin.identity) ||
      r.pendingAuthoringSave && !r.pendingAuthoringSave.confirmed || !p?.revision || !h.good(p.response) ||
      !same(p.response.data.value, p.revision) || p.revision.definitionVersion !== p.body.expectedDefinitionVersion ||
      p.revision.digest !== p.body.expectedPreviewDigest) throw new h.Blocked('Original retained script definition or source save not confirmed');
  const revision = (await h.ok(h.admin, 'GET', definitions + r.id + '/revisions/' + p.revision.id)).value;
  h.check('New script fixture retains its exact formally published immutable revision and original authoring identity', same(revision, p.revision) && revision.applicationDefinitionId === r.id && revision.applicationUuid === r.creation.intended.uuid);
  const proof = { proof: 'New published script definition and exact immutable revision intentionally retained as owner fixture facts. All author writes and original publication acknowledged and independently confirmed; no deletion or runtime installation claim.', retainedDefinitionId: r.id, retainedRevisionId: revision.id };
  r.retentionProof = proof; r.phase = 'deleted'; h.persist(); h.observe?.({ kind: 'retained-published-script-fixture', ...proof });
  return proof;
}
async function publish(h, app) {
  const r = h.state.resources.find(v => v.kind === 'definition' && v.id === app.id), current = (await h.ok(h.admin, 'GET', definitions + app.id)).value;
  if (!r?.creation?.ownershipConfirmed || r.scriptPublication) throw new h.Blocked('Publication requires exact new owned script definition without a prior intent');
  const route = definitions + app.id + '/revisions/', preview = (await h.ok(h.admin, 'POST', route + 'preview', { expectedDefinitionVersion: current.updateTime })).value;
  h.check('Formal script revision preflight confirms exact definition and compatible current source', preview.definitionVersion === current.updateTime && preview.compatible === true && /^sha256:[a-f0-9]{64}$/.test(preview.digest));
  const p = { route, body: { expectedDefinitionVersion: current.updateTime, expectedPreviewDigest: preview.digest, changeLog: 'Script library reuse regression fixture' }, outcome: 'unknown' };
  r.scriptPublication = p; h.persist(); p.response = await h.api(h.admin, 'POST', route, p.body); h.persist();
  h.check('Original script publication acknowledges exact source definition and preflight digest', h.good(p.response) && p.response.data.value?.applicationDefinitionId === app.id && p.response.data.value.digest === preview.digest);
  p.revision = (await h.ok(h.admin, 'GET', route + p.response.data.value.id)).value; h.persist();
  h.check('Independent immutable revision exactly confirms original script publication receipt', same(p.revision, p.response.data.value));
  p.outcome = 'confirmed'; h.persist(); return p.revision;
}
async function libraryReuse(h) {
  // Publication creates permanent facts only in the explicitly owned isolated daemon.
  await require('./delivery_cases.cjs').fixture(h);
  const app = await a.definition(h, 'libraryreuse'), first = await a.library(h, app), edited = structuredClone(first);
  const spec = JSON.parse(decode(edited.files['display/definition.json'])); spec.name = '已编辑程序'; spec.description = '保存后复用';
  const source = decode(edited.files['display/main.go']).replace('input["label"]', '"edited:"+input["label"].(string)');
  edited.files['display/definition.json'] = b64(JSON.stringify(spec)); edited.files['display/main.go'] = b64(source);
  await saveLibrary(h, app, edited);
  const copy = structuredClone(edited), copied = structuredClone(spec); copied.key = 'displaycopy'; copied.name = '独立程序副本'; copied.sourceFiles = ['displaycopy/main.go']; copied.entrypoint.file = 'displaycopy/main.go';
  copy.definitions.push({ key: copied.key, definition: 'displaycopy/definition.json' });
  copy.files['displaycopy/definition.json'] = b64(JSON.stringify(copied)); copy.files['displaycopy/main.go'] = b64(source);
  await saveLibrary(h, app, copy);
  const entity = a.newEntity(h, app); entity.blockInfo = [await a.scriptBinding(h)];
  const second = a.newEntity(h, app); second.name = 'samplecopy'; second.showName = '复制程序绑定'; second.blockInfo = [await a.scriptBinding(h)];
  second.blockInfo[0].key = 'copied-binding'; second.blockInfo[0].scriptKey = 'displaycopy';
  // Defining a script while binding uses the same authoritative file library;
  // it does not introduce an embedded-source format alongside library keys.
  const direct = structuredClone(copy), directSpec = structuredClone(copied); directSpec.key = 'displaydirect'; directSpec.name = '绑定时直接定义';
  directSpec.sourceFiles = ['displaydirect/main.go']; directSpec.entrypoint.file = 'displaydirect/main.go';
  direct.definitions.push({ key: directSpec.key, definition: 'displaydirect/definition.json' });
  direct.files['displaydirect/definition.json'] = b64(JSON.stringify(directSpec)); direct.files['displaydirect/main.go'] = b64(source);
  await saveLibrary(h, app, direct);
  const third = a.newEntity(h, app); third.name = 'sampledirect'; third.showName = '直接定义程序绑定'; third.blockInfo = [await a.scriptBinding(h)];
  third.blockInfo[0].key = 'direct-binding'; third.blockInfo[0].scriptKey = 'displaydirect';
  await a.save(h, app, await a.draft(h, app), [entity, second, third]);
  const model = await a.draft(h, app);
  h.check('Independent reentry preserves selected original, copied and directly defined script bindings including required zero/false and output mapping', model.entities.length === 3 &&
    model.entities.every(e => { const fn = e.blockInfo?.[0]?.stageInfo?.functions?.insert; return fn?.input?.count === 0 && fn.input.enabled === false && fn.input.label === '$referenceValue.name' && fn.bindField === 'description' && fn.resultField === 'result'; }) &&
    model.entities.find(e => e.name === second.name)?.blockInfo[0].scriptKey === 'displaycopy' && model.entities.find(e => e.name === third.name)?.blockInfo[0].scriptKey === 'displaydirect');
  const debug = (await h.ok(h.admin, 'POST', '/panel/application/definition/entity/scripts/debug', { scriptContent: source, functionName: 'block.Handle', inputs: spec.inputs, outputs: spec.outputs,
    input: { count: 0, enabled: false, label: 'probe' }, timeout: 1000, mode: 'example' })).value;
  h.check('Real author debugger accepts the saved declared required zero/false and precise output contract', debug.valid === true && same(debug.output, { result: 'edited:probe' }));
  const frozen = await publish(h, app);
  h.check('Published revision freezes every original/copied/direct program file, parameter declaration and exact library index identity', frozenLibraryMatches(frozen, app, direct));
  const changed = structuredClone(direct); changed.files['display/main.go'] = b64(source.replace('edited:', 'unpublished:'));
  await saveLibrary(h, app, changed);
  const now = (await h.ok(h.admin, 'GET', definitions + app.id + '/revisions/' + frozen.id)).value;
  h.check('Changing original author source leaves copied source and every frozen program/binding exactly unchanged', same(now, frozen) &&
    (await h.ok(h.admin, 'GET', definitions + app.id + '/function-blocks')).value.content.files['displaycopy/main.go'] === copy.files['displaycopy/main.go']);
  const r = h.state.resources.find(v => v.kind === 'definition' && v.id === app.id); await retained(h, r);
}
libraryReuse.transport = 'owner-api';
module.exports = { handlers: { 'F016-001': libraryReuse }, saveLibrary, publish, guard, retained, frozenLibraryMatches };
