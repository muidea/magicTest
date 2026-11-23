#!/usr/bin/env python3
"""Create and validate synthetic fixtures and multi-stage simulation plans; never writes a service."""
import argparse
import copy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_app_model_root

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = resolve_app_model_root('chess-room-booking')
ORDER_STATES = [
    'pending_confirmation',
    'confirmed',
    'merchant_rejected',
    'customer_canceled',
    'merchant_canceled',
    'pending_expired',
    'in_use',
    'completed',
    'no_show',
]
DEPENDENCY_ORDER = [
    'merchant',
    'store',
    'room',
    'bookingRule',
    'openingException',
    'customerProfile',
    'staffAssignment',
    'bookingOrder',
    'roomOccupancy',
    'orderEvent',
    'complaint',
    'complaintEntry',
]
MODES = ('seed', 'replay', 'live-stream')


def instant(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timestamp must include an explicit UTC offset')
    return value.astimezone(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def create(anchor):
    base = instant(anchor)
    records = {name: [] for name in DEPENDENCY_ORDER}
    at = stamp(base - timedelta(days=1))

    def add(entity, key, **values):
        common = {'version': 1, 'createdAt': at, 'updatedAt': at, 'updatedBy': 'fixture:operator'}
        records[entity].append({'key': entity + ':' + key, 'values': common | values})

    def ref(entity, key):
        return {'$ref': entity + ':' + key}

    def scope(store, room=None):
        merchant = 'B' if store.startswith('B') else 'A'
        result = {'merchantId': ref('merchant', merchant), 'storeId': ref('store', store)}
        if room:
            result['roomId'] = ref('room', room)
        return result

    for key in ['A', 'B']:
        add('merchant', key, code='FIXTURE-' + key, name='模拟商户' + key, availability='active')
    for key in ['A1', 'A2', 'B1']:
        add('store', key, merchantId=ref('merchant', key[0]), code='FIXTURE-' + key, name='模拟门店' + key,
            address='仅用于验证的虚构地址 ' + key, timeZone='UTC', availability='active', published=True)
    for key, store, state in [
        ('A1-R1', 'A1', 'active'),
        ('A1-R2', 'A1', 'active'),
        ('A2-R1', 'A2', 'active'),
        ('B1-R1', 'B1', 'active'),
        ('B1-R2', 'B1', 'maintenance'),
        ('B1-R3', 'B1', 'suspended'),
    ]:
        add('room', key, **scope(store), code=key, name='模拟房间' + key, capacity=4,
            features='空调、棋牌桌（模拟）', availability=state,
            referencePriceDescription='到店咨询；仅展示，不产生支付状态')
    for room, store in [('A1-R1', 'A1'), ('A1-R2', 'A1'), ('A2-R1', 'A2'), ('B1-R1', 'B1')]:
        add('bookingRule', room, **scope(store, room), scopeKey='fixture:room:' + room, ruleVersion=1,
            effectiveFrom=stamp(base - timedelta(days=7)),
            weeklyWindows=json.dumps({'windows': [{'weekdays': list(range(1, 8)), 'startLocal': '00:00', 'endLocal': '23:59', 'endDayOffset': 0}]}),
            confirmationMode='manual' if room == 'A2-R1' else 'automatic',
            pendingPolicy=json.dumps({'reserveWhilePending': True, 'holdSeconds': 900}),
            timePolicy=json.dumps({'mode': 'interval', 'granularityMinutes': None, 'allowCrossDay': False,
                                   'minDurationMinutes': 30, 'maxDurationMinutes': 120, 'dstAmbiguity': 'reject'}),
            cancelPolicy=json.dumps({'customerBeforeStartMinutes': 0, 'merchantReasonRequired': True}),
            reschedulePolicy=json.dumps({'maxTimes': 1, 'allowRoomChange': True, 'allowStoreChange': False, 'reconfirmationRequired': True}),
            arrivalPolicy=json.dumps({'checkInBeforeMinutes': 15, 'noShowAfterMinutes': 30,
                                      'allowEarlyCompletion': True, 'overrunPolicy': 'manual-no-automatic-extension'}))
    add('openingException', 'maintenance', **scope('B1', 'B1-R2'), scopeKey='fixture:room:B1-R2',
        localDate=base.date().isoformat(), effect='close', reason='模拟维护')
    for key in ['U1', 'U2']:
        add('customerProfile', key, subject='fixture:customer:' + key, displayName='模拟顾客' + key,
            consentVersion='fixture-v1', availability='active')
    for key, merchant, stores in [('EA1', 'A', ['A1']), ('MB', 'B', ['B1'])]:
        add('staffAssignment', key, merchantId=ref('merchant', merchant), subject='fixture:staff:' + key,
            storeIds=[ref('store', s) for s in stores], availability='active', effectiveFrom=stamp(base - timedelta(days=7)))
    for index, status in enumerate(ORDER_STATES):
        key = f'O{index + 1:02}'
        store, room = ('A2', 'A2-R1') if status in ['pending_confirmation', 'pending_expired'] else ('A1', 'A1-R1')
        if status == 'no_show':
            store, room = 'B1', 'B1-R1'
        start = base + timedelta(hours=index + 8)
        end = start + timedelta(minutes=45)
        values = dict(
            orderNo='FIXTURE-' + key,
            **scope(store, room),
            customerSubject='fixture:customer:' + ('U1' if index % 2 == 0 else 'U2'),
            startAt=stamp(start),
            endAt=stamp(end),
            status=status,
            resourceSnapshot=json.dumps({'merchantName': '模拟商户' + store[0], 'storeName': '模拟门店' + store, 'roomCode': room, 'roomName': '模拟房间' + room, 'storeTimeZone': 'UTC'}, ensure_ascii=False),
            ruleSnapshot=json.dumps({'scopeKey': 'fixture:room:' + room, 'ruleVersion': 1, 'fixtureOnly': True}),
            referencePriceSnapshot=json.dumps({'description': '仅展示', 'notPaymentEvidence': True}, ensure_ascii=False),
        )
        if status in ['confirmed', 'in_use', 'completed', 'no_show']:
            values['confirmedAt'] = stamp(start - timedelta(hours=1))
        if status in ['in_use', 'completed']:
            values['checkInAt'] = stamp(start)
        if status == 'completed':
            values['completedAt'] = stamp(end)
        add('bookingOrder', key, **values)
        active = status in ['pending_confirmation', 'confirmed', 'in_use']
        occupancy = dict(**scope(store, room), orderId=ref('bookingOrder', key), sampleKey='FIXTURE-SAMPLE-' + key, allocationRevision=1,
                         startAt=stamp(start), endAt=stamp(end), state='active' if active else 'released')
        if status in ['pending_confirmation', 'pending_expired']:
            occupancy['holdUntil'] = stamp(start - timedelta(minutes=15))
        if not active:
            occupancy.update(releasedAt=stamp(end), releaseReason='fixture:' + status)
        add('roomOccupancy', key, **occupancy)
        add('orderEvent', key, orderId=ref('bookingOrder', key), sampleKey='FIXTURE-SAMPLE-' + key, eventSequence=1, eventType='fixture_snapshot',
            toStatus=status, actorSubject='fixture:operator', occurredAt=stamp(start), operationId='fixture:operation:' + key,
            reason='合成状态展示样例，不是业务命令执行证明')
    for key, order, status, store in [('C01', 'O08', 'open', 'A1'), ('C02', 'O09', 'resolved', 'B1')]:
        customer = 'U2' if order == 'O08' else 'U1'
        add('complaint', key, caseNo='FIXTURE-' + key, **scope(store), orderId=ref('bookingOrder', order),
            complainantSubject='fixture:customer:' + customer, category='service', summary='模拟服务说明问题', status=status)
        add('complaintEntry', key + '-1', complaintId=ref('complaint', key), entrySequence=1, kind='message',
            authorSubject='fixture:customer:' + customer, content='模拟顾客留言', visibility='customer', occurredAt=stamp(base + timedelta(hours=20)))
    add('complaintEntry', 'C02-2', complaintId=ref('complaint', 'C02'), entrySequence=2, kind='note',
        authorSubject='fixture:operator', content='模拟内部处理备注；后续须验证不会对顾客显示', visibility='internal', occurredAt=stamp(base + timedelta(hours=21)))
    return {
        'schemaVersion': 'chess-room-booking.synthetic-fixture/v1',
        'anchorUtc': stamp(base),
        'purpose': 'offline-and-isolated-display-planning-only',
        'runtimeIdentity': None,
        'scenarioAssumptions': {
            'approvedBusinessDefaults': False,
            'confirmation': 'mixed-automatic-and-manual',
            'reserveWhilePending': True,
            'holdSeconds': 900,
            'timeZone': 'UTC',
            'crossDay': False,
            'note': '这些数值仅为固定回放样例，不改变 Q01—Q13 的待决状态；样例含终态及未到期阶段，非实时占用快照。',
        },
        'records': records,
    }


def validate(fixture, root=MODEL_ROOT):
    if fixture.get('schemaVersion') != 'chess-room-booking.synthetic-fixture/v1' or fixture.get('runtimeIdentity') is not None:
        raise ValueError('synthetic fixture schema/identity mismatch')
    if fixture['scenarioAssumptions']['approvedBusinessDefaults']:
        raise ValueError('fixture policies must not claim business approval')
    instant(fixture['anchorUtc'])
    all_models = {p.stem: json.loads(p.read_text()) for p in (Path(root) / 'definition/application/entities').glob('*.json')}
    if 'bookingSample' not in all_models:
        raise ValueError('authoritative model definition missing bookingSample')
    models = {name: doc for name, doc in all_models.items() if name != 'bookingSample'}
    if set(fixture['records']) != set(models):
        raise ValueError('fixture entity closure mismatch')
    lookup = {}
    for entity, rows in fixture['records'].items():
        fields = {f['name']: f for f in models[entity]['fields']}
        for row in rows:
            key = row['key']
            values = row['values']
            if not key.startswith(entity + ':') or key in lookup:
                raise ValueError('invalid/duplicate fixture key')
            if 'id' in values or set(values) - set(fields):
                raise ValueError('runtime primary identity or unknown field')
            lookup[key] = (entity, values)
            for name, field in fields.items():
                if name == 'id':
                    continue
                constraints = field['spec']['constraint'].split(',')
                if 'req' in constraints and (name not in values or values[name] is None or values[name] == ''):
                    raise ValueError(f'missing required {key}.{name}')
                if name not in values:
                    continue
                value = values[name]
                typ = field['type']
                if value is None:
                    if not typ['isPtr']:
                        raise ValueError('null nonoptional field')
                    continue
                if typ['pkgPath']:
                    continue
                if typ['name'] == 'int64' and (type(value) is not int or not -(2**63) <= value < 2**63):
                    raise ValueError('invalid int64')
                if typ['name'] == 'boolean' and type(value) is not bool:
                    raise ValueError('invalid boolean')
                if typ['name'] in ['string', 'datetime'] and not isinstance(value, str):
                    raise ValueError('invalid string/time')
                if typ['name'] == 'datetime':
                    instant(value)
                for c in constraints:
                    if c.startswith('in=') and value not in c[3:].split(':'):
                        raise ValueError('invalid enumeration')
                    if c.startswith('max=') and len(value) > int(c[4:]):
                        raise ValueError('string too long')
                    if c.startswith('range='):
                        low, high = map(int, c[6:].split(':'))
                        if not low <= value <= high:
                            raise ValueError('out of range')
        seen = set()
        for row in rows:
            for constraint in models[entity]['uniqueConstraints']:
                marker = constraint['name'] + json.dumps([row['values'].get(n) for n in constraint['fields']], sort_keys=True)
                if marker in seen:
                    raise ValueError('duplicate natural identity')
                seen.add(marker)

    def target(value, entity=None):
        if not isinstance(value, dict) or set(value) != {'$ref'} or value['$ref'] not in lookup:
            raise ValueError('unresolved fixture reference')
        actual, values = lookup[value['$ref']]
        if entity and actual != entity:
            raise ValueError('wrong reference target')
        return values

    for entity, rows in fixture['records'].items():
        fields = {f['name']: f for f in models[entity]['fields']}
        for row in rows:
            v = row['values']
            for name, value in v.items():
                typ = fields[name]['type']
                if typ['pkgPath'] and value is not None:
                    items = value if typ['elemType'] else [value]
                    if not isinstance(items, list):
                        raise ValueError('reference slice must be list')
                    for item in items:
                        target(item, (typ['elemType'] or typ)['name'])
            if 'storeId' in v and 'merchantId' in v and target(v['storeId'])['merchantId'] != v['merchantId']:
                raise ValueError('cross-merchant store')
            if 'roomId' in v and v['roomId'] is not None:
                room = target(v['roomId'])
                if room['storeId'] != v.get('storeId') or room['merchantId'] != v.get('merchantId'):
                    raise ValueError('cross-scope room')
            if entity == 'staffAssignment' and any(target(s)['merchantId'] != v['merchantId'] for s in v['storeIds']):
                raise ValueError('cross-merchant staff')
            if entity == 'complaint':
                order = target(v['orderId'])
                if any(order[n] != v[n] for n in ['merchantId', 'storeId']) or order['customerSubject'] != v['complainantSubject']:
                    raise ValueError('cross-scope complaint')
            if entity in ['bookingRule', 'openingException']:
                scope_ref = v.get('roomId') or v['storeId']
                if v['scopeKey'] != 'fixture:' + scope_ref['$ref']:
                    raise ValueError('scopeKey differs from resource')
            if entity == 'store':
                ZoneInfo(v['timeZone'])
            if entity == 'openingException':
                if date.fromisoformat(v['localDate']).isoformat() != v['localDate']:
                    raise ValueError('invalid local date')
            if 'startAt' in v and instant(v['startAt']) >= instant(v['endAt']):
                raise ValueError('invalid interval')
            for name in ['weeklyWindows', 'localWindows', 'pendingPolicy', 'timePolicy', 'cancelPolicy', 'reschedulePolicy', 'arrivalPolicy', 'resourceSnapshot', 'ruleSnapshot', 'contactSnapshot', 'referencePriceSnapshot']:
                if v.get(name) is not None:
                    if not isinstance(json.loads(v[name]), dict):
                        raise ValueError('structured text must encode an object')
    active = []
    allocations = {}
    for row in fixture['records']['roomOccupancy']:
        v = row['values']
        order = target(v['orderId'])
        oid = v['orderId']['$ref']
        if any(v[n] != order[n] for n in ['merchantId', 'storeId', 'roomId', 'startAt', 'endAt']):
            raise ValueError('allocation differs from order')
        if v['state'] == 'active':
            if order['status'] not in ['pending_confirmation', 'confirmed', 'in_use']:
                raise ValueError('terminal order holds resource')
            if oid in allocations:
                raise ValueError('multiple active allocations')
            for other in active:
                if v['roomId'] == other['roomId'] and instant(v['startAt']) < instant(other['endAt']) and instant(v['endAt']) > instant(other['startAt']):
                    raise ValueError('overlapping active allocations')
            active.append(v)
            allocations[oid] = v
    for row in fixture['records']['bookingOrder']:
        if row['values']['status'] in ['confirmed', 'in_use'] and row['key'] not in allocations:
            raise ValueError('confirmed order missing allocation')
    counts = {e: len(rows) for e, rows in fixture['records'].items()}
    return {
        'status': 'synthetic-fixture-validated',
        'counts': counts,
        'totalRecords': sum(counts.values()),
        'activeOccupancyCount': len(active),
        'businessCommandsExecuted': False,
        'liveValidation': 'not-run',
    }


def plan(fixture):
    validate(fixture)
    return {
        'schemaVersion': 'chess-room-booking.fixture-plan/v1',
        'status': 'planning-only-no-writes',
        'targetInstance': None,
        'executable': False,
        'requires': 'future controlled fixture ingestion or isolated test harness; not generic booking CRUD',
        'steps': [{'entity': e, 'count': len(fixture['records'][e]), 'keys': [r['key'] for r in fixture['records'][e]]} for e in DEPENDENCY_ORDER],
        'rules': [
            'resolve aliases using real owner allocated identities',
            'no source fixed primary keys',
            'verify same merchant/store relations',
            'never expose real contacts or CAS credentials',
            'do not treat fixture orders as operation receipts',
            'retain exact ownership list for cleanup',
        ],
    }


def _transition_actions_for_order(target_key, target_status, next_version):
    paths = {
        'pending_confirmation': [],
        'confirmed': ['confirm'],
        'merchant_rejected': ['reject'],
        'customer_canceled': ['cancel-by-customer'],
        'merchant_canceled': ['cancel-by-merchant'],
        'pending_expired': ['expire'],
        'in_use': ['confirm', 'check-in'],
        'completed': ['confirm', 'check-in', 'complete'],
        'no_show': ['confirm', 'mark-no-show'],
    }
    steps = []
    ver = next_version
    for idx, action in enumerate(paths[target_status], 1):
        steps.append({
            'key': f'act:{target_key}:{idx}:{action}',
            'entity': 'bookingOrder',
            'targetKey': target_key,
            'action': action,
            'expectedVersion': ver,
            'fields': {},
        })
        ver += 1
    return steps


def simulation_plan(anchor, run_id, mode='replay', cycles=4):
    """Build deterministic closeout ingestion & action-transition plan for seed/replay/live-stream modes."""
    if not run_id or len(run_id) > 64 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run_id):
        raise ValueError('run-id requires 1..64 ASCII letters, digits, hyphen or underscore')
    if mode not in MODES:
        raise ValueError(f'unsupported mode {mode}; expected one of {MODES}')
    if not (isinstance(cycles, int) and 1 <= cycles <= 12):
        raise ValueError('cycles must be an integer in 1..12')

    baseline = create(anchor)
    validate(baseline)
    records = copy.deepcopy(baseline['records'])
    records['staffAssignment'][0]['values']['storeIds'].append({'$ref': 'store:A2'})

    master_entities = ('merchant', 'store', 'room', 'bookingRule', 'openingException', 'customerProfile', 'staffAssignment')
    direct = []
    action_steps = []
    sample_creates = []
    derived = []
    final_states = {}
    final_versions = {}

    for entity in master_entities:
        for row in records[entity]:
            values = dict(row['values'])
            values.pop('version')
            if entity == 'merchant':
                final_states[row['key']] = 'active'
                values['availability'] = 'pending_review'
                action_steps.append({
                    'key': f"act:{row['key']}:1:approve",
                    'entity': 'merchant',
                    'targetKey': row['key'],
                    'action': 'approve',
                    'expectedVersion': 1,
                    'fields': {},
                })
                final_versions[row['key']] = 2
            elif entity == 'room':
                target_state = values['availability']
                values['availability'] = 'active'
                final_states[row['key']] = target_state
                if target_state == 'maintenance':
                    action_steps.append({
                        'key': f"act:{row['key']}:1:enter-maintenance",
                        'entity': 'room',
                        'targetKey': row['key'],
                        'action': 'enter-maintenance',
                        'expectedVersion': 1,
                        'fields': {},
                    })
                    final_versions[row['key']] = 2
                elif target_state == 'suspended':
                    action_steps.append({
                        'key': f"act:{row['key']}:1:suspend",
                        'entity': 'room',
                        'targetKey': row['key'],
                        'action': 'suspend',
                        'expectedVersion': 1,
                        'fields': {},
                    })
                    final_versions[row['key']] = 2
                else:
                    final_versions[row['key']] = 1
            else:
                final_versions[row['key']] = 1
            direct.append({'entity': entity, 'key': row['key'], 'values': values, 'createEnabled': True, 'blockedBy': []})

    base_dt = instant(anchor)
    if mode == 'replay':
        orders = {r['key']: r['values'] for r in records['bookingOrder']}
        events = {r['values']['orderId']['$ref']: r for r in records['orderEvent']}
        for row in records['bookingOrder']:
            values = dict(row['values'])
            values.pop('version')
            target_status = values['status']
            values['status'] = 'pending_confirmation'
            for ts_field in ('confirmedAt', 'checkInAt', 'completedAt'):
                values.pop(ts_field, None)
            direct.append({'entity': 'bookingOrder', 'key': row['key'], 'values': values, 'createEnabled': True, 'blockedBy': []})
            steps = _transition_actions_for_order(row['key'], target_status, 1)
            action_steps.extend(steps)
            final_states[row['key']] = target_status
            final_versions[row['key']] = 1 + len(steps)

        for row in records['complaint']:
            values = dict(row['values'])
            values.pop('version')
            target_status = values['status']
            values['status'] = 'open'
            values.pop('assignedSubject', None)
            values.pop('resolution', None)
            direct.append({'entity': 'complaint', 'key': row['key'], 'values': values, 'createEnabled': True, 'blockedBy': []})
            if target_status == 'resolved':
                action_steps.append({
                    'key': f"act:{row['key']}:1:start-processing",
                    'entity': 'complaint',
                    'targetKey': row['key'],
                    'action': 'start-processing',
                    'expectedVersion': 1,
                    'fields': {},
                })
                action_steps.append({
                    'key': f"act:{row['key']}:2:resolve",
                    'entity': 'complaint',
                    'targetKey': row['key'],
                    'action': 'resolve',
                    'expectedVersion': 2,
                    'fields': {'resolution': 'fixture:resolved'},
                })
                final_states[row['key']] = 'resolved'
                final_versions[row['key']] = 3
            else:
                final_states[row['key']] = 'open'
                final_versions[row['key']] = 1

        for row in records['complaintEntry']:
            values = dict(row['values'])
            values.pop('version')
            direct.append({'entity': 'complaintEntry', 'key': row['key'], 'values': values, 'createEnabled': True, 'blockedBy': []})
            final_versions[row['key']] = 1

        for row in records['roomOccupancy']:
            occupancy = row['values']
            order_key = occupancy['orderId']['$ref']
            order = orders[order_key]
            alias = order_key.split(':')[1]
            sample_key = 'FIXTURE-SAMPLE-' + run_id + '-' + alias
            values = {name: copy.deepcopy(occupancy.get(name)) for name in (
                'merchantId', 'storeId', 'roomId', 'orderId', 'startAt', 'endAt',
                'holdUntil', 'releasedAt', 'releaseReason', 'createdAt', 'updatedAt', 'updatedBy',
            )}
            values.update(sampleKey=sample_key, status=order['status'])
            sample_creates.append({'entity': 'bookingSample', 'key': 'bookingSample:' + alias, 'values': values, 'createEnabled': True, 'blockedBy': []})
            identity = {
                'field': 'sampleKey',
                'prefix': 'CRB-S-',
                'parts': [{'from': 'deployment', 'field': 'deploymentId'}, {'from': 'source', 'field': 'sampleKey', 'expected': sample_key}],
                'allocatedBy': 'script-effect-host',
            }
            occ_expected = copy.deepcopy(occupancy)
            occ_expected.pop('sampleKey', None)
            occ_expected.pop('version', None)
            event = copy.deepcopy(events[order_key]['values'])
            event.pop('sampleKey', None)
            event.pop('version', None)
            event['operationId'] = sample_key
            event['reason'] = '模拟采集派生展示快照；不是预约命令完成回执'
            for target, expected in [('roomOccupancy', occ_expected), ('orderEvent', event)]:
                derived.append({
                    'entity': target,
                    'sourceKey': 'bookingSample:' + alias,
                    'identityRecipe': copy.deepcopy(identity),
                    'expectedValues': expected,
                    'externalCreateEnabled': False,
                    'requires': 'owner-completed effect receipt and independent readback',
                })
    elif mode == 'live-stream':
        live_cycle_states = ['pending_confirmation', 'confirmed', 'in_use', 'completed']
        at = stamp(base_dt)
        last_order_key = None
        for idx in range(cycles):
            alias = f'L{idx + 1:02}'
            order_key = 'bookingOrder:' + alias
            last_order_key = order_key
            target_status = live_cycle_states[idx % len(live_cycle_states)]
            store_key = 'A2' if target_status == 'pending_confirmation' else 'A1'
            room_key = 'A2-R1' if store_key == 'A2' else ('A1-R1' if idx % 2 == 0 else 'A1-R2')
            merchant_key = 'A'
            start = base_dt - timedelta(hours=cycles - idx)
            end = start + timedelta(minutes=45)
            values = {
                'createdAt': at,
                'updatedAt': at,
                'updatedBy': 'simulator:live-stream',
                'orderNo': f'LIVE-{run_id}-{alias}',
                'merchantId': {'$ref': 'merchant:' + merchant_key},
                'storeId': {'$ref': 'store:' + store_key},
                'roomId': {'$ref': 'room:' + room_key},
                'customerSubject': 'fixture:customer:U1',
                'startAt': stamp(start),
                'endAt': stamp(end),
                'status': 'pending_confirmation',
                'resourceSnapshot': json.dumps({'merchantName': '模拟商户' + merchant_key, 'storeName': '模拟门店' + store_key, 'roomCode': room_key, 'storeTimeZone': 'UTC'}, ensure_ascii=False),
                'ruleSnapshot': json.dumps({'scopeKey': 'fixture:room:' + room_key, 'ruleVersion': 1, 'liveStream': True}),
                'referencePriceSnapshot': json.dumps({'description': '仅展示', 'notPaymentEvidence': True}, ensure_ascii=False),
            }
            direct.append({'entity': 'bookingOrder', 'key': order_key, 'values': values, 'createEnabled': True, 'blockedBy': []})
            steps = _transition_actions_for_order(order_key, target_status, 1)
            action_steps.extend(steps)
            final_states[order_key] = target_status
            final_versions[order_key] = 1 + len(steps)

            sample_key = f'FIXTURE-SAMPLE-{run_id}-{alias}'
            active = target_status in ('pending_confirmation', 'confirmed', 'in_use')
            hold_until = stamp(start - timedelta(minutes=15)) if target_status == 'pending_confirmation' else None
            released_at = stamp(end) if not active else None
            release_reason = 'live:' + target_status if not active else None
            sample_values = {
                'sampleKey': sample_key,
                'merchantId': {'$ref': 'merchant:' + merchant_key},
                'storeId': {'$ref': 'store:' + store_key},
                'roomId': {'$ref': 'room:' + room_key},
                'orderId': {'$ref': order_key},
                'startAt': stamp(start),
                'endAt': stamp(end),
                'status': target_status,
                'holdUntil': hold_until,
                'releasedAt': released_at,
                'releaseReason': release_reason,
                'createdAt': at,
                'updatedAt': at,
                'updatedBy': 'simulator:live-stream',
            }
            sample_creates.append({'entity': 'bookingSample', 'key': 'bookingSample:' + alias, 'values': sample_values, 'createEnabled': True, 'blockedBy': []})
            identity = {
                'field': 'sampleKey',
                'prefix': 'CRB-S-',
                'parts': [{'from': 'deployment', 'field': 'deploymentId'}, {'from': 'source', 'field': 'sampleKey', 'expected': sample_key}],
                'allocatedBy': 'script-effect-host',
            }
            occ_expected = {
                'merchantId': {'$ref': 'merchant:' + merchant_key},
                'storeId': {'$ref': 'store:' + store_key},
                'roomId': {'$ref': 'room:' + room_key},
                'orderId': {'$ref': order_key},
                'allocationRevision': 1,
                'startAt': stamp(start),
                'endAt': stamp(end),
                'state': 'active' if active else 'released',
                'holdUntil': hold_until,
                'releasedAt': released_at,
                'releaseReason': release_reason,
                'createdAt': at,
                'updatedAt': at,
                'updatedBy': 'simulator:live-stream',
            }
            evt_expected = {
                'orderId': {'$ref': order_key},
                'eventSequence': 1,
                'eventType': 'fixture_snapshot',
                'toStatus': target_status,
                'actorSubject': 'simulator:live-stream',
                'occurredAt': stamp(start),
                'operationId': sample_key,
                'reason': '模拟采集派生展示快照；不是预约命令完成回执',
                'createdAt': at,
                'updatedAt': at,
                'updatedBy': 'simulator:live-stream',
            }
            for target, expected in [('roomOccupancy', occ_expected), ('orderEvent', evt_expected)]:
                derived.append({
                    'entity': target,
                    'sourceKey': 'bookingSample:' + alias,
                    'identityRecipe': copy.deepcopy(identity),
                    'expectedValues': expected,
                    'externalCreateEnabled': False,
                    'requires': 'owner-completed effect receipt and independent readback',
                })

        # Add one live complaint + entry tied to last_order_key
        ckey = 'complaint:LC01'
        direct.append({
            'entity': 'complaint',
            'key': ckey,
            'values': {
                'caseNo': f'LIVE-CASE-{run_id}',
                'merchantId': {'$ref': 'merchant:A'},
                'storeId': {'$ref': 'store:A1'},
                'orderId': {'$ref': last_order_key},
                'complainantSubject': 'fixture:customer:U1',
                'category': 'service',
                'summary': '动态流实时工单验证',
                'status': 'open',
                'createdAt': at,
                'updatedAt': at,
                'updatedBy': 'simulator:live-stream',
            },
            'createEnabled': True,
            'blockedBy': [],
        })
        action_steps.append({
            'key': f'act:{ckey}:1:start-processing',
            'entity': 'complaint',
            'targetKey': ckey,
            'action': 'start-processing',
            'expectedVersion': 1,
            'fields': {},
        })
        final_states[ckey] = 'processing'
        final_versions[ckey] = 2
        direct.append({
            'entity': 'complaintEntry',
            'key': 'complaintEntry:LC01-1',
            'values': {
                'complaintId': {'$ref': ckey},
                'entrySequence': 1,
                'kind': 'message',
                'authorSubject': 'fixture:customer:U1',
                'content': '动态流工单受理说明',
                'visibility': 'customer',
                'occurredAt': at,
                'createdAt': at,
                'updatedAt': at,
                'updatedBy': 'simulator:live-stream',
            },
            'createEnabled': True,
            'blockedBy': [],
        })
        final_versions['complaintEntry:LC01-1'] = 1

    visible_business = len(direct)
    source_records = len(sample_creates)
    derived_count = len(derived)
    return {
        'schemaVersion': 'chess-room-booking.simulation-fixture-plan/v1',
        'version': '0.1.0-dev.5',
        'mode': mode,
        'cycles': cycles,
        'anchorUtc': baseline['anchorUtc'],
        'runId': run_id,
        'targetInstance': None,
        'executable': True,
        'plannedCapabilities': 46,
        'enabledCapabilities': 46,
        'blockedBy': [],
        'scenarioAssumptions': baseline['scenarioAssumptions'],
        'timeMode': 'live-window-stream' if mode == 'live-stream' else 'fixed-replay-not-current-business-state',
        'directCreates': direct,
        'actionSteps': action_steps,
        'sampleCreates': sample_creates,
        'derivedExpectations': derived,
        'finalStates': final_states,
        'finalVersions': final_versions,
        'counts': {
            'visibleBusinessRecords': visible_business,
            'actionSteps': len(action_steps),
            'sourceRecords': source_records,
            'derivedRecords': derived_count,
            'totalPersistedRecords': visible_business + source_records + derived_count,
            'directCreates': visible_business,
            'sampleCreates': source_records,
            'derivedCreates': derived_count,
        },
        'rules': [
            'resolve aliases to owner allocated exact IDs before writes',
            'create records in initial state without action-owned timestamps or subjects',
            'execute business state transitions strictly through Apps EntityAction with expectedVersion',
            'ingest bookingSample via Gateway reliable source after target order reaches post-action status',
            'both independent effects and readback required; never bypass state machines',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['generate', 'check', 'plan', 'simulation-plan'])
    parser.add_argument('--fixture', type=Path, default=ROOT / 'fixtures/baseline.json')
    parser.add_argument('--anchor-utc', default='2026-11-01T00:00:00Z', help='explicit offset required')
    parser.add_argument('--run-id', default='replay-20261101', help='synthetic batch identity for simulation-plan')
    parser.add_argument('--mode', choices=MODES, default='replay', help='simulation plan mode')
    parser.add_argument('--cycles', type=int, default=4, help='order/sample cycles for live-stream mode')
    parser.add_argument('--output', type=Path, help='new JSON output; existing files are preserved')
    args = parser.parse_args()
    if args.command == 'simulation-plan':
        result = simulation_plan(args.anchor_utc, args.run_id, mode=args.mode, cycles=args.cycles)
    elif args.command == 'generate':
        result = create(args.anchor_utc)
        validate(result)
    else:
        fixture = json.loads(args.fixture.expanduser().read_text())
        result = validate(fixture) if args.command == 'check' else plan(fixture)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        target = args.output.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x') as stream:
            stream.write(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
