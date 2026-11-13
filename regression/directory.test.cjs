const test = require('node:test');
const assert = require('node:assert/strict');
const { readDirectory } = require('./directory.cjs');
const actor = () => ({ identity: { account: 'original-reader', namespace: 't001' } });
const page = (values, total, pageNum = 1, pageSize = 2) => ({ values, pagination: { total, pageNum, pageSize } });
function harness(pages) {
  const calls = [];
  return { Blocked: Error, calls, async ok(who, method, route) { calls.push({ who, method, route }); return pages.shift(); } };
}
test('complete filtered directory retains original subject and namespace across pages', async () => {
  const who = actor(), h = harness([page([{id:1},{id:2}],3),page([{id:3}],3,2)]);
  assert.deepEqual(await readDirectory(h,who,'/cas/namespaces/t001/accounts/?subjectType=account%7C%3D',{pageSize:2}),[{id:1},{id:2},{id:3}]);
  assert.ok(h.calls.every(c=>c.who===who && c.method==='GET' && new URL(c.route,'https://x.invalid').searchParams.get('subjectType')==='account|='));
  assert.equal(new URL(h.calls[1].route,'https://x.invalid').searchParams.get('_pageNum'),'2');
});
test('explicit zero total permits null without inventing omitted values',async()=>{
  assert.deepEqual(await readDirectory(harness([page(null,0)]),actor(),'/resources/',{pageSize:2}),[]);
  await assert.rejects(readDirectory(harness([page(undefined,0)]),actor(),'/resources/',{pageSize:2}),/malformed/);
});
test('repeated pages, directory churn and short pages cannot prove absence',async()=>{
  for(const pages of [
    [page([{id:1},{id:2}],3),page([{id:1}],3,2)],
    [page([{id:1},{id:2}],3),page([{id:3}],4,2)],
    [page([{id:1}],3)],
    [{values:[{id:1}],pagination:{total:1}}],
    [page([{id:Number.MAX_SAFE_INTEGER+1}],1)],
  ]) await assert.rejects(readDirectory(harness(pages),actor(),'/resources/',{pageSize:2}));
});
test('read budget is checked before further requests and cannot be raised without bound',async()=>{
  const h=harness([page([{id:1},{id:2}],3)]);
  await assert.rejects(readDirectory(h,actor(),'/resources/',{pageSize:2,maxPages:1}),/budget/);
  assert.equal(h.calls.length,1);
  await assert.rejects(readDirectory(harness([]),actor(),'//other.invalid/resources/'));
  await assert.rejects(readDirectory(harness([]),actor(),'/\\other.invalid/resources/'));
});
test('final response cannot switch subject or host before returning a complete directory', async () => {
  for (const mode of ['identity', 'origin']) {
    const who = actor(), h = harness([]);
    h.ok = async () => { if (mode === 'identity') who.identity.namespace = 't002'; else who.origin = 'https://other.invalid'; return page([], 0); };
    await assert.rejects(readDirectory(h, who, '/resources/', { pageSize: 2 }), /actor changed/);
  }
});
test('subject mutation between responses refuses to continue',async()=>{
  const who=actor(),h=harness([]);
  h.ok=async()=>{who.identity.namespace='t002';return page([{id:1},{id:2}],3)};
  await assert.rejects(readDirectory(h,who,'/resources/',{pageSize:2}),/actor changed/);
});

test('explicit string directory identities preserve opaque values across complete pages', async () => {
  const rows = [{ id: '9007199254740993' }, { id: 'a'.repeat(32) }, { id: '9223372036854775807' }];
  const h = harness([page(rows.slice(0, 2), 3), page(rows.slice(2), 3, 2)]);
  assert.deepEqual(await readDirectory(h, actor(), '/portal/applications/', { pageSize: 2, idFormat: 'string' }), rows);
  for (const id of ['', ' ', 'a b', 'x\n', 'x\x00', 'x'.repeat(129), 7, null, undefined])
    await assert.rejects(readDirectory(harness([page([{ id }], 1)]), actor(), '/portal/applications/', { pageSize: 2, idFormat: 'string' }), /identities/);
  await assert.rejects(readDirectory(harness([page([{ id: '7' }], 1)]), actor(), '/resources/', { pageSize: 2 }), /identities/);
  await assert.rejects(readDirectory(harness([page([{ id: '7' }, { id: '7' }], 2)]), actor(), '/portal/applications/', { pageSize: 2, idFormat: 'string' }), /identities/);
  const invalid = harness([]);
  await assert.rejects(readDirectory(invalid, actor(), '/resources/', { idFormat: 'any' }), /format/);
  assert.equal(invalid.calls.length, 0);
});
