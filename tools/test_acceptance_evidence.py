import tempfile
from pathlib import Path
import unittest

from acceptance_evidence import EvidenceDirectory


class EvidenceDirectoryTests(unittest.TestCase):
    def test_existing_run_and_frozen_parent_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old"
            old.mkdir()
            (old / "joint.log").write_bytes(b"original\x00bytes")
            with self.assertRaises(FileExistsError):
                EvidenceDirectory(old)
            (old / "SHA256SUMS").write_text("immutable")
            with self.assertRaises(ValueError):
                EvidenceDirectory(old / "new")
            self.assertFalse((old / "new").exists())
            self.assertEqual((old / "joint.log").read_bytes(), b"original\x00bytes")

    def test_frozen_or_replaced_run_rejects_later_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = EvidenceDirectory(root / "run")
            with evidence.open_log("joint.log") as log:
                log.write("first\n")
            with evidence.open_log("joint.log") as log:
                log.write("second\n")
            (root / "run" / "SHA256SUMS").write_text("frozen")
            for operation in (lambda: evidence.open_log("joint.log"),
                              lambda: evidence.write_json("result.json", {}),
                              lambda: evidence.copy(root / "run" / "joint.log", "copy.log")):
                with self.assertRaises(ValueError):
                    operation()
            self.assertEqual((root / "run" / "joint.log").read_text(), "first\nsecond\n")
            (root / "run").rename(root / "original")
            (root / "run").mkdir()
            with self.assertRaises(ValueError):
                evidence.write_json("result.json", {})

    def test_symlinks_traversal_and_overwrites_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "alias").symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                EvidenceDirectory(root / "alias" / "run")
            evidence = EvidenceDirectory(root / "run")
            evidence.write_json("result.json", {"status": "passed"})
            with self.assertRaises(FileExistsError):
                evidence.write_json("result.json", {"status": "failed"})
            for name in ("../outside", "SHA256SUMS", "/outside"):
                with self.assertRaises(ValueError):
                    evidence.write_json(name, {})
            (root / "run" / "external.log").symlink_to(root / "run" / "result.json")
            with self.assertRaises(ValueError):
                evidence.open_log("external.log")


if __name__ == "__main__":
    unittest.main()
