// Negative build/publication commands retain the exact actor, payload and
// pre-command owner directories. Unknown outcomes never authorize replay/delete.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { readDirectory } = require('./directory.cjs');
const packages = '/panel/application/deployment-packages/';
const definitions = '/panel/application/definitions/';
function targetRejection(response, variant) {
  if (response?.status !== 400 || response.data?.error?.code !== 4 || response.data.value != null) return false;
  const message = response.data.error.message;
  if (variant === 'missing-dependency') return message === 'components.api.dependsOn: 组件依赖引用无效';
  return variant === 'missing-image' && message === '组件 api 镜像解析失败: deployment image is not prepared in the local docker daemon';
}
function originalActor(h, r) {
  const actor = h[r.actor];
  if (!actor || actor.origin !== r.origin || !same(actor.identity, r.actorIdentity)) throw new h.Blocked('Native admission needs the exact original owner actor and origin');
  return actor;
}
async function snapshot(h, actor, r) {
  const value = { packages: await readDirectory(h, actor, packages) };
  if (r.definitionId) {
    value.definition = (await h.ok(actor, 'GET', definitions + r.definitionId)).value;
    value.revisions = await readDirectory(h, actor, definitions + r.definitionId + '/revisions/');
  }
  return value;
}
async function probe(h, { intended, variant, definitionId }) {
  if (!['missing-dependency', 'missing-image'].includes(variant)) throw new h.Blocked('Unknown native admission diagnostic');
  if (definitionId !== undefined && (!Number.isSafeInteger(definitionId) || definitionId < 1 || variant !== 'missing-image')) throw new h.Blocked('Invalid original native revision identity');
  const route = definitionId ? definitions + definitionId + '/revisions/' : packages + 'builds/';
  if (h.state.resources.some(r => r.kind === 'native-admission-probe' && r.route === route && same(r.intended, intended))) throw new h.Blocked('Original native admission command already exists; no POST replay');
  const actor = h.admin, r = { kind: 'native-admission-probe', actor: 'admin', actorIdentity: structuredClone(actor.identity), origin: actor.origin,
    collection: packages, route, definitionId, variant, intended: structuredClone(intended), journalId: crypto.randomBytes(16).toString('hex'), phase: 'intent', outcome: 'not-sent' };
  h.state.resources.push(r); h.persist();
  r.before = await snapshot(h, originalActor(h, r), r); h.persist();
  if (definitionId) h.check('Original invalid-image draft has no published revision before command', r.before.definition.id === definitionId && r.before.revisions.length === 0, r.before);
  r.outcome = 'unknown'; h.persist();
  r.response = await h.api(originalActor(h, r), 'POST', route, r.intended);
  // Persist unexpected returned identities as well; absence of an ID never
  // licenses DELETE /undefined or retrying the original business command.
  r.outcome = targetRejection(r.response, variant) ? 'rejected-before-registration' : h.good(r.response) ? 'unexpectedly-accepted' : 'unconfirmed-rejection';
  if (r.response.data?.value?.id) r.returnedId = r.response.data.value.id;
  h.persist();
  r.after = await snapshot(h, originalActor(h, r), r); h.persist();
  h.check('Actual native command reaches exact component-stage ' + variant + ' rejection', r.outcome === 'rejected-before-registration', r.response);
  h.check('Independent complete package/revision owner reads remain exactly unchanged', same(r.before, r.after), { before: r.before, after: r.after });
  r.phase = 'deleted'; h.persist();
  return r;
}
async function cleanup(h, r) {
  const actor = originalActor(h, r);
  if (r.outcome === 'not-sent') return { proof: 'Native admission command not dispatched' };
  if (r.outcome !== 'rejected-before-registration' || !targetRejection(r.response, r.variant) || !r.before) throw new h.Blocked('Unresolved original native command: retain original intent, no POST replay or guessed DELETE');
  const current = await snapshot(h, actor, r);
  if (!same(current, r.before)) throw new h.Blocked('Native admission owner state differs from original; retain exact command for formal disposition');
  return { proof: 'Exact pre-registration rejection and independently unchanged complete original owner state' };
}
function guardDefinitionCleanup(h, resource) {
  if (resource.collection === definitions && h.state.resources.some(r => r.kind === 'native-admission-probe' && r.definitionId === resource.id && r.phase !== 'deleted')) throw new h.Blocked('Original native publication is unresolved; preserve its exact parent definition');
}
module.exports = { probe, cleanup, targetRejection, guardDefinitionCleanup };
