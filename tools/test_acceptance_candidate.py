import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from acceptance_candidate import APPLICATIONS, bind_candidate, image_source_snapshot


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CandidateBindingTests(unittest.TestCase):
    def fixture(self, root):
        delivery, images = root / "delivery", root / "images"
        delivery.mkdir()
        images.mkdir()
        entries = [{"application": name, "reference": "docker.io/muidea/" + name.lower(),
                    "tag": "candidate", "digest": "sha256:" + "a" * 64} for name in sorted(APPLICATIONS)]
        files = {"services/images.lock.json": json.dumps({"apiVersion": "magic.images.lock/v1", "images": entries}).encode()}
        for index in range(46):
            files[f"services/platform/deployments/magicPanel/entity/entity{index}.json"] = b"{}"
        for name, data in files.items():
            target = delivery / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        metadata = {"apiVersion": "magic.static-delivery/v1", "liveReady": False,
                    "planDigest": "b" * 64, "deliverySHA256": {name: sha(data) for name, data in files.items()}}
        (delivery / "delivery.json").write_text(json.dumps(metadata))
        (images / "image-build-source-sha256.json").write_text(json.dumps({"fixture": "inputs"}))
        (images / "candidate-image-provenance.json").write_text(json.dumps({"status": "passed", "sourceInputsUnchanged": True, "images": entries}))
        for directory in (delivery, images):
            (directory / "SHA256SUMS").write_text("".join(sha(path.read_bytes()) + "  " + str(path.relative_to(directory)) + "\n"
                                                        for path in sorted(directory.rglob("*")) if path.is_file()))
        return delivery, images

    def bind(self, root, delivery, images, **kwargs):
        return bind_candidate(root, delivery, images,
                              inspect=kwargs.get("inspect", lambda _: "sha256:" + "a" * 64),
                              snapshot=kwargs.get("snapshot", lambda _: {"fixture": "inputs"}))

    def test_matches_same_inputs_and_images_before_and_after(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            delivery, images = self.fixture(root)
            # In a real acceptance run the frozen manifest belongs to an
            # ancestor; it is evidence, not a declared delivery payload file.
            manifest = delivery / "SHA256SUMS"
            (root / "SHA256SUMS").write_text("".join(
                line.split("  ", 1)[0] + "  delivery/" + line.split("  ", 1)[1] + "\n"
                for line in manifest.read_text().splitlines()))
            manifest.unlink()
            before = self.bind(root, delivery, images)
            self.assertEqual(before, self.bind(root, delivery, images))
            self.assertEqual(before["panelEntities"], 46)
            self.assertEqual(len(before["localImages"]), 7)
            self.assertIn("not executed", before["boundary"])

    def test_rejects_changes_before_owner_calls(self):
        for fault in ("delivery-file", "record-tamper", "source-drift", "image-drift", "extra-runtime", "unfrozen", "symlink"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                delivery, images = self.fixture(root)
                manifest = delivery / "SHA256SUMS"
                (root / "SHA256SUMS").write_text("".join(
                    line.split("  ", 1)[0] + "  delivery/" + line.split("  ", 1)[1] + "\n"
                    for line in manifest.read_text().splitlines()))
                manifest.unlink()
                kwargs = {}
                if fault == "delivery-file":
                    (delivery / "services/images.lock.json").write_text("{}")
                elif fault == "record-tamper":
                    (delivery / "delivery.json").write_text("{}")
                elif fault == "source-drift":
                    kwargs["snapshot"] = lambda _: {"fixture": "changed"}
                elif fault == "image-drift":
                    kwargs["inspect"] = lambda _: "sha256:" + "c" * 64
                elif fault == "extra-runtime":
                    (delivery / ".env").write_text("must-not-consume")
                elif fault == "unfrozen":
                    (images / "SHA256SUMS").unlink()
                elif fault == "symlink":
                    path = delivery / "services/images.lock.json"
                    path.rename(delivery / "moved.json")
                    path.symlink_to(delivery / "moved.json")
                with self.assertRaises(ValueError):
                    self.bind(root, delivery, images, **kwargs)

    def test_build_input_snapshot_detects_additions_and_vendor_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "magicRunner/vendor/local").mkdir(parents=True)
            vendor = root / "magicRunner/vendor/local/dependency.go"
            vendor.write_text("package local\n")
            first = image_source_snapshot(root)
            (root / "magicRunner/new.go").write_text("package main\n")
            self.assertNotEqual(first, image_source_snapshot(root))
            second = image_source_snapshot(root)
            vendor.write_text("package changed\n")
            self.assertNotEqual(second, image_source_snapshot(root))

    def test_driver_requires_complete_candidate_arguments_before_database(self):
        driver = Path(__file__).with_name("check_published_block_lifecycle.py")
        environment = dict(os.environ)
        environment.pop("MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN", None)
        for args in (["--candidate-delivery", "/missing"],
                     ["--candidate-delivery", "/missing", "--candidate-image-evidence", "/missing"]):
            result = subprocess.run([sys.executable, str(driver), *args], env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
