#!/usr/bin/env python3
"""正式 GET 导出适配器的离线传输替身测试；不访问实例。"""
import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tools, exporter = load("test_readback_tools"), load("export_readback")


class Reader:
    def __init__(self, fault="", variant="A"):
        self.snapshot, self.target = tools.fixture(variant)
        document, _ = tools.normalizer.normalize(self.snapshot, self.target)
        self.fixture_bytes = json.dumps(document, ensure_ascii=False).encode()
        self.target["fixtureDigest"] = tools.normalizer.digest(self.fixture_bytes)
        self.fault, self.calls, self.sweeps = fault, [], 0

    def get(self, path, query, binding):
        self.calls.append((path, copy.deepcopy(query), copy.deepcopy(binding)))
        if "runtime/query" in path:
            value = {"application": {"key": "device-management"}, "readIdentity": copy.deepcopy(binding), "entities": [
                {"entity": {"name": name, "pkgPath": "/deviceManagement", "primaryKey": "id"}, "capabilities": {"query": True}}
                for name in tools.normalizer.ENTITIES]}
            if self.fault == "identity":
                value["readIdentity"]["executionEpoch"] += 1
            if self.fault == "directory":
                value["entities"].pop()
            if self.fault == "permission":
                value["entities"][0]["capabilities"]["query"] = False
            if self.fault == "metadata-drift" and self.sweeps:
                value["entities"][0]["entity"]["primaryKey"] = "other"
            return {"value": value}
        name = query["entity"].rsplit("/", 1)[-1]
        if name == "location":
            self.sweeps += 1
        rows = copy.deepcopy(self.snapshot["entities"][name]["rows"])
        for row in rows:
            row["id"] = int(row["id"])
            for field in tools.normalizer.RELATIONS.get(name, {}):
                if row[field] is not None:
                    row[field]["id"] = int(row[field]["id"])
        if self.fault == "expanded-reference" and name == "device":
            for row in rows:
                row["category"].update({"sortOrder": 0, "version": 1})
        if self.fault == "unknown-reference" and name == "device":
            rows[0]["category"]["untrusted"] = "field"
        page: dict[str, object] = {"total": len(rows), "pageNum": 1, "pageSize": 1000}
        if self.fault == "partial":
            page["hasMore"] = True
        if self.fault == "count":
            page["total"] = len(rows) + 1
        if self.fault == "cursor":
            page["nextCursor"] = "not-finished"
        if self.fault == "unsorted" and len(rows) > 1:
            rows.reverse()
        if self.fault == "float-id" and rows:
            rows[0]["id"] = float(rows[0]["id"])
        if self.fault == "drift" and self.sweeps == 2 and name == "device":
            rows[0]["name"] = "changed"
        if self.fault == "null-missing" and name == "device":
            rows[0].pop("serialNumber")
        return {"values": rows, "pagination": page}


class ExportTest(unittest.TestCase):
    def test_exact_owner_requests_and_independent_oracle(self):
        for variant in ("A", "B", "C"):
            with self.subTest(variant=variant):
                reader = Reader(variant=variant)
                snapshot = exporter.export(reader, reader.target, reader.fixture_bytes)
                document, mapping = tools.normalizer.normalize(snapshot, reader.target)
                self.assertEqual(tools.oracle.verify(document)["variant"], variant)
                self.assertEqual(mapping["entities"]["device"][0]["id"], "9223372036854700000")
                self.assertEqual(len(reader.calls), 15)
                for path, query, binding in reader.calls:
                    self.assertEqual(binding, reader.target["binding"])
                    self.assertEqual(query["deploymentId"], binding["deploymentId"])
                    if "runtime/query" not in path:
                        self.assertEqual(query["application"], "device-management")
                        self.assertTrue(query["entity"].startswith("/deviceManagement/"))
                        self.assertEqual(json.loads(query["_sortFilter"]), {"fieldName": "id", "ascFlag": True})

    def test_partial_drift_authority_and_precision_fail_closed(self):
        for fault in ("identity", "directory", "permission", "metadata-drift", "partial", "count", "cursor", "unsorted", "float-id", "drift", "null-missing", "unknown-reference"):
            with self.subTest(fault=fault):
                reader = Reader(fault)
                with self.assertRaises(ValueError):
                    exporter.export(reader, reader.target, reader.fixture_bytes)

    def test_expanded_owner_reference_has_one_identity_projection(self):
        reader = Reader("expanded-reference")
        snapshot = exporter.export(reader, reader.target, reader.fixture_bytes)
        self.assertEqual(set(snapshot["entities"]["device"]["rows"][0]["category"]), {"id", "code"})
        document, _ = tools.normalizer.normalize(snapshot, reader.target)
        self.assertEqual(tools.oracle.verify(document)["variant"], "A")

    def test_no_credentials_in_url_no_insecure_origin_or_redirect(self):
        for origin in ("http://example.test", "https://user:pass@example.test", "https://example.test/path", "https://example.test?token=secret", "https://example.test/#fragment"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                exporter.AppsReader(origin, "test-token")
        with self.assertRaises(ValueError):
            exporter.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.test")
        reader = Reader()
        with self.assertRaises(ValueError):
            exporter.export(reader, reader.target, reader.fixture_bytes + b" ")
        self.assertEqual(reader.calls, [])


if __name__ == "__main__":
    unittest.main()
