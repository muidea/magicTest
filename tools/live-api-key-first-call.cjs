// Attach to an explicitly selected, already authenticated browser tab.
// Keys exist only in browser memory; this script saves bounded diagnostics.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const WebSocket = require(path.resolve(__dirname, '../../magicWebPortal/node_modules/ws'));

const [debugURL, targetId, service, queryPath, outputFile, countArg = '5'] = process.argv.slice(2);
const count = Number(countArg);
if (!debugURL || !targetId || !/^\d+$/.test(service || '') ||
    !/^\/api\/v1\/gateway\/services\/[\w-]+\/[\w-]+(?:\?[^#]*)?$/.test(queryPath || '') ||
    !outputFile || !Number.isInteger(count) || count < 1 || count > 100) {
  console.error('Usage: node live-api-key-first-call.cjs DEBUG_URL TARGET_ID SERVICE_ID GET_PATH OUTPUT_JSON [COUNT=5]');
  process.exit(1);
}
const result = { startedAt: new Date().toISOString(), samples: [], cleanup: [], errors: [] };
const names = [];
let ws, session, seq = 0, stage = 'connect';
const pending = new Map();
function save() { fs.writeFileSync(outputFile, JSON.stringify(result, null, 2) + '\n', { mode: 0o600 }); }
function send(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDPTimeout')); }, 30000);
    pending.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}
async function evaluate(expression) {
  const reply = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, session);
  if (reply.exceptionDetails) {
    // Exception descriptions can contain credentials or payloads. Keep only a
    // recognized class; HTTP business errors are separately bounded below.
    const description = reply.exceptionDetails.exception?.description || '';
    const type = description.match(/^(TypeError|SyntaxError|ReferenceError|AbortError|Error)\b/)?.[1] || 'PageException';
    throw new Error(type);
  }
  return reply.result.value;
}
const pageHelpers = `
 const safeError = e => e ? {code:e.code,message:String(e.message||'').replace(/sk_[A-Za-z0-9_-]+/g,'[redacted]').replace(/[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+/g,'[redacted]').slice(0,300)} : null;
 const read = async r => {try{return {json:await r.json()}}catch(_){return {invalidJSON:true}}};
`;
async function main() {
  try {
    const version = await (await fetch(debugURL + '/json/version', { signal: AbortSignal.timeout(5000) })).json();
    ws = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.once('open', resolve); ws.once('error', () => reject(new Error('CDPConnectError'))); });
    const disconnect = () => {
      for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('CDPDisconnected')); }
      pending.clear();
    };
    ws.on('close', disconnect);
    ws.on('error', disconnect);
    ws.on('message', raw => {
      const m = JSON.parse(raw), p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id); clearTimeout(p.timer);
      m.error ? p.reject(new Error('CDPProtocolError')) : p.resolve(m.result);
    });
    const targets = await send('Target.getTargets');
    const target = targets.targetInfos.find(t => t.targetId === targetId && t.type === 'page');
    if (!target || !/^https:\/\/[\w-]+\.local\.vpc\//.test(target.url)) throw new Error('InvalidTarget');
    result.origin = new URL(target.url).origin;
    ({ sessionId: session } = await send('Target.attachToTarget', { targetId, flatten: true }));
    stage = 'verify session';
    const valid = await evaluate(`(async()=>{const r=await fetch('/api/v1/web/session/',{signal:AbortSignal.timeout(10000)});const j=await r.json();return r.ok&&!j.error&&!!j.value})()`);
    if (!valid) throw new Error('UnauthenticatedTarget');
    for (let i = 0; i < count; i++) {
      const name = 'accept-first-' + crypto.randomBytes(8).toString('hex');
      names.push(name); // Track before issuance: a lost response may still commit.
      stage = 'issue and first call';
      const sample = await evaluate(`(async()=>{${pageHelpers}
        let secret;
        const startedAt=new Date().toISOString();
        try {
          const issued=await fetch('/api/v1/web/proxy/portal/service/credentials/',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(15000),body:JSON.stringify({service:${service},name:${JSON.stringify(name)}})});
          const b=await read(issued),j=b.json;
          if(!issued.ok||!j||j.error||!j.apiKey)return {startedAt,issueStatus:issued.status,issueError:safeError(j?.error),invalidJSON:b.invalidJSON||false,missingKey:!j?.apiKey};
          secret=j.apiKey;
          const start=performance.now();
          try {
            const r=await fetch(${JSON.stringify(queryPath)},{credentials:'omit',headers:{Authorization:'ApiKey '+secret},signal:AbortSignal.timeout(15000)});
            const b=await read(r);
            return {startedAt,issueStatus:issued.status,status:r.status,error:safeError(b.json?.error),invalidJSON:b.invalidJSON||false,requestMilliseconds:Math.round(performance.now()-start)};
          }catch(e){return {startedAt,issueStatus:issued.status,stage:'first call',errorType:e.name}}
        }catch(e){return {startedAt,stage:'issue',errorType:e.name}}
        finally{secret=undefined}
      })()`);
      result.samples.push({ index: i, ...sample }); save();
      if (sample.issueError || sample.missingKey || sample.errorType) break;
    }
  } catch (e) {
    result.errors.push({ stage, errorType: /^[A-Za-z]+$/.test(e.message) ? e.message : e.name });
  } finally {
    // One failed cleanup must not prevent all subsequent cleanup attempts.
    for (const name of names) {
      stage = 'revoke';
      try {
        const cleanup = await evaluate(`(async()=>{${pageHelpers}
          const r=await fetch('/api/v1/web/proxy/portal/service/credentials/${service}?name='+encodeURIComponent(${JSON.stringify(name)}),{method:'DELETE',signal:AbortSignal.timeout(15000)});
          const b=await read(r);
          const list=await fetch('/api/v1/web/proxy/portal/service/credentials/?service=${service}&_pageNum=1&_pageSize=10000',{signal:AbortSignal.timeout(15000)});
          const v=await read(list),rows=v.json?.values;
          return {status:r.status,error:safeError(b.json?.error),confirmed:r.ok&&!!b.json&&!b.json.error&&list.ok&&!v.json?.error&&Array.isArray(rows)&&rows.filter(x=>x.name===${JSON.stringify(name)}).every(x=>x.status===1)};
        })()`);
        result.cleanup.push({ name, ...cleanup });
      } catch (e) { result.cleanup.push({ name, confirmed: false, errorType: e.message }); }
      save();
    }
    result.finishedAt = new Date().toISOString();
    result.complete = result.samples.length === count && result.samples.every(s => s.status === 200 && !s.error && !s.invalidJSON) && !result.errors.length && result.cleanup.length === names.length && result.cleanup.every(c => c.confirmed);
    save();
    if (ws) ws.close();
    console.log(JSON.stringify({ samples: result.samples.length, complete: result.complete, cleanupConfirmed: result.cleanup.filter(c => c.confirmed).length, report: outputFile }));
    if (!result.complete) process.exitCode = 1;
  }
}
main().catch(() => { console.error('Diagnostic runner failed'); process.exitCode = 1; });
