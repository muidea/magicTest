const { test } = require('node:test');
const assert = require('node:assert/strict');
const profiles = require('./platform_profiles.cjs');

const REMOVED_COARSE_KEYS = [
  'platform-operations-owner',
  'tenant-security-admin',
  'builtin-management-owner',
  'portal-basic-user',
  'portal-user',
];

test('exported fine-grained profile keys exclude removed coarse keys', () => {
  const values = [
    profiles.PORTAL_CORE_KEY,
    profiles.PORTAL_APPS_KEY,
    profiles.PORTAL_SERVICES_KEY,
    profiles.PORTAL_TENANT_APPS_EDITOR_KEY,
    profiles.PORTAL_SELF_FILES_KEY,
    profiles.PORTAL_SERVICE_ENDPOINT_KEY,
    profiles.TENANT_OPS_ACCOUNTS_KEY,
    profiles.TENANT_OPS_AUDIT_METRICS_KEY,
    ...profiles.PORTAL_BASIC_KEYS,
    ...profiles.PORTAL_TENANT_BASE_KEYS,
  ];
  for (const key of values) {
    assert.equal(REMOVED_COARSE_KEYS.includes(key), false, 'unexpected coarse key: ' + key);
  }
  assert.deepEqual(profiles.PORTAL_BASIC_KEYS, [
    'portal-usage-core',
    'portal-usage-apps',
    'portal-usage-services',
  ]);
  assert.deepEqual(profiles.PORTAL_TENANT_BASE_KEYS, [
    'portal-usage-core',
    'portal-usage-apps',
    'portal-usage-tenant-apps-editor',
    'portal-usage-services',
  ]);
});

test('dedupRoleRefs preserves first-seen order and strips duplicates/extra fields', () => {
  const result = profiles.dedupRoleRefs([
    { module: '/modules/kernel/runner', key: 'portal-app-catalog-viewer', extra: 1 },
    { module: '/modules/kernel/runner', key: 'portal-service-invoker' },
    { module: '/modules/kernel/runner', key: 'portal-app-catalog-viewer' },
    null,
    { module: '', key: 'missing' },
  ]);
  assert.deepEqual(result, [
    { module: '/modules/kernel/runner', key: 'portal-app-catalog-viewer' },
    { module: '/modules/kernel/runner', key: 'portal-service-invoker' },
  ]);
});

test('portalBasicProfileSet requires complete enabled account usage profiles and filters invalid ones', () => {
  const base = [
    {
      key: 'portal-usage-services',
      systemManaged: true,
      subjectType: 'account',
      scene: 'usage',
      status: 2,
      roleRefs: [
        { module: '/modules/kernel/runner', key: 'portal-service-catalog-viewer' },
        { module: '/modules/kernel/runner', key: 'portal-service-invoker' },
      ],
    },
    {
      key: 'portal-usage-core',
      systemManaged: true,
      subjectType: 'account',
      scene: 'usage',
      status: 2,
      roleRefs: [
        { module: '/modules/kernel/runner', key: 'usage-panel-profile-viewer' },
      ],
    },
    {
      key: 'portal-usage-apps',
      systemManaged: true,
      subjectType: 'account',
      scene: 'usage',
      status: 2,
      roleRefs: [
        { module: '/modules/kernel/runner', key: 'portal-app-catalog-viewer' },
      ],
    },
  ];
  const full = profiles.portalBasicProfileSet(base);
  assert.equal(full.complete, true);
  assert.equal(full.templates.map(t => t.key).join(','), 'portal-usage-core,portal-usage-apps,portal-usage-services');
  assert.equal(full.roleRefs.length, 4);

  const missingOne = profiles.portalBasicProfileSet(base.slice(0, 2));
  assert.equal(missingOne.complete, false);

  for (const patch of [{ scene: 'management' }, { status: 1 }, { subjectType: 'endpoint' }, { systemManaged: false }, { roleRefs: [] }]) {
    const mutated = structuredClone(base);
    Object.assign(mutated[1], patch);
    assert.equal(profiles.portalBasicProfileSet(mutated).complete, false);
  }
});

test('tenantPortalKeys conditionally includes portal-usage-self-files when enabled system profile exists', async () => {
  const withFiles = await profiles.tenantPortalKeys({}, 'tenantA', {}, async () => [
    { key: 'portal-usage-self-files', systemManaged: true, subjectType: 'account', scene: 'usage', status: 2 },
  ]);
  assert.deepEqual(withFiles, [...profiles.PORTAL_TENANT_BASE_KEYS, 'portal-usage-self-files']);

  const withoutFiles = await profiles.tenantPortalKeys({}, 'tenantA', {}, async () => []);
  assert.deepEqual(withoutFiles, profiles.PORTAL_TENANT_BASE_KEYS);
});
