#!/usr/bin/env python3
"""本机独立 PostgreSQL 验证 CAS bootstrap、Installer 同步/交付与 Panel 初始化，不部署或访问 Live。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

from acceptance_evidence import EvidenceDirectory
from acceptance_candidate import bind_candidate
from check_published_block_lifecycle import source_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "codespace")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--race", action="store_true")
    parser.add_argument("--authorization-recovery", action="store_true", help="persist a partial profile failure, renew authority and resume the original operation; requires --panel-inputs")
    parser.add_argument("--catalog-prerequisite-recovery", action="store_true", help="real old-cleanup overlap and exact original-plan prerequisite recovery; requires --catalog-predecessor")
    parser.add_argument("--catalog-predecessor", action="store_true", help="frozen catalogue predecessor update, stale-plan rejection and concurrent publication; requires --panel-inputs")
    parser.add_argument("--panel-inputs", type=Path, help="consume current formal Panel app.json/cas.json with freshly exported route catalogs")
    parser.add_argument("--candidate-delivery", type=Path, help="bind to a frozen static delivery; source fixtures do not execute released services")
    parser.add_argument("--candidate-image-evidence", type=Path, help="frozen source-built image provenance; requires --candidate-delivery")
    args = parser.parse_args()
    if bool(args.candidate_delivery) != bool(args.candidate_image_evidence):
        parser.error("both candidate delivery and image evidence are required")
    workspace = args.workspace.absolute()
    out = EvidenceDirectory(args.evidence)
    candidate_before = None
    if args.candidate_delivery:
        panel_inputs = args.candidate_delivery.absolute() / "services/platform/deployments/magicPanel"
        if args.panel_inputs and args.panel_inputs.absolute() != panel_inputs:
            parser.error("candidate Panel declarations cannot be overridden")
        args.panel_inputs = panel_inputs
        try:
            candidate_before = bind_candidate(workspace, args.candidate_delivery, args.candidate_image_evidence)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            out.write_json("result.json", {"status": "failed", "reason": "candidate input preflight refused", "live": "not-run"})
            raise RuntimeError("candidate input preflight refused before owner or database calls") from error
        out.write_json("candidate-before.json", candidate_before)
    build_env = dict(os.environ)
    if candidate_before:
        build_env.update(GOFLAGS="-mod=vendor", GOWORK="off")
    if args.authorization_recovery and not args.panel_inputs:
        parser.error("--authorization-recovery requires --panel-inputs")
    if args.catalog_predecessor and not args.panel_inputs:
        parser.error("--catalog-predecessor requires --panel-inputs")
    if args.catalog_prerequisite_recovery and not args.catalog_predecessor:
        parser.error("--catalog-prerequisite-recovery requires --catalog-predecessor")
    entities = args.panel_inputs / "entity" if candidate_before else Path.home() / "dataspace/magicPlatform/services/platform/deployments/magicPanel/entity"
    postgres_address = "postgres:17.7-alpine"
    if candidate_before:
        matches = [address for address in candidate_before["localImages"] if address.removeprefix("docker.io/").startswith("postgres:")]
        if len(matches) != 1:
            raise RuntimeError("candidate PostgreSQL image is missing or ambiguous")
        postgres_address = matches[0]
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", postgres_address]))[0]["Id"]
    if candidate_before and image != candidate_before["localImages"][postgres_address]:
        raise RuntimeError("candidate PostgreSQL image changed before isolated startup")
    delivery_image = json.loads(subprocess.check_output(["docker", "image", "inspect", "golang:1.26.7-bookworm"]))[0]["Id"]
    catalog_files = []
    if args.panel_inputs:
        args.panel_inputs = args.panel_inputs.resolve(strict=True)
        before_export = source_snapshot(workspace, entities)
        for name, repository, extra in (("panel", "magicRunner", ["--application", "magicPanel"]), ("gateway", "magicRunner", ["--application", "magicGateway"]), ("file", "magicFile", [])):
            output = out.directory / (name + "-catalog.json")
            with out.open_log(name + "-catalog-export.log") as log:
                subprocess.run(["go", "run", "./cmd/authorization-catalog", *extra, "--output", str(output)], cwd=workspace / repository, env=build_env, stdout=log, stderr=subprocess.STDOUT, check=True)
            catalog_files.append(output)
            if candidate_before:
                application = {"panel": "magicPanel", "gateway": "magicGateway", "file": "magicFile"}[name]
                declarations = args.panel_inputs.parent / application / "app.json"
                version = json.loads(declarations.read_text())["releaseRef"]["version"]
                frozen_catalog = args.candidate_delivery / "services/platform/releases" / application / version / "authorization-catalog.json"
                if json.loads(output.read_text()) != json.loads(frozen_catalog.read_text()):
                    raise RuntimeError("exported authorization catalog differs from candidate")
        if before_export != source_snapshot(workspace, entities):
            raise RuntimeError("source changed while exporting route catalogs")
        for name in ("app.json", "cas.json"):
            out.copy(args.panel_inputs / name, "formal-panel-" + name)
            out.copy(args.panel_inputs.parent / "magicFile" / name, "formal-file-" + name)

    def snapshot():
        value = source_snapshot(workspace, entities)
        value[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if candidate_before:
            helper = Path(__file__).with_name("acceptance_candidate.py")
            value[str(helper.resolve())] = hashlib.sha256(helper.read_bytes()).hexdigest()
        if args.panel_inputs:
            for path in [args.panel_inputs / "app.json", args.panel_inputs / "cas.json", args.panel_inputs.parent / "magicFile/app.json", args.panel_inputs.parent / "magicFile/cas.json", *catalog_files]:
                value[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return value

    initial = snapshot()
    out.write_json("source-sha256.json", initial)
    shared = set(subprocess.check_output(["docker", "ps", "-q", "--no-trunc"], text=True).split())
    container = None
    exit_code = None
    label = "runtime-foundation-2026-10-21"
    name = "magic-runtime-foundation-" + secrets.token_hex(6)
    with tempfile.TemporaryDirectory(prefix="magic-runtime-foundation-pg-") as private:
        if args.panel_inputs:
            inputs = Path(private) / "inputs"
            inputs.mkdir(mode=0o700)
            shutil.copyfile(args.panel_inputs / "app.json", inputs / "app.json")
            shutil.copyfile(args.panel_inputs / "cas.json", inputs / "panel-cas.json")
            for file_name in ("app.json", "cas.json"):
                shutil.copyfile(args.panel_inputs.parent / "magicFile" / file_name, inputs / ("file-" + file_name))
            for path in catalog_files:
                shutil.copyfile(path, inputs / path.name)
        binary = Path(private) / "foundation.test"
        build = ["go", "test", "-c", "./internal/modules/kernel/installer/biz/base", "-o", str(binary)]
        if args.race:
            build.append("-race")
        with out.open_log("probe-build.log") as log:
            compiled = subprocess.run(build, cwd=workspace / "magicRunner", env=build_env, stdout=log, stderr=subprocess.STDOUT)
        compiled.check_returncode()
        password = secrets.token_hex(32)
        envfile = Path(private) / "postgres.env"
        envfile.write_text("POSTGRES_USER=acceptance\nPOSTGRES_DB=acceptance\nPOSTGRES_PASSWORD=" + password + "\n")
        envfile.chmod(0o600)
        try:
            container = subprocess.check_output([
                "docker", "run", "--pull=never", "-d", "--name", name, "--label", "magic.acceptance.owner=" + label,
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
            env = {key: value for key, value in os.environ.items() if not key.startswith(("MAGIC_PUBLISHED_", "MAGIC_CAS_POSTGRES_"))}
            env.update(
                MAGIC_PUBLISHED_RUNTIME_BOOTSTRAP_POSTGRES="1",
                MAGIC_PUBLISHED_RUNTIME_FOUNDATION_POSTGRES="1",
                MAGIC_PUBLISHED_FOUNDATION_BINARY=str(binary), MAGIC_PUBLISHED_FOUNDATION_IMAGE=delivery_image,
                DEPLOYMENT_PLAN_DIGEST=hashlib.sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest(),
                MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN="postgres://acceptance:" + password + "@127.0.0.1:" + port + "/acceptance?sslmode=disable",
                MAGIC_PUBLISHED_BLOCK_PANEL_DATABASE="1", MAGIC_PUBLISHED_BLOCK_CAS_MAINLINE="1",
                MAGIC_PUBLISHED_BLOCK_BASE_REPOSITORY=str(workspace / "magicBase"),
                MAGIC_PUBLISHED_BLOCK_CAS_REPOSITORY=str(workspace / "magicCas"),
                MAGIC_PUBLISHED_BLOCK_PANEL_ENTITIES=str(entities),
                MAGIC_PUBLISHED_BLOCK_OUTPUT=str(out.directory),
                GOFLAGS="-mod=vendor" if candidate_before else "",
            )
            if candidate_before:
                env["GOWORK"] = "off"
            if args.panel_inputs:
                env["MAGIC_PUBLISHED_FOUNDATION_PANEL_INPUTS"] = str(inputs)
            if args.catalog_predecessor:
                env["MAGIC_PUBLISHED_CATALOG_PREDECESSOR"] = "1"
            if args.authorization_recovery:
                env["MAGIC_PUBLISHED_AUTHORIZATION_RECOVERY"] = "1"
            if args.catalog_prerequisite_recovery:
                env["MAGIC_PUBLISHED_CATALOG_PREREQUISITE_RECOVERY"] = "1"
            command = ["go", "test", "./internal/modules/kernel/panel/biz", "-run", "^TestPublishedRuntimeFoundationThroughPostgresBase$", "-count=1", "-timeout=600s", "-v"]
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
    if candidate_before:
        candidate_after = bind_candidate(workspace, args.candidate_delivery, args.candidate_image_evidence)
        out.write_json("candidate-after.json", candidate_after)
        stable = stable and candidate_before == candidate_after
    proof_file = out.directory / "runtime-foundation.json"
    proof = json.loads(proof_file.read_text()) if proof_file.exists() else None
    delivery_file = out.directory / "foundation-delivery.json"
    delivery = json.loads(delivery_file.read_text()) if delivery_file.exists() else None
    passed = exit_code == 0 and stable and proof is not None and proof["status"] == "passed" and all(proof[k] is True for k in ("publicCASBootstrap", "publicInstallerSynchronization", "generatedGatewayIdentity", "publicPanelInitialization")) and delivery is not None and delivery["status"] == "passed" and delivery["synchronizations"] == 2 and all(delivery[k] is True for k in ("immutableDeliveryReplay", "gatewayCredentialAuthenticated", "baseReceiptKeyScoped", "baseCASCredentialAbsent", "installerAuthorityEnded", "staleAuthorityRefused", "privateSecretTmpfs"))
    if args.panel_inputs:
        passed = passed and all(proof.get(key) is True for key in ("fullPanelManifestConsumed", "generatedControlInitialization", "actualBaseStartupMatched")) and delivery.get("fullPanelManifestConsumed") is True and delivery.get("platformAuthorizationPolicySynchronized") is True and delivery.get("identityCount") == 4 and delivery.get("securityBindingCount") == 6
    if args.panel_inputs:
        confirmation_file = out.directory / "catalog-confirmation.json"
        confirmation = json.loads(confirmation_file.read_text()) if confirmation_file.exists() else {}
        passed = passed and confirmation.get("status") == "passed" and confirmation.get("droppedSuccessfulResponses") == 1 and confirmation.get("catalogWrites") in ((9, 10) if args.catalog_prerequisite_recovery else (6,) if args.catalog_predecessor else (2,)) and confirmation.get("confirmationRequests") == (22 if args.catalog_prerequisite_recovery else 14 if args.catalog_predecessor else 5) and confirmation.get("sameDeclarationReplayDidNotWrite") is True
    if args.authorization_recovery:
        recovery_file = out.directory / "authorization-recovery.json"
        recovery = json.loads(recovery_file.read_text()) if recovery_file.exists() else {}
        passed = passed and recovery.get("status") == "passed" and all(recovery.get(k) is True for k in ("originalOperationResumed", "freshAuthorityUsed", "revokedAuthorityRefused", "wrongReferenceRefused", "completedReplayNoResume"))
    if args.catalog_predecessor:
        predecessor_file = out.directory / "catalog-predecessor.json"
        predecessor = json.loads(predecessor_file.read_text()) if predecessor_file.exists() else {}
        passed = passed and predecessor.get("status") == "passed" and predecessor.get("revisions") == [1, 2, 3, 4, 5] and predecessor.get("concurrentWinners") == 1 and predecessor.get("stalePlansRefused") == 2 and predecessor.get("sameDeclarationReplayNoWrite") is True
    if args.catalog_prerequisite_recovery:
        recovery_file = out.directory / "catalog-prerequisite-recovery.json"
        recovery = json.loads(recovery_file.read_text()) if recovery_file.exists() else {}
        overlap_file = out.directory / "catalog-prerequisite-overlap.json"
        overlap = json.loads(overlap_file.read_text()) if overlap_file.exists() else {}
        passed = passed and recovery.get("status") == "passed" and recovery.get("revisions") == [6,7,8,8,9] and all(recovery.get(k) is True for k in ("originalFrozenPlanRecovered", "recoveryDidNotAllocateGeneration", "readOnlyMissingVisibilityRefused", "finalOriginalDeclarationRestored")) and overlap.get("status") == "passed"
        passed = passed and confirmation.get("catalogWrites") == (9 if recovery.get("olderCleanupSuperseded") else 10)
    out.write_json("result.json", dict(
        status="passed" if passed else "failed", exitCode=exit_code, race=args.race, sourcesUnchanged=stable, authorizationRecovery=args.authorization_recovery, catalogPredecessor=args.catalog_predecessor, catalogPrerequisiteRecovery=args.catalog_prerequisite_recovery, candidateBinding=candidate_before,
        database="isolated-postgresql", databaseAccess="business-magicbase-service-magicorm;infrastructure-panel-database-block",
        postgresImageID=image, fixtureDeliveryImageID=delivery_image,
        scope="current full Panel manifest and current route-exported catalogs; public bootstrap/import/sync/security/delivery and generated control credential initialization" if args.panel_inputs else "public CAS bootstrap plan-bound authority; public Installer minimal foundation identity synchronization/immutable delivery/authority end; delivered Gateway authentication and Panel initialization through PostgreSQL",
        proofBoundary="source-bound acceptance plan; isolated Base address; no complete release/Compose, shared BFF/full service lifecycle/controlled rotation claim" if args.panel_inputs else "minimal Gateway-only foundation manifest and ephemeral source-bound acceptance plan; complete released Panel manifest, full service lifecycle, shared BFF and controlled key rotation remain open",
        liveReady=False, deployment="not-run", live="not-run",
    ))
    print("runtime bootstrap", "passed" if passed else "failed", "race=" + str(args.race), "liveReady=false", flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
