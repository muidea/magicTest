#!/usr/bin/env python3
"""Create a telemetry-only V3 acceptance plan offline; performs no API calls."""
from copy import deepcopy
from datetime import timedelta
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulator.common import digest, instant, require, utc


def build(deployment_id, run_id, anchor):
    require(re.fullmatch(r'[a-f0-9]{32}', deployment_id), 'exact new deployment ID required')
    require(re.fullmatch(r'[A-F0-9]{12}', run_id), 'new 12-character uppercase hex run ID required')
    root = Path(__file__).resolve().parents[1]
    bootstrap = json.loads((root / 'fixtures/threshold-v3/bootstrap.json').read_text())
    fixture = json.loads((root / 'fixtures/threshold-v3/cases.json').read_text())
    anchor = instant(anchor)
    shift = anchor - instant(fixture['liveSequence'][-1]['record']['sampledAt'])
    operations = []
    prefix = 'DM-' + run_id + '-'
    for entity in ('location', 'category', 'device'):
        for source in bootstrap[entity]:
            fields = deepcopy(source)
            code = fields['code']
            fields['code'] = prefix + code
            for key, relation in (('parentCode', 'parent'), ('categoryCode', 'category'), ('locationCode', 'location')):
                if key in fields:
                    ref = fields.pop(key)
                    fields[relation] = None if ref is None else {'$ref': ('location' if relation == 'parent' else relation) + ':' + ref}
            operations.append({'key': entity + ':' + code, 'entity': entity, 'operation': 'create', 'fields': fields})
    samples = []
    expected = []
    for case in fixture['liveSequence']:
        fields = deepcopy(case['record'])
        device = fields.pop('deviceCode')
        fields['device'] = {'$ref': 'device:' + device}
        fields['sampledAt'] = utc(instant(fields['sampledAt']) + shift)
        key = 'telemetry:' + case['key']
        samples.append({'key': key, 'entity': 'telemetry', 'operation': 'create', 'fields': fields})
        expected.append({'sourceKey': key, 'candidates': deepcopy(case['expected'])})
    result = {'schemaVersion': 'device-management.threshold-plan/v1',
              'status': 'offline-only-runtime-authorization-and-recovery-not-ready',
              'deploymentId': deployment_id, 'runId': run_id, 'anchor': utc(anchor),
              'window': {'from': utc(anchor - timedelta(hours=24)), 'to': utc(anchor)},
              'bootstrap': operations, 'telemetry': samples, 'expectedEffects': expected,
              'expectedCounts': deepcopy(fixture['expectedLive']),
              'forbiddenWrites': ['alarm', 'maintenance'], 'requiresNewIsolatedInstallation': True}
    result['digest'] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment-id', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--anchor', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = build(args.deployment_id, args.run_id, args.anchor)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(plan, output, ensure_ascii=False, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
