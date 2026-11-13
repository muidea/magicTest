const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const page = require('./page_runtime_cases.cjs');
const business = require('./business_cases.cjs');
const delivery = require('./model_delivery.cjs');
const metadata = require('./definition_metadata_cases.cjs');
const { authorFixture: author } = require('./page_author_cases.cjs');
const { packageContent } = require('./owner_transport.cjs');
const { sameTarget } = require('./portal_overview_cases.cjs');
// The same finite PNG fixture used by the owner contract tests; no fetched art.
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=';
const bytes = Buffer.from(image.split(',')[1], 'base64');
const digest = value => 'sha256:' + crypto.createHash('sha256').update(value).digest('hex');
function acknowledgedImageSaveMatches(before, payload, ack, current) {
  if (!before || !payload || !ack || !current || ![image, before.icon].includes(payload.icon) || typeof payload.icon !== 'string') return false;
  const submitted = structuredClone(payload);
  // The existing storage DTO omits its empty optional versionConstraint.
  // Only this precise UI-added empty field has an equivalent owner shape.
  if (!Object.hasOwn(before.storage || {}, 'versionConstraint') && submitted.storage?.versionConstraint === '') delete submitted.storage.versionConstraint;
  const expected = metadata.command(before, { icon: payload.icon });
  return same(submitted, expected) && Number.isSafeInteger(ack.updateTime) && ack.updateTime > before.updateTime &&
    same(current, ack) && same(ack, { ...before, icon: payload.icon, updateTime: ack.updateTime });
}
function uploadedImageMatches(before, payload, ack, current) {
  return payload?.icon === image && acknowledgedImageSaveMatches(before, payload, ack, current);
}
async function reconcileImageUpload(h, r) {
  const intent = r.pendingAuthoringSave, before = r.metadataJournal?.original, created = r.creation?.response?.data?.value;
  if (r.kind !== 'definition' || r.collection !== '/panel/application/definitions/' || !r.creation?.ownershipConfirmed || !created ||
      created.id !== r.id || before?.id !== r.id || before.uuid !== created.uuid || before.name !== created.name || r.modelDelivery ||
      !same(h.admin.identity, r.creation.actorIdentity) || h.admin.origin !== r.creation.origin || intent?.confirmed !== false || intent.method !== 'PUT' ||
      intent.route !== r.collection + r.id || !/^[a-f0-9]{32}$/.test(intent.journalId || '') || !h.good(intent.response) ||
      !acknowledgedImageSaveMatches(before, intent.payload, intent.response.data.value, intent.response.data.value)) throw new h.Blocked('Exact original acknowledged image save proof required; no replay');
  const current = (await h.ok(h.admin, 'GET', intent.route)).value;
  h.check('Independent complete owner confirms exact original accepted image save and version without replay', acknowledgedImageSaveMatches(before, intent.payload, intent.response.data.value, current));
  if (!same(h.admin.identity, r.creation.actorIdentity) || h.admin.origin !== r.creation.origin) throw new h.Blocked('Original image save actor changed');
  intent.reconciliation = { originalJournalId: intent.journalId, definitionId: r.id, uuid: created.uuid, version: current.updateTime,
    expectedImageDigest: digest(bytes), originalSubmittedImagePersisted: intent.payload.icon === image, omittedEmptyStorageVersionConstraint: Object.hasOwn(intent.payload.storage || {}, 'versionConstraint'), noCommandReplayed: true };
  intent.confirmed = true; r.metadataJournal.last = current; h.persist(); return intent.reconciliation;
}
function verifyIconArchive(archive, app, expected) {
  if (!archive || archive.crcValid !== true || new Set(archive.names).size !== archive.names.length || archive.manifest?.apiVersion !== 'magic.model-package/v1' ||
      archive.manifest.kind !== 'ApplicationModelPackage' || archive.manifest.application?.uuid !== app.uuid || archive.manifest.application.key !== app.name ||
      !same(archive.manifest.icon, { path: 'assets/icon.png', mediaType: 'image/png', digest: digest(expected) }) ||
      archive.names.filter(n => n === 'assets/icon.png').length !== 1 || archive.payload !== expected.toString('base64') ||
      archive.checksums?.files?.filter(f => f.path === 'assets/icon.png' && f.size === expected.length && f.digest === digest(expected)).length !== 1) throw Error('Exact original icon ZIP bytes, manifest identity and checksum binding required');
}
async function prepare(h, authored) {
  const current = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + authored.app.id)).value;
  const r = metadata.track(h, current, false);
  authored.app = await metadata.write(h, r, { icon: image });
  authored.pages = await author.read(h, authored.app, 'pages');
  h.check('Metadata image command preserves exact model/pages identity and portable original PNG bytes', authored.app.icon === image && authored.pages.applicationId === authored.app.id && authored.pages.applicationUuid === authored.app.uuid);
}
async function prepareUpload(h, authored) {
  const current = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + authored.app.id)).value;
  const journal = metadata.track(h, current, false), browser = h.admin.page;
  await browser.goto(h.admin.origin + '/panel/application/definition/edit?aid=' + authored.app.id, { waitUntil: 'networkidle' });
  await browser.getByRole('heading', { name: '编辑应用定义', exact: true }).waitFor();
  await browser.locator('.ant-spin-spinning').waitFor({ state: 'hidden' });
  h.check('Original image author loads the exact owner metadata before input',
    await browser.locator('input#uuid').inputValue() === current.uuid && await browser.locator('input#name').inputValue() === current.name);
  const input = browser.locator('input[type="file"][accept="image/png,image/jpeg"]');
  h.check('Real author exposes one original image file input', await input.count() === 1);
  await input.setInputFiles({ name: 'original-regression.png', mimeType: 'image/png', buffer: bytes });
  const preview = browser.locator('img[alt="应用图标"]'); await preview.waitFor();
  h.check('Real FileReader upload preview retains exact original PNG bytes', await preview.getAttribute('src') === image);
  const replace = browser.locator('button').filter({ hasText: '更换图标' });
  h.check('Original image upload has one native replacement button inside Upload', await replace.count() === 1);
  await replace.waitFor();
  await h.screenshot(h.admin, 'original-image-upload-preview');
  await require('./definition_browser_cases.cjs').observeAuthorSave(h, authored.app, '/panel/application/definitions/' + authored.app.id,
    () => browser.getByRole('button', { name: /^保\s*存$/ }).click(), async intent => {
      const owner = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + authored.app.id)).value;
      h.check('Original image UI save uses exact initial definition version and complete metadata contract',
        uploadedImageMatches(current, intent.payload, intent.response.data.value, owner), owner);
      journal.last = owner; authored.app = owner; h.persist();
    });
  authored.pages = await author.read(h, authored.app, 'pages');
  await h.screenshot(h.admin, 'original-image-upload-saved');
}
async function iconProjection(h, f, actor, phase) {
  const entries = await h.directory(actor, '/portal/applications/', { idFormat: 'string' }), runtime = [];
  for (let index = 0; index < f.installations.length; index++) {
    const installation = f.installations[index], context = await business.runtime(h, f, index, actor);
    const value = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + installation.deploymentId)).value;
    const matching = entries.filter(e => e.deploymentId === installation.deploymentId && e.applicationUuid === f.application.uuid && e.sourceID === String(installation.receipt.runtimeApplicationId));
    h.check('Ordinary Portal and independent runtime retain exact original installed artwork and installation provenance',
      matching.length === 1 && matching[0].icon === image && value.application?.icon === image && same(value.readIdentity, context.identity), { entry: matching, runtime: value });
    runtime.push(value);
  }
  const browser = actor.page;
  for (const width of [1440, 390]) {
    await browser.setViewportSize({ width, height: 900 });
    await browser.goto(actor.origin + '/portal/', { waitUntil: 'networkidle' });
    await browser.getByRole('heading', { name: '门户工作台', exact: true }).waitFor();
    if (entries.length > 4) {
      const panel = browser.locator('.ant-card').filter({ has: browser.locator('.ant-card-head-title').getByText('我的应用', { exact: true }) });
      const all = panel.getByRole('button').filter({ hasText: new RegExp('^查看全部\\s*\\(' + entries.length + '\\)$') });
      h.check('Icon navigation retains one real view-all button with the independent complete owner count', await all.count() === 1);
      await all.click();
      await browser.waitForURL(url => sameTarget(url, new URL('/portal/applications/', actor.origin)));
    }
    for (const [index, installation] of f.installations.entries()) {
      const entry = entries.find(e => e.deploymentId === installation.deploymentId);
      const name = entry.showName || entry.name;
      const target = entries.length > 4 ? browser.locator('.magic-resource-card').filter({ has: browser.getByText(name, { exact: true }) }) : browser.getByRole('button', { name, exact: true });
      await target.waitFor();
      h.check('Icon consumer belongs to one exact original visible application card', await target.count() === 1);
      const img = target.locator('.ant-avatar img'); await img.waitFor();
      h.check('Original portal installation exposes exactly one image consumer', await img.count() === 1);
      const loaded = await img.evaluate(node => ({ src: node.getAttribute('src'), complete: node.complete, width: node.naturalWidth, height: node.naturalHeight }));
      h.check('Actual ordinary installed icon consumer decodes the exact original inline PNG at declared width', same(loaded, { src: image, complete: true, width: 1, height: 1 }), { width, index, loaded });
    }
    await h.screenshot(actor, 'installed-icon-' + phase + '-' + width);
  }
  return runtime;
}
async function survival(h, roundtrip = false) {
  const f = await page.explicitFixture(h, undefined, undefined, { suffix: roundtrip ? 'iconroundtrip' : 'iconretained', requestPrefix: roundtrip ? 'icon-roundtrip-' : 'icon-retained-', prepareAuthor: roundtrip ? prepareUpload : prepare,
    ...(roundtrip ? { prepareDelivery: async (h, f) => {
      const response = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
      h.check('Positive icon ZIP import uses real complete original download', response.status === 200 && Buffer.isBuffer(response.data.bytes));
      await delivery.importExact(h, f, response.data.bytes);
    } } : {}) });
  const actor = await business.member(h, 'manager'); let primary;
  try {
    h.check('Published immutable revision freezes original inline image', f.revision.application.icon === image);
    const download = await packageContent(h.admin, '/panel/application/model-packages/' + f.package.id + '/content', h.observe);
    h.check('Original icon package download contains real ZIP bytes', download.status === 200 && Buffer.isBuffer(download.data.bytes));
    const archive = JSON.parse(execFileSync('python3', ['-B', '-c', 'import io,sys,zipfile,json,base64\nz=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))\nprint(json.dumps({"crcValid":z.testzip() is None,"names":z.namelist(),"manifest":json.loads(z.read("package.json")),"checksums":json.loads(z.read("checksums.json")),"payload":base64.b64encode(z.read("assets/icon.png")).decode()}))'], { input: download.data.bytes, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }));
    verifyIconArchive(archive, f.application, bytes);
    h.observe({ kind: 'installed-original-icon-zip-binding', packageId: f.package.id, artifactDigest: f.package.artifactDigest,
      zipDigest: digest(download.data.bytes), imageDigest: digest(bytes), imageSize: bytes.length, icon: archive.manifest.icon });
    const before = await iconProjection(h, f, actor, 'before'), installationsBefore = [];
    for (const r of f.pageRequests) installationsBefore.push((await h.ok(h.admin, 'GET', '/panel/application/installations/' + r.installation.id)).value);
    const current = (await h.ok(h.admin, 'GET', '/panel/application/definitions/' + f.application.id)).value;
    h.check('New unpublished edit starts from independently read original published application and artwork', current.id === f.application.id && current.uuid === f.application.uuid && current.name === f.application.name && current.icon === image);
    // Publication advances the definition revision. Keep its prior author
    // journal intact and condition this separate edit on the current owner.
    const journal = metadata.track(h, current, true);
    await metadata.write(h, journal, { icon: 'appstore' });
    h.check('Unpublished image replacement preserves complete original published revision and both runtime projections',
      same((await h.ok(h.admin, 'GET', '/panel/application/definitions/' + f.application.id + '/revisions/' + f.revision.id)).value, f.revision) &&
      same(await iconProjection(h, f, actor, 'unpublished'), before));
    await delivery.removePackage(h, f);
    h.check('Formal allowed source package removal leaves complete original dual runtime/image metadata unchanged', same(await iconProjection(h, f, actor, 'source-removed'), before));
    for (const [index, r] of f.pageRequests.entries()) h.check('Source removal preserves exact original ready installation and immutable revision',
      same((await h.ok(h.admin, 'GET', '/panel/application/installations/' + r.installation.id)).value, installationsBefore[index]));
    const outsider = await business.member(h, 'outsider');
    const outsiderEntries = await h.directory(outsider, '/portal/applications/', { idFormat: 'string' });
    h.check('Ordinary account without either installation has no private icon/application projection', !outsiderEntries.some(e => f.installations.some(i => i.deploymentId === e.deploymentId)));
  } catch (error) { primary = error; throw error; }
  finally { await page.disposeExplicitFixture(h, f, primary); }
}
const handlers = { 'F050-001': h => survival(h, true), 'F050-002': h => survival(h) };
for (const handler of Object.values(handlers)) { handler.transport = 'owner-api'; handler.requiresOnlyDeliveryFixture = true; }
module.exports = { handlers, verifyIconArchive, uploadedImageMatches, acknowledgedImageSaveMatches, reconcileImageUpload };
