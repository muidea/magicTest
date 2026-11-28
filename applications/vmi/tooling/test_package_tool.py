"""Offline unit tests for VMI definition package validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_tool


class VmiPackageToolTests(unittest.TestCase):
    def test_validate_source_passes(self):
        profile = package_tool.validate_source()
        self.assertEqual(profile["key"], "vmi")
        self.assertEqual(profile["version"], "0.1.0-dev.1")

    def test_check_runs_official_codec(self):
        report, files = package_tool.run("check")
        self.assertTrue(report["officialBuild"])
        self.assertTrue(report["officialParse"])
        self.assertTrue(report["officialParseUnpacked"])
        self.assertTrue(report["deterministicBuild"])
        self.assertTrue(report["schemaCreatePreflight"])
        self.assertTrue(report["runtimeEffectValidation"])
        self.assertEqual(report["entityCount"], 18)
        self.assertEqual(report["functionBlockCount"], 2)
        self.assertTrue(report["pageRuntimeInspection"]["ready"])
        self.assertIn("package.zip", files)


if __name__ == "__main__":
    unittest.main()
