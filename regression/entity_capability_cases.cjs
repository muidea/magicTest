const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const delivery = require('./model_delivery.cjs');
const definitions = '/panel/application/definitions/';
const variants = [
  ['unknown', e => { e.serviceExpose.capabilities[0].key = 'unsupported-operation'; }],
  ['duplicate', e => { e.serviceExpose.capabilities.push(structuredClone(e.serviceExpose.capabilities[0])); }],
  ['null-item', e => { e.serviceExpose.capabilities.push(null); }],
  ['empty-key', e => { e.serviceExpose.capabilities[0].key = ''; }],
];
async function rejected(h, app, before, invalid, label, collect = false) {
  const route = definitions + app.id + '/model-draft', payload = a.command(before, [invalid]);
  const findings = [];
  for (const [method, suffix] of [['POST', '/check'], ['PUT', '']]) {
    const parent = h.state.resources.find(r => r.kind === 'definition' && r.id === app.id);
    if (!parent?.creation?.ownershipConfirmed || parent.capabilityAdmission?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original capability admission intent unresolved; no repeat');
    const c = { method, route: route + suffix, payload: structuredClone(payload), outcome: 'unknown' };
    (parent.capabilityAdmission ||= []).push(c); h.persist();
    c.response = await h.api(h.admin, method, c.route, payload); h.persist();
    const current = await a.draft(h, app);
    const refused = [200, 400, 409, 422].includes(c.response.status) && [4, 18, 21].includes(c.response.data?.error?.code) &&
      /capabilit|能力|serviceExpose/i.test(c.response.data.error.message) && c.response.data.value == null;
    if (same(current, before) && (refused || method === 'POST' && h.good(c.response))) {
      c.outcome = refused ? 'rejected-and-unchanged' : 'invalid-preflight-accepted-without-write'; h.persist();
    } else if (method === 'PUT' && h.good(c.response) && same(current, c.response.data.value)) {
      c.outcome = 'invalid-save-accepted-and-independently-confirmed'; h.persist();
    }
    if (collect) {
      if (c.outcome === 'unknown') throw new h.Blocked('Original capability command lacks exact semantic disposition; no further admission commands');
      const finding = { label, method, definitionId: app.id, outcome: c.outcome, refused, unchanged: same(current, before) };
      findings.push(finding); h.observe({ kind: 'capability-admission-result', ...finding });
    } else {
      h.check('Formal ' + method + ' rejects ' + label + ' capability declaration at its own semantic validation', refused, c.response);
      h.check('Rejected capability declaration preserves the complete original model', same(current, before));
    }
  }
  return findings;
}
async function admission(h) {
  await require('./delivery_cases.cjs').fixture(h);
  const findings = [];
  // Each counterexample owns a separate draft. An acknowledged invalid save
  // must not become another probe's baseline or require a synthetic rollback.
  for (const [index, [label, mutate]] of variants.entries()) {
    const sample = await a.definition(h, 'capability' + index), valid = a.newEntity(h, sample);
    valid.serviceExpose = { enabled: true, capabilities: [{ key: 'query', enabled: true }] };
    const baseline = await a.save(h, sample, await a.draft(h, sample), [valid]);
    const invalid = structuredClone(baseline.entities[0]); mutate(invalid);
    findings.push(...await rejected(h, sample, baseline, invalid, label, true));
  }
  const app = await a.definition(h, 'capability'), entity = a.newEntity(h, app);
  entity.serviceExpose = { enabled: true, capabilities: [{ key: 'query', enabled: true }] };
  const original = await a.save(h, app, await a.draft(h, app), [entity]);
  const closed = structuredClone(original.entities[0]); closed.serviceExpose.enabled = false;
  const disabled = await a.save(h, app, original, [closed]);
  h.check('Definition owner retains total exposure disabled independently of its enabled query declaration', same(disabled.entities[0].serviceExpose, closed.serviceExpose));
  const f = await delivery.publish(h, app);
  h.check('Formal publication freezes the exact total-disabled entity capability declaration',
    f.revision.entities.length === 1 && same(f.revision.entities[0].serviceExpose, closed.serviceExpose));
  const reopened = structuredClone(disabled.entities[0]); reopened.serviceExpose.enabled = true;
  await a.save(h, app, await a.draft(h, app), [reopened]);
  h.check('Unpublished capability edit leaves original immutable revision and package unchanged',
    same((await h.ok(h.admin, 'GET', definitions + app.id + '/revisions/' + f.revision.id)).value, f.revision) &&
    same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + f.package.id)).value, f.package));
  await delivery.retained(h, f.resource);
  h.check('All independent invalid capability declarations are semantically rejected by both check and save without model mutation',
    findings.length === variants.length * 2 && findings.every(f => f.refused && f.unchanged), findings);

  const pages = require('./page_runtime_cases.cjs'), { authorFixture: pageAuthor } = require('./page_author_cases.cjs'), business = require('./business_cases.cjs');
  const fx = await pages.explicitFixture(h, undefined, undefined, {
    suffix: 'capdisabled',
    requestPrefix: 'capdisabled-',
    prepareAuthor: async (h, authored) => {
      const current = await a.draft(h, authored.app), entity = structuredClone(current.entities[0]);
      entity.serviceExpose = { enabled: false, capabilities: [{ key: 'get', enabled: true }] };
      authored.model = await a.save(h, authored.app, current, [entity]);
      authored.pages = await pageAuthor.read(h, authored.app, 'pages');
    },
  });
  let fxPrimary;
  try {
    const installed = fx.installations[0], rtUuid = installed.receipt.runtimeApplicationUuid;
    const manager = await business.member(h, 'manager');
    const rt = (await h.ok(manager, 'GET', '/apps/application/runtimes/' + fx.application.name + '?deploymentId=' + installed.deploymentId)).value;
    const rtEntity = rt.entities?.find(e => e.entity?.pkgPath === fx.revision.entities[0].pkgPath && e.entity?.name === fx.revision.entities[0].name);
    h.check('Installed runtime metadata reflects total-disabled service exposure cleanly', !rtEntity?.serviceExpose?.enabled, rtEntity);
    const hubCaps = await h.directory(h.admin, '/panel/hub/capabilitys/');
    const leakedCaps = hubCaps.filter(c => c.application?.uuid === rtUuid || c.runtimeApplicationUuid === rtUuid || c.deploymentId === installed.deploymentId);
    h.check('Panel capability directory registers zero exposed capabilities for total-disabled installed entity', leakedCaps.length === 0, leakedCaps);
    const svcAttempt = await h.api(h.admin, 'POST', '/panel/hub/services/', {
      name: h.state.prefix + '_capdisabled_svc',
      displayName: '总开关关闭禁止服务',
      type: 'external',
      capabilities: [],
    });
    h.check('Cannot create a service consumer around empty capability list from total-disabled entity', !h.good(svcAttempt), svcAttempt);
  } catch (error) { fxPrimary = error; throw error; }
  finally { await pages.disposeExplicitFixture(h, fx, fxPrimary); }
}
admission.transport = 'owner-api';
module.exports = { handlers: { 'F019-003': admission }, rejected, variants };
