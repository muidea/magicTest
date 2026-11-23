#!/usr/bin/env python3
"""回读规范化的离线合同测试；输入由测试构造，不表示已经从实际服务导出。"""
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


generator, oracle, normalizer = (load(name) for name in ("generate_fixture", "fixture_oracle", "normalize_readback"))


def fixture(variant="A"):
    entities = generator.generate(variant)
    binding = {"namespace": "fixture-tenant", "deploymentId": "a" * 32, "installationId": "9223372036854775000",
               "runtimeApplicationUuid": "fixture-runtime", "generation": 3, "executionEpoch": 4, "artifactDigest": "sha256:" + "b" * 64}
    target = {"schemaVersion": "magic.device-readback-target/v1", "binding": binding, "variant": variant, "fixtureDigest": "sha256:" + "c" * 64}
    ids = {name: {row["code"]: str(9223372036854700000 + index) for index, row in enumerate(rows)}
           for name, rows in entities.items() if name != "telemetry"}
    snapshot = {"schemaVersion": "magic.device-owner-readback/v1", "binding": copy.deepcopy(binding), "variant": variant,
                "fixtureDigest": target["fixtureDigest"], "dataVersion": "device-management/v0.1", "definitionVersion": "device-management/v0.2",
                "synthetic": True, "anchor": "2026-10-14T12:00:00Z", "entities": {}}
    for name, rows in entities.items():
        readback = copy.deepcopy(rows)
        for index, row in enumerate(readback):
            row["id"] = str(9223372036854700000 + index)
            for field, destination in normalizer.RELATIONS.get(name, {}).items():
                if row[field] is not None:
                    row[field] = {"id": ids[destination][row[field]], "code": row[field]}
            if name == "alarm":
                row["acknowledgedBy"] = None if row["status"] == "open" else "fixture-verified-subject"
                row["resolvedBy"] = "fixture-verified-subject" if row["status"] == "resolved" else None
        snapshot["entities"][name] = {"pkgKey": "/deviceManagement/" + name, "complete": True, "total": len(readback), "rows": readback}
    return snapshot, target


class ReadbackTest(unittest.TestCase):
    def test_owner_rows_normalize_to_independent_oracle_and_exact_ids(self):
        for variant in ("A", "B", "C"):
            with self.subTest(variant=variant):
                snapshot, target = fixture(variant)
                before = copy.deepcopy(snapshot)
                document, mapping = normalizer.normalize(snapshot, target)
                self.assertEqual(oracle.verify(document)["counts"]["device"], {"A": 24, "B": 3, "C": 1}[variant])
                self.assertEqual(mapping["entities"]["device"][0]["id"], "9223372036854700000")
                self.assertEqual(document["entities"]["location"][-1]["parent"], "SITE-01")
                self.assertEqual(snapshot, before)
                self.assertEqual(mapping["authority"], "observed-owner-readback-not-cleanup-authorization")
                if variant == "A":
                    self.assertEqual(mapping["entities"]["alarm"][1]["observedMetadata"]["acknowledgedBy"], "fixture-verified-subject")

    def test_wrong_scope_partial_rows_precision_and_relations_rejected(self):
        snapshot, target = fixture()
        faults = {
            "namespace": lambda d: d["binding"].__setitem__("namespace", "other"),
            "installation": lambda d: d["binding"].__setitem__("installationId", "10"),
            "generation": lambda d: d["binding"].__setitem__("generation", 2),
            "epoch": lambda d: d["binding"].__setitem__("executionEpoch", 2),
            "digest": lambda d: d["binding"].__setitem__("artifactDigest", "sha256:" + "e" * 64),
            "partial": lambda d: d["entities"]["device"].__setitem__("complete", False),
            "count": lambda d: d["entities"]["device"].__setitem__("total", 25),
            "unsafe-id": lambda d: d["entities"]["device"]["rows"][0].__setitem__("id", 9223372036854700000),
            "boolean-id": lambda d: d["entities"]["device"]["rows"][0].__setitem__("id", True),
            "duplicate-id": lambda d: d["entities"]["device"]["rows"][1].__setitem__("id", "9223372036854700000"),
            "duplicate-code": lambda d: d["entities"]["device"]["rows"][1].__setitem__("code", "DEV-001"),
            "missing-null": lambda d: d["entities"]["device"]["rows"][0].pop("serialNumber"),
            "unknown-field": lambda d: d["entities"]["device"]["rows"][0].__setitem__("fileRef", "untrusted"),
            "foreign-reference": lambda d: d["entities"]["device"]["rows"][0]["location"].__setitem__("id", "1"),
            "conflicting-reference": lambda d: d["entities"]["device"]["rows"][0]["location"].__setitem__("code", "LINE-B2"),
            "missing-reference": lambda d: d["entities"]["device"]["rows"][0].__setitem__("location", None),
            "numeric-time": lambda d: d["entities"]["telemetry"]["rows"][0].__setitem__("sampledAt", 1234567890),
            "duplicate-sample": lambda d: d["entities"]["telemetry"]["rows"][1].__setitem__("sampledAt", d["entities"]["telemetry"]["rows"][0]["sampledAt"]),
        }
        for name, mutate in faults.items():
            with self.subTest(name=name):
                candidate = copy.deepcopy(snapshot)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    normalizer.normalize(candidate, target)

    def test_cli_no_overwrite_and_strict_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, target = fixture("B")
            (root / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
            (root / "target.json").write_text(json.dumps(target), encoding="utf-8")
            output = root / "normalized"
            command = [sys.executable, "-I", str(ROOT / "normalize_readback.py"), "--snapshot", str(root / "snapshot.json"), "--target", str(root / "target.json"), "--output", str(output)]
            subprocess.run(command, check=True, capture_output=True)
            document = json.loads((output / "logical.json").read_bytes())
            self.assertEqual(oracle.verify(document)["variant"], "B")
            checked = subprocess.run([sys.executable, "-I", str(ROOT / "fixture_oracle.py"), "--document", str(output / "logical.json")], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(checked.stdout)["counts"]["device"], 3)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertTrue((output / "id-mapping.json").is_file())
            for payload in ('{"a":1,"a":2}', '{"a":NaN}'):
                with self.assertRaises(ValueError):
                    normalizer.strict_json(payload)

    def test_time_offset_normalizes_but_numeric_or_naive_time_rejected(self):
        self.assertEqual(normalizer.instant("2026-10-14T14:00:00+02:00"), "2026-10-14T12:00:00Z")
        for value in (123, True, "2026-10-14T12:00:00", "2026-10-14T12:00:00.0000001Z"):
            with self.assertRaises(ValueError):
                normalizer.instant(value)


if __name__ == "__main__":
    unittest.main()
