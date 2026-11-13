#!/usr/bin/env python3
"""Run standard branches with candidate, evidence, report and cleanup gates."""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def run_browser(command, private, directory, *, startup_seconds=120):
    """Bound launch only; preserve original unknown business commands after launch."""
    marker = private / 'browser-started.json'
    if marker.exists():
        raise ValueError('Fresh browser execution must not reuse a startup marker')
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    while process.poll() is None and not marker.exists():
        if time.monotonic() - started >= startup_seconds:
            # Kill only the session created above, never a platform service or
            # unrelated browser. Kernel D-state descendants may outlive signals.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            code = process.wait(timeout=10)
            save(directory / 'browser-startup.json', {
                'status': 'blocked', 'reason': 'Browser launch deadline exceeded before post-launch marker',
                'startupBudgetSeconds': startup_seconds, 'driverExit': code,
                'disposition': 'Original private state retained; no retry, resource cleanup or kernel-thread termination claimed',
            })
            return code
        time.sleep(min(0.1, startup_seconds))
    return process.wait()


def tool_hashes():
    runtime = ROOT / 'regression'
    paths = sorted(path for path in runtime.iterdir() if path.is_file() and
                   (path.suffix == '.cjs' and not path.name.endswith('.test.cjs') or
                    path.suffix == '.py' and not path.name.startswith('test_')))
    return {path.name: 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


@contextmanager
def environment_lock(credentials):
    origin = json.loads(credentials.read_text()).get('origin', '')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Credentials require an explicit HTTPS origin without userinfo')
    key = hashlib.sha256((parsed.hostname.lower() + ':' + str(parsed.port or 443)).encode()).hexdigest()
    directory = Path.home() / '.local/state/magicTest/regression-locks'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / (key + '.lock')).open('a') as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another standard regression owns this environment; no browser mutations started') from None
        try:
            yield
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)


def load_owner(catalog_path):
    script = catalog_path.parent.parent / 'scripts/platform_acceptance.py'
    spec = importlib.util.spec_from_file_location('platform_acceptance', script)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    return owner


def save(path, value):
    with path.open('x') as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write('\n')


def relocate(entry, prefix):
    entry = copy.deepcopy(entry)
    for proof in entry.get('evidence', []):
        proof['path'] = str(Path(prefix) / proof['path'])
    return entry


def finish(owner, catalog, before, after, browser, directory, browser_exit):
    same_candidate = before['environment'] == after['environment']
    cleanup_files = sorted((directory / 'browser/attempts').glob('*/cleanup.json'))
    cleanup = [{'path': str(p.relative_to(directory)),
                'sha256': 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest(),
                'allCleaned': json.loads(p.read_text()).get('allCleaned') is True}
               for p in cleanup_files]
    cleaned = bool(cleanup) and all(p['allCleaned'] for p in cleanup)
    result = {**before, 'runId': directory.name,
              'results': [relocate(e, 'browser') for e in browser.get('results', [])]}
    # Health is an independent real handler, never a substitute for browser cases.
    selected = {entry['caseId'] for entry in result['results']}
    if same_candidate and 'F059-001' in selected:
        result['results'] = [e for e in result['results'] if e['caseId'] != 'F059-001']
        result['results'].append(relocate(after['results'][0], 'health-after'))
    save(directory / 'results.json', result)
    entries = owner.validate_results(catalog, result, directory)
    report = owner.summarize(catalog, entries, 'standard')
    report['environment'] = before['environment']
    report['executionGates'] = {
        'sameDeploymentBeforeAfter': same_candidate,
        'healthyBeforeAfter': before['results'][0]['status'] == after['results'][0]['status'] == 'passed',
        'browserExit': browser_exit,
        'currentBrowserResourcesCleaned': cleaned,
        'cleanupEvidence': cleanup,
        'historicalInfrastructureRegistry': 'not reconciled by browser runner; isolated-ops handlers must prove their own lifecycle',
    }
    report['caseComplete'] = report['complete']
    gates = report['executionGates']
    report['complete'] = report['complete'] and same_candidate and cleaned and gates['healthyBeforeAfter'] and browser_exit == 0
    report['catalogCoverage']['complete'] = report['catalogCoverage']['complete'] and report['complete']
    save(directory / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=os.getenv('MAGICTEST_REGRESSION_CONFIG'),
                        help='private JSON: credentials, output; optional catalog, cases, chrome')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.config).expanduser().read_text()) if args.config else {}
    unknown = set(config) - {'credentials', 'output', 'catalog', 'cases', 'chrome', 'fileUploadMaxBytes', 'deliveryFixtureConfig', 'databaseFixtureMode', 'runtimeSnapshotConfig'}
    if unknown:
        raise ValueError('Unknown regression config fields: ' + ', '.join(sorted(unknown)))
    if 'fileUploadMaxBytes' in config and (type(config['fileUploadMaxBytes']) is not int or not 1 <= config['fileUploadMaxBytes'] <= 1024 ** 3):
        raise ValueError('fileUploadMaxBytes requires the verified positive deployment content limit within the 1 GiB tool budget')
    if 'databaseFixtureMode' in config and (config['databaseFixtureMode'] not in ['bounded', 'isolated-tmpfs-only'] or config['databaseFixtureMode'] == 'isolated-tmpfs-only' and not config.get('deliveryFixtureConfig')):
        raise ValueError('databaseFixtureMode requires bounded or isolated-tmpfs-only with dedicated deliveryFixtureConfig')
    if 'runtimeSnapshotConfig' in config and (not isinstance(config['runtimeSnapshotConfig'], str) or not config['runtimeSnapshotConfig'].strip()):
        raise ValueError('runtimeSnapshotConfig requires a non-empty private file path')
    catalog_path = Path(config.get('catalog', ROOT.parent / 'docs/acceptance/platform-catalog.json')).expanduser().resolve()
    owner = load_owner(catalog_path)
    catalog = json.loads(catalog_path.read_text())
    owner.validate_catalog(catalog)
    cases = config.get('cases')
    standard_ids = {c['id'] for c in catalog['cases'] if c['required'] and any(p['suite'] == 'standard' for p in c['execution'])}
    if cases is not None and (not isinstance(cases, list) or not cases or any(not isinstance(c, str) or c not in standard_ids for c in cases) or len(cases) != len(set(cases))):
        raise ValueError('cases must be distinct required standard case IDs')
    command = ['node', str(ROOT / 'regression/standard.cjs'), '--catalog', str(catalog_path)]
    if cases:
        command += ['--cases', ','.join(cases)]
    if 'fileUploadMaxBytes' in config:
        command += ['--file-upload-max-bytes', str(config['fileUploadMaxBytes'])]
    if 'deliveryFixtureConfig' in config:
        command += ['--delivery-fixture-config', str(Path(config['deliveryFixtureConfig']).expanduser().resolve())]
    if 'databaseFixtureMode' in config:
        command += ['--database-fixture-mode', config['databaseFixtureMode']]
    if 'runtimeSnapshotConfig' in config:
        command += ['--runtime-snapshot-config', str(Path(config['runtimeSnapshotConfig']).expanduser().absolute())]
    if args.dry_run:
        return subprocess.run(command + ['--dry-run', 'true'], cwd=ROOT).returncode
    for name in ['credentials', 'output']:
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ValueError('Missing private config field: ' + name)
    credentials = Path(config['credentials']).expanduser().resolve()
    if not credentials.is_file():
        raise ValueError('Credentials file does not exist')
    with environment_lock(credentials):
        return execute_live(config, catalog_path, owner, catalog, command, credentials, cases)


def execute_live(config, catalog_path, owner, catalog, command, credentials, cases):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    directory = Path(config['output']).expanduser().resolve() / stamp
    directory.mkdir(parents=True, exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix='platform-standard-' + stamp + '-'))
    print('Evidence: ' + str(directory), flush=True)
    print('Private recovery state (retained outside repositories): ' + str(private), flush=True)
    inputs = tool_hashes()
    save(directory / 'inputs.json', {'suite': 'standard', 'selectedCases': cases or 'all required standard branches',
                                    'catalogDigest': owner.digest(catalog), 'toolHashes': inputs,
                                    'fileUploadMaxBytes': config.get('fileUploadMaxBytes'),
                                    'runtimeSnapshotConfigDigest': 'sha256:' + hashlib.sha256(Path(config['runtimeSnapshotConfig']).expanduser().read_bytes()).hexdigest() if config.get('runtimeSnapshotConfig') else None,
                                    'databaseFixtureMode': config.get('databaseFixtureMode', 'bounded'),
                                    'coordination': 'exclusive local origin lock held through preflight, mutations, cleanup and report',
                                    'credentials': 'external private file, not archived',
                                    'deliveryFixtureConfigDigest': 'sha256:' + hashlib.sha256(Path(config['deliveryFixtureConfig']).expanduser().read_bytes()).hexdigest() if config.get('deliveryFixtureConfig') else None})
    before_path = owner.capture_health(catalog, directory / 'health-before')
    before = json.loads(before_path.read_text())
    if before['results'][0]['status'] != 'passed':
        save(directory / 'preflight.json', {'status': 'blocked', 'reason': 'Core health preflight failed; browser mutations not started'})
        return 2
    command += ['--credentials', str(credentials), '--private-state', str(private),
                '--output', str(directory / 'browser'), '--baseline-health', str(before_path)]
    if config.get('chrome'):
        command += ['--chrome', str(Path(config['chrome']).expanduser())]
    browser_exit = run_browser(command, private, directory)
    after_path = owner.capture_health(catalog, directory / 'health-after')
    after = json.loads(after_path.read_text())
    browser_path = directory / 'browser/results.json'
    browser = json.loads(browser_path.read_text()) if browser_path.exists() else {}
    report = finish(owner, catalog, before, after, browser, directory, browser_exit)
    print(json.dumps({'counts': report['counts'], 'complete': report['complete'],
                      'executionGates': report['executionGates']}, ensure_ascii=False))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        # Config and credential file contents are intentionally never printed.
        print('Standard regression orchestration failed: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        sys.exit(1)
