// Ordinary accounts share a group ceiling, while CAS owns each member's scope.
const { isDeepStrictEqual: same } = require('node:util');
const business = require('./business_cases.cjs');
const { fixture } = require('./delivery_cases.cjs');
const base = '/cas/namespaces/panel/';
async function account(h, role) {
  const value = await h.create(base + 'accounts/', { account: h.state.prefix + '-' + role, displayName: '实例范围成员 ' + role,
    password: h.state.password, status: 2, roleTemplateKeys: ['portal-basic-user'] }, 'account');
  const actor = await h.login(value.account, h.state.password, 'panel', h.state.password + '-' + role);
  h.state.fixtures.businessMembers ||= {};
  h.state.fixtures.businessMembers[role] = { id: value.id, account: value.account, password: actor.password };
  h.persist();
  return { value, role, resource: h.state.resources.find(r => r.kind === 'account' && r.id === value.id), actor: await business.member(h, role) };
}
async function assign(h, member, group, access) {
  const r = member.resource, route = base + 'accounts/' + member.value.id + '/role-templates';
  if (r.authorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original member scope command unresolved; no role replacement replay');
  const body = { roleTemplateKeys: ['portal-basic-user', group.key], applicationScopes: [{ templateKey: group.key, applicationAccess: access }] };
  const c = { method: 'PUT', route, body, outcome: 'unknown' }; (r.authorityCommands ||= []).push(c); h.persist();
  c.response = await h.api(h.admin, 'PUT', route, body); h.persist();
  await confirmAssignment(h, member, group, access, c);
}
async function confirmAssignment(h, member, group, access, c) {
  h.check('Formal CAS group assignment acknowledges exact original member and scoped input', h.good(c.response), c.response);
  const query = new URLSearchParams({ subjectId: member.value.id + '|=', subjectType: 'account|=' });
  const bindings = await h.directory(h.admin, base + 'subject-role-bindings/?' + query);
  const bound = bindings.filter(b => b.sourceType === 'template' && b.sourceKey === group.key && b.status === 2);
  h.check('Independent CAS binding retains exact member-selected scopes rather than the group ceiling', bound.length > 0 && bound.every(b => b.subjectId === member.value.id && b.subjectType === 'account' && (access.length ? same(b.applicationAccess, access) : !Object.hasOwn(b, 'applicationAccess'))), bound);
  const detail = (await h.ok(h.admin, 'GET', base + 'accounts/' + member.value.id)).value;
  // Account detail projects binding roleRefs. Member application scopes are
  // expanded by CAS during authorization, then checked on the real runtime.
  const roles = detail.effectiveRoles || [];
  h.check('Account functional role projection contains only the original common template references', roles.length === group.roleRefs.length && group.roleRefs.every(ref => roles.some(r => r.module === ref.module && r.key === ref.key)), roles);
  c.outcome = 'confirmed'; h.persist();
}
async function reconcile(h, r) {
  if (r.kind !== 'account' || r.phase === 'deleted' || !r.creation?.ownershipConfirmed || r.collection !== base + 'accounts/' || !same(r.creation.actorIdentity, h.admin.identity) || r.creation.origin !== h.admin.origin) throw new h.Blocked('Member scope recovery requires the exact owned account and original administrator');
  const pending = r.authorityCommands?.filter(c => c.outcome === 'unknown');
  if (pending?.length !== 1) throw new h.Blocked('Member scope recovery requires exactly one original unresolved assignment');
  const c = pending[0], scopes = c.body.applicationScopes;
  if (c.method !== 'PUT' || c.route !== base + 'accounts/' + r.id + '/role-templates' || scopes?.length !== 1) throw new h.Blocked('Original scoped assignment identity is incomplete');
  const tracked = h.state.resources.filter(v => v.kind === 'role-template' && v.phase !== 'deleted' && v.creation?.ownershipConfirmed && v.creation.intended.key === scopes[0].templateKey);
  if (tracked.length !== 1) throw new h.Blocked('Original common template identity is missing');
  const group = (await h.ok(h.admin, 'GET', base + 'role-templates/' + tracked[0].id)).value;
  h.check('Original common template retains its exact key and functional references', group.id === tracked[0].id && group.key === scopes[0].templateKey && same(group.roleRefs, tracked[0].creation.intended.roleRefs));
  await confirmAssignment(h, { value: { id: r.id } }, group, scopes[0].applicationAccess, c);
  return { accountId: r.id, templateId: group.id, proof: 'Original acknowledged scope input and independent CAS binding/role reads; no assignment replay' };
}
async function edit(h, member, r, allowed) {
  if (r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original business row command unresolved');
  const manager = await business.member(h, 'manager'), before = await business.record(h, manager, r);
  const body = business.request(r, 'update', [{ name: 'name', value: 'Scoped ordinary writer ' + member.role }]);
  const route = '/apps/entity/value/write/update/execute/?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId;
  const c = { body, actingIdentity: structuredClone(member.actor.identity), outcome: 'unknown' }; r.commands.push(c); h.persist();
  c.response = await h.api(member.actor, 'POST', route, body); h.persist();
  if (allowed) {
    h.check('Original ordinary editor writes through reliable public owner with exact principal and intent receipt', h.good(c.response) && business.receiptMatches(member.actor, body, c.response.data.value), c.response);
    const receipt = (await h.ok(member.actor, 'POST', route.replace('/execute/', '/receipt/'), body)).value;
    const after = await business.record(h, manager, r);
    h.check('Independent original owner and formal receipt confirm only the intended member edit', same(receipt, c.response.data.value) && h.good(after) && after.data.value.name === body.fields[0].value && String(after.data.value.version) === receipt.version && same({ ...after.data.value, name: before.data.value.name, version: before.data.value.version }, before.data.value), after);
    c.receipt = receipt; c.outcome = 'confirmed'; r.version = receipt.version;
  } else {
    h.denied(c.response, 'Original ordinary viewer cannot write an enabled entity capability');
    h.check('Independent original owner preserves the entire row after viewer refusal', same(await business.record(h, manager, r), before));
    c.outcome = 'rejected-authority-and-unchanged';
  }
  h.persist();
}
async function memberScopes(h) {
  const f = await fixture(h), manager = await business.member(h, 'manager');
  const templates = await h.directory(h.admin, base + 'role-templates/');
  const ordinary = templates.filter(t => t.key === 'portal-basic-user' && t.systemManaged && t.subjectType === 'account' && t.status === 2);
  h.check('Existing protected ordinary profile supplies the common functional roles without additional management authority', ordinary.length === 1 && ordinary[0].roleRefs?.length > 0, ordinary);
  const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-instance-group', name: '同组不同实例范围', subjectType: 'account',
    description: 'Only existing installed instance levels; member subsets decided by CAS', roleRefs: structuredClone(ordinary[0].roleRefs), status: 2,
    applicationAccess: f.installations.map(i => ({ applicationUuid: i.deploymentId, accessLevel: 'manager' })) }, 'role-template');
  const members = [await account(h, 'scoped-editor'), await account(h, 'scoped-viewer')];
  for (const [i, member] of members.entries()) await assign(h, member, group, [{ applicationUuid: f.installations[i].deploymentId, accessLevel: i ? 'viewer' : 'editor' }]);
  const contexts = await Promise.all([business.runtime(h, f, 0, manager), business.runtime(h, f, 1, manager)]), records = [];
  let primary;
  try {
    for (const [i, context] of contexts.entries()) records.push(await business.create(h, context, 'group-' + i));
    for (const [i, member] of members.entries()) {
      const own = await business.runtime(h, f, i, member.actor);
      h.check('Actual member runtime capabilities reflect its own editor or viewer level', own.ui.capabilities.get === true && own.ui.capabilities.create === (i === 0) && own.ui.capabilities.update === (i === 0) && own.ui.capabilities.delete === false, own.ui.capabilities);
      h.check('Original scoped member reads its authorized exact ordinary business record', same(await business.record(h, member.actor, records[i]), await business.record(h, manager, records[i])));
      h.inaccessible(await business.record(h, member.actor, records[1 - i]), 'The same group does not expose another member instance record');
      await edit(h, member, records[i], i === 0);
    }
    const saved = (await h.ok(h.admin, 'GET', base + 'role-templates/' + group.id)).value;
    h.check('Member subset assignments preserve the original common template ceiling', same(saved.applicationAccess, group.applicationAccess));
  } catch (error) { primary = error; throw error; }
  finally { await business.finishCleanup(h, [...records].reverse(), primary); }
}
memberScopes.transport = 'owner-api';
async function groupScope(h, m, group, enabled) {
  if (m.resource.authorityCommands?.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original group command unresolved; no replacement');
  const c = { method: 'PUT', route: base + 'accounts/' + m.value.id + '/role-templates', outcome: 'unknown', body: {
    roleTemplateKeys: ['portal-basic-user', ...(enabled ? [group.key] : [])],
    applicationScopes: enabled ? [{ templateKey: group.key, applicationAccess: group.applicationAccess }] : [] } };
  (m.resource.authorityCommands ||= []).push(c); h.persist();
  c.response = await h.api(h.admin, c.method, c.route, c.body); h.persist();
  h.check('Exact original group replacement acknowledged without rewriting independent direct grant', h.good(c.response), c.response);
  const bindings = await h.directory(h.admin, base + 'subject-role-bindings/?' + new URLSearchParams({ subjectId: m.value.id + '|=', subjectType: 'account|=' }));
  const own = bindings.filter(b => b.sourceType === 'template' && b.sourceKey === group.key && b.status === 2);
  h.check('Independent CAS directory confirms exact current group binding scope or its removal', enabled ? own.length > 0 && own.every(b => same(b.applicationAccess, group.applicationAccess)) : own.length === 0, bindings);
  c.outcome = 'confirmed'; h.persist();
}
async function accessCommand(h, r, accessLevel, assignmentId) {
  if (r.commands.some(c => c.outcome === 'unknown') || r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity)) throw new h.Blocked('Original direct access intent unresolved or actor changed; no grant or retirement replay');
  const collection = '/panel/application/installations/' + r.installation.id + '/access-operations/';
  const generation = (await h.ok(h.admin, 'GET', collection.replace('access-operations/', 'access-generation') + '?accountId=' + r.accountId)).value;
  h.check('Current generation baseline belongs to the exact original member and installation', generation.namespace === 'panel' && generation.deploymentId === r.installation.deploymentId && generation.accountId === r.accountId && Number.isSafeInteger(generation.epoch) && generation.epoch >= 0, generation);
  const submissionId = require('node:crypto').randomBytes(16).toString('hex');
  const c = { route: accessLevel ? collection : collection.replace('access-operations/', 'access-retirements/'), outcome: 'unknown',
    body: { submissionId, assignmentId, accountId: r.accountId, accessLevel, expectedEpoch: generation.epoch, reason: accessLevel ? 'Owned ordinary regression union grant' : '' } };
  r.commands.push(c); h.persist();
  c.response = await h.api(h.admin, 'POST', c.route, c.body); h.persist();
  h.check('Exact original direct access intent acknowledged', h.good(c.response), c.response);
  const query = collection + '?submissionId=' + submissionId, intent = (await h.ok(h.admin, 'GET', query)).value;
  h.check('Independent coordinator lookup preserves complete original submitted intent', same(intent, c.response.data.value) && intent.submissionId === submissionId && intent.accountId === r.accountId && intent.installationId === r.installation.id && intent.deploymentId === r.installation.deploymentId && intent.accessLevel === accessLevel && intent.expectedEpoch === generation.epoch, intent);
  c.execution = { route: collection + intent.id + (accessLevel ? '/execute' : '/retire'), body: { expectedVersion: intent.version, resumeOriginal: false } }; h.persist();
  c.execution.response = await h.api(h.admin, 'POST', c.execution.route, c.execution.body); h.persist();
  h.check('Original grant or retirement execution acknowledged', h.good(c.execution.response), c.execution.response);
  const completed = (await h.ok(h.admin, 'GET', query)).value;
  h.check('Independent coordinator confirms exact completed original access operation', same(completed, c.execution.response.data.value) && completed.id === intent.id && completed.status === 'completed' && completed.accountId === r.accountId && completed.installationId === r.installation.id && completed.deploymentId === r.installation.deploymentId && completed.accessLevel === accessLevel && completed.assignmentId > 0, completed);
  c.completed = completed; c.outcome = 'confirmed'; r.assignmentId = completed.assignmentId; r.active = !!accessLevel; h.persist();
}
async function retireAccess(h, r) {
  if (r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity)) throw new h.Blocked('Original direct grant actor changed; retain account and operation');
  await resumeRejectedRetirement(h, r);
  await reconcileRejectedRetirement(h, r);
  if (r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original direct grant unresolved; retain account and operation');
  if (r.active) await accessCommand(h, r, '', r.assignmentId);
  const bindings = await h.directory(h.admin, base + 'subject-role-bindings/?' + new URLSearchParams({ subjectId: r.accountId + '|=', subjectType: 'account|=' }));
  h.check('CAS confirms original direct installation source has no active member binding after formal retirement', !bindings.some(b => b.sourceType !== 'template' && b.status === 2 && (b.roleModule === '/applications/' + r.installation.deploymentId || b.applicationAccess?.some(a => a.applicationUuid === r.installation.deploymentId))), bindings);
  r.phase = 'deleted'; h.persist(); return { proof: 'Exact completed original Panel access retirement and independent CAS binding absence; durable operation history retained.' };
}
function originalRetirementMatches(r, c, value) {
  const before = c.response?.data?.value;
  const grant = r.commands.find(g => g.outcome === 'confirmed' && g.completed?.status === 'completed' && g.completed.accessLevel && g.completed.assignmentId === r.assignmentId);
  return !!before && before.status === 'prepared' && before.version === 1 &&
    !!grant && same(grant.completed.requestedBy, before.requestedBy) &&
    before.installationId === r.installation.id && before.deploymentId === r.installation.deploymentId && before.namespace === r.actorIdentity.namespace &&
    before.revisionDigest === r.installation.sourceDigest && before.accountId === r.accountId && before.assignmentId === r.assignmentId &&
    before.accessLevel === '' && before.submissionId === c.body.submissionId && before.expectedEpoch === c.body.expectedEpoch &&
    /^[a-f0-9]{64}$/.test(before.requestKey) && Number.isSafeInteger(value?.version) && value.version >= before.version &&
    Number.isSafeInteger(value.updateTime) && value.updateTime >= before.updateTime &&
    ['prepared', 'awaiting-original-result', 'confirmed', 'completed'].includes(value.status) &&
    same({ ...before, status: value.status, version: value.version, updateTime: value.updateTime }, value);
}
async function resumeRejectedRetirement(h, r) {
  const pending = r.commands.filter(c => c.outcome === 'unknown');
  if (pending.length !== 1) return;
  const c = pending[0], collection = '/panel/application/installations/' + r.installation.id + '/access-operations/';
  const before = c.response?.data?.value, response = c.execution?.response;
  if (!before || !h.good(c.response) || c.route !== collection.replace('access-operations/', 'access-retirements/') || c.body.accessLevel !== '' ||
      c.body.assignmentId !== r.assignmentId || c.body.accountId !== r.accountId ||
      c.execution?.route !== collection + before.id + '/retire' || !same(c.execution.body, { expectedVersion: 1, resumeOriginal: false }) ||
      response?.status !== 409 || response.data?.error?.code !== 19 || response.data.error.message !== 'application lifecycle changed before commit' || response.data.value != null) return;
  if (r.origin !== h.admin.origin || !same(r.actorIdentity, h.admin.identity)) throw new h.Blocked('Original retirement actor changed; no resume');
  const route = collection + '?submissionId=' + c.body.submissionId;
  let current = (await h.ok(h.admin, 'GET', route)).value;
  h.check('Explicit retirement recovery keeps every original intent/key/epoch and original member/installation', originalRetirementMatches(r, c, current), current);
  if (c.originalResume) {
    if (!h.good(c.originalResume.response) || !same(c.originalResume.response.data.value, current) || current.status !== 'completed')
      throw new h.Blocked('Original retirement recovery unresolved; no resume replay');
  } else if (current.status !== 'completed') {
    c.originalResume = { route: c.execution.route, body: { expectedVersion: current.version, resumeOriginal: true }, before: current, outcome: 'unknown' }; h.persist();
    c.originalResume.response = await h.api(h.admin, 'POST', c.originalResume.route, c.originalResume.body); h.persist();
    h.check('Existing owner explicitly resumes only the exact original retirement', h.good(c.originalResume.response), c.originalResume.response);
    current = (await h.ok(h.admin, 'GET', route)).value;
    h.check('Independent owner confirms completed original retirement after explicit resume', same(current, c.originalResume.response.data.value) && originalRetirementMatches(r, c, current) && current.status === 'completed');
  }
  c.completed = current; c.outcome = 'confirmed'; r.active = false;
  if (c.originalResume) c.originalResume.outcome = 'confirmed';
  h.persist();
}
async function reconcileRejectedRetirement(h, r) {
  const pending = r.commands.filter(c => c.outcome === 'unknown');
  if (pending.length !== 1) return;
  const c = pending[0], grant = r.commands.find(g => g.outcome === 'confirmed' && g.completed?.status === 'completed' && g.completed.accessLevel && g.completed.assignmentId === r.assignmentId);
  const collection = '/panel/application/installations/' + r.installation.id + '/';
  const fieldRefusal = !!c.body.reason?.trim() && c.response?.status === 400 && c.response.data?.error?.code === 4 && c.response.data.error.message === 'application access original submission is incomplete';
  // The owner emits this exact error only for an atomically NotApplied
  // lifecycle transaction. Other409s and transport failures remain unknown.
  const commitRefusal = c.body.reason === '' && c.response?.status === 409 && c.response.data?.error?.code === 19 && c.response.data.error.message === 'application lifecycle changed before commit';
  if (!grant || c.execution || c.route !== collection + 'access-retirements/' || c.body.accessLevel !== '' || c.body.assignmentId !== r.assignmentId || c.body.accountId !== r.accountId || !/^[a-f0-9]{32}$/.test(c.body.submissionId) || !fieldRefusal && !commitRefusal) return;
  let originalGrant;
  if (commitRefusal) {
    h.check('Original retirement conflict belongs to unchanged actor and completed exact original grant', r.origin === h.admin.origin && same(r.actorIdentity, h.admin.identity) &&
      grant.completed.namespace === 'panel' && grant.completed.accountId === r.accountId && grant.completed.installationId === r.installation.id &&
      grant.completed.deploymentId === r.installation.deploymentId && /^[a-f0-9]{32}$/.test(grant.completed.submissionId));
    originalGrant = (await h.ok(h.admin, 'GET', collection + 'access-operations/?submissionId=' + grant.completed.submissionId)).value;
    h.check('Independent original grant coordinator read preserves its full completed public receipt', same(originalGrant, grant.completed));
  }
  const original = await h.api(h.admin, 'GET', collection + 'access-operations/?submissionId=' + c.body.submissionId);
  const rows = await h.directory(h.admin, collection + 'assignments/'), matches = rows.filter(a => a.id === r.assignmentId);
  h.check('Complete original installation assignment directory contains exactly the original active assignment', matches.length === 1, rows);
  const assignment = matches[0];
  const generation = (await h.ok(h.admin, 'GET', collection + 'access-generation?accountId=' + r.accountId)).value;
  h.check('Rejected retirement has no original coordinator intent and preserves exact active assignment and generation',
    [200, 404].includes(original.status) && original.data?.error?.code === 2 && !original.data.value &&
    assignment.id === r.assignmentId && assignment.installationId === r.installation.id && assignment.subjectId === r.accountId && assignment.accessLevel === grant.completed.accessLevel && assignment.reason === grant.body.reason && same(assignment.assignedBy, grant.completed.requestedBy) &&
    generation.epoch === c.body.expectedEpoch && generation.accountId === r.accountId && generation.deploymentId === r.installation.deploymentId &&
    (!commitRefusal || generation.namespace === 'panel'), { original, assignment, generation });
  c.outcome = 'rejected-before-intent'; c.disposition = { proof: commitRefusal ?
    'Original exact HTTP409 owner NotApplied transaction; original submission absent, completed original grant unchanged, active assignment identity/scope and epoch preserved. Never resend original submission; any new retirement uses a new intent and current owner fences.' :
    'Original exact HTTP400 pre-I/O field rejection; original submission absent, assignment and epoch unchanged. New retirement must use a new valid empty-reason intent.', original, assignment, generation, ...(commitRefusal ? { originalGrant } : {}) }; h.persist();
}
async function union(h) {
  const f = await fixture(h), manager = await business.member(h, 'manager');
  const ordinary = (await h.directory(h.admin, base + 'role-templates/')).find(t => t.key === 'portal-basic-user' && t.systemManaged && t.status === 2);
  h.check('Existing ordinary functional profile is present', ordinary?.roleRefs?.length > 0);
  const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-union-group', name: '直接与组授权并集', subjectType: 'account', roleRefs: ordinary.roleRefs, status: 2,
    applicationAccess: [{ applicationUuid: f.installations[0].deploymentId, accessLevel: 'viewer' }] }, 'role-template');
  const m = await account(h, 'union-member'), context = await business.runtime(h, f, 0, manager), rows = [];
  const r = { kind: 'member-access-retirement', phase: 'created', accountId: m.value.id, installation: f.installations[0], commands: [], active: false,
    origin: h.admin.origin, actorIdentity: structuredClone(h.admin.identity) };
  h.state.resources.push(r); h.persist();
  let primary;
  try {
    const row = await business.create(h, context, 'union'); rows.push(row);
    await groupScope(h, m, group, true); await accessCommand(h, r, 'editor', 0);
    const verify = async writable => {
      const current = await business.runtime(h, f, 0, m.actor);
      h.check('Ordinary runtime reflects union of the remaining exact group and direct sources', current.ui.capabilities.get === true && current.ui.capabilities.create === writable && current.ui.capabilities.update === writable && current.ui.capabilities.delete === false, current.ui.capabilities);
      h.check('Original ordinary member still reads exact row while at least one source grants read', same(await business.record(h, m.actor, row), await business.record(h, manager, row)));
      await edit(h, m, row, writable);
    };
    await verify(true);
    await groupScope(h, m, group, false); await verify(true);
    await groupScope(h, m, group, true); await retireAccess(h, r); await verify(false);
    await groupScope(h, m, group, false);
    h.inaccessible(await business.record(h, m.actor, row), 'Removing the last independent source revokes the original member business read');
  } catch (error) { primary = error; throw error; }
  finally {
    try {
      if (r.phase !== 'deleted') {
        try { await retireAccess(h, r); }
        catch (error) { h.observe({ kind: 'original-direct-access-cleanup-open', accountId: r.accountId, message: error.message }); if (!primary) throw error; }
      }
    }
    finally { await business.finishCleanup(h, rows.reverse(), primary); }
  }
}
union.transport = 'owner-api';
async function matrixWrite(h, member, r, operation, allowed) {
  if (!['update', 'delete'].includes(operation) || r.phase !== 'created' || r.commands.some(c => c.outcome === 'unknown')) throw new h.Blocked('Original role-matrix row or command unresolved; no write replay');
  const manager = await business.member(h, 'manager'), before = await business.record(h, manager, r);
  h.check('Role matrix reads exact original owner row and current version before dispatch', h.good(before) && String(before.data.value.id) === r.recordId && String(before.data.value.version) === r.version);
  const body = business.request(r, operation, operation === 'update' ? [{ name: 'name', value: '独立写权限 ' + member.role }] : []);
  const route = '/apps/entity/value/write/' + operation + '/execute/?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId;
  const c = { body, actingIdentity: structuredClone(member.actor.identity), negativeActor: allowed ? undefined : structuredClone(member.actor.identity), outcome: 'unknown' };
  r.commands.push(c); h.persist();
  c.response = await h.api(member.actor, 'POST', route, body); h.persist();
  if (allowed) {
    h.check('Current exact ordinary data role receives its own original reliable write receipt', h.good(c.response) && business.receiptMatches(member.actor, body, c.response.data.value), c.response);
    const receipt = (await h.ok(member.actor, 'POST', route.replace('/execute/', '/receipt/'), body)).value;
    const after = await business.record(h, manager, r);
    const unchanged = operation === 'update' ? h.good(after) && after.data.value.name === body.fields[0].value && String(after.data.value.version) === receipt.version && same({ ...after.data.value, name: before.data.value.name, version: before.data.value.version }, before.data.value) : [200, 404].includes(after.status) && after.data?.error?.code === 2 && after.data.value == null;
    h.check('Independent authorized owner confirms only exact original update or terminal deletion and stable original receipt', same(receipt, c.response.data.value) && unchanged, { receipt, after });
    c.receipt = receipt; c.outcome = 'confirmed'; r.version = receipt.version; r.phase = operation === 'delete' ? 'delete-acknowledged' : 'created';
  } else {
    h.denied(c.response, 'Current independent role cannot perform an ungranted ' + operation);
    h.check('Rejected role-matrix write preserves complete original owner row', same(await business.record(h, manager, r), before));
    c.outcome = 'rejected-authority-and-unchanged';
  }
  h.persist();
}
async function independentDataRoles(h) {
  const f = await fixture(h), manager = await business.member(h, 'manager');
  const ordinary = (await h.directory(h.admin, base + 'role-templates/')).find(t => t.key === 'portal-basic-user' && t.systemManaged && t.status === 2 && t.subjectType === 'account');
  h.check('Independent data-role matrix uses existing ordinary functional roles', ordinary?.roleRefs?.length > 0);
  const contexts = [await business.runtime(h, f, 0, manager), await business.runtime(h, f, 1, manager)];
  const access = contexts.map((c, i) => ({ applicationUuid: c.identity.deploymentId, accessLevel: i ? 'viewer' : 'manager' }));
  const group = await h.create(base + 'role-templates/', { key: h.state.prefix + '-matrix-levels', name: '双实例不同数据级别', subjectType: 'account', status: 2, roleRefs: ordinary.roleRefs, applicationAccess: access }, 'role-template');
  const member = await account(h, 'data-role-matrix'), rows = [];
  let primary;
  try {
    await assign(h, member, group, access);
    const first = await business.create(h, contexts[0], 'matrix-manager'); rows.push(first);
    const second = await business.create(h, contexts[1], 'matrix-viewer'); rows.push(second);
    for (const row of [first, second]) h.check('Same original member reads both explicitly granted installation records', same(await business.record(h, member.actor, row), await business.record(h, manager, row)));
    await matrixWrite(h, member, first, 'update', true);
    await matrixWrite(h, member, second, 'update', false);
    await matrixWrite(h, member, second, 'delete', false);
    await matrixWrite(h, member, first, 'delete', true);
    const roles = await h.directory(h.admin, base + 'roles/');
    for (const permission of ['read', 'write', 'delete']) {
      const ref = { module: '/applications/' + contexts[0].identity.deploymentId, key: 'application-data-' + permission };
      h.check('Independent data role exists in the exact installed CAS catalogue', roles.filter(v => v.module === ref.module && v.key === ref.key && v.status === 2).length === 1, ref);
      const template = await h.create(base + 'role-templates/', { key: h.state.prefix + '-only-' + permission, name: '独立数据角色 ' + permission, subjectType: 'account', status: 2,
        roleRefs: [...ordinary.roleRefs, ref], applicationAccess: [] }, 'role-template');
      await assign(h, member, template, []);
      const row = await business.create(h, contexts[0], 'matrix-only-' + permission); rows.push(row);
      const read = await business.record(h, member.actor, row);
      if (permission === 'read') h.check('Only-read role reads exact original owner data', same(read, await business.record(h, manager, row)));
      else h.denied(read, 'Independent ' + permission + ' role does not implicitly grant read');
      h.denied(await business.record(h, member.actor, second), 'Exact installationA role does not retain previous installationB viewer scope');
      await matrixWrite(h, member, row, 'update', permission === 'write');
      await matrixWrite(h, member, row, 'delete', permission === 'delete');
      h.check('Independent role changes leave original other-installation record unchanged', same((await business.record(h, manager, second)).data.value, second.created));
    }
    // This template was created before the account and is retired after it.
    // Explicitly remove the later raw-role templates before reverse teardown.
    await assign(h, member, group, []);
  } catch (error) { primary = error; throw error; }
  finally { await business.finishCleanup(h, [...rows].reverse(), primary); }
  await h.partial('Same-account dual-installation levels and independent current read/write/delete commands verified. A third actual installation and explicit business-action denial under data-manager authority remain unverified; no empty action catalogue is used as permission proof.');
}
independentDataRoles.transport = 'owner-api';
async function reconcileMatrixWriteRefusal(h, r) {
  const pending = r.commands?.filter(c => c.outcome === 'unknown');
  if (r.kind !== 'business-record' || r.phase !== 'created' || r.actorRole !== 'manager' || r.version !== '1' || pending?.length !== 1 || r.commands.length !== 2) throw new h.Blocked('Matrix refusal recovery requires the original untouched created row and one pending update');
  const c = pending[0], created = r.commands[0], body = c.body;
  if (created === c || created.outcome !== 'confirmed' || created.body.operation !== 'create' || !same(created.body, r.createRequest) || body.operation !== 'update' || body.cancel || c.negativeActor || body.id !== r.recordId || body.expectedVersion !== r.version || !same(body.identity, r.identity) || body.entity !== r.entity || c.response?.status !== 200 || c.response.data?.error?.code !== 5 || c.response.data.error.message !== '读取安装页面需要应用实例运行权限' || c.response.data.value != null) throw new h.Blocked('Original matrix refusal lacks the exact pre-execution denial and immutable creation intent');
  const actor = await business.member(h, 'data-role-matrix'), manager = await business.member(h, r.actorRole);
  if (actor.origin !== r.origin || !same(actor.identity, c.actingIdentity) || manager.origin !== r.origin || !same(manager.identity, r.actorIdentity)) throw new h.Blocked('Original matrix caller or creator changed');
  const route = operation => '/apps/entity/value/write/' + operation + '/receipt/?application=' + encodeURIComponent(r.applicationKey) + '&deploymentId=' + r.identity.deploymentId;
  const original = await h.api(actor, 'POST', route('update'), business.receiptRequest(body));
  h.check('Original actual caller receipt query proves no completion without replaying its rejected update', [200, 404].includes(original.status) && original.data?.error?.code === 2 && original.data.error.message === '原业务写入尚无完成事实；禁止据此自动重发' && original.data.value == null, original);
  const receipt = (await h.ok(manager, 'POST', route('create'), business.receiptRequest(created.body))).value;
  const row = await business.record(h, manager, r);
  h.check('Independent original creator confirms exact durable creation receipt and complete untouched owner row', business.receiptMatches(manager, created.body, receipt) && same(receipt, created.receipt) && receipt.id === r.recordId && receipt.version === '1' && h.good(row) && same(row.data.value, r.created) && String(r.created.id) === r.recordId && String(r.created.version) === r.version, { receipt, row });
  c.disposition = { originalReceiptQuery: original, creationReceipt: receipt, ownerRow: row, proof: 'Exact original UI-authority refusal, original caller completion absence, original durable create receipt and complete unchanged owner row; no execute replay. Product failure retained.' };
  c.outcome = 'rejected-before-write-and-unchanged'; h.persist();
  return { operationId: body.operationId, recordId: r.recordId, proof: c.disposition.proof };
}
module.exports = { handlers: { 'F006-001': memberScopes, 'F006-002': independentDataRoles, 'F006-003': union }, account, assign, edit, reconcile, accessCommand, retireAccess, resumeRejectedRetirement, originalRetirementMatches, reconcileRejectedRetirement, matrixWrite, reconcileMatrixWriteRefusal };
