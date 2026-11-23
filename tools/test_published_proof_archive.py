"""Verified owner oracles must survive temporary fixture cleanup byte for byte."""

from pathlib import Path
import tempfile
import unittest

from acceptance_evidence import EvidenceDirectory
from check_published_block_lifecycle import archive_required_proofs


class IndependentProofArchive(unittest.TestCase):
    def test_retains_all_three_datetime_oracles_after_fixture_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = EvidenceDirectory(Path(directory) / "evidence")
            names = [f"detail-time-{stage}.json" for stage in ("ungranted", "grant", "revoked")]
            originals = {name: ('{"UTC":"original-' + name + '"}\n').encode() for name in names}
            with tempfile.TemporaryDirectory(dir=directory) as fixture:
                for name, data in originals.items():
                    (Path(fixture) / name).write_bytes(data)
                archive_required_proofs(fixture, evidence, names)
            for name, data in originals.items():
                self.assertEqual((evidence.directory / name).read_bytes(), data)

    def test_refuses_missing_or_changed_original(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture"
            fixture.mkdir()
            evidence = EvidenceDirectory(Path(directory) / "evidence")
            name = "detail-time-grant.json"
            with self.assertRaisesRegex(RuntimeError, "required independent proof missing"):
                archive_required_proofs(fixture, evidence, [name])
            (fixture / name).write_bytes(b'{"UTC":"stored-instant"}')
            archive_required_proofs(fixture, evidence, [name])
            archive_required_proofs(fixture, evidence, [name])
            (evidence.directory / name).write_bytes(b'{"UTC":"different-instant"}')
            with self.assertRaisesRegex(RuntimeError, "archived independent proof differs"):
                archive_required_proofs(fixture, evidence, [name])

    def test_reuses_replacement_archive_name_and_refuses_frozen_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture"
            (fixture / "replacement").mkdir(parents=True)
            (fixture / "replacement" / "ready.json").write_bytes(b'{"ready":true}\n')
            evidence = EvidenceDirectory(Path(directory) / "evidence")
            evidence.copy(fixture / "replacement" / "ready.json", "replacement-ready.json")
            archive_required_proofs(fixture, evidence, ["replacement/ready.json"])
            (fixture / "new.json").write_bytes(b"{}")
            (evidence.directory / "SHA256SUMS").write_bytes(b"frozen")
            with self.assertRaisesRegex(ValueError, "frozen evidence"):
                archive_required_proofs(fixture, evidence, ["new.json"])
            self.assertFalse((evidence.directory / "new.json").exists())


if __name__ == "__main__":
    unittest.main()
