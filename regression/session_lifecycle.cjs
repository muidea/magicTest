// Stop completed UI surfaces from polling throughout a long regression run.
// Keep each original browser context, credentials and identity for later reads.
const { isDeepStrictEqual: same } = require('node:util');
async function readyActor(h, name, readSession) {
  const original = h[name], identity = structuredClone(original.identity), origin = original.origin;
  let actor=original, response=await readSession(actor,'GET','/api/v1/web/session/');
  if(response.status===401 || response.status===200 && response.data?.error?.code===11) {
    if(!actor.password)throw new h.Blocked('Original case actor credential unavailable: '+name);
    actor=await h.login(identity.account,actor.password,identity.namespace);
    if(!same(actor.identity,identity) || actor.origin!==origin)throw new h.Blocked('Original case actor changed during authentication: '+name);
    h[name]=actor;
    h.observe({kind:'case-boundary-reauthentication',actor:identity,origin,scope:'Same original account before case entry; no resource command replay.'});
    response=await readSession(actor,'GET','/api/v1/web/session/');
  }
  if(!h.good(response) || !same(actor.identity,identity) || actor.origin!==origin || response.data.value?.account?.account!==identity.account || response.data.value.homeNamespace!==identity.namespace) throw new h.Blocked('AUTH-INVALID: original actor session is unavailable: '+name);
  return actor;
}
async function parkSessions(sessions, observe = () => {}) {
  const results = [];
  for (const actor of sessions) {
    if (actor.page.isClosed()) continue;
    const current = new URL(actor.page.url());
    if (current.origin !== actor.origin || !/^\/(panel|portal|workbench)(\/|$)/.test(current.pathname)) continue;
    try {
      const response = await actor.page.goto(actor.origin + '/api/v1/web/session/', { waitUntil: 'domcontentloaded', timeout: 10000 });
      results.push({ actor: actor.identity, from: current.pathname, status: response?.status(), parked: new URL(actor.page.url()).origin === actor.origin && new URL(actor.page.url()).pathname === '/api/v1/web/session/' });
    } catch (error) {
      // Housekeeping cannot replace the case outcome or prove an owner result.
      results.push({ actor: actor.identity, from: current.pathname, parked: false, error: error.name });
    }
  }
  if (results.length) observe({ kind: 'completed-browser-surfaces', results });
  return results;
}
module.exports = { parkSessions, readyActor };
