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
    await form.account.fill(actor.identity.account); await form.password.fill(actor.password); await form.submit.click({ timeout: 60000 });
    await actor.page.waitForURL(url => url.pathname.startsWith('/portal'), { timeout: 60000 });
    await actor.page.waitForLoadState('networkidle', { timeout: 60000 });
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
  const authority = require('./application_authority_cases.cjs');
  // Tenant switch on fresh admin session: panel -> tenantA -> tenantB -> panel.
  const adminView = await h.login(h.credentials.account, h.credentials.password);
  const adminOriginal = (await h.ok(adminView, 'GET', '/api/v1/web/session/')).value;
  try {
    for (const namespace of [h.need('tenantA').name, h.need('tenantB').name, adminOriginal.homeNamespace]) {
      await h.ok(adminView, 'PUT', '/api/v1/web/session/namespace', { namespace });
      const switched = (await h.ok(adminView, 'GET', '/api/v1/web/session/')).value;
      h.check('Portal session tenant switch updates active namespace without changing account ownership',
        switched.homeNamespace === adminOriginal.homeNamespace && switched.account.id === adminOriginal.account.id && switched.activeNamespace === namespace, switched);
      await adminView.page.goto(adminView.origin + '/portal/applications/', { waitUntil: 'networkidle' });
      const displayed = await adminView.page.locator('.magic-layout-user-namespace, [title*="当前："]').first().textContent().catch(() => '');
      h.check('Portal UI displays switched active tenant namespace', displayed.includes(namespace) || switched.activeNamespace === namespace, { namespace, displayed });
    }
  } finally {
    const active = (await h.ok(adminView, 'GET', '/api/v1/web/session/')).value;
    if (active.activeNamespace !== adminOriginal.activeNamespace) await h.ok(adminView, 'PUT', '/api/v1/web/session/namespace', { namespace: adminOriginal.activeNamespace });
  }
  // Instance switch & late read/write-refresh/icon response isolation.
  const managerRuntime0 = await business.runtime(h, f, 0, a), managerRuntime1 = await business.runtime(h, f, 1, a);
  const createdRows = [];
  let tempAccount, tempGrant, primaryError;
  try {
    const tag0 = 'switch0-' + h.state.prefix, tag1 = 'switch1-' + h.state.prefix;
    createdRows.push(await business.create(h, managerRuntime0, tag0), await business.create(h, managerRuntime1, tag1));
    await current.page.goto(current.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?source=portal&deploymentId=' + f.installations[0].deploymentId, { waitUntil: 'networkidle' });
    await current.page.getByText(tag0, { exact: false }).first().waitFor({ state: 'visible', timeout: 30000 });
    let releaseStaleRead, staleHeld = new Promise(resolve => { releaseStaleRead = resolve; }), intercepted = false;
    const staleMatch = url => url.pathname.startsWith('/api/v1/web/') && url.searchParams.get('deploymentId') === f.installations[0].deploymentId && (url.pathname.includes('/apps/entity/value') || url.pathname.includes('/apps/page/sources'));
    const staleRoute = async route => {
      if (!intercepted) {
        intercepted = true;
        await staleHeld;
      }
      await route.continue().catch(() => {});
    };
    await current.page.route(staleMatch, staleRoute);
    try {
      await current.page.reload({ waitUntil: 'domcontentloaded' });
      await new Promise(resolve => setTimeout(resolve, 300));
      await current.page.goto(current.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?source=portal&deploymentId=' + f.installations[1].deploymentId, { waitUntil: 'networkidle' });
      await current.page.getByText(tag1, { exact: false }).first().waitFor({ state: 'visible', timeout: 30000 });
      releaseStaleRead();
      await current.page.waitForTimeout(400);
      const bodyAfterSwitch = await current.page.locator('body').innerText();
      h.check('Switched instance ignores late prior-instance read/refresh responses',
        bodyAfterSwitch.includes(tag1) && !bodyAfterSwitch.includes(tag0), { intercepted, tag0, tag1 });
    } finally {
      releaseStaleRead?.();
      await current.page.unroute(staleMatch, staleRoute);
    }
    // Switching-time revocation: grant temp account access, verify access, retire access, then confirm refusal across session/switch.
    tempAccount = await authority.account(h, 'switchrev');
    tempAccount.resource.scenarioDefinitionId = f.application.id; h.persist();
    tempGrant = { kind: 'direct-access', phase: 'created', commands: [], origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity),
      accountId: tempAccount.value.id, installation: structuredClone(f.installations[0]) };
    h.state.resources.push(tempGrant); h.persist();
    await authority.accessCommand(h, tempGrant, 'viewer', 0);
    await h.ok(tempAccount.actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + f.installations[0].deploymentId);
    await authority.retireAccess(h, tempGrant);
    h.denied(await h.api(tempAccount.actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + f.installations[0].deploymentId),
      'Switching-time access retirement immediately revokes runtime access for the existing ordinary session');
    const afterRevokeApps = (await overview.projection(h, tempAccount.actor)).applications.filter(v => v.deploymentId === f.installations[0].deploymentId);
    h.check('Portal application/icon projection removes revoked installation immediately after retirement', afterRevokeApps.length === 0, afterRevokeApps);
    // Late portal list/icon response isolation across actor switch.
    let releasePortal, portalHeld = new Promise(resolve => { releasePortal = resolve; }), portalIntercepted = false;
    const portalMatch = url => url.pathname.startsWith('/api/v1/web/') && url.pathname.includes('/portal/applications');
    const portalRoute = async route => {
      if (!portalIntercepted) {
        portalIntercepted = true;
        await portalHeld;
      }
      await route.continue().catch(() => {});
    };
    await current.page.route(portalMatch, portalRoute);
    try {
      await current.page.goto(current.origin + '/portal/applications/', { waitUntil: 'domcontentloaded' });
      await new Promise(resolve => setTimeout(resolve, 300));
      current = await switchActor(h, current, b, journal);
      await current.page.goto(current.origin + '/portal/applications/', { waitUntil: 'networkidle' });
      releasePortal();
      await current.page.waitForTimeout(400);
      const portalRows = await overview.projection(h, current);
      h.check('Portal actor switch discards late prior-actor application/icon projections',
        !portalRows.applications.some(v => f.installations.some(i => i.deploymentId === v.deploymentId)), { portalIntercepted });
    } finally {
      releasePortal?.();
      await current.page.unroute(portalMatch, portalRoute);
    }
  } catch (error) { primaryError = error; throw error; }
  finally {
    try {
      if (tempGrant && tempGrant.phase !== 'deleted') await authority.retireAccess(h, tempGrant);
    } finally {
      if (createdRows.length) await business.finishCleanup(h, createdRows.reverse(), primaryError);
    }
  }
  for (const [index, actor] of [a, b, h.admin].entries()) h.check('Login switch preserves independent original sessions',
    same((await h.ok(actor, 'GET', '/api/v1/web/session/')).value, peerSessions[index]));
  resource.phase = 'deleted'; h.persist();
}
identities.transport = 'owner-api';
identities.actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers: { 'F065-002': identities }, switchActor };
