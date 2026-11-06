// Persist negative-test side effects before issuing commands. Only public owner
// reads and conditional writes may establish cleanup; uncertainty stays open.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const fields = ['platformName', 'platformShortName', 'loginTitle', 'loginSubtitle', 'footerText', 'primaryColor', 'logoAltText', 'backgroundPosition', 'backgroundOverlayOpacity', 'sloganMode', 'sloganAltText', 'brandingFeatureMode', 'brandingFeatureAltText'];
const assets = ['brandIcon', 'favicon', 'desktopBackground', 'mobileBackground', 'desktopSlogan', 'mobileSlogan', 'desktopBrandingFeature', 'mobileBrandingFeature'];
const scalar = value => Object.fromEntries(fields.map(key => [key, value?.[key] ?? (key === 'backgroundOverlayOpacity' ? null : key.endsWith('Mode') ? 'inherit' : '')]));
const assetValues = value => Object.fromEntries(assets.map(key => [key, value?.[key] ?? null]));
const semantics = value => ({ namespace: value.namespace, override: value.override ? { ...scalar(value.override), ...assetValues(value.override) } : null,
  resolved: Object.fromEntries(Object.entries(value.resolved || {}).filter(([key]) => key !== 'version')) });
const rejected = response => [401, 403].includes(response.status) || [5, 11, 12, 22].includes(response.data?.error?.code);
const noGlobalWrite = (r, current) => same(current, r.original) && (r.outcome === 'rejected' || (r.outcome === 'accepted' && r.permittedNamespace && r.permittedNamespace !== r.original.namespace && r.response?.data?.value?.namespace === r.permittedNamespace && r.response?.data?.value?.override?.namespace === r.permittedNamespace));
function register(h, resource) { h.state.resources.push(resource); h.persist(); return resource; }
async function brandRead(h, r) { const value = (await h.ok(h.admin, 'GET', r.collection)).value; h.check('Brand owner returns the exact original namespace', value?.namespace === r.original.namespace, value); return value; }
async function negativeBrandWrite(h, actor, collection, original, intended, { requestRoute = collection, headers = {}, permittedNamespace } = {}) {
  const r = register(h, { kind: 'negative-branding', collection, requestRoute, permittedNamespace, name: original.namespace, original: structuredClone(original), intended: structuredClone(intended), requestId: crypto.randomBytes(16).toString('hex'), actorIdentity: actor.identity, phase: 'intent', outcome: 'unknown' });
  let result;
  try { result = await h.api(actor, 'PUT', requestRoute, intended, { ...headers, 'Idempotency-Key': r.requestId }); }
  catch (error) { r.observed = await brandRead(h, r); h.persist(); throw error; }
  r.response = result; r.outcome = h.good(result) ? 'accepted' : rejected(result) ? 'rejected' : 'unknown'; h.persist();
  r.observed = await brandRead(h, r); h.persist();
  if (noGlobalWrite(r, r.observed)) { r.phase = 'deleted'; h.persist(); }
  return result;
}
async function categories(h, r) {
  const list = await h.ok(h.admin, 'GET', r.collection + '?_pageSize=100');
  if (!Array.isArray(list.values) || list.pagination?.hasMore || list.pagination?.total > list.values.length) throw new h.Blocked('Category cleanup needs a complete owner directory');
  return list.values.filter(value => value.name === r.name);
}
async function negativeCreate(h, actor, collection, intended, kind) {
  const r = register(h, { kind: 'negative-create', targetKind: kind, collection, name: intended.name, intended: structuredClone(intended), actorIdentity: actor.identity, phase: 'intent', outcome: 'not-sent' });
  const before = await categories(h, r);
  h.check('Negative creation uses a new exact current-run name', before.length === 0, before);
  r.outcome = 'unknown'; h.persist();
  let result;
  try { result = await h.api(actor, 'POST', collection, intended); }
  catch (error) { r.observed = await categories(h, r); h.persist(); throw error; }
  r.response = result; r.outcome = h.good(result) ? 'accepted' : rejected(result) ? 'rejected' : 'unknown';
  if (h.good(result)) { r.id = result.data.value?.id; r.written = result.data.value; }
  h.persist(); // Including unexpected success, before the caller's denial assertion.
  r.observed = await categories(h, r); h.persist();
  if (r.outcome === 'rejected' && r.observed.length === 0) { r.phase = 'deleted'; h.persist(); }
  return result;
}
async function cleanupNegativeMutation(h, r) {
  if (r.kind === 'negative-create') {
    if (r.outcome === 'not-sent') return { proof: 'No negative command was sent' };
    const rows = await categories(h, r); r.observed = rows; h.persist();
    if (r.outcome === 'rejected' && rows.length === 0) return { rows, proof: 'No command sent or terminal denial and complete owner absence' };
    if (r.outcome !== 'accepted' || !r.id || r.written?.name !== r.name) throw new h.Blocked('Unknown negative creation: retain exact intent; no blind POST replay or deletion by guessed ID');
    if (rows.length === 0) {
      const absent = await h.api(h.admin, 'GET', r.collection + r.id);
      h.check('Exact negative-created ID is independently absent', absent.data?.error?.code === 2 && absent.data.value == null, absent);
      return { proof: 'Exact original returned ID absent from owner' };
    }
    const current = (await h.ok(h.admin, 'GET', r.collection + r.id)).value;
    h.check('Cleanup targets only the returned original category identity', rows.length === 1 && rows[0].id === r.id && same(current, r.written), { current, written: r.written });
    await h.ok(h.admin, 'DELETE', r.collection + r.id);
    await h.gone(r.collection, r.id);
    h.check('Complete category directory confirms no residual test name', (await categories(h, r)).length === 0);
    return { id: r.id, proof: 'Original returned ID, exact owner read, public DELETE and independent absence' };
  }
  const current = await brandRead(h, r); r.observed = current; h.persist();
  if (noGlobalWrite(r, current)) return { proof: 'Terminal denial or exact local result, and unchanged global owner snapshot' };
  if (r.restored && same(current, r.restored)) return { proof: 'Previously confirmed guarded restore remains exact' };
  const written = r.response?.data?.value;
  h.check('Restore requires the exact acknowledged write and independent owner revision', r.outcome === 'accepted' && written?.override?.id > 0 && same(current, written) && same(scalar(written.override), scalar(r.intended)) && same(assetValues(written.override), assetValues(r.original.override)) && written.override.resourceVersion === (r.original.override?.resourceVersion || 0) + 1 && (!r.original.override || (r.original.override.id === 0 && r.original.override.resourceVersion === 0) || written.override.id === r.original.override.id), { current, written, outcome: r.outcome });
  // Empty scalar PUT removes only the profile when there was no override.
  // It preserves assets and uses the same owner version guard as ordinary PUT.
  if (r.restoreIntended) throw new h.Blocked('Unknown original restore: query owner command; do not replay a business write');
  r.restoreIntended = { ...scalar(r.original.override), expectedResourceId: current.override.id, expectedResourceVersion: current.override.resourceVersion };
  r.restoreRequestId = crypto.randomBytes(16).toString('hex'); h.persist();
  const restored = await h.api(h.admin, 'PUT', r.collection, r.restoreIntended, { 'Idempotency-Key': r.restoreRequestId });
  h.check('Conditional brand restore is acknowledged by owner', h.good(restored), restored);
  const after = await brandRead(h, r);
  h.check('Independent owner read proves original branding semantics and assets restored', same(semantics(after), semantics(r.original)), { original: r.original, after });
  r.restored = after; h.persist();
  return { restored: after, proof: 'Version-guarded scalar PUT and independent owner semantics; resource revision may advance' };
}
module.exports = { negativeBrandWrite, negativeCreate, cleanupNegativeMutation };
