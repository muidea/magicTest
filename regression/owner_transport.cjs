// A single public HTTP request with the original browser's current cookies.
// The local Host map is the same one used by the regression browser; APIRequest
// has separate OS DNS and does not inherit Chromium host-resolver-rules.
const { request } = require('playwright');
const { isDeepStrictEqual: same } = require('node:util');
async function ownerExchange(actor, method, route, body, observe, mode = 'json') {
  if (!actor?.identity || !actor.context || !route.startsWith('/') || route.startsWith('//')) throw Error('Owner request requires original browser identity and same-origin route');
  const origin = actor.origin, identity = structuredClone(actor.identity);
  const endpoint = mode === 'public-file-download' || route.startsWith('/api/') ? route : '/api/v1/web/proxy' + route;
  const target = new URL(endpoint, origin);
  if (target.origin !== origin) throw Error('Owner route resolves outside original origin');
  const connect = new URL(target);
  if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
  const cookies = await actor.context.cookies(target.href);
  const cookieKey = c => c.name + '\n' + c.path;
  if (new Set(cookies.map(cookieKey)).size !== cookies.length) throw Error('Ambiguous owner cookies; no request sent');
  const mapped = cookies.map(c => ({ ...c, domain: connect.hostname }));
  const transport = await request.newContext({ ignoreHTTPSErrors: true, storageState: { cookies: mapped, origins: [] } });
  try {
    const response = await transport.fetch(connect.href, { method, headers: { Host: target.host, Origin: origin, ...(body === undefined || mode.endsWith('upload') ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : mode.endsWith('upload') ? { multipart: { file: { name: body.name, mimeType: 'application/octet-stream', buffer: body.bytes } } } : { data: body }), maxRedirects: 0, maxRetries: 0, timeout: 30000 });
    let data;
    if (mode.endsWith('download') && response.status() === 200 && response.headers()['content-type']?.startsWith('application/octet-stream')) data = { bytes: await response.body() };
    else { const text = await response.text(); try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; } }
    const result = { status: response.status(), data };
    observe({ kind: 'request', transport: 'public-owner-original-browser-cookies-one-shot', actor: identity, origin, method, route, ...(mode === 'json' ? { body, response: result } : { representation: mode, response: { status: result.status, ...(data.bytes ? { byteLength: data.bytes.length, digest: 'sha256:' + require('node:crypto').createHash('sha256').update(data.bytes).digest('hex') } : { data }) } }) });
    // BFF cookies are host-only. Copy only actual cookie changes back to the
    // exact original host, including deletion, without importing other actors.
    const after = (await transport.storageState()).cookies;
    if (!same(actor.identity, identity) || actor.origin !== origin) throw Error('Original owner actor changed during request');
    for (const original of cookies) {
      const next = after.find(c => cookieKey(c) === cookieKey(original));
      if (!next) await actor.context.clearCookies({ name: original.name, domain: original.domain, path: original.path });
    }
    for (const next of after) {
      const old = cookies.find(c => cookieKey(c) === cookieKey(next));
      const current = { ...next, domain: old?.domain || target.hostname };
      if (!old || !same(current, old)) await actor.context.addCookies([current]);
    }
    return result;
  } finally { await transport.dispose(); }
}
async function ownerRequest(actor, method, route, body, observe = () => {}) {
  return ownerExchange(actor, method, route, body, observe);
}
async function feedbackAttachment(actor, method, route, file, observe = () => {}) {
  const prefix = /^\/(portal|panel\/support)\/feedbacks\/[1-9][0-9]*\/attachments\//;
  const tail = route.replace(prefix, '');
  if (!prefix.test(route) || (method === 'POST' ? tail !== '' || !file || !Buffer.isBuffer(file.bytes) || file.bytes.length < 1 || file.bytes.length > 10 * 1024 * 1024 || typeof file.name !== 'string' || !file.name.trim() || /[\\/\x00-\x1f]/.test(file.name) : method !== 'GET' || !/^bound_[A-Za-z0-9_-]{32,64}$/.test(tail) || file !== undefined)) throw Error('Exact feedback attachment operation required');
  return ownerExchange(actor, method, route, file, observe, method === 'POST' ? 'attachment-upload' : 'attachment-download');
}
async function fileTransfer(actor, method, route, file, observe = () => {}) {
  const url = new URL(route, actor.origin), upload = method === 'POST';
  if (url.origin !== actor.origin || !route.startsWith('/') || route.startsWith('//') || url.hash) throw Error('Original file operation must be same-origin');
  const publicRead = method === 'GET' && /^\/static\/share\//.test(url.pathname);
  const protectedRead = method === 'GET' && (/^\/files\/self\/files\/download\/$/.test(url.pathname) || /^\/files\/static\/(private|share)\//.test(url.pathname));
  if (upload ? !['/files/upload/', '/files/self/files/upload/'].includes(url.pathname) || !file || !Buffer.isBuffer(file.bytes) || file.bytes.length > 10 * 1024 * 1024 || !/^[A-Za-z0-9_.-]+$/.test(file.name) || url.searchParams.get('key-name') !== 'file' : (!publicRead && !protectedRead) || file !== undefined) throw Error('Exact finite ordinary-file transfer required');
  if (publicRead && (await actor.context.cookies(actor.origin)).length) throw Error('Public file proof requires an independent context without cookies');
  return ownerExchange(actor, method, route, file, observe, upload ? 'file-upload' : publicRead ? 'public-file-download' : 'file-download');
}
async function brandingAsset(actor, route, file, observe = () => {}) {
  if (route !== '/panel/namespace-branding/assets/brand-icon' || !file || !Buffer.isBuffer(file.bytes) || file.bytes.length < 1 || file.bytes.length > 1024 * 1024 || typeof file.name !== 'string' || !/^[A-Za-z0-9_.-]+\.png$/.test(file.name)) throw Error('Exact finite tenant brand-icon upload required');
  return ownerExchange(actor, 'POST', route, file, observe, 'branding-upload');
}
module.exports = { ownerRequest, feedbackAttachment, fileTransfer, brandingAsset };
