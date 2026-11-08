// Disposable empty PostgreSQL only: no production credentials, SQL or volumes.
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
function docker(args, env) {
  try { return execFileSync('docker', args, { encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, ...env } }).trim(); }
  catch (error) { throw new Error('Database fixture docker ' + args[0] + ' failed (exit ' + error.status + '); private output omitted'); }
}
function inspect(run, id) {
  return JSON.parse(run(['inspect', '--format', '{{json .}}', id]));
}
function owned(value, journal) {
  return value.Id === journal.id && value.Name === '/' + journal.name && value.Image === journal.imageID && value.Config?.Labels?.['magic-test.fixture'] === journal.marker && Array.isArray(value.Mounts) && !value.Mounts.some(m => m.Type !== 'tmpfs');
}
function postgresCleanup(h, journal, run = docker) {
  if (!/^[a-f0-9]{64}$/.test(journal.id || '') || !/^magic-test-pg-[a-f0-9]{16}$/.test(journal.name || '') || !/^[a-f0-9]{32}$/.test(journal.marker || '')) throw new h.Blocked('Original database fixture journal identity is incomplete');
  return async () => {
    if (journal.phase === 'deleted') return;
    if (h.state.resources.some(r => r.collection === '/panel/operations/database-instances/' && r.creation?.intended?.address === journal.name + ':5432' && r.phase !== 'deleted')) throw new h.Blocked('Original database registration is still open; retain its exact disposable physical target');
    const value = inspect(run, journal.id);
    if (!owned(value, journal)) throw new h.Blocked('Database cleanup identity, labels, image or volume check failed');
    if (value.State.Running) run(['stop', '--time', '10', journal.id]);
    if (!owned(inspect(run, journal.id), journal)) throw new h.Blocked('Database container identity changed before removal');
    journal.removal = { outcome: 'unknown' }; h.persist();
    run(['rm', journal.id]);
    const remaining = run(['ps', '-aq', '--no-trunc', '--filter', 'id=' + journal.id]);
    if (remaining) throw new h.Blocked('Original database container removal is not independently confirmed');
    journal.phase = 'deleted'; journal.removal.outcome = 'confirmed'; h.persist();
    h.observe({ kind: 'disposable-postgres-disposition', id: journal.id, name: journal.name, imageID: journal.imageID, networkID: journal.networkID, removed: true, persistentVolumesUsed: false });
  };
}
async function createPostgres(h, run = docker, pause = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const panel = inspect(run, 'magicPanel'), networks = Object.entries(panel.NetworkSettings.Networks);
  if (networks.length !== 1) throw new h.Blocked('Disposable database requires one unambiguous Panel Docker network');
  const [network, info] = networks[0], imageID = run(['image', 'inspect', 'postgres:17.7-alpine3.22', '--format', '{{.Id}}']);
  if (!/^sha256:[a-f0-9]{64}$/.test(imageID) || !/^[a-f0-9]{64}$/.test(info.NetworkID)) throw new h.Blocked('Database fixture requires an existing immutable image and exact network');
  const journal = { name: 'magic-test-pg-' + crypto.randomBytes(8).toString('hex'), marker: crypto.randomBytes(16).toString('hex'), imageID, network, networkID: info.NetworkID,
    password: crypto.randomBytes(24).toString('hex'), username: 'regression_probe', database: 'regression_fixture', phase: 'intent' };
  (h.state.externalDatabaseFixtures ||= []).push(journal); h.persist();
  // The password is passed via the child environment, never a command argument.
  journal.id = run(['create', '--name', journal.name, '--label', 'magic-test.fixture=' + journal.marker, '--network', network,
    '--memory', '256m', '--cpus', '0.5', '--tmpfs', '/var/lib/postgresql/data:rw,size=128m',
    '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_USER=' + journal.username, '-e', 'POSTGRES_DB=' + journal.database, imageID], { POSTGRES_PASSWORD: journal.password });
  h.persist();
  if (!/^[a-f0-9]{64}$/.test(journal.id) || !owned(inspect(run, journal.id), journal)) throw new h.Blocked('New database container identity or volume proof is incomplete; preserve original intent');
  journal.phase = 'created'; h.persist();
  // Register cleanup before starting. An unresolved platform resource prevents
  // disposal of its physical target even if the functional assertion failed.
  const cleanup = postgresCleanup(h, journal, run);
  h.teardowns.push(cleanup);
  run(['start', journal.id]);
  const started = inspect(run, journal.id);
  if (!owned(started, journal) || !started.State.Running || started.NetworkSettings.Networks[network]?.NetworkID !== journal.networkID) throw new h.Blocked('Original disposable database did not start on the exact intended network');
  let ready = false;
  for (let i = 0; i < 30; i++) {
    // pg_isready does not authenticate or write SQL. Polling reads are safe.
    try { run(['exec', journal.id, 'pg_isready', '-h', '127.0.0.1', '-p', '5432', '-U', journal.username, '-d', journal.database]); ready = true; break; }
    catch (_) { if (i < 29) await pause(1000); }
  }
  if (!ready) throw new h.Blocked('Disposable database readiness was not established');
  journal.phase = 'ready'; h.persist();
  h.observe({ kind: 'disposable-postgres-ready', id: journal.id, imageID, networkID: journal.networkID, address: journal.name + ':5432', memoryLimitBytes: started.HostConfig.Memory, cpuNanoLimit: started.HostConfig.NanoCpus, persistentVolumesUsed: false });
  return { ...journal, address: journal.name + ':5432', alternateAddress: started.NetworkSettings.Networks[network].IPAddress + ':5432', memoryLimitBytes: started.HostConfig.Memory, cleanup };
}
module.exports = { createPostgres, postgresCleanup, owned };
