const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const endpoint = (r, queryOnly) => '/apps/entity/value/write/update/' + (queryOnly ? 'receipt' : 'execute') +
  '/?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId;
async function reject(h, actor, r, field, value, expected) {
  if (!same(actor.identity, r.actorIdentity) || actor.origin !== r.origin ||
      r.commands.some(c => c.outcome === 'unknown') || r.constraintCommands?.some(c => c.outcome === 'unknown'))
    throw new h.Blocked('Original field command unresolved or actor changed; no replacement write');
  const before = await business.record(h, actor, r);
  h.check('Negative field sample starts with the exact original acknowledged record and version',
    h.good(before) && String(before.data.value.id) === r.recordId && String(before.data.value.version) === r.version);
  const c = { body: business.request(r, 'update', [{ name: field, value }]), expected, outcome: 'unknown' };
  (r.constraintCommands ||= []).push(c); h.persist();
  c.response = await h.api(actor, 'POST', endpoint(r, false), c.body); h.persist();
  c.receiptRead = await h.api(actor, 'POST', endpoint(r, true), c.body); h.persist();
  const after = await business.record(h, actor, r);
  const refused = [200, 400, 409].includes(c.response.status) && c.response.data?.error?.code === expected.code &&
    c.response.data.error.message === expected.message && c.response.data.value == null;
  const noReceipt = [200, 404].includes(c.receiptRead.status) && c.receiptRead.data?.error?.code === 2 &&
    c.receiptRead.data.error.message === '原业务写入尚无完成事实；禁止据此自动重发' && c.receiptRead.data.value == null;
  const unchanged = h.good(after) && same(after.data.value, before.data.value);
  if (refused && noReceipt && unchanged) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
  h.check('Exact field refusal, absent original completion receipt and unchanged complete business row agree',
    c.outcome === 'rejected-and-unchanged', { field, response: c.response, receipt: c.receiptRead, unchanged });
}
async function constraints(h) {
  const f = await fixture(h), actor = await business.member(h, 'manager'), context = await business.runtime(h, f, 0, actor);
  const fields = Object.fromEntries(f.revision.entities[0].fields.map(v => [v.name, v]));
  h.check('Frozen fixture explicitly declares required/nonblank fields, nullable description, default zero and owner-allocated key/version',
    fields.id.spec.primaryKey && fields.id.spec.valueDeclare === 'snowflake' && fields.name.spec.constraint.includes('req') &&
    fields.description.type.isPtr === true && fields.sortOrder.spec.defaultValue === 0 &&
    f.revision.entities[0].writeRules.versionField === 'version' && f.revision.entities[0].writeRules.nonBlank.includes('name'));
  const r = { kind: 'business-record', actorRole: 'manager', phase: 'intent', ...context,
    origin: actor.origin, actorIdentity: structuredClone(actor.identity), commands: [], constraintCommands: [] };
  delete r.ui; h.state.resources.push(r); h.persist();
  let primary;
  try {
    const body = business.request(r, 'create', [{ name: 'code', value: 'RG-' + crypto.randomBytes(8).toString('hex').toUpperCase() },
      { name: 'name', value: '字段约束默认值样本' }, { name: 'description', value: null }]);
    h.check('Actual submitted create omits owner key, owner version and defaulted sortOrder', body.id === '' && body.expectedVersion === '' &&
      body.fields.every(v => !['id', 'version', 'sortOrder'].includes(v.name)));
    await business.execute(h, actor, r, body);
    const created = await business.record(h, actor, r);
    h.check('Independent ordinary owner read confirms generated key, initial version, nullable value and materialized default zero',
      h.good(created) && String(created.data.value.id) === r.recordId && r.version === '1' &&
      created.data.value.description === null && created.data.value.sortOrder === 0 &&
      body.fields.every(v => same(created.data.value[v.name], v.value)), created);
    r.created = created.data.value; r.createRequest = body; h.persist();
    for (const description of ['', '合法说明 Δ', null]) {
      await business.execute(h, actor, r, business.request(r, 'update', [{ name: 'description', value: description }, { name: 'sortOrder', value: 0 }]));
      const current = await business.record(h, actor, r);
      h.check('Nullable/empty/text values and explicit zero retain exact persisted values and owner version', h.good(current) &&
        current.data.value.description === description && current.data.value.sortOrder === 0 && String(current.data.value.version) === r.version);
    }
    for (const [field, value, code, message] of [
      ['name', null, 21, '写入标量类型或约束无效: name'],
      ['name', ' '.repeat(3), 4, '字段不能为空白: name'],
      ['name', '长'.repeat(257), 21, '写入标量类型或约束无效: name'],
      ['description', '长'.repeat(2001), 21, '写入标量类型或约束无效: description'],
      ['sortOrder', 'invalid-number', 21, '写入标量类型或约束无效: sortOrder'],
      ['id', 7, 21, '写入字段未声明、不可写或不是单值: id'],
      ['version', 99, 21, '写入字段未声明、不可写或不是单值: version'],
    ]) await reject(h, actor, r, field, value, { code, message });
  } catch (error) { primary = error; throw error; }
  finally { await business.finishCleanup(h, [r], primary); }
}
constraints.transport = 'owner-api';
module.exports = { handlers: { 'F013-002': constraints }, reject };
