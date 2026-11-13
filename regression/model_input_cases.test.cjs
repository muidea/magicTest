const { test } = require('node:test');
const assert = require('node:assert/strict');
const { ids, modelEntities, relation } = require('./model_input_cases.cjs');
test('browser admission negatives preserve original identity and never claim durable receipt absence', async t => {
  const business = require('./business_cases.cjs'), { rejectedWrite } = require('./model_input_cases.cjs');
  const body = { operationId: 'original', operation: 'create', fields: [{ name: 'targets', references: [{ id: '7' }, { id: '7' }] }] };
  const refusal = { status: 200, data: { error: { code: 4, message: '业务写入请求或精确身份无效' } } };
  const expected = { stage: 'browser-contract', code: 4, messagePattern: '^业务写入请求或精确身份无效$' };
  let changed = false;
  t.mock.method(business, 'record', async () => ({ status: 200, data: { value: { id: '9', version: changed ? 2 : 1 } } }));
  for (const mode of ['exact', 'wrong-stage', 'forbidden', 'receipt', 'changed']) {
    const r = { commands: [], applicationKey: 'fixture', identity: { deploymentId: 'original' } }, calls = [];
    changed = false;
    const h = { Blocked: Error, persist() {}, good: v => v.status === 200, check: (m, c) => assert.ok(c, m),
      api: async (_actor, _method, route, input) => {
        calls.push({ route, input }); assert.deepEqual(input, body);
        if (calls.length === 1) return structuredClone(refusal);
        changed = mode === 'changed';
        if (mode === 'wrong-stage') return { status: 200, data: { error: { code: 2, message: '原业务写入尚无完成事实；禁止据此自动重发' } } };
        if (mode === 'forbidden') return { status: 403, data: refusal.data };
        if (mode === 'receipt') return { status: 200, data: { value: { operationId: 'original' } } };
        return structuredClone(refusal);
      } };
    if (mode === 'exact') {
      await rejectedWrite(h, {}, r, body, expected);
      assert.equal(r.constraintCommands[0].outcome, 'rejected-at-browser-contract');
    } else {
      await assert.rejects(rejectedWrite(h, {}, r, body, expected), /browser contract/);
      assert.equal(r.constraintCommands[0].outcome, 'unknown');
      await assert.rejects(rejectedWrite(h, {}, r, body, expected), /no replay/);
    }
    assert.equal(calls.length, 2); assert.match(calls[0].route, /create\/execute/); assert.match(calls[1].route, /create\/receipt/);
  }
});
test('owner rejection still requires exact original completion absence and unchanged complete row', async t => {
  const business = require('./business_cases.cjs'), { rejectedWrite } = require('./model_input_cases.cjs');
  t.mock.method(business, 'record', async () => ({ status: 200, data: { value: { id: '9', version: 1 } } }));
  const r = { commands: [], applicationKey: 'fixture', identity: { deploymentId: 'original' } };
  let calls = 0;
  const h = { Blocked: Error, persist() {}, good: v => v.status === 200, check: (m, c) => assert.ok(c, m),
    api: async () => ++calls === 1 ? { status: 200, data: { error: { code: 2, message: 'target not found' } } } :
      { status: 200, data: { error: { code: 2, message: '原业务写入尚无完成事实；禁止据此自动重发' } } } };
  await rejectedWrite(h, {}, r, { operation: 'update', operationId: 'original' }, { code: 2, messagePattern: '^target not found$' });
  assert.equal(r.constraintCommands[0].outcome, 'rejected-and-unchanged');
});
test('relation reader rejects missing or rounded identities and retains exact large decimal string IDs', () => {
  assert.deepEqual(ids([{ id: '9007199254740993' }, { id: 21 }]), ['21', '9007199254740993']);
  for (const invalid of [[{ id: 9007199254740992 }], [{}], [{ id: '1.5' }], [{ id: 0 }], ['21']]) assert.throws(() => ids(invalid), /Unsafe or missing/);
  assert.deepEqual(ids(null), []); assert.deepEqual(ids([]), []);
});
test('relation fixture uses independent target identity and does not rewrite original author input', () => {
  const original = { id: 7, name: 'sample', pkgPath: '/original', updateTime: 41, createTime: 31, expectedEntityVersion: 41,
    fields: [], uniqueConstraints: [{ name: 'unique_code', fields: ['code'] }], writeRules: { versionField: 'version' } };
  const [host, target] = modelEntities(original, 'relations');
  assert.equal(target.id, 0); assert.equal(target.name, 'zzRelationTarget'); assert.equal(host.id, 7);
  assert.equal(target.uniqueConstraints[0].name, 'unique_code_target');
  assert.deepEqual(original.fields, []); assert.equal(host.fields[0].type.isPtr, true); assert.equal(host.fields[1].type.elemType.name, target.name);
  assert.equal(relation('owned', target, false, true).type.isPtr, false);
  const payload = require('./authoring_cases.cjs').authoring.command({ definitionVersion: 51, entities: [original] }, [host, target]);
  assert.deepEqual(payload.baseline, [{ id: 7, entity: '/original/sample', version: 41 }]);
  assert.equal(payload.entities[0].expectedEntityVersion, 41);
  assert.equal(payload.entities[1].expectedEntityVersion, undefined);
  assert.equal(payload.entities[1].updateTime, undefined);
  assert.equal(original.expectedEntityVersion, 41); assert.equal(original.updateTime, 41);
});
test('expanded model uses explicit complete views for both original host and independently named target', () => {
  const { inputViews } = require('./model_input_cases.cjs');
  const entity = { name: 'sample', pkgPath: '/original', uniqueConstraints: [], fields: [{ name: 'id', spec: { primaryKey: true, valueDeclare: 'snowflake' } }, { name: 'name', spec: {} }] };
  const ui = { entity: { primaryKey: 'id' }, capabilities: { query: true }, fields: [{ name: 'id', type: 'integer' }, { name: 'name', type: 'string', required: true }] };
  for (const mode of ['types', 'relations']) {
    const model = modelEntities(entity, mode), views = inputViews({ model: { entities: model } }, ui);
    assert.deepEqual(Object.keys(views), model.map(e => e.pkgPath + '/' + e.name));
    assert.deepEqual(views['/original/sample'].fields.map(f => f.name), model[0].fields.map(f => f.name));
    assert.equal(views['/original/sample'].fields[0].readonly, true);
    if (mode === 'types') {
      assert.equal(model[0].fields.find(f => f.name === 'flag').type.name, 'boolean');
      assert.equal(views['/original/sample'].fields.find(f => f.name === 'flag').type, 'boolean');
      assert.equal(views['/original/sample'].fields.find(f => f.name === 'occurredAt').format, 'date-time');
    }
    else assert.equal(views['/original/sample'].fields.find(f => f.name === 'targets').type, 'array');
  }
  assert.equal(ui.fields.length, 2); assert.throws(() => ids([{ id: '7' }, { id: 7 }]), /Duplicate/);
});
