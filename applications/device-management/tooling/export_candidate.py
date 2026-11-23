#!/usr/bin/env python3
"""Export the explicitly blocked device-management definition fixture."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_app_model_root, resolve_workspace_root


def validate_function_blocks(root, artifact):
    library_root = root / "definition/blocks"
    index = json.loads((library_root / "index.json").read_text())
    if index["schemaVersion"] != "magic.application-function-blocks/v1":
        raise ValueError("unsupported function block library schema")
    if (index["applicationKey"], index["applicationUuid"], index["modelRevision"]) != (
            artifact["applicationKey"], artifact["applicationUuid"], artifact["version"]):
        raise ValueError("function block library belongs to another model")
    if "functionBlocks" in artifact["application"]:
        raise ValueError("scripts must be managed in separate function block files")
    expected = {"index.json"}
    keys = set()

    def read_member(name, suffix):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name:
            raise ValueError("invalid function block member path")
        target = library_root / name
        if not target.resolve().is_relative_to(library_root.resolve()) or target.is_symlink():
            raise ValueError("function block file escapes definition directory")
        if path.suffix != suffix or name in expected:
            raise ValueError("invalid or duplicate function block file")
        expected.add(name)
        return target.read_text()

    for entry in index["definitions"]:
        key = entry["key"]
        if not key or key.strip() != key or key in keys:
            raise ValueError("empty or duplicate function block key")
        keys.add(key)
        definition = json.loads(read_member(entry["definition"], ".json"))
        if definition["key"] != key or not definition["name"].strip():
            raise ValueError("function block definition identity mismatch")
        if definition["language"] != "go":
            raise ValueError("unsupported script language")
        files = definition["sourceFiles"]
        if not files or definition["entrypoint"]["file"] not in files:
            raise ValueError("function block source files or entrypoint are missing")
        for name in files:
            if PurePosixPath(name).parent != PurePosixPath(entry["definition"]).parent:
                raise ValueError("script source must belong to its own function block directory")
            read_member(name, ".go")
    actual = {str(path.relative_to(library_root)) for path in library_root.rglob("*") if path.is_file()}
    if expected != actual:
        raise ValueError("function block library has missing or unindexed files")
    for entity in artifact["entities"]:
        for block in entity.get("blockInfo") or []:
            if block.get("scriptKey") and block["scriptKey"] not in keys:
                raise ValueError("entity references a missing script function block")


def validate_design(root):
    artifact = json.loads((root / "definition/candidate.artifact.json").read_text())
    design = json.loads((root / "definition/page-definition.artifact.json").read_text())
    if "uiMeta" in artifact["application"]:
        raise ValueError("application pages must be managed in the separate page definition")
    if (artifact["application"]["name"], artifact["application"]["uuid"]) != (
            artifact["applicationKey"], artifact["applicationUuid"]):
        raise ValueError("application metadata does not match the model identity")
    if (design["applicationKey"], design["applicationUuid"], design["modelRevision"]) != (
            artifact["applicationKey"], artifact["applicationUuid"], artifact["version"]):
        raise ValueError("page definition does not match the application identity/revision")
    if design["schemaVersion"] != "magic.application-ui/v1":
        raise ValueError("unsupported candidate page schema")
    validate_function_blocks(root, artifact)
    entities = {e["pkgPath"] + "/" + e["name"]: e for e in artifact["entities"]}
    if len(entities) != 6 or sum(len(e["fields"]) for e in entities.values()) != 57:
        raise ValueError("expected six complete entities and 57 fields")
    if set(design["entityViews"]) != set(entities):
        raise ValueError("entity view definitions must match model entities")
    for entity_key, entity in entities.items():
        if "uiMeta" in entity:
            raise ValueError("entity display metadata must be in the page definition")
        # Entity members are flat under application/entities and use only the
        # short entity name; the application prefix remains in the manifest key.
        entity_member = "application/entities/" + entity_key.rsplit("/", 1)[-1] + ".json"
        if "/" in PurePosixPath(entity_member).name:
            raise ValueError("entity package members must remain one directory deep")
        names = {f["name"] for f in entity["fields"]}
        if len(names) != len(entity["fields"]):
            raise ValueError("duplicate field")
        for field in entity["fields"]:
            typ = field["type"]
            if typ["pkgPath"] and typ["pkgPath"] + "/" + typ["name"] not in entities:
                raise ValueError("missing relationship target")
        for key in ("uniqueConstraints", "indexes"):
            for declaration in entity.get(key) or []:
                if not set(declaration["fields"]) <= names:
                    raise ValueError("invalid schema field reference")
        ui = design["entityViews"][entity_key]
        references = ui["list"]["columns"] + ui["list"]["filters"]
        for section in ui["detail"]["sections"] + ui["form"]["sections"]:
            references += section["fields"]
        if not set(references) <= names:
            raise ValueError("invalid entity UI field reference")
    location = entities["/deviceManagement/location"]
    parent = next(f for f in location["fields"] if f["name"] == "parent")
    if parent["type"]["name"] != "location" or not parent["type"]["isPtr"]:
        raise ValueError("self reference must be preserved")
    sources = {s["key"]: s for s in design["dataSources"]}
    pages = {p["key"]: p for p in design["pages"]}
    if set(sources) != {f"DS{index:02d}" for index in range(1, 13)} or len(pages) != 10:
        raise ValueError("expected DS01 through DS12 and all 10 pages")
    if len(sources) != len(design["dataSources"]) or len(pages) != len(design["pages"]):
        raise ValueError("duplicate page or source key")
    for source in sources.values():
        names = {f["name"] for f in entities[source["entity"]]["fields"]}
        references = list(source["fields"]) + source.get("groupBy", [])
        references += [order["field"] for order in source.get("orderBy", [])]
        for key in ("timeWindow", "bucket"):
            if key in source:
                references.append(source[key]["field"])
        for metric in source.get("metrics", []):
            if "field" in metric:
                references.append(metric["field"])
            references += [f["field"] for f in metric.get("filters", [])]
        if not set(references) <= names:
            raise ValueError("invalid source field reference")
    routes = set()
    for page in pages.values():
        for route in page["routes"]:
            if route in routes:
                raise ValueError("duplicate page route")
            routes.add(route)
            parameters = {part[1:] for part in route.split("/") if part.startswith(":")}
            if not parameters <= set(page["routeParameters"]):
                raise ValueError("undeclared route parameter")
        components = page["components"]
        if len({c["key"] for c in components}) != len(components):
            raise ValueError("duplicate component key")
        for component in components:
            if not set(component["dataSources"]) <= sources.keys():
                raise ValueError("invalid component source reference")
            if not 1 <= component["layout"]["span"] <= page["layout"]["columns"]:
                raise ValueError("invalid component span")
            properties = component["properties"]
            for key in ("detailPage", "editorPage", "devicePage"):
                if key in properties and properties[key] not in pages:
                    raise ValueError("invalid component page reference")
            if not set(properties.get("links", {}).values()) <= pages.keys():
                raise ValueError("invalid metric page reference")
            for parameter in component.get("parameters", {}).values():
                if parameter["from"] == "route" and parameter["name"] not in page["routeParameters"]:
                    raise ValueError("invalid component route parameter")
            if "entity" in properties:
                names = {f["name"] for f in entities[properties["entity"]]["fields"]}
                references = []
                for key in ("fields", "columns", "filters", "readonlyFields"):
                    references += properties.get(key, [])
                for section in properties.get("sections", []):
                    references += section["fields"]
                if not set(references) <= names:
                    raise ValueError("invalid component entity field reference")
    if design["defaultPage"] not in pages:
        raise ValueError("invalid default page")
    if design.get("navigationMode") not in (None, "top", "tree"):
        raise ValueError("invalid navigationMode")

    def walk_nav(items, depth=0):
        if not isinstance(items, list) or depth > 8:
            raise ValueError("invalid navigation tree depth or container")
        for entry in items:
            if isinstance(entry, str):
                if entry not in pages:
                    raise ValueError("invalid navigation page reference")
            elif isinstance(entry, dict) and entry.get("group") and entry.get("children"):
                walk_nav(entry["children"], depth + 1)
            else:
                raise ValueError("invalid navigation item")

    walk_nav(design["navigation"])


def finish_delivery(root, workspace, temporary):
    report = json.loads((temporary / "validation-report.json").read_text())
    report["sourceCommits"] = {
        name: subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=workspace / name, text=True
        ).strip()
        for name in ("magicRunner", "magicBase", "magicOrm")
    }
    report["designReferencesValid"] = True
    verification = root / "verification"
    verification.mkdir(exist_ok=True)
    (verification / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    os.replace(temporary / "candidate.canonical-artifact.json",
               verification / "candidate.canonical-artifact.json")
    os.replace(temporary / "page-definition.canonical-artifact.json",
               verification / "page-definition.canonical-artifact.json")
    output = root / "model-package/output"
    output.mkdir(parents=True, exist_ok=True)
    name = "device-management-0.1.0-dev.1-definition-candidate.zip"
    os.replace(temporary / name, output / name)
    unpacked = root / "model-package/unpacked"
    if unpacked.exists():
        shutil.rmtree(unpacked)
    os.replace(temporary / "unpacked", unpacked)
    digest = hashlib.sha256((output / name).read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  {name}\n")
    print(f"Single model candidate created: {name} (page extension; blocked import)")


def load_unpacked(root):
    """Read edits to the unpacked package; never trust its stale checksums."""
    unpacked = root / "model-package/unpacked"
    manifest = json.loads((unpacked / "package.json").read_text())
    content = manifest["content"]

    def read_member(name):
        path = (unpacked / name).resolve()
        if not path.is_relative_to(unpacked.resolve()):
            raise ValueError("unpacked member escapes package directory")
        return json.loads(path.read_text())

    artifact_path = root / "definition/candidate.artifact.json"
    artifact = json.loads(artifact_path.read_text())
    identity = manifest["application"]
    if (identity["key"], identity["uuid"], identity["modelRevision"]) != (
            artifact["applicationKey"], artifact["applicationUuid"], artifact["version"]):
        raise ValueError("unpacked package identity differs from the candidate")
    expected = {"package.json", "checksums.json", content["application"], content["pages"]}
    expected.update(item["path"] for item in content["entities"])
    block_prefix = "application/blocks/"
    if content["functionBlocks"] != block_prefix + "index.json":
        raise ValueError("unexpected function block index path")
    expected.update(str(path.relative_to(unpacked)) for path in
                    (unpacked / block_prefix).rglob("*") if path.is_file())
    actual = {str(path.relative_to(unpacked)) for path in unpacked.rglob("*") if path.is_file()}
    if expected != actual:
        raise ValueError("unpacked package has missing or unexpected members")
    artifact["application"] = read_member(content["application"])
    artifact["entities"] = [read_member(item["path"]) for item in content["entities"]]
    artifact["artifactDigest"] = ""
    pages = read_member(content["pages"])
    # The library index and source files are separately validated before export.
    block_root = unpacked / block_prefix
    return artifact, pages, block_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-unpacked", action="store_true",
                        help="read edits from unpacked package and regenerate all digests")
    parser.add_argument("--model-root", type=Path,
                        help="authoritative device-management model root (defaults to magicPlatform/apps/models/device-management)")
    args = parser.parse_args()
    tooling = Path(__file__).resolve().parent
    root = args.model_root.expanduser().resolve() if args.model_root else resolve_app_model_root("device-management")
    workspace = resolve_workspace_root()
    if (root / "definition/threshold-execution.design.json").exists():
        parser.error("threshold V3 is a design candidate with no active reliable effect binding; "
                     "use validate_threshold_candidate.py for offline checks and Panel for formal publication; "
                     "this historical exporter must not overwrite baseline packages")
    runner = workspace / "magicRunner"
    codec = runner / "internal/modules/kernel/panel/pkg/modelpackage"
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="device-model-candidate-") as working:
        working = Path(working)
        definition_root = root
        if args.from_unpacked:
            artifact, pages, block_root = load_unpacked(root)
            definition_root = working
            (working / "definition").mkdir()
            for name, value in (("candidate.artifact.json", artifact),
                                ("page-definition.artifact.json", pages)):
                (working / "definition" / name).write_text(
                    json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            shutil.copytree(block_root, working / "definition/blocks")
        validate_design(definition_root)
        source = definition_root / "definition/candidate.artifact.json"
        page_source = definition_root / "definition/page-definition.artifact.json"
        env.update(GOWORK="off", DEVICE_CANDIDATE_SOURCE=str(source),
                   DEVICE_PAGE_SOURCE=str(page_source),
                   DEVICE_BLOCK_SOURCE=str(definition_root / "definition/blocks"),
                   DEVICE_CANDIDATE_OUTPUT=str(working))
        # Run current codec helpers without changing production admission.
        with tempfile.NamedTemporaryFile(
            dir=codec, prefix="zz_device_candidate_", suffix="_test.go", delete=False
        ) as temporary:
            temporary.write((tooling / "export_candidate_test.go.txt").read_bytes())
            temporary_path = Path(temporary.name)
        try:
            subprocess.run(
                ["go", "test", "./internal/modules/kernel/panel/pkg/modelpackage",
                 "-run", "^TestExportDeviceManagementDefinitionCandidate$", "-count=1", "-v"],
                cwd=runner, env=env, check=True,
            )
        finally:
            temporary_path.unlink(missing_ok=True)
        if args.from_unpacked:
            for name in ("candidate.artifact.json", "page-definition.artifact.json"):
                shutil.copyfile(working / "definition" / name, root / "definition" / name)
            shutil.rmtree(root / "definition/blocks")
            shutil.copytree(working / "definition/blocks", root / "definition/blocks")
        finish_delivery(root, workspace, working)


if __name__ == "__main__":
    main()
