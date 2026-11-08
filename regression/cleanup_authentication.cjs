const { isDeepStrictEqual: same } = require('node:util');
async function renewCleanupOwners(h, resource, readSession) {
  const specs = resource.kind === 'ordinary-file' ? [{ actorName: resource.actorName, identity: resource.actorIdentity, origin: resource.origin }] : resource.kind === 'feedback-ticket' ? [resource.creator, resource.manager] : resource.kind.startsWith('cas-probe-') ? [{ actorName: resource.actor, identity: resource.actorIdentity, origin: resource.origin }] : [];
  for (const spec of specs) {
    if (!spec || !['admin', 'user', 'tenantAdmin', 'otherTenantAdmin'].includes(spec.actorName)) throw new h.Blocked('Named cleanup owner is not an original supported actor');
    let actor = h[spec.actorName];
    if (!same(actor?.identity, spec.identity) || actor.origin !== spec.origin) throw new h.Blocked('Named cleanup actor or origin differs from original journal');
    let response = await readSession(actor, 'GET', '/api/v1/web/session/');
    if (response.status === 401 || response.status === 200 && response.data?.error?.code === 11) {
      if (typeof actor.password !== 'string' || !actor.password) throw new h.Blocked('Original cleanup credential unavailable; no replacement actor');
      h.observe({ kind: 'cleanup-owner-reauthentication', actor: structuredClone(spec.identity), origin: spec.origin, scope: 'Original browser session only; no business command is replayed' });
      const fresh = await h.login(actor.identity.account, actor.password, actor.identity.namespace);
      if (!same(fresh?.identity, spec.identity) || fresh.origin !== spec.origin) throw new h.Blocked('Reauthenticated cleanup owner differs from original journal');
      h[spec.actorName] = fresh; actor = fresh;
      response = await readSession(actor, 'GET', '/api/v1/web/session/');
    }
    if (!h.good(response) || response.data.value?.homeNamespace !== spec.identity.namespace || response.data.value?.account?.account !== spec.identity.account) throw new h.Blocked('Original cleanup session unavailable or belongs to another subject; no business replay');
  }
}
module.exports = { renewCleanupOwners };
