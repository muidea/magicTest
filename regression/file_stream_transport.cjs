// Finite ordinary self-file transfers. Streaming avoids buffering the product
// content limit in Playwright/Chromium; no redirects, retries or guessed IDs.
const crypto = require('node:crypto');
const http = require('node:http');
const https = require('node:https');
const { once } = require('node:events');
const { isDeepStrictEqual: same } = require('node:util');
const budget = 1024 * 1024 * 1024 + 1;
const block = Buffer.alloc(64 * 1024);
for (let i = 0; i < block.length; i++) block[i] = i % 251;
function* chunks(size) {
  if (!Number.isSafeInteger(size) || size < 0 || size > budget) throw Error('Finite self-file content budget required');
  for (let offset = 0; offset < size; offset += block.length) yield block.subarray(0, Math.min(block.length, size - offset));
}
function digest(size) {
  const hash = crypto.createHash('sha256'); for (const chunk of chunks(size)) hash.update(chunk);
  return 'sha256:' + hash.digest('hex');
}
function multipart(size, name) {
  if (!/^[A-Za-z0-9_.-]+$/.test(name)) throw Error('Finite original filename required');
  // Validate before opening a connection, including the zero-byte case.
  chunks(size).next();
  const boundary = 'regression-' + crypto.randomBytes(24).toString('hex');
  const head = Buffer.from('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="' + name + '"\r\nContent-Type: application/octet-stream\r\n\r\n');
  const tail = Buffer.from('\r\n--' + boundary + '--\r\n');
  return { boundary, length: head.length + size + tail.length, *[Symbol.iterator]() { yield head; yield* chunks(size); yield tail; } };
}
async function mirrorCookies(actor, target, values) {
  for (const value of values || []) {
    const parts = value.split(';').map(s => s.trim()), equal = parts[0].indexOf('=');
    if (equal < 1) throw Error('Malformed original response cookie');
    const cookie = { name: parts[0].slice(0, equal), value: parts[0].slice(equal + 1), domain: target.hostname, path: '/' };
    let maxAge;
    for (const part of parts.slice(1)) {
      const [key, ...rest] = part.split('='), val = rest.join('=');
      switch (key.toLowerCase()) {
        case 'domain': if (val.replace(/^\./, '').toLowerCase() !== target.hostname.toLowerCase()) throw Error('Response cookie escaped original host'); break;
        case 'path': cookie.path = val; break;
        case 'secure': cookie.secure = true; break;
        case 'httponly': cookie.httpOnly = true; break;
        case 'samesite': cookie.sameSite = ({ lax: 'Lax', strict: 'Strict', none: 'None' })[val.toLowerCase()]; break;
        case 'max-age': maxAge = Number(val); break;
        case 'expires': cookie.expires = Date.parse(val) / 1000; break;
      }
    }
    if (maxAge !== undefined) cookie.expires = Date.now() / 1000 + maxAge;
    if (cookie.expires !== undefined && cookie.expires <= Date.now() / 1000) await actor.context.clearCookies({ name: cookie.name, domain: cookie.domain, path: cookie.path });
    else await actor.context.addCookies([cookie]);
  }
}
async function transfer(actor, method, route, file, observe = () => {}) {
  if (!actor?.identity || !actor.context || !route.startsWith('/') || route.startsWith('//')) throw Error('Original self-file actor and route required');
  const target = new URL(route, actor.origin), identity = structuredClone(actor.identity), origin = actor.origin;
  if (target.origin !== origin || target.hash || !['http:', 'https:'].includes(target.protocol)) throw Error('Self-file transfer escaped original origin');
  const upload = method === 'POST';
  if (upload ? target.pathname !== '/files/self/files/upload/' || target.searchParams.get('key-name') !== 'file' || !file : method !== 'GET' || target.pathname !== '/files/self/files/download/' || file !== undefined) throw Error('Exact finite self-file operation required');
  const body = upload ? multipart(file.size, file.name) : undefined;
  const endpoint = '/api/v1/web/proxy' + target.pathname + target.search;
  const cookies = await actor.context.cookies(new URL(endpoint, origin).href);
  if (new Set(cookies.map(c => c.name + '\n' + c.path)).size !== cookies.length) throw Error('Ambiguous original self-file cookies');
  const headers = { Host: target.host, Origin: origin, ...(cookies.length ? { Cookie: cookies.map(c => c.name + '=' + c.value).join('; ') } : {}) };
  if (body) Object.assign(headers, { 'Content-Type': 'multipart/form-data; boundary=' + body.boundary, 'Content-Length': String(body.length) });
  let timer, request, response, requestError, sent = 0;
  const completed = new Promise((resolve, reject) => {
    request = (target.protocol === 'https:' ? https : http).request({ protocol: target.protocol, hostname: target.hostname.endsWith('.local.vpc') ? '127.0.0.1' : target.hostname,
      port: target.port || undefined, servername: target.hostname, path: endpoint, method, headers, rejectUnauthorized: false, agent: false }, resolve);
    request.on('error', error => { requestError = error; reject(error); });
    timer = setTimeout(() => request.destroy(Error('Original finite file transfer exceeded 180 seconds; outcome unknown, never retry')), 180000);
  });
  // The response can arrive while writing a rejected body. Stop writing then;
  // an actual HTTP response is distinct from a transport-unknown outcome.
  completed.then(r => { response = r; }, () => {});
  const send = (async () => {
    try {
      if (body) for (const chunk of body) {
        if (response || requestError) break;
        if (!request.write(chunk)) await Promise.race([once(request, 'drain'), completed]);
        sent += chunk.length;
      }
      if (!request.destroyed) request.end();
    } catch (error) { if (!response) request.destroy(error); }
  })();
  try {
    const incoming = await completed;
    const binary = !upload && incoming.statusCode === 200 && incoming.headers['content-type']?.startsWith('application/octet-stream');
    let size = 0, payload = [], hash = crypto.createHash('sha256');
    for await (const chunk of incoming) {
      size += chunk.length;
      if (binary) { if (size > budget) throw Error('Original file response exceeds finite read budget'); hash.update(chunk); }
      else { if (size > 1024 * 1024) throw Error('Original file JSON response exceeds evidence budget'); payload.push(chunk); }
    }
    let data;
    if (binary) data = { byteLength: size, digest: 'sha256:' + hash.digest('hex') };
    else { const text = Buffer.concat(payload).toString(); try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; } }
    if (actor.origin !== origin || !same(actor.identity, identity)) throw Error('Original self-file actor changed during transfer');
    await mirrorCookies(actor, target, incoming.headers['set-cookie']);
    const result = { status: incoming.statusCode, data };
    observe({ kind: 'request', transport: 'finite-stream-original-browser-cookies-one-shot', actor: identity, origin, method, route,
      ...(body ? { contentBytes: file.size, multipartBytes: body.length, sentBytes: sent } : {}), response: result });
    return result;
  } finally { clearTimeout(timer); request.destroy(); await send; }
}
module.exports = { transfer, digest, multipart, budget };
