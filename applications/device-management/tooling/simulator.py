#!/usr/bin/env python3
"""API-key-only device simulator; run --help for bounded, restartable workflows."""
import argparse
import os
from pathlib import Path
import secrets
import sys

# Support `python3 -I ~/.../simulator.py` without importing from the caller's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulator.client import Gateway
from simulator.common import Failure, dumps, home_path, load, private_directory, require, write_json
from simulator.config import DEFAULT_URL, SCENARIOS, configure, validate
from simulator.journal import Journal
from simulator.plan import build, plan_digest
from simulator.runner import Runner


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest='mode', required=True)
    init = sub.add_parser('init', help='write a new non-secret config and offline plan; no network')
    init.add_argument('--api-key-file', required=True)
    init.add_argument('--run-dir', required=True)
    init.add_argument('--service-url', default=DEFAULT_URL)
    init.add_argument('--run-id', default=None)
    init.add_argument('--anchor', default=None)
    init.add_argument('--scenario', choices=SCENARIOS, default='live-stream-v1')
    init.add_argument('--ca-file', default='~/dataspace/magicPlatform/services/secret/tls/tls.crt')
    init.add_argument('--ca-is-root', action='store_true', help='use ordinary root CA verification instead of a configured leaf trust anchor')
    for mode in ('plan', 'probe', 'seed', 'bootstrap', 'backfill', 'collect', 'replay', 'live-stream', 'update', 'verify', 'run'):
        command = sub.add_parser(mode)
        command.add_argument('--config', required=True)
        if mode in ('collect', 'live-stream', 'run'):
            command.add_argument('--cycles', type=int, default=1, help='new cycles this invocation (bounded by maxCycles)')
        if mode == 'update':
            command.add_argument('--entity', choices=('location', 'category', 'device'), required=True)
            command.add_argument('--logical-code', required=True)
            command.add_argument('--changes', required=True, help='JSON file with fields and expectedFields')
    return result


def main(argv=None):
    os.umask(0o077)
    args = parser().parse_args(argv)
    if args.mode == 'init':
        directory = home_path(args.run_dir)
        require(not directory.exists(), 'run directory already exists; use its config to resume')
        config = configure(args.service_url, args.api_key_file, str(directory), args.run_id or secrets.token_hex(6).upper(),
                           args.anchor, args.scenario)
        config['tls'] = {'caFile': args.ca_file, 'trustLeaf': not args.ca_is_root}
        validate(config)
        plan = build(config)
        private_directory(directory)
        write_json(directory / 'config.json', config, exclusive=True)
        write_json(directory / 'plan.json', plan, exclusive=True)
        print(dumps({'status': 'planned', 'config': str(directory / 'config.json'), 'expected': plan['expected'],
                     'network': 'not-run', 'window': plan['window']}))
        return 0
    config = validate(load(home_path(args.config)))
    plan = build(config)
    directory = home_path(config['run']['journalDirectory'])
    require(directory.is_dir(), 'initialize a new run first')
    require(load(directory / 'plan.json') == plan, 'offline plan differs from current configuration')
    if args.mode == 'plan':
        print(dumps(plan))
        return 0
    if args.mode in ('backfill', 'collect', 'update', 'verify'):
        require((directory / 'journal.sqlite3').is_file(), 'bootstrap/probe journal missing')
    with Journal(directory, plan_digest(config, plan)) as journal:
        runner = None
        try:
            client = Gateway(config, journal)
            runner = Runner(config, plan, journal, client,
                            lambda phase, done, total: print(dumps({'phase': phase, 'done': done, 'total': total}), flush=True))
            totals = runner.preflight()
            if args.mode == 'probe':
                print(dumps({'status': 'reachable', 'serviceUrl': config['serviceUrl'], 'totals': totals,
                             'auth': 'ApiKey only', 'businessWrites': False}))
            elif args.mode in ('seed', 'bootstrap'):
                runner.phase('bootstrap')
            elif args.mode == 'backfill':
                runner.phase('backfill')
            elif args.mode == 'collect':
                runner.collect(args.cycles)
            elif args.mode == 'replay':
                print(dumps(runner.replay_checks()))
            elif args.mode == 'update':
                changes = load(home_path(args.changes), limit=65536)
                runner.update(args.entity, args.logical_code, changes.get('fields'), changes.get('expectedFields'))
            elif args.mode == 'verify':
                print(dumps(runner.verify()))
            elif args.mode in ('live-stream', 'run'):
                runner.phase('bootstrap')
                runner.phase('backfill')
                runner.collect(args.cycles)
                print(dumps(runner.verify()))
            print(dumps(journal.summary()))
        finally:
            if runner:
                runner.export()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Stopped. Prepared/unknown requests remain in the journal; rerun the original phase to reconcile.', file=sys.stderr)
        sys.exit(130)
    except Failure as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, KeyError, TypeError, ValueError):
        print('Local configuration/file/transport failure; no credential or server body was printed.', file=sys.stderr)
        sys.exit(1)
