const { test } = require('node:test');
const assert = require('node:assert/strict');
const { exactSource } = require('./page_refresh_cases.cjs');
test('delayed page traffic can only target exact original same-origin frozen read plan', () => {
  const origin = 'https://panel.local.vpc', context = { applicationKey: 'original', identity: { deploymentId: 'original-installation' } };
  const value = { method: 'POST', url: origin + '/api/v1/web/proxy/apps/page/sources/?application=original&deploymentId=original-installation', body: { sourceKey: 'records' } };
  const request = v => ({ method: () => v.method, url: () => v.url, postDataJSON: () => v.body });
  assert.equal(exactSource(request(value), origin, context), true);
  for (const patch of [{ method: 'GET' }, { url: value.url.replace('panel.local.vpc', 'peer.local.vpc') }, { url: value.url.replace('original-installation', 'peer-installation') },
    { url: value.url.replace('application=original', 'application=peer') }, { url: value.url + '&deploymentId=original-installation' }, { url: value.url + '&application=original' },
    { url: value.url.replace('/page/sources/', '/entity/value/write/update/execute/') }, { body: { sourceKey: 'peer' } }, { body: null }]) assert.equal(exactSource(request({ ...value, ...patch }), origin, context), false);
  assert.equal(exactSource({ ...request(value), postDataJSON: () => { throw Error('Not JSON'); } }, origin, context), false);
});
