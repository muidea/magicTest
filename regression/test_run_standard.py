"""Exercise report gates without browser mutations or product acceptance claims."""
import copy
import hashlib
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest import mock

from regression import run_standard

from regression.run_standard import ROOT, environment_lock, finish, load_owner, run_browser, tool_hashes


class ReportGatesTest(unittest.TestCase):
    def test_launch_deadline_stops_only_driver_and_preserves_original_state(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            state = directory / 'state.json'
            original = b'{"resources":[{"operationId":"original-unknown"}]}\n'
            state.write_bytes(original)
            result = run_browser([sys.executable, '-B', '-c', 'import time;time.sleep(60)'], directory, directory, startup_seconds=0.1)
            self.assertEqual(result, -signal.SIGKILL)
            self.assertEqual(state.read_bytes(), original)
            evidence = json.loads((directory / 'browser-startup.json').read_text())
            self.assertEqual(evidence['status'], 'blocked')
            self.assertNotIn('original-unknown', json.dumps(evidence))

    def test_post_launch_marker_does_not_timeout_or_retry_a_business_driver(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            marker = directory / 'browser-started.json'
            program = 'import pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text("{}\\n");time.sleep(0.3);sys.exit(17)'
            result = run_browser([sys.executable, '-B', '-c', program, str(marker)], directory, directory, startup_seconds=0.2)
            self.assertEqual(result, 17)
            self.assertFalse((directory / 'browser-startup.json').exists())
            with self.assertRaisesRegex(ValueError, 'must not reuse'):
                run_browser([sys.executable, '-B', '-c', 'raise Exception("must not launch")'], directory, directory)

    def test_early_driver_error_is_preserved_without_fabricated_startup_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result = run_browser([sys.executable, '-B', '-c', 'import sys;sys.exit(23)'], directory, directory, startup_seconds=1)
            self.assertEqual(result, 23)
            self.assertFalse((directory / 'browser-startup.json').exists())

    def test_tool_identity_includes_runtime_helpers(self):
        hashes = tool_hashes()
        for name in ['directory.cjs', 'resource_lifecycle.cjs', 'negative_mutations.cjs', 'public_probe.cjs', 'standard_cases.cjs', 'snapshot_cases.py', 'model_fixture.py']:
            self.assertEqual(hashes[name], 'sha256:' + hashlib.sha256((ROOT / 'regression' / name).read_bytes()).hexdigest())
        self.assertFalse(any(name.endswith('.test.cjs') for name in hashes))
        self.assertFalse(any(name.startswith('test_') for name in hashes))

    def test_runtime_snapshot_config_dry_run_wiring_without_private_reads_or_process_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            target = str(Path(folder) / 'not-read-machine-config.json')
            config.write_text(json.dumps({'runtimeSnapshotConfig': target, 'cases': ['F035-006']}))
            with mock.patch.object(sys, 'argv', ['run_standard.py', '--config', str(config), '--suite', 'abnormal', '--dry-run']), \
                    mock.patch.object(run_standard.subprocess, 'run', return_value=mock.Mock(returncode=0)) as driver:
                self.assertEqual(run_standard.main(), 0)
            command = driver.call_args.args[0]
            self.assertEqual(command[command.index('--suite') + 1], 'abnormal')
            self.assertEqual(command[command.index('--runtime-snapshot-config') + 1], target)
            self.assertEqual(command[-2:], ['--dry-run', 'true'])
            self.assertFalse(Path(target).exists())
            with mock.patch.object(sys, 'argv', ['run_standard.py', '--config', str(config), '--dry-run']):
                with self.assertRaisesRegex(ValueError, 'required standard case IDs'):
                    run_standard.main()

    def test_runtime_snapshot_config_rejects_empty_or_non_path_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            for value in ['', '  ', None, 7, {}, []]:
                config.write_text(json.dumps({'runtimeSnapshotConfig': value}))
                with mock.patch.object(sys, 'argv', ['run_standard.py', '--config', str(config), '--dry-run']), \
                        mock.patch.object(run_standard.subprocess, 'run') as driver:
                    with self.assertRaisesRegex(ValueError, 'non-empty private file path'):
                        run_standard.main()
                    driver.assert_not_called()

    def test_runtime_machine_inputs_archive_only_config_digest_without_reading_bearer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config_file = root / 'machine.json'
            payload = {'origin': 'http://127.0.0.1:12345', 'tokenFile': str(root / 'must-not-read-token'),
                       'instanceId': 'unit-gateway', 'incarnation': 'unit-boot', 'endpointId': 7, 'clientId': 'unit-client'}
            config_file.write_text(json.dumps(payload))
            health = root / 'unit-preflight.json'
            health.write_text(json.dumps({'results': [{'status': 'blocked'}]}))
            owner = mock.Mock()
            owner.digest.return_value = 'unit-catalog-digest'
            owner.capture_health.return_value = health
            config = {'output': str(root / 'evidence'), 'runtimeSnapshotConfig': str(config_file)}
            with mock.patch.object(run_standard.tempfile, 'mkdtemp', return_value=str(root / 'private')), \
                    mock.patch.object(run_standard, 'run_browser') as browser, \
                    mock.patch('builtins.print'):
                self.assertEqual(run_standard.execute_live(config, root / 'catalog.json', owner, {}, [], root / 'credentials', ['F035-006']), 2)
                browser.assert_not_called()
            archived = next((root / 'evidence').glob('*/inputs.json')).read_text()
            result = json.loads(archived)
            self.assertEqual(result['runtimeSnapshotConfigDigest'], 'sha256:' + hashlib.sha256(config_file.read_bytes()).hexdigest())
            self.assertNotIn('must-not-read-token', archived)
            self.assertNotIn('unit-client', archived)
            self.assertFalse(Path(payload['tokenFile']).exists())

    @classmethod
    def setUpClass(cls):
        catalog_path = ROOT.parent / 'docs/acceptance/platform-catalog.json'
        cls.owner = load_owner(catalog_path)
        cls.catalog = json.loads(catalog_path.read_text())
        cls.owner.validate_catalog(cls.catalog)

    def run_report(self, *, cleaned=True, drift=False, browser_exit=0, healthy=True, suite='standard'):
        with tempfile.TemporaryDirectory() as private:
            directory = Path(private)
            for folder in ['browser', 'health-after']:
                (directory / folder).mkdir()
                (directory / folder / 'core-health.json').write_text('unit fixture, not Live evidence\n')
            if cleaned is not None:
                cleanup = directory / 'browser/attempts/unit'
                cleanup.mkdir(parents=True)
                (cleanup / 'cleanup.json').write_text(json.dumps({'allCleaned': cleaned}))
            versions = {name: 'sha256:' + '0' * 64 for name in self.owner.CORE}
            environment = {'name': 'unit-only', 'versions': versions, 'configurationDigest': 'sha256:' + '1' * 64}
            environment['fingerprint'] = self.owner.digest({'versions': versions, 'configurationDigest': environment['configurationDigest']})
            entry = {'caseId': 'F059-001', 'suite': suite, 'status': 'passed', 'method': 'live',
                     'role': 'unit-fixture', 'namespace': 'unit', 'resource': 'unit',
                     'observedAt': '2026-11-05T00:00:00+00:00', 'actual': 'Unit-only report input',
                     'environmentFingerprint': environment['fingerprint'],
                     'evidence': [{'kind': 'operational', 'path': 'core-health.json',
                                   'sha256': 'sha256:' + hashlib.sha256((directory / 'browser/core-health.json').read_bytes()).hexdigest()}]}
            before = {'schema': 'magic.acceptance.results/v1', 'baseline': self.catalog['baseline'],
                      'catalogDigest': self.owner.digest(self.catalog), 'runId': 'unit',
                      'environment': environment, 'results': [{**entry, 'suite': 'standard'}]}
            after = copy.deepcopy(before)
            browser = copy.deepcopy(before)
            browser['results'] = []
            for case in self.catalog['cases']:
                if not case['required'] or not any(part['suite'] == suite for part in case['execution']):
                    continue
                proof = copy.deepcopy(entry)
                proof['caseId'] = case['id']
                proof['method'] = 'live' if 'live' in case['methods'] else 'browser'
                proof['evidence'][0]['kind'] = proof['method']
                browser['results'].append(proof)
            if drift:
                after['environment']['configurationDigest'] = 'sha256:' + '2' * 64
            if not healthy:
                after['results'][0].update(status='failed', reason='Unit unhealthy fixture', defectId='UNIT')
            return finish(self.owner, self.catalog, before, after, browser, directory, browser_exit, suite=suite)

    def test_complete_requires_all_gates(self):
        report = self.run_report()
        self.assertTrue(report['complete'])
        self.assertEqual(report['suite'], 'standard')
        self.assertEqual(report['requiredChecks'], 184)
        abnormal = self.run_report(suite='abnormal')
        self.assertTrue(abnormal['complete'])
        self.assertEqual(abnormal['suite'], 'abnormal')
        self.assertEqual(abnormal['requiredChecks'], 28)

    def test_case_pass_does_not_hide_cleanup_failure_or_missing_receipt(self):
        for cleaned in [False, None]:
            with self.subTest(cleaned=cleaned):
                report = self.run_report(cleaned=cleaned)
                self.assertTrue(report['caseComplete'])
                self.assertFalse(report['complete'])

    def test_candidate_drift_invalidates_completion(self):
        report = self.run_report(drift=True)
        self.assertFalse(report['executionGates']['sameDeploymentBeforeAfter'])
        self.assertFalse(report['complete'])

    def test_nonzero_browser_exit_prevents_success(self):
        self.assertFalse(self.run_report(browser_exit=2)['complete'])

    def test_unhealthy_candidate_prevents_success(self):
        self.assertFalse(self.run_report(healthy=False)['complete'])

    def test_environment_lock_excludes_same_origin_and_releases_after_error(self):
        with tempfile.TemporaryDirectory() as private:
            credentials = Path(private) / 'credentials.json'
            credentials.write_text(json.dumps({'origin': 'https://regression-lock-unit.invalid'}))
            with self.assertRaisesRegex(RuntimeError, 'unit interruption'):
                with environment_lock(credentials):
                    with self.assertRaisesRegex(ValueError, 'no browser mutations started'):
                        with environment_lock(credentials):
                            self.fail('Second same-environment run entered mutation scope')
                    raise RuntimeError('unit interruption')
            with environment_lock(credentials):
                pass

    def test_delivery_fixture_dry_run_does_not_read_private_files_and_validates_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config.json'
            target = str(root / 'uncreated-delivery-fixture.json')
            config.write_text(json.dumps({'deliveryFixtureConfig': target}))
            with mock.patch.object(sys, 'argv', ['run_standard.py', '--config', str(config), '--dry-run']), \
                    mock.patch.object(run_standard.subprocess, 'run', return_value=mock.Mock(returncode=0)) as driver:
                self.assertEqual(run_standard.main(), 0)
            command = driver.call_args.args[0]
            self.assertEqual(command[command.index('--delivery-fixture-config') + 1], target)
            self.assertFalse(Path(target).exists())
            for invalid in ['', '   ', None, 3, {}, []]:
                config.write_text(json.dumps({'deliveryFixtureConfig': invalid}))
                with mock.patch.object(sys, 'argv', ['run_standard.py', '--config', str(config), '--dry-run']), \
                        mock.patch.object(run_standard.subprocess, 'run') as driver:
                    with self.assertRaisesRegex(ValueError, 'deliveryFixtureConfig requires a non-empty private file path'):
                        run_standard.main()
                    driver.assert_not_called()

    def _run_fixture_preflight(self, root, *, state_payload=None, manifest_payload=None, members_exists=False, stage_exit=0):
        private_root = root / 'private-fixture'
        private_root.mkdir(exist_ok=True)
        if state_payload is not None:
            (private_root / 'fixture-state.json').write_text(json.dumps(state_payload))
        if manifest_payload is not None:
            (private_root / 'fixture-manifest.json').write_text(json.dumps(manifest_payload))
        if members_exists:
            (private_root / 'member-credentials.json').write_text(json.dumps({'manager': {'account': 'rg-mgr'}}))
        fixture_cfg = root / 'fixture-config.json'
        fixture_cfg.write_text(json.dumps({'mode': 'local-panel', 'daemonId': 'daemon-1', 'privateRoot': str(private_root)}))
        health = root / 'health-before.json'
        health.write_text(json.dumps({'results': [{'status': 'passed'}], 'environment': {'name': 'unit'}}))
        owner = mock.Mock()
        owner.digest.return_value = 'unit-digest'
        owner.capture_health.return_value = health
        config = {'output': str(root / 'evidence'), 'deliveryFixtureConfig': str(fixture_cfg)}

        def fake_subprocess(cmd, **_kwargs):
            action = cmd[-1]
            if stage_exit != 0 and action == 'publish':
                return mock.Mock(returncode=stage_exit, stdout='', stderr='boom')
            if action == 'members':
                (private_root / 'fixture-state.json').write_text(json.dumps({
                    'daemonId': 'daemon-1', 'stage': 'members-ready', 'commands': [], 'originalCasForms': []}))
                (private_root / 'fixture-manifest.json').write_text(json.dumps({
                    'status': 'published', 'daemonId': 'daemon-1'}))
                (private_root / 'member-credentials.json').write_text(json.dumps({'manager': {'account': 'rg-mgr'}}))
            return mock.Mock(returncode=0, stdout='{}', stderr='')

        with mock.patch.object(run_standard.tempfile, 'mkdtemp', return_value=str(root / 'private')), \
                mock.patch.object(run_standard.subprocess, 'run', side_effect=fake_subprocess) as fixture_runner, \
                mock.patch.object(run_standard, 'run_browser', return_value=0) as browser, \
                mock.patch.object(run_standard, 'finish', return_value={'counts': {}, 'complete': True, 'executionGates': {}}), \
                mock.patch('builtins.print'):
            rc = run_standard.execute_live(config, root / 'catalog.json', owner, {}, ['node', 'standard.cjs'], root / 'credentials', None)
        evidence_dir = next((root / 'evidence').iterdir())
        return rc, evidence_dir, fixture_runner, browser

    def test_delivery_fixture_auto_prepares_fresh_state_in_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rc, evidence_dir, fixture_runner, browser = self._run_fixture_preflight(root)
            self.assertEqual(rc, 0)
            browser.assert_called_once()
            actions = [call.args[0][-1] for call in fixture_runner.call_args_list]
            self.assertEqual(actions, ['bootstrap', 'publish', 'install', 'members'])
            preflight = json.loads((evidence_dir / 'delivery-fixture-preflight.json').read_text())
            self.assertEqual(preflight['status'], 'ready')
            self.assertEqual([item['action'] for item in preflight['preparedActions']], ['bootstrap', 'publish', 'install', 'members'])

    def test_delivery_fixture_skips_prep_when_members_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rc, evidence_dir, fixture_runner, browser = self._run_fixture_preflight(
                root,
                state_payload={'daemonId': 'daemon-1', 'stage': 'members-ready', 'commands': [], 'originalCasForms': []},
                manifest_payload={'status': 'published', 'daemonId': 'daemon-1'},
                members_exists=True,
            )
            self.assertEqual(rc, 0)
            browser.assert_called_once()
            fixture_runner.assert_not_called()
            preflight = json.loads((evidence_dir / 'delivery-fixture-preflight.json').read_text())
            self.assertEqual(preflight['preparedActions'], [])

    def test_delivery_fixture_blocks_unsafe_or_failed_state_before_browser_launch(self):
        unsafe_states = [
            {'daemonId': 'other-daemon', 'stage': 'new', 'commands': [], 'originalCasForms': []},
            {'daemonId': 'daemon-1', 'stage': 'publish-in-progress', 'commands': [], 'originalCasForms': []},
            {'daemonId': 'daemon-1', 'stage': 'published', 'commands': [{'outcome': 'unknown'}], 'originalCasForms': []},
            {'daemonId': 'daemon-1', 'stage': 'bootstrapped', 'commands': [], 'originalCasForms': [{'phase': 'response-not-delivered'}]},
        ]
        for payload in unsafe_states:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                rc, evidence_dir, fixture_runner, browser = self._run_fixture_preflight(Path(folder), state_payload=payload)
                self.assertEqual(rc, 2)
                fixture_runner.assert_not_called()
                browser.assert_not_called()
                self.assertEqual(json.loads((evidence_dir / 'preflight.json').read_text())['status'], 'blocked')

        with tempfile.TemporaryDirectory() as folder:
            rc, evidence_dir, fixture_runner, browser = self._run_fixture_preflight(Path(folder), stage_exit=2)
            self.assertEqual(rc, 2)
            browser.assert_not_called()
            self.assertEqual([c.args[0][-1] for c in fixture_runner.call_args_list], ['bootstrap', 'publish'])
            preflight = json.loads((evidence_dir / 'preflight.json').read_text())
            self.assertEqual(preflight['status'], 'blocked')
            self.assertIn('publish failed', preflight['reason'])


if __name__ == '__main__':
    unittest.main()
