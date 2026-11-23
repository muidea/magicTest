#!/usr/bin/env python3
"""ApiKey Gateway + Bearer Apps-Action synthetic orchestrator: plan/run/verify. Never retries an unknown write."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
from admission_contract import validate_plan
from fixture_tool import MODEL_ROOT, ROOT, simulation_plan


class Failure(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Failure(message)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def strict_json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Failure('nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError):
        raise Failure('invalid JSON') from None


def digest(value):
    return 'sha256:' + hashlib.sha256(dumps(value).encode()).hexdigest()


def load(path):
    with Path(path).expanduser().open('rb') as stream:
        raw = stream.read((8 << 20) + 1)
    require(len(raw) <= 8 << 20, 'input size exceeded')
    return strict_json(raw)


def identity(value):
    require(type(value) in (int, str) and re.fullmatch(r'[1-9][0-9]{0,18}', str(value))
            and int(value) <= 9223372036854775807, 'invalid exact int64 identity')
    return str(value)


def definitions():
    return {p.stem: load(p) for p in sorted((MODEL_ROOT / 'definition/application/entities').glob('*.json'))}


def definition_digest():
    return digest({p.relative_to(MODEL_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted((MODEL_ROOT / 'definition/application').rglob('*')) if p.is_file()})


def checked_plan(value, models):
    mode = value.get('mode', 'replay')
    cycles = value.get('cycles', 4)
    require(value == simulation_plan(value['anchorUtc'], value['runId'], mode=mode, cycles=cycles),
            'plan differs from frozen generator')
    validate_plan(value, list(models.values()))
    return value


def endpoint(url):
    part = urlsplit(url)
    require(part.scheme == 'https' and part.hostname and not part.username and not part.password
            and not part.query and not part.fragment and re.fullmatch(
                r'/api/v1/gateway/services/[A-Za-z0-9_-]+', part.path), 'invalid HTTPS service URL')
    return url


def action_endpoint(url):
    part = urlsplit(url)
    require(part.scheme == 'https' and part.hostname and not part.username and not part.password
            and not part.query and not part.fragment and part.path in (
                '/api/v1/apps/entity/action/execute/',
                '/api/v1/web/proxy/apps/entity/action/execute/',
            ), 'invalid HTTPS Apps action URL')
    return url


def _read_secret(path, env_name, label):
    if path:
        fd = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600, f'{label} file requires owned regular mode 0600')
            raw = os.read(fd, 16385)
            require(len(raw) <= 16384, f'{label} file too large')
            value = raw.decode().strip()
        finally:
            os.close(fd)
    else:
        value = os.environ.get(env_name, '').strip()
    require(value and len(value) <= 16384 and all(32 < ord(c) < 127 for c in value), f'missing or invalid {label}')
    return value


def secret(path=None):
    return _read_secret(path, 'CHESS_SIM_API_KEY', 'ApiKey')


def action_secret(path=None):
    return _read_secret(path, 'CHESS_SIM_ACTION_TOKEN', 'ActionToken')


def _tls_context(ca_file=None, trust_leaf=False):
    context = ssl.create_default_context(cafile=str(Path(ca_file).expanduser()) if ca_file else None)
    if trust_leaf:
        require(ca_file and hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'), 'explicit leaf trust unsupported')
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise Failure('Gateway redirect refused')


class Gateway:
    def __init__(self, url, key, ca_file=None, trust_leaf=False):
        self.url, self.key = endpoint(url), key
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=_tls_context(ca_file, trust_leaf)))
        self.requests, self.last = 0, 0.0

    def call(self, entity, operation, value_id=None, fields=None, query=None):
        require(entity in definitions() and operation in ('query', 'get', 'create'), 'unsupported operation')
        require(operation != 'create' or entity not in ('orderEvent', 'roomOccupancy'), 'derived create forbidden')
        require(self.requests < 500, 'request budget exhausted')
        self.requests += 1
        time.sleep(max(0, .5 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        url = self.url + '/' + entity + '_' + operation
        if operation == 'get':
            url += '/' + identity(value_id)
        if query:
            url += '?' + urlencode(query)
        request = Request(url, method='POST' if operation == 'create' else 'GET',
                          data=dumps(fields).encode() if fields is not None else None,
                          headers={'Authorization': 'ApiKey ' + self.key,
                                   'Accept': 'application/json', 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=30) as response:
                require(response.status == 200 and response.headers.get_content_type() == 'application/json',
                        'invalid Gateway response type/status')
                raw = response.read((4 << 20) + 1)
                require(len(raw) <= 4 << 20, 'Gateway response too large')
                result = strict_json(raw)
                require(isinstance(result, dict) and result.get('error') is None, 'Gateway business failure; body withheld')
                return result, response.headers.get('X-Magic-Operation-ID', '')
        except HTTPError as error:
            status = error.code
            error.close()
            raise Failure(f'Gateway HTTP {status}; body withheld') from None
        except (URLError, TimeoutError, OSError):
            raise Failure('Gateway transport failure; write outcome may be unknown') from None

    def get(self, entity, value_id):
        result, _ = self.call(entity, 'get', value_id=value_id)
        value = result.get('value')
        require(isinstance(value, dict) and identity(value.get('id')) == identity(value_id), 'get identity mismatch')
        return value

    def scan(self, entity):
        result, previous, total = [], 0, None
        for number in range(1, 12):
            response, _ = self.call(entity, 'query', query={
                '_pageNum': number, '_pageSize': 100, '_needTotal': 'true', '_viewType': 'detail',
                '_sortFilter': dumps({'fieldName': 'id', 'ascFlag': True})})
            page, rows = response.get('pagination'), response.get('values')
            require(isinstance(page, dict) and type(page.get('total')) is int and 0 <= page['total'] <= 1000,
                    'missing or over-budget pagination')
            total = page['total'] if total is None else total
            require(page['total'] == total and page.get('pageNum') == number and page.get('pageSize') == 100
                    and not page.get('nextCursor') and not page.get('hasMore'), 'unstable/unsupported pagination')
            if rows is None and total == 0:
                rows = []
            require(isinstance(rows, list) and len(rows) <= 100, 'invalid query rows')
            for row in rows:
                require(isinstance(row, dict), 'invalid query record')
                actual = int(identity(row.get('id')))
                require(actual > previous, 'query identities duplicated or not ascending')
                previous = actual
            result.extend(rows)
            require(len(result) <= total, 'query exceeds total')
            if len(result) == total:
                return result
            require(len(rows) == 100, 'incomplete query page')
        raise Failure('page budget exhausted')


class ActionClient:
    def __init__(self, url, token, application_key='chess-room-booking', ca_file=None, trust_leaf=False):
        self.url = action_endpoint(url)
        self.token = token
        self.application_key = application_key
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=_tls_context(ca_file, trust_leaf)))
        self.requests, self.last = 0, 0.0

    def execute(self, scope, entity, action, record_id, expected_version, operation_id, fields=None):
        require(re.fullmatch(r'[a-f0-9]{32}', operation_id or ''), 'invalid action operationId')
        require(self.requests < 500, 'action request budget exhausted')
        self.requests += 1
        time.sleep(max(0, .5 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        body = {
            'apiVersion': 'magic.entity-action/v1',
            'operationId': operation_id,
            'identity': {
                'namespace': scope['namespace'],
                'deploymentId': scope['deploymentId'],
                'installationId': identity(scope['installationId']),
                'runtimeApplicationUuid': scope['runtimeApplicationUuid'],
                'generation': int(identity(scope['generation'])),
                'executionEpoch': int(identity(scope['executionEpoch'])),
                'artifactDigest': scope['artifactDigest'],
            },
            'entity': '/chessRoomBooking/' + entity,
            'action': action,
            'id': identity(record_id),
            'expectedVersion': identity(expected_version),
            'fields': [{'name': k, 'value': v} for k, v in sorted((fields or {}).items())],
        }
        query = urlencode({'application': self.application_key, 'deploymentId': scope['deploymentId']})
        request = Request(self.url + '?' + query, method='POST',
                          data=dumps(body).encode(),
                          headers={'Authorization': 'Bearer ' + self.token,
                                   'Accept': 'application/json', 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=30) as response:
                require(response.status == 200 and response.headers.get_content_type() == 'application/json',
                        'invalid Apps action response type/status')
                raw = response.read((4 << 20) + 1)
                require(len(raw) <= 4 << 20, 'Apps response too large')
                result = strict_json(raw)
                require(isinstance(result, dict) and result.get('error') is None, 'Apps action failure; body withheld')
                return result
        except HTTPError as error:
            status = error.code
            error.close()
            raise Failure(f'Apps action HTTP {status}; body withheld') from None
        except (URLError, TimeoutError, OSError):
            raise Failure('Apps action transport failure; action outcome may be unknown') from None


class Journal:
    def __init__(self, directory, binding):
        self.directory = Path(directory).expanduser()
        require(not self.directory.is_symlink(), 'state directory cannot be symlink')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.stat()
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'state directory requires owned mode 0700')
        self.lock = os.open(self.directory / 'run.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.path = self.directory / 'journal.json'
            require(not self.path.is_symlink(), 'journal cannot be symlink')
            if self.path.exists():
                require(stat.S_IMODE(self.path.stat().st_mode) == 0o600, 'journal requires mode 0600')
                self.data = load(self.path)
                require(self.data.get('binding') == binding, 'journal service/plan/definition binding mismatch')
                self.data.setdefault('actions', {})
                self.data.setdefault('samples', {})
            else:
                self.data = {'binding': binding, 'preflight': False, 'identity': None, 'records': {}, 'actions': {}, 'samples': {}}
                self.save()
        except BaseException:
            os.close(self.lock)
            raise

    def save(self):
        fd, temp = tempfile.mkstemp(prefix='.journal-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(dumps(self.data) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def close(self):
        os.close(self.lock)


def resolve(values, records):
    if isinstance(values, dict):
        if set(values) == {'$ref'}:
            row = records.get(values['$ref'])
            require(row is not None and row.get('status') == 'confirmed', 'dependency is not confirmed')
            return {'id': int(identity(row['id']))}
        return {k: resolve(v, records) for k, v in values.items()}
    if isinstance(values, list):
        return [resolve(v, records) for v in values]
    return values


def compare(actual, expected, model, ignored_fields=()):
    require(isinstance(actual, dict), 'record is not an object')
    fields = {f['name']: f for f in model['fields']}
    for name, value in expected.items():
        if name in ignored_fields:
            continue
        item = actual.get(name)
        typ = fields[name]['type']
        if typ.get('pkgPath') and value is not None:
            if isinstance(value, list):
                require(isinstance(item, list) and sorted(identity(v.get('id')) for v in item) ==
                        sorted(identity(v['id']) for v in value), 'reference collection mismatch')
            else:
                require(isinstance(item, dict) and identity(item.get('id')) == identity(value['id']), 'reference mismatch')
        elif typ['name'] == 'datetime' and value is not None:
            from admission_contract import instant
            if isinstance(item, str) and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}', item):
                item = item.replace(' ', 'T') + 'Z'
            require(instant(item) == instant(value), 'UTC datetime mismatch')
        else:
            require(type(item) is type(value) and item == value, f'scalar/null mismatch on {name}')


def normalize_execution_identity(value):
    require(isinstance(value, dict), 'missing execution identity')
    deployment_id = value.get('deploymentId', '')
    artifact_digest = value.get('artifactDigest', '')
    namespace = value.get('namespace')
    runtime_uuid = value.get('runtimeApplicationUuid')
    require(re.fullmatch(r'[a-f0-9]{32}', deployment_id) and
            re.fullmatch(r'sha256:[a-f0-9]{64}', artifact_digest) and
            isinstance(namespace, str) and namespace and
            isinstance(runtime_uuid, str) and runtime_uuid, 'invalid execution identity')
    normalized = {
        'deploymentId': deployment_id,
        'artifactDigest': artifact_digest,
        'namespace': namespace,
        'runtimeApplicationUuid': runtime_uuid,
        'installationId': identity(value.get('installationId')),
        'generation': int(identity(value.get('generation'))),
        'executionEpoch': int(identity(value.get('executionEpoch'))),
    }
    return normalized


def receipt_identity(receipt):
    return normalize_execution_identity(receipt.get('identity'))


def accept_create(result, operation, row, journal):
    receipt = result.get('receipt')
    require(isinstance(receipt, dict) and receipt.get('apiVersion') in (
        'magic.entity-value-write/v1', 'magic.entity-source-write/v1'), 'missing reliable receipt')
    require(re.fullmatch(r'[a-f0-9]{32}', operation or '') and receipt.get('operationId') == operation
            and receipt.get('operation') == 'create' and not receipt.get('canceled')
            and receipt.get('entity') == '/chessRoomBooking/' + row['entity'], 'receipt operation mismatch')
    scope = receipt_identity(receipt)
    require(journal.data['identity'] is None or normalize_execution_identity(journal.data['identity']) == scope, 'execution identity changed')
    value_id = identity(receipt.get('id'))
    value = result.get('value')
    require(isinstance(value, dict) and identity(value.get('id')) == value_id, 'create identity mismatch')
    require(identity(receipt.get('version')) == '1', 'create version mismatch')
    require(row['entity'] != 'bookingSample' or receipt.get('effectCount') == 2, 'source effect intentions missing')
    journal.data['identity'] = scope
    return {'id': value_id, 'operationId': operation, 'status': 'received'}


def accept_action(result, operation_id, step, target_id, journal):
    receipt = result.get('value') or result.get('receipt') or result
    require(isinstance(receipt, dict) and receipt.get('apiVersion') == 'magic.entity-action/v1',
            'missing action receipt')
    require(receipt.get('operationId') == operation_id and receipt.get('action') == step['action']
            and receipt.get('entity') == '/chessRoomBooking/' + step['entity']
            and identity(receipt.get('id')) == identity(target_id), 'action receipt mismatch')
    scope = receipt_identity(receipt)
    require(normalize_execution_identity(journal.data['identity']) == scope, 'action execution identity mismatch')
    next_ver = int(identity(receipt.get('version')))
    require(next_ver == step['expectedVersion'] + 1, 'action receipt version mismatch')
    return {'status': 'received', 'operationId': operation_id, 'nextVersion': next_ver, 'state': receipt.get('state')}


def run(plan, models, gateway, journal, action_client=None):
    data, rows = journal.data, journal.data['records']
    actions = journal.data['actions']
    samples = journal.data['samples']

    if not data['preflight']:
        require(not rows and not actions and not samples, 'preflight incomplete with existing intents')
        for name in models:
            require(not gateway.scan(name), 'initial instance must be empty; no writes performed')
        data['preflight'] = True
        journal.save()

    # Stage 1: Direct creates (initial states only, no action-owned timestamps/subjects)
    for row in plan.get('directCreates', []):
        key, entity = row['key'], row['entity']
        fields = resolve(row['values'], rows)
        entry = rows.get(key)
        if entry is None:
            rows[key] = {'status': 'sending', 'payloadDigest': digest(fields)}
            journal.save()  # Crash after this point is unknown, never an automatic resend.
            result, operation = gateway.call(entity, 'create', fields=fields)
            accepted = accept_create(result, operation, row, journal)
            rows[key].update(accepted)
            journal.save()
        else:
            require(entry.get('payloadDigest') == digest(fields), 'submitted payload changed')
            require(entry.get('status') in ('received', 'confirmed') and entry.get('id'),
                    'write outcome unknown: stop and ask platform owner to inspect original operation; do not resend')
        actual = gateway.get(entity, rows[key]['id'])
        if rows[key]['status'] != 'confirmed':
            compare(actual, fields, models[entity])
            require(identity(actual.get('version')) == '1', 'independent create version mismatch')
            rows[key]['status'] = 'confirmed'
            journal.save()

    # Stage 2: Business state-machine action transitions with expectedVersion optimistic concurrency
    for step in plan.get('actionSteps', []):
        skey = step['key']
        target_entry = rows.get(step['targetKey'])
        require(target_entry and target_entry.get('status') == 'confirmed', 'action target not confirmed')
        target_id = target_entry['id']
        aentry = actions.get(skey)
        step_digest = digest({'targetId': target_id, 'entity': step['entity'], 'action': step['action'],
                              'expectedVersion': step['expectedVersion'], 'fields': step.get('fields', {})})
        if aentry is None:
            require(action_client is not None, 'action client required for business state actions')
            op_id = secrets.token_hex(16)
            actions[skey] = {'status': 'sending', 'operationId': op_id, 'payloadDigest': step_digest}
            journal.save()  # Unknown action outcome must never automatically replay a new operationId.
            res = action_client.execute(data['identity'], step['entity'], step['action'],
                                        target_id, step['expectedVersion'], op_id, step.get('fields'))
            accepted = accept_action(res, op_id, step, target_id, journal)
            actions[skey].update(accepted)
            journal.save()
        else:
            require(aentry.get('payloadDigest') == step_digest, 'action payload changed')
            require(aentry.get('status') in ('received', 'confirmed'),
                    'action outcome unknown: stop and inspect original Apps operation; do not retry')
        if actions[skey]['status'] != 'confirmed':
            actual = gateway.get(step['entity'], target_id)
            require(int(identity(actual.get('version'))) >= step['expectedVersion'] + 1,
                    'post-action record version did not advance')
            actions[skey]['status'] = 'confirmed'
            journal.save()

    # Stage 3: Reliable source ingestion (bookingSample -> CreateEffect)
    for row in plan.get('sampleCreates', []):
        key, entity = row['key'], row['entity']
        require(entity == 'bookingSample', 'only bookingSample allowed in sampleCreates')
        fields = resolve(row['values'], rows)
        sentry = samples.get(key)
        if sentry is None:
            samples[key] = {'status': 'sending', 'payloadDigest': digest(fields)}
            journal.save()
            result, operation = gateway.call(entity, 'create', fields=fields)
            accepted = accept_create(result, operation, row, journal)
            samples[key].update(accepted)
            journal.save()
        else:
            require(sentry.get('payloadDigest') == digest(fields), 'submitted sample payload changed')
            require(sentry.get('status') in ('received', 'confirmed') and sentry.get('id'),
                    'sample write outcome unknown: stop and inspect original operation; do not resend')
        actual = gateway.get(entity, samples[key]['id'])
        if samples[key]['status'] != 'confirmed':
            compare(actual, fields, models[entity])
            require(identity(actual.get('version')) == '1', 'independent sample create version mismatch')
            samples[key]['status'] = 'confirmed'
            journal.save()

    return {
        'directConfirmed': len(rows),
        'actionsConfirmed': len(actions),
        'samplesConfirmed': len(samples),
        'derivedVerified': False,
        'taskReceiptsVerified': False,
    }


def derived_identity(deployment, sample_key):
    raw = json.dumps([deployment, sample_key], ensure_ascii=False, separators=(',', ':')).encode()
    return 'CRB-S-' + base64.b32encode(hashlib.sha256(raw).digest()).decode().rstrip('=')


def verify(plan, models, gateway, journal, wait_seconds=0):
    rows = journal.data['records']
    actions = journal.data['actions']
    samples_journal = journal.data['samples']
    journal.data.pop('readbackVerified', None)
    journal.save()

    require(set(rows) == {r['key'] for r in plan.get('directCreates', [])} and journal.data['identity'],
            'direct phase incomplete')
    require(set(actions) == {s['key'] for s in plan.get('actionSteps', [])}, 'action phase incomplete')
    require(set(samples_journal) == {r['key'] for r in plan.get('sampleCreates', [])}, 'sample phase incomplete')

    final_states = plan.get('finalStates', {})
    final_versions = plan.get('finalVersions', {})

    for row in plan.get('directCreates', []):
        entry = rows[row['key']]
        require(entry.get('status') == 'confirmed', 'direct write not confirmed')
        actual = gateway.get(row['entity'], entry['id'])
        expected_values = resolve(row['values'], rows)
        state_rule = models[row['entity']].get('writeRules', {}).get('state')
        ignored = ()
        if state_rule and row['key'] in final_states:
            sf = state_rule['field']
            expected_values[sf] = final_states[row['key']]
            # Ignore timestamps/subject fields populated by action steps
            action_owned = [f for a in models[row['entity']]['writeRules'].get('actions', [])
                            for f in (a.get('timeField'), a.get('subjectField'), *a.get('inputFields', [])) if f]
            ignored = tuple(action_owned)
        compare(actual, expected_values, models[row['entity']], ignored_fields=ignored)
        expected_ver = str(final_versions.get(row['key'], 1))
        require(identity(actual.get('version')) == expected_ver, f'post-action version mismatch on {row["key"]}')

    for step in plan.get('actionSteps', []):
        require(actions[step['key']].get('status') == 'confirmed', 'action step not confirmed')

    for row in plan.get('sampleCreates', []):
        sentry = samples_journal[row['key']]
        require(sentry.get('status') == 'confirmed', 'sample create not confirmed')
        actual = gateway.get(row['entity'], sentry['id'])
        compare(actual, resolve(row['values'], rows), models[row['entity']])
        require(identity(actual.get('version')) == '1', 'independent sample version mismatch')

    deadline = time.monotonic() + wait_seconds
    samples = {r['key']: r for r in plan.get('sampleCreates', [])}
    derived_plan = plan.get('derivedExpectations', [])
    while True:
        inventories, total = {}, 0
        for name in models:
            inventories[name] = gateway.scan(name)
            total += len(inventories[name])
            require(total <= 1000, 'total read row budget exceeded')
        missing = False
        target_ids = {name: set() for name in ('roomOccupancy', 'orderEvent')}
        for expected in derived_plan:
            entity = expected['entity']
            sample_key = samples[expected['sourceKey']]['values']['sampleKey']
            key = derived_identity(journal.data['identity']['deploymentId'], sample_key)
            candidates = [r for r in inventories[entity] if r.get('sampleKey') == key]
            require(len(candidates) <= 1, 'duplicate derived identity')
            if not candidates:
                missing = True
                continue
            row_id = identity(candidates[0].get('id'))
            target_ids[entity].add(row_id)
            actual = gateway.get(entity, row_id)
            compare(actual, resolve(expected['expectedValues'], rows) | {'sampleKey': key}, models[entity])
        for name in models:
            if name in target_ids:
                expected_ids = target_ids[name]
            elif name == 'bookingSample':
                expected_ids = {identity(samples_journal[r['key']]['id']) for r in plan.get('sampleCreates', [])}
            else:
                expected_ids = {identity(rows[r['key']]['id']) for r in plan.get('directCreates', []) if r['entity'] == name}
            require({identity(r.get('id')) for r in inventories[name]} == expected_ids,
                    f'unexpected or missing instance records in {name}')
        if not missing:
            journal.data['readbackVerified'] = True
            journal.save()
            return {
                'directConfirmed': len(rows),
                'actionsConfirmed': len(actions),
                'samplesConfirmed': len(samples_journal),
                'derivedReadbackConfirmed': len(derived_plan),
                'totalRecords': total,
                'taskReceiptsVerified': False,
                'liveAccepted': False,
                'next': 'platform owner verifies task receipts and 19 workbench pages',
            }
        require(time.monotonic() < deadline, 'derived readback incomplete; inspect platform tasks, never create targets directly')
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'run', 'verify'))
    parser.add_argument('--mode', choices=('seed', 'replay', 'live-stream'), default='replay')
    parser.add_argument('--cycles', type=int, default=4)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--anchor-utc', default='2026-11-01T00:00:00Z')
    parser.add_argument('--run-id', default='replay-closeout-20261122')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--service-url', default='https://panel.local.vpc/api/v1/gateway/services/chess_room_booking_simulation')
    parser.add_argument('--action-url', default='https://panel.local.vpc/api/v1/apps/entity/action/execute/')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--api-key-file', type=Path)
    parser.add_argument('--action-token-file', type=Path)
    parser.add_argument('--ca-file', type=Path)
    parser.add_argument('--trust-leaf', action='store_true')
    parser.add_argument('--wait-seconds', type=int, default=0)
    args = parser.parse_args()
    journal = None
    try:
        if args.command == 'plan':
            value = simulation_plan(args.anchor_utc, args.run_id, mode=args.mode, cycles=args.cycles)
            checked_plan(value, definitions())
            if args.output:
                with args.output.expanduser().open('x') as stream:
                    stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            else:
                print(dumps(value))
            return
        require(args.state_dir is not None and 0 <= args.wait_seconds <= 60, 'state-dir and wait budget 0..60 required')
        models = definitions()
        if args.plan:
            plan = checked_plan(load(args.plan), models)
        else:
            plan = checked_plan(simulation_plan(args.anchor_utc, args.run_id, mode=args.mode, cycles=args.cycles), models)
        url = endpoint(args.service_url)
        journal = Journal(args.state_dir, {'serviceUrl': url, 'planDigest': digest(plan), 'definitionDigest': definition_digest()})
        gateway = Gateway(url, secret(args.api_key_file), args.ca_file, args.trust_leaf)
        action_client = None
        if args.command == 'run' and plan.get('actionSteps'):
            token = action_secret(args.action_token_file) if (args.action_token_file or os.environ.get('CHESS_SIM_ACTION_TOKEN')) else None
            if token:
                action_client = ActionClient(args.action_url, token, ca_file=args.ca_file, trust_leaf=args.trust_leaf)
            result = run(plan, models, gateway, journal, action_client=action_client)
        elif args.command == 'run':
            result = run(plan, models, gateway, journal)
        else:
            result = verify(plan, models, gateway, journal, args.wait_seconds)
        print(dumps(result))
    except Failure as error:
        print(str(error) + '; no write was retried.')
        raise SystemExit(1) from None
    except (ValueError, KeyError, TypeError, OSError):
        print('Simulation stopped; review local journal and platform original operation. No write was retried.')
        raise SystemExit(1) from None
    finally:
        if journal:
            journal.close()


if __name__ == '__main__':
    main()
