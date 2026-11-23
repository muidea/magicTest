#!/usr/bin/env python3
"""Dual simulated-application offline preflight and live E2E orchestrator."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

LIVE_E2E_DIR = Path(__file__).resolve().parent
APPLICATIONS_ROOT = LIVE_E2E_DIR.parent
MAGIC_TEST_ROOT = APPLICATIONS_ROOT.parent
if str(APPLICATIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(APPLICATIONS_ROOT))

from platform_paths import resolve_app_model_root, resolve_platform_root

ALL_APPS = ('device-management', 'chess-room-booking')


def verify_package_bundle(model_root: Path) -> dict:
    """Verify authoritative package.zip exists and matches its SHA256SUMS."""
    package_dir = model_root / 'package'
    zip_path = package_dir / 'package.zip'
    sums_path = package_dir / 'SHA256SUMS'
    if not zip_path.is_file() or not sums_path.is_file():
        raise FileNotFoundError(f'missing package bundle or SHA256SUMS under {package_dir}')
    lines = [line.strip() for line in sums_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    expected = None
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and Path(parts[-1]).name == 'package.zip':
            expected = parts[0].lower()
            break
    if not expected:
        raise ValueError(f'SHA256SUMS missing package.zip entry: {sums_path}')
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest().lower()
    if actual != expected:
        raise ValueError(f'package.zip SHA-256 mismatch under {package_dir}: expected {expected}, got {actual}')
    return {
        'packageDir': str(package_dir),
        'packageSha256': actual,
        'sizeBytes': zip_path.stat().st_size,
    }


def _preflight_device_management(model_root: Path) -> dict:
    tooling_dir = APPLICATIONS_ROOT / 'device-management/tooling'
    app_root = APPLICATIONS_ROOT / 'device-management'
    if str(tooling_dir) not in sys.path:
        sys.path.insert(0, str(tooling_dir))
    import validate_threshold_candidate as dm_validator
    from simulator.config import configure
    from simulator.plan import build as build_sim_plan

    bundle = verify_package_bundle(model_root)
    facts = dm_validator.validate(model_root, app_root)
    replay_cfg = configure(
        'https://panel.local.vpc/api/v1/gateway/services/device_management_service',
        '~/nonexistent-dry-run-key',
        '~/nonexistent-dry-run-dir',
        'AABBCCDDEEFF',
        scenario='replay-v3',
    )
    replay_plan = build_sim_plan(replay_cfg)
    return {
        'app': 'device-management',
        'bundle': bundle,
        'definitionChecks': facts,
        'replayPlan': {
            'scenario': replay_plan['scenario'],
            'bootstrapSteps': len(replay_plan['bootstrap']),
            'backfillSteps': len(replay_plan['backfill']),
        },
        'status': 'offline-preflight-passed',
    }


def _preflight_chess_room_booking(model_root: Path) -> dict:
    tooling_dir = APPLICATIONS_ROOT / 'chess-room-booking/tooling'
    if str(tooling_dir) not in sys.path:
        sys.path.insert(0, str(tooling_dir))
    import admission_contract as crb_admission
    import fixture_tool as crb_fixture
    import package_tool as crb_package

    bundle = verify_package_bundle(model_root)
    profile = crb_package.validate_source(model_root)
    baseline = crb_fixture.create('2026-11-01T00:00:00Z')
    baseline_result = crb_fixture.validate(baseline, model_root)
    entities = [
        crb_package.read_json(p)
        for p in sorted((model_root / 'definition/application/entities').glob('*.json'))
    ]
    replay_plan = crb_fixture.simulation_plan('2026-11-01T00:00:00Z', 'dryrun-replay', mode='replay')
    plan_check = crb_admission.validate_plan(replay_plan, entities)
    return {
        'app': 'chess-room-booking',
        'bundle': bundle,
        'profileRevision': profile['modelRevision'],
        'baselineRecords': baseline_result['totalRecords'],
        'planCheck': plan_check,
        'status': 'offline-preflight-passed',
    }


def run_dry_run(platform_root: Path, apps: list[str]) -> dict:
    results = {}
    for app in apps:
        model_root = resolve_app_model_root(app, platform_root)
        if app == 'device-management':
            results[app] = _preflight_device_management(model_root)
        elif app == 'chess-room-booking':
            results[app] = _preflight_chess_room_booking(model_root)
        else:
            raise ValueError(f'unsupported app: {app}')
    return {
        'schemaVersion': 'magic.dual-apps-e2e/v1',
        'mode': 'dry-run',
        'executedAtUtc': datetime.now(timezone.utc).isoformat(),
        'platformRoot': str(platform_root),
        'apps': results,
        'liveExecuted': False,
        'passed': True,
    }


def _run_subprocess(cmd: list[str], cwd: Path) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return {
        'command': cmd,
        'returncode': proc.returncode,
        'stdoutTail': proc.stdout.splitlines()[-20:],
        'stderrTail': proc.stderr.splitlines()[-20:],
    }


def run_live(args: argparse.Namespace, platform_root: Path, apps: list[str]) -> dict:
    preflight = run_dry_run(platform_root, apps)
    live_results = {}
    overall_passed = True

    if 'device-management' in apps:
        if not args.dm_config:
            raise ValueError('--dm-config is required for live device-management verification')
        dm_sim = APPLICATIONS_ROOT / 'device-management/tooling/simulator.py'
        mode_cmd = [sys.executable, '-I', str(dm_sim), args.dm_command, '--config', str(args.dm_config)]
        if args.dm_command in ('collect', 'live-stream', 'run'):
            mode_cmd.extend(['--cycles', str(args.cycles)])
        res = _run_subprocess(mode_cmd, MAGIC_TEST_ROOT)
        verify_res = None
        if res['returncode'] == 0 and args.dm_command != 'verify':
            verify_res = _run_subprocess(
                [sys.executable, '-I', str(dm_sim), 'verify', '--config', str(args.dm_config)],
                MAGIC_TEST_ROOT,
            )
        passed = res['returncode'] == 0 and (verify_res is None or verify_res['returncode'] == 0)
        overall_passed = overall_passed and passed
        live_results['device-management'] = {
            'primary': res,
            'verify': verify_res,
            'passed': passed,
        }

    if 'chess-room-booking' in apps:
        if not (args.crb_state_dir and args.crb_api_key_file and args.crb_action_token_file):
            raise ValueError(
                '--crb-state-dir, --crb-api-key-file, and --crb-action-token-file are required '
                'for live chess-room-booking verification'
            )
        crb_sim = APPLICATIONS_ROOT / 'chess-room-booking/tooling/simulation_tool.py'
        common_flags = [
            '--mode', args.crb_mode,
            '--cycles', str(args.cycles),
            '--service-url', args.crb_gateway_url,
            '--action-url', args.crb_action_url,
            '--state-dir', str(args.crb_state_dir),
            '--api-key-file', str(args.crb_api_key_file),
            '--action-token-file', str(args.crb_action_token_file),
        ]
        if args.crb_anchor_utc:
            common_flags.extend(['--anchor-utc', args.crb_anchor_utc])
        if args.crb_run_id:
            common_flags.extend(['--run-id', args.crb_run_id])
        if args.ca_file:
            common_flags.extend(['--ca-file', str(args.ca_file)])
        if args.trust_leaf:
            common_flags.append('--trust-leaf')
        run_res = _run_subprocess([sys.executable, '-I', str(crb_sim), 'run', *common_flags], MAGIC_TEST_ROOT)
        verify_res = None
        if run_res['returncode'] == 0:
            verify_res = _run_subprocess(
                [sys.executable, '-I', str(crb_sim), 'verify', '--wait-seconds', str(args.crb_wait_seconds), *common_flags],
                MAGIC_TEST_ROOT,
            )
        passed = run_res['returncode'] == 0 and (verify_res is None or verify_res['returncode'] == 0)
        overall_passed = overall_passed and passed
        live_results['chess-room-booking'] = {
            'run': run_res,
            'verify': verify_res,
            'passed': passed,
        }

    return {
        'schemaVersion': 'magic.dual-apps-e2e/v1',
        'mode': 'live',
        'executedAtUtc': datetime.now(timezone.utc).isoformat(),
        'platformRoot': str(platform_root),
        'preflight': preflight['apps'],
        'live': live_results,
        'liveExecuted': True,
        'passed': overall_passed,
    }


def _parse_apps(raw: str) -> list[str]:
    selected = [item.strip() for item in raw.split(',') if item.strip()]
    if not selected:
        raise ValueError('at least one application must be specified')
    unknown = [item for item in selected if item not in ALL_APPS]
    if unknown:
        raise ValueError(f'unsupported apps: {", ".join(unknown)}')
    return selected


def default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')
    return MAGIC_TEST_ROOT / 'reports/applications' / f'{stamp}-dual-e2e'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform-root', type=Path, help='path to magicPlatform checkout')
    parser.add_argument('--output-dir', type=Path, help='directory for E2E summary report (never overwrites existing summary)')
    parser.add_argument('--apps', default=','.join(ALL_APPS), help='comma-separated list from device-management,chess-room-booking')
    parser.add_argument('--dry-run', action='store_true', help='run offline model/package/fixture preflight without live calls')
    parser.add_argument('--cycles', type=int, default=4, help='simulation cycles for live-stream runs')
    parser.add_argument('--dm-config', type=Path, help='device-management simulator config.json for live run')
    parser.add_argument('--dm-command', choices=('replay', 'live-stream', 'run', 'verify'), default='replay')
    parser.add_argument('--crb-mode', choices=('seed', 'replay', 'live-stream'), default='replay')
    parser.add_argument('--crb-gateway-url', default='https://panel.local.vpc/api/v1/gateway/services/chess_room_booking_simulation')
    parser.add_argument('--crb-action-url', default='https://panel.local.vpc/api/v1/apps/entity/action/execute/')
    parser.add_argument('--crb-state-dir', type=Path, help='chess-room-booking simulator state directory')
    parser.add_argument('--crb-api-key-file', type=Path, help='chess-room-booking Gateway API key file (0600)')
    parser.add_argument('--crb-action-token-file', type=Path, help='chess-room-booking Apps Bearer token file (0600)')
    parser.add_argument('--crb-anchor-utc', default=None)
    parser.add_argument('--crb-run-id', default=None)
    parser.add_argument('--crb-wait-seconds', type=int, default=60)
    parser.add_argument('--ca-file', type=Path, help='TLS CA / leaf certificate file')
    parser.add_argument('--trust-leaf', action='store_true')
    args = parser.parse_args(argv)

    apps = _parse_apps(args.apps)
    platform_root = resolve_platform_root(args.platform_root)
    out_dir = (args.output_dir or default_output_dir()).expanduser().resolve()
    summary_path = out_dir / 'e2e-summary.json'
    if summary_path.exists():
        raise FileExistsError(f'refusing to overwrite existing report: {summary_path}')

    if args.dry_run:
        report = run_dry_run(platform_root, apps)
    else:
        report = run_live(args, platform_root, apps)

    out_dir.mkdir(parents=True, exist_ok=True)
    with summary_path.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
