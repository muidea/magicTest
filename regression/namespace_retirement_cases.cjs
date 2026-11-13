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
  await h.partial('No-application tenant formal aggregate deletion, original target404, exact CAS directory absence, durable retirement and three unrelated original login sessions implemented. In-use application refusal and interrupted original retirement recovery still require their dedicated fixtures.');
}
retirement.actors = ['tenantAdmin', 'otherTenantAdmin']; retirement.transport = 'owner-api';
module.exports = { handlers: { 'F003-004': retirement }, receiptMatches };
