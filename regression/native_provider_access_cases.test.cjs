const { test } = require('node:test');
const assert = require('node:assert/strict');
const { policyDenied, providerPreview, cleanup, reconcileBuild } = require('./native_provider_access_cases.cjs');
test('acknowledged build recovery confirms original receipt and provenance without replay; ambiguous identities stay open', async () => {
  const f = fixture(), digest = 'sha256:' + 'a'.repeat(64);
  const p = { id: 7, applicationUuid: 'original-app', applicationName: 'magicBase', releaseVersion: '1.0.0', packageDigest: digest,
    uploadedBy: { namespace: 'panel', accountId: 9 } };
  Object.assign(f.r, { applicationUuid: 'original-app', package: p, preexistingIds: [], commands: [{ method: 'POST', route: '/panel/application/deployment-packages/builds/',
    body: { builtinKind: 'magicBase', applicationUuid: 'original-app', releaseVersion: '1.0.0', expectedBuildDigest: digest }, actorIdentity: structuredClone(f.r.actorIdentity),
    origin: f.r.origin, outcome: 'unknown', response: { status: 200, data: { error: null, value: structuredClone(p) } } }] });
  f.h.ok = async (_actor, _method, route) => ({ value: route === '/api/v1/web/session/' ? { account: { id: 9, account: 'original' }, homeNamespace: 'panel' } : p });
  for (const mutate of [x => x.preexistingIds.push(7), x => x.commands[0].body.expectedBuildDigest = 'other', x => x.commands[0].response.data.value.id = 8,
    x => x.commands[0].actorIdentity.account = 'other']) {
    const r = structuredClone(f.r); mutate(r); await assert.rejects(reconcileBuild(f.h, r)); assert.equal(r.commands[0].outcome, 'unknown');
  }
  await reconcileBuild(f.h, f.r); assert.equal(f.r.commands[0].outcome, 'confirmed'); assert.equal(f.r.packageAcknowledged, true); assert.equal(f.writes(), 0);
});
test('provider preview requires matching component image metadata, application identity and initial native contract', () => {
  for (const [kind, provider] of [['magicBase', 'modelExecution'], ['magicGateway', 'modelGateway']]) {
    const imageConfig = { platform: { application: kind, runtimeProviderKind: provider } }, digest = 'sha256:' + 'a'.repeat(64);
    const p = { applicationUuid: 'exact', applicationName: kind, applicationType: 'internal', nativeContractVersion: 'magic.native-orchestration/v1',
      buildDigest: digest, imageConfig, imageDigest: digest, components: [{ imageConfig: structuredClone(imageConfig), imageDigest: digest }] };
    assert.ok(providerPreview(p, kind, 'exact'));
    for (const mutate of [x => x.applicationUuid = 'other', x => x.components[0].imageConfig.platform.runtimeProviderKind = 'other',
      x => x.imageConfig.platform.application = 'other', x => x.nativeContractVersion = 'other', x => x.buildDigest = 'invalid',
      x => x.components.push(x.components[0]), x => x.imageDigest = 'other']) {
      const changed = structuredClone(p); mutate(changed); assert.equal(providerPreview(changed, kind, 'exact'), false);
    }
  }
});
test('provider authorization proof requires the exact owner policy, never a login failure or arbitrary forbidden response', () => {
  const message = '运行提供方包要求系统运维或部署治理权限';
  assert.ok(policyDenied({ status: 403, data: { error: { code: 5, message }, value: null } }, message));
  assert.ok(policyDenied({ status: 401, data: { error: { code: 5, message }, value: null } }, message));
  for (const response of [{ status: 401, data: { error: { code: 11, message: 'login required' }, value: null } },
    { status: 403, data: { error: { code: 5, message: 'not authorized' }, value: null } },
    { status: 403, data: { error: { code: 11, message }, value: null } },
    { status: 403, data: { error: { code: 5, message }, value: { id: 1 } } }]) assert.equal(policyDenied(response, message), false);
});
function fixture() {
  let reads = 0, writes = 0;
  const h = { admin: { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.test' },
    Blocked: Error, persist() {}, good: r => r.status === 200 && !r.data.error, check(label, condition) { assert.ok(condition, label); },
    async ok() { reads++; return { value: {} }; }, async api() { writes++; return {}; } };
  const r = { phase: 'created', commands: [], actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin };
  return { h, r, reads: () => reads, writes: () => writes };
}
test('native provider cleanup never guesses a package or repeats unresolved original commands', async () => {
  for (const mutate of [f => f.r.commands.push({ outcome: 'unknown' }), f => f.r.scenarioCommands = [{ outcome: 'unknown' }], f => f.h.admin.identity.account = 'other',
    f => f.r.package = { id: 7 }, f => { f.r.package = { id: 7, applicationUuid: 'shared' }; f.r.packageAcknowledged = true; f.r.preexistingIds = [7]; }]) {
    const f = fixture(); mutate(f); await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.writes(), 0); assert.equal(f.reads(), 0); assert.equal(f.r.phase, 'created');
  }
});
test('completed policy-only probes have no invented package deletion', async () => {
  const f = fixture(); f.r.commands = [{ outcome: 'rejected-and-unchanged' }]; await cleanup(f.h, f.r);
  assert.equal(f.r.phase, 'deleted'); assert.equal(f.reads(), 0); assert.equal(f.writes(), 0);
});
test('original exact HTTP401 policy refusal from nonmutating preview has a read-only disposition, while an arbitrary401 cannot', async () => {
  const f = fixture(); f.r.applicationUuid = 'original-app';
  f.r.commands = [{ method: 'POST', route: '/panel/application/deployment-packages/builds/preview', body: { builtinKind: 'magicBase', applicationUuid: 'original-app' },
    actorIdentity: { namespace: 'panel', account: 'limited' }, origin: f.r.origin, outcome: 'unknown', response: { status: 401, data: { error: { code: 5, message: '运行提供方包要求系统运维或部署治理权限' }, value: null } } }];
  f.h.state = { resources: [{ kind: 'account', id: 9, phase: 'created', collection: '/cas/namespaces/panel/accounts/', creation: { ownershipConfirmed: true, intended: { account: 'limited' } } }] };
  const account = { id: 9, account: 'limited', status: 2, effectiveRoles: [{ module: '/modules/kernel/runner', key: 'management-application-publisher' }] };
  f.h.ok = async () => ({ value: account }); f.h.directory = async () => [];
  f.r.commands[0].response.data.error.code = 11;
  await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.r.commands[0].outcome, 'unknown');
  f.r.commands[0].response.data.error.code = 5; account.effectiveRoles.push({ key: 'operations-runtime-manager' });
  await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.r.commands[0].outcome, 'unknown');
  account.effectiveRoles.pop(); await cleanup(f.h, f.r);
  assert.equal(f.r.phase, 'deleted'); assert.equal(f.writes(), 0); assert.equal(f.r.commands[0].disposition.originalOutcome, 'unknown');
});
