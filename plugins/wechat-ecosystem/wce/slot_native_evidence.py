"""Re-read original producer completion bytes without scanning its whole past.

A fact-cache entry locates records; it does not authenticate a delivery, grant
permission, prove source continuity or establish a producer's assigned role.
The private Source provider must separately establish those things. This
reader only verifies the original five-record completion and returns its text
in memory. It never stores text, accepts a path from MCP or calls a platform.
"""
from hashlib import sha256
import os
import stat

from .draft_revision_native_source import (
    MAX_LINE, Record, _first_line, _open_source, _regular,
    checked_guard, registration_digest, require)
from .slot_native_codec import initial_state, consume
from .slot_native_lookup import metadata_origin
from .slot_visible_projection import PROFILE as VISIBLE_PROFILE,FIELDS as PROJECTION_FIELDS,validate as validate_projection


KINDS = ('started', 'context', 'typed', 'raw', 'terminal')
FACT_FIELDS = {'schema', 'authority', 'thread_id', 'turn_id', 'root_turn_id',
               'item_id', 'text_sha256', 'references'} | {k + '_ordinal' for k in KINDS}
REFERENCE_FIELDS = {'source_id', 'ordinal', 'byte_start', 'byte_end', 'raw_line_sha256'}


def _read(fd, start, end, guard):
    parts = []
    offset = start
    while offset < end:
        checked_guard(guard)
        part = os.pread(fd, min(65536, end - offset), offset)
        require(bool(part), 'SLOT_COMPLETION_REFERENCE_CHANGED')
        parts.append(part)
        offset += len(part)
    return b''.join(parts)


def completion_text(lookup, fact, guard):
    """Validate an already-indexed completion against its current native source.

    No caller-provided source/path, current-source claim or authorization flag
    is created here. Reopening/compaction needs a separately verified reference
    bridge; retaining a cache row alone cannot substitute for the old bytes.
    """
    checked_guard(guard)
    require(type(fact)is dict and type(fact.get('schema'))is int and fact['schema']in(1,2),
        'SLOT_COMPLETION_FACT_INVALID')
    expected=FACT_FIELDS if fact['schema']==1 else FACT_FIELDS|PROJECTION_FIELDS
    require(set(fact)==expected
            and fact['authority'] is False and type(fact['references']) is dict
            and set(fact['references']) == set(KINDS), 'SLOT_COMPLETION_FACT_INVALID')
    if fact['schema']==2:
        validate_projection({key:fact[key]for key in PROJECTION_FIELDS},
            {'sha256':fact['text_sha256'],'bytes':fact['text_bytes']},
            {'sha256':fact['raw_text_sha256'],'bytes':fact['raw_text_bytes']})
    source = lookup.locate()
    registration = registration_digest(source)
    require(source.thread_id == fact['thread_id'], 'SLOT_COMPLETION_SOURCE_CHANGED')
    previous_ordinal = source.metadata_ordinal
    previous_end = 0
    for kind in KINDS:
        ref = fact['references'][kind]
        require(type(ref) is dict and set(ref) == REFERENCE_FIELDS
                and ref['source_id'] == source.source_id
                and type(ref['ordinal']) is int and ref['ordinal'] > previous_ordinal
                and ref['ordinal'] == fact[kind + '_ordinal']
                and type(ref['byte_start']) is int and type(ref['byte_end']) is int
                and previous_end <= ref['byte_start'] < ref['byte_end']
                and ref['byte_end'] - ref['byte_start'] <= MAX_LINE,
                'SLOT_COMPLETION_FACT_INVALID')
        previous_ordinal, previous_end = ref['ordinal'], ref['byte_end']
    fd, parent, name, descriptors, chain = _open_source(source)
    try:
        captured_end = os.fstat(fd).st_size
        require(previous_end <= captured_end, 'SLOT_COMPLETION_REFERENCE_CHANGED')
        first = _first_line(fd, captured_end, guard)
        require(sha256(first).hexdigest() == source.session_meta_sha256,
                'SLOT_COMPLETION_SOURCE_CHANGED')
        meta = Record(source.source_id, source.metadata_ordinal, 0, len(first),
                      source.session_meta_sha256, first).value
        require(metadata_origin(meta, source.thread_id) == source.metadata_ordinal,
                'SLOT_COMPLETION_SOURCE_CHANGED')
        rows, original_bytes = [], []
        for kind in KINDS:
            ref = fact['references'][kind]
            raw = _read(fd, ref['byte_start'], ref['byte_end'], guard)
            require(sha256(raw).hexdigest() == ref['raw_line_sha256'],
                    'SLOT_COMPLETION_REFERENCE_CHANGED')
            record = Record(source.source_id, ref['ordinal'], ref['byte_start'],
                            ref['byte_end'], ref['raw_line_sha256'], raw)
            row = record.value
            require(row.get('ordinal') == ref['ordinal'] and type(row.get('type')) is str
                    and type(row.get('payload')) is dict, 'SLOT_COMPLETION_FACT_INVALID')
            rows.append(row)
            original_bytes.append(raw)
        # This is a projection check of five already-indexed references, not a
        # continuous source ingestion. Advance the pure checker to each real
        # ordinal without producing or modifying any ingestion checkpoint.
        state = initial_state(source.thread_id,fact['started_ordinal'],
            projection_profile=VISIBLE_PROFILE if fact['schema']==2 else None)
        completed = []
        for row in rows:
            state['next_ordinal'] = row['ordinal']
            state, found = consume(state, {k: row[k] for k in ('ordinal', 'type', 'payload')})
            completed.extend(found)
        require(completed == [{k: v for k, v in fact.items() if k != 'references'}],
                'SLOT_COMPLETION_FACT_INVALID')
        if fact['schema']==2:text=rows[2]['payload']['item']['content'][0]['text']
        else:text=rows[3]['payload']['content'][0]['text']
        require(sha256(text.encode()).hexdigest() == fact['text_sha256'],
                'SLOT_COMPLETION_FACT_INVALID')
        for kind, raw in zip(KINDS, original_bytes):
            ref = fact['references'][kind]
            require(_read(fd, ref['byte_start'], ref['byte_end'], guard) == raw,
                    'SLOT_COMPLETION_REFERENCE_CHANGED')
        require(_first_line(fd, os.fstat(fd).st_size, guard) == first,
                'SLOT_COMPLETION_SOURCE_CHANGED')
        _regular(os.fstat(fd), source)
        _regular(os.stat(name, dir_fd=parent, follow_symlinks=False), source)
        for ancestor, entry, identity in chain:
            info = os.stat(entry, dir_fd=ancestor, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity,
                    'SOURCE_ANCESTOR_CHANGED')
        require(registration_digest(lookup.locate()) == registration,
                'HOST_NATIVE_POINTER_CHANGED')
        checked_guard(guard)
        return text
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
