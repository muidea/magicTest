#!/usr/bin/env python3
"""Offline tests for the dual-application E2E harness."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

LIVE_E2E_DIR = Path(__file__).resolve().parent
APPLICATIONS_ROOT = LIVE_E2E_DIR.parent
for entry in (LIVE_E2E_DIR, APPLICATIONS_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from platform_paths import resolve_platform_root
import run_dual_apps_e2e as e2e


class DualAppsE2ETests(unittest.TestCase):
    def test_dry_run_preflight_writes_summary_without_overwriting(self):
        with tempfile.TemporaryDirectory(prefix='dual-e2e-test-') as temp:
            out_dir = Path(temp) / 'report'
            rc = e2e.main(['--dry-run', '--output-dir', str(out_dir)])
            self.assertEqual(rc, 0)
            summary_path = out_dir / 'e2e-summary.json'
            self.assertTrue(summary_path.is_file())
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            self.assertEqual(summary['mode'], 'dry-run')
            self.assertFalse(summary['liveExecuted'])
            self.assertTrue(summary['passed'])
            self.assertEqual(set(summary['apps']), {'device-management', 'chess-room-booking'})
            with self.assertRaises(FileExistsError):
                e2e.main(['--dry-run', '--output-dir', str(out_dir)])

    def test_tampered_package_checksum_is_rejected(self):
        real_platform = resolve_platform_root()
        with tempfile.TemporaryDirectory(prefix='dual-e2e-badpkg-') as temp:
            fake_platform = Path(temp) / 'magicPlatform'
            shutil.copytree(real_platform / 'apps/models/device-management/definition',
                            fake_platform / 'apps/models/device-management/definition')
            pkg_dir = fake_platform / 'apps/models/device-management/package'
            pkg_dir.mkdir(parents=True)
            (pkg_dir / 'package.zip').write_bytes(b'not-a-valid-bundle')
            (pkg_dir / 'SHA256SUMS').write_text('0' * 64 + '  package.zip\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                e2e.run_dry_run(fake_platform, ['device-management'])


if __name__ == '__main__':
    unittest.main()
