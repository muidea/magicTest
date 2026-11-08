// Read-only disposition of a precisely acknowledged stale UI PUT whose
// independent read was interrupted. Never replay the failed authoring command.
const { isDeepStrictEqual: same } = require('node:util');
async function reconcileConflict(h, r, evidence, evidenceDigest) {
  const base = '/panel/application/definitions/', intent = r.pendingAuthoringSave, created = r.creation?.response?.data?.value;
  const exactActor = () => same(h.admin.identity, r.creation?.actorIdentity) && h.admin.origin === r.creation?.origin;
  const response = intent?.response, match = intent?.route?.match(/^\/panel\/application\/definition\/entitys\/([1-9][0-9]*)$/);
  const entityId = match && Number(match[1]);
  if (r.kind !== 'definition' || r.collection !== base || r.phase === 'deleted' || !r.creation?.ownershipConfirmed || !created || created.id !== r.id || !exactActor() ||
      intent?.confirmed !== false || intent.method !== 'PUT' || !Number.isSafeInteger(entityId) || entityId <= 0 || intent.payload?.application?.id !== r.id ||
      !Number.isSafeInteger(intent.payload.expectedDefinitionVersion) || !Number.isSafeInteger(intent.payload.expectedEntityVersion) ||
      response?.status !== 200 || response.data?.error?.code !== 19 || response.data.value != null || !/^sha256:[a-f0-9]{64}$/.test(evidenceDigest)) throw new h.Blocked('No exact original acknowledged entity conflict; retain original command');
  const modelRoute = base + r.id + '/model-draft', trace = evidence?.trace || [];
  const acknowledged = trace.some(t => t.kind === 'assertion' && t.message === 'Original UI write reached the expected owner outcome' && t.passed === true && same(t.details, response));
  const interruption = trace.some(t => t.kind === 'browser-transport-failure' && t.origin === h.admin.origin && t.path === '/api/v1/web/proxy' + modelRoute && t.method === 'GET' && t.error === 'net::ERR_NETWORK_CHANGED');
  const writes = trace.filter(t => t.kind === 'request' && t.origin === h.admin.origin && same(t.actor, h.admin.identity) && t.method === 'PUT' && t.route === modelRoute && h.good(t.response));
  const before = writes.at(-1)?.response.data.value;
  if (evidence.caseId !== 'F013-003' || evidence.status !== 'blocked' || !acknowledged || !interruption || before?.applicationId !== r.id || before.applicationUuid !== created.uuid ||
      before.definitionVersion <= intent.payload.expectedDefinitionVersion || !before.targetDigest || !before.entities?.some(e => e.id === entityId && e.updateTime > intent.payload.expectedEntityVersion)) throw new h.Blocked('Immutable original case lacks the exact newer owner snapshot and conflict/interruption proof');
  const app = (await h.ok(h.admin, 'GET', base + r.id)).value;
  h.check('Conflict recovery reads the original acknowledged definition identity', app.id === r.id && app.uuid === created.uuid && app.name === created.name && exactActor(), app);
  const current = (await h.ok(h.admin, 'GET', modelRoute)).value;
  h.check('Independent owner exactly preserves the original newer snapshot after rejected stale PUT', same(current, before) && exactActor(), current);
  intent.reconciliation = { originalJournalId: intent.journalId, originalCaseEvidenceDigest: evidenceDigest, applicationId: r.id, entityId, definitionVersion: current.definitionVersion,
    targetDigest: current.targetDigest, noCommandReplayed: true, proof: 'Original terminal VersionConflict plus exact immutable pre-conflict newer snapshot and independent current owner equality' };
  intent.confirmed = true; h.persist();
  return intent.reconciliation;
}
module.exports = { reconcileConflict };
