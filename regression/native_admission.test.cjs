const { test } = require('node:test');
const assert = require('node:assert/strict');
const { probe, cleanup, targetRejection, guardDefinitionCleanup } = require('./native_admission.cjs');
const payload = { applicationUuid: 'original-app', expectedBuildDigest: 'sha256:control', contract: { components: { api: { dependsOn: [{ componentRef: 'missing', condition: 'started' }] } } } };
function fixture(mode) {
  const actor = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.test' };
  let persisted, rows = [], calls = [];
  const h = { admin: actor, Blocked: Error, state: { resources: [] },
    persist() { if (mode === 'persist-failed') throw Error('persist failed'); persisted = structuredClone(this.state.resources); },
    check(label, condition) { assert.ok(condition, label); }, good: r => r.status === 200 && !r.data.error,
    async api(actual, method, route, body) {
      assert.equal(actual, actor); calls.push({ method, route });
      if (method === 'POST') {
        const r = persisted.at(-1);
        assert.equal(r.outcome, 'unknown'); assert.deepEqual(r.intended, body); assert.ok(r.before);
        if (mode === 'lost') throw Error('response lost');
        if (mode === 'accepted') { rows = [{ id: 17, name: 'unexpected' }]; return { status: 200, data: { value: rows[0] } }; }
        if (mode === 'auth-denied') return { status: 403, data: { error: { code: 5, message: 'components.api.dependsOn: 组件依赖引用无效' } } };
        if (mode === 'wrong-stage') return { status: 400, data: { error: { code: 4, message: '生成前必须完成应用包预检确认' } } };
        if (mode === 'directory-changed') rows = [{ id: 21, name: 'other-owner-write' }];
        return { status: 400, data: { value: null, error: { code: 4, message: mode === 'revision' ? '组件 api 镜像解析失败: deployment image is not prepared in the local docker daemon' : 'components.api.dependsOn: 组件依赖引用无效' } } };
      }
      assert.equal(method, 'GET', 'cleanup never guesses a DELETE or replays POST');
      if (route === '/panel/application/definitions/7') return { status: 200, data: { value: { id: 7, name: 'exact-invalid-image-draft' } } };
      return { status: 200, data: { values: structuredClone(rows), pagination: { total: mode === 'incomplete' ? 2 : rows.length, pageNum: 1, pageSize: 100, hasMore: false } } };
    },
    async ok(...args) { const r = await this.api(...args); assert.ok(this.good(r)); return r.data; }
  };
  return { h, actor, calls, saved: () => persisted };
}
test('native actual build journals original intent before one POST and closes only exact component-stage rejection with complete unchanged owner state', async () => {
  const f = fixture(), r = await probe(f.h, { intended: payload, variant: 'missing-dependency' });
  assert.equal(r.phase, 'deleted'); assert.equal(r.outcome, 'rejected-before-registration');
  assert.equal(f.calls.filter(c => c.method === 'POST').length, 1);
  assert.match((await cleanup(f.h, r)).proof, /independently unchanged/);
  await assert.rejects(probe(f.h, { intended: payload, variant: 'missing-dependency' }), /no POST replay/);
});
for (const mode of ['lost', 'accepted', 'auth-denied', 'wrong-stage', 'directory-changed']) test('native ' + mode + ' retains original identity without guessed cleanup/replay', async () => {
  const f = fixture(mode);
  await assert.rejects(probe(f.h, { intended: payload, variant: 'missing-dependency' }));
  const r = f.h.state.resources[0]; assert.notEqual(r.phase, 'deleted');
  if (mode === 'accepted') assert.equal(f.saved()[0].returnedId, 17);
  await assert.rejects(cleanup(f.h, r));
  await assert.rejects(probe(f.h, { intended: payload, variant: 'missing-dependency' }), /no POST replay/);
  assert.equal(f.calls.filter(c => c.method === 'POST').length, 1);
});
test('native incomplete directory and durable journal failure block BEFORE command', async () => {
  for (const mode of ['incomplete', 'persist-failed']) {
    const f = fixture(mode); await assert.rejects(probe(f.h, { intended: payload, variant: 'missing-dependency' }));
    assert.equal(f.calls.filter(c => c.method === 'POST').length, 0);
    assert.equal(f.h.state.resources[0].outcome, 'not-sent');
  }
});
test('native cleanup rejects changed original principal or Host before owner access', async () => {
  for (const field of ['origin', 'identity']) {
    const f = fixture('lost'); await assert.rejects(probe(f.h, { intended: payload, variant: 'missing-dependency' }));
    if (field === 'origin') f.actor.origin = 'https://other.test'; else f.actor.identity.account = 'other';
    const count = f.calls.length; await assert.rejects(cleanup(f.h, f.h.state.resources[0]), /exact original/); assert.equal(f.calls.length, count);
  }
});
test('native rejection proof disallows foreign values, earlier validation, resolver outages and authentication failures', () => {
  assert.equal(targetRejection({ status: 400, data: { error: { code: 4, message: '组件 api 镜像解析失败: deployment docker image inspection is unavailable' } } }, 'missing-image'), false);
  assert.equal(targetRejection({ status: 400, data: { value: { id: 17 }, error: { code: 4, message: 'components.api.dependsOn: 组件依赖引用无效' } } }, 'missing-dependency'), false);
  assert.equal(targetRejection({ status: 400, data: { error: { code: 4, message: '部署配置已变更，请重新预检确认' } } }, 'missing-image'), false);
  assert.equal(targetRejection({ status: 403, data: { error: { code: 4, message: '组件 api 镜像解析失败: missing' } } }, 'missing-image'), false);
});
test('native publication snapshots its exact draft, complete revision history and package directory; unresolved publication blocks parent removal', async () => {
  const f = fixture('revision'), parent = { collection: '/panel/application/definitions/', id: 7 };
  const r = await probe(f.h, { definitionId: 7, intended: { expectedDefinitionVersion: 10, expectedPreviewDigest: 'positive-control-digest' }, variant: 'missing-image' });
  assert.equal(r.route, '/panel/application/definitions/7/revisions/');
  assert.ok(f.calls.some(c => c.method === 'GET' && c.route === '/panel/application/definitions/7/revisions/?_pageSize=100&_pageNum=1'));
  assert.equal(r.before.definition.id, 7); assert.deepEqual(r.after.revisions, []);
  guardDefinitionCleanup(f.h, parent);
  r.phase = 'intent';
  assert.throws(() => guardDefinitionCleanup(f.h, parent), /preserve its exact parent/);
  guardDefinitionCleanup(f.h, { ...parent, id: 8 });
});
