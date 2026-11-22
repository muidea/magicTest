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

function buildTemplates(specs) {
  return specs.map(spec => ({
    key: spec.key,
    kind: 'system-profile',
    systemManaged: true,
    status: 2,
    scene: spec.scene,
    subjectType: spec.subjectType,
    roleRefs: [{ module: '/modules/kernel/runner', key: 'probe-' + spec.key }],
    applicationAccess: spec.applicationAccess,
  }));
}

test('exported fine-grained profile keys exclude removed coarse keys and cover all 26 specs', () => {
  const values = [
    profiles.PLATFORM_OPS_NAMESPACE_KEY,
    profiles.PLATFORM_OPS_RUNTIME_KEY,
    profiles.PLATFORM_OPS_DEPLOYMENT_KEY,
    profiles.PLATFORM_OPS_LOGGING_KEY,
    profiles.TENANT_OPS_ACCOUNTS_KEY,
    profiles.TENANT_OPS_ROLES_TEMPLATES_KEY,
    profiles.TENANT_OPS_CREDENTIALS_KEY,
    profiles.TENANT_OPS_REGISTRATION_FEDERATION_KEY,
    profiles.TENANT_OPS_AUDIT_METRICS_KEY,
    profiles.TENANT_OPS_SETTINGS_KEY,
    profiles.PLATFORM_MGMT_CATALOG_KEY,
    profiles.PLATFORM_MGMT_APP_AUTHORING_KEY,
    profiles.PLATFORM_MGMT_APP_OPERATIONS_KEY,
    profiles.PLATFORM_MGMT_APP_ACCESS_KEY,
    profiles.PLATFORM_MGMT_ALL_APPS_MANAGER_KEY,
    profiles.PLATFORM_MGMT_SERVICES_KEY,
    profiles.PLATFORM_MGMT_SUPPORT_KEY,
    profiles.PLATFORM_MGMT_FILES_VIEWER_KEY,
    profiles.PLATFORM_MGMT_FILES_EDITOR_KEY,
    profiles.PLATFORM_MGMT_FILES_MANAGER_KEY,
    profiles.PORTAL_CORE_KEY,
    profiles.PORTAL_APPS_KEY,
    profiles.PORTAL_TENANT_APPS_EDITOR_KEY,
    profiles.PORTAL_SERVICES_KEY,
    profiles.PORTAL_SELF_FILES_KEY,
    profiles.PORTAL_SERVICE_ENDPOINT_KEY,
    ...profiles.PORTAL_BASIC_KEYS,
    ...profiles.PORTAL_TENANT_BASE_KEYS,
  ];
  for (const key of values) {
    assert.equal(REMOVED_COARSE_KEYS.includes(key), false, 'unexpected coarse key: ' + key);
  }
  assert.equal(profiles.CORE_PLATFORM_PROFILE_SPECS.length, 22);
  assert.equal(profiles.MAGICFILE_PROFILE_SPECS.length, 4);
  assert.equal(profiles.PLATFORM_PROFILE_SPECS.length, 26);
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

test('validatePlatformSystemProfiles verifies default vs tenant catalogs, magicFile conditional sets, and fails closed on drift', () => {
  const defaultWithFiles = buildTemplates(profiles.expectedPlatformProfiles([], { namespaceClass: 'default', requireMagicFile: true }));
  assert.equal(defaultWithFiles.length, 25);
  assert.equal(profiles.validatePlatformSystemProfiles(defaultWithFiles, { namespaceClass: 'default', requireMagicFile: true }).ok, true);

  const tenantWithoutFiles = buildTemplates(profiles.expectedPlatformProfiles([], { namespaceClass: 'tenant', requireMagicFile: false }));
  assert.equal(tenantWithoutFiles.length, 18);
  assert.equal(profiles.validatePlatformSystemProfiles(tenantWithoutFiles, { namespaceClass: 'tenant' }).ok, true);

  const tenantWithFiles = buildTemplates(profiles.expectedPlatformProfiles([], { namespaceClass: 'tenant', requireMagicFile: true }));
  assert.equal(tenantWithFiles.length, 22);
  assert.equal(profiles.validatePlatformSystemProfiles(tenantWithFiles, { namespaceClass: 'tenant', requireMagicFile: true }).ok, true);

  // Partial magicFile projection (only 1 of 4) fails closed in auto-detect mode.
  const partial = [...tenantWithoutFiles, ...buildTemplates([profiles.MAGICFILE_PROFILE_SPECS[0]])];
  const partialResult = profiles.validatePlatformSystemProfiles(partial, { namespaceClass: 'tenant' });
  assert.equal(partialResult.ok, false);
  assert.equal(partialResult.partialMagicFile, true);
  assert.equal(partialResult.missing.length, 3);

  // Coarse legacy key fails validation.
  const withCoarse = [...tenantWithFiles, ...buildTemplates([{ key: 'portal-basic-user', scene: 'usage', subjectType: 'account', applicationAccess: [] }])];
  const coarseResult = profiles.validatePlatformSystemProfiles(withCoarse, { namespaceClass: 'tenant' });
  assert.equal(coarseResult.ok, false);
  assert.deepEqual(coarseResult.presentCoarse, ['portal-basic-user']);

  // Default-only profile leaked into tenant fails validation.
  const leakedDefault = [...tenantWithoutFiles, ...buildTemplates([profiles.CORE_PLATFORM_PROFILE_SPECS[0]])];
  const leakResult = profiles.validatePlatformSystemProfiles(leakedDefault, { namespaceClass: 'tenant' });
  assert.equal(leakResult.ok, false);
  assert.deepEqual(leakResult.excludedDefaultOnly, ['platform-ops-namespace']);

  // Wrong scene / wrong applicationAccess fails validation.
  const mutated = structuredClone(tenantWithoutFiles);
  const editorSpec = mutated.find(t => t.key === 'portal-usage-tenant-apps-editor');
  editorSpec.applicationAccess = [];
  const mismatchResult = profiles.validatePlatformSystemProfiles(mutated, { namespaceClass: 'tenant' });
  assert.equal(mismatchResult.ok, false);
  assert.equal(mismatchResult.mismatched[0].key, 'portal-usage-tenant-apps-editor');
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
