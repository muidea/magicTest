#!/usr/bin/env python3
"""Validate the threshold draft offline; never publish a package or contact Live."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from export_candidate import validate_design
from platform_paths import resolve_app_model_root, resolve_workspace_root


def validate(definition_root, fixture_root=None):
    definition_root = Path(definition_root)
    fixture_root = Path(fixture_root or definition_root)
    validate_design(definition_root)
    read = lambda name: json.loads((definition_root / name).read_text())
    read_fixture = lambda name: json.loads((fixture_root / name).read_text())
    artifact = read('definition/candidate.artifact.json')
    plan = read('definition/threshold-execution.design.json')
    fixture = read_fixture('fixtures/threshold-v3/cases.json')
    bootstrap = read_fixture('fixtures/threshold-v3/bootstrap.json')
    if artifact['version'] != 3 or artifact['artifactDigest']:
        raise ValueError('draft sequence must be 3 with no fabricated release digest')
    if artifact['application']['version'] != plan['businessVersion'] or any(
            e['version'] != plan['businessVersion'] for e in artifact['entities']):
        raise ValueError('business versions disagree')
    if plan['liveReady'] or plan['status'] != 'design-only-not-runtime-manifest':
        raise ValueError('effect design must not claim runtime availability')
    if plan['input']['rules'] != fixture['rules']:
        raise ValueError('script design and verification rules disagree')
    binding = read('definition/threshold-effect.binding.design.json')
    trigger = binding['stageInfo']['functions']['insert']
    if (binding['scriptKey'] != plan['scriptKey'] or trigger['input'] != plan['input'] | {'record': '$referenceValue'}
            or trigger['createEffect']['targetEntity'] != plan['targetEntity']
            or trigger['createEffect']['maxRecords'] != plan['maxDerivedRecords']):
        raise ValueError('effect binding design and execution design disagree')
    block = read('definition/blocks/telemetry-threshold/definition.json')
    inputs = {parameter['name']: parameter for parameter in block['inputs']}
    sample = next(case for case in fixture['liveSequence'] if case['key'] == 'multi-high')
    if inputs['record'].get('example') != sample['record'] or inputs['rules'].get('example') != fixture['rules']:
        raise ValueError('debug examples must match the frozen multi-high fixture and rules')
    if any('default' in parameter for parameter in block['inputs'] + block['outputs']):
        raise ValueError('debug examples must not become execution defaults')
    entities = {e['name']: e for e in artifact['entities']}
    if entities['telemetry'].get('blockInfo') != [binding] or any(
            e.get('blockInfo') for name, e in entities.items() if name != 'telemetry'):
        raise ValueError('candidate must contain exactly the reviewed telemetry effect binding')
    if entities['telemetry']['uniqueConstraints'] != [
        {'name': 'uq_dm_telemetry_device_sampled', 'fields': ['device', 'sampledAt']}]:
        raise ValueError('sample identity must have a declared unique constraint')
    if any(c['key'] == 'create' and c['enabled'] for c in entities['alarm']['serviceExpose']['capabilities']):
        raise ValueError('new scenario must not expose alarm creation')
    for name, entity in entities.items():
        caps = {c['key']: bool(c.get('enabled')) for c in entity['serviceExpose']['capabilities']}
        if name in ('location', 'category', 'device'):
            expected_caps = dict(query=True, get=True, create=True, update=True, delete=True)
        elif name in ('telemetry', 'maintenance'):
            expected_caps = dict(query=True, get=True, create=True, update=False, delete=False)
        else:
            expected_caps = dict(query=True, get=True, create=False, update=False, delete=False)
        if not entity['serviceExpose']['enabled'] or caps != expected_caps:
            raise ValueError(f'unexpected serviceExpose matrix for {name}: {caps}')
    capabilities = sum(bool(op.get('enabled')) for e in entities.values()
                       for op in e['serviceExpose']['capabilities'] if e['serviceExpose']['enabled'])
    if capabilities != 23:
        raise ValueError(f'expected 23 standard exposed operations, got {capabilities}')
    if len(fixture['liveSequence']) != 10 or sum(len(c['expected']) for c in fixture['liveSequence']) != 9:
        raise ValueError('fixture must retain 10 samples and 9 derived alarms')
    if any(len(bootstrap[key]) != fixture['expectedLive'][key] for key in ('location', 'category', 'device', 'maintenance')) or bootstrap['alarm']:
        raise ValueError('bootstrap must have 3/1/1/0 records and no injected alarms')
    return {'entities': len(entities), 'fields': sum(len(e['fields']) for e in entities.values()),
            'standardExposedOperations': capabilities, 'activeBindings': 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-root', type=Path, help='authoritative device-management model root')
    parser.add_argument('--report', type=Path, help='write offline evidence; default prints JSON only')
    parser.add_argument('--output-dir', type=Path, help='retain a new standard ZIP and unpacked candidate; never overwrites')
    args = parser.parse_args()
    if args.output_dir and (args.output_dir.expanduser().exists() or args.output_dir.expanduser().is_symlink()):
        parser.error('output already exists; choose a new --output-dir')
    app_root = Path(__file__).resolve().parents[1]
    model_root = args.model_root.expanduser().resolve() if args.model_root else resolve_app_model_root('device-management')
    workspace = resolve_workspace_root()
    facts = validate(model_root, app_root)
    runner = workspace / 'magicRunner'
    codec = runner / 'internal/modules/kernel/panel/pkg/modelpackage'
    template = Path(__file__).with_suffix('.go.txt')
    with tempfile.TemporaryDirectory(prefix='device-threshold-check-') as temp:
        report_path = Path(temp) / 'result.json'
        # Go's overlay adds this test only to this command's view of the
        # package. Never create/delete a test in the shared Runner worktree:
        # another build may enumerate it just before our cleanup.
        test_file = Path(temp) / 'candidate_test.go'
        test_file.write_bytes(template.read_bytes())
        virtual_file = codec / f'zz_{Path(temp).name.replace("-", "_")}_test.go'
        if virtual_file.exists():
            raise ValueError('overlay test path already exists')
        overlay_path = Path(temp) / 'overlay.json'
        overlay_path.write_text(json.dumps({'Replace': {str(virtual_file): str(test_file)}}))
        env = dict(os.environ, GOWORK='off', DEVICE_THRESHOLD_ROOT=str(model_root),
                   DEVICE_THRESHOLD_FIXTURE_ROOT=str(app_root),
                   DEVICE_THRESHOLD_REPORT=str(report_path), DEVICE_THRESHOLD_OUTPUT=str(Path(temp) / "bundle") if args.output_dir else "")
        subprocess.run(['go', 'test', '-overlay', str(overlay_path),
                        './internal/modules/kernel/panel/pkg/modelpackage',
                        '-run', '^TestDeviceThresholdCandidate$', '-count=1', '-v'],
                       cwd=runner, env=env, check=True, timeout=180)
        report = json.loads(report_path.read_text())
        if args.output_dir:
            destination = args.output_dir.expanduser().absolute()
            destination.parent.mkdir(parents=True, exist_ok=True)
            # mkdir reserves the destination; an existing delivery is immutable.
            destination.mkdir()
            for source in (Path(temp) / 'bundle').rglob('*'):
                if source.is_file():
                    target = destination / source.relative_to(Path(temp) / 'bundle')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as stream:
                        stream.write(source.read_bytes())
    report.update(facts)
    source_sha256 = {
        str(p.relative_to(model_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((model_root / 'definition').rglob('*')) if p.is_file()
    }
    for p in sorted((app_root / 'fixtures/threshold-v3').glob('*.json')) + [Path(__file__).resolve(), template, app_root / 'tooling/export_candidate.py']:
        if p.is_file():
            source_sha256[str(p.relative_to(app_root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    report['sourceSHA256'] = source_sha256
    report['sourceCommits'] = {name: subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                             cwd=workspace / name, text=True).strip()
                             for name in ('magicRunner', 'magicBase', 'magicOrm')}
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        if args.report.exists():
            parser.error('report already exists; choose a new evidence path or remove your own temporary report')
        with args.report.open('x') as handle:
            handle.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
