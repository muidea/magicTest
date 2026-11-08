const { test } = require('node:test');
const assert = require('node:assert/strict');
const profile = require('./branding_profile.cjs');
const identity = { account: 'original', namespace: 'panel' }, origin = 'https://panel.example';
function fixture(withProfile = true, withAssets = true) {
  const icon = withAssets ? { digest: 'original-asset', resourceVersion: 3, url: '/original.png' } : null;
  const view = { namespace: 'panel', override: withProfile || withAssets ? { id: withProfile ? 7 : 0, resourceVersion: withProfile ? 2 : 0, ...profile.scalars({}), ...(withProfile ? { platformName: 'original' } : {}), ...(icon ? { brandIcon: icon } : {}) } : null, resolved: { platformName: 'original' } };
  let current = structuredClone(view), snapshots = [], sends = [];
  const h = { admin: { identity: structuredClone(identity), origin }, Blocked: Error, state: { resources: [] }, check: (label, ok) => assert.ok(ok, label), good: r => r.status === 200 && !r.data.error, persist: () => snapshots.push(structuredClone(h.state)), ok: async (actor, method, route) => { assert.equal(method, 'GET'); assert.equal(route, profile.route); return { value: structuredClone(current) }; }, api: async (actor, method, route, body) => {
    assert.equal(method, 'PUT'); assert.equal(route, profile.route); assert.equal(snapshots.at(-1).resources[0].commands.at(-1).outcome, 'unknown');
    assert.equal(body.expectedResourceId, current.override?.id || 0); assert.equal(body.expectedResourceVersion, current.override?.resourceVersion || 0);
    sends.push(structuredClone(body));
    const fields = Object.fromEntries(profile.scalarKeys.map(k => [k, body[k]]));
    if (JSON.stringify(fields) === JSON.stringify(profile.scalars({}))) current.override = icon ? { ...fields, id: 0, resourceVersion: 0, brandIcon: icon } : null;
    else current.override = { ...fields, id: current.override?.id || 9, resourceVersion: (current.override?.resourceVersion || 0) + 1, ...(icon ? { brandIcon: icon } : {}) };
    current.resolved.platformName = fields.platformName || 'original';
    return { status: 200, data: { error: null, value: structuredClone(current) } };
  } };
  return { h, r: profile.track(h, h.admin, view), sends, setCurrent: value => { current = value; } };
}
test('conditional brand restoration preserves original asset-only, absent and explicit scalar semantics without DELETE or revision replay', async () => {
  for (const pair of [[true, true], [false, true], [false, false]]) {
    const f = fixture(...pair);
    await profile.write(f.h, f.h.admin, f.r, { ...profile.scalars(f.r.original), platformName: 'current-run' });
    await profile.restore(f.h, f.r);
    assert.equal(f.r.phase, 'deleted'); assert.equal(f.sends.length, 2);
    assert.deepEqual(profile.scalars(f.r.restored), profile.scalars(f.r.original));
    assert.deepEqual(profile.assets(f.r.restored), profile.assets(f.r.original));
    assert.ok((f.r.restored.override?.resourceVersion || 0) !== 2);
    await profile.restore(f.h, f.r); assert.equal(f.sends.length, 2);
  }
});
test('brand restore refuses another actor, origin, resource identity or concurrent version without overwriting', async () => {
  for (const mode of ['actor', 'origin', 'id', 'version']) {
    const f = fixture();
    if (mode === 'actor') f.h.admin.identity.account = 'foreign';
    if (mode === 'origin') f.h.admin.origin = 'https://foreign.example';
    if (mode === 'id' || mode === 'version') { const changed = structuredClone(f.r.last); changed.override[mode === 'id' ? 'id' : 'resourceVersion']++; f.setCurrent(changed); }
    await assert.rejects(profile.restore(f.h, f.r)); assert.equal(f.sends.length, 0); assert.equal(f.r.phase, 'created');
  }
});
test('lost brand response persists original intent and prevents restore and write replay even when owner has applied it', async () => {
  const f = fixture(), dispatch = f.h.api;
  f.h.api = async (...args) => { await dispatch(...args); throw Error('lost original response'); };
  await assert.rejects(profile.write(f.h, f.h.admin, f.r, { ...profile.scalars(f.r.original), platformName: 'unknown' }), /lost original/);
  assert.equal(f.r.commands[0].outcome, 'unknown');
  await assert.rejects(profile.restore(f.h, f.r), /never replay/);
  await assert.rejects(profile.write(f.h, f.h.admin, f.r, profile.scalars(f.r.original)), /never replay/);
  assert.equal(f.sends.length, 1);
});
test('brand acknowledgement cannot hide changed original assets or wrong returned resource identity', async () => {
  for (const mode of ['asset', 'identity']) {
    const f = fixture(), dispatch = f.h.api;
    f.h.api = async (...args) => { const r = await dispatch(...args); const changed = structuredClone(r.data.value); if (mode === 'asset') changed.override.brandIcon.digest = 'foreign'; else changed.override.id++; f.setCurrent(changed); r.data.value = changed; return r; };
    await assert.rejects(profile.write(f.h, f.h.admin, f.r, { ...profile.scalars(f.r.original), platformName: 'current' }), /not independently/);
    assert.equal(f.r.commands[0].outcome, 'unknown');
    await assert.rejects(profile.restore(f.h, f.r), /never replay/); assert.equal(f.sends.length, 1);
  }
});
