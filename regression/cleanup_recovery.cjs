const { isDeepStrictEqual: same } = require('node:util');
const crypto = require('node:crypto');
const { sanitize } = require('./evidence_sanitizer.cjs');
// Selection is not disposition. Each mode still performs its full original
// actor/intent/receipt proof; unrelated unknown commands remain protected.
function pendingBusinessReconciliation(resources, mode) {
  if (!['matrix-write-refusal', 'business-create'].includes(mode)) throw Error('Unknown business reconciliation mode');
  return resources.filter(r => r.kind === 'business-record' && r.phase !== 'deleted' && r.commands?.some(c =>
    c.outcome === 'unknown' && (mode === 'business-create' ? c.body?.operation === 'create' || c.body?.cancel === true :
      c.body?.operation === 'update' && c.response?.status === 200 && c.response.data?.error?.code === 5 &&
      c.response.data.error.message === '读取安装页面需要应用实例运行权限')));
}
async function confirmRolledBackNamespace(h,r,proof) {
  const c=r.creation,name=c?.intended?.name;
  if(r.kind!=='namespace' || r.collection!=='/panel/namespace-onboardings/' || r.phase!=='intent' || r.id!=null || c?.outcome!=='unknown' || c.response || !same(c.actorIdentity,h.admin.identity) || c.origin!==h.admin.origin || !name || proof?.name!==name || proof.sourceContainer!=='magiccas' || !/^[a-f0-9]{32}$/.test(proof.creationId || '') || proof.sourceLogSha256!=='sha256:'+crypto.createHash('sha256').update(proof.sourceLine || '').digest('hex') || !proof.sourceLine.includes('namespace provisioning failed namespace='+name+' ') || !proof.sourceLine.includes('creationId='+proof.creationId+' '))throw new h.Blocked('Original failed namespace owner identity and immutable source proof required');
  const receipt=(await h.ok(h.admin,'GET','/cas/namespace/creations/'+proof.creationId)).value;
  h.check('Formal original creation owner proves terminal rollback with exact namespace identity',receipt.creationId===proof.creationId && receipt.name===name && receipt.phase==='rolled-back' && Number.isSafeInteger(receipt.namespaceId) && receipt.namespaceId>0 && receipt.version>0 && !!receipt.failure && !receipt.namespace,receipt);
  const absent=await h.api(h.admin,'GET','/cas/namespaces/'+receipt.namespaceId);
  h.check('Independent original namespace ID is absent after owner rollback', [200,404].includes(absent.status) && absent.data?.error?.code===2 && absent.data.value==null,absent);
  const rows=await h.directory(h.admin,'/cas/namespaces/');
  h.check('Complete current owner directory excludes original rolled-back namespace name and ID',!rows.some(v=>v.id===receipt.namespaceId || v.name===name));
  if(!same(c.actorIdentity,h.admin.identity) || c.origin!==h.admin.origin)throw new h.Blocked('Original rollback actor changed');
  r.id=receipt.namespaceId;r.reconciliation={kind:'owner-terminal-namespace-rollback',receipt,sourceLogSha256:proof.sourceLogSha256,creationId:proof.creationId,noCommandReplayed:true};r.phase='deleted';h.persist();return r.reconciliation;
}
async function confirmProxySessionRefusal(h, r) {
  const c = r.creation, response = c?.response;
  const directory = r.kind === 'definition' && r.collection === '/panel/application/definitions/' ? r.collection
    : r.kind === 'namespace' && r.collection === '/panel/namespace-onboardings/' ? '/cas/namespaces/' : null;
  // Web.currentSession returns this response before proxy target selection.
  // A generic 503, timeout or missing response is never a disposition proof.
  if (!directory || r.phase !== 'intent' || r.id != null || c?.outcome !== 'unconfirmed' || response?.status !== 503 ||
      !same(response.data, { text: 'application session refresh is still in progress; retry shortly\n' }) ||
      !same(c.actorIdentity, h.admin.identity) || c.origin !== h.admin.origin || !c.intended?.name ||
      !same(c.identity, r.kind === 'definition' ? { uuid: c.intended.uuid } : { name: c.intended.name }) ||
      r.kind === 'definition' && !/^[a-f0-9]{32}$/.test(c.intended.uuid || '')) throw new h.Blocked('Original exact pre-dispatch session refusal required; generic errors and unknown writes remain open');
  const rows = await h.directory(h.admin, directory);
  if (!same(c.actorIdentity, h.admin.identity) || c.origin !== h.admin.origin) throw new h.Blocked('Original actor changed during refusal reconciliation');
  h.check('Complete independent owner directory excludes every original refused resource identity', !rows.some(v => v.name === c.intended.name || r.kind === 'definition' && v.uuid === c.intended.uuid));
  r.reconciliation = { kind: 'bff-session-refusal-before-target', originalJournalId: c.journalId,
    originalResponseDigest: 'sha256:' + crypto.createHash('sha256').update(JSON.stringify(response)).digest('hex'),
    ownerDirectory: directory, originalName: c.intended.name, noCommandReplayed: true,
    proof: 'Exact Web currentSession refusal before proxy target dispatch and complete owner absence; original failed response retained.' };
  r.phase = 'deleted'; h.persist(); return r.reconciliation;
}
const credentialIdentity = value => value == null ? value : Object.fromEntries(['name', 'clientId', 'credentialId', 'endpointId', 'scope', 'audience', 'status', 'issuedAt', 'expiresAt'].filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]]));
function bindOriginalCleanup(state, original) {
  if (!Array.isArray(original?.resources) || !Array.isArray(original.trace)) throw Error('Original cleanup evidence is incomplete');
  const pending = state.resources.filter(r => r.phase !== 'deleted');
  if (!pending.length) throw Error('No original pending resource to recover');
  for (const r of pending) {
    const sameAnonymousResource = row => {
      if (!['business-record', 'member-access-retirement', 'source-effect-scenario'].includes(r.kind)) return true;
      if (Object.hasOwn(r, 'confirmed') || Object.hasOwn(r, 'error')) return false;
      // These resources have no synthetic common id. Bind their full original
      // command/installation snapshot, not an ambiguous kind + undefined id.
      const { confirmed, error, ...snapshot } = row;
      return same(sanitize(snapshot), sanitize(r));
    };
    const sameFileIdentity = row => r.kind !== 'ordinary-file' || ['base', 'relative', 'source', 'path', 'expectedDigest', 'expectedSize', 'origin', 'actorName', 'visibility', 'uploadRoute'].every(key => same(row[key], r[key]));
    const matches = original.resources.filter(row => row.confirmed === false && row.kind === r.kind && row.collection === r.collection && row.id === r.id && row.name === r.name &&
      sameAnonymousResource(row) && sameFileIdentity(row) && same(row.brandingCommands, r.brandingCommands) && same(row.pendingDatabaseCommands, r.pendingDatabaseCommands) && same(row.availability, r.availability) && same(row.authorityCommands, r.authorityCommands) && same(row.nativePackageDraftCommands, r.nativePackageDraftCommands) && row.actor === r.actor &&
      same(sanitize(row.scriptPublication), sanitize(r.scriptPublication)) &&
      same(sanitize(row.pendingServiceCommands), sanitize(r.pendingServiceCommands)) &&
      (r.kind !== 'definition' || same(sanitize(row.modelDelivery), sanitize(r.modelDelivery))) &&
      (!r.scriptPublication || same(sanitize(row.pendingAuthoringSave), sanitize(r.pendingAuthoringSave))) &&
      (r.kind !== 'service-graph-subscription' || row.requestId === r.requestId && row.serviceId === r.serviceId && row.actorOrigin === r.actorOrigin && same(row.receipt, r.receipt)) &&
      (r.kind !== 'branding-profile-restore' || row.namespace === r.namespace && row.origin === r.origin && same(row.original, r.original) && same(row.last, r.last) && same(row.commands, r.commands)) &&
      (r.kind !== 'log-retention-restore' || row.origin === r.origin && same(row.original, r.original) && same(row.last, r.last) && same(row.commands, r.commands)) &&
      (!['deployment-review-request', 'deployment-review-guard'].includes(r.kind) || ['commands', 'last', 'installation', 'operation', 'placement', 'failedModelDisposition'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (!['native-provider-probe', 'native-package-probe'].includes(r.kind) || ['commands', 'imports', 'package', 'preexistingIds', 'packageAcknowledged', 'applicationUuid'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'native-admission-probe' || ['route', 'definitionId', 'variant', 'intended', 'journalId', 'outcome', 'response', 'before', 'after'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'bound-reference-probe' || ['origin', 'namespace', 'subject', 'name', 'consumer', 'foreignConsumer', 'expectedSize', 'expectedDigest', 'fileRef', 'commands'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'runtime-policy-probe' || ['origin', 'policyId', 'before', 'last', 'inventory', 'installations', 'commands'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'native-runtime-request' || ['commands', 'last', 'input', 'marker', 'installation', 'operation', 'uninstallLifecycleId', 'currentInstallation', 'failureRetirement', 'failureObservation'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'native-lifecycle-probe' || ['origin', 'config', 'scripts', 'privateRoot', 'env', 'journal', 'network', 'packageId', 'nativeIds', 'before', 'resume', 'sentinelNonce', 'probeImageLabels', 'probes', 'commands', 'ownerReads', 'peers'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'deployment-material-probe' || ['origin', 'config', 'sources', 'privateRoot', 'root', 'commands', 'tracked', 'originalFiles', 'expectedFiles', 'originalPeers', 'displacedFiles', 'snapshot', 'lock'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'lifecycle-admission-probe' || ['origin', 'reads', 'route', 'intended', 'expected', 'journalId', 'outcome', 'response', 'before', 'after'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      (r.kind !== 'requester-preview-request' || ['commands', 'last', 'requester'].every(key => same(sanitize(row[key]), sanitize(r[key])))) &&
      same(row.actorIdentity, r.actorIdentity) && same(row.ownerIdentity, r.ownerIdentity) &&
      same(row.creation?.actorIdentity, r.creation?.actorIdentity) && row.creation?.origin === r.creation?.origin &&
      same(row.creation?.identity, r.creation?.identity) && row.parentSubscriptionId === r.parentSubscriptionId && same(credentialIdentity(row.value), credentialIdentity(r.value)));
    if (matches.length !== 1) throw Error('Pending resource differs from exact original immutable cleanup evidence');
  }
  return pending;
}
function recoveredNamespace(r) {
  const recovery = r.recovery, receipt = recovery?.receipt, intended = r.creation?.intended, value = receipt?.namespace;
  return r.kind === 'namespace' && recovery?.kind === 'cas-namespace-creation' && same(recovery.originalIdentity, r.creation.identity) &&
    /^[a-f0-9]{32}$/.test(receipt?.creationId || '') && receipt.phase === 'completed' && receipt.version > 0 &&
    receipt.namespaceId === r.id && receipt.name === intended.name && value?.id === r.id && value.name === intended.name &&
    value.status === intended.status && value.startTime === intended.startTime && value.expireTime === intended.expireTime && value.description === intended.description && same(value.scope || [], intended.scope || []);
}
async function recoverNamespace(h, r, proof) {
  if (r.kind !== 'namespace' || r.id || r.creation?.outcome !== 'unknown' || r.creation.response || !same(h.admin.identity, r.creation.actorIdentity) || h.admin.origin !== r.creation.origin) throw new h.Blocked('Namespace recovery requires exact original unresolved creation and original platform actor');
  const escaped = r.creation.intended.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  h.check('Original CAS provisioning log binds the exact namespace and full operation identity', proof?.name === r.creation.intended.name && /^[a-f0-9]{32}$/.test(proof.creationId) && proof.sourceContainer === 'magiccas' && proof.sourceLogSha256 === 'sha256:' + crypto.createHash('sha256').update(proof.sourceLine || '').digest('hex') &&
    /namespace provisioning completed/.test(proof.sourceLine) && new RegExp('namespace["= :]+"?' + escaped + '(?:"|\\s|,)').test(proof.sourceLine) && proof.sourceLine.includes(proof.creationId), { name: proof?.name, creationId: proof?.creationId, sourceLogSha256: proof?.sourceLogSha256 });
  if (proof.retirement) return confirmCompensatedNamespace(h, r, proof);
  const receipt = (await h.ok(h.admin, 'GET', '/cas/namespace/creations/' + proof.creationId)).value;
  const candidate = { ...r, id: receipt?.namespaceId, recovery: { kind: 'cas-namespace-creation', originalIdentity: structuredClone(r.creation.identity), receipt } };
  h.check('Formal CAS receipt proves the exact original creation and complete namespace contents', recoveredNamespace(candidate), receipt);
  r.id = candidate.id; r.recovery = { ...candidate.recovery, ownerLog: { name: proof.name, creationId: proof.creationId, sourceLogSha256: proof.sourceLogSha256 } }; r.phase = 'created'; h.persist();
  return r.recovery;
}
const absent = response => [200, 404].includes(response.status) && response.data?.error?.code === 2 && response.data.value == null;
async function confirmCompensatedNamespace(h, r, proof) {
  const ref = proof.retirement;
  h.check('Compensation reference carries a full original owner retirement identity', Number.isSafeInteger(ref.namespaceId) && ref.namespaceId > 0 && Number.isSafeInteger(ref.expectedVersion) && ref.expectedVersion > 0 && /^[a-f0-9]{32}$/.test(ref.requestId || '') &&
    ref.sourceLogSha256 === 'sha256:' + crypto.createHash('sha256').update(ref.sourceLine || '').digest('hex') &&
    /namespace retirement attempt finished/.test(ref.sourceLine) && ref.sourceLine.includes('namespaceId=' + ref.namespaceId + ' ') && ref.sourceLine.includes('requestId=' + ref.requestId + ' ') && /phase=completed(?:\s|$)/.test(ref.sourceLine));
  const query = new URLSearchParams({ requestId: ref.requestId, name: r.creation.intended.name, expectedVersion: String(ref.expectedVersion) });
  const receipt = (await h.ok(h.admin, 'GET', '/cas/namespace/retirements/' + ref.namespaceId + '?' + query)).value;
  h.check('Formal owner retirement binds the original namespace name, exact ID and terminal request', receipt?.namespaceId === ref.namespaceId && receipt.requestId === ref.requestId && receipt.expectedVersion === ref.expectedVersion && receipt.name === r.creation.intended.name && receipt.phase === 'completed' && receipt.version > 0 && !receipt.failure && !receipt.namespace, receipt);
  const creation = await h.api(h.admin, 'GET', '/cas/namespace/creations/' + proof.creationId);
  h.check('Original creation has no current namespace projection after owner compensation', absent(creation), creation);
  h.check('Independent exact namespace read confirms compensated resource absent', absent(await h.api(h.admin, 'GET', '/cas/namespaces/' + ref.namespaceId)));
  const directory = await h.directory(h.admin, '/cas/namespaces/');
  h.check('Complete owner directory contains neither original name nor retired ID', !directory.some(n => n.name === r.creation.intended.name || n.id === ref.namespaceId));
  r.id = ref.namespaceId; r.recovery = { kind: 'cas-compensated-namespace', originalIdentity: structuredClone(r.creation.identity), creationId: proof.creationId, receipt, proof };
  r.phase = 'deleted'; h.persist();
  return r.recovery;
}
async function confirmUnsentTemplate(h, r, evidence) {
  const actor = h.tenantAdmin, reason = evidence?.reason || '';
  if (r.kind !== 'role-template' || r.id || r.creation?.outcome !== 'unknown' || r.creation.response || !same(actor?.identity, r.creation.actorIdentity) || actor.origin !== r.creation.origin) throw new h.Blocked('DNS recovery requires exact original unknown template intent and actor');
  const host = new URL(actor.origin).hostname, endpoint = actor.origin + '/api/v1/web/proxy' + r.collection;
  const lengths = [...reason.matchAll(/\bcontent-length: (\d+)\s*(?:\n|$)/g)].map(m => Number(m[1]));
  h.check('Immutable original case identifies a DNS failure before the exact POST could connect', evidence.status === 'blocked' && reason.startsWith('apiRequestContext.fetch: getaddrinfo ENOTFOUND ' + host + '\n') && reason.includes('→ POST ' + endpoint + '\n') && lengths.length === 1 && lengths[0] === Buffer.byteLength(JSON.stringify(r.creation.intended)), { caseId: evidence.caseId, endpoint });
  const rows = await h.directory(actor, r.collection);
  h.check('Complete independent owner directory confirms original unsent key absent', !rows.some(row => row.key === r.creation.intended.key), { intendedKey: r.creation.intended.key, keys: rows.map(row => row.key) });
  r.recovery = { kind: 'dns-before-connect', originalJournalId: r.creation.journalId, caseId: evidence.caseId, endpoint, ownerKeys: rows.map(row => row.key) };
  r.phase = 'deleted'; h.persist(); return r.recovery;
}
async function confirmRetiredCredential(h, r, original) {
  const actor = h.tenantAdmin;
  if (r.kind !== 'service-graph-credential' || r.outcome !== 'unknown' || r.response || r.value || !same(actor?.identity, r.ownerIdentity) || !same(actor.identity, r.actorIdentity)) throw new h.Blocked('Lost credential requires exact original owner and unresolved initial issuance');
  const parents = original.resources.filter(p => p.kind === 'service-graph-subscription' && p.id === r.parentSubscriptionId && p.serviceId === r.serviceId && p.confirmed === true && p.phase === 'deleted' && p.outcome === 'accepted' && p.deletion?.outcome === 'accepted' && h.good(p.deletion.response) && same(p.ownerIdentity, r.ownerIdentity));
  h.check('Immutable original cleanup contains one formally retired exact parent subscription', parents.length === 1);
  const parent = parents[0], snapshot = parent.deletion.response.data.value;
  h.check('Original parent owner response preserves service, subscriber and namespace identity', snapshot?.id === parent.id && snapshot.service?.id === r.serviceId && snapshot.namespace === actor.identity.namespace && same(snapshot.subscriberRef, parent.original.subscriberRef), snapshot);
  const matches = (snapshot.credentials || []).filter(c => c.name === r.name && c.clientId && c.credentialId > 0 && c.endpointId > 0);
  h.check('Owner retirement snapshot binds exactly one original lost credential', matches.length === 1);
  const credential = matches[0], cas = '/cas/namespaces/' + actor.identity.namespace + '/';
  h.check('Exact original subscription remains absent', absent(await h.api(actor, 'GET', parent.collection + parent.id)));
  for (const [route, key, value] of [[cas + 'oauth/clients/' + encodeURIComponent(credential.clientId), 'clientId', credential.clientId], [cas + 'endpoints/' + credential.endpointId, 'id', credential.endpointId]]) {
    const result = await h.api(actor, 'GET', route);
    h.check('Independent CAS owner confirms original credential principal retired', absent(result) || h.good(result) && result.data.value?.[key] === value && [1, 3].includes(result.data.value.status), result);
  }
  r.recovery = { kind: 'parent-subscription-retirement', originalSubscriptionId: parent.id, originalRequestId: parent.requestId,
    credential: credentialIdentity(credential), endpointId: credential.endpointId, proof: 'Immutable original formal parent deletion includes this exact credential; independent Panel/CAS terminal reads' };
  r.phase = 'deleted'; h.persist(); return r.recovery;
}
async function cleanupRetiredCreator(h, r, original) {
  const creator = r.creation?.actorIdentity;
  const owner = [h.tenantAdmin, h.otherTenantAdmin].find(a => a?.identity?.namespace === creator?.namespace);
  const base = '/cas/namespaces/' + creator?.namespace + '/';
  const creation = r.creation?.response;
  if (r.kind !== 'role-template' || r.phase !== 'created' || r.deletion || r.recovery || r.creation?.outcome !== 'accepted' || !h.good(creation || { status: 0, data: {} }) || creation.data.value?.id !== r.id || creation.data.value.key !== r.creation.intended.key || r.collection !== base + 'role-templates/' || !owner || same(owner.identity, creator) || owner.origin !== r.creation.origin) throw new h.Blocked('Retired creator disposition requires acknowledged exact original template and distinct original same-tenant manager');
  const retired = original.resources.filter(row => row.kind === 'account' && row.confirmed === true && row.phase === 'deleted' && row.collection === base + 'accounts/' && row.creation?.intended?.account === creator.account && row.deletion?.outcome === 'acknowledged' && h.good(row.deletion.response) && row.deletion.response.data.value?.id === row.id && row.deletion.response.data.value.account === creator.account);
  h.check('Original immutable cleanup proves one formally retired exact creator account', retired.length === 1);
  const account = retired[0];
  h.check('Independent CAS owner confirms exact original creator account remains absent', absent(await h.api(h.admin, 'GET', account.collection + account.id)));
  const current = await h.api(owner, 'GET', r.collection + r.id);
  h.check('Formal tenant manager reads the exact acknowledged original template', h.good(current) && current.data.value?.id === r.id && current.data.value.key === r.creation.intended.key);
  r.recovery = { kind: 'retired-creator-owned-template-disposition', retiredCreatorId: account.id, originalActor: structuredClone(creator), actorIdentity: structuredClone(owner.identity), origin: owner.origin, outcome: 'unknown' }; h.persist();
  const response = await h.api(owner, 'DELETE', r.collection + r.id); r.recovery.response = response; h.persist();
  h.check('Real current tenant manager authority acknowledges exact original template deletion', h.good(response) && response.data.value?.id === r.id && response.data.value.key === r.creation.intended.key);
  h.check('Independent original template owner read confirms formal disposition', absent(await h.api(owner, 'GET', r.collection + r.id)));
  r.recovery.outcome = 'confirmed'; r.phase = 'deleted'; h.persist();
  return r.recovery;
}
module.exports = { pendingBusinessReconciliation, cleanupRetiredCreator, bindOriginalCleanup, recoverNamespace, recoveredNamespace, confirmUnsentTemplate, confirmRetiredCredential, confirmProxySessionRefusal, confirmRolledBackNamespace };
