import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('model_fixture', Path(__file__).with_name('model_fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class ProducerGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runner = self.root / 'runner'
        (self.runner / fixture.PACKAGE).mkdir(parents=True)
        (self.runner / fixture.PACKAGE / 'codec.go').write_text('package modelpackage\n')
        (self.runner / 'vendor').mkdir()
        (self.runner / 'vendor/modules.txt').write_text('')
        self.input = self.root / 'input.json'
        self.input.write_text('{}')
        self.output = self.root / 'output'

    def test_source_output_rejected_before_any_command(self):
        with patch.object(fixture.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'outside'):
                fixture.produce(self.runner, self.input, self.runner / 'output')
            run.assert_not_called()
        self.assertFalse((self.runner / 'output').exists())

    def test_malformed_input_never_invokes_owner_or_creates_output(self):
        self.input.write_text('{')
        with patch.object(fixture.subprocess, 'run') as run:
            with self.assertRaises(json.JSONDecodeError):
                fixture.produce(self.runner, self.input, self.output)
            run.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_original_output_cannot_be_overwritten(self):
        self.output.mkdir()
        original = self.output / 'package.zip'
        original.write_bytes(b'original failure evidence')
        with patch.object(fixture, 'source_identity', return_value={'revision': 'source'}):
            with self.assertRaises(FileExistsError):
                fixture.produce(self.runner, self.input, self.output)
        self.assertEqual(original.read_bytes(), b'original failure evidence')

    def test_zero_exit_without_owner_outputs_is_failure(self):
        with patch.object(fixture, 'source_identity', return_value={'revision': 'source'}), patch.object(fixture.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'no outputs')) as run:
            report = fixture.produce(self.runner, self.input, self.output)
        self.assertEqual(report['status'], 'failed')
        command = run.call_args.args[0]
        self.assertIn('-mod=vendor', command)
        env = run.call_args.kwargs['env']
        self.assertEqual(env['GOPROXY'], 'off')
        self.assertEqual(env['GOTOOLCHAIN'], 'local')
        self.assertEqual(list((self.runner / fixture.PACKAGE).glob('zz_*')), [])

    def test_timeout_records_blocked_without_live_commands(self):
        with patch.object(fixture, 'source_identity', return_value={'revision': 'source'}), patch.object(fixture.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['go'], 180, output=b'original diagnostic')):
            report = fixture.produce(self.runner, self.input, self.output)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual((self.output / 'codec.log').read_bytes(), b'original diagnostic')
        self.assertIn('not executed', report['live'])
        self.assertTrue(report['sourceUnchanged'])


if __name__ == '__main__':
    unittest.main()
