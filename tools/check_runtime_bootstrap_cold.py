#!/usr/bin/env python3
"""本机独立 PostgreSQL 验证 Panel 公共初始化的独立进程恢复，不部署或访问 Live。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from acceptance_evidence import EvidenceDirectory
from check_published_block_lifecycle import source_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "codespace")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--race", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.absolute()
    entities = Path.home() / "dataspace/magicPlatform/services/platform/deployments/magicPanel/entity"
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", "postgres:17.7-alpine"]))[0]["Id"]
    out = EvidenceDirectory(args.evidence)

    def snapshot():
        value = source_snapshot(workspace, entities)
        value[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        return value

    initial = snapshot()
    out.write_json("source-sha256.json", initial)
    shared = set(subprocess.check_output(["docker", "ps", "-q", "--no-trunc"], text=True).split())
    container = None
    exit_code = None
    label = "runtime-bootstrap-cold-2026-10-21"
    name = "magic-runtime-bootstrap-cold-" + secrets.token_hex(6)
    with tempfile.TemporaryDirectory(prefix="magic-runtime-bootstrap-cold-pg-") as private:
        password = secrets.token_hex(32)
        envfile = Path(private) / "postgres.env"
        envfile.write_text("POSTGRES_USER=acceptance\nPOSTGRES_DB=acceptance\nPOSTGRES_PASSWORD=" + password + "\n")
        envfile.chmod(0o600)
        try:
            container = subprocess.check_output([
                "docker", "run", "-d", "--name", name, "--label", "magic.acceptance.owner=" + label,
                "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=1024m",
                "-p", "127.0.0.1::5432", "--env-file", str(envfile), image,
            ], text=True).strip()
            info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
            port = info["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
            for attempt in range(60):
                if subprocess.run(["docker", "exec", container, "pg_isready", "-U", "acceptance"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("isolated PostgreSQL did not start")
            env = {key: value for key, value in os.environ.items() if not key.startswith(("MAGIC_PUBLISHED_", "MAGIC_CAS_POSTGRES_", "MAGIC_RUNTIME_BOOTSTRAP_CHILD_"))}
            env.update(
                MAGIC_PUBLISHED_RUNTIME_BOOTSTRAP_POSTGRES="1",
                MAGIC_PUBLISHED_RUNTIME_BOOTSTRAP_COLD="1",
                MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN="postgres://acceptance:" + password + "@127.0.0.1:" + port + "/acceptance?sslmode=disable",
                MAGIC_PUBLISHED_BLOCK_PANEL_DATABASE="1", MAGIC_PUBLISHED_BLOCK_CAS_MAINLINE="1",
                MAGIC_PUBLISHED_BLOCK_BASE_REPOSITORY=str(workspace / "magicBase"),
                MAGIC_PUBLISHED_BLOCK_CAS_REPOSITORY=str(workspace / "magicCas"),
                MAGIC_PUBLISHED_BLOCK_PANEL_ENTITIES=str(entities),
                MAGIC_PUBLISHED_BLOCK_OUTPUT=str(out.directory),
                GOFLAGS="",
            )
            command = ["go", "test", "./internal/modules/kernel/panel/biz", "-run", "^TestPublishedRuntimeBootstrapColdRecovery$", "-count=1", "-timeout=300s", "-v"]
            if args.race:
                env["MAGIC_PUBLISHED_BLOCK_RACE"] = "1"
                command.append("-race")
            with out.open_log("joint.log") as log:
                result = subprocess.run(command, cwd=workspace / "magicRunner", env=env, stdout=log, stderr=subprocess.STDOUT)
            exit_code = result.returncode
            # Never export even an unexpected diagnostic containing the private input.
            for path in out.directory.iterdir():
                if path.is_file():
                    data = path.read_bytes()
                    if password.encode() in data:
                        path.write_bytes(data.replace(password.encode(), b"[redacted]"))
        finally:
            if container is not None:
                info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
                assert info["Id"] == container and info["Name"] == "/" + name and info["Config"]["Labels"]["magic.acceptance.owner"] == label
                subprocess.run(["docker", "rm", "--force", "--volumes", container], check=True, stdout=subprocess.DEVNULL)
            unchanged = shared == set(subprocess.check_output(["docker", "ps", "-q", "--no-trunc"], text=True).split())
            out.write_json("cleanup.json", dict(ownedPostgresRemoved=container is not None, sharedRunningContainersUnchanged=unchanged, sharedContainerCount=len(shared)))
            assert unchanged
    stable = initial == snapshot()
    proof_file = out.directory / "runtime-bootstrap-cold.json"
    proof = json.loads(proof_file.read_text()) if proof_file.exists() else None
    processes = proof.get("processes", []) if proof else []
    valid_processes = len(processes) == 4 and len({p["pid"] for p in processes}) == 4 and len({p["receiptDigest"] for p in processes}) == 1 and [p["phase"] for p in processes] == ["commit-loss", "recover", "recover-again", "conflict"] and [p["result"] for p in processes] == ["committed-response-lost", "recovered", "recovered", "conflict-refused"] and [p["commits"] for p in processes] == [1, 0, 0, 0] and [p["casPreflights"] for p in processes] == [1, 0, 0, 0]
    passed = exit_code == 0 and stable and proof is not None and proof["status"] == "passed" and valid_processes
    out.write_json("result.json", dict(
        status="passed" if passed else "failed", exitCode=exit_code, race=args.race, sourcesUnchanged=stable,
        database="isolated-postgresql", databaseAccess="business-magicbase-service-magicorm;infrastructure-panel-database-block",
        scope="public Panel InitializeRuntimeBootstrap across four sequential fresh test processes; writer exits after actual committed response loss; two cold read-only recoveries; conflicting manifest refused",
        proofBoundary="public Panel Biz in independent test executables; Base/CAS stay running; full Panel process service restart, Installer foundation issuance and shared BFF topology remain open",
        liveReady=False, deployment="not-run", live="not-run",
    ))
    print("runtime bootstrap", "passed" if passed else "failed", "race=" + str(args.race), "liveReady=false", flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
