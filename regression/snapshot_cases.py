#!/usr/bin/env python3
"""Exercise the real snapshot owner against disposable files and a real workload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(platform, private):
    platform, private = Path(platform).resolve(), Path(private).resolve()
    if not (platform / 'scripts/platform-snapshot.py').is_file():
        raise ValueError('Snapshot source owner is unavailable')
    if private.exists() or platform == private or platform in private.parents:
        raise ValueError('Use a new independent private directory')
    private.mkdir(mode=0o700, parents=True)
    root = private / 'deployment'
    root.mkdir()
    for name in ['services/data', 'services/secret', 'apps/data', 'scripts']:
        (root / name).mkdir(parents=True, exist_ok=True)
    for name in ['backup.sh', 'restore.sh', 'scripts/platform-snapshot.py', 'scripts/lifecycle-lock.sh']:
        shutil.copy2(platform / name, root / name)
    # These are finite boundary-fixture bytes, not fake business or owner receipts.
    (root / 'services/.env').write_text('MAGICTEST_SNAPSHOT_BOUNDARY=1\n')
    (root / 'services/data/original').write_bytes(b'original snapshot boundary \x00\xff')
    (root / 'services/secret/original').write_bytes(os.urandom(32))
    (root / 'services/secret/original').chmod(0o600)
    tracked = ['services/.env', 'services/data/original', 'services/secret/original']
    original = {p: sha(root / p) for p in tracked}
    events = []
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}

    def command(args, expected, diagnostic=None):
        result = subprocess.run(args, env=env, capture_output=True, timeout=60)
        output = result.stdout + result.stderr
        if result.returncode != expected or diagnostic and diagnostic.encode() not in output:
            raise RuntimeError('Snapshot boundary did not reach the declared owner refusal')
        events.append({'command': [str(x).replace(str(private), '<private>') for x in args],
                       'exitCode': result.returncode, 'diagnostic': diagnostic,
                       'outputSha256': hashlib.sha256(output).hexdigest()})
        return result

    def unchanged():
        if {p: sha(root / p) for p in tracked} != original:
            raise RuntimeError('Original boundary-fixture state changed after refused restore')

    archive = private / 'snapshot.tgz'
    command(['sh', str(root / 'backup.sh'), '--output', str(archive)], 0)
    command(['python3', '-B', str(root / 'scripts/platform-snapshot.py'), 'verify', '--archive', str(archive)], 0)
    damaged = private / 'damaged.tgz'
    damaged.write_bytes(archive.read_bytes() + b'corrupt')
    shutil.copy2(str(archive) + '.json', str(damaged) + '.json')
    command(['sh', str(root / 'restore.sh'), '--archive', str(damaged), '--replace'], 1, 'checksum is invalid')
    unchanged()
    other = private / 'other-root'
    (other / 'scripts').mkdir(parents=True)
    (other / 'services').mkdir()
    for name in ['restore.sh', 'scripts/platform-snapshot.py', 'scripts/lifecycle-lock.sh']:
        shutil.copy2(platform / name, other / name)
    command(['sh', str(other / 'restore.sh'), '--archive', str(archive), '--replace'], 1, 'different deployment root')
    unchanged()
    name = 'magictest-snapshot-' + uuid.uuid4().hex[:12]
    journal = {'kind': 'snapshot-active-workload', 'name': name, 'root': str(root), 'phase': 'create-intent'}
    state = private / 'workload-journal.json'
    state.write_text(json.dumps(journal))
    created = subprocess.run(['docker', 'create', '--pull=never', '--name', name,
                              '--label', 'io.muidea.magictest.snapshot=' + name,
                              '--network', 'none', '--mount', 'type=bind,src=' + str(root / 'apps/data') + ',dst=/fixture',
                              'alpine:3.22.0', 'sleep', '300'], capture_output=True, timeout=30)
    if created.returncode:
        raise RuntimeError('Real isolated workload unavailable; no restore dispatched')
    journal.update(containerId=created.stdout.decode().strip(), phase='created')
    state.write_text(json.dumps(journal))
    try:
        subprocess.run(['docker', 'start', journal['containerId']], check=True, capture_output=True, timeout=30)
        inspect = json.loads(subprocess.check_output(['docker', 'inspect', journal['containerId']]))[0]
        if not inspect['State']['Running'] or inspect['Config']['Labels'].get('io.muidea.magictest.snapshot') != name:
            raise RuntimeError('Original workload identity is not running')
        command(['sh', str(root / 'restore.sh'), '--archive', str(archive), '--replace'], 1, 'active containers')
        unchanged()
        return {'status': 'passed', 'cases': ['damaged-checksum', 'wrong-root', 'active-mounted-workload'],
                'ownerScriptSha256': sha(platform / 'scripts/platform-snapshot.py'),
                'snapshotSha256': sha(archive), 'originalStateUnchanged': True, 'events': events,
                'scope': 'Real snapshot/restore entrypoints, real filesystem and Docker workload; no application-data recovery claim.'}
    finally:
        inspect = json.loads(subprocess.check_output(['docker', 'inspect', journal['containerId']]))[0]
        mounts = inspect.get('Mounts', [])
        if (inspect['Id'] != journal['containerId'] or
                inspect['Config']['Labels'].get('io.muidea.magictest.snapshot') != name or
                len(mounts) != 1 or mounts[0].get('Type') != 'bind' or
                mounts[0].get('Source') != str(root / 'apps/data') or
                mounts[0].get('Destination') != '/fixture'):
            raise RuntimeError('Workload cleanup ownership changed')
        subprocess.run(['docker', 'rm', '-f', journal['containerId']], check=True, capture_output=True, timeout=30)
        absent = subprocess.run(['docker', 'inspect', journal['containerId']], capture_output=True, timeout=30)
        if absent.returncode != 1 or b'No such' not in absent.stderr:
            raise RuntimeError('Original workload absence not independently confirmed')
        journal['phase'] = 'disposed'
        state.write_text(json.dumps(journal))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--private', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.platform, args.private), ensure_ascii=False))
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'blocked', 'reason': type(error).__name__,
                          'beforeWorkloadDispatch': not (Path(args.private) / 'workload-journal.json').exists()}, ensure_ascii=False))
        raise SystemExit(2)
