#!/usr/bin/env python3
"""离线工具回归：固定数据、独立预期、拒绝篡改和重复输出。"""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load("generate_fixture")
oracle = load("fixture_oracle")


class FixtureToolsTest(unittest.TestCase):
    def document(self):
        return {"schemaVersion": "magic.device-fixture/v1", "dataVersion": "device-management/v0.1",
                "definitionVersion": "device-management/v0.2", "variant": "A", "synthetic": True,
                "anchor": "2026-10-14T12:00:00Z", "entities": generator.generate("A")}

    def test_fixed_counts_and_independent_expected_values(self):
        result = oracle.verify(self.document())
        self.assertEqual(result["counts"], {"location": 7, "category": 3, "device": 24, "telemetry": 492, "alarm": 12, "maintenance": 8})
        self.assertEqual(result["onlineRate"], "78.26")
        self.assertEqual(result["unresolvedAlarms"], 9)
        self.assertEqual(result["maintenanceDevices"], 6)
        self.assertEqual(result["temperatureMeanDEV001"], "22.15")

    def test_semantic_corruption_rejected_without_checksum_dependency(self):
        original = self.document()
        faults = {
            "duplicate-sample": lambda d: d["entities"]["telemetry"].__setitem__(1, copy.deepcopy(d["entities"]["telemetry"][0])),
            "bad-formula": lambda d: d["entities"]["telemetry"][0].__setitem__("temperature", 99),
            "missing-null": lambda d: d["entities"]["telemetry"][103].__setitem__("temperature", 25.7),
            "lost-zero": lambda d: d["entities"]["telemetry"][24].__setitem__("loadPercent", None),
            "upper-bound": lambda d: d["entities"]["telemetry"][0].__setitem__("sampledAt", "2026-10-14T12:00:00Z"),
            "bad-maintenance-reference": lambda d: d["entities"]["maintenance"][1].__setitem__("device", "DEV-024"),
            "bad-tree": lambda d: d["entities"]["location"][0].__setitem__("parent", "WS-A"),
            "wrong-state": lambda d: d["entities"]["alarm"][0].__setitem__("status", "resolved"),
            "environment-id": lambda d: d["entities"]["device"][0].__setitem__("id", 123),
        }
        for name, mutate in faults.items():
            with self.subTest(name=name):
                document = copy.deepcopy(original)
                mutate(document)
                with self.assertRaises(ValueError):
                    oracle.verify(document)

    def test_reproducible_bundle_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first", Path(directory) / "second"
            one = generator.write_bundle(first)
            two = generator.write_bundle(second)
            self.assertEqual(one, two)
            for name in ("A.json", "B.json", "C.json", "manifest.json"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            with self.assertRaises(FileExistsError):
                generator.write_bundle(first)
            command = [sys.executable, "-I", str(ROOT / "fixture_oracle.py"), "--bundle", str(first)]
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            summaries = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([row["counts"]["device"] for row in summaries], [24, 3, 1])
            self.assertEqual([row["onlineRate"] for row in summaries], ["78.26", "100.00", "100.00"])
            payload = first / "A.json"
            payload.write_bytes(payload.read_bytes() + b" ")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
