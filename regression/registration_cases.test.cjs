const { test } = require('node:test');
const assert = require('node:assert/strict');
const { directoryValues, registrationAuthority } = require('./registration_cases.cjs');
const h = { Blocked: Error };

test('new registration ingress waits only on read-only 404 and confirms exact enabled original owner', async () => {
  const { waitForRegistrationIngress } = require('./registration_cases.cjs');
  for (const mode of ['ready', 'late-ready', 'permanent-404', 'unexpected-success', 'server-error', 'disabled', 'wrong-owner', 'changed-owner', 'untracked']) {
    const ns = { id: 7, name: 'original', updateTime: 10, status: 2, startTime: Date.now() - 1000, expireTime: Date.now() + 60000 };
    const actor = { identity: { namespace: 'original' } }, calls = [], delays = [];
    const current = { ...ns, ...(mode === 'disabled' ? { status: 1 } : {}), ...(mode === 'wrong-owner' ? { id: 8 } : {}), ...(mode === 'changed-owner' ? { updateTime: 11 } : {}) };
    const resource = { kind: 'namespace', id: 7, name: 'original', phase: 'created', creation: { ownershipConfirmed: mode !== 'untracked', response: { data: { value: ns } } } };
    let reads = 0;
    const harness = { state: { resources: [resource] }, admin: {}, check(label, condition) { assert.ok(condition, label); }, async ok(who, method, route) { assert.equal(who, this.admin); calls.push([method, route]); return { value: current }; }, async api(who, method, route) { assert.equal(who, actor); calls.push([method, route]); reads++; return { status: mode === 'unexpected-success' ? 200 : mode === 'server-error' ? 503 : mode === 'ready' || (mode === 'late-ready' && reads === 3) ? 401 : 404, data: {} }; } };
    const result = waitForRegistrationIngress(harness, ns, actor, async ms => delays.push(ms));
    if (['ready', 'late-ready'].includes(mode)) await result; else await assert.rejects(result);
    assert.ok(calls.every(c => c[0] === 'GET'));
    if (mode === 'late-ready') { assert.equal(reads, 3); assert.deepEqual(delays, [1000, 1000]); }
    if (mode === 'permanent-404') { assert.equal(reads, 6); assert.equal(delays.length, 5); }
    if (['disabled', 'wrong-owner', 'changed-owner', 'untracked'].includes(mode)) assert.equal(reads, 0);
    if (['unexpected-success', 'server-error'].includes(mode)) assert.equal(reads, 1);
  }
});

test('owner empty directory with total zero is readable', () => {
  assert.deepEqual(directoryValues(h, { values: null, pagination: { total: 0 } }), []);
  assert.deepEqual(directoryValues(h, { values: [], pagination: { total: 0 } }), []);
  const rows = [{ id: 7 }];
  assert.equal(directoryValues(h, { values: rows, pagination: { total: 1 } }), rows);
});

test('registration authority uses exact source, subject and protected role set', () => {
  const check = { check(label, condition) { assert.ok(condition, label); } };
  const roleRefs = [{ module: 'runner', key: 'portal-viewer' }];
  const binding = { subjectType: 'account', subjectId: 7, sourceType: 'registration', sourceKey: 'account-registration:7', sourceVersion: 1, status: 2, roleModule: 'runner', roleKey: 'portal-viewer' };
  registrationAuthority(check, 7, roleRefs, [binding]);
  for (const change of [
    { subjectId: 8 }, { subjectType: 'endpoint' }, { sourceType: 'template' },
    { sourceKey: 'account-registration:8' }, { sourceVersion: 0 }, { status: 1 },
    { roleKey: 'management-admin' },
  ]) assert.throws(() => registrationAuthority(check, 7, roleRefs, [{ ...binding, ...change }]));
  assert.throws(() => registrationAuthority(check, 7, roleRefs, []));
  assert.throws(() => registrationAuthority(check, 7, roleRefs, [binding, binding]));
});

test('missing or incomplete registration identity rows never become an empty directory', () => {
  for (const page of [
    { values: null, pagination: { total: 1 } },
    { values: null },
    { pagination: { total: 0 } },
    { values: [], pagination: { total: 1 } },
    { values: [], pagination: { total: 0, hasMore: true } },
  ]) assert.throws(() => directoryValues(h, page), /requires complete reader/);
});
