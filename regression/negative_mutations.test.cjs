const { test } = require('node:test');
const assert = require('node:assert/strict');
const { negativeBrandWrite, negativeCreate, cleanupNegativeMutation } = require('./negative_mutations.cjs');
const { handlers } = require('./standard_cases.cjs');
const clone = value => structuredClone(value);
const good = r => r.status === 200 && !r.data?.error;
const check = (label, condition) => assert.ok(condition, label);
const denied = { status: 403, data: { error: { code: 5 } } };
const brandRoute = '/panel/namespace-branding/';
function brandFixture(initial = null) {
  let current = { namespace: 'panel', override: clone(initial), resolved: { platformName: initial?.platformName || 'original', version: 'initial' } };
  const original = clone(current), persisted = [], commands = [];
  const h = { state: { resources: [] }, admin: {}, check, good, Blocked: Error,
    persist() { persisted.push(clone(h.state.resources)); },
    async ok(actor, method) { assert.equal(method, 'GET'); return { value: clone(current) }; },
    async api(actor, method, route, body) {
      assert.equal(method, 'PUT'); commands.push(clone(body));
      assert.ok(h.state.resources.some(r => r.kind === 'negative-branding' && r.phase !== 'deleted'), 'intent exists before command');
      assert.equal(body.expectedResourceVersion, current.override?.resourceVersion || 0, 'owner conditional write');
      if (body.expectedResourceId !== undefined) assert.equal(body.expectedResourceId, current.override?.id || 0, 'owner exact identity guard');
      const empty = !body.platformName;
      current = { namespace: 'panel', override: empty ? null : { ...clone(body), id: current.override?.id || 1, resourceVersion: (current.override?.resourceVersion || 0) + 1 }, resolved: { platformName: empty ? 'original' : body.platformName, version: 'changed' } };
      delete current.override?.expectedResourceVersion; delete current.override?.expectedResourceId;
      return { status: 200, data: { value: clone(current) } };
    }
  };
  return { h, original, persisted, commands, read: () => clone(current), mutate: value => { current = value; } };
}

test('unexpected global branding success restores absent profile with conditional PUT', async () => {
  const f = brandFixture();
  const result = await negativeBrandWrite(f.h, { identity: { account: 'original-tenant-admin' } }, brandRoute, f.original, { platformName: 'unique-negative', expectedResourceVersion: 0 });
  assert.ok(good(result));
  const r = f.h.state.resources[0];
  assert.equal(f.persisted[0][0].outcome, 'unknown');
  assert.equal(r.original.override, null);
  const proof = await cleanupNegativeMutation(f.h, r);
  assert.equal(proof.restored.override, null);
  assert.equal(f.commands.length, 2);
  assert.equal(f.commands[1].expectedResourceVersion, 1);
  assert.equal(f.commands[1].platformName, '');
});

test('brand restore preserves original scalar semantics and assets', async () => {
  const f = brandFixture({ id: 7, resourceVersion: 3, platformName: 'original', brandIcon: { digest: 'asset' } });
  const api = f.h.api;
  f.h.api = async (...args) => {
    const result = await api(...args);
    const value = f.read(); value.override.brandIcon = { digest: 'asset' }; f.mutate(value);
    result.data.value = f.read(); return result;
  };
  await negativeBrandWrite(f.h, {}, brandRoute, f.original, { platformName: 'unique-negative', expectedResourceVersion: 3 });
  const proof = await cleanupNegativeMutation(f.h, f.h.state.resources[0]);
  assert.deepEqual(proof.restored.override.brandIcon, f.original.override.brandIcon);
  assert.equal(proof.restored.override.resourceVersion, 5);
});

test('concurrent branding edits and unknown results remain open without destructive restore', async () => {
  for (const mode of ['concurrent', 'response-lost', 'restore-response-lost', 'rejected-but-written']) {
    const f = brandFixture();
    const api = f.h.api;
    if (mode === 'response-lost') f.h.api = async (...args) => { await api(...args); throw Error('response lost'); };
    if (mode === 'rejected-but-written') f.h.api = async (...args) => { await api(...args); return denied; };
    try { await negativeBrandWrite(f.h, {}, brandRoute, f.original, { platformName: 'unique-negative', expectedResourceVersion: 0 }); } catch (e) { assert.match(e.message, /response lost/); }
    const r = f.h.state.resources[0];
    if (mode === 'concurrent') { const current = f.read(); current.override.platformName = 'maintainer'; current.override.resourceVersion++; f.mutate(current); }
    if (mode === 'restore-response-lost') f.h.api = async (...args) => { await api(...args); throw Error('restore response lost'); };
    await assert.rejects(cleanupNegativeMutation(f.h, r));
    assert.notEqual(r.phase, 'deleted');
    const count = f.commands.length;
    await assert.rejects(cleanupNegativeMutation(f.h, r));
    assert.equal(f.commands.length, count, 'unknown restore is never replayed');
    if (mode === 'concurrent') assert.equal(f.read().override.platformName, 'maintainer');
    else if (mode !== 'restore-response-lost') assert.equal(f.commands.length, 1);
  }
});

test('branding version conflict at actual restore leaves concurrent owner data intact', async () => {
  const f = brandFixture();
  await negativeBrandWrite(f.h, {}, brandRoute, f.original, { platformName: 'unique-negative', expectedResourceVersion: 0 });
  f.h.api = async () => {
    const current = f.read(); current.override.platformName = 'racing-maintainer'; current.override.resourceVersion++; f.mutate(current);
    return { status: 409, data: { error: { code: 21 } } };
  };
  await assert.rejects(cleanupNegativeMutation(f.h, f.h.state.resources[0]), /acknowledged/);
  assert.equal(f.read().override.platformName, 'racing-maintainer');
});

function categoryFixture(mode) {
  const rows = [], persisted = [], removed = [];
  const h = { admin: {}, state: { resources: [] }, check, good, Blocked: Error,
    persist() { persisted.push(clone(h.state.resources)); },
    async ok(actor, method, route) {
      if (method === 'DELETE') { removed.push(rows[0].id); rows.length = 0; return {}; }
      return route.includes('?') ? { values: clone(rows) } : { value: clone(rows[0]) };
    },
    async api(actor, method, route, body) {
      if (method === 'GET') return { status: 200, data: { error: { code: 2 }, value: null } };
      assert.equal(h.state.resources[0].outcome, 'unknown', 'intent persisted before POST');
      if (mode === 'denied') return denied;
      const value = { ...clone(body), id: 99 }; rows.push(value);
      if (mode === 'response-lost') throw Error('response lost');
      return { status: 200, data: { value: clone(value) } };
    },
    async gone(collection, id) { assert.equal(id, 99); assert.equal(rows.length, 0); }
  };
  return { h, rows, persisted, removed };
}
test('negative POST journals unexpected returned ID before denial and cleans the exact identity', async () => {
  const f = categoryFixture('accepted');
  const result = await negativeCreate(f.h, {}, '/catalogs/', { name: 'current-run-unique' }, 'catalog');
  assert.throws(() => assert.equal(good(result), false));
  const r = f.h.state.resources[0];
  assert.equal(r.id, 99);
  assert.equal(r.phase, 'intent');
  await cleanupNegativeMutation(f.h, r);
  assert.deepEqual(f.removed, [99]);
  assert.equal(f.rows.length, 0);
});
test('negative POST response loss keeps known residual and cleanup open without replay or guessed deletion', async () => {
  const f = categoryFixture('response-lost');
  await assert.rejects(negativeCreate(f.h, {}, '/catalogs/', { name: 'current-run-unique' }, 'catalog'), /response lost/);
  const r = f.h.state.resources[0];
  assert.equal(r.observed[0].id, 99);
  await assert.rejects(cleanupNegativeMutation(f.h, r), /Unknown negative creation/);
  assert.notEqual(r.phase, 'deleted');
  assert.equal(f.rows.length, 1);
  assert.deepEqual(f.removed, []);
});
test('terminal negative POST denial closes only after complete independent absence', async () => {
  const f = categoryFixture('denied');
  await negativeCreate(f.h, {}, '/catalogs/', { name: 'current-run-unique' }, 'catalog');
  assert.equal(f.h.state.resources[0].phase, 'deleted');
});

test('F051 both readonly-role and missing-role branches register unexpected POST before throwing', async () => {
  for (const readerAvailable of [true, false]) {
    const f = categoryFixture('accepted'), h = f.h;
    h.credentials = { namespace: 'panel' }; h.state.prefix = 'fixture'; h.user = {}; h.state.password = 'fixture-only';
    const c = { id: 1, name: 'fixture-catalog' };
    h.create = async (route, body, kind) => kind === 'catalog' ? c : { ...body, id: 2 };
    h.login = async () => ({});
    h.denied = (r, label) => { if (good(r)) { assert.equal(h.state.resources[0].id, 99); throw Error(label); } };
    const ok = h.ok;
    h.directory = async (actor, route) => (await h.ok(actor, 'GET', route)).values;
    h.ok = async (actor, method, route) => {
      if (route.includes('/roles/')) return { values: readerAvailable ? [{ module: '/modules/kernel/runner', key: 'management-catalog-viewer', humanAssignable: true, status: 2, privilege: [{ module: '/modules/kernel/runner', uriPath: '/panel/catalogs/', value: 4 }] }] : [] };
      if (actor !== h.admin) return route.includes('?') ? { values: [c] } : { value: c };
      return ok(actor, method, route);
    };
    const api = h.api;
    h.api = (actor, method, route, body) => method === 'DELETE' ? Promise.resolve(denied) : api(actor, method, route, body);
    await assert.rejects(handlers['F051-003'](h), /cannot write category/);
    assert.equal(h.state.resources[0].id, 99);
    await cleanupNegativeMutation(h, h.state.resources[0]);
    assert.equal(f.rows.length, 0);
  }
});


test('F055 registers the actual platform write before failed authorization assertion', async () => {
  const f = brandFixture(), h = f.h;
  h.credentials = { namespace: 'panel' }; h.state.prefix = 'fixture';
  h.admin.origin = 'https://panel.local.vpc'; h.tenantAdmin = { identity: { account: 'tenant-admin' } }; h.user = {};
  h.need = () => ({ name: 't001' }); h.owned = () => {}; h.sessionAtOrigin = async () => ({ identity: h.tenantAdmin.identity, addressed: true });
  let local = { namespace: 't001', override: null };
  const originalOk = h.ok, originalApi = h.api;
  h.ok = async (actor, method, route, body) => {
    if (route === '/api/v1/web/session/') return { value: { homeNamespace: 't001', account: { account: 'tenant-admin' } } };
    if (actor === h.admin) return originalOk(actor, method, route, body);
    if (method === 'PUT') local = { namespace: 't001', override: { ...body, namespace: 't001', resourceVersion: 1 }, resolved: { platformName: body.platformName } };
    return { value: clone(local) };
  };
  h.api = async (actor, method, route, body, headers) => actor.addressed || actor === h.admin ? originalApi(actor, method, route, body, headers) : actor === h.user ? denied : { status: 200, data: { value: clone(local) } };
  h.denied = (result, label) => check(label, !good(result));
  await assert.rejects(handlers['F055-003'](h), /cannot edit actual platform global branding/);
  assert.equal(h.state.resources.length, 2);
  assert.equal(h.state.resources[0].phase, 'deleted');
  assert.equal(h.state.resources[1].name, 'panel');
  assert.match(f.read().override.platformName, /fixture-forbidden-global/);
  await cleanupNegativeMutation(h, h.state.resources[1]);
  assert.equal(f.read().override, null);
});


test('forged brand target hints journal and restore a global side effect before local-target assertion', async () => {
  const f = brandFixture();
  const result = await negativeBrandWrite(f.h, { identity: { account: 'tenant-admin' } }, brandRoute, f.original,
    { platformName: 'forbidden-hint', expectedResourceVersion: 0 },
    { requestRoute: brandRoute + '?namespace=panel', headers: { 'X-Namespace': 'panel' }, permittedNamespace: 't001' });
  assert.equal(result.data.value.namespace, 'panel');
  const r = f.h.state.resources[0];
  assert.notEqual(r.phase, 'deleted');
  assert.equal(r.requestRoute, brandRoute + '?namespace=panel');
  await cleanupNegativeMutation(f.h, r);
  assert.equal(f.read().override, null);
});

test('incomplete category directory blocks before POST; cleanup does not claim absence', async () => {
  const f = categoryFixture('accepted'); let sent = false;
  f.h.ok = async () => ({ values: [], pagination: { hasMore: true } });
  f.h.api = async () => { sent = true; throw Error('must not send'); };
  await assert.rejects(negativeCreate(f.h, {}, '/catalogs/', { name: 'current-run-unique' }, 'catalog'), /complete owner directory/);
  assert.equal(sent, false);
  const r = f.h.state.resources[0];
  assert.equal(r.outcome, 'not-sent');
  assert.match((await cleanupNegativeMutation(f.h, r)).proof, /No negative command/);
});

test('unexpected category identity change prevents cleanup deletion', async () => {
  const f = categoryFixture('accepted');
  await negativeCreate(f.h, {}, '/catalogs/', { name: 'current-run-unique' }, 'catalog');
  f.rows[0].id = 100;
  await assert.rejects(cleanupNegativeMutation(f.h, f.h.state.resources[0]), /original category identity/);
  assert.deepEqual(f.removed, []);
});

test('restart cleanup retains the original exact branding intent and does not replay a confirmed restore', async () => {
  const f = brandFixture();
  await negativeBrandWrite(f.h, {}, brandRoute, f.original, { platformName: 'unique-negative', expectedResourceVersion: 0 });
  const restoredState = JSON.parse(JSON.stringify(f.h.state)); f.h.state = restoredState;
  await cleanupNegativeMutation(f.h, restoredState.resources[0]);
  const commands = f.commands.length;
  await cleanupNegativeMutation(f.h, restoredState.resources[0]);
  assert.equal(f.commands.length, commands);
});


test('asset-only owner projection with ID/version zero restores profile absence while retaining assets', async () => {
  const icon = { digest: 'existing-asset', resourceVersion: 3 };
  const f = brandFixture({ id: 0, resourceVersion: 0, namespace: 'panel', platformName: '', sloganMode: '', brandingFeatureMode: '', brandIcon: icon });
  const api = f.h.api;
  f.h.api = async (...args) => {
    const result = await api(...args);
    const value = f.read();
    value.override = value.override ? { ...value.override, brandIcon: clone(icon) } : clone(f.original.override);
    f.mutate(value); result.data.value = f.read(); return result;
  };
  await negativeBrandWrite(f.h, {}, brandRoute, f.original, { platformName: 'negative', expectedResourceVersion: 0 });
  const proof = await cleanupNegativeMutation(f.h, f.h.state.resources[0]);
  assert.deepEqual(proof.restored.override, f.original.override);
  assert.equal(f.commands[1].expectedResourceVersion, 1);
});


test('restoration sends resource ID and version so owner can reject same-version recreation during PUT', async () => {
  const f = brandFixture();
  await negativeBrandWrite(f.h, {}, brandRoute, f.original, { platformName: 'unique-negative', expectedResourceVersion: 0 });
  f.h.api = async (actor, method, route, body) => {
    assert.equal(body.expectedResourceId, 1); assert.equal(body.expectedResourceVersion, 1);
    const recreated = f.read(); recreated.override.id = 200; recreated.override.platformName = 'maintainer'; f.mutate(recreated);
    return { status: 409, data: { error: { code: 21 } } };
  };
  await assert.rejects(cleanupNegativeMutation(f.h, f.h.state.resources[0]), /acknowledged/);
  assert.equal(f.read().override.id, 200); assert.equal(f.read().override.platformName, 'maintainer');
});
