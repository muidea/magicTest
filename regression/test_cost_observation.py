"""Offline helper safety and formal-tool integration; no Docker or platform run."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from regression import cost_observation as cost


ROOT = Path.home() / 'dataspace/magicPlatform'


class CostObservationTest(unittest.TestCase):
    def test_formal_parsers_and_summary_preserve_one_process_root_without_double_counting(self):
        collector, digest = cost.load_tool(ROOT, 'collect-qps-analysis.py')
        summary, _ = cost.load_tool(ROOT, 'summarize-qps-analysis.py')
        self.assertRegex(digest, '^sha256:[a-f0-9]{64}$')
        root = {'sampleID': 'process-1', 'operation': 'QueryEntityValue', 'totalMs': 5,
                'stagesMs': {'resolve': 3}, 'rpc': {'GET /api/v1/value/query/_': {'calls': 1, 'errors': 0, 'totalMs': 4}}}
        line = json.dumps({'msg': 'application cost sample', **root, 'password': 'DO-NOT-EXPORT'})
        parsed = collector.parse_log(line)
        self.assertNotIn('DO-NOT-EXPORT', json.dumps(parsed))
        events = [{'container': 'magicPanel', **parsed}, {'container': 'magicPanel', 'kind': 'sample',
                   'data': {'sampleID': 'process-1', 'operation': 'resolveApplicationEntity', 'totalMs': 3}}]
        result = summary.request_evidence(events)
        self.assertEqual(result['requestSamples'][0]['rootCount'], 1)
        self.assertEqual(result['requestSamples'][0]['root']['totalMs'], 5)
        self.assertIn('Nested stages and RPC totals overlap; do not sum them.', result['limits'])

    def config(self):
        return {'platformRoot': '/tmp/platform-executor-test/root', 'dockerDataRoot': '/tmp/platform-executor-test/docker-data',
                'daemonId': 'dedicated', 'containerId': 'a' * 64,
                'costObservation': {'containers': ['magicPanel', 'magicbase', 'magiccas', 'postgres']}}

    def inspect(self):
        return [{'Name': '/' + name, 'Id': str(i) * 64, 'Image': 'sha256:' + 'b' * 64,
                 'State': {'StartedAt': '2026-11-10T00:00:00Z', 'Running': True},
                 'Config': {'Env': ['SECRET=DO-NOT-EXPORT', 'MAGIC_PROFILE_WINDOW=1s', 'MAGIC_PROFILE_SAMPLE_EVERY=1']}}
                for i, name in enumerate(self.config()['costObservation']['containers'])]

    def test_topology_exports_only_original_identity_and_allowlisted_controls(self):
        config = self.config()
        info = {'ID': 'dedicated', 'DockerRootDir': config['dockerDataRoot'], 'Driver': 'overlay2'}
        with patch.object(cost, 'command', side_effect=[json.dumps(info), json.dumps(self.inspect())]), \
                patch.object(cost.os, 'uname', return_value=SimpleNamespace(nodename='a' * 12)), \
                patch.object(Path, 'resolve', lambda p: p):
            result = cost.topology(config)
        self.assertEqual(len(result), 4)
        self.assertNotIn('DO-NOT-EXPORT', json.dumps(result))

    def test_wrong_daemon_and_duplicate_container_controls_block_before_any_stats(self):
        config = self.config()
        good = {'ID': 'dedicated', 'DockerRootDir': config['dockerDataRoot'], 'Driver': 'overlay2'}
        for mode in ['daemon', 'duplicate', 'foreign-container', 'stopped']:
            info = copy.deepcopy(good)
            rows = self.inspect()
            if mode == 'daemon':
                info['ID'] = 'foreign'
            elif mode == 'duplicate':
                rows[0]['Config']['Env'].append('MAGIC_PROFILE_WINDOW=2s')
            elif mode == 'foreign-container':
                rows[0]['Name'] = '/foreign'
            else:
                rows[0]['State']['Running'] = False
            with patch.object(cost, 'command', side_effect=[json.dumps(info), json.dumps(rows)]), \
                    patch.object(cost.os, 'uname', return_value=SimpleNamespace(nodename='a' * 12)), \
                    patch.object(Path, 'resolve', lambda p: p):
                with self.assertRaises(ValueError):
                    cost.topology(config)

    def stats(self, collector, commit=1):
        row = {'datname': 'postgres', 'stats_reset': 'original'}
        for key in ['xact_commit', 'xact_rollback', 'blks_read', 'blks_hit', 'temp_bytes', 'deadlocks',
                    'tup_returned', 'tup_fetched', 'tup_inserted', 'tup_updated', 'tup_deleted', 'blk_read_time', 'blk_write_time']:
            row[key] = commit if key == 'xact_commit' else 0
        return {'database': [row], 'statementStatisticsAvailable': False, 'statements': None}

    def run_phase(self, mode):
        collector, _ = cost.load_tool(ROOT, 'collect-qps-analysis.py')
        before, after = self.stats(collector), self.stats(collector, 2)
        if mode == 'reset':
            after['database'][0]['stats_reset'] = 'reset'
        if mode == 'missing-database':
            after['database'] = []
        if mode == 'extension-change':
            after['statementStatisticsAvailable'] = True
        lines = '\n'.join('irrelevant' for _ in range(5000)) if mode == 'truncated' else 'irrelevant\n'
        proc = SimpleNamespace(stdout=lines, stderr='')
        emitted = []
        identity = [{'id': 'original'}]
        with patch.object(cost, 'topology', side_effect=[identity, [{'id': 'changed'}] if mode == 'drift' else identity]), \
                patch.object(cost, 'snapshot', side_effect=[before, after]), \
                patch.object(cost.subprocess, 'run', return_value=proc), \
                patch.object(cost.time, 'time', side_effect=[100, 110]):
            result = cost.phase({**self.config(), 'platformRoot': str(ROOT)}, 'idle', 8, '1' * 32,
                                emit=lambda text, **kw: emitted.append(json.loads(text)), sleep=lambda _: None)
        return result, emitted

    def test_phase_emits_ready_after_snapshot_and_retains_real_counter_interval(self):
        result, emitted = self.run_phase('success')
        self.assertEqual(emitted[0]['kind'], 'ready')
        self.assertEqual(emitted[0]['startedAt'], result['report']['startedAt'])
        self.assertEqual(result['report']['databaseDelta'][0]['delta']['xact_commit'], 1)
        self.assertFalse(result['summary']['sqlFingerprintAvailable'])

    def test_phase_rejects_drift_truncation_reset_and_incomplete_database_evidence(self):
        for mode in ['drift', 'truncated', 'reset', 'missing-database', 'extension-change']:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.run_phase(mode)

    def test_statement_fingerprint_int64_identity_is_preserved_as_exact_text(self):
        collector, _ = cost.load_tool(ROOT, 'collect-qps-analysis.py')
        before, after = self.stats(collector), self.stats(collector, 2)
        statement = {'dbid': 1, 'userid': 2, 'queryid': -9007199254740993, 'toplevel': True,
                     'calls': 1, 'total_exec_time': 2.5, 'rows': 1, 'shared_blks_hit': 0,
                     'shared_blks_read': 0, 'temp_blks_read': 0, 'temp_blks_written': 0}
        for item in [before, after]:
            item['statementStatisticsAvailable'] = True
            item['statements'] = {'reset': 'original', 'rows': [copy.deepcopy(statement)]}
        after['statements']['rows'][0]['calls'] = 2
        with patch.object(cost, 'topology', return_value=[{'id': 'original'}]), \
                patch.object(cost, 'snapshot', side_effect=[before, after]), \
                patch.object(cost.subprocess, 'run', return_value=SimpleNamespace(stdout='', stderr='')), \
                patch.object(cost.time, 'time', side_effect=[100, 110]):
            result = cost.phase({**self.config(), 'platformRoot': str(ROOT)}, 'idle', 8, '1' * 32,
                                emit=lambda *a, **kw: None, sleep=lambda _: None)
        self.assertEqual(result['report']['statementDelta'][0]['identity'], ['1', '2', '-9007199254740993', True])
        self.assertEqual(result['summary']['topStatementDelta'][0]['identity'][2], '-9007199254740993')


if __name__ == '__main__':
    unittest.main()
