// Conditional commands on an acknowledged current-run installation. A lost
// reply stays unknown: observing a disabled instance alone cannot prove who
// changed it, so teardown and automatic replay remain forbidden.
const { isDeepStrictEqual: same } = require('node:util');
const { installationUnchanged } = require('./deployment_review_cases.cjs');
const base = '/panel/application/installations/';
function immutable(value) {
  return Object.fromEntries(['id', 'namespace', 'deploymentId', 'applicationUuid', 'applicationKey', 'sourceDigest', 'runtimeType', 'instanceKey'].map(k => [k, value[k]]));
}
function confirms(h, before, command, after) {
  const ack = command.response?.data?.value;
  const state = command.action === 'disable' ? 'disabled' : 'ready';
  // Action responses omit the computed deploymentVersion projection.
  const projected = v => Object.fromEntries(Object.entries(v).filter(([k]) => k !== 'deploymentVersion'));
  return h.good(command.response) && ack && same(projected(ack), projected(after)) && same(immutable(before), immutable(after)) &&
    same(after.receipt?.database, before.receipt?.database) && after.receipt?.runtimeApplicationUuid === before.receipt?.runtimeApplicationUuid &&
    after.status === state && after.reason === command.body.reason && after.updateTime > before.updateTime &&
    // The public DTO omits zero int64 timestamps. A retained nonzero (or an
    // explicit null/wrong type) still cannot prove activation cleared it.
    (state === 'disabled' ? after.disabledAt > 0 : after.activatedAt > 0 &&
      (!Object.hasOwn(after, 'disabledAt') || after.disabledAt === 0));
}
async function control(h, resource, action) {
  if (resource.scenarioCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original lifecycle command unresolved; no replay');
  if (!['disable', 'activate'].includes(action) || !resource.creation?.ownershipConfirmed || resource.creation.origin !== h.admin.origin ||
      !same(resource.creation.actorIdentity, h.admin.identity) || resource.commands?.some(c => c.outcome === 'unknown') || !resource.installation)
    throw new h.Blocked('Exact acknowledged original installation and actor required before lifecycle command');
  const before = (await h.ok(h.admin, 'GET', base + resource.installation.id)).value;
  if (!installationUnchanged(resource.installation, before) || before.status !== (action === 'disable' ? 'ready' : 'disabled'))
    throw new h.Blocked('Original installation changed or has wrong lifecycle state; no replacement command');
  const c = { action, method: 'POST', route: base + before.id + '/' + action, body: { expectedDigest: before.sourceDigest,
    expectedUpdateTime: before.updateTime, reason: 'Current-run original installation ' + action }, before,
    actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, outcome: 'unknown' };
  (resource.scenarioCommands ||= []).push(c); h.persist();
  try { c.response = await h.api(h.admin, 'POST', c.route, c.body); }
  catch (error) { c.transportError = error.message; }
  h.persist();
  c.after = (await h.ok(h.admin, 'GET', base + before.id)).value; h.persist();
  if (h.admin.origin === c.origin && same(h.admin.identity, c.actorIdentity) && confirms(h, before, c, c.after)) {
    c.outcome = 'confirmed'; resource.installation = c.after; h.persist();
  }
  h.check('Exact original conditional ' + action + ' receipt and independent owner preserve runtime/storage identities', c.outcome === 'confirmed', c);
  return c.after;
}
module.exports = { control, confirms, immutable };
