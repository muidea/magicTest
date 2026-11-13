"""Actual temporary-file flock tests; no Docker, browser or platform process."""
import fcntl
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import unittest

from regression import audit_admission_lock as tool


class AdmissionLockTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / '.operation-audit'
        self.root.mkdir(mode=0o700)
        self.lock = self.root / 'admission.lock'
        self.lock.write_bytes(b'original-lock-bytes')
        self.lock.chmod(0o600)
        self.correlation = 'a' * 32

    def launch(self, *, root=None, uid=None):
        process = subprocess.Popen([sys.executable, '-B', str(Path(tool.__file__)), '--root', str(root or self.root),
                                    '--uid', str(os.getuid() if uid is None else uid), '--correlation', self.correlation],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: self.stop(process))
        return process

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

    def ready(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'isolated helper startup deadline')
        return json.loads(process.stdout.readline())

    def test_actual_readonly_flock_blocks_other_holder_and_exact_release_preserves_file(self):
        before = self.lock.stat(), self.lock.read_bytes()
        process = self.launch()
        ready = self.ready(process)
        self.assertEqual(ready['kind'], 'ready')
        with self.lock.open('rb') as second:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out, err = process.communicate(('release:' + self.correlation + '\n').encode(), timeout=5)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(err, b'')
        released = json.loads(out)
        self.assertEqual(released, {**ready, 'kind': 'released'})
        after = self.lock.stat(), self.lock.read_bytes()
        self.assertEqual((before[0].st_ino, stat.S_IMODE(before[0].st_mode), before[1]),
                         (after[0].st_ino, stat.S_IMODE(after[0].st_mode), after[1]))
        with self.lock.open('rb') as second:
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_wrong_release_or_eof_cannot_claim_disposition(self):
        for payload in [b'release:wrong\n', b'']:
            process = self.launch()
            self.assertEqual(self.ready(process)['kind'], 'ready')
            out, _ = process.communicate(payload, timeout=5)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(json.loads(out)['kind'], 'unavailable')
            self.assertEqual(self.lock.read_bytes(), b'original-lock-bytes')

    def test_symlink_mode_uid_and_missing_owner_paths_are_rejected_without_creation(self):
        self.lock.chmod(0o644)
        process = self.launch()
        out, _ = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 2)
        self.assertNotIn(str(self.root), out.decode())
        self.lock.chmod(0o600)
        process = self.launch(uid=os.getuid() + 1)
        self.assertEqual(json.loads(process.communicate(timeout=5)[0])['kind'], 'unavailable')
        link = Path(self.folder.name) / 'alias'
        link.symlink_to(self.root, target_is_directory=True)
        process = self.launch(root=link)
        self.assertEqual(json.loads(process.communicate(timeout=5)[0])['kind'], 'unavailable')
        self.lock.unlink()
        process = self.launch()
        self.assertEqual(json.loads(process.communicate(timeout=5)[0])['kind'], 'unavailable')
        self.assertFalse(self.lock.exists())

    def test_changed_original_inode_cannot_emit_successful_release(self):
        process = self.launch()
        self.assertEqual(self.ready(process)['kind'], 'ready')
        self.lock.rename(self.root / 'retained-original')
        self.lock.write_bytes(b'replacement')
        self.lock.chmod(0o600)
        out, _ = process.communicate(('release:' + self.correlation + '\n').encode(), timeout=5)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(out)['kind'], 'unavailable')
        self.assertEqual((self.root / 'retained-original').read_bytes(), b'original-lock-bytes')
        self.assertEqual(self.lock.read_bytes(), b'replacement')

    def test_existing_other_holder_is_not_stolen_or_unlocked(self):
        with self.lock.open('rb') as first:
            fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
            process = self.launch()
            out, _ = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(json.loads(out)['kind'], 'unavailable')
            with self.lock.open('rb') as second:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_bounded_read_protocol_deadline_with_partial_line(self):
        program = ('import sys;from regression.audit_admission_lock import hold;'
                   'hold(sys.argv[1],int(sys.argv[2]),sys.argv[3],deadline=0.08)')
        process = subprocess.Popen([sys.executable, '-B', '-c', program, str(self.root), str(os.getuid()), self.correlation],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: self.stop(process))
        self.assertEqual(self.ready(process)['kind'], 'ready')
        process.stdin.write(b'release:'); process.stdin.flush()
        self.assertEqual(process.wait(timeout=5), 1)
        self.assertEqual(self.lock.read_bytes(), b'original-lock-bytes')


if __name__ == '__main__':
    unittest.main()
