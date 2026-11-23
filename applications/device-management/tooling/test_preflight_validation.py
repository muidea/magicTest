#!/usr/bin/env python3
"""A/B/C 只读预检的离线回归；构造回读不代表真实实例证据。"""
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


preflight, tools = load("preflight_validation"), load("test_readback_tools")
BUNDLE = ROOT.parent / "fixtures" / "fixed-v1"


def inputs():
    targets, snapshots = {}, {}
    for variant, prefix in zip(("A", "B", "C"), ("a", "b", "c")):
        snapshot, target = tools.fixture(variant)
        target["fixtureDigest"] = preflight.normalizer.digest((BUNDLE / (variant + ".json")).read_bytes())
        target["binding"].update(namespace="other-tenant" if variant == "C" else "same-tenant",
                                  deploymentId=prefix * 32, runtimeApplicationUuid="runtime-" + variant)
        snapshot["binding"] = copy.deepcopy(target["binding"])
        snapshot["fixtureDigest"] = target["fixtureDigest"]
        targets[variant] = target
        snapshots[variant] = json.dumps(snapshot, ensure_ascii=False).encode()
    return {"schemaVersion": "magic.device-validation-targets/v1", "targets": targets}, snapshots


class PreflightTest(unittest.TestCase):
    def test_offline_materials_never_claim_live_or_cleanup(self):
        targets, _ = inputs()
        result = preflight.verify(BUNDLE, targets)
        self.assertFalse(result["liveReady"])
        self.assertEqual(result["live"], "not-run")
        self.assertEqual(result["cleanup"], "not-run")
        self.assertEqual(result["variants"]["A"]["expected"]["counts"]["telemetry"], 492)
        self.assertTrue(all(v["ownerReadback"] == "not-run" for v in result["variants"].values()))
        self.assertNotIn("same-tenant", json.dumps(result))

    def test_all_owner_snapshots_normalized_and_independently_checked(self):
        targets, snapshots = inputs()
        result = preflight.verify(BUNDLE, targets, snapshots)
        self.assertTrue(all(v["ownerReadback"] == "offline-observation-verified" for v in result["variants"].values()))
        self.assertFalse(result["liveReady"])
        self.assertEqual(result["initialization"], "not-run")
        self.assertEqual(result["variants"]["A"]["expected"]["onlineRate"], "78.26")

    def test_wrong_target_isolation_digest_and_partial_evidence_rejected(self):
        targets, snapshots = inputs()
        faults = {
            "same-runtime": lambda d: d["targets"]["B"]["binding"].__setitem__("runtimeApplicationUuid", "runtime-A"),
            "same-deployment": lambda d: d["targets"]["B"]["binding"].__setitem__("deploymentId", "a" * 32),
            "wrong-ab": lambda d: d["targets"]["B"]["binding"].__setitem__("namespace", "third-tenant"),
            "wrong-c": lambda d: d["targets"]["C"]["binding"].__setitem__("namespace", "same-tenant"),
            "other-candidate": lambda d: d["targets"]["C"]["binding"].__setitem__("artifactDigest", "sha256:" + "d" * 64),
            "fixture-digest": lambda d: d["targets"]["B"].__setitem__("fixtureDigest", "sha256:" + "d" * 64),
            "variant": lambda d: d["targets"]["B"].__setitem__("variant", "A"),
            "missing": lambda d: d["targets"].pop("C"),
            "unknown": lambda d: d.__setitem__("token", "forbidden"),
        }
        for fault, mutate in faults.items():
            with self.subTest(fault=fault):
                candidate = copy.deepcopy(targets)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    preflight.verify(BUNDLE, candidate)
        with self.assertRaises(ValueError):
            preflight.verify(BUNDLE, targets, {"A": snapshots["A"]})
        for entity, field, value in (("telemetry", "temperature", -999), ("device", "description", "未授权更改"), ("location", "sortOrder", True)):
            altered = json.loads(snapshots["A"])
            altered["entities"][entity]["rows"][0][field] = value
            candidate = dict(snapshots, A=json.dumps(altered).encode())
            with self.assertRaises(ValueError):
                preflight.verify(BUNDLE, targets, candidate)

    def test_manifest_tamper_and_cli_no_implicit_network_or_writes(self):
        targets, _ = inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "targets.json").write_text(json.dumps(targets), encoding="utf-8")
            command = [sys.executable, "-I", str(ROOT / "preflight_validation.py"), "--bundle", str(BUNDLE), "--targets", str(root / "targets.json")]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertFalse(json.loads(completed.stdout)["liveReady"])
            self.assertEqual({p.name for p in root.iterdir()}, {"targets.json"})
            self.assertNotEqual(subprocess.run(command + ["--snapshot-a", str(root / "absent.json")], capture_output=True).returncode, 0)
            for source in BUNDLE.iterdir():
                if source.is_file():
                    (root / source.name).write_bytes(source.read_bytes())
            (root / "B.json").write_bytes((root / "B.json").read_bytes() + b" ")
            with self.assertRaises(ValueError):
                preflight.verify(root, targets)


if __name__ == "__main__":
    unittest.main()
