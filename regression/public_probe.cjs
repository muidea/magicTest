// Observe Chromium's raw first response while manual fetch prevents a second hop.
// Browser fetch exposes opaqueredirect as status 0; that value is never our verdict.
async function publicGet(actor, route) {
  if (typeof route !== 'string' || !route.startsWith('/') || route.startsWith('//')) throw Error('Direct public probe must be a same-origin GET');
  const origin = new URL(actor.origin).origin;
  const target = new URL(route, origin);
  if (target.origin !== origin || target.hash || new URL(actor.page.url()).origin !== origin) throw Error('Direct public probe must use the original same-origin page');
  let listener, timer;
  const first = new Promise((resolve, reject) => {
    listener = response => {
      const request = response.request();
      if (response.url() === target.href && request.method() === 'GET' && request.resourceType() === 'fetch') resolve(response);
    };
    actor.page.on('response', listener);
    timer = setTimeout(() => reject(Error('No first-hop response for public probe')), 30000);
  });
  try {
    const [response, visible] = await Promise.all([first, actor.page.evaluate(async url => {
      const r = await fetch(url, { redirect: 'manual', credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(30000) });
      const text = await r.text(); let data;
      try { data = JSON.parse(text); } catch { data = { text: text.slice(0, 1000) }; }
      return { status: r.status, type: r.type, data };
    }, target.href)]);
    const status = response.status();
    if (response.request().redirectedFrom() || (visible.type === 'opaqueredirect' ? status < 300 || status >= 400 : visible.status !== status)) throw Error('Public probe response cannot be bound to its first hop');
    return { status, location: await response.headerValue('location'), url: response.url(), data: visible.data };
  } finally {
    clearTimeout(timer);
    actor.page.off('response', listener);
  }
}
module.exports = { publicGet };
