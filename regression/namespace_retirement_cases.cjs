const { isDeepStrictEqual: same } = require('node:util');
function receiptMatches(r, value) {
  return value?.namespaceId === r.id && value.name === r.name && value.phase === 'complete' && /^[a-f0-9]{32}$/.test(value.requestId || '') &&
    Number.isSafeInteger(value.expectedVersion) && value.expectedVersion > 0 && Number.isSafeInteger(value.revision) && value.revision > 0;
}
async function retirement(h) {
  const actors = [h.admin, h.tenantAdmin, h.otherTenantAdmin], sessions = [];
  for (const actor of actors) sessions.push((await h.ok(actor, 'GET', '/api/v1/web/session/')).value);
  const ns = await h.create('/panel/namespace-onboardings/', { name: h.state.prefix + 'retire', description: '空间删除独立样本', scope: [], status: 2,
    startTime: Date.now() - 1000, expireTime: Date.now() + 86400000, initialAdminPassword: h.state.password }, 'namespace');
  const r = h.state.resources.find(v => v.kind === 'namespace' && v.id === ns.id);
  const anon = await h.anonymous(ns.name, actor => require('./registration_cases.cjs').waitForRegistrationIngress(h, ns, actor));
  const accounts = await h.directory(h.admin, '/cas/namespaces/' + ns.name + '/accounts/');
  h.check('Fresh no-application tenant has exactly its one enabled bootstrap account', accounts.length === 1 && accounts[0].status === 2);
  r.retirementLogin = { account: accounts[0].account, namespace: ns.name, newPassword: h.state.password + 'R', outcome: 'prepared' };
  h.persist();
  const target = await h.login(accounts[0].account, h.state.password, ns.name, r.retirementLogin.newPassword, async () => {
    r.retirementLogin.outcome = 'password-change-in-progress'; h.persist();
  });
  await h.ok(target, 'GET', '/api/v1/web/session/');
  r.retirementLogin.outcome = 'session-confirmed'; h.persist();
  r.retirementSession = { actorIdentity: structuredClone(target.identity), origin: target.origin };
  h.persist();
  // Probe real in-use tenant retirement refusal before retiring the blocking resource cleanly.
  const delivery = await require('./delivery_cases.cjs').fixture(h);
  const { packageContent, packageUpload } = require('./owner_transport.cjs');
  const zip = await packageContent(h.admin, '/panel/application/model-packages/' + delivery.package.id + '/content', h.observe);
  h.check('Download delivery model ZIP for in-use tenant probe', zip.status === 200 && Buffer.isBuffer(zip.data.bytes));
  const up = await packageUpload(target, { name: h.state.prefix + '-inuse-probe.zip', bytes: zip.data.bytes }, h.observe);
  h.check('Fresh tenant admin uploads model ZIP into target namespace', h.good(up) && !!up.data?.value?.uploadRef, up);
  const tPkg = (await h.ok(target, 'POST', '/panel/application/model-packages/imports/', { uploadRef: up.data.value.uploadRef })).value;
  let req;
  try {
    req = (await h.ok(target, 'POST', '/panel/application/deployment-requests/', {
      sourceKind: 'model-package', packageId: tPkg.id, expectedDigest: tPkg.artifactDigest,
      instanceKey: h.state.prefix + 'inuse', instanceName: '在用阻止删除样本',
      storageProvisioning: { mode: 'allocate' }, reason: 'F003-004 active request blocks tenant deletion',
    })).value;
    const blocked = await h.api(h.admin, 'DELETE', r.collection + r.id);
    h.check('In-use tenant deletion is explicitly refused while an active deployment request exists',
      [200, 400, 409].includes(blocked.status) && blocked.data?.error?.code === 21 &&
      /仍在用.*安装申请|请先完成卸载、取消或清理/.test(blocked.data.error.message || '') && blocked.data.value == null, blocked);
    h.check('Refused deletion preserves exact tenant record, CAS directory entry and active target session',
      (await h.directory(h.admin, '/cas/namespaces/')).some(v => v.id === r.id && v.name === r.name) &&
      (await h.ok(target, 'GET', '/api/v1/web/session/')).value?.homeNamespace === ns.name);
  } finally {
    if (req?.id) {
      const freshReq = (await h.api(target, 'GET', '/panel/application/deployment-requests/' + req.id)).data?.value || req;
      if (freshReq.status === 'submitted') {
        const cancelled = await h.ok(target, 'POST', '/panel/application/deployment-requests/' + freshReq.id + '/cancel', {
          expectedVersion: freshReq.version, reason: 'Cancel F003-004 in-use blocker before tenant retirement',
        });
        await h.ok(target, 'POST', '/panel/application/deployment-requests/' + freshReq.id + '/cleanup', {
          expectedVersion: cancelled.value.version, reason: 'Cleanup F003-004 in-use blocker before tenant retirement',
        });
      }
    }
    if (tPkg?.id) await h.api(target, 'DELETE', '/panel/application/model-packages/' + tPkg.id).catch(() => {});
  }
  await require('./resource_lifecycle.cjs').deleteResource(h, h.admin, r);
  const receipt = (await h.ok(h.admin, 'GET', r.collection + r.id + '/retirement')).value;
  h.check('Durable aggregate owner receipt binds complete original namespace retirement identity', receiptMatches(r, receipt), receipt);
  h.check('Complete independent CAS directory contains neither original name nor ID', !(await h.directory(h.admin, '/cas/namespaces/')).some(v => v.id === r.id || v.name === r.name));
  for (const actor of [target, anon]) {
    const result = await h.api(actor, 'GET', '/api/v1/web/session/');
    h.check('Retired target tenant requests return designed404 with no session identity', result.status === 404 && !result.data?.value?.account, result);
  }
  for (const [index, actor] of actors.entries()) h.check('Exact original unrelated tenant login session survives namespace retirement',
    same((await h.ok(actor, 'GET', '/api/v1/web/session/')).value, sessions[index]));
  r.retirement = receipt; r.phase = 'deleted'; h.persist();
  h.observe({
    kind: 'special-branches-deferred',
    caseId: 'F003-004',
    classification: '[C]',
    note: 'Interrupted original retirement recovery requires a dedicated fault-injection fixture tracked in the special suite [C].',
  });
}
retirement.actors = ['tenantAdmin', 'otherTenantAdmin']; retirement.transport = 'owner-api';
module.exports = { handlers: { 'F003-004': retirement }, receiptMatches };
