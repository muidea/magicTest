// Feedback facts belong to Panel; attachment bytes remain owned by File.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { feedbackAttachment } = require('./owner_transport.cjs');
const handlers = {}, portal = '/portal/feedbacks/', panel = '/panel/support/feedbacks/';
const messages = area => area === 'portal' ? '/portal/feedback/messages/' : '/panel/support/feedback/messages/';
const hash = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
const validID = id => Number.isSafeInteger(id) && id > 0;
const absent = r => [200, 404].includes(r.status) && r.data?.error?.code === 2 && r.data.value == null;
function attachmentDenied(h, result) {
  if (result.status === 404 && result.data?.text === 'feedback attachment is unavailable\n') h.check('Exact existing private attachment is concealed by its owner download handler', true, result);
  else h.inaccessible(result, 'Private attachment enforces the same ticket boundary');
}
function original(h, actor, expected) {
  if (!actor || actor.origin !== expected.origin || !same(actor.identity, expected.identity)) throw new h.Blocked('Feedback requires the exact original actor and tenant origin');
}
function intent(h, r, actor, method, route, body, kind) {
  const command = { kind, actor: { identity: structuredClone(actor.identity), origin: actor.origin }, method, route, body: structuredClone(body), outcome: 'unknown' };
  r.commands.push(command); h.persist(); return command;
}
function ticketMatches(value, r) {
  return value?.id === r.id && value.title === r.intended.title && value.submitter?.id === r.submitterID && value.submitter.account === r.creator.identity.account;
}
async function ticket(h, suffix) {
  const creator = h.user, manager = h.tenantAdmin;
  if (creator.identity.namespace !== manager.identity.namespace || creator.origin !== manager.origin) throw new h.Blocked('Feedback manager must belong to the exact creator tenant');
  const r = { kind: 'feedback-ticket', phase: 'intent', actorIdentity: structuredClone(creator.identity),
    creator: { identity: structuredClone(creator.identity), origin: creator.origin, actorName: 'user' }, manager: { identity: structuredClone(manager.identity), origin: manager.origin, actorName: 'tenantAdmin' },
    intended: { type: 'feedback', title: h.state.prefix + '-feedback-' + suffix + '-' + crypto.randomBytes(4).toString('hex'), content: '原反馈内容：中文与Unicode Δ', privacy: 'PRIVATE', attachments: [] }, commands: [] };
  h.state.resources.push(r); h.persist();
  r.creation = intent(h, r, creator, 'POST', portal, r.intended, 'create');
  const result = await h.api(creator, 'POST', portal, r.intended);
  r.creation.response = result;
  if (h.good(result) && validID(result.data.value?.id)) { r.id = result.data.value.id; r.submitterID = result.data.value.submitter?.id; r.phase = 'created'; }
  h.persist();
  h.check('Portal acknowledges exact original private feedback creation', h.good(result) && validID(r.id) && validID(r.submitterID) && ticketMatches(result.data.value, r) && result.data.value.privacy === 'PRIVATE', result);
  original(h, creator, r.creator); original(h, manager, r.manager);
  const owner = (await h.ok(manager, 'GET', panel + r.id)).value;
  h.check('Independent manager owner confirms original creator and namespace', ticketMatches(owner, r) && owner.namespace === creator.identity.namespace && owner.content === r.intended.content && owner.status === 'WAITING' && owner.privacy === 'PRIVATE', owner);
  r.creation.outcome = 'confirmed'; h.persist(); return r;
}
async function upload(h, r) {
  const actor = h[r.creator.actorName]; original(h, actor, r.creator);
  const bytes = Buffer.concat([Buffer.from('原始附件\0\r\nUnicode Δ ' + h.state.prefix), Buffer.from([0, 255, 128, 10])]);
  const file = { name: 'feedback-proof.bin', bytes }, route = portal + r.id + '/attachments/';
  const c = intent(h, r, actor, 'POST', route, { name: file.name, size: bytes.length, digest: hash(bytes) }, 'upload');
  const result = await feedbackAttachment(actor, 'POST', route, file, h.observe);
  c.response = result; h.persist();
  const a = result.data?.value;
  h.check('Attachment receipt matches original uploaded bytes', h.good(result) && /^bound_[A-Za-z0-9_-]{32,64}$/.test(a?.fileRef) && a.name === file.name && a.size === bytes.length && a.digest === hash(bytes), result);
  const owner = (await h.ok(h[r.manager.actorName], 'GET', panel + r.id)).value;
  h.check('Independent ticket owner contains exact immutable attachment metadata', ticketMatches(owner, r) && owner.attachments?.length === 1 && same(JSON.parse(owner.attachments[0]), a), owner);
  c.outcome = 'confirmed'; r.attachment = a; h.persist();
  for (const [reader, base] of [[actor, portal], [h[r.manager.actorName], panel]]) {
    const read = await feedbackAttachment(reader, 'GET', base + r.id + '/attachments/' + a.fileRef, undefined, h.observe);
    h.check('Original creator and authorized manager independently download exact attachment bytes', read.status === 200 && Buffer.isBuffer(read.data.bytes) && read.data.bytes.equals(bytes), { status: read.status, size: read.data.bytes?.length, expectedDigest: hash(bytes) });
  }
  return a;
}
async function message(h, r, actor, area, content) {
  const body = { requestId: crypto.randomBytes(16).toString('hex'), feedback: { id: r.id }, pid: 0, content, attachments: [] }, route = messages(area);
  const c = intent(h, r, actor, 'POST', route, body, 'message');
  const result = await h.api(actor, 'POST', route, body); c.response = result; h.persist();
  h.check('Original message receives exact ticket/actor/content acknowledgement', h.good(result) && validID(result.data.value?.id) && result.data.value.feedback?.id === r.id && result.data.value.submitter?.account === actor.identity.account && result.data.value.content === content, result);
  const resolved = await h.ok(actor, 'POST', route, { ...body, resolveOnly: true });
  h.check('Formal original request receipt resolves exactly the acknowledged message', same(resolved.value, result.data.value), resolved);
  c.outcome = 'confirmed'; c.messageID = result.data.value.id; h.persist(); return result.data.value;
}
async function cleanup(h, r) {
  const creator = h[r.creator?.actorName], manager = h[r.manager?.actorName];
  original(h, creator, r.creator); original(h, manager, r.manager);
  if (!validID(r.id) || r.creation?.outcome !== 'confirmed' || r.commands?.some(c => c.outcome !== 'confirmed')) throw new h.Blocked('Unresolved original feedback operation; retain exact ticket without command replay');
  const current = await h.api(manager, 'GET', panel + r.id);
  if (!absent(current)) {
    h.check('Feedback cleanup confirms original ticket and creator in original namespace', h.good(current) && ticketMatches(current.data.value, r) && current.data.value.namespace === r.creator.identity.namespace, current);
    if (r.deletion) throw new h.Blocked('Original feedback DELETE remains unresolved; do not replay');
    r.deletion = { outcome: 'unknown' }; h.persist();
    const deleted = await h.api(manager, 'DELETE', panel + r.id); r.deletion.response = deleted; h.persist();
    h.check('Formal manager aggregate delete acknowledges exact original ticket', h.good(deleted) && ticketMatches(deleted.data.value, r), deleted);
    r.deletion.outcome = 'acknowledged'; h.persist();
  } else if (!r.deletion || r.deletion.outcome !== 'acknowledged') throw new h.Blocked('Feedback disappeared without original delete acknowledgement');
  for (const [actor, base] of [[creator, portal], [manager, panel]]) h.check('Independent original ticket read confirms absence', absent(await h.api(actor, 'GET', base + r.id)));
  for (const c of r.commands.filter(c => c.kind === 'message')) h.check('Independent original message owner confirms exact original message absence', absent(await h.api(manager, 'GET', '/panel/support/feedback/messages/' + c.messageID)));
  r.phase = 'deleted'; h.persist();
  return { proof: 'Original creator and tenant manager, acknowledged aggregate DELETE and independent exact ticket/message absence. File cleanup is covered by the owner aggregate acknowledgement; no independent File-byte absence claim.' };
}
async function postDeleteUpload(h, r, exchange = feedbackAttachment) {
  const actor = h[r.creator?.actorName], manager = h[r.manager?.actorName];
  original(h, actor, r.creator); original(h, manager, r.manager);
  if (r.phase !== 'deleted' || r.creation?.outcome !== 'confirmed' || r.deletion?.outcome !== 'acknowledged' ||
      !ticketMatches(r.deletion.response?.data?.value, r) || !h.good(r.deletion.response) ||
      r.commands?.some(c => c.outcome !== 'confirmed' || c.kind === 'post-delete-upload'))
    throw new h.Blocked('Post-delete probe requires exact original acknowledged deletion; no upload replay');
  for (const [reader, base] of [[actor, portal], [manager, panel]]) {
    if (!absent(await h.api(reader, 'GET', base + r.id))) throw new h.Blocked('Original deleted ticket absence not confirmed; no post-delete upload');
  }
  const bytes = Buffer.from('post-delete-' + h.state.prefix), file = { name: 'post-delete.bin', bytes };
  // Keep this resource open until the negative command is independently
  // confirmed. A lost response cannot disappear behind a prior deleted phase.
  r.phase = 'created';
  const c = intent(h, r, actor, 'POST', portal + r.id + '/attachments/',
    { name: file.name, size: bytes.length, digest: hash(bytes) }, 'post-delete-upload');
  c.response = await exchange(actor, 'POST', c.route, file, h.observe); h.persist();
  h.check('Fresh upload to exact original deleted ticket reaches owner NotFound without an attachment receipt', absent(c.response), c.response);
  for (const [reader, base] of [[actor, portal], [manager, panel]])
    h.check('Rejected post-delete upload cannot recreate original ticket', absent(await h.api(reader, 'GET', base + r.id)));
  c.outcome = 'confirmed'; h.persist();
  await cleanup(h, r);
}
handlers['F054-004'] = async h => {
  const target = await ticket(h, 'delete-target'), peer = await ticket(h, 'delete-peer');
  await upload(h, target); await upload(h, peer);
  h.check('Byte-identical attachments have independent exact ticket consumer bindings',
    target.attachment.digest === peer.attachment.digest && target.attachment.size === peer.attachment.size && target.attachment.fileRef !== peer.attachment.fileRef);
  await message(h, target, h.user, 'portal', '删除目标消息：' + h.state.prefix);
  await message(h, peer, h.user, 'portal', '保持对照消息：' + h.state.prefix);
  const before = (await h.ok(h.tenantAdmin, 'GET', panel + peer.id)).value;
  const peerMessages = await h.directory(h.tenantAdmin, messages('panel') + '?feedbackId=' + peer.id);
  const bytes = await feedbackAttachment(h.user, 'GET', portal + peer.id + '/attachments/' + peer.attachment.fileRef, undefined, h.observe);
  h.check('Peer attachment has real readable bytes before target deletion', bytes.status === 200 && Buffer.isBuffer(bytes.data.bytes));
  await cleanup(h, target);
  for (const [actor, base] of [[h.user, portal], [h.tenantAdmin, panel]]) {
    const download = await feedbackAttachment(actor, 'GET', base + target.id + '/attachments/' + target.attachment.fileRef, undefined, h.observe);
    h.check('Exact original deleted ticket attachment is unavailable through both owner download surfaces',
      download.status === 404 && download.data?.text === 'feedback attachment is unavailable\n', download);
    h.check('Complete scoped feedback directory no longer exposes original deleted ticket', !(await h.directory(actor, base)).some(v => v.id === target.id));
  }
  await postDeleteUpload(h, target);
  h.check('Target deletion and rejected upload preserve entire independent peer ticket and ordered messages',
    same((await h.ok(h.tenantAdmin, 'GET', panel + peer.id)).value, before) &&
    same(await h.directory(h.tenantAdmin, messages('panel') + '?feedbackId=' + peer.id), peerMessages));
  for (const [actor, base] of [[h.user, portal], [h.tenantAdmin, panel]]) {
    const download = await feedbackAttachment(actor, 'GET', base + peer.id + '/attachments/' + peer.attachment.fileRef, undefined, h.observe);
    h.check('Deleting another consumer of identical content preserves peer exact original downloadable bytes',
      download.status === 200 && Buffer.isBuffer(download.data.bytes) && download.data.bytes.equals(bytes.data.bytes));
  }
  await cleanup(h, peer);
  await h.partial('Formal ticket/message deletion, both owner download refusals, rejected fresh post-delete upload and byte-identical independent peer consumer preservation verified. Single-reference sharing and independent File retirement proof remain unverified; interrupted File cleanup and a previously dispatched upload arriving after deletion are separate special conditions.');
};
handlers['F054-001'] = async h => {
  const r = await ticket(h, 'exchange'); await upload(h, r);
  const first = await message(h, r, h.user, 'portal', '提交者补充：' + h.state.prefix);
  const second = await message(h, r, h.tenantAdmin, 'panel', '管理方回复：' + h.state.prefix);
  const c = intent(h, r, h.tenantAdmin, 'PUT', panel + r.id, { status: 'PROCESSING' }, 'status');
  const response = await h.api(h.tenantAdmin, 'PUT', panel + r.id, c.body); c.response = response; h.persist();
  h.check('Manager formally acknowledges feedback processing status', h.good(response) && ticketMatches(response.data.value, r) && response.data.value.status === 'PROCESSING', response);
  for (const [actor, area, base] of [[h.user, 'portal', portal], [h.tenantAdmin, 'panel', panel]]) {
    const current = (await h.ok(actor, 'GET', base + r.id)).value;
    h.check('Both original parties observe identical status and attachment', ticketMatches(current, r) && current.status === 'PROCESSING' && same(current.attachments.map(JSON.parse), [r.attachment]), current);
    const rows = await h.directory(actor, messages(area) + '?feedbackId=' + r.id);
    h.check('Both complete message directories preserve exact identities, content and sequence', rows.length === 2 && rows[0].id === first.id && rows[1].id === second.id && rows[0].content === first.content && rows[1].content === second.content && rows[0].createTime <= rows[1].createTime, rows);
  }
  c.outcome = 'confirmed'; h.persist();
  for (const [actor, pagePath] of [[h.user, '/portal/feedback/'], [h.tenantAdmin, '/panel/support/feedback/message']]) {
    await actor.page.goto(actor.origin + pagePath + '?id=' + r.id, { waitUntil: 'networkidle' });
    await actor.page.getByText(first.content, { exact: true }).waitFor({ state: 'visible' });
    await actor.page.getByText(second.content, { exact: true }).waitFor({ state: 'visible' });
    const items = await actor.page.locator('.ant-list-item').allTextContents();
    const firstIndex = items.findIndex(text => text.includes(first.content)), secondIndex = items.findIndex(text => text.includes(second.content));
    h.check('Both real detail pages render original message order and attachment', firstIndex >= 0 && secondIndex > firstIndex && await actor.page.getByRole('button', { name: r.attachment.name, exact: true }).isVisible(), { firstIndex, secondIndex });
    await h.screenshot(actor, 'feedback-exchange-' + actor.identity.account);
  }
};
handlers['F054-002'] = async h => {
  const r = await ticket(h, 'private'); await upload(h, r);
  const privateMessage = await message(h, r, h.user, 'portal', '私有消息非空对照：' + h.state.prefix);
  const ns = h.need('tenantA').name;
  const account = await h.create('/cas/namespaces/' + ns + '/accounts/', { account: h.state.prefix + '-feedback-peer-' + crypto.randomBytes(4).toString('hex'), displayName: '工单同租户对照', password: h.state.password, status: 2, roleTemplateKeys: ['portal-user'] }, 'account');
  const peer = await h.login(account.account, h.state.password, ns, h.state.password + 'P');
  for (const actor of [peer, h.otherTenantAdmin]) {
    const positive = await h.api(actor, 'GET', '/api/v1/web/session/'); h.check('Negative actor has its own valid account/tenant session', h.good(positive) && positive.data.value?.account?.account === actor.identity.account && positive.data.value.homeNamespace === actor.identity.namespace, positive);
    for (const base of [portal, panel]) {
      h.inaccessible(await h.api(actor, 'GET', base + r.id), 'Other account/tenant cannot read private ticket');
      const download = await feedbackAttachment(actor, 'GET', base + r.id + '/attachments/' + r.attachment.fileRef, undefined, h.observe);
      attachmentDenied(h, download);
    }
    for (const area of ['portal', 'panel']) {
      const listRoute = messages(area) + '?feedbackId=' + r.id;
      const list = await h.api(actor, 'GET', listRoute);
      if (h.good(list)) h.check('Authorized foreign directory is scoped empty and cannot expose original private replies', (await h.directory(actor, listRoute)).length === 0);
      else h.inaccessible(list, 'Other account/tenant cannot list private replies');
      const body = { requestId: crypto.randomBytes(16).toString('hex'), feedback: { id: r.id }, pid: 0, content: '不得提交的越权回复', attachments: [] };
      const c = intent(h, r, actor, 'POST', messages(area), body, 'negative-message');
      const result = await h.api(actor, 'POST', messages(area), body); c.response = result; h.persist();
      h.inaccessible(result, 'Other account/tenant cannot reply to private ticket');
      const rows = await h.directory(h.tenantAdmin, messages('panel') + '?feedbackId=' + r.id);
      h.check('Independent message owner preserves only original nonempty private message after rejected reply', rows.length === 1 && rows[0].id === privateMessage.id && rows[0].content === privateMessage.content, rows);
      c.outcome = 'confirmed'; h.persist();
    }
  }
  const owner = (await h.ok(h.tenantAdmin, 'GET', panel + r.id)).value;
  h.check('Unauthorized probes leave original private ticket unchanged', ticketMatches(owner, r) && owner.status === 'WAITING' && owner.privacy === 'PRIVATE' && same(owner.attachments.map(JSON.parse), [r.attachment]));
};
handlers['F050-003'] = handlers['F054-002'];
for (const [id, handler] of Object.entries(handlers)) { handler.actors = ['F054-001', 'F054-004'].includes(id) ? ['user', 'tenantAdmin'] : ['user', 'tenantAdmin', 'otherTenantAdmin']; handler.transport = 'owner-api'; }
module.exports = { handlers, cleanup, ticket, upload, attachmentDenied, postDeleteUpload };
