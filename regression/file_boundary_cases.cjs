const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { transfer, digest, budget } = require('./file_stream_transport.cjs');
const { cleanup } = require('./file_cases.cjs');
const self = '/files/self/files/';
async function createSizedFile(h, size, suffix) {
  const actor = h.user, relative = h.state.prefix + '/boundary-' + suffix + '-' + crypto.randomBytes(8).toString('hex');
  const name = 'boundary-' + suffix + '.bin', uploadRoute = self + 'upload/?' + new URLSearchParams({ 'key-name': 'file', filePath: relative });
  const r = { kind: 'ordinary-file', phase: 'intent', actorName: 'user', actorIdentity: structuredClone(actor.identity), origin: actor.origin,
    visibility: 'self', base: self, relative, name, expectedSize: size, expectedDigest: digest(size), uploadRoute, creation: { outcome: 'unknown' } };
  const before = await h.directory(actor, self);
  h.check('Original upload name is absent before its single dispatch', !before.some(row => row.name === name || row.path?.includes('/' + relative + '/')));
  h.state.resources.push(r); h.persist();
  r.creation.response = await transfer(actor, 'POST', uploadRoute, { name, size }, h.observe); h.persist();
  const response = r.creation.response;
  if (!h.good(response)) {
    const after = await h.directory(actor, self);
    h.check('Rejected original upload preserves complete original owner directory and has no token', !response.data?.value?.token && same(after, before), { status: response.status, error: response.data?.error, beforeIDs: before.map(x => x.id), afterIDs: after.map(x => x.id) });
    // A transport/authorization failure never proves the content limit.
    const rejected = [200, 400, 413, 422].includes(response.status) && response.data?.error?.code === 4 && /(?:upload|file|empty|size|limit)/i.test(response.data.error.message);
    if (rejected) { r.creation.outcome = 'rejected-and-owner-directory-unchanged'; r.phase = 'deleted'; h.persist(); }
    h.check('Upload rejection reaches explicit File content validation', rejected, response);
    return { r, accepted: false };
  }
  r.token = response.data.value?.token;
  h.persist();
  h.check('Original content upload returns exact filename and a nonempty opaque token', response.data.value?.name === name && typeof r.token === 'string' && !!r.token, response);
  r.view = self + 'view/?' + new URLSearchParams({ fileToken: r.token }); h.persist();
  const view = (await h.ok(actor, 'GET', r.view)).value;
  if (Number.isSafeInteger(view?.id) && view.id > 0) { r.id = view.id; r.path = view.path; }
  h.persist();
  h.check('Independent token read binds exact original self file to safe ID and private original path', r.id > 0 && view.token === r.token && view.name === name && typeof r.path === 'string' && r.path.startsWith('/static/private/self-') && r.path.includes('/' + relative + '/') && r.path.endsWith('/' + name) && !r.path.includes('..'), view);
  h.check('Independent exact File ID equals original token view', same((await h.ok(actor, 'GET', self + r.id)).value, view));
  r.download = self + 'download/?' + new URLSearchParams({ fileToken: r.token });
  r.creation.outcome = 'confirmed'; r.phase = 'created'; h.persist();
  const bytes = await transfer(actor, 'GET', r.download, undefined, h.observe);
  h.check('Independent streamed original file has exact intended content length and digest', bytes.status === 200 && bytes.data.byteLength === size && bytes.data.digest === r.expectedDigest, bytes);
  const rows = await h.directory(actor, self);
  h.check('Complete owner directory has exactly one original token/ID and no duplicate path', rows.filter(row => row.id === r.id || row.token === r.token || row.path === r.path).length === 1 && rows.some(row => row.id === r.id && row.token === r.token && row.name === name));
  r.creation.outcome = 'confirmed'; r.phase = 'created'; h.persist();
  return { r, accepted: true };
}
async function boundaries(h) {
  const limit = h.fileUploadMaxBytes;
  if (!Number.isSafeInteger(limit) || limit < 1 || limit >= budget) throw new h.Blocked('F049-003 needs the actual deployment uploads.maxBytes (configuration or evidenced source default) as fileUploadMaxBytes; never substitute the old 10 MiB tool buffer');
  h.observe({ kind: 'ordinary-file-content-limit', bytes: limit, basis: 'Explicit deployment input; exact L/L+1 behavior must agree before acceptance', specialNotExecuted: 'Interruptions before/after admission require isolated controlled-fault owner' });
  const outcomes = [];
  // Retire each accepted original before dispatching the next large upload.
  // Empty uploads may be valid or explicitly rejected by the current owner.
  for (const [suffix, size] of [['empty', 0], ['below', limit - 1], ['limit', limit], ['above', limit + 1]]) {
    const result = await createSizedFile(h, size, suffix);
    if (result.accepted) await cleanup(h, result.r);
    outcomes.push({ suffix, size, accepted: result.accepted, disposed: result.r.phase === 'deleted' });
  }
  h.check('Exact actual content boundary accepts L-1/L, rejects L+1, and retires every original upload', outcomes.every(x => x.disposed) && outcomes.filter(x => ['below', 'limit'].includes(x.suffix)).every(x => x.accepted) && outcomes.find(x => x.suffix === 'above').accepted === false, outcomes);
}
boundaries.actors = ['user']; boundaries.transport = 'owner-api';
module.exports = { handlers: { 'F049-003': boundaries }, createSizedFile };
