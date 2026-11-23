import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import platform_closeout as subject


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = {'namespace': 't001', 'installationId': 1, 'deploymentId': 'a' * 32,
                        'applicationUuid': 'b' * 32, 'applicationName': 'accept-script',
                        'sourceDigest': 'sha256:' + 'c' * 64, 'expectedVersion': 7,
                        'status': 'running', 'purpose': 'acceptance', 'allowedActions': ['read', 'disable', 'uninstall'],
                        'cleanup': 'destroy only this installation'}
        self.fingerprint = 'sha256:' + 'd' * 64
        self.data = {'schema': 'magic.acceptance.fixtures/v1', 'environmentFingerprint': self.fingerprint, 'fixtures': [self.fixture]}

    def test_existing_demo_and_parallel_fixture_reuse_are_rejected(self):
        subject.validate_fixtures(self.data)
        self.fixture['applicationName'] = 'Demo'
        with self.assertRaises(ValueError): subject.validate_fixtures(self.data)
        self.fixture['applicationName'] = 'accept-script'
        self.data['fixtures'].append(copy.deepcopy(self.fixture))
        with self.assertRaises(ValueError): subject.validate_fixtures(self.data)

    def test_owner_readback_must_match_before_any_mutation(self):
        self.fixture['environmentFingerprint'] = self.fingerprint
        subject.require_current_fixture(self.fixture, self.fixture, 'disable', self.fingerprint)
        for key, value in [('namespace', 't002'), ('deploymentId', 'e' * 32), ('sourceDigest', 'sha256:' + 'f' * 64), ('expectedVersion', 8), ('status', 'uninstalled')]:
            current = dict(self.fixture, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                subject.require_current_fixture(self.fixture, current, 'disable', self.fingerprint)
        with self.assertRaises(ValueError): subject.require_current_fixture(self.fixture, self.fixture, 'cancel', self.fingerprint)
        with self.assertRaises(ValueError): subject.require_current_fixture(self.fixture, self.fixture, 'disable', 'other')

    def test_retry_and_historical_pass_do_not_hide_first_failure(self):
        required = ['install', 'disable', 'cleanup']
        attempts = [{'step': 'install', 'attempt': 1, 'status': 'failed', 'environmentFingerprint': self.fingerprint}]
        attempts += [{'step': step, 'attempt': 2, 'status': 'passed', 'environmentFingerprint': self.fingerprint} for step in required]
        report = subject.summarize_steps(required, attempts, self.fingerprint)
        self.assertFalse(report['passed'])
        self.assertEqual(report['firstFailure']['status'], 'failed')
        attempts[0]['resolutionEvidence'] = 'root-cause.md'
        self.assertTrue(subject.summarize_steps(required, attempts, self.fingerprint)['passed'])
        self.assertFalse(subject.summarize_steps(required, attempts, 'new-version')['passed'])

    def test_partially_completed_case_cannot_pass(self):
        report = subject.summarize_steps(['login', 'password-change', 'logout'],
            [{'step': 'login', 'attempt': 1, 'status': 'passed', 'environmentFingerprint': self.fingerprint}], self.fingerprint)
        self.assertFalse(report['passed'])
        self.assertEqual(report['incompleteSteps'], ['password-change', 'logout'])

    def test_unit_success_cannot_close_a_live_defect(self):
        tasks = [{'id': f'C{i:02}', 'state': 'regression-passed', 'owner': 'owner', 'summary': 'scope',
                  'codeRequired': True, 'remaining': ['live verification'], 'regressionEvidence': 'tests.json'} for i in range(1, 10)]
        data = {'schema': 'magic.closeout/v1', 'tasks': tasks}
        self.assertTrue(subject.validate_tasks(data)['readyForLive'])
        self.assertFalse(subject.validate_tasks(data)['complete'])
        tasks[0]['state'] = 'closed'
        with self.assertRaises(ValueError): subject.validate_tasks(data)


    def test_evidence_must_exist_and_match_passed_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / 'regression.json'
            evidence.write_text(json.dumps({'passed': True}))
            proof = {'path': evidence.name, 'digest': 'sha256:' + hashlib.sha256(evidence.read_bytes()).hexdigest()}
            data = {'tasks': [{'id': 'C01', 'state': 'regression-passed', 'codeRequired': True, 'regressionEvidence': proof}]}
            subject.verify_task_evidence(data, root)
            evidence.write_text(json.dumps({'passed': False}))
            with self.assertRaises(ValueError): subject.verify_task_evidence(data, root)
            proof['digest'] = 'sha256:' + hashlib.sha256(evidence.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): subject.verify_task_evidence(data, root)
            proof['path'] = '../outside.json'
            with self.assertRaises(ValueError): subject.verify_task_evidence(data, root)


if __name__ == '__main__': unittest.main()
