// Ordinary files only. Bound business references have separate owner contracts.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { fileTransfer } = require('./owner_transport.cjs');
const {
  PORTAL_CORE_KEY,
  PORTAL_SELF_FILES_KEY,
  PLATFORM_MGMT_FILES_VIEWER_KEY,
  PLATFORM_MGMT_FILES_EDITOR_KEY,
  PLATFORM_MGMT_FILES_MANAGER_KEY,
  validatePlatformSystemProfiles,
} = require('./platform_profiles.cjs');
const handlers = {}, self = '/files/self/files/', managed = '/files/';
const hash = b => 'sha256:' + crypto.createHash('sha256').update(b).digest('hex');
const validID = id => Number.isSafeInteger(id) && id > 0;
const absent = r => [200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
function original(h, actor, r) {
  if (!actor || actor.origin !== r.origin || !same(actor.identity, r.actorIdentity)) throw new h.Blocked('Ordinary file requires exact original creator and tenant');
}
function matches(value, r) { return value?.id === r.id && value.token === r.token && value.name === r.name && value.path === r.path; }
const idRoute = r => r.base + r.id + (r.base === managed ? '?' + new URLSearchParams({ fileSource: r.source }) : '');
const downloadRoute = r => r.base === self ? self + 'download/?' + new URLSearchParams({ fileToken: r.token }) : '/files' + r.path + '?' + new URLSearchParams({ fileToken: r.token });
async function createFile(h, actorName, visibility) {
  const actor = h[actorName], suffix = crypto.randomBytes(8).toString('hex'), name = 'proof-' + suffix + '.bin';
  const source = h.state.prefix + '-' + suffix, relative = h.state.prefix + '/' + suffix, own = visibility === 'self';
  const body = Buffer.concat([Buffer.from('Original file bytes\0\r\n中文 Δ ' + suffix), Buffer.from([0, 255, 128])]);
  const base = own ? self : managed, query = new URLSearchParams({ 'key-name': 'file', filePath: relative });
  if (!own) { query.set('fileSource', source); query.set('fileScope', visibility === 'public' ? 'share' : source); }
  const r = { kind: 'ordinary-file', phase: 'intent', actorName, actorIdentity: structuredClone(actor.identity), origin: actor.origin, visibility, base, source, relative, name, expectedDigest: hash(body), expectedSize: body.length, uploadRoute: base + 'upload/?' + query, creation: { outcome: 'unknown' } };
  h.state.resources.push(r); h.persist(); original(h, actor, r);
  const response = await fileTransfer(actor, 'POST', r.uploadRoute, { name, bytes: body }, h.observe);
  r.creation.response = response;
  if (h.good(response) && typeof response.data.value?.token === 'string' && response.data.value.token) r.token = response.data.value.token;
  h.persist(); h.check('Original finite file upload acknowledges exact name and opaque token', h.good(response) && response.data.value?.name === name && !!r.token, response);
  r.view = base + 'view/?' + new URLSearchParams({ fileToken: r.token, ...(own ? {} : { fileSource: source }) });
  const view = (await h.ok(actor, 'GET', r.view)).value;
  if (validID(view?.id)) { r.id = view.id; r.path = view.path; }
  h.persist();
  h.check('Independent File owner view confirms exact original token, name and safe stored path', validID(r.id) && matches(view, r) && typeof r.path === 'string' && r.path.startsWith('/static/' + (visibility === 'public' ? 'share/' : 'private/')) && !r.path.includes('..') && r.path.endsWith('/' + name), view);
  h.check('Independent exact file-ID/source read matches original owner metadata', same((await h.ok(actor, 'GET', idRoute(r))).value, view));
  r.download = downloadRoute(r);
  r.creation.outcome = 'confirmed'; r.phase = 'created'; h.persist();
  const bytes = await fileTransfer(actor, 'GET', r.download, undefined, h.observe);
  h.check('File download independently returns original binary bytes', bytes.status === 200 && Buffer.isBuffer(bytes.data.bytes) && bytes.data.bytes.equals(body), { status: bytes.status, digest: bytes.data.bytes && hash(bytes.data.bytes), size: bytes.data.bytes?.length });
  return r;
}
async function cleanup(h, r) {
  const actor = h[r.actorName]; original(h, actor, r);
  if (r.creation?.outcome !== 'confirmed') await reconcileAcknowledgedFile(h, r);
  if (r.creation?.outcome !== 'confirmed' || !validID(r.id) || !r.token || !r.path) throw new h.Blocked('Unresolved original file creation; never guess file ID or replay upload');
  const current = await h.api(actor, 'GET', idRoute(r));
  if (!absent(current)) {
    h.check('File deletion reads exact original owner metadata', h.good(current) && matches(current.data.value, r), current);
    if (r.deletion) throw new h.Blocked('Original file DELETE unresolved; never replay');
    r.deletion = { outcome: 'unknown' }; h.persist();
    const response = await h.api(actor, 'DELETE', idRoute(r)); r.deletion.response = response; h.persist();
    h.check('Formal File delete acknowledges original exact identity', h.good(response) && matches(response.data.value, r), response);
    r.deletion.outcome = 'acknowledged'; h.persist();
  } else if (r.deletion?.outcome !== 'acknowledged') throw new h.Blocked('File absence has no acknowledged original delete');
  h.check('Independent exact File ID/source is absent after original delete', absent(await h.api(actor, 'GET', idRoute(r))));
  h.check('Independent original opaque token no longer returns metadata', absent(await h.api(actor, 'GET', r.view)));
  const bytes = await fileTransfer(actor, 'GET', r.download, undefined, h.observe);
  h.check('Original byte route is inaccessible after acknowledged File delete', (bytes.status === 404 || r.visibility === 'private' && bytes.status === 403) && !bytes.data?.bytes, { status: bytes.status });
  r.phase = 'deleted'; h.persist(); return { proof: 'Original upload/token->owner-ID/source, formal exact File DELETE and independent ID/token absence and byte-route inaccessibility; private route denial does not claim an independent filesystem inspection' };
}
async function reconcileAcknowledgedFile(h, r) {
  const actor = h[r.actorName]; original(h, actor, r);
  const ack = r.creation?.response, query = new URL(r.uploadRoute || '/', r.origin).searchParams;
  if (!h.good(ack || { status: 0, data: {} }) || ack.data.value?.token !== r.token || ack.data.value?.name !== r.name || !r.token || !r.view || !validID(r.id) || !r.path || query.get('filePath') !== r.relative || query.get('key-name') !== 'file' || r.base === managed && query.get('fileSource') !== r.source || r.deletion) throw new h.Blocked('Unresolved original file creation; no accepted exact token/ID/source proof, never replay upload');
  const view = await h.ok(actor, 'GET', r.view), byID = await h.ok(actor, 'GET', idRoute(r));
  h.check('Original accepted opaque token and exact ID/source independently resolve the original file', matches(view.value, r) && same(byID.value, view.value), view);
  r.download = downloadRoute(r);
  const content = await fileTransfer(actor, 'GET', r.download, undefined, h.observe);
  h.check('Original acknowledged upload bytes independently match private intended digest and size', content.status === 200 && Buffer.isBuffer(content.data.bytes) && content.data.bytes.length === r.expectedSize && hash(content.data.bytes) === r.expectedDigest, { status: content.status, size: content.data.bytes?.length, digest: content.data.bytes && hash(content.data.bytes) });
  r.creation.recovery = { originalOutcome: r.creation.outcome, proof: 'Accepted original upload token/name, independent original ID/source and token view equality, exact original expected bytes; no new upload' };
  r.creation.outcome = 'confirmed'; r.phase = 'created'; h.persist();
}
// An explicit recovery disposition, separate from the functional HTTP404
// assertion. Never accept HTTP500 as a passing case or resend the DELETE.
async function reconcileOwnerDeletedFile(h, r, proof) {
  const actor = h[r.actorName]; original(h, actor, r);
  const staticSuffix = typeof r.path === 'string' && r.path.slice('/static'.length);
  const root = proof?.rootDirectory;
  const valid = r.visibility === 'public' && r.creation?.outcome === 'confirmed' && r.deletion?.outcome === 'acknowledged' && h.good(r.deletion.response) && matches(r.deletion.response.data.value, r) &&
    proof?.kind === 'magicfile-static-missing' && proof.sourceContainer === 'magicFile' && proof.fileID === r.id && proof.namespace === r.actorIdentity.namespace && proof.originalPath === r.path &&
    /^\/static\/share\/[A-Za-z0-9_./-]+$/.test(r.path) && !r.path.includes('..') && typeof root === 'string' && root.startsWith('/') && !root.endsWith('/') && !root.includes('..') && !/[\s"\x00-\x1f]/.test(root) &&
    typeof proof.sourceLine === 'string' && proof.sourceLine.includes('WARN failed to serve static file path=' + staticSuffix + ' err="open ' + root + staticSuffix + ': no such file or directory"') &&
    proof.sourceLogSha256 === hash(Buffer.from(proof.sourceLine));
  if (!valid) throw new h.Blocked('Original File disposition requires acknowledged exact DELETE and exact missing-physical-path owner log; no guessed identity or replay');
  h.check('Independent original file ID/source remains absent for owner-confirmed disposition', absent(await h.api(actor, 'GET', idRoute(r))));
  h.check('Independent original opaque token remains absent for owner-confirmed disposition', absent(await h.api(actor, 'GET', r.view)));
  const result = await fileTransfer(actor, 'GET', r.download, undefined, h.observe);
  h.check('Original public byte route returns no content during exact owner-proven disposition', result.status === 404 || result.status === 500 && result.data?.text === '');
  r.recovery = { kind: 'owner-proven-original-file-deletion', originalFileID: r.id, sourceLogSha256: proof.sourceLogSha256, originalPath: r.path,
    sourceContainer: proof.sourceContainer, rootDirectory: root, byteRouteStatus: result.status, functionalRouteDefectOpen: result.status !== 404,
    proof: 'Acknowledged exact original DELETE, independent ID/source and token absence, exact original physical-path File warning; no upload or DELETE replay. Functional status-code failure remains unchanged.' };
  r.phase = 'deleted'; h.persist();
  h.observe({ kind: 'original-file-deletion-disposition', ...r.recovery });
  return r.recovery;
}
async function anonymous(h, origin, namespace, action) {
  const context = await h.browser.newContext({ ignoreHTTPSErrors: true });
  const actor = { origin, context, identity: { account: 'anonymous', namespace } };
  try { return await action(actor); } finally { await context.close(); }
}
handlers['F049-001'] = async h => {
  // Establish that the public file route reaches a missing-file boundary before
  // creating bytes. A SPA fallback or upstream error must fail here rather than
  // accumulating files which this candidate cannot independently retire.
  await anonymous(h, h.tenantAdmin.origin, h.tenantAdmin.identity.namespace, async actor => {
    const probe = '/static/share/regression-missing-' + crypto.randomBytes(16).toString('hex') + '/proof.bin';
    const result = await fileTransfer(actor, 'GET', probe, undefined, h.observe);
    h.check('Public shared-file entry rejects an unknown file as HTTP404 before any upload', result.status === 404 && !result.data?.bytes, { status: result.status, returnedText: typeof result.data?.text === 'string' });
  });
  const shared = await createFile(h, 'tenantAdmin', 'public'), privateFile = await createFile(h, 'tenantAdmin', 'private');
  await anonymous(h, h.tenantAdmin.origin, h.tenantAdmin.identity.namespace, async actor => {
    const bytes = await fileTransfer(actor, 'GET', shared.path, undefined, h.observe);
    h.check('Independent anonymous public share read returns exact original content', bytes.status === 200 && hash(bytes.data?.bytes || Buffer.alloc(0)) === shared.expectedDigest, { status: bytes.status, size: bytes.data.bytes?.length });
  });
  await cleanup(h, shared);
  const retained = await fileTransfer(h.tenantAdmin, 'GET', privateFile.download, undefined, h.observe);
  h.check('Deleting original shared file preserves independent private file', retained.status === 200 && hash(retained.data.bytes || Buffer.alloc(0)) === privateFile.expectedDigest);
  await cleanup(h, privateFile);

  const ns = h.tenantAdmin.identity.namespace;
  const templates = await h.directory(h.tenantAdmin, '/cas/namespaces/' + ns + '/role-templates/');
  const profileCheck = validatePlatformSystemProfiles(templates, { namespaceClass: 'tenant', requireMagicFile: true });
  h.check('Namespace projects all four magicFile fine-grained system-profiles alongside platform core profiles', profileCheck.ok, profileCheck);

  const seed = await createFile(h, 'tenantAdmin', 'private');
  const viewerAcc = await h.createAs('tenantAdmin', '/cas/namespaces/' + ns + '/accounts/', { account: h.state.prefix + '-file-viewer', displayName: '文件只读', password: h.state.password, status: 2, roleTemplateKeys: [PORTAL_CORE_KEY, PLATFORM_MGMT_FILES_VIEWER_KEY] }, 'account');
  const editorAcc = await h.createAs('tenantAdmin', '/cas/namespaces/' + ns + '/accounts/', { account: h.state.prefix + '-file-editor', displayName: '文件编辑', password: h.state.password, status: 2, roleTemplateKeys: [PORTAL_CORE_KEY, PLATFORM_MGMT_FILES_EDITOR_KEY] }, 'account');
  const managerAcc = await h.createAs('tenantAdmin', '/cas/namespaces/' + ns + '/accounts/', { account: h.state.prefix + '-file-manager', displayName: '文件管理', password: h.state.password, status: 2, roleTemplateKeys: [PORTAL_CORE_KEY, PLATFORM_MGMT_FILES_MANAGER_KEY] }, 'account');
  const viewer = await h.login(viewerAcc.account, h.state.password, ns, h.state.password + 'V');
  const editor = await h.login(editorAcc.account, h.state.password, ns, h.state.password + 'E');
  const manager = await h.login(managerAcc.account, h.state.password, ns, h.state.password + 'M');

  const viewerDownload = await fileTransfer(viewer, 'GET', seed.download, undefined, h.observe);
  h.check('file-viewer reads managed file bytes with exact digest', viewerDownload.status === 200 && hash(viewerDownload.data?.bytes || Buffer.alloc(0)) === seed.expectedDigest);
  h.check('file-viewer reads managed file metadata', h.good(await h.api(viewer, 'GET', seed.view)));
  const viewerUpload = await fileTransfer(viewer, 'POST', managed + 'upload/?' + new URLSearchParams({ 'key-name': 'file', filePath: h.state.prefix + '/v-denied', fileSource: h.state.prefix + '-v', fileScope: h.state.prefix + '-v' }), { name: 'denied.bin', bytes: Buffer.from('x') }, h.observe);
  h.check('file-viewer cannot upload managed file', !h.good(viewerUpload) && viewerUpload.status === 403, viewerUpload);
  h.denied(await h.api(viewer, 'DELETE', idRoute(seed)), 'file-viewer cannot delete managed file');

  const editorDownload = await fileTransfer(editor, 'GET', seed.download, undefined, h.observe);
  h.check('file-editor reads managed file bytes with exact digest', editorDownload.status === 200 && hash(editorDownload.data?.bytes || Buffer.alloc(0)) === seed.expectedDigest);
  h.denied(await h.api(editor, 'DELETE', idRoute(seed)), 'file-editor cannot delete managed file');

  h._fileMatrixEditor = editor;
  const editorFile = await createFile(h, '_fileMatrixEditor', 'private');
  delete h._fileMatrixEditor;
  h.denied(await h.api(editor, 'DELETE', idRoute(editorFile)), 'file-editor cannot delete its own managed upload');
  const managerDel = await h.api(manager, 'DELETE', idRoute(editorFile));
  h.check('file-manager deletes managed file uploaded by editor', h.good(managerDel) && matches(managerDel.data?.value, editorFile), managerDel);
  h.check('Deleted editor file ID is absent from independent owner read', absent(await h.api(manager, 'GET', idRoute(editorFile))));
  editorFile.deletion = { outcome: 'acknowledged', response: managerDel };
  editorFile.phase = 'deleted';
  h.persist();

  h._fileMatrixManager = manager;
  const managerFile = await createFile(h, '_fileMatrixManager', 'private');
  const mgrDelSelf = await h.api(manager, 'DELETE', idRoute(managerFile));
  delete h._fileMatrixManager;
  h.check('file-manager uploads and deletes managed file completely', h.good(mgrDelSelf) && matches(mgrDelSelf.data?.value, managerFile), mgrDelSelf);
  h.check('Deleted manager file ID is absent from independent owner read', absent(await h.api(manager, 'GET', idRoute(managerFile))));
  managerFile.deletion = { outcome: 'acknowledged', response: mgrDelSelf };
  managerFile.phase = 'deleted';
  h.persist();

  await cleanup(h, seed);
};
handlers['F049-002'] = async h => {
  const r = await createFile(h, 'user', 'self');
  const ns = h.user.identity.namespace;
  const account = await h.create('/cas/namespaces/' + ns + '/accounts/', { account: h.state.prefix + '-file-peer-' + crypto.randomBytes(4).toString('hex'), displayName: '个人文件同租户对照', password: h.state.password, status: 2, roleTemplateKeys: [PORTAL_CORE_KEY, PORTAL_SELF_FILES_KEY] }, 'account');
  const peer = await h.login(account.account, h.state.password, ns, h.state.password + 'F');
  for (const actor of [peer, h.otherTenantAdmin]) {
    const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
    h.check('Negative file reader has its own valid original account and tenant', session.account.account === actor.identity.account && session.homeNamespace === actor.identity.namespace);
    for (const route of [self + r.id, r.view]) h.inaccessible(await h.api(actor, 'GET', route), 'Different subject/tenant cannot obtain private file metadata');
    const bytes = await fileTransfer(actor, 'GET', r.download, undefined, h.observe);
    h.check('Different subject/tenant cannot download original private bytes', bytes.status === 404 && !bytes.data?.bytes, { status: bytes.status });
  }
  const originalBytes = await fileTransfer(h.user, 'GET', r.download, undefined, h.observe);
  h.check('Original owner bytes remain intact after all foreign probes', originalBytes.status === 200 && hash(originalBytes.data.bytes || Buffer.alloc(0)) === r.expectedDigest);
};
for (const [id, handler] of Object.entries(handlers)) { handler.actors = id === 'F049-001' ? ['tenantAdmin'] : ['user', 'otherTenantAdmin']; handler.transport = 'owner-api'; }
module.exports = { handlers, cleanup, createFile, reconcileAcknowledgedFile, reconcileOwnerDeletedFile };
