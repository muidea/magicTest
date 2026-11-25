#!/usr/bin/env python3
"""Offline unit tests for export_remote_sim_bundle.py."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

TOOLS_DIR = Path(__file__).resolve().parent
MAGICTEST_ROOT = TOOLS_DIR.parent
APPLICATIONS_ROOT = MAGICTEST_ROOT / "applications"
for entry in (TOOLS_DIR, APPLICATIONS_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import export_remote_sim_bundle as exporter
from platform_paths import resolve_platform_root


class ExportRemoteSimBundleTests(unittest.TestCase):
    def test_exports_manifest_verified_bundle_and_excludes_tests_caches_and_secrets(self):
        real_platform = resolve_platform_root()
        with tempfile.TemporaryDirectory(prefix="sim-bundle-test-") as tmp:
            tmp_path = Path(tmp)
            fake_test = tmp_path / "magicTest"
            (fake_test / "applications/live_e2e").mkdir(parents=True)
            (fake_test / "applications/device-management/tooling/simulator").mkdir(parents=True)
            (fake_test / "applications/device-management/tooling/__pycache__").mkdir(parents=True)
            (fake_test / "applications/device-management/fixtures").mkdir(parents=True)
            (fake_test / "applications/chess-room-booking/tooling").mkdir(parents=True)
            (fake_test / "applications/chess-room-booking/fixtures").mkdir(parents=True)
            (fake_test / "load").mkdir(parents=True)
            (fake_test / "reports").mkdir(parents=True)

            (fake_test / "README.md").write_text("# magicTest\n", encoding="utf-8")
            (fake_test / "applications/README.md").write_text("# apps\n", encoding="utf-8")
            (fake_test / "applications/platform_paths.py").write_text(
                (MAGICTEST_ROOT / "applications/platform_paths.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (fake_test / "applications/live_e2e/README.md").write_text("# live_e2e\n", encoding="utf-8")
            (fake_test / "applications/live_e2e/run_dual_apps_e2e.py").write_text("# runner\n", encoding="utf-8")
            (fake_test / "applications/live_e2e/bootstrap_simulated_apps.py").write_text("# bootstrap\n", encoding="utf-8")
            (fake_test / "applications/live_e2e/test_live_e2e.py").write_text("# secret test\n", encoding="utf-8")
            (fake_test / "applications/device-management/README.md").write_text("# dm\n", encoding="utf-8")
            (fake_test / "applications/device-management/tooling/simulator.py").write_text("# sim\n", encoding="utf-8")
            (fake_test / "applications/device-management/tooling/simulator/common.py").write_text("# mod\n", encoding="utf-8")
            (fake_test / "applications/device-management/tooling/test_simulator.py").write_text("# excluded\n", encoding="utf-8")
            (fake_test / "applications/device-management/tooling/validate.go.txt").write_text("// excluded\n", encoding="utf-8")
            (fake_test / "applications/device-management/tooling/__pycache__/x.pyc").write_bytes(b"pyc")
            (fake_test / "applications/device-management/tooling/leaked.key").write_text("SECRET", encoding="utf-8")
            (fake_test / "applications/device-management/fixtures/manifest.json").write_text("{}\n", encoding="utf-8")
            (fake_test / "applications/chess-room-booking/README.md").write_text("# crb\n", encoding="utf-8")
            (fake_test / "applications/chess-room-booking/tooling/simulation_tool.py").write_text("# sim\n", encoding="utf-8")
            (fake_test / "applications/chess-room-booking/fixtures/baseline.json").write_text("{}\n", encoding="utf-8")
            (fake_test / "load/__init__.py").write_text("", encoding="utf-8")
            (fake_test / "load/run_load.py").write_text("# load\n", encoding="utf-8")
            (fake_test / "load/apm_client.py").write_text("# apm\n", encoding="utf-8")
            (fake_test / "load/test_load.py").write_text("# excluded\n", encoding="utf-8")
            (fake_test / "reports/run.json").write_text("{}", encoding="utf-8")

            archive_path = tmp_path / "out/sim-bundle.tar.gz"
            rc = exporter.main([
                "--output", str(archive_path),
                "--magic-test-root", str(fake_test),
                "--platform-root", str(real_platform),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(archive_path.is_file())

            with self.assertRaises(FileExistsError):
                exporter.export_bundle(archive_path, fake_test, real_platform, force=False)

            with tarfile.open(archive_path, "r:gz") as tf:
                names = set(tf.getnames())
                self.assertIn("magic-sim-bundle/bundle-manifest.json", names)
                self.assertIn("magic-sim-bundle/README-REMOTE.txt", names)
                self.assertIn("magic-sim-bundle/magicTest/applications/device-management/tooling/simulator.py", names)
                self.assertIn("magic-sim-bundle/magicTest/load/run_load.py", names)
                self.assertIn("magic-sim-bundle/magicTest/load/apm_client.py", names)
                self.assertIn("magic-sim-bundle/magicPlatform/apps/models/device-management/package/package.zip", names)
                self.assertIn("magic-sim-bundle/magicPlatform/apps/models/chess-room-booking/package/package.zip", names)
                self.assertIn("magic-sim-bundle/magicPlatform/scripts/deployment-health.sh", names)

                for forbidden_sub in ("__pycache__", ".pyc", "test_live_e2e.py", "test_simulator.py", "test_load.py", "validate.go.txt", "leaked.key", "/reports/", "unpacked"):
                    self.assertFalse(any(forbidden_sub in n for n in names), f"forbidden archive entry matching {forbidden_sub}")

                manifest = json.loads(tf.extractfile("magic-sim-bundle/bundle-manifest.json").read().decode("utf-8"))
                self.assertEqual(manifest["apiVersion"], "magic.sim-bundle/v1")
                self.assertEqual(manifest["fileCount"], len(manifest["files"]))
                for item in manifest["files"]:
                    member = tf.extractfile(f"magic-sim-bundle/{item['path']}")
                    self.assertIsNotNone(member)
                    data = member.read()
                    self.assertEqual(len(data), item["size"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])


if __name__ == "__main__":
    unittest.main()
