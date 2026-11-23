#!/usr/bin/env python3
"""Check or refresh demo authoring authorization using Runner's actual contract; no Live IO."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def resolve_platform_root(explicit=None):
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env_root = os.environ.get('MAGICPLATFORM_ROOT', '').strip()
    if env_root:
        candidates.append(Path(env_root))
    workspace = Path(__file__).resolve().parents[2]
    candidates.extend([workspace / 'magicPlatform', workspace.parent / 'dataspace/magicPlatform'])
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / 'apps/models').is_dir():
            return resolved
    raise ValueError('magicPlatform checkout with apps/models/ not found; pass --platform-root or set MAGICPLATFORM_ROOT')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='refresh editable definition sources only')
    parser.add_argument('--platform-root', type=Path, help='magicPlatform checkout containing apps/models/')
    parser.add_argument('--runner-root', type=Path, help='magicRunner checkout; defaults to workspace sibling')
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[2]
    runner = (args.runner_root or workspace / 'magicRunner').expanduser().resolve()
    models_root = resolve_platform_root(args.platform_root) / 'apps/models'
    with tempfile.TemporaryDirectory(prefix='demo-authorization-') as directory:
        temp = Path(directory)
        actual = temp / 'authorization_test.go'
        actual.write_bytes(Path(__file__).with_suffix('.go.txt').read_bytes())
        virtual = runner / 'internal/modules/kernel/panel/pkg/common' / ('zz_' + temp.name.replace('-', '_') + '_test.go')
        overlay = temp / 'overlay.json'
        overlay.write_text(json.dumps({'Replace': {str(virtual): str(actual)}}))
        for app in ('device-management', 'chess-room-booking'):
            output = temp / (app + '.json')
            env = dict(os.environ, GOWORK='off', DEMO_AUTH_ROOT=str(models_root), DEMO_AUTH_APPLICATION=app,
                       DEMO_AUTH_WRITE='1' if args.write else '0', DEMO_AUTH_OUTPUT=str(output))
            subprocess.run(['go', 'test', '-overlay', str(overlay), './internal/modules/kernel/panel/pkg/common',
                            '-run', '^TestRefreshDemoAuthorization$', '-v', '-count=1'], cwd=runner, env=env, check=True, timeout=180)
            if args.write:
                path = models_root / app / ('definition/candidate.artifact.json' if app == 'device-management' else 'definition/application/metadata.json')
                document = json.loads(path.read_text())
                metadata = document['application'] if app == 'device-management' else document
                metadata['authorization'] = json.loads(output.read_text())
                path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
