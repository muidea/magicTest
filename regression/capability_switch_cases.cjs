// Frozen author switches must agree with the receipt-bound runtime catalogue.
const { isDeepStrictEqual: same } = require('node:util');
const { authoring: author } = require('./authoring_cases.cjs');
const delivery = require('./model_delivery.cjs');
const review = require('./deployment_review_cases.cjs');
const operations = ['query', 'get', 'create', 'update', 'delete'];
const route = '/panel/hub/capabilitys/';
function matrix(h, app) {
  return ['all', 'closed', ...operations].map((name, index) => {
    const entity = author.newEntity(h, app);
    entity.name = 'switch' + index;
    entity.showName = '能力开关 ' + name;
    entity.uniqueConstraints[0].name = 'uq_switch' + index + '_code';
    entity.serviceExpose = { enabled: name !== 'closed', capabilities: operations.map(key => ({ key, enabled: name !== key })) };
    return entity;
  });
}
function catalogueMatches(f, installation, values, namespace) {
  const receipt = installation?.receipt;
  if (!receipt || typeof namespace !== 'string' || !namespace || installation.namespace !== namespace || installation.sourceDigest !== f.package.artifactDigest ||
      receipt.revisionId !== f.revision.id || receipt.revisionDigest !== f.package.artifactDigest ||
      !Number.isSafeInteger(receipt.runtimeApplicationId) || receipt.runtimeApplicationId <= 0 || !receipt.runtimeApplicationUuid ||
      receipt.entities?.length !== f.revision.entities.length || !Array.isArray(values)) return false;
  const expected = [], entities = new Set(), definitions = new Set();
  for (const source of f.revision.entities) {
    // Published entities intentionally drop editable database IDs. Their
    // frozen package key is the canonical identity, also present in receipts.
    const pkgKey = source.pkgPath + '/' + source.name;
    const matches = receipt.entities.filter(e => e.definitionEntityId === source.id && e.pkgKey === pkgKey);
    if (matches.length !== 1 || !Number.isSafeInteger(matches[0].runtimeEntityId) || matches[0].runtimeEntityId <= 0 ||
        entities.has(matches[0].runtimeEntityId) || definitions.has(pkgKey)) return false;
    entities.add(matches[0].runtimeEntityId); definitions.add(pkgKey);
    for (const capability of source.serviceExpose.capabilities) if (source.serviceExpose.enabled && capability.enabled)
      expected.push({ source, runtimeId: matches[0].runtimeEntityId, key: capability.key });
  }
  if (values.length !== expected.length || new Set(values.map(v => v.id)).size !== values.length || new Set(values.map(v => v.key)).size !== values.length) return false;
  return expected.every(({ source, runtimeId, key }) => values.filter(v => {
    let options; try { options = JSON.parse(v.options); } catch { return false; }
    return Number.isSafeInteger(v.id) && v.id > 0 && v.runtimeApplication?.runtimeApplicationUUID === receipt.runtimeApplicationUuid &&
      v.runtimeApplication.applicationKey === installation.applicationKey && v.runtimeApplication.instanceKey === installation.instanceKey && v.status === 1 && v.kind === key &&
      v.key === source.name + '_' + key && v.providerType === 'application' && v.providerKey === receipt.runtimeApplicationUuid && v.sourceType === 'entity' &&
      options.generated === true && options.source === 'entity' && options.capability === key && options.status === 1 &&
      options.runtimeApplicationID === receipt.runtimeApplicationId && options.runtimeApplicationUUID === receipt.runtimeApplicationUuid &&
      options.runtimeEntityID === runtimeId && options.runtimeEntityName === source.name && options.runtimeEntityPkgPath === source.pkgPath &&
      options.runtimeEntityPkgKey === source.pkgPath + '/' + source.name;
  }).length === 1);
}
async function switches(h) {
  await require('./delivery_cases.cjs').fixture(h);
  const app = await author.definition(h, 'capswitch');
  const saved = await author.save(h, app, await author.draft(h, app), matrix(h, app));
  const f = await delivery.publish(h, app);
  h.check('Immutable revision freezes every whole and individual operation switch exactly',
    f.revision.entities.length === 7 && saved.entities.every(e => f.revision.entities.some(v => v.name === e.name && v.pkgPath === e.pkgPath && same(v.serviceExpose, e.serviceExpose))));
  h.admin.id = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account.id;
  const r = await review.create(h, f, 'capswitch'); delivery.linkRequest(h, f, r);
  let primary;
  try {
    await review.approve(h, r, [h.admin]);
    const source = r.installation.receipt.runtimeApplicationUuid;
    const read = () => h.directory(h.admin, route, { pageSize: 2 });
    const before = await read(), owned = before.filter(v => v.providerKey === source);
    h.check('Complete installed capability catalogue matches all receipt-bound enabled pairs and excludes every disabled pair', catalogueMatches(f, r.installation, owned, h.admin.identity.namespace), owned);
    const current = await author.draft(h, app), changed = structuredClone(current.entities);
    for (const entity of changed) {
      entity.serviceExpose.enabled = !entity.serviceExpose.enabled;
      for (const capability of entity.serviceExpose.capabilities) capability.enabled = !capability.enabled;
    }
    await author.save(h, app, current, changed);
    h.check('Unpublished switch changes preserve original frozen revision and package',
      same((await h.ok(h.admin, 'GET', '/panel/application/definitions/' + app.id + '/revisions/' + f.revision.id)).value, f.revision) &&
      same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + f.package.id)).value, f.package));
    h.check('Unpublished switch changes preserve every exact original installed capability', same((await read()).filter(v => v.providerKey === source), owned));
    await review.cleanup(h, r);
    const after = await read();
    h.check('Formal original installation destroy retires its entire generated capability set and preserves peer catalogues',
      !after.some(v => v.providerKey === source) && same(after, before.filter(v => v.providerKey !== source)));
  } catch (error) { primary = error; throw error; }
  finally {
    try { if (r.phase !== 'deleted') await review.cleanup(h, r); await delivery.retained(h, f.resource); }
    catch (error) { h.observe({ kind: 'original-capability-switch-cleanup-open', requestId: r.id, message: error.message }); if (!primary) throw error; }
  }
  await h.partial('Whole/per-operation switches, exact frozen receipt-bound catalogue, unpublished edit isolation and original capability retirement verified. Real generated-service calls and republished enabled-to-disabled transition remain unverified; catalogue absence is not a runtime invocation refusal.');
}
switches.transport = 'owner-api';
module.exports = { handlers: { 'F019-001': switches }, matrix, catalogueMatches };
