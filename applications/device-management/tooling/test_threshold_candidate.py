"""Check that the installation candidate preserves its reviewed effect and old packages."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_app_model_root
from validate_threshold_candidate import validate

APP_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = resolve_app_model_root('device-management')


class ThresholdDraftBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='threshold-definition-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(MODEL_ROOT / 'definition', self.root / 'definition')
        shutil.copytree(APP_ROOT / 'fixtures/threshold-v3', self.root / 'fixtures/threshold-v3')

    def edit(self, name, change):
        path = self.root / name
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))

    def test_rejects_unreviewed_binding(self):
        def change(value):
            entity = next(e for e in value['entities'] if e['name'] == 'telemetry')
            entity['blockInfo'] = [{'scriptKey': 'telemetry.evaluateThresholds'}]
        self.edit('definition/candidate.artifact.json', change)
        with self.assertRaisesRegex(ValueError, 'exactly the reviewed telemetry effect binding'):
            validate(self.root)

    def test_rejects_alarm_create_even_with_twenty_three_operations(self):
        def change(value):
            for entity in value['entities']:
                for operation in entity['serviceExpose']['capabilities']:
                    if (entity['name'], operation['key']) == ('alarm', 'create'):
                        operation['enabled'] = True
                    if (entity['name'], operation['key']) == ('maintenance', 'create'):
                        operation['enabled'] = False
        self.edit('definition/candidate.artifact.json', change)
        with self.assertRaisesRegex(ValueError, 'must not expose alarm creation'):
            validate(self.root)

    def test_rejects_rule_drift_between_design_and_oracle(self):
        self.edit('fixtures/threshold-v3/cases.json',
                  lambda value: value['rules'][0].update(upper=80))
        with self.assertRaisesRegex(ValueError, 'rules disagree'):
            validate(self.root)

    def test_rejects_effect_binding_rule_drift(self):
        self.edit('definition/threshold-effect.binding.design.json',
                  lambda value: value['stageInfo']['functions']['insert']['input']['rules'][0].update(upper=80))
        with self.assertRaisesRegex(ValueError, 'effect binding design'):
            validate(self.root)

    def test_rejects_injected_alarm_fixture(self):
        self.edit('fixtures/threshold-v3/bootstrap.json',
                  lambda value: value['alarm'].append({'code': 'FAKE-ALARM'}))
        with self.assertRaisesRegex(ValueError, 'no injected alarms'):
            validate(self.root)

    def test_rejects_empty_or_reserved_catalog(self):
        for bad in ('', '  ', 'inner', 'INNER'):
            with self.subTest(catalog=bad):
                tmp = tempfile.TemporaryDirectory(prefix='threshold-catalog-test-')
                self.addCleanup(tmp.cleanup)
                root = Path(tmp.name)
                shutil.copytree(self.root / 'definition', root / 'definition')
                shutil.copytree(self.root / 'fixtures', root / 'fixtures')
                path = root / 'definition/candidate.artifact.json'
                data = json.loads(path.read_text())
                data['application']['catalog'] = bad
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, 'catalog'):
                    validate(root)

    def test_legacy_export_cli_refuses_before_changing_packages(self):
        package_root = MODEL_ROOT / 'package'
        before = {p: p.read_bytes() for p in package_root.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, '-I', str(APP_ROOT / 'tooling/export_candidate.py'),
                                 '--from-unpacked', '--model-root', str(MODEL_ROOT)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('historical exporter must not overwrite', result.stderr)
        after = {p: p.read_bytes() for p in package_root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
