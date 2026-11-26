"""Fault-oriented offline three-stage ingestion & action tests. No sockets or real credentials."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

import simulation_tool as sim


CONTRACT = sim.load(Path(__file__).parent / 'testdata/write-identity.json')
SCOPE = CONTRACT['identity']


class FakeGateway:
    def __init__(self, models):
        self.models = models
        self.records = {name: [] for name in models}
        self.writes = 0
        self.failure = None
        self.last_fields = None

    def scan(self, entity):
        return copy.deepcopy(self.records[entity])

    def get(self, entity, value_id):
        return copy.deepcopy(next(r for r in self.records[entity] if str(r['id']) == str(value_id)))

    def call(self, entity, operation, fields=None):
        assert operation == 'create'
        self.writes += 1
        self.last_fields = fields
        if self.failure == 'transport':
            raise sim.Failure('transport')
        rules = self.models[entity].get('writeRules', {})
        state_rule = rules.get('state')
        if state_rule:
            sf = state_rule['field']
            if sf in fields and fields[sf] != state_rule['initial']:
                raise sim.Failure('Gateway HTTP 400; body withheld')
        value_id = 9007199254740993 + self.writes
        stored = {'id': value_id, 'version': 1, **copy.deepcopy(fields)}
        if state_rule and state_rule['field'] not in stored:
            stored[state_rule['field']] = state_rule['initial']
        self.records[entity].append(stored)
        receipt = {
            'apiVersion': 'magic.entity-source-write/v1' if entity == 'bookingSample' else 'magic.entity-value-write/v1',
            'operationId': CONTRACT['operationId'],
            'operation': 'create',
            'entity': '/chessRoomBooking/' + entity,
            'id': str(value_id),
            'version': '1',
            'identity': copy.deepcopy(SCOPE),
            'effectCount': 2 if entity == 'bookingSample' else 0,
        }
        if self.failure == 'identity':
            receipt['identity']['generation'] = 2
        if self.failure == 'receipt':
            receipt['id'] = str(value_id + 1)
        return {'receipt': receipt, 'value': {'id': value_id}}, CONTRACT['operationId']


class FakeActionClient:
    def __init__(self, gateway):
        self.gateway = gateway
        self.calls = 0
        self.failure = None

    def execute(self, scope, entity, action, record_id, expected_version, operation_id, fields=None):
        assert type(scope['generation']) is int and scope['generation'] > 0
        assert type(scope['executionEpoch']) is int and scope['executionEpoch'] > 0
        self.calls += 1
        if self.failure == 'transport':
            raise sim.Failure('Apps action transport failure; action outcome may be unknown')
        record = next(r for r in self.gateway.records[entity] if str(r['id']) == str(record_id))
        if int(record['version']) != int(expected_version):
            raise sim.Failure('Apps action HTTP 409; body withheld')
        rules = self.gateway.models[entity]['writeRules']
        state_field = rules['state']['field']
        rule = next(a for a in rules['actions'] if a['key'] == action)
        allowed_from = rule.get('fromStates') or [rule['from']]
        if record[state_field] not in allowed_from:
            raise sim.Failure('Apps action HTTP 400; body withheld')
        record[state_field] = rule['to']
        if fields:
            record.update(copy.deepcopy(fields))
        if rule.get('timeField'):
            record[rule['timeField']] = record.get('updatedAt')
        if rule.get('subjectField'):
            record[rule['subjectField']] = 'apps:operator'
        record['version'] += 1
        return {
            'value': {
                'apiVersion': 'magic.entity-action/v1',
                'operationId': operation_id,
                'identity': copy.deepcopy(scope),
                'inputDigest': 'sha256:' + '0' * 64,
                'entity': '/chessRoomBooking/' + entity,
                'action': action,
                'id': str(record_id),
                'version': str(record['version']),
                'state': record[state_field],
                'subject': 'apps:operator',
                'executedAt': '2026-11-01T00:00:00Z',
            }
        }


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.models = sim.definitions()
        self.plan = sim.checked_plan(sim.simulation_plan('2026-11-01T00:00:00Z', 'unit-replay', mode='replay'), self.models)
        self.journal = sim.Journal(Path(self.temp.name) / 'private', {'test': 'binding'})
        self.gateway = FakeGateway(self.models)
        self.actions = FakeActionClient(self.gateway)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def add_effects(self):
        sources = {r['key']: r for r in self.plan['sampleCreates']}
        for index, item in enumerate(self.plan['derivedExpectations']):
            expected = sim.resolve(item['expectedValues'], self.journal.data['records'])
            expected['sampleKey'] = sim.derived_identity(SCOPE['deploymentId'], sources[item['sourceKey']]['values']['sampleKey'])
            expected['id'] = 9007199254741993 + index
            self.gateway.records[item['entity']].append(expected)

    def test_full_three_stage_replay_and_no_rewrites(self):
        res = sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(res['directConfirmed'], 34)
        self.assertEqual(res['actionsConfirmed'], 18)
        self.assertEqual(res['samplesConfirmed'], 9)
        self.assertEqual(self.gateway.writes, 43)  # 34 direct + 9 bookingSample
        self.assertEqual(self.actions.calls, 18)

        self.add_effects()
        verified = sim.verify(self.plan, self.models, self.gateway, self.journal)
        self.assertEqual(verified['totalRecords'], 61)
        self.assertEqual(verified['actionsConfirmed'], 18)
        self.assertEqual(verified['derivedReadbackConfirmed'], 18)
        self.assertFalse(verified['taskReceiptsVerified'])
        self.assertFalse(verified['liveAccepted'])

        # Re-running does zero additional writes or actions
        sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(self.gateway.writes, 43)
        self.assertEqual(self.actions.calls, 18)
        self.assertEqual(len(self.gateway.records['staffAssignment'][0]['storeIds']), 2)
        self.assertEqual(self.gateway.records['bookingOrder'][7]['status'], 'completed')
        self.assertEqual(self.gateway.records['bookingOrder'][7]['version'], 4)
        self.assertTrue(all(e['id'].isdigit() for e in self.journal.data['records'].values()))
        self.assertEqual(self.journal.path.stat().st_mode & 0o777, 0o600)

    def test_seed_and_live_stream_modes_execute_cleanly(self):
        for mode, cycles in (('seed', 4), ('live-stream', 3)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                gw = FakeGateway(self.models)
                ac = FakeActionClient(gw)
                jn = sim.Journal(Path(tmp) / 'state', {'mode': mode})
                try:
                    p = sim.checked_plan(sim.simulation_plan('2026-11-22T06:00:00Z', f'run-{mode}', mode=mode, cycles=cycles), self.models)
                    res = sim.run(p, self.models, gw, jn, action_client=ac)
                    if mode == 'seed':
                        self.assertEqual(res['directConfirmed'], 20)
                        self.assertEqual(res['actionsConfirmed'], 4)
                        self.assertEqual(res['samplesConfirmed'], 0)
                        v = sim.verify(p, self.models, gw, jn)
                        self.assertEqual(v['totalRecords'], 20)
                    else:
                        self.assertEqual(res['directConfirmed'], 25)  # 20 + 3 orders + 1 complaint + 1 entry
                        self.assertEqual(res['samplesConfirmed'], 3)
                        sources = {r['key']: r for r in p['sampleCreates']}
                        for idx, item in enumerate(p['derivedExpectations']):
                            exp = sim.resolve(item['expectedValues'], jn.data['records'])
                            exp['sampleKey'] = sim.derived_identity(SCOPE['deploymentId'], sources[item['sourceKey']]['values']['sampleKey'])
                            exp['id'] = 9007199254745000 + idx
                            gw.records[item['entity']].append(exp)
                        v = sim.verify(p, self.models, gw, jn)
                        self.assertEqual(v['derivedReadbackConfirmed'], 6)
                        self.assertEqual(v['totalRecords'], 34)
                finally:
                    jn.close()

    def test_stale_expected_version_raises_409_without_retry(self):
        sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        merchant_id = self.gateway.records['merchant'][0]['id']
        calls_before = self.actions.calls
        with self.assertRaisesRegex(sim.Failure, 'HTTP 409'):
            self.actions.execute(SCOPE, 'merchant', 'suspend', merchant_id, expected_version=1, operation_id='d' * 32)
        self.assertEqual(self.actions.calls, calls_before + 1)

    def test_unknown_write_or_action_is_never_resent_even_after_restart(self):
        for fault in ('transport', 'receipt'):
            with self.subTest(fault=fault):
                self.gateway.failure = fault
                with self.assertRaises(sim.Failure):
                    sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
                self.gateway.failure = None
                writes = self.gateway.writes
                with self.assertRaisesRegex(sim.Failure, 'unknown'):
                    sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
                self.assertEqual(self.gateway.writes, writes)

        with tempfile.TemporaryDirectory() as tmp:
            gw = FakeGateway(self.models)
            ac = FakeActionClient(gw)
            jn = sim.Journal(Path(tmp) / 'act-unknown', {'test': 'action'})
            try:
                ac.failure = 'transport'
                with self.assertRaisesRegex(sim.Failure, 'action outcome may be unknown'):
                    sim.run(self.plan, self.models, gw, jn, action_client=ac)
                calls = ac.calls
                ac.failure = None
                with self.assertRaisesRegex(sim.Failure, 'action outcome unknown'):
                    sim.run(self.plan, self.models, gw, jn, action_client=ac)
                self.assertEqual(ac.calls, calls)
            finally:
                jn.close()

    def test_received_identity_survives_failed_read_and_is_only_read_back(self):
        original = self.gateway.get

        def fail(*_):
            raise sim.Failure('read failed')

        self.gateway.get = fail
        with self.assertRaisesRegex(sim.Failure, 'read failed'):
            sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(self.journal.data['records']['merchant:A']['status'], 'received')
        self.gateway.get = original
        sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(self.gateway.writes, 43)
        self.assertEqual(self.actions.calls, 18)

    def test_protocol_identity_width_rejects_old_fixture(self):
        scope = copy.deepcopy(SCOPE)
        scope['deploymentId'] = 'a' * 64
        with self.assertRaisesRegex(sim.Failure, 'execution identity'):
            sim.receipt_identity({'identity': scope})
        result, operation = self.gateway.call('merchant', 'create', fields={'code': 'fixture'})
        with self.assertRaisesRegex(sim.Failure, 'operation mismatch'):
            sim.accept_create(result, 'c' * 64, {'entity': 'merchant'}, self.journal)
        self.assertEqual(sim.receipt_identity(result['receipt']), sim.normalize_execution_identity(SCOPE))

    def test_mixed_int_and_string_execution_identity_between_gateway_and_apps(self):
        original_execute = self.actions.execute

        def string_identity_execute(*args, **kwargs):
            result = original_execute(*args, **kwargs)
            scope = result['value']['identity']
            for key in ('installationId', 'generation', 'executionEpoch'):
                scope[key] = str(scope[key])
            return result

        self.actions.execute = string_identity_execute
        summary = sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertGreater(summary['actionsConfirmed'], 0)
        self.assertIs(type(self.journal.data['identity']['installationId']), str)
        self.assertIs(type(self.journal.data['identity']['generation']), int)
        self.assertIs(type(self.journal.data['identity']['executionEpoch']), int)
        self.add_effects()
        verified = sim.verify(self.plan, self.models, self.gateway, self.journal)
        self.assertEqual(verified['derivedReadbackConfirmed'], 18)

    def test_action_client_serializes_int_generation_epoch_and_str_installation_id(self):
        captured = {}

        class OkResponse:
            status = 200

            class Headers:
                @staticmethod
                def get_content_type():
                    return 'application/json'

            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"value":{"id":"1"}}'

        class WireOpener:
            def open(self, req, timeout=30):
                captured['body'] = sim.strict_json(req.data.decode('utf-8'))
                return OkResponse()

        client = object.__new__(sim.ActionClient)
        client.url = 'https://example.test/api/v1/apps/entity/action/execute/'
        client.token = 'tok'
        client.application_key = 'chess-room-booking'
        client.opener = WireOpener()
        client.requests, client.last = 0, 0
        mixed_scope = dict(SCOPE, installationId=9007199254740993, generation='2', executionEpoch='3')
        client.execute(mixed_scope, 'merchant', 'approve', 100, 1, 'e' * 32)
        sent_id = captured['body']['identity']
        self.assertIs(type(sent_id['installationId']), str)
        self.assertEqual(sent_id['installationId'], '9007199254740993')
        self.assertIs(type(sent_id['generation']), int)
        self.assertEqual(sent_id['generation'], 2)
        self.assertIs(type(sent_id['executionEpoch']), int)
        self.assertEqual(sent_id['executionEpoch'], 3)

    def test_nonempty_preflight_never_writes(self):
        self.gateway.records['room'].append({'id': 1})
        with self.assertRaisesRegex(sim.Failure, 'empty'):
            sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(self.gateway.writes, 0)

    def test_scope_change_blocks_dependents_and_following_runs(self):
        original = self.gateway.get

        def switch(*args):
            result = original(*args)
            self.gateway.failure = 'identity'
            return result

        self.gateway.get = switch
        with self.assertRaisesRegex(sim.Failure, 'identity changed'):
            sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(self.gateway.writes, 2)
        with self.assertRaisesRegex(sim.Failure, 'unknown'):
            sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.assertEqual(self.gateway.writes, 2)

    def test_partial_and_wrong_effects_never_claim_completion(self):
        sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        with self.assertRaisesRegex(sim.Failure, 'incomplete'):
            sim.verify(self.plan, self.models, self.gateway, self.journal)
        self.add_effects()
        self.gateway.records['roomOccupancy'][0]['orderId'] = {'id': 42}
        with self.assertRaisesRegex(sim.Failure, 'reference mismatch'):
            sim.verify(self.plan, self.models, self.gateway, self.journal)
        self.assertNotIn('readbackVerified', self.journal.data)

    def test_state_binding_lock_and_invalid_plan(self):
        with self.assertRaises(OSError):
            sim.Journal(self.journal.directory, {'test': 'binding'})
        self.plan['directCreates'][0]['values']['name'] = 'changed'
        with self.assertRaisesRegex(sim.Failure, 'frozen'):
            sim.checked_plan(self.plan, self.models)
        with self.assertRaises(sim.Failure):
            sim.strict_json('{"a":1,"a":2}')
        for url in ('http://host/api/v1/gateway/services/key', 'https://user:pass@host/api/v1/gateway/services/key',
                    'https://host/api/v1/gateway/services/key?apiKey=value'):
            with self.assertRaises(sim.Failure):
                sim.endpoint(url)

    def test_utc_null_collection_and_scalar_comparison(self):
        model = self.models['staffAssignment']
        expected = {'effectiveFrom': '2026-11-01T00:00:00Z', 'storeIds': [{'id': 9007199254740993}, {'id': 42}]}
        actual = {'effectiveFrom': '2026-11-01 00:00:00.000', 'storeIds': [{'id': 42}, {'id': '9007199254740993'}]}
        sim.compare(actual, expected, model)
        actual['storeIds'][1]['id'] = 9007199254740992.0
        with self.assertRaises(sim.Failure):
            sim.compare(actual, expected, model)

    def test_transport_writes_once_and_unexpected_identity_precision_is_rejected(self):
        from urllib.error import URLError

        class BrokenOpener:
            calls = 0

            def open(self, *_a, **_kw):
                self.calls += 1
                raise URLError('private transport diagnostic')

        gateway = object.__new__(sim.Gateway)
        gateway.requests, gateway.last = 0, 0
        gateway.url, gateway.key, gateway.opener = 'https://example.test/service', 'test-only', BrokenOpener()
        with self.assertRaisesRegex(sim.Failure, 'transport'):
            gateway.call('merchant', 'create', fields={'code': 'fixture'})
        self.assertEqual(gateway.opener.calls, 1)
        for value in (True, 1.0, '01', '-1', '9223372036854775808'):
            with self.subTest(value=value), self.assertRaises(sim.Failure):
                sim.identity(value)

    def test_request_and_pagination_budget(self):
        gateway = object.__new__(sim.Gateway)
        gateway.requests = 500
        with self.assertRaisesRegex(sim.Failure, 'budget'):
            gateway.call('merchant', 'query')
        pages = iter([
            ({'pagination': {'total': 2, 'pageNum': 1, 'pageSize': 100}, 'values': [{'id': 1}]}, ''),
        ])
        gateway.call = lambda *_a, **_kw: next(pages)
        with self.assertRaisesRegex(sim.Failure, 'incomplete'):
            gateway.scan('merchant')

    def test_secret_file_modes_and_no_symlink(self):
        path = Path(self.temp.name) / 'key'
        path.write_text('fake-test-key')
        os.chmod(path, 0o600)
        self.assertEqual(sim.secret(path), 'fake-test-key')
        os.chmod(path, 0o644)
        with self.assertRaises(sim.Failure):
            sim.secret(path)
        alias = Path(self.temp.name) / 'link'
        alias.symlink_to(path)
        with self.assertRaises(OSError):
            sim.secret(alias)

    def test_inspect_instance_readonly_on_empty_and_populated_gateway(self):
        empty_res = sim.inspect_instance(self.models, self.gateway)
        self.assertTrue(empty_res['empty'])
        self.assertEqual(empty_res['totalRecords'], 0)
        self.assertTrue(empty_res['readOnly'])
        self.assertFalse(empty_res['liveAccepted'])
        self.assertEqual(set(empty_res['counts']), set(self.models))
        self.assertEqual(self.gateway.writes, 0)

        sim.run(self.plan, self.models, self.gateway, self.journal, action_client=self.actions)
        self.add_effects()
        writes_before = self.gateway.writes
        pop_res = sim.inspect_instance(self.models, self.gateway)
        self.assertFalse(pop_res['empty'])
        self.assertEqual(pop_res['totalRecords'], 61)
        self.assertTrue(pop_res['readOnly'])
        self.assertFalse(pop_res['liveAccepted'])
        self.assertEqual(pop_res['counts']['bookingOrder'], 9)
        self.assertEqual(self.gateway.writes, writes_before)


if __name__ == '__main__':
    unittest.main()
