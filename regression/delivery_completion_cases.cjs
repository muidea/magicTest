// Delivery tests consume immutable owner facts; ZIP inspection is independent.
const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const pages = require('./page_runtime_cases.cjs');
const delivery = require('./model_delivery.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const { packageContent } = require('./owner_transport.cjs');
const base = '/panel/application/definitions/';
// Mirror only the public portable-export contract's exact identity fields.
// Every business field, block, capability and write rule remains compared.
function portableEntities(entities) {
  return structuredClone(entities).map(entity => {
    entity.id = 0; entity.createTime = 0; entity.updateTime = 0;
    entity.icon = ''; entity.application = null; delete entity.uiMeta;
    return entity;
  }).sort((a, b) => {
    const left = a.pkgPath + '/' + a.name, right = b.pkgPath + '/' + b.name;
    return left < right ? -1 : left > right ? 1 : 0;
  });
}
function archive(bytes) {
  return JSON.parse(execFileSync('python3', ['-B', '-c', `import io,json,sys,zipfile,hashlib,posixpath
z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
names=z.namelist()
assert len(names)==len(set(names)) and len(names)<=10000
assert all(not n.startswith('/') and posixpath.normpath(n)==n and '..' not in n.split('/') for n in names)
assert sum(i.file_size for i in z.infolist())<=256*1024*1024
assert z.testzip() is None
checks=json.loads(z.read('checksums.json'))
assert checks['apiVersion']=='magic.checksums/v1'
entries=checks['files']; paths=[e['path'] for e in entries]
assert len(paths)==len(set(paths)) and set(paths)==set(names)-{'checksums.json'}
for e in entries:
 b=z.read(e['path']); assert len(b)==e['size'] and 'sha256:'+hashlib.sha256(b).hexdigest()==e['digest']
manifest=json.loads(z.read('package.json')); c=manifest['content']
print(json.dumps({'manifest':manifest,'metadata':json.loads(z.read(c['application'])),'pages':json.loads(z.read(c['pages'])),
 'entities':[json.loads(z.read(e['path'])) for e in c['entities']],
 'programFiles':{n[len('application/blocks/'):]:__import__('base64').b64encode(z.read(n)).decode() for n in names if n.startswith('application/blocks/')},'files':names}))`], { input: bytes, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, stdio: ['pipe', 'pipe', 'pipe'] }));
}
async function roundtrip(h, f) {
  const result = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
  h.check('Complete original model ZIP is downloaded through the public transport', result.status === 200 && Buffer.isBuffer(result.data.bytes));
  const files = archive(result.data.bytes), m = files.manifest;
  h.check('Independent CRC/checksum reader binds exact model contract, release, complete entity identities and pages to published owner',
    m.apiVersion === 'magic.model-package/v1' && m.application.uuid === f.application.uuid && m.application.key === f.application.name && m.application.modelRevision === f.revision.version &&
    m.content.artifactDigest === f.package.artifactDigest && same(files.pages, f.revision.content.pages) &&
    same(files.metadata.authorization, f.revision.application.authorization) &&
    same(files.entities, portableEntities(f.revision.entities)) && same(files.programFiles, f.revision.content.functionBlocks.files), { manifest: m, files: files.files });
  await delivery.importExact(h, f, result.data.bytes);
  f.roundtrip = { manifest: m, files: files.files, transportDigest: 'sha256:' + crypto.createHash('sha256').update(result.data.bytes).digest('hex') };
  h.observe({ kind: 'original-model-roundtrip', ...f.roundtrip });
}
async function model(h) {
  let library;
  const f = await pages.explicitFixture(h, undefined, undefined, { suffix: 'completemodel', requestPrefix: 'completemodel-',
    prepareAuthor: async (h, authored) => { library = await a.library(h, authored.app); authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages'); },
    prepareDelivery: roundtrip });
  let primary;
  try {
    h.check('Formal published program library keeps every exact editable source byte and parameter file', require('./script_library_cases.cjs').frozenLibraryMatches(f.revision, f.application, library));
    for (const i of f.installations) h.check('Real installed receipt consumes the exact frozen package and revision after ZIP import',
      i.sourceDigest === f.package.artifactDigest && i.receipt.revisionId === f.revision.id && i.receipt.revisionDigest === f.package.artifactDigest, i);
    const before = f.revision, current = await a.draft(h, f.application), changed = structuredClone(current.entities);
    changed[0].description = 'Unpublished model delivery edit ' + h.state.prefix;
    await a.save(h, f.application, current, changed);
    h.check('New editable author save leaves original installed frozen revision unchanged', same((await h.ok(h.admin, 'GET', base + f.application.id + '/revisions/' + before.id)).value, before));
  } catch (error) { primary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, f, primary); }
  await h.partial('Formal entity/page/program save, full ZIP checksums, exact import, double installation and draft/frozen isolation implemented. Nonempty assets/reference-data and separate editable-definition reconstruction remain open.');
}
async function authorization(h) {
  const business = require('./business_cases.cjs'), f = await pages.explicitFixture(h, undefined, undefined,
    { suffix: 'authdelivery', requestPrefix: 'authdelivery-', prepareDelivery: roundtrip });
  let primary;
  try {
    const auth = f.revision.application.authorization;
    h.check('Frozen default authorization uses one initial application-level data contract without entity ACLs', auth?.apiVersion === 'magic.application-authorization/v1' &&
      same(auth.dataAccess.map(v => v.operation).sort(), ['delete', 'read', 'write']) && auth.dataAccess.every(v => same(Object.keys(v), ['operation'])) && auth.entityActions.length === 0, auth);
    const outsider = await business.member(h, 'outsider'), manager = await business.member(h, 'manager');
    const roles = await h.directory(h.admin, '/cas/namespaces/panel/roles/');
    for (let index = 0; index < f.installations.length; index++) {
      const i = f.installations[index], module = '/applications/' + i.deploymentId, scoped = roles.filter(v => v.module === module);
      h.check('Independent CAS directory registers each frozen data role for this exact installation',
        ['application-data-read', 'application-data-write', 'application-data-delete'].every(key => scoped.filter(v => v.key === key && v.status === 2).length === 1), scoped);
      const context = await business.runtime(h, f, index, manager);
      h.denied(await h.api(outsider, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + i.deploymentId), 'Formal registration does not grant an ordinary unassigned account runtime access');
      h.check('Registered installation remains the exact owner identity', context.identity.installationId === String(i.id));
    }
    const current = await a.draft(h, f.application), changed = structuredClone(current.entities); changed[0].description = 'Unpublished authorization fixture edit';
    await a.save(h, f.application, current, changed);
    h.check('Editable draft update does not modify frozen authorization or current CAS role directory', same((await h.ok(h.admin, 'GET', base + f.application.id + '/revisions/' + f.revision.id)).value, f.revision) && same(await h.directory(h.admin, '/cas/namespaces/panel/roles/'), roles));
  } catch (error) { primary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, f, primary); }
  await h.partial('Default application read/write/delete freeze, ZIP import, exact-instance CAS role registration and no implicit account grant implemented. Explicit built-in dependencies, action/extensions, Endpoint no-grant and old-ACL rejection remain open.');
}
async function upgradeAdmission(h) {
  const { fixture } = require('./delivery_cases.cjs'), f = await fixture(h), before = [];
  for (const i of f.installations) before.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value);
  const directories = ['/panel/application/deployment-requests/', '/panel/operations/namespaces/panel/application-deployment-operations/'];
  const snapshots = [];
  for (const route of directories) snapshots.push(await h.directory(h.admin, route));
  for (const i of before) {
    const response = await h.api(h.admin, 'POST', '/panel/application/installations/' + i.id + '/upgrade-preview', { packageId: f.package.id, expectedDigest: f.package.artifactDigest });
    h.check('Same published version is refused at precise upgrade version gate before execution', require('./deployment_review_cases.cjs').refusal(response, '目标必须是更新的正式发布版本；相同版本重试请恢复原操作，首期不支持降级'), response);
  }
  for (const [index, route] of directories.entries()) h.check('Upgrade preflight refusals create no replacement request or operation', same(await h.directory(h.admin, route), snapshots[index]));
  for (const i of before) h.check('Version refusal preserves entire original installed peer', same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + i.id)).value, i));
  await h.partial('Same-version formal upgrade preflight and exact peer/request/operation preservation implemented. Lower version, Schema/write-rule/interface changes, actual approval fence and native upgrade refusal remain open.');
}
const handlers = { 'F020-001': model, 'F020-004': authorization, 'F033-005': upgradeAdmission };
for (const fn of Object.values(handlers)) { fn.transport = 'owner-api'; fn.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers, archive, roundtrip, portableEntities };
