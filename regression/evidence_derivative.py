#!/usr/bin/env python3
"""Create a secret-free public derivative without changing original evidence.

Only explicitly supplied original 64-hex opaque File tokens are replaced.
Keep raw originals outside repositories before publishing either directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

TEXT = {'.json', '.jsonl', '.md', '.txt', '.log'}


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            # Public HTTP content observations identify a route and measured
            # response bytes, not an archived local file. Preserve their hash;
            # it describes the received body rather than a derivative file.
            content_observation = (value['path'].startswith('/static/')
                                   and type(value.get('bytes')) is int
                                   and value['bytes'] >= 0
                                   and (type(value.get('status')) is int
                                        or value.get('contentStatus') == 'temporary-content-retained-by-user')
                                   and re.fullmatch(r'sha256:[a-f0-9]{64}', value['sha256']))
            if not content_observation:
                yield value
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def resolve_reference(file, root, ref):
    # Evidence references are relative to their JSON container or run root.
    path = Path(ref)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Evidence derivative only accepts contained relative references')
    parents = [file.parent, *file.parent.parents]
    for parent in parents:
        if parent != root and root not in parent.parents:
            continue
        target = parent / path
        if target.is_file():
            if root.resolve() not in target.resolve().parents:
                raise ValueError('Evidence reference escapes original run')
            return target
    raise ValueError('Original evidence reference is missing: ' + ref)


def create_derivative(source, output, tokens):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir() or source == output or source in output.parents or output in source.parents:
        raise ValueError('Source and new derivative directory must be independent')
    if not tokens or any(not re.fullmatch('[a-f0-9]{64}', token) for token in tokens):
        raise ValueError('Supply only exact original 64-hex opaque File tokens')
    if output.exists():
        raise FileExistsError('Never overwrite an original or existing derivative')
    files = sorted(p for p in source.rglob('*') if p.is_file())
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Evidence trees with symlinks are not supported')
    documents = {}
    # Validate original hash contracts before creating a derivative. Do not
    # repair a corrupt source and then pretend it was a valid original.
    for file in files:
        if file.suffix == '.json':
            value = json.loads(file.read_text())
            refs = list(references(value))
            for ref in refs:
                target = resolve_reference(file, source, ref['path'])
                if digest(target) != ref['sha256']:
                    raise ValueError('Original evidence digest mismatch: ' + str(file.relative_to(source)))
            documents[file.relative_to(source)] = value
    shutil.copytree(source, output)
    redacted = []
    originals = {str(file.relative_to(source)): digest(file) for file in files}
    for file in files:
        if file.suffix not in TEXT:
            continue
        raw = file.read_bytes()
        transformed = raw
        for token in tokens:
            transformed = transformed.replace(token.encode(), b'[REDACTED-FILE-TOKEN]')
        if transformed != raw:
            dest = output / file.relative_to(source)
            dest.write_bytes(transformed)
            redacted.append(str(file.relative_to(source)))
    # Hash references form a DAG. Resolve leaves before results/report records;
    # a cycle can never stabilize and is rejected instead of fabricating hashes.
    pending = set(documents)
    while pending:
        progress = False
        for relative in sorted(pending):
            dest = output / relative
            value = json.loads(dest.read_text())
            refs = list(references(value))
            targets = [resolve_reference(dest, output, r['path']) for r in refs]
            if any(target.relative_to(output) in pending for target in targets):
                continue
            changed = False
            for ref, target in zip(refs, targets):
                actual = digest(target)
                if ref['sha256'] != actual:
                    ref['sha256'] = actual
                    changed = True
            if changed:
                dest.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            pending.remove(relative)
            progress = True
        if not progress:
            raise ValueError('Cyclic evidence digest references; derivative is incomplete')
    for relative in documents:
        dest = output / relative
        for ref in references(json.loads(dest.read_text())):
            if digest(resolve_reference(dest, output, ref['path'])) != ref['sha256']:
                raise ValueError('Derivative digest verification failed')
    if any(any(token.encode() in p.read_bytes() for token in tokens) for p in output.rglob('*') if p.is_file() and p.suffix in TEXT):
        raise ValueError('Known opaque token remains in derivative')
    original_unchanged = all(digest(source / name) == sha for name, sha in originals.items())
    if not original_unchanged:
        raise ValueError('Original evidence changed during derivative creation')
    report = {'kind': 'public-redacted-derivative', 'redactorSha256': digest(Path(__file__)), 'originalBytesUnchanged': original_unchanged,
              'originalFilesSha256': originals, 'publicFilesSha256': {name: digest(output / name) for name in originals},
              'opaqueFileTokensRedacted': len(set(tokens)), 'filesContainingTokenText': redacted,
              'referencesVerified': True,
              'preserves': 'original verdicts, numeric owner error codes, timestamps and resource dispositions; referenced public file digests are recomputed',
              'rawOriginalRetention': 'exact immutable original tree retained in external private storage; never publish raw token-bearing originals'}
    (output / 'redaction-provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--values', required=True, help='external private JSON array of exact original opaque File tokens')
    args = parser.parse_args()
    report = create_derivative(args.source, args.output, json.loads(Path(args.values).read_text()))
    print(json.dumps({key: report[key] for key in ['kind', 'originalBytesUnchanged', 'referencesVerified']}))


if __name__ == '__main__':
    main()
