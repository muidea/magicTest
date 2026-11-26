const { test } = require('node:test');
const assert = require('node:assert/strict');
const { resolveMaxUploadBytes } = require('./file_boundary_cases.cjs');

test('resolveMaxUploadBytes auto-discovers limit from magicFile limits endpoint when config omits it', async () => {
  const h = {
    user: { name: 'user' },
    Blocked: class Blocked extends Error {},
    good: (res) => res && res.status === 200 && res.data?.error == null,
    async api(_actor, method, route) {
      assert.equal(method, 'GET');
      assert.equal(route, '/files/self/files/limits/');
      return { status: 200, data: { value: { maxUploadBytes: 64 * 1024 * 1024, maxUploadReferenceBytes: 512 * 1024 * 1024 }, error: null } };
    },
  };
  const resolved = await resolveMaxUploadBytes(h);
  assert.equal(resolved.limit, 64 * 1024 * 1024);
  assert.match(resolved.basis, /Authoritative GET \/files\/self\/files\/limits\//);
});

test('resolveMaxUploadBytes rejects mismatch between configured fileUploadMaxBytes and deployment endpoint', async () => {
  const h = {
    user: { name: 'user' },
    fileUploadMaxBytes: 32 * 1024 * 1024,
    Blocked: class Blocked extends Error {},
    good: (res) => res && res.status === 200 && res.data?.error == null,
    async api() {
      return { status: 200, data: { value: { maxUploadBytes: 64 * 1024 * 1024 }, error: null } };
    },
  };
  await assert.rejects(resolveMaxUploadBytes(h), (err) => err instanceof h.Blocked && /disagrees/.test(err.message));
});

test('resolveMaxUploadBytes fails closed when both endpoint and config are unavailable', async () => {
  const h = {
    user: { name: 'user' },
    Blocked: class Blocked extends Error {},
    good: () => false,
    async api() {
      return { status: 404, data: {} };
    },
  };
  await assert.rejects(resolveMaxUploadBytes(h), (err) => err instanceof h.Blocked);
});
