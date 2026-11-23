"""Single-process, durable intent journal. Prepared writes are never blindly retried."""
import fcntl
import os
import sqlite3
import stat
from .common import Failure, dumps, private_directory, require, strict_json


class Journal:
    def __init__(self, directory, binding_digest):
        private_directory(directory)
        self.directory = directory
        lock = directory / 'run.lock'
        self.lock_fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock_fd)
            raise Failure('another simulator process owns this run') from None
        path = directory / 'journal.sqlite3'
        self.db = None
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600,
                        'journal must be an owned 0600 file')
            finally:
                os.close(fd)
            self.db = sqlite3.connect(path)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS intents (
                    key TEXT PRIMARY KEY, entity TEXT NOT NULL, operation TEXT NOT NULL,
                    payload TEXT NOT NULL, state TEXT NOT NULL, id TEXT, result TEXT, note TEXT);
            ''')
            with self.db:
                previous = self.meta('bindingDigest')
                require(previous is None or previous == binding_digest, 'run inputs changed; refusing to reuse this journal')
                self.set_meta('bindingDigest', binding_digest)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.db:
            self.db.close()
            self.db = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def meta(self, key, default=None):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return strict_json(row[0]) if row else default

    def set_meta(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, dumps(value)))

    def remember(self, key, value):
        with self.db:
            require(self.meta(key) in (None, value), 'persisted cycle/input differs')
            self.set_meta(key, value)

    def consume_request(self, maximum):
        with self.db:
            count = self.meta('requests', 0)
            require(count < maximum, 'persistent request budget exhausted')
            self.set_meta('requests', count + 1)

    def intent(self, key):
        self.db.row_factory = sqlite3.Row
        row = self.db.execute('SELECT * FROM intents WHERE key=?', (key,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['payload'] = strict_json(result['payload'])
        result['result'] = strict_json(result['result']) if result['result'] else None
        return result

    def prepare(self, op, payload):
        require(self.intent(op['key']) is None, 'intent already exists')
        with self.db:
            self.db.execute('INSERT INTO intents(key,entity,operation,payload,state) VALUES (?,?,?,?,?)',
                            (op['key'], op['entity'], op['operation'], dumps(payload), 'prepared'))

    def mark(self, key, state, result=None, note=None, value_id=None):
        with self.db:
            self.db.execute('UPDATE intents SET state=?,id=COALESCE(?,id),result=COALESCE(?,result),note=? WHERE key=?',
                            (state, value_id, dumps(result) if result is not None else None, note, key))

    def intents(self):
        return [self.intent(row[0]) for row in self.db.execute('SELECT key FROM intents ORDER BY rowid').fetchall()]

    def mapping(self):
        return {row['key']: row['id'] for row in self.intents()
                if row['operation'] == 'create' and row['state'] in ('confirmed', 'satisfied') and row['id']}

    def summary(self):
        rows = self.intents()
        states = {s: sum(r['state'] == s for r in rows) for s in ('prepared', 'confirmed', 'satisfied', 'unknown', 'rejected')}
        counts = {}
        for row in rows:
            if row['operation'] == 'create' and row['state'] in ('confirmed', 'satisfied'):
                counts[row['entity']] = counts.get(row['entity'], 0) + 1
        return {'states': states, 'created': counts, 'requests': self.meta('requests', 0),
                'retention': 'retained for page validation; simulator never deletes business data',
                'exactlyOnce': False, 'independentAppsReadback': 'not-run', 'browserAcceptance': 'not-run'}
