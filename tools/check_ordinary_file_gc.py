#!/usr/bin/env python3
"""验证普通 File 清理经 Base/magicOrm/PostgreSQL 及多进程共享卷，不执行 Live。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlparse

from acceptance_evidence import EvidenceDirectory
from check_published_block_lifecycle import source_snapshot


STAGES = ("seed", "recover", "race-a", "race-b", "verify")


def validate_proof(proof, stages):
    if (proof.get("Status") != "passed" or proof.get("Database") != "postgresql"
            or proof.get("IndependentFileProcesses") != 5 or proof.get("SharedVolume") is not True
            or proof.get("Stages") != stages):
        raise ValueError("independent PostgreSQL/shared-volume proof missing")
    if [item.get("stage") for item in stages] != list(STAGES):
        raise ValueError("worker stages differ")
    if any(item.get("status") != "passed" or not str(item.get("pid", "")).isdigit() for item in stages):
        raise ValueError("worker proof missing")
    if len({item["pid"] for item in stages}) != 5:
        raise ValueError("workers were not independent OS processes")
    for key in ("committedResponseLost", "metadataAbsent", "bytesRetained", "explicitDeletionResponseLost"):
        if stages[0].get(key) is not True:
            raise ValueError("unknown metadata commit proof missing")
    for key in ("originalJournalRecovered", "physicalVersionRemoved", "explicitDeletionRecovered"):
        if stages[1].get(key) is not True:
            raise ValueError("new-process recovery proof missing")
    codes = [item.get("resultCode") for item in stages[2:4]]
    if any(type(code) is not int for code in codes) or codes.count(0) != 1:
        raise ValueError("shared-volume conditional cleanup proof missing")
    final = stages[4]
    if (final.get("removed") != ["lost", "explicit-lost", "explicit", "expired", "temporary"]
            or final.get("unchanged") != ["permanent-zero", "permanent-negative", "renewed", "managed", "foreign"]
            or final.get("pendingJournals") != 0 or final.get("database") != "postgresql"):
        raise ValueError("exact deletion/retention proof missing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "codespace")
    parser.add_argument("--panel-entities", type=Path, default=Path.home() / "dataspace/magicPlatform/services/platform/deployments/magicPanel/entity")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--race", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN", "")
    try:
        endpoint = urlparse(dsn)
        valid = endpoint.scheme in ("postgres", "postgresql") and endpoint.hostname == "127.0.0.1" and endpoint.username and endpoint.password and endpoint.port
    except ValueError:
        valid = False
    if not valid:
        parser.error("requires an explicitly authorized isolated loopback PostgreSQL DSN in the environment")
    workspace = args.workspace.resolve()
    if not args.panel_entities.is_dir() or any(not (workspace / name / "go.mod").is_file() for name in ("magicBase", "magicFile", "magicRunner")):
        parser.error("source repositories or Panel entity declarations missing")
    evidence = EvidenceDirectory(args.evidence)

    def snapshot():
        result = source_snapshot(workspace, args.panel_entities)
        result[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        return result

    sources = snapshot()
    evidence.write_json("source-sha256.json", sources)
    result = {"status": "failed", "database": "postgresql", "race": args.race, "live": "not-run"}
    try:
        with tempfile.TemporaryDirectory(prefix="magic-ordinary-file-gc-output-") as directory:
            # Do not inherit switches from other acceptance combinations.
            environment = {key: value for key, value in os.environ.items() if not key.startswith(("MAGIC_PUBLISHED_", "MAGIC_FILE_GC_", "MAGIC_CAS_POSTGRES_"))}
            environment.update(MAGIC_ORDINARY_FILE_GC="1", MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN=dsn,
                               MAGIC_PUBLISHED_BLOCK_BASE_REPOSITORY=str(workspace / "magicBase"),
                               MAGIC_PUBLISHED_BLOCK_PANEL_ENTITIES=str(args.panel_entities.resolve()),
                               MAGIC_PUBLISHED_BLOCK_OUTPUT=directory, MAGIC_PUBLISHED_BLOCK_RACE="1" if args.race else "0")
            command = ["go", "-C", str(workspace / "magicRunner"), "test", "./internal/modules/kernel/panel/biz", "-run", "^TestOrdinaryFileGCThroughBasePostgresAndSharedVolume$", "-count=1", "-timeout=240s", "-v"]
            if args.race:
                command.append("-race")
            with evidence.open_log("joint.log") as log:
                process = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            names = ["base-service.log", "file-gc-proof.json"]
            names.extend(f"file-gc-{stage}.{suffix}" for stage in STAGES for suffix in ("json", "log"))
            for name in names:
                path = Path(directory) / name
                if path.is_file():
                    evidence.copy(path)
            if process.returncode:
                raise ValueError(f"joint test failed with exit code {process.returncode}")
            log = (evidence.directory / "joint.log").read_text()
            if "--- PASS: TestOrdinaryFileGCThroughBasePostgresAndSharedVolume" not in log or "--- SKIP:" in log:
                raise ValueError("joint test did not execute")
            stages = [json.loads((Path(directory) / f"file-gc-{stage}.json").read_text()) for stage in STAGES]
            validate_proof(json.loads((Path(directory) / "file-gc-proof.json").read_text()), stages)
            for stage in STAGES:
                log = (Path(directory) / f"file-gc-{stage}.log").read_text()
                if "--- PASS: TestOrdinaryCleanupPostgresWorker" not in log or "--- SKIP:" in log:
                    raise ValueError("File worker did not execute")
            if sources != snapshot():
                raise ValueError("source/declarations changed during validation")
            result.update(status="passed", independentFileProcesses=5, sharedVolume=True,
                          scope="ordinary immutable upload versions; explicit/expired/temporary deletion; unknown commit recovery")
    except (OSError, ValueError, KeyError) as error:
        result["reason"] = str(error)
        raise
    finally:
        evidence.write_json("result.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
