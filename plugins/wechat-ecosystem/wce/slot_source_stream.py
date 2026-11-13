"""Bounded work on a growing registered source; no cumulative byte quota.

Checkpoints are private ingestion facts, not permissions. The source owner must
persist a returned checkpoint and its interpreted facts atomically, and enforce
the native owner/index pointer before and after this call. Old prefix readers
and their evidence semantics are deliberately unchanged.
"""
from dataclasses import dataclass
from hashlib import sha256
import os
import stat

from .draft_revision_native_source import (
    RegisteredSource, Record, SourceHold, MAX_LINE, canonical, checked_guard,
    require, strict_json, registration_digest, _open_source, _regular, _first_line)
from .slot_native_lookup import metadata_origin


WORK_BYTES = 8 * 1024 * 1024
WORK_RECORDS = 50000
DOMAIN = 'WCE_NATIVE_SEGMENT_CHAIN_V1'


@dataclass(frozen=True)
class Checkpoint:
    registration_sha256: str
    offset: int
    next_ordinal: int
    chain_sha256: str
    previous_start: int
    previous_end: int
    previous_sha256: str


@dataclass(frozen=True)
class Segment:
    checkpoint: Checkpoint
    records: tuple
    captured_end: int
    state: str
    segment_sha256: str


def initial(source):
    require(type(source) is RegisteredSource and source.start_offset == 0
            and type(source.metadata_ordinal) is int and source.metadata_ordinal >= 0,
            'SLOT_SOURCE_REGISTRATION_INVALID')
    empty = sha256(b'').hexdigest()
    return Checkpoint(registration_digest(source), 0, source.metadata_ordinal,
                      empty, 0, 0, empty)


def _checkpoint(source, cursor):
    require(type(source) is RegisteredSource and type(cursor) is Checkpoint
            and cursor.registration_sha256 == registration_digest(source),
            'SLOT_SOURCE_CHECKPOINT_MISMATCH')
    for name in ('offset', 'next_ordinal', 'previous_start', 'previous_end'):
        value = getattr(cursor, name)
        require(type(value) is int and value >= 0, 'SLOT_SOURCE_CHECKPOINT_INVALID')
    require(cursor.previous_start <= cursor.previous_end == cursor.offset,
            'SLOT_SOURCE_CHECKPOINT_INVALID')
    require(cursor.previous_end - cursor.previous_start <= MAX_LINE,
            'SLOT_SOURCE_CHECKPOINT_INVALID')
    if cursor.offset:
        require(cursor.previous_start < cursor.previous_end
                and cursor.next_ordinal > source.metadata_ordinal,
                'SLOT_SOURCE_CHECKPOINT_INVALID')
    for name in ('registration_sha256', 'chain_sha256', 'previous_sha256'):
        value = getattr(cursor, name)
        require(type(value) is str and len(value) == 64
                and all(char in '0123456789abcdef' for char in value),
                'SLOT_SOURCE_CHECKPOINT_INVALID')
    if cursor.offset == 0:
        require(cursor == initial(source), 'SLOT_SOURCE_CHECKPOINT_INVALID')


def _range(fd, start, end, guard):
    os.lseek(fd, start, os.SEEK_SET)
    output = bytearray()
    while start + len(output) < end:
        checked_guard(guard)
        part = os.read(fd, min(65536, end - start - len(output)))
        require(bool(part), 'SOURCE_TRUNCATED')
        output.extend(part)
    checked_guard(guard)
    return bytes(output)


def _anchors(fd, source, cursor, first, captured_end, guard):
    require(_first_line(fd, captured_end, guard) == first, 'SOURCE_META_CHANGED')
    if cursor.offset:
        previous = _range(fd, cursor.previous_start, cursor.previous_end, guard)
        require(sha256(previous).hexdigest() == cursor.previous_sha256
                and previous.endswith(b'\n'), 'SLOT_SOURCE_PREVIOUS_SEGMENT_CHANGED')


def read_next(source, cursor, guard, *, work_bytes=WORK_BYTES, work_records=WORK_RECORDS):
    """Double-read the next complete-line segment, retaining at most one batch.

    Smaller work settings change only batching. They cannot skip records or
    establish a completion. A line may use the existing native line envelope;
    this is not a full-history or daily business capacity limit.
    """
    _checkpoint(source, cursor)
    require(type(work_bytes) is int and 1 <= work_bytes <= WORK_BYTES
            and type(work_records) is int and 1 <= work_records <= WORK_RECORDS,
            'SLOT_SOURCE_WORK_INVALID')
    checked_guard(guard)
    fd, parent, name, descriptors, ancestors = _open_source(source)
    try:
        captured_end = os.fstat(fd).st_size
        require(captured_end >= cursor.offset and captured_end > 0, 'SOURCE_TRUNCATED')
        first = _first_line(fd, captured_end, guard)
        require(sha256(first).hexdigest() == source.session_meta_sha256, 'SOURCE_META_CHANGED')
        meta = strict_json(first, maximum=MAX_LINE)
        require(metadata_origin(meta, source.thread_id) == source.metadata_ordinal,
                'SOURCE_META_INVALID')
        _anchors(fd, source, cursor, first, captured_end, guard)
        if cursor.offset == captured_end:
            raw = b''
        else:
            limit = min(captured_end, cursor.offset + work_bytes)
            raw = _range(fd, cursor.offset, limit, guard)
            boundary = raw.rfind(b'\n')
            # A batch boundary cannot turn a valid long record into a quota.
            # Extend only to finish its first line, within the existing codec.
            while boundary < 0 and limit < captured_end and len(raw) < MAX_LINE:
                extra_end = min(captured_end, cursor.offset + MAX_LINE, limit + 65536)
                raw += _range(fd, limit, extra_end, guard)
                limit = extra_end
                boundary = raw.find(b'\n')
            if boundary < 0:
                require(len(raw) < MAX_LINE, 'SOURCE_LINE_LIMIT')
                raw = b''
            else:
                raw = raw[:boundary + 1]
        rows = []
        position = cursor.offset
        for line in raw.splitlines(keepends=True):
            if len(rows) == work_records:
                break
            checked_guard(guard)
            require(line.endswith(b'\n') and len(line) <= MAX_LINE, 'SOURCE_LINE_LIMIT')
            value = strict_json(line, maximum=MAX_LINE)
            ordinal = cursor.next_ordinal + len(rows)
            require(type(value) is dict and type(value.get('ordinal')) is int
                    and value['ordinal'] == ordinal and type(value.get('type')) is str
                    and type(value.get('payload')) is dict, 'SOURCE_RECORD_INVALID')
            rows.append(Record(source.source_id, ordinal, position,
                               position + len(line), sha256(line).hexdigest(), line))
            position += len(line)
        raw = raw[:position - cursor.offset]
        if raw and cursor.offset == 0:
            require(raw.split(b'\n', 1)[0] + b'\n' == first, 'SOURCE_META_CHANGED')
        require(_range(fd, cursor.offset, position, guard) == raw, 'SOURCE_PREFIX_CHANGED')
        _anchors(fd, source, cursor, first, captured_end, guard)
        _regular(os.fstat(fd), source)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        _regular(current, source)
        require(current.st_size >= captured_end, 'SOURCE_TRUNCATED')
        for ancestor, entry, identity in ancestors:
            info = os.stat(entry, dir_fd=ancestor, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity,
                    'SOURCE_ANCESTOR_CHANGED')
        checked_guard(guard)
        segment_sha = sha256(raw).hexdigest()
        if raw:
            chain = sha256(canonical({'domain': DOMAIN, 'previous': cursor.chain_sha256,
                'registration_sha256': cursor.registration_sha256,
                'byte_start': cursor.offset, 'byte_end': position,
                'first_ordinal': cursor.next_ordinal,
                'next_ordinal': cursor.next_ordinal + len(rows),
                'segment_sha256': segment_sha})).hexdigest()
            next_cursor = Checkpoint(cursor.registration_sha256, position,
                cursor.next_ordinal + len(rows), chain, cursor.offset, position, segment_sha)
        else:
            next_cursor = cursor
        state = ('CURRENT' if position == current.st_size else
                 'SCANNING' if current.st_size > captured_end or raw else
                 'SOURCE_TAIL_INCOMPLETE')
        return Segment(next_cursor, tuple(rows), captured_end, state, segment_sha)
    except OSError:
        raise SourceHold('SOURCE_READ_HOLD') from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
