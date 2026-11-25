#!/usr/bin/env python3
"""Export a minimal, secret-free tar.gz bundle for cross-machine simulation & health checks."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile

MAGICTEST_ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS_ROOT = MAGICTEST_ROOT / "applications"
if str(APPLICATIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(APPLICATIONS_ROOT))

from platform_paths import resolve_platform_root

EXCLUDED_DIRS = frozenset({
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "reports",
    "secrets",
    "unpacked",
})

EXCLUDED_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.go.txt",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    ".DS_Store",
    ".env",
    ".env.*",
    "test_*.py",
    "*_test.py",
    "*_test.sh",
    "*.test.cjs",
    "*.test.ts",
    "*.test.tsx",
)


def _is_excluded(rel_parts: tuple[str, ...], name: str, is_dir: bool) -> bool:
    for part in rel_parts:
        if part in EXCLUDED_DIRS:
            return True
    if is_dir:
        return name in EXCLUDED_DIRS
    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _collect_filtered_tree(src_root: Path, base_in_repo: str, archive_repo_prefix: str) -> list[tuple[Path, str]]:
    start = src_root / base_in_repo
    if not start.exists():
        raise FileNotFoundError(f"required path does not exist: {start}")
    results: list[tuple[Path, str]] = []
    if start.is_file():
        if not _is_excluded(tuple(Path(base_in_repo).parts[:-1]), start.name, False):
            results.append((start, f"{archive_repo_prefix}/{base_in_repo}"))
        return results

    for current, dirs, files in os.walk(start, followlinks=False):
        cur_path = Path(current)
        rel_dir = cur_path.relative_to(src_root)
        dirs[:] = sorted(d for d in dirs if not _is_excluded(rel_dir.parts, d, True) and not (cur_path / d).is_symlink())
        for fname in sorted(files):
            fpath = cur_path / fname
            if fpath.is_symlink() or not fpath.is_file():
                continue
            if _is_excluded(rel_dir.parts, fname, False):
                continue
            rel_file = fpath.relative_to(src_root).as_posix()
            results.append((fpath, f"{archive_repo_prefix}/{rel_file}"))
    return results


def collect_bundle_entries(magic_test_root: Path, platform_root: Path) -> list[tuple[Path, str]]:
    magic_test_root = magic_test_root.resolve()
    platform_root = platform_root.resolve()

    entries: list[tuple[Path, str]] = []
    test_targets = (
        "README.md",
        "applications/README.md",
        "applications/platform_paths.py",
        "applications/live_e2e",
        "applications/device-management",
        "applications/chess-room-booking",
        "load",
    )
    for rel in test_targets:
        entries.extend(_collect_filtered_tree(magic_test_root, rel, "magicTest"))

    platform_targets = (
        "apps/models/README.md",
        "apps/models/device-management/README.md",
        "apps/models/device-management/definition",
        "apps/models/device-management/package/README.md",
        "apps/models/device-management/package/SHA256SUMS",
        "apps/models/device-management/package/package.zip",
        "apps/models/device-management/package/source-checks.json",
        "apps/models/chess-room-booking/README.md",
        "apps/models/chess-room-booking/definition",
        "apps/models/chess-room-booking/package/README.md",
        "apps/models/chess-room-booking/package/SHA256SUMS",
        "apps/models/chess-room-booking/package/package.zip",
        "apps/models/chess-room-booking/package/schema-preflight.json",
        "apps/models/chess-room-booking/package/source-checks.json",
        "scripts/deployment-domain.sh",
        "scripts/deployment-health.sh",
        "scripts/deployment-mode.sh",
        "scripts/deployment-oem.sh",
        "scripts/deployment-preflight.sh",
        "scripts/deployment-python.sh",
        "scripts/deployment-tls.sh",
        "scripts/deployment_toml.py",
    )
    for rel in platform_targets:
        target = platform_root / rel
        if not target.exists():
            if rel.endswith(".json"):
                continue
            raise FileNotFoundError(f"required magicPlatform asset not found: {target}")
        entries.extend(_collect_filtered_tree(platform_root, rel, "magicPlatform"))

    seen: set[str] = set()
    unique: list[tuple[Path, str]] = []
    for src, arc_rel in sorted(entries, key=lambda item: item[1]):
        if arc_rel in seen:
            continue
        seen.add(arc_rel)
        unique.append((src, arc_rel))
    return unique


def _add_bytes(tf: tarfile.TarFile, arc_name: str, payload: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name=arc_name)
    info.size = len(payload)
    info.mode = mode
    info.mtime = 0
    tf.addfile(info, io.BytesIO(payload))


def export_bundle(
    output_path: Path,
    magic_test_root: Path,
    platform_root: Path,
    *,
    force: bool = False,
) -> dict[str, object]:
    output_path = output_path.expanduser().resolve()
    if output_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing bundle archive: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    entries = collect_bundle_entries(magic_test_root, platform_root)
    manifest_files: list[dict[str, object]] = []
    root_prefix = "magic-sim-bundle"

    tmp_output = output_path.with_name(f".{output_path.name}.tmp-{os.getpid()}")
    try:
        with tarfile.open(tmp_output, "w:gz") as tf:
            for src, arc_rel in entries:
                data = src.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                mode = 0o755 if os.access(src, os.X_OK) or src.suffix == ".sh" else 0o644
                full_arc = f"{root_prefix}/{arc_rel}"
                _add_bytes(tf, full_arc, data, mode=mode)
                manifest_files.append({
                    "path": arc_rel,
                    "size": len(data),
                    "sha256": sha,
                })

            readme_text = (
                "magic-sim-bundle (cross-machine read-only models + simulation tools)\n"
                "====================================================================\n\n"
                "1. Extract:\n"
                "   tar -xzf <bundle>.tar.gz\n"
                "   cd magic-sim-bundle\n"
                "   export MAGICPLATFORM_ROOT=\"$PWD/magicPlatform\"\n\n"
                "2. Remote deployment health & APM check (pass --target-address <IP> if DNS is not configured):\n"
                "   sh magicPlatform/scripts/deployment-health.sh --skip-docker --base-url https://panel.example.com --include-apm --json\n\n"
                "3. Dry-run & run simulated apps bootstrap:\n"
                "   python3 -B magicTest/applications/live_e2e/bootstrap_simulated_apps.py \\\n"
                "     all --base-url https://panel.example.com --state-dir ~/.local/state/magic-sim --dry-run\n\n"
                "   python3 -B magicTest/applications/live_e2e/run_dual_apps_e2e.py \\\n"
                "     --platform-root \"$PWD/magicPlatform\" --dry-run --output-dir /tmp/magic-e2e-dry-run\n\n"
                "4. Cross-server HTTPS load + Prometheus APM (reusing --state-dir):\n"
                "   python3 -B magicTest/load/run_load.py \\\n"
                "     --from-sim-state ~/.local/state/magic-sim \\\n"
                "     --sim-app device-management --sim-scenario gateway-read \\\n"
                "     --mode step --concurrency 2,8 --duration 30 \\\n"
                "     --apm-url https://apm.example.com/prometheus/ --apm-idle-seconds 30 --require-apm\n"
            ).encode("utf-8")
            _add_bytes(tf, f"{root_prefix}/README-REMOTE.txt", readme_text, mode=0o644)

            manifest = {
                "apiVersion": "magic.sim-bundle/v1",
                "createdUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fileCount": len(manifest_files),
                "files": manifest_files,
            }
            manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            _add_bytes(tf, f"{root_prefix}/bundle-manifest.json", manifest_bytes, mode=0o644)

        os.replace(tmp_output, output_path)
    finally:
        if tmp_output.exists():
            tmp_output.unlink()

    archive_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "archive": str(output_path),
        "archiveSha256": archive_sha256,
        "fileCount": len(manifest_files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output .tar.gz path")
    parser.add_argument("--magic-test-root", type=Path, default=MAGICTEST_ROOT, help="Path to magicTest root")
    parser.add_argument("--platform-root", type=Path, default=None, help="Path to magicPlatform root")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output archive")
    args = parser.parse_args(argv)

    platform_root = resolve_platform_root(args.platform_root)
    summary = export_bundle(args.output, args.magic_test_root, platform_root, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
