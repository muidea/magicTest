#!/usr/bin/env python3
"""只读场景／用例／脚本导航；不执行测试，不生成验收通过结论。"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

from test_catalog import TARGETS


ROOT = Path(__file__).resolve().parent
DEFAULT_INVENTORY = ROOT / "regression" / "inventory.json"


def resolve_reference(reference: str, workspace: Path, platform: Path) -> Path:
    roots = {"~/codespace/": workspace, "~/dataspace/magicPlatform/": platform}
    for prefix, root in roots.items():
        if reference.startswith(prefix):
            suffix = reference[len(prefix):]
            if not suffix or ".." in PurePosixPath(suffix).parts:
                raise ValueError(f"非法仓库引用: {reference}")
            resolved = (root / suffix).resolve()
            if not resolved.is_relative_to(root.resolve()):
                raise ValueError(f"仓库引用越界: {reference}")
            return resolved
    raise ValueError(f"仓库引用必须使用登记的 ~/ 前缀: {reference}")


def unique_index(items: list[dict], field: str) -> dict:
    result = {}
    for item in items:
        key = item[field]
        if key in result:
            raise ValueError(f"重复 {field}: {key}")
        result[key] = item
    return result


def validate_inventory(inventory: dict, catalog: dict, workspace: Path, platform: Path) -> None:
    features = unique_index(catalog["features"], "id")
    cases = unique_index(catalog["cases"], "id")
    assets = unique_index(inventory["assets"], "id")
    scenarios = unique_index(inventory["scenarios"], "id")
    if inventory["scope"] != "platform-basic":
        raise ValueError("平台基本功能与模拟应用必须分列")
    assigned = Counter(fid for s in scenarios.values() for fid in s["featureIds"])
    if set(assigned) != set(features) or any(count != 1 for count in assigned.values()):
        raise ValueError("每类功能必须且只能归入一个主场景，不能遗漏或引用未知功能")
    if any(c["featureId"] not in features for c in cases.values()):
        raise ValueError("用例引用未知功能")
    target_ids = {target.key for target in TARGETS}
    references = [inventory["sourceCatalog"], *inventory["applicationSuites"]]
    for asset in assets.values():
        references.append(asset["path"])
        if asset.get("target") and asset["target"] not in target_ids:
            raise ValueError(f"未知统一入口 target: {asset['target']}")
        if asset["layer"] not in {"api", "browser", "browser-api", "source", "source-inventory", "tool"}:
            raise ValueError(f"未知资产层次: {asset['id']}")
        if not asset["limitation"].strip():
            raise ValueError(f"缺资产限制: {asset['id']}")
    for scenario in scenarios.values():
        if not scenario["owners"] or not scenario["featureIds"]:
            raise ValueError(f"缺 owner 或功能: {scenario['id']}")
        if set(scenario["candidateAssets"]) - assets.keys():
            raise ValueError(f"场景引用未知资产: {scenario['id']}")
    for review in unique_index(inventory["caseReviews"], "caseId").values():
        if review["caseId"] not in cases:
            raise ValueError(f"复核引用未知用例: {review['caseId']}")
        # 本盘点仅登记候选与缺口；稳定执行资格须在完成用例卡及实跑后另行评审。
        if review["status"] not in {"partial", "needs_rewrite", "unreviewed"}:
            raise ValueError(f"盘点不能声明完整覆盖或验收通过: {review['caseId']}")
        if set(review["assetIds"]) - assets.keys() or not review["finding"].strip():
            raise ValueError(f"复核缺少有效资产或发现: {review['caseId']}")
    for reference in references:
        if not resolve_reference(reference, workspace, platform).is_file():
            raise ValueError(f"引用文件不存在: {reference}")


def build_rows(inventory: dict, catalog: dict) -> list[dict]:
    scenarios = {fid: s for s in inventory["scenarios"] for fid in s["featureIds"]}
    reviews = {r["caseId"]: r for r in inventory["caseReviews"]}
    rows = []
    for case in catalog["cases"]:
        scenario = scenarios[case["featureId"]]
        review = reviews.get(case["id"], {})
        rows.append({
            "caseId": case["id"], "title": case["title"],
            "scenarioId": scenario["id"], "scenario": scenario["title"],
            "kind": case["kind"], "fixture": case["fixture"],
            "methods": case["methods"], "priority": case["priority"],
            "owners": scenario["owners"],
            "status": review.get("status", "unreviewed"),
            "candidateAssets": scenario["candidateAssets"],
            "reviewedAssets": review.get("assetIds", []),
            "finding": review.get("finding", "尚未逐断言复核；场景候选不代表本用例已有脚本覆盖。"),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--catalog", type=Path, help="显式指定原用例目录，不复制用例定义")
    parser.add_argument("--workspace", type=Path, default=ROOT.parent)
    parser.add_argument("--platform-root", type=Path, default=Path.home() / "dataspace/magicPlatform")
    parser.add_argument("--check", action="store_true", help="检查功能完整分组、用例引用、target及文件存在性")
    parser.add_argument("--case", help="查看单条固定编号用例，例如 F033-001")
    parser.add_argument("--scenario", help="按主场景筛选，例如 R07")
    parser.add_argument("--json", action="store_true", help="输出全部或筛选后的逐用例映射")
    args = parser.parse_args(argv)
    try:
        inventory = json.loads(args.inventory.read_text())
        catalog_path = args.catalog or resolve_reference(inventory["sourceCatalog"], args.workspace, args.platform_root)
        catalog = json.loads(catalog_path.read_text())
        validate_inventory(inventory, catalog, args.workspace, args.platform_root)
        rows = build_rows(inventory, catalog)
        if args.scenario:
            if args.scenario not in {s["id"] for s in inventory["scenarios"]}:
                raise ValueError(f"未知场景: {args.scenario}")
            rows = [r for r in rows if r["scenarioId"] == args.scenario]
        if args.case:
            rows = [r for r in rows if r["caseId"] == args.case]
        if not rows:
            raise ValueError("没有匹配的用例")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"盘点检查失败: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"purpose": "inventory-only", "cases": rows, "assets": inventory["assets"]}, ensure_ascii=False, indent=2))
    elif args.case or args.scenario:
        assets = {a["id"]: a for a in inventory["assets"]}
        for row in rows:
            print(f"{row['caseId']} {row['title']} [{row['scenarioId']}/{row['status']}]")
            print(f"  {row['finding']}")
            for aid in row["candidateAssets"]:
                print(f"  候选 {aid}: {assets[aid]['path']}")
                print(f"    {assets[aid]['limitation']}")
    else:
        for scenario in inventory["scenarios"]:
            selected = [r for r in rows if r["scenarioId"] == scenario["id"]]
            print(f"{scenario['id']} {scenario['title']}: {len(scenario['featureIds'])}类功能 / {len(selected)}条用例 / {len(scenario['candidateAssets'])}个候选资产")
        print(f"结构检查通过：{len(inventory['scenarios'])}个场景，{len(catalog['features'])}类功能，{len(rows)}条用例。")
        print("脚本复核状态：" + json.dumps(Counter(r["status"] for r in rows), ensure_ascii=False))
        print("仅证明盘点结构与引用有效；不表示脚本就绪、业务通过或Live完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
