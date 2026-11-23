"""Offline oracle for the declared writeRules/v1 contract; not proof of server admission."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re


def instant(value):
    if not isinstance(value, str):
        raise ValueError('datetime required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('explicit UTC instant required')
    return parsed.astimezone(timezone.utc).replace(microsecond=parsed.microsecond // 1000 * 1000)


def validate_contract(entities):
    entities = {e['name']: e for e in entities}
    frozen = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/admission-contract-r4.json').read_text())
    actual = {name: {key: e['writeRules'].get(key, []) for key in ('assertions', 'checks')} for name, e in entities.items()}
    if actual != frozen:
        raise ValueError('admission declarations differ from reviewed R4 contract')
    for name, keys in {
        'staffAssignment': ['stores-merchant'],
        'bookingSample': ['store-merchant', 'room-store', 'room-merchant', 'order-merchant-id', 'order-store-id', 'order-room-id', 'order-start-at', 'order-end-at', 'order-status'],
        'bookingOrder': ['room-store', 'room-merchant'],
        'complaint': ['order-merchant-id', 'order-store-id', 'order-complainant-subject'],
    }.items():
        rules = entities[name]['writeRules']
        if rules['apiVersion'] != 'magic.entity-write-rules/v1' or not set(keys) <= {r['key'] for r in rules.get('assertions', [])}:
            raise ValueError('required relationship contract missing: ' + name)
    sample = entities['bookingSample']['writeRules']
    if not {'valid-interval', 'pending-hold', 'hold-before-start', 'nonpending-no-hold', 'active-no-release', 'active-no-reason', 'terminal-release', 'terminal-reason', 'expired-after-hold', 'historical-after-start'} <= {c['key'] for c in sample.get('checks', [])}:
        raise ValueError('sampling admission checks missing')


def _validate_row_rules(row, models, rows):
    entity = models[row['entity']]
    fields = {f['name']: f for f in entity['fields']}
    values = row['values']

    def matches(when):
        if not when:
            return True
        value = values.get(when['field'])
        return (value is not None) == when['present'] if 'present' in when else value in when['in']

    def resolve(model, record, path):
        name, *tail = path
        field = next(f for f in model['fields'] if f['name'] == name)
        value = record.get(name)
        if not field['type'].get('pkgPath'):
            return [instant(value) if value is not None and field['type']['name'] == 'datetime' else value]
        refs = value if isinstance(value, list) else [value]
        result = []
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {'$ref'} or ref['$ref'] not in rows:
                raise ValueError('missing authoritative alias: ' + row['key'])
            target, actual = rows[ref['$ref']]
            if tail:
                result.extend(resolve(models[target], actual, tail))
            else:
                result.append(ref['$ref'])
        return result

    for rule in entity['writeRules'].get('assertions', []):
        if not matches(rule.get('when')):
            continue
        right = resolve(entity, values, rule['right'])
        if len(right) != 1 or any(v != right[0] for v in resolve(entity, values, rule['left'])):
            raise ValueError('relationship/snapshot mismatch: ' + row['key'] + '/' + rule['key'])
    for rule in entity['writeRules'].get('checks', []):
        if not matches(rule.get('when')):
            continue
        v = values.get(rule['field'])
        op = rule['operator']
        if op in ('lt', 'lte'):
            other = values.get(rule['otherField'])
            if v is None or other is None:
                raise ValueError('missing temporal value: ' + rule['key'])
            if fields[rule['field']]['type']['name'] == 'datetime':
                v, other = instant(v), instant(other)
            good = v < other if op == 'lt' else v <= other
        elif op == 'matches':
            good = isinstance(v, str) and re.search(rule['pattern'], v) is not None
        else:
            good = v is None if op == 'null' else v is not None if op == 'notNull' else isinstance(v, str) and bool(v.strip())
        if not good:
            raise ValueError('record check mismatch: ' + row['key'] + '/' + rule['key'])


def _action_owned_fields(rules):
    owned = set()
    for action in rules.get('actions', []):
        for key in ('subjectField', 'timeField'):
            if action.get(key):
                owned.add(action[key])
        for name in action.get('inputFields', []):
            owned.add(name)
    return owned


def validate_plan(plan, entities):
    validate_contract(entities)
    models = {e['name']: e for e in entities}
    direct_rows = plan.get('directCreates', [])
    action_steps = plan.get('actionSteps', [])
    sample_rows = plan.get('sampleCreates', [])

    rows = {}
    versions = {}

    for row in direct_rows:
        entity_name = row['entity']
        if row['key'] in rows:
            raise ValueError('duplicate create key: ' + row['key'])
        rules = models[entity_name].get('writeRules', {})
        values = copy.deepcopy(row['values'])
        if rules.get('state'):
            state_field = rules['state']['field']
            initial = rules['state']['initial']
            if state_field in values and values[state_field] != initial:
                raise ValueError(f"create state must equal initial {initial}: {row['key']}")
            values.setdefault(state_field, initial)
        for owned in _action_owned_fields(rules):
            if owned in values and values[owned] is not None:
                raise ValueError(f"action-owned field forbidden on create: {row['key']}.{owned}")
        rows[row['key']] = (entity_name, values)
        versions[row['key']] = 1
        _validate_row_rules({'key': row['key'], 'entity': entity_name, 'values': values}, models, rows)

    for step in action_steps:
        target_key = step['targetKey']
        if target_key not in rows:
            raise ValueError('unknown action target: ' + target_key)
        entity_name, record = rows[target_key]
        if step['entity'] != entity_name:
            raise ValueError('action entity mismatch: ' + target_key)
        if step['expectedVersion'] != versions[target_key]:
            raise ValueError('action version conflict: ' + target_key)
        rules = models[entity_name].get('writeRules', {})
        state_rule = rules.get('state')
        if not state_rule:
            raise ValueError('entity has no state machine: ' + entity_name)
        rule = next((a for a in rules.get('actions', []) if a['key'] == step['action']), None)
        if not rule:
            raise ValueError(f"unknown action {step['action']} for {entity_name}")
        allowed_from = rule.get('fromStates') or [rule['from']]
        current_state = record.get(state_rule['field'])
        if current_state not in allowed_from:
            raise ValueError(f"illegal transition {current_state} via {step['action']} on {target_key}")
        submitted = step.get('fields', {})
        allowed_inputs = set(rule.get('inputFields', []))
        if not set(submitted) <= allowed_inputs:
            raise ValueError(f"undeclared input fields on action {step['action']}")
        for nb in rule.get('nonBlankInputs', []):
            val = submitted.get(nb)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"non-blank action input missing: {nb}")
        record.update(submitted)
        record[state_rule['field']] = rule['to']
        if rule.get('timeField'):
            record[rule['timeField']] = step.get('recordedAt') or record.get('updatedAt')
        if rule.get('subjectField'):
            record[rule['subjectField']] = step.get('actorSubject') or 'apps:operator'
        versions[target_key] += 1

    for row in sample_rows:
        if row['key'] in rows:
            raise ValueError('duplicate sample key: ' + row['key'])
        rows[row['key']] = (row['entity'], copy.deepcopy(row['values']))
        _validate_row_rules(row, models, rows)

    return {
        'directCreatesChecked': len(direct_rows),
        'actionStepsChecked': len(action_steps),
        'sampleCreatesChecked': len(sample_rows),
        'databaseExecuted': False,
        'liveAccepted': False,
    }
