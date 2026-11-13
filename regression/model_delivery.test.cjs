const test = require('node:test');
const assert = require('node:assert/strict');
const { command, retained, removePackage, packageRemovalMatches, importExact, publishNext, linkRequest } = require('./model_delivery.cjs');
function setup() {
  const actor = { identity: { namespace: 'panel', account: 'original' }, origin: 'https://panel.invalid' };
  const r = { kind: 'definition', id: 7, creation: { ownershipConfirmed: true, actorIdentity: structuredClone(actor.identity), origin: actor.origin, intended: { uuid: 'original-uuid' } }, modelDelivery: { commands: [], requests: [] } };
  const h = { admin: actor, state: { resources: [r] }, Blocked: Error, persist() {}, observe() {},
    good: r => r.status === 200 && !r.data.error, check(label, condition) { assert.ok(condition, label); } };
  return { h, r };
}
test('immutable model fixture commands preserve unknown original intents and refuse write replay', async () => {
  for (const mode of ['good', 'response-loss', 'read-loss', 'wrong-identity']) {
    const { h, r } = setup(); let sends = 0;
    h.api = async () => { sends++; assert.equal(r.modelDelivery.commands.at(-1).outcome, 'unknown'); if (mode === 'response-loss') throw Error('response lost'); return { status: 200, data: { value: { id: 9, uuid: 'original-uuid' } } }; };
    const execute = () => command(h, r, '/publish/', { expectedDefinitionVersion: 5 }, async v => { if (mode === 'read-loss') throw Error('owner read lost'); return mode === 'wrong-identity' ? { ...v, id: 10 } : structuredClone(v); }, v => v.uuid === 'original-uuid');
    if (mode === 'good') { await execute(); assert.equal(r.modelDelivery.commands[0].outcome, 'confirmed'); }
    else { await assert.rejects(execute()); assert.equal(r.modelDelivery.commands[0].outcome, 'unknown'); await assert.rejects(execute(), /unresolved/); }
    assert.equal(sends, 1);
  }
});
function lineageFixture() {
  const { h, r } = setup();
  const revision = { id: 9, version: 1, applicationDefinitionId: r.id, applicationUuid: 'original-uuid', definitionVersion: 5, digest: 'sha256:' + 'a'.repeat(64) };
  const pkg = { id: 10, applicationUuid: revision.applicationUuid, applicationKey: 'app', sourceRevisionId: 9, artifactDigest: 'sha256:' + 'b'.repeat(64), status: 'valid' };
  const next = { ...revision, id: 11, version: 2, definitionVersion: 6, digest: 'sha256:' + 'c'.repeat(64) };
  const nextPackage = { ...pkg, id: 12, sourceRevisionId: next.id, artifactDigest: 'sha256:' + 'd'.repeat(64) };
  const makeCommands = (rev, p) => [
    { outcome: 'confirmed', route: '/panel/application/definitions/7/revisions/', body: { expectedDefinitionVersion: rev.definitionVersion, expectedPreviewDigest: rev.digest }, value: rev, response: { status: 200, data: { value: rev } } },
    { outcome: 'confirmed', route: '/panel/application/definitions/7/revisions/' + rev.id + '/model-packages', value: p, response: { status: 200, data: { value: p } } },
  ];
  Object.assign(r.modelDelivery, { revision, package: pkg, commands: makeCommands(revision, pkg) });
  const f = { application: { uuid: 'original-uuid', name: 'app' }, resource: r, revision, package: pkg };
  h.ok = async (_actor, _method, route) => ({ value: structuredClone(route === '/panel/application/definitions/7' ? { uuid: 'original-uuid', updateTime: 6 } :
    route.endsWith('/preview') ? { compatible: true, definitionVersion: 6, nextVersion: 2, digest: next.digest } :
    route.endsWith('/9') ? revision : route.endsWith('/10') ? pkg : route.endsWith('/11') ? next : nextPackage) });
  h.api = async (_actor, _method, route) => ({ status: 200, data: { value: structuredClone(route.endsWith('/model-packages') ? nextPackage : next) } });
  return { h, r, f, revision, pkg, next, nextPackage, makeCommands };
}
test('later publication keeps original immutable receipts and links requests to exact revision lineage', async () => {
  const { h, r, f } = lineageFixture(), original = structuredClone(r.modelDelivery);
  const next = await publishNext(h, f);
  assert.deepEqual(r.modelDelivery.commands, original.commands); assert.deepEqual(r.modelDelivery.revision, original.revision);
  assert.equal(next.delivery, r.modelDelivery.successors[0]); assert.equal(next.revision.version, 2);
  const request = { kind: 'deployment-review-request', id: 21, phase: 'created', creation: { ownershipConfirmed: true, intended: { packageId: next.package.id } } };
  h.state.resources.push(request); linkRequest(h, next, request);
  assert.deepEqual(r.modelDelivery.requests, []); assert.deepEqual(next.delivery.requests, [21]);
  await assert.rejects(retained(h, r), /undisposed|lifecycle/); assert.notEqual(r.phase, 'deleted');
  request.phase = 'deleted'; const proof = await retained(h, r);
  assert.equal(proof.retainedRevisionId, 9); assert.equal(proof.successors[0].retainedRevisionId, 11);
});
test('later publish/build response loss and actor drift retain exact unknown lineage without any replacement publish', async () => {
  for (const mode of ['publish-loss', 'build-loss', 'actor-drift']) {
    const { h, r, f } = lineageFixture(), api = h.api; let sends = 0;
    h.api = async (...args) => { sends++; assert.equal(r.modelDelivery.successors[0].commands.at(-1).outcome, 'unknown');
      if (mode === 'publish-loss' || mode === 'build-loss' && sends === 2) throw Error('original response lost');
      const result = await api(...args); if (mode === 'actor-drift') h.admin.identity.account = 'foreign'; return result; };
    await assert.rejects(publishNext(h, f)); const count = sends;
    await assert.rejects(publishNext(h, f), /unresolved/); await assert.rejects(retained(h, r), /unresolved/);
    await assert.rejects(removePackage(h, f), /unresolved/); assert.equal(sends, count);
    assert.equal(r.modelDelivery.revision.id, 9); assert.notEqual(r.phase, 'deleted');
  }
});
test('retention rejects broken successor lineage and changed original facts without declaring parent disposed', async () => {
  for (const mode of ['wrong-predecessor', 'wrong-package', 'unknown-successor']) {
    const { h, r, f } = lineageFixture(), next = await publishNext(h, f);
    if (mode === 'wrong-predecessor') next.delivery.predecessorRevisionId = 99;
    if (mode === 'wrong-package') next.delivery.package.applicationUuid = 'foreign';
    if (mode === 'unknown-successor') next.delivery.commands[1].outcome = 'unknown';
    await assert.rejects(retained(h, r)); assert.notEqual(r.phase, 'deleted');
  }
});
test('positive model ZIP import binds upload and complete immutable owner facts; unknown results fence every repeat', async () => {
  for (const mode of ['good', 'upload-loss', 'purpose', 'digest', 'import-loss', 'owner-drift', 'directory-drift', 'foreign-actor', 'actor-drift']) {
    const { h, r } = setup(), bytes = Buffer.from('complete original fixture bytes'); h.state.prefix = 'rg';
    const pkg = { id: 10, applicationUuid: 'original-uuid', status: 'valid' }; r.modelDelivery.package = pkg;
    const f = { resource: r, package: pkg }; let uploads = 0, writes = 0, reads = 0;
    h.directory = async () => ++reads === 2 && mode === 'directory-drift' ? [pkg, { id: 11 }] : [structuredClone(pkg)];
    h.ok = async () => ({ value: mode === 'owner-drift' ? { ...pkg, applicationUuid: 'foreign' } : structuredClone(pkg) });
    h.api = async () => { writes++; if (mode === 'import-loss') throw Error('original import response lost'); return { status: 200, data: { value: structuredClone(pkg) } }; };
    const transfer = async (actor, input) => {
      uploads++; assert.equal(actor, h.admin); assert.equal(input.bytes, bytes); assert.equal(r.modelDelivery.imports[0].outcome, 'unknown');
      if (mode === 'upload-loss') throw Error('original upload response lost');
      if (mode === 'actor-drift') actor.identity.account = 'foreign';
      return { status: 200, data: { value: { name: input.name, size: bytes.length, digest: mode === 'digest' ? 'wrong' : 'sha256:' + require('node:crypto').createHash('sha256').update(bytes).digest('hex'), purpose: mode === 'purpose' ? 'other' : 'application-model-package', uploadRef: 'a'.repeat(43), expiresAt: Date.now() + 60000 } } };
    };
    const download = async () => ({ status: 200, data: { bytes } });
    if (mode === 'foreign-actor') h.admin.identity.account = 'foreign';
    const run = () => importExact(h, f, bytes, transfer, download);
    if (mode === 'good') { await run(); assert.equal(r.modelDelivery.imports[0].outcome, 'confirmed'); }
    else {
      await assert.rejects(run()); await assert.rejects(run(), /unresolved/);
      await assert.rejects(removePackage(h, f), /unresolved/); await assert.rejects(retained(h, r), /unresolved/);
    }
    assert.equal(uploads, mode === 'foreign-actor' ? 0 : 1);
    assert.equal(writes, ['foreign-actor', 'actor-drift', 'upload-loss', 'purpose', 'digest'].includes(mode) ? 0 : 1);
  }
});
test('model source removal journals one allowed exact DELETE and never repeats after response loss', async () => {
  for (const lost of [false, true]) {
    const { h, r } = setup(), pkg = { id: 10, applicationUuid: 'original-uuid', packageDigest: 'transport-source', artifactDigest: 'frozen-artifact' };
    r.modelDelivery.package = pkg; let sends = 0;
    h.ok = async (_, method, route) => ({ value: route.endsWith('/cleanup-preview') ? { packageId: 10, sourceDigest: pkg.packageDigest, allowed: true } : structuredClone(pkg) });
    h.directory = async () => [];
    h.api = async (_, method) => {
      if (method === 'GET') return { status: 200, data: { error: { code: 2 }, value: null } };
      assert.equal(method, 'DELETE'); sends++; assert.equal(r.modelDelivery.packageDisposition.outcome, 'unknown');
      if (lost) throw Error('response lost'); return { status: 200, data: {} };
    };
    const f = { resource: r, package: pkg };
    if (lost) { await assert.rejects(removePackage(h, f), /response lost/); await assert.rejects(removePackage(h, f), /unresolved/); }
    else {
      await removePackage(h, f); assert.equal(packageRemovalMatches(h, r), true);
      for (const change of [v => v.modelDelivery.packageDisposition.preview.sourceDigest = 'artifact-instead-of-package',
        v => v.modelDelivery.packageDisposition.actorIdentity.account = 'foreign', v => v.modelDelivery.packageDisposition.origin = 'https://foreign.invalid',
        v => v.modelDelivery.packageDisposition.route += 'other', v => v.modelDelivery.packageDisposition.before.id++,
        v => v.modelDelivery.packageDisposition.directoryAbsent = false, v => v.modelDelivery.packageDisposition.absence.data.error.code = 5]) {
        const altered = structuredClone(r); change(altered); assert.equal(packageRemovalMatches(h, altered), false);
      }
      await assert.rejects(removePackage(h, f), /already dispatched/);
    }
    assert.equal(sends, 1);
  }
});
test('cleanup original-evidence binding preserves complete model package disposal identity', () => {
  const { bindOriginalCleanup } = require('./cleanup_recovery.cjs');
  const { r } = setup(); r.phase = 'created'; r.collection = '/panel/application/definitions/';
  r.modelDelivery.packageDisposition = { method: 'DELETE', route: '/panel/application/model-packages/10', outcome: 'unknown' };
  const evidence = { resources: [{ ...structuredClone(r), confirmed: false }], trace: [] };
  assert.equal(bindOriginalCleanup({ resources: [r] }, evidence)[0], r);
  const changed = structuredClone(r); changed.modelDelivery.packageDisposition.route = '/panel/application/model-packages/11';
  assert.throws(() => bindOriginalCleanup({ resources: [changed] }, evidence), /differs/);
});
test('retained publication requires exact immutable owner reads and formal disposition of every related delivery', async () => {
  for (const mode of ['good', 'removed-package', 'removed-package-reappeared', 'removed-package-unproven', 'pending-save', 'unlinked-request', 'linked-request', 'changed-package', 'wrong-actor', 'borrowed-revision', 'wrong-build-route']) {
    const { h, r } = setup();
    r.modelDelivery.revision = { id: 9, applicationDefinitionId: 7, applicationUuid: 'original-uuid', definitionVersion: 5, digest: 'original-digest' };
    r.modelDelivery.package = { id: 10, applicationUuid: 'original-uuid', sourceRevisionId: 9, packageDigest: 'original-package-source' };
    r.modelDelivery.commands = [
      { outcome: 'confirmed', route: '/panel/application/definitions/7/revisions/', body: { expectedDefinitionVersion: 5, expectedPreviewDigest: 'original-digest' }, value: structuredClone(r.modelDelivery.revision), response: { status: 200, data: { value: structuredClone(r.modelDelivery.revision) } } },
      { outcome: 'confirmed', route: '/panel/application/definitions/7/revisions/9/model-packages', value: structuredClone(r.modelDelivery.package), response: { status: 200, data: { value: structuredClone(r.modelDelivery.package) } } },
    ];
    h.ok = async (_, method, route) => { assert.equal(method, 'GET'); return { value: route.includes('/revisions/') ? r.modelDelivery.revision : { ...r.modelDelivery.package, ...(mode === 'changed-package' ? { id: 11 } : {}) } }; };
    if (mode.startsWith('removed-package')) {
      r.modelDelivery.packageDisposition = { outcome: 'confirmed', method: 'DELETE', route: '/panel/application/model-packages/10',
        origin: r.creation.origin, actorIdentity: structuredClone(r.creation.actorIdentity), before: structuredClone(r.modelDelivery.package),
        preview: { allowed: true, packageId: 10, sourceDigest: r.modelDelivery.package.packageDigest },
        response: { status: 200, data: {} }, absence: { status: 200, data: { error: { code: 2 }, value: null } },
        directoryAbsent: mode !== 'removed-package-unproven' };
      h.api = async (_, method, route) => { assert.equal(method, 'GET'); assert.equal(route, '/panel/application/model-packages/10');
        return mode === 'removed-package-reappeared' ? { status: 200, data: { value: structuredClone(r.modelDelivery.package) } } : structuredClone(r.modelDelivery.packageDisposition.absence); };
    }
    if (mode === 'pending-save') r.pendingAuthoringSave = { confirmed: false };
    if (mode.endsWith('request')) {
      h.state.resources.push({ kind: 'deployment-review-request', id: 20, phase: 'created', creation: { intended: { packageId: 10 } } });
      if (mode === 'linked-request') r.modelDelivery.requests.push(20);
    }
    if (mode === 'wrong-actor') h.admin.identity.account = 'other';
    if (mode === 'borrowed-revision') r.modelDelivery.commands[0].response.data.value.applicationUuid = 'other';
    if (mode === 'wrong-build-route') r.modelDelivery.commands[1].route = '/panel/application/definitions/8/revisions/9/model-packages';
    if (mode === 'good') { const proof = await retained(h, r); assert.equal(proof.retainedPackageId, 10); assert.equal(r.phase, 'deleted'); }
    else if (mode === 'removed-package') { const proof = await retained(h, r); assert.equal(proof.formallyRemovedPackageId, 10); assert.equal(proof.retainedPackageId, undefined); assert.equal(r.phase, 'deleted'); }
    else { await assert.rejects(retained(h, r)); assert.notEqual(r.phase, 'deleted'); }
  }
});
