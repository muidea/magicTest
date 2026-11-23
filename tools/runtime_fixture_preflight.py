#!/usr/bin/env python3
"""Read-only isolation preflight for controlled runtime fault verification."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from platform_closeout import require, validate_fixtures


def verify_runtime_owners(manifest, inventory, containers):
    fixtures = validate_fixtures(manifest)
    require(bool(fixtures), 'at least one isolated application is required')
    require(inventory.get('environmentFingerprint') == manifest['environmentFingerprint'], 'inventory version changed')
    require(inventory.get('complete') is True, 'assignment inventory must be complete')
    captured = inventory.get('capturedAt', 0)
    require(type(captured) is int and 0 <= time.time() - captured <= 60, 'assignment inventory must be refreshed within 60 seconds')
    assignments = inventory.get('assignments')
    require(isinstance(assignments, list) and len(assignments) <= 10000, 'invalid assignment inventory')
    for assignment in assignments:
        require(isinstance(assignment, dict) and assignment.get('desiredState') in {'prepared', 'running', 'stopped', 'revoked'}, 'invalid assignment state')
        require(all(isinstance(assignment.get(key), str) and bool(assignment[key]) for key in
                    ('namespace', 'deploymentId', 'applicationUuid', 'executionInstanceId', 'incarnation', 'gatewayInstanceId', 'gatewayIncarnation')),
                'assignment owner identity is incomplete')
        require(type(assignment.get('installationId')) is int and assignment['installationId'] > 0, 'assignment installation identity is incomplete')
    owned = {(f['namespace'], f['deploymentId'], f['installationId'], f['applicationUuid']) for f in fixtures}
    runtimes = manifest.get('runtimes')
    require(isinstance(runtimes, list) and bool(runtimes), 'explicit runtime owners are required')
    seen, seen_containers, result = set(), set(), []
    for runtime in runtimes:
        identity = runtime.get('instanceId')
        require(isinstance(identity, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}', identity), 'invalid runtime identity')
        require(identity not in seen and identity not in {'platform-base', 'platform-gateway'}, 'shared or duplicate runtime owner')
        seen.add(identity)
        require(runtime.get('purpose') == 'acceptance', 'runtime must be dedicated to acceptance')
        startup = runtime.get('startup', {})
        kind = startup.get('kind')
        require(kind in {'base', 'gateway'} and startup.get('apiVersion') == 'magic.runtime-instance/v1', 'invalid startup contract')
        require(startup.get('instanceId') == identity and startup.get('incarnation') == runtime.get('incarnation') and bool(runtime.get('incarnation')), 'runtime incarnation changed')
        require(startup.get('bootstrapApplications') == [], 'bootstrap runtime must never be faulted')
        namespaces = {f['namespace'] for f in fixtures}
        require(startup.get('namespaceScope') in namespaces, 'runtime must have an isolated concrete tenant scope')
        container_id = runtime.get('containerId', '')
        require(re.fullmatch(r'[a-f0-9]{64}', container_id) is not None, 'use immutable full container ID')
        require(container_id not in seen_containers, 'runtime scenarios must not share a container')
        seen_containers.add(container_id)
        container = containers.get(container_id, {})
        require(container.get('Id') == container_id and container.get('State', {}).get('Running') is True, 'container is missing or not running')
        require(container.get('Name', '').startswith('/native-'), 'platform container cannot be used for faults')
        require(container.get('_acceptanceStartup') == startup, 'mounted runtime startup does not match the frozen owner')
        labels = container.get('Config', {}).get('Labels') or {}
        for key, field in [('io.platform.deployment-id', 'providerDeploymentId'), ('io.platform.runtime.application-uuid', 'providerApplicationUuid')]:
            require(re.fullmatch(r'[a-f0-9]{32}', runtime.get(field, '')) is not None and labels.get(key) == runtime[field], 'provider/container ownership mismatch')
        active = []
        for assignment in assignments:
            if assignment.get('desiredState') == 'revoked':
                continue
            uses = assignment.get('executionInstanceId') == identity if kind == 'base' else assignment.get('gatewayInstanceId') == identity
            if not uses:
                continue
            require((assignment.get('namespace'), assignment.get('deploymentId'), assignment.get('installationId'), assignment.get('applicationUuid')) in owned,
                    'runtime carries an application outside this fixture; faults are forbidden')
            incarnation = assignment.get('incarnation') if kind == 'base' else assignment.get('gatewayIncarnation')
            require(incarnation == runtime['incarnation'], 'assignment incarnation does not match runtime')
            active.append(assignment['deploymentId'])
        result.append({'instanceId': identity, 'incarnation': runtime['incarnation'], 'kind': kind,
                       'containerId': container_id, 'imageId': container.get('Image'), 'deployments': sorted(set(active))})
    return {'schema': 'magic.acceptance.runtime-preflight/v1', 'environmentFingerprint': manifest['environmentFingerprint'],
            'capturedAt': int(time.time()), 'isolationVerified': True, 'livePassed': False, 'runtimes': result}



def verify_uninstall_checkpoint(manifest, checkpoint):
    """Check captured owner facts; this does not execute or pass Live recovery."""
    fixtures = validate_fixtures(manifest)
    require(checkpoint.get('schema') == 'magic.acceptance.uninstall-checkpoint/v1', 'invalid uninstall checkpoint')
    require(checkpoint.get('environmentFingerprint') == manifest['environmentFingerprint'], 'checkpoint candidate changed')
    installation = checkpoint.get('installation', {})
    matches = [f for f in fixtures if f['installationId'] == installation.get('id') and f['namespace'] == installation.get('namespace')]
    require(len(matches) == 1, 'checkpoint is not owned by this fixture')
    fixture = matches[0]
    for key in ('namespace', 'deploymentId', 'applicationUuid', 'sourceDigest'):
        require(installation.get(key) == fixture[key], 'installation binding changed: ' + key)
    require(installation.get('runtimeType') == 'model-driven', 'checkpoint must be a model installation')
    require(installation.get('status') in {'uninstallFailed', 'uninstalling'}, 'normal or completed uninstall is not interruption evidence')
    require(bool(installation.get('operationId')), 'original lifecycle operation is missing')
    receipt = installation.get('receipt', {})
    require(isinstance(receipt, dict) and bool(receipt.get('runtimeApplicationUuid')), 'materialized runtime receipt is required')
    uninstall = receipt.get('uninstallation', {})
    require(uninstall.get('startedAt', 0) > 0 and uninstall.get('finishedAt', 0) == 0, 'uninstall is not pending')
    require(uninstall.get('dataDisposition') in {'retain', 'destroy'}, 'frozen data disposition is missing')
    assignment, observed = checkpoint.get('assignment', {}), checkpoint.get('runtimeReceipt', {})
    require(assignment.get('desiredState') == 'revoked' and observed.get('state') == 'stopped', 'actual drain is unconfirmed')
    for key in ('namespace', 'deploymentId', 'applicationUuid'):
        require(assignment.get(key) == installation.get(key), 'assignment installation binding changed: ' + key)
    require(assignment.get('installationId') == installation['id'], 'assignment installation ID changed')
    require(assignment.get('runtimeApplicationUuid') == receipt['runtimeApplicationUuid'], 'runtime metadata binding changed')
    for key in ('namespace', 'deploymentId', 'installationId', 'applicationUuid', 'runtimeApplicationUuid', 'revisionDigest',
                'planDigest', 'generation', 'executionEpoch', 'executionGrantId', 'gatewayInstanceId', 'gatewayIncarnation'):
        require(assignment.get(key) not in (None, '', 0) and observed.get(key) == assignment[key], 'stopped receipt binding changed: ' + key)
    require(observed.get('baseInstanceId') == assignment.get('executionInstanceId') and observed.get('baseIncarnation') == assignment.get('incarnation'), 'Base owner changed')
    require(observed.get('targetAddress') == '' and observed.get('observedAt', 0) > 0, 'stopped receipt still exposes execution target')
    require(assignment.get('gatewayAppliedGeneration') == assignment['generation'] and assignment.get('gatewayAppliedSnapshotVersion', 0) > 0
            and 0 < assignment.get('gatewayAppliedAt', 0) <= int(time.time() * 1000) and assignment.get('gatewayAppliedTargetAddress') == '',
            'Gateway withdrawal is unconfirmed')
    return {'schema': 'magic.acceptance.uninstall-preflight/v1', 'environmentFingerprint': manifest['environmentFingerprint'],
            'installationId': installation['id'], 'operationId': installation['operationId'], 'generation': assignment['generation'],
            'checkpointVerified': True, 'livePassed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('inventory', type=Path, nargs='?', help='fresh complete owner API assignment inventory; never a hand-written subset')
    parser.add_argument('--uninstall-checkpoint', type=Path, help='captured installation, assignment and stopped receipt; no Docker mutation')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if args.uninstall_checkpoint:
        print(json.dumps(verify_uninstall_checkpoint(manifest, json.loads(args.uninstall_checkpoint.read_text())), ensure_ascii=False, indent=2))
        return
    require(args.inventory is not None, 'fresh assignment inventory is required')
    inventory = json.loads(args.inventory.read_text())
    containers = {}
    for runtime in manifest.get('runtimes', []):
        container_id = runtime.get('containerId', '')
        require(re.fullmatch(r'[a-f0-9]{64}', container_id) is not None, 'invalid container ID')
        # Do not print raw inspect: environment variables may contain secrets.
        completed = subprocess.run(['docker', 'inspect', container_id], check=True, capture_output=True, timeout=10)
        records = json.loads(completed.stdout)
        require(len(records) == 1, 'ambiguous container owner')
        startup = subprocess.run(['docker', 'exec', container_id, 'head', '-c', '131073',
                                  '/var/app/secret/runtime-instance/runtime-instance.json'],
                                 check=True, capture_output=True, timeout=10)
        require(len(startup.stdout) <= 131072, 'startup contract exceeds size limit')
        records[0]['_acceptanceStartup'] = json.loads(startup.stdout)
        containers[container_id] = records[0]
    print(json.dumps(verify_runtime_owners(manifest, inventory, containers), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print('Runtime isolation could not be verified; no fault operation was performed.', file=sys.stderr)
        sys.exit(1)
