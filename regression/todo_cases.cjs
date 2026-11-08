// Real CAS sources drive durable todos; no direct event or database injection.
const { createRegistrationFixture, setRegistrationPolicy, submitRegistration, reviewRegistration } = require('./registration_cases.cjs');
async function sourceTodos(h, actor, request, expectedStatus) {
  let matches = [];
  for (let attempt = 0; attempt < 10; attempt++) {
    matches = (await h.directory(actor, '/panel/todos/')).filter(t => t.source === 'magicCas' && t.categoryKey === 'registration-review' && t.sourceID === String(request.id) && t.namespace === actor.identity.namespace);
    if (matches.length === 1 && matches[0].status === expectedStatus) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  h.check('Independent scoped todo projection confirms one exact source in expected state', matches.length === 1 && matches[0].status === expectedStatus && matches[0].content.includes(request.account), { sourceRequestId: request.id, expectedStatus, matches });
  return matches[0];
}
async function lifecycle(h) {
  const f = await createRegistrationFixture(h, 'todos');
  await setRegistrationPolicy(h, f);
  const actor = await h.login(f.bootstrap.account, h.state.password, f.ns.name, h.state.password + 'T');
  for (const action of ['approve', 'reject']) {
    const account = h.state.prefix + '-todo-' + action;
    const request = await submitRegistration(h, f, { account, password: h.state.password, displayName: '待办真实来源', email: account + '@example.test', phone: '' });
    h.check('Original source owner acknowledges pending registration', request.status === 'pending');
    const todo = await sourceTodos(h, actor, request, 'pending');
    const pending = (await h.ok(h.admin, 'GET', f.reg + 'accounts/' + request.id)).value;
    h.check('Independent CAS read pairs original pending request and account', pending.id === request.id && pending.accountId === request.accountId && pending.status === 'pending');
    await actor.page.goto(actor.origin + '/panel/support/todos/', { waitUntil: 'networkidle' });
    const row = actor.page.locator('tr.ant-table-row').filter({ hasText: todo.content });
    await row.waitFor({ state: 'visible' });
    h.check('Real todo directory shows original source content, type and namespace', (await row.innerText()).includes('用户注册审核') && (await row.innerText()).includes(f.ns.name));
    await h.screenshot(actor, 'todo-' + action + '-pending');
    await row.getByRole('button', { name: '查看处理', exact: true }).click();
    await actor.page.waitForURL(url => url.pathname === '/panel/cas/access/' && url.searchParams.get('tab') === 'registration');
    h.check('Todo navigates within the original tenant to its source review screen', new URL(actor.page.url()).origin === actor.origin);
    await reviewRegistration(h, f, request, action, actor);
    const final = (await h.ok(actor, 'GET', f.reg + 'accounts/' + request.id)).value;
    h.check('Original source owner independently confirms exact review result', final.id === request.id && final.accountId === request.accountId && final.account === account && final.status === (action === 'approve' ? 'approved' : 'rejected'));
    if (action === 'approve') h.check('Approved source activates exact original account', (await h.ok(actor, 'GET', f.base + 'accounts/' + request.accountId)).value.status === 2);
    else await h.gone(f.base + 'accounts/', request.accountId);
    // Panel's public contract is pending-only, including when a caller supplies
    // another status. Prove original-source exit through this real projection;
    // do not invent access to Base's private completed-todo history.
    let residual = true;
    for (let attempt = 0; attempt < 10; attempt++) {
      residual = (await h.directory(actor, '/panel/todos/?status=pending')).some(t => t.sourceKey === todo.sourceKey && t.sourceID === String(request.id));
      if (!residual) break;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    h.check('Fresh public pending projection excludes exact terminal original source', !residual, { sourceRequestId: request.id, originalTodoId: todo.id, originalTodoIdentity: todo.identity,
      proof: 'CAS original terminal source and independent Panel pending absence; terminal todo storage history is not exposed by this API' });
    await actor.page.goto(actor.origin + '/panel/support/todos/', { waitUntil: 'networkidle' });
    h.check('Default pending UI no longer displays disposed original source', await actor.page.locator('tr.ant-table-row').filter({ hasText: todo.content }).count() === 0);
    await h.screenshot(actor, 'todo-' + action + '-closed');
  }
}
async function disappear(h, actor, request, todo) {
  let residual = true;
  for (let attempt = 0; attempt < 10; attempt++) {
    residual = (await h.directory(actor, '/panel/todos/')).some(t => t.sourceKey === todo.sourceKey && t.sourceID === String(request.id));
    if (!residual) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  h.check('Exact terminal source no longer appears in independent pending projection', !residual, { requestId: request.id, todoId: todo.id });
}
async function ownership(h) {
  const fixtures = [];
  for (const suffix of ['todoowna', 'todoownb']) {
    const f = await createRegistrationFixture(h, suffix);
    await setRegistrationPolicy(h, f);
    const actor = await h.login(f.bootstrap.account, h.state.password, f.ns.name, h.state.password + 'O');
    const account = h.state.prefix + '-' + suffix;
    const request = await submitRegistration(h, f, { account, password: h.state.password, displayName: '待办隔离来源', email: account + '@example.test', phone: '' });
    const todo = await sourceTodos(h, actor, request, 'pending');
    fixtures.push({ f, actor, request, todo });
  }
  const [a, b] = fixtures;
  const member = await h.create(a.f.base + 'accounts/', { account: h.state.prefix + '-todo-member', displayName: '同租户普通成员', password: h.state.password, status: 2, roleTemplateKeys: ['portal-user'] }, 'account');
  const ordinary = await h.login(member.account, h.state.password, a.f.ns.name, h.state.password + 'M');
  await h.ok(ordinary, 'GET', '/system/context/?surface=portal');
  for (const route of ['/panel/todos/', '/panel/todos/?id=' + a.todo.id, a.f.reg + 'accounts/' + a.request.id]) {
    const response = await h.api(ordinary, 'GET', route);
    h.denied(response, 'Authenticated ordinary member cannot list or guess original review source');
    h.check('Denied todo/source response exposes no original content', !JSON.stringify(response).includes(a.request.account) && !response.data?.value && !response.data?.values?.length);
  }
  for (const [own, foreign] of [[a, b], [b, a]]) {
    for (const query of ['', '?id=' + foreign.todo.id, '?namespace=' + foreign.f.ns.name + '&sourceID=' + foreign.request.id]) {
      const values = await h.directory(own.actor, '/panel/todos/' + query);
      h.check('Original tenant has no foreign todo even with guessed ID or target hints', values.every(t => t.namespace === own.f.ns.name && t.sourceID !== String(foreign.request.id) && t.identity !== foreign.todo.identity), { actor: own.actor.identity, query, values });
    }
    h.inaccessible(await h.api(own.actor, 'GET', own.f.reg + 'accounts/' + foreign.request.id), 'Foreign source ID cannot be read through own namespace detail');
    h.denied(await h.api(own.actor, 'GET', foreign.f.reg + 'accounts/' + foreign.request.id), 'Explicit foreign namespace review detail denied');
    await own.actor.page.goto(own.actor.origin + '/panel/support/todos/', { waitUntil: 'networkidle' });
    // The table request starts after the page's system-context read. Network
    // idle does not prove the source row has rendered; wait for that exact row.
    try {
      await own.actor.page.locator('tr.ant-table-row').filter({ hasText: own.todo.content }).waitFor({ state: 'visible', timeout: 15000 });
    } catch (error) {
      await h.screenshot(own.actor, 'todo-owner-unresolved-' + own.f.ns.name);
      h.observe({ kind: 'todo-ui-readiness', identity: own.actor.identity, path: new URL(own.actor.page.url()).pathname,
        visibleText: (await own.actor.page.locator('body').innerText()).slice(0, 5000) });
      throw error;
    }
    h.check('Fresh tenant without business installations reads own pending source and excludes peer', await own.actor.page.locator('tr.ant-table-row').filter({ hasText: own.todo.content }).count() === 1 && await own.actor.page.locator('tr.ant-table-row').filter({ hasText: foreign.todo.content }).count() === 0);
    await h.screenshot(own.actor, 'todo-owner-' + own.f.ns.name);
  }
  for (const { f, actor, request, todo } of fixtures) {
    const original = (await h.ok(actor, 'GET', f.reg + 'accounts/' + request.id)).value;
    h.check('Unauthorized reads preserve original pending source', original.id === request.id && original.accountId === request.accountId && original.status === 'pending');
    await reviewRegistration(h, f, request, 'reject', actor);
    await disappear(h, actor, request, todo);
  }
}
async function dashboard(h) {
  const f = await createRegistrationFixture(h, 'todoquick');
  await setRegistrationPolicy(h, f);
  const actor = await h.login(f.bootstrap.account, h.state.password, f.ns.name, h.state.password + 'Q');
  const account = h.state.prefix + '-quick-review';
  const request = await submitRegistration(h, f, { account, password: h.state.password, displayName: '概览快捷审核', email: account + '@example.test', phone: '' });
  const todo = await sourceTodos(h, actor, request, 'pending');
  const accounts = await h.directory(actor, f.base + 'accounts/');
  let profile, count;
  for (let attempt = 0; attempt < 10; attempt++) {
    profile = (await h.ok(actor, 'GET', '/panel/profile')).value;
    count = profile.summary?.find(t => t.name === '访问账号');
    if (count?.value === accounts.length) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  h.check('Management count matches exact current tenant account owner directory', count?.value === accounts.length && accounts.some(t => t.id === request.accountId), { summary: profile.summary, accountIds: accounts.map(t => t.id), namespace: f.ns.name });
  await actor.page.goto(actor.origin + '/panel/', { waitUntil: 'networkidle' });
  const card = actor.page.locator('.ant-card').filter({ has: actor.page.locator('.ant-card-head-title').getByText('待办审批', { exact: true }) });
  await card.getByText(todo.content, { exact: true }).waitFor({ state: 'visible' });
  h.check('Dashboard displays original namespace and independently confirmed account count', await actor.page.getByText(f.ns.name, { exact: true }).count() > 0 && await actor.page.locator('.ant-statistic').filter({ hasText: '访问账号' }).locator('.ant-statistic-content-value').innerText() === String(accounts.length));
  await h.screenshot(actor, 'dashboard-original-source');
  const quick = actor.page.locator('.ant-card').filter({ has: actor.page.locator('.ant-card-head-title').getByText('高频操作', { exact: true }) });
  await quick.getByRole('button', { name: /(?:^|\s)处理待办$/ }).click();
  await actor.page.waitForURL(url => url.pathname.replace(/\/$/, '') === '/panel/support/todos');
  const row = actor.page.locator('tr.ant-table-row').filter({ hasText: todo.content });
  await row.getByRole('button', { name: '查看处理', exact: true }).click();
  await actor.page.waitForURL(url => url.origin === actor.origin && url.pathname === '/panel/cas/access/' && url.searchParams.get('tab') === 'registration');
  await reviewRegistration(h, f, request, 'reject', actor);
  const final = (await h.ok(actor, 'GET', f.reg + 'accounts/' + request.id)).value;
  h.check('Source owner confirms exact original quick-action review result', final.id === request.id && final.accountId === request.accountId && final.status === 'rejected');
  await h.gone(f.base + 'accounts/', request.accountId);
  await disappear(h, actor, request, todo);
  await actor.page.goto(actor.origin + '/panel/', { waitUntil: 'networkidle' });
  await card.getByText('暂无待办事项', { exact: true }).waitFor({ state: 'visible' });
  h.check('Independent fresh dashboard drops processed original pending source', await card.getByText(todo.content, { exact: true }).count() === 0);
  await h.screenshot(actor, 'dashboard-original-source-closed');
}
module.exports = { handlers: { 'F052-001': lifecycle, 'F052-002': ownership, 'F066-001': dashboard } };
