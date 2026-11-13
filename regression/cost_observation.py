"""Bounded read-only observation using the candidate's formal cost tools.

One ready line is emitted only after the original baseline snapshot. The caller
may issue one ordinary request, then receives the original interval's result.
No SQL text, container environment, credentials or unrelated logs are exported.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time


class ObservationUnavailable(ValueError):
    """Static tool diagnostic, safe to export without subprocess output."""


def load_tool(root, name):
    file = Path(root) / 'scripts' / name
    if file.resolve() != file or not file.is_file():
        raise ObservationUnavailable('Original regular candidate cost tool required')
    original = file.read_bytes()
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if file.read_bytes() != original:
        raise ObservationUnavailable('Candidate cost tool changed while loading')
    return module, 'sha256:' + hashlib.sha256(original).hexdigest()


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=45)


def topology(config):
    info = json.loads(command(['docker', 'info', '--format', '{{json .}}']))
    root = config['platformRoot']
    if (not re.fullmatch(r'/tmp/platform-executor-[A-Za-z0-9_/-]+', root)
            or str(Path(root).resolve()) != root
            or config['dockerDataRoot'] != str(Path(root).parent / 'docker-data')
            or info['ID'] != config['daemonId']
            or info['DockerRootDir'] != config['dockerDataRoot']
            or info['Driver'] != 'overlay2'
            or not re.fullmatch(r'[a-f0-9]{64}', config['containerId'])
            or os.uname().nodename != config['containerId'][:12]):
        raise ObservationUnavailable('Original dedicated daemon and deployment required')
    names = config['costObservation']['containers']
    if (not isinstance(names, list) or not 4 <= len(names) <= 16
            or len(set(names)) != len(names)
            or not {'magicPanel', 'magicbase', 'magiccas', 'postgres'} <= set(names)
            or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', n) for n in names)):
        raise ObservationUnavailable('Finite explicit actual observation containers required')
    rows = json.loads(command(['docker', 'inspect', *names]))
    if len(rows) != len(names):
        raise ObservationUnavailable('Complete original container identities required')
    result = []
    for row in rows:
        env = row.get('Config', {}).get('Env', [])
        switches = {}
        for key in ['MAGIC_PROFILE_WINDOW', 'MAGIC_PROFILE_SAMPLE_EVERY']:
            values = [v.split('=', 1)[1] for v in env if v.startswith(key + '=')]
            if len(values) > 1:
                raise ObservationUnavailable('Duplicate effective profile declaration')
            value = values[0] if values else ''
            # Only profile controls leave this process, never the rest of Env.
            if not re.fullmatch(r'[0-9smh.]{0,30}', value):
                raise ObservationUnavailable('Invalid bounded profile declaration')
            switches[key] = value
        result.append({'name': row['Name'].removeprefix('/'), 'id': row['Id'],
                       'image': row['Image'], 'startedAt': row['State']['StartedAt'],
                       'running': row['State']['Running'], 'switches': switches})
    if {r['name'] for r in result} != set(names) or any(not r['running'] for r in result):
        raise ObservationUnavailable('All exact declared containers must be running')
    return sorted(result, key=lambda r: r['name'])


def snapshot(collector):
    # These are the documented PostgreSQL statistics, never owner business data.
    rows = collector.sql('postgres', 'postgres', collector.DB_SQL)
    available = collector.sql('postgres', 'postgres',
                              "SELECT to_json(EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements'));")
    if type(available) is not bool:
        raise ObservationUnavailable('Explicit statement statistics availability required')
    statements = collector.sql('postgres', 'postgres', collector.STAT_SQL) if available else None
    return {'at': time.time(), 'database': rows, 'statementStatisticsAvailable': available, 'statements': statements}


def phase(config, phase_name, seconds, token, emit=print, sleep=time.sleep):
    before_containers = topology(config)
    collector, collector_hash = load_tool(config['platformRoot'], 'collect-qps-analysis.py')
    summarizer, summary_hash = load_tool(config['platformRoot'], 'summarize-qps-analysis.py')
    before = snapshot(collector)
    start = time.time()
    emit(json.dumps({'kind': 'ready', 'token': token, 'startedAt': start,
                     'containers': before_containers}), flush=True)
    sleep(seconds)
    after = snapshot(collector)
    end = time.time()
    after_containers = topology(config)
    if before_containers != after_containers:
        raise ObservationUnavailable('Original container or effective observation switch changed')
    report = {'phase': phase_name, 'startedAt': start, 'finishedAt': end, 'errors': [], 'events': [],
              'statementStatisticsAvailable': before['statementStatisticsAvailable'], 'databaseDelta': []}
    for name in config['costObservation']['containers']:
        def iso(t):
            return datetime.fromtimestamp(t, timezone.utc).isoformat()
        proc = subprocess.run(['docker', 'logs', '--tail', '5000', '--since', iso(start), '--until', iso(end), name],
                              capture_output=True, text=True, check=True, timeout=30)
        lines = (proc.stdout + '\n' + proc.stderr).splitlines()
        if len(lines) >= 5000:
            raise ObservationUnavailable('Possible original observation log truncation')
        rejected = []
        for line in lines:
            event = collector.parse_log(line, rejected)
            if not event or event['kind'] not in ['window', 'sample']:
                continue
            if event['kind'] == 'window':
                data = event['data']
                begin = datetime.fromisoformat(data['startedAt'].replace('Z', '+00:00')).timestamp()
                finish = datetime.fromisoformat(data['endedAt'].replace('Z', '+00:00')).timestamp()
                event['fullyInsidePhase'] = start <= begin < finish <= end
            report['events'].append({'container': name, **event})
        if rejected:
            raise ObservationUnavailable('Malformed observation diagnostic record')
    if before['statementStatisticsAvailable'] != after['statementStatisticsAvailable']:
        raise ObservationUnavailable('Statement statistics availability changed during original phase')
    database_keys = ['xact_commit', 'xact_rollback', 'blks_read', 'blks_hit', 'temp_bytes', 'deadlocks',
                     'tup_returned', 'tup_fetched', 'tup_inserted', 'tup_updated', 'tup_deleted', 'blk_read_time', 'blk_write_time']
    report['databaseDelta'] = collector.delta(before['database'], after['database'], database_keys, ['datname'])
    # An empty/removed starting database is incomplete; the owner delta helper
    # already marks newly observed/reset/decreasing statistics as invalid.
    if ({r['datname'] for r in before['database']} != {r['datname'] for r in after['database']}
            or not report['databaseDelta'] or any(not r['valid'] for r in report['databaseDelta'])):
        raise ObservationUnavailable('Original complete database counter interval changed or reset')
    if before['statementStatisticsAvailable']:
        a, b = before['statements'], after['statements']
        report['statementStatisticsReset'] = a['reset'] != b['reset']
        report['statementDelta'] = collector.delta(a['rows'], b['rows'],
            ['calls', 'total_exec_time', 'rows', 'shared_blks_hit', 'shared_blks_read', 'temp_blks_read', 'temp_blks_written'],
            ['dbid', 'userid', 'queryid', 'toplevel'])
        # PostgreSQL queryid is signed int64. Preserve exact identities when
        # this Python evidence crosses the JavaScript JSON boundary.
        for row in report['statementDelta']:
            row['identity'] = [str(v) if type(v) is int else v for v in row['identity']]
        if report['statementStatisticsReset']:
            raise ObservationUnavailable('Original statement statistics were reset')
    report['coverage'] = {'fullWindows': sum(e['kind'] == 'window' and e['fullyInsidePhase'] for e in report['events']),
                          'sampleRecords': sum(e['kind'] == 'sample' for e in report['events'])}
    for name, original_hash in [('collect-qps-analysis.py', collector_hash), ('summarize-qps-analysis.py', summary_hash)]:
        if 'sha256:' + hashlib.sha256((Path(config['platformRoot']) / 'scripts' / name).read_bytes()).hexdigest() != original_hash:
            raise ObservationUnavailable('Original candidate cost tool changed during capture')
    return {'kind': 'result', 'token': token, 'containers': before_containers,
            'tools': {'collector': collector_hash, 'summarizer': summary_hash},
            'report': report, 'summary': summarizer.summarize(report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--phase', choices=['idle', 'read'], required=True)
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    if not 8 <= args.seconds <= 40 or not re.fullmatch(r'[a-f0-9]{32}', args.token):
        raise ObservationUnavailable('Finite observation interval and exact original token required')
    config = json.loads(Path(args.config).read_text())
    print(json.dumps(phase(config, args.phase, args.seconds, args.token)), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Child stderr must not serialize subprocess output or original logs.
        print(json.dumps({'kind': 'unavailable', 'errorType': type(error).__name__,
                          **({'reason': str(error)} if isinstance(error, ObservationUnavailable) else {})}), flush=True)
        raise SystemExit(2)
