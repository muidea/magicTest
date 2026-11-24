#!/usr/bin/env python3
"""Build/check local definitions using the official Runner codec; no HTTP or Live writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_app_model_root, resolve_workspace_root

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = resolve_app_model_root('chess-room-booking')
WORKSPACE = resolve_workspace_root()

ACTION_KEY_RE = re.compile(r'^[a-z][a-z0-9-]{0,63}$')
EXPECTED_ACTIONS = {
    'merchant': ['approve', 'reject', 'suspend', 'resume'],
    'room': ['enter-maintenance', 'finish-maintenance', 'suspend', 'resume'],
    'bookingOrder': ['confirm', 'reject', 'expire', 'check-in', 'complete', 'mark-no-show', 'cancel-by-customer', 'cancel-by-merchant'],
    'complaint': ['start-processing', 'resolve', 'close'],
}
EXPECTED_TEMPLATES = {'analyst', 'frontdesk', 'store-manager', 'platform-ops', 'channel-ingestor'}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key {key}: {path}')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def validate_source(root=MODEL_ROOT):
    base = root / 'definition/application'
    for path in (root / 'definition').rglob('*'):
        if path.is_symlink():
            raise ValueError(f'symlinks are not definition sources: {path}')
        if path.is_file() and path.suffix == '.json':
            read_json(path)
    profile = read_json(root / 'definition/profile.json')
    app = read_json(base / 'metadata.json')
    catalog = str(app.get('catalog', '')).strip()
    if not catalog or catalog.lower() == 'inner':
        raise ValueError('application catalog must be non-empty and not inner')
    pages = read_json(base / 'pages/definition.json')
    blocks = read_json(base / 'blocks/index.json')
    identity = (app['name'], app['uuid'], profile['modelRevision'])
    if identity != (profile['key'], profile['uuid'], pages['modelRevision']):
        raise ValueError('model profile identity mismatch')
    for doc in (pages, blocks):
        if identity != (doc['applicationKey'], doc['applicationUuid'], doc['modelRevision']):
            raise ValueError('page/block identity mismatch')
    if app['version'] != profile['version'] or profile['businessReady']:
        raise ValueError('validation profile/version mismatch')
    entities = [read_json(p) for p in sorted((base / 'entities').glob('*.json'))]
    expected = {'merchant', 'store', 'room', 'bookingRule', 'openingException', 'customerProfile',
                'staffAssignment', 'bookingOrder', 'roomOccupancy', 'orderEvent', 'complaint', 'complaintEntry', 'bookingSample'}
    if {e['name'] for e in entities} != expected or len(entities) != len(expected):
        raise ValueError('expected 12 display entities and one sampling source')
    if sum(len(e['fields']) for e in entities) != 186:
        raise ValueError('expected 186 fields')
    expected_members = {'metadata.json', 'pages/definition.json', 'blocks/index.json'}
    expected_members.update(f'entities/{name}.json' for name in expected)
    refs = {item['key']: item['definition'] for item in blocks['definitions']}
    if len(blocks['definitions']) != 2 or refs != {
            'bookingSample.occupancy': 'sample-occupancy/definition.json',
            'bookingSample.event': 'sample-event/definition.json'}:
        raise ValueError('expected two explicit sampling blocks')
    for key, name in refs.items():
        block = read_json(base / 'blocks' / name)
        directory = name.split('/')[0]
        if block['key'] != key or set(block['sourceFiles']) != {directory + '/main.go', directory + '/validation.go'}:
            raise ValueError('block source closure mismatch')
        expected_members.add('blocks/' + name)
        expected_members.update('blocks/' + member for member in block['sourceFiles'])
    actual_members = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
    if actual_members != expected_members:
        raise ValueError('unindexed/missing definition members')

    # Assets validation (4 appearance images copied under definition/assets/)
    assets_dir = root / 'definition/assets'
    assets_index_path = assets_dir / 'index.json'
    if not assets_index_path.is_file():
        raise ValueError('missing definition/assets/index.json')
    assets_index = read_json(assets_index_path)
    if assets_index.get('schemaVersion') != 'magic.application-assets/v1' or len(assets_index.get('files', [])) != 4:
        raise ValueError('expected 4 appearance assets in definition/assets/index.json')
    for item in assets_index['files']:
        asset_file = root / 'definition' / item['path']
        if not asset_file.is_file():
            raise ValueError('missing asset file: ' + item['path'])
        raw_bytes = asset_file.read_bytes()
        if len(raw_bytes) != item['size'] or 'sha256:' + hashlib.sha256(raw_bytes).hexdigest() != item['digest']:
            raise ValueError('asset digest/size mismatch: ' + item['path'])

    enabled = 0
    # bookingOrder has appendOnly=False so state actions work while Gateway/serviceExpose keeps update=False/delete=False.
    mutable_update = {'merchant', 'store', 'room', 'openingException', 'customerProfile', 'staffAssignment', 'complaint'}
    action_or_update = mutable_update | {'bookingOrder'}
    mutable_delete = {'openingException', 'staffAssignment'}
    declared_action_pairs = []
    for e in entities:
        if e['version'] != app['version'] or e['pkgPath'] != '/' + app['pkgPrefix']:
            raise ValueError('entity namespace/version mismatch')
        rules = e.get('writeRules', {})
        expected_append_only = e['name'] not in action_or_update
        if rules.get('apiVersion') != 'magic.entity-write-rules/v1' or bool(rules.get('appendOnly')) != expected_append_only or rules.get('versionField') != 'version':
            raise ValueError('entity writeRules appendOnly/versionField mismatch: ' + e['name'])
        capabilities = {c['key']: c['enabled'] for c in e['serviceExpose']['capabilities']}
        create = e['name'] not in {'roomOccupancy', 'orderEvent'}
        update = e['name'] in mutable_update
        delete = e['name'] in mutable_delete
        if not e['serviceExpose']['enabled'] or capabilities != dict(query=True, get=True, create=create, update=update, delete=delete):
            raise ValueError('service capability/gated create mismatch: ' + e['name'])
        enabled += sum(capabilities.values())
        if e['name'] != 'bookingSample' and e.get('blockInfo'):
            raise ValueError('only sampling source may trigger blocks')
        if e['name'] in {'bookingSample', 'roomOccupancy', 'orderEvent'}:
            if 'sampleKey' not in rules.get('immutable', []) or 'sampleKey' not in rules.get('nonBlank', []) or not any(u['fields'] == ['sampleKey'] for u in e['uniqueConstraints']):
                raise ValueError('sample identity must be immutable, nonblank and unique')
        actions = rules.get('actions', [])
        if e['name'] in EXPECTED_ACTIONS:
            keys = [a['key'] for a in actions]
            if keys != EXPECTED_ACTIONS[e['name']] or any(not ACTION_KEY_RE.fullmatch(k) for k in keys):
                raise ValueError('entity actions mismatch: ' + e['name'])
            if not rules.get('state') or not rules['state'].get('transitions'):
                raise ValueError('state machine required for actions: ' + e['name'])
            for k in keys:
                declared_action_pairs.append((f'/{app["pkgPrefix"]}/{e["name"]}', k))
        elif actions:
            raise ValueError('unexpected actions on entity: ' + e['name'])

    # CAS metadata authorization validation
    auth = app.get('authorization', {})
    expected_sorted_actions = [
        {'entity': ent, 'action': act}
        for ent, act in sorted(declared_action_pairs, key=lambda pair: f'/apps/entity-actions{pair[0]}/{pair[1]}')
    ]
    if auth.get('entityActions') != expected_sorted_actions or len(expected_sorted_actions) != 19:
        raise ValueError('metadata authorization.entityActions must match sorted 19 model actions')
    templates = auth.get('templates', [])
    if {t['key'] for t in templates} != EXPECTED_TEMPLATES:
        raise ValueError('metadata authorization.templates must match 5 workbench templates')
    for template in templates:
        roles = set(template.get('roleKeys', []))
        if template.get('subjectType') == 'account':
            if 'application-viewer' not in roles:
                raise ValueError(f"account template {template.get('key')} must include application-viewer")
            if 'application-data-read' in roles:
                raise ValueError(f"account template {template.get('key')} must use application-viewer instead of application-data-read")

    from admission_contract import validate_contract
    validate_contract(entities)
    staff = next(e for e in entities if e['name'] == 'staffAssignment')
    stores = next(f for f in staff['fields'] if f['name'] == 'storeIds')
    if not stores['type']['elemType'] or 'req' not in stores['spec']['constraint'].split(','):
        raise ValueError('staff required multi-reference contract must be preserved')
    readiness = read_json(root / 'definition/readiness.json')
    if enabled != 46 or readiness['enabledCapabilities'] != enabled or readiness['plannedCapabilities'] != 46 or readiness['liveReady'] or readiness['businessReady'] or readiness['gatedCreates'] != {}:
        raise ValueError('capability readiness mismatch')

    # Interactive page tree & capabilities validation
    if pages.get('navigationMode') != 'tree' or len(pages.get('navigation', [])) != 5:
        raise ValueError('pages must declare navigationMode=tree with 5 groups')
    if not pages.get('actions'):
        raise ValueError('interactive workbench must declare page actions')
    for pg in pages['pages']:
        if any(marker in pg.get('title', '') for marker in ('（验证）', '布局核对', '边界')):
            raise ValueError('internal verification wording remains in page title: ' + pg['key'])
    for ek, view in pages['entityViews'].items():
        name = ek.rsplit('/', 1)[-1]
        expected_caps = {
            'query': True,
            'get': True,
            'create': name not in {'roomOccupancy', 'orderEvent'},
            'update': name in mutable_update,
            'delete': name in mutable_delete,
        }
        if view.get('capabilities') != expected_caps:
            raise ValueError('page entityView capabilities mismatch: ' + ek)

    coverage = read_json(root / 'definition/page-coverage.json')
    expected_pages = {f'C{i:02}' for i in range(1, 7)} | {f'M{i:02}' for i in range(1, 8)} | {f'P{i:02}' for i in range(1, 7)}
    if {p['designPage'] for p in coverage['pages']} != expected_pages or len(coverage['pages']) != 19:
        raise ValueError('all 19 design pages require explicit coverage')
    actual_pages = {p['key'] for p in pages['pages']}
    if len(actual_pages) != 19 or actual_pages != {p['runtimePage'] for p in coverage['pages']} | set(coverage['supportPages']):
        raise ValueError('runtime pages and coverage disagree')
    if coverage['runtimeSourceCount'] != len(pages['dataSources']) or coverage['runtimePageCount'] != len(pages['pages']):
        raise ValueError('coverage counts disagree')
    targets = read_json(root / 'definition/page-targets.design.json')
    if {p['key'] for p in targets['pages']} != expected_pages or len(targets['pages']) != 19:
        raise ValueError('target page design is incomplete')
    logical_sources = {s['key'] for s in targets['dataSources']}
    if logical_sources != {f'DS{i:02}' for i in range(1, 19)} or len(targets['dataSources']) != 18:
        raise ValueError('target business source design is incomplete')
    for page in targets['pages']:
        if not set(page['logicalSources']) <= logical_sources or page['runtimeProjection'] not in actual_pages:
            raise ValueError('target page has unresolved source/projection')
    coordination = read_json(root / 'definition/coordination.design.json')
    if {record['key'] for record in coordination['records']} != set(profile['excludedRuntimeOwners']):
        raise ValueError('coordinator definitions and profile disagree')
    if coordination['runtimeImplemented'] or any(record['genericCRUD'] or record['includedInModelPackage']
                                                for record in coordination['records']):
        raise ValueError('private coordination records must not become generic package entities')
    contracts = read_json(root / 'definition/business-contract.design.json')
    if contracts['reservationWritesImplemented'] or any(c['runtimeEnabled'] for c in contracts['commands']):
        raise ValueError('unimplemented cross-entity reservation commands must remain disabled')
    return profile


def source_fingerprints():
    result = {}
    for p in sorted((MODEL_ROOT / 'definition').rglob('*')):
        if p.is_file():
            result[p.relative_to(MODEL_ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    local_files = sorted((ROOT / 'tooling').glob('*.py')) + sorted((ROOT / 'fixtures').glob('*.json'))
    local_files += [ROOT / 'tooling/package_codec_test.go.txt'] + sorted((ROOT / 'tooling/testdata').glob('*.json'))
    for p in local_files:
        if p.is_file():
            result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def run(mode, package=None, runner=None):
    validate_source()
    runner = (runner or WORKSPACE / 'magicRunner').expanduser().resolve()
    before = source_fingerprints()
    template = ROOT / 'tooling/package_codec_test.go.txt'
    with tempfile.TemporaryDirectory(prefix='chess-definition-') as temp:
        temp = Path(temp)
        output = temp / 'result'
        actual = temp / 'definition_test.go'
        actual.write_bytes(template.read_bytes())
        virtual = runner / 'internal/modules/kernel/panel/pkg/modelpackage' / f'zz_{temp.name.replace("-", "_")}_test.go'
        if virtual.exists():
            raise ValueError('overlay target already exists')
        overlay = temp / 'overlay.json'
        overlay.write_text(json.dumps({'Replace': {str(virtual): str(actual)}}))
        env = dict(os.environ, GOWORK='off', CHESS_DEFINITION_ROOT=str(MODEL_ROOT),
                   CHESS_TOOLING_ROOT=str(ROOT), CHESS_TOOL_OUTPUT=str(output), CHESS_TOOL_MODE=mode)
        if package:
            env['CHESS_INSPECT_PACKAGE'] = str(package.expanduser().resolve())
        subprocess.run(['go', 'test', '-overlay', str(overlay),
                        './internal/modules/kernel/panel/pkg/modelpackage',
                        '-run', '^TestChessRoomDefinitionTool$', '-count=1', '-v'],
                       cwd=runner, env=env, check=True, timeout=240)
        if before != source_fingerprints():
            raise ValueError('definition/tool source changed during validation')
        report = read_json(output / 'source-checks.json')
        report['sourceSHA256'] = before
        report['sourceCommits'] = {name: subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=runner if name == 'magicRunner' else WORKSPACE / name, text=True).strip()
                                   for name in ('magicRunner', 'magicBase', 'magicOrm')}
        report['publishPreflight'] = 'not-run'
        (output / 'source-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        files = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob('*') if p.is_file()}
    return report, files


def write_bundle(destination, files):
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('output already exists; preserve it and choose a new --output-dir')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve before writing. Other runs cannot overwrite this result.
    destination.mkdir()
    for name, raw in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    zip_path = destination / 'package.zip'
    checksum = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (destination / 'SHA256SUMS').write_text(f'{checksum}  package.zip\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'build', 'inspect'])
    parser.add_argument('--package', type=Path, help='downloaded standard ZIP for inspect')
    parser.add_argument('--output-dir', type=Path, help='new output directory; never overwrites')
    parser.add_argument('--runner-root', type=Path, help='Runner checkout; defaults to workspace sibling')
    parser.add_argument('--report', type=Path, help='save JSON evidence to a new file without retaining another bundle')
    args = parser.parse_args()
    if (args.command == 'inspect') != bool(args.package):
        parser.error('--package is required only for inspect')
    if args.command == 'check' and args.output_dir:
        parser.error('check prints evidence only; use build to retain a bundle')
    destination = args.output_dir or MODEL_ROOT / 'package'
    if (args.command == 'build' or args.output_dir) and (destination.expanduser().exists() or destination.expanduser().is_symlink()):
        parser.error('output already exists; choose a new --output-dir')
    if args.report and (args.report.expanduser().exists() or args.report.expanduser().is_symlink()):
        parser.error('report already exists; choose a new --report')
    report, files = run(args.command, args.package, args.runner_root)
    if args.command == 'build':
        write_bundle(destination, files)
    elif args.command == 'inspect' and args.output_dir:
        write_bundle(args.output_dir, files)
    if args.report:
        target = args.report.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
