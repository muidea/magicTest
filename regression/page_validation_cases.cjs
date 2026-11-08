// Exercise deployed public owner checks and conditional refusals. Registration
// remains partial until publication/import/installation boundaries are exercised.
const crypto = require('node:crypto');
const { isDeepStrictEqual: same } = require('node:util');
const { authoring: a } = require('./authoring_cases.cjs');
const { authorFixture: author } = require('./page_author_cases.cjs');
const { ownerRequest } = require('./owner_transport.cjs');
const digest = bytes => 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
const route = (app, member) => '/panel/application/definitions/' + app.id + '/' + member;
// Large image content is retained in the original private command journal;
// public evidence records exact decoded bytes and base64 representation hashes.
function compact(value, key = '') {
  if (key === 'files' && value && typeof value === 'object' && !Array.isArray(value)) return Object.fromEntries(Object.entries(value).map(([path, encoded]) => [path,
    typeof encoded === 'string' ? { representation: 'base64; original bytes in private command journal', encodedBytes: Buffer.byteLength(encoded), encodedDigest: digest(Buffer.from(encoded)), bytes: Buffer.from(encoded, 'base64').length, digest: digest(Buffer.from(encoded, 'base64')) } : encoded]));
  if (Array.isArray(value)) return value.map(v => compact(v));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, compact(v, k)]));
  return value;
}
function transport(h) {
  const own = Object.create(h);
  own.api = (actor, method, path, body) => ownerRequest(actor, method, path, body, event => h.observe(compact(event)));
  own.ok = async (...args) => { const r = await own.api(...args); h.check('Public page owner request succeeds: ' + args[1] + ' ' + args[2], h.good(r), { status: r.status, error: r.data?.error }); return r.data; };
  return own;
}
const rejected = r => [200, 400, 422].includes(r?.status) && r.data?.error?.code === 4 && r.data.value == null;
async function unchanged(h, app, before) {
  const current = { pages: await author.read(h, app, 'pages'), members: await author.read(h, app, 'package-members'), model: await a.draft(h, app) };
  return same(current, before);
}
async function rejectSave(h, app, member, before, content, diagnostic, label) {
  const path = route(app, member), payload = { expectedDefinitionVersion: before[member === 'pages' ? 'pages' : 'members'].definitionVersion, content };
  const intent = a.journalSave(h, app, path, payload); intent.method = 'PUT';
  intent.response = await h.api(h.admin, 'PUT', path, payload); h.persist();
  const preserved = await unchanged(h, app, before);
  // A known owner refusal plus independent unchanged facts can dispose this
  // exact intent even when the target diagnostic assertion subsequently fails.
  if (rejected(intent.response) && preserved) { intent.confirmed = true; h.persist(); }
  h.check(label + ' reaches exact owner validation rather than authentication, conflict or transport failure', rejected(intent.response) && diagnostic.test(intent.response.data.error.message), compact(intent.response));
  h.check(label + ' preserves complete original pages, model, image bytes and definition version', preserved);
}
async function rejectPage(h, app, before, content, diagnostic, label) {
  const response = await h.api(h.admin, 'POST', route(app, 'pages/check'), { expectedDefinitionVersion: before.pages.definitionVersion, content });
  h.check(label + ' read-only check reaches exact validation', rejected(response) && diagnostic.test(response.data.error.message), response);
  h.check(label + ' read-only check preserves all original owner facts', await unchanged(h, app, before));
  await rejectSave(h, app, 'pages', before, content, diagnostic, label);
}
function structures(original) {
  const change = (label, diagnostic, apply) => { const content = structuredClone(original); apply(content); return { label, diagnostic, content }; };
  return [
    change('Duplicate page route', /home|other.*路由|路由冲突/, c => { const p = structuredClone(c.pages[0]); p.key = 'other'; p.navigation = false; c.pages.push(p); }),
    change('Missing component source', /records.*(?:存在的数据源|数据源.*不存在)/, c => { c.pages[0].components[1].dataSources = ['absentSource']; }),
    change('Missing model field', /absentField/, c => { c.dataSources[0].fields.push('absentField'); c.pages[0].components[1].properties.columns.push('absentField'); }),
    change('Unsupported component type', /intro.*(?:类型尚不支持|arbitrary-html)/, c => { c.pages[0].components[0].type = 'arbitrary-html'; }),
    change('Unsupported component property', /(?:intro.*properties|html)/, c => { c.pages[0].components[0].properties.html = '<script>invalid</script>'; }),
    change('Missing navigation page', /(?:导航页面不存在.*absentPage|absentPage)/, c => { c.navigation = ['absentPage']; }),
    change('Duplicate component identity', /home.*组件.*重复/, c => { c.pages[0].components.push(structuredClone(c.pages[0].components[0])); })
  ];
}
function appearances(original) {
  const change = (label, diagnostic, apply) => { const content = structuredClone(original); apply(content.pages[0]); return { label, diagnostic, content }; };
  return [
    change('Arbitrary CSS', /css|未知字段|unknown field/i, p => { p.appearance = { css: 'position:fixed' }; }),
    change('Expression property', /expression|未知字段|unknown field/i, p => { p.components[0].properties.expression = 'fetch("https://invalid.invalid")'; }),
    change('External image URL', /url|未知字段|unknown field/i, p => { p.appearance = { background: { image: { mode: 'asset', assetKey: 'outside', url: 'https://invalid.invalid/image.png' } } }; }),
    change('Invalid color', /背景颜色无效/, p => { p.appearance = { background: { color: 'url(https://invalid.invalid)' } }; }),
    ...[-1, 13, 1.5].map(width => change('Invalid border width ' + width, /边框|borderWidth|integer|int/i, p => { p.presentationDefaults = { borderWidth: width }; })),
    change('Dangling image identity', /home.*appearance.background.image.assetKey.*absentImage/, p => { p.appearance = { background: { image: { mode: 'asset', assetKey: 'absentImage' } } }; })
  ];
}
async function baseline(h, app) { return { pages: await author.read(h, app, 'pages'), members: await author.read(h, app, 'package-members'), model: await a.draft(h, app) }; }
async function structure(h) {
  h = transport(h);
  const { app } = await author.fixture(h, 'pagereject'), before = await baseline(h, app);
  const positive = await h.ok(h.admin, 'POST', route(app, 'pages/check'), { expectedDefinitionVersion: before.pages.definitionVersion, content: before.pages.content });
  h.check('Unchanged legitimate page reaches the deployed capability report', typeof positive.value?.ready === 'boolean', positive);
  for (const candidate of structures(before.pages.content)) await rejectPage(h, app, before, candidate.content, candidate.diagnostic, candidate.label);
  await h.partial('页面结构check/save的7组拒绝与原内容保持已验证；非法循环及正式发布、包导入、安装、运行门禁仍缺配套夹具，未计整例通过');
}
// PNG metadata padding is a valid tEXt chunk, not a corrupt or truncated image.
function crc32(bytes) { let crc = 0xffffffff; for (const b of bytes) { crc ^= b; for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1)); } return (crc ^ 0xffffffff) >>> 0; }
function sizedPNG(png, size) {
  if (!Buffer.isBuffer(png) || !png.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) || png.subarray(-8, -4).toString() !== 'IEND' || size < png.length + 20) throw Error('A complete original PNG and finite positive comment budget are required');
  const data = Buffer.alloc(size - png.length - 12, 0x62); Buffer.from('Comment\0').copy(data);
  const chunk = Buffer.alloc(data.length + 12); chunk.writeUInt32BE(data.length); chunk.write('tEXt', 4); data.copy(chunk, 8); chunk.writeUInt32BE(crc32(chunk.subarray(4, -4)), chunk.length - 4);
  return Buffer.concat([png.subarray(0, -12), chunk, png.subarray(-12)]);
}
function imageContent(original, png, key = 'candidate', mime = 'image/png', extension = 'png') {
  const content = structuredClone(original), path = 'assets/' + key + '.' + extension;
  content.assets ||= { schemaVersion: 'magic.application-assets/v1', files: [] };
  content.assets.files.push({ key, path, purpose: 'page-image', mime, size: png.length, digest: digest(png) });
  content.files[path] = png.toString('base64'); return content;
}
function budgetContent(original, png, version, bytes) {
  if (!Number.isSafeInteger(bytes) || bytes < 1024 || bytes > 8 * 1024 * 1024 + 1) throw Error('Finite public 8 MiB envelope boundary required');
  for (let pad = 0; pad < 4; pad++) {
    const key = 'budget' + 'x'.repeat(pad), sample = imageContent(original, png, key);
    // Size digits also contribute to the actual UTF-8 JSON envelope.
    const asset = sample.assets.files.at(-1), file = asset.path;
    for (let size = Math.floor(bytes * 3 / 4) - 4096; size < Math.floor(bytes * 3 / 4); size++) {
      asset.size = size; sample.files[file] = '';
      const overhead = Buffer.byteLength(JSON.stringify({ expectedDefinitionVersion: version, content: sample }));
      if (overhead + 4 * Math.ceil(size / 3) !== bytes) continue;
      const payload = sizedPNG(png, size), content = imageContent(original, payload, key);
      if (Buffer.byteLength(JSON.stringify({ expectedDefinitionVersion: version, content })) !== bytes) throw Error('Original PNG envelope size changed');
      return { content, payload };
    }
  }
  throw Error('Could not construct the exact original UTF-8 envelope budget');
}
async function appearance(h) {
  h = transport(h);
  const { app } = await author.fixture(h, 'appearancereject'); let before = await baseline(h, app);
  for (const width of [0, 12]) {
    const content = structuredClone(before.pages.content); content.pages[0].presentationDefaults = { borderWidth: width };
    await author.save(h, app, 'pages', before.pages, content); before = await baseline(h, app);
  }
  for (const candidate of appearances(before.pages.content)) await rejectPage(h, app, before, candidate.content, candidate.diagnostic, candidate.label);
  const png = await h.admin.page.screenshot({ clip: { x: 0, y: 0, width: 2, height: 2 }, animations: 'disabled' });
  const types = [ ['svg', 'image/svg+xml', Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>')],
    ['gif', 'image/gif', Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', 'base64')],
    ['webp', 'image/webp', Buffer.from('UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA', 'base64')] ];
  for (const [extension, mime, bytes] of [...types, ['png', 'image/png', types[1][2]]]) await rejectSave(h, app, 'package-members', before, imageContent(before.members.content, bytes, 'candidate', mime, extension), /资源真实类型或像素限额无效.*assets\/candidate/, 'Reject actual ' + mime + ' bytes / ' + extension);
  for (const bytes of [8 * 1024 * 1024 - 1, 8 * 1024 * 1024, 8 * 1024 * 1024 + 1]) {
    const sample = budgetContent(before.members.content, png, before.members.definitionVersion, bytes);
    h.check('Generated budget sample is a real decodable PNG', await h.admin.page.evaluate(encoded => new Promise(resolve => { const image = new Image(); image.onload = () => resolve(image.naturalWidth === 2 && image.naturalHeight === 2); image.onerror = () => resolve(false); image.src = 'data:image/png;base64,' + encoded; }), sample.payload.toString('base64')));
    h.observe({ kind: 'page-image-envelope-boundary', bytes, imageBytes: sample.payload.length, digest: digest(sample.payload), ownerLimit: 8 * 1024 * 1024, scope: 'public UTF-8 JSON request, includes base64 expansion; not proof of accepting 8 MiB raw image through this endpoint' });
    if (bytes > 8 * 1024 * 1024) await rejectSave(h, app, 'package-members', before, sample.content, /定义 JSON 为空或超过大小限制/, 'Above public definition request budget');
    else {
      await author.save(h, app, 'package-members', before.members, sample.content);
      const current = await baseline(h, app);
      await author.save(h, app, 'package-members', current.members, before.members.content); // Formal release of this exact unreferenced image.
      before = await baseline(h, app);
    }
  }
  await h.partial('外观check/save的8组拒绝、0/12合法边框、SVG/GIF/WebP及伪PNG拒绝、公开JSON 8MiB边界−1/边界/边界+1已验证；发布/导入/安装与原包字节保持仍待配套夹具，未计整例通过');
}
structure.transport = appearance.transport = 'owner-api';
module.exports = { handlers: { 'F067-003': structure, 'F068-002': appearance }, compact, rejected, rejectSave, sizedPNG, budgetContent };
