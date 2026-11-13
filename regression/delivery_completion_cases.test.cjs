const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { archive } = require('./delivery_completion_cases.cjs');
test('portable comparison strips only formal export identities and still detects business, permission and execution contract changes', () => {
  const { portableEntities } = require('./delivery_completion_cases.cjs');
  const source = [{ id: 7, createTime: 31, updateTime: 41, icon: 'author-icon', application: { id: 9 }, uiMeta: { fields: [] },
    name: 'sample', pkgPath: '/original', fields: [{ name: 'code', type: { name: 'string' } }],
    writeRules: { versionField: 'version' }, blockInfo: [{ key: 'original' }], serviceExpose: { enabled: true } }];
  const original = structuredClone(source), expected = [{ ...source[0], id: 0, createTime: 0, updateTime: 0, icon: '', application: null }];
  delete expected[0].uiMeta;
  assert.deepEqual(portableEntities(source), expected); assert.deepEqual(source, original);
  for (const mutate of [s => s[0].fields[0].type.name = 'integer', s => s[0].writeRules.versionField = 'other',
    s => s[0].blockInfo = [], s => s[0].serviceExpose.enabled = false, s => s[0].unexpected = true]) {
    const changed = structuredClone(source); mutate(changed);
    assert.notDeepEqual(portableEntities(changed), expected);
  }
});
function zip(mode) {
  return execFileSync('python3', ['-B', '-c', `import io,zipfile,json,hashlib,sys
mode=sys.argv[1]
files={'package.json':json.dumps({'apiVersion':'magic.model-package/v1','content':{'application':'application.json','pages':'pages.json','entities':[{'path':'entity.json'}]}}).encode(), 'application.json':b'{"authorization":{"apiVersion":"magic.application-authorization/v1"}}','pages.json':b'{"pages":[]}','entity.json':b'{"name":"original"}','application/blocks/main.go':b'package block\\n'}
if mode=='traversal': files['../outside']=b'bad'
checks={'apiVersion':'magic.checksums/v1','files':[{'path':p,'size':len(v),'digest':'sha256:'+hashlib.sha256(v).hexdigest()} for p,v in files.items()]}
if mode=='bad-contract': checks['apiVersion']='invented'
if mode=='missing-entry': checks['files'].pop()
if mode=='duplicate-entry': checks['files'].append(checks['files'][0])
if mode=='tampered': files['entity.json']=b'{"name":"modified"}'
if mode!='no-checksums': files['checksums.json']=json.dumps(checks).encode()
out=io.BytesIO()
with zipfile.ZipFile(out,'w') as z:
 for p,v in files.items(): z.writestr(p,v)
 if mode=='duplicate-path': z.writestr('entity.json',b'{}')
sys.stdout.buffer.write(out.getvalue())`, mode], { stdio: ['ignore', 'pipe', 'pipe'] });
}
test('independent model ZIP inspection verifies every original byte and rejects tampering, missing coverage, duplicate paths and traversal', () => {
  const read = archive(zip('valid'));
  assert.deepEqual(read.entities, [{ name: 'original' }]);
  assert.equal(read.metadata.authorization.apiVersion, 'magic.application-authorization/v1');
  assert.deepEqual(read.programFiles, { 'main.go': Buffer.from('package block\n').toString('base64') });
  for (const mode of ['tampered', 'no-checksums', 'missing-entry', 'duplicate-entry', 'duplicate-path', 'traversal', 'bad-contract'])
    assert.throws(() => archive(zip(mode)), undefined, mode);
});
