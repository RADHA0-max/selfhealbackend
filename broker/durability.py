"""Broker-private request journal. Unknown outcomes are never retried automatically."""
import fcntl
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from broker.protocol import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_request(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('request must be a single-link regular file')
        raw = source.read(MAX_REQUEST_BYTES + 1)
        after = os.fstat(source.fileno())
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError('request exceeds 64 KiB limit')
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('request changed during read')
        return raw


def publish(path, raw):
    """Atomic no-overwrite publication, durable file and directory, bounded bytes."""
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('invalid response bytes')
    fd, name = tempfile.mkstemp(prefix='.response-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.link(name, str(path), follow_symlinks=False)
        sync_directory(path.parent)
    finally:
        os.unlink(name)


class Journal:
    """Exclusive batch ownership plus durable at-most-once admission.

    Directory must be writable only by the trusted broker. No expiry/lease can
    turn an uncertain request into a new inference. Store is deliberately not
    garbage-collected: deleting it would discard replay protection.
    """
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = None
        self.db = None

    def __enter__(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('broker state directory must be private and owned')
        fd = os.open(str(self.directory/'owner.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, 'rb+')
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                raise ValueError('invalid broker lock')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = self.directory/'requests.sqlite'
            if os.path.lexists(path) and (path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1):
                raise ValueError('invalid broker journal')
            self.db = sqlite3.connect(str(path), timeout=5)
            os.chmod(str(path), 0o600)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('''CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('CLAIMED','COMPLETE','UNCERTAIN')),
                response BLOB)''')
            self.db.commit()
            sync_directory(self.directory)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def claim(self, identity, raw):
        digest = hashlib.sha256(raw).hexdigest()
        with self.db:
            row = self.db.execute('SELECT digest,state,response FROM requests WHERE id=?', (identity,)).fetchone()
            if row:
                if row[0] != digest:
                    return 'CONFLICT', None
                return row[1], row[2]
            self.db.execute('INSERT INTO requests VALUES (?,?,?,NULL)', (identity, digest, 'CLAIMED'))
        return 'NEW', None

    def finish(self, identity, response):
        if not isinstance(response, bytes) or len(response) > MAX_RESPONSE_BYTES:
            raise ValueError('invalid response bytes')
        with self.db:
            result = self.db.execute("UPDATE requests SET state='COMPLETE', response=? WHERE id=? AND state='CLAIMED'", (response, identity))
            if result.rowcount != 1:
                raise ValueError('request not claimed')

    def uncertain(self, identity):
        with self.db:
            self.db.execute("UPDATE requests SET state='UNCERTAIN' WHERE id=? AND state='CLAIMED'", (identity,))
