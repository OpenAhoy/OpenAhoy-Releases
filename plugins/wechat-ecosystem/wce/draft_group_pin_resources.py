"""Explicit, owner-scoped immutable path resources; never permission or H.

Candidate component only. Group callers must opt in and keep their original
semantic/QA/current/force validation. Standalone PinnedFile is not replaced.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import stat
import threading
import weakref

from .contracts import WCEError
from .own_fd_domain import fd_capacity_allowed

TRANSIENT_FDS = 35
MAX_RAW_BYTES = 64 * 1024 * 1024


def need(value, code='GROUP_PIN_RESOURCE_HOLD'):
    if value is not True:
        raise WCEError(code)


def full(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def directory_core(info):
    # Legitimate child creation changes directory times/nlink. Never rebase
    # identity/uid/gid/mode; current FD/name still compare the complete stat.
    return full(info)[:5]


def path_value(value):
    path = Path(value)
    need(path.is_absolute() and '..' not in path.parts
         and len(path.parts) <= 32 and len(str(path)) <= 4096
         and not any(ord(c) < 32 or ord(c) == 127 for c in str(path)))
    return path


def capacity(additional, *, persistent):
    count = len(os.listdir('/dev/fd'))
    need(fd_capacity_allowed(count, additional, TRANSIENT_FDS if persistent else 0),
         'GROUP_PIN_FD_CAPACITY')
    return count


def close_all(callbacks, original=None):
    """Try every close; a body exception is never replaced by cleanup."""
    first = None
    for callback in callbacks:
        try:
            callback()
        except BaseException as error:
            if first is None:
                first = error
    if original is None and first is not None:
        raise first


@dataclass
class _Directory:
    fd: int
    parent: object
    name: object
    baseline: tuple


@dataclass
class _Leaf:
    path: Path
    fd: int
    parent: int
    baseline: tuple
    checksum: str
    raw: bytes


class PinView:
    __slots__ = ('_pool', '_record', '_owner', '_thread', '_shared', 'closed', '__weakref__')

    def __init__(self, *args, **kwargs):
        raise WCEError('GROUP_PIN_VIEW_ISSUER_REQUIRED')

    def check(self):
        self._pool._check_view(self)
        return True

    @property
    def raw(self):
        self.check()
        return self._record.raw

    @property
    def fd(self):
        self.check()
        return self._record.fd

    @property
    def pin(self):
        self.check()
        return self._record.baseline

    @property
    def sha(self):
        self.check()
        return self._record.checksum

    @property
    def path(self):
        return self._record.path

    def close(self):
        if self.closed:
            return
        self._pool._release_view(self)


class PinPool:
    """One explicit entry/history or immutable process-catalog lifetime.

    Catalog acquisition is creator-thread-only. After sealing, existing leaves
    may be checked by process workers under the pool lock. A fixed catalog row
    selector must authorize borrow_existing before the Group caller calls it.
    """
    def __init__(self, owner, *, catalog=False):
        need(owner is not None and type(catalog) is bool)
        self.owner, self.catalog = owner, catalog
        self.pid, self.thread = os.getpid(), threading.get_ident()
        self.closed, self.sealed = False, False
        self._lock = threading.RLock()
        self._directories, self._leaves = {}, {}
        self._views = weakref.WeakKeyDictionary()
        self.raw_bytes = 0
        self.peak_fds = 0

    def _guard(self, owner, *, mutate=False):
        need(not self.closed and self.owner is owner and self.pid == os.getpid(),
             'GROUP_PIN_OWNER_CLOSED')
        need(threading.get_ident() == self.thread or (self.catalog and self.sealed and not mutate),
             'GROUP_PIN_THREAD')
        if mutate:
            need(not self.sealed, 'GROUP_PIN_CATALOG_SEALED')

    def _check_directory(self, path):
        item = self._directories[path]
        opened = os.fstat(item.fd)
        named = opened if item.parent is None else os.stat(item.name, dir_fd=item.parent, follow_symlinks=False)
        need(stat.S_ISDIR(named.st_mode) and directory_core(opened) == item.baseline
             == directory_core(named) and full(opened) == full(named), 'GROUP_PIN_ANCESTOR_CHANGED')

    def _check_chain(self, directory):
        for path in reversed((directory, *directory.parents)):
            self._check_directory(path)

    def _directory(self, path):
        if path in self._directories:
            self._check_chain(path)
            return self._directories[path].fd
        parent = None if path == Path('/') else self._directory(path.parent)
        self.peak_fds = max(self.peak_fds, capacity(1, persistent=True))
        fd = os.open('/' if parent is None else path.name,
                     os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     **({} if parent is None else {'dir_fd': parent}))
        try:
            info = os.fstat(fd)
            need(stat.S_ISDIR(info.st_mode))
            record = _Directory(fd, parent, None if parent is None else path.name, directory_core(info))
            self._directories[path] = record
            self._check_chain(path)
        except BaseException as original:
            self._directories.pop(path, None)
            close_all((lambda: os.close(fd),), original)
            raise
        return fd

    def directory(self, path, *, owner):
        with self._lock:
            self._guard(owner, mutate=True)
            before = set(self._directories)
            try:
                return self._directory(path_value(path))
            except BaseException as original:
                self._rollback(set(self._leaves), before, self.raw_bytes, original)
                raise

    def _rollback(self, leaves, directories, raw_bytes, original):
        callbacks = []
        for path in reversed(list(self._leaves)):
            if path not in leaves:
                leaf = self._leaves.pop(path)
                callbacks.append(lambda fd=leaf.fd: os.close(fd))
        for path in reversed(list(self._directories)):
            if path not in directories:
                item = self._directories.pop(path)
                callbacks.append(lambda fd=item.fd: os.close(fd))
        self.raw_bytes = raw_bytes
        close_all(callbacks, original)

    def _check_leaf(self, leaf):
        self._check_chain(leaf.path.parent)
        opened = os.fstat(leaf.fd)
        named = os.stat(leaf.path.name, dir_fd=leaf.parent, follow_symlinks=False)
        need(stat.S_ISREG(named.st_mode) and full(opened) == leaf.baseline == full(named),
             'GROUP_PIN_FILE_CHANGED')

    def _view(self, leaf, owner, *, shared=False):
        view = object.__new__(PinView)
        view._pool, view._record, view._owner = self, leaf, owner
        view._thread, view._shared, view.closed = threading.get_ident(), shared, False
        self._views[view] = (leaf, owner, view._thread, shared)
        return view

    def acquire(self, path, checksum, maximum, *, owner):
        with self._lock:
            self._guard(owner, mutate=True)
            leaves, directories, raw_bytes = set(self._leaves), set(self._directories), self.raw_bytes
            try:
                return self._acquire(path, checksum, maximum, owner=owner)
            except BaseException as original:
                self._rollback(leaves, directories, raw_bytes, original)
                raise

    def _acquire(self, path, checksum, maximum, *, owner):
        with self._lock:
            self._guard(owner, mutate=True)
            path = path_value(path)
            need(type(checksum) is str and len(checksum) == 64
                 and all(c in '0123456789abcdef' for c in checksum)
                 and type(maximum) is int and maximum > 0)
            leaf = self._leaves.get(path)
            if leaf is not None:
                need(leaf.checksum == checksum and 0 < leaf.baseline[6] <= maximum,
                     'GROUP_PIN_EXPECTATION_CHANGED')
                self._check_leaf(leaf)
                return self._view(leaf, owner, shared=self.catalog)
            parent = self._directory(path.parent)
            self.peak_fds = max(self.peak_fds, capacity(1, persistent=True))
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                info = os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                     and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                     and 0 < info.st_size <= maximum, 'GROUP_PIN_FILE_TYPE')
                baseline = full(info)
                need(full(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == baseline,
                     'GROUP_PIN_FILE_CHANGED')
                need(self.raw_bytes + info.st_size <= MAX_RAW_BYTES, 'GROUP_PIN_RAW_LIMIT')
                chunks, size = [], 0
                while size <= maximum:
                    block = os.read(fd, min(65536, maximum + 1 - size))
                    if not block:
                        break
                    chunks.append(block)
                    size += len(block)
                raw = b''.join(chunks)
                need(size == info.st_size and sha256(raw).hexdigest() == checksum, 'GROUP_PIN_FILE_SHA')
                leaf = _Leaf(path, fd, parent, baseline, checksum, raw)
                self._check_leaf(leaf)
                self._leaves[path] = leaf
                self.raw_bytes += size
            except BaseException as original:
                close_all((lambda: os.close(fd),), original)
                raise
            return self._view(leaf, owner, shared=self.catalog)

    def seal(self, *, owner):
        with self._lock:
            self._guard(owner, mutate=True)
            need(self.catalog)
            self.check_all(owner=owner)
            self.sealed = True

    def borrow_existing(self, path, checksum, maximum, *, owner, borrower):
        with self._lock:
            self._guard(owner)
            need(self.catalog and self.sealed and borrower is not None, 'GROUP_PIN_BORROW_REQUIRED')
            leaf = self._leaves.get(path_value(path))
            need(leaf is not None and leaf.checksum == checksum and type(maximum) is int
                 and 0 < leaf.baseline[6] <= maximum, 'GROUP_PIN_BORROW_CHANGED')
            self._check_leaf(leaf)
            return self._view(leaf, borrower)

    def _check_view(self, view):
        with self._lock:
            self._guard(self.owner)
            need(type(view) is PinView and view in self._views and not view.closed
                 and view._pool is self and self._leaves.get(view._record.path) is view._record,
                 'GROUP_PIN_VIEW_CLOSED')
            facts = self._views[view]
            need(view._record is facts[0] and view._owner is facts[1]
                 and view._thread == facts[2] and view._shared is facts[3],
                 'GROUP_PIN_VIEW_CHANGED')
            need((view._shared and self.catalog and self.sealed)
                 or view._thread == threading.get_ident(), 'GROUP_PIN_THREAD')
            self._check_leaf(view._record)

    def _release_view(self, view):
        with self._lock:
            self._guard(self.owner)
            facts = self._views.get(view)
            need(facts is not None and view._pool is self and not view.closed
                 and (facts[3] or facts[2] == threading.get_ident()), 'GROUP_PIN_VIEW_CLOSED')
            view.closed = True
            self._views.pop(view, None)

    def check_all(self, *, owner):
        with self._lock:
            self._guard(owner)
            for path in self._directories:
                self._check_directory(path)
            # Already checked every ancestor once; do not recursively check_all
            # from every file/view and accidentally make collective fences N².
            for leaf in self._leaves.values():
                opened = os.fstat(leaf.fd)
                named = os.stat(leaf.path.name, dir_fd=leaf.parent, follow_symlinks=False)
                need(stat.S_ISREG(named.st_mode) and full(opened) == leaf.baseline == full(named),
                     'GROUP_PIN_FILE_CHANGED')

    def close(self, *, owner, original=None):
        with self._lock:
            if self.closed:
                return
            need(self.owner is owner and self.pid == os.getpid()
                 and self.thread == threading.get_ident(), 'GROUP_PIN_CLOSE_OWNER')
            self.closed = True
            for view in list(self._views):
                view.closed = True
            callbacks = [lambda fd=x.fd: os.close(fd) for x in reversed(list(self._leaves.values()))]
            callbacks += [lambda fd=x.fd: os.close(fd) for x in reversed(list(self._directories.values()))]
            self._views.clear()
            self._leaves.clear()
            self._directories.clear()
            self.raw_bytes = 0
            close_all(callbacks, original)


class CodePins:
    """Metadata-only mechanical checks. Full code_scope stays in full_guard."""
    def __init__(self, root, pool, *, owner):
        need(type(pool) is PinPool and not pool.catalog)
        self.pool, self.owner, self.root = pool, owner, path_value(root)
        self.thread, self.pid, self.closed = threading.get_ident(), os.getpid(), False
        self.parent = pool.directory(self.root, owner=owner)
        self.names = self._names()
        need(bool(self.names), 'GROUP_CODE_FILES_REQUIRED')
        self.baselines = {name: self._sample(name) for name in self.names}
        self.check()

    def _names(self):
        return tuple(sorted(name for name in os.listdir(self.parent) if name.endswith('.py')))

    def _sample(self, name):
        capacity(1, persistent=False)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'GROUP_CODE_FILE_TYPE')
            image = full(before)
            need(full(os.stat(name, dir_fd=self.parent, follow_symlinks=False)) == image
                 == full(os.fstat(fd)), 'GROUP_CODE_FILE_CHANGED')
        except BaseException as original:
            close_all((lambda: os.close(fd),), original)
            raise
        else:
            os.close(fd)
            return image

    def check(self):
        need(not self.closed and self.pid == os.getpid() and self.thread == threading.get_ident(),
             'GROUP_CODE_PIN_CLOSED')
        self.pool._guard(self.owner)
        self.pool._check_chain(self.root)
        need(self._names() == self.names, 'GROUP_CODE_FILE_SET_CHANGED')
        for name in self.names:
            need(self._sample(name) == self.baselines[name], 'GROUP_CODE_FILE_CHANGED')
        need(self._names() == self.names, 'GROUP_CODE_FILE_SET_CHANGED')
        self.pool._check_chain(self.root)
        return True

    def close(self):
        self.closed = True
