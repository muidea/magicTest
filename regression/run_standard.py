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
import shutil
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


DELIVERY_STAGE_ACTIONS = (
    ('new', 'bootstrap', 'bootstrapped'),
    ('bootstrapped', 'publish', 'published'),
    ('published', 'install', 'installed'),
    ('installed', 'members', 'members-ready'),
)
UNRESOLVED_CAS_PHASES = {'sending', 'unknown', 'response-not-delivered'}


def _delivery_fixture_blocked(directory, reason, **extra):
    save(directory / 'preflight.json', {'status': 'blocked', 'reason': reason, **extra})
    return False


def _validate_delivery_state(state, fixture_config):
    if state.get('daemonId') != fixture_config.get('daemonId') or state.get('containerId') != fixture_config.get('containerId'):
        return 'Original delivery fixture identity does not match deliveryFixtureConfig; no automatic initialization or replay'
    if any(cmd.get('outcome') == 'unknown' for cmd in state.get('commands', [])):
        return 'Original delivery fixture has unresolved commands; inspect fixture-state.json without replay'
    if any(form.get('phase') in UNRESOLVED_CAS_PHASES for form in state.get('originalCasForms', [])):
        return 'Original delivery fixture has unresolved CAS forms; inspect fixture-state.json without replay'
    return None


def _ready_manifest_error(private_root, fixture_config):
    manifest_file = private_root / 'fixture-manifest.json'
    members_file = private_root / 'member-credentials.json'
    if not manifest_file.is_file() or not members_file.is_file():
        return 'Delivery fixture reached members-ready but fixture-manifest.json or member-credentials.json is missing'
    manifest = json.loads(manifest_file.read_text())
    if manifest.get('status') != 'published' or manifest.get('daemonId') != fixture_config.get('daemonId'):
        return 'Delivery fixture manifest does not match expected published status or daemonId'
    return None


def ensure_delivery_fixture(fixture_config_path, directory):
    """Verify delivery fixture readiness and prepare missing stages only from clean confirmed states."""
    try:
        fixture_config = json.loads(fixture_config_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return _delivery_fixture_blocked(directory, f'Unable to read deliveryFixtureConfig: {error}')
    private_root_raw = fixture_config.get('privateRoot')
    if not isinstance(private_root_raw, str) or not private_root_raw.strip():
        return _delivery_fixture_blocked(directory, 'deliveryFixtureConfig requires a non-empty privateRoot')
    private_root = Path(private_root_raw).expanduser()
    state_file = private_root / 'fixture-state.json'
    manifest_file = private_root / 'fixture-manifest.json'

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except (OSError, json.JSONDecodeError) as error:
            return _delivery_fixture_blocked(directory, f'Unable to read delivery fixture state: {error}')
        conflict = _validate_delivery_state(state, fixture_config)
        if conflict:
            return _delivery_fixture_blocked(directory, conflict)
        stage = state.get('stage')
    else:
        if manifest_file.exists():
            return _delivery_fixture_blocked(directory, 'Delivery fixture manifest exists without fixture-state.json; refusing overwrite')
        stage = 'new'

    if stage == 'members-ready':
        error = _ready_manifest_error(private_root, fixture_config)
        if error:
            return _delivery_fixture_blocked(directory, error)
        save(directory / 'delivery-fixture-preflight.json', {
            'status': 'ready',
            'stage': stage,
            'preparedActions': [],
            'manifestDigest': 'sha256:' + hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
        })
        return True

    stage_index = next((idx for idx, item in enumerate(DELIVERY_STAGE_ACTIONS) if item[0] == stage), None)
    if stage_index is None:
        return _delivery_fixture_blocked(directory, f'Delivery fixture state is {stage!r}; inspect or reconcile original state without replay')

    prepared = []
    for _, action, expected_stage in DELIVERY_STAGE_ACTIONS[stage_index:]:
        print(f'Delivery fixture preflight: running {action}...', flush=True)
        proc = subprocess.run(
            ['node', str(ROOT / 'regression/delivery_fixture.cjs'), str(fixture_config_path), action],
            cwd=ROOT, capture_output=True, text=True,
        )
        prepared.append({'action': action, 'expectedStage': expected_stage, 'returncode': proc.returncode})
        if proc.returncode != 0:
            return _delivery_fixture_blocked(
                directory,
                f'Delivery fixture preparation stage {action} failed before browser mutations started',
                preparedActions=prepared,
            )

    if not state_file.is_file():
        return _delivery_fixture_blocked(directory, 'Delivery fixture preparation completed without fixture-state.json', preparedActions=prepared)
    final_state = json.loads(state_file.read_text())
    error = _validate_delivery_state(final_state, fixture_config)
    if error or final_state.get('stage') != 'members-ready':
        return _delivery_fixture_blocked(directory, error or f"Unexpected final delivery fixture stage: {final_state.get('stage')!r}", preparedActions=prepared)
    ready_error = _ready_manifest_error(private_root, fixture_config)
    if ready_error:
        return _delivery_fixture_blocked(directory, ready_error, preparedActions=prepared)

    save(directory / 'delivery-fixture-preflight.json', {
        'status': 'ready',
        'stage': 'members-ready',
        'preparedActions': prepared,
        'manifestDigest': 'sha256:' + hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
    })
    return True


def finish(owner, catalog, before, after, browser, directory, browser_exit, suite='standard'):
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
    report = owner.summarize(catalog, entries, suite)
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
    parser.add_argument('--suite', choices=['standard', 'abnormal'], default='standard',
                        help='execution suite to run: standard (positive default) or abnormal')
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
    if 'deliveryFixtureConfig' in config and (not isinstance(config['deliveryFixtureConfig'], str) or not config['deliveryFixtureConfig'].strip()):
        raise ValueError('deliveryFixtureConfig requires a non-empty private file path')
    catalog_path = Path(config.get('catalog', ROOT.parent / 'docs/acceptance/platform-catalog.json')).expanduser().resolve()
    owner = load_owner(catalog_path)
    catalog = json.loads(catalog_path.read_text())
    owner.validate_catalog(catalog)
    cases = config.get('cases')
    suite_ids = {c['id'] for c in catalog['cases'] if c['required'] and any(p['suite'] == args.suite for p in c['execution'])}
    if cases is not None and (not isinstance(cases, list) or not cases or any(not isinstance(c, str) or c not in suite_ids for c in cases) or len(cases) != len(set(cases))):
        raise ValueError(f'cases must be distinct required {args.suite} case IDs')
    command = ['node', str(ROOT / 'regression/standard.cjs'), '--catalog', str(catalog_path), '--suite', args.suite]
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
        return execute_live(config, catalog_path, owner, catalog, command, credentials, cases, suite=args.suite)


def cleanup_historical_runs(catalog_path, output_root, *, suite='standard', cases=None):
    """Clean previous local run artifacts under acceptance/runs before a full regression."""
    if cases is not None:
        return {'cleaned': False, 'reason': 'targeted-subset'}
    acceptance_dir = Path(catalog_path).parent
    runs_root = acceptance_dir / 'runs'
    if acceptance_dir.is_symlink() or runs_root.is_symlink() or (runs_root.exists() and not runs_root.is_dir()):
        raise ValueError(f'unsafe acceptance runs root: {runs_root}')
    runs_root_abs = Path(os.path.abspath(runs_root))
    output_abs = Path(os.path.abspath(Path(output_root).expanduser()))
    if output_abs != runs_root_abs and not output_abs.is_relative_to(runs_root_abs):
        return {'cleaned': False, 'reason': 'output-outside-runs-root'}
    probe = output_abs
    while probe != runs_root_abs:
        if probe.is_symlink():
            raise ValueError(f'unsafe symlinked regression output path: {probe}')
        probe = probe.parent
    preserved_names = {'.git', '.gitignore', '.gitattributes', '.gitkeep'}
    targets = []
    if runs_root_abs.exists():
        if suite == 'standard':
            for entry in sorted(runs_root_abs.iterdir()):
                if entry.name not in preserved_names:
                    targets.append(entry)
        else:
            rel_parts = output_abs.relative_to(runs_root_abs).parts if output_abs != runs_root_abs else ()
            if len(rel_parts) >= 2:
                current_round = runs_root_abs / rel_parts[0]
                for entry in sorted(runs_root_abs.iterdir()):
                    if entry != current_round and entry.name not in preserved_names:
                        targets.append(entry)
                if output_abs.is_dir():
                    for entry in sorted(output_abs.iterdir()):
                        if entry.name not in preserved_names:
                            targets.append(entry)
            elif len(rel_parts) == 1:
                standard_dir = runs_root_abs / 'standard'
                for entry in sorted(runs_root_abs.iterdir()):
                    if entry != standard_dir and entry != output_abs and entry.name not in preserved_names:
                        targets.append(entry)
                if output_abs.is_dir():
                    for entry in sorted(output_abs.iterdir()):
                        if entry.name not in preserved_names:
                            targets.append(entry)
            else:
                for entry in sorted(runs_root_abs.iterdir()):
                    if entry.name not in preserved_names:
                        targets.append(entry)
    removed_files = 0
    removed_bytes = 0
    for target in targets:
        entries = [target] if target.is_symlink() or target.is_file() else target.rglob('*')
        for entry in entries:
            if entry.is_file() and not entry.is_symlink():
                removed_files += 1
                removed_bytes += entry.stat().st_size
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    return {
        'cleaned': True,
        'suite': suite,
        'runsRoot': str(runs_root_abs),
        'removedEntries': len(targets),
        'removedFiles': removed_files,
        'removedBytes': removed_bytes,
    }


def execute_live(config, catalog_path, owner, catalog, command, credentials, cases, suite='standard'):
    history_cleanup = cleanup_historical_runs(catalog_path, config['output'], suite=suite, cases=cases)
    if history_cleanup.get('cleaned'):
        print(
            f"Historical runs cleaned under {history_cleanup['runsRoot']}: "
            f"{history_cleanup['removedEntries']} entries, {history_cleanup['removedFiles']} files",
            flush=True,
        )
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    directory = Path(config['output']).expanduser().resolve() / stamp
    directory.mkdir(parents=True, exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix=f'platform-{suite}-{stamp}-'))
    print('Evidence: ' + str(directory), flush=True)
    print('Private recovery state (retained outside repositories): ' + str(private), flush=True)
    inputs = tool_hashes()
    save(directory / 'inputs.json', {'suite': suite, 'selectedCases': cases or f'all required {suite} branches',
                                    'historyCleanup': history_cleanup,
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
    if config.get('deliveryFixtureConfig'):
        fixture_config_path = Path(config['deliveryFixtureConfig']).expanduser().resolve()
        if not ensure_delivery_fixture(fixture_config_path, directory):
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
    report = finish(owner, catalog, before, after, browser, directory, browser_exit, suite=suite)
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
