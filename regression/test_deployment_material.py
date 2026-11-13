"""Offline formal snapshot source checks; Docker stop observations are mocked.

Only newly allocated finite files are touched. These checks do not establish
that a real deployment stopped, recovered its database, or passed Live.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SOURCE = Path.home() / 'dataspace/magicPlatform/scripts/platform-snapshot.py'
spec = importlib.util.spec_from_file_location('formal_material_snapshot', SOURCE)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


def facts(root, names):
    result = {}
    for name in names:
        p = root / name
        st = p.stat()
        result[name] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_size,
                        st.st_mode & 0o777, st.st_uid, st.st_gid)
    return result


class SnapshotMaterialTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='magictest-material-source-')
        self.addCleanup(self.directory.cleanup)
        self.private = Path(self.directory.name)
        self.root = self.private / 'deployment'
        self.root.mkdir()
        self.names = ['services/.env', 'services/data/probe', 'services/secret/probe',
                      'services/runtime/probe', 'apps/data/first/probe', 'apps/data/second/probe']
        for index, name in enumerate(self.names):
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            file.write_bytes(bytes([0, 255, index, 128]) + os.urandom(index + 1))
            file.chmod(0o600)
        self.before = facts(self.root, self.names)
        self.archive = self.private / 'snapshot.tgz'
        # Explicit source double only; never call Docker or an actual platform.
        stopped = mock.patch.object(owner, 'check_stopped')
        self.stopped = stopped.start()
        self.addCleanup(stopped.stop)
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def backup(self):
        owner.backup(self.root, self.archive)
        return owner.verify(self.archive, self.root)

    def test_same_root_complete_roundtrip_preserves_original_and_displaced_facts(self):
        manifest = self.backup()
        self.assertTrue(set(self.names).issubset(manifest['files']))
        self.assertEqual(manifest['deploymentRoot'], str(self.root))
        self.assertEqual(manifest['sha256'], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        for file in [self.archive, Path(str(self.archive) + '.json')]:
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        for name in self.names:
            (self.root / name).write_bytes(b'changed material ' + name.encode())
        changed = facts(self.root, self.names)
        owner.restore(self.root, self.archive, replace=True)
        self.assertEqual(facts(self.root, self.names), self.before)
        displaced = list(self.root.glob('.recovery-old-*'))
        self.assertEqual(len(displaced), 1)
        self.assertEqual(facts(displaced[0], self.names), changed)
        self.assertEqual(self.stopped.call_count, 4)

    def test_existing_target_refusal_never_changes_actual_files(self):
        self.backup()
        with self.assertRaisesRegex(owner.SnapshotError, 'restore target exists'):
            owner.restore(self.root, self.archive)
        self.assertEqual(facts(self.root, self.names), self.before)
        self.assertEqual(list(self.root.glob('.recovery-old-*')), [])

    def test_archive_and_manifest_are_exclusive_original_outputs(self):
        self.backup()
        archive = self.archive.read_bytes()
        metadata = Path(str(self.archive) + '.json').read_bytes()
        with self.assertRaisesRegex(owner.SnapshotError, 'already exists'):
            owner.backup(self.root, self.archive)
        self.assertEqual(self.archive.read_bytes(), archive)
        self.assertEqual(Path(str(self.archive) + '.json').read_bytes(), metadata)

    def test_corrupt_or_different_root_cannot_publish_replacement_state(self):
        self.backup()
        other = self.private / 'other'
        other.mkdir()
        with self.assertRaisesRegex(owner.SnapshotError, 'different deployment root'):
            owner.restore(other, self.archive, replace=True)
        self.archive.write_bytes(self.archive.read_bytes() + b'corrupt')
        with self.assertRaisesRegex(owner.SnapshotError, 'checksum'):
            owner.restore(self.root, self.archive, replace=True)
        self.assertEqual(facts(self.root, self.names), self.before)

    def test_unavailable_numeric_owner_restoration_fails_before_target_swaps(self):
        self.backup()
        with mock.patch.object(owner.os, 'chown', side_effect=PermissionError('source-only denied')):
            with self.assertRaises(PermissionError):
                owner.restore(self.root, self.archive, replace=True)
        self.assertEqual(facts(self.root, self.names), self.before)
        self.assertEqual(list(self.root.glob('.recovery-old-*')), [])

    def test_stop_proof_failure_cannot_be_reported_as_restore_or_empty_success(self):
        self.backup()
        self.stopped.side_effect = owner.SnapshotError('source double: active target')
        with self.assertRaisesRegex(owner.SnapshotError, 'active target'):
            owner.restore(self.root, self.archive, replace=True)
        self.assertEqual(facts(self.root, self.names), self.before)
        self.assertEqual(list(self.root.glob('.recovery-old-*')), [])


if __name__ == '__main__':
    unittest.main()
