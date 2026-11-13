const test = require('node:test');
const assert = require('node:assert/strict');
const { rejected } = require('./entity_capability_cases.cjs');
test('capability negatives prove semantic refusal and unchanged owner, never authentication or read-only acceptance', async () => {
  for (const mode of ['refused', 'authentication', 'accepted-check', 'accepted-save', 'owner-read-loss', 'mutated-after-refusal']) {
    const before = { definitionVersion: 5, entities: [{ id: 8, name: 'sample', pkgPath: '/test', updateTime: 4 }] };
    const parent = { kind: 'definition', id: 7, creation: { ownershipConfirmed: true } }, calls = [];
    const h = { state: { resources: [parent] }, persist() {}, Blocked: Error, good: r => r.status === 200 && !r.data.error,
      check(label, condition) { assert.ok(condition, label); },
      async api(_, method) {
        calls.push(method); assert.equal(parent.capabilityAdmission.at(-1).outcome, 'unknown');
        if (mode === 'authentication') return { status: 401, data: { error: { code: 11, message: 'session unavailable' } } };
        if (mode === 'accepted-check' || mode === 'accepted-save' && method === 'PUT') return { status: 200, data: { error: null, value: method === 'PUT' ? { ...before, definitionVersion: 6 } : { targetDigest: 'invalid-but-accepted' } } };
        return { status: 200, data: { error: { code: 4, message: 'capability declaration invalid' }, value: null } };
      },
      async ok() {
        if (mode === 'owner-read-loss') throw Error('independent owner unavailable');
        return { value: mode === 'accepted-save' && calls.at(-1) === 'PUT' || mode === 'mutated-after-refusal' ? { ...before, definitionVersion: 6 } : structuredClone(before) };
      } };
    if (mode === 'refused') {
      await rejected(h, { id: 7 }, before, before.entities[0], 'unknown');
      assert.deepEqual(calls, ['POST', 'PUT']);
      assert.ok(parent.capabilityAdmission.every(c => c.outcome === 'rejected-and-unchanged'));
    } else {
      await assert.rejects(rejected(h, { id: 7 }, before, before.entities[0], 'unknown'));
      const outcome = parent.capabilityAdmission.at(-1).outcome;
      if (mode === 'accepted-check') assert.equal(outcome, 'invalid-preflight-accepted-without-write');
      else if (mode === 'accepted-save') assert.equal(outcome, 'invalid-save-accepted-and-independently-confirmed');
      else {
        assert.equal(outcome, 'unknown');
        const count = calls.length;
        await assert.rejects(rejected(h, { id: 7 }, before, before.entities[0], 'unknown'), /unresolved/);
        assert.equal(calls.length, count);
      }
    }
  }
});
test('collected admission verifies both methods after known acceptance but stops at unknown identity or result', async () => {
  for (const mode of ['accepted', 'authentication', 'changed-after-error', 'read-loss']) {
    const before = { definitionVersion: 5, entities: [{ id: 8, name: 'sample', pkgPath: '/test', updateTime: 4 }] };
    const after = { ...before, definitionVersion: 6 }, parent = { kind: 'definition', id: 7, creation: { ownershipConfirmed: true } }, calls = [];
    const h = { state: { resources: [parent] }, persist() {}, observe() {}, Blocked: Error, good: r => r.status === 200 && !r.data.error,
      async api(_, method) {
        calls.push(method);
        return mode === 'authentication' ? { status: 401, data: { error: { code: 11 } } } : mode === 'changed-after-error' ? { status: 200, data: { error: { code: 4, message: 'capability invalid' } } } : { status: 200, data: { error: null, value: method === 'PUT' ? after : before } };
      },
      async ok() {
        if (mode === 'read-loss') throw Error('owner read lost');
        return { value: mode === 'changed-after-error' || calls.at(-1) === 'PUT' ? after : before };
      } };
    if (mode === 'accepted') {
      const result = await rejected(h, { id: 7 }, before, before.entities[0], 'unknown', true);
      assert.deepEqual(calls, ['POST', 'PUT']);
      assert.deepEqual(result.map(f => [f.refused, f.unchanged]), [[false, true], [false, false]]);
      assert.equal(parent.capabilityAdmission[1].outcome, 'invalid-save-accepted-and-independently-confirmed');
    } else {
      await assert.rejects(rejected(h, { id: 7 }, before, before.entities[0], 'unknown', true), /disposition|owner read lost/);
      assert.deepEqual(calls, ['POST']);
      assert.equal(parent.capabilityAdmission[0].outcome, 'unknown');
      await assert.rejects(rejected(h, { id: 7 }, before, before.entities[0], 'unknown', true), /unresolved/);
      assert.deepEqual(calls, ['POST']);
    }
  }
});
