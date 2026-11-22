// Shared fine-grained platform profile keys and catalog validators aligned with
// Runner's PlatformSystemAccessProfiles (D1/D2/D4 closeout). No coarse legacy keys.
const PLATFORM_OPS_NAMESPACE_KEY = 'platform-ops-namespace';
const PLATFORM_OPS_RUNTIME_KEY = 'platform-ops-runtime';
const PLATFORM_OPS_DEPLOYMENT_KEY = 'platform-ops-deployment';
const PLATFORM_OPS_LOGGING_KEY = 'platform-ops-logging';
const TENANT_OPS_ACCOUNTS_KEY = 'tenant-ops-accounts';
const TENANT_OPS_ROLES_TEMPLATES_KEY = 'tenant-ops-roles-templates';
const TENANT_OPS_CREDENTIALS_KEY = 'tenant-ops-credentials';
const TENANT_OPS_REGISTRATION_FEDERATION_KEY = 'tenant-ops-registration-federation';
const TENANT_OPS_AUDIT_METRICS_KEY = 'tenant-ops-audit-metrics';
const TENANT_OPS_SETTINGS_KEY = 'tenant-ops-settings';
const PLATFORM_MGMT_CATALOG_KEY = 'platform-mgmt-catalog';
const PLATFORM_MGMT_APP_AUTHORING_KEY = 'platform-mgmt-app-authoring';
const PLATFORM_MGMT_APP_OPERATIONS_KEY = 'platform-mgmt-app-operations';
const PLATFORM_MGMT_APP_ACCESS_KEY = 'platform-mgmt-app-access';
const PLATFORM_MGMT_ALL_APPS_MANAGER_KEY = 'platform-mgmt-all-apps-manager';
const PLATFORM_MGMT_SERVICES_KEY = 'platform-mgmt-services';
const PLATFORM_MGMT_SUPPORT_KEY = 'platform-mgmt-support';
const PLATFORM_MGMT_FILES_VIEWER_KEY = 'platform-mgmt-files-viewer';
const PLATFORM_MGMT_FILES_EDITOR_KEY = 'platform-mgmt-files-editor';
const PLATFORM_MGMT_FILES_MANAGER_KEY = 'platform-mgmt-files-manager';
const PORTAL_CORE_KEY = 'portal-usage-core';
const PORTAL_APPS_KEY = 'portal-usage-apps';
const PORTAL_TENANT_APPS_EDITOR_KEY = 'portal-usage-tenant-apps-editor';
const PORTAL_SERVICES_KEY = 'portal-usage-services';
const PORTAL_SELF_FILES_KEY = 'portal-usage-self-files';
const PORTAL_SERVICE_ENDPOINT_KEY = 'portal-usage-service-endpoint';

const REMOVED_COARSE_PROFILE_KEYS = [
  'platform-operations-owner',
  'tenant-security-admin',
  'builtin-management-owner',
  'portal-basic-user',
  'portal-user',
];

const MAGICFILE_PROFILE_SPECS = [
  { key: PLATFORM_MGMT_FILES_VIEWER_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_FILES_EDITOR_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_FILES_MANAGER_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PORTAL_SELF_FILES_KEY, scene: 'usage', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
];
const MAGICFILE_PROFILE_KEYS = MAGICFILE_PROFILE_SPECS.map(spec => spec.key);

const CORE_PLATFORM_PROFILE_SPECS = [
  { key: PLATFORM_OPS_NAMESPACE_KEY, scene: 'operations', namespaceClass: 'default', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_OPS_RUNTIME_KEY, scene: 'operations', namespaceClass: 'default', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_OPS_DEPLOYMENT_KEY, scene: 'operations', namespaceClass: 'default', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_OPS_LOGGING_KEY, scene: 'operations', namespaceClass: 'default', subjectType: 'account', applicationAccess: [] },
  { key: TENANT_OPS_ACCOUNTS_KEY, scene: 'operations', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: TENANT_OPS_ROLES_TEMPLATES_KEY, scene: 'operations', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: TENANT_OPS_CREDENTIALS_KEY, scene: 'operations', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: TENANT_OPS_REGISTRATION_FEDERATION_KEY, scene: 'operations', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: TENANT_OPS_AUDIT_METRICS_KEY, scene: 'operations', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: TENANT_OPS_SETTINGS_KEY, scene: 'operations', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_CATALOG_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_APP_AUTHORING_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_APP_OPERATIONS_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_APP_ACCESS_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  {
    key: PLATFORM_MGMT_ALL_APPS_MANAGER_KEY,
    scene: 'management',
    namespaceClass: 'all',
    subjectType: 'account',
    applicationAccess: [{ applicationUuid: '*', accessLevel: 'manager' }],
  },
  { key: PLATFORM_MGMT_SERVICES_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PLATFORM_MGMT_SUPPORT_KEY, scene: 'management', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PORTAL_CORE_KEY, scene: 'usage', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PORTAL_APPS_KEY, scene: 'usage', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  {
    key: PORTAL_TENANT_APPS_EDITOR_KEY,
    scene: 'usage',
    namespaceClass: 'tenant',
    subjectType: 'account',
    applicationAccess: [{ applicationUuid: '*', accessLevel: 'editor' }],
  },
  { key: PORTAL_SERVICES_KEY, scene: 'usage', namespaceClass: 'all', subjectType: 'account', applicationAccess: [] },
  { key: PORTAL_SERVICE_ENDPOINT_KEY, scene: 'usage', namespaceClass: 'all', subjectType: 'endpoint', applicationAccess: [] },
];

const PLATFORM_PROFILE_SPECS = [...CORE_PLATFORM_PROFILE_SPECS, ...MAGICFILE_PROFILE_SPECS];

const PORTAL_BASIC_KEYS = [PORTAL_CORE_KEY, PORTAL_APPS_KEY, PORTAL_SERVICES_KEY];
const PORTAL_TENANT_BASE_KEYS = [
  PORTAL_CORE_KEY,
  PORTAL_APPS_KEY,
  PORTAL_TENANT_APPS_EDITOR_KEY,
  PORTAL_SERVICES_KEY,
];

function dedupRoleRefs(refs = []) {
  const seen = new Map();
  for (const ref of refs) {
    if (!ref || !ref.module || !ref.key) continue;
    const identity = `${ref.module}\0${ref.key}`;
    if (!seen.has(identity)) {
      seen.set(identity, { module: ref.module, key: ref.key });
    }
  }
  return [...seen.values()];
}

function normalizeApplicationAccess(items = []) {
  return [...(items || [])]
    .filter(x => x && x.applicationUuid)
    .map(x => ({ applicationUuid: x.applicationUuid, accessLevel: x.accessLevel }))
    .sort((a, b) => a.applicationUuid.localeCompare(b.applicationUuid));
}

function expectedPlatformProfiles(templates = [], { namespaceClass = 'tenant', requireMagicFile } = {}) {
  const presentKeys = new Set((templates || []).filter(Boolean).map(t => t.key));
  const presentMagicFile = MAGICFILE_PROFILE_KEYS.filter(key => presentKeys.has(key));
  const includeMagicFile =
    requireMagicFile === true
      ? true
      : requireMagicFile === false
        ? false
        : presentMagicFile.length > 0;
  const source = includeMagicFile ? PLATFORM_PROFILE_SPECS : CORE_PLATFORM_PROFILE_SPECS;
  if (namespaceClass === 'all') return [...source];
  return source.filter(spec => spec.namespaceClass === 'all' || spec.namespaceClass === namespaceClass);
}

function validatePlatformSystemProfiles(templates = [], options = {}) {
  const { namespaceClass = 'tenant', requireMagicFile } = options;
  const rows = Array.isArray(templates) ? templates : [];
  const byKey = new Map();
  for (const row of rows) {
    if (row && row.key) byKey.set(row.key, row);
  }
  const presentCoarse = REMOVED_COARSE_PROFILE_KEYS.filter(key => byKey.has(key));
  const expected = expectedPlatformProfiles(rows, { namespaceClass, requireMagicFile });
  const excludedDefaultOnly =
    namespaceClass === 'tenant'
      ? CORE_PLATFORM_PROFILE_SPECS.filter(spec => spec.namespaceClass === 'default' && byKey.has(spec.key)).map(spec => spec.key)
      : [];
  const excludedTenantOnly =
    namespaceClass === 'default'
      ? CORE_PLATFORM_PROFILE_SPECS.filter(spec => spec.namespaceClass === 'tenant' && byKey.has(spec.key)).map(spec => spec.key)
      : [];
  const missing = [];
  const mismatched = [];
  for (const spec of expected) {
    const actual = byKey.get(spec.key);
    if (!actual) {
      missing.push(spec.key);
      continue;
    }
    const problems = [];
    if (actual.kind !== 'system-profile') problems.push('kind=' + actual.kind);
    if (actual.systemManaged !== true) problems.push('systemManaged=' + actual.systemManaged);
    if (actual.status !== 2) problems.push('status=' + actual.status);
    if (actual.scene !== spec.scene) problems.push('scene=' + actual.scene + '!=' + spec.scene);
    if (actual.subjectType !== spec.subjectType) problems.push('subjectType=' + actual.subjectType + '!=' + spec.subjectType);
    if (!Array.isArray(actual.roleRefs) || actual.roleRefs.length === 0) problems.push('empty roleRefs');
    const actualAccess = JSON.stringify(normalizeApplicationAccess(actual.applicationAccess));
    const expectedAccess = JSON.stringify(normalizeApplicationAccess(spec.applicationAccess));
    if (actualAccess !== expectedAccess) problems.push('applicationAccess=' + actualAccess + '!=' + expectedAccess);
    if (problems.length > 0) mismatched.push({ key: spec.key, problems });
  }
  const presentMagicFile = MAGICFILE_PROFILE_KEYS.filter(key => byKey.has(key));
  const partialMagicFile =
    requireMagicFile === undefined &&
    presentMagicFile.length > 0 &&
    presentMagicFile.length < MAGICFILE_PROFILE_KEYS.length;
  return {
    ok:
      presentCoarse.length === 0 &&
      excludedDefaultOnly.length === 0 &&
      excludedTenantOnly.length === 0 &&
      missing.length === 0 &&
      mismatched.length === 0 &&
      !partialMagicFile,
    expectedKeys: expected.map(spec => spec.key),
    presentCoarse,
    excludedDefaultOnly,
    excludedTenantOnly,
    missing,
    mismatched,
    partialMagicFile,
  };
}

function portalBasicProfileSet(templates = []) {
  const byKey = new Map();
  for (const t of templates) {
    if (
      t &&
      PORTAL_BASIC_KEYS.includes(t.key) &&
      t.systemManaged &&
      t.subjectType === 'account' &&
      t.status === 2 &&
      (!t.scene || t.scene === 'usage')
    ) {
      byKey.set(t.key, t);
    }
  }
  const matched = PORTAL_BASIC_KEYS.map(key => byKey.get(key)).filter(Boolean);
  const complete =
    matched.length === PORTAL_BASIC_KEYS.length &&
    matched.every(t => Array.isArray(t.roleRefs) && t.roleRefs.length > 0);
  return {
    keys: [...PORTAL_BASIC_KEYS],
    templates: matched,
    complete,
    roleRefs: dedupRoleRefs(matched.flatMap(t => t.roleRefs || [])),
  };
}

async function tenantPortalKeys(h, namespace, actor = h.admin, listTemplates) {
  const route = '/cas/namespaces/' + namespace + '/role-templates/';
  const rows = listTemplates
    ? await listTemplates(route)
    : h.directory
      ? await h.directory(actor, route)
      : [];
  const hasSelfFiles = rows.some(
    t =>
      t &&
      t.key === PORTAL_SELF_FILES_KEY &&
      t.systemManaged &&
      t.subjectType === 'account' &&
      t.status === 2 &&
      (!t.scene || t.scene === 'usage'),
  );
  return [...PORTAL_TENANT_BASE_KEYS, ...(hasSelfFiles ? [PORTAL_SELF_FILES_KEY] : [])];
}

module.exports = {
  PLATFORM_OPS_NAMESPACE_KEY,
  PLATFORM_OPS_RUNTIME_KEY,
  PLATFORM_OPS_DEPLOYMENT_KEY,
  PLATFORM_OPS_LOGGING_KEY,
  TENANT_OPS_ACCOUNTS_KEY,
  TENANT_OPS_ROLES_TEMPLATES_KEY,
  TENANT_OPS_CREDENTIALS_KEY,
  TENANT_OPS_REGISTRATION_FEDERATION_KEY,
  TENANT_OPS_AUDIT_METRICS_KEY,
  TENANT_OPS_SETTINGS_KEY,
  PLATFORM_MGMT_CATALOG_KEY,
  PLATFORM_MGMT_APP_AUTHORING_KEY,
  PLATFORM_MGMT_APP_OPERATIONS_KEY,
  PLATFORM_MGMT_APP_ACCESS_KEY,
  PLATFORM_MGMT_ALL_APPS_MANAGER_KEY,
  PLATFORM_MGMT_SERVICES_KEY,
  PLATFORM_MGMT_SUPPORT_KEY,
  PLATFORM_MGMT_FILES_VIEWER_KEY,
  PLATFORM_MGMT_FILES_EDITOR_KEY,
  PLATFORM_MGMT_FILES_MANAGER_KEY,
  PORTAL_CORE_KEY,
  PORTAL_APPS_KEY,
  PORTAL_TENANT_APPS_EDITOR_KEY,
  PORTAL_SERVICES_KEY,
  PORTAL_SELF_FILES_KEY,
  PORTAL_SERVICE_ENDPOINT_KEY,
  REMOVED_COARSE_PROFILE_KEYS,
  MAGICFILE_PROFILE_SPECS,
  MAGICFILE_PROFILE_KEYS,
  CORE_PLATFORM_PROFILE_SPECS,
  PLATFORM_PROFILE_SPECS,
  PORTAL_BASIC_KEYS,
  PORTAL_TENANT_BASE_KEYS,
  dedupRoleRefs,
  expectedPlatformProfiles,
  validatePlatformSystemProfiles,
  portalBasicProfileSet,
  tenantPortalKeys,
};
