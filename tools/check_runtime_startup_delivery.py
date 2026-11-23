#!/usr/bin/env python3
"""验证 Installer 公共入口的普通 Base 密钥交付；独立 tmpfs，不连接数据库或 Live。"""

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile

from acceptance_evidence import EvidenceDirectory
from check_published_block_lifecycle import source_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "codespace")
    parser.add_argument("--image", default="golang:1.26.7-bookworm")
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.absolute()
    runner = workspace / "magicRunner"
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]
    image_id = image["Id"]  # A local immutable image ID; never pull or resolve a tag again.
    out = EvidenceDirectory(args.evidence)
    checks = []

    def snapshot():
        value = source_snapshot(workspace, Path.home() / "dataspace/magicPlatform/services/platform/deployments/magicPanel/entity")
        value[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        return value

    initial = snapshot()
    out.write_json("source-sha256.json", initial)

    def run(name, command, cwd=runner):
        with out.open_log(name + ".log") as log:
            result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        checks.append(dict(name=name, command=command, exitCode=result.returncode))
        print(name, result.returncode, flush=True)
        result.check_returncode()

    shared = set(subprocess.check_output(["docker", "ps", "-q", "--no-trunc"], text=True).split())
    name = "magic-runtime-delivery-" + secrets.token_hex(6)
    container = None
    removed = False
    isolation_verified = False
    failure = None
    try:
        run("installer-race", ["go", "test", "./internal/modules/kernel/installer/biz/base", "-race", "-count=1"])
        run("installer-vet", ["go", "vet", "./internal/modules/kernel/installer/biz/base"])
        run("installer-build", ["go", "build", "-o", "/dev/null", "./application/magicInstaller/cmd"])
        with tempfile.TemporaryDirectory(prefix="magic-runtime-delivery-binary-") as private:
            binary = Path(private) / "installer.test"
            run("probe-build", ["go", "test", "-c", "-race", "./internal/modules/kernel/installer/biz/base", "-o", str(binary)])
            container = subprocess.check_output([
                "docker", "create", "--name", name,
                "--label", "magic.acceptance.owner=runtime-delivery-2026-10-21",
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--tmpfs", "/var/app/secret:rw,noexec,nosuid,mode=0700",
                "--tmpfs", "/tmp:rw,noexec,nosuid,mode=0700",
                "--mount", "type=bind,source=" + str(binary) + ",target=/acceptance/probe,readonly",
                "--env", "MAGIC_RUNTIME_DELIVERY_ACCEPTANCE=isolated-container",
                image_id, "/acceptance/probe",
                "-test.run=^TestPublicRuntimeDeliveryInIsolatedContainer$", "-test.v", "-test.count=1",
            ], text=True).strip()
            info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
            assert info["Id"] == container and info["Config"]["Labels"]["magic.acceptance.owner"] == "runtime-delivery-2026-10-21"
            assert info["HostConfig"]["NetworkMode"] == "none" and info["HostConfig"]["ReadonlyRootfs"]
            assert info["HostConfig"]["Tmpfs"]["/var/app/secret"] == "rw,noexec,nosuid,mode=0700"
            binds = [mount for mount in info["Mounts"] if mount["Type"] == "bind"]
            assert len(binds) == 1 and binds[0]["Source"] == str(binary) and not binds[0]["RW"]
            assert all(mount["Type"] == "bind" or mount["Type"] == "tmpfs" and mount["Destination"] in {"/tmp", "/var/app/secret"} for mount in info["Mounts"])
            isolation_verified = True
            run("public-delivery", ["docker", "start", "--attach", container])
            info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
            assert info["State"]["ExitCode"] == 0 and info["State"]["Status"] == "exited"
            proof = (out.directory / "public-delivery.log").read_text()
            assert "--- PASS: TestPublicRuntimeDeliveryInIsolatedContainer" in proof and "--- SKIP:" not in proof and "DATA RACE" not in proof
    except Exception as error:
        failure = error
    finally:
        if container is not None:
            info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
            assert info["Id"] == container and info["Name"] == "/" + name and info["Config"]["Labels"]["magic.acceptance.owner"] == "runtime-delivery-2026-10-21"
            subprocess.run(["docker", "rm", "--force", "--volumes", container], check=True, stdout=subprocess.DEVNULL)
            removed = True
        unchanged = shared == set(subprocess.check_output(["docker", "ps", "-q", "--no-trunc"], text=True).split())
        out.write_json("cleanup.json", dict(ownedContainerRemoved=removed, sharedRunningContainersUnchanged=unchanged, sharedContainerCount=len(shared), binaryTemporaryDirectoryRemoved=True))
        assert unchanged
    stable = initial == snapshot()
    passed = failure is None and stable
    out.write_json("result.json", dict(
        status="passed" if passed else "failed", checks=checks, sourcesUnchanged=stable,
        image=image_id, isolatedSecretTmpfs=isolation_verified, network="none" if isolation_verified else "not-run", defaultVendor=True,
        scope="public Installer ResolveRuntimeBootstrap/ResolveRuntimeStartup; real private SecretStore; ordinary system Base startup/derived receipt key/control database binding; immutable retry; stale action key and same-incarnation receipt change refused; fresh paired incarnation preserves predecessor",
        proofBoundary="no CAS foundation synchronization or Panel initialization; no database connection, runtime restart or online key rotation; formal shared BFF topology remains open",
        database="not-connected", deployment="not-run", live="not-run", liveReady=False,
    ))
    if failure is not None:
        raise failure
    assert stable


if __name__ == "__main__":
    main()
