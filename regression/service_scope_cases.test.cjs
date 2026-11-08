const { test } = require('node:test');
const assert = require('node:assert/strict');
const { command } = require('./service_scope_cases.cjs');
test('service commands persist original intent and never replay after response loss or failed independent confirmation', async () => {
  for (const mode of ['accepted', 'response-loss', 'owner-read-failed']) {
    const resource = {}, requests = [], h = { Blocked: Error, tenantAdmin: { identity: { account: 'owner', namespace: 'a' } }, persist() {},
      async api(actor, method, route, body) {
        assert.equal(resource.pendingServiceCommands.length, 1);
        assert.equal(resource.pendingServiceCommands[0].confirmed, false);
        assert.deepEqual(resource.pendingServiceCommands[0].body, body);
        requests.push({ method, route, body });
        if (mode === 'response-loss') throw Error('original response lost');
        return { status: 200, data: { value: { id: 7 } } };
      } };
    const execute = () => command(h, resource, 'PUT', '/services/7', { expectedServiceVersion: 12, options: 'original-bytes' }, async response => {
      assert.equal(response.data.value.id, 7);
      if (mode === 'owner-read-failed') throw Error('independent owner read failed');
    });
    if (mode === 'accepted') { await execute(); assert.equal(resource.pendingServiceCommands[0].confirmed, true); }
    else {
      await assert.rejects(execute());
      await assert.rejects(execute(), /unresolved/);
      assert.equal(resource.pendingServiceCommands[0].confirmed, false);
    }
    assert.equal(requests.length, 1);
  }
});
const { copiedProbe } = require('./service_scope_cases.cjs');
test('copied guide parser rejects foreign hosts, substituted resources and shell fragments', () => {
  const example = "curl --request GET 'https://a.example/api/v1/gateway/services/target/probe?marker=%3Cmarker%3E' \\\n  --header 'Authorization: ApiKey <API_KEY>'";
  assert.equal(copiedProbe(example, 'https://a.example', 'target').searchParams.get('marker'), '<marker>');
  for (const invalid of [example.replace('a.example', 'b.example'), example.replace('/target/', '/foreign/'), example + '; env', example.replace('GET', 'DELETE'), example.replace('%3Cmarker%3E', 'fixed')]) assert.throws(() => copiedProbe(invalid, 'https://a.example', 'target'));
});
