const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { rejected, rejectSave, compact, sizedPNG, budgetContent } = require('./page_validation_cases.cjs');
const sha = b => 'sha256:' + crypto.createHash('sha256').update(b).digest('hex');
test('negative page writes retain unknown, unauthorized, accepted and changed-owner outcomes', async () => {
  for (const mode of ['refused', 'wrong-diagnostic', 'accepted', 'unauthenticated', 'conflict', 'changed', 'unknown']) {
    const app = { id: 7 }, before = { pages: { definitionVersion: 10, content: { pages: [] } }, members: { definitionVersion: 10, content: { files: {} } }, model: { definitionVersion: 10, entities: [] } };
    const r = { id: 7, collection: '/panel/application/definitions/', creation: { ownershipConfirmed: true } };
    let calls = 0, journaled = false;
    const response = mode === 'accepted' ? { status: 200, data: { error: null, value: {} } } : { status: mode === 'unauthenticated' ? 401 : 200, data: { error: { code: mode === 'unauthenticated' ? 11 : mode === 'conflict' ? 19 : 4, message: mode === 'wrong-diagnostic' ? 'other rejected field' : 'exact invalid page' }, value: null } };
    const h = { admin: {}, Blocked: Error, state: { resources: [r] },
      persist() { journaled = !!r.pendingAuthoringSave && !r.pendingAuthoringSave.confirmed; },
      check(label, condition) { assert.ok(condition, label); },
      async api(actor, method, path) { assert.equal(actor, h.admin); assert.equal(method, 'PUT'); assert.equal(path, '/panel/application/definitions/7/pages'); assert.equal(journaled, true); calls++; if (mode === 'unknown') throw Error('original result lost'); return response; },
      async ok(actor, method, path) { assert.equal(method, 'GET'); const member = path.endsWith('/pages') ? 'pages' : path.endsWith('/package-members') ? 'members' : 'model'; return { value: mode === 'changed' && member === 'pages' ? { ...before.pages, definitionVersion: 11 } : structuredClone(before[member]) }; } };
    const operation = rejectSave(h, app, 'pages', before, { pages: ['invalid'] }, /exact invalid page/, 'original refusal');
    if (mode === 'refused') await operation; else await assert.rejects(operation);
    assert.equal(calls, 1, 'never replay the original conditional mutation');
    assert.equal(r.pendingAuthoringSave.confirmed, ['refused', 'wrong-diagnostic'].includes(mode));
    assert.equal(r.pendingAuthoringSave.payload.expectedDefinitionVersion, 10);
  }
});
test('owner validation refusal requires the correct stage and empty success value', () => {
  assert.ok(rejected({ status: 400, data: { error: { code: 4 }, value: null } }));
  for (const code of [2, 5, 11, 12, 15, 19, 21, 22]) assert.ok(!rejected({ status: 200, data: { error: { code }, value: null } }));
  assert.ok(!rejected({ status: 503, data: { error: { code: 4 }, value: null } }));
  assert.ok(!rejected({ status: 200, data: { error: { code: 4 }, value: {} } }));
});
test('image evidence compaction preserves original identities and hashes both representations', () => {
  const bytes = Buffer.from('original byte content'), encoded = bytes.toString('base64');
  const value = { body: { id: 7, files: { 'assets/original.png': encoded } }, response: { status: 200, data: { error: { code: 4 }, value: null } } };
  const result = compact(value);
  assert.deepEqual(result.response, value.response); assert.equal(result.body.id, 7);
  assert.equal(result.body.files['assets/original.png'].digest, sha(bytes));
  assert.equal(result.body.files['assets/original.png'].encodedDigest, sha(Buffer.from(encoded)));
  assert.equal(result.body.files['assets/original.png'].bytes, bytes.length);
  assert.equal(value.body.files['assets/original.png'], encoded, 'never rewrite actual input bytes');
});
test('exact public budgets include original version, manifest digits and base64 expansion', () => {
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cP5sAAAAASUVORK5CYII=', 'base64');
  const original = { schemaVersion: 'magic.application-package-members/v1', files: {} };
  for (const version of [1, 1794102833913]) for (const bytes of [8191, 8192, 8193]) {
    const sample = budgetContent(original, png, version, bytes);
    assert.equal(Buffer.byteLength(JSON.stringify({ expectedDefinitionVersion: version, content: sample.content })), bytes);
    const asset = sample.content.assets.files[0]; assert.equal(asset.digest, sha(sample.payload)); assert.equal(asset.size, sample.payload.length);
    assert.deepEqual(Buffer.from(sample.content.files[asset.path], 'base64'), sample.payload);
    assert.deepEqual(sample.payload.subarray(0, png.length - 12), png.subarray(0, -12));
    assert.deepEqual(sample.payload.subarray(-12), png.subarray(-12));
    assert.equal(sample.payload.subarray(png.length - 8, png.length - 4).toString(), 'tEXt');
    assert.deepEqual(original, { schemaVersion: 'magic.application-package-members/v1', files: {} });
  }
  for (const size of [-1, NaN, Infinity, 8 * 1024 * 1024 + 2]) assert.throws(() => budgetContent(original, png, 1, size));
  assert.throws(() => sizedPNG(Buffer.from('not PNG'), 100));
});
