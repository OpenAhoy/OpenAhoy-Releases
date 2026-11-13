"""Bounded native byte observations, never USER/QA interpretation or authority.

Explicit full/loop delegates belong to the caller. This resource entry is not
a Group Gate, grant, trusted seal or cross-call current-source cache.

Shared-index SQL is point-in-time: unrelated row/WAL coordination writes are
not source changes. The final identity fence does not prove row stability or
exclude ABA after the last lookup SQL/guard. There is no atomic index seal.
"""
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import os
import re
import stat
import threading

from .draft_revision_native_source import (
    RegisteredSource, Record, SourceHold, MAX_PREFIX, MAX_SEGMENT, MAX_LINE,
    MAX_RECORDS, canonical, strict_json, registration_digest, _open_source,
    _regular, _metadata_origin,
)
from .draft_revision_native_lookup import NativeThreadLookup, valid_thread
from .draft_revision_stream import _RawReplay

MAX_SOURCES = 64
MAX_WINDOWS = 256
MAX_LOOKUPS = 64
_PATH = type(Path('/'))
_EMPTY = sha256(b'').hexdigest()
_CODES = frozenset('GROUP_STREAM_' + suffix for suffix in (
    'INPUT', 'RESOURCE', 'CURSOR', 'REVIEWED_PREFIX', 'RECORD', 'SOURCE_HOLD',
    'CALLBACK_HOLD', 'ENTRY_CLOSED', 'ENTRY_THREAD', 'ENTRY_REENTRANT',
    'ENTRY_SCOPE', 'CHANGED', 'INDEX_SCOPE', 'METADATA', 'REPLAY',
))


def _need(condition, suffix):
    if not condition:
        raise SourceHold('GROUP_STREAM_' + suffix)


def _hex(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def _source(source):
    _need(type(source) is RegisteredSource, 'INPUT')
    _need(type(source.path) is _PATH and source.path.is_absolute()
          and '..' not in source.path.parts and '\x00' not in str(source.path), 'INPUT')
    _need(all(type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value)
              for value in (source.source_id, source.thread_id)), 'INPUT')
    valid_thread(source.thread_id)
    _need(all(_hex(value) for value in (source.preceding_sha256, source.session_meta_sha256)), 'INPUT')
    _need(all(type(value) is int and value >= 0 for value in (source.device, source.inode,
          source.start_offset, source.start_ordinal, source.metadata_ordinal)), 'INPUT')
    _need(source.start_offset < MAX_PREFIX and source.metadata_ordinal <= source.start_ordinal < MAX_RECORDS,
          'INPUT')


def _snapshot_source(source):
    """Detach caller-owned frozen objects; Python freezing is not a seal."""
    _need(type(source) is RegisteredSource, 'INPUT')
    result = RegisteredSource(source.source_id, source.path, source.device,
        source.inode, source.thread_id, source.start_offset, source.start_ordinal,
        source.preceding_sha256, source.session_meta_sha256, source.metadata_ordinal)
    _source(result)
    object.__setattr__(result, 'path', Path(str(result.path)))
    return result


@dataclass(frozen=True)
class SourceWindow:
    source: RegisteredSource = field(repr=False)
    reviewed_end: int
    reviewed_prefix_sha256: str


@dataclass(frozen=True)
class SourceObservation:
    """Private raw records for a future parser; the summary is detached data."""
    summary_bytes: bytes = field(repr=False)
    records: tuple = field(repr=False)

    @property
    def summary(self):
        return strict_json(self.summary_bytes)


def _generation(info, *, structure=False):
    values = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
              info.st_nlink)
    if not structure:
        values += (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return values


class _Pin:
    def __init__(self, source, *, structure=False):
        self.source = source
        self.structure = structure
        self.fd, self.parent, self.name, self.descriptors, self.chain = _open_source(source)
        try:
            self.generation = _generation(os.fstat(self.fd), structure=structure)
            self.ancestors = tuple((pin, _generation(os.stat(name, dir_fd=parent,
                follow_symlinks=False))[:6]) for parent, name, pin in self.chain)
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        opened = os.fstat(self.fd)
        current = os.stat(self.name, dir_fd=self.parent, follow_symlinks=False)
        _regular(opened, self.source)
        _regular(current, self.source)
        _need(_generation(opened, structure=self.structure) == self.generation
              == _generation(current, structure=self.structure), 'CHANGED')
        for (parent, name, identity), (original, attributes) in zip(self.chain, self.ancestors):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            _need(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity == original
                  and _generation(info)[:6] == attributes, 'CHANGED')

    def close(self):
        descriptors, self.descriptors = self.descriptors, []
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _path_source(path):
    info = path.lstat()
    return RegisteredSource('group-index-pin', path, info.st_dev, info.st_ino,
                            'group-index-pin', 0, 0, _EMPTY, '0' * 64)


class _IndexPin:
    def __init__(self, path):
        self.main = _Pin(_path_source(path), structure=True)
        self.sides = {}
        try:
            self.format = os.pread(self.main.fd, 20, 0)
            _need(len(self.format) == 20 and self.format[:16] == b'SQLite format 3\x00', 'METADATA')
            for suffix in ('-wal', '-shm'):
                side = Path(str(path) + suffix)
                try:
                    side.lstat()
                except FileNotFoundError:
                    self.sides[suffix] = None
                else:
                    self.sides[suffix] = _Pin(_path_source(side), structure=True)
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        self.main.check()
        _need(os.pread(self.main.fd, 20, 0) == self.format, 'CHANGED')
        for suffix, pin in self.sides.items():
            if pin is not None:
                pin.check()
            else:
                try:
                    os.stat(self.main.name + suffix, dir_fd=self.main.parent, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise SourceHold('GROUP_STREAM_CHANGED')

    def close(self):
        for pin in self.sides.values():
            if pin is not None:
                pin.close()
        self.main.close()


def _base(source):
    return (source.source_id, source.path, source.device, source.inode,
            source.thread_id, source.session_meta_sha256, source.metadata_ordinal)


class NativeStreamEntry:
    """Single-thread, fixed-request observation resources; no authority."""
    def __init__(self, full, loop):
        _need(callable(full) and callable(loop), 'INPUT')
        self._full_callback, self._loop_callback = full, loop
        self._thread = threading.get_ident()
        self._closed = False
        self._poisoned = False
        self._busy = False
        self._pins = {}
        self._indices = {}
        self._request = None
        self._lookups = ()
        self._groups = ()
        self._observations = ()
        self._retained = 0
        self._record_count = 0

    def __enter__(self):
        self._live()
        return self

    def __exit__(self, *_):
        self.close()

    def _live(self):
        _need(not self._closed and not self._poisoned, 'ENTRY_CLOSED')
        _need(threading.get_ident() == self._thread, 'ENTRY_THREAD')

    def _callback(self, callback):
        self._live()
        try:
            result = callback()
        except BaseException:
            raise SourceHold('GROUP_STREAM_CALLBACK_HOLD') from None
        _need(result is True, 'CALLBACK_HOLD')
        self._live()
        return True

    def _full(self):
        return self._callback(self._full_callback)

    def _loop(self):
        return self._callback(self._loop_callback)

    def _pure_fence(self):
        for pin in self._pins.values():
            pin.check()
        for pin in self._indices.values():
            pin.check()

    def _locate(self):
        for source, _, lookup in self._groups:
            self._loop()
            self._pure_fence()
            current = lookup.locate(source.thread_id)
            _source(current)
            _need(_base(current) == _base(source), 'CHANGED')
            self._pure_fence()

    def _call(self, operation):
        try:
            self._live()
            _need(not self._busy, 'ENTRY_REENTRANT')
            self._busy = True
            return operation()
        except BaseException as error:
            self._poisoned = True
            self.close()
            code = (error.code if type(error) is SourceHold and type(error.code) is str
                    and error.code in _CODES else 'GROUP_STREAM_SOURCE_HOLD')
            raise SourceHold(code) from None
        finally:
            self._busy = False

    def close(self):
        self._closed = True
        self._observations = ()
        self._groups = ()
        self._lookups = ()
        self._request = None
        for pin in self._pins.values():
            pin.close()
        for pin in self._indices.values():
            pin.close()


def _prepare(entry, windows, lookups):
    _need(type(windows) is tuple and 0 < len(windows) <= MAX_WINDOWS
          and type(lookups) is tuple and 0 < len(lookups) <= MAX_LOOKUPS, 'RESOURCE')
    groups = {}
    physical = {}
    fixed_windows = []
    for window in windows:
        _need(type(window) is SourceWindow, 'INPUT')
        source = _snapshot_source(window.source)
        reviewed_end, reviewed_sha = window.reviewed_end, window.reviewed_prefix_sha256
        _need(type(reviewed_end) is int and source.start_offset < reviewed_end <= MAX_PREFIX
              and _hex(reviewed_sha), 'INPUT')
        window = SourceWindow(source, reviewed_end, reviewed_sha)
        fixed_windows.append(window)
        key = source.thread_id
        if key not in groups:
            _need(len(groups) < MAX_SOURCES, 'RESOURCE')
            identity = (source.device, source.inode)
            _need(identity not in physical, 'INDEX_SCOPE')
            physical[identity] = key
            groups[key] = (source, [])
        _need(_base(source) == _base(groups[key][0]), 'INDEX_SCOPE')
        groups[key][1].append(window)
    for lookup in lookups:
        _need(type(lookup) is NativeThreadLookup and type(lookup.state_path) is _PATH
              and type(lookup.session_root) is _PATH and type(lookup.owner_thread) is str
              and type(lookup.allowed_threads) is frozenset
              and 0 < len(lookup.allowed_threads) <= 2, 'INPUT')
        valid_thread(lookup.owner_thread)
        for thread in lookup.allowed_threads:
            _need(type(thread) is str, 'INPUT')
            valid_thread(thread)
    fixed = []
    for source, bound in groups.values():
        matches = [lookup for lookup in lookups if source.thread_id in lookup.allowed_threads]
        _need(len(matches) == 1, 'INDEX_SCOPE')
        fixed.append((source, tuple(bound), matches[0]))
    # Compare only already constrained primitive representations; never dataclass
    # wide equality or caller-controlled equality hooks.
    request = canonical({'windows': [{'registration': registration_digest(w.source),
        'end': w.reviewed_end, 'sha': w.reviewed_prefix_sha256} for w in fixed_windows],
        'lookups': [{'path': str(l.state_path), 'owner': l.owner_thread,
                     'threads': sorted(l.allowed_threads)} for l in lookups]})
    if entry._request is not None:
        _need(request == entry._request and len(lookups) == len(entry._lookups)
              and all(current is original for current, original in zip(lookups, entry._lookups)),
              'ENTRY_SCOPE')
        return False
    # All baselines precede the first callback/lookup worker. No later rebase.
    for source, _, _ in fixed:
        entry._pins[source.thread_id] = _Pin(source)
    for lookup in lookups:
        if lookup.state_path not in entry._indices:
            entry._indices[lookup.state_path] = _IndexPin(lookup.state_path)
    entry._groups = tuple(fixed)
    entry._request = request
    entry._lookups = lookups
    return True


def _pass(entry, source, windows, pin, replay, *, first):
    fd = pin.fd
    end = pin.generation[6]
    _need(0 < end <= MAX_PREFIX, 'RESOURCE')
    minimum = min(window.source.start_offset for window in windows)
    markers = {0, end}
    for window in windows:
        markers.update((window.source.start_offset, window.reviewed_end))
    hashes = {0: _EMPTY}
    ordinals = {}
    records = []
    whole = sha256()
    offset = 0
    count = 0
    os.lseek(fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(fd), 'rb', buffering=65536) as stream:
        while offset < end:
            entry._loop()
            raw = stream.readline(min(MAX_LINE + 1, end - offset + 1))
            _need(type(raw) is bytes and raw.endswith(b'\n') and 0 < len(raw) <= MAX_LINE
                  and offset + len(raw) <= end, 'RECORD')
            row = strict_json(raw, maximum=MAX_LINE)
            entry._loop()
            ordinal = source.metadata_ordinal + count
            _need(ordinal < MAX_RECORDS and type(row) is dict
                  and type(row.get('ordinal')) is int and row['ordinal'] == ordinal
                  and type(row.get('type')) is str and type(row.get('payload')) is dict, 'RECORD')
            if offset == 0:
                _need(sha256(raw).hexdigest() == source.session_meta_sha256
                      and row['type'] == 'session_meta'
                      and type(row['payload'].get('id')) is str
                      and row['payload']['id'] == source.thread_id, 'METADATA')
                _metadata_origin(row, source)
            if offset in markers:
                ordinals[offset] = ordinal
            whole.update(raw)
            if first:
                replay.capture(raw, entry._loop)
                entry._record_count += 1
                _need(entry._record_count <= MAX_RECORDS, 'RESOURCE')
                if offset >= minimum:
                    entry._retained += len(raw)
                    _need(entry._retained <= MAX_SEGMENT, 'RESOURCE')
                    records.append(Record(source.source_id, ordinal, offset, offset + len(raw),
                                          sha256(raw).hexdigest(), raw))
            else:
                replay.compare(raw, entry._loop)
            offset += len(raw)
            count += 1
            if offset in markers:
                hashes[offset] = whole.hexdigest()
            entry._loop()
    _need(offset == end and set(hashes) == markers, 'CURSOR')
    for window in windows:
        current = window.source
        _need(ordinals.get(current.start_offset) == current.start_ordinal
              and hashes[current.start_offset] == current.preceding_sha256, 'CURSOR')
        _need(hashes[window.reviewed_end] == window.reviewed_prefix_sha256, 'REVIEWED_PREFIX')
    if first:
        replay.seal()
    else:
        replay.finish(entry._loop)
    return whole.hexdigest(), count, tuple(records)


def _observe_one(entry, source, windows):
    pin = entry._pins[source.thread_id]
    _need(0 < pin.generation[6] <= MAX_PREFIX, 'RESOURCE')
    replay = _RawReplay(pin.generation[6])
    try:
        entry._full()
        entry._pure_fence()
        first = _pass(entry, source, windows, pin, replay, first=True)
        entry._full()
        entry._pure_fence()
        entry._full()
        second = _pass(entry, source, windows, pin, replay, first=False)
        entry._full()
        _need(first[:2] == second[:2], 'REPLAY')
        entry._pure_fence()
    finally:
        # Drop the entire per-source replay before another source is scanned.
        replay.blocks.clear()
        replay.pending.clear()
        replay.buffer = b''
    summary = canonical({'schema': 'GROUP_NATIVE_STREAM_OBSERVATION_V1', 'authority': False,
        'thread_sha256': sha256(source.thread_id.encode()).hexdigest(),
        'source_registration_sha256': registration_digest(source),
        'prefix_bytes': pin.generation[6], 'prefix_sha256': first[0], 'record_count': first[1],
        'windows_sha256': sha256(canonical([{'registration': registration_digest(w.source),
            'end': w.reviewed_end, 'sha': w.reviewed_prefix_sha256} for w in windows])).hexdigest(),
        'generation_sha256': sha256(canonical([str(x) for x in pin.generation])).hexdigest()})
    entry._full()
    entry._pure_fence()
    return SourceObservation(summary, first[2])


def observe(entry, windows, *, lookups):
    _need(type(entry) is NativeStreamEntry, 'INPUT')

    def operation():
        fresh = _prepare(entry, windows, lookups)
        entry._full()
        entry._pure_fence()
        entry._locate()
        if fresh:
            entry._observations = tuple(_observe_one(entry, source, bound)
                                        for source, bound, _ in entry._groups)
        entry._full()
        entry._locate()
        entry._pure_fence()
        return entry._observations
    return entry._call(operation)


def recheck(entry):
    _need(type(entry) is NativeStreamEntry, 'INPUT')

    def operation():
        _need(entry._request is not None, 'ENTRY_SCOPE')
        entry._pure_fence()
        entry._full()
        entry._locate()
        entry._pure_fence()
    return entry._call(operation)


def finish(entry):
    _need(type(entry) is NativeStreamEntry, 'INPUT')

    def operation():
        _need(entry._request is not None, 'ENTRY_SCOPE')
        entry._pure_fence()
        entry._full()
        entry._locate()
        result = entry._observations
        entry._pure_fence()  # Last shared fence: no callback/query after here.
        entry.close()
        return result
    return entry._call(operation)
