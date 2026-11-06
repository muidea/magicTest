// Public author validation/debug and durable library reads.
const crypto = require('node:crypto');
const handlers = {};
const root = '/panel/application/definition/entity/scripts/';
const source = `package block
import ("context";"fmt")
func Handle(ctx context.Context,input map[string]any,output map[string]any) error {
fmt.Println("regression script output")
output["count"] = input["count"]
output["enabled"] = input["enabled"]
return nil
}`;
const parameters = [{ name: 'count', type: 'number', required: true }, { name: 'enabled', type: 'boolean', required: true }];
const sample = () => ({ scriptContent: source, functionName: 'block.Handle', inputs: parameters,
  outputs: parameters, input: { count: 0, enabled: false }, timeout: 1000, mode: 'example' });
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

handlers['F017-001'] = async h => {
  const request = sample(), checked = (await h.ok(h.admin, 'POST', root + 'validate', request)).value;
  h.check('Legal script formats to distinct compilable source without diagnostics', checked.valid && typeof checked.formattedSource === 'string' && checked.formattedSource !== source && !checked.diagnostics?.length);
  const formatted = checked.formattedSource;
  const again = (await h.ok(h.admin, 'POST', root + 'validate', { ...request, scriptContent: formatted })).value;
  h.check('Formatting is stable and legal', again.valid && again.formattedSource === formatted);
  const debug = (await h.ok(h.admin, 'POST', root + 'debug', { ...request, scriptContent: formatted })).value;
  h.check('Real debug preserves required zero and false, output and logs', debug.valid && same(debug.output, { count: 0, enabled: false }) && debug.log.includes('regression script output') && debug.mode === 'example' && debug.durationMs >= 0 && !debug.diagnostics?.length, debug);
  const body = JSON.parse(h.fs.readFileSync(h.path.resolve(h.root, '../docs/scripts/fixtures/platform-regression/fixture-definition-create-request.json')));
  Object.assign(body, { uuid: crypto.randomBytes(16).toString('hex'), name: h.state.prefix + '-script', showName: '脚本调试保存回读', pkgPrefix: h.state.prefix + 'script' });
  const app = await h.create('/panel/application/definitions/', body, 'definition');
  const route = '/panel/application/definitions/' + app.id + '/function-blocks';
  const original = (await h.ok(h.admin, 'GET', route)).value;
  const definition = { key: 'sample', name: '示例调试', language: 'go', sourceFiles: ['sample/main.go'],
    entrypoint: { file: 'sample/main.go', function: 'block.Handle' }, inputs: parameters, outputs: parameters };
  const content = { schemaVersion: 'magic.application-function-blocks/v1', definitions: [{ key: 'sample', definition: 'sample/definition.json' }], files: {
    'sample/definition.json': Buffer.from(JSON.stringify(definition)).toString('base64'),
    'sample/main.go': Buffer.from(formatted).toString('base64') } };
  await h.ok(h.admin, 'PUT', route, { expectedDefinitionVersion: original.definitionVersion, content });
  const saved = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Independent library owner read proves exact formatted source and parameters saved', saved.applicationId === app.id && saved.applicationUuid === app.uuid && saved.definitionVersion > original.definitionVersion && same(saved.content, content), saved);
  const broken = await h.api(h.admin, 'POST', root + 'validate', { ...request, scriptContent: formatted.replace('return nil', 'return @') });
  h.check('Syntax failure retains located diagnostic', !h.good(broken) && !broken.data.value?.valid && broken.data.value?.diagnostics?.some(d => d.line > 0 && d.column > 0 && d.message), broken);
  const wrongOutput = await h.api(h.admin, 'POST', root + 'debug', { ...request, outputs: [{ name: 'count', type: 'string', required: true }] });
  h.check('Output mismatch reports diagnostics while preserving execution log', !h.good(wrongOutput) && !wrongOutput.data.value?.valid && wrongOutput.data.value?.diagnostics?.some(d => /count/.test(d.message)) && wrongOutput.data.value.log.includes('regression script output'), wrongOutput);
  const after = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Validation and debug cannot mutate saved author source', same(after, saved));
};

handlers['F017-002'] = async h => {
  const request = sample();
  const bad = [
    ['syntax', { scriptContent: source.replace('return nil', 'return @') }, /./],
    ['entrypoint', { functionName: 'block.Missing' }, /./],
    ['input-type', { input: { count: 'wrong', enabled: false } }, /count/],
    ['required-input', { input: { count: 0 } }, /enabled/],
    ['output-type', { outputs: [{ name: 'count', type: 'string', required: true }] }, /count/],
  ];
  for (const [label, changes, diagnostic] of bad) {
    const result = await h.api(h.admin, 'POST', root + 'debug', { ...request, ...changes });
    h.check('Debug rejects ' + label + ' with explicit diagnostics', !h.good(result) && !result.data.value?.valid && result.data.value?.diagnostics?.some(d => diagnostic.test(d.message)), result);
    if (label === 'syntax') h.check('Syntax diagnostic retains source position', result.data.value.diagnostics.some(d => d.line > 0 && d.column > 0), result);
  }
  for (const timeout of [-1, 3001]) {
    const result = await h.api(h.admin, 'POST', root + 'debug', { ...request, timeout });
    h.check('Author debug rejects out-of-range budget ' + timeout, !h.good(result) && /1.*3000/.test(result.data.error?.message || ''), result);
  }
  for (const timeout of [0, 3000]) {
    const result = (await h.ok(h.admin, 'POST', root + 'debug', { ...request, timeout })).value;
    h.check('Default and maximum debug budgets preserve zero/false: ' + timeout, result.valid && same(result.output, { count: 0, enabled: false }), result);
  }
  const minimum = await h.api(h.admin, 'POST', root + 'debug', { ...request, timeout: 1 });
  h.check('Minimum 1ms is admitted; actual compilation/execution may hit the deadline', !/调试超时必须/.test(minimum.data.error?.message || '') && (h.good(minimum) || minimum.data.value?.diagnostics?.some(d => /context|deadline|超时|cancel/i.test(d.message))), minimum);
  const loop = `package block
import ("context";"fmt")
func Handle(ctx context.Context,input map[string]any,output map[string]any) error {
fmt.Println("regression bounded loop started")
for {}
}`;
  const loopRequest = { ...request, scriptContent: loop, timeout: 500 };
  const started = Date.now();
  const [timed, control] = await Promise.all([
    h.api(h.admin, 'POST', root + 'debug', loopRequest),
    h.api(h.admin, 'GET', '/api/v1/web/session/'),
  ]);
  h.check('Unrelated request continues during bounded author execution', h.good(control), control);
  h.check('Long loop reaches execution, times out and retains log/diagnostic', !h.good(timed) && !timed.data.value?.valid && timed.data.value?.log?.includes('regression bounded loop started') && timed.data.value?.diagnostics?.some(d => /context|deadline|超时|cancel/i.test(d.message)) && Date.now() - started < 10000, timed);
  const cancelled = await h.admin.page.evaluate(async body => {
    const abort = new AbortController(), started = Date.now();
    const pending = fetch('/api/v1/web/proxy/panel/application/definition/entity/scripts/debug', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: abort.signal,
    }).then(async r => ({ status: r.status, body: await r.text() }), error => ({ name: error.name }));
    await new Promise(resolve => setTimeout(resolve, 250));
    abort.abort();
    return { result: await pending, elapsedMs: Date.now() - started };
  }, { ...loopRequest, timeout: 3000 });
  h.check('Browser cancels the original debug request within a bounded interval; this is transport evidence', cancelled.result.name === 'AbortError' && cancelled.elapsedMs < 10000, cancelled);
  await h.ok(h.admin, 'GET', '/api/v1/web/session/');
  for (const [label, scriptContent] of [
    ['goroutine', source.replace('return nil', 'go func() {}()\nreturn nil')],
    ['init', source + '\nfunc init() {}'],
    ['global', source + '\nvar unauthorized = 1'],
  ]) {
    const result = await h.api(h.admin, 'POST', root + 'validate', { ...request, scriptContent });
    h.check('Untrusted ' + label + ' declaration is rejected by the formal validator', !h.good(result) && !result.data.value?.valid && result.data.value?.diagnostics?.length > 0, result);
  }
  await h.partial('AUTHOR-DEBUG-CANCEL: browser AbortError proves transport cancellation only. Executing-script cancellation is covered by owner source tests; this Live case stays partial until the same request has independent server-stop evidence.');
};

module.exports = { handlers };
