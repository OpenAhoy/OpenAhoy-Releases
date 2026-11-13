"""One fresh-exec, single-thread native index observation, never authorization.

Invoked only as the fixed sibling script with ``python -I -B``. Keep this file
stdlib-only: no package bootstrap, account service, credential or network code.
The nofollow anchor and FD fence below preserve native_source/native_lookup
primitives; their standalone copy avoids importing the product in the child.
mode=ro protects database data; live WAL coordination can modify existing SHM.
"""
from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

INPUT_LIMIT = 8192
OUTPUT_LIMIT = 16384
QUERY_SECONDS = 5.0
PROTOCOL = 'WCE_NATIVE_INDEX_V1'
UUID = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
ERROR_CODES = frozenset({
    'HOST_INDEX_WORKER_PROTOCOL', 'HOST_INDEX_WORKER_DEADLINE',
    'HOST_NATIVE_ROOT_INVALID', 'HOST_THREAD_ID_INVALID',
    'HOST_NATIVE_INDEX_INVALID', 'HOST_NATIVE_INDEX_CHANGED',
    'HOST_NATIVE_INDEX_ROW_INVALID', 'HOST_NATIVE_THREAD_MISSING',
    'HOST_NATIVE_OWNER_MISMATCH', 'HOST_NATIVE_SOURCE_PATH',
    'HOST_NATIVE_LOOKUP_HOLD', 'HOST_SQLITE_FD_UNAVAILABLE',
    'HOST_SQLITE_CONNECTION_IDENTITY_UNPROVEN',
    'HOST_SQLITE_AUXILIARY_UNVERIFIED', 'SOURCE_OPEN_HOLD',
})


class WorkerHold(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise WorkerHold(code)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8') + b'\n'


def decode(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum
            and raw.endswith(b'\n') and raw.count(b'\n') == 1,
            'HOST_INDEX_WORKER_PROTOCOL')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'HOST_INDEX_WORKER_PROTOCOL')
            result[key] = value
        return result

    def invalid(_):
        raise WorkerHold('HOST_INDEX_WORKER_PROTOCOL')

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=invalid)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkerHold('HOST_INDEX_WORKER_PROTOCOL') from None


def valid_text(value, maximum):
    return (type(value) is str and '\x00' not in value
            and 0 < len(value.encode('utf-8')) <= maximum)


def validate_request(value):
    require(type(value) is dict and set(value) == {
        'protocol', 'index_path', 'session_root', 'device', 'inode',
        'owner_thread', 'thread', 'deadline'}, 'HOST_INDEX_WORKER_PROTOCOL')
    require(value['protocol'] == PROTOCOL, 'HOST_INDEX_WORKER_PROTOCOL')
    for key in ('owner_thread', 'thread'):
        require(type(value[key]) is str and re.fullmatch(UUID, value[key]),
                'HOST_THREAD_ID_INVALID')
    require(all(type(value[key]) is int and 0 <= value[key] < 2**64
                for key in ('device', 'inode')), 'HOST_INDEX_WORKER_PROTOCOL')
    require(type(value['deadline']) in (int, float) and math.isfinite(value['deadline']),
            'HOST_INDEX_WORKER_PROTOCOL')
    remaining = value['deadline'] - time.monotonic()
    require(remaining > 0, 'HOST_INDEX_WORKER_DEADLINE')
    require(remaining <= QUERY_SECONDS, 'HOST_INDEX_WORKER_PROTOCOL')
    require(valid_text(value['index_path'], 4096) and valid_text(value['session_root'], 4096),
            'HOST_NATIVE_ROOT_INVALID')
    path, root = Path(value['index_path']), Path(value['session_root'])
    require(path.is_absolute() and root.is_absolute() and '..' not in path.parts
            and '..' not in root.parts and path.name == 'state_5.sqlite'
            and root.name == 'sessions' and root.parent == path.parent,
            'HOST_NATIVE_ROOT_INVALID')
    return path, root


def _regular(info, identity):
    return (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and (info.st_dev, info.st_ino) == identity)


def _open_index(path, identity):
    """Standalone equivalent of native_source._open_source's nofollow chain."""
    descriptors, chain = [], []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(parent)
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(child)
            info = os.fstat(child)
            chain.append((parent, name, (info.st_dev, info.st_ino)))
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        descriptors.append(fd)
        require(_regular(os.fstat(fd), identity), 'SOURCE_OPEN_HOLD')
        return fd, descriptors, chain
    except (OSError, WorkerHold):
        for fd in reversed(descriptors):
            os.close(fd)
        raise WorkerHold('SOURCE_OPEN_HOLD') from None


def _fd_regulars():
    found = {}
    try:
        for entry in os.listdir('/dev/fd'):
            if not entry.isdecimal():
                continue
            fd = int(entry)
            try:
                info = os.fstat(fd)
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                found[fd] = (info.st_dev, info.st_ino)
    except OSError:
        raise WorkerHold('HOST_SQLITE_FD_UNAVAILABLE') from None
    return found


def _auxiliary_pins(path):
    pins = {}
    for suffix in ('-wal', '-shm'):
        auxiliary = Path(str(path) + suffix)
        try:
            info = auxiliary.lstat()
        except FileNotFoundError:
            continue
        identity = (info.st_dev, info.st_ino)
        require(_regular(info, identity), 'HOST_SQLITE_AUXILIARY_UNVERIFIED')
        pins[suffix] = identity
    return pins


def _sqlite_identity_fence(before, state_path, identity, auxiliary):
    """Keep the original exact-new-main-FD and complete allowed-identity set."""
    current = _fd_regulars()
    opened = {fd: pin for fd, pin in current.items() if fd not in before}
    require(list(opened.values()).count(identity) == 1,
            'HOST_SQLITE_CONNECTION_IDENTITY_UNPROVEN')
    require(_auxiliary_pins(state_path) == auxiliary, 'HOST_SQLITE_AUXILIARY_UNVERIFIED')
    allowed = {identity, *auxiliary.values()}
    require(all(pin in allowed for pin in opened.values()),
            'HOST_SQLITE_CONNECTION_IDENTITY_UNPROVEN')


def check_anchor(path, fd, identity, chain):
    require(_regular(path.lstat(), identity) and _regular(os.fstat(fd), identity),
            'HOST_NATIVE_INDEX_CHANGED')
    for ancestor, item, expected in chain:
        current = os.stat(item, dir_fd=ancestor, follow_symlinks=False)
        require(stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == expected,
                'HOST_NATIVE_INDEX_CHANGED')


def validate_rows(rows, thread, owner_thread, root):
    expected = {thread, owner_thread}
    require(type(rows) is list and len(rows) == len(expected), 'HOST_NATIVE_THREAD_MISSING')
    require(all(type(row) in (tuple, list) and len(row) == 4
                and valid_text(row[0], 36) and re.fullmatch(UUID, row[0])
                and valid_text(row[1], 4096) and valid_text(row[2], 1024)
                and valid_text(row[3], 1024) for row in rows), 'HOST_NATIVE_INDEX_ROW_INVALID')
    entries = {row[0]: row for row in rows}
    require(len(entries) == len(rows) and set(entries) == expected, 'HOST_NATIVE_THREAD_MISSING')
    entry, owner = entries[thread], entries[owner_thread]
    require(entry[2:] == owner[2:], 'HOST_NATIVE_OWNER_MISMATCH')
    path = Path(entry[1])
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(root)
            and re.fullmatch(r'rollout-[0-9T:-]+-' + thread + r'(?:_' + UUID + r')?\.jsonl', path.name),
            'HOST_NATIVE_SOURCE_PATH')
    return path, tuple(entry[2:])


# Each CASE rejects oversized/type-invalid values inside SQLite before Python
# can materialize them. Only these four fields, two IDs and three rows exist in
# the protocol. LIMIT 3 exposes duplicate/missing-row ambiguity without fetchall.
QUERY = '''SELECT
CASE WHEN typeof(id)='text' AND length(CAST(id AS BLOB))=36 THEN id END,
CASE WHEN typeof(rollout_path)='text' AND length(CAST(rollout_path AS BLOB)) BETWEEN 1 AND 4096 THEN rollout_path END,
CASE WHEN typeof(creator_user_id)='text' AND length(CAST(creator_user_id AS BLOB)) BETWEEN 1 AND 1024 THEN creator_user_id END,
CASE WHEN typeof(creator_account_id)='text' AND length(CAST(creator_account_id AS BLOB)) BETWEEN 1 AND 1024 THEN creator_account_id END
FROM threads WHERE id IN (?,?) LIMIT 3'''


def query(value):
    path, root = validate_request(value)
    deadline = value['deadline']
    identity = (value['device'], value['inode'])

    def guard():
        require(time.monotonic() < deadline, 'HOST_INDEX_WORKER_DEADLINE')

    descriptors = []
    try:
        guard()
        fd, descriptors, chain = _open_index(path, identity)
        header = os.read(fd, 100)
        require(len(header) == 100 and header[:16] == b'SQLite format 3\x00', 'HOST_NATIVE_INDEX_INVALID')
        auxiliary = _auxiliary_pins(path)
        # Reject initially missing WAL coordination files. A later concurrent unlink
        # can make SQLite recreate sidecars before the second fence rejects it;
        # mode=ro is not an OS-level zero-filesystem-write guarantee.
        require(not auxiliary or set(auxiliary) == {'-wal', '-shm'}, 'HOST_SQLITE_AUXILIARY_UNVERIFIED')
        require(header[18:20] != b'\x02\x02' or set(auxiliary) == {'-wal', '-shm'},
                'HOST_SQLITE_AUXILIARY_UNVERIFIED')
        guard()
        before = _fd_regulars()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                    timeout=min(1.0, max(0.001, deadline - time.monotonic())))) as db:
            _sqlite_identity_fence(before, path, identity, auxiliary)
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)

            def authorize(action, first, second, database, trigger):
                if time.monotonic() >= deadline:
                    return sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_SELECT:
                    return sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_READ and first == 'threads' and database == 'main' and trigger is None:
                    return sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_FUNCTION and second in ('typeof', 'length'):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            db.set_authorizer(authorize)
            rows = db.execute(QUERY, (value['thread'], value['owner_thread'])).fetchmany(3)
            guard()
            _sqlite_identity_fence(before, path, identity, auxiliary)
            validate_rows(rows, value['thread'], value['owner_thread'], root)
            check_anchor(path, fd, identity, chain)
        guard()
        check_anchor(path, fd, identity, chain)
        return {'protocol': PROTOCOL, 'status': 'OK', 'rows': rows}
    except WorkerHold:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError, UnicodeError, OverflowError):
        raise WorkerHold('HOST_NATIVE_LOOKUP_HOLD') from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def main():
    try:
        raw = bytearray()
        while True:
            part = os.read(0, min(4096, INPUT_LIMIT + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
            require(len(raw) <= INPUT_LIMIT, 'HOST_INDEX_WORKER_PROTOCOL')
        result = query(decode(bytes(raw), INPUT_LIMIT))
    except BaseException as error:
        code = error.code if isinstance(error, WorkerHold) and error.code in ERROR_CODES else 'HOST_NATIVE_LOOKUP_HOLD'
        result = {'protocol': PROTOCOL, 'status': 'HOLD', 'code': code}
    encoded = encode(result)
    if len(encoded) > OUTPUT_LIMIT:
        encoded = encode({'protocol': PROTOCOL, 'status': 'HOLD', 'code': 'HOST_INDEX_WORKER_PROTOCOL'})
    try:
        while encoded:
            written = os.write(1, encoded)
            encoded = encoded[written:]
    except OSError:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
