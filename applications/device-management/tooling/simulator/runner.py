"""Serial writes, durable recovery and complete readback over the public service."""
import time
from datetime import datetime, timezone
from .client import RemoteFailure
from .common import ENTITIES, Failure, RELATIONS, digest, identity, instant, require, same_fields, utc, write_json
from .plan import cycle


def stored_row(value):
    if isinstance(value, dict):
        return {k: identity(v) if k in ('id', 'version') and v is not None else stored_row(v) for k, v in value.items()}
    if isinstance(value, list):
        return [stored_row(v) for v in value]
    return value


class Runner:
    def __init__(self, config, plan, journal, gateway, progress=None):
        self.config, self.plan, self.journal, self.gateway = config, plan, journal, gateway
        self.progress = progress or (lambda *_: None)
        self.inventory = None

    def preflight(self):
        # API-key-only: these are actual service reads, not admin/catalog requests.
        self.inventory = {entity: self.gateway.scan(entity) for entity in ENTITIES}
        self.journal.remember('serviceUrl', self.config['serviceUrl'])
        return {entity: len(rows) for entity, rows in self.inventory.items()}

    def resolve(self, fields):
        mapping = self.journal.mapping()
        result = {}
        for name, value in fields.items():
            if isinstance(value, dict) and set(value) == {'$ref'}:
                require(value['$ref'] in mapping, 'referenced bootstrap record has not been confirmed')
                result[name] = {'id': identity(mapping[value['$ref']])}
            else:
                result[name] = value
        return result

    def recover(self, intent):
        payload = intent['payload']
        entity, value_id = intent['entity'], intent['id']
        if not value_id:
            if intent['operation'] == 'update':
                value_id = payload['id']
            else:
                require(entity != 'telemetry', 'unknown telemetry create without returned ID; stop for owner reconciliation (no uniqueness proof)')
                matches = [row for row in self.gateway.scan(entity) if row.get('code') == payload['fields']['code']]
                require(len(matches) == 1, 'unknown create is absent/ambiguous; never automatically resend it')
                value_id = identity(matches[0]['id'])
        row = self.gateway.get(entity, value_id)
        expected = dict(payload['fields'])
        if intent['operation'] == 'update':
            expected['version'] = str(int(expected['version']) + 1)
        require(same_fields(stored_row(row), expected), 'unknown result conflicts with current record; manual reconciliation required')
        self.journal.mark(intent['key'], 'satisfied', stored_row(row), 'postcondition satisfied; original commit attribution unproven', identity(value_id))
        return row

    def execute(self, op):
        intent = self.journal.intent(op['key'])
        if intent:
            require(intent['entity'] == op['entity'] and intent['operation'] == op['operation'], 'intent type mismatch')
            if intent['state'] in ('confirmed', 'satisfied'):
                return
            require(intent['state'] in ('prepared', 'unknown'), 'previous intent rejected; do not silently replace it')
            self.recover(intent)
            return
        require(all(i['state'] in ('confirmed', 'satisfied') for i in self.journal.intents()),
                'resolve the original unfinished intent before starting another write')
        fields = self.resolve(op['fields'])
        entity, kind = op['entity'], op['operation']
        payload = {'fields': fields}
        if kind == 'update':
            mapping = self.journal.mapping()
            require(op['target'] in mapping, 'update target not owned by this run')
            value_id = identity(mapping[op['target']])
            before = stored_row(self.gateway.get(entity, value_id))
            # Only a new explicitly planned update may read a fresh owner version.
            fields['version'] = identity(before.get('version'))
            payload['id'] = value_id
            if op.get('expectedFields') is not None:
                require(same_fields(before, self.resolve(op['expectedFields'])), 'explicit update precondition changed')
        else:
            value_id = None
            require(self.inventory is not None, 'service preflight required')
            for row in self.inventory[entity]:
                if 'code' in fields:
                    collision = row.get('code') == fields['code']
                else:
                    collision = (identity(row.get('device', {}).get('id')) == fields['device']['id']
                                 and instant(row.get('sampledAt')) == instant(fields['sampledAt']))
                require(not collision, 'natural key already exists outside this prepared intent; refusing adoption')
        # Reserve at least the write request before persisting prepared state.
        require(self.journal.meta('requests', 0) < self.config['run']['maxRequests'], 'request budget exhausted before write')
        self.journal.prepare(op, payload)
        try:
            response = self.gateway.call(entity, kind, fields=fields, value_id=value_id)
            row = response.get('value')
            require(isinstance(row, dict), 'write returned no value')
            value_id = identity(row.get('id'))
            if kind == 'update':
                require(value_id == payload['id'], 'write returned the wrong record')
            # Persist returned ID before any follow-up I/O, so missing GET can be recovered without a create replay.
            self.journal.mark(op['key'], 'prepared', note='write response received', value_id=value_id)
            actual = stored_row(self.gateway.get(entity, value_id))
            expected = dict(fields)
            if kind == 'update':
                expected['version'] = str(int(expected['version']) + 1)
            require(same_fields(actual, expected), 'post-write independent GET differs from submitted fields')
            self.journal.mark(op['key'], 'confirmed', actual, 'Gateway response and GET agree', value_id)
            if kind == 'create':
                self.inventory[entity].append(row)
        except BaseException:
            self.journal.mark(op['key'], 'unknown', note='interrupted/error; query original result before further writes')
            raise

    def _bootstrap_done(self):
        return all(
            self.journal.intent(op['key']) and self.journal.intent(op['key'])['state'] in ('confirmed', 'satisfied')
            for op in self.plan['bootstrap']
        )

    def phase(self, name):
        require(name in ('bootstrap', 'backfill'), 'unknown plan phase')
        if name == 'backfill':
            require(self._bootstrap_done(), 'bootstrap must finish before backfill')
        for index, op in enumerate(self.plan[name], 1):
            self.execute(op)
            if index % 20 == 0 or index == len(self.plan[name]):
                self.progress(name, index, len(self.plan[name]))
        self.export()

    def collect(self, count):
        require(self._bootstrap_done(), 'bootstrap must finish before collect')
        completed = self.journal.meta('completedCycles', 0)
        maximum = self.config['run']['maxCycles']
        require(type(count) is int and 1 <= count <= maximum - completed, 'cycles exceed remaining run budget')
        for step in range(count):
            index = self.journal.meta('completedCycles', 0)
            key = f'cycle:{index}'
            ops = self.journal.meta(key)
            if ops is None:
                now = datetime.now(timezone.utc)
                previous = self.journal.meta('lastSampleAt')
                require(previous is None or instant(previous) < now, 'clock did not advance; refusing duplicate/older samples')
                ops = cycle(self.config, index, utc(now))
                self.journal.remember(key, ops)
            for op in ops:
                self.execute(op)
            first_telemetry = next((op for op in ops if op['entity'] == 'telemetry'), ops[0])
            with self.journal.db:
                self.journal.set_meta('lastSampleAt', first_telemetry['fields'].get('sampledAt') or utc(datetime.now(timezone.utc)))
                self.journal.set_meta('completedCycles', index + 1)
            self.progress('collect', index + 1, maximum)
            self.export()
            if step + 1 < count:
                time.sleep(self.config['run']['intervalSeconds'])

    def replay_checks(self):
        checks = self.plan.get('replayChecks')
        require(isinstance(checks, dict), 'replayChecks require replay-v3 scenario')
        self.phase('bootstrap')
        self.phase('backfill')

        idempotent_fields = self.resolve(checks['idempotentSample'])
        response = self.gateway.call('telemetry', 'create', fields=idempotent_fields)
        row = response.get('value')
        require(isinstance(row, dict), 'idempotent replay returned no value')
        original_id = self.journal.mapping()[checks['idempotentSourceKey']]
        require(identity(row.get('id')) == original_id, 'idempotent telemetry retry created a different record')

        conflict_fields = self.resolve(checks['conflictSample'])
        rejected = False
        try:
            self.gateway.call('telemetry', 'create', fields=conflict_fields)
        except RemoteFailure as error:
            require(error.status == 409 or (error.status == 200 and error.code is not None),
                    'unexpected failure mode for conflicting telemetry retry')
            rejected = True
        require(rejected, 'conflicting telemetry sample was not rejected')

        verification = self.verify()
        expected = checks['expectedDerivedAlarms']
        derived = verification['derivedAlarms']
        require(derived['total'] == expected['total']
                and derived['bySeverity'].get('major', 0) == expected['major']
                and derived['bySeverity'].get('critical', 0) == expected['critical']
                and derived['bySeverity'].get('minor', 0) == expected['minor'],
                'derived alarm counts disagree with replay oracle')
        return {'status': 'pass', 'idempotentRetry': 'passed', 'conflictRejection': 'passed',
                'derivedAlarms': derived, 'verification': verification}

    def update(self, entity, logical, fields, expected):
        allowed = {
            'location': {'name', 'description', 'sortOrder', 'parent'},
            'category': {'name', 'description', 'sortOrder'},
            'device': {'name', 'description', 'category', 'location', 'manufacturer',
                       'model', 'serialNumber', 'commissionedOn', 'connectionStatus', 'lastSeenAt'},
        }
        require(entity in allowed and isinstance(fields, dict) and fields and set(fields) <= allowed[entity], 'update includes forbidden fields')
        require(isinstance(expected, dict) and set(expected) == set(fields), 'explicit update needs matching expectedFields for every changed field')
        if 'connectionStatus' in fields:
            require(fields['connectionStatus'] in ('online', 'offline', 'unknown'), 'invalid connectionStatus')
        for name in RELATIONS.get(entity, {}):
            if name in fields and fields[name] is not None:
                require(isinstance(fields[name], dict) and set(fields[name]) == {'$ref'}, 'updates use owned logical references')
        op = {'key': 'edit:' + digest({'entity': entity, 'logical': logical, 'fields': fields, 'expected': expected}),
              'entity': entity, 'operation': 'update', 'target': entity + ':' + logical,
              'fields': fields, 'expectedFields': expected}
        self.execute(op)
        self.export()

    def verify(self):
        unresolved = [i for i in self.journal.intents() if i['state'] not in ('confirmed', 'satisfied')]
        require(not unresolved, 'unresolved writes exist; recover their original phase first')
        first = {entity: self.gateway.scan(entity) for entity in ENTITIES}
        second = {entity: self.gateway.scan(entity) for entity in ENTITIES}
        require(first == second, 'two complete readbacks differ; pause collectors and retry verification')
        expected, actual_counts, mapping = {}, {}, self.journal.mapping()
        for intent in self.journal.intents():
            fields = dict(intent['payload']['fields'])
            if intent['operation'] == 'update':
                fields['version'] = str(int(fields['version']) + 1)
            expected.setdefault((intent['entity'], intent['id']), {}).update(fields)
        for (entity, value_id), fields in expected.items():
            matches = [row for row in second[entity] if identity(row['id']) == value_id]
            require(len(matches) == 1 and same_fields(stored_row(matches[0]), fields), 'complete service readback differs from journal expectations')
        for entity in ENTITIES:
            owned = [value for key, value in mapping.items() if self.journal.intent(key)['entity'] == entity]
            actual_counts[entity] = sum(identity(row['id']) in owned for row in second[entity])
            require(actual_counts[entity] == len(owned), 'owned records missing from complete query')
            prefix = 'DM-' + self.config['run']['runId'] + '-'
            require(all(identity(row['id']) in owned for row in second[entity] if str(row.get('code', '')).startswith(prefix)),
                    'untracked records use this run prefix')
        devices = [row for row in second['device'] if identity(row['id']) in mapping.values()]
        device_ids = {identity(row['id']) for row in devices}
        telemetry = [row for row in second['telemetry'] if identity(row.get('device', {}).get('id')) in device_ids]
        require(len(telemetry) == actual_counts['telemetry'], 'untracked/duplicate telemetry for owned devices')
        seen = set()
        for row in telemetry:
            key = identity(row['device']['id']), instant(row['sampledAt'])
            require(key not in seen, 'duplicate telemetry natural key in readback')
            seen.add(key)
        owned_alarms = [row for row in second['alarm'] if identity(row.get('device', {}).get('id')) in device_ids]
        by_severity = {}
        for row in owned_alarms:
            sev = row.get('severity') or 'unknown'
            by_severity[sev] = by_severity.get(sev, 0) + 1
        eligible = [row for row in devices if row.get('lifecycleStatus') != 'retired']
        online = sum(row.get('connectionStatus') == 'online' for row in eligible)
        result = {
            'status': 'pass',
            'scope': 'two stable complete Gateway readbacks; no Apps/browser acceptance',
            'counts': actual_counts,
            'serviceTotals': {e: len(second[e]) for e in ENTITIES},
            'derivedAlarms': {'total': len(owned_alarms), 'bySeverity': by_severity},
            'window': self.plan['window'],
            'online': online,
            'onlineDenominator': len(eligible),
            'unknownWrites': 0,
            'exactlyOnce': False,
            'communicationFacts': 'gateway-device-update',
            'observedAt': utc(datetime.now(timezone.utc)),
        }
        write_json(self.journal.directory / 'readback.json', stored_row(second))
        write_json(self.journal.directory / 'verification.json', result)
        self.export()
        return result

    def export(self):
        write_json(self.journal.directory / 'id-mapping.json', self.journal.mapping())
        write_json(self.journal.directory / 'summary.json', self.journal.summary())
