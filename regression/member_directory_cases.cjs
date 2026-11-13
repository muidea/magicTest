// Complete CAS directories in an owned tenant. Reads have no snapshot promise;
// a known concurrent change discards the in-flight aggregate and starts over.
const { isDeepStrictEqual: same } = require('node:util');
const { readDirectory } = require('./directory.cjs');
const { createRegistrationFixture } = require('./registration_cases.cjs');
const { changeRoles } = require('./audit_cases.cjs');
const ordered = rows => [...rows].sort((a, b) => a.id - b.id);
const refs = values => values.map(v => v.module + ':' + v.key).sort();
function listView(account) { const view = structuredClone(account); delete view.effectivePrivileges; return view; }
function replacedTemplateCounts(before, after, from, to) {
  // subjectCount is a live owner projection and must change with the binding.
  // Preserve every other template field and require the exact expected delta.
  return same(ordered(after), ordered(before.map(template => ({ ...template,
    subjectCount: template.subjectCount + (template.id === from.id ? -1 : template.id === to.id ? 1 : 0),
  }))));
}
function memberProjection(account, bindings, template) {
  const owned = bindings.filter(v => v.subjectType === 'account' && v.subjectId === account.id && v.status === 2);
  return account.status === 2 && account.templateRefs?.length === 1 && account.templateRefs[0].key === template.key &&
    same(refs(account.effectiveRoles || []), refs(template.roleRefs)) && owned.length === template.roleRefs.length &&
    owned.every(v => v.sourceType === 'template' && v.sourceKey === template.key && v.sourceVersion > 0) &&
    same(refs(owned.map(v => ({ module: v.roleModule, key: v.roleKey }))), refs(template.roleRefs));
}
async function readFault(h, route, mode) {
  const actor = h.admin, pathname = '/api/v1/web/proxy' + new URL(route, actor.origin).pathname;
  let intercepted = 0, requests = 0, complete = false, refused = false;
  const pattern = u => u.origin === actor.origin && u.pathname === pathname && u.searchParams.get('_pageNum') === '2';
  await actor.page.route(pattern, async r => {
    h.check('Controlled directory fault intercepts only the exact original second GET page', r.request().method() === 'GET');
    intercepted++;
    if (mode === 'cancel') await r.abort('aborted');
    else await r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 15, message: 'controlled browser-only second directory page failure' } }) });
  });
  const consumer = { Blocked: h.Blocked, async ok(who, method, url) {
    requests++;
    const response = await h.api(who, method, url);
    if (!h.good(response)) throw new h.Blocked('Directory page unavailable; no complete projection');
    return response.data;
  } };
  try {
    try { await readDirectory(consumer, actor, route, { pageSize: 2 }); complete = true; }
    catch (error) { refused = true; }
  } finally { await actor.page.unroute(pattern); }
  h.check('Actual browser ' + mode + ' on page two yields no successful partial directory', intercepted === 1 && requests === 2 && refused && !complete);
  h.observe({ kind: 'directory-controlled-read-fault', mode, intercepted, requests, complete,
    scope: 'Browser-only second-page transport fault; live owner records unchanged, not an injected server dependency failure.' });
}
async function completeMembers(h) {
  const f = await createRegistrationFixture(h, 'memberpages'), groups = [], members = [];
  for (const suffix of ['first', 'second']) groups.push(await h.create(f.base + 'role-templates/', {
    key: h.state.prefix + '-pages-' + suffix, name: '多页成员模板 ' + suffix, subjectType: 'account',
    roleRefs: structuredClone(f.portal.roleRefs), applicationAccess: [], status: 2,
  }, 'role-template'));
  for (let i = 0; i < 6; i++) members.push(await h.create(f.base + 'accounts/', {
    account: h.state.prefix + '-paged-' + i, displayName: '多页普通成员 ' + i,
    password: h.state.password, status: 2, roleTemplateKeys: [groups[0].key],
  }, 'account'));
  const bindingRoute = f.base + 'subject-role-bindings/?subjectType=account%7C%3D';
  const full = async () => ({ accounts: ordered(await h.directory(h.admin, f.base + 'accounts/', { pageSize: 2 })),
    templates: ordered(await h.directory(h.admin, f.base + 'role-templates/', { pageSize: 2 })),
    bindings: ordered(await h.directory(h.admin, bindingRoute, { pageSize: 2 })) });
  const initial = await full();
  h.check('Real multi-page member and binding directories contain every distinct owned subject and copied template',
    initial.accounts.length === members.length + 1 && initial.accounts.some(v => v.id === f.bootstrap.id) &&
    members.every(m => initial.accounts.some(v => v.id === m.id && v.account === m.account)) &&
    initial.bindings.length > 2 && groups.every(g => initial.templates.some(v => v.id === g.id && same(v.roleRefs, g.roleRefs))));
  for (const m of members) {
    const exact = (await h.ok(h.admin, 'GET', f.base + 'accounts/' + m.id)).value;
    h.check('Complete account/template/binding projection equals independent exact current subject roles',
      initial.accounts.some(v => same(listView(v), listView(exact))) && memberProjection(exact, initial.bindings, groups[0]), { accountId: m.id });
  }
  let changed = false, discardedError;
  const resource = h.state.resources.find(r => r.kind === 'account' && r.id === members[0].id);
  const changing = { Blocked: h.Blocked, async ok(actor, method, route) {
    const page = await h.ok(actor, method, route);
    if (!changed) { changed = true; await changeRoles(h, h.admin, resource, [groups[1].key]); }
    return page;
  } };
  try { await readDirectory(changing, h.admin, bindingRoute, { pageSize: 2 }); }
  catch (error) { discardedError = error.message; }
  if (resource.authorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original in-flight member template replacement remains unresolved; no further directory claims');
  h.observe({ kind: 'known-changing-directory-discarded', changed, discardedError,
    scope: 'The first aggregate is deliberately discarded regardless of success; no transactional snapshot or automatic same-total churn detection claimed.' });
  const current = await full(), exact = (await h.ok(h.admin, 'GET', f.base + 'accounts/' + members[0].id)).value;
  h.check('Fresh complete read after acknowledged in-flight role replacement contains only the current template source',
    changed && memberProjection(exact, current.bindings, groups[1]) && current.accounts.some(v => same(listView(v), listView(exact))) &&
    replacedTemplateCounts(initial.templates, current.templates, groups[0], groups[1]));
  for (const mode of ['dependency-failure', 'cancel']) {
    await readFault(h, bindingRoute, mode);
    h.check('Controlled incomplete reads preserve every current original owner account, template and binding', same(await full(), current));
  }
}
module.exports = { handlers: { 'F005-004': completeMembers }, memberProjection, listView, replacedTemplateCounts };
