// Exercise actual frozen read scheduling; all held traffic is read-only POST.
const { isDeepStrictEqual: same } = require('node:util');
const page = require('./page_runtime_cases.cjs');
const business = require('./business_cases.cjs');
const { authoring: a } = require('./authoring_cases.cjs');
const { field, inputViews } = require('./model_input_cases.cjs');
async function prepareRefresh(h, authored) {
  const current = await a.draft(h, authored.app), entity = structuredClone(current.entities[0]);
  entity.fields.push(field('occurredAt', 'datetime', true));
  authored.model = await a.save(h, authored.app, current, [entity]);
  authored.pages = await require('./page_author_cases.cjs').authorFixture.read(h, authored.app, 'pages');
}
function configure(content, entity) {
  content.refresh = { seconds: 5, overlap: false, pauseWhenHidden: true, cancelOnLeave: true, failureBackoffSeconds: [10, 20] };
  const list = content.dataSources.find(s => s.key === 'records');
  content.dataSources.push({
    ...structuredClone(list),
    key: 'windowed',
    fields: ['id', 'name', 'occurredAt'],
    timeWindow: { field: 'occurredAt', defaultHours: 24, bounds: '[from,to)', timezone: 'UTC' },
  });
  const short = entity.split('/').at(-1);
  content.actions = { ...(content.actions || {}), [short]: [...new Set([...(content.actions?.[short] || []), 'create'])] };
  content.navigation.push('static', 'windowed', 'createform');
  content.pages.push(
    { key: 'static', title: '只读切换目标', routes: ['/static'], navigation: true, routeParameters: [], layout: { type: 'responsive-grid', columns: 12, gap: 0 },
      components: [{ key: 'static-text', type: 'text', layout: { span: 12, order: 0 }, dataSources: [], properties: { text: '原页面读取已离开' } }] },
    { key: 'windowed', title: '时间窗列表', routes: ['/windowed'], navigation: true, routeParameters: [], layout: { type: 'responsive-grid', columns: 12, gap: 0 },
      components: [{ key: 'windowed-table', type: 'entity-table', layout: { span: 12, order: 0 }, dataSources: ['windowed'], properties: { entity, columns: ['id', 'name'], readonly: true } }] },
    { key: 'createform', title: '写入面板共存页', routes: ['/forms/create'], navigation: true, routeParameters: [], layout: { type: 'responsive-grid', columns: 12, gap: 0 },
      components: [
        { key: 'write-form', type: 'entity-form', layout: { span: 12, order: 0 }, dataSources: [],
          properties: { entity, mode: 'create', sections: [{ title: '基本信息', fields: ['code', 'name', 'description', 'sortOrder', 'occurredAt'] }] } },
        { key: 'live-table', type: 'entity-table', layout: { span: 12, order: 1 }, dataSources: ['records'], properties: { entity, columns: ['id', 'name'], readonly: true } },
      ] },
  );
}
function exactSource(request, origin, context) {
  try {
    const url = new URL(request.url());
    return request.method() === 'POST' && url.origin === origin && url.pathname === '/api/v1/web/proxy/apps/page/sources/' &&
      url.searchParams.getAll('application').length === 1 && url.searchParams.getAll('deploymentId').length === 1 &&
      url.searchParams.get('application') === context.applicationKey && url.searchParams.get('deploymentId') === context.identity.deploymentId &&
      request.postDataJSON()?.sourceKey === 'records';
  } catch { return false; }
}
async function bounded(promise, message, milliseconds = 25000) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error(message)), milliseconds); })]); }
  finally { clearTimeout(timer); }
}
async function scheduling(h) {
  const f = await page.explicitFixture(h, configure, undefined, { suffix: 'pagerefresh', requestPrefix: 'page-refresh-', prepareAuthor: prepareRefresh, buildEntityViews: inputViews });
  const actor = await business.member(h, 'manager'), rows = [];
  let primary, hiddenVerified = false;
  try {
    const contexts = [];
    for (let i = 0; i < f.installations.length; i++) {
      const context = await business.runtime(h, f, i, actor);
      const value = (await h.ok(actor, 'GET', '/apps/application/runtimes/' + f.application.name + '?deploymentId=' + context.identity.deploymentId)).value;
      h.check('Original runtime freezes the exact declared read schedule and complete page contract', same(value.pages, f.revision.content.pages) && same(value.pages.refresh, { seconds: 5, overlap: false, pauseWhenHidden: true, cancelOnLeave: true, failureBackoffSeconds: [10, 20] }));
      context.pageDigest = value.installation.pageDigest; contexts.push(context);
      rows.push(await business.create(h, context, 'read-schedule-' + i));
    }
    const context = contexts[0], row = rows[0], browser = actor.page;
    const originalOwner = (await business.record(h, actor, row)).data.value;
    const readResponse = () => browser.waitForResponse(r => exactSource(r.request(), actor.origin, context), { timeout: 20000 });
    const checkResponse = async response => {
      const result = await response.json();
      h.check('Actual scheduled renderer read reaches exact original frozen source and original business primary key', response.status() === 200 && !result.error && same(page.decodePage(result.value, context, 10, 'records'), [{ id: row.recordId, name: row.created.name }]), result);
    };
    const target = actor.origin + '/workbench/apps/' + encodeURIComponent(f.application.name) + '?' + new URLSearchParams({ source: 'portal', deploymentId: context.identity.deploymentId, pageKey: 'home' });
    for (const width of [1440, 768, 390]) {
      await browser.setViewportSize({ width, height: 1000 });
      const first = readResponse(); first.catch(() => {});
      await browser.goto(target, { waitUntil: 'networkidle' }); await checkResponse(await first);
      await browser.locator('tbody tr[data-row-key="' + row.recordId + '"]').waitFor();
      const next = readResponse(); next.catch(() => {}); await checkResponse(await next);
      h.check('Automatic page refresh preserves exact original row and excludes peer installation content', await browser.getByText(row.created.name, { exact: true }).count() === 1 && await browser.getByText(rows[1].created.name, { exact: true }).count() === 0);
      await h.screenshot(actor, 'scheduled-real-read-' + width);
    }
    // Fail one actual read, then let the original browser/controller recover
    // through the real owner. No write or owner response is replayed.
    const failureMatch = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/apps/page/sources/' && url.searchParams.get('application') === context.applicationKey && url.searchParams.get('deploymentId') === context.identity.deploymentId;
    let failedAt, recoveredAt, failureSeen;
    const failure = new Promise(resolve => { failureSeen = resolve; });
    const failOne = async route => {
      if (!exactSource(route.request(), actor.origin, context)) return route.continue();
      if (!failedAt) {
        failedAt = Date.now();
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 9, message: 'controlled-page-read-failure' } }) });
        failureSeen();
      } else { recoveredAt ||= Date.now(); await route.continue(); }
    };
    await browser.route(failureMatch, failOne);
    const recovered = browser.waitForResponse(r => exactSource(r.request(), actor.origin, context) && r.status() === 200 && recoveredAt !== undefined, { timeout: 45000 }); recovered.catch(() => {});
    try {
      await bounded(failure, 'Original actual automatic read never reached controlled failure');
      const alert = browser.locator('.application-page-surface .ant-alert-error'); await alert.first().waitFor();
      h.check('Actual read error leaves a necessary visible failure instead of silently retaining a successful list', await alert.first().isVisible());
      await h.screenshot(actor, 'actual-read-failure-before-backoff');
      await checkResponse(await recovered);
      h.check('First actual failed read recovers through the real owner only after declared10s failure backoff', recoveredAt - failedAt >= 9500, { elapsedMilliseconds: recoveredAt - failedAt, declaredSeconds: 10 });
      await alert.first().waitFor({ state: 'hidden' });
      await browser.locator('tbody tr[data-row-key="' + row.recordId + '"]').waitFor();
      await h.screenshot(actor, 'actual-read-recovered-after-backoff');
    } finally { await browser.unroute(failureMatch, failOne); }
    // Use a real foreground tab; headless environments that never report
    // hidden cannot provide evidence for this boundary.
    let hiddenReads = 0, foreground;
    const countHidden = request => { if (exactSource(request, actor.origin, context)) hiddenReads++; };
    try {
      foreground = await actor.context.newPage(); await foreground.goto('about:blank'); await foreground.bringToFront();
      if (await browser.evaluate(() => document.hidden)) {
        browser.on('request', countHidden);
        await browser.waitForTimeout(6250);
        h.check('Real background browser page pauses declared automatic reads', hiddenReads === 0, { hiddenReads });
        browser.off('request', countHidden);
        const resumed = readResponse(); resumed.catch(() => {}); await browser.bringToFront();
        h.check('Original browser actually regains visible state', await browser.evaluate(() => !document.hidden));
        await checkResponse(await resumed); hiddenVerified = true;
      } else h.observe({ kind: 'page-hidden-resume-unverified', reason: 'Actual foreground-tab switch did not make the original headless page hidden; no visibility override injected' });
    } finally { browser.off('request', countHidden); if (foreground) await foreground.close(); await browser.bringToFront(); }
    h.observe({ kind: 'actual-page-hidden-resume', verified: hiddenVerified });
    await browser.setViewportSize({ width: 1440, height: 1000 });
    let captured, release, finished, calls = 0, dispatchedAt, outcome;
    const capturedPromise = new Promise(resolve => { captured = resolve; }), gate = new Promise(resolve => { release = resolve; }), done = new Promise(resolve => { finished = resolve; });
    const match = url => url.origin === actor.origin && url.pathname === '/api/v1/web/proxy/apps/page/sources/' && url.searchParams.get('application') === context.applicationKey && url.searchParams.get('deploymentId') === context.identity.deploymentId;
    const hold = async route => {
      if (!exactSource(route.request(), actor.origin, context)) return route.continue();
      calls++;
      if (calls !== 1) { await route.abort('failed'); return; }
      dispatchedAt = Date.now();
      try {
        const response = await route.fetch({ maxRetries: 0 });
        await checkResponse(response); captured(); await gate;
        try { await route.fulfill({ response }); outcome = 'released-real-original-response'; }
        catch (error) { outcome = 'original-browser-read-canceled'; h.observe({ kind: 'original-read-release-canceled', message: error.message }); }
      } catch (error) { outcome = 'owner-read-error'; captured(error); }
      finally { finished(); }
    };
    await browser.route(match, hold);
    try {
      const error = await bounded(capturedPromise, 'Actual automatic original source read was not captured');
      if (error) throw error;
      await browser.waitForTimeout(6250);
      h.check('A real owner read held beyond declared interval never starts an overlapping same-source read', calls === 1 && Date.now() - dispatchedAt >= 6250, { calls, heldMilliseconds: Date.now() - dispatchedAt });
      await browser.locator('.application-page-navigation').getByRole('button', { name: '只读切换目标', exact: true }).click();
      await browser.getByRole('heading', { name: '只读切换目标', exact: true }).waitFor();
      await browser.getByText('原页面读取已离开', { exact: true }).waitFor();
      release(); await bounded(done, 'Held original read did not settle after actual page navigation');
      await browser.waitForTimeout(6250);
      h.check('Actual navigation disposes original read scheduling and late response cannot restore prior business row', calls === 1 && new URL(browser.url()).searchParams.get('pageKey') === 'static' &&
        await browser.locator('tbody tr[data-row-key="' + row.recordId + '"]').count() === 0 && await browser.getByText(row.created.name, { exact: true }).count() === 0 &&
        ['released-real-original-response', 'original-browser-read-canceled'].includes(outcome), { calls, outcome });
      await h.screenshot(actor, 'real-navigation-after-late-read');
    } finally { release(); await bounded(done, 'Original read handler remains unsettled').catch(error => h.observe({ kind: 'original-read-handler-open', message: error.message })); await browser.unroute(match, hold); }
    const restored = readResponse(); restored.catch(() => {});
    await browser.locator('.application-page-navigation').getByRole('button', { name: '原始作者页面', exact: true }).click();
    await checkResponse(await restored); await browser.locator('tbody tr[data-row-key="' + row.recordId + '"]').waitFor();
    h.check('Returning to original page reads original owner row without replaying or changing business writes', same((await business.record(h, actor, row)).data.value, originalOwner) && row.commands.length === 1 && row.commands[0].body.operation === 'create');
    await h.screenshot(actor, 'real-navigation-returned-original-row');

    // Verify durable write panel keeps user input intact while live auto-refresh ticks.
    const formUrl = new URL(target); formUrl.searchParams.set('pageKey', 'createform');
    const draftLabel = '未提交草稿 ' + h.state.prefix;
    const formFirst = readResponse(); formFirst.catch(() => {});
    await browser.goto(formUrl.href, { waitUntil: 'networkidle' });
    await checkResponse(await formFirst);
    const nameInput = browser.getByRole('textbox', { name: '写入字段 name', exact: true });
    await nameInput.waitFor();
    await nameInput.fill(draftLabel);
    const formTick = readResponse(); formTick.catch(() => {});
    await checkResponse(await formTick);
    h.check('Automatic background table refresh preserves unsaved write-panel draft without replaying writes',
      await nameInput.inputValue() === draftLabel && row.commands.length === 1);
    await h.screenshot(actor, 'durable-write-panel-during-auto-refresh');

    // Verify relative and fixed UTC time-window source refreshes.
    const windowUrl = new URL(target); windowUrl.searchParams.set('pageKey', 'windowed');
    const isWindowedSource = req => {
      try {
        const u = new URL(req.url());
        return req.method() === 'POST' && u.origin === actor.origin && u.pathname === '/api/v1/web/proxy/apps/page/sources/' &&
          u.searchParams.get('deploymentId') === context.identity.deploymentId && req.postDataJSON()?.sourceKey === 'windowed';
      } catch { return false; }
    };
    const relReqPromise = browser.waitForRequest(isWindowedSource, { timeout: 20000 }); relReqPromise.catch(() => {});
    await browser.goto(windowUrl.href, { waitUntil: 'networkidle' });
    const relBody = (await relReqPromise).postDataJSON();
    const relSpan = Date.parse(relBody?.to) - Date.parse(relBody?.from);
    h.check('Relative time-window source sends exact 24h UTC window on automatic read', relSpan === 24 * 3600 * 1000, relBody);
    await browser.locator('.application-page-runtime-surface').click({ button: 'right', position: { x: 40, y: 40 } });
    await browser.getByLabel('趋势开始时间 UTC', { exact: true }).fill('2026-01-01T00:00:00Z');
    await browser.getByLabel('趋势结束时间 UTC', { exact: true }).fill('2026-01-02T00:00:00Z');
    const fixedNext = browser.waitForRequest(isWindowedSource, { timeout: 20000 }); fixedNext.catch(() => {});
    await browser.getByRole('button', { name: '应用过滤', exact: true }).click();
    const fixedReq1 = (await fixedNext).postDataJSON();
    const fixedAuto = browser.waitForRequest(isWindowedSource, { timeout: 20000 }); fixedAuto.catch(() => {});
    const fixedReq2 = (await fixedAuto).postDataJSON();
    h.check('Fixed UTC time range persists across subsequent automatic refreshes',
      fixedReq1?.from === '2026-01-01T00:00:00.000Z' && fixedReq1?.to === '2026-01-02T00:00:00.000Z' &&
      fixedReq2?.from === fixedReq1?.from && fixedReq2?.to === fixedReq1?.to, { fixedReq1, fixedReq2 });
    const restoredWindow = browser.waitForRequest(isWindowedSource, { timeout: 20000 }); restoredWindow.catch(() => {});
    await browser.locator('.application-page-runtime-surface').click({ button: 'right', position: { x: 40, y: 40 } });
    await browser.getByRole('button', { name: '最近时间窗', exact: true }).click();
    const restoredBody = (await restoredWindow).postDataJSON();
    h.check('Restoring relative window returns to live 24h UTC range cleanly',
      restoredBody?.from !== '2026-01-01T00:00:00.000Z' && Date.parse(restoredBody?.to) - Date.parse(restoredBody?.from) === 24 * 3600 * 1000, restoredBody);

    // Account switching: unauthorized viewer receives denial without polling; after explicit grant, viewer executes automatic refreshes under its own session.
    const viewer = await business.member(h, 'viewer');
    const viewerSession = (await h.ok(viewer, 'GET', '/api/v1/web/session/')).value;
    const viewerGrant = { kind: 'member-access-retirement', phase: 'created', accountId: viewerSession.account.id, installation: f.installations[0], commands: [], active: false, origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity) };
    h.state.resources.push(viewerGrant); f.pageGrants.push(viewerGrant); h.persist();
    await require('./application_authority_cases.cjs').accessCommand(h, viewerGrant, 'viewer', 0);
    const viewerRead = viewer.page.waitForResponse(r => exactSource(r.request(), viewer.origin, context), { timeout: 20000 }); viewerRead.catch(() => {});
    await viewer.page.goto(target, { waitUntil: 'networkidle' });
    await checkResponse(await viewerRead);
    const viewerNext = viewer.page.waitForResponse(r => exactSource(r.request(), viewer.origin, context), { timeout: 20000 }); viewerNext.catch(() => {});
    await checkResponse(await viewerNext);
    await h.screenshot(viewer, 'account-switch-viewer-auto-refresh');
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const identities = new Set(f.installations.map(i => String(i.id)));
    const open = h.state.resources.filter(r => r.kind === 'business-record' && identities.has(r.identity?.installationId) && r.phase !== 'deleted');
    if (!open.length) await page.disposeExplicitFixture(h, f, primary);
    else { h.observe({ kind: 'original-page-refresh-business-cleanup-open', count: open.length }); if (!primary) throw new h.Blocked('Retain exact installation until original row cleanup is proved'); }
  }
  if (!hiddenVerified) {
    h.observe({
      kind: 'special-branches-deferred',
      caseId: 'F069-005',
      classification: '[C]',
      note: 'Headed OS-window background tab pause/resume requires interactive window focus tracked in the special suite [C].',
    });
  }
}
scheduling.transport = 'owner-api';
module.exports = { handlers: { 'F069-005': scheduling }, exactSource };
