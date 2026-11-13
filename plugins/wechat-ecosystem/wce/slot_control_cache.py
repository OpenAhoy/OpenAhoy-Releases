"""Derived human control facts and atomic cursors, never execution grants.

The private host chooses this cache and supplies the host-selected same-owner human lookup.
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
from .slot_human_codec import initial_state, consume, _validate_state, pending_ordinals
from .slot_control_text_profile import completion_identity
from .slot_control_semantics import interpret, Context, RULE
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
 version INTEGER NOT NULL CHECK(version>=0), delta_sha TEXT NOT NULL);
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

CREATE TABLE control_current(
 key_sha TEXT PRIMARY KEY, thread_id TEXT NOT NULL, connection_id TEXT NOT NULL,
 date_key TEXT NOT NULL, group_key TEXT NOT NULL, value_json TEXT NOT NULL);
CREATE INDEX current_target ON control_current(connection_id,date_key,group_key,thread_id);
CREATE TRIGGER current_no_delete BEFORE DELETE ON control_current
BEGIN SELECT RAISE(ABORT, 'current restriction cannot disappear'); END;
CREATE TABLE control_participation(thread_id TEXT NOT NULL,connection_id TEXT NOT NULL,
 PRIMARY KEY(thread_id,connection_id));
CREATE INDEX participant_account ON control_participation(connection_id,thread_id);
CREATE TRIGGER participant_no_delete BEFORE DELETE ON control_participation
BEGIN SELECT RAISE(ABORT, 'source participation cannot disappear'); END;
CREATE TRIGGER participant_no_update BEFORE UPDATE ON control_participation
BEGIN SELECT RAISE(ABORT, 'immutable source participation'); END;
CREATE TABLE control_delta(
 registration TEXT NOT NULL, version INTEGER NOT NULL, key_sha TEXT NOT NULL,
 before_json TEXT, after_json TEXT NOT NULL, PRIMARY KEY(registration,version,key_sha));
CREATE TRIGGER delta_no_update BEFORE UPDATE ON control_delta
BEGIN SELECT RAISE(ABORT, 'immutable control delta'); END;
CREATE TRIGGER delta_no_delete BEFORE DELETE ON control_delta
BEGIN SELECT RAISE(ABORT, 'immutable control delta'); END;
'''


def _json(value):
    return canonical(value).decode('utf-8')


def _hash(value):
    return sha256(canonical(value)).hexdigest()


def _require_same_completion(row, fact):
    saved = json.loads(row[2])
    require(row[:2] == (saved['root_turn_id'], saved['text_sha256'])
        and completion_identity(saved) == completion_identity(fact),
        'SOURCE_NATIVE_ID_CONTENT_CONFLICT')


def _pin(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
            'SOURCE_CACHE_IDENTITY_INVALID')
    return info.st_dev, info.st_ino




class HumanControlCache:
    def __init__(self, directory, owner_binding, guard, context_provider, *, scan_guard=None):
        self.directory = Path(directory)
        self.root_pin = path_check(self.directory, True)
        require(type(owner_binding) is str and len(owner_binding) == 64
                and all(char in '0123456789abcdef' for char in owner_binding),
                'SOURCE_CACHE_BINDING_INVALID')
        self.owner_binding, self.guard = owner_binding, guard
        self.scan_guard=guard if scan_guard is None else scan_guard
        require(callable(context_provider), "SLOT_CONTROL_CONTEXT_REQUIRED")
        self.context_provider = context_provider
        self.path = self.directory / 'native-human-controls.sqlite3'
        self.lock = self.directory / 'native-human-controls.lock'

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
            if self.path.stat().st_size == 0:
                pin = _pin(self.path)
                with closing(sqlite3.connect(self.path)) as db:
                    require(db.execute('PRAGMA user_version').fetchone()[0] == 0
                        and db.execute('SELECT name FROM sqlite_master').fetchall() == [],
                        'SOURCE_CACHE_BINDING_INVALID')
                    db.execute('PRAGMA synchronous=FULL')
                    db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
                    db.execute('INSERT INTO cache_owner VALUES(?)', (self.owner_binding,))
                    db.execute('PRAGMA user_version=1')
                    self._guard()
                    require(_pin(self.path) == pin, 'SOURCE_CACHE_IDENTITY_CHANGED')
                    db.commit()
                directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            with self._database() as db:
                self._validate(db)

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
        return self.directory / ('native-human-controls-' + registration + '.' + kind + '.json')

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
        row = db.execute('SELECT thread_id,cursor_json,codec_json,references_json,state,captured_end,version,delta_sha '
                         'FROM streams WHERE registration=?', (registration,)).fetchone()
        if row is None:
            return None
        try:
            return {'thread_id': row[0], 'cursor': json.loads(row[1]),
                    'codec': json.loads(row[2]), 'references': json.loads(row[3]),
                    'state': row[4], 'captured_end': row[5], 'version': row[6],
                    'delta_sha256': row[7]}
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
            require(_delta_hash(db,registration,current['version']) == current['delta_sha256'],
                    'SLOT_CONTROL_INDEX_DELTA_CONFLICT')
            for key, previous, following in db.execute(
                'SELECT key_sha,before_json,after_json FROM control_delta WHERE registration=? AND version=? ORDER BY key_sha',
                (registration,current['version'])):
                actual_row=db.execute('SELECT value_json FROM control_current WHERE key_sha=?',(key,)).fetchone()
                require(actual_row == (following,), 'SLOT_CONTROL_INDEX_CONFLICT')
                marker=self._control_marker(key)
                require(marker in (self._control_header(key,previous),self._control_header(key,following)),
                        'SLOT_CONTROL_INDEX_CONFLICT')
                atomic_write(self.directory/('control-'+key+'.head.json'),
                    self._control_header(key,following), expected_parent=self.root_pin)
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

    @staticmethod
    def _state(db, source):
        registration = registration_digest(source)
        row = db.execute('SELECT thread_id,cursor_json,codec_json,references_json,state,captured_end,version '
                         'FROM streams WHERE registration=?', (registration,)).fetchone()
        if row is None:
            return initial(source), initial_state(source.thread_id, source.metadata_ordinal), {}, 0
        require(row[0] == source.thread_id, 'SOURCE_CACHE_REGISTRATION_CONFLICT')
        try:
            cursor = Checkpoint(**json.loads(row[1]))
            codec, refs = json.loads(row[2]), json.loads(row[3])
        except (TypeError, ValueError):
            raise SourceHold('SOURCE_CACHE_CORRUPT') from None
        _validate_state(codec)
        require(cursor.next_ordinal == codec.get('next_ordinal')
                and codec.get('thread_id') == source.thread_id and type(refs) is dict
                and set(refs) == pending_ordinals(codec), 'SOURCE_CACHE_CORRUPT')
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

        lookup is a private HumanThreadLookup, not caller-selected JSON.
        Only checkpoints and content-free native references are persisted.
        """
        self._guard()
        source = lookup.locate()
        registration = registration_digest(source)
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db)
            # A new native file/history_base is not continuity by itself.
            # Existing controls remain; a provider must prove and adopt an
            # actual previous-tail bridge before adding another generation.
            prior_sources = db.execute('SELECT registration FROM streams WHERE thread_id=?',
                                       (source.thread_id,)).fetchall()
            require(not prior_sources or all(row[0] == registration for row in prior_sources),
                    'SLOT_HUMAN_CONTINUITY_REQUIRED')
            anchored = self._anchored_projection(db, registration)
            cursor, codec, refs, version = self._state(db, source)
            segment = read_next(source, cursor, self.scan_guard, **work)
            facts = []; updates = {}
            for record in segment.records:
                value = record.value
                refs[str(record.ordinal)] = record.reference()
                codec, completed = consume(codec, record, allow_opaque_images=True)
                for fact in completed:
                    locations = {}
                    for kind in ('started', 'context', 'typed', 'raw'):
                        locations[kind] = refs[str(fact[kind + '_ordinal'])]
                    # Pending references can outlive the last segment anchor. Re-read
                    # their actual bytes, twice, before releasing a USER fact.
                    for reference in locations.values():
                        _verify_reference(source, reference, self.guard)
                    prior = db.execute('SELECT root_turn_id,text_sha256,fact_json FROM completions '
                        'WHERE thread_id=? AND turn_id=? AND item_id=?',
                        (fact['thread_id'],fact['turn_id'],fact['item_id'])).fetchone()
                    if prior is not None:
                        _require_same_completion(prior, fact)
                        continue
                    context = self.context_provider(fact)
                    require(type(context) is Context and context.owner_sha256 == self.owner_binding,
                            'SLOT_CONTROL_CONTEXT_INVALID')
                    previous = [] if codec['focus'] is None else [codec['focus']]
                    text = value['payload']['item']['content'][0]['text']
                    control = interpret(text, fact, context, previous)
                    control['registration_sha256'] = registration
                    control['previous_event_sha256'] = codec['event_head']
                    codec['event_head'] = _hash(control)
                    if not all(e['kind']=='NON_CONTROL' and e['reason']=='PROGRESS_ONLY' for e in control['effects']):
                        codec['focus'] = control if any(e['kind'] in ('RESTRICT','RESUME','AMBIGUOUS','AUDIENCE_CHANGE')
                            for e in control['effects']) else None
                    complete = fact | {'references': locations, 'control': control}
                    facts.append(complete)
                    current_updates=_current_updates(complete,registration,version+1)
                    codec['controlled_cids']=sorted(set(codec['controlled_cids']) |
                        {item['connection_id'] for item in current_updates.values()})
                    for key, current in current_updates.items():
                        if key not in updates:
                            row = db.execute('SELECT value_json FROM control_current WHERE key_sha=?',(key,)).fetchone()
                            before = None if row is None else row[0]
                            if before is not None: self._check_control_marker(key, before)
                            updates[key] = [before, _json(current)]
                        else: updates[key][1] = _json(current)
                keep = pending_ordinals(codec)
                refs = {key: item for key, item in refs.items() if key in keep}
            segment_state = ('INPUT_PENDING' if segment.state == 'CURRENT'
                and any(item['raw'] is not None for item in codec['turns'].values()) else segment.state)
            require(codec['next_ordinal'] == segment.checkpoint.next_ordinal,
                    'SOURCE_CACHE_CURSOR_CONFLICT')
            require(registration_digest(lookup.locate()) == registration,
                    'HOST_NATIVE_POINTER_CHANGED')
            self._guard()
            fault('before_transaction')
            stream_after = {'thread_id': source.thread_id, 'cursor': asdict(segment.checkpoint),
                'codec': codec, 'references': refs, 'state': segment_state,
                'captured_end': segment.captured_end, 'version': version + 1,
                'delta_sha256': _updates_hash(updates)}
            before_header = (None if anchored is None else
                self._header(registration, _hash(anchored), version))
            after_header = self._header(registration, _hash(stream_after), version + 1)
            pending = {'before': before_header, 'after': after_header}
            require(self._marker(registration, 'pending') is None, 'SOURCE_CACHE_COMMIT_UNKNOWN')
            atomic_write(self._marker_path(registration, 'pending'), pending, expected_parent=self.root_pin)
            fault('pending_before_transaction')
            db.execute('BEGIN IMMEDIATE')
            if version == 0:
                db.execute('INSERT INTO streams VALUES(?,?,?,?,?,?,?,?,?)',
                    (registration, source.thread_id, _json(asdict(cursor)),
                     _json(initial_state(source.thread_id, source.metadata_ordinal)), '{}',
                     'SCANNING', 0, 0, _updates_hash({})))
            require(db.execute('SELECT version FROM streams WHERE registration=?',
                               (registration,)).fetchone() == (version,), 'SOURCE_CACHE_CURSOR_CONFLICT')
            new_count = 0
            for fact in facts:
                key = (fact['thread_id'], fact['turn_id'], fact['item_id'])
                previous = db.execute('SELECT root_turn_id,text_sha256,fact_json FROM completions '
                                      'WHERE thread_id=? AND turn_id=? AND item_id=?', key).fetchone()
                identity = (fact['root_turn_id'], fact['text_sha256'])
                if previous is not None:
                    _require_same_completion(previous, fact)
                    continue
                db.execute('INSERT INTO completions VALUES(?,?,?,?,?,?,?)',
                    (*key, *identity, registration, _json(fact)))
                new_count += 1
            for cid in codec['controlled_cids']:
                db.execute('INSERT OR IGNORE INTO control_participation VALUES(?,?)',(source.thread_id,cid))
            for key, (before, after) in sorted(updates.items()):
                value = json.loads(after)
                db.execute('INSERT INTO control_delta VALUES(?,?,?,?,?)',
                           (registration,version+1,key,before,after))
                db.execute('INSERT INTO control_current VALUES(?,?,?,?,?,?) '
                    'ON CONFLICT(key_sha) DO UPDATE SET value_json=excluded.value_json',
                    (key,value['thread_id'],value['connection_id'],value['date_key'],value['group_key'],after))
            if segment.records:
                db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?)',
                    (registration, cursor.offset, segment.checkpoint.offset,
                     segment.segment_sha256, cursor.chain_sha256, segment.checkpoint.chain_sha256,
                     after_header['state_sha256']))
            db.execute('UPDATE streams SET cursor_json=?,codec_json=?,references_json=?,state=?,captured_end=?,version=?,delta_sha=? '
                       'WHERE registration=? AND version=?',
                (_json(asdict(segment.checkpoint)), _json(codec), _json(refs), segment_state,
                 segment.captured_end, version + 1, stream_after['delta_sha256'], registration, version))
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
                    'state': segment_state, 'next_ordinal': segment.checkpoint.next_ordinal,
                    'processed_end': segment.checkpoint.offset, 'new_human_events': new_count}

    def completion(self, thread_id, turn_id, item_id):
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db)
            row = db.execute('SELECT fact_json,first_registration FROM completions WHERE thread_id=? AND turn_id=? AND item_id=?',
                             (thread_id, turn_id, item_id)).fetchone()
            if row is None:
                return None
            self._anchored_projection(db, row[1])
            return json.loads(row[0])

    def fence(self, lookup, observed):
        """Before each new admission: require the same fully consumed source.

        This is a point-in-time observation, not a lock over future USER input.
        The platform executor still owns its permission and UNKNOWN checks.
        """
        source=lookup.locate(); registration=registration_digest(source)
        require(type(observed) is dict and observed.get('authority') is False
            and observed.get('registration_sha256') == registration
            and observed.get('state') == 'CURRENT', 'SLOT_HUMAN_REOBSERVE_REQUIRED')
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db); self._anchored_projection(db,registration)
            cursor,codec,refs,version=self._state(db,source)
            require([row[0] for row in db.execute('SELECT connection_id FROM control_participation '
                'WHERE thread_id=? ORDER BY connection_id',(source.thread_id,))] == codec['controlled_cids'],
                'SLOT_CONTROL_PARTICIPATION_CONFLICT')
            require(_hash(asdict(cursor)) == observed.get('checkpoint_sha256')
                and not any(item['raw'] is not None for item in codec['turns'].values()),
                'SLOT_HUMAN_REOBSERVE_REQUIRED')
            segment=read_next(source,cursor,self.scan_guard,work_records=1)
            require(segment.state == 'CURRENT' and not segment.records
                and segment.checkpoint == cursor
                and registration_digest(lookup.locate()) == registration,
                'SLOT_HUMAN_REOBSERVE_REQUIRED')
            self._guard()
        return {'authority':False,'state':'CURRENT_POINT_IN_TIME',
                'registration_sha256':registration,'checkpoint_sha256':_hash(asdict(cursor))}

    def _control_marker(self,key):
        path=self.directory/('control-'+key+'.head.json')
        if not os.path.lexists(path): return None
        pin=_pin(path)
        value=strict_json(FileSource(self.directory).read(path.name),16384)
        require(_pin(path)==pin,'SOURCE_CACHE_IDENTITY_CHANGED')
        return value

    def _control_header(self,key,value):
        return None if value is None else {'schema':1,'owner_binding':self.owner_binding,
            'db_identity':list(_pin(self.path)),'key_sha256':key,'value_sha256':sha256(value.encode()).hexdigest()}

    def _check_control_marker(self,key,value):
        require(self._control_marker(key)==self._control_header(key,value),
                'SLOT_CONTROL_INDEX_ANCHOR_MISMATCH')

    def decision(self, target, *, operation='submit'):
        require(operation in ('submit','task_read'),'SLOT_CONTROL_OPERATION_INVALID')
        if operation=='task_read': return {'authority':False,'state':'TASK_READ_UNAFFECTED','reasons':[]}
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db)
            # Four exact date/group keys per relevant source. Never scan the
            # event history or unrelated accounts/groups to decide one target.
            threads=db.execute('SELECT thread_id FROM control_participation WHERE connection_id=?',
                               (target['connection_id'],)).fetchall()
            rows=[]
            for (thread,) in threads:
                for date in ('*',target['date']):
                    for group in ('*',target['group_id']):
                        key=_hash([thread,target['connection_id'],date,group])
                        row=db.execute('SELECT value_json FROM control_current WHERE key_sha=?',(key,)).fetchone()
                        if row is None:
                            require(self._control_marker(key) is None,'SLOT_CONTROL_INDEX_MISSING')
                        else: rows.append((key,row[0]))
            current={}; checked=set()
            for key,raw in rows:
                value=json.loads(raw); registration=value['registration_sha256']
                if registration not in checked:
                    self._anchored_projection(db,registration); checked.add(registration)
                self._check_control_marker(key,raw)
                row=db.execute('SELECT fact_json FROM completions WHERE thread_id=? AND turn_id=? AND item_id=?',
                    tuple(value['fact_key'])).fetchone()
                require(row is not None and sha256(row[0].encode()).hexdigest()==value['fact_sha256'],
                        'SLOT_CONTROL_FACT_CONFLICT')
                require(json.loads(row[0])['control']['rule_version'] == RULE,
                        'SLOT_CONTROL_REINTERPRETATION_REQUIRED')
                order=(value['ordinal'],value['position'])
                prior=current.get(value['thread_id'])
                if prior is None or order > prior[0]: current[value['thread_id']]=(order,value['effect'])
            reasons=sorted({effect['reason'] for _,effect in current.values()
                            if effect['kind'] in ('RESTRICT','AMBIGUOUS','AUDIENCE_CHANGE')})
            return {'authority':False,'state':'RESTRICTED' if reasons else 'UNRESTRICTED_FACTS_ONLY','reasons':reasons}

    def history(self, *, after_rowid=0, limit=20):
        require(type(after_rowid) is int and after_rowid>=0 and type(limit) is int and 1<=limit<=20,
                'SLOT_CONTROL_HISTORY_INVALID')
        with locked(self.lock, nonblocking=True), self._database() as db:
            self._validate(db)
            rows=db.execute('SELECT rowid,fact_json,first_registration FROM completions '
                'WHERE rowid>? ORDER BY rowid LIMIT ?', (after_rowid,limit)).fetchall()
            for registration in {row[2] for row in rows}: self._anchored_projection(db,registration)
            return {'authority':False,'items':[{'rowid':row[0],'fact':json.loads(row[1])}for row in rows],
                    'next_after':rows[-1][0] if len(rows)==limit else None}


def _current_updates(fact,registration,version):
    result={}
    for position,effect in enumerate(fact['control']['effects']):
        if effect['kind'] not in ('RESTRICT','RESUME','AMBIGUOUS','AUDIENCE_CHANGE'): continue
        scope=effect['scope']
        # Explicit artifact triples avoid a date x group Cartesian product.
        keys=scope['target_keys'] or [(cid,date,'*') for cid in scope['connection_ids']
                                     for date in scope['dates'] or ['*']]
        for cid,date,group in keys:
            key=_hash([fact['thread_id'],cid,date,group])
            result[key]={'thread_id':fact['thread_id'],'connection_id':cid,'date_key':date,'group_key':group,
                'ordinal':fact['typed_ordinal'],'position':position,
                'effect':{'kind':effect['kind'],'reason':effect['reason']},
                'fact_key':[fact['thread_id'],fact['turn_id'],fact['item_id']],
                'fact_sha256':sha256(_json(fact).encode()).hexdigest(),
                'registration_sha256':registration,'version':version}
    return result


def _updates_hash(updates):
    state=sha256(b'SLOT_CONTROL_DELTA_V1\0')
    for key,(before,after) in sorted(updates.items()): state.update(canonical([key,before,after])+b'\n')
    return state.hexdigest()


def _delta_hash(db,registration,version):
    state=sha256(b'SLOT_CONTROL_DELTA_V1\0')
    for row in db.execute('SELECT key_sha,before_json,after_json FROM control_delta '
            'WHERE registration=? AND version=? ORDER BY key_sha',(registration,version)):
        state.update(canonical(list(row))+b'\n')
    return state.hexdigest()


def _verify_reference(source, ref, guard):
    from .draft_revision_native_source import _open_source, _regular, MAX_LINE
    require(ref['source_id'] == source.source_id and ref['byte_end'] - ref['byte_start'] <= MAX_LINE,
            'SLOT_HUMAN_REFERENCE_INVALID')
    fd, parent, name, descriptors, chain = _open_source(source)
    try:
        opened = os.fstat(fd); _regular(opened, source)
        def read():
            checked_guard(guard)
            os.lseek(fd, ref['byte_start'], os.SEEK_SET)
            raw = b''
            while len(raw) < ref['byte_end'] - ref['byte_start']:
                part = os.read(fd, min(65536, ref['byte_end'] - ref['byte_start'] - len(raw)))
                require(part, 'SLOT_HUMAN_REFERENCE_CHANGED'); raw += part
            return raw
        raw = read()
        require(sha256(raw).hexdigest() == ref['raw_line_sha256'] and read() == raw,
                'SLOT_HUMAN_REFERENCE_CHANGED')
        require(os.fstat(fd).st_size >= ref['byte_end'], 'SLOT_HUMAN_REFERENCE_CHANGED')
        _regular(os.stat(name, dir_fd=parent, follow_symlinks=False), source)
        for ancestor, entry, identity in chain:
            info=os.stat(entry,dir_fd=ancestor,follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino)==identity,
                    'SOURCE_ANCESTOR_CHANGED')
        checked_guard(guard)
    finally:
        for descriptor in reversed(descriptors): os.close(descriptor)
