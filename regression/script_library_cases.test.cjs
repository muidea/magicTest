const { test } = require('node:test');
const assert = require('node:assert/strict');
const { guard, retained, frozenLibraryMatches } = require('./script_library_cases.cjs');
const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
function fixture() {
  const identity = { account: 'original-author', namespace: 'panel' }, origin = 'https://panel.test', revision = { id: 11, applicationDefinitionId: 7, applicationUuid: 'exact-uuid', definitionVersion: 13, digest: 'original-digest' };
  const r = { kind: 'definition', id: 7, phase: 'created', creation: { ownershipConfirmed: true, origin, actorIdentity: structuredClone(identity), intended: { uuid: 'exact-uuid' } },
    scriptPublication: { outcome: 'confirmed', body: { expectedDefinitionVersion: 13, expectedPreviewDigest: 'original-digest' }, revision, response: { status: 200, data: { value: structuredClone(revision) } } },
    pendingAuthoringSave: { confirmed: true, payload: { content: { files: { 'original/main.go': 'original-bytes' } } } } };
  let reads = 0;
  const h = { admin: { identity, origin }, Blocked: Error, good: r => r?.status === 200 && !r.data?.error, check: (m, c) => assert.ok(c, m), persist() {},
    async ok(actor, method, route) { reads++; assert.equal(method, 'GET', 'retained fixtures never delete published facts'); assert.equal(route, '/panel/application/definitions/7/revisions/11'); return { value: structuredClone(revision) }; } };
  return { h, r, reads: () => reads };
}
test('exact published script fixture is retained only with matching original publication, source version, digest and independent owner revision', async () => {
  const { h, r, reads } = fixture(), proof = await retained(h, r);
  assert.equal(r.phase, 'deleted'); assert.equal(proof.retainedDefinitionId, 7); assert.equal(proof.retainedRevisionId, 11); assert.equal(reads(), 1);
  assert.match(proof.proof, /intentionally retained/);
});
test('unknown publication and author source write block cleanup without mutation, guessed deletion or publishing again', async () => {
  for (const mode of ['unknown', 'unconfirmed-save', 'wrong-author', 'wrong-origin', 'wrong-response', 'wrong-source-version', 'wrong-source-digest']) {
    const { h, r, reads } = fixture();
    if (mode === 'unknown') r.scriptPublication.outcome = 'unknown';
    if (mode === 'unconfirmed-save') r.pendingAuthoringSave.confirmed = false;
    if (mode === 'wrong-author') r.creation.actorIdentity.account = 'replacement';
    if (mode === 'wrong-origin') r.creation.origin = 'https://foreign.test';
    if (mode === 'wrong-response') r.scriptPublication.response.data.value.id = 12;
    if (mode === 'wrong-source-version') r.scriptPublication.body.expectedDefinitionVersion = 14;
    if (mode === 'wrong-source-digest') r.scriptPublication.body.expectedPreviewDigest = 'replacement';
    await assert.rejects(retained(h, r)); assert.equal(r.phase, 'created'); assert.equal(reads(), 0);
  }
  assert.throws(() => guard({ Blocked: Error }, { scriptPublication: { outcome: 'unknown' } }), /without DELETE/);
});
test('script fixture recovery binds full original publication and latest exact author-source write', () => {
  const { r } = fixture(), evidence = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, evidence)[0], r);
  for (const mutate of [x => x.scriptPublication.revision.id++, x => x.scriptPublication.body.expectedPreviewDigest = 'other', x => x.scriptPublication.outcome = 'unknown', x => x.pendingAuthoringSave.payload.content.files['original/main.go'] = 'replacement']) {
    const changed = structuredClone(r); mutate(changed); assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /differs/);
  }
});
test('frozen script assertion consumes current immutable file content and complete index identity rather than a top-level legacy projection', () => {
  const app = { name: 'app', uuid: 'exact' }, content = { schemaVersion: 'magic.application-function-blocks/v1', definitions: [{ key: 'one', definition: 'one/definition.json' }], files: { 'one/main.go': Buffer.from('original').toString('base64') } };
  const index = { schemaVersion: content.schemaVersion, applicationKey: app.name, applicationUuid: app.uuid, modelRevision: 1, definitions: content.definitions };
  const revision = { version: 1, content: { functionBlocks: { index, files: { ...content.files, 'index.json': Buffer.from(JSON.stringify(index)).toString('base64') } } } };
  assert.equal(frozenLibraryMatches(revision, app, content), true);
  for (const mutate of [x => x.content.functionBlocks.files['one/main.go'] = 'other', x => x.content.functionBlocks.index.applicationUuid = 'foreign', x => x.content.functionBlocks.index.modelRevision++, x => x.content.functionBlocks.files['unexpected.go'] = 'foreign', x => x.content.functionBlocks.index.definitions = []]) {
    const changed = structuredClone(revision); mutate(changed); assert.equal(frozenLibraryMatches(changed, app, content), false);
  }
  assert.equal(frozenLibraryMatches({ version: 1, application: { functionBlocks: [{ key: 'one' }] } }, app, content), false);
});
