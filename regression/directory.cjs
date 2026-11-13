// Public owner directory reads retain the original actor, route filters and
// complete pagination. A partial projection is never proof of absence.
async function readDirectory(h, actor, route, { pageSize = 100, maxPages = 100, idFormat = 'number' } = {}) {
  if (!actor?.identity || !route.startsWith('/') || route.startsWith('//') || route.includes('#')) throw new h.Blocked('Owner directory requires an original actor and same-origin resource path');
  if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100 || !Number.isSafeInteger(maxPages) || maxPages < 1 || maxPages > 100) throw new h.Blocked('Invalid directory read budget');
  if (!['number', 'string'].includes(idFormat)) throw new h.Blocked('Explicit supported directory identity format required');
  const validIdentity = idFormat === 'number' ? id => Number.isSafeInteger(id) && id > 0
    : id => typeof id === 'string' && id.length > 0 && id.length <= 128 && !/[\s\x00-\x1f\x7f]/.test(id);
  const url = new URL(route, 'https://owner.invalid');
  if (url.origin !== 'https://owner.invalid') throw new h.Blocked('Owner directory path resolves outside its origin');
  const original = structuredClone(actor.identity);
  const origin = actor.origin;
  const originalActor = () => {
    if (JSON.stringify(actor.identity) !== JSON.stringify(original) || actor.origin !== origin) throw new h.Blocked('Original directory actor changed during pagination');
  };
  const rows = [], ids = new Set(); let total;
  for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
    originalActor();
    url.searchParams.set('_pageSize', String(pageSize)); url.searchParams.set('_pageNum', String(pageNum));
    const page = await h.ok(actor, 'GET', url.pathname + url.search);
    originalActor();
    const pagination = page.pagination;
    if (!pagination || !Number.isSafeInteger(pagination.total) || pagination.total < 0 || pagination.pageNum !== pageNum || pagination.pageSize !== pageSize) throw new h.Blocked('Owner directory pagination is missing or differs from the requested page');
    if (total === undefined) total = pagination.total;
    if (total !== pagination.total || total > pageSize * maxPages) throw new h.Blocked('Owner directory changed or exceeds the explicit read budget');
    const values = page.values === null && total === 0 ? [] : page.values;
    if (!Array.isArray(values) || values.length > pageSize || rows.length + values.length > total) throw new h.Blocked('Owner directory response is incomplete or malformed');
    for (const value of values) {
      if (!value || !validIdentity(value.id) || ids.has(value.id)) throw new h.Blocked('Owner directory has missing, unsafe or repeated resource identities');
      ids.add(value.id); rows.push(value);
    }
    if (rows.length === total) {
      if (pagination.hasMore === true) throw new h.Blocked('Owner directory claims additional results beyond its total');
      return rows;
    }
    if (values.length !== pageSize || pagination.hasMore === false) throw new h.Blocked('Owner directory ended before its declared total');
  }
  throw new h.Blocked('Owner directory read budget exhausted; no complete absence proof');
}
module.exports = { readDirectory };
