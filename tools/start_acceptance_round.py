#!/usr/bin/env python3
"""Keep one acceptance round under reports/runs; never touch application or service data."""

import argparse
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]


def start_round(root, name):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*', name):
        raise ValueError('round must be YYYY-MM-DD-name using lowercase letters, digits and hyphens')
    root = Path(root).absolute()
    reports = root / 'reports'
    runs = reports / 'runs'
    containers = [reports, runs]
    # Validate every destination before removing anything. Reject symlinked roots.
    for directory in [root, root / 'acceptance', *containers]:
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(f'unsafe archive directory: {directory}')
    if not (root / 'acceptance/platform-catalog.json').is_file():
        raise ValueError('acceptance catalogue is missing')
    current = runs / name
    if current.is_symlink() or (current.exists() and not current.is_dir()):
        raise ValueError(f'unsafe current round: {current}')
    index = reports / 'README.md'
    if index.is_symlink() or (index.exists() and not index.is_file()):
        raise ValueError(f'unsafe reports index: {index}')
    targets = []
    if runs.exists():
        for entry in runs.iterdir():
            if entry == current or entry.name in {'.git', '.gitignore', '.gitattributes', 'README.md'}:
                continue
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
    current.mkdir(parents=True, exist_ok=True)
    readme = current / 'README.md'
    if not readme.exists():
        readme.write_text(f'# {name}\n\n状态：执行中，尚未完成验收。不继承旧轮次通过数。\n')
    if index.is_file():
        index.write_text(re.sub(r'reports/runs/[^/\s)]+/README\.md',
                               f'reports/runs/{name}/README.md',
                               index.read_text()))
    return {'round': name, 'removedEntries': len(targets),
            'removedFiles': removed_files, 'removedBytes': removed_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('round', help='YYYY-MM-DD-name; an existing current round is preserved')
    args = parser.parse_args()
    print(json.dumps(start_round(ROOT, args.round), ensure_ascii=False))


if __name__ == '__main__':
    main()
