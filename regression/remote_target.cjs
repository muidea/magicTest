// Shared remote/local target address resolution for Chromium and direct HTTP transports.
function baseDomainFromOrigin(origin) {
  const hostname = new URL(origin).hostname.toLowerCase();
  const labels = hostname.split('.').filter(Boolean);
  return labels.length <= 2 ? hostname : labels.slice(1).join('.');
}

function resolveConnectHost(hostname, env = process.env) {
  const host = String(hostname || '');
  const lower = host.toLowerCase();
  const target = (env.MAGICTEST_TARGET_ADDRESS || '').trim();
  const baseDomain = (env.MAGICTEST_BASE_DOMAIN || '').trim().toLowerCase();
  if (target && (!baseDomain || lower === baseDomain || lower.endsWith('.' + baseDomain))) {
    return target;
  }
  if (lower.endsWith('.local.vpc')) {
    return '127.0.0.1';
  }
  return host;
}

function browserHostResolverArgs(origin, targetAddress) {
  const target = typeof targetAddress === 'string' ? targetAddress.trim() : '';
  if (target) {
    const baseDomain = baseDomainFromOrigin(origin);
    return ['--host-resolver-rules=MAP *.' + baseDomain + ' ' + target + ',MAP ' + baseDomain + ' ' + target];
  }
  return ['--host-resolver-rules=MAP *.local.vpc 127.0.0.1'];
}

module.exports = { baseDomainFromOrigin, resolveConnectHost, browserHostResolverArgs };
