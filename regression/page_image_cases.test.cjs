const { test } = require('node:test');
const assert = require('node:assert/strict');
const { assetRead, assetMatches, deniedAssetMatches, archiveMatches } = require('./page_image_cases.cjs');
const asset = { key: 'image', path: 'assets/image.png', purpose: 'page-image', mime: 'image/png', size: 68, digest: 'sha256:' + 'a'.repeat(64) };
test('image success requires actual bytes, media and private response headers', () => {
  const value = { status: 200, mime: asset.mime, size: asset.size, digest: asset.digest, cache: 'private, no-store', nosniff: 'nosniff' };
  assert.equal(assetMatches(value, asset), true);
  for (const patch of [{ status: 401 }, { mime: 'image/jpeg' }, { size: 0 }, { digest: 'sha256:' + 'b'.repeat(64) }, { cache: 'public' }, { nosniff: null }, { error: { code: 5 } }]) assert.equal(assetMatches({ ...value, ...patch }, asset), false);
});
test('image denial must reach the exact owner fence without accepting authentication or binary responses', () => {
  const value = { status: 409, mime: 'application/json', error: { code: 19, message: '精确安装读取身份已变化' }, value: null, cache: 'private, no-store', nosniff: 'nosniff' };
  assert.equal(deniedAssetMatches(value, 19, value.error.message), true);
  for (const patch of [{ status: 401 }, { status: 503 }, { mime: 'image/png' }, { error: { code: 5, message: value.error.message } }, { error: { code: 19, message: 'earlier gate' } }, { value: { bytes: 'private' } }, { cache: 'public' }]) assert.equal(deniedAssetMatches({ ...value, ...patch }, 19, value.error.message), false);
});
test('frozen image ZIP binds exact application, real file bytes, index and independent checksum', () => {
  const application = { uuid: 'original-application', name: 'original-key' };
  const file = { path: asset.path, size: asset.size, digest: asset.digest };
  const value = { crcValid: true, names: ['package.json', 'assets/index.json', asset.path, 'checksums.json'],
    manifest: { apiVersion: 'magic.model-package/v1', application: { uuid: application.uuid, key: application.name }, content: { assets: 'assets/index.json' } },
    assets: { schemaVersion: 'magic.application-assets/v1', files: [asset] }, files: [file], checksums: { files: [file] } };
  assert.equal(archiveMatches(value, application, [asset]), true);
  for (const change of [v => { v.crcValid = false; }, v => v.names.push(asset.path), v => { v.manifest.application.uuid = 'peer'; },
    v => { v.assets.files[0].purpose = 'icon'; }, v => { v.assets.files[0].digest = 'wrong'; }, v => v.files.pop(),
    v => { v.files[0].size++; }, v => { v.checksums.files[0].digest = 'wrong'; }, v => v.checksums.files.push(v.checksums.files[0])]) {
    const changed = structuredClone(value); change(changed); assert.equal(archiveMatches(changed, application, [asset]), false);
  }
});
test('independent image read uses the registered normalized public route and original installation header', async () => {
  const actor = { identity: { account: 'original', namespace: 'panel' }, origin: 'https://panel.local.vpc', context: {}, page: {
    url: () => 'https://panel.local.vpc/portal/',
    evaluate: async (_, request) => {
      assert.equal(request.route, '/api/v1/web/proxy/apps/application/assets/original%20image?application=original&deploymentId=original-installation');
      assert.deepEqual(JSON.parse(Buffer.from(request.header, 'base64url')), context.identity);
      return { status: 200, mime: asset.mime, size: asset.size, digest: asset.digest, cache: 'private, no-store', nosniff: 'nosniff' };
    },
  } };
  const context = { applicationKey: 'original', identity: { deploymentId: 'original-installation' } };
  const h = { check: (_, valid) => assert.equal(valid, true), observe: () => {}, Blocked: Error };
  assert.equal(assetMatches(await assetRead(h, actor, context, 'original image'), asset), true);
  actor.page.url = () => 'https://peer.local.vpc/';
  await assert.rejects(assetRead(h, actor, context, 'original image'), /exact origin/);
});
