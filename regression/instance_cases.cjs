const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const base = '/panel/application/installations/';
const read = (h, id) => h.ok(h.admin, 'GET', base + id).then(r => r.value);
function original(h, r) {
  if (h.admin.origin !== r.origin || !same(h.admin.identity, r.actorIdentity) || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original instance-name command unresolved or actor changed; no replay');
}
function withoutDisplay(value) {
  const copy = structuredClone(value); delete copy.instanceName; delete copy.deploymentVersion; return copy;
}
async function rename(h, r, name, expected = r.last.deploymentVersion, errorCode) {
  original(h, r); const before = await read(h, r.id);
  if (!same(before, r.last)) throw new h.Blocked('Instance changed concurrently; do not overwrite its display name');
  const c = { route: base + r.id + '/instance-name', body: { instanceName: name, expectedDeploymentVersion: expected }, outcome: 'unknown' };
  r.commands.push(c); h.persist(); c.response = await h.api(h.admin, 'PUT', c.route, c.body); h.persist();
  const current = await read(h, r.id);
  if (errorCode !== undefined) {
    if (!h.good(c.response) && [4, 19].includes(c.response.data?.error?.code) && same(current, before)) { c.outcome = 'rejected-and-unchanged'; h.persist(); }
    h.check('Invalid or stale display-name command reaches exact owner refusal and preserves complete original instance',
      c.outcome === 'rejected-and-unchanged' && c.response.data.error.code === errorCode, c.response);
  } else {
    h.check('Conditional rename and independent owner agree on exact current name and next deployment revision', h.good(c.response) && same(current, c.response.data.value) && current.instanceName === name &&
      current.deploymentVersion === before.deploymentVersion + (name === before.instanceName ? 0 : 1) && same(withoutDisplay(current), withoutDisplay(before)), current);
    c.outcome = 'confirmed'; r.last = current; h.persist();
  }
  h.check('Other original installed instance remains completely unchanged', same(await read(h, r.peer.id), r.peer));
  return current;
}
async function restore(h, r) {
  original(h, r);
  if (!same(await read(h, r.id), r.last)) throw new h.Blocked('Instance-name restoration rejects a concurrent owner revision');
  if (r.last.instanceName !== r.original.instanceName) await rename(h, r, r.original.instanceName);
  h.check('Independent owner restores original display text and all immutable installation facts', same(withoutDisplay(await read(h, r.id)), withoutDisplay(r.original)) && (await read(h, r.id)).instanceName === r.original.instanceName);
  r.phase = 'deleted'; h.persist();
  return { proof: 'Current-run instance name restored conditionally by original owner, peer unchanged; deployment revision advances and historical installation/request facts are retained.' };
}
async function prepare(h) {
  const f = await fixture(h);
  if (f.installations?.length !== 2) throw new h.Blocked('Two officially installed fixture instances are required');
  const original = await read(h, f.installations[0].id), peer = await read(h, f.installations[1].id);
  h.check('Ready dual instances retain exact original namespace, application and separate deployment identities',
    original.status === 'ready' && peer.status === 'ready' && original.applicationUuid === f.application.uuid && peer.applicationUuid === f.application.uuid && original.namespace === 'panel' && peer.namespace === 'panel' && original.id !== peer.id && original.deploymentId !== peer.deploymentId);
  const r = { kind: 'instance-name-restore', id: original.id, phase: 'created', original, last: original, peer,
    origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity), commands: [] };
  h.state.resources.push(r); h.persist(); return r;
}
async function names(h) {
  const r = await prepare(h);
  try {
    for (const name of ['  中文 实例 · / #1 😀  ', '名'.repeat(128)]) {
      await rename(h, r, name);
      const rows = await h.directory(h.admin, base);
      h.check('Complete current installation directory retains exact free display name and identity', rows.some(v => v.id === r.id && v.instanceName === name && v.instanceKey === r.original.instanceKey));
      await h.admin.page.goto(h.admin.origin + '/panel/application/deployment/', { waitUntil: 'networkidle' });
      await h.admin.page.reload({ waitUntil: 'networkidle' });
      const row = h.admin.page.locator('tr[data-row-key="' + r.id + '"]'); await row.waitFor();
      h.check('Real refreshed deployment page displays original instance current name', (await row.innerText()).includes(name.trim()));
      await h.screenshot(h.admin, 'instance-name-' + name.length);
    }
  } finally { await restore(h, r); }
}
async function invalidNames(h) {
  const r = await prepare(h);
  try {
    const stale = r.last.deploymentVersion;
    await rename(h, r, '并发作者已经确认的名称 ' + h.state.prefix);
    await rename(h, r, 'MUST NOT OVERWRITE', stale, 19);
    for (const name of ['', '  ', '名'.repeat(129), 'a\nb', 'a\tb', 'a\0b']) await rename(h, r, name, r.last.deploymentVersion, 4);
  } finally { await restore(h, r); }
}
names.transport = invalidNames.transport = 'owner-api';
module.exports = { handlers: { 'F032-002': names, 'F032-003': invalidNames }, restore, rename, withoutDisplay };
