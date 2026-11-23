#!/usr/bin/env python3
"""离线预检固定 A/B/C 材料、独立目标与可选 owner 回读；不连接网络、不写实例或清理数据。"""
import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalizer, oracle = load("normalize_readback"), load("fixture_oracle")
require = normalizer.require
VARIANTS = ("A", "B", "C")


def read_bounded(path, limit):
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    require(len(payload) <= limit, "离线预检输入超过预算")
    return payload


def verify(bundle, target_document, snapshots=None):
    require(isinstance(target_document, dict) and set(target_document) == {"schemaVersion", "targets"}
            and target_document["schemaVersion"] == "magic.device-validation-targets/v1", "预检目标集合合同无效")
    targets = target_document["targets"]
    require(isinstance(targets, dict) and set(targets) == set(VARIANTS), "必须独立声明 A/B/C 三个目标")
    manifest = normalizer.strict_json(read_bounded(bundle / "manifest.json", 16 << 10))
    require(isinstance(manifest, dict) and set(manifest) == {"schemaVersion", "synthetic", "files", "initialization", "live"}
            and manifest["schemaVersion"] == "magic.device-fixture-manifest/v1" and manifest["synthetic"] is True
            and manifest["initialization"] == "not-run" and manifest["live"] == "not-run", "固定样例清单合同或证据边界无效")
    require(isinstance(manifest["files"], dict) and set(manifest["files"]) == {v + ".json" for v in VARIANTS}, "固定样例成员不完整")
    require(snapshots is None or isinstance(snapshots, dict) and set(snapshots) == set(VARIANTS), "回读必须完整提供 A/B/C，不能以单实例证明隔离")
    reports, bindings = {}, {}
    for variant in VARIANTS:
        payload = read_bounded(bundle / (variant + ".json"), 8 << 20)
        entry = manifest["files"][variant + ".json"]
        require(isinstance(entry, dict) and set(entry) == {"size", "digest"}
                and type(entry["size"]) is int and entry["size"] == len(payload)
                and entry["digest"] == normalizer.digest(payload), "固定样例清单大小或摘要不匹配")
        fixture = normalizer.strict_json(payload)
        expected = oracle.verify(fixture)
        require(expected["variant"] == variant, "固定样例文件与变体不匹配")
        target = targets[variant]
        require(isinstance(target, dict) and target.get("variant") == variant and target.get("fixtureDigest") == entry["digest"], "独立目标与固定样例摘要不匹配")
        # 使用空记录仅验证严格目标合同，不从回读推断身份，不视为空库证明。
        empty = {"schemaVersion": "magic.device-owner-readback/v1", "binding": target["binding"], "variant": variant,
                 "fixtureDigest": entry["digest"], "dataVersion": fixture["dataVersion"], "definitionVersion": fixture["definitionVersion"],
                 "synthetic": True, "anchor": fixture["anchor"], "entities": {
                     name: {"pkgKey": "/deviceManagement/" + name, "complete": True, "total": 0, "rows": []}
                     for name in normalizer.ENTITIES}}
        normalizer.normalize(empty, target)
        bindings[variant] = target["binding"]
        report = {"fixtureDigest": entry["digest"], "expected": expected, "ownerReadback": "not-run"}
        if snapshots is not None:
            raw = snapshots[variant]
            require(isinstance(raw, bytes) and len(raw) <= 8 << 20, "owner 回读超过预算或不是原始字节")
            logical, _ = normalizer.normalize(normalizer.strict_json(raw), target)
            actual = oracle.verify(logical)
            require(actual == expected, "owner 回读独立对账与固定样例不符")
            # oracle 负责独立业务公式；逐字段比较另外保护名称、描述等非统计内容。
            for name in normalizer.ENTITIES:
                def natural(row):
                    return json.dumps([row["device"], row["sampledAt"]] if name == "telemetry" else [row["code"]], ensure_ascii=False)
                observed = json.dumps(sorted(logical["entities"][name], key=natural), ensure_ascii=False, sort_keys=True, allow_nan=False)
                wanted = json.dumps(sorted(fixture["entities"][name], key=natural), ensure_ascii=False, sort_keys=True, allow_nan=False)
                require(observed == wanted, "owner 回读逻辑字段或 JSON 值类型与固定样例不符: " + name)
            report.update(ownerReadback="offline-observation-verified", snapshotDigest=normalizer.digest(raw))
        reports[variant] = report
    require(bindings["A"]["namespace"] == bindings["B"]["namespace"]
            and bindings["C"]["namespace"] != bindings["A"]["namespace"], "A/B 必须同租户、C 必须异租户")
    for field in ("deploymentId", "runtimeApplicationUuid"):
        require(len({bindings[v][field] for v in VARIANTS}) == 3, "A/B/C 必须是不同运行实例")
    require(len({bindings[v]["artifactDigest"] for v in VARIANTS}) == 1, "A/B/C 必须绑定同一个固定模型候选")
    return {"schemaVersion": "magic.device-offline-preflight/v1", "mode": "offline-read-only", "variants": reports,
            "targetIsolation": "contract-verified-not-runtime-proof", "initialization": "not-run", "cleanup": "not-run",
            "live": "not-run", "liveReady": False,
            "remainingEvidence": ["authorized-initialization-and-operation-recovery", "actual-owner-export-provenance",
                                  "database-concurrency-and-isolation", "precise-cleanup-authorization-and-readback", "DMUI-001-030"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path, help="独立核验的 A/B/C 目标集合，不从回读自动生成")
    for variant in VARIANTS:
        parser.add_argument("--snapshot-" + variant.lower(), type=Path)
    args = parser.parse_args()
    paths = {v: getattr(args, "snapshot_" + v.lower()) for v in VARIANTS}
    require(not any(paths.values()) or all(paths.values()), "必须一起提供三个 owner 回读")
    snapshots = {v: read_bounded(paths[v], 8 << 20) for v in VARIANTS} if all(paths.values()) else None
    result = verify(args.bundle, normalizer.strict_json(read_bounded(args.targets, 64 << 10)), snapshots)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
