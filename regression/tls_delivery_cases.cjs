// Formal certificate delivery and isolated rotation; all mutations use owner helpers.
const crypto = require('node:crypto');
const https = require('node:https');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const { fixture } = require('./delivery_cases.cjs');
const { strictMismatch } = require('./ingress_cases.cjs');
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
function requestAt(host, port, servername, ca, route = '/api/v1/web/branding/') {
  return new Promise((resolve, reject) => {
    let fingerprint;
    const request = https.request({ hostname: host, port, servername, ca, rejectUnauthorized: true, agent: false,
      method: 'GET', path: route, headers: { Host: servername, Accept: 'application/json' } }, response => {
      const chunks = []; let bytes = 0;
      response.on('data', chunk => { bytes += chunk.length; if (bytes > 65536) response.destroy(Error('Finite public TLS probe response budget exceeded')); else chunks.push(chunk); });
      response.once('error', reject);
      response.once('end', () => {
        const body = Buffer.concat(chunks); let value;
        try { value = JSON.parse(body); } catch { value = { text: body.toString().slice(0, 1000) }; }
        resolve({ status: response.statusCode, fingerprint, data: value });
      });
    });
    request.once('socket', socket => socket.once('secureConnect', () => { fingerprint = hash(socket.getPeerCertificate().raw); }));
    request.setTimeout(15000, () => request.destroy(Error('Strict TLS probe timeout')));
    request.once('error', reject); request.end();
  });
}
function prepare(h, platform, original, scratch) {
  const fs = h.fs, path = h.path, names = ['tls.crt', 'tls.key', 'ca.crt'];
  const before = Object.fromEntries(names.map(name => [name, fs.readFileSync(path.join(original, name))]));
  const local = path.join(scratch, 'local-ca'), explicit = path.join(scratch, 'files');
  fs.mkdirSync(local, { mode: 0o700 });
  for (const name of names) { fs.copyFileSync(path.join(original, name), path.join(local, name)); fs.chmodSync(path.join(local, name), name.endsWith('.key') ? 0o600 : 0o644); }
  const script = path.join(platform, 'scripts/deployment-tls.sh'), reload = path.join(platform, 'scripts/reload-traefik-tls.sh');
  const materialize = (directory, env) => execFileSync('sh', ['-c', 'set -eu; . "$1"; deployment_materialize_tls local.vpc "$2" "$3"', 'tls-probe', script, directory, reload],
    { env: { ...process.env, ...env }, timeout: 30000, stdio: ['ignore', 'pipe', 'pipe'] });
  materialize(local, { TLS_MODE: 'local-ca' });
  materialize(explicit, { TLS_MODE: 'files', TLS_CERT_FILE: path.join(local, 'tls.crt'), TLS_KEY_FILE: path.join(local, 'tls.key'), TLS_CA_FILE: path.join(local, 'ca.crt') });
  for (const directory of [local, explicit]) {
    h.check('Formal preparation retains exact leaf, private key and CA bytes without changing the original deployment', names.every(name =>
      fs.readFileSync(path.join(directory, name)).equals(before[name]) && fs.readFileSync(path.join(original, name)).equals(before[name])));
    h.check('Prepared key and TLS directory have restrictive formal delivery modes', (fs.statSync(path.join(directory, 'tls.key')).mode & 0o777) === 0o600 && (fs.statSync(directory).mode & 0o777) === 0o700);
  }
  const leaf = new crypto.X509Certificate(before['tls.crt']);
  return { modes: [local, explicit].map((directory, index) => ({ mode: index ? 'files' : 'local-ca-valid-material-reuse', ca: fs.readFileSync(path.join(directory, 'ca.crt')) })),
    leafDigest: hash(leaf.raw), certificate: { subject: leaf.subject, issuer: leaf.issuer, san: leaf.subjectAltName, validTo: leaf.validTo },
    originalUnchanged: () => names.every(name => fs.readFileSync(path.join(original, name)).equals(before[name])) };
}
async function delivery(h) {
  require('./delivery_fixture.cjs').requireIsolatedDaemon(h, 'DELIVERY-FIXTURE: dedicated nested daemon isolation is required for TLS delivery mutation');
  await fixture(h);
  const config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig)), platform = config.platformRoot;
  const original = h.path.join(platform, 'services/secret/tls');
  for (const file of [original, ...['tls.crt', 'tls.key', 'ca.crt'].map(name => h.path.join(original, name))])
    if (h.fs.lstatSync(file).isSymbolicLink()) throw new h.Blocked('Exact isolated TLS owner paths must not be redirected');
  const actors = [h.admin, h.tenantAdmin, h.otherTenantAdmin];
  const names = actors.map(a => new URL(a.origin).hostname);
  h.check('TLS fixture addresses distinct actual local tenant Hosts', new Set(names).size === 3 && names.every(name => name.endsWith('.local.vpc')));
  const scratch = h.fs.mkdtempSync(h.path.join(h.fs.realpathSync(os.tmpdir()), 'magictest-tls-delivery-'));
  let prepared;
  try {
    prepared = prepare(h, platform, original, scratch);
    for (const mode of prepared.modes) {
      for (const [index, actor] of actors.entries()) {
        const origin = new URL(actor.origin), result = await requestAt('127.0.0.1', Number(origin.port || 443), names[index], mode.ca);
        h.observe({ kind: 'strict-tls-current-tenant', mode: mode.mode, host: names[index], expectedNamespace: actor.identity.namespace, result });
        h.check('Trusted actual TLS leaf and Host route return only the intended tenant projection', result.status === 200 && !result.data.error && result.data.value?.namespace === actor.identity.namespace && result.fingerprint === prepared.leafDigest, result);
      }
      const unknown = 'missing-' + crypto.randomBytes(10).toString('hex');
      h.check('Unknown TLS Host has no current CAS namespace identity', !(await h.directory(h.admin, '/cas/namespaces/')).some(n => n.name === unknown));
      const result = await requestAt('127.0.0.1', 443, unknown + '.local.vpc', mode.ca);
      h.check('Certificate-covered unknown Host establishes strict TLS then hits the tenant404 fence without a default-tenant projection', result.status === 404 && result.fingerprint === prepared.leafDigest && !result.data.value?.namespace, result);
      const mismatch = await strictMismatch('127.0.0.1', 443, unknown + '.invalid', mode.ca);
      h.check('SAN mismatch fails before application HTTP independently of tenant404', mismatch.code === 'ERR_TLS_CERT_ALTNAME_INVALID');
    }
    h.check('All preparations and actual anonymous probes preserve original TLS owner bytes', prepared.originalUnchanged());
    h.observe({ kind: 'tls-delivery-modes', leafDigest: prepared.leafDigest, certificate: prepared.certificate,
      scope: 'Existing valid local-CA reuse and explicit files materialization, strict actual leaf/chain/Host/tenant reads. No fresh CA rotation, ingress reload, OS trust change or external DNS/CA issuance claim.' });
  } finally { h.fs.rmSync(scratch, { recursive: true, force: true }); }
}
delivery.transport = 'owner-api'; delivery.actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports = { handlers: { 'F062-001': delivery }, requestAt, prepare };

const materialNames = ['tls.crt', 'tls.key', 'ca.crt'];
function materialize(platform, source, destination, mode = 'files', run = execFileSync) {
  return run('sh', ['-c', 'set -eu; . "$1"; deployment_materialize_tls local.vpc "$2" "$3"', 'tls-material',
    require('node:path').join(platform, 'scripts/deployment-tls.sh'), destination, require('node:path').join(platform, 'scripts/reload-traefik-tls.sh')],
    { env: { ...process.env, TLS_MODE: mode, ...(mode === 'files' ? { TLS_CERT_FILE: source + '/tls.crt', TLS_KEY_FILE: source + '/tls.key', TLS_CA_FILE: source + '/ca.crt' } : {}) },
      timeout: 45000, stdio: ['ignore', 'pipe', 'pipe'] });
}
const digests = (h, directory) => Object.fromEntries(materialNames.map(name => [name, hash(h.fs.readFileSync(h.path.join(directory, name)))]));
function containerProjection(run = execFileSync) {
  const rows = JSON.parse(run('docker', ['inspect', 'traefik', 'magicPanel', 'magicGateway', 'magicbase', 'magiccas', 'magicFile', 'magicWebPortal', 'postgres'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }));
  return rows.map(v => ({ name: v.Name, id: v.Id, image: v.Image, running: v.State.Running, startedAt: v.State.StartedAt,
    mounts: v.Mounts.map(m => ({ source: m.Source, target: m.Destination, type: m.Type, writable: m.RW })) }));
}
const canonicalContainers = containers => containers.map(v => ({ ...v, ...(v.mounts ? { mounts: [...v.mounts].sort((a, b) => a.target.localeCompare(b.target)) } : {}) })).sort((a, b) => a.name.localeCompare(b.name));
function rotationGuard(h, r, config, containers) {
  const same = require('node:util').isDeepStrictEqual;
  if (r.kind !== 'tls-material-restore' || !same(h.admin.identity, r.actorIdentity) || h.admin.origin !== r.origin ||
      config.platformRoot !== r.platformRoot || config.daemonId !== r.daemonId || r.originalRoot !== h.path.join(config.platformRoot, 'services/secret/tls') ||
      h.path.dirname(r.scratch) !== h.fs.realpathSync(os.tmpdir()) || !/^magictest-tls-rotation-[A-Za-z0-9]+$/.test(h.path.basename(r.scratch)) ||
      r.backup !== h.path.join(r.scratch, 'original') || r.candidate !== h.path.join(r.scratch, 'next'))
    throw new h.Blocked('TLS restoration requires exact original actor, daemon, private backup and environment paths');
  for (const dir of [r.originalRoot, r.scratch, r.backup, r.candidate]) {
    if (h.fs.realpathSync(dir) !== dir || !h.fs.lstatSync(dir).isDirectory()) throw new h.Blocked('TLS owner or backup directory was redirected');
    for (const name of dir === r.scratch ? [] : materialNames) if (!h.fs.lstatSync(h.path.join(dir, name)).isFile() || h.fs.lstatSync(h.path.join(dir, name)).isSymbolicLink())
      throw new h.Blocked('TLS material must remain exact regular files');
  }
  if (!same(digests(h, r.backup), r.originalDigests) || !same(digests(h, r.candidate), r.candidateDigests) ||
      (h.fs.statSync(h.path.join(r.backup, 'tls.key')).mode & 0o777) !== 0o600 || (h.fs.statSync(r.scratch).mode & 0o777) !== 0o700)
    throw new h.Blocked('Original private TLS backup or candidate integrity changed');
  const current = digests(h, r.originalRoot);
  if (!materialNames.every(name => [r.originalDigests[name], r.candidateDigests[name]].includes(current[name])))
    throw new h.Blocked('Concurrent foreign TLS material must not be overwritten');
  containers = canonicalContainers(containers);
  const before = canonicalContainers(r.containers), ingress = containers.find(v => v.name === '/traefik'), originalIngress = before.find(v => v.name === '/traefik');
  if (!ingress || !originalIngress || !ingress.running || ingress.id !== originalIngress.id || ingress.image !== originalIngress.image || !same(ingress.mounts, originalIngress.mounts) ||
      !ingress.mounts.some(m => m.source === r.originalRoot && m.target === '/etc/traefik/tls' && m.type === 'bind' && m.writable === false) ||
      !same(containers.filter(v => v.name !== '/traefik'), before.filter(v => v.name !== '/traefik')))
    throw new h.Blocked('Original ingress ownership or unrelated core runtime changed; no guessed restart');
  return current;
}
async function served(h, r, source, allowRetiredHosts = false) {
  const ca = h.fs.readFileSync(h.path.join(source, 'ca.crt')), leaf = hash(new crypto.X509Certificate(h.fs.readFileSync(h.path.join(source, 'tls.crt'))).raw);
  const probes = [];
  const namespaces = allowRetiredHosts ? await h.directory(h.admin, '/cas/namespaces/') : null;
  for (const spec of r.hosts) {
    const retired = namespaces && !namespaces.some(v => v.name === spec.namespace);
    if (retired) {
      const original = h.state.resources.filter(v => v.kind === 'namespace' && v.name === spec.namespace && v.phase === 'deleted' && v.creation?.ownershipConfirmed && v.creation.identity?.name === spec.namespace &&
        require('node:util').isDeepStrictEqual(v.creation.actorIdentity, r.actorIdentity) && v.creation.origin === r.origin && v.creation.response?.data?.value?.id === v.id && Number.isSafeInteger(v.id) && v.id > 0);
      if (original.length !== 1 || namespaces.some(v => v.id === original[0].id)) throw new h.Blocked('Retired TLS Host requires its unique exact original owner namespace ID and complete directory absence');
      const exact = await h.api(h.admin, 'GET', '/cas/namespaces/' + original[0].id);
      h.check('Original tenant is independently absent before a preserved TLS Host returns404', [200, 404].includes(exact.status) && exact.data?.error?.code === 2 && exact.data.value == null, exact);
    }
    const matches = result => result?.fingerprint === leaf && (retired ? result.status === 404 && !result.data.value?.namespace : result.status === 200 && !result.data.error && result.data.value?.namespace === spec.namespace);
    let result, lastError;
    for (let attempt = 0; attempt < 30; attempt++) {
      try {
        result = await requestAt('127.0.0.1', spec.port, spec.host, ca);
        if (matches(result)) break;
      } catch (error) { lastError = { code: error.code, message: error.message }; }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    h.check('Actual reloaded TLS leaf, strict CA and unchanged Host route match the intended namespace', matches(result),
      { host: spec.host, namespace: spec.namespace, expectedLeaf: leaf, result, lastError });
    probes.push({ host: spec.host, namespace: spec.namespace, fingerprint: result.fingerprint });
  }
  const result = await requestAt('127.0.0.1', r.hosts[0].port, r.unknownHost, ca);
  h.check('Reloaded TLS preserves the exact covered unknown-tenant404 fence', result.status === 404 && result.fingerprint === leaf && !result.data.value?.namespace, result);
  return probes;
}
async function applyMaterial(h, r, source, stage, run = execFileSync) {
  const same = require('node:util').isDeepStrictEqual;
  const previous = r.commands.find(c => c.stage === stage);
  if (previous) {
    if (!same(digests(h, r.originalRoot), digests(h, source))) throw new h.Blocked('Original TLS command remains unresolved; never replay materialization or reload');
    const proof = await served(h, r, source);
    previous.outcome = 'confirmed-by-current-served-leaf'; previous.probes = proof; h.persist(); return;
  }
  const c = { stage, materialize: 'deployment_materialize_tls files', reload: 'reload-traefik-tls.sh', expectedDigests: digests(h, source), outcome: 'unknown' };
  r.commands.push(c); h.persist();
  try {
    materialize(r.platformRoot, source, r.originalRoot, 'files', run); c.materialized = true; h.persist();
    run('sh', [h.path.join(r.platformRoot, 'scripts/reload-traefik-tls.sh')], { timeout: 120000, stdio: ['ignore', 'pipe', 'pipe'] });
    c.reloadReturned = true; h.persist();
  } catch (error) { c.reportedError = { name: error.name, status: error.status, signal: error.signal }; h.persist(); throw error; }
  h.check('Formal files delivery wrote exactly the intended complete TLS material', same(digests(h, r.originalRoot), c.expectedDigests));
  c.probes = await served(h, r, source); c.outcome = 'confirmed'; h.persist();
}
async function restoreMaterial(h, r) {
  const config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig));
  require('./delivery_fixture.cjs').validateIsolation(config, JSON.parse(execFileSync('docker', ['info', '--format', '{{json .}}'], { encoding: 'utf8' })));
  rotationGuard(h, r, config, containerProjection());
  if (!r.commands.length) {
    h.check('No TLS mutation was dispatched and exact original material is still present', require('node:util').isDeepStrictEqual(digests(h, r.originalRoot), r.originalDigests));
    r.noMutationDisposition = await served(h, r, r.backup, true); h.persist();
  } else await applyMaterial(h, r, r.backup, 'restore');
  rotationGuard(h, r, config, containerProjection());
  h.check('Original leaf, key and CA bytes are independently restored after formal reload', require('node:util').isDeepStrictEqual(digests(h, r.originalRoot), r.originalDigests));
  const pending = r.commands.filter(c => c.outcome === 'unknown');
  if (pending.length) throw new h.Blocked('Original TLS operation outcome remains open despite restoration; preserve backup and command history');
  r.phase = 'deleted'; h.persist(); h.fs.rmSync(r.scratch, { recursive: true });
  return { proof: 'Exact original material restored through formal delivery/reload; strict served original leaf/CA and all current tenant routes, unrelated core identities unchanged. Original command history retained, private key backup removed only after confirmation.' };
}
async function rotation(h) {
  await fixture(h);
  const config = JSON.parse(h.fs.readFileSync(h.deliveryFixtureConfig)), platformRoot = config.platformRoot;
  const originalRoot = h.path.join(platformRoot, 'services/secret/tls');
  if (h.fs.existsSync(h.path.join(originalRoot, 'traefik-acme.toml'))) throw new h.Blocked('Controlled local/files TLS rotation requires file-owned current certificate; managed external ACME is a separate scope');
  const scratch = h.fs.mkdtempSync(h.path.join(h.fs.realpathSync(os.tmpdir()), 'magictest-tls-rotation-')), backup = h.path.join(scratch, 'original'), candidate = h.path.join(scratch, 'next');
  h.fs.mkdirSync(backup, { mode: 0o700 });
  let r, primary;
  try {
    for (const name of materialNames) {
      if (h.fs.realpathSync(h.path.join(originalRoot, name)) !== h.path.join(originalRoot, name)) throw new h.Blocked('Original TLS source cannot be redirected');
      h.fs.copyFileSync(h.path.join(originalRoot, name), h.path.join(backup, name)); h.fs.chmodSync(h.path.join(backup, name), name === 'tls.key' ? 0o600 : 0o644);
    }
    materialize(platformRoot, undefined, candidate, 'local-ca');
    const actors = [h.admin, h.tenantAdmin, h.otherTenantAdmin], unknown = 'missing-' + crypto.randomBytes(10).toString('hex');
    h.check('TLS rotation unknown Host is absent in the complete current CAS namespace directory', !(await h.directory(h.admin, '/cas/namespaces/')).some(v => v.name === unknown));
    r = { kind: 'tls-material-restore', phase: 'created', actorIdentity: structuredClone(h.admin.identity), origin: h.admin.origin,
      platformRoot, daemonId: config.daemonId, originalRoot, scratch, backup, candidate, originalDigests: digests(h, backup), candidateDigests: digests(h, candidate), containers: containerProjection(), commands: [],
      unknownHost: unknown + '.local.vpc', hosts: actors.map(actor => { const u = new URL(actor.origin); return { host: u.hostname, port: Number(u.port || 443), namespace: actor.identity.namespace }; }) };
    h.state.resources.push(r); h.persist();
    rotationGuard(h, r, config, containerProjection());
    h.check('Fresh local candidate has different leaf and CA from original material', r.originalDigests['tls.crt'] !== r.candidateDigests['tls.crt'] && r.originalDigests['ca.crt'] !== r.candidateDigests['ca.crt']);
    await served(h, r, backup);
    const sessions = await Promise.all(actors.map(a => h.ok(a, 'GET', '/api/v1/web/session/').then(v => v.value)));
    await applyMaterial(h, r, candidate, 'rotate');
    rotationGuard(h, r, config, containerProjection());
    await restoreMaterial(h, r);
    for (const [index, actor] of actors.entries()) h.check('Original login session survives certificate update and restoration in its own tenant', require('node:util').isDeepStrictEqual((await h.ok(actor, 'GET', '/api/v1/web/session/')).value, sessions[index]));
    h.observe({ kind: 'tls-rotation-restoration', commands: r.commands, originalDigests: r.originalDigests, candidateDigests: r.candidateDigests, qualification: 'Dedicated local/files certificate update, actual formal ingress restart, strict served leaf/CA and tenant routes, original material and sessions restored. No external PKI claim.' });
  } catch (error) { primary = error; throw error; }
  finally {
    if (r && r.phase !== 'deleted') {
      try { await restoreMaterial(h, r); }
      catch (error) { h.observe({ kind: 'tls-original-restoration-open', message: error.message }); if (!primary) throw error; }
    } else if (!r) h.fs.rmSync(scratch, { recursive: true });
  }
}
rotation.transport = 'owner-api'; rotation.actors = ['tenantAdmin', 'otherTenantAdmin'];
module.exports.handlers['F062-003'] = rotation;
Object.assign(module.exports, { materialize, rotationGuard, applyMaterial, restoreMaterial, digests, canonicalContainers });
