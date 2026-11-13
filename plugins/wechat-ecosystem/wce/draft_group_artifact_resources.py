"""Producer-artifact-only vnode pins; candidate, never source/role authority.

The two reviewed inventory consumers issue selections. A selection does not
replace any semantic/QA/current check. Other PinnedFile categories stay held.
"""
from dataclasses import dataclass
from hashlib import sha256
import inspect
import mmap
import os
from pathlib import Path
import stat
import sys
import threading
import time

from .draft_group_pin_resources import PinPool, need, full, path_value, capacity, close_all

MAX_MAPS = 512
MAX_VM = 64 * 1024 * 1024
MAX_RAW = 64 * 1024 * 1024
_MEDIA = ('text/html', 'application/json', 'image/png', 'image/jpeg')
_MMAP_TYPE = mmap.mmap


class _Quota:
    """Only process aggregate accounting, no paths/FDs/authorization objects."""
    def __init__(self):
        self.pid = os.getpid()
        self.lock = threading.RLock()
        self.count = self.vm = self.raw = 0

    def reserve(self, size):
        page = mmap.PAGESIZE
        rounded = ((size + page - 1) // page) * page
        with self.lock:
            need(self.pid == os.getpid(), 'GROUP_ARTIFACT_QUOTA_FORK')
            need(self.count + 1 <= MAX_MAPS and self.vm + rounded <= MAX_VM
                 and self.raw + size <= MAX_RAW, 'GROUP_ARTIFACT_MAPPING_LIMIT')
            self.count += 1
            self.vm += rounded
            self.raw += size
        return (rounded, size)

    def release(self, charge):
        with self.lock:
            need(self.pid == os.getpid() and self.count > 0
                 and self.vm >= charge[0] and self.raw >= charge[1], 'GROUP_ARTIFACT_QUOTA_CHANGED')
            self.count -= 1
            self.vm -= charge[0]
            self.raw -= charge[1]

    def snapshot(self):
        with self.lock:
            need(self.pid == os.getpid(), 'GROUP_ARTIFACT_QUOTA_FORK')
            return {'count': self.count, 'vm': self.vm, 'raw': self.raw}


_QUOTA = _Quota()


@dataclass
class _Record:
    path: Path
    parent: int
    baseline: tuple
    checksum: str
    raw: bytes
    mapping: object
    charge: tuple


class _Selection:
    __slots__ = ()
    def __init__(self, *args, **kwargs):
        need(False, 'GROUP_ARTIFACT_SELECTION_ISSUER_REQUIRED')


class ArtifactView:
    __slots__ = ('_resources', 'closed')
    def __init__(self, *args, **kwargs):
        need(False, 'GROUP_ARTIFACT_VIEW_ISSUER_REQUIRED')

    def check(self):
        return self._resources._check_view(self)

    @property
    def raw(self):
        return self._resources._checked_record(self).raw

    @property
    def sha(self):
        return self._resources._checked_record(self).checksum

    @property
    def pin(self):
        # Keep original PinnedFile's public file_state6 representation.
        value = self._resources._checked_record(self).baseline
        return (value[0], value[1], value[6], value[7], value[8], value[5])

    def close(self):
        self._resources._release_view(self)


class ArtifactResources:
    """Explicit same-entry resource owner, borrowing its held ancestor pool.

    No destructor, ambient entry lookup, public path/role or mapped flag. The
    caller owns final fences and closes this owner before the ancestor pool.
    """
    def __init__(self, pool, *, owner):
        need(type(pool) is PinPool and not pool.catalog, 'GROUP_ARTIFACT_POOL_REQUIRED')
        pool._guard(owner)
        self.pool, self.owner = pool, owner
        self.pid, self.thread = os.getpid(), threading.get_ident()
        self.closed, self.poisoned = False, False
        self._failed = []
        self._records, self._views, self._selections = {}, {}, {}
        self.mapping_seconds = 0.0

    def _guard(self):
        need(not self.closed and not self.poisoned and self.pid == os.getpid()
             and self.thread == threading.get_ident(), 'GROUP_ARTIFACT_OWNER_CLOSED')
        self.pool._guard(self.owner)

    def selection(self, inventory, roots):
        """Only the original two accepted-inventory loops can issue a selector."""
        self._guard()
        frame = inspect.currentframe().f_back
        try:
            accepted = False
            module = sys.modules.get('wce.draft_group_host_review')
            cls = getattr(module, 'GroupInputAdapter', None)
            method = getattr(cls, 'inspect_in', None)
            if method is not None and frame.f_code is method.__code__ and frame.f_globals is vars(module):
                adapter = frame.f_locals.get('self')
                host = getattr(adapter, 'host', None)
                from .draft_group_operator_semantics import is_operator
                exact_inventory=(inventory==host.chain.artifact_inventory
                    if host is not None and is_operator(host) else
                    host is not None and inventory is host.chain.semantic['artifact_inventory'])
                accepted = (type(adapter) is cls and host is not None
                            and exact_inventory
                            and roots is adapter.roots)
            module = sys.modules.get('wce.draft_group_host_native_v2')
            method = getattr(module, 'read_native_v2_review_materials_in', None)
            if method is not None and frame.f_code is method.__code__ and frame.f_globals is vars(module):
                semantic = frame.f_locals.get('semantic')
                pins = frame.f_locals.get('pins')
                accepted = (type(semantic) is dict and inventory is semantic.get('artifact_inventory')
                            and pins is not None and roots is pins.artifact_roots)
            module = sys.modules.get('wce.draft_group_operator_review_chain')
            method = getattr(module,'read_operator_review_materials_in',None)
            if method is not None and frame.f_code is method.__code__ and frame.f_globals is vars(module):
                values=frame.f_locals.get('values');pins=frame.f_locals.get('pins')
                from .draft_group_operator_review_chain import FixedOperatorHostPins
                accepted=(type(values) is dict and inventory is values.get('artifact_inventory')
                          and type(pins) is FixedOperatorHostPins and roots is pins.artifact_roots)
            need(accepted, 'GROUP_ARTIFACT_INVENTORY_ISSUER_REQUIRED')
        finally:
            del frame
        return self._new_selection(inventory, roots)

    def _new_selection(self, inventory, roots):
        # Private data-plane builder; the production entry is selection above.
        self._guard()
        need(type(inventory) is list and 0 < len(inventory) <= 3072,
             'GROUP_ARTIFACT_INVENTORY_REQUIRED')
        pairs = tuple(roots.items()) if type(roots) is dict else roots
        need(type(pairs) is tuple and pairs and len({x[0] for x in pairs}) == len(pairs),
             'GROUP_ARTIFACT_ROOTS_REQUIRED')
        root_map = {key: path_value(path) for key, path in pairs}
        specs = []
        for spec in inventory:
            need(type(spec) is dict and set(spec) == {'root_sha', 'relative_path', 'sha256', 'size', 'media_type'},
                 'GROUP_ARTIFACT_SPEC_REQUIRED')
            root = root_map.get(spec['root_sha'])
            checksum, relative, size, media = (spec[k] for k in ('sha256', 'relative_path', 'size', 'media_type'))
            need(root is not None and type(checksum) is str and len(checksum) == 64
                 and all(c in '0123456789abcdef' for c in checksum)
                 and type(relative) is str and ':' not in relative
                 and 0 < len(relative.split('/')) <= 32
                 and all(x not in ('', '.', '..') for x in relative.split('/'))
                 and media in _MEDIA and type(size) is int
                 and 0 < size <= (4 if media == 'text/html' else 2) * 1024 * 1024,
                 'GROUP_ARTIFACT_SPEC_REQUIRED')
            path = path_value(root / relative)
            need(path.is_relative_to(root), 'GROUP_ARTIFACT_ROOT_CHANGED')
            specs.append((path, checksum, size, media))
        selection = object.__new__(_Selection)
        self._selections[selection] = tuple(specs)
        return selection

    def acquire(self, selection, index, maximum):
        self._guard()
        specs = self._selections.get(selection)
        need(specs is not None and type(index) is int and 0 <= index < len(specs),
             'GROUP_ARTIFACT_SELECTION_CHANGED')
        path, checksum, size, media = specs[index]
        need(type(maximum) is int and 0 < size <= maximum
             <= (4 if media == 'text/html' else 2) * 1024 * 1024,
             'GROUP_ARTIFACT_MAXIMUM')
        record = self._records.get(path)
        if record is None:
            record = self._open(path, checksum, size, maximum)
            self._records[path] = record
        need(record.checksum == checksum and record.baseline[6] == size
             and size <= maximum, 'GROUP_ARTIFACT_EXPECTATION_CHANGED')
        self._check_record(record)
        view = object.__new__(ArtifactView)
        view._resources, view.closed = self, False
        self._views[view] = record
        return view

    def _open(self, path, checksum, size, maximum):
        parent = self.pool.directory(path.parent, owner=self.owner)
        capacity(1, persistent=False)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        mapping, charge, raw = None, None, b''
        def cleanup_map():
            try:
                if mapping is not None:
                    mapping.close()
            finally:
                if charge is not None:
                    if mapping is None or mapping.closed:
                        _QUOTA.release(charge)
                    else:
                        # Keep live map/raw and its charge reachable; this owner
                        # is poisoned until explicit close can really unmap it.
                        self._failed.append((mapping, charge, raw))
                        self.poisoned = True
        try:
            info = os.fstat(fd)
            baseline = full(info)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                 and info.st_size == size and 0 < size <= maximum,
                 'GROUP_ARTIFACT_FILE_TYPE')
            need(full(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == baseline,
                 'GROUP_ARTIFACT_FILE_CHANGED')
            charge = _QUOTA.reserve(size)
            parts, count = [], 0
            while count <= size:
                block = os.read(fd, min(65536, size + 1 - count))
                if not block:
                    break
                parts.append(block)
                count += len(block)
            raw = b''.join(parts)
            need(count == size and sha256(raw).hexdigest() == checksum, 'GROUP_ARTIFACT_FILE_SHA')
            started = time.monotonic()
            mapping = mmap.mmap(fd, size, access=mmap.ACCESS_READ, trackfd=False)
            self.mapping_seconds += time.monotonic() - started
            need(full(os.fstat(fd)) == baseline
                 == full(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                 'GROUP_ARTIFACT_FILE_CHANGED')
            record = _Record(path, parent, baseline, checksum, raw, mapping, charge)
        except BaseException as original:
            callbacks = [cleanup_map, lambda: os.close(fd)]
            close_all(callbacks, original)
            raise
        else:
            try:
                os.close(fd)
            except BaseException as original:
                close_all((cleanup_map,), original)
                raise
            return record

    def _check_record(self, record, *, ancestors=True):
        need(type(record.mapping) is _MMAP_TYPE and not record.mapping.closed,
             'GROUP_ARTIFACT_MAPPING_CLOSED')
        if ancestors:
            self.pool._check_chain(record.path.parent)
        capacity(1, persistent=False)
        fd = os.open(record.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=record.parent)
        try:
            before = full(os.fstat(fd))
            named = full(os.stat(record.path.name, dir_fd=record.parent, follow_symlinks=False))
            need(before == record.baseline == named == full(os.fstat(fd))
                 == full(os.stat(record.path.name, dir_fd=record.parent, follow_symlinks=False)),
                 'GROUP_ARTIFACT_FILE_CHANGED')
        except BaseException as original:
            close_all((lambda: os.close(fd),), original)
            raise
        else:
            os.close(fd)

    def _checked_record(self, view):
        self._guard()
        record = self._views.get(view)
        need(type(view) is ArtifactView and view._resources is self
             and record is not None and not view.closed, 'GROUP_ARTIFACT_VIEW_CLOSED')
        self._check_record(record)
        return record

    def _check_view(self, view):
        self._checked_record(view)
        return True

    def _release_view(self, view):
        if view.closed:
            return
        self._guard()
        need(view in self._views and view._resources is self, 'GROUP_ARTIFACT_VIEW_CLOSED')
        self._views.pop(view)
        view.closed = True

    def check_all(self):
        self._guard()
        for path in self.pool._directories:
            self.pool._check_directory(path)
        for record in self._records.values():
            self._check_record(record, ancestors=False)

    def close(self, *, original=None):
        need(self.pid == os.getpid() and self.thread == threading.get_ident(),
             'GROUP_ARTIFACT_CLOSE_OWNER')
        self.closed = True
        for view in self._views:
            view.closed = True
        self._views.clear()
        self._selections.clear()
        callbacks = []
        for path, record in reversed(list(self._records.items())):
            def close_record(path=path, record=record):
                try:
                    record.mapping.close()
                finally:
                    # A genuine munmap failure keeps the quota and record for
                    # explicit retry; never account an unclosed map as freed.
                    if record.mapping.closed:
                        _QUOTA.release(record.charge)
                        self._records.pop(path, None)
            callbacks.append(close_record)
        for pending in tuple(self._failed):
            mapping, charge, raw = pending
            def close_pending(pending=pending, mapping=mapping, charge=charge):
                try:
                    mapping.close()
                finally:
                    if mapping.closed:
                        _QUOTA.release(charge)
                        self._failed.remove(pending)
            callbacks.append(close_pending)
        close_all(callbacks, original)
