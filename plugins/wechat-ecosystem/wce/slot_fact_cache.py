"""Derived native facts and atomic ingestion cursors, never execution grants.

The private host chooses this cache and supplies the registered producer lookup.
A cache row alone is not a completed-slot capability. Before using a fact the
source provider must validate its current source/role and original byte refs.
This cache may be rebuilt from verified native input; it is not the publication
or standing-authority journal and never resets either of those journals.
"""
from contextlib import closing
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat

from .own_connection_policy import locked, atomic_write
from .own_bootstrap_security import path_check
from .bounded_file import FileSource
from .publication_contract import strict_json
from .draft_revision_native_source import (
    SourceHold, canonical, checked_guard, registration_digest, require)
from .slot_native_codec import initial_state, consume, _validate_state
from .slot_source_stream import Checkpoint, initial, read_next


SCHEMA = '''
CREATE TABLE cache_owner(binding TEXT PRIMARY KEY NOT NULL);
CREATE TABLE streams(
 registration TEXT PRIMARY KEY NOT NULL,
 thread_id TEXT NOT NULL,
 cursor_json TEXT NOT NULL,
 codec_json TEXT NOT NULL,
 references_json TEXT NOT NULL,
 state TEXT NOT NULL,
 captured_end INTEGER NOT NULL,
 version INTEGER NOT NULL CHECK(version>=0));
CREATE TABLE segments(
 registration TEXT NOT NULL,
 byte_start INTEGER NOT NULL,
 byte_end INTEGER NOT NULL CHECK(byte_end>byte_start),
 segment_sha TEXT NOT NULL,
 previous_chain TEXT NOT NULL,
 next_chain TEXT NOT NULL,
 stream_after_sha TEXT NOT NULL,
 PRIMARY KEY(registration,byte_start),
 FOREIGN KEY(registration) REFERENCES streams(registration));
CREATE TABLE completions(
 thread_id TEXT NOT NULL,
 turn_id TEXT NOT NULL,
 item_id TEXT NOT NULL,
 root_turn_id TEXT NOT NULL,
 text_sha256 TEXT NOT NULL,
 first_registration TEXT NOT NULL,
 fact_json TEXT NOT NULL,
 PRIMARY KEY(thread_id,turn_id,item_id));
CREATE TRIGGER completion_no_update BEFORE UPDATE ON completions
BEGIN SELECT RAISE(ABORT, 'immutable completion'); END;
CREATE TRIGGER completion_no_delete BEFORE DELETE ON completions
BEGIN SELECT RAISE(ABORT, 'immutable completion'); END;
CREATE TRIGGER segment_no_update BEFORE UPDATE ON segments
BEGIN SELECT RAISE(ABORT, 'immutable segment'); END;
CREATE TRIGGER segment_no_delete BEFORE DELETE ON segments
BEGIN SELECT RAISE(ABORT, 'immutable segment'); END;
'''


def _json(value):
    return canonical(value).decode('utf-8')


def _hash(value):
    return sha256(canonical(value)).hexdigest()


def _pin(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
            'SOURCE_CACHE_IDENTITY_INVALID')
    return info.st_dev, info.st_ino


def _pending_ordinals(codec):
    result = set()
    for turn in codec['turns'].values():
        result.add(turn['started_ordinal'])
        if turn['context_ordinal'] is not None:
            result.add(turn['context_ordinal'])
        for kind in ('typed', 'raw'):
            if turn[kind] is not None:
                result.add(turn[kind]['ordinal'])
    return {str(value) for value in result}


class FactCache:
    def __init__(self, directory, owner_binding, guard, *, scan_guard=None, seed=None, projection_profile=None):
        self.directory = Path(directory)
        self.root_pin = path_check(self.directory, True)
        require(type(owner_binding) is str and len(owner_binding) == 64
                and all(char in '0123456789abcdef' for char in owner_binding),
                'SOURCE_CACHE_BINDING_INVALID')
        self.owner_binding, self.guard = owner_binding, guard
        self.scan_guard=guard if scan_guard is None else scan_guard
        if seed is not None:
            from .slot_producer_seed import ProducerSeed
            require(type(seed)is ProducerSeed,'SLOT_UNCHECKED_PRODUCER_SEED');seed.fence()
        self.seed=seed
        from .slot_visible_projection import PROFILE
        require(projection_profile in (None,PROFILE),'SLOT_PRODUCER_SEED_CACHE_CHANGED')
        self.projection_profile=projection_profile
        self.path = self.directory / 'native-facts.sqlite3'
        self.lock = self.directory / 'native-facts.lock'

    def _guard(self):
        checked_guard(self.guard)
        require(path_check(self.directory, True) == self.root_pin, 'SOURCE_CACHE_ROOT_CHANGED')

    def initialize(self):
        self._guard()
        with locked(self.lock, nonblocking=True):
            self._guard()
            if not os.path.lexists(self.path):
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            # A process may stop between creating the private inode and the
            # first schema commit. Only that exact empty initial state can be
            # initialized again; never erase or repair an unknown existing DB.
            pin = _pin(self.path)
            empty = self.path.lstat().st_size == 0
            with self._database() as db:
                initial = (empty and db.execute('PRAGMA user_version').fetchone()[0] == 0
                           and not db.execute('SELECT name FROM sqlite_schema LIMIT 1').fetchall())
                if initial:
                    db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
                    db.execute('INSERT INTO cache_owner VALUES(?)', (self.owner_binding,))
                    db.execute('PRAGMA user_version=1')
                    self._guard()
                    require(_pin(self.path) == pin, 'SOURCE_CACHE_IDENTITY_CHANGED')
                    db.commit()
                self._validate(db)
            if initial:
                directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)

    def _validate(self, db):
        require(db.execute('PRAGMA user_version').fetchone()[0] == 1
                and db.execute('SELECT binding FROM cache_owner LIMIT 2').fetchall() == [(self.owner_binding,)],
                'SOURCE_CACHE_BINDING_INVALID')

    def _database(self):
        """Read only after initialize; no missing-file recreation on reads."""
        from contextlib import contextmanager
        @contextmanager
        def open_database():
            self._guard()
            pin = _pin(self.path)
            # Path is internally selected. Opening mode=rw prevents silently
            # replacing a missing registered cache with an empty database.
            uri = self.path.as_uri() + '?mode=rw'
            with closing(sqlite3.connect(uri, uri=True)) as db:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA synchronous=FULL')
                require(_pin(self.path) == pin, 'SOURCE_CACHE_IDENTITY_CHANGED')
                yield db
                self._guard()
                require(_pin(self.path) == pin, 'SOURCE_CACHE_IDENTITY_CHANGED')
        return open_database()

    def _marker_path(self, registration, kind):
        require(type(registration) is str and len(registration) == 64
                and all(char in '0123456789abcdef' for char in registration),
                'SOURCE_CACHE_REGISTRATION_CONFLICT')
        return self.directory / ('native-facts-' + registration + '.' + kind + '.json')

    def _marker(self, registration, kind):
        path = self._marker_path(registration, kind)
        if not os.path.lexists(path):
            return None
        pin = _pin(path)
        value = strict_json(FileSource(self.directory).read(path.name), 16384)
        require(_pin(path) == pin, 'SOURCE_CACHE_IDENTITY_CHANGED')
        return value

    def _header(self, registration, state_sha, version):
        return {'schema': 1, 'owner_binding': self.owner_binding,
                'registration_sha256': registration, 'db_identity': list(_pin(self.path)),
                'state_sha256': state_sha, 'version': version}

    @staticmethod
    def _projection(db, registration):
        row = db.execute('SELECT thread_id,cursor_json,codec_json,references_json,state,captured_end,version '
                         'FROM streams WHERE registration=?', (registration,)).fetchone()
        if row is None:
            return None
        try:
            return {'thread_id': row[0], 'cursor': json.loads(row[1]),
                    'codec': json.loads(row[2]), 'references': json.loads(row[3]),
                    'state': row[4], 'captured_end': row[5], 'version': row[6]}
        except (TypeError, ValueError):
            raise SourceHold('SOURCE_CACHE_CORRUPT') from None

    def _clear_pending(self, registration, expected):
        require(self._marker(registration, 'pending') == expected,
                'SOURCE_CACHE_COMMIT_UNKNOWN')
        self._guard()
        self._marker_path(registration, 'pending').unlink()
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _recover(self, db, registration):
        pending = self._marker(registration, 'pending')
        if pending is None:
            return
        require(type(pending) is dict and set(pending) == {'before', 'after'}
                and type(pending['after']) is dict, 'SOURCE_CACHE_COMMIT_UNKNOWN')
        before, after = pending['before'], pending['after']
        current = self._projection(db, registration)
        actual = None if current is None else self._header(
            registration, _hash(current), current['version'])
        head = self._marker(registration, 'head')
        require(actual in (before, after) and head in (before, after),
                'SOURCE_CACHE_COMMIT_UNKNOWN')
        if actual == after:
            require(after == self._header(registration, _hash(current), current['version']),
                    'SOURCE_CACHE_COMMIT_UNKNOWN')
            self._guard()
            atomic_write(self._marker_path(registration, 'head'), after, expected_parent=self.root_pin)
        else:
            require(head == before, 'SOURCE_CACHE_COMMIT_UNKNOWN')
        self._clear_pending(registration, pending)

    def _anchored_projection(self, db, registration):
        self._recover(db, registration)
        current = self._projection(db, registration)
        head = self._marker(registration, 'head')
        if current is None:
            require(head is None, 'SOURCE_CACHE_ANCHOR_MISMATCH')
            return None
        require(head == self._header(registration, _hash(current), current['version']),
                'SOURCE_CACHE_ANCHOR_MISMATCH')
        cursor = current['cursor']
        if cursor['offset']:
            segment = db.execute('SELECT byte_start,byte_end,segment_sha,next_chain '
                                 'FROM segments WHERE registration=? AND byte_start=?',
                                 (registration, cursor['previous_start'])).fetchone()
            require(segment == (cursor['previous_start'], cursor['previous_end'],
                    cursor['previous_sha256'], cursor['chain_sha256']), 'SOURCE_CACHE_SEGMENT_MISSING')
        return current

    def _initial_codec(self,source):
        if self.seed is None:return initial_state(source.thread_id,source.metadata_ordinal,
            projection_profile=self.projection_profile)
        from .slot_producer_seed import initial
        return initial(self.seed,source,projection_profile=self.projection_profile)

    def _codec(self,state):
        if self.seed is None:
            _validate_state(state)
            require(state.get('projection_profile')==self.projection_profile,'SLOT_PRODUCER_SEED_CACHE_CHANGED')
            return state
        from .slot_producer_seed import pending_codec
        return pending_codec(self.seed,state,projection_profile=self.projection_profile)

    def _state(self, db, source):
        registration = registration_digest(source)
        row = db.execute('SELECT thread_id,cursor_json,codec_json,references_json,state,captured_end,version '
                         'FROM streams WHERE registration=?', (registration,)).fetchone()
        if row is None:
            return initial(source), self._initial_codec(source), {}, 0
        require(row[0] == source.thread_id, 'SOURCE_CACHE_REGISTRATION_CONFLICT')
        try:
            cursor = Checkpoint(**json.loads(row[1]))
            codec, refs = json.loads(row[2]), json.loads(row[3])
        except (TypeError, ValueError):
            raise SourceHold('SOURCE_CACHE_CORRUPT') from None
        pending=self._codec(codec)
        require(cursor.next_ordinal == codec.get('next_ordinal')
                and (self.seed is not None or codec.get('thread_id') == source.thread_id) and type(refs) is dict
                and set(refs) == _pending_ordinals(pending), 'SOURCE_CACHE_CORRUPT')
        for ordinal, ref in refs.items():
            require(type(ref) is dict and set(ref) == {
                'source_id', 'ordinal', 'byte_start', 'byte_end', 'raw_line_sha256'}
                and ref['source_id'] == source.source_id and type(ref['ordinal']) is int
                and str(ref['ordinal']) == ordinal
                and type(ref['byte_start']) is int and type(ref['byte_end']) is int
                and 0 <= ref['byte_start'] < ref['byte_end'] <= cursor.offset
                and type(ref['raw_line_sha256']) is str and len(ref['raw_line_sha256']) == 64
                and all(char in '0123456789abcdef' for char in ref['raw_line_sha256']),
                'SOURCE_CACHE_CORRUPT')
        return cursor, codec, refs, row[6]

    def advance(self, lookup, *, fault=lambda stage: None, **work):
        """One automatically repeatable work batch; no platform request.

        lookup is a private ProducerThreadLookup, not caller-selected JSON.
        Only checkpoints and content-free native references are persisted.
        """
        self._guard()
        source = lookup.locate()
        if self.seed is not None:self.seed.fence()
        registration = registration_digest(source)
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db)
            anchored = self._anchored_projection(db, registration)
            cursor, codec, refs, version = self._state(db, source)
            segment = read_next(source, cursor, self.scan_guard, **work)
            facts = []
            for record in segment.records:
                value = record.value
                refs[str(record.ordinal)] = record.reference()
                if self.seed is None:
                    codec, completed = consume(codec, {key: value[key] for key in ('ordinal', 'type', 'payload')})
                else:
                    from .slot_producer_seed import advance
                    codec,completed=advance(self.seed,codec,record,projection_profile=self.projection_profile)
                for fact in completed:
                    locations = {}
                    for kind in ('started', 'context', 'typed', 'raw', 'terminal'):
                        locations[kind] = refs[str(fact[kind + '_ordinal'])]
                    facts.append(fact | {'references': locations})
                keep = _pending_ordinals(self._codec(codec))
                refs = {key: item for key, item in refs.items() if key in keep}
            require(codec['next_ordinal'] == segment.checkpoint.next_ordinal,
                    'SOURCE_CACHE_CURSOR_CONFLICT')
            require(registration_digest(lookup.locate()) == registration,
                    'HOST_NATIVE_POINTER_CHANGED')
            if self.seed is not None:self.seed.fence()
            self._guard()
            fault('before_transaction')
            stream_after = {'thread_id': source.thread_id, 'cursor': asdict(segment.checkpoint),
                'codec': codec, 'references': refs, 'state': segment.state,
                'captured_end': segment.captured_end, 'version': version + 1}
            before_header = (None if anchored is None else
                self._header(registration, _hash(anchored), version))
            after_header = self._header(registration, _hash(stream_after), version + 1)
            pending = {'before': before_header, 'after': after_header}
            require(self._marker(registration, 'pending') is None, 'SOURCE_CACHE_COMMIT_UNKNOWN')
            atomic_write(self._marker_path(registration, 'pending'), pending, expected_parent=self.root_pin)
            fault('pending_before_transaction')
            db.execute('BEGIN IMMEDIATE')
            if version == 0:
                db.execute('INSERT INTO streams VALUES(?,?,?,?,?,?,?,?)',
                    (registration, source.thread_id, _json(asdict(cursor)),
                     _json(self._initial_codec(source)), '{}',
                     'SCANNING', 0, 0))
            require(db.execute('SELECT version FROM streams WHERE registration=?',
                               (registration,)).fetchone() == (version,), 'SOURCE_CACHE_CURSOR_CONFLICT')
            new_count = 0
            for fact in facts:
                key = (fact['thread_id'], fact['turn_id'], fact['item_id'])
                previous = db.execute('SELECT root_turn_id,text_sha256,fact_json FROM completions '
                                      'WHERE thread_id=? AND turn_id=? AND item_id=?', key).fetchone()
                identity = (fact['root_turn_id'], fact['text_sha256'])
                if previous is not None:
                    from .slot_visible_projection import identity as completion_identity
                    require(previous[:2] == identity
                        and completion_identity(json.loads(previous[2]))==completion_identity(fact),
                        'SOURCE_NATIVE_ID_CONTENT_CONFLICT')
                    continue
                db.execute('INSERT INTO completions VALUES(?,?,?,?,?,?,?)',
                    (*key, *identity, registration, _json(fact)))
                new_count += 1
            if segment.records:
                db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?)',
                    (registration, cursor.offset, segment.checkpoint.offset,
                     segment.segment_sha256, cursor.chain_sha256, segment.checkpoint.chain_sha256,
                     after_header['state_sha256']))
            db.execute('UPDATE streams SET cursor_json=?,codec_json=?,references_json=?,state=?,captured_end=?,version=? '
                       'WHERE registration=? AND version=?',
                (_json(asdict(segment.checkpoint)), _json(codec), _json(refs), segment.state,
                 segment.captured_end, version + 1, registration, version))
            self._guard()
            fault('before_commit')
            db.commit()
            fault('after_commit')
            self._recover(db, registration)
            require(self._anchored_projection(db, registration) == stream_after,
                    'SOURCE_CACHE_COMMIT_UNKNOWN')
            fault('after_anchor')
            return {'authority': False, 'registration_sha256': registration,
                    'checkpoint_sha256': _hash(asdict(segment.checkpoint)),
                    'state': segment.state, 'next_ordinal': segment.checkpoint.next_ordinal,
                    'processed_end': segment.checkpoint.offset, 'new_completions': new_count}

    def completion(self, thread_id, turn_id, item_id):
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db)
            row = db.execute('SELECT fact_json,first_registration FROM completions WHERE thread_id=? AND turn_id=? AND item_id=?',
                             (thread_id, turn_id, item_id)).fetchone()
            if row is None:
                return None
            self._anchored_projection(db, row[1])
            return json.loads(row[0])
