const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const collection = '/panel/operations/database-instances/';
const placements = '/panel/operations/namespace-storage-placements/';
const duplicate = r => [200, 400, 409, 422].includes(r.status) && r.data?.error?.code === 7 && /数据库端点已登记/.test(r.data.error.message) && r.data.value == null;
const connectionFailure = r => [200, 400, 500, 502, 503].includes(r.status) && r.data?.error?.code !== undefined && ![5, 11, 12, 22].includes(r.data.error.code) && r.data.value == null && /(?:dial tcp|connect: connection refused|failed to connect|连接失败|连接被拒绝)/i.test(r.data.error.message);
function unchanged(rows, before) { return rows.length === before.length && before.every(value => rows.some(row => same(row, value))); }
async function duplicateAttempt(h, original, before, payload) {
  const r = { collection, kind: 'database-instance', name: payload.name, phase: 'intent', creation: {
    journalId: crypto.randomBytes(16).toString('hex'), actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
    identity: { name: payload.name }, intended: structuredClone(payload), outcome: 'unknown'
  } };
  h.state.resources.push(r); h.persist();
  const response = await (h.ownerApi || h.api)(h.admin, 'POST', collection, payload);
  r.creation.response = response; r.creation.outcome = h.good(response) ? 'accepted' : 'unconfirmed';
  if (h.good(response) && Number.isSafeInteger(response.data.value?.id) && response.data.value.id > 0) { r.id = response.data.value.id; r.phase = 'created'; }
  h.persist();
  const rows = await h.directory(h.admin, collection), current = (await h.ok(h.admin, 'GET', collection + original.id)).value;
  const rejected = duplicate(response), preserved = unchanged(rows, before) && same(current, original);
  if (rejected && preserved) { r.creation.outcome = 'rejected-and-original-directory-unchanged'; r.phase = 'deleted'; h.persist(); }
  h.check('Duplicate original physical endpoint reaches formal uniqueness refusal, never an auth or storage failure', rejected, response);
  h.check('Duplicate refusal preserves complete original directory and exact existing resource', preserved, { beforeIDs: before.map(v => v.id), afterIDs: rows.map(v => v.id), current });
}
async function boundaries(h) {
  const baseline = await h.directory(h.admin, collection), beforePlacements = await h.directory(h.admin, placements);
  const address = '127.0.0.1:9';
  if (baseline.some(row => row.engine === 'postgresql' && row.address === address)) throw new h.Blocked('Boundary endpoint is already registered; never reuse or mutate another owner resource');
  const payload = { name: h.state.prefix + '-wrong-db', catalog: 'regression', engine: 'postgresql', engineVersion: '17', address,
    administrator: 'regression_unused', password: h.state.password, description: '禁用的错误连接回归目录；不供应安装、不创建数据库',
    cpuMillis: 1000, memoryBytes: 1024 * 1024 * 1024, databaseLimit: 1, status: 'disabled', healthStatus: 'unknown' };
  const created = await h.create(collection, payload, 'database-instance');
  const original = (await h.ok(h.admin, 'GET', collection + created.id)).value;
  h.check('Boundary resource is disabled, has zero allocations, and never exposes the submitted private password', original.status === 'disabled' && original.allocatedDatabaseCount === 0 && original.address === address && original.engine === 'postgresql' && original.resourceVersion === 1 && !JSON.stringify(original).includes(payload.password), original);
  const before = await h.directory(h.admin, collection);
  h.check('Creation adds only the original isolated endpoint to the complete directory', before.length === baseline.length + 1 && before.some(row => same(row, original)) && baseline.every(value => before.some(row => same(row, value))));
  for (const [index, address] of ['127.0.0.1:00009', '[::ffff:127.0.0.1]:9'].entries()) await duplicateAttempt(h, original, before, { ...payload, name: h.state.prefix + '-duplicate-db-' + index, address });
  const afterCreatePlacements = await h.directory(h.admin, placements);
  h.check('Original registration has exactly one formal default placement and duplicates create no extras', afterCreatePlacements.filter(row => row.instance?.id === original.id).length === 1 && afterCreatePlacements.length === beforePlacements.length + 1 && beforePlacements.every(value => afterCreatePlacements.some(row => same(row, value))), afterCreatePlacements.filter(row => row.instance?.id === original.id));
  const failures = [];
  for (const operation of ['overview', 'databases']) {
    const response = await h.api(h.admin, 'GET', collection + original.id + '/explorer/' + operation);
    h.check('Database failure response does not expose the original submitted private password', !JSON.stringify(response).includes(payload.password));
    failures.push({ operation, response });
  }
  h.check('Failed read-only connections cannot change original registration or allocated resources', same((await h.ok(h.admin, 'GET', collection + original.id)).value, original) && unchanged(await h.directory(h.admin, collection), before) && unchanged(await h.directory(h.admin, placements), afterCreatePlacements));
  // Preserve all original responses and dispose our metadata before evaluating
  // the diagnostic stage. Generic storage/auth errors cannot fake a dial test.
  await h.remove(collection, original.id);
  h.check('Formal deletion removes only the original endpoint and its automatically owned default placement', unchanged(await h.directory(h.admin, collection), baseline) && unchanged(await h.directory(h.admin, placements), beforePlacements));
  h.check('Each public explorer reached a real wrong-connection diagnostic', failures.every(({ response }) => connectionFailure(response)), failures);
}
async function management(h) {
  const baseline = await h.directory(h.admin, collection), beforePlacements = await h.directory(h.admin, placements);
  const physical = await require('./postgres_fixture.cjs').createPostgres(h);
  const originalControls = require('./postgres_fixture.cjs').readControls(h, physical);
  const payload = { name: h.state.prefix + '-physical-db', catalog: 'regression', engine: 'postgresql', engineVersion: '17', address: physical.address,
    administrator: physical.username, password: physical.password, description: '独立无持久卷数据库；规格只作规划', cpuMillis: 1000, memoryBytes: 1024 ** 3,
    databaseLimit: 1, status: 'disabled', healthStatus: 'unknown' };
  const created = await h.create(collection, payload, 'database-instance');
  const resource = h.state.resources.find(r => r.collection === collection && r.id === created.id);
  const read = () => h.ok(h.admin, 'GET', collection + created.id).then(r => r.value);
  let current = await read();
  h.check('New resource preserves exact connection identity and masks original private credential', current.id === created.id && current.address === physical.address && current.administrator === physical.username && current.status === 'disabled' && current.allocatedDatabaseCount === 0 && !JSON.stringify(current).includes(physical.password), current);
  const originalPlacement = (await h.directory(h.admin, placements)).filter(p => p.instance?.id === created.id);
  h.check('New physical endpoint owns exactly one default placement', originalPlacement.length === 1 && originalPlacement[0].mode === 'shared' && originalPlacement[0].namespace === '', originalPlacement);
  const command = async (route, body, confirm) => {
    if (resource.pendingDatabaseCommands?.some(c => !c.confirmed)) throw new h.Blocked('Original database mutation is unresolved; no replay');
    const intent = { route, body: structuredClone(body), confirmed: false };
    (resource.pendingDatabaseCommands ||= []).push(intent); h.persist();
    intent.response = await h.api(h.admin, 'PUT', route, body); h.persist();
    h.check('Original database command is acknowledged', h.good(intent.response), intent.response);
    await confirm(); intent.confirmed = true; h.persist();
  };
  const target = h.need('tenantA').name, foreign = h.need('tenantB').name;
  await command(placements + originalPlacement[0].id, { namespace: target, instanceId: created.id, mode: 'dedicated', status: 'active', expectedResourceVersion: originalPlacement[0].resourceVersion }, async () => {
    const rows = await h.directory(h.admin, placements);
    const value = rows.find(row => row.id === originalPlacement[0].id);
    h.check('Independent placement owner confirms conditional exact tenant exclusivity before enabling database', value?.id === originalPlacement[0].id && value.instance.id === created.id && value.namespace === target && value.mode === 'dedicated' && value.status === 'active' && value.resourceVersion > originalPlacement[0].resourceVersion, value);
  });
  const options = async n => {
    const value = (await h.ok(h.admin, 'GET', '/panel/operations/namespaces/' + n + '/application-storage-options/')).value;
    h.check('Storage option projection belongs to the exact requested original tenant', value.namespace === n);
    return value.instances.some(v => v.id === created.id);
  };
  h.check('Disabled original endpoint is not an allocation candidate', !(await options(target)) && !(await options(foreign)));
  const beforeOverview = (await h.ok(h.admin, 'GET', collection + created.id + '/explorer/overview')).value.overview;
  const edit = async status => {
    const before = current, update = { ...payload, password: '', name: payload.name + '-edited', address: physical.alternateAddress, description: '已更新规划容量，不修改实际服务器硬限额', cpuMillis: 2000, memoryBytes: 2 * 1024 ** 3, databaseLimit: 3, status };
    await command(collection + created.id, update, async () => {
      current = await read();
      h.check('Independent database owner persists complete original edit, increments resource revision and retains physical ownership', current.id === before.id && current.address === physical.alternateAddress && current.administrator === physical.username && current.name === update.name && current.description === update.description && current.cpuMillis === update.cpuMillis && current.memoryBytes === update.memoryBytes && current.databaseLimit === 3 && current.status === status && current.resourceVersion > before.resourceVersion && current.allocatedDatabaseCount === 0 && !JSON.stringify(current).includes(physical.password), current);
    });
  };
  await edit('active');
  h.check('Active dedicated physical resource is selectable only in its original tenant', await options(target) && !(await options(foreign)));
  const explore = async operation => {
    const result = (await h.ok(h.admin, 'GET', collection + created.id + '/explorer/' + operation)).value;
    h.check('Real database explorer does not expose the original generated credential', !JSON.stringify(result).includes(physical.password));
    h.observe({ kind: 'original-physical-database-explorer', databaseInstanceID: created.id, operation, result });
    return result;
  };
  const overview = (await explore('overview')).overview, databases = (await explore('databases')).databases;
  h.check('Public explorer connects to actual PostgreSQL and reads the independent fixture database and owner', /^17\./.test(overview.serverVersion) && overview.databaseCount >= 2 && databases.some(d => d.name === physical.database && d.owner === physical.username), { overview, databases });
  h.check('Planning edits preserve actual server identity, observed container controls and database count', current.memoryBytes === 2 * 1024 ** 3 && same(require('./postgres_fixture.cjs').readControls(h, physical), originalControls) && overview.databaseCount === beforeOverview.databaseCount && overview.startedAt === beforeOverview.startedAt && overview.maxConnections === beforeOverview.maxConnections, originalControls);
  const page = h.admin.page;
  await page.goto(h.admin.origin + '/panel/database/?tab=instance', { waitUntil: 'networkidle' });
  const row = page.locator('tr[data-row-key="' + created.id + '"]');
  try {
    await row.waitFor();
    h.check('Real database directory shows original edited identity and dedicated tenant', (await row.innerText()).includes(current.name) && (await row.innerText()).includes(target));
    await row.getByRole('button', { name: '控制台', exact: true }).click();
    const drawer = page.locator('.ant-drawer-content').filter({ hasText: '数据库控制台 · ' + current.name });
    await drawer.waitFor();
    await drawer.locator('.ant-select-selector').first().click();
    const schemaRead = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith(collection + created.id + '/explorer/schemas') && url.searchParams.get('database') === physical.database && response.request().method() === 'GET';
    });
    schemaRead.catch(() => {});
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content').filter({ hasText: physical.database }).click();
    const response = await schemaRead, data = await response.json();
    h.check('Real control selects original fixture database and owner returns its actual public schema', response.status() === 200 && data.error == null && data.value?.schemas?.some(schema => schema.name === 'public'), data);
    await drawer.locator('.ant-select-selection-item').filter({ hasText: physical.database }).waitFor();
    await h.screenshot(h.admin, 'original-postgres-explorer');
    await page.goto(h.admin.origin + '/panel/database/?tab=instance', { waitUntil: 'networkidle' });
  } catch (error) { await h.screenshot(h.admin, 'database-explorer-unresolved'); throw error; }
  for (const status of ['draining', 'disabled']) {
    await edit(status);
    h.check('Original non-active state withdraws new allocation candidacy without deleting the directory', !(await options(target)) && !(await options(foreign)) && (await read()).id === created.id);
  }
  h.check('Planning and read-only exploration create no managed databases or allocations', current.allocatedDatabaseCount === 0);
  await h.remove(collection, created.id);
  h.check('Formal original resource deletion removes only its owned directory and placement', unchanged(await h.directory(h.admin, collection), baseline) && unchanged(await h.directory(h.admin, placements), beforePlacements));
  await physical.cleanup();
}
management.actors = ['tenantAdmin', 'otherTenantAdmin'];

async function reconcileDatabaseCommands(h, resource) {
  if (resource.kind !== 'database-instance' || resource.collection !== collection || !same(resource.creation?.actorIdentity, h.admin.identity) || resource.creation?.origin !== h.admin.origin || !h.good(resource.creation?.response || { status: 0, data: {} }) || resource.creation.response.data.value?.id !== resource.id) throw new h.Blocked('Database reconciliation requires exact acknowledged original resource and creator');
  for (const command of resource.pendingDatabaseCommands || []) {
    if (command.confirmed) continue;
    const ack = command.response, value = ack?.data?.value, body = command.body;
    if (!body || command.route !== placements + value?.id || body.instanceId !== resource.id || body.mode !== 'dedicated' || body.status !== 'active' || !h.good(ack || { status: 0, data: {} }) || value.resourceVersion !== body.expectedResourceVersion + 1 || value.instance?.id !== resource.id || value.namespace !== body.namespace || value.mode !== body.mode || value.status !== body.status) throw new h.Blocked('Original database mutation has no supported exact acknowledged placement proof; never replay');
    const rows = await h.directory(h.admin, placements), current = rows.find(row => row.id === value.id);
    h.check('Complete independent placement directory confirms exact original acknowledged command without replay', same(current, value), { originalPlacementId: value.id, observed: current });
    command.reconciliation = { proof: 'Original PUT ACK and complete independent exact placement read; unsupported GET was an executor error, no PUT replay', originalResourceID: resource.id, placementID: value.id };
    command.confirmed = true; h.persist();
  }
}
module.exports = { handlers: { 'F047-001': management, 'F047-002': boundaries }, duplicate, connectionFailure, reconcileDatabaseCommands };
