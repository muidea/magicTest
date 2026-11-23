#!/usr/bin/env python3
"""Durable, identity-bound lifecycle for acceptance infrastructure (not business data)."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

from platform_acceptance import CORE, configuration_digest, require

SCHEMA = 'magic.acceptance.resources/v1'
RUN_LABEL = 'io.acceptance.run'
OWNER_LABEL = 'io.acceptance.owner'
MARKER = '.acceptance-owner.json'
KINDS = ('container', 'network', 'volume')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            os.chmod(temporary, 0o600)
            stream.write(value if isinstance(value, bytes) else
                         (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def load(path):
    return json.loads(Path(path).read_text())


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'deadline must include timezone')
    return parsed


class Docker:
    def __init__(self, host='unix:///var/run/docker.sock'):
        self.host = host
        # Explicit endpoint; never inherit an inner daemon or a named context.
        self.env = dict(os.environ, DOCKER_HOST=host)
        self.env.pop('DOCKER_CONTEXT', None)

    def call(self, *args, timeout=90):
        result = subprocess.run(['docker', *args], env=self.env, capture_output=True,
                                text=True, timeout=timeout)
        # stderr may contain deployment values; keep raw output out of public reports.
        require(result.returncode == 0, 'docker command failed: ' + ' '.join(args[:2]))
        return result.stdout.strip()

    def engine(self):
        value = self.call('info', '--format', '{{.ID}}')
        require(bool(value), 'Docker engine identity unavailable')
        return value

    def items(self, kind):
        args = ('container', 'ls', '-aq', '--no-trunc') if kind == 'container' else (kind, 'ls', '-q')
        ids = self.call(*args).splitlines()
        # An unavailable daemon/failed inspect is never proof of absence.
        return json.loads(self.call(kind, 'inspect', *ids)) if ids else []


def identity(kind, item):
    return item['Name'] if kind == 'volume' else item['Id']


def name_of(item):
    return item['Name'].lstrip('/')


def labels_of(kind, item):
    return (item.get('Config', {}).get('Labels') if kind == 'container' else item.get('Labels')) or {}


def core_snapshot(docker, names=CORE):
    items = {name_of(x): x for x in docker.items('container')}
    require(set(names) <= items.keys(), 'shared core inventory incomplete')
    return {name: {'id': items[name]['Id'], 'image': items[name]['Image'],
                   'startedAt': items[name]['State']['StartedAt'],
                   'restartCount': items[name]['RestartCount'],
                   'configurationDigest': configuration_digest([items[name]])}
            for name in names}


def process_identity(pid):
    base = Path('/proc') / str(pid)
    try:
        stat = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        return {'pid': pid, 'startTicks': stat[19],
                'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'cwd': str((base / 'cwd').resolve(strict=True)),
                'commandDigest': 'sha256:' + hashlib.sha256((base / 'cmdline').read_bytes()).hexdigest()}
    except FileNotFoundError:
        return None


class Resources:
    def __init__(self, state, docker=None, core=CORE):
        self.state = Path(state).expanduser().resolve()
        self.docker = docker or Docker()
        self.core = core

    @contextmanager
    def locked(self):
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.state / '.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield self

    def path(self, run):
        require(isinstance(run, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run), 'invalid run ID')
        return self.state / (run + '.json')

    def read(self, run):
        record = load(self.path(run))
        require(record['schema'] == SCHEMA and record['runId'] == run, 'invalid resource record')
        require(record['host'] == self.docker.host and record['engine'] == self.docker.engine(), 'Docker engine changed')
        if record.get('ownershipProof'):
            require(sha(record['ownershipProof']['path']) == record['ownershipProof']['sha256'], 'legacy ownership proof changed')
        return record

    def save(self, record):
        record['updatedAt'] = now()
        atomic(self.path(record['runId']), record)

    def new(self, run, root):
        require(not self.path(run).exists(), 'run already registered; recover original run')
        root = Path(root).absolute()
        require(root == root.resolve() and len(root.parts) >= 3, 'unsafe/symlink workspace root')
        require(not self.state.is_relative_to(root), 'registry must be outside disposable workspace')
        return {'schema': SCHEMA, 'runId': run, 'generation': uuid.uuid4().hex,
                'host': self.docker.host, 'engine': self.docker.engine(), 'root': str(root),
                'coreBefore': core_snapshot(self.docker, self.core), 'createdAt': now(),
                'phase': 'creating', 'resources': [], 'processes': []}

    def marker(self, record, create=False):
        root = Path(record['root'])
        require(root == root.resolve(), 'workspace path changed or is a symlink')
        expected = {k: record[k] for k in ('runId', 'generation', 'engine', 'root')}
        if create:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            require(not (root / MARKER).exists(), 'workspace already owned')
            atomic(root / MARKER, expected)
        require(load(root / MARKER) == expected, 'workspace ownership marker mismatch')

    def scan(self):
        return {kind: self.docker.items(kind) for kind in KINDS}

    def resolve(self, record, resource, inventory=None):
        items = (inventory or self.scan())[resource['kind']]
        same_name = [x for x in items if name_of(x) == resource['name']]
        if resource.get('id'):
            found = [x for x in items if identity(resource['kind'], x) == resource['id']]
        else:
            # Write-ahead intent can recover a lost create response, using a unique generation.
            found = [x for x in same_name if labels_of(resource['kind'], x).get(OWNER_LABEL) == record['generation']]
        require(len(found) <= 1, 'ambiguous resource identity')
        if not found:
            require(not same_name, 'resource name reused by another identity')
            return None
        item = found[0]
        labels = labels_of(resource['kind'], item)
        require(labels.get(RUN_LABEL) == record['runId'], 'resource run label mismatch')
        if not resource.get('legacy'):
            require(labels.get(OWNER_LABEL) == record['generation'], 'resource generation mismatch')
        require(name_of(item) == resource['name'], 'resource renamed')
        resource['id'] = identity(resource['kind'], item)
        return item

    def intent(self, record, kind, name):
        resource = {'kind': kind, 'name': name, 'phase': 'intent'}
        record['resources'].append(resource)
        self.save(record)
        return resource

    def create(self, run, root, daemon=True, image='alpine:3.22.0'):
        record = self.new(run, root)
        require(not Path(root).exists(), 'new workspace must not already exist')
        self.save(record)  # Persist intent before mkdir/network/container mutations.
        try:
            self.marker(record, create=True)
            network = 'acceptance-' + run.lower() + '-outer'
            container = 'acceptance-' + run.lower() + '-daemon'
            labels = ['--label', RUN_LABEL + '=' + run, '--label', OWNER_LABEL + '=' + record['generation']]
            require(not any(name_of(x) in (network, container) for values in self.scan().values() for x in values), 'fixture name already exists')
            n = self.intent(record, 'network', network)
            self.docker.call('network', 'create', *labels, network)
            require(self.resolve(record, n) is not None, 'created network missing')
            self.save(record)
            c = self.intent(record, 'container', container)
            args = ['container', 'create', '--name', container, *labels, '--network', n['id']]
            if daemon:
                r = Path(root) / 'isolated'
                (r / 'socket').mkdir(parents=True, mode=0o700)
                (r / 'docker-data').mkdir()
                args += ['--privileged', '--memory', '4g', '--pids-limit', '4096']
                for source, target in [('/usr/bin', '/usr/bin'), ('/usr/sbin', '/usr/sbin'),
                                       ('/usr/lib64', '/lib64'), ('/lib/x86_64-linux-gnu', '/lib/x86_64-linux-gnu'),
                                       ('/usr/lib/x86_64-linux-gnu', '/usr/lib/x86_64-linux-gnu'),
                                       ('/etc/alternatives', '/etc/alternatives'), ('/lib/modules', '/lib/modules'),
                                       ('/usr/libexec/docker', '/usr/libexec/docker')]:
                    args += ['--mount', f'type=bind,src={source},dst={target},readonly']
                args += ['--mount', f'type=bind,src={r},dst={r}', '--mount', f'type=bind,src={r}/socket,dst=/var/run',
                         '--entrypoint', '/usr/bin/dockerd', image, '--data-root=' + str(r / 'docker-data'),
                         '--exec-root=/run/acceptance-docker', '--pidfile=/run/acceptance-docker.pid',
                         '--host=unix:///var/run/docker.sock', '--storage-driver=overlay2',
                         '--feature=containerd-snapshotter=false', '--bip=172.30.88.1/24', '--log-level=warn', '--group=1000']
            else:
                args += [image, 'sleep', '300']
            self.docker.call(*args)
            require(self.resolve(record, c) is not None, 'created container missing')
            self.save(record)
            self.docker.call('container', 'start', c['id'])
            if daemon:
                inner = Docker('unix://' + str(Path(root) / 'isolated/socket/docker.sock'))
                for attempt in range(30):
                    try:
                        inner.engine()
                        break
                    except (ValueError, subprocess.TimeoutExpired):
                        require(attempt < 29, 'isolated daemon did not become ready')
                        time.sleep(1)
                current = self.resolve(record, c)
                atomic(r / 'daemon-ownership.json', {
                    'container': container, 'containerId': c['id'], 'network': network,
                    'ip': current['NetworkSettings']['Networks'][network]['IPAddress'],
                    'privateSocket': str(r / 'socket/docker.sock'), 'privateDataRoot': str(r / 'docker-data'),
                    'sharedDockerSocketMounted': False, 'onlyOwnedRootWritable': True,
                    'generation': record['generation']})
            else:
                require(self.resolve(record, c)['State']['Running'], 'fixture failed to start')
            record['phase'] = 'active'
            self.save(record)
            return record
        except BaseException as exc:
            record['phase'] = 'creation-failed'
            record['cleanupMode'] = 'rollback'
            record['lastError'] = type(exc).__name__
            self.save(record)
            try:
                self.cleanup_record(record, rollback=True)
            except BaseException as cleanup_error:
                record['phase'] = 'cleanup-failed'
                record['lastError'] = type(cleanup_error).__name__
                self.save(record)
            raise

    def adopt(self, run, ownership, root):
        proof = load(ownership)
        record = self.new(run, root)
        inventory = self.scan()
        container = next((x for x in inventory['container'] if x['Id'] == proof['containerId']), None)
        require(container is not None and name_of(container) == proof['container'], 'archived container not found')
        require(labels_of('container', container).get(RUN_LABEL) == run, 'archived container run differs')
        require(proof.get('sharedDockerSocketMounted') is False and proof.get('onlyOwnedRootWritable') is True, 'unsafe legacy daemon')
        data = Path(proof['privateDataRoot'])
        require(data.is_relative_to(Path(root)) and data.parent != Path(root), 'legacy workspace not contained')
        writable = [m for m in container['Mounts'] if m.get('RW')]
        require(writable and all(m['Type'] == 'bind' and Path(m['Source']).is_relative_to(Path(root)) for m in writable), 'legacy writable mount escapes workspace')
        networks = [x for x in inventory['network'] if name_of(x) == proof['network']]
        require(len(networks) == 1 and container['NetworkSettings']['Networks'][proof['network']]['NetworkID'] == networks[0]['Id'], 'legacy network differs')
        require(labels_of('network', networks[0]).get(RUN_LABEL) == run, 'legacy network ownership differs')
        record['resources'] = [{'kind': kind, 'name': name_of(item), 'id': item['Id'], 'legacy': True, 'phase': 'ready'}
                               for kind, item in [('container', container), ('network', networks[0])]]
        record['ownershipProof'] = {'path': str(Path(ownership).resolve()), 'sha256': sha(ownership)}
        record['phase'] = 'historical-unresolved'
        self.save(record)
        if Path(root).exists():
            self.marker(record, create=True)
        return record

    def retain(self, run, plan):
        record = self.read(run)
        require(record['phase'] in ('active', 'historical-unresolved', 'retained'), 'cannot change a started continuation')
        require(plan.get('reason') and plan.get('cases'), 'retention needs reason and cases')
        parse_time(plan['notBefore'])
        root = Path(record['root'])
        require(plan.get('checks') and plan.get('inputs'), 'continuation needs checks and pinned inputs')
        require(set(plan['cases']) == {x['caseId'] for x in plan.get('evidence', [])}, 'case/evidence mismatch')
        for item in plan['evidence']:
            path = Path(item['path'])
            require(path.resolve() == path and path.is_relative_to(root), 'evidence outside workspace')
        for item in plan['inputs']:
            path = Path(item['path'])
            require(path.resolve() == path and (path.is_relative_to(root) or item.get('tool') is True), 'input outside owned workspace')
            require(sha(path) == item['sha256'], 'input digest mismatch')
        record['retention'] = plan
        record['phase'] = 'retained'
        self.save(record)
        return record

    def track_process(self, run, pid, script):
        record = self.read(run)
        require(record['phase'] in ('active', 'retained', 'historical-unresolved'), 'cannot register process during cleanup')
        current = process_identity(pid)
        require(current is not None and Path(current['cwd']).is_relative_to(Path(record['root'])), 'process outside workspace')
        script = Path(script).resolve(strict=True)
        require(script.is_relative_to(Path(record['root'])), 'process script outside workspace')
        args = [os.fsdecode(x) for x in (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0') if x]
        words = args[1:]
        if Path(args[0]).name in ('bash', 'sh') and '-lc' in args:
            words = shlex.split(args[args.index('-lc') + 1])
        require(any(str((Path(current['cwd']) / arg).resolve()) == str(script)
                    for arg in words), 'process script not present in command')
        require(not any(x['identity']['pid'] == pid for x in record['processes']), 'process already registered')
        record['processes'].append({'identity': current, 'script': str(script), 'sha256': sha(script)})
        self.save(record)

    def untracked_processes(self, record):
        known = {x['identity']['pid'] for x in record['processes']}
        found = []
        for path in Path('/proc').iterdir():
            if not path.name.isdigit() or int(path.name) == os.getpid() or int(path.name) in known:
                continue
            try:
                current = process_identity(int(path.name))
                if current and Path(current['cwd']).is_relative_to(Path(record['root'])):
                    found.append(current['pid'])
            except (PermissionError, ProcessLookupError):
                continue
        return found

    def check_core(self, record):
        require(core_snapshot(self.docker, self.core) == record['coreBefore'], 'shared core identity/configuration changed')

    def stop_processes(self, record):
        for process in record['processes']:
            expected = process['identity']
            current = process_identity(expected['pid'])
            if current is None:
                continue
            require(sha(process['script']) == process['sha256'], 'mock script changed')
            require(current == expected, 'mock process identity changed')
            fd = os.pidfd_open(expected['pid'])
            try:
                require(process_identity(expected['pid']) == expected, 'mock PID reused')
                signal.pidfd_send_signal(fd, signal.SIGTERM)
                for _ in range(50):
                    if process_identity(expected['pid']) is None:
                        break
                    time.sleep(.1)
                require(process_identity(expected['pid']) is None, 'mock did not stop')
            finally:
                os.close(fd)

    def remove_resource(self, record, resource):
        current = self.resolve(record, resource)
        if current is not None:
            if resource['kind'] == 'container':
                self.docker.call('container', 'rm', '-f', resource['id'])
            else:
                self.docker.call(resource['kind'], 'rm', resource['id'])
        require(self.resolve(record, resource) is None, 'resource deletion not confirmed')
        resource['phase'] = 'deleted'
        self.save(record)

    def remove_root(self, record):
        root = Path(record['root'])
        if not root.exists():
            return
        self.marker(record)
        # Root-owned Docker data is removed by a separately registered, confined helper.
        # Marker survives interruption. The helper has no host socket/network/privilege.
        helper = next((x for x in record['resources'] if x.get('role') == 'root-cleaner'), None)
        if helper is None:
            helper = self.intent(record, 'container', 'acceptance-' + record['runId'].lower() + '-root-cleaner')
            helper['role'] = 'root-cleaner'
            self.save(record)
        current = self.resolve(record, helper)
        if current is None:
            self.docker.call('container', 'create', '--name', helper['name'], '--network', 'none',
                             '--label', RUN_LABEL + '=' + record['runId'], '--label', OWNER_LABEL + '=' + record['generation'],
                             '--cap-drop', 'ALL', '--cap-add', 'DAC_OVERRIDE', '--cap-add', 'FOWNER',
                             '--security-opt', 'no-new-privileges', '--mount', f'type=bind,src={root},dst=/owned',
                             'alpine:3.22.0', 'sh', '-ec',
                             'find /owned -mindepth 1 -maxdepth 1 ! -name ' + MARKER + ' -exec rm -rf -- {} +')
            require(self.resolve(record, helper) is not None, 'root helper not found')
            self.save(record)
        self.docker.call('container', 'start', helper['id'])
        require(self.docker.call('container', 'wait', helper['id']) == '0', 'private workspace cleanup failed')
        require(set(p.name for p in root.iterdir()) == {MARKER}, 'private workspace still contains resources')
        self.remove_resource(record, helper)
        self.marker(record)
        (root / MARKER).unlink()
        root.rmdir()

    def cleanup_record(self, record, rollback=False):
        self.check_core(record)
        if Path(record['root']).exists():
            self.marker(record)
        if not rollback:
            require(record['phase'] in ('archived', 'cleanup-failed', 'cleaned'), 'verification/archive required before cleanup')
            require(record.get('archive'), 'missing archive receipt')
            self.check_archive(record)
        self.save(record)
        self.stop_processes(record)
        require(not self.untracked_processes(record), 'unregistered process in workspace; identify before cleanup')
        for kind, items in self.scan().items():
            for item in items:
                if labels_of(kind, item).get(RUN_LABEL) == record['runId']:
                    matched = next((x for x in record['resources'] if x['kind'] == kind and
                                    x['name'] == name_of(item)), None)
                    require(matched is not None and self.resolve(record, matched) is not None,
                            'unregistered resource in run; identify before cleanup')
        # Containers first; do not detach unrelated network endpoints to force success.
        for kind in ('container', 'network'):
            for resource in list(record['resources']):
                if resource['kind'] == kind and resource.get('role') != 'root-cleaner':
                    self.remove_resource(record, resource)
        self.remove_root(record)
        self.check_core(record)
        record['phase'] = 'cleaned'
        record.pop('lastError', None)
        self.save(record)

    def cleanup(self, run):
        record = self.read(run)
        try:
            self.cleanup_record(record, rollback=record.get('cleanupMode') == 'rollback' or
                                record['phase'] in ('creation-failed', 'creating'))
        except BaseException as exc:
            # Do not promote a precondition rejection into permission to bypass retention.
            if record['phase'] in ('archived', 'cleanup-failed', 'creating', 'creation-failed'):
                record['phase'] = 'cleanup-failed'
                record['lastError'] = type(exc).__name__
                self.save(record)
            raise
        return record

    def check_archive(self, record):
        receipt = record['archive']
        manifest = load(Path(receipt['path']) / 'manifest.json')
        require(sha(Path(receipt['path']) / 'manifest.json') == receipt['sha256'], 'archive manifest changed')
        for item in manifest['files']:
            require(sha(Path(receipt['path']) / item['name']) == item['sha256'], 'archived evidence changed')
        for item in manifest.get('references', []):
            require(sha(item['path']) == item['sha256'], 'retirement evidence reference changed')

    def retire(self, run, decision, archive):
        """Archive a reviewed historical disposition; does not remove any resource."""
        record = self.read(run)
        require(record['phase'] == 'historical-unresolved', 'only historical runs can be retired')
        require(decision.get('runId') == run and decision.get('engine') == record['engine'], 'retirement identity mismatch')
        require(decision.get('resourceIds') == sorted(x['id'] for x in record['resources']), 'retirement resource IDs mismatch')
        require(decision.get('reason') and decision.get('pendingCases') == [] and
                decision.get('disposition') in ('completed', 'superseded'), 'retirement needs an explicit final disposition')
        require(decision.get('references'), 'retirement needs archived evidence references')
        self.check_core(record)
        for resource in record['resources']:
            self.resolve(record, resource)
        for item in decision['references']:
            path = Path(item['path']).resolve()
            require(not path.is_relative_to(Path(record['root'])), 'retirement proof must survive workspace deletion')
            require(sha(path) == item['sha256'], 'retirement evidence digest mismatch')
        target = Path(archive).resolve()
        require(not target.is_relative_to(Path(record['root'])), 'archive inside disposable workspace')
        require(not target.exists(), 'retirement archive must be new')
        atomic(target / 'retirement.json', decision)
        manifest = {'schema': SCHEMA, 'runId': run, 'generation': record['generation'],
                    'files': [{'name': 'retirement.json', 'sha256': sha(target / 'retirement.json')}],
                    'references': decision['references']}
        atomic(target / 'manifest.json', manifest)
        record['archive'] = {'path': str(target), 'sha256': sha(target / 'manifest.json')}
        record['phase'] = 'archived'
        self.save(record)
        return record

    def continue_run(self, run, archive):
        record = self.read(run)
        if record['phase'] in ('archived', 'cleanup-failed', 'cleaned'):
            return self.cleanup(run)
        require(record['phase'] in ('retained', 'verified'), 'continuation in unknown/failed state; review before retrying business probes')
        plan = record['retention']
        require(datetime.now(timezone.utc) > parse_time(plan['notBefore']), 'real retention boundary not reached')
        self.check_core(record)
        for resource in record['resources']:
            require(self.resolve(record, resource) is not None, 'retained resource missing')
        self.marker(record)
        for item in plan['inputs']:
            require(sha(item['path']) == item['sha256'], 'continuation input changed')
        if record['phase'] == 'retained':
            record['phase'] = 'verifying'
            record['verificationStartedAt'] = now()
            self.save(record)
            # No retries of writes after timeout, cancellation or an unknown result.
            try:
                for check in plan['checks']:
                    require(Path(check['cwd']).is_relative_to(Path(record['root'])), 'check cwd outside owned workspace')
                    subprocess.run(check['argv'], cwd=check['cwd'], check=True, timeout=check.get('timeout', 240),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for evidence in plan['evidence']:
                    result = load(evidence['path'])
                    require(result.get('passed') is True and result.get('status') == 'passed', 'natural verification did not pass')
                    require(result.get('checks') and all(x.get('passed') is True for x in result['checks']), 'incomplete verification checks')
                    require(parse_time(result['startedAt']) >= parse_time(record['verificationStartedAt']), 'stale verification result')
                    require(result.get('cases', {}).get(evidence['caseId']) == 'passed', 'case receipt mismatch')
                record['phase'] = 'verified'
                record['verifiedEvidence'] = [{'path': x['path'], 'caseId': x['caseId'], 'sha256': sha(x['path']),
                                               'publicFields': x.get('publicFields')} for x in plan['evidence']]
                self.save(record)
            except BaseException as exc:
                record['phase'] = 'verification-failed'
                record['lastError'] = type(exc).__name__
                self.save(record)
                raise
        # Archive retry never reruns business probes. Archive failure leaves everything retained.
        target = Path(archive).resolve()
        require(not target.is_relative_to(Path(record['root'])), 'archive must be outside disposable workspace')
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        files = []
        for index, item in enumerate(record['verifiedEvidence']):
            require(sha(item['path']) == item['sha256'], 'verified evidence changed before archive')
            destination = target / (str(index) + '-' + Path(item['path']).name)
            payload = Path(item['path']).read_bytes()
            if item.get('publicFields'):
                source = json.loads(payload)
                payload = (json.dumps({k: source[k] for k in item['publicFields'] if k in source},
                                      indent=2, ensure_ascii=False) + '\n').encode()
            expected_digest = 'sha256:' + hashlib.sha256(payload).hexdigest()
            require(not destination.exists() or sha(destination) == expected_digest, 'archive collision')
            if not destination.exists():
                atomic(destination, payload)
            files.append({'name': destination.name, 'sha256': sha(destination), 'caseId': item['caseId'],
                          'sourceDigest': item['sha256']})
        manifest = {'schema': SCHEMA, 'runId': run, 'generation': record['generation'],
                    'verificationStartedAt': record['verificationStartedAt'], 'files': files}
        manifest_path = target / 'manifest.json'
        require(not manifest_path.exists() or load(manifest_path) == manifest, 'archive manifest collision')
        atomic(manifest_path, manifest)
        record['archive'] = {'path': str(target), 'sha256': sha(manifest_path)}
        record['phase'] = 'archived'
        self.save(record)
        self.check_archive(record)
        return self.cleanup(run)

    def report(self):
        inventory = self.scan()
        records = [self.read(path.stem) for path in sorted(self.state.glob('*.json'))]
        report = {'schema': SCHEMA, 'observedAt': now(), 'runs': [], 'unresolved': [], 'allCleaned': False, 'passed': False}
        explained = set()
        for record in records:
            errors, remaining = [], []
            try:
                self.check_core(record)
                for resource in record['resources']:
                    current = self.resolve(record, resource, inventory)
                    if record['phase'] == 'retained':
                        require(current is not None, 'retained resource missing')
                        if resource['kind'] == 'container':
                            require(current['State']['Running'], 'retained daemon not running')
                    if current is not None:
                        key = (resource['kind'], resource['id'])
                        explained.add(key)
                        entry = {'kind': key[0], 'id': key[1], 'name': resource['name']}
                        if key[0] == 'container':
                            entry['runtimeState'] = current['State'].get('Status', 'running' if current['State']['Running'] else 'stopped')
                            entry['exitCode'] = current['State'].get('ExitCode')
                        remaining.append(entry)
                if Path(record['root']).exists():
                    self.marker(record)
                    remaining.append({'kind': 'workspace', 'path': record['root']})
                elif record['phase'] == 'retained':
                    raise ValueError('retained workspace missing')
                for process in record['processes']:
                    expected = process['identity']
                    if process_identity(expected['pid']) is not None:
                        require(process_identity(expected['pid']) == expected, 'mock process identity changed')
                        remaining.append({'kind': 'process', 'pid': expected['pid']})
                    elif record['phase'] == 'retained':
                        raise ValueError('retained mock process missing')
                require(not self.untracked_processes(record), 'unregistered process in workspace')
                if record['phase'] == 'retained':
                    for item in record['retention']['inputs']:
                        require(sha(item['path']) == item['sha256'], 'retention input changed')
                if record.get('archive'):
                    self.check_archive(record)
            except (ValueError, OSError, KeyError) as exc:
                errors.append(str(exc))
            status = 'cleaned' if not remaining and not errors and record['phase'] == 'cleaned' else 'historical-unresolved'
            if record['phase'] == 'retained' and not errors:
                plan = record['retention']
                if datetime.now(timezone.utc) <= parse_time(plan['notBefore']):
                    status = 'retained-pending'
                else:
                    status = 'verification-due'
            elif record['phase'] in ('cleanup-failed', 'verification-failed', 'verifying', 'verified', 'archived') or errors:
                status = 'cleanup-failed' if record['phase'] == 'cleanup-failed' or errors else 'incomplete'
            report['runs'].append({'runId': record['runId'], 'status': status, 'phase': record['phase'],
                                   'remaining': remaining, 'errors': errors,
                                   'retention': {k: record['retention'][k] for k in ('reason', 'cases', 'notBefore')} if 'retention' in record else None})
        for kind, items in inventory.items():
            for item in items:
                labels = labels_of(kind, item)
                name = name_of(item)
                candidate = labels.get(RUN_LABEL) or re.match(r'^(acceptance-|native-|accept-|codex-b)', name)
                if candidate and (kind, identity(kind, item)) not in explained:
                    report['unresolved'].append({'kind': kind, 'name': name, 'id': identity(kind, item),
                                                  'runId': labels.get(RUN_LABEL), 'status': 'ownership-unresolved'})
        statuses = [x['status'] for x in report['runs']]
        report['allCleaned'] = not report['unresolved'] and all(x == 'cleaned' for x in statuses)
        report['passed'] = not report['unresolved'] and all(x in ('cleaned', 'retained-pending') for x in statuses)
        return report


def check_candidate(before, after):
    """Verify a retained container candidate matches its archived config and health."""
    require(after is not None and after['Name'].lstrip('/') == before['name'], 'retained candidate identity changed')
    require(after['Image'] == before['image'] and after['State']['StartedAt'] == before['startedAt'] and
            after['RestartCount'] == before['restartCount'], 'retained candidate image/start/restart changed')
    require(after['State']['Running'] and after['State'].get('Health', {}).get('Status', 'healthy') == 'healthy',
            'retained candidate not healthy')
    # Preserve the original capture's exact encoding; do not reinterpret its historical digest.
    config = {'Config': after['Config'], 'HostConfig': after['HostConfig'],
              'Mounts': sorted(after['Mounts'], key=lambda x: x.get('Destination', ''))}
    actual = 'sha256:' + hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    require(actual == before['configurationDigest'], 'retained candidate configuration changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path.home() / '.local/state/platform-acceptance/resources')
    parser.add_argument('--host', default='unix:///var/run/docker.sock')
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('create')
    create.add_argument('--run', required=True)
    create.add_argument('--root', type=Path, required=True)
    create.add_argument('--fixture', action='store_true', help='small non-privileged lifecycle regression fixture')
    adopt = commands.add_parser('adopt')
    adopt.add_argument('--run', required=True)
    adopt.add_argument('--root', type=Path, required=True)
    adopt.add_argument('--ownership', type=Path, required=True)
    retain = commands.add_parser('retain')
    retain.add_argument('--run', required=True)
    retain.add_argument('--plan', type=Path, required=True)
    resume = commands.add_parser('continue')
    resume.add_argument('--run', required=True)
    resume.add_argument('--archive', type=Path, required=True)
    cleanup = commands.add_parser('cleanup')
    cleanup.add_argument('--run', required=True)
    process = commands.add_parser('track-process')
    process.add_argument('--run', required=True)
    process.add_argument('--pid', required=True, type=int)
    process.add_argument('--script', required=True, type=Path)
    retire = commands.add_parser('retire')
    retire.add_argument('--run', required=True)
    retire.add_argument('--decision', required=True, type=Path)
    retire.add_argument('--archive', required=True, type=Path)
    report = commands.add_parser('report')
    report.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        with Resources(args.state, Docker(args.host)).locked() as owner:
            if args.action == 'create':
                owner.create(args.run, args.root, daemon=not args.fixture)
            elif args.action == 'adopt':
                owner.adopt(args.run, args.ownership, args.root)
            elif args.action == 'retain':
                owner.retain(args.run, load(args.plan))
            elif args.action == 'continue':
                owner.continue_run(args.run, args.archive)
            elif args.action == 'cleanup':
                owner.cleanup(args.run)
            elif args.action == 'track-process':
                owner.track_process(args.run, args.pid, args.script)
            elif args.action == 'retire':
                owner.retire(args.run, load(args.decision), args.archive)
            result = owner.report()
            if args.action == 'report' and args.output:
                atomic(args.output, result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result['passed'] else 2
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print('acceptance resource lifecycle incomplete: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
