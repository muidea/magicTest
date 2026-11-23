// Browser regression only; does not create accounts or modify applications.
// Credentials come from a private file. CDP URLs, codes and cookies stay in memory.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

function safePath(raw) {
  try { const url = new URL(raw); return url.protocol === 'https:' ? url.pathname : '[non-https]'; }
  catch { return '[invalid-url]'; }
}
function trackNetwork(raw, type, origin) {
  try {
    const url = new URL(raw);
    if (url.origin !== new URL(origin).origin) return false;
    return ['Document', 'Script', 'Stylesheet'].includes(type)
      || /^\/(?:oauth\/|api\/v1\/(?:cas\/oauth\/|web\/(?:auth\/|session\/)))/.test(url.pathname);
  } catch { return false; }
}
function loginInteractionExpected(request, body, namespace) {
  if (request?.method !== 'GET' || request?.path !== '/oauth/login') return false;
  const query = new URL(request.url).searchParams;
  return query.getAll('transaction').length === 1 && !!query.get('transaction')
    && query.getAll('namespace').length === 1 && query.get('namespace') === namespace
    && ['login', 'password_change'].includes(body?.interaction)
    && body.transaction === query.get('transaction') && body.namespace === namespace
    && typeof body.csrfToken === 'string' && !!body.csrfToken && !body.error;
}
function responseFailed(event, pendingAllowed = false) {
  return event.kind === 'response' && event.status >= 400
    && event.expectedInteraction !== true && !(pendingAllowed && event.interactionPending);
}
function safeException(details) {
  const allowed = new Set(['Error', 'TypeError', 'ReferenceError', 'SyntaxError', 'RangeError', 'DOMException']);
  return { kind: 'exception', class: allowed.has(details?.exception?.className) ? details.exception.className : 'BrowserException',
    path: details?.url ? safePath(details.url) : '[unknown-script]', line: Number.isInteger(details?.lineNumber) ? details.lineNumber : null };
}
// The journal is authoritative and append-only. The progress file is a
// replaceable projection; completed evidence is created exclusively once.
function createEvidenceStore(outputFile, metadata) {
  if (fs.existsSync(outputFile)) throw new Error('EvidenceAlreadyExists');
  const journal = outputFile + '.attempts.jsonl', progress = outputFile + '.progress.json';
  fs.writeFileSync(journal, JSON.stringify({ kind: 'started', ...metadata }) + '\n', { flag: 'wx', mode: 0o600 });
  fs.writeFileSync(progress, JSON.stringify(metadata) + '\n', { flag: 'wx', mode: 0o600 });
  const seen = new Set();
  return {
    record(sample) {
      const key = JSON.stringify([sample.namespace, sample.group, sample.index]);
      if (seen.has(key)) throw new Error('DuplicateSampleEvidence');
      fs.appendFileSync(journal, JSON.stringify({ kind: 'sample', ...sample }) + '\n');
      seen.add(key);
    },
    snapshot(result) { fs.writeFileSync(progress, JSON.stringify(result, null, 2) + '\n'); },
    finish(result) {
      fs.writeFileSync(outputFile, JSON.stringify(result, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
      fs.appendFileSync(journal, JSON.stringify({ kind: 'finished', passed: result.passed, finishedAt: result.finishedAt }) + '\n');
    },
  };
}
function logoutDocumentComplete(pathname, text) {
  if (pathname.startsWith('/login')) return true;
  if (pathname !== '/api/v1/cas/oauth/logout') return false;
  try { return JSON.parse(text).status === 'ok'; } catch { return false; }
}
function sessionRejected(status, body) {
  // This endpoint uses the platform JSON error contract: Unauthorized=11.
  return [200, 401].includes(status) && body?.error?.code === 11 && body.value == null;
}
function validateTenants(value) {
  assert.ok(Array.isArray(value?.tenants) && value.tenants.length > 0 && value.tenants.length <= 10, 'InvalidTenants');
  const seen = new Set();
  for (const tenant of value.tenants) {
    assert.match(tenant.namespace || '', /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/, 'InvalidNamespace');
    const origin = new URL(tenant.origin);
    assert.equal(origin.protocol, 'https:', 'HTTPSRequired');
    assert.equal(origin.username + origin.password + origin.search + origin.hash, '', 'InvalidOrigin');
    assert.equal(origin.pathname, '/', 'InvalidOriginPath');
    assert.equal(origin.hostname.split('.')[0], tenant.namespace, 'NamespaceHostMismatch');
    assert.ok(tenant.account && tenant.password && !seen.has(tenant.origin), 'InvalidCredentialBinding');
    seen.add(tenant.origin);
  }
  return value.tenants;
}
const acceptancePolicy = 'magic.login.business-outcome/v1';
function transportFailed(event) {
  return event.kind === 'transport' && !(event.cancelled && event.error === 'net::ERR_ABORTED');
}
function navigationFailed(event) {
  // Let the existing navigation settle within its deadline after a network
  // change. Do not resubmit credentials or retry an authorization exchange.
  return responseFailed(event, true) || transportFailed(event) && event.error !== 'net::ERR_NETWORK_CHANGED';
}
// Keep transport evidence separate from the verified business outcome.
// Authentication recovery needs all endpoint assertions and logout readback;
// resource recovery needs a later completed successful load of that path.
function classifySample(sample) {
  const events = sample.events || [], checks = sample.checks || {}, cleanup = sample.cleanup || {};
  const authPath = p => /^\/(?:oauth\/|api\/v1\/(?:cas\/oauth\/|web\/(?:auth\/|session\/)))/.test(p || '');
  const transports = events.filter(transportFailed);
  const authValues = ['login', 'callbackReplay', 'portalSession', 'panelSession'].map(key => checks[key]);
  const authComplete = authValues.every(value => value === true) && cleanup.logoutCompleted === true && cleanup.sessionRejected === true;
  const authRejected = events.some(e => authPath(e.path) && responseFailed(e)) || authValues.some(value => value === false)
    || cleanup.logoutCompleted === false || cleanup.sessionRejected === false;
  const authentication = authRejected ? 'failed' : authComplete ? 'passed' : 'unconfirmed';
  const resourceFailed = events.some(e => e.kind === 'exception' || !authPath(e.path) && responseFailed(e));
  const resourceUnconfirmed = transports.some(e => !authPath(e.path) &&
    !(e.error === 'net::ERR_NETWORK_CHANGED' && events.slice(events.indexOf(e) + 1).some(later =>
      later.kind === 'completed' && later.path === e.path && later.status >= 200 && later.status < 300)));
  const pageResources = resourceFailed ? 'failed' : resourceUnconfirmed ? 'unconfirmed' : authValues.every(value => value === true) ? 'passed' : 'unconfirmed';
  const toolFailed = transports.some(e => e.error !== 'net::ERR_NETWORK_CHANGED') || /^CDP/.test(sample.failure || '') || cleanup.browserDisposed === false;
  const toolEnvironment = toolFailed ? 'failed' : transports.length ? 'warning' : cleanup.browserDisposed === true && !sample.failure ? 'passed' : 'unconfirmed';
  return { authentication, pageResources, toolEnvironment };
}
function assessSample(sample) {
  const dimensions = classifySample(sample);
  const passed = dimensions.authentication === 'passed' && dimensions.pageResources === 'passed'
    && ['passed', 'warning'].includes(dimensions.toolEnvironment)
    && !sample.failure && !sample.cleanup?.failure && sample.cleanup?.browserDisposed === true;
  const failed = Object.values(dimensions).includes('failed');
  return { policy: acceptancePolicy, dimensions, passed, status: passed ? 'passed' : failed ? 'failed' : 'blocked',
    networkChanges: (sample.events || []).filter(e => transportFailed(e) && e.error === 'net::ERR_NETWORK_CHANGED')
      .map(e => ({ path: e.path, at: e.at, businessImpact: passed ? 'none-observed' : 'not-excluded' })) };
}

async function main() {
  const [debugURL, credentialsFile, outputFile, sequentialArg = '20', fingerprintFile] = process.argv.slice(2);
  const sequential = Number(sequentialArg);
  assert.ok(debugURL && credentialsFile && outputFile && fingerprintFile && Number.isInteger(sequential) && sequential >= 1 && sequential <= 40, 'InvalidArguments');
  const endpoint = new URL(debugURL);
  assert.ok(endpoint.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname), 'LocalCDPRequired');
  assert.equal(fs.statSync(credentialsFile).mode & 0o077, 0, 'PrivateCredentialFileRequired');
  const tenants = validateTenants(JSON.parse(fs.readFileSync(credentialsFile)));
  const digest = file => 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  const result = { schema: 'magic.login.regression/v3', acceptancePolicy, namespaces: tenants.map(t => t.namespace), startedAt: new Date().toISOString(), toolDigest: digest(__filename),
    candidateFingerprint: digest(fingerprintFile), sequential, concurrency: [2, 5, 10], incompleteTenants: [], samples: [] };
  const evidence = createEvidenceStore(outputFile, { schema: result.schema, acceptancePolicy, startedAt: result.startedAt, toolDigest: result.toolDigest, candidateFingerprint: result.candidateFingerprint });
  const WebSocket = require(path.resolve(__dirname, '../../magicWebPortal/node_modules/ws'));
  let ws;
  try {
    const version = await (await fetch(debugURL + '/json/version', { signal: AbortSignal.timeout(5000) })).json();
    ws = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.once('open', resolve); ws.once('error', () => reject(new Error('CDPConnectError'))); });
  } catch {
    result.finishedAt = new Date().toISOString(); result.passed = false; result.failure = 'CDPConnectError';
    evidence.finish(result); ws?.close(); throw new Error('CDPConnectError');
  }
  let seq = 0;
  const pending = new Map(), traces = new Map();
  function send(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDPTimeout')); }, 30000);
      pending.set(id, { resolve, reject, timer });
      ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  ws.on('close', () => { for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('CDPDisconnected')); } pending.clear(); });
  ws.on('error', () => {});
  ws.on('message', raw => {
    const message = JSON.parse(raw), p = pending.get(message.id);
    if (p) { pending.delete(message.id); clearTimeout(p.timer); message.error ? p.reject(new Error('CDPProtocolError')) : p.resolve(message.result); return; }
    const trace = traces.get(message.sessionId);
    if (!trace) return;
    const params = message.params || {};
    if (message.method === 'Runtime.exceptionThrown') trace.events.push({ ...safeException(params.exceptionDetails), at: new Date().toISOString() });
    if (message.method === 'Network.requestWillBeSent' && trackNetwork(params.request.url, params.type, trace.origin)) {
      const pathname = safePath(params.request.url);
      if (params.redirectResponse) trace.events.push({ kind: 'response', path: safePath(params.redirectResponse.url), status: params.redirectResponse.status, at: new Date().toISOString() });
      // The complete callback URI is used solely for an immediate replay in
      // this same private browser context, and is never serialized.
      if (params.type === 'Document' && pathname === '/api/v1/web/auth/callback') trace.callback = params.request.url;
      trace.requests.set(params.requestId, { path: pathname, timestamp: params.timestamp, method: params.request.method, url: params.request.url });
      trace.events.push({ kind: params.type === 'Document' ? 'navigation' : 'request', type: params.type, path: pathname, at: new Date().toISOString() });
    }
    if (message.method === 'Network.responseReceived' && trace.requests.has(params.requestId)) {
      const request = trace.requests.get(params.requestId);
      request.responseStatus = params.response.status;
      const event = { kind: 'response', path: request.path, status: params.response.status,
        elapsedMs: Number.isFinite(params.timestamp - request.timestamp) ? Math.max(0, Math.round((params.timestamp - request.timestamp) * 1000)) : null, at: new Date().toISOString() };
      if (params.response.status === 401 && request.method === 'GET' && request.path === '/oauth/login') { event.interactionPending = true; request.interactionEvent = event; }
      trace.events.push(event);
    }
    if (message.method === 'Network.loadingFinished') {
      const request = trace.requests.get(params.requestId);
      if (request) trace.events.push({ kind: 'completed', path: request.path, status: request.responseStatus, at: new Date().toISOString() });
      if (request?.interactionEvent) {
        send('Network.getResponseBody', { requestId: params.requestId }, message.sessionId).then(result => {
          let body; try { body = JSON.parse(result.base64Encoded ? Buffer.from(result.body, 'base64').toString() : result.body); } catch {}
          request.interactionEvent.expectedInteraction = loginInteractionExpected(request, body, trace.namespace);
        }).catch(() => { request.interactionEvent.expectedInteraction = false; }).finally(() => { delete request.interactionEvent.interactionPending; });
      }
    }
    if (message.method === 'Network.loadingFailed' && trace.requests.has(params.requestId)) {
      trace.events.push({ kind: 'transport', path: trace.requests.get(params.requestId).path, cancelled: !!params.canceled,
        error: /^net::ERR_[A-Z_]+$/.test(params.errorText || '') ? params.errorText : 'BrowserTransportFailure', at: new Date().toISOString() });
    }
  });
  async function evaluate(sessionId, expression) {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId);
    if (result.exceptionDetails) {
      traces.get(sessionId)?.events.push({ ...safeException(result.exceptionDetails), at: new Date().toISOString() });
      throw new Error('PageEvaluationFailure');
    }
    return result.result.value;
  }
  async function wait(sessionId, expression, failFast = false) {
    const until = Date.now() + 45000;
    while (Date.now() < until) {
      if (failFast && traces.get(sessionId)?.events.some(navigationFailed)) {
        throw new Error('LoginNavigationFailed');
      }
      try { if (await evaluate(sessionId, expression)) return; } catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('PageConditionTimeout');
  }
  function save() { evidence.snapshot(result); }
  async function run(tenant, group, index) {
    const sample = { namespace: tenant.namespace, group, index, startedAt: new Date().toISOString(), checks: {}, events: [], cleanup: {} };
    let browserContextId, sessionId;
    const trace = { origin: tenant.origin, namespace: tenant.namespace, callback: '', requests: new Map(), events: sample.events };
    try {
      ({ browserContextId } = await send('Target.createBrowserContext'));
      const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
      ({ sessionId } = await send('Target.attachToTarget', { targetId, flatten: true }));
      traces.set(sessionId, trace);
      await send('Page.enable', {}, sessionId); await send('Runtime.enable', {}, sessionId); await send('Network.enable', {}, sessionId);
      await send('Page.navigate', { url: tenant.origin + '/login/?from=/panel/' }, sessionId);
      await wait(sessionId, `!!document.querySelector('input[name=account]')&&!!document.querySelector('input[name=password]')`, true);
      await evaluate(sessionId, `(()=>{const account=document.querySelector('input[name=account]');const password=document.querySelector('input[name=password]');account.value=${JSON.stringify(tenant.account)};password.value=${JSON.stringify(tenant.password)};account.form.requestSubmit();return true})()`);
      await wait(sessionId, `location.pathname.startsWith('/panel')`, true);
      const read = `(async()=>{const r=await fetch('/api/v1/web/session/',{signal:AbortSignal.timeout(10000)});let j;try{j=await r.json()}catch{return false};return r.ok&&!j.error&&j.value?.homeNamespace===${JSON.stringify(tenant.namespace)}&&j.value?.activeNamespace===${JSON.stringify(tenant.namespace)}})()`;
      sample.checks.login = await evaluate(sessionId, read);
      if (!trace.callback) throw new Error('CallbackNavigationNotObserved');
      const replayStart = sample.events.length;
      await send('Page.navigate', { url: trace.callback }, sessionId);
      const replayDeadline = Date.now() + 45000;
      while (!sample.events.slice(replayStart).some(e => e.kind === 'response' && e.path === '/api/v1/web/auth/callback')) {
        if (Date.now() >= replayDeadline) throw new Error('CallbackReplayResponseMissing');
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      await wait(sessionId, `location.pathname.startsWith('/panel')`);
      sample.checks.callbackReplay = await evaluate(sessionId, read);
      for (const area of ['portal', 'panel']) {
        await send('Page.navigate', { url: tenant.origin + '/' + area + '/' }, sessionId);
        await wait(sessionId, `document.readyState==='complete'&&location.pathname.startsWith('/${area}')`);
        sample.checks[area + 'Session'] = await evaluate(sessionId, read);
      }
    } catch (error) { sample.failure = /^[A-Za-z]+$/.test(error.message) ? error.message : 'BrowserRegressionFailure'; }
    finally {
      if (sessionId) {
        try {
          await send('Page.navigate', { url: tenant.origin + '/api/v1/web/auth/logout' }, sessionId);
          await wait(sessionId, `document.readyState==='complete'&&(location.pathname.startsWith('/login')||location.pathname==='/api/v1/cas/oauth/logout')`);
          const document = await evaluate(sessionId, `({path:location.pathname,text:document.body?.innerText||''})`);
          sample.cleanup.logoutCompleted = logoutDocumentComplete(document.path, document.text);
          sample.cleanup.logoutPath = document.path;
          const rejected = await evaluate(sessionId, `(async()=>{const r=await fetch('/api/v1/web/session/',{signal:AbortSignal.timeout(10000)});let body;try{body=await r.json()}catch{return {status:r.status}};return {status:r.status,body:{error:body.error?{code:body.error.code}:null,value:body.value==null?null:true}}})()`);
          sample.cleanup.sessionRejected = sessionRejected(rejected.status, rejected.body);
        } catch { sample.cleanup.failure = 'LogoutUnconfirmed'; }
        trace.callback = ''; traces.delete(sessionId);
      }
      try { if (browserContextId) await send('Target.disposeBrowserContext', { browserContextId }); sample.cleanup.browserDisposed = !!browserContextId; }
      catch { sample.cleanup.browserDisposed = false; }
      Object.assign(sample, assessSample(sample));
      sample.finishedAt = new Date().toISOString(); evidence.record(sample); result.samples.push(sample); save();
    }
    return sample.passed;
  }
  try {
    for (const tenant of tenants) {
      let stable = true;
      for (let i = 0; i < sequential; i++) {
        if (!await run(tenant, 'sequential', i)) { stable = false; break; }
      }
      if (!stable) { result.incompleteTenants.push(tenant.namespace); save(); continue; }
      for (const concurrency of result.concurrency) await Promise.all(Array.from({ length: concurrency }, (_, i) => run(tenant, 'parallel-' + concurrency, i)));
    }
  } finally { result.finishedAt = new Date().toISOString(); result.passed = result.samples.length === tenants.length * (sequential + 17) && result.samples.every(s => s.passed); save(); evidence.finish(result); ws.close(); }
  if (!result.passed) process.exitCode = 1;
}
if (require.main === module) main().catch(() => { console.error('Login regression could not complete; inspect sanitized output and local CDP availability.'); process.exitCode = 1; });
module.exports = { acceptancePolicy, assessSample, classifySample, navigationFailed, loginInteractionExpected, responseFailed, safePath, trackNetwork, safeException, createEvidenceStore, validateTenants, logoutDocumentComplete, sessionRejected };
