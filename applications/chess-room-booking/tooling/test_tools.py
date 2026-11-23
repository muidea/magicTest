"""Offline checks for fixtures, three-stage admission/actions and package safety; no Live."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import admission_contract as admission
import fixture_tool as fixture
import package_tool as package


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture.create('2026-11-01T00:00:00Z')
        self.models = [package.read_json(p) for p in sorted((package.MODEL_ROOT / 'definition/application/entities').glob('*.json'))]

    def test_fixed_replay_and_utc_conversion(self):
        self.assertEqual(self.data, fixture.create('2026-11-01T08:00:00+08:00'))
        result = fixture.validate(self.data)
        self.assertEqual(result['totalRecords'], 52)
        self.assertEqual(result['activeOccupancyCount'], 3)
        self.assertFalse(fixture.plan(self.data)['executable'])

    def test_foreign_reference_and_merchant_escape_are_rejected(self):
        for field, value in [('merchantId', {'$ref': 'merchant:B'}), ('storeId', {'$ref': 'room:A1-R1'}), ('storeId', {'$ref': 'store:missing'})]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.data)
                data['records']['room'][0]['values'][field] = value
                with self.assertRaises(ValueError):
                    fixture.validate(data)

    def test_overlapping_active_allocations_are_rejected(self):
        data = copy.deepcopy(self.data)
        orders = {r['values']['status']: r for r in data['records']['bookingOrder']}
        confirmed, in_use = orders['confirmed'], orders['in_use']
        for name in ['startAt', 'endAt']:
            in_use['values'][name] = confirmed['values'][name]
        for row in data['records']['roomOccupancy']:
            if row['values']['orderId']['$ref'] == in_use['key']:
                for name in ['startAt', 'endAt']:
                    row['values'][name] = confirmed['values'][name]
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            fixture.validate(data)

    def test_adjacent_active_allocations_are_allowed(self):
        data = copy.deepcopy(self.data)
        orders = {r['values']['status']: r for r in data['records']['bookingOrder']}
        first, second = orders['confirmed'], orders['in_use']
        second['values']['startAt'] = first['values']['endAt']
        second['values']['endAt'] = fixture.stamp(fixture.instant(second['values']['startAt']) + fixture.timedelta(minutes=45))
        for row in data['records']['roomOccupancy']:
            if row['values']['orderId']['$ref'] == second['key']:
                for name in ['startAt', 'endAt']:
                    row['values'][name] = second['values'][name]
        fixture.validate(data)

    def test_terminal_hold_and_missing_allocation_are_rejected(self):
        for which in ['terminal', 'missing']:
            data = copy.deepcopy(self.data)
            if which == 'terminal':
                data['records']['roomOccupancy'][2]['values']['state'] = 'active'
            else:
                data['records']['roomOccupancy'] = []
            with self.subTest(which=which), self.assertRaises(ValueError):
                fixture.validate(data)

    def test_primary_key_invalid_type_and_unapproved_policy_are_rejected(self):
        for change in ['id', 'bool', 'policy', 'naive-time', 'duplicate-key']:
            data = copy.deepcopy(self.data)
            if change == 'id':
                data['records']['merchant'][0]['values']['id'] = 123
            elif change == 'bool':
                data['records']['room'][0]['values']['capacity'] = True
            elif change == 'policy':
                data['scenarioAssumptions']['approvedBusinessDefaults'] = True
            elif change == 'naive-time':
                data['records']['bookingOrder'][0]['values']['startAt'] = '2026-11-01T08:00:00'
            else:
                data['records']['merchant'].append(copy.deepcopy(data['records']['merchant'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                fixture.validate(data)

    def test_complaint_must_belong_to_same_customer(self):
        self.data['records']['complaint'][0]['values']['complainantSubject'] = 'fixture:customer:U1'
        with self.assertRaisesRegex(ValueError, 'complaint'):
            fixture.validate(self.data)

    def test_store_rule_allows_null_room_and_validates_scope_identity(self):
        values = self.data['records']['bookingRule'][0]['values']
        values['roomId'] = None
        values['scopeKey'] = 'fixture:' + values['storeId']['$ref']
        fixture.validate(self.data)
        values['scopeKey'] = 'fixture:store:B1'
        with self.assertRaisesRegex(ValueError, 'scopeKey'):
            fixture.validate(self.data)

    def test_invalid_local_date_is_rejected(self):
        self.data['records']['openingException'][0]['values']['localDate'] = '2026-02-30'
        with self.assertRaises(ValueError):
            fixture.validate(self.data)

    def test_replay_seed_and_live_stream_plans_validate_against_models(self):
        replay = fixture.simulation_plan('2026-11-01T00:00:00Z', 'unit-replay', mode='replay')
        self.assertTrue(replay['executable'])
        self.assertEqual(len(replay['directCreates']), 34)
        self.assertEqual(len(replay['actionSteps']), 18)
        self.assertEqual(len(replay['sampleCreates']), 9)
        self.assertEqual(len(replay['derivedExpectations']), 18)
        self.assertEqual(admission.validate_plan(replay, self.models), {
            'directCreatesChecked': 34,
            'actionStepsChecked': 18,
            'sampleCreatesChecked': 9,
            'databaseExecuted': False,
            'liveAccepted': False,
        })

        seed = fixture.simulation_plan('2026-11-01T00:00:00Z', 'unit-seed', mode='seed')
        self.assertEqual(len(seed['directCreates']), 20)
        self.assertEqual(len(seed['actionSteps']), 4)
        self.assertEqual(len(seed['sampleCreates']), 0)
        self.assertEqual(admission.validate_plan(seed, self.models)['directCreatesChecked'], 20)

        live = fixture.simulation_plan('2026-11-22T08:00:00Z', 'unit-live', mode='live-stream', cycles=6)
        self.assertEqual(len(live['directCreates']), 28)  # 20 master + 6 orders + 1 complaint + 1 entry
        self.assertEqual(len(live['sampleCreates']), 6)
        self.assertEqual(len(live['derivedExpectations']), 12)
        self.assertGreater(len(live['actionSteps']), 4)
        self.assertEqual(admission.validate_plan(live, self.models)['sampleCreatesChecked'], 6)

        for run_id in ('', '../escape', 'a b', '中', 'x' * 65):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                fixture.simulation_plan('2026-11-01T00:00:00Z', run_id)

    def test_admission_rejects_non_initial_states_action_owned_fields_and_bad_transitions(self):
        plan = fixture.simulation_plan('2026-11-01T00:00:00Z', 'unit-neg', mode='replay')

        # 1. Creating bookingOrder directly in non-initial status is forbidden
        bad_state = copy.deepcopy(plan)
        next(r for r in bad_state['directCreates'] if r['key'] == 'bookingOrder:O02')['values']['status'] = 'confirmed'
        with self.assertRaisesRegex(ValueError, 'initial'):
            admission.validate_plan(bad_state, self.models)

        # 2. Creating bookingOrder with action-owned confirmedAt is forbidden
        bad_owned = copy.deepcopy(plan)
        next(r for r in bad_owned['directCreates'] if r['key'] == 'bookingOrder:O02')['values']['confirmedAt'] = '2026-11-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'action-owned'):
            admission.validate_plan(bad_owned, self.models)

        # 3. Stale expectedVersion or illegal transition in actionSteps is forbidden
        bad_ver = copy.deepcopy(plan)
        bad_ver['actionSteps'][0]['expectedVersion'] = 9
        with self.assertRaisesRegex(ValueError, 'version'):
            admission.validate_plan(bad_ver, self.models)

        bad_tx = copy.deepcopy(plan)
        bad_tx['actionSteps'].append({'key': 'act:bad', 'entity': 'bookingOrder', 'targetKey': 'bookingOrder:O01', 'action': 'complete', 'expectedVersion': 1, 'fields': {}})
        with self.assertRaisesRegex(ValueError, 'illegal transition'):
            admission.validate_plan(bad_tx, self.models)

        # 4. Sample constraints & contract drift still fail
        bad_sample = copy.deepcopy(plan)
        sample = bad_sample['sampleCreates'][0]
        sample['values']['holdUntil'] = None
        with self.assertRaises(ValueError):
            admission.validate_plan(bad_sample, self.models)

        for fault in ('missing', 'wrong-path', 'wrong-condition'):
            changed = copy.deepcopy(self.models)
            model = next(e for e in changed if e['name'] == 'bookingSample')
            if fault == 'missing':
                model['writeRules']['checks'].pop()
            elif fault == 'wrong-path':
                model['writeRules']['assertions'][0]['right'] = ['orderId']
            else:
                model['writeRules']['checks'][1]['when'] = {'field': 'status', 'in': ['completed']}
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                admission.validate_contract(changed)


class PackageSafetyTests(unittest.TestCase):
    def test_current_closeout_source_contract(self):
        self.assertEqual(package.validate_source()['key'], 'chess-room-booking')

    def test_gates_assets_actions_and_protections_cannot_be_silently_removed(self):
        for mutation in ('gate', 'appendOnlySample', 'bookingOrderUpdateCap', 'staffRequired', 'extraBlockFile', 'missingAsset', 'nonTreeNav', 'badActionKey'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                shutil.copytree(package.MODEL_ROOT / 'definition', root / 'definition')
                staff_path = root / 'definition/application/entities/staffAssignment.json'
                sample_path = root / 'definition/application/entities/bookingSample.json'
                order_path = root / 'definition/application/entities/bookingOrder.json'
                pages_path = root / 'definition/application/pages/definition.json'
                if mutation == 'gate':
                    value = package.read_json(staff_path)
                    value['serviceExpose']['capabilities'][2]['enabled'] = False
                    staff_path.write_text(json.dumps(value))
                elif mutation == 'appendOnlySample':
                    value = package.read_json(sample_path)
                    value['writeRules']['appendOnly'] = False
                    sample_path.write_text(json.dumps(value))
                elif mutation == 'bookingOrderUpdateCap':
                    value = package.read_json(order_path)
                    next(c for c in value['serviceExpose']['capabilities'] if c['key'] == 'update')['enabled'] = True
                    order_path.write_text(json.dumps(value))
                elif mutation == 'staffRequired':
                    value = package.read_json(staff_path)
                    next(f for f in value['fields'] if f['name'] == 'storeIds')['spec']['constraint'] = ''
                    staff_path.write_text(json.dumps(value))
                elif mutation == 'extraBlockFile':
                    (root / 'definition/application/blocks/extra.go').write_text('package block')
                elif mutation == 'missingAsset':
                    (root / 'definition/assets/appearance-canvas.png').unlink()
                elif mutation == 'nonTreeNav':
                    pages = package.read_json(pages_path)
                    pages['navigationMode'] = 'top'
                    pages_path.write_text(json.dumps(pages))
                else:
                    value = package.read_json(order_path)
                    value['writeRules']['actions'][0]['key'] = 'badCamelCase'
                    order_path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    package.validate_source(root)

    def test_duplicate_json_keys_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source.json'
            path.write_text('{"key":1,"key":2}')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                package.read_json(path)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'existing'
            destination.mkdir()
            marker = destination / 'keep'
            marker.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                package.write_bundle(destination, {'package.zip': b'new'})
            self.assertEqual(marker.read_bytes(), b'original')
            self.assertEqual(list(destination.iterdir()), [marker])

    def test_human_account_templates_require_application_viewer_not_raw_data_read(self):
        for bad_role in ('application-data-read', None):
            with self.subTest(bad_role=bad_role), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                shutil.copytree(package.MODEL_ROOT / 'definition', root / 'definition')
                meta_path = root / 'definition/application/metadata.json'
                meta = package.read_json(meta_path)
                frontdesk = next(t for t in meta['authorization']['templates'] if t['key'] == 'frontdesk')
                roles = [r for r in frontdesk['roleKeys'] if r != 'application-viewer']
                if bad_role:
                    roles.insert(0, bad_role)
                frontdesk['roleKeys'] = roles
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
                with self.assertRaisesRegex(ValueError, 'application-viewer'):
                    package.validate_source(root)

    def test_live_stream_order_event_actor_subject_matches_sample_updated_by(self):
        live_plan = fixture.simulation_plan('2026-11-22T08:00:00Z', 'live-actor', mode='live-stream', cycles=4)
        sample_updated_by = {r['key']: r['values']['updatedBy'] for r in live_plan['sampleCreates']}
        events = [d for d in live_plan['derivedExpectations'] if d['entity'] == 'orderEvent']
        self.assertEqual(len(events), 4)
        for item in events:
            self.assertEqual(item['expectedValues']['actorSubject'], sample_updated_by[item['sourceKey']])
            self.assertEqual(item['expectedValues']['actorSubject'], 'simulator:live-stream')


if __name__ == '__main__':
    unittest.main()
