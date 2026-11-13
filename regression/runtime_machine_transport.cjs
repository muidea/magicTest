// Read-only public machine port. Never borrow browser cookies or submit the
// original agent's receipt, signature, cursor or local persistent state.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const crypto = require('node:crypto');
const limit = 16 * 1024 * 1024;
function privateFile(filename, maxBytes) {
  const home = require('node:os').homedir();
  if (typeof filename !== 'string' || !path.isAbsolute(filename) || [path.join(home, 'codespace'), path.join(home, 'dataspace')].some(root => filename === root || filename.startsWith(root + path.sep))) throw Error('Runtime machine inputs require private files outside repositories');
  try {
    if (fs.realpathSync(filename) !== path.resolve(filename)) throw Error();
    const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    try {
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.uid !== process.getuid() || stat.mode & 0o077 || stat.size < 1 || stat.size > maxBytes) throw Error();
      const bytes = fs.readFileSync(fd);
      if (bytes.length > maxBytes) throw Error();
      return bytes;
    } finally { fs.closeSync(fd); }
  } catch { throw Error('Runtime machine private file is unavailable or has unsafe ownership, mode or size'); }
}
function loadConfig(filename) {
  let bytes, c;
  try { bytes = privateFile(filename, 8192); c = JSON.parse(bytes); } catch { throw Error('Runtime snapshot private configuration required'); }
  const keys = ['origin', 'instanceId', 'incarnation', 'endpointId', 'clientId', 'tokenFile'];
  if (!c || typeof c !== 'object' || Array.isArray(c) || Object.keys(c).length !== keys.length || keys.some(k => !Object.hasOwn(c, k)) ||
      !['instanceId', 'incarnation', 'clientId'].every(k => typeof c[k] === 'string' && /^[A-Za-z0-9._:-]{1,256}$/.test(c[k])) ||
      !Number.isSafeInteger(c.endpointId) || c.endpointId <= 0) throw Error('Exact runtime snapshot machine binding required');
  let url;
  try { url = new URL(c.origin); } catch { throw Error('Runtime machine origin required'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== c.origin || url.username || url.password) throw Error('Runtime machine origin must be a canonical operator-owned HTTP origin');
  const raw = privateFile(c.tokenFile, 65536).toString(), token = raw.trim();
  if (!/^[A-Za-z0-9._~+/-]+=*$/.test(token) || raw !== token && raw !== token + '\n') throw Error('Single original deployment-issued bearer required');
  return { ...c, token, configDigest: 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex') };
}
function getSnapshot(c, query = '') {
  if (!['', '?_pageSize=1', '?namespace=panel', '?instanceId=' + encodeURIComponent(c.instanceId)].includes(query)) throw Error('Only finite read-only snapshot probes are supported');
  const target = new URL('/api/v1/panel/runtime-execution/snapshot/' + query, c.origin), connect = new URL(target);
  if (connect.hostname.endsWith('.local.vpc')) connect.hostname = '127.0.0.1';
  return new Promise((resolve, reject) => {
    let timer;
    const fail = () => { clearTimeout(timer); reject(Error('Runtime machine GET failed; no retry, credential or owner response body in diagnostic')); };
    const request = (connect.protocol === 'https:' ? https : http).request(connect, { method: 'GET', agent: false, ...(connect.protocol === 'https:' ? { servername: target.hostname } : {}),
      headers: { Host: target.host, Accept: 'application/json', Authorization: 'Bearer ' + c.token } }, response => {
      if (response.statusCode >= 300 && response.statusCode < 400) { response.destroy(); fail(); return; }
      const chunks = []; let size = 0;
      response.on('data', chunk => { size += chunk.length; if (size > limit) { response.destroy(); request.destroy(); fail(); } else chunks.push(chunk); });
      response.on('error', fail);
      response.on('end', () => {
        if (size > limit) return fail();
        clearTimeout(timer);
        const bytes = Buffer.concat(chunks), text = bytes.toString();
        if ([text, response.headers['content-type'] || '', response.headers['cache-control'] || ''].some(v => v.includes(c.token))) return fail();
        let data;
        try { data = JSON.parse(text); } catch { data = null; }
        resolve({ status: response.statusCode, data, byteLength: bytes.length,
          sha256: 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex'),
          contentType: response.headers['content-type'] || '', cacheControl: response.headers['cache-control'] || '' });
      });
    });
    timer = setTimeout(() => { request.destroy(); fail(); }, 15000);
    request.once('error', fail); request.end();
  });
}
module.exports = { loadConfig, privateFile, getSnapshot, limit };
