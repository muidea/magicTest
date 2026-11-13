// Preserve numeric application error codes while redacting OAuth credential strings.
function sanitize(value, key = '') {
  if (typeof value === 'string' && /^(?:code|state|nonce|transaction)$/.test(key)) return '[REDACTED]';
  if (/password|secret|token|csrf|authorization|cookie|api_?key|upload_?ref|code_verifier|code_challenge/i.test(key)) return '[REDACTED]';
  if (Array.isArray(value)) return value.map(x => sanitize(x));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, sanitize(v, k)]));
  if (typeof value === 'string') return value.replace(/\x1b\[[0-9;]*m/g, '').replace(/((?:set-cookie|cookie|authorization)\s*:\s*)[^\r\n]*/gi, '$1[REDACTED]').replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[REDACTED-JWT]').replace(/([?&](?:code|state|nonce|transaction|fileToken)=)[^&\s"']+/gi, '$1[REDACTED]').replace(/(\bname:token,value:)[a-f0-9]{64}\b/gi, '$1[REDACTED-FILE-TOKEN]');
  return value;
}
module.exports = { sanitize };
