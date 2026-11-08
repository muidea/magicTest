const { test } = require('node:test');
const assert = require('node:assert/strict');
const { cleanup } = require('./feedback_cases.cjs');
const { attachmentDenied } = require('./feedback_cases.cjs');
test('private attachment accepts exact owner concealment, never route miss, outage or binary content', () => {
  const h = { check: (_, value) => assert.ok(value), inaccessible: () => { throw Error('Not the expected boundary'); } };
  attachmentDenied(h, { status: 404, data: { text: 'feedback attachment is unavailable\n' } });
  for (const result of [{ status: 404, data: { text: '404 page not found\n' } }, { status: 503, data: { text: 'feedback attachment is unavailable\n' } }, { status: 200, data: { bytes: Buffer.from('private content') } }]) assert.throws(() => attachmentDenied(h, result));
});
class Blocked extends Error {}
function fixture() {
  const identity = account => ({ namespace: 'tenant-a', account });
  const actor = account => ({ identity: identity(account), origin: 'https://tenant-a.example' });
  const user = actor('member'), tenantAdmin = actor('manager'), calls = [];
  const value = { id: 19, title: 'original', submitter: { id: 7, account: 'member' }, namespace: 'tenant-a' };
  const r = { kind: 'feedback-ticket', id: 19, phase: 'created', intended: { title: 'original' }, submitterID: 7,
    creator: { actorName: 'user', identity: identity('member'), origin: user.origin }, manager: { actorName: 'tenantAdmin', identity: identity('manager'), origin: tenantAdmin.origin },
    creation: { outcome: 'confirmed' }, commands: [{ kind: 'message', outcome: 'confirmed', messageID: 21 }] };
  let deleted = false;
  const h = { user, tenantAdmin, Blocked, persist() {}, good: x => x.status === 200 && !x.data.error,
    check: (label, condition) => assert.ok(condition, label), api: async (actor, method, route) => {
      calls.push({ actor: actor.identity.account, method, route });
      if (method === 'DELETE') { deleted = true; return { status: 200, data: { value } }; }
      return deleted ? { status: 200, data: { error: { code: 2 }, value: null } } : { status: 200, data: { value } };
    } };
  return { h, r, calls, value };
}
test('feedback cleanup uses original manager and independently confirms ticket and message absence', async () => {
  const { h, r, calls } = fixture(); await cleanup(h, r);
  assert.equal(r.phase, 'deleted'); assert.equal(calls.filter(x => x.method === 'DELETE').length, 1);
  assert.equal(calls.find(x => x.method === 'DELETE').actor, 'manager');
  assert.ok(calls.some(x => x.actor === 'member' && x.route === '/portal/feedbacks/19'));
  assert.ok(calls.some(x => x.route === '/panel/support/feedback/messages/21'));
});
test('unknown upload, unconfirmed original creation and changed manager never authorize deletion', async () => {
  for (const change of [f => f.r.commands.push({ kind: 'upload', outcome: 'unknown' }), f => f.r.creation.outcome = 'unknown', f => f.h.tenantAdmin.identity.namespace = 'other']) {
    const f = fixture(); change(f); await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.calls.filter(x => x.method === 'DELETE').length, 0);
  }
});
test('different original creator or namespace returned by owner prevents deleting guessed ticket', async () => {
  for (const change of [f => f.value.submitter.id = 8, f => f.value.title = 'other', f => f.value.namespace = 'tenant-b']) {
    const f = fixture(); change(f); await assert.rejects(cleanup(f.h, f.r)); assert.equal(f.calls.filter(x => x.method === 'DELETE').length, 0);
  }
});
test('response-lost original DELETE is retained and cannot be replayed', async () => {
  const f = fixture(); f.h.api = async (actor, method) => {
    f.calls.push({ method }); if (method === 'DELETE') throw Error('lost original response'); return { status: 200, data: { value: f.value } };
  };
  await assert.rejects(cleanup(f.h, f.r), /lost original response/);
  assert.equal(f.r.deletion.outcome, 'unknown'); assert.equal(f.r.phase, 'created');
  await assert.rejects(cleanup(f.h, f.r), /do not replay/); assert.equal(f.calls.filter(x => x.method === 'DELETE').length, 1);
});
