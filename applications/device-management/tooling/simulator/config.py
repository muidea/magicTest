"""API-key-only configuration: Gateway owns subscription and target routing."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from .common import home_path, instant, require, utc

DEFAULT_URL = 'https://panel.local.vpc/api/v1/gateway/services/device_management_service'
SCENARIOS = ('live-stream-v1', 'replay-v3', 'current-window-v1', 'fixed-history-v1')
REPLAY_ANCHOR = '2026-10-24T04:00:00Z'
FIXED_ANCHOR = '2026-10-14T12:00:00Z'


def endpoint(value):
    p = urlsplit(value)
    require(p.scheme == 'https' and p.hostname and not p.username and not p.password and not p.query and not p.fragment,
            'service URL must be HTTPS without userinfo, query or fragment')
    require(re.fullmatch(r'/api/v1/gateway/services/[a-z][a-z0-9_]{2,63}', p.path.rstrip('/')) is not None,
            'invalid canonical Gateway service URL')
    return p.scheme + '://' + p.netloc, p.path.rstrip('/')


def configure(service_url, credential_file, directory, run_id, anchor=None, scenario='live-stream-v1'):
    if scenario == 'fixed-history-v1':
        require(anchor is None or instant(anchor) == instant(FIXED_ANCHOR), 'fixed-history anchor must remain unchanged')
        anchor = FIXED_ANCHOR
    elif scenario == 'replay-v3':
        require(anchor is None or instant(anchor) == instant(REPLAY_ANCHOR), 'replay-v3 anchor must remain unchanged')
        anchor = REPLAY_ANCHOR
    value = {
        'schemaVersion': 'device-management.simulator-config/v1', 'serviceUrl': service_url.rstrip('/'),
        'credentialFile': str(credential_file),
        'tls': {'caFile': '~/dataspace/magicPlatform/services/secret/tls/tls.crt', 'trustLeaf': True},
        'run': {'runId': run_id, 'scenario': scenario,
                'anchor': anchor or utc(datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)),
                'randomSeed': 20261023, 'intervalSeconds': 60, 'maxCycles': 60,
                'maxRequests': 10000, 'maxReadRows': 20000, 'qps': 2, 'journalDirectory': str(directory)}}
    return validate(value)


def validate(config):
    require(isinstance(config, dict) and config.get('schemaVersion') == 'device-management.simulator-config/v1',
            'unsupported simulator configuration')
    endpoint(config['serviceUrl'])
    run = config['run']
    require(re.fullmatch(r'[A-F0-9]{12}', run.get('runId', '')), 'runId must contain 12 uppercase hexadecimal characters')
    scenario = run.get('scenario')
    require(scenario in SCENARIOS, 'unsupported scenario')
    anchor = instant(run['anchor'])
    require(anchor.minute == anchor.second == anchor.microsecond == 0, 'anchor must be an exact UTC hour')
    if scenario == 'replay-v3':
        require(anchor == instant(REPLAY_ANCHOR), 'replay-v3 anchor must remain unchanged')
    elif scenario == 'fixed-history-v1':
        require(anchor == instant(FIXED_ANCHOR), 'fixed-history anchor must remain unchanged')
    for key, low, high in (('intervalSeconds', 1, 3600), ('maxCycles', 1, 1440),
                           ('maxRequests', 1, 100000), ('maxReadRows', 100, 100000)):
        require(type(run.get(key)) is int and low <= run[key] <= high, 'invalid run budget: ' + key)
    require(type(run.get('randomSeed')) is int, 'randomSeed must be an integer')
    require(type(run.get('qps')) in (float, int) and 0 < run['qps'] <= 10, 'invalid request rate')
    for value in (config['credentialFile'], config['tls']['caFile'], run['journalDirectory']):
        home_path(value)
    require(type(config['tls'].get('trustLeaf', False)) is bool, 'invalid TLS trustLeaf')
    return config
