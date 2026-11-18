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
    const matches = receipt.entities.filter(e => (e.definitionEntityId === source.id || e.definitionEntityId === 0) && e.pkgKey === pkgKey);
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
async function callGateway(actor, method, route, apiKey, body) {
  return actor.page.evaluate(async ({ url, method, body, apiKey }) => {
    const response = await fetch(url, {
      method,
      credentials: 'omit',
      headers: { Authorization: 'ApiKey ' + apiKey, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(15000),
    });
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 500) }; }
    return { status: response.status, data };
  }, { url: new URL(route, actor.origin).toString(), method, body, apiKey });
}
async function switches(h) {
  await require('./delivery_cases.cjs').fixture(h);
  const generated = require('./generated_service_cases.cjs');
  const graph = require('./service_graph.cjs');
  const contract = require('./service_contract_cases.cjs');
  const authority = require('./application_authority_cases.cjs');
  const business = require('./business_cases.cjs');
  const absent = res => [200, 404].includes(res?.status) && res.data?.error?.code === 2 && res.data?.value == null;
  const app = await author.definition(h, 'capswitch');
  const saved = await author.save(h, app, await author.draft(h, app), matrix(h, app));
  const f = await delivery.publish(h, app);
  h.check('Immutable revision freezes every whole and individual operation switch exactly',
    f.revision.entities.length === 7 && saved.entities.every(e => f.revision.entities.some(v => v.name === e.name && v.pkgPath === e.pkgPath && same(v.serviceExpose, e.serviceExpose))));
  h.admin.id = (await h.ok(h.admin, 'GET', '/api/v1/web/session/')).value.account.id;
  const r = await review.create(h, f, 'capswitch'); delivery.linkRequest(h, f, r);
  let primary, r2;
  let cred1, sub1, svc1, cred2, sub2, svc2;
  const retireServiceChain = async (svc, sub, cred) => {
    if (cred?.resource?.phase === 'created' && !cred.__retired) {
      if (cred.resource.endpointAuthorityCommands?.at(-1)?.outcome === 'confirmed' && cred.resource.endpointAuthorityCommands.at(-1).body?.roleTemplateKeys?.length) {
        await contract.endpointTemplates(h, cred, []);
      }
      await graph.retireCredential(h, cred);
      cred.__retired = true;
    }
    if (sub?.resource?.phase === 'created' && !sub.__retired) {
      await graph.retire(h, sub);
      sub.__retired = true;
    }
    if (svc?.phase && svc.phase !== 'deleted' && !svc.__cleaned) {
      await generated.cleanup(h, svc);
      svc.__cleaned = true;
    }
  };
  try {
    await review.approve(h, r, [h.admin]);
    const source = r.installation.receipt.runtimeApplicationUuid;
    const read = () => h.directory(h.admin, route, { pageSize: 2 });
    const before = await read(), owned = before.filter(v => v.providerKey === source);
    h.check('Complete installed capability catalogue matches all receipt-bound enabled pairs and excludes every disabled pair', catalogueMatches(f, r.installation, owned, h.admin.identity.namespace), owned);
    const current = await author.draft(h, app), changed = structuredClone(current.entities);
    for (const entity of changed) {
      if (entity.name === 'switch0' || entity.name === 'switch1') entity.serviceExpose.enabled = !entity.serviceExpose.enabled;
      else for (const capability of entity.serviceExpose.capabilities) capability.enabled = !capability.enabled;
    }
    await author.save(h, app, current, changed);
    h.check('Unpublished switch changes preserve original frozen revision and package',
      same((await h.ok(h.admin, 'GET', '/panel/application/definitions/' + app.id + '/revisions/' + f.revision.id)).value, f.revision) &&
      same((await h.ok(h.admin, 'GET', '/panel/application/model-packages/' + f.package.id)).value, f.package));
    h.check('Unpublished switch changes preserve every exact original installed capability', same((await read()).filter(v => v.providerKey === source), owned));

    const casBase = '/cas/namespaces/panel/';
    const fullEntity = f.revision.entities.find(e => e.serviceExpose?.enabled && e.serviceExpose.capabilities?.length === 5 && e.serviceExpose.capabilities.every(c => c.enabled));
    h.check('Switch matrix includes an entity with all five CRUD capabilities enabled', !!fullEntity, f.revision.entities);
    const fullEntityKey = fullEntity.pkgPath + '/' + fullEntity.name;
    const fullCaps = owned.filter(c => JSON.parse(c.options).runtimeEntityPkgKey === fullEntityKey);
    const byKind = Object.fromEntries(fullCaps.map(c => [c.kind, c]));
    h.check('Installed capability catalogue exposes all five CRUD capabilities for full entity',
      fullCaps.length === 5 && ['create', 'query', 'get', 'update', 'delete'].every(k => !!byKind[k]), fullCaps);

    const ordinary = (await h.directory(h.admin, casBase + 'role-templates/')).filter(t => t.key === 'portal-basic-user' && t.systemManaged && t.subjectType === 'account' && t.status === 2);
    h.check('Capability switch caller uses built-in portal-basic-user functional profile', ordinary.length === 1 && ordinary[0].roleRefs?.length > 0);
    const dataRoles = ['read', 'write', 'delete'].map(k => ({ module: '/applications/' + r.installation.deploymentId, key: 'application-data-' + k }));
    const accountRefs = [...new Map([...ordinary[0].roleRefs, ...dataRoles].map(ref => [JSON.stringify([ref.module, ref.key]), structuredClone(ref)])).values()];
    const access1 = [{ applicationUuid: r.installation.deploymentId, accessLevel: 'manager' }];
    const callerGroup = await h.create(casBase + 'role-templates/', { key: h.state.prefix + '-capswitch-caller', name: '能力开关实调账号角色', subjectType: 'account', status: 2, roleRefs: accountRefs, applicationAccess: access1 }, 'role-template');
    const caller = await authority.account(h, 'capswitch-caller');
    await authority.assign(h, caller, callerGroup, access1);
    const epTpl1 = await h.create(casBase + 'role-templates/', { key: h.state.prefix + '-capswitch-ep', name: '能力开关接口端点权限', subjectType: 'endpoint', status: 2, applicationAccess: [], roleRefs: dataRoles }, 'role-template');

    const capIds1 = ['create', 'query', 'get', 'update', 'delete'].map(k => byKind[k].id);
    svc1 = generated.intent(h, h.state.prefix + '_capswitch_crud', capIds1, source);
    await generated.converge(h, svc1, capIds1, '能力开关实调服务');
    const pub1 = svc1.last.publications[0];
    await generated.mutation(h, svc1, 'PUT', generated.publications + pub1.id, { service: { id: svc1.serviceId }, status: 1, visibleScope: 'panel', allowSubscription: true, requireApproval: false, maxSubscriptions: 2, maxQPS: 0, dailyQuota: 0 }, async (response, all) => {
      h.check('Generated switch CRUD publication allows ordinary subscription', h.good(response) && all[generated.publications].some(v => v.id === pub1.id && v.allowSubscription));
    });
    await generated.publish(h, svc1);
    const internal1 = { service: svc1.last.service, publication: svc1.last.publications[0], ownerIdentity: structuredClone(h.admin.identity) };
    sub1 = await graph.subscribe(h, internal1, caller.actor);
    cred1 = await graph.credential(h, sub1, 'capswitch-crud');
    const meta1 = (await h.ok(caller.actor, 'GET', '/portal/service/debug/' + internal1.service.id)).value;
    const opByKind = Object.fromEntries(['create', 'query', 'get', 'update', 'delete'].map(k => [k, meta1.operations.find(o => o.key === byKind[k].key)]));
    h.check('Generated CRUD service freezes exact operations for all five enabled capabilities',
      meta1.operations.length === 5 && Object.values(opByKind).every(Boolean), meta1);
    const ungranted = await callGateway(caller.actor, 'GET', opByKind.query.pathTemplate, cred1.apiKey);
    h.check('Subscribed Endpoint is refused before explicit application role grant', contract.currentRoleRefusal(ungranted), ungranted);
    await contract.endpointTemplates(h, cred1, [epTpl1.key]);

    const runtimeMeta1 = (await h.ok(caller.actor, 'GET', '/apps/application/runtimes/' + encodeURIComponent(app.name) + '?deploymentId=' + r.installation.deploymentId)).value;
    const ownerCtx1 = { identity: runtimeMeta1.readIdentity, applicationKey: app.name, entity: fullEntityKey };

    const createdRes = await callGateway(caller.actor, 'POST', opByKind.create.pathTemplate, cred1.apiKey, { code: 'CAP-1', name: 'capswitch-initial', description: 'switch test row' });
    const created = createdRes.data?.value;
    const createdId = created?.id === undefined ? '' : String(created.id);
    const ownerCreated = createdId ? await business.record(h, caller.actor, ownerCtx1, createdId) : null;
    h.check('Generated create capability persists real row matching independent owner read',
      h.good(createdRes) && !!createdId && h.good(ownerCreated) && ownerCreated.data.value.code === 'CAP-1' && ownerCreated.data.value.name === 'capswitch-initial', { createdRes, ownerCreated });

    const queriedRes = await callGateway(caller.actor, 'GET', opByKind.query.pathTemplate, cred1.apiKey);
    const queriedRows = Array.isArray(queriedRes.data?.values) ? queriedRes.data.values : Array.isArray(queriedRes.data?.value) ? queriedRes.data.value : [];
    h.check('Generated query capability lists created record', h.good(queriedRes) && queriedRows.some(row => String(row.id) === createdId), queriedRes);

    const getRes = await callGateway(caller.actor, 'GET', opByKind.get.pathTemplate.replace(/\{id\}/g, createdId), cred1.apiKey);
    h.check('Generated get capability matches exact independent owner record', h.good(getRes) && same(getRes.data?.value, ownerCreated.data.value), { getRes, ownerCreated });

    const updatedRes = await callGateway(caller.actor, 'PUT', opByKind.update.pathTemplate.replace(/\{id\}/g, createdId), cred1.apiKey, { version: ownerCreated.data.value.version, name: 'capswitch-updated' });
    const ownerUpdated = await business.record(h, caller.actor, ownerCtx1, createdId);
    h.check('Generated update capability advances version and persists updated field in owner',
      h.good(updatedRes) && h.good(ownerUpdated) && ownerUpdated.data.value.name === 'capswitch-updated' && ownerUpdated.data.value.code === 'CAP-1' && Number(ownerUpdated.data.value.version) > Number(ownerCreated.data.value.version), { updatedRes, ownerUpdated });

    const deletePath = opByKind.delete.pathTemplate.replace(/\{id\}/g, createdId) + '?expectedVersion=' + encodeURIComponent(String(ownerUpdated.data.value.version));
    const deletedRes = await callGateway(caller.actor, 'DELETE', deletePath, cred1.apiKey);
    const ownerAfterDelete = await business.record(h, caller.actor, ownerCtx1, createdId);
    h.check('Generated delete capability formally removes row confirmed absent in independent owner',
      h.good(deletedRes) && absent(ownerAfterDelete), { deletedRes, ownerAfterDelete });

    await retireServiceChain(svc1, sub1, cred1);
    const retiredCall = await callGateway(caller.actor, 'GET', opByKind.query.pathTemplate, cred1.apiKey);
    h.check('Retired generated switch service rejects late Gateway call', retiredCall.status >= 400 || retiredCall.data?.error != null, retiredCall);

    await review.cleanup(h, r);
    const after = await read();
    h.check('Formal original installation destroy retires its entire generated capability set and preserves peer catalogues',
      !after.some(v => v.providerKey === source) && same(after, before.filter(v => v.providerKey !== source)));

    const next = await delivery.publishNext(h, f);
    h.check('Republished inverted switch matrix freezes flipped serviceExpose flags in newer immutable revision',
      next.revision.id !== f.revision.id && changed.every(e => next.revision.entities.some(v => v.name === e.name && v.pkgPath === e.pkgPath && same(v.serviceExpose, e.serviceExpose))));
    r2 = await review.create(h, next, 'capswitch-next'); delivery.linkRequest(h, next, r2);
    await review.approve(h, r2, [h.admin]);
    const source2 = r2.installation.receipt.runtimeApplicationUuid;
    const owned2 = (await read()).filter(v => v.providerKey === source2);
    const prevPairs = new Set(owned.map(c => JSON.parse(c.options).runtimeEntityPkgKey + ':' + c.kind));
    const nextPairs = new Set(owned2.map(c => JSON.parse(c.options).runtimeEntityPkgKey + ':' + c.kind));
    h.check('Republished enabled-to-disabled transition removes every prior enabled pair from installed catalogue and exposes flipped pairs',
      catalogueMatches(next, r2.installation, owned2, h.admin.identity.namespace) && [...prevPairs].every(p => !nextPairs.has(p)) && owned2.length > 0, owned2);

    const epTpl2 = await h.create(casBase + 'role-templates/', { key: h.state.prefix + '-capswitch-ep2', name: '翻转载荷接口端点权限', subjectType: 'endpoint', status: 2, applicationAccess: [], roleRefs: ['read', 'write', 'delete'].map(k => ({ module: '/applications/' + r2.installation.deploymentId, key: 'application-data-' + k })) }, 'role-template');
    const access2 = [{ applicationUuid: r2.installation.deploymentId, accessLevel: 'manager' }];
    const callerGroup2 = await h.create(casBase + 'role-templates/', { key: h.state.prefix + '-capswitch-caller2', name: '翻转载荷账号角色', subjectType: 'account', status: 2, roleRefs: [...new Map([...ordinary[0].roleRefs, ...['read', 'write', 'delete'].map(k => ({ module: '/applications/' + r2.installation.deploymentId, key: 'application-data-' + k }))].map(ref => [JSON.stringify([ref.module, ref.key]), structuredClone(ref)])).values()], applicationAccess: access2 }, 'role-template');
    const caller2 = await authority.account(h, 'capswitch-caller2');
    await authority.assign(h, caller2, callerGroup2, access2);

    const flippedCap = owned2.find(c => c.kind === 'query') || owned2[0];
    svc2 = generated.intent(h, h.state.prefix + '_capswitch_next', [flippedCap.id], source2);
    await generated.converge(h, svc2, [flippedCap.id], '能力开关翻转后服务');
    const pub2 = svc2.last.publications[0];
    await generated.mutation(h, svc2, 'PUT', generated.publications + pub2.id, { service: { id: svc2.serviceId }, status: 1, visibleScope: 'panel', allowSubscription: true, requireApproval: false, maxSubscriptions: 2, maxQPS: 0, dailyQuota: 0 }, async response => {
      h.check('Flipped enabled capability publication allows subscription', h.good(response));
    });
    await generated.publish(h, svc2);
    const internal2 = { service: svc2.last.service, publication: svc2.last.publications[0], ownerIdentity: structuredClone(h.admin.identity) };
    sub2 = await graph.subscribe(h, internal2, caller2.actor);
    cred2 = await graph.credential(h, sub2, 'capswitch-next');
    await contract.endpointTemplates(h, cred2, [epTpl2.key]);
    const meta2 = (await h.ok(caller2.actor, 'GET', '/portal/service/debug/' + internal2.service.id)).value;
    const activeOp2 = meta2.operations.find(o => o.key === flippedCap.key);
    const activeRes2 = await callGateway(caller2.actor, activeOp2.method, activeOp2.pathTemplate.replace(/\{id\}/g, '1'), cred2.apiKey);
    const disabledAttempt = await callGateway(caller2.actor, 'GET', '/api/v1/gateway/services/' + internal2.service.key + '/' + byKind.query.key, cred2.apiKey);
    h.check('Newly enabled capability succeeds via Gateway while republish-disabled capability route is refused at runtime',
      h.good(activeRes2) && (disabledAttempt.status >= 400 || disabledAttempt.data?.error != null), { activeRes2, disabledAttempt });

    await retireServiceChain(svc2, sub2, cred2);
    await review.cleanup(h, r2);
  } catch (error) { primary = error; throw error; }
  finally {
    try {
      await retireServiceChain(svc2, sub2, cred2);
      await retireServiceChain(svc1, sub1, cred1);
      if (r2 && r2.phase !== 'deleted') await review.cleanup(h, r2);
      if (r.phase !== 'deleted') await review.cleanup(h, r);
      await delivery.retained(h, f.resource);
    } catch (error) { h.observe({ kind: 'original-capability-switch-cleanup-open', requestId: r.id, message: error.message }); if (!primary) throw error; }
  }
}
switches.transport = 'owner-api';
module.exports = { handlers: { 'F019-001': switches }, matrix, catalogueMatches };
