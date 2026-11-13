// Real deployment owners operate exclusively on newly allocated private roots.
const { execFileSync } = require('node:child_process');
const os = require('node:os');
const handlers = {};
function cleanupBoundary(h, resource, command = execFileSync) {
  const journalPath = h.path.join(resource.privateRoot, 'workload-journal.json');
  if (!h.fs.existsSync(journalPath) && resource.helperOutput?.beforeWorkloadDispatch === true) {
    resource.phase = 'deleted'; h.persist();
    return { proof: 'Synchronous helper returned before any workload dispatch; no workload journal or command was created.' };
  }
  if (!h.fs.existsSync(journalPath)) throw new h.Blocked('Snapshot workload result remains unknown; retain private intent');
  const journal = JSON.parse(h.fs.readFileSync(journalPath));
  if (!/^[a-f0-9]{64}$/.test(journal.containerId || '') || journal.root !== h.path.join(h.fs.realpathSync(resource.privateRoot), 'deployment') ||
      !/^magictest-snapshot-[a-f0-9]{12}$/.test(journal.name || '')) throw new h.Blocked('Snapshot cleanup requires original exact workload receipt');
  try {
    const current = JSON.parse(command('docker', ['inspect', journal.containerId], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }))[0];
    if (current.Id !== journal.containerId || current.Config.Labels?.['io.muidea.magictest.snapshot'] !== journal.name ||
        current.Mounts?.length !== 1 || current.Mounts[0].Type !== 'bind' || current.Mounts[0].Destination !== '/fixture' ||
        current.Mounts[0].Source !== h.path.join(journal.root, 'apps/data')) throw new h.Blocked('Original snapshot workload ownership changed');
    if (resource.deletion) throw new h.Blocked('Original workload removal remains unknown; do not replay');
    resource.deletion = { outcome: 'unknown' }; h.persist();
    command('docker', ['rm', '-f', journal.containerId], { stdio: ['ignore', 'pipe', 'pipe'] });
    resource.deletion.outcome = 'acknowledged'; h.persist();
  } catch (error) {
    if (!error.stderr || !/No such/.test(String(error.stderr))) throw error;
  }
  let absent = false;
  try { command('docker', ['inspect', journal.containerId], { stdio: ['ignore', 'pipe', 'pipe'] }); }
  catch (error) { absent = error.status === 1 && /No such/.test(String(error.stderr)); }
  if (!absent) throw new h.Blocked('Original snapshot workload absence unconfirmed');
  resource.phase = 'deleted'; h.persist();
  return { proof: 'Exact journaled workload and owned mount; independent Docker owner confirms original container absent. Fixture files retained privately.', originalContainerId: journal.containerId };
}
handlers['F060-003'] = async h => {
  const parent = h.fs.mkdtempSync(h.path.join(os.tmpdir(), 'magictest-snapshot-boundary-'));
  const privateRoot = h.path.join(parent, 'owner-fixture');
  const resource = { kind: 'deployment-boundary', privateRoot, phase: 'intent' };
  h.state.resources.push(resource); h.persist();
  let result;
  try {
    result = JSON.parse(execFileSync('python3', ['-B', h.path.join(h.root, 'regression/snapshot_cases.py'),
      '--platform', h.path.join(os.homedir(), 'dataspace/magicPlatform'), '--private', privateRoot],
    { encoding: 'utf8', timeout: 240000, stdio: ['ignore', 'pipe', 'pipe'] }));
  } catch (error) {
    if (error.stdout) { try { resource.helperOutput = JSON.parse(error.stdout); h.persist(); h.observe({ kind: 'snapshot-boundary-incomplete', ...resource.helperOutput }); } catch {} }
    throw new h.Blocked('SNAPSHOT-BOUNDARY: owner fixture or its cleanup did not complete; private exact workload journal retained outside repositories');
  }
  resource.helperOutput = result; h.persist();
  h.observe({ kind: 'snapshot-workload-disposition', ...cleanupBoundary(h, resource) });
  h.observe({ kind: 'real-deployment-snapshot-boundaries', ...result });
  h.check('Real snapshot owner rejects damaged, wrong-root and online restores without changing original state',
    result.status === 'passed' && result.originalStateUnchanged === true && result.cases?.length === 3 && result.events?.length === 5, result);
};
handlers['F060-003'].transport = 'owner-api';
module.exports = { handlers, cleanupBoundary };
