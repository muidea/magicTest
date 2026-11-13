// Saved installation receipts and task diagnostics are distinct owner facts.
const { isDeepStrictEqual: same } = require('node:util');
const { fixture } = require('./delivery_cases.cjs');
const business = require('./business_cases.cjs');
const native = require('./native_runtime_cases.cjs');
const base = '/panel/application/installations/';
const widths = [1440, 1024, 390];
function modelSummaryMatches(f, value, identity, database, schema) {
  const r = value?.receipt, b = r?.database;
  return value?.status === 'ready' && value.runtimeType === 'model-driven' && value.sourceKind === 'model-package' &&
    value.namespace === 'panel' && value.applicationUuid === f.application.uuid && value.sourceDigest === f.package.artifactDigest &&
    r?.storageRequired === true && business.installationMatches(f, value, identity) &&
    Number.isSafeInteger(r.runtimeApplicationId) && r.runtimeApplicationId > 0 && /^[a-f0-9]{32}$/.test(r.runtimeApplicationUuid) &&
    Array.isArray(r.completedSteps) && r.completedSteps.length > 0 && new Set(r.completedSteps).size === r.completedSteps.length &&
    b?.provisioningMode === 'allocate' && Number.isSafeInteger(b.bindingId) && b.bindingId > 0 &&
    database?.id === b.databaseResourceId && schema?.id === b.schemaResourceId && schema?.databaseResourceId === database?.id &&
    schema.databaseName === database.name && typeof schema.name === 'string' && schema.name.length > 0 &&
    database.status === 'active' && schema.status === 'active' && !value.failure && !value.receiptDiagnostic && !value.packagedReceipt;
}
async function summaryRow(h, drawer, label, expected) {
  // The inner has locator is evaluated relative to each row. Repeating the
  // outer drawer locator there would require another drawer inside that row.
  const row = drawer.locator('tr').filter({ has: h.admin.page.getByText(label, { exact: true }) });
  const actual = await row.locator('.ant-descriptions-item-content').allTextContents();
  h.check('Installation summary renders one exact owner-backed field: ' + label,
    await row.count() === 1 && actual.length === 1 && actual[0].trim() === expected, { label, expected, rows: await row.count(), actual });
}
async function settledDrawerGeometry(read, wait = () => new Promise(resolve => setTimeout(resolve, 30)), now = Date.now, budget = 10000) {
  const start = now(); let last, actual, stable = 0;
  // The first getAnimations() may precede rc-motion's opening transition.
  // Geometry must enter the viewport and settle, even if that list is empty.
  for (let n = 0; n < 350; n++) {
    actual = await read();
    const fits = actual.scroll <= actual.viewport + 1 && actual.left >= -1 && actual.right <= actual.viewport + 1;
    const unchanged = last && ['viewport', 'scroll', 'left', 'right'].every(k => Math.abs(actual[k] - last[k]) < 0.5);
    stable = fits && !actual.moving ? unchanged ? stable + 1 : 1 : 0;
    if (stable >= 3) return { ...actual, settled: true };
    if (now() - start >= budget || n === 349) break;
    last = actual; await wait();
  }
  return { ...actual, settled: false };
}
async function visibleSummary(h, value, width) {
  const page = h.admin.page;
  await page.setViewportSize({ width, height: 900 });
  await page.goto(h.admin.origin + '/panel/application/deployment/', { waitUntil: 'networkidle' });
  const row = page.locator('tr[data-row-key="' + value.id + '"]');
  await row.getByRole('button', { name: '安装详情', exact: true }).click();
  const drawer = page.locator('.ant-drawer:visible');
  await drawer.getByText('安装回执摘要', { exact: true }).waitFor();
  await drawer.locator('.ant-drawer-content-wrapper').evaluate(async element => {
    await Promise.all(element.getAnimations().map(animation => animation.finished.catch(() => {})));
  });
  await summaryRow(h, drawer, '运行应用身份', value.receipt.runtimeApplicationUuid);
  const b = value.receipt.database;
  await summaryRow(h, drawer, '存储绑定', `绑定 ${b.bindingId} / 数据库 ${b.databaseResourceId} / Schema ${b.schemaResourceId}`);
  await summaryRow(h, drawer, '原生就绪回执', '不适用');
  await summaryRow(h, drawer, '实例标识', value.instanceKey);
  await summaryRow(h, drawer, '内部实例 ID', value.deploymentId);
  await summaryRow(h, drawer, '安装 ID', String(value.id));
  await summaryRow(h, drawer, '制品摘要 (Source Digest)', value.sourceDigest);
  const text = await drawer.innerText();
  h.check('Saved receipt carries both actual-access advice and explicit current-health qualification',
    text.includes('通过应用入口验证实际访问；安装记录不替代当前运行健康检查。') &&
    text.includes('以上为保存的回执，不表示 Base、Gateway、Ingress') && text.includes('实际结构问题请使用结构诊断，执行失败请查看部署任务。'));
  const size = await settledDrawerGeometry(() => drawer.locator('.ant-drawer-content-wrapper').evaluate(el => {
    const rect = el.getBoundingClientRect();
    return { viewport: innerWidth, scroll: document.documentElement.scrollWidth, left: rect.left, right: rect.right,
      moving: el.getAnimations().some(a => a.pending || a.playState === 'running') };
  }));
  h.check('Installation drawer fits the declared viewport after bounded opening and stable geometry', size.settled && size.viewport === width, { width, ...size });
  await h.screenshot(h.admin, 'installation-summary-' + value.id + '-' + width);
  await drawer.getByRole('button', { name: 'Close', exact: true }).click();
  // Ant keeps the full-screen drawer root mounted after closing; its actual
  // content wrapper is the visibility boundary.
  await drawer.locator('.ant-drawer-content-wrapper').waitFor({ state: 'hidden' });
}
async function summary(h) {
  const f = await fixture(h), actor = await business.member(h, 'manager'), originals = [];
  const databases = await h.directory(h.admin, '/panel/storage-resources/databases/');
  const schemas = await h.directory(h.admin, '/panel/storage-resources/database-schemas/');
  for (let index = 0; index < f.installations.length; index++) {
    const value = (await h.ok(h.admin, 'GET', base + f.installations[index].id)).value;
    const runtime = await business.runtime(h, f, index, actor), binding = value.receipt?.database;
    const database = databases.find(v => v.id === binding?.databaseResourceId), schema = schemas.find(v => v.id === binding?.schemaResourceId);
    h.check('Saved summary joins exact installation, frozen artifact, actual runtime identity and independent current storage owner facts',
      modelSummaryMatches(f, value, runtime.identity, database, schema), { installation: value, runtimeIdentity: runtime.identity, database, schema });
    originals.push(value);
    for (const width of widths) await visibleSummary(h, value, width);
    h.check('Reading all summary widths preserves the entire original installation', same((await h.ok(h.admin, 'GET', base + value.id)).value, value));
  }
  await native.failedCleanup(h, async (r, component) => {
    h.check('Real intended failure has no installed receipt and cannot be presented as a ready or failed installation summary',
      native.expectedExitFailure(r) && !(await h.directory(h.admin, base)).some(v => v.deploymentId === r.last.deploymentId));
    const page = h.admin.page;
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(h.admin.origin + '/panel/operations/deployment-tasks/', { waitUntil: 'networkidle' });
      const card = page.locator('.ant-card').filter({ has: page.getByText('应用部署任务', { exact: true }) });
      const row = card.locator('tr[data-row-key="' + r.operation.id + '"]'); await row.waitFor();
      const message = row.getByText(r.operation.failureMessage, { exact: true }); await message.waitFor();
      h.check('Actual task UI displays the exact original failure and execution budget without a replacement operation',
        (await row.innerText()).includes(r.operation.attempt + '/' + r.operation.maxAttempts) && await message.count() === 1);
      await h.screenshot(h.admin, 'installation-failed-task-' + width);
    }
    h.check('Diagnosis reads preserve the complete original failed request, operation and their budget',
      same((await h.ok(h.admin, 'GET', '/panel/application/deployment-requests/' + r.id)).value, r.last) &&
      same((await h.ok(h.admin, 'GET', '/panel/operations/namespaces/panel/application-deployment-operations/' + r.operation.id)).value, r.operation));
    h.observe({ kind: 'installation-summary-original-failure', request: r.last, operation: r.operation, component,
      qualification: 'Real failed task diagnostics; owner confirms no installation record. Does not prove failed-installation summary branch.' });
  });
  for (const value of originals) h.check('Original dual model installations remain entirely unchanged after native failure and its formal disposal', same((await h.ok(h.admin, 'GET', base + value.id)).value, value));
  await h.partial('Exact successful dual model summaries, runtime/storage identity and saved-health qualification verified at three widths; real original native failure diagnosed and formally retired. No failed installation record was produced, so its summary/server nextAction branch remains unverified.');
}
summary.transport = 'owner-api';
module.exports = { handlers: { 'F034-001': summary }, modelSummaryMatches, summaryRow, settledDrawerGeometry };
