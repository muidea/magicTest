import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('evidence_derivative', Path(__file__).with_name('evidence_derivative.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class DerivativeProofs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'original'
        self.source.mkdir()
        self.output = self.root / 'public'
        self.token = 'a' * 64
        self.proof = self.source / 'proof.json'
        self.proof.write_text(json.dumps({'status': 'failed', 'error': {'code': 2, 'message': 'file token ' + self.token + ' does not exist'}}))
        self.result = self.source / 'results.json'
        self.result.write_text(json.dumps({'evidence': [{'path': 'proof.json', 'sha256': tool.digest(self.proof)}], 'counts': {'failed': 1}}))
        (self.source / 'report.json').write_text(json.dumps({'evidence': [{'path': 'results.json', 'sha256': tool.digest(self.result)}]}))

    def test_raw_failure_kept_and_entire_public_hash_chain_repaired(self):
        originals = {p.name: p.read_bytes() for p in self.source.iterdir()}
        report = tool.create_derivative(self.source, self.output, [self.token])
        self.assertTrue(report['originalBytesUnchanged'])
        for name, data in originals.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        proof = json.loads((self.output / 'proof.json').read_text())
        self.assertEqual(proof['status'], 'failed')
        self.assertEqual(proof['error']['code'], 2)
        for p in self.output.iterdir():
            self.assertNotIn(self.token, p.read_text())
        results = json.loads((self.output / 'results.json').read_text())
        self.assertEqual(results['counts'], {'failed': 1})
        self.assertEqual(results['evidence'][0]['sha256'], tool.digest(self.output / 'proof.json'))
        summary = json.loads((self.output / 'report.json').read_text())
        self.assertEqual(summary['evidence'][0]['sha256'], tool.digest(self.output / 'results.json'))

    def test_nested_case_references_use_original_browser_output_anchor(self):
        attempt = self.source / 'browser/attempts/current'
        attempt.mkdir(parents=True)
        image = attempt / 'screenshot.png'
        image.write_bytes(b'non-secret image bytes')
        case = attempt / 'case.json'
        case.write_text(json.dumps({'evidence': [{'path': 'attempts/current/screenshot.png', 'sha256': tool.digest(image)}]}))
        tool.create_derivative(self.source, self.output, [self.token])
        copied = json.loads((self.output / 'browser/attempts/current/case.json').read_text())
        self.assertEqual(copied['evidence'][0]['sha256'], tool.digest(self.output / 'browser/attempts/current/screenshot.png'))

    def test_corrupt_original_rejected_before_output(self):
        self.proof.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            tool.create_derivative(self.source, self.output, [self.token])
        self.assertFalse(self.output.exists())

    def test_http_content_observation_is_preserved_but_absolute_file_reference_rejected(self):
        observation = {'path': '/static/share/platform/legal/privacy.md', 'bytes': 42,
                       'sha256': 'sha256:' + 'b' * 64, 'contentStatus': 'temporary-content-retained-by-user'}
        (self.source / 'http.json').write_text(json.dumps(observation))
        tool.create_derivative(self.source, self.output, [self.token])
        self.assertEqual(json.loads((self.output / 'http.json').read_text()), observation)
        (self.source / 'http.json').write_text(json.dumps({'path': '/etc/passwd', 'sha256': observation['sha256']}))
        with self.assertRaisesRegex(ValueError, 'contained relative'):
            tool.create_derivative(self.source, self.root / 'other-public', [self.token])

    def test_never_overwrites_original_or_public_evidence(self):
        with self.assertRaisesRegex(ValueError, 'independent'):
            tool.create_derivative(self.source, self.source / 'public', [self.token])
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            tool.create_derivative(self.source, self.output, [self.token])

    def test_opaque_token_contract_and_symlink_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, '64-hex'):
            tool.create_derivative(self.source, self.output, ['arbitrary string'])
        (self.source / 'linked').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            tool.create_derivative(self.source, self.output, [self.token])
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
