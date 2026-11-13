"""Bounded, held-FD sources for explicit historical locator validation.

Sources prove which local bytes were read; they never grant business authority.
"""
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import os
import fcntl
from pathlib import Path
import re
import sqlite3
import stat
import sys
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .own_bootstrap_security import decode
from .own_identity_checkpoint import Reader, LEGACY, file_metadata
from .own_validation_scope import OwnedConnection
from .draft_revision_index_worker import _fd_regulars
from .own_fd_domain import fd_capacity_allowed

CHECKPOINT_DIRECTORY = 'identity-history-checkpoints'
# Legacy FileSource may hold '/' plus 32 path components and one file.
# Keep that full sequential-read peak available while persistent FDs are held.
TRANSIENT_FDS = 35
_DB_SOURCES = WeakKeyDictionary()


def hold(condition):
    if not condition:
        raise WCEError('OWN_HISTORY_LOCATOR_HOLD')


def safe_path(value):
    path = Path(value)
    hold(path.is_absolute() and '..' not in path.parts and len(path.parts) <= 32
         and len(str(path)) <= 4096 and not any(ord(c) < 32 or ord(c) == 127 for c in str(path)))
    return path


def core(info):
    return {k: file_metadata(info)[k] for k in ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink')}


class HeldFiles:
    def __init__(self, base):
        self.base, self.stack = safe_path(base), ExitStack()
        self.parents, self.files = {}, {}
        self.budget = {'proof': 512 * 1024, 'checkpoint': 64 * 1024 * 1024,
                       'record': 32 * 1024 * 1024}
        self.streamed = dict.fromkeys(self.budget, 0)
        self.peak_fds = 0

    def _capacity(self, additional=0):
        # listdir's transient enumeration descriptor is conservative headroom.
        count = len(os.listdir('/dev/fd'))
        self.peak_fds = max(self.peak_fds, count)
        hold(fd_capacity_allowed(count, additional, TRANSIENT_FDS))

    def _directory_guard(self, path, fd):
        info = os.fstat(fd)
        hold(stat.S_ISDIR(info.st_mode))
        if path.is_relative_to(self.base):
            hold(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
        if path != Path('/'):
            named = os.stat(path.name, dir_fd=self.parents[path.parent], follow_symlinks=False)
            hold(stat.S_ISDIR(named.st_mode) and core(named) == core(info))

    def check_directories(self):
        for path, fd in self.parents.items():
            self._directory_guard(path, fd)

    def parent(self, path):
        path = safe_path(path)
        if Path('/') not in self.parents:
            self._capacity(1)
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.stack.callback(os.close, fd)
            self.parents[Path('/')] = fd
        current = Path('/')
        for part in path.parts[1:]:
            child = current / part
            if child not in self.parents:
                self._capacity(1)
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=self.parents[current])
                self.stack.callback(os.close, fd)
                self.parents[child] = fd
            self._directory_guard(child, self.parents[child])
            current = child
        return self.parents[path]

    def directory(self, path):
        fd = self.parent(path)
        return {k: file_metadata(os.fstat(fd))[k] for k in ('dev', 'ino', 'mode', 'uid', 'gid')}

    def proof_lock(self, path):
        item = self.file(path)
        hold(item['pin']['bytes'] == 0)
        try:
            fcntl.flock(item['fd'], fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WCEError('CONNECTION_BUSY') from None
        self.check_file(safe_path(path))

    def file(self, path, *, mutable=False):
        path = safe_path(path)
        if path not in self.files:
            parent = self.parent(path.parent)
            self._capacity(1)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            self.stack.callback(os.close, fd)
            info = os.fstat(fd)
            hold(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)
            pin = file_metadata(info)
            hold(file_metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == pin)
            self.files[path] = {'fd': fd, 'pin': pin, 'mutable': mutable, 'raw': None, 'category': None}
            self._capacity()
        item = self.files[path]
        hold(item['mutable'] == mutable)
        self.check_file(path)
        return item

    def check_file(self, path):
        item = self.files[path]
        parent = self.parents[path.parent]
        current = os.fstat(item['fd'])
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if item['mutable']:
            hold(core(current) == core(named) == {k: item['pin'][k] for k in core(current)})
        else:
            hold(file_metadata(current) == file_metadata(named) == item['pin'])

    def read(self, path, maximum, category, *, force=False):
        path = safe_path(path)
        item = self.file(path)
        hold(0 < item['pin']['bytes'] <= maximum and category in self.budget)
        hold(item['category'] in (None, category))
        if item['raw'] is not None and not force:
            return item['pin'] | {'sha256': sha256(item['raw']).hexdigest()}, item['raw']
        os.lseek(item['fd'], 0, os.SEEK_SET)
        parts, size = [], 0
        while True:
            amount = min(65536, maximum + 1 - size, self.budget[category] + 1)
            hold(amount > 0)
            block = os.read(item['fd'], amount)
            if not block:
                break
            size += len(block)
            self.budget[category] -= len(block)
            self.streamed[category] += len(block)
            hold(size <= maximum and self.budget[category] >= 0)
            parts.append(block)
        self.check_file(path)
        hold(size == item['pin']['bytes'])
        raw = b''.join(parts)
        if item['raw'] is not None:
            hold(raw == item['raw'])
        item['raw'], item['category'] = raw, category
        return item['pin'] | {'sha256': sha256(raw).hexdigest()}, raw

    def verify(self, category=None):
        for path, item in list(self.files.items()):
            self.check_file(path)
            if item['raw'] is not None and (category is None or item['category'] == category):
                maximum = {'proof': 262144, 'checkpoint': 4 * 1024 * 1024,
                           'record': 2 * 1024 * 1024}[item['category']]
                self.read(path, maximum, item['category'], force=True)
        self.check_directories()
        self._capacity()

    def close(self):
        try:
            self.check_directories()
        finally:
            self.stack.close()


class _DBSource:
    def __init__(self, db, path, before, files, anchor, *, readonly, revision_header):
        hold(type(readonly) is bool)
        self.readonly = readonly
        self.revision_header = revision_header
        self.db, self.path = db, safe_path(path)
        self.files = files
        try:
            wanted = (anchor['pin']['dev'], anchor['pin']['ino'])
            opened = {fd: pin for fd, pin in _fd_regulars().items() if fd not in before
                      and fd != anchor['fd']}
            hold(list(opened.values()).count(wanted) == 1 and all(pin == wanted for pin in opened.values()))
            self.sqlite_fd = next(fd for fd, pin in opened.items() if pin == wanted)
            self.identity = wanted
            hold(Path(sqlite3.Connection.execute(db, 'PRAGMA database_list').fetchone()[2]) == self.path)
            self.active = True
            self.guard()
        except BaseException:
            raise

    def guard(self):
        hold(self.active and type(self.db) is OwnedConnection)
        hold((os.fstat(self.sqlite_fd).st_dev, os.fstat(self.sqlite_fd).st_ino) == self.identity)
        self.files.check_file(self.path)
        self.files.check_directories()
        # A closed or substituted SQLite object cannot retain a valid witness.
        hold(type(self.db.in_transaction) is bool)

    def close(self):
        self.active = False
        self.files.close()


def _revision_header_check(path, anchor, files):
    """Original revision inventory's DELETE-format gate, before SQLite opens."""
    pin=anchor['pin']
    parent=files.parents[path.parent]
    hold(file_metadata(os.fstat(anchor['fd'])) == pin
         == file_metadata(os.stat(path.name,dir_fd=parent,follow_symlinks=False)))
    prefix=os.pread(anchor['fd'],100,0)
    if len(prefix)!=100 or prefix[:16]!=b'SQLite format 3\x00' or prefix[18:20]!=b'\x01\x01':
        raise WCEError('DRAFT_REVISION_DATABASE_JOURNAL_MODE_HOLD')
    hold(not any(os.path.lexists(str(path)+suffix) for suffix in ('-wal','-shm','-journal')))
    files.check_directories()


@contextmanager
def owned_connection(path, *, readonly=False, timeout=10, isolation_level=None, _revision_header=False):
    """Actual OwnStore open point; source associations are never caller flags."""
    hold(type(readonly) is bool and type(_revision_header) is bool
         and (not _revision_header or readonly is True))
    path = safe_path(path)
    files = HeldFiles(path.parent)
    db, witness = None, None
    try:
        # Pin a safe existing target before SQLite gets an opportunity to open it.
        anchor = files.file(path, mutable=True)
        if _revision_header:_revision_header_check(path,anchor,files)
        files._capacity(4)
        before = _fd_regulars()
        target = path.as_uri() + ('?mode=ro' if readonly else '?mode=rw')
        db = sqlite3.connect(target, uri=True, timeout=timeout,
                             isolation_level=isolation_level, factory=OwnedConnection)
        witness = _DBSource(db, path, before, files, anchor, readonly=readonly,
                            revision_header=_revision_header)
        if _revision_header:_revision_header_check(path,anchor,files)
        _DB_SOURCES[db] = witness
        yield db
    finally:
        original = sys.exc_info()[1]
        cleanup_error = None
        try:
            if witness is not None:
                _DB_SOURCES.pop(db, None)
                witness.close()
            else:
                files.close()
        except BaseException as error:
            cleanup_error = error
        try:
            if db is not None:
                db.close()
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
        if original is None and cleanup_error is not None:
            raise cleanup_error


def connection_source(db):
    if type(db) is not OwnedConnection:
        return None
    witness = _DB_SOURCES.get(db)
    if witness is not None:
        hold(type(witness) is _DBSource and witness.db is db)
        witness.guard()
    return witness


def checkpoint(raw, registry):
    """Strict CLOSED_SET_V2 envelope; independent of the old proof budget."""
    hold(type(raw) is bytes and 0 < len(raw) <= 4 * 1024 * 1024)
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            hold(depth <= 16)
        elif byte in (93, 125):
            depth -= 1
            hold(depth >= 0)
    value = decode(raw, 4 * 1024 * 1024)
    hold(type(value) is dict and set(value) == {'snapshot_format', 'accounts'}
         and value['snapshot_format'] == 'WCE_RECOVERY_CLOSED_SET_V2')
    data = value['accounts']
    hold(type(data) is dict and set(data) == {'files', 'members', 'directories', 'keychain_access', 'business_write'}
         and data['keychain_access'] is False and data['business_write'] is False)
    hold(all(type(data[key]) is dict for key in ('files', 'members', 'directories')))
    hold(len(data['files']) <= 4096 and len(data['members']) <= 128 and len(data['directories']) <= 128)
    base = safe_path(registry).parent
    hold(set(data['members']) == set(data['directories']) and str(base) in data['directories'])
    expected = {'dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'bytes', 'mtime_ns', 'ctime_ns', 'sha256'}
    total, children = 0, set()
    for name, pin in data['files'].items():
        path = safe_path(name)
        hold(path.is_relative_to(base) and type(pin) is dict and set(pin) == expected
             and all(type(pin[k]) is int and pin[k] >= 0 for k in expected - {'sha256'})
             and pin['uid'] == os.getuid() and pin['nlink'] == 1
             and type(pin['sha256']) is str and re.fullmatch('[a-f0-9]{64}', pin['sha256']) is not None
             and pin['bytes'] <= 128 * 1024 * 1024)
        legacy = (pin['mode'] == 0o700 and pin['bytes'] <= 65536 and path.suffix == '.command'
                  and LEGACY.fullmatch(path.name) is not None
                  and path.parent.parent.name in {'accounts', 'own'} and path.parent.parent.parent == base)
        hold(pin['mode'] == 0o600 or legacy)
        total += pin['bytes']
        hold(str(path.parent) in data['directories'])
    hold(total <= 384 * 1024 * 1024)
    for name, pin in data['directories'].items():
        path = safe_path(name)
        hold(path.is_relative_to(base) and type(pin) is dict
             and set(pin) == {'dev', 'ino', 'mode', 'uid', 'gid'}
             and all(type(v) is int and v >= 0 for v in pin.values())
             and pin['mode'] == 0o700 and pin['uid'] == os.getuid())
        names = data['members'][name]
        hold(type(names) is list and len(names) <= 1024
             and all(type(n) is str for n in names) and names == sorted(set(names)))
        for leaf in names:
            hold(type(leaf) is str and leaf not in ('', '.', '..') and '/' not in leaf
                 and not any(ord(c) < 32 or ord(c) == 127 for c in leaf))
            child = str(path / leaf)
            hold(child in data['files'] or child in data['directories'])
            children.add(child)
    hold(children == (set(data['files']) | set(data['directories'])) - {str(base)})
    return data
