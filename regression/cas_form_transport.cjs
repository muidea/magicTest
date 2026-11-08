// Transport only the browser's original CAS form. No synthesized command or retry.
const { isDeepStrictEqual: same } = require('node:util');
async function withOriginalCasForms(actor, { journal, persist, record = () => {} }, action) {
  const { page, origin } = actor, identity = structuredClone(actor.identity);
  const targetOrigin = new URL(origin);
  if (targetOrigin.origin !== origin || !identity?.account || !identity.namespace || !Array.isArray(journal)) throw Error('Original CAS form identity is required');
  const seen = new Set(), allowed = ['/oauth/login', '/oauth/password/change'];
  const match = url => url.pathname.startsWith('/oauth/');
  let failure;
  const route = async r => {
    const req = r.request(), url = new URL(req.url());
    if (req.method() !== 'POST') return r.continue();
    let intent;
    try {
      if (actor.origin !== origin || !same(actor.identity, identity) || url.origin !== origin || !allowed.includes(url.pathname) || url.search || !req.isNavigationRequest() || req.frame() !== page.mainFrame()) throw Error('Refused non-original CAS form');
      const headers = await req.allHeaders(), body = req.postDataBuffer();
      if (!body || !headers['content-type']?.startsWith('application/x-www-form-urlencoded') || headers.origin !== origin) throw Error('Refused non-form CAS command');
      const fields = new URLSearchParams(body.toString('utf8'));
      for (const key of ['namespace', 'transaction', 'csrf_token', 'password']) if (fields.getAll(key).length !== 1 || !fields.get(key)) throw Error('Refused incomplete CAS form');
      if (fields.get('namespace') !== identity.namespace || (url.pathname === '/oauth/login' && (fields.getAll('account').length !== 1 || fields.get('account') !== identity.account))) throw Error('Refused different CAS form identity');
      if (seen.has(url.pathname)) throw Error('Refused duplicate original CAS command');
      seen.add(url.pathname);
      // This journal contains credentials and is exclusively private runtime state.
      intent = { kind: 'original-cas-form', actor: identity, origin, path: url.pathname, method: 'POST', bodyBase64: body.toString('base64'), headers, phase: 'sending' };
      journal.push(intent); persist();
      if (actor.origin !== origin || !same(actor.identity, identity)) throw Error('Original CAS actor changed before dispatch');
      const connect = new URL(url);
      if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
      const response = await r.fetch({ url: connect.href, method: 'POST', headers: { ...headers, host: url.host }, postData: body, maxRedirects: 0, maxRetries: 0, timeout: 30000 });
      intent.status = response.status(); intent.phase = 'response-received'; persist();
      await r.fulfill({ response });
      intent.phase = 'browser-delivered'; persist();
      record({ kind: 'original-cas-form-transport', origin, path: url.pathname, method: 'POST', status: response.status(), outcome: 'browser-delivered' });
    } catch (error) {
      failure ||= error;
      if (intent) { intent.phase = intent.status ? 'response-not-delivered' : 'unknown'; try { persist(); } catch {} }
      record({ kind: 'original-cas-form-transport', origin, path: url.pathname, method: 'POST', outcome: intent ? intent.phase : 'refused' });
      await r.abort('failed').catch(() => {});
    }
  };
  record({ kind: 'cas-form-transport-selection', origin, paths: allowed, mode: 'original-browser-form-one-shot', selectedBeforeAction: true });
  await page.route(match, route);
  try {
    const result = await action();
    if (failure) throw failure;
    return result;
  } catch (error) { throw failure || error; }
  finally { await page.unroute(match, route); }
}
module.exports = { withOriginalCasForms };
