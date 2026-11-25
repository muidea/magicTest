const { test } = require('node:test');
const assert = require('node:assert/strict');
const { baseDomainFromOrigin, resolveConnectHost, browserHostResolverArgs } = require('./remote_target.cjs');

test('baseDomainFromOrigin strips first subdomain label only when >2 labels', () => {
  assert.equal(baseDomainFromOrigin('https://panel.example.com'), 'example.com');
  assert.equal(baseDomainFromOrigin('https://panel.local.vpc'), 'local.vpc');
  assert.equal(baseDomainFromOrigin('https://example.com'), 'example.com');
  assert.equal(baseDomainFromOrigin('https://panel.qa.internal.corp:8443'), 'qa.internal.corp');
});

test('resolveConnectHost preserves local.vpc default and honors remote targetAddress', () => {
  assert.equal(resolveConnectHost('panel.local.vpc', {}), '127.0.0.1');
  assert.equal(resolveConnectHost('tenant-a.local.vpc', {}), '127.0.0.1');
  assert.equal(resolveConnectHost('panel.example.com', {}), 'panel.example.com');

  const env = { MAGICTEST_TARGET_ADDRESS: '10.20.30.40', MAGICTEST_BASE_DOMAIN: 'example.com' };
  assert.equal(resolveConnectHost('panel.example.com', env), '10.20.30.40');
  assert.equal(resolveConnectHost('rg1234a.example.com', env), '10.20.30.40');
  assert.equal(resolveConnectHost('example.com', env), '10.20.30.40');
  assert.equal(resolveConnectHost('unrelated.other.net', env), 'unrelated.other.net');
});

test('browserHostResolverArgs emits remote MAP rules when targetAddress is set', () => {
  assert.deepEqual(
    browserHostResolverArgs('https://panel.local.vpc', ''),
    ['--host-resolver-rules=MAP *.local.vpc 127.0.0.1'],
  );
  assert.deepEqual(
    browserHostResolverArgs('https://panel.example.com:8443', '10.20.30.40'),
    ['--host-resolver-rules=MAP *.example.com 10.20.30.40,MAP example.com 10.20.30.40'],
  );
});
