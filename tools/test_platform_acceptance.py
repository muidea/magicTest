import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import platform_acceptance as subject


class AcceptanceEvidenceTests(unittest.TestCase):
    def test_configuration_ignores_mount_order_but_detects_changes(self):
        containers = [{'Name': '/panel', 'Config': {'Env': ['MODE=dev']},
                       'HostConfig': {}, 'Mounts': [
                           {'Source': '/data', 'Destination': '/app/data'},
                           {'Source': '/config', 'Destination': '/app/config'}]}]
        reordered = copy.deepcopy(containers)
        reordered[0]['Mounts'].reverse()
        self.assertEqual(subject.configuration_digest(containers),
                         subject.configuration_digest(reordered))
        reordered[0]['Mounts'][0]['Source'] = '/different-config'
        self.assertNotEqual(subject.configuration_digest(containers),
                            subject.configuration_digest(reordered))

    def setUp(self):
        self.catalog = json.loads((subject.ROOT / 'acceptance/platform-catalog.json').read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        proof = self.root / 'proof.json'
        proof.write_text('{"checked":true}\n')
        versions = {name: 'sha256:' + 'a' * 64 for name in subject.CORE}
        config = 'sha256:' + 'b' * 64
        fingerprint = subject.digest({'versions': versions, 'configurationDigest': config})
        self.results = {'schema': 'magic.acceptance.results/v1', 'baseline': self.catalog['baseline'],
                        'catalogDigest': subject.digest(self.catalog), 'runId': 'test',
                        'environment': {'name': 'isolated-test', 'versions': versions, 'configurationDigest': config, 'fingerprint': fingerprint},
                        'results': [{'caseId': 'F059-001', 'suite': 'standard', 'status': 'passed', 'method': 'live',
                                     'environmentFingerprint': fingerprint, 'role': 'inspector', 'namespace': 'platform',
                                     'resource': 'core', 'actual': 'checked', 'observedAt': '2026-10-01T00:00:00+00:00',
                                     'evidence': [{'kind': 'operational', 'path': proof.name,
                                                   'sha256': 'sha256:' + hashlib.sha256(proof.read_bytes()).hexdigest()}]}]}

    def test_one_pass_cannot_complete_feature_or_platform(self):
        entries = subject.validate_results(self.catalog, self.results, self.root)
        report = subject.summarize(self.catalog, entries)
        self.assertFalse(report['complete'])
        self.assertEqual(report['counts']['passed'], 1)
        self.assertEqual(report['coverage'], 1 / report['requiredChecks'])
        all_report = subject.summarize(self.catalog, entries, 'all')
        self.assertEqual(next(f for f in all_report['features'] if f['id'] == 'F059')['status'], 'partial')

    def test_empty_scope_is_not_passed(self):
        report = subject.summarize(self.catalog, {})
        self.assertEqual(report['coverage'], 0)
        self.assertIsNone(report['passRate'])
        self.assertFalse(report['complete'])

    def test_evidence_and_target_integrity(self):
        mutations = [lambda r: r['results'][0].update(environmentFingerprint='other'),
                     lambda r: r['environment']['versions'].update(magicPanel='muidea/magicpanel:master'),
                     lambda r: r.update(catalogDigest='old'),
                     lambda r: r['results'][0].update(method='unit'),
                     lambda r: r['results'][0]['evidence'][0].update(kind='historical'),
                     lambda r: r['results'][0]['evidence'][0].update(sha256='wrong'),
                     lambda r: r['results'].append(copy.deepcopy(r['results'][0])),
                     lambda r: r['results'][0].update(evidence=[]),
                     lambda r: r['results'][0].update(status='blocked'),
                     lambda r: r['results'][0].update(status='failed', reason='failure')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                data = copy.deepcopy(self.results)
                mutate(data)
                with self.assertRaises(ValueError):
                    subject.validate_results(self.catalog, data, self.root)

    def test_blocked_does_not_count_as_executed(self):
        self.results['results'][0].update(status='blocked', reason='needs isolated environment', evidence=[])
        entries = subject.validate_results(self.catalog, self.results, self.root)
        report = subject.summarize(self.catalog, entries)
        self.assertEqual(report['coverage'], 0)
        self.assertEqual(report['counts']['blocked'], 1)

    def test_browser_cases_need_visual_evidence(self):
        self.results['results'][0].update(caseId='F001-004', method='manual')
        with self.assertRaises(ValueError):
            subject.validate_results(self.catalog, self.results, self.root)

    def test_catalogue_requires_every_feature_and_unique_ids(self):
        for mutate in (lambda c: c['cases'].append(copy.deepcopy(c['cases'][0])),
                       lambda c: c.update(cases=[x for x in c['cases'] if x['featureId'] != 'F064'])):
            data = copy.deepcopy(self.catalog)
            mutate(data)
            with self.assertRaises(ValueError):
                subject.validate_catalog(data)

    def test_catalogue_requires_purpose_owners_and_current_sources(self):
        mutations = (
            lambda c: c['cases'][0].pop('purpose'),
            lambda c: c['features'][0].update(owners=[]),
            lambda c: c.update(sources=['../old-stage.md']),
            lambda c: c['executionRequirements'].pop('cleanup'),
        )
        for mutate in mutations:
            data = copy.deepcopy(self.catalog)
            mutate(data)
            with self.assertRaises(ValueError):
                subject.validate_catalog(data)

    def test_generated_ledger_stays_in_sync(self):
        current = (subject.ROOT / 'acceptance/platform-case-ledger.md').read_text()
        self.assertEqual(subject.render_ledger(self.catalog), current)

    def test_generated_abnormal_view_stays_in_sync(self):
        self.assertEqual(subject.render_abnormal_cases(self.catalog),
                         (subject.ROOT / 'acceptance/platform-abnormal-cases.md').read_text())

    def test_generated_special_view_stays_in_sync(self):
        self.assertEqual(subject.render_special_cases(self.catalog),
                         (subject.ROOT / 'acceptance/platform-special-cases.md').read_text())

    def test_execution_partition_separates_positive_standard_from_abnormal_and_special(self):
        cases = subject.validate_catalog(self.catalog)
        suites = lambda cid: {p['suite'] for p in cases[cid]['execution']}
        self.assertEqual(suites('F009-001'), {'special'})
        self.assertEqual(suites('F056-001'), {'standard', 'special'})
        self.assertEqual(next(p['fixture'] for p in cases['F056-001']['execution']
                              if p['suite'] == 'standard'), 'business')
        # Positive functional, UI interaction, and non-destructive auth/boundary/recovery checks stay in standard.
        for cid in ('F001-004', 'F006-003', 'F013-003', 'F068-004'):
            self.assertEqual(suites(cid), {'standard'}, cid)
        for cid in ('F030-002', 'F041-002', 'F045-003', 'F069-005', 'F070-001'):
            self.assertEqual(suites(cid), {'standard', 'special'}, cid)
        # Destructive / fault / interrupt / concurrent-conflict checks live in abnormal.
        for cid in ('F020-002', 'F028-002', 'F062-002'):
            self.assertEqual(suites(cid), {'abnormal'}, cid)
        for cid in ('F001-005', 'F010-003', 'F010-005', 'F017-002', 'F035-006', 'F048-003', 'F057-004', 'F058-002', 'F071-005'):
            self.assertEqual(suites(cid), {'abnormal', 'special'}, cid)
        for cid in ('F057-005', 'F059-002', 'F060-001', 'F060-002', 'F061-001', 'F061-002', 'F061-003', 'F062-001', 'F062-003', 'F063-001', 'F063-002'):
            self.assertEqual(suites(cid), {'special'}, cid)
        self.assertEqual(sum('standard' in suites(cid) for cid in cases), 184)
        self.assertEqual(sum('abnormal' in suites(cid) for cid in cases), 28)
        self.assertEqual(sum('special' in suites(cid) for cid in cases), 75)
        self.assertEqual(len(cases), 245)

    def test_invalid_or_incomplete_routing_is_rejected(self):
        mutations = (
            lambda c: c['cases'][0].pop('execution'),
            lambda c: c['cases'][0].update(execution=[]),
            lambda c: c['cases'][0]['execution'].append(copy.deepcopy(c['cases'][0]['execution'][0])),
            lambda c: c['cases'][0]['execution'][0].update(suite='external'),
            lambda c: c['cases'][0]['execution'][0].update(scope=''),
            lambda c: c['cases'][0]['execution'][0].update(fixture='unknown'),
            lambda c: c['cases'][0]['execution'][0].update(fixture='natural-time'),
            lambda c: c['cases'][0]['execution'][0].update(prerequisites=['unknown']),
            lambda c: c['cases'][0]['execution'][0].update(suite='special'),
            lambda c: c['cases'][0]['execution'][0].update(suite='abnormal'),
            lambda c: c['cases'][0].update(methods=['manual']),
        )
        for mutate in mutations:
            catalog = copy.deepcopy(self.catalog)
            mutate(catalog)
            with self.assertRaises(ValueError):
                subject.validate_catalog(catalog)

    def test_abnormal_and_special_blocks_do_not_block_positive_standard_or_mark_whole_case_passed(self):
        entries = {(c['id'], p['suite']): {'status': 'passed' if p['suite'] == 'standard' else 'blocked'}
                   for c in self.catalog['cases'] for p in c['execution']}
        standard = subject.summarize(self.catalog, entries)
        abnormal = subject.summarize(self.catalog, entries, 'abnormal')
        special = subject.summarize(self.catalog, entries, 'special')
        whole = subject.summarize(self.catalog, entries, 'all')
        self.assertTrue(standard['complete'])
        self.assertEqual(standard['requiredChecks'], 184)
        self.assertFalse(abnormal['complete'])
        self.assertEqual(abnormal['counts']['blocked'], 28)
        self.assertFalse(special['complete'])
        self.assertEqual(special['counts']['blocked'], 75)
        self.assertFalse(whole['complete'])
        self.assertFalse(standard['catalogCoverage']['complete'])
        mixed = next(c for c in standard['catalogCoverage']['cases'] if c['caseId'] == 'F056-001')
        self.assertEqual(mixed['status'], 'blocked')
        del entries[('F056-001', 'special')]
        report = subject.summarize(self.catalog, entries)
        mixed = next(c for c in report['catalogCoverage']['cases'] if c['caseId'] == 'F056-001')
        self.assertEqual(mixed['status'], 'partial')

    def test_result_identity_requires_suite_and_allows_both_mixed_parts(self):
        self.results['results'][0]['caseId'] = 'F056-001'
        part = copy.deepcopy(self.results['results'][0])
        part['suite'] = 'special'
        self.results['results'].append(part)
        entries = subject.validate_results(self.catalog, self.results, self.root)
        self.assertEqual(len(entries), 2)
        whole = subject.summarize(self.catalog, entries)['catalogCoverage']
        self.assertEqual(whole['counts']['passed'], 1)
        for bad_suite in ('other', None):
            self.results['results'][0]['suite'] = bad_suite
            with self.assertRaises(ValueError):
                subject.validate_results(self.catalog, self.results, self.root)

    def test_manual_evidence_cannot_complete_standard_automatic_scope(self):
        item = self.results['results'][0]
        item.update(caseId='F001-004', method='manual')
        item['evidence'][0]['kind'] = 'manual'
        with self.assertRaisesRegex(ValueError, 'automated'):
            subject.validate_results(self.catalog, self.results, self.root)

    def test_cli_default_completion_is_separate_from_special_and_catalogue(self):
        import contextlib
        import io
        from unittest.mock import patch

        template = self.results['results'][0]
        self.results['results'] = []
        for case in self.catalog['cases']:
            for part in case['execution']:
                result = copy.deepcopy(template)
                result.update(caseId=case['id'], suite=part['suite'],
                              method='browser' if 'browser' in case['methods'] else 'live')
                if result['method'] == 'browser':
                    result['evidence'][0]['kind'] = 'browser'
                if part['suite'] == 'special':
                    result.update(status='blocked', reason='missing specialized prerequisites', evidence=[])
                self.results['results'].append(result)
        source = self.root / 'results.json'
        source.write_text(json.dumps(self.results))
        target = self.root / 'report.json'
        argv = ['platform_acceptance.py', '--results', str(source), '--output', str(target)]
        with contextlib.redirect_stdout(io.StringIO()):
            with patch('sys.argv', argv):
                self.assertEqual(subject.main(), 0)
            report = json.loads(target.read_text())
            self.assertEqual(report['suite'], 'standard')
            self.assertEqual(report['requiredChecks'], 184)
            self.assertTrue(report['complete'])
            self.assertFalse(report['catalogCoverage']['complete'])
            with patch('sys.argv', argv + ['--suite', 'abnormal']):
                self.assertEqual(subject.main(), 0)
            abnormal = json.loads(target.read_text())
            self.assertEqual(abnormal['suite'], 'abnormal')
            self.assertEqual(abnormal['requiredChecks'], 28)
            with patch('sys.argv', argv + ['--suite', 'special']):
                self.assertEqual(subject.main(), 2)
        self.assertEqual(json.loads(target.read_text())['counts']['blocked'], 75)

    def test_remote_https_validation_and_f059_honesty_gate(self):
        proof = self.root / 'remote-proof.json'
        proof.write_text('{"checked":true}\n')
        cfg = subject.digest({'origin': 'https://panel.example.com', 'issuer': 'https://panel.example.com/api/v1/cas', 'jwksKeys': ['k1:RSA:RS256'], 'brandingStatus': 200})
        fp = subject.digest({'mode': 'remote-https', 'origin': 'https://panel.example.com', 'configurationDigest': cfg})
        remote = {
            'schema': 'magic.acceptance.results/v1',
            'baseline': self.catalog['baseline'],
            'catalogDigest': subject.digest(self.catalog),
            'runId': 'remote-test',
            'environment': {
                'name': 'remote-https',
                'mode': 'remote-https',
                'origin': 'https://panel.example.com',
                'targetAddress': '10.0.0.2',
                'tlsVerification': 'system-ca',
                'configurationDigest': cfg,
                'fingerprint': fp,
            },
            'results': [{
                'caseId': 'F001-004',
                'suite': 'standard',
                'status': 'passed',
                'method': 'browser',
                'environmentFingerprint': fp,
                'role': 'admin',
                'namespace': 'panel',
                'resource': 'rg1',
                'observedAt': '2026-11-25T00:00:00+00:00',
                'actual': 'Remote browser login passed',
                'evidence': [{'kind': 'browser', 'path': proof.name, 'sha256': 'sha256:' + hashlib.sha256(proof.read_bytes()).hexdigest()}],
            }],
        }
        entries = subject.validate_results(self.catalog, remote, self.root)
        self.assertIn(('F001-004', 'standard'), entries)
        remote['results'][0]['caseId'] = 'F059-001'
        remote['results'][0]['method'] = 'live'
        remote['results'][0]['evidence'][0]['kind'] = 'live'
        with self.assertRaisesRegex(ValueError, 'F059-001'):
            subject.validate_results(self.catalog, remote, self.root)


if __name__ == '__main__':
    unittest.main()
