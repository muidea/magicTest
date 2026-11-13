const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createPostgres, owned, resourceControls, readControls } = require('./postgres_fixture.cjs');
function fixture() {
  const imageID = 'sha256:' + 'a'.repeat(64), networkID = 'b'.repeat(64), id = 'c'.repeat(64), calls = [];
  let container, removed = false, ready = true;
  const h = { Blocked: Error, state: { resources: [] }, teardowns: [], persist() {}, observe(event) { assert.ok(!JSON.stringify(event).includes(h.state.externalDatabaseFixtures[0].password)); } };
  const run = (args, env) => {
    calls.push({ args, env });
    if (args[0] === 'image') return imageID;
    if (args[0] === 'create') {
      const name = args[args.indexOf('--name') + 1], marker = args[args.indexOf('--label') + 1].split('=')[1];
      assert.ok(!args.join(' ').includes(env.POSTGRES_PASSWORD));
      assert.equal(args.at(-1), imageID);
      assert.ok(args.includes('--tmpfs'));
      container = { Id: id, Image: imageID, Name: '/' + name, Config: { Labels: { 'magic-test.fixture': marker } }, Mounts: [{ Type: 'tmpfs' }], State: { Running: false }, HostConfig: { Memory: 268435456, NanoCpus: 500000000 }, NetworkSettings: { Networks: { isolated: { NetworkID: networkID, IPAddress: '172.20.0.6' } } } };
      return id;
    }
    if (args[0] === 'inspect') {
      if (args.at(-1) === 'magicPanel') return JSON.stringify({ NetworkSettings: { Networks: { isolated: { NetworkID: networkID } } } });
      assert.equal(args.at(-1), id); assert.equal(removed, false); return JSON.stringify(container);
    }
    if (args[0] === 'start') { assert.equal(args[1], id); container.State.Running = true; return id; }
    if (args[0] === 'exec') { if (!ready) throw new Error('not ready'); return 'accepting connections'; }
    if (args[0] === 'stop') { assert.equal(args.at(-1), id); container.State.Running = false; return id; }
    if (args[0] === 'rm') { assert.equal(args[1], id); removed = true; return id; }
    if (args[0] === 'ps') return removed ? '' : id;
    throw new Error('Unexpected operation');
  };
  return { h, run, calls, setReady(value) { ready = value; }, get container() { return container; }, get removed() { return removed; } };
}
test('disposable database pins existing image/network, passes password only through environment, and proves exact removal', async () => {
  const f = fixture(), db = await createPostgres(f.h, f.run);
  assert.equal(db.alternateAddress, '172.20.0.6:5432');
  assert.equal(db.memoryLimitBytes, 268435456);
  await db.cleanup(); await f.h.teardowns[0]();
  assert.ok(f.removed);
  assert.equal(f.calls.filter(c => c.args[0] === 'create').length, 1);
  assert.equal(f.calls.filter(c => c.args[0] === 'rm').length, 1);
  assert.equal(f.h.state.externalDatabaseFixtures[0].removal.outcome, 'confirmed');
});
test('unresolved platform registration or changed identity/volumes prevents physical cleanup', async () => {
  for (const mode of ['open-owner', 'label', 'image', 'id', 'volume', 'missing-mounts', 'unknown-mount']) {
    const f = fixture(), db = await createPostgres(f.h, f.run);
    if (mode === 'open-owner') f.h.state.resources.push({ collection: '/panel/operations/database-instances/', creation: { intended: { address: db.address } }, phase: 'created' });
    if (mode === 'label') f.container.Config.Labels['magic-test.fixture'] = 'other';
    if (mode === 'image') f.container.Image = 'other';
    if (mode === 'id') f.container.Id = 'other';
    if (mode === 'volume') f.container.Mounts.push({ Type: 'volume' });
    if (mode === 'missing-mounts') delete f.container.Mounts;
    if (mode === 'unknown-mount') f.container.Mounts.push({ Type: 'unknown' });
    await assert.rejects(db.cleanup(), /still open|check failed/);
    assert.equal(f.removed, false);
    assert.equal(f.calls.some(c => ['stop', 'rm'].includes(c.args[0])), false);
    assert.equal(owned(f.container, db), mode === 'open-owner');
  }
});
test('readiness failure retains original identity and registered safe teardown without replaying creation', async () => {
  const f = fixture(); f.setReady(false);
  await assert.rejects(createPostgres(f.h, f.run, async () => {}), /readiness/);
  assert.equal(f.h.teardowns.length, 1);
  assert.equal(f.calls.filter(c => c.args[0] === 'create').length, 1);
  await f.h.teardowns[0](); assert.ok(f.removed);
});
test('tmpfs-only database mode requires exact dedicated daemon/root/container and cannot relax host fixture limits',()=>{
  const config={platformRoot:'/tmp/platform-executor-unit/platform',dockerDataRoot:'/tmp/platform-executor-unit/docker-data',daemonId:'original-daemon',containerId:'d'.repeat(64)};
  const info={ID:config.daemonId,DockerRootDir:config.dockerDataRoot,Driver:'overlay2'};
  const h={databaseFixtureMode:'isolated-tmpfs-only',deliveryFixtureConfig:'/private/config.json',Blocked:Error,observe(){},fs:{readFileSync(){return JSON.stringify(config);}}};
  const run=args=>{assert.equal(args[0],'info');return JSON.stringify(info);};
  assert.deepEqual(resourceControls(h,run,'d'.repeat(12)),[]);
  for(const alter of [()=>{info.ID='other';},()=>{info.DockerRootDir='/var/lib/docker';},()=>{config.containerId='e'.repeat(64);},()=>{h.deliveryFixtureConfig=undefined;}]){
    const originalInfo=structuredClone(info),originalConfig=structuredClone(config),originalPath=h.deliveryFixtureConfig;
    alter();assert.throws(()=>resourceControls(h,run,'d'.repeat(12)),/nested daemon|Dedicated/);
    Object.assign(info,originalInfo);Object.assign(config,originalConfig);h.deliveryFixtureConfig=originalPath;
  }
  assert.deepEqual(resourceControls({...h,databaseFixtureMode:undefined},()=>{throw Error('not needed');}),['--memory','256m','--cpus','0.5']);
});
test('database planning verification reads actual controls only from exact original physical ownership',async()=>{
  const f=fixture(),db=await createPostgres(f.h,f.run);
  assert.deepEqual(readControls(f.h,db,f.run),{memoryLimitBytes:268435456,cpuNanoLimit:500000000});
  f.container.Config.Labels['magic-test.fixture']='other';assert.throws(()=>readControls(f.h,db,f.run),/ownership changed/);
});
