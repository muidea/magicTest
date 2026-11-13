#!/usr/bin/env node
// Prepare durable public-owner fixtures only inside a dedicated nested daemon.
// Published definitions are retained as immutable fixture facts, never called deleted.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual: same } = require('node:util');
const { ownerRequest } = require('./owner_transport.cjs');
const { withOriginalCasForms } = require('./cas_form_transport.cjs');
const { createResource } = require('./resource_lifecycle.cjs');
const { sanitize } = require('./evidence_sanitizer.cjs');

function validateIsolation(config, info, hostname = os.hostname()) {
  const root = config.platformRoot, data = config.dockerDataRoot;
  if (!root?.startsWith('/tmp/platform-executor-') || path.resolve(root) !== root ||
      !data || data !== path.join(path.dirname(root), 'docker-data') ||
      info.ID !== config.daemonId || info.DockerRootDir !== data || info.Driver !== 'overlay2' ||
      !config.containerId?.match(/^[a-f0-9]{64}$/) || hostname !== config.containerId.slice(0, 12)) {
    throw Error('Dedicated nested daemon and original owned root are required');
  }
}
function dedicatedDeliveryOnly(selected, handlers, config, state) {
  return typeof config === 'string' && !!config.trim() && Array.isArray(selected) && selected.length > 0 &&
    Array.isArray(state?.resources) && state.resources.length === 0 && state.fixtures && Object.keys(state.fixtures).length === 0 &&
    selected.every(entry => handlers[entry.id]?.requiresOnlyDeliveryFixture === true && !handlers[entry.id].actors?.length);
}
function resumeBootstrapAllowed(state) {
  return state?.stage === 'bootstrap-in-progress' && state.originalCasForms?.length === 0 &&
    state.commands?.length === 0 && state.resources?.length === 0 && state.passwordChange == null;
}
function persistFile(file, value) {
  const temporary = file + '.' + crypto.randomBytes(8).toString('hex');
  const fd = fs.openSync(temporary, 'wx', 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  fs.renameSync(temporary, file);
  const directory = fs.openSync(path.dirname(file), 'r');
  try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
}
function fixtureManifest(state, config) {
  return { status: 'published', fixtureScope: 'dedicated isolated daemon', daemonId: config.daemonId,
    application: state.application, revision: state.revision, package: state.package,
    installations: state.installations || [], deploymentRequests: state.deploymentRequests || [],
    members: Object.fromEntries(Object.entries(state.members || {}).map(([key, value]) => [key, { account: value.account, id: value.id, namespace: 'panel', access: value.access }])),
    disposition: 'Published definitions and owner receipts intentionally retained in private isolated deployment; no deletion, cleanup or acceptance claim.' };
}
async function main() {
  const [configFile, action] = process.argv.slice(2);
  if (!configFile || !['bootstrap', 'resume-bootstrap', 'publish', 'install', 'resume-install', 'members'].includes(action)) throw Error('Expected private config and bootstrap, resume-bootstrap, publish, install, resume-install or members');
  const bootstrap = ['bootstrap', 'resume-bootstrap'].includes(action);
  const config = JSON.parse(fs.readFileSync(configFile));
  validateIsolation(config, JSON.parse(execFileSync('docker', ['info', '--format', '{{json .}}'], { encoding: 'utf8' })));
  const root = path.resolve(__dirname, '..'), privateRoot = config.privateRoot;
  if (!privateRoot?.startsWith(path.dirname(config.platformRoot) + '/') ||
      privateRoot === config.platformRoot || privateRoot.startsWith(config.platformRoot + '/')) throw Error('Independent owned private fixture directory required');
  fs.mkdirSync(privateRoot, { recursive: true, mode: 0o700 });
  const file = path.join(privateRoot, 'fixture-state.json');
  const state = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file)) : {
    prefix: 'rg' + crypto.randomBytes(4).toString('hex'), commands: [], resources: [], originalCasForms: [],
    daemonId: config.daemonId, containerId: config.containerId, stage: 'new', assertions: [], observations: [] };
  if (state.daemonId !== config.daemonId || state.containerId !== config.containerId ||
      state.commands.some(c => c.outcome === 'unknown') || state.originalCasForms.some(c => ['sending', 'unknown', 'response-not-delivered'].includes(c.phase))) throw Error('Original fixture identity or command remains unresolved; no replay');
  const persist = () => persistFile(file, state); persist();
  if (action === 'resume-bootstrap' && !resumeBootstrapAllowed(state)) throw Error('Bootstrap resume requires exact original pre-command state; no CAS form or password-change replay');
  const check = (message, condition, details) => {
    state.assertions.push({ message, passed: !!condition, details: sanitize(details) }); persist();
    if (!condition) throw Error(message);
  };
  const { chromium } = require('./playwright.cjs');
  const browser = await chromium.launch({ executablePath: config.chrome || '/usr/bin/chromium-browser', headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--no-proxy-server', '--host-resolver-rules=MAP *.local.vpc 127.0.0.1'] });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const actor = { page: await context.newPage(), context, origin: 'https://panel.local.vpc', identity: { account: 'platform-admin', namespace: 'panel' } };
    const observe = event => { state.observations.push(sanitize(event)); persist(); };
    const api = (principal, method, route, body) => ownerRequest(principal, method, route, body, observe);
    const good = r => r.status === 200 && !r.data.error && !('text' in r.data);
    const ok = async (...args) => { const r = await api(...args); check(args[1] + ' ' + args[2], good(r), r); return r.data; };
    const credentialsFile = path.join(privateRoot, 'credentials.json');
    if (state.stage !== { bootstrap: 'new', 'resume-bootstrap': 'bootstrap-in-progress', publish: 'bootstrapped', install: 'published', 'resume-install': 'install-in-progress', members: 'installed' }[action]) throw Error('Action requires the exact original predecessor stage; read original state without replay');
    state.stage = (bootstrap ? 'bootstrap' : action === 'resume-install' ? 'install' : action) + '-in-progress'; persist();
    const credentials = bootstrap ? { origin: actor.origin, namespace: 'panel', account: 'platform-admin',
      password: fs.readFileSync(path.join(config.platformRoot, 'services/secret/cas/bootstrap-admin-password'), 'utf8').trim() } : JSON.parse(fs.readFileSync(credentialsFile));
    await withOriginalCasForms(actor, { journal: state.originalCasForms, persist, record: observe }, async () => {
      await actor.page.goto(actor.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
      await actor.page.locator('input[name=account]').fill(credentials.account);
      await actor.page.locator('input[name=password]').fill(credentials.password);
      await actor.page.locator('form[action="/oauth/login"] button[type=submit]').click();
      await actor.page.waitForFunction(() => document.querySelector('form[action="/oauth/password/change"]') || ['/portal', '/panel'].some(p => location.pathname.startsWith(p)) || new URL(location.href).searchParams.has('error'), {}, { timeout: 60000 });
      if (bootstrap) {
        check('Fresh isolated account requires initial password change', await actor.page.locator('form[action="/oauth/password/change"]').count() === 1);
        state.passwordChange = { password: 'Fixture@' + crypto.randomBytes(20).toString('hex'), outcome: 'unknown' }; persist();
        await actor.page.locator('#cas-new-password').fill(state.passwordChange.password);
        await actor.page.locator('#cas-new-password-confirm').fill(state.passwordChange.password);
        await actor.page.locator('form[action="/oauth/password/change"] button[type=submit]').click();
      }
      await actor.page.waitForURL(u => ['/portal', '/panel'].some(p => u.pathname.startsWith(p)), { timeout: 45000 });
      const session = (await ok(actor, 'GET', '/api/v1/web/session/')).value;
      check('Independent session confirms original isolated account and tenant', session.account?.account === 'platform-admin' && session.homeNamespace === 'panel');
    });
    if (bootstrap) {
      credentials.password = state.passwordChange.password;
      persistFile(credentialsFile, credentials); state.passwordChange.outcome = 'confirmed'; state.stage = 'bootstrapped'; persist();
      console.log(JSON.stringify({ status: 'bootstrapped', fixtureScope: 'dedicated isolated daemon; no shared platform changes' })); return;
    }
    const h = { fs, path, root, state, persist, admin: actor, api, ownerApi: api, ok, good, check, observe, Blocked: Error };
    h.create = (collection, body, kind) => createResource(h, actor, 'admin', collection, body, kind);
    h.directory = route => require('./directory.cjs').readDirectory(h, actor, route);
    async function command(route, body, independentRead, confirm = same) {
      const c = { method: 'POST', route, body, outcome: 'unknown' }; state.commands.push(c); persist();
      const r = await api(actor, 'POST', route, body); c.response = r; persist();
      check('Original delivery owner command acknowledged', good(r), r);
      const value = await independentRead(r.data.value);
      check('Independent exact delivery owner read confirms original receipt', confirm(value, r.data.value), value);
      c.outcome = 'confirmed'; persist(); return value;
    }
    if (action === 'members') {
      state.members = {}; persist();
      for (const [role, access] of [['manager', 'manager'], ['viewer', 'viewer'], ['outsider', '']]) {
        const password = 'Member@' + crypto.randomBytes(20).toString('hex');
        const account = await h.create('/cas/namespaces/panel/accounts/', { account: state.prefix + '-' + role,
          displayName: 'Regression ordinary ' + role, password, status: 2, roleTemplateKeys: ['portal-basic-user'] }, 'account');
        state.members[role] = { account: account.account, id: account.id, password, access, assignments: [] }; persist();
        if (access) for (const instance of state.installations) {
          const collection = '/panel/application/installations/' + instance.id + '/access-operations/';
          const generation = (await ok(actor, 'GET', '/panel/application/installations/' + instance.id + '/access-generation?accountId=' + account.id)).value;
          check('Formal CAS generation belongs to exact original account and instance', generation.accountId === account.id && generation.deploymentId === instance.deploymentId && generation.namespace === 'panel');
          const submission = crypto.randomBytes(16).toString('hex');
          const intent = await command(collection, { submissionId: submission, assignmentId: 0, accountId: account.id, accessLevel: access, expectedEpoch: generation.epoch, reason: 'Dedicated ordinary regression member' },
            () => ok(actor, 'GET', collection + '?submissionId=' + submission).then(r => r.value));
          const completed = await command(collection + intent.id + '/execute', { expectedVersion: intent.version, resumeOriginal: false },
            () => ok(actor, 'GET', collection + '?submissionId=' + submission).then(r => r.value));
          check('Formal assignment coordinator confirms exact completed ordinary member grant', completed.status === 'completed' && completed.accountId === account.id && completed.installationId === instance.id && completed.accessLevel === access && completed.assignmentId > 0, completed);
          state.members[role].assignments.push(completed); persist();
        }
        const memberContext = await browser.newContext({ ignoreHTTPSErrors: true });
        const member = { page: await memberContext.newPage(), context: memberContext, origin: actor.origin, identity: { account: account.account, namespace: 'panel' } };
        await withOriginalCasForms(member, { journal: state.originalCasForms, persist, record: observe }, async () => {
          await member.page.goto(member.origin + '/api/v1/web/auth/login?return_to=%2Fportal%2F', { waitUntil: 'networkidle' });
          await member.page.locator('input[name=account]').fill(account.account); await member.page.locator('input[name=password]').fill(password);
          await member.page.locator('form[action="/oauth/login"] button[type=submit]').click();
          await member.page.waitForFunction(() => document.querySelector('form[action="/oauth/password/change"]') || ['/portal', '/panel'].some(p => location.pathname.startsWith(p)), {}, { timeout: 60000 });
          if (await member.page.locator('form[action="/oauth/password/change"]').count()) {
            const change = { password: 'Member@' + crypto.randomBytes(20).toString('hex'), outcome: 'unknown' };
            state.members[role].passwordChange = change; persist();
            await member.page.locator('#cas-new-password').fill(change.password); await member.page.locator('#cas-new-password-confirm').fill(change.password);
            await member.page.locator('form[action="/oauth/password/change"] button[type=submit]').click();
          }
          await member.page.waitForURL(u => ['/portal', '/panel'].some(p => u.pathname.startsWith(p)), { timeout: 45000 });
          const session = (await ok(member, 'GET', '/api/v1/web/session/')).value;
          check('Independent ordinary session retains exact member and panel tenant', session.account?.account === account.account && session.homeNamespace === 'panel');
          const change = state.members[role].passwordChange;
          if (change) { change.outcome = 'confirmed'; state.members[role].password = change.password; persist(); }
        });
        await memberContext.close();
      }
      state.stage = 'members-ready'; persist();
      persistFile(path.join(privateRoot, 'member-credentials.json'), state.members);
      persistFile(path.join(privateRoot, 'fixture-manifest.json'), fixtureManifest(state, config));
      console.log(JSON.stringify({ status: 'members-ready', roles: Object.keys(state.members), scope: 'Formal CAS accounts and Panel access operations; no runtime business acceptance claim' })); return;
    }
    if (['install', 'resume-install'].includes(action)) {
      const pkg = (await ok(actor, 'GET', '/panel/application/model-packages/' + state.package.id)).value;
      check('Installation uses exact original immutable package', same(pkg, state.package));
      let storage = (await ok(actor, 'GET', '/panel/application/installations/storage-options/')).value;
      if (!storage.allocation?.available) {
        const instances = await h.directory('/panel/operations/database-instances/');
        check('Fresh isolated foundation endpoint is not already registered', !instances.some(v => v.address === 'postgres:5432'));
        const env = Object.fromEntries(fs.readFileSync(path.join(config.platformRoot, 'services/.env'), 'utf8').split('\n').filter(line => /^[A-Z_]+=/.test(line)).map(line => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));
        check('Dedicated foundation credentials are materialized', !!env.POSTGRES_ROOT && !!env.POSTGRES_ROOT_PASSWORD && env.POSTGRES_ROOT_PASSWORD !== 'CHANGE_ME');
        state.databaseInstance = await h.create('/panel/operations/database-instances/', {
          name: state.prefix + '-delivery-db', catalog: 'regression', engine: 'postgresql', engineVersion: '17', address: 'postgres:5432',
          administrator: env.POSTGRES_ROOT, password: env.POSTGRES_ROOT_PASSWORD, description: 'Dedicated isolated deployment fixture pool',
          cpuMillis: 1000, memoryBytes: 1024 ** 3, databaseLimit: 20, status: 'active', healthStatus: 'unknown'
        }, 'database-instance'); persist();
        storage = (await ok(actor, 'GET', '/panel/application/installations/storage-options/')).value;
      }
      check('Formal owner exposes available automatic storage', storage.allocation?.available === true);
      if (action === 'install') { state.deploymentRequests = []; state.installations = []; persist(); }
      for (const suffix of ['one', 'two']) {
        const existing = state.deploymentRequests.find(v => v.instanceKey === state.prefix + '-' + suffix);
        if (state.installations.some(v => v.instanceKey === state.prefix + '-' + suffix)) {
          const saved = state.installations.find(v => v.instanceKey === state.prefix + '-' + suffix);
          check('Previously confirmed original installation still matches owner', same((await ok(actor, 'GET', '/panel/application/installations/' + saved.id)).value, saved));
          continue;
        }
        const request = existing || await command('/panel/application/deployment-requests/', {
          sourceKind: 'model-package', packageId: pkg.id, expectedDigest: pkg.artifactDigest,
          instanceKey: state.prefix + '-' + suffix, instanceName: 'Regression fixture ' + suffix,
          storageProvisioning: { mode: 'allocate' }, reason: 'Dedicated regression delivery fixture'
        }, value => ok(actor, 'GET', '/panel/application/deployment-requests/' + value.id).then(r => r.value));
        if (!existing) { state.deploymentRequests.push(request); persist(); }
        const ops = '/panel/operations/namespaces/panel/application-deployment-requests/' + request.id;
        let approved;
        if (existing) {
          const receipt = state.commands.find(c => c.route === ops + '/approve');
          check('Resume binds original acknowledged approval and operation without command replay', receipt?.outcome === 'confirmed' && receipt.response.data.value.id === request.id && receipt.response.data.value.operationId === request.operationId);
          approved = (await ok(actor, 'GET', ops)).value;
          check('Independent original request keeps exact approved operation and plan', approved.id === request.id && approved.operationId === request.operationId && approved.planDigest === request.planDigest);
        } else {
          const options = (await ok(actor, 'GET', ops + '/runtime-options')).values;
          const bases = options.filter(v => v.kind === 'base'), gateways = options.filter(v => v.kind === 'gateway');
          check('Dedicated fixture has unambiguous registered Base and Gateway candidates', bases.length === 1 && gateways.length === 1, options);
          approved = await command(ops + '/approve', { expectedVersion: request.version, reason: 'Approve isolated regression fixture',
          runtimePlacement: { executionInstanceId: bases[0].id, gatewayInstanceId: gateways[0].id }
        }, value => ok(actor, 'GET', ops).then(r => r.value), (value, receipt) => value.id === receipt.id && value.operationId === receipt.operationId && value.planDigest === receipt.planDigest && value.packageId === request.packageId && value.namespace === 'panel');
          state.deploymentRequests[state.deploymentRequests.length - 1] = approved; persist();
        }
        let current, operation;
        for (let n = 0; n < 180; n++) {
          current = (await ok(actor, 'GET', ops)).value;
          operation = (await ok(actor, 'GET', '/panel/operations/namespaces/panel/application-deployment-operations/' + approved.operationId)).value;
          if (['succeeded', 'failed', 'cancelled'].includes(operation.status)) break;
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
        state.deploymentRequests[state.deploymentRequests.findIndex(v => v.id === request.id)] = current;
        (state.operations ||= []).push(operation); persist();
        check('Original approved operation reaches successful terminal owner state', current.status === 'succeeded' && operation.status === 'succeeded', { request: current, operation });
        const rows = (await h.directory('/panel/application/installations/')).filter(v => v.deploymentId === request.deploymentId && v.applicationUuid === pkg.applicationUuid);
        check('Complete installation directory contains exactly one original ready instance', rows.length === 1 && rows[0].status === 'ready', rows);
        const installation = (await ok(actor, 'GET', '/panel/application/installations/' + rows[0].id)).value;
        check('Independent exact installation owner confirms ready original package and instance', installation.status === 'ready' && installation.deploymentId === request.deploymentId && installation.applicationUuid === pkg.applicationUuid && installation.sourceDigest === pkg.artifactDigest, installation);
        state.installations.push(installation); persist();
      }
      check('Two installed fixtures retain different owner and deployment identities', state.installations[0].id !== state.installations[1].id && state.installations[0].deploymentId !== state.installations[1].deploymentId);
      state.stage = 'installed'; persist(); persistFile(path.join(privateRoot, 'fixture-manifest.json'), fixtureManifest(state, config));
      console.log(JSON.stringify({ status: 'installed', installationIds: state.installations.map(v => v.id), acceptance: 'ready only; runtime business verification pending' })); return;
    }
    const { authorFixture } = require('./page_author_cases.cjs');
    const { app } = await authorFixture.fixture(h, 'delivery');
    state.application = app; persist();
    const definition = (await ok(actor, 'GET', '/panel/application/definitions/' + app.id)).value;
    const revisions = '/panel/application/definitions/' + app.id + '/revisions/';
    const preview = (await ok(actor, 'POST', revisions + 'preview', { expectedDefinitionVersion: definition.updateTime })).value;
    check('Owner preview has exact definition and compatible digest', preview.definitionVersion === definition.updateTime && preview.compatible === true && !!preview.digest, preview);
    const revision = await command(revisions, { expectedDefinitionVersion: preview.definitionVersion, expectedPreviewDigest: preview.digest, changeLog: 'Stable regression delivery fixture' },
      value => ok(actor, 'GET', revisions + value.id).then(r => r.value));
    state.revision = revision; persist();
    const pkg = await command(revisions + revision.id + '/model-packages', {}, value => ok(actor, 'GET', '/panel/application/model-packages/' + value.id).then(r => r.value));
    state.package = pkg; state.stage = 'published'; persist();
    const manifest = fixtureManifest(state, config);
    // This is private executable input: redacting authorization declarations
    // would change the frozen contract and invalidate exact owner comparisons.
    persistFile(path.join(privateRoot, 'fixture-manifest.json'), manifest);
    console.log(JSON.stringify({ status: 'published', applicationId: app.id, revisionId: revision.id, packageId: pkg.id, acceptance: 'not yet executed' }));
  } catch (error) {
    state.lastError = { name: error.name, message: error.message, stack: error.stack }; persist();
    throw error;
  } finally { await browser.close(); }
}
if (require.main === module) main().catch(error => { console.error(JSON.stringify({ status: 'blocked', error: error.name, detail: 'Private exact fixture journal retained; no automatic mutation replay' })); process.exitCode = 2; });
module.exports = { validateIsolation, fixtureManifest, dedicatedDeliveryOnly, resumeBootstrapAllowed };
