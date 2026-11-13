const { test } = require('node:test');
const assert = require('node:assert/strict');
const { decodePage, scanPages } = require('./page_runtime_cases.cjs');
const context = { identity: { deploymentId: 'a'.repeat(32) }, pageDigest: 'sha256:' + 'b'.repeat(64) };
const row = id => ({ fields: [{ key: 'id', value: { kind: 'integer', number: id } }, { key: 'name', value: { kind: 'string', text: '同名' } }] });
const value = ids => ({ identity: structuredClone(context.identity), sourceKey: 'records', pageDigest: context.pageDigest, readAt: '2026-11-09T07:00:00.000Z', value: { apiVersion: 'magic.base-value-read/v1', rows: ids.map(row) } });
test('published pages add exact application identity to the full saved author content', () => {
  const { frozenPages } = require('./page_runtime_cases.cjs');
  const content = { schemaVersion: 'magic.application-ui/v1', entityViews: { '/sample': { fields: [] } }, pages: [{ key: 'home' }] };
  const published = frozenPages(content, { name: 'exact', uuid: 'original' });
  assert.deepEqual(published, { ...content, applicationKey: 'exact', applicationUuid: 'original', modelRevision: 1 });
  published.pages[0].key = 'other'; assert.equal(content.pages[0].key, 'home');
});
test('explicit authored view keeps model-allocated key read-only without mutating runtime fallback or copying layout', () => {
  const { explicitView } = require('./page_runtime_cases.cjs');
  const entity = { name: 'sample', pkgPath: '/new', fields: [{ name: 'id', spec: { primaryKey: true, valueDeclare: 'snowflake' } }, { name: 'name', spec: {} }] };
  const ui = { entity: { primaryKey: 'id' }, capabilities: { query: true }, fields: [{ name: 'id', readonly: false }, { name: 'name', required: true }], detail: { layout: 'unsupported' } };
  const view = explicitView(entity, ui);
  assert.equal(view.fields[0].readonly, true); assert.equal(ui.fields[0].readonly, false);
  assert.equal(view.detail, undefined); assert.equal(view.entity.pkgPath, '/new');
  assert.deepEqual(view.fields[1], ui.fields[1]);
  for (const change of [e => { e.fields[0].spec.valueDeclare = 'customer'; }, e => { e.fields.pop(); }, e => { e.fields[1].spec.primaryKey = true; }]) {
    const altered = structuredClone(entity); change(altered); assert.throws(() => explicitView(altered, ui));
  }
});
test('source probe keeps original route while testing a different expected installation fence', async () => {
  const { sourceRead } = require('./page_runtime_cases.cjs');
  const original = 'a'.repeat(32), wrong = { deploymentId: 'b'.repeat(32) };
  const actor = { origin: 'https://panel.test', page: { async evaluate(_, args) {
    assert.equal(new URL(args.url).searchParams.get('deploymentId'), original);
    assert.deepEqual(JSON.parse(Buffer.from(args.header, 'base64url').toString()), wrong);
    return { status: 409, data: { error: { code: 19 } } };
  } } };
  const result = await sourceRead({ observe() {} }, actor, { applicationKey: 'exact', instance: { deploymentId: original }, identity: wrong }, { sourceKey: 'records', pageSize: 5 });
  assert.equal(result.status, 409);
});
test('frozen page decoder preserves exact int64 keys and rejects identity, scalar, time and projection substitution', () => {
  assert.equal(decodePage(value(['9007199254740993']), context, 5)[0].id, '9007199254740993');
  for (const change of [v => { v.identity.deploymentId = 'c'.repeat(32); }, v => { v.sourceKey = 'other'; }, v => { v.pageDigest = 'sha256:' + 'c'.repeat(64); }, v => { v.readAt = '2026-02-30T07:00:00.000Z'; }, v => { v.value.error = { message: 'owner error' }; }, v => { v.value.rows[0].fields[0].value.number = '9223372036854775808'; }, v => { v.value.rows[0].fields[0].value.number = 7; }, v => { v.value.rows[0].fields[1].key = 'id'; }, v => { v.value.rows[0].fields[1].value.kind = 'null'; }, v => { v.hasMore = true; }]) {
    const response = value(['7']); change(response); assert.throws(() => decodePage(response, context, 5));
  }
});
test('frozen source scanner stops at duplicate, nonmonotone, repeated cursor or owner failure without a new read', async () => {
  for (const mode of ['duplicate', 'nonmonotone', 'repeated-cursor', 'owner-error', 'good']) {
    let sent = 0;
    const h = { Blocked: Error, good: r => r.status === 200 && !r.data.error, check(label, valid) { assert.ok(valid, label); } };
    const read = async (_, actor, bound, body) => {
      assert.equal(bound, context); sent++; assert.equal(body.pageSize, 1);
      const result = value([sent === 1 ? '7' : mode === 'duplicate' ? '7' : mode === 'nonmonotone' ? '6' : '8']);
      if (sent === 1 || mode === 'repeated-cursor') { result.hasMore = true; result.nextCursor = 'opaque-original'; }
      return { status: mode === 'owner-error' ? 503 : 200, cacheControl: 'private, no-store', data: { value: result } };
    };
    const action = scanPages(h, {}, context, 1, read);
    if (mode === 'good') assert.deepEqual((await action).rows.map(r => r.id), ['7', '8']);
    else await assert.rejects(action, /source page succeeds|strictly increasing|earlier continuation/);
    assert.equal(sent, mode === 'owner-error' ? 1 : 2);
  }
});
