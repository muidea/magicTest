const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { verifyIconArchive, uploadedImageMatches, acknowledgedImageSaveMatches, reconcileImageUpload } = require('./installed_icon_cases.cjs');
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=';
test('image UI comparison permits only DTO omission of the exact empty optional storage constraint', () => {
  const before = { id: 7, uuid: 'original', name: 'original', updateTime: 10, storage: { required: true, engine: 'postgresql', slots: [] } };
  const payload = { ...require('./definition_metadata_cases.cjs').command(before, { icon: image }), storage: { ...before.storage, versionConstraint: '' } };
  const ack = { ...before, icon: image, updateTime: 11 };
  assert.equal(uploadedImageMatches(before, payload, ack, ack), true);
  for (const mutate of [p => p.storage.versionConstraint = '>=17', p => p.storage.engine = 'mysql', p => p.expectedDefinitionVersion++, p => p.uuid = 'foreign', p => p.icon = 'other', p => p.unknown = 'unexpected']) {
    const changed = structuredClone(payload); mutate(changed); assert.equal(uploadedImageMatches(before, changed, ack, ack), false);
  }
  assert.equal(uploadedImageMatches(before, payload, ack, { ...ack, updateTime: 12 }), false);
  assert.equal(uploadedImageMatches(before, payload, { ...ack, storage: { ...ack.storage, slots: [{ foreign: true }] } }, ack), false);
});
test('original accepted image recovery requires exact original actor, acknowledged command and complete unchanged current owner', async () => {
  for (const mode of ['good', 'no-image', 'unknown-response', 'foreign-actor', 'wrong-current', 'published', 'changed-input']) {
    const actor = { identity: { account: 'author', namespace: 'panel' }, origin: 'https://panel.test' };
    const before = { id: 7, uuid: 'original', name: 'original', updateTime: 10, storage: { required: true, slots: [] } }, ack = { ...before, icon: image, updateTime: 11 };
    const r = { kind: 'definition', id: 7, collection: '/panel/application/definitions/', phase: 'created', creation: { ownershipConfirmed: true, actorIdentity: structuredClone(actor.identity), origin: actor.origin, response: { data: { value: before } } }, metadataJournal: { original: before, last: before },
      pendingAuthoringSave: { confirmed: false, method: 'PUT', route: '/panel/application/definitions/7', journalId: 'a'.repeat(32), payload: require('./definition_metadata_cases.cjs').command(before, { icon: image }), response: { status: 200, data: { value: ack } } } };
    if (mode === 'no-image') { before.icon = ''; ack.icon = ''; r.pendingAuthoringSave.payload.icon = ''; }
    if (mode === 'unknown-response') delete r.pendingAuthoringSave.response;
    if (mode === 'foreign-actor') actor.identity.account = 'other';
    if (mode === 'published') r.modelDelivery = {};
    if (mode === 'changed-input') r.pendingAuthoringSave.payload.storage.slots = [{ foreign: true }];
    let reads = 0;
    const h = { admin: actor, Blocked: Error, persist() {}, good: x => x?.status === 200 && !x.data.error, check(label, value) { assert.ok(value, label); }, async ok(who, method, route) { reads++; assert.equal(who, actor); assert.equal(method, 'GET'); assert.equal(route, r.pendingAuthoringSave.route); return { value: mode === 'wrong-current' ? { ...ack, updateTime: 12 } : ack }; } };
    if (['good', 'no-image'].includes(mode)) { const proof = await reconcileImageUpload(h, r); assert.equal(proof.noCommandReplayed, true); assert.equal(proof.originalSubmittedImagePersisted, mode === 'good'); assert.equal(r.pendingAuthoringSave.confirmed, true); assert.deepEqual(r.metadataJournal.last, ack); }
    else { await assert.rejects(reconcileImageUpload(h, r)); assert.equal(r.pendingAuthoringSave.confirmed, false); }
    if (!['good', 'no-image', 'wrong-current'].includes(mode)) assert.equal(reads, 0);
  }
});
test('installed icon archive proof binds exact application, PNG bytes, manifest and independent checksum entry', () => {
  const bytes = Buffer.from('original-test-bytes'), app = { uuid: 'original', name: 'original-key' };
  const digest = 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
  const archive = { crcValid: true, names: ['package.json', 'checksums.json', 'assets/icon.png'], manifest: { apiVersion: 'magic.model-package/v1', kind: 'ApplicationModelPackage', application: { uuid: app.uuid, key: app.name }, icon: { path: 'assets/icon.png', mediaType: 'image/png', digest } }, payload: bytes.toString('base64'), checksums: { files: [{ path: 'assets/icon.png', size: bytes.length, digest }] } };
  verifyIconArchive(archive, app, bytes);
  for (const change of [a => a.crcValid = false, a => a.names.push('assets/icon.png'), a => a.manifest.application.uuid = 'foreign', a => a.manifest.icon.digest = 'wrong', a => a.payload = Buffer.from('wrong').toString('base64'), a => a.checksums.files[0].size++, a => a.checksums.files = []]) {
    const copy = structuredClone(archive); change(copy); assert.throws(() => verifyIconArchive(copy, app, bytes));
  }
});

test('original no-image save can be disposed without claiming uploaded image persisted', () => {
  const before = { id: 7, uuid: 'original', icon: '', updateTime: 10 }, payload = require('./definition_metadata_cases.cjs').command(before), ack = { ...before, updateTime: 11 };
  assert.equal(acknowledgedImageSaveMatches(before, payload, ack, ack), true);
  assert.equal(uploadedImageMatches(before, payload, ack, ack), false);
  assert.equal(acknowledgedImageSaveMatches(before, { ...payload, icon: 'arbitrary' }, { ...ack, icon: 'arbitrary' }, { ...ack, icon: 'arbitrary' }), false);
  assert.equal(acknowledgedImageSaveMatches(before, payload, ack, { ...ack, showName: 'foreign' }), false);
});
