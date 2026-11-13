"""Bounded native-source reads; no QA authority, registration or business I/O.

Paths and cursors must originate from the trusted host's source lookup. These
objects are ordinary same-UID integrity checks, not secrets or a sandbox.
"""
from asyncio import CancelledError
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat

MAX_PREFIX = 1024 * 1024 * 1024
MAX_SEGMENT = 64 * 1024 * 1024
MAX_LINE = 32 * 1024 * 1024
MAX_RECORDS = 500000
MAX_SAFE_INT = 2**53 - 1


class SourceHold(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise SourceHold(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def checked_guard(guard):
    """New host-adapter contract: exact True, or a fixed failure without detail."""
    require(callable(guard), 'SOURCE_GUARD_HOLD')
    try:
        accepted = guard()
    except (Exception, CancelledError):
        raise SourceHold('SOURCE_GUARD_HOLD') from None
    require(accepted is True, 'SOURCE_GUARD_HOLD')


def strict_json(raw, *, maximum=256 * 1024, nodes=100000, depth=64):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, "SOURCE_JSON_LIMIT")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "SOURCE_JSON_DUPLICATE")
            result[key] = value
        return result

    def bad(_):
        raise SourceHold("SOURCE_JSON_NUMBER")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=bad)
        remaining = nodes

        def visit(item, level):
            nonlocal remaining
            remaining -= 1
            require(remaining >= 0 and level <= depth, "SOURCE_JSON_LIMIT")
            kind = type(item)
            if kind is dict:
                for key, child in item.items():
                    visit(key, level + 1)
                    visit(child, level + 1)
            elif kind is list:
                for child in item:
                    visit(child, level + 1)
            elif kind is int:
                require(abs(item) <= MAX_SAFE_INT, "SOURCE_JSON_NUMBER")
            elif kind is float:
                require(math.isfinite(item), "SOURCE_JSON_NUMBER")
            elif kind is str:
                item.encode("utf-8")
            else:
                require(kind in (bool, type(None)), "SOURCE_JSON_TYPE")

        visit(value, 0)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise SourceHold("SOURCE_JSON_INVALID") from None


@dataclass(frozen=True)
class RegisteredSource:
    """Private host lookup result, never accepted as a serialized tool argument."""
    source_id: str
    path: Path = field(repr=False)
    device: int
    inode: int
    thread_id: str
    start_offset: int
    start_ordinal: int
    preceding_sha256: str
    session_meta_sha256: str
    metadata_ordinal: int = 0


@dataclass(frozen=True)
class Record:
    source_id: str
    ordinal: int
    byte_start: int
    byte_end: int
    raw_line_sha256: str
    raw_line: bytes = field(repr=False)

    def __post_init__(self):
        require(type(self.raw_line) is bytes and self.raw_line.endswith(b"\n")
                and len(self.raw_line) <= MAX_LINE
                and self.byte_end - self.byte_start == len(self.raw_line)
                and sha256(self.raw_line).hexdigest() == self.raw_line_sha256,
                "SOURCE_RECORD_BYTES_CHANGED")

    @property
    def value(self):
        # Return a detached parse, so a caller cannot mutate the retained source
        # object after it has been hashed and before another validation step.
        return strict_json(self.raw_line, maximum=MAX_LINE)

    def reference(self):
        return {"source_id": self.source_id, "ordinal": self.ordinal,
                "byte_start": self.byte_start, "byte_end": self.byte_end,
                "raw_line_sha256": self.raw_line_sha256}


@dataclass(frozen=True)
class PrefixRead:
    source: RegisteredSource = field(repr=False)
    prefix_bytes: int
    prefix_sha256: str
    session_meta: Record = field(repr=False)
    records: tuple[Record, ...] = field(repr=False)


def _identity(info):
    return info.st_dev, info.st_ino


def _regular(info, source):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and _identity(info) == (source.device, source.inode),
            "SOURCE_IDENTITY_CHANGED")


def _open_source(source):
    require(type(source) is RegisteredSource, "UNREGISTERED_NATIVE_SOURCE")
    require(isinstance(source.path, Path), "SOURCE_PATH_INVALID")
    path = Path(source.path)
    require(path.is_absolute() and ".." not in path.parts and "\x00" not in str(path),
            "SOURCE_PATH_INVALID")
    descriptors, chain = [], []
    try:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(parent)
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
            descriptors.append(child)
            chain.append((parent, name, _identity(os.fstat(child))))
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        descriptors.append(fd)
        _regular(os.fstat(fd), source)
        return fd, parent, path.name, descriptors, chain
    except (OSError, SourceHold):
        for fd in reversed(descriptors):
            os.close(fd)
        raise SourceHold("SOURCE_OPEN_HOLD") from None


def _read_exact(fd, size):
    result = bytearray()
    while len(result) < size:
        part = os.read(fd, min(2 * 1024 * 1024, size - len(result)))
        require(bool(part), "SOURCE_TRUNCATED")
        result.extend(part)
    return bytes(result)


def _read_prefix(fd, end, start, guard):
    """Hash the complete prefix, retaining only the bounded target segment."""
    os.lseek(fd, 0, os.SEEK_SET)
    whole, preceding, segment = sha256(), sha256(), bytearray()
    offset = 0
    while offset < end:
        checked_guard(guard)
        part = os.read(fd, min(2 * 1024 * 1024, end - offset))
        require(bool(part), "SOURCE_TRUNCATED")
        whole.update(part)
        if offset < start:
            preceding.update(part[:min(len(part), start - offset)])
        if offset + len(part) > start:
            segment.extend(part[max(0, start - offset):])
        offset += len(part)
    checked_guard(guard)
    return whole.hexdigest(), preceding.hexdigest(), bytes(segment)


def _first_line(fd, end_offset, guard):
    os.lseek(fd, 0, os.SEEK_SET)
    first = bytearray()
    maximum = min(MAX_LINE, end_offset)
    while not first.endswith(b"\n"):
        checked_guard(guard)
        require(len(first) < maximum, "SOURCE_META_LIMIT")
        part = os.read(fd, min(65536, maximum - len(first)))
        require(bool(part), "SOURCE_TRUNCATED")
        newline = part.find(b"\n")
        first.extend(part if newline < 0 else part[:newline + 1])
    checked_guard(guard)
    return bytes(first)


def _metadata_origin(meta,source):
    require(type(source.metadata_ordinal) is int and 0<=source.metadata_ordinal<MAX_RECORDS,
            'SOURCE_META_INVALID')
    if source.metadata_ordinal:
        data=meta['payload'];base=data.get('history_base')
        require(data.get('history_mode')=='paginated' and type(base) is dict
            and set(base)=={'end_byte_offset','end_ordinal_exclusive','thread_id'}
            and base['thread_id']==source.thread_id
            and type(base['end_ordinal_exclusive']) is int
            and base['end_ordinal_exclusive']==source.metadata_ordinal
            and type(base['end_byte_offset']) is int and base['end_byte_offset']>=0,
            'SOURCE_HISTORY_BASE_UNVERIFIED')


def read_prefix(source, end_offset, guard):
    """Read a host-selected complete-line prefix, allowing legitimate appends.

    Every guard runs after expensive reads too. No source bytes are persisted;
    callers store only hashes, registered handles and bounded record references.
    """
    require(type(source) is RegisteredSource, "UNREGISTERED_NATIVE_SOURCE")
    require(type(source.metadata_ordinal) is int and 0 <= source.metadata_ordinal < MAX_RECORDS, "SOURCE_META_INVALID")
    require(all(type(v) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", v)
                for v in (source.source_id, source.thread_id))
            and all(type(v) is str and re.fullmatch(r"[a-f0-9]{64}", v)
                    for v in (source.preceding_sha256, source.session_meta_sha256))
            and all(type(v) is int and v >= 0 for v in (source.device, source.inode)),
            "SOURCE_REGISTRATION_INVALID")
    require(type(end_offset) is int and type(source.start_offset) is int
            and type(source.start_ordinal) is int
            and 0 <= source.start_offset < end_offset
            and end_offset - source.start_offset <= MAX_SEGMENT
            and 0 <= source.start_ordinal < MAX_RECORDS, "SOURCE_PREFIX_LIMIT")
    checked_guard(guard)
    fd, parent, name, descriptors, chain = _open_source(source)
    try:
        require(os.fstat(fd).st_size >= end_offset, "SOURCE_TRUNCATED")
        if source.start_offset:
            os.lseek(fd, source.start_offset - 1, os.SEEK_SET)
            require(_read_exact(fd, 1) == b"\n", "SOURCE_CURSOR_NOT_LINE_BOUNDARY")
        first = _first_line(fd, end_offset, guard)
        require(sha256(first).hexdigest() == source.session_meta_sha256,
                "SOURCE_META_CHANGED")
        meta = strict_json(bytes(first), maximum=MAX_LINE)
        require(type(meta) is dict and meta.get("ordinal") == source.metadata_ordinal
                and type(meta.get("ordinal")) is int
                and meta.get("type") == "session_meta"
                and type(meta.get("payload")) is dict
                and meta["payload"].get("id") == source.thread_id, "SOURCE_META_INVALID")
        _metadata_origin(meta,source)
        if source.start_offset==0:
            require(source.start_ordinal==source.metadata_ordinal,"SOURCE_META_INVALID")
        full_sha, before_sha, segment = _read_prefix(fd, end_offset,
                                                    source.start_offset, guard)
        require(before_sha == source.preceding_sha256, "SOURCE_CURSOR_CHANGED")
        require(segment.endswith(b"\n"), "SOURCE_INCOMPLETE_LINE")
        if source.start_offset == 0:
            require(segment.split(b"\n", 1)[0] + b"\n" == first,
                    "SOURCE_META_CHANGED")
        records, offset = [], source.start_offset
        for line in segment.splitlines(keepends=True):
            require(line.endswith(b"\n") and len(line) <= MAX_LINE,
                    "SOURCE_LINE_LIMIT")
            value = strict_json(line, maximum=MAX_LINE)
            ordinal = source.start_ordinal + len(records)
            require(ordinal < MAX_RECORDS and type(value) is dict
                    and type(value.get("ordinal")) is int
                    and value["ordinal"] == ordinal
                    and type(value.get("type")) is str
                    and type(value.get("payload")) is dict, "SOURCE_RECORD_INVALID")
            records.append(Record(source.source_id, ordinal, offset,
                                  offset + len(line), sha256(line).hexdigest(), line))
            offset += len(line)
        require(offset == end_offset and bool(records), "SOURCE_RANGE_INVALID")
        # Re-read precisely N bytes. Appended bytes and mtime changes are allowed;
        # prefix edits, truncation, unlink/rotation and ancestor swaps are not.
        repeated, repeated_before, repeated_segment = _read_prefix(
            fd, end_offset, source.start_offset, guard)
        require((repeated, repeated_before, repeated_segment) ==
                (full_sha, before_sha, segment), "SOURCE_PREFIX_CHANGED")
        require(_first_line(fd, end_offset, guard) == first, "SOURCE_META_CHANGED")
        _regular(os.fstat(fd), source)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        _regular(current, source)
        require(current.st_size >= end_offset, "SOURCE_TRUNCATED")
        for ancestor, entry, identity in chain:
            info = os.stat(entry, dir_fd=ancestor, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and _identity(info) == identity,
                    "SOURCE_ANCESTOR_CHANGED")
        checked_guard(guard)
        meta_record = Record(source.source_id, source.metadata_ordinal, 0, len(first),
                             sha256(first).hexdigest(), bytes(first))
        result = PrefixRead(source, end_offset, full_sha, meta_record, tuple(records))
    except OSError:
        raise SourceHold("SOURCE_READ_HOLD") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    checked_guard(guard)
    return result


def registration_digest(source):
    require(type(source) is RegisteredSource, 'UNREGISTERED_NATIVE_SOURCE')
    return digest({'source_id':source.source_id, 'path_sha256':sha256(str(source.path).encode()).hexdigest(),
        'device':source.device,'inode':source.inode,'thread_id':source.thread_id,
        'start_offset':source.start_offset,'start_ordinal':source.start_ordinal,
        'preceding_sha256':source.preceding_sha256,'session_meta_sha256':source.session_meta_sha256,
        'metadata_ordinal':source.metadata_ordinal})


def read_current_prefix(source,guard):
    """Host-selected complete current prefix, never a caller-selected old N.

    Legitimate append after capture is allowed; later resolve/consume must read
    a fresh suffix. This is an observed prefix, not atomic future-event control.
    A partial final line HOLDs rather than being silently excluded.
    """
    checked_guard(guard)
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        end=os.fstat(fd).st_size
        require(source.start_offset<end,'SOURCE_PREFIX_LIMIT')
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
    checked_guard(guard)
    return read_prefix(source,end,guard)


def verify_registered_cursor(source,guard):
    """Verify pre-spawn registration bytes/identity even before a suffix exists."""
    require(type(source) is RegisteredSource and type(source.start_offset) is int
        and type(source.start_ordinal) is int and 0<source.start_offset
        and 0<source.start_ordinal<MAX_RECORDS,'SOURCE_CURSOR_INVALID')
    checked_guard(guard)
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        end=source.start_offset
        require(os.fstat(fd).st_size>=end,'SOURCE_TRUNCATED')
        first=_first_line(fd,end,guard)
        meta=strict_json(first,maximum=MAX_LINE)
        require(sha256(first).hexdigest()==source.session_meta_sha256
            and type(meta) is dict and type(meta.get('ordinal')) is int and meta['ordinal']==source.metadata_ordinal
            and meta.get('type')=='session_meta' and type(meta.get('payload')) is dict
            and meta['payload'].get('id')==source.thread_id,'SOURCE_META_CHANGED')
        _metadata_origin(meta,source)
        whole,before,segment=_read_prefix(fd,end,end,guard)
        require(whole==before==source.preceding_sha256 and segment==b'','SOURCE_CURSOR_CHANGED')
        # Only retain a bounded tail to verify the prior native ordinal; hash
        # the complete earlier prefix without copying its private contents.
        start=max(0,end-MAX_LINE)
        os.lseek(fd,start,os.SEEK_SET);tail=_read_exact(fd,end-start)
        require(tail.endswith(b'\n'),'SOURCE_CURSOR_NOT_LINE_BOUNDARY')
        lines=tail.splitlines(keepends=True)
        require(bool(lines) and (start==0 or len(lines)>=2),'SOURCE_LINE_LIMIT')
        previous=strict_json(lines[-1],maximum=MAX_LINE)
        require(type(previous) is dict and type(previous.get('ordinal')) is int
            and previous['ordinal']==source.start_ordinal-1,'SOURCE_CURSOR_ORDINAL_CHANGED')
        repeated,repeated_before,_=_read_prefix(fd,end,end,guard)
        require(repeated==whole and repeated_before==before and _first_line(fd,end,guard)==first,
                'SOURCE_PREFIX_CHANGED')
        _regular(os.fstat(fd),source)
        current=os.stat(name,dir_fd=parent,follow_symlinks=False);_regular(current,source)
        require(current.st_size>=end,'SOURCE_TRUNCATED')
        for ancestor,entry,identity in chain:
            info=os.stat(entry,dir_fd=ancestor,follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and _identity(info)==identity,'SOURCE_ANCESTOR_CHANGED')
        checked_guard(guard)
        return current.st_size
    except OSError:
        raise SourceHold('SOURCE_READ_HOLD') from None
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
