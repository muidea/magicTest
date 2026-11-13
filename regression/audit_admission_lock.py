"""Hold an existing isolated owner admission flock by a read-only descriptor.

Never create/remove/rename/chmod or edit an owner queue entry. Closing this
process releases only its own flock; it says nothing about business rollback.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import stat
import sys
import time


def facts(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid,
            'mode': stat.S_IMODE(info.st_mode)}


def emit(kind, correlation, value):
    print(json.dumps({'kind': kind, 'correlation': correlation, **value}), flush=True)


def hold(root, uid, correlation, *, deadline=90):
    root = Path(root)
    if (not root.is_absolute() or root.resolve() != root or root.name != '.operation-audit'
            or not re.fullmatch(r'[a-f0-9]{32}', correlation) or uid < 0):
        raise ValueError('Exact original audit root and protocol identity required')
    parent = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700 or parent.st_uid != uid:
        raise ValueError('Original owner-only admission directory required')
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if facts(os.fstat(directory)) != facts(parent):
            raise ValueError('Original audit directory changed')
        fd = os.open('admission.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            original = os.fstat(fd)
            if not stat.S_ISREG(original.st_mode) or stat.S_IMODE(original.st_mode) != 0o600 or original.st_uid != uid:
                raise ValueError('Original regular private admission lock required')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            proof = {'directory': facts(parent), 'lock': facts(original)}
            emit('ready', correlation, proof)
            with selectors.DefaultSelector() as selector:
                selector.register(sys.stdin, selectors.EVENT_READ)
                end = time.monotonic() + deadline
                line = b''
                while not line.endswith(b'\n') and len(line) < 128:
                    if not selector.select(max(0, end - time.monotonic())):
                        raise ValueError('Original admission hold deadline expired')
                    chunk = os.read(sys.stdin.fileno(), 128 - len(line))
                    if not chunk:
                        break
                    line += chunk
            if line != ('release:' + correlation + '\n').encode():
                raise ValueError('Exact original admission release required')
            if (facts(root.stat(follow_symlinks=False)) != facts(parent)
                    or facts(os.stat('admission.lock', dir_fd=directory, follow_symlinks=False)) != facts(original)):
                raise ValueError('Original admission inode changed while held')
            fcntl.flock(fd, fcntl.LOCK_UN)
            emit('released', correlation, proof)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    p.add_argument('--uid', required=True, type=int)
    p.add_argument('--correlation', required=True)
    a = p.parse_args()
    try:
        hold(a.root, a.uid, a.correlation)
    except Exception:
        # No paths, environment, raw owner content or subprocess diagnostics.
        emit('unavailable', a.correlation, {'reason': 'Original isolated admission lock unavailable or disposition unconfirmed'})
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
