from pathlib import Path
import tempfile
import unittest

from check_published_block_lifecycle import private_journal_path, source_snapshot


class PublishedJournalHandoffTests(unittest.TestCase):
    def test_only_private_bounded_input_and_exclusive_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.json"
            self.assertEqual(private_journal_path(path, exporting=True), path)
            path.write_text("{}")
            path.chmod(0o600)
            self.assertEqual(private_journal_path(path, exporting=False), path)
            with self.assertRaises(ValueError):
                private_journal_path(path, exporting=True)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                private_journal_path(path, exporting=False)
            path.chmod(0o600)
            path.write_bytes(b"x" * 65537)
            with self.assertRaises(ValueError):
                private_journal_path(path, exporting=False)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                private_journal_path(root / "new.json", exporting=True)

    def test_evidence_and_symlinks_cannot_receive_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private"
            private.mkdir(mode=0o700)
            alias = root / "alias"
            alias.symlink_to(private, target_is_directory=True)
            with self.assertRaises(ValueError):
                private_journal_path(alias / "input.json", exporting=True)
            (private / "input.json").symlink_to(root / "missing")
            with self.assertRaises(ValueError):
                private_journal_path(private / "input.json", exporting=True)
            acceptance = root / "acceptance"
            acceptance.mkdir(mode=0o700)
            with self.assertRaises(ValueError):
                private_journal_path(acceptance / "input.json", exporting=True)
            (private / "SHA256SUMS").write_text("frozen")
            with self.assertRaises(ValueError):
                private_journal_path(private / "new.json", exporting=True)

    def test_source_snapshot_binds_shared_production_namespace_authorizer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "magicModulesRepo/pkg/namespaceauth/authorize.go"
            source.parent.mkdir(parents=True)
            source.write_text("package namespaceauth\n")
            first = source_snapshot(root, root / "entities")
            self.assertIn(str(source), first)
            source.write_text("package namespaceauth\n// changed\n")
            second = source_snapshot(root, root / "entities")
            self.assertNotEqual(first[str(source)], second[str(source)])

    def test_browser_inputs_cannot_change_without_invalidating_joint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                root / "magicWebPortal/src/pages/login/cas/index.tsx",
                root / "magicWebPortal/scripts/check-mainline-bff-browser.cjs",
                root / "magicWebPortal/src/assets/brand.png",
            ]
            for source in paths:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b"initial browser input")
            first = source_snapshot(root, root / "entities")
            for source in paths:
                self.assertIn(str(source), first)
                source.write_bytes(b"changed while Chromium is running")
                second = source_snapshot(root, root / "entities")
                self.assertNotEqual(first[str(source)], second[str(source)])


if __name__ == "__main__":
    unittest.main()
