const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { assessSample, navigationFailed, classifySample, loginInteractionExpected, responseFailed, safePath, trackNetwork, safeException, createEvidenceStore, validateTenants, logoutDocumentComplete, sessionRejected } = require('./live-login-regression.cjs');
assert.equal(safePath('https://t001.local.vpc/api/v1/web/auth/callback?state=private&code=private#private'), '/api/v1/web/auth/callback');
assert.equal(safePath('javascript:secret'), '[non-https]');
assert.equal(safePath('private'), '[invalid-url]');
const tenant = { origin: 'https://t001.local.vpc', namespace: 't001', account: 'test', password: 'test-only' };
assert.equal(validateTenants({ tenants: [tenant] }).length, 1);
for (const patch of [{ origin: 'http://t001.local.vpc' }, { namespace: '*' }, { origin: 'https://t002.local.vpc' }, { origin: 'https://user:secret@t001.local.vpc' }, { origin: 'https://t001.local.vpc/?code=private' }]) {
  assert.throws(() => validateTenants({ tenants: [{ ...tenant, ...patch }] }));
}
assert.throws(() => validateTenants({ tenants: [tenant, tenant] }));
assert.equal(logoutDocumentComplete('/login/', ''), true);
assert.equal(logoutDocumentComplete('/api/v1/cas/oauth/logout', '{"status":"ok"}'), true);
assert.equal(logoutDocumentComplete('/api/v1/cas/oauth/logout', '{"error":"unavailable"}'), false);
assert.equal(logoutDocumentComplete('/api/v1/web/auth/callback', '{"status":"ok"}'), false);
assert.equal(logoutDocumentComplete('/api/v1/cas/oauth/logout', 'invalid'), false);
for (const status of [200, 401]) assert.equal(sessionRejected(status, { error: { code: 11 }, value: null }), true);
for (const status of [200, 401, 503]) assert.equal(sessionRejected(status, { error: { code: 15 }, value: null }), false);
assert.equal(sessionRejected(200, { error: null, value: null }), false);
assert.equal(sessionRejected(200, { error: { code: 11 }, value: {} }), false);
assert.equal(sessionRejected(401, undefined), false);
assert.equal(trackNetwork('https://t001.local.vpc/oauth/login?code=private', 'Fetch', tenant.origin), true);
assert.equal(trackNetwork('https://t001.local.vpc/umi.js', 'Script', tenant.origin), true);
assert.equal(trackNetwork('https://t002.local.vpc/oauth/login', 'Document', tenant.origin), false);
assert.equal(trackNetwork('https://t001.local.vpc/other', 'Fetch', tenant.origin), false);
const exception = safeException({ exception: { className: 'TypeError', description: 'password=private' }, url: tenant.origin + '/umi.js?token=private', lineNumber: 7, text: 'private' });
assert.deepEqual(exception, { kind: 'exception', class: 'TypeError', path: '/umi.js', line: 7 });
assert.equal(safeException({ exception: { className: 'private' } }).class, 'BrowserException');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'login-evidence-'));
try {
  const output = path.join(directory, 'result.json');
  const store = createEvidenceStore(output, { startedAt: 'test' });
  const sample = { namespace: 't001', group: 'sequential', index: 0, passed: false, failure: 'LoginNavigationFailed' };
  store.record(sample);
  const firstEvidence = fs.readFileSync(output + '.attempts.jsonl', 'utf8');
  assert.throws(() => store.record({ ...sample, passed: true }), /DuplicateSampleEvidence/);
  store.snapshot({ samples: [{ ...sample, passed: true }] });
  assert.equal(fs.readFileSync(output + '.attempts.jsonl', 'utf8'), firstEvidence);
  assert.throws(() => createEvidenceStore(output, {}));
  store.finish({ passed: false, samples: [sample] });
  const completed = fs.readFileSync(output, 'utf8');
  assert.throws(() => store.finish({ passed: true }));
  assert.throws(() => createEvidenceStore(output, {}), /EvidenceAlreadyExists/);
  assert.equal(fs.readFileSync(output, 'utf8'), completed);
  for (const file of [output, output + '.attempts.jsonl', output + '.progress.json']) assert.equal(fs.statSync(file).mode & 0o077, 0);
} finally { fs.rmSync(directory, { recursive: true, force: true }); }
console.log('Login harness redaction and scope validation passed.');

const interactionRequest = { method: 'GET', path: '/oauth/login', url: tenant.origin + '/oauth/login?transaction=private&namespace=t001' };
const interactionBody = { interaction: 'login', transaction: 'private', namespace: 't001', csrfToken: 'private' };
assert.equal(loginInteractionExpected(interactionRequest, interactionBody, 't001'), true);
for (const patch of [{ transaction: 'foreign' }, { namespace: 't002' }, { csrfToken: '' }, { interaction: 'unknown' }, { error: 'access_denied' }]) assert.equal(loginInteractionExpected(interactionRequest, { ...interactionBody, ...patch }, 't001'), false);
assert.equal(loginInteractionExpected({ ...interactionRequest, method: 'POST' }, interactionBody, 't001'), false);
assert.equal(loginInteractionExpected({ ...interactionRequest, url: interactionRequest.url + '&namespace=t002' }, interactionBody, 't001'), false);
assert.equal(responseFailed({ kind: 'response', status: 401 }), true);
assert.equal(responseFailed({ kind: 'response', status: 401, interactionPending: true }, true), false);
assert.equal(responseFailed({ kind: 'response', status: 401, interactionPending: true }), true);
assert.equal(responseFailed({ kind: 'response', status: 401, expectedInteraction: true }), false);

const complete = { checks: { login: true, callbackReplay: true, portalSession: true, panelSession: true }, cleanup: { logoutCompleted: true, sessionRejected: true, browserDisposed: true }, events: [] };
assert.deepEqual(classifySample(complete), { authentication: 'passed', pageResources: 'passed', toolEnvironment: 'passed' });
const resourceFailure = { ...complete, events: [{ kind: 'transport', path: '/umi.css', error: 'net::ERR_NETWORK_CHANGED' }] };
assert.deepEqual(classifySample(resourceFailure), { authentication: 'passed', pageResources: 'unconfirmed', toolEnvironment: 'warning' });
assert.deepEqual(classifySample({ ...resourceFailure, checks: {}, failure: 'PageConditionTimeout' }), { authentication: 'unconfirmed', pageResources: 'unconfirmed', toolEnvironment: 'warning' });
assert.equal(classifySample({ ...complete, checks: { ...complete.checks, login: false } }).authentication, 'failed');
assert.equal(classifySample({ ...complete, checks: { ...complete.checks, login: false }, events: [{ kind: 'transport', path: '/api/v1/web/session/', error: 'net::ERR_CONNECTION_RESET' }] }).authentication, 'failed');
assert.equal(classifySample({ ...complete, failure: 'CDPTimeout' }).toolEnvironment, 'failed');
assert.deepEqual(classifySample({ ...complete, events: [{ kind: 'transport', path: '/umi.css', error: 'net::ERR_ABORTED', cancelled: true }] }), classifySample(complete));
const networkChange = { kind: 'transport', path: '/api/v1/web/auth/logout', error: 'net::ERR_NETWORK_CHANGED' };
const recovered = { ...complete, events: [networkChange] };
assert.equal(assessSample(recovered).passed, true);
assert.equal(assessSample(recovered).dimensions.toolEnvironment, 'warning');
assert.equal(assessSample(recovered).networkChanges[0].businessImpact, 'none-observed');
assert.equal(navigationFailed(networkChange), false);
assert.equal(navigationFailed({ ...networkChange, error: 'net::ERR_CONNECTION_RESET' }), true);
assert.equal(assessSample({ ...recovered, cleanup: { browserDisposed: true } }).status, 'blocked');
assert.equal(assessSample({ ...recovered, cleanup: { ...complete.cleanup, sessionRejected: false } }).status, 'failed');
assert.equal(assessSample({ ...recovered, cleanup: { ...complete.cleanup, logoutCompleted: false } }).status, 'failed');
assert.equal(assessSample({ ...recovered, checks: { ...complete.checks, login: false } }).status, 'failed');
assert.equal(assessSample({ ...recovered, failure: 'PageConditionTimeout' }).passed, false);
assert.equal(assessSample({ ...recovered, cleanup: { ...complete.cleanup, failure: 'LogoutUnconfirmed' } }).passed, false);
assert.equal(assessSample(resourceFailure).status, 'blocked');
const loaded = { kind: 'completed', path: '/umi.css', status: 200 };
assert.equal(assessSample({ ...resourceFailure, events: [...resourceFailure.events, loaded] }).passed, true);
for (const events of [[loaded, ...resourceFailure.events], [...resourceFailure.events, { ...loaded, path: '/other.css' }],
  [...resourceFailure.events, { ...loaded, status: 503 }], [...resourceFailure.events, { kind: 'response', path: '/umi.css', status: 200 }]]) {
  assert.equal(assessSample({ ...resourceFailure, events }).passed, false, 'resource recovery must finish after the failure');
}
for (const event of [{ kind: 'exception', path: '/umi.js', class: 'TypeError' },
  { kind: 'response', path: '/api/v1/web/auth/logout', status: 500 },
  { kind: 'response', path: '/oauth/login', status: 401 },
  { kind: 'response', path: '/umi.css', status: 404 },
  { ...networkChange, error: 'net::ERR_NAME_NOT_RESOLVED' }]) {
  assert.equal(assessSample({ ...recovered, events: [networkChange, event] }).status, 'failed');
}
assert.equal(assessSample({ ...recovered, failure: 'CDPTimeout' }).status, 'failed');
assert.equal(assessSample({ ...recovered, cleanup: { ...complete.cleanup, browserDisposed: false } }).passed, false);
assert.equal(assessSample({ ...complete, events: [{ kind: 'response', path: '/oauth/login', status: 401, expectedInteraction: true }] }).passed, true);
console.log('Business outcome and recovered network-change policy passed.');
const { reassess } = require('./reassess-login-regression.cjs');
const frozen = { schema: 'magic.login.regression/v2', sequential: 1, concurrency: [2, 5, 10], incompleteTenants: [], samples: [] };
for (const [group, count] of [['sequential', 1], ['parallel-2', 2], ['parallel-5', 5], ['parallel-10', 10]]) {
  for (let index = 0; index < count; index++) frozen.samples.push({ ...recovered, namespace: 't001', group, index, passed: false, dimensions: { toolEnvironment: 'failed' } });
}
const frozenJSON = JSON.stringify(frozen);
assert.equal(reassess(frozen, ['t001']).passed, true);
assert.equal(JSON.stringify(frozen), frozenJSON, 'reassessment must not mutate first evidence');
assert.equal(reassess({ ...frozen, samples: frozen.samples.slice(1) }, ['t001']).passed, false);
assert.equal(reassess(frozen, ['t001', 'panel']).complete, false);
assert.equal(reassess({ ...frozen, incompleteTenants: ['t001'] }, ['t001']).passed, false);
assert.throws(() => reassess({ ...frozen, samples: [...frozen.samples, frozen.samples[0]] }, ['t001']), /DuplicateOrUnexpectedSample/);
assert.throws(() => reassess(frozen, ['panel']), /DuplicateOrUnexpectedSample/);
const reassessmentDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'login-reassessment-'));
try {
  const source = path.join(reassessmentDirectory, 'source.json'), output = path.join(reassessmentDirectory, 'assessment.json');
  fs.writeFileSync(source, frozenJSON);
  const execute = () => require('node:child_process').spawnSync(process.execPath,
    [path.join(__dirname, 'reassess-login-regression.cjs'), source, output, 't001']);
  assert.equal(execute().status, 0);
  const originalOutput = fs.readFileSync(output, 'utf8');
  assert.equal(execute().status, 1);
  assert.equal(fs.readFileSync(source, 'utf8'), frozenJSON);
  assert.equal(fs.readFileSync(output, 'utf8'), originalOutput);
  assert.equal(JSON.parse(originalOutput).newLiveExecution, false);
  assert.equal(fs.statSync(output).mode & 0o077, 0);
} finally { fs.rmSync(reassessmentDirectory, { recursive: true, force: true }); }
console.log('Frozen-evidence reassessment coverage and immutability passed.');
