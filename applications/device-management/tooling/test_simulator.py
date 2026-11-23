#!/usr/bin/env python3
"""Behavioral recovery tests and actual HTTPS/JSON Gateway adapter integration."""
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulator.client import Gateway, RemoteFailure
from simulator.common import ENTITIES, Failure, gateway_result, identity, instant, secret, utc
from simulator.config import configure
from simulator.journal import Journal
from simulator.plan import build, cycle, plan_digest
from simulator.runner import Runner


class MemoryGateway:
    def __init__(self, derive_alarms=False):
        self.rows = {entity: [] for entity in ENTITIES}
        self.next_id = 9223372036854700000
        self.writes = []
        self.fail_after_commit = False
        self.fail_get = False
        self.derive_alarms = derive_alarms

    def scan(self, entity):
        return copy.deepcopy(sorted(self.rows[entity], key=lambda row: int(row['id'])))

    def get(self, entity, value_id):
        if self.fail_get:
            self.fail_get = False
            raise RemoteFailure()
        return copy.deepcopy(next(row for row in self.rows[entity] if identity(row['id']) == identity(value_id)))

    def _derive_threshold_alarms(self, telemetry_row):
        dev = telemetry_row['device']
        sampled_at = telemetry_row['sampledAt']
        rules = [
            ('temperature', 10, 75, 'major'),
            ('vibration', None, 4.5, 'critical'),
            ('loadPercent', 20, 90, 'minor'),
        ]
        for metric, low, high, sev in rules:
            val = telemetry_row.get(metric)
            if val is None:
                continue
            direction = None
            if low is not None and val < low:
                direction = 'below'
            elif high is not None and val > high:
                direction = 'above'
            if direction:
                self.next_id += 1
                self.rows['alarm'].append({
                    'id': self.next_id,
                    'code': f'DTA-{self.next_id}',
                    'device': copy.deepcopy(dev),
                    'title': f'{metric}: {direction}',
                    'severity': sev,
                    'status': 'open',
                    'occurredAt': sampled_at,
                    'version': 1,
                })

    def call(self, entity, operation, fields=None, value_id=None, query=None):
        self.writes.append((entity, operation, copy.deepcopy(fields)))
        fields = copy.deepcopy(fields)
        if entity == 'alarm' and operation == 'create':
            raise RemoteFailure(403)
        if operation == 'create':
            if entity == 'telemetry':
                for existing in self.rows['telemetry']:
                    if (identity(existing['device']['id']) == identity(fields['device']['id'])
                            and instant(existing['sampledAt']) == instant(fields['sampledAt'])):
                        if (existing.get('temperature') == fields.get('temperature')
                                and existing.get('vibration') == fields.get('vibration')
                                and existing.get('loadPercent') == fields.get('loadPercent')):
                            return {'value': copy.deepcopy(existing)}
                        raise RemoteFailure(409)
            self.next_id += 1
            row = dict(fields, id=self.next_id)
            if entity in ('location', 'category', 'device', 'alarm'):
                row['version'] = 1
            if entity == 'device':
                row.update(connectionStatus='unknown', lastSeenAt=None)
            self.rows[entity].append(row)
            if entity == 'telemetry' and self.derive_alarms:
                self._derive_threshold_alarms(row)
        else:
            row = next(row for row in self.rows[entity] if identity(row['id']) == identity(value_id))
            if entity == 'device' and 'lifecycleStatus' in fields:
                raise RemoteFailure(400)
            if int(row['version']) != int(fields['version']):
                raise RemoteFailure(200, 21)
            row.update(fields)
            row['version'] = int(fields['version']) + 1
        if self.fail_after_commit:
            self.fail_after_commit = False
            raise RemoteFailure()
        return {'value': copy.deepcopy(row)}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.config = configure('https://example.test/api/v1/gateway/services/device_management_service',
                                str(self.root / 'key'), str(self.root), 'AB12CD34EF56', '2026-10-23T00:00:00Z',
                                scenario='current-window-v1')
        self.plan = build(self.config)
        self.gateway = MemoryGateway()
        self.binding = plan_digest(self.config, self.plan)

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, journal):
        runner = Runner(self.config, self.plan, journal, self.gateway)
        runner.preflight()
        return runner

    def test_full_plan_roundtrip_conditional_updates_and_no_replay(self):
        self.assertEqual(len(self.plan['backfill']), 500)
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            r.phase('bootstrap')
            r.phase('backfill')
            result = r.verify()
            self.assertEqual(result['counts'], self.plan['expected'])
            self.assertEqual(result['onlineDenominator'], 24)
            self.assertEqual(result['online'], 18)
            writes = len(self.gateway.writes)
            r.phase('bootstrap')
            r.phase('backfill')
            self.assertEqual(len(self.gateway.writes), writes)
            self.assertTrue(all(int(value) > 2 ** 53 for value in j.mapping().values()))
            r.update('category', 'CAT-PUMP', {'name': '更新水泵'}, {'name': '水泵'})
            r.update('device', 'DEV-001', {'connectionStatus': 'offline'}, {'connectionStatus': 'online'})
            r.verify()
            with self.assertRaises(Failure):
                r.update('device', 'DEV-001', {'lifecycleStatus': 'running'}, {'lifecycleStatus': 'standby'})

    def test_committed_create_lost_response_recovers_without_second_post(self):
        op = self.plan['bootstrap'][0]
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            self.gateway.fail_after_commit = True
            with self.assertRaises(RemoteFailure):
                r.execute(op)
            self.assertEqual(j.intent(op['key'])['state'], 'unknown')
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            r.execute(op)
            self.assertEqual(len(self.gateway.writes), 1)
            self.assertEqual(j.intent(op['key'])['state'], 'satisfied')

    def test_get_failure_after_response_has_durable_returned_id(self):
        op = self.plan['bootstrap'][0]
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            self.gateway.fail_get = True
            with self.assertRaises(RemoteFailure):
                r.execute(op)
            self.assertIsNotNone(j.intent(op['key'])['id'])
            r.execute(op)
            self.assertEqual(len(self.gateway.writes), 1)

    def test_unknown_telemetry_cannot_be_replayed_or_other_write_started(self):
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            r.phase('bootstrap')
            op = self.plan['backfill'][0]
            self.gateway.fail_after_commit = True
            with self.assertRaises(RemoteFailure):
                r.execute(op)
            writes = len(self.gateway.writes)
            with self.assertRaisesRegex(Failure, 'unknown telemetry'):
                r.execute(op)
            with self.assertRaisesRegex(Failure, 'original unfinished'):
                r.execute(self.plan['backfill'][1])
            self.assertEqual(len(self.gateway.writes), writes)

    def test_lock_changed_plan_and_unowned_collision(self):
        with Journal(self.root, self.binding):
            with self.assertRaises(Failure):
                Journal(self.root, self.binding)
        with self.assertRaises(Failure):
            Journal(self.root, 'changed-plan')
        op = self.plan['bootstrap'][0]
        self.gateway.call('location', 'create', fields=op['fields'])
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            with self.assertRaisesRegex(Failure, 'outside this prepared intent'):
                r.execute(op)

    def test_collect_cycle_restart_uses_original_time_and_values(self):
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            r.phase('bootstrap')
            expected = cycle(self.config, 0, '2026-10-23T02:03:04.000Z')
            j.remember('cycle:0', expected)
            r.execute(expected[0])
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            r.collect(1)
            self.assertEqual(j.meta('completedCycles'), 1)
            self.assertEqual(len(self.gateway.rows['telemetry']), 18)
            self.assertEqual({r['sampledAt'] for r in self.gateway.rows['telemetry']}, {'2026-10-23T02:03:04.000Z'})
            self.assertEqual(j.meta('cycle:0'), expected)

    def test_live_stream_seed_and_four_rotating_cycles(self):
        live_root = Path(self.temp.name) / 'live'
        live_root.mkdir(mode=0o700)
        cfg = configure('https://example.test/api/v1/gateway/services/device_management_service',
                        str(live_root / 'key'), str(live_root), '112233445566', '2026-10-23T00:00:00Z',
                        scenario='live-stream-v1')
        cfg['run']['intervalSeconds'] = 1
        plan = build(cfg)
        gw = MemoryGateway(derive_alarms=True)
        with Journal(live_root, plan_digest(cfg, plan)) as j:
            r = Runner(cfg, plan, j, gw)
            r.preflight()
            r.phase('bootstrap')
            r.phase('backfill')
            # Run 4 rotating cycles: steady, thermal-ramp (alarms), DEV-005 offline drop, reconnect
            for idx, ts in enumerate(('2026-10-23T01:00:00.000Z', '2026-10-23T01:01:00.000Z',
                                      '2026-10-23T01:02:00.000Z', '2026-10-23T01:03:00.000Z')):
                ops = cycle(cfg, idx, ts)
                j.remember(f'cycle:{idx}', ops)
                for op in ops:
                    r.execute(op)
                j.set_meta('completedCycles', idx + 1)
            result = r.verify()
            self.assertEqual(result['counts']['device'], 12)
            self.assertEqual(result['counts']['telemetry'], 192 + 8 + 8 + 7 + 8)
            # 1 minor boundary alarm from backfill (loadPercent=0 on DEV-002 hour 0) + 3 cycle stage-1 threshold alarms
            self.assertEqual(result['derivedAlarms']['total'], 4)
            self.assertEqual(result['derivedAlarms']['bySeverity'], {'major': 1, 'minor': 2, 'critical': 1})
            self.assertEqual(result['online'], 8)
            self.assertEqual(result['onlineDenominator'], 12)

    def test_replay_v3_derives_nine_alarms_idempotent_and_conflict(self):
        replay_root = Path(self.temp.name) / 'replay'
        replay_root.mkdir(mode=0o700)
        cfg = configure('https://example.test/api/v1/gateway/services/device_management_service',
                        str(replay_root / 'key'), str(replay_root), 'AABBCCDDEEFF', scenario='replay-v3')
        plan = build(cfg)
        gw = MemoryGateway(derive_alarms=True)
        with Journal(replay_root, plan_digest(cfg, plan)) as j:
            r = Runner(cfg, plan, j, gw)
            r.preflight()
            outcome = r.replay_checks()
            self.assertEqual(outcome['status'], 'pass')
            self.assertEqual(outcome['derivedAlarms']['total'], 9)
            self.assertEqual(outcome['derivedAlarms']['bySeverity'], {'major': 3, 'critical': 2, 'minor': 4})
            self.assertEqual(len(gw.rows['telemetry']), 10)

    def test_foreign_mutation_and_duplicate_sample_are_not_hidden(self):
        with Journal(self.root, self.binding) as j:
            r = self.runner(j)
            r.phase('bootstrap')
            r.phase('backfill')
            row = self.gateway.rows['device'][0]
            original = row['name']
            row['name'] = 'manual edit'
            with self.assertRaises(Failure):
                r.verify()
            row['name'] = original
            duplicate = copy.deepcopy(self.gateway.rows['telemetry'][0])
            duplicate['id'] = self.gateway.next_id + 1
            self.gateway.rows['telemetry'].append(duplicate)
            with self.assertRaises(Failure):
                r.verify()

    def test_fixture_rules_determinism_and_precision(self):
        self.assertEqual(build(self.config), self.plan)
        self.assertTrue(any(op['fields'].get('loadPercent') == 0 for op in self.plan['backfill']))
        self.assertTrue(any(op['entity'] == 'telemetry' and op['fields'].get('temperature') is None for op in self.plan['backfill']))
        for op in self.plan['bootstrap']:
            if op['operation'] == 'create':
                self.assertNotIn('connectionStatus', op['fields'])
                self.assertNotIn('lastSeenAt', op['fields'])
        for op in self.plan['backfill']:
            self.assertNotEqual(op['entity'], 'alarm')
        for invalid in (True, 1.0, '1e3', '-1', '01', 9223372036854775808):
            with self.subTest(invalid=invalid), self.assertRaises(Failure):
                identity(invalid)

    def test_public_utc_representation_does_not_weaken_strict_input(self):
        value = {'values': [{'sampledAt': '2026-10-23 05:00:00.000',
                             'device': {'lastSeenAt': None}, 'name': '2026-10-23 05:00:00.000'}]}
        normalized = gateway_result(value)['values'][0]
        self.assertEqual(normalized['sampledAt'], '2026-10-23T05:00:00.000Z')
        self.assertEqual(normalized['device']['lastSeenAt'], None)
        self.assertEqual(normalized['name'], value['values'][0]['name'])
        with self.assertRaises(Failure):
            instant('2026-10-23 05:00:00.000')


class HTTPSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        os.chmod(cls.root, 0o700)
        cls.cert, cls.key = cls.root / 'ca.crt', cls.root / 'tls.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(cls.key),
                        '-out', str(cls.cert), '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cls.requests = []
        cls.fault = ''

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                cls.requests.append((self.command, self.path, self.headers.get('Authorization')))
                p = urlsplit(self.path)
                if cls.fault == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', 'https://other.invalid/')
                    self.end_headers()
                    return
                if cls.fault == 'unauthorized':
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'FAKE-SECRET-DO-NOT-PRINT')
                    return
                page = int(parse_qs(p.query).get('_pageNum', ['1'])[0])
                all_rows = [{'id': 9223372036854700000 + n, 'sampledAt': '2026-10-23 01:02:03.004'} for n in range(1, 102)]
                rows = all_rows[(page - 1) * 100:page * 100]
                self.reply({'values': rows, 'pagination': {'total': 101 if cls.fault != 'total-drift' or page == 1 else 102,
                    'pageNum': page, 'pageSize': 100}})

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                cls.requests.append((self.command, self.path, json.loads(raw)))
                self.reply({'error': {'code': 21, 'message': 'FAKE-SECRET-DO-NOT-PRINT'}})

            def reply(self, body):
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        cls.server = ThreadingHTTPServer(('localhost', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, cls.key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        type(self).requests = []
        type(self).fault = ''
        self.run = tempfile.TemporaryDirectory(dir=self.root)
        self.directory = Path(self.run.name)
        key = self.directory / 'api.key'
        key.write_text('not-a-real-subscription-key')
        key.chmod(0o600)
        self.config = configure(f'https://localhost:{self.server.server_port}/api/v1/gateway/services/device_management_service',
                                str(key), str(self.directory), 'AABBCCDDEEFF', '2026-10-23T00:00:00Z')
        self.config['tls'] = {'caFile': str(self.cert), 'trustLeaf': False}
        self.config['run']['qps'] = 10

    def tearDown(self):
        self.run.cleanup()

    def test_actual_https_pagination_apikey_and_wire_int64(self):
        with Journal(self.directory, 'https') as journal:
            gateway = Gateway(self.config, journal)
            rows = gateway.scan('device')
            self.assertEqual(len(rows), 101)
            self.assertEqual(rows[0]['sampledAt'], '2026-10-23T01:02:03.004Z')
            self.assertTrue(all(r[2] == 'ApiKey not-a-real-subscription-key' for r in type(self).requests))
            with self.assertRaises(RemoteFailure) as error:
                gateway.call('telemetry', 'create', {'device': {'id': '9223372036854700001'}, 'loadPercent': 0})
            self.assertNotIn('FAKE-SECRET', str(error.exception))
            self.assertEqual(type(self).requests[-1][2]['device']['id'], 9223372036854700001)
            self.assertEqual(sum(r[0] == 'POST' for r in type(self).requests), 1)

    def test_redirect_auth_fail_and_changed_total_fail_closed(self):
        for fault in ('redirect', 'unauthorized', 'total-drift'):
            with self.subTest(fault=fault):
                type(self).fault = fault
                with Journal(self.directory, 'https') as journal:
                    gateway = Gateway(self.config, journal)
                    with self.assertRaises(Failure) as error:
                        gateway.scan('device')
                    self.assertNotIn('FAKE-SECRET', str(error.exception))

    def test_key_permissions_and_symlink(self):
        path = Path(self.config['credentialFile'])
        path.chmod(0o644)
        with self.assertRaises(Failure):
            secret(path)
        path.chmod(0o600)
        link = self.directory / 'symlink.key'
        link.symlink_to(path)
        with self.assertRaises(OSError):
            secret(link)


if __name__ == '__main__':
    unittest.main()
