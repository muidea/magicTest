"""Bind isolated source acceptance to a frozen static delivery and local images.

This proves input identity, not execution of the released service entrypoints.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


OWNERS = {"magicBase", "magicCas", "magicFile", "magicRunner", "magicWebPortal"}
APPLICATIONS = {"magicBase", "magicCas", "magicFile", "magicPanel", "magicGateway", "magicInstaller", "magicWebPortal"}


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def read_input(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("candidate input is unavailable or unsafe")
    return path.read_bytes()


def frozen_record(path):
    data = read_input(path)
    for parent in path.parents:
        manifest = parent / "SHA256SUMS"
        if manifest.is_file():
            relative = str(path.relative_to(parent))
            entries = [line.split("  ", 1) for line in read_input(manifest).decode().splitlines()]
            matches = [digest for digest, name in entries if name == relative]
            if matches != [checksum(data)]:
                raise ValueError("candidate frozen record checksum differs")
            return data
    raise ValueError("candidate acceptance requires frozen input records")


def image_source_snapshot(workspace):
    paths = set()
    for name in OWNERS:
        owner = workspace / name
        for current, children, files in os.walk(owner):
            children[:] = [name for name in children if name not in {
                ".git", "node_modules", "bin", "dist", ".umi", ".umi-production",
                ".umi-test", ".mfsu", ".swc", "coverage"}]
            for name in files:
                path = Path(current) / name
                if owner.name == "magicWebPortal":
                    if (any(path.is_relative_to(owner / part) for part in ("src", "public", "docker", "scripts"))
                            or path.parent == owner and (path.suffix in {".ts", ".js", ".json"} or path.name == "yarn.lock")):
                        paths.add(path)
                elif path.suffix in {".go", ".json", ".toml", ".sh", ".tpl"} or name in {"go.mod", "go.sum", "Dockerfile", "Makefile", "modules.txt"}:
                    paths.add(path)
    return {"~/codespace/" + str(path.relative_to(workspace)): checksum(read_input(path)) for path in sorted(paths)}


def inspect_image(address):
    result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", address],
                            check=True, capture_output=True, text=True)
    return result.stdout.strip()


def bind_candidate(workspace, delivery, images, inspect=inspect_image, snapshot=image_source_snapshot):
    workspace, delivery, images = map(lambda path: Path(path).absolute(), (workspace, delivery, images))
    for path in (workspace, delivery, images):
        if path.resolve(strict=True) != path or not path.is_dir():
            raise ValueError("candidate paths must be real directories")
    metadata = frozen_record(delivery / "delivery.json")
    record = json.loads(metadata)
    if record.get("apiVersion") != "magic.static-delivery/v1" or record.get("liveReady") is not False:
        raise ValueError("candidate delivery completion record is invalid")
    expected = record.get("deliverySHA256", {})
    if not expected or len(expected) > 4096:
        raise ValueError("candidate delivery file inventory is invalid")
    for name, digest in expected.items():
        path = PurePosixPath(name)
        if path.is_absolute() or str(path) != name or ".." in path.parts or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("candidate delivery inventory path is invalid")
        target = delivery / name
        if target.resolve(strict=True) != target or checksum(read_input(target)) != digest:
            raise ValueError("candidate delivery contents changed")
    actual = {str(path.relative_to(delivery)) for path in delivery.rglob("*") if path.is_file()}
    if actual != set(expected) | {"delivery.json"}:
        raise ValueError("candidate delivery contains undeclared files")
    source_bytes = frozen_record(images / "image-build-source-sha256.json")
    sources = json.loads(source_bytes)
    if sources != snapshot(workspace):
        raise ValueError("current source/vendor/build inputs differ from candidate images")
    provenance_bytes = frozen_record(images / "candidate-image-provenance.json")
    provenance = json.loads(provenance_bytes)
    if provenance.get("status") != "passed" or not provenance.get("sourceInputsUnchanged") or {item["application"] for item in provenance.get("images", [])} != APPLICATIONS:
        raise ValueError("candidate image source provenance is incomplete")
    lock = json.loads(read_input(delivery / "services/images.lock.json"))
    if lock.get("apiVersion") != "magic.images.lock/v1":
        raise ValueError("candidate full image lock is invalid")
    locked = {}
    for item in lock["images"]:
        address = item["reference"] + ":" + item["tag"]
        if address in locked or inspect(address) != item["digest"]:
            raise ValueError("candidate local image identity differs from lock")
        locked[address] = item["digest"]
    for item in provenance["images"]:
        if locked.get(item["reference"] + ":" + item["tag"]) != item["digest"]:
            raise ValueError("candidate provenance and delivery image vector differ")
    entities = delivery / "services/platform/deployments/magicPanel/entity"
    if len(list(entities.glob("*.json"))) != 46:
        raise ValueError("candidate Panel entity inventory is incomplete")
    return {"status": "passed", "deliverySHA256": checksum(metadata),
            "imageSourceSHA256": checksum(source_bytes), "imageProvenanceSHA256": checksum(provenance_bytes),
            "planDigest": record["planDigest"], "sourceInputs": len(sources), "deliveryFiles": len(expected),
            "localImages": locked, "panelEntities": 46,
            "boundary": "source acceptance bound to released inputs; released process/Compose/Nginx lifecycle is not executed by this identity check",
            "live": "not-run"}
