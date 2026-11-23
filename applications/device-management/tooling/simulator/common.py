"""Strict local inputs and secret-free failures for the device simulator."""
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

ENTITIES = ('location', 'category', 'device', 'telemetry', 'alarm', 'maintenance')
RELATIONS = {'location': {'parent': 'location'}, 'device': {'category': 'category', 'location': 'location'},
             'telemetry': {'device': 'device'}, 'alarm': {'device': 'device'}, 'maintenance': {'device': 'device'}}
OPERATIONS = {
    e: ('query', 'get', 'create', 'update')
    if e in ENTITIES[:3]
    else ('query', 'get', 'create')
    if e in ('telemetry', 'maintenance')
    else ('query', 'get')
    for e in ENTITIES
}


class Failure(ValueError):
    """Messages must not contain server response bodies or credentials."""


def require(condition, message):
    if not condition:
        raise Failure(message)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Failure('non-finite JSON')))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise Failure('invalid JSON') from None


def digest(value):
    return 'sha256:' + hashlib.sha256(dumps(value).encode()).hexdigest()


def identity(value):
    require(type(value) in (str, int) and re.fullmatch(r'[1-9][0-9]{0,18}', str(value)) is not None
            and int(value) <= 9223372036854775807, 'invalid exact positive int64 identity')
    return str(value)


def instant(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)', value), 'timezone required')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        raise Failure('invalid timestamp') from None


def utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def gateway_result(value):
    """Base public datetime uses magicOrm's explicitly UTC, timezone-free millisecond format.

    Do not relax configuration/input timestamp parsing or infer the process timezone.
    """
    datetime_fields = {'sampledAt', 'occurredAt', 'performedAt', 'lastSeenAt', 'acknowledgedAt', 'resolvedAt'}
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in datetime_fields and isinstance(item, str) and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}', item):
                result[key] = utc(instant(item.replace(' ', 'T') + 'Z'))
            else:
                result[key] = gateway_result(item)
        return result
    if isinstance(value, list):
        return [gateway_result(item) for item in value]
    return value


def home_path(value):
    require(isinstance(value, str) and value.startswith(('~/', '/')), 'local paths must be absolute or home-rooted')
    return Path(value).expanduser()


def load(path, limit=8 << 20):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'input size exceeded')
    return strict_json(raw)


def private_directory(path):
    path = Path(path)
    require(not path.is_symlink(), 'private directory cannot be a symlink')
    if not path.exists():
        path.mkdir(mode=0o700, parents=True)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
            'private directory requires owner-only mode 0700')


def secret(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600,
                'credential requires an owned regular 0600 file')
        raw = os.read(fd, 16385)
        require(len(raw) <= 16384, 'credential size exceeded')
        key = raw.decode().strip()
        require(key and not any(c.isspace() for c in key) and all(32 < ord(c) < 127 for c in key), 'invalid credential file')
        return key
    finally:
        os.close(fd)


def write_json(path, value, exclusive=False):
    path = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def same_fields(actual, expected):
    require(isinstance(actual, dict), 'record is not an object')
    for key, expected_value in expected.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if isinstance(expected_value, dict) and set(expected_value) == {'id'}:
            if not isinstance(actual_value, dict) or identity(actual_value.get('id')) != identity(expected_value['id']):
                return False
        elif key.endswith('At') and expected_value is not None:
            if instant(actual_value) != instant(expected_value):
                return False
        elif isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            if type(actual_value) not in (int, float) or not math.isfinite(actual_value) or actual_value != expected_value:
                return False
        elif actual_value != expected_value:
            return False
    return True
