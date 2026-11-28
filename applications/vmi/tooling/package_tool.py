#!/usr/bin/env python3
"""Build/check local VMI definitions using the official Runner codec; no HTTP or Live writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_app_model_root, resolve_workspace_root

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = resolve_app_model_root("vmi")
WORKSPACE = resolve_workspace_root()

ACTION_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
EXPECTED_TEMPLATES = {"vmi-viewer", "warehouse-operator", "store-clerk", "vmi-manager", "vmi-ingestor"}


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key}: {path}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def validate_source(root: Path = MODEL_ROOT):
    base = root / "definition/application"
    for path in (root / "definition").rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlinks are not definition sources: {path}")
        if path.is_file() and path.suffix == ".json":
            read_json(path)
    profile = read_json(root / "definition/profile.json")
    app = read_json(base / "metadata.json")
    catalog = str(app.get("catalog", "")).strip()
    if not catalog or catalog.lower() == "inner":
        raise ValueError("application catalog must be non-empty and not inner")
    pages = read_json(base / "pages/definition.json")
    blocks = read_json(base / "blocks/index.json")
    identity = (app["name"], app["uuid"], profile["modelRevision"])
    if identity != (profile["key"], profile["uuid"], pages["modelRevision"]):
        raise ValueError("model profile identity mismatch")
    for doc in (pages, blocks):
        if identity != (doc["applicationKey"], doc["applicationUuid"], doc["modelRevision"]):
            raise ValueError("page/block identity mismatch")
    if app["version"] != profile["version"] or profile["businessReady"]:
        raise ValueError("validation profile/version mismatch")

    entities = [read_json(p) for p in sorted((base / "entities").glob("*.json"))]
    expected = {
        "partner", "warehouse", "shelf", "product", "productInfo", "store",
        "member", "goods", "stockin", "stockout", "goodsInfo", "order",
        "goodsItem", "rewardPolicy", "credit", "creditReward", "creditReport",
        "inventoryAlert",
    }
    if {e["name"] for e in entities} != expected or len(entities) != len(expected):
        raise ValueError("expected 18 VMI business entities")

    expected_members = {"metadata.json", "pages/definition.json", "blocks/index.json"}
    expected_members.update(f"entities/{name}.json" for name in expected)
    refs = {item["key"]: item["definition"] for item in blocks["definitions"]}
    if refs != {
        "goodsInfo.alert": "goods-movement-alert/definition.json",
        "goodsItem.alert": "order-item-alert/definition.json",
    }:
        raise ValueError("expected two VMI CreateEffect blocks")
    for key, name in refs.items():
        block = read_json(base / "blocks" / name)
        directory = name.split("/")[0]
        if block["key"] != key or set(block["sourceFiles"]) != {directory + "/main.go", directory + "/validation.go"}:
            raise ValueError("block source closure mismatch: " + key)
        expected_members.add("blocks/" + name)
        expected_members.update("blocks/" + member for member in block["sourceFiles"])
    actual_members = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    if actual_members != expected_members:
        raise ValueError(f"unindexed/missing definition members: diff={actual_members ^ expected_members}")

    assets_dir = root / "definition/assets"
    assets_index = read_json(assets_dir / "index.json")
    if assets_index.get("schemaVersion") != "magic.application-assets/v1" or len(assets_index.get("files", [])) != 4:
        raise ValueError("expected 4 appearance assets in definition/assets/index.json")
    for item in assets_index["files"]:
        asset_file = root / "definition" / item["path"]
        raw_bytes = asset_file.read_bytes()
        if len(raw_bytes) != item["size"] or "sha256:" + hashlib.sha256(raw_bytes).hexdigest() != item["digest"]:
            raise ValueError("asset digest/size mismatch: " + item["path"])

    declared_action_pairs = []
    enabled = 0
    for e in entities:
        if e["version"] != app["version"] or e["pkgPath"] != "/" + app["pkgPrefix"]:
            raise ValueError("entity namespace/version mismatch: " + e["name"])
        caps = {c["key"]: c["enabled"] for c in e["serviceExpose"]["capabilities"]}
        enabled += sum(caps.values())
        for act in e.get("writeRules", {}).get("actions", []):
            k = act["key"]
            if not ACTION_KEY_RE.fullmatch(k):
                raise ValueError("invalid action key: " + k)
            declared_action_pairs.append((f"/{app['pkgPrefix']}/{e['name']}", k))

    auth = app.get("authorization", {})
    expected_sorted_actions = [
        {"entity": ent, "action": act}
        for ent, act in sorted(declared_action_pairs, key=lambda pair: f"/apps/entity-actions{pair[0]}/{pair[1]}")
    ]
    if auth.get("entityActions") != expected_sorted_actions:
        raise ValueError("metadata authorization.entityActions does not match sorted entity actions")
    templates = auth.get("templates", [])
    if {t["key"] for t in templates} != EXPECTED_TEMPLATES:
        raise ValueError("metadata authorization.templates must match 5 VMI templates")
    for template in templates:
        roles = set(template.get("roleKeys", []))
        if template.get("subjectType") == "account":
            if "application-viewer" not in roles or "application-data-read" in roles:
                raise ValueError(f"account template {template.get('key')} violates application-viewer rule")

    readiness = read_json(root / "definition/readiness.json")
    if enabled != readiness["enabledCapabilities"] or readiness["liveReady"] or readiness["businessReady"]:
        raise ValueError("capability readiness mismatch")
    if pages.get("navigationMode") != "tree" or len(pages.get("navigation", [])) != 6:
        raise ValueError("pages must declare navigationMode=tree with 6 groups")
    return profile


def source_fingerprints():
    result = {}
    for p in sorted((MODEL_ROOT / "definition").rglob("*")):
        if p.is_file():
            result[p.relative_to(MODEL_ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    local_files = sorted((ROOT / "tooling").glob("*.py")) + [ROOT / "tooling/package_codec_test.go.txt"] + sorted((ROOT / "tooling/testdata").glob("*.json"))
    for p in local_files:
        if p.is_file():
            result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def run(mode: str, package: Path | None = None, runner: Path | None = None):
    validate_source()
    runner = (runner or WORKSPACE / "magicRunner").expanduser().resolve()
    before = source_fingerprints()
    template = ROOT / "tooling/package_codec_test.go.txt"
    with tempfile.TemporaryDirectory(prefix="vmi-definition-") as temp:
        temp_path = Path(temp)
        output = temp_path / "result"
        actual = temp_path / "definition_test.go"
        actual.write_bytes(template.read_bytes())
        virtual = runner / "internal/modules/kernel/panel/pkg/modelpackage" / f"zz_{temp_path.name.replace('-', '_')}_test.go"
        if virtual.exists():
            raise ValueError("overlay target already exists")
        overlay = temp_path / "overlay.json"
        overlay.write_text(json.dumps({"Replace": {str(virtual): str(actual)}}), encoding="utf-8")
        env = dict(
            os.environ,
            GOWORK="off",
            VMI_DEFINITION_ROOT=str(MODEL_ROOT),
            VMI_TOOLING_ROOT=str(ROOT),
            VMI_TOOL_OUTPUT=str(output),
            VMI_TOOL_MODE=mode,
        )
        if package:
            env["VMI_INSPECT_PACKAGE"] = str(package.expanduser().resolve())
        subprocess.run(
            ["go", "test", "-overlay", str(overlay), "./internal/modules/kernel/panel/pkg/modelpackage", "-run", "^TestVMIDefinitionTool$", "-count=1", "-v"],
            cwd=runner,
            env=env,
            check=True,
            timeout=240,
        )
        if before != source_fingerprints():
            raise ValueError("definition/tool source changed during validation")
        report = read_json(output / "source-checks.json")
        report["sourceSHA256"] = before
        report["sourceCommits"] = {
            name: subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runner if name == "magicRunner" else WORKSPACE / name, text=True).strip()
            for name in ("magicRunner", "magicBase", "magicOrm")
        }
        (output / "source-checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    return report, files


def write_bundle(destination: Path, files: dict[str, bytes]):
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("output already exists; preserve it and choose a new --output-dir")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    for name, raw in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    checksum = hashlib.sha256((destination / "package.zip").read_bytes()).hexdigest()
    (destination / "SHA256SUMS").write_text(f"{checksum}  package.zip\n", encoding="utf-8")
    (destination / "README.md").write_text(
        "# VMI 供应商管理库存候选模型包\n\n"
        "- [package.zip](~/dataspace/magicPlatform/apps/models/vmi/package/package.zip)\n"
        "- [source-checks.json](~/dataspace/magicPlatform/apps/models/vmi/package/source-checks.json)\n"
        "- [schema-preflight.json](~/dataspace/magicPlatform/apps/models/vmi/package/schema-preflight.json)\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "build", "inspect"])
    parser.add_argument("--package", type=Path, help="downloaded standard ZIP for inspect")
    parser.add_argument("--output-dir", type=Path, help="new output directory; never overwrites")
    parser.add_argument("--runner-root", type=Path, help="Runner checkout; defaults to workspace sibling")
    args = parser.parse_args()
    if (args.command == "inspect") != bool(args.package):
        parser.error("--package is required only for inspect")
    destination = args.output_dir or (MODEL_ROOT / "package")
    if (args.command == "build" or args.output_dir) and (destination.exists() or destination.is_symlink()):
        parser.error("output already exists; choose a new --output-dir")
    report, files = run(args.command, args.package, args.runner_root)
    if args.command == "build" or (args.command == "inspect" and args.output_dir):
        write_bundle(destination, files)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
