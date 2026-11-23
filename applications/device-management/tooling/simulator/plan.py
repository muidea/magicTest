"""Legal V3 business requests for seed, replay, and live-stream scenarios."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
from generate_fixture import generate, ANCHOR
from .common import ENTITIES, RELATIONS, digest, instant, require, utc

ROOT = Path(__file__).resolve().parents[2]


def prefixed(run_id, logical):
    return 'DM-' + run_id + '-' + logical


def _build_replay_v3(config):
    run = config['run']
    anchor = instant(run['anchor'])
    bootstrap_data = json.loads((ROOT / 'fixtures/threshold-v3/bootstrap.json').read_text())
    cases_data = json.loads((ROOT / 'fixtures/threshold-v3/cases.json').read_text())
    bootstrap, backfill = [], []
    for entity in ('location', 'category', 'device'):
        for row in bootstrap_data[entity]:
            code = row['code']
            fields = dict(row)
            fields['code'] = prefixed(run['runId'], code)
            for key_name, target_entity, field_name in (
                ('parentCode', 'location', 'parent'),
                ('categoryCode', 'category', 'category'),
                ('locationCode', 'location', 'location'),
            ):
                if key_name in fields:
                    ref = fields.pop(key_name)
                    fields[field_name] = None if ref is None else {'$ref': f'{target_entity}:{ref}'}
            if entity == 'device':
                fields['lifecycleStatus'] = 'standby'
            bootstrap.append({'key': f'{entity}:{code}', 'entity': entity, 'operation': 'create', 'fields': fields})
    bootstrap.append({
        'key': 'device:DTA-DEVICE-001:heartbeat',
        'entity': 'device',
        'operation': 'update',
        'target': 'device:DTA-DEVICE-001',
        'fields': {'connectionStatus': 'online', 'lastSeenAt': '2026-10-24T00:00:00.000Z'},
    })
    for case in cases_data['liveSequence']:
        fields = dict(case['record'])
        device_code = fields.pop('deviceCode')
        fields['device'] = {'$ref': f'device:{device_code}'}
        backfill.append({'key': f'telemetry:{case["key"]}', 'entity': 'telemetry', 'operation': 'create', 'fields': fields})
    normal_fields = dict(cases_data['liveSequence'][0]['record'])
    normal_device = normal_fields.pop('deviceCode')
    normal_fields['device'] = {'$ref': f'device:{normal_device}'}
    conflict_fields = dict(normal_fields)
    conflict_fields['temperature'] = 99.9
    return {
        'schemaVersion': 'device-management.simulator-plan/v1',
        'serviceUrl': config['serviceUrl'],
        'runId': run['runId'],
        'scenario': run['scenario'],
        'anchor': utc(anchor),
        'window': {'from': utc(anchor - timedelta(hours=4)), 'to': utc(anchor)},
        'bootstrap': bootstrap,
        'backfill': backfill,
        'replayChecks': {
            'idempotentSourceKey': 'telemetry:normal',
            'idempotentSample': normal_fields,
            'conflictSample': conflict_fields,
            'expectedDerivedAlarms': {'total': 9, 'major': 3, 'critical': 2, 'minor': 4},
        },
        'expected': {'location': 3, 'category': 1, 'device': 1, 'telemetry': 10, 'alarm': 0, 'maintenance': 0},
        'limits': {
            'communicationFacts': 'gateway-device-update',
            'stateActions': 'entity-action-only',
            'alarmSource': 'telemetry-threshold-alarms-create-effect',
            'exactlyOnce': False,
            'installationFencing': 'Gateway-owned; no client management API',
        },
    }


def _build_live_stream_v1(config):
    run = config['run']
    anchor = instant(run['anchor'])
    require(anchor <= datetime.now(timezone.utc), 'anchor is in the future')
    rows = deepcopy(generate('A'))
    shift = anchor - ANCHOR
    bootstrap, backfill = [], []
    for loc in rows['location']:
        fields = dict(loc)
        fields['code'] = prefixed(run['runId'], loc['code'])
        if fields.get('parent') is not None:
            fields['parent'] = {'$ref': f'location:{loc["parent"]}'}
        bootstrap.append({'key': f'location:{loc["code"]}', 'entity': 'location', 'operation': 'create', 'fields': fields})
    for cat in rows['category']:
        fields = dict(cat)
        fields['code'] = prefixed(run['runId'], cat['code'])
        bootstrap.append({'key': f'category:{cat["code"]}', 'entity': 'category', 'operation': 'create', 'fields': fields})
    for dev in rows['device'][:12]:
        fields = dict(dev)
        fields['code'] = prefixed(run['runId'], dev['code'])
        fields['category'] = {'$ref': f'category:{dev["category"]}'}
        fields['location'] = {'$ref': f'location:{dev["location"]}'}
        fields['lifecycleStatus'] = 'standby'
        fields.pop('connectionStatus', None)
        fields.pop('lastSeenAt', None)
        bootstrap.append({'key': f'device:{dev["code"]}', 'entity': 'device', 'operation': 'create', 'fields': fields})
    for n in range(1, 9):
        ref = f'device:DEV-{n:03}'
        bootstrap.append({
            'key': f'{ref}:heartbeat',
            'entity': 'device',
            'operation': 'update',
            'target': ref,
            'fields': {'connectionStatus': 'online', 'lastSeenAt': utc(anchor)},
        })
    for n in range(9, 11):
        ref = f'device:DEV-{n:03}'
        bootstrap.append({
            'key': f'{ref}:heartbeat',
            'entity': 'device',
            'operation': 'update',
            'target': ref,
            'fields': {'connectionStatus': 'offline', 'lastSeenAt': utc(anchor - timedelta(hours=2))},
        })
    for mnt in rows['maintenance'][:4]:
        fields = dict(mnt)
        fields['code'] = prefixed(run['runId'], mnt['code'])
        fields['device'] = {'$ref': f'device:{mnt["device"]}'}
        fields['performedAt'] = utc(instant(mnt['performedAt']) + shift)
        bootstrap.append({'key': f'maintenance:{mnt["code"]}', 'entity': 'maintenance', 'operation': 'create', 'fields': fields})
    start = anchor - timedelta(hours=24)
    for n in range(1, 9):
        for hour in range(24):
            sampled_at = utc(start + timedelta(hours=hour))
            temperature = None if (n, hour) == (5, 7) else round(28 + 1.4 * n + (hour % 6) * 1.1, 2)
            vibration = round(1.1 + 0.12 * (n % 5) + (hour % 3) * 0.08, 2)
            load_percent = 0 if (n, hour) == (2, 0) else round(35 + (n * 5 + hour * 2) % 45, 2)
            backfill.append({
                'key': f'telemetry:DEV-{n:03}:{hour:02d}',
                'entity': 'telemetry',
                'operation': 'create',
                'fields': {
                    'device': {'$ref': f'device:DEV-{n:03}'},
                    'sampledAt': sampled_at,
                    'temperature': temperature,
                    'vibration': vibration,
                    'loadPercent': load_percent,
                },
            })
    return {
        'schemaVersion': 'device-management.simulator-plan/v1',
        'serviceUrl': config['serviceUrl'],
        'runId': run['runId'],
        'scenario': run['scenario'],
        'anchor': utc(anchor),
        'window': {'from': utc(start), 'to': utc(anchor)},
        'bootstrap': bootstrap,
        'backfill': backfill,
        'expected': {'location': 7, 'category': 3, 'device': 12, 'telemetry': 192, 'alarm': 0, 'maintenance': 4},
        'limits': {
            'communicationFacts': 'gateway-device-update',
            'stateActions': 'entity-action-only',
            'alarmSource': 'telemetry-threshold-alarms-create-effect',
            'exactlyOnce': False,
            'installationFencing': 'Gateway-owned; no client management API',
        },
    }


def _build_legacy_window(config):
    run = config['run']
    anchor = ANCHOR if run['scenario'] == 'fixed-history-v1' else instant(run['anchor'])
    require(anchor <= datetime.now(timezone.utc), 'anchor is in the future')
    rows = deepcopy(generate('A'))
    shift = anchor - ANCHOR
    bootstrap, backfill = [], []
    for entity in ENTITIES:
        if entity == 'alarm':
            continue
        for index, row in enumerate(rows[entity]):
            logical = row.get('code', f'SAMPLE-{index + 1:04}')
            key = entity + ':' + logical
            fields = dict(row)
            if 'code' in fields:
                fields['code'] = prefixed(run['runId'], logical)
            for field in RELATIONS.get(entity, {}):
                if fields.get(field) is not None:
                    fields[field] = {'$ref': RELATIONS[entity][field] + ':' + fields[field]}
            for field in ('sampledAt', 'occurredAt', 'performedAt'):
                if field in fields:
                    fields[field] = utc(instant(fields[field]) + shift)
            if entity == 'device':
                for field in ('connectionStatus', 'lastSeenAt'):
                    fields.pop(field, None)
                fields['lifecycleStatus'] = 'standby'
            op = {'key': key, 'entity': entity, 'operation': 'create', 'fields': fields}
            (bootstrap if entity in ENTITIES[:3] else backfill).append(op)
    for number in range(1, 19):
        ref = f'device:DEV-{number:03}'
        bootstrap.append({'key': ref + ':heartbeat', 'entity': 'device', 'operation': 'update', 'target': ref,
                          'fields': {'connectionStatus': 'online', 'lastSeenAt': utc(anchor)}})
    return {
        'schemaVersion': 'device-management.simulator-plan/v1', 'serviceUrl': config['serviceUrl'],
        'runId': run['runId'], 'scenario': run['scenario'], 'anchor': utc(anchor),
        'window': {'from': utc(anchor - timedelta(hours=24)), 'to': utc(anchor)},
        'bootstrap': bootstrap, 'backfill': backfill,
        'expected': {'location': 7, 'category': 3, 'device': 24, 'telemetry': 492, 'alarm': 0, 'maintenance': 8},
        'limits': {'communicationFacts': 'gateway-device-update', 'stateActions': 'entity-action-only',
                   'alarmSource': 'telemetry-threshold-alarms-create-effect', 'exactlyOnce': False,
                   'installationFencing': 'Gateway-owned; no client management API'},
    }


def build(config):
    scenario = config['run']['scenario']
    if scenario == 'replay-v3':
        return _build_replay_v3(config)
    if scenario == 'live-stream-v1':
        return _build_live_stream_v1(config)
    return _build_legacy_window(config)


def cycle(config, index, sampled_at):
    run = config['run']
    scenario = run['scenario']
    require(scenario != 'replay-v3', 'replay-v3 uses fixed backfill and replay checks only')
    rng = random.Random(f'{run["randomSeed"]}:{index}')
    result = []
    if scenario == 'live-stream-v1':
        stage = index % 4
        # 4 rotating scenarios: 0=steady, 1=thermal-ramp (triggers alarms), 2=DEV-005 offline gap, 3=DEV-005 reconnect
        for number in range(1, 9):
            ref = f'device:DEV-{number:03}'
            if stage == 2 and number == 5:
                result.append({
                    'key': f'collect:{index}:heartbeat:{number}',
                    'entity': 'device',
                    'operation': 'update',
                    'target': ref,
                    'fields': {'connectionStatus': 'offline'},
                })
                continue
            temp = round(29 + number + rng.uniform(0, 2.5), 2)
            vib = round(1.1 + (number % 5) * 0.1 + rng.uniform(0, 0.15), 2)
            load = round(35 + (number * 4 + index * 3) % 45, 2)
            if stage == 1:
                if number == 2:
                    temp = 78.5
                elif number == 3:
                    load = 94.0
                elif number == 4:
                    vib = 5.1
            result.append({
                'key': f'collect:{index}:telemetry:{number}',
                'entity': 'telemetry',
                'operation': 'create',
                'fields': {
                    'device': {'$ref': ref},
                    'sampledAt': sampled_at,
                    'temperature': temp,
                    'vibration': vib,
                    'loadPercent': load,
                },
            })
            result.append({
                'key': f'collect:{index}:heartbeat:{number}',
                'entity': 'device',
                'operation': 'update',
                'target': ref,
                'fields': {'connectionStatus': 'online', 'lastSeenAt': sampled_at},
            })
        return result

    for number in range(1, 19):
        ref = f'device:DEV-{number:03}'
        result.append({'key': f'collect:{index}:telemetry:{number}', 'entity': 'telemetry', 'operation': 'create',
                       'fields': {'device': {'$ref': ref}, 'sampledAt': sampled_at,
                                  'temperature': round(20 + number + rng.uniform(0, 3), 3),
                                  'vibration': round(1 + number % 5 / 10 + rng.uniform(0, .1), 3),
                                  'loadPercent': (3 * number + index * 2) % 101}})
        result.append({'key': f'collect:{index}:heartbeat:{number}', 'entity': 'device', 'operation': 'update',
                       'target': ref, 'fields': {'connectionStatus': 'online', 'lastSeenAt': sampled_at}})
    return result


def plan_digest(config, plan):
    # Credentials can rotate; changing secret bytes never changes business intent.
    return digest({'serviceUrl': config['serviceUrl'], 'run': config['run'], 'plan': plan})
