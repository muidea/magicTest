// Public Panel conditional scalar commands. Dedicated asset commands retain
// their separate lifecycle; restoring a profile must never DELETE its assets.
const { isDeepStrictEqual: same } = require('node:util');
const route = '/panel/namespace-branding/';
const scalarKeys = ['platformName', 'platformShortName', 'loginTitle', 'loginSubtitle', 'footerText', 'primaryColor', 'logoAltText', 'backgroundPosition', 'backgroundOverlayOpacity', 'sloganMode', 'sloganAltText', 'brandingFeatureMode', 'brandingFeatureAltText'];
const assetKeys = ['brandIcon', 'favicon', 'desktopBackground', 'mobileBackground', 'desktopSlogan', 'mobileSlogan', 'desktopBrandingFeature', 'mobileBrandingFeature'];
function scalars(view) {
  return Object.fromEntries(scalarKeys.map(key => [key, view.override?.[key] ?? (key === 'backgroundOverlayOpacity' ? null : key.endsWith('Mode') ? 'inherit' : '')]));
}
const assets = view => Object.fromEntries(assetKeys.map(key => [key, view.override?.[key] ?? null]));
const read = async (h, actor) => (await h.ok(actor, 'GET', route)).value;
function original(h, r, actor) {
  if (r.kind !== 'branding-profile-restore' || r.collection !== route || !same(actor?.identity, r.actorIdentity) || actor.origin !== r.origin || r.namespace !== actor.identity.namespace) throw new h.Blocked('Brand profile requires exact original actor, namespace and origin');
  if (r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Unresolved original brand command; never replay or reset');
}
function track(h, actor, view) {
  h.check('Brand snapshot belongs to original actor namespace', view.namespace === actor.identity.namespace);
  const r = { kind: 'branding-profile-restore', collection: route, actorIdentity: structuredClone(actor.identity), origin: actor.origin, namespace: view.namespace, original: structuredClone(view), last: structuredClone(view), phase: 'created', commands: [] };
  h.state.resources.push(r); h.persist(); return r;
}
async function write(h, actor, r, values) {
  original(h, r, actor);
  const before = await read(h, actor);
  if (!same(before, r.last)) throw new h.Blocked('Concurrent brand revision or projection changed; no overwrite');
  const body = { ...scalars({}), ...values, expectedResourceId: before.override?.id || 0, expectedResourceVersion: before.override?.resourceVersion || 0 };
  if (!same(Object.keys(body).sort(), [...scalarKeys, 'expectedResourceId', 'expectedResourceVersion'].sort())) throw Error('Only current scalar contract is writable');
  const command = { body: structuredClone(body), outcome: 'unknown' }; r.commands.push(command); h.persist();
  command.response = await h.api(actor, 'PUT', route, body); h.persist();
  const after = await read(h, actor);
  const intended = Object.fromEntries(scalarKeys.map(key => [key, body[key]]));
  const empty = same(intended, scalars({}));
  const identityOK = empty ? !after.override || after.override.id === 0 && after.override.resourceVersion === 0 : Number.isSafeInteger(after.override?.id) && after.override.id > 0 && (!before.override?.id || after.override.id === before.override.id) && after.override.resourceVersion === (before.override?.resourceVersion || 0) + 1;
  if (h.good(command.response) && same(command.response.data.value, after) && after.namespace === r.namespace && identityOK && same(scalars(after), intended) && same(assets(before), assets(after))) {
    command.outcome = 'confirmed'; r.last = structuredClone(after); h.persist(); return after;
  }
  if ([200, 400, 409, 422].includes(command.response.status) && [4, 19].includes(command.response.data?.error?.code) && command.response.data.value == null && same(after, before)) {
    command.outcome = 'rejected-and-unchanged'; h.persist();
    h.check('Brand scalar command accepted at intended owner stage', false, command.response);
  }
  throw new h.Blocked('Original brand command outcome not independently confirmed; preserve journal');
}
async function restore(h, r, actor = h.admin) {
  original(h, r, actor);
  const before = await read(h, actor);
  if (r.phase === 'deleted') {
    h.check('Restored scalar and original asset semantics remain exact', same(scalars(before), scalars(r.original)) && same(assets(before), assets(r.original)));
    return { proof: 'Independent original scalar and asset semantics; historical version not rewritten' };
  }
  if (!same(before, r.last)) throw new h.Blocked('Concurrent brand owner changed; restoration cannot overwrite');
  if (!same(scalars(before), scalars(r.original))) await write(h, actor, r, scalars(r.original));
  const after = await read(h, actor);
  h.check('Independent owner confirms original scalar and asset semantics restored', same(scalars(after), scalars(r.original)) && same(assets(after), assets(r.original)) && after.namespace === r.namespace);
  r.phase = 'deleted'; r.restored = structuredClone(after); h.persist();
  return { proof: 'Conditional scalar restoration and independent owner read; dedicated assets preserved; no historical version replay' };
}
module.exports = { route, scalarKeys, assetKeys, scalars, assets, read, track, write, restore };
