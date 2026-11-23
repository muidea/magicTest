from pathlib import Path
import tempfile
import unittest

from start_acceptance_round import start_round


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'magicTest'
        (self.root / 'reports/runs/2026-10-28-old').mkdir(parents=True)
        (self.root / 'acceptance').mkdir(parents=True)
        (self.root / 'acceptance/platform-catalog.json').write_text('{}')
        (self.root / 'reports/runs/2026-10-28-old/result.json').write_text('old')

    def test_preserves_current_catalogue_and_application_data(self):
        current = self.root / 'reports/runs/2026-10-29-current'
        current.mkdir()
        (current / 'result.json').write_text('current')
        (self.root / 'applications/device-management').mkdir(parents=True)
        (self.root / 'applications/device-management/config.json').write_text('application')
        result = start_round(self.root, current.name)
        self.assertEqual(result['removedFiles'], 1)
        self.assertEqual((current / 'result.json').read_text(), 'current')
        self.assertTrue((self.root / 'acceptance/platform-catalog.json').is_file())
        self.assertTrue((self.root / 'applications/device-management/config.json').is_file())
        self.assertEqual(start_round(self.root, current.name)['removedEntries'], 0)

    def test_validates_all_roots_before_deletion(self):
        (self.root / 'reports/runs/bad').symlink_to(self.root / 'acceptance', target_is_directory=True)
        (self.root / 'reports/runs').unlink() if False else None
        # Replace reports with symlink to trigger pre-check refusal
        (self.root / 'reports_link').symlink_to(self.root / 'acceptance', target_is_directory=True)
        # Validate direct symlinked reports root
        temp_root = Path(self.temp.name) / 'badTest'
        (temp_root / 'acceptance').mkdir(parents=True)
        (temp_root / 'acceptance/platform-catalog.json').write_text('{}')
        (temp_root / 'reports').symlink_to(temp_root / 'acceptance', target_is_directory=True)
        with self.assertRaises(ValueError):
            start_round(temp_root, '2026-10-29-current')
        self.assertTrue((self.root / 'reports/runs/2026-10-28-old/result.json').exists())

    def test_rejects_traversal(self):
        with self.assertRaises(ValueError):
            start_round(self.root, '../outside')

    def test_new_round_refreshes_index_and_unlinks_external_symlink_safely(self):
        index = self.root / 'reports/README.md'
        index.write_text('当前轮次：`~/codespace/magicTest/reports/runs/2026-10-28-old/README.md`')
        external = Path(self.temp.name) / 'outside'
        external.mkdir()
        (external / 'keep').write_text('unrelated')
        (self.root / 'reports/runs/old-link').symlink_to(external, target_is_directory=True)
        start_round(self.root, '2026-10-29-current')
        self.assertTrue((external / 'keep').is_file())
        self.assertFalse((self.root / 'reports/runs/old-link').is_symlink())
        self.assertFalse((self.root / 'reports/runs/2026-10-28-old').exists())
        self.assertTrue((self.root / 'reports/runs/2026-10-29-current/README.md').is_file())
        self.assertIn('reports/runs/2026-10-29-current/README.md', index.read_text())


if __name__ == '__main__':
    unittest.main()
