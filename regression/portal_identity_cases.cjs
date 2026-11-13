// Real same-context logout/login; no cookie or React-state substitution.
const { isDeepStrictEqual: same } = require('node:util');
const overview = require('./portal_overview_cases.cjs');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
const { waitLoginForm } = require('./login_readiness.cjs');
async function switchActor(h, current, target, journal) {
  if (current.context !== journal.context || current.page !== journal.page || current.origin !== target.origin ||
      current.identity.namespace !== target.identity.namespace || journal.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Same original context/tenant required; unknown login command cannot be replayed');
  const c = { from: structuredClone(current.identity), to: structuredClone(target.identity), outcome: 'unknown' };
  journal.commands.push(c); h.persist();
  await current.page.goto(current.origin + '/api/v1/web/auth/logout', { waitUntil: 'networkidle' });
  const absent = await h.api(current, 'GET', '/api/v1/web/session/');
  h.check('Same context formally loses original logged-out BFF session', absent.status === 401 || absent.data?.error?.code === 11, absent);
  const actor = { ...target, context: current.context, page: current.page };
  await withOriginalCasForms(actor, { journal: h.state.originalCasForms ||= [], persist: h.persist, record: h.observe }, async () => {
    await actor.page.goto(actor.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
    const form = await waitLoginForm(actor.page);
    await form.account.fill(actor.identity.account); await form.password.fill(actor.password); await form.submit.click();
    await actor.page.waitForURL(url => url.pathname.startsWith('/portal'), { timeout: 45000 });
    await actor.page.waitForLoadState('networkidle');
  });
  const session = (await h.ok(actor, 'GET', '/api/v1/web/session/')).value;
  h.check('Same-context CAS login establishes exact next ordinary subject and tenant', session.account.account === target.identity.account &&
    session.homeNamespace === target.identity.namespace && session.activeNamespace === target.identity.namespace);
  c.outcome = 'confirmed'; h.persist(); return actor;
}
async function identities(h) {
  const f = await require('./delivery_cases.cjs').fixture(h), business = require('./business_cases.cjs');
  const a = await business.member(h, 'manager'), b = await business.member(h, 'outsider');
  h.check('Original ordinary source subjects are distinct in the same tenant', a.identity.account !== b.identity.account && a.origin === b.origin);
  let current = await h.login(a.identity.account, a.password, a.identity.namespace);
  const resource = { kind: 'portal-identity-session', phase: 'created', commands: [], originalIdentity: structuredClone(a.identity) };
  // Browser handles stay outside the serializable private resource journal.
  const journal = { context: current.context, page: current.page, commands: resource.commands };
  h.state.resources.push(resource); h.persist();
  const peerSessions = [];
  for (const actor of [a, b, h.admin]) peerSessions.push((await h.ok(actor, 'GET', '/api/v1/web/session/')).value);
  let baseline;
  for (const [index, target] of [a, b, a].entries()) {
    if (index) current = await switchActor(h, current, target, journal);
    const rows = await overview.projection(h, current), ids = new Set(f.installations.map(i => i.deploymentId));
    const applications = rows.applications.filter(v => ids.has(v.deploymentId));
    h.check('Same-context identity projects exactly its independently assigned original installation membership', index === 1 ? applications.length === 0 :
      applications.length === 2 && f.installations.every(i => applications.some(v => v.deploymentId === i.deploymentId && v.applicationUuid === f.application.uuid)), applications);
    if (!index) baseline = structuredClone(applications);
    if (index === 2) h.check('Returning A reads identical original application entries after B', same(applications, baseline));
    for (const width of [1366, 390]) await overview.home(h, current, rows, width, 'same-context-' + index);
    if (index === 1) for (const instance of f.installations) h.denied(await h.api(current, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + instance.deploymentId),
      'Same browser B cannot read A installation by guessing deployment');
  }
  for (const [index, actor] of [a, b, h.admin].entries()) h.check('Login switch preserves independent original sessions',
    same((await h.ok(actor, 'GET', '/api/v1/web/session/')).value, peerSessions[index]));
  resource.phase = 'deleted'; h.persist();
  await h.partial('Same-page/context formal CAS logout and A→B→A login, nonempty/empty installation membership, complete scoped owner projections, desktop/mobile counts and B instance refusal implemented. Tenant/instance switch, switching-time revocation and late read/write-refresh/icon responses remain open.');
}
identities.transport = 'owner-api';
module.exports = { handlers: { 'F065-002': identities }, switchActor };
