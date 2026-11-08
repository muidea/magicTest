const { isDeepStrictEqual: same } = require('node:util');
const route = '/panel/namespace-branding/';
const rejectedAdmission = r => r?.status === 200 && r.data?.error?.code === 21 && r.data.error.message === '租户空间安装或删除操作正在进行，请稍后重试' && r.data.value == null;
async function resetBranding(h, actor, resource, pause = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const parent = h.state.resources.find(r => r.kind === 'namespace' && r.name === resource.name && r.phase !== 'deleted');
  if (resource.kind !== 'namespace-branding' || resource.collection !== route || resource.id !== '' || actor?.identity?.namespace !== resource.name || !parent?.creation?.ownershipConfirmed) throw new h.Blocked('Brand reset requires the original tracked tenant and actor');
  if (resource.brandingCommands?.some(command => command.outcome !== 'confirmed')) throw new h.Blocked('Original tenant branding command remains unresolved; no reset or parent deletion');
  if (resource.actorIdentity && (!same(resource.actorIdentity, actor.identity) || resource.origin !== actor.origin)) throw new h.Blocked('Brand reset requires exact original journal actor and origin');
  resource.brandingReset ||= { actorIdentity: structuredClone(actor.identity), origin: actor.origin, attempts: [] }; h.persist();
  const journal = resource.brandingReset;
  if (!same(actor.identity, journal.actorIdentity) || actor.origin !== journal.origin) throw new h.Blocked('Brand cleanup actor changed');
  for (let attempt = 0; attempt < 4; attempt++) {
    const before = (await h.ok(actor, 'GET', route)).value;
    h.check('Brand cleanup reads exact original tenant', before?.namespace === resource.name);
    if (before.override == null) return { proof: 'Independent original tenant read confirms no branding override', resetAttempts: journal.attempts };
    const last = journal.attempts.at(-1);
    if (last && !rejectedAdmission(last.response)) throw new h.Blocked('Original branding reset remains open; no replay without owner proof');
    const entry = { outcome: 'unknown' }; journal.attempts.push(entry); h.persist();
    const response = await h.api(actor, 'DELETE', route);
    entry.response = response; entry.outcome = h.good(response) ? 'acknowledged' : rejectedAdmission(response) ? 'rejected-before-admission' : 'unconfirmed'; h.persist();
    if (h.good(response)) {
      const after = (await h.ok(actor, 'GET', route)).value;
      h.check('Independent owner confirms original branding reset', after?.namespace === resource.name && after.override == null);
      return { proof: 'Journaled reset and independent original tenant absence', resetAttempts: journal.attempts };
    }
    if (!rejectedAdmission(response)) throw new h.Blocked('Brand reset result requires original owner reconciliation; no automatic retry');
    // This exact owner rejection precedes command creation. It is distinct
    // from transport loss, cancellation, generic code 21 or an unknown result.
    if (attempt < 3) await pause(1000);
  }
  throw new h.Blocked('Brand reset admission remained busy; original resource retained');
}
module.exports = { resetBranding, rejectedAdmission };
