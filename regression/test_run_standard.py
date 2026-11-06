"""Exercise report gates without browser mutations or product acceptance claims."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from regression.run_standard import ROOT, environment_lock, finish, load_owner, tool_hashes


class ReportGatesTest(unittest.TestCase):
    def test_tool_identity_includes_runtime_helpers(self):
        hashes = tool_hashes()
        for name in ['directory.cjs', 'resource_lifecycle.cjs', 'negative_mutations.cjs', 'public_probe.cjs', 'standard_cases.cjs']:
            self.assertEqual(hashes[name], 'sha256:' + hashlib.sha256((ROOT / 'regression' / name).read_bytes()).hexdigest())
        self.assertFalse(any(name.endswith('.test.cjs') for name in hashes))

    @classmethod
    def setUpClass(cls):
        catalog_path = ROOT.parent / 'docs/acceptance/platform-catalog.json'
        cls.owner = load_owner(catalog_path)
        cls.catalog = json.loads(catalog_path.read_text())
        cls.owner.validate_catalog(cls.catalog)

    def run_report(self, *, cleaned=True, drift=False, browser_exit=0, healthy=True):
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
            entry = {'caseId': 'F059-001', 'suite': 'standard', 'status': 'passed', 'method': 'live',
                     'role': 'unit-fixture', 'namespace': 'unit', 'resource': 'unit',
                     'observedAt': '2026-11-05T00:00:00+00:00', 'actual': 'Unit-only report input',
                     'environmentFingerprint': environment['fingerprint'],
                     'evidence': [{'kind': 'operational', 'path': 'core-health.json',
                                   'sha256': 'sha256:' + hashlib.sha256((directory / 'browser/core-health.json').read_bytes()).hexdigest()}]}
            before = {'schema': 'magic.acceptance.results/v1', 'baseline': self.catalog['baseline'],
                      'catalogDigest': self.owner.digest(self.catalog), 'runId': 'unit',
                      'environment': environment, 'results': [entry]}
            after = copy.deepcopy(before)
            browser = copy.deepcopy(before)
            browser['results'] = []
            for case in self.catalog['cases']:
                if not case['required'] or not any(part['suite'] == 'standard' for part in case['execution']):
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
            return finish(self.owner, self.catalog, before, after, browser, directory, browser_exit)

    def test_complete_requires_all_gates(self):
        self.assertTrue(self.run_report()['complete'])

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


if __name__ == '__main__':
    unittest.main()
