#!/usr/bin/env python3
"""Validate closeout tasks and isolated fixtures without executing business mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

STATES = {'open', 'root-cause-confirmed', 'regression-passed', 'live-pending', 'live-passed', 'closed'}
ACTIONS = {'read', 'activate', 'disable', 'uninstall', 'cancel', 'delete-package'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_tasks(data):
    require(data.get('schema') == 'magic.closeout/v1', 'invalid closeout schema')
    tasks = data.get('tasks', [])
    require(isinstance(tasks, list) and {t.get('id') for t in tasks} == {f'C{i:02}' for i in range(1, 10)} and len(tasks) == 9,
            'all C01-C09 tasks must remain tracked exactly once')
    for task in tasks:
        require(task.get('state') in STATES and task.get('owner') and task.get('summary'), 'missing task state or owner')
        require(type(task.get('codeRequired')) is bool, 'codeRequired must be explicit')
        require(isinstance(task.get('remaining'), list), 'remaining work must be explicit')
        if task['state'] in {'regression-passed', 'live-pending', 'live-passed', 'closed'} and task['codeRequired']:
            require(task.get('regressionEvidence'), task['id'] + ' requires regression evidence')
        if task['state'] in {'live-passed', 'closed'}:
            proof = task.get('liveEvidence', {})
            require(proof.get('passed') is True and re.fullmatch(r'sha256:[a-f0-9]{64}', proof.get('environmentFingerprint', ''))
                    and proof.get('path'), task['id'] + ' requires live evidence bound to a deployed version')
        if task['state'] == 'closed':
            require(not task['remaining'] and task.get('rootCause') and task.get('resolution'), 'closed task lacks full resolution')
    return {'readyForLive': all(not t['codeRequired'] or t['state'] in {'regression-passed', 'live-pending', 'live-passed', 'closed'} for t in tasks),
            'complete': all(t['state'] == 'closed' for t in tasks),
            'openTasks': [t['id'] for t in tasks if t['state'] != 'closed']}


def verify_task_evidence(data, directory):
    """The CLI verifies actual evidence bytes, not merely a claimed filename."""
    directory = Path(directory).resolve()
    for task in data['tasks']:
        keys = []
        if task['codeRequired'] and task['state'] in {'regression-passed', 'live-pending', 'live-passed', 'closed'}:
            keys.append('regressionEvidence')
        if task['state'] in {'live-passed', 'closed'}:
            keys.append('liveEvidence')
        for key in keys:
            proof = task.get(key)
            require(isinstance(proof, dict) and proof.get('path'), 'evidence must include a path and content hash')
            target = (directory / proof['path']).resolve()
            require(target.is_relative_to(directory) and target.is_file(), 'evidence is outside the ledger directory or missing')
            digest = 'sha256:' + hashlib.sha256(target.read_bytes()).hexdigest()
            require(proof.get('digest') == digest, 'evidence content changed: ' + task['id'])
            evidence = json.loads(target.read_text())
            require(evidence.get('passed') is True, 'evidence does not confirm a passed run')
            if key == 'liveEvidence':
                require(evidence.get('environmentFingerprint') == proof['environmentFingerprint'], 'live evidence version mismatch')


def validate_fixtures(data):
    require(data.get('schema') == 'magic.acceptance.fixtures/v1', 'invalid fixture schema')
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', data.get('environmentFingerprint', '')), 'fixture needs immutable environment')
    fixtures = data.get('fixtures', [])
    require(isinstance(fixtures, list), 'fixtures must be an array')
    installations, deployments = set(), set()
    for fixture in fixtures:
        namespace = fixture.get('namespace', '')
        require(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', namespace), 'invalid fixture namespace')
        require(fixture.get('purpose') == 'acceptance' and fixture.get('applicationName', '').startswith('accept-'), 'only isolated acceptance applications may be mutated')
        require(type(fixture.get('installationId')) is int and fixture['installationId'] > 0, 'invalid installation ID')
        require(type(fixture.get('expectedVersion')) is int and fixture['expectedVersion'] > 0, 'fixture needs current version')
        require(re.fullmatch(r'[a-f0-9]{32}', fixture.get('deploymentId', '')), 'invalid deployment identity')
        require(re.fullmatch(r'[a-f0-9]{32}', fixture.get('applicationUuid', '')), 'invalid application identity')
        require(re.fullmatch(r'sha256:[a-f0-9]{64}', fixture.get('sourceDigest', '')), 'missing frozen artifact identity')
        ik, dk = (namespace, fixture['installationId']), (namespace, fixture['deploymentId'])
        require(ik not in installations and dk not in deployments, 'parallel scenarios must not share one installation')
        installations.add(ik)
        deployments.add(dk)
        actions = fixture.get('allowedActions', [])
        require(isinstance(actions, list) and bool(actions) and set(actions) <= ACTIONS, 'invalid allowed actions')
        require(fixture.get('status') not in {'uninstalled', 'deleted', 'cancelled'}, 'do not reuse cleaned fixtures')
        require(bool(fixture.get('cleanup')), 'fixture cleanup plan is required')
    return [dict(fixture, environmentFingerprint=data['environmentFingerprint']) for fixture in fixtures]


def require_current_fixture(fixture, current, action, fingerprint):
    """Call after reading the owner API, immediately before a versioned mutation."""
    require(action in fixture['allowedActions'], 'action was not included in fixture scope')
    require(fingerprint == fixture['environmentFingerprint'], 'deployment changed; regenerate fixture proof')
    for key in ('namespace', 'installationId', 'deploymentId', 'applicationUuid', 'sourceDigest', 'expectedVersion', 'status'):
        require(current.get(key) == fixture.get(key), 'fixture current binding mismatch: ' + key)
    require(current.get('status') not in {'uninstalled', 'deleted', 'cancelled'}, 'fixture is already cleaned')


def summarize_steps(required, attempts, fingerprint):
    """Keep the first failed attempt; a later pass cannot erase its cause."""
    require(required and len(required) == len(set(required)), 'required steps must be unique')
    require(isinstance(attempts, list), 'attempts must be an array')
    failures, current = [], {}
    keys = set()
    for attempt in attempts:
        key = (attempt.get('step'), attempt.get('attempt'), attempt.get('environmentFingerprint'))
        require(key not in keys and type(attempt.get('attempt')) is int and attempt['attempt'] > 0, 'duplicate or invalid attempt')
        keys.add(key)
        require(attempt.get('step') in required and attempt.get('status') in {'passed', 'failed', 'blocked'}, 'invalid attempt step')
        if attempt['status'] != 'passed':
            failures.append(attempt)
        if attempt.get('environmentFingerprint') == fingerprint:
            before = current.get(attempt['step'])
            if before is None or before['attempt'] < attempt['attempt']:
                current[attempt['step']] = attempt
    missing = [step for step in required if current.get(step, {}).get('status') != 'passed']
    unresolved = [entry for entry in failures if entry.get('environmentFingerprint') == fingerprint and not entry.get('resolutionEvidence')]
    return {'passed': not missing and not unresolved, 'incompleteSteps': missing,
            'firstFailure': failures[0] if failures else None, 'unresolvedFailures': len(unresolved)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['tasks', 'fixtures'])
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    data = json.loads(args.file.read_text())
    if args.kind == 'tasks':
        result = validate_tasks(data)
        verify_task_evidence(data, args.file.parent)
    else:
        result = {'fixtures': len(validate_fixtures(data))}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as error:
        print('Closeout validation rejected: ' + str(error), file=sys.stderr)
        sys.exit(1)
