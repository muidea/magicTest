// Panel owns conditional policy writes; log owners consume this projection.
const { isDeepStrictEqual: same } = require('node:util');
const route = '/panel/operations/log-retention/';
const fields = { retentionDays: [0, 36500], cleanupIntervalSeconds: [1, 86400], cleanupBatchSize: [1, 5000], cleanupMaxBatches: [1, 100] };
const read = (h, actor = h.admin) => h.ok(actor, 'GET', route).then(r => r.value);
const payload = (document, policies = document.policies) => ({ expectedResourceVersion: document.resourceVersion, ...structuredClone(policies) });
const isOriginal = (h, r) => same(h.admin?.identity, r.actorIdentity) && h.admin?.origin === r.origin;
function journal(h, r, body) {
  if (!isOriginal(h, r) || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Retention command requires original owner and no unresolved original write');
  const command = { body: structuredClone(body), outcome: 'unknown' }; r.commands.push(command); h.persist(); return command;
}
async function acknowledged(h, r, c, response, before) {
  c.response = response; h.persist();
  const current = await read(h);
  if (h.good(response) && same(current, response.data.value) && current.resourceVersion === c.body.expectedResourceVersion + 1 && same(current.policies, { securityAudit: c.body.securityAudit, operationLog: c.body.operationLog })) {
    r.last = current; c.outcome = 'confirmed'; h.persist(); return current;
  }
  if ([200, 400, 409, 422].includes(response.status) && [4, 19].includes(response.data?.error?.code) && same(current, before)) { c.outcome = 'rejected-and-unchanged'; h.persist(); return current; }
  throw new h.Blocked('Original retention command has no exact independent outcome; preserve journal without replay');
}
async function write(h, r, policies) {
  const before = await read(h);
  h.check('Retention write uses only the exact previously acknowledged owner revision', same(before, r.last));
  const c = journal(h, r, payload(before, policies));
  const current = await acknowledged(h, r, c, await h.api(h.admin, 'PUT', route, c.body), before);
  h.check('Formal retention boundary save acknowledges both exact policies', c.outcome === 'confirmed');
  return current;
}
async function restore(h, r) {
  if (!isOriginal(h, r)) throw new h.Blocked('Retention restore requires original platform account and origin');
  const current = await read(h);
  if (r.phase === 'deleted') {
    h.check('Previously restored log retention policies still match original semantics', same(current.policies, r.original.policies));
    return { proof: 'Original retention policy semantics independently restored; historical resourceVersion is not rewritten' };
  }
  if (r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Unresolved original retention write; never replay restore');
  if (!same(current, r.last)) throw new h.Blocked('Concurrent retention owner revision differs; no overwrite');
  if (!same(current.policies, r.original.policies)) {
    const c = journal(h, r, payload(current, r.original.policies));
    await acknowledged(h, r, c, await h.api(h.admin, 'PUT', route, c.body), current);
    h.check('Original retention restoration is acknowledged', c.outcome === 'confirmed');
  }
  const after = await read(h);
  h.check('Independent owner read proves both original policies restored', same(after.policies, r.original.policies));
  r.phase = 'deleted'; r.restored = after; h.persist();
  return { proof: 'Conditional original-owner restore and independent complete policy read; no log data or historical revisions modified' };
}
async function uiReadFailure(h, r) {
  const page = h.admin.page, match = url => url.pathname === '/api/v1/web/proxy' + route;
  let reads = 0, writes = 0;
  const failure = async request => {
    if (request.request().method() === 'GET') { reads++; return request.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 21, message: 'controlled browser-local retention read failure' } }) }); }
    writes++; await request.abort('failed');
  };
  await page.route(match, failure);
  try {
    await page.goto(h.admin.origin + '/panel/operations/settings/', { waitUntil: 'networkidle' });
    const card = page.locator('.ant-card').filter({ has: page.getByText('日志保留策略', { exact: true }) });
    await card.getByText('日志保留策略暂时无法加载', { exact: true }).waitFor();
    h.check('Failed real policy read exposes neither invented default inputs nor a save action', reads > 0 && writes === 0 && await card.getByRole('spinbutton').count() === 0 && await card.getByRole('button', { name: '保存日志保留策略', exact: true }).count() === 0);
    await h.screenshot(h.admin, 'retention-read-failure');
  } finally { await page.unroute(match, failure); }
  await page.getByRole('button', { name: '重新加载', exact: true }).click();
  const input = page.getByRole('spinbutton', { name: '安全审计保留天数', exact: true });
  await input.waitFor();
  h.check('Recovery renders actual owner policy rather than defaults', Number(await input.inputValue()) === r.last.policies.securityAudit.retentionDays && same(await read(h), r.last));
  // Only open and cancel the destructive-action prompt. Short retention is
  // never dispatched against shared logs during a functional regression.
  await input.fill('1'); await input.press('Tab');
  let sent = 0; const watch = request => { if (request.method() === 'PUT' && match(new URL(request.url()))) sent++; };
  page.on('request', watch);
  try {
    await page.getByRole('button', { name: '保存日志保留策略', exact: true }).click();
    const prompt = page.getByText('缩短保留时间会在后续清理中永久删除旧记录，确认保存？', { exact: true });
    await prompt.waitFor();
    const popover = page.locator('.ant-popover').filter({ has: prompt });
    await popover.getByRole('button', { name: /取\s*消/ }).click();
    h.check('Shortening prompt explains permanent deletion and cancel sends no policy write', sent === 0 && same(await read(h), r.last));
    await h.screenshot(h.admin, 'retention-shortening-cancelled');
  } finally { page.off('request', watch); }
}
async function boundaries(h) {
  // Positive retention can make old records eligible for deletion. Admit it
  // only after proving this is the dedicated isolated fixture daemon.
  const isolated = !!h.deliveryFixtureConfig;
  if (isolated) await require('./delivery_cases.cjs').fixture(h);
  const original = await read(h);
  h.check('Complete policy owner read has both declared policies and safe conditional revision', Number.isSafeInteger(original.resourceVersion) && original.resourceVersion >= 0 && same(Object.keys(original.policies).sort(), ['operationLog', 'securityAudit']));
  const r = { kind: 'log-retention-restore', phase: 'created', original, last: original, actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin, commands: [] };
  h.state.resources.push(r); h.persist();
  try {
    for (const type of ['securityAudit', 'operationLog']) for (const [field, [min, max]] of Object.entries(fields)) for (const invalid of [min - 1, max + 1]) {
      const before = await read(h), body = payload(before); body[type][field] = invalid;
      const c = journal(h, r, body), response = await h.api(h.admin, 'PUT', route, body);
      await acknowledged(h, r, c, response, before);
      h.check('Owner rejects out-of-range ' + type + '.' + field + '=' + invalid + ' without changing either policy', c.outcome === 'rejected-and-unchanged' && response.data?.error?.code === 4, response);
    }
    // Keep retention permanently disabled while testing fast cleanup limits.
    const low = { retentionDays: 0, cleanupIntervalSeconds: 1, cleanupBatchSize: 1, cleanupMaxBatches: 1 };
    const high = { retentionDays: 0, cleanupIntervalSeconds: 86400, cleanupBatchSize: 5000, cleanupMaxBatches: 100 };
    await write(h, r, { securityAudit: low, operationLog: high });
    await write(h, r, { securityAudit: high, operationLog: low });
    await uiReadFailure(h, r);
    const before = await read(h), bodies = [{ securityAudit: low, operationLog: high }, { securityAudit: high, operationLog: high }].map(p => payload(before, p));
    // Persist both concurrent commands before either is dispatched.
    const commands = bodies.map(body => ({ body, outcome: 'unknown' })); r.commands.push(...commands); h.persist();
    const outcomes = await Promise.all(commands.map(c => h.api(h.admin, 'PUT', route, c.body)));
    commands.forEach((c, i) => { c.response = outcomes[i]; }); h.persist();
    const after = await read(h), winner = outcomes.findIndex(h.good), loser = winner === 0 ? 1 : 0;
    h.check('Same-version concurrent retention writes have exactly one acknowledged winner and one explicit conflict', outcomes.filter(h.good).length === 1 && outcomes[loser].data?.error?.code === 19, outcomes);
    h.check('Independent owner confirms exactly one revision and both winning policies', same(after, outcomes[winner].data.value) && after.resourceVersion === before.resourceVersion + 1 && same(after.policies, { securityAudit: bodies[winner].securityAudit, operationLog: bodies[winner].operationLog }));
    commands[winner].outcome = 'confirmed'; commands[loser].outcome = 'rejected-conflict'; r.last = after; h.persist();
    if (isolated) {
      for (const days of [1, 36500]) {
        const policy = { ...high, retentionDays: days };
        await write(h, r, { securityAudit: policy, operationLog: policy });
      }
    }
  } finally { await restore(h, r); }
  if (!isolated) await h.partial('Out-of-range limits, zero-day permanent retention, both cleanup-limit extrema, concurrent conditional writes and UI read-failure/shortening-cancel verified. Positive retentionDays=36500 requires an isolated log owner: shared failure history is never made eligible for deletion by this executor.');
}
boundaries.transport = 'owner-api';
module.exports = { handlers: { 'F058-002': boundaries }, restore, fields };
