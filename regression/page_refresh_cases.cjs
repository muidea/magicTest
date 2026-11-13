// Exercise actual frozen read scheduling; all held traffic is read-only POST.
const { isDeepStrictEqual: same } = require('node:util');
const page = require('./page_runtime_cases.cjs');
const business = require('./business_cases.cjs');
function configure(content) {
  content.refresh = { seconds: 5, overlap: false, pauseWhenHidden: true, cancelOnLeave: true, failureBackoffSeconds: [10, 20] };
  content.navigation.push('static');
  content.pages.push({ key: 'static', title: '只读切换目标', routes: ['/static'], navigation: true, routeParameters: [], layout: { type: 'responsive-grid', columns: 12, gap: 0 },
    components: [{ key: 'static-text', type: 'text', layout: { span: 12, order: 0 }, dataSources: [], properties: { text: '原页面读取已离开' } }] });
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
  const f = await page.explicitFixture(h, configure, undefined, { suffix: 'pagerefresh', requestPrefix: 'page-refresh-' });
  const actor = await business.member(h, 'manager'), rows = [];
  let primary;
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
    const recovered = browser.waitForResponse(r => exactSource(r.request(), actor.origin, context) && r.status() === 200, { timeout: 30000 }); recovered.catch(() => {});
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
    let hiddenVerified = false, hiddenReads = 0, foreground;
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
  } catch (error) { primary = error; throw error; }
  finally {
    await business.finishCleanup(h, [...rows].reverse(), primary);
    const identities = new Set(f.installations.map(i => String(i.id)));
    const open = h.state.resources.filter(r => r.kind === 'business-record' && identities.has(r.identity?.installationId) && r.phase !== 'deleted');
    if (!open.length) await page.disposeExplicitFixture(h, f, primary);
    else { h.observe({ kind: 'original-page-refresh-business-cleanup-open', count: open.length }); if (!primary) throw new h.Blocked('Retain exact installation until original row cleanup is proved'); }
  }
  await h.partial('Exact frozen schedule, actual automatic reads at three widths, one actual read failure/error/10s backoff/real-owner recovery, held real original owner read beyond interval with no overlap, actual page navigation/late read disposal/return and independent original business row verified. Real hidden/resume outcome is separately evidenced and is not inferred when unsupported. Relative/fixed time windows, account switching and durable write panel remain unverified.');
}
scheduling.transport = 'owner-api';
module.exports = { handlers: { 'F069-005': scheduling }, exactSource };
