import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import acceptance_resources as subject


class FakeDocker:
    host = 'unix:///test/docker.sock'

    def __init__(self):
        self.data = {kind: [] for kind in subject.KINDS}
        self.count = 0
        self.actions = []
        self.failure = None
        self.unavailable = False

    def engine(self):
        if self.unavailable:
            raise ValueError('daemon unavailable')
        return 'engine-1'

    def items(self, kind):
        self.engine()
        return copy.deepcopy(self.data[kind])

    def call(self, *args, **kwargs):
        self.engine()
        self.actions.append(args)
        before = self.failure == (args[:2], 'before')
        after = self.failure == (args[:2], 'after')
        if before:
            self.failure = None
            raise ValueError('injected failure')
        kind, action = args[:2]
        result = ''
        if action == 'create':
            self.count += 1
            labels = dict(args[i + 1].split('=', 1) for i, arg in enumerate(args) if arg == '--label')
            name = args[args.index('--name') + 1] if kind == 'container' else args[-1]
            item = {'Id': f'{self.count:064x}', 'Name': '/' + name if kind == 'container' else name,
                    'Labels': labels, 'Config': {'Labels': labels, 'Env': []}, 'HostConfig': {},
                    'Image': 'sha256:fixture', 'RestartCount': 0, 'Mounts': [],
                    'State': {'Running': False, 'StartedAt': '2026-10-01T00:00:00Z', 'ExitCode': 0}}
            if '--mount' in args:
                mount = args[args.index('--mount') + 1]
                item['root'] = mount.split('src=')[1].split(',')[0]
            self.data[kind].append(item)
            result = item['Id']
        elif action == 'rm':
            self.data[kind] = [x for x in self.data[kind] if x['Id'] != args[-1]]
        elif action in ('start', 'wait'):
            item = next(x for x in self.data[kind] if x['Id'] == args[-1])
            item['State']['Running'] = action == 'start'
            if action == 'start' and 'root' in item:
                for child in Path(item['root']).iterdir():
                    if child.name != subject.MARKER:
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                item['State']['Running'] = False
            if action == 'wait':
                result = '0'
        else:
            raise AssertionError(args)
        if after:
            self.failure = None
            raise ValueError('response lost')
        return result


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.docker = FakeDocker()
        self.owner = subject.Resources(self.base / 'state', self.docker, core=())
        self.root = self.base / 'workspace'

    def create(self):
        return self.owner.create('TEST', self.root, daemon=False)

    def plan(self, days=1):
        self.root.mkdir(exist_ok=True)
        script = self.root / 'verify.py'
        script.write_text("from pathlib import Path\nimport json\nfrom datetime import datetime,timezone\n"
                          "Path('result.json').write_text(json.dumps({'startedAt':datetime.now(timezone.utc).isoformat(),"
                          "'status':'passed','passed':True,'checks':[{'passed':True}],'cases':{'fixture':'passed'}}))\n")
        return {'reason': 'real boundary test', 'cases': ['fixture'],
                'notBefore': (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
                'inputs': [{'path': str(script), 'sha256': subject.sha(script)}],
                'checks': [{'cwd': str(self.root), 'argv': [sys.executable, str(script)]}],
                'evidence': [{'caseId': 'fixture', 'path': str(self.root / 'result.json')}]}

    def archived(self, record):
        archive = self.base / 'archive'
        subject.atomic(archive / 'manifest.json', {'files': []})
        record['archive'] = {'path': str(archive), 'sha256': subject.sha(archive / 'manifest.json')}
        record['phase'] = 'archived'
        self.owner.save(record)
        return record

    def test_create_persists_exact_identity_and_requires_archive(self):
        record = self.create()
        self.assertEqual(record['phase'], 'active')
        self.assertEqual(len(record['resources']), 2)
        self.assertTrue(all(len(x['id']) == 64 for x in record['resources']))
        with self.assertRaisesRegex(ValueError, 'archive'):
            self.owner.cleanup('TEST')
        self.assertEqual(self.owner.read('TEST')['phase'], 'active')

    def test_cleaned_requires_container_network_and_root_absence(self):
        self.archived(self.create())
        (self.root / 'private').write_text('not a public artifact')
        self.owner.cleanup('TEST')
        result = self.owner.report()
        self.assertTrue(result['allCleaned'])
        self.assertFalse(self.root.exists())
        self.assertTrue(all(not x for x in self.docker.data.values()))
        self.owner.cleanup('TEST')  # Idempotent confirmation.

    def test_create_failure_rolls_back_network_and_workspace(self):
        self.docker.failure = (('container', 'create'), 'before')
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(self.owner.read('TEST')['phase'], 'cleaned')
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_unknown_network_create_result_recovers_by_generation(self):
        self.docker.failure = (('network', 'create'), 'after')
        with self.assertRaises(ValueError):
            self.create()
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_unknown_container_create_result_recovers_same_id(self):
        self.docker.failure = (('container', 'create'), 'after')
        with self.assertRaises(ValueError):
            self.create()
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_start_failure_rolls_back(self):
        self.docker.failure = (('container', 'start'), 'before')
        with self.assertRaises(ValueError):
            self.create()
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_cleanup_failure_keeps_receipt_and_retry_confirms(self):
        self.archived(self.create())
        self.docker.failure = (('container', 'rm'), 'before')
        with self.assertRaises(ValueError):
            self.owner.cleanup('TEST')
        self.assertEqual(self.owner.report()['runs'][0]['status'], 'cleanup-failed')
        self.owner.cleanup('TEST')
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_unknown_remove_result_is_not_success_until_rechecked(self):
        self.archived(self.create())
        self.docker.failure = (('container', 'rm'), 'after')
        with self.assertRaises(ValueError):
            self.owner.cleanup('TEST')
        self.assertFalse(self.owner.report()['allCleaned'])
        self.owner.cleanup('TEST')
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_unavailable_daemon_never_means_absent(self):
        self.create()
        self.docker.unavailable = True
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.owner.report()
        self.assertTrue(self.root.exists())

    def test_name_reuse_is_blocked_without_deleting_replacement(self):
        self.archived(self.create())
        self.docker.data['container'][0]['Id'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'reused'):
            self.owner.cleanup('TEST')
        self.assertEqual(len(self.docker.data['container']), 1)
        self.assertFalse(self.owner.report()['passed'])

    def test_label_change_blocks_removal(self):
        self.archived(self.create())
        self.docker.data['container'][0]['Config']['Labels'][subject.RUN_LABEL] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'label'):
            self.owner.cleanup('TEST')
        self.assertEqual(len(self.docker.data['container']), 1)

    def test_legacy_stopped_container_and_old_network_block_clean_report(self):
        self.docker.call('container', 'create', '--name', 'acceptance-old-daemon', '--label', 'io.acceptance.run=OLD', 'alpine')
        self.docker.call('network', 'create', '--label', 'io.acceptance.run=OLDER', 'acceptance-older-outer')
        report = self.owner.report()
        self.assertFalse(report['passed'])
        self.assertEqual(len(report['unresolved']), 2)
        self.assertFalse(any(x[1] == 'rm' for x in self.docker.actions))

    def test_labeled_volume_is_inventory_residue(self):
        self.docker.data['volume'].append({'Name': 'old-volume', 'Labels': {subject.RUN_LABEL: 'OLD'}})
        self.assertEqual(self.owner.report()['unresolved'][0]['kind'], 'volume')

    def test_retained_is_explained_but_never_all_cleaned(self):
        self.create()
        self.owner.retain('TEST', self.plan())
        report = self.owner.report()
        self.assertTrue(report['passed'])
        self.assertFalse(report['allCleaned'])
        self.assertEqual(report['runs'][0]['status'], 'retained-pending')
        with self.assertRaisesRegex(ValueError, 'boundary'):
            self.owner.continue_run('TEST', self.base / 'archive')
        with self.assertRaises(ValueError):
            self.owner.cleanup('TEST')

    def test_deadline_elapsed_does_not_authorize_cleanup(self):
        self.create()
        self.owner.retain('TEST', self.plan(-1))
        self.assertEqual(self.owner.report()['runs'][0]['status'], 'verification-due')
        with self.assertRaises(ValueError):
            self.owner.cleanup('TEST')
        self.assertTrue(self.root.exists())

    def test_tampered_input_and_missing_retained_resource_fail_report(self):
        self.create()
        plan = self.plan()
        self.owner.retain('TEST', plan)
        Path(plan['inputs'][0]['path']).write_text('changed')
        self.assertFalse(self.owner.report()['passed'])
        self.docker.data['container'].clear()
        self.assertFalse(self.owner.report()['passed'])

    def test_continue_verifies_archives_and_then_cleans(self):
        self.create()
        self.owner.retain('TEST', self.plan(-1))
        self.owner.continue_run('TEST', self.base / 'archive')
        self.assertTrue((self.base / 'archive/0-result.json').exists())
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_failed_check_does_not_cleanup_or_retry_writes(self):
        self.create()
        plan = self.plan(-1)
        plan['checks'][0]['argv'] = [sys.executable, '-c', 'raise SystemExit(1)']
        self.owner.retain('TEST', plan)
        with self.assertRaises(subprocess.CalledProcessError):
            self.owner.continue_run('TEST', self.base / 'archive')
        self.assertEqual(self.owner.read('TEST')['phase'], 'verification-failed')
        with self.assertRaisesRegex(ValueError, 'unknown/failed'):
            self.owner.continue_run('TEST', self.base / 'archive')
        self.assertTrue(self.root.exists())

    def test_stale_result_cannot_pass(self):
        self.create()
        plan = self.plan(-1)
        plan['checks'][0]['argv'] = [sys.executable, '-c', 'pass']
        subject.atomic(self.root / 'result.json', {'passed': True, 'status': 'passed', 'startedAt': '2020-01-01T00:00:00Z',
                                                 'checks': [{'passed': True}], 'cases': {'fixture': 'passed'}})
        self.owner.retain('TEST', plan)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.owner.continue_run('TEST', self.base / 'archive')
        self.assertTrue(self.root.exists())

    def test_archive_failure_retries_archive_only(self):
        self.create()
        self.owner.retain('TEST', self.plan(-1))
        original = subject.atomic
        with patch.object(subject, 'atomic', side_effect=subject.atomic) as write:
            def fail_manifest(path, value):
                if Path(path).name == 'manifest.json':
                    raise OSError('archive disk full')
                original(path, value)
            write.side_effect = fail_manifest
            with self.assertRaises(OSError):
                self.owner.continue_run('TEST', self.base / 'archive')
        self.assertEqual(self.owner.read('TEST')['phase'], 'verified')
        with patch.object(subject.subprocess, 'run', side_effect=AssertionError('must not reverify')):
            self.owner.continue_run('TEST', self.base / 'archive')
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_archive_tamper_blocks_cleanup(self):
        record = self.archived(self.create())
        subject.atomic(self.base / 'archive/manifest.json', {'files': [], 'changed': True})
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.owner.cleanup('TEST')
        self.assertEqual(len(self.docker.data['container']), 1)

    def test_marker_mismatch_preserves_workspace(self):
        self.archived(self.create())
        subject.atomic(self.root / subject.MARKER, {'runId': 'OTHER'})
        with self.assertRaisesRegex(ValueError, 'marker'):
            self.owner.cleanup('TEST')
        self.assertTrue(self.root.exists())

    def test_shared_core_change_blocks_before_deletion(self):
        record = self.archived(self.create())
        record['coreBefore'] = {'changed': True}
        self.owner.save(record)
        count = len(self.docker.actions)
        with self.assertRaisesRegex(ValueError, 'core'):
            self.owner.cleanup('TEST')
        self.assertEqual(count, len(self.docker.actions))

    def test_rollback_cleanup_failure_can_retry_without_fake_archive(self):
        original = self.owner.remove_root
        with patch.object(self.owner, 'remove_root', side_effect=ValueError('cleanup failed')):
            self.docker.failure = (('container', 'create'), 'before')
            with self.assertRaises(ValueError):
                self.create()
        self.assertEqual(self.owner.read('TEST')['phase'], 'cleanup-failed')
        self.owner.cleanup('TEST')
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_unregistered_same_run_resource_prevents_cleanup(self):
        self.archived(self.create())
        self.docker.call('network', 'create', '--label', 'io.acceptance.run=TEST', 'acceptance-test-extra')
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            self.owner.cleanup('TEST')
        self.assertTrue(self.root.exists())

    def test_source_path_symlink_rejected(self):
        self.create()
        plan = self.plan()
        (self.root / 'alias.py').symlink_to('verify.py')
        plan['inputs'][0]['path'] = str(self.root / 'alias.py')
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.owner.retain('TEST', plan)

    def test_cancelled_verification_preserves_unknown_result(self):
        self.create()
        self.owner.retain('TEST', self.plan(-1))
        with patch.object(subject.subprocess, 'run', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.owner.continue_run('TEST', self.base / 'archive')
        self.assertEqual(self.owner.read('TEST')['phase'], 'verification-failed')
        self.assertTrue(self.root.exists())

    def test_real_process_is_registered_stopped_and_confirmed(self):
        self.create()
        script = self.root / 'mock.py'
        script.write_text('import time\ntime.sleep(120)\n')
        process = subprocess.Popen([sys.executable, str(script)], cwd=self.root)
        try:
            self.owner.track_process('TEST', process.pid, script)
            self.archived(self.owner.read('TEST'))
            self.owner.cleanup('TEST')
            self.assertIsNotNone(process.poll())
            self.assertTrue(self.owner.report()['allCleaned'])
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait()

    def test_unknown_process_blocks_root_deletion(self):
        self.archived(self.create())
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], cwd=self.root)
        try:
            with self.assertRaisesRegex(ValueError, 'unregistered process'):
                self.owner.cleanup('TEST')
            self.assertTrue(self.root.exists())
        finally:
            process.terminate()
            process.wait()

    def test_retirement_requires_exact_ids_and_archived_proof(self):
        record = self.create()
        record['phase'] = 'historical-unresolved'
        self.owner.save(record)
        proof = self.base / 'historical-result.json'
        subject.atomic(proof, {'status': 'blocked', 'supersededBy': 'NEW'})
        decision = {'runId': 'TEST', 'engine': self.docker.engine(),
                    'resourceIds': sorted(x['id'] for x in record['resources']),
                    'reason': 'old candidate superseded', 'pendingCases': [], 'disposition': 'superseded',
                    'references': [{'path': str(proof), 'sha256': subject.sha(proof)}]}
        wrong = copy.deepcopy(decision)
        wrong['resourceIds'] = ['wrong']
        with self.assertRaisesRegex(ValueError, 'IDs'):
            self.owner.retire('TEST', wrong, self.base / 'retirement')
        self.owner.retire('TEST', decision, self.base / 'retirement')
        self.assertTrue(self.root.exists())
        self.owner.cleanup('TEST')
        self.assertTrue(self.owner.report()['allCleaned'])

    def test_retained_run_cannot_be_retired_to_skip_natural_checks(self):
        self.create()
        self.owner.retain('TEST', self.plan())
        with self.assertRaisesRegex(ValueError, 'historical'):
            self.owner.retire('TEST', {}, self.base / 'retirement')

    def test_adopt_checks_archived_id_and_writable_mount_boundaries(self):
        self.docker.call('network', 'create', '--label', 'io.acceptance.run=OLD', 'acceptance-old-outer')
        self.docker.call('container', 'create', '--name', 'acceptance-old-daemon', '--label', 'io.acceptance.run=OLD', 'alpine')
        container = self.docker.data['container'][0]
        container['Mounts'] = [{'Type': 'bind', 'Source': str(self.root / 'isolated'), 'RW': True}]
        container['NetworkSettings'] = {'Networks': {'acceptance-old-outer': {'NetworkID': self.docker.data['network'][0]['Id']}}}
        proof = {'containerId': container['Id'], 'container': 'acceptance-old-daemon',
                 'network': 'acceptance-old-outer', 'privateDataRoot': str(self.root / 'isolated/docker-data'),
                 'sharedDockerSocketMounted': False, 'onlyOwnedRootWritable': True}
        proof_path = self.base / 'ownership.json'
        subject.atomic(proof_path, proof)
        container['Mounts'][0]['Source'] = '/var/run'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.owner.adopt('OLD', proof_path, self.root)
        container['Mounts'][0]['Source'] = str(self.root / 'isolated')
        adopted = self.owner.adopt('OLD', proof_path, self.root)
        self.assertEqual(adopted['phase'], 'historical-unresolved')
        self.assertEqual(len(adopted['resources']), 2)

    def test_cleanup_report_prevents_complete_acceptance_without_changing_case_counts(self):
        import platform_acceptance
        summary = {'complete': True, 'counts': {'passed': 212}, 'features': [],
                   'requiredCases': 212, 'requiredChecks': 212, 'coverage': 1, 'passRate': 1,
                   'catalogCoverage': {'complete': True}}
        output = self.base / 'acceptance.json'
        with patch.object(sys, 'argv', ['platform_acceptance.py', '--resource-state', str(self.owner.state), '--output', str(output)]), \
                patch.object(platform_acceptance, 'summarize', return_value=summary), \
                patch.object(subject.Resources, 'report', return_value={'passed': False, 'allCleaned': False}):
            self.assertEqual(platform_acceptance.main(), 2)
        saved = subject.load(output)
        self.assertTrue(saved['caseComplete'])
        self.assertFalse(saved['complete'])
        self.assertEqual(saved['counts']['passed'], 212)
        self.assertFalse(saved['catalogCoverage']['complete'])

    def test_b92_preflight_rejects_config_restart_and_health_changes(self):
        from acceptance_resources import check_candidate
        import hashlib
        after = {'Name': '/component', 'Image': 'sha256:original', 'Config': {'Env': ['MODE=test']},
                 'HostConfig': {}, 'Mounts': [], 'RestartCount': 0,
                 'State': {'Running': True, 'StartedAt': '2026-10-14', 'Health': {'Status': 'healthy'}}}
        configuration = {k: after[k] for k in ('Config', 'HostConfig', 'Mounts')}
        before = {'name': 'component', 'image': after['Image'], 'startedAt': '2026-10-14', 'restartCount': 0,
                  'configurationDigest': 'sha256:' + hashlib.sha256(json.dumps(configuration, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
        check_candidate(before, after)
        for variant in ('config', 'restart', 'health'):
            changed = copy.deepcopy(after)
            if variant == 'config':
                changed['Config']['Env'] = ['MODE=other']
            elif variant == 'restart':
                changed['RestartCount'] = 1
            else:
                changed['State']['Health']['Status'] = 'unhealthy'
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                check_candidate(before, changed)


if __name__ == '__main__':
    unittest.main()
