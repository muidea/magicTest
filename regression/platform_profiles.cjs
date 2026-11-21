// Shared fine-grained platform profile keys and helpers aligned with Runner's
// PlatformSystemAccessProfiles (D1/D2/D4 closeout). No coarse legacy keys.
const PORTAL_CORE_KEY = 'portal-usage-core';
const PORTAL_APPS_KEY = 'portal-usage-apps';
const PORTAL_SERVICES_KEY = 'portal-usage-services';
const PORTAL_TENANT_APPS_EDITOR_KEY = 'portal-usage-tenant-apps-editor';
const PORTAL_SELF_FILES_KEY = 'portal-usage-self-files';
const PORTAL_SERVICE_ENDPOINT_KEY = 'portal-usage-service-endpoint';
const TENANT_OPS_ACCOUNTS_KEY = 'tenant-ops-accounts';
const TENANT_OPS_AUDIT_METRICS_KEY = 'tenant-ops-audit-metrics';

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
  PORTAL_CORE_KEY,
  PORTAL_APPS_KEY,
  PORTAL_SERVICES_KEY,
  PORTAL_TENANT_APPS_EDITOR_KEY,
  PORTAL_SELF_FILES_KEY,
  PORTAL_SERVICE_ENDPOINT_KEY,
  TENANT_OPS_ACCOUNTS_KEY,
  TENANT_OPS_AUDIT_METRICS_KEY,
  PORTAL_BASIC_KEYS,
  PORTAL_TENANT_BASE_KEYS,
  dedupRoleRefs,
  portalBasicProfileSet,
  tenantPortalKeys,
};
