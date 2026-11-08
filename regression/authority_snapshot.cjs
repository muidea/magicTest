const { isDeepStrictEqual } = require('node:util');

// CAS aggregation fields are sets. All other arrays, including nested fields,
// retain their order. Sorting retains duplicates and every field of each item.
const authoritySets = ['templateRefs', 'effectiveRoles', 'effectivePrivileges', 'roleRefs'];
function objectKeys(value) {
  if (Array.isArray(value)) return value.map(objectKeys);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, objectKeys(value[key])]));
  return value;
}
function authoritySnapshot(value) {
  const result = objectKeys(value);
  if (!result || typeof result !== 'object' || Array.isArray(result)) return result;
  for (const key of authoritySets) {
    if (Array.isArray(result[key])) result[key].sort((a, b) => {
      const left = JSON.stringify(a), right = JSON.stringify(b);
      return left < right ? -1 : left > right ? 1 : 0;
    });
  }
  return result;
}
const sameAuthority = (left, right) => isDeepStrictEqual(authoritySnapshot(left), authoritySnapshot(right));
function accountDirectorySnapshot(rows) {
  if (!Array.isArray(rows) || rows.some(row => !Number.isSafeInteger(row?.id) || row.id <= 0) || new Set(rows.map(row => row.id)).size !== rows.length) throw Error('Account snapshot requires complete, unique, safe resource IDs');
  return rows.map(authoritySnapshot).sort((a, b) => a.id - b.id);
}
const sameAccounts = (left, right) => isDeepStrictEqual(accountDirectorySnapshot(left), accountDirectorySnapshot(right));
module.exports = { authoritySnapshot, sameAuthority, sameAccounts };
