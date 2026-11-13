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
async function restoreScopedCreator(h, pending) {
  const resources=pending.filter(r=>r.actor==='limitedTemplateManager' && r.phase!=='deleted');
  if(!resources.length)return;
  const reference=resources[0].creation;
  if(!reference || !resources.every(r=>r.collection==='/cas/namespaces/'+reference.actorIdentity.namespace+'/role-templates/' && same(r.creation?.actorIdentity,reference.actorIdentity) && r.creation.origin===reference.origin))throw new h.Blocked('Original limited creator identity is inconsistent');
  const accounts=h.state.resources.filter(r=>r.kind==='account' && r.phase!=='deleted' && r.creation?.ownershipConfirmed && r.collection==='/cas/namespaces/'+reference.actorIdentity.namespace+'/accounts/' && r.creation.intended.account===reference.actorIdentity.account);
  if(accounts.length!==1)throw new h.Blocked('Exact original limited creator account must remain available');
  const forms=h.state.originalCasForms || [], relevant=forms.filter(f=>same(f.actor,reference.actorIdentity) && f.origin===reference.origin);
  const form=relevant.findLast(f=>f.path==='/oauth/login' && f.phase==='browser-delivered' && f.status===302);
  if(!form || relevant.slice(relevant.indexOf(form)+1).some(f=>f.path==='/oauth/password/change'))throw new h.Blocked('Original successful creator login credential unavailable or changed');
  const fields=new URLSearchParams(Buffer.from(form.bodyBase64,'base64').toString());
  if(fields.getAll('password').length!==1 || !fields.get('password') || fields.get('account')!==reference.actorIdentity.account || fields.get('namespace')!==reference.actorIdentity.namespace)throw new h.Blocked('Original creator form identity is incomplete');
  const actor=await h.login(reference.actorIdentity.account,fields.get('password'),reference.actorIdentity.namespace);
  const session=(await h.ok(actor,'GET','/api/v1/web/session/')).value;
  if(!same(actor.identity,reference.actorIdentity) || actor.origin!==reference.origin || session.account?.id!==accounts[0].id || session.homeNamespace!==reference.actorIdentity.namespace)throw new h.Blocked('Restored creator differs from exact original owner');
  h.limitedTemplateManager=actor;
  h.observe({kind:'original-limited-creator-session',accountId:accounts[0].id,actor:reference.actorIdentity,origin:reference.origin,proof:'Exact owned account and private original successful form; independent session identity, no authority or resource command replay.'});
}
module.exports = { renewCleanupOwners, restoreScopedCreator };
