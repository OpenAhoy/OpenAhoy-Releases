"""Private continuation store; no sender or authorization factory.

This isolated candidate indexes the verified old baseline and implements
private continuation state transitions behind checked host callbacks. It is
not itself wired to MCP or an HTTP sender; the legacy facade uses its local journal.
"""
import json
import os
import sqlite3
import stat
import threading
import weakref
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from hashlib import sha256
from pathlib import Path

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write
from .publication_contract import binding
from .publication_store import read_file, sync_directory
from .service import canonical, digest

PROFILE = 'CURRENT_PUBLICATION_CONTINUATION_FOUNDATION_V1'
_TICKET_SEAL = object()
_SCHEMA_NAMES = {'meta','legacy_metadata','legacy_latest','legacy_latest_no_delete','legacy_revision_events','legacy_revision_proposals','revision_events_no_update','revision_events_no_delete','revision_proposals_no_update','revision_proposals_no_delete','slot_dispatch_state','slot_dispatch_no_delete','slot_observations','slot_observation_lookup','slot_observation_no_update','slot_observation_no_delete','account_state','old_intents','old_claims','old_claim_lookup','events','fact_batches',
                 'target_overlays','staged_slot_lookup','intent_versions','target_claims','target_claim_lookup',
                 'slot_batches','slot_members','slot_batches_no_update','slot_batches_no_delete',
                 'slot_members_no_update','slot_members_no_delete',
                 'target_claims_no_update','target_claims_no_delete','return_receipts',
                 'receipts_no_update','receipts_no_delete','versions_no_update','versions_no_delete',
                 'account_denial_no_reset',
                 'events_no_update','events_no_delete','batches_no_update','batches_no_delete'}
_LOCAL_LOCKS = weakref.WeakValueDictionary()
_LOCAL_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class _SubmitTicket:
    session: object = field(repr=False)
    handle: str
    claim_seq: int
    claim_sha: str
    request: object = field(repr=False)
    token: object = field(repr=False)
    pid: int
    thread: int
    seal: object = field(repr=False)


@dataclass(frozen=True)
class _QueryTicket:
    session: object = field(repr=False)
    handle: str
    claim_seq: int
    claim_sha: str
    request: object = field(repr=False)
    token: object = field(repr=False)
    task: object = field(repr=False)
    pid: int
    thread: int
    seal: object = field(repr=False)


def _fail():
    raise WCEError('CONTINUATION_HISTORY_HOLD')


def _owned_file(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    try:
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                    or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
                _fail()
            return st.st_dev, st.st_ino
        finally:
            os.close(fd)
    except (OSError, ValueError):
        _fail()


class ContinuationIndex:
    """Preserve old facts and private intent transitions; it grants no authority."""

    def __init__(self, old_store):
        from .current_publication_store import Store
        if type(old_store) is not Store:
            _fail()
        self.old = old_store
        self.account = old_store.legacy.key
        self.binding = binding(old_store.policy.data)
        self.db_path = old_store.legacy.anchor / 'slot-continuation-v1.sqlite3'
        self.head_path = old_store.legacy.anchor / 'slot-continuation-v1-head.json'
        self.marker_path = old_store.legacy.anchor / 'slot-continuation-v1-marker.json'
        self.enrollment_path = old_store.policy.root / 'slot-continuation-v1-enrollment.json'

    def _guard(self, *, historical=False):
        self.old.runtime_guard()
        if not historical:
            self.old.policy.check()
        path_check(self.old.legacy.anchor, True)

    @contextmanager
    def _db(self, *, readonly=False, historical=False):
        self._guard(historical=historical)
        identity = _owned_file(self.db_path)
        selected = self.db_path.as_uri() + '?mode=ro' if readonly else str(self.db_path)
        conn = sqlite3.connect(selected, uri=readonly, timeout=10, isolation_level=None)
        try:
            if _owned_file(self.db_path) != identity:
                _fail()
            conn.execute('PRAGMA foreign_keys=ON')
            if not readonly:
                conn.execute('PRAGMA synchronous=FULL')
            conn.row_factory = sqlite3.Row
            yield conn, identity
        except (sqlite3.Error, ValueError, TypeError, UnicodeError, AttributeError, KeyError, IndexError):
            _fail()
        finally:
            conn.close()

    def _baseline(self):
        # Actual old reader checks its full immutable chain and all old validators.
        value = self.old._read_legacy()
        return value, {'account': self.account, 'binding': self.binding,
            'old_value_sha': digest(value), 'old_head': read_file(self.old.path, 16384),
            'old_marker': self.old._marker()}

    def _meta(self, db, identity):
        row = db.execute('SELECT * FROM meta WHERE id=1').fetchone()
        if row is None or row['profile'] != PROFILE or row['account'] != self.account:
            _fail()
        value = json.loads(row['baseline'])
        if (digest(value) != row['baseline_sha'] or value['account'] != self.account or value['binding'] != self.binding
                or tuple(json.loads(row['identity'])) != identity
                or value['old_head'] != read_file(self.old.path, 16384)
                or value['old_marker'] != self.old._marker()):
            _fail()
        return row

    def _check_old_index(self, db, meta):
        # The old ledger is itself bounded. Verify this frozen projection before
        # using a negative lookup: a missing index row is never proof of absence.
        intents = [(r['handle'], r['row_sha']) for r in db.execute(
            'SELECT handle,row_sha FROM old_intents ORDER BY handle')]
        claims = [tuple(r) for r in db.execute(
            'SELECT kind,fingerprint,handle FROM old_claims ORDER BY kind,fingerprint,handle')]
        value = json.loads(meta['baseline'])
        if digest({'intents': intents, 'claims': claims}) != value['old_index_sha']:
            _fail()

    def _head(self, db, identity, *, recover=False, initializing=False, bootstrap=False):
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        if (names != _SCHEMA_NAMES or db.execute('PRAGMA user_version').fetchone()[0] != 1
                or db.execute('PRAGMA application_id').fetchone()[0] != 0x57434543):
            _fail()
        meta = self._meta(db, identity)
        marker = read_file(self.marker_path, 16384)
        if (marker != {'profile': PROFILE, 'account': self.account, 'baseline_sha': meta['baseline_sha'],
                       'state': 'INITIALIZING' if initializing else 'ACTIVE'}):
            _fail()
        enrollment = read_file(self.enrollment_path, 16384)
        if enrollment != marker and not (bootstrap and not initializing and enrollment == dict(marker, state='INITIALIZING')):
            _fail()
        if not bootstrap and enrollment['state'] != 'ACTIVE':
            _fail()
        if not os.path.lexists(self.head_path):
            # The only safe incomplete creation is a committed empty event chain.
            if not initializing or not recover or meta['seq'] != 0 or meta['event_sha'] is not None:
                _fail()
            atomic_write(self.head_path, {'profile': PROFILE, 'account': self.account,
                'identity': list(identity), 'baseline_sha': meta['baseline_sha'],
                'seq': 0, 'event_sha': None})
        head = read_file(self.head_path, 16384)
        expected = {'profile': PROFILE, 'account': self.account,
            'identity': list(identity), 'baseline_sha': meta['baseline_sha'],
            'seq': meta['seq'], 'event_sha': meta['event_sha']}
        if head == expected:
            if meta['seq']:
                latest = db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(meta['seq'],)).fetchone()
                if latest is None:
                    _fail()
                event = json.loads(latest['event_json'])
                if digest(event) != meta['event_sha']:
                    _fail()
            return head
        if not recover or (head.get('profile') != PROFILE or head.get('account') != self.account
                or head.get('identity') != list(identity) or head.get('baseline_sha') != meta['baseline_sha']
                or type(head.get('seq')) is not int or not 1 <= meta['seq'] - head['seq'] <= 256):
            _fail()
        previous = head.get('event_sha')
        for seq in range(head['seq'] + 1, meta['seq'] + 1):
            row = db.execute('SELECT previous_sha,event_sha,event_json FROM events WHERE seq=?',
                             (seq,)).fetchone()
            if row is None or row['previous_sha'] != previous:
                _fail()
            event = json.loads(row['event_json'])
            if (event.get('seq') != seq or event.get('previous_sha') != previous
                    or digest(event) != row['event_sha']):
                _fail()
            previous = row['event_sha']
        if previous != meta['event_sha']:
            _fail()
        atomic_write(self.head_path, expected)
        if read_file(self.head_path, 16384) != expected:
            _fail()
        return expected

    def bootstrap(self, *, fault=lambda phase: None):
        with self.old.legacy.dispatch_lock():
            self._guard()
            value, baseline = self._baseline()
            intents = sorted((handle, digest(row)) for handle, row in value['targets'].items())
            claims = []
            for handle, row in value['targets'].items():
                pairs = [('DRAFT_REF', digest(row['reference']))]
                pairs += [tuple(c) for c in row.get('content_claims', [])]
                task = row.get('task')
                if isinstance(task, dict):
                    pairs.append(('TASK', digest([task.get('kind'), task.get('digits')])))
                elif row.get('state') in {'SUBMIT_CLAIMED','UNKNOWN'} and row.get('submit_count') == 1:
                    # Include a proven original staged task even before it was
                    # adopted into the old target row. This is indexing only.
                    recovered = self.old._staged_submit(value,row,self.old.runtime_guard,check_conflict=False)
                    if recovered.get('state') == 'ORIGINAL_TASK_STAGED_LOCAL_ONLY':
                        old_task = recovered['task']
                        pairs.append(('TASK',digest([old_task.kind,old_task.digits])))
                    elif recovered.get('state') != 'ORIGINAL_RECEIPT_NOT_FOUND':
                        _fail()
                claims.extend((k, f, handle) for k, f in set(pairs))
            baseline['old_index_sha'] = digest({'intents': intents, 'claims': sorted(claims)})
            legacy_metadata = {key:value for key,value in value.items() if key != 'targets'}
            baseline['legacy_metadata_sha'] = digest(legacy_metadata)
            baseline_sha = digest(baseline)
            parent = self.old.legacy.anchor
            path_check(parent, True)
            initial = {'profile': PROFILE, 'account': self.account,
                       'baseline_sha': baseline_sha, 'state': 'INITIALIZING'}
            active = dict(initial, state='ACTIVE')
            if not os.path.lexists(self.enrollment_path):
                if any(os.path.lexists(p) for p in (self.marker_path, self.db_path, self.head_path)):
                    _fail()
                atomic_write(self.enrollment_path, initial)
                fault('enrollment_created')
            enrollment = read_file(self.enrollment_path, 16384)
            if enrollment not in (initial, active):
                _fail()
            if not os.path.lexists(self.marker_path):
                if enrollment != initial or os.path.lexists(self.db_path) or os.path.lexists(self.head_path):
                    _fail()
                atomic_write(self.marker_path, initial)
                fault('marker_created')
            marker = read_file(self.marker_path, 16384)
            if marker not in (initial, active) or (enrollment == active and marker != active):
                _fail()
            if not os.path.lexists(self.db_path):
                if marker != initial or os.path.lexists(self.head_path):
                    _fail()
                fd = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(fd)
                sync_directory(parent)
                fault('empty_db_created')
            with self._db() as (db, identity):
                names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
                if not names:
                    if marker != initial or os.path.lexists(self.head_path):
                        _fail()
                    db.executescript('''BEGIN IMMEDIATE;
CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1),profile TEXT NOT NULL,account TEXT NOT NULL,identity TEXT NOT NULL,baseline TEXT NOT NULL,baseline_sha TEXT NOT NULL,seq INTEGER NOT NULL,event_sha TEXT);
CREATE TABLE legacy_metadata(id INTEGER PRIMARY KEY CHECK(id=1),value_json TEXT NOT NULL,value_sha TEXT NOT NULL,event_seq INTEGER NOT NULL);
CREATE TABLE legacy_latest(field TEXT NOT NULL,key_text TEXT NOT NULL,entry_json TEXT NOT NULL,event_seq INTEGER NOT NULL,PRIMARY KEY(field,key_text));
CREATE TRIGGER legacy_latest_no_delete BEFORE DELETE ON legacy_latest BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TABLE legacy_revision_events(handle TEXT NOT NULL,event_seq INTEGER NOT NULL,event_sha TEXT NOT NULL,PRIMARY KEY(handle,event_seq));
CREATE TABLE legacy_revision_proposals(proposal_sha TEXT PRIMARY KEY NOT NULL,handle TEXT NOT NULL,event_seq INTEGER NOT NULL);
CREATE TRIGGER revision_events_no_update BEFORE UPDATE ON legacy_revision_events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER revision_events_no_delete BEFORE DELETE ON legacy_revision_events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER revision_proposals_no_update BEFORE UPDATE ON legacy_revision_proposals BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER revision_proposals_no_delete BEFORE DELETE ON legacy_revision_proposals BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TABLE account_state(id INTEGER PRIMARY KEY CHECK(id=1),denial_json TEXT);
CREATE TRIGGER account_denial_no_reset BEFORE UPDATE ON account_state WHEN OLD.denial_json IS NOT NULL AND NEW.denial_json IS NOT OLD.denial_json BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TABLE old_intents(handle TEXT PRIMARY KEY,row_json TEXT NOT NULL,row_sha TEXT NOT NULL);
CREATE TABLE old_claims(kind TEXT NOT NULL,fingerprint TEXT NOT NULL,handle TEXT NOT NULL REFERENCES old_intents(handle),PRIMARY KEY(kind,fingerprint,handle));
CREATE INDEX old_claim_lookup ON old_claims(kind,fingerprint);
CREATE TABLE events(seq INTEGER PRIMARY KEY,previous_sha TEXT,event_sha TEXT NOT NULL,event_json TEXT NOT NULL);
CREATE TABLE fact_batches(batch_key TEXT PRIMARY KEY,facts_sha TEXT NOT NULL,start_seq INTEGER NOT NULL,end_seq INTEGER NOT NULL);
CREATE TABLE target_overlays(handle TEXT PRIMARY KEY,origin TEXT NOT NULL,slot_key TEXT,row_json TEXT NOT NULL,row_sha TEXT NOT NULL,event_seq INTEGER NOT NULL);
CREATE INDEX staged_slot_lookup ON target_overlays(slot_key);
CREATE TABLE intent_versions(handle TEXT NOT NULL,event_seq INTEGER NOT NULL,row_json TEXT NOT NULL,row_sha TEXT NOT NULL,PRIMARY KEY(handle,event_seq));
CREATE TABLE target_claims(kind TEXT NOT NULL,fingerprint TEXT NOT NULL,handle TEXT NOT NULL REFERENCES target_overlays(handle),PRIMARY KEY(kind,fingerprint,handle));
CREATE INDEX target_claim_lookup ON target_claims(kind,fingerprint);
CREATE TABLE slot_batches(slot_key TEXT PRIMARY KEY,descriptor_json TEXT NOT NULL,descriptor_sha TEXT NOT NULL,event_seq INTEGER NOT NULL);
CREATE TABLE slot_members(slot_key TEXT NOT NULL REFERENCES slot_batches(slot_key),ordinal INTEGER NOT NULL,handle TEXT NOT NULL UNIQUE REFERENCES target_overlays(handle),PRIMARY KEY(slot_key,ordinal));
CREATE TABLE slot_dispatch_state(handle TEXT PRIMARY KEY NOT NULL,claim_seq INTEGER NOT NULL,claim_sha TEXT NOT NULL,body_sha TEXT NOT NULL,source_sha TEXT NOT NULL,phase TEXT NOT NULL,phase_seq INTEGER NOT NULL);
CREATE TRIGGER slot_dispatch_no_delete BEFORE DELETE ON slot_dispatch_state BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TABLE slot_observations(seq INTEGER PRIMARY KEY,handle TEXT NOT NULL,source_sha TEXT NOT NULL,reference_sha TEXT NOT NULL,projection_sha TEXT NOT NULL,response_sha TEXT NOT NULL);
CREATE INDEX slot_observation_lookup ON slot_observations(handle,seq);
CREATE TRIGGER slot_observation_no_update BEFORE UPDATE ON slot_observations BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER slot_observation_no_delete BEFORE DELETE ON slot_observations BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER slot_batches_no_update BEFORE UPDATE ON slot_batches BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER slot_batches_no_delete BEFORE DELETE ON slot_batches BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER slot_members_no_update BEFORE UPDATE ON slot_members BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER slot_members_no_delete BEFORE DELETE ON slot_members BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER target_claims_no_update BEFORE UPDATE ON target_claims BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER target_claims_no_delete BEFORE DELETE ON target_claims BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TABLE return_receipts(handle TEXT NOT NULL,claim_seq INTEGER NOT NULL,method TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha TEXT NOT NULL,PRIMARY KEY(handle,claim_seq));
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER batches_no_update BEFORE UPDATE ON fact_batches BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER batches_no_delete BEFORE DELETE ON fact_batches BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER receipts_no_update BEFORE UPDATE ON return_receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER receipts_no_delete BEFORE DELETE ON return_receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER versions_no_update BEFORE UPDATE ON intent_versions BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER versions_no_delete BEFORE DELETE ON intent_versions BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
''')
                    db.execute('INSERT INTO meta VALUES(1,?,?,?,?,?,0,NULL)',
                        (PROFILE,self.account,canonical(list(identity)),canonical(baseline),baseline_sha))
                    db.execute('INSERT INTO legacy_metadata VALUES(1,?,?,0)',
                               (canonical(legacy_metadata),digest(legacy_metadata)))
                    db.execute('INSERT INTO account_state VALUES(1,?)',
                               (canonical(value['denial']) if value['denial'] is not None else None,))
                    for handle,pending in value.get('revision_pending_images',{}).items():
                        if type(pending) is not dict or type(pending.get('proposal_sha256')) is not str:
                            _fail()
                        db.execute('INSERT INTO legacy_revision_proposals VALUES(?,?,0)',
                                   (pending['proposal_sha256'],handle))
                    for handle, row in value['targets'].items():
                        db.execute('INSERT INTO old_intents VALUES(?,?,?)', (handle,canonical(row),digest(row)))
                    db.executemany('INSERT INTO old_claims VALUES(?,?,?)', sorted(claims))
                    db.execute('PRAGMA application_id=1464026435')
                    db.execute('PRAGMA user_version=1')
                    self._guard()
                    if self.old._read_legacy() != value:
                        _fail()
                    db.execute('COMMIT')
                    fault('baseline_committed')
                elif names != _SCHEMA_NAMES:
                    _fail()
                meta = self._meta(db, identity)
                if meta['baseline_sha'] != baseline_sha:
                    _fail()
                self._check_old_index(db, meta)
                self._head(db, identity, recover=True, initializing=marker == initial, bootstrap=True)
                fault('head_written')
                if marker == initial:
                    atomic_write(self.marker_path, active)
                    fault('marker_activated')
                if enrollment == initial:
                    atomic_write(self.enrollment_path, active)
                self._guard()
                return {'state':'BASELINE_INDEXED', 'account_key':self.account,
                        'baseline_sha256':baseline_sha, 'targets':len(value['targets'])}

    def old_target(self, handle):
        with self.old.legacy.dispatch_lock():
            with self._db() as (db, identity):
                self._head(db,identity,recover=True)
                self._check_old_index(db, self._meta(db, identity))
                row = db.execute('SELECT row_json,row_sha FROM old_intents WHERE handle=?',(handle,)).fetchone()
                if row is None:
                    return None
                value = json.loads(row['row_json'])
                if digest(value) != row['row_sha'] or value.get('intent_handle') != handle:
                    _fail()
                self._guard()
                return value

    def old_conflicts(self, kind, fingerprint):
        with self.old.legacy.dispatch_lock():
            with self._db() as (db, identity):
                self._head(db,identity,recover=True)
                self._check_old_index(db, self._meta(db, identity))
                result = [row[0] for row in db.execute('SELECT handle FROM old_claims WHERE kind=? AND fingerprint=? ORDER BY handle',(kind,fingerprint))]
                self._guard()
                return result

    @staticmethod
    def _slot_conflicts(db, reference, claims):
        pairs = [('DRAFT_REF',digest(reference))] + [tuple(item) for item in claims]
        handles = set()
        for kind,fingerprint in pairs:
            handles.update(row[0] for row in db.execute(
                "SELECT c.handle FROM target_claims c JOIN target_overlays o ON o.handle=c.handle "
                "WHERE o.origin='SLOT' AND c.kind=? AND c.fingerprint=?",(kind,fingerprint)))
        return sorted(handles)

    def slot_conflicts_held(self, reference, claims):
        """Report whole original groups under the already-held account lock."""
        with self._db(readonly=True) as (db,identity):
            self._head(db,identity,recover=False)
            self._check_old_index(db,self._meta(db,identity))
            selected = _ContinuationSession(self,db,identity,None,None)
            try:
                result = []
                for handle in self._slot_conflicts(db,reference,claims):
                    row = selected._row(handle)
                    result.append({'intent_handle':handle,'state':row['state'],
                                   'submit_count':row['submit_count']})
                self._guard()
                return result
            finally:
                selected.active = False

    def legacy_view(self):
        """Original bounded inventory projection plus proof-bound old overlays."""
        from .draft_revision_gate import _ACTIVE, RevisionExecutionGate
        active = _ACTIVE.get()
        recovering = (active is not None and type(active[0]) is RevisionExecutionGate
                      and active[0].service.policy is self.old.policy and active[0].held() is True)
        with self._db(readonly=not recovering) as (db, identity):
            if recovering:
                self._head(db,identity,recover=True)
            db.execute('BEGIN')
            self._head(db,identity,recover=False)
            meta = self._meta(db,identity)
            self._check_old_index(db,meta)
            entry = db.execute('SELECT * FROM legacy_metadata WHERE id=1').fetchone()
            if entry is None:
                _fail()
            metadata = json.loads(entry['value_json'])
            initial_metadata = deepcopy(metadata)
            if digest(metadata) != entry['value_sha']:
                _fail()
            if entry['event_seq'] == 0:
                if entry['value_sha'] != json.loads(meta['baseline'])['legacy_metadata_sha']:
                    _fail()
            else:
                event = db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(entry['event_seq'],)).fetchone()
                if event is None:
                    _fail()
                parsed = json.loads(event['event_json'])
                if (digest(parsed) != event['event_sha'] or parsed.get('kind') != 'LEGACY_BATCH'
                        or parsed.get('metadata_sha') != entry['value_sha']):
                    _fail()
            for latest in db.execute('SELECT * FROM legacy_latest ORDER BY event_seq,field,key_text'):
                delta = json.loads(latest['entry_json'])
                event = db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',
                                   (latest['event_seq'],)).fetchone()
                if event is None:
                    _fail()
                parsed = json.loads(event['event_json'])
                if (digest(parsed) != event['event_sha'] or parsed.get('kind') != 'LEGACY_BATCH'
                        or delta not in parsed.get('deltas',[])
                        or delta.get('field') != latest['field']
                        or canonical(delta.get('key')) != latest['key_text']):
                    _fail()
                field, key = delta['field'], delta['key']
                if field == 'targets':
                    _fail()
                if key is None:
                    metadata[field] = deepcopy(delta['new'])
                else:
                    if type(key) is not str or type(metadata.get(field)) is not dict:
                        _fail()
                    metadata[field][key] = deepcopy(delta['new'])
            self._check_revision_projection(db,initial_metadata,metadata)
            handles = {row[0] for row in db.execute('SELECT handle FROM old_intents')}
            handles.update(row[0] for row in db.execute("SELECT handle FROM target_overlays WHERE origin='OLD'"))
            selected = _ContinuationSession(self,db,identity,None,None)
            try:
                value = dict(metadata,targets={handle:selected._row(handle) for handle in sorted(handles)})
            finally:
                selected.active = False
            self._validate_legacy_proofs(value)
            self._head(db,identity,recover=False)
            self._guard()
            db.execute('COMMIT')
            return value

    def _check_revision_projection(self, db, initial, current):
        """Recheck affected original revision members against immutable deltas."""
        fields={'revision_pending_images','revision_pending_baselines','revision_pending_uploads',
                'revision_reservations','revision_successors'}
        handles=[row[0] for row in db.execute('SELECT DISTINCT handle FROM legacy_revision_events')]
        for handle in handles:
            self._guard()
            state={field:deepcopy(initial.get(field,{}).get(handle)) for field in fields}
            present={field:handle in initial.get(field,{}) for field in fields}
            links=db.execute('SELECT event_seq,event_sha FROM legacy_revision_events WHERE handle=? ORDER BY event_seq',(handle,))
            for link in links:
                row=db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(link['event_seq'],)).fetchone()
                if row is None:
                    _fail()
                event=json.loads(row['event_json'])
                if digest(event)!=row['event_sha'] or row['event_sha']!=link['event_sha'] or event.get('kind')!='LEGACY_BATCH':
                    _fail()
                for delta in event.get('deltas',[]):
                    field,key=delta.get('field'),delta.get('key')
                    if field not in fields:
                        continue
                    if key is None:
                        old=delta.get('old') or {};new=delta.get('new')
                        if type(old) is not dict or type(new) is not dict:
                            _fail()
                        old_present=handle in old;new_present=handle in new
                        before=old.get(handle);after=new.get(handle)
                    elif key==handle:
                        old_present=delta.get('old_present');new_present=True
                        before=delta.get('old');after=delta.get('new')
                    else:
                        continue
                    if old_present != present[field] or before != state[field] or not new_present:
                        _fail()
                    state[field]=deepcopy(after);present[field]=True
            for field in fields:
                projected=current.get(field,{})
                if type(projected) is not dict or (handle in projected)!=present[field] or projected.get(handle)!=state[field]:
                    _fail()

    def _validate_legacy_proofs(self, value):
        """Retain the original cold-read checks for revision evidence."""
        from .current_publication_pending_image import validate as validate_pending, verify_case_link
        from .draft_revision_pending_baseline import validate as validate_baseline
        from .draft_revision_pending_upload import validate as validate_upload
        required={'schema','account_key','batches','targets','denial','sequence'}
        optional={'revision_reservations','revision_successors','revision_pending_images',
                  'revision_pending_baselines','revision_pending_uploads'}
        if (type(value) is not dict or set(value)-optional != required
                or value.get('schema') != 1 or value.get('account_key') != self.account
                or type(value.get('sequence')) is not int or value['sequence'] < 0
                or type(value.get('batches')) is not dict or type(value.get('targets')) is not dict):
            _fail()
        targets=value['targets']
        pending=value.get('revision_pending_images',{})
        baselines=value.get('revision_pending_baselines',{})
        uploads=value.get('revision_pending_uploads',{})
        reservations=value.get('revision_reservations',{})
        successors=value.get('revision_successors',{})
        if (any(type(item) is not dict for item in (pending,baselines,uploads,reservations,successors))
                or not set(pending)<=set(targets) or not set(baselines)<=set(pending)
                or not set(uploads)<=set(baselines) or not set(reservations)<=set(targets)
                or not set(successors)<=set(reservations)):
            _fail()
        for handle,record in pending.items():
            validate_pending(targets[handle],record)
        for handle,record in baselines.items():
            validate_baseline(record,pending[handle])
        for handle,record in uploads.items():
            validate_upload(record,pending[handle],baselines[handle])
            self.old._verify_pending_upload_archive(handle,record)
        for handle,record in reservations.items():
            self.old._verify_revision_reservation(handle,targets[handle],record)
            if handle in pending:
                verify_case_link(self.old,value,handle,record['case_id'],self.old.runtime_guard)
        for handle,record in successors.items():
            self.old._verify_revision_successor(handle,targets[handle],reservations[handle],record)

    def legacy_save(self, value):
        """Accept revision changes only under the actual same-account gate."""
        from .draft_revision_gate import _ACTIVE, RevisionExecutionGate
        active = _ACTIVE.get()
        if (active is None or type(active[0]) is not RevisionExecutionGate
                or active[0].service.policy is not self.old.policy or active[0].held() is not True):
            raise WCEError('CURRENT_PUBLICATION_CONTINUATION_WRITE_REQUIRED')
        gate = active[0]
        def current():
            if gate.held() is not True:
                _fail()
        self._legacy_delta_save(value,current)

    def legacy_prepare(self, value, inventory, targets, authority, guard):
        """Commit the original checked inventory preparation to the delta journal."""
        from .single_publication_source import is_authority, is_single, selected_targets, QUALITY
        from .saved_groups_publication_source import is_saved_groups
        from . import publication_inventory_access as observed
        from .current_publication_service import content_claims
        if not is_authority(authority) or not callable(guard):
            _fail()
        self.old._authority(authority,guard)
        actual = observed.load_complete(self.old.policy,inventory.get('inventory_handle'),guard)
        if actual != inventory or not observed.complete_for(authority, actual):
            _fail()
        derived = []
        for page,index,page_sha,target in observed.frozen_targets(self.old.policy,actual,guard):
            if page['observed_ms'] < authority.request_ms:
                _fail()
            rows = target['projection']['response']['news_item']
            derived.append({key:target[key] for key in ('reference','listed_update_time','projection_sha256','response_sha256')} | {
                'inventory_handle':actual['inventory_handle'],'page':page['page'],'page_sha256':page_sha,
                'page_index':index,'article_count':len(rows),'titles':[row['title'] for row in rows],
                'content_claims':content_claims(target['projection'])})
        derived.sort(key=lambda item:(item['page'],item['page_index']))
        if (len(derived) != actual.get('total_groups')
                or actual.get('observed_groups') != actual.get('total_groups')):
            _fail()
        derived = selected_targets(authority, actual, derived)
        if derived != targets:
            _fail()
        before = self.legacy_view()
        source = authority.evidence()['source_sha256']
        if (set(value['batches']) != set(before['batches']) | {source}
                or source in before['batches']
                or any(value['batches'][key] != item for key,item in before['batches'].items())):
            _fail()
        batch = value['batches'][source]
        if (batch['inventory_handle'] != actual['inventory_handle']
                or batch['inventory_sha256'] != digest(actual)
                or batch['authority'] != authority.evidence()):
            _fail()
        added = {key:row for key,row in value['targets'].items() if key not in before['targets']}
        if set(added) != set(batch['intent_handles']):
            _fail()
        by_reference = {item['reference']:item for item in derived}
        if len(by_reference) != len(derived):
            _fail()
        for handle,row in added.items():
            expected = by_reference.get(row.get('reference'))
            if (expected is None or set(row) != set(expected) | {
                    'intent_handle','batch_source_sha','account_key','binding_sha256',
                    'state','submit_count','task','reply','queries'} | ({'quality_source'} if is_single(authority) or is_saved_groups(authority) else set())
                    or (is_single(authority) and row.get('quality_source') != QUALITY)
                    or (is_saved_groups(authority) and row.get('quality_source') != authority.quality_source)
                    or row.get('intent_handle') != handle
                    or row.get('batch_source_sha') != source or row.get('account_key') != self.account
                    or row.get('binding_sha256') != self.binding or row.get('state') != 'READY'
                    or row.get('submit_count') != 0 or row.get('task') is not None or row.get('reply') is not None
                    or type(row.get('queries')) is not int or row['queries'] != 0
                    or any(row.get(key) != item for key,item in expected.items())):
                _fail()
            if is_saved_groups(authority):
                authority.check_target(row)
            self.old.guard_legacy(row['reference'],row['content_claims'],authority=authority,
                                  guard=guard,source_sha=source)
        def current():
            self.old._authority(authority,guard,source)
        self._legacy_delta_save(value,current,require_open=True)

    def _legacy_delta_save(self, value, current, *, require_open=False):
        """Private transaction primitive; caller must hold the account lock."""
        from .current_publication_delta import changes
        from .current_publication_store import _transition
        before = self.legacy_view()
        required={'schema','account_key','batches','targets','denial','sequence'}
        optional={'revision_reservations','revision_successors','revision_pending_images',
                  'revision_pending_baselines','revision_pending_uploads'}
        if type(value) is not dict or set(value)-optional != required:
            _fail()
        _transition(before,value,self.old._verify_recovery,self.old._verify_revision_reservation,
                    self.old._verify_revision_successor,self.old._verify_pending_upload_archive)
        if any(value['targets'].get(k) != row for k,row in before['targets'].items()):
            _fail()
        added = {k:row for k,row in value['targets'].items() if k not in before['targets']}
        delta = changes(before,value)
        current()
        with self._db() as (db,identity):
            self._head(db,identity,recover=True)
            meta = self._meta(db,identity)
            seq = meta['seq']+1
            event = {'profile':PROFILE,'account':self.account,'seq':seq,
                'previous_sha':meta['event_sha'],'kind':'LEGACY_BATCH',
                'deltas':delta,'targets':{k:digest(v) for k,v in added.items()}}
            event_sha = digest(event)
            db.execute('BEGIN IMMEDIATE')
            try:
                if require_open:
                    account = db.execute('SELECT denial_json FROM account_state WHERE id=1').fetchone()
                    if account is None or account['denial_json'] is not None:
                        _fail()
                db.execute('INSERT INTO events VALUES(?,?,?,?)',(seq,meta['event_sha'],event_sha,canonical(event)))
                for change in delta:
                    db.execute('INSERT INTO legacy_latest VALUES(?,?,?,?) '
                        'ON CONFLICT(field,key_text) DO UPDATE SET entry_json=excluded.entry_json,event_seq=excluded.event_seq',
                        (change['field'],canonical(change['key']),canonical(change),seq))
                affected = set()
                for change in delta:
                    if change['field'] not in {'revision_pending_images','revision_pending_baselines',
                                               'revision_pending_uploads','revision_reservations','revision_successors'}:
                        continue
                    if change['key'] is None:
                        if type(change['new']) is not dict:
                            _fail()
                        affected.update(change['new'])
                    else:
                        affected.add(change['key'])
                db.executemany('INSERT INTO legacy_revision_events VALUES(?,?,?)',
                               ((handle,seq,event_sha) for handle in sorted(affected)))
                for change in delta:
                    if change['field'] != 'revision_pending_images':
                        continue
                    pairs = (change['new'].items() if change['key'] is None else
                             [(change['key'],change['new'])])
                    for handle,pending in pairs:
                        if type(pending) is not dict or type(pending.get('proposal_sha256')) is not str:
                            _fail()
                        db.execute('INSERT OR IGNORE INTO legacy_revision_proposals VALUES(?,?,?)',
                                   (pending['proposal_sha256'],handle,seq))
                        existing = db.execute('SELECT handle FROM legacy_revision_proposals WHERE proposal_sha=?',
                                              (pending['proposal_sha256'],)).fetchone()
                        if existing is None or existing['handle'] != handle:
                            _fail()
                for handle,row in added.items():
                    reference = digest(row['reference'])
                    if self._slot_conflicts(db,row['reference'],row.get('content_claims',[])):
                        _fail()
                    db.execute('INSERT INTO target_overlays VALUES(?,?,?,?,?,?)',
                        (handle,'OLD',None,canonical(row),digest(row),seq))
                    db.execute('INSERT INTO intent_versions VALUES(?,?,?,?)',(handle,seq,canonical(row),digest(row)))
                    claims = [('DRAFT_REF',reference)] + [tuple(c) for c in row.get('content_claims',[])]
                    db.executemany('INSERT INTO target_claims VALUES(?,?,?)',((k,f,handle) for k,f in claims))
                db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1',(seq,event_sha))
                current()
                self._guard()
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise
            self._head(db,identity,recover=True)
        current()

    def append_unverified(self, batch_key, facts, *, fault=lambda phase: None):
        """Store non-authorizing facts in bounded chunks; never claim or send.

        This low-level primitive is not wired to a source provider. Callers
        must never interpret these records as an approved Source or intent.
        """
        if (type(batch_key) is not str or len(batch_key) != 64
                or any(c not in '0123456789abcdef' for c in batch_key)
                or type(facts) is not list or not 1 <= len(facts) <= 256):
            _fail()
        for fact in facts:
            if (type(fact) is not str or not 1 <= len(fact.encode('utf-8')) <= 4096):
                _fail()
        with self.old.legacy.dispatch_lock():
            with self._db() as (db, identity):
                self._head(db, identity, recover=True)
                meta = self._meta(db, identity)
                self._check_old_index(db, meta)
                facts_sha = digest(facts)
                existing = db.execute('SELECT * FROM fact_batches WHERE batch_key=?', (batch_key,)).fetchone()
                if existing is not None:
                    if (existing['facts_sha'] != facts_sha or existing['end_seq'] > meta['seq']
                            or existing['end_seq'] - existing['start_seq'] + 1 != len(facts)):
                        _fail()
                    for offset, fact in enumerate(facts):
                        seq = existing['start_seq'] + offset
                        stored = db.execute('SELECT event_sha,event_json FROM events WHERE seq=?', (seq,)).fetchone()
                        if stored is None:
                            _fail()
                        event = json.loads(stored['event_json'])
                        if (digest(event) != stored['event_sha'] or event.get('seq') != seq
                                or event.get('batch_key') != batch_key or event.get('value') != fact):
                            _fail()
                    return {'state':'UNVERIFIED_FACTS_STORED', 'sequence':existing['end_seq']}
                seq, previous = meta['seq'], meta['event_sha']
                first = seq + 1
                db.execute('BEGIN IMMEDIATE')
                try:
                    for fact in facts:
                        seq += 1
                        event = {'profile': PROFILE, 'account': self.account,
                            'seq': seq, 'previous_sha': previous,
                            'kind': 'UNVERIFIED_FACT', 'batch_key': batch_key, 'value': fact}
                        event_sha = digest(event)
                        db.execute('INSERT INTO events VALUES(?,?,?,?)',
                                   (seq, previous, event_sha, canonical(event)))
                        previous = event_sha
                    db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1', (seq, previous))
                    db.execute('INSERT INTO fact_batches VALUES(?,?,?,?)',
                               (batch_key, facts_sha, first, seq))
                    self._guard()
                    db.execute('COMMIT')
                except BaseException:
                    if db.in_transaction:
                        db.execute('ROLLBACK')
                    raise
                fault('after_db_commit')
                self._head(db, identity, recover=True)
                self._guard()
                return {'state': 'UNVERIFIED_FACTS_STORED', 'sequence': seq}

    @contextmanager
    def session(self, authorization_check, conflict_check):
        """Private host adapter, never exposed as a tool or a grant factory.

        Both callbacks must revalidate actual host-owned evidence. A callback
        returning True is only a hook; this module cannot establish its origin.
        The product integration must bind exact trusted implementations.
        """
        if not callable(authorization_check) or not callable(conflict_check):
            _fail()
        # Serialize our own same-process preflight before the old dispatcher
        # opens its history DB. The real cross-process/account lock still owns
        # admission and no waiting or additional business quota is introduced.
        key = (str(self.old.legacy.anchor), self.account)
        with _LOCAL_LOCKS_GUARD:
            local = _LOCAL_LOCKS.get(key)
            if local is None:
                local = threading.Lock()
                _LOCAL_LOCKS[key] = local
        if not local.acquire(blocking=False):
            _fail()
        try:
            with self.old.legacy.dispatch_lock():
                with self._db() as (db, identity):
                    self._head(db, identity, recover=True)
                    self._check_old_index(db, self._meta(db, identity))
                    session = _ContinuationSession(self, db, identity, authorization_check, conflict_check)
                    try:
                        yield session
                    finally:
                        session.active = False
        finally:
            local.release()


class _ContinuationSession:
    def __init__(self, index, db, identity, authorization_check, conflict_check):
        self.index, self.db, self.identity = index, db, identity
        self.authorization_check, self.conflict_check = authorization_check, conflict_check
        self.pid, self.thread, self.active = os.getpid(), threading.get_ident(), True

    def _check_active(self):
        if not self.active or self.pid != os.getpid() or self.thread != threading.get_ident():
            _fail()

    def _guard(self, action, row):
        self._check_active()
        self.index._guard()
        try:
            authorized = self.authorization_check(action, deepcopy(row))
        except Exception:
            _fail()
        if authorized is not True:
            _fail()

    def _row(self, handle):
        self._check_active()
        entry = self.db.execute('SELECT * FROM target_overlays WHERE handle=?', (handle,)).fetchone()
        if entry is None:
            entry = self.db.execute('SELECT row_json,row_sha FROM old_intents WHERE handle=?', (handle,)).fetchone()
            if entry is None:
                _fail()
        else:
            event = self.db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',
                                    (entry['event_seq'],)).fetchone()
            if event is None:
                _fail()
            parsed = json.loads(event['event_json'])
            linked = (parsed.get('targets',{}).get(handle) == entry['row_sha']
                      if parsed.get('kind') == 'LEGACY_BATCH'
                      else parsed.get('handle') == handle and parsed.get('row_sha') == entry['row_sha'])
            if digest(parsed) != event['event_sha'] or not linked:
                _fail()
        row = json.loads(entry['row_json'])
        if digest(row) != entry['row_sha'] or row.get('intent_handle') != handle:
            _fail()
        if 'slot_key' in entry.keys() and entry['slot_key'] != row.get('slot_key'):
            _fail()
        if row.get('recovered_receipt_sha256') is not None:
            stored = self.db.execute("SELECT * FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchall()
            if stored:
                receipt, task = self._receipt_task(handle,row,stored)
                if task is None or receipt != row['recovered_receipt_sha256'] or asdict(task) != row.get('task'):
                    _fail()
            else:
                value = self.index.old._read_legacy()
                original = value['targets'].get(handle)
                if original is None:
                    _fail()
                recovered = self.index.old._staged_submit(value,original,self.index.old.runtime_guard,check_conflict=False)
                if (recovered.get('state') != 'ORIGINAL_TASK_STAGED_LOCAL_ONLY'
                        or recovered.get('receipt_sha256') != row['recovered_receipt_sha256']
                        or asdict(recovered.get('task')) != row.get('task')):
                    _fail()
        if row.get('submit_rejection_receipt_sha') is not None:
            stored = self.db.execute("SELECT * FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchall()
            receipt_sha, task = self._receipt_task(handle,row,stored)
            if receipt_sha != row['submit_rejection_receipt_sha'] or task is not None:
                _fail()
            receipt = json.loads(stored[0]['receipt_json'])
            from .current_publication_store import PERMISSION_ERRORS
            code = receipt.get('error_code')
            state = 'DENIED' if code in PERMISSION_ERRORS else 'PLATFORM_REJECTED'
            if (type(code) is not int or code == 0 or receipt.get('reason') != 'PLATFORM_REJECTED'
                    or receipt.get('http_status') != 200 or row.get('state') != state):
                _fail()
            expected_reply = {'error_code':code,'reason':receipt['reason'],
                'api_method':'freepublish.submit','request_sha256':receipt['request_sha'],
                'response_sha256':receipt['response_sha'],'http_status':receipt['http_status']}
            if row.get('reply') != expected_reply:
                _fail()
        if row.get('applied_query_seq') is not None:
            receipt, prior, receipt_sha = self._query_receipt(handle,row,row['applied_query_seq'])
            if receipt_sha != row.get('applied_query_receipt_sha'):
                _fail()
            expected = self._query_outcome(handle,prior,receipt)
            keys = ['state','reply','task','submit_count','reference']
            if not (type(row.get('query_unknown_seq')) is int
                    and row['query_unknown_seq'] > row['applied_query_seq']):
                keys.append('last_query')
            for key in keys:
                if row.get(key) != expected.get(key):
                    _fail()
        return row

    def target(self, handle):
        row = self._row(handle)
        self._guard('read', row)
        return row

    def _save(self, handle, row, origin, kind, *, claims=(), check_action, check_row,
              receipt=None, denial=None, post_return=False, fault=lambda phase: None):
        self._check_active()
        meta = self.index._meta(self.db, self.identity)
        seq = meta['seq'] + 1
        event = {'profile': PROFILE, 'account': self.index.account, 'seq': seq,
                 'previous_sha': meta['event_sha'], 'kind': kind,
                 'handle': handle, 'row_sha': digest(row), 'claims': [list(x) for x in claims]}
        event_sha = digest(event)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?)',
                (seq, meta['event_sha'], event_sha, canonical(event)))
            self.db.execute('INSERT INTO target_overlays VALUES(?,?,?,?,?,?) '
                'ON CONFLICT(handle) DO UPDATE SET row_json=excluded.row_json,row_sha=excluded.row_sha,event_seq=excluded.event_seq',
                (handle,origin,row.get('slot_key'),canonical(row),digest(row),seq))
            self.db.execute('INSERT INTO intent_versions VALUES(?,?,?,?)',
                            (handle,seq,canonical(row),digest(row)))
            if kind=='SUBMIT_CLAIM' and origin=='SLOT' and row.get('dispatch_protocol')=='SLOT_DISPATCH_BARRIER_V1':
                import json as _json
                raw=_json.dumps({'media_id':row['reference']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
                self.db.execute('INSERT INTO slot_dispatch_state VALUES(?,?,?,?,?,?,?)',
                    (handle,seq,event_sha,sha256(raw).hexdigest(),row['batch_source_sha'],'RESERVED',seq))
            self.db.executemany('INSERT OR IGNORE INTO target_claims VALUES(?,?,?)',
                                ((k, f, handle) for k, f in claims))
            if receipt is not None:
                self.db.execute('INSERT INTO return_receipts VALUES(?,?,?,?,?)',
                    (handle,receipt['claim_seq'],receipt['method'],canonical(receipt),digest(receipt)))
            if denial is not None:
                self.db.execute('UPDATE account_state SET denial_json=? WHERE id=1',(canonical(denial),))
            self.db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1', (seq,event_sha))
            if post_return:
                # Once a request has returned, persist that bounded result even
                # if its sending deadline expired. No new request is enabled.
                self._check_active()
                path_check(self.index.old.legacy.anchor, True)
                if _owned_file(self.index.db_path) != self.identity:
                    _fail()
                self.index._meta(self.db, self.identity)
            else:
                self._guard(check_action, check_row)
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise
        fault('after_db_commit')
        self.index._head(self.db,self.identity,recover=True)
        return self._row(handle)

    def stage_target(self, row, *, fault=lambda phase: None):
        from .current_publication_store import HANDLE
        if (type(row) is not dict or type(row.get('intent_handle')) is not str
                or HANDLE.fullmatch(row['intent_handle']) is None
                or row.get('account_key') != self.index.account
                or row.get('binding_sha256') != self.index.binding
                or row.get('state') != 'READY' or row.get('submit_count') != 0
                or row.get('task') is not None or type(row.get('reference')) is not str
                or not row['reference'] or type(row.get('content_claims')) is not list
                or type(row.get('queries')) is not int or row['queries'] != 0
                or type(row.get('article_count')) is not int or not 1 <= row['article_count'] <= 8
                or type(row.get('slot_key')) is not str or len(row['slot_key']) != 64
                or any(c not in '0123456789abcdef' for c in row['slot_key'])
                or type(row.get('batch_source_sha')) is not str or len(row['batch_source_sha']) != 64
                or any(c not in '0123456789abcdef' for c in row['batch_source_sha'])):
            _fail()
        handle = row['intent_handle']
        self._guard('stage', row)
        account = self.db.execute('SELECT denial_json FROM account_state WHERE id=1').fetchone()
        if account is None or account['denial_json'] is not None:
            _fail()
        ref = digest(row['reference'])
        existing = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?', (handle,)).fetchone()
        if existing is not None:
            if existing['origin'] != 'SLOT' or self._row(handle) != row:
                _fail()
            self._guard('stage', row)
            return row
        if self._slot(row['slot_key']) is not None:
            _fail()
        if (self.db.execute('SELECT 1 FROM old_intents WHERE handle=?', (handle,)).fetchone()
                or self.db.execute('SELECT 1 FROM old_claims WHERE kind=? AND fingerprint=?', ('DRAFT_REF',ref)).fetchone()
                or self.db.execute('SELECT 1 FROM target_claims WHERE kind=? AND fingerprint=?', ('DRAFT_REF',ref)).fetchone()):
            _fail()
        try:
            clear = self.conflict_check('stage', deepcopy(row))
        except Exception:
            _fail()
        if clear is not True:
            _fail()
        self._guard('stage', row)
        content = row['content_claims']
        if any(type(c) not in (list,tuple) or len(c)!=2
                or any(type(x) is not str or not x for x in c) for c in content):
            _fail()
        return self._save(handle,row,'SLOT','STAGED',claims=[('DRAFT_REF',ref),*content],
                          check_action='stage',check_row=row,fault=fault)

    def _slot(self, key):
        batch = self.db.execute('SELECT * FROM slot_batches WHERE slot_key=?',(key,)).fetchone()
        if batch is None:
            return None
        descriptor = json.loads(batch['descriptor_json'])
        event = self.db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',
                                (batch['event_seq'],)).fetchone()
        if event is None:
            _fail()
        parsed = json.loads(event['event_json'])
        members = self.db.execute('SELECT ordinal,handle FROM slot_members WHERE slot_key=? ORDER BY ordinal',(key,)).fetchall()
        if (digest(descriptor) != batch['descriptor_sha'] or descriptor.get('slot_key') != key
                or self.slot_key(descriptor.get('identity')) != key
                or descriptor.get('binding_sha') != self.index.binding
                or digest(parsed) != event['event_sha'] or parsed.get('kind') != 'SLOT_FROZEN'
                or parsed.get('slot_key') != key or parsed.get('slot_sha') != batch['descriptor_sha']
                or [tuple(item) for item in members] != list(enumerate(
                    [group['handle'] for group in descriptor.get('groups',[])]))):
            _fail()
        return descriptor

    def slot_key(self, identity):
        """Compute the logical identity from stable host-validated inputs."""
        from datetime import date
        fields = {'principal_id','tenant_id','producer_role','channel','schedule_id','day','slot'}
        if (type(identity) is not dict or set(identity) != fields
                or any(type(v) is not str or not v or v != v.strip() or not v.isprintable()
                       for v in identity.values())):
            _fail()
        actor = self.index.old.policy.data['actor']
        if identity['principal_id'] != actor['principal_id'] or identity['tenant_id'] != actor['tenant_id']:
            _fail()
        try:
            if date.fromisoformat(identity['day']).isoformat() != identity['day']:
                _fail()
        except ValueError:
            _fail()
        return digest({'account_key':self.index.account,**identity})

    def freeze_slot(self, descriptor, *, fault=lambda phase: None):
        """Freeze a host-qualified complete logical slot, without publishing."""
        fields = {'identity','source_sha','binding_sha','standing_sha','control_sha','producer_sha','qa_sha','groups'}
        extended = fields | {'profile','group_order','conflicts','completed_slot_handle'}
        hashes = fields - {'identity','groups'}
        is_extended = type(descriptor) is dict and set(descriptor) == extended
        if (type(descriptor) is not dict or set(descriptor) not in (fields, extended)
                or any(type(descriptor[k]) is not str or len(descriptor[k])!=64
                       or any(c not in '0123456789abcdef' for c in descriptor[k])
                       for k in hashes)
                or descriptor['binding_sha'] != self.index.binding
                or type(descriptor['groups']) is not list or (not descriptor['groups'] and not is_extended)
                or any(type(g) is not dict or set(g)!={'handle','save_sha','get_sha','content_sha'}
                       or type(g['handle']) is not str
                       or any(type(g[k]) is not str or len(g[k])!=64
                              or any(c not in '0123456789abcdef' for c in g[k])
                              for k in ('save_sha','get_sha','content_sha'))
                       for g in descriptor['groups'])
                or len({g['handle'] for g in descriptor['groups']}) != len(descriptor['groups'])):
            _fail()
        if is_extended:
            conflicts, order = descriptor['conflicts'], descriptor['group_order']
            if (descriptor['profile'] != 'SLOT_UNOBSERVED_MANIFEST_V1'
                    or type(descriptor['completed_slot_handle']) is not str
                    or __import__('re').fullmatch(r'completed-slot-[a-f0-9]{48}',descriptor['completed_slot_handle']) is None
                    or type(conflicts) is not list or type(order) is not list or not order
                    or len(order) != len(conflicts) + len(descriptor['groups'])
                    or any(type(item) is not dict or set(item) != {'kind','index','group_sha'}
                           or item['kind'] not in {'READY','ORIGINAL'} or type(item['index']) is not int
                           or type(item['group_sha']) is not str or len(item['group_sha']) != 64
                           or any(c not in '0123456789abcdef' for c in item['group_sha']) for item in order)
                    or sorted(x['index'] for x in order if x['kind']=='READY') != list(range(len(descriptor['groups'])))
                    or sorted(x['index'] for x in order if x['kind']=='ORIGINAL') != list(range(len(conflicts)))
                    or any(type(item) is not dict or set(item) != {'reference','reference_sha','claims','original_handles','legacy_intents'}
                           or type(item['reference']) is not str or not item['reference']
                           or type(item['reference_sha']) is not str or len(item['reference_sha']) != 64
                           or any(c not in '0123456789abcdef' for c in item['reference_sha'])
                           or item['reference_sha'] != digest(item['reference'])
                           or type(item['claims']) is not list
                           or any(type(c) is not list or len(c)!=2 or any(type(x) is not str or not x for x in c) for c in item['claims'])
                           or type(item['original_handles']) is not list
                           or item['original_handles'] != sorted(set(item['original_handles']))
                           or any(type(h) is not str for h in item['original_handles'])
                           or type(item['legacy_intents']) is not list
                           or item['legacy_intents'] != sorted(set(item['legacy_intents']))
                           or any(type(h) is not str or not h for h in item['legacy_intents'])
                           or not (item['original_handles'] or item['legacy_intents']) for item in conflicts)):
                _fail()
            for conflict in conflicts:
                actual_owners = set()
                for kind, fingerprint in [('DRAFT_REF',conflict['reference_sha']),*conflict['claims']]:
                    for table in ('old_claims','target_claims'):
                        actual_owners.update(r[0] for r in self.db.execute(
                            'SELECT handle FROM '+table+' WHERE kind=? AND fingerprint=?',(kind,fingerprint)))
                if sorted(actual_owners) != conflict['original_handles']:
                    _fail()
                for handle in conflict['original_handles']:
                    self._row(handle)
                from .current_publication_slot_stage import _legacy_conflicts
                if _legacy_conflicts(self,conflict['reference'],conflict['claims']) != conflict['legacy_intents']:
                    _fail()
        key = self.slot_key(descriptor['identity'])
        descriptor = dict(descriptor,slot_key=key)
        self._guard('freeze_slot',descriptor)
        existing = self._slot(key)
        if existing is not None:
            if existing != descriptor:
                _fail()
        staged = {item[0] for item in self.db.execute(
            "SELECT handle FROM target_overlays WHERE origin='SLOT' AND slot_key=?",(key,))}
        if staged != {group['handle'] for group in descriptor['groups']}:
            _fail()
        for group in descriptor['groups']:
            handle = group['handle']
            row = self._row(handle)
            entry = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
            if (entry is None or entry['origin'] != 'SLOT'
                    or (existing is None and row.get('state') != 'READY')
                    or row.get('slot_key') != key or row.get('batch_source_sha') != descriptor['source_sha']
                    or any(row.get(k) != group[k] for k in ('save_sha','get_sha','content_sha'))):
                _fail()
        if existing is not None:
            self._guard('freeze_slot',descriptor)
            return {'state':'SLOT_FROZEN','slot_key':key,'slot_sha256':digest(existing)}
        meta = self.index._meta(self.db,self.identity)
        seq = meta['seq'] + 1
        event = {'profile':PROFILE,'account':self.index.account,'seq':seq,
            'previous_sha':meta['event_sha'],'kind':'SLOT_FROZEN',
            'slot_key':descriptor['slot_key'],'slot_sha':digest(descriptor)}
        event_sha = digest(event)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?)',(seq,meta['event_sha'],event_sha,canonical(event)))
            self.db.execute('INSERT INTO slot_batches VALUES(?,?,?,?)',
                            (key,canonical(descriptor),digest(descriptor),seq))
            self.db.executemany('INSERT INTO slot_members VALUES(?,?,?)',
                ((key,ordinal,group['handle']) for ordinal,group in enumerate(descriptor['groups'])))
            self.db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1',(seq,event_sha))
            self._guard('freeze_slot',descriptor)
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise
        fault('after_db_commit')
        self.index._head(self.db,self.identity,recover=True)
        if self._slot(key) != descriptor:
            _fail()
        return {'state':'SLOT_FROZEN','slot_key':key,'slot_sha256':digest(descriptor)}

    def claim(self, handle, *, quota=None, fault=lambda phase: None):
        row = self._row(handle)
        qualified = dict(row,quota=deepcopy(quota))
        self._guard('claim', qualified)
        target = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        if target is not None and target['origin'] == 'SLOT':
            slot = self._slot(row.get('slot_key'))
            if (slot is None or handle not in [group['handle'] for group in slot['groups']]
                    or slot['source_sha'] != row.get('batch_source_sha')):
                _fail()
        account = self.db.execute('SELECT denial_json FROM account_state WHERE id=1').fetchone()
        if account is None or account['denial_json'] is not None:
            _fail()
        if row.get('state') != 'READY' or row.get('submit_count') != 0:
            _fail()
        claims = row.get('content_claims', [])
        if type(claims) is not list or any(type(c) not in (list,tuple) or len(c)!=2
                or any(type(x) is not str or not x for x in c) for c in claims):
            _fail()
        for kind, fingerprint in claims:
            owners = [r[0] for r in self.db.execute(
                'SELECT handle FROM old_claims WHERE kind=? AND fingerprint=? UNION SELECT handle FROM target_claims WHERE kind=? AND fingerprint=?',
                (kind,fingerprint,kind,fingerprint))]
            for owner in owners:
                if owner != handle and self._row(owner).get('submit_count') == 1:
                    _fail()
        try:
            clear = self.conflict_check('claim', deepcopy(qualified))
        except Exception:
            _fail()
        if clear is not True:
            _fail()
        self._guard('claim', qualified)
        updated = dict(qualified,state='SUBMIT_CLAIMED',submit_count=1)
        origin = (target['origin'] if target is not None else
                  ('OLD' if self.db.execute('SELECT 1 FROM old_intents WHERE handle=?',(handle,)).fetchone() else 'SLOT'))
        return self._save(handle,updated,origin,'SUBMIT_CLAIM',claims=claims,
                          check_action='claim',check_row=qualified,fault=fault)

    def mark_submit_unknown(self, handle, *, fault=lambda phase: None):
        row = self._row(handle)
        self._guard('recover', row)
        if row.get('state') == 'UNKNOWN' and row.get('submit_count') == 1:
            return row
        if row.get('state') != 'SUBMIT_CLAIMED' or row.get('submit_count') != 1 or row.get('task') is not None:
            _fail()
        if self.db.execute("SELECT 1 FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchone():
            _fail()
        updated = dict(row,state='UNKNOWN',reason='SUBMIT_RESULT_UNDETERMINED')
        entry = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        return self._save(handle,updated,entry['origin'],'SUBMIT_UNKNOWN',
                          check_action='recover',check_row=row,fault=fault)

    def submit_ticket(self, handle, request, token):
        from .http_transport import HTTPRequest
        from .publication_wire import DraftMediaID, encode
        row = self._row(handle)
        self._guard('send', row)
        if (row.get('state') != 'SUBMIT_CLAIMED' or row.get('submit_count') != 1
                or row.get('task') is not None or type(request) is not HTTPRequest):
            _fail()
        expected = encode('freepublish.submit', {'media_id': DraftMediaID(row['reference'],
            self.index.account, handle)}, token, account_key=self.index.account, intent_id=handle)
        if request != expected:
            _fail()
        entry = self.db.execute('SELECT event_seq FROM target_overlays WHERE handle=?', (handle,)).fetchone()
        event = self.db.execute('SELECT event_sha,event_json FROM events WHERE seq=?',
                                (entry['event_seq'],)).fetchone() if entry else None
        if event is None:
            _fail()
        claim = json.loads(event['event_json'])
        if (claim.get('kind') != 'SUBMIT_CLAIM' or claim.get('handle') != handle
                or digest(claim) != event['event_sha'] or claim.get('row_sha') != digest(row)):
            _fail()
        self._guard('send', row)
        return _SubmitTicket(self,handle,entry['event_seq'],event['event_sha'],request,token,
                             os.getpid(),threading.get_ident(),_TICKET_SEAL)

    def stage_submit_reply(self, ticket, response, token, *, fault=lambda phase: None):
        from .publication_receipt import _project
        from .publication_wire import parse
        self._check_active()
        if (type(ticket) is not _SubmitTicket or ticket.seal is not _TICKET_SEAL
                or ticket.session is not self or ticket.token is not token
                or ticket.pid != os.getpid() or ticket.thread != threading.get_ident()):
            _fail()
        row = self._row(ticket.handle)
        event = self.db.execute('SELECT event_sha,event_json FROM events WHERE seq=?',
                                (ticket.claim_seq,)).fetchone()
        if (row.get('state') != 'SUBMIT_CLAIMED' or row.get('submit_count') != 1
                or event is None or event['event_sha'] != ticket.claim_sha
                or digest(json.loads(event['event_json'])) != ticket.claim_sha
                or json.loads(event['event_json']).get('kind') != 'SUBMIT_CLAIM'
                or json.loads(event['event_json']).get('handle') != ticket.handle
                or json.loads(event['event_json']).get('row_sha') != digest(row)):
            _fail()
        reply = parse('freepublish.submit', response, token,
                      account_key=self.index.account,intent_id=ticket.handle)
        receipt = {'profile': 'CONTINUATION_SUBMIT_RECEIPT_V1',
            'account': self.index.account, 'binding': self.index.binding,
            'handle': ticket.handle, 'claim_seq':ticket.claim_seq, 'claim_sha':ticket.claim_sha,
            'method':'freepublish.submit',
            'request_sha':sha256(ticket.request.body).hexdigest(),
            'reason':reply.reason, 'error_code':reply.error_code,
            'http_status':reply.http_status, 'response_sha':reply.response_sha,
            'result':_project(reply.result)}
        existing = self.db.execute('SELECT receipt_json,receipt_sha FROM return_receipts '
            'WHERE handle=? AND claim_seq=?',(ticket.handle,ticket.claim_seq)).fetchone()
        if existing is not None:
            if existing['receipt_sha'] != digest(receipt) or json.loads(existing['receipt_json']) != receipt:
                _fail()
            return {'state':'ORIGINAL_REPLY_STAGED','receipt_sha256':digest(receipt)}
        origin = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(ticket.handle,)).fetchone()['origin']
        claims = []
        if (reply.reason == 'PARSED_SUCCESS' and type(reply.result) is dict
                and reply.result.get('task') is not None):
            task = reply.result['task']
            claims.append(('TASK',digest([task.kind,task.digits])))
        self._save(ticket.handle,row,origin,'SUBMIT_REPLY_STAGED',check_action='receipt',check_row=row,
                   claims=claims,receipt=receipt,post_return=True,fault=fault)
        return {'state':'ORIGINAL_REPLY_STAGED','receipt_sha256':digest(receipt)}

    def adopt_staged_submit(self, handle, *, fault=lambda phase: None):
        """Adopt only the previously stored response for this exact original claim."""
        row = self._row(handle)
        self._guard('recover', row)
        if row.get('task') is not None:
            return row
        if row.get('state') not in {'SUBMIT_CLAIMED','UNKNOWN'} or row.get('submit_count') != 1:
            _fail()
        receipts = self.db.execute("SELECT * FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchall()
        if not receipts:
            return {'state':'ORIGINAL_RECEIPT_NOT_FOUND'}
        receipt_sha, task = self._receipt_task(handle,row,receipts)
        if task is None:
            receipt = json.loads(receipts[0]['receipt_json'])
            code = receipt.get('error_code')
            if (type(code) is not int or code == 0 or receipt.get('reason') != 'PLATFORM_REJECTED'
                    or receipt.get('http_status') != 200):
                return {'state':'ORIGINAL_RECEIPT_UNDETERMINED'}
            from .current_publication_store import PERMISSION_ERRORS
            state = 'DENIED' if code in PERMISSION_ERRORS else 'PLATFORM_REJECTED'
            reply = {'error_code':code,'reason':receipt['reason'],'api_method':'freepublish.submit',
                'request_sha256':receipt['request_sha'],'response_sha256':receipt['response_sha'],
                'http_status':receipt['http_status']}
            updated = dict(row,state=state,reply=reply,submit_rejection_receipt_sha=receipt_sha)
            self._guard('recover',updated)
            origin = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()['origin']
            denial = {'intent_handle':handle,'reply':reply} if state == 'DENIED' else None
            return self._save(handle,updated,origin,'SUBMIT_REJECTED',
                              check_action='recover',check_row=updated,denial=denial,fault=fault)
        updated = dict(row,state='ACCEPTED',task=asdict(task),
                       recovered_receipt_sha256=receipt_sha)
        return self._adopt_task(handle,updated,task,'ORIGINAL_TASK_ADOPTED',fault)

    def _receipt_task(self, handle, row, receipts):
        from .publication_wire import TaskID, _task
        if len(receipts) != 1:
            _fail()
        entry = receipts[0]
        receipt = json.loads(entry['receipt_json'])
        claim = self.db.execute('SELECT event_sha,event_json FROM events WHERE seq=?',
                                (entry['claim_seq'],)).fetchone()
        version = self.db.execute('SELECT row_json,row_sha FROM intent_versions WHERE handle=? AND event_seq=?',
                                  (handle,entry['claim_seq'])).fetchone()
        if version is None or digest(json.loads(version['row_json'])) != version['row_sha']:
            _fail()
        if (digest(receipt) != entry['receipt_sha'] or claim is None
                or digest(json.loads(claim['event_json'])) != claim['event_sha']
                or receipt.get('claim_sha') != claim['event_sha']
                or receipt.get('account') != self.index.account or receipt.get('binding') != self.index.binding
                or receipt.get('method') != 'freepublish.submit' or entry['method'] != 'freepublish.submit'
                or receipt.get('handle') != handle or receipt.get('claim_seq') != entry['claim_seq']
                or json.loads(claim['event_json']).get('kind') != 'SUBMIT_CLAIM'
                or json.loads(claim['event_json']).get('handle') != handle
                or json.loads(claim['event_json']).get('row_sha') != version['row_sha']):
            _fail()
        prior = json.loads(version['row_json'])
        if (prior.get('state') != 'SUBMIT_CLAIMED' or prior.get('submit_count') != 1
                or prior.get('reference') != row.get('reference')):
            _fail()
        expected = json.dumps({'media_id':row['reference']},sort_keys=True,
                              separators=(',',':'),ensure_ascii=True).encode('ascii')
        if receipt.get('request_sha') != sha256(expected).hexdigest():
            _fail()
        result = receipt.get('result')
        if (receipt.get('reason') != 'PARSED_SUCCESS' or receipt.get('error_code') is not None
                or receipt.get('http_status') != 200 or type(result) is not dict
                or type(result.get('task')) is not dict or result.get('observed_task') != result['task']):
            return entry['receipt_sha'], None
        try:
            task = TaskID(**result['task'])
            _task(task,'PUBLISH_TASK',self.index.account,handle)
        except Exception:
            _fail()
        if task.source_method != 'freepublish.submit' or task.response_sha != receipt.get('response_sha'):
            _fail()
        return entry['receipt_sha'], task

    def adopt_old_staged_submit(self, handle, *, fault=lambda phase: None):
        """Read the legacy staged proof through its original verifier, never send."""
        row = self._row(handle)
        self._guard('recover',row)
        if row.get('task') is not None:
            return row
        value = self.index.old._read_legacy()
        original = value['targets'].get(handle)
        if original is None or original != row:
            _fail()
        recovered = self.index.old._staged_submit(value,original,self.index.old.runtime_guard,check_conflict=True)
        if recovered['state'] == 'ORIGINAL_RECEIPT_NOT_FOUND':
            return recovered
        if recovered['state'] != 'ORIGINAL_TASK_STAGED_LOCAL_ONLY':
            _fail()
        task = recovered['task']
        updated = dict(row,state='ACCEPTED',task=asdict(task),reply=recovered['reply'],
                       recovered_receipt_sha256=recovered['receipt_sha256'])
        return self._adopt_task(handle,updated,task,'LEGACY_TASK_ADOPTED',fault)

    def _adopt_task(self, handle, updated, task, kind, fault):
        self._guard('recover',updated)
        try:
            clear = self.conflict_check('task',deepcopy(updated))
        except Exception:
            _fail()
        if clear is not True:
            _fail()
        task_fingerprint = digest([task.kind,task.digits])
        owners = [r[0] for r in self.db.execute(
            'SELECT handle FROM old_claims WHERE kind=? AND fingerprint=? UNION SELECT handle FROM target_claims WHERE kind=? AND fingerprint=?',
            ('TASK',task_fingerprint,'TASK',task_fingerprint))]
        if any(owner != handle for owner in owners):
            _fail()
        entry = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        origin = entry['origin'] if entry else 'OLD'
        return self._save(handle,updated,origin,kind,claims=[('TASK',task_fingerprint)],
                          check_action='recover',check_row=updated,fault=fault)

    def claim_query(self, handle, *, fault=lambda phase: None):
        row = self._row(handle)
        self._guard('query',row)
        if (row.get('state') not in {'ACCEPTED','PROCESSING','PUBLISHED_URLS_INCOMPLETE'}
                or type(row.get('task')) is not dict or row.get('query_pending',False)
                or type(row.get('queries')) is not int or row['queries'] < 0):
            _fail()
        seq = self.index._meta(self.db,self.identity)['seq'] + 1
        updated = dict(row,query_pending=True,queries=row['queries']+1,query_claim_seq=seq)
        entry = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        origin = entry['origin'] if entry else 'OLD'
        return self._save(handle,updated,origin,'QUERY_CLAIM',check_action='query',check_row=row,fault=fault)

    def mark_query_unknown(self, handle, *, fault=lambda phase: None):
        row = self._row(handle)
        self._guard('query_recover',row)
        if row.get('query_pending') is not True or type(row.get('query_claim_seq')) is not int:
            _fail()
        seq = row['query_claim_seq']
        if self.db.execute('SELECT 1 FROM return_receipts WHERE handle=? AND claim_seq=?',(handle,seq)).fetchone():
            _fail()
        updated = dict(row,query_pending=False,query_unknown_seq=seq,
            last_query={'reason':'QUERY_RESULT_UNDETERMINED','error_code':None,
                        'http_status':None,'response_sha256':None})
        entry = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        return self._save(handle,updated,entry['origin'],'QUERY_UNKNOWN',
                          check_action='query_recover',check_row=row,fault=fault)

    def query_ticket(self, handle, request, token):
        from .http_transport import HTTPRequest
        from .publication_wire import TaskID, _task, encode
        row = self._row(handle)
        self._guard('query',row)
        if row.get('query_pending') is not True or type(request) is not HTTPRequest:
            _fail()
        try:
            task = TaskID(**row['task'])
            _task(task,'PUBLISH_TASK',self.index.account,handle)
        except Exception:
            _fail()
        expected = encode('freepublish.get', {'task_id':task},token,
                          account_key=self.index.account,intent_id=handle)
        if request != expected:
            _fail()
        entry = self.db.execute('SELECT event_seq FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        claim = self.db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',
                                (row.get('query_claim_seq'),)).fetchone()
        if entry is None or entry['event_seq'] != row['query_claim_seq'] or claim is None:
            _fail()
        event = json.loads(claim['event_json'])
        if (digest(event) != claim['event_sha'] or event.get('kind') != 'QUERY_CLAIM'
                or event.get('handle') != handle or event.get('row_sha') != digest(row)):
            _fail()
        self._guard('query',row)
        return _QueryTicket(self,handle,row['query_claim_seq'],claim['event_sha'],request,token,
                            task,os.getpid(),threading.get_ident(),_TICKET_SEAL)

    def stage_query_reply(self, ticket, response, token, *, fault=lambda phase: None):
        from .publication_receipt import _project
        from .publication_wire import parse
        self._check_active()
        if (type(ticket) is not _QueryTicket or ticket.seal is not _TICKET_SEAL
                or ticket.session is not self or ticket.token is not token
                or ticket.pid != os.getpid() or ticket.thread != threading.get_ident()):
            _fail()
        row = self._row(ticket.handle)
        claim = self.db.execute('SELECT event_sha,event_json FROM events WHERE seq=?',(ticket.claim_seq,)).fetchone()
        if (row.get('query_pending') is not True or row.get('query_claim_seq') != ticket.claim_seq
                or claim is None or claim['event_sha'] != ticket.claim_sha
                or digest(json.loads(claim['event_json'])) != ticket.claim_sha
                or json.loads(claim['event_json']).get('row_sha') != digest(row)):
            _fail()
        reply = parse('freepublish.get',response,token,account_key=self.index.account,
            intent_id=ticket.handle,expected_task=ticket.task,article_count=row.get('article_count'))
        receipt = {'profile':'CONTINUATION_QUERY_RECEIPT_V1','method':'freepublish.get',
            'account':self.index.account,'binding':self.index.binding,'handle':ticket.handle,
            'claim_seq':ticket.claim_seq,'claim_sha':ticket.claim_sha,
            'request_sha':sha256(ticket.request.body).hexdigest(),
            'reason':reply.reason,'error_code':reply.error_code,'http_status':reply.http_status,
            'response_sha':reply.response_sha,'result':_project(reply.result)}
        existing = self.db.execute('SELECT receipt_json,receipt_sha FROM return_receipts '
            'WHERE handle=? AND claim_seq=?',(ticket.handle,ticket.claim_seq)).fetchone()
        if existing is not None:
            if existing['receipt_sha'] != digest(receipt) or json.loads(existing['receipt_json']) != receipt:
                _fail()
            return {'state':'ORIGINAL_REPLY_STAGED','receipt_sha256':digest(receipt)}
        origin = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(ticket.handle,)).fetchone()['origin']
        self._save(ticket.handle,row,origin,'QUERY_REPLY_STAGED',check_action='receipt',check_row=row,
                   receipt=receipt,post_return=True,fault=fault)
        return {'state':'ORIGINAL_REPLY_STAGED','receipt_sha256':digest(receipt)}

    def _query_receipt(self, handle, row, seq):
        from .publication_wire import TaskID, _task
        entry = self.db.execute('SELECT * FROM return_receipts WHERE handle=? AND claim_seq=? AND method=?',
                                (handle,seq,'freepublish.get')).fetchone()
        if entry is None:
            return None, None, None
        receipt = json.loads(entry['receipt_json'])
        claim = self.db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(seq,)).fetchone()
        version = self.db.execute('SELECT row_json,row_sha FROM intent_versions WHERE handle=? AND event_seq=?',
                                  (handle,seq)).fetchone()
        if claim is None or version is None:
            _fail()
        event, prior = json.loads(claim['event_json']),json.loads(version['row_json'])
        if (digest(receipt)!=entry['receipt_sha'] or digest(event)!=claim['event_sha']
                or digest(prior)!=version['row_sha'] or event.get('row_sha')!=version['row_sha']
                or event.get('kind')!='QUERY_CLAIM' or event.get('handle')!=handle
                or receipt.get('profile')!='CONTINUATION_QUERY_RECEIPT_V1'
                or receipt.get('claim_sha')!=claim['event_sha'] or receipt.get('claim_seq')!=seq
                or receipt.get('account')!=self.index.account or receipt.get('binding')!=self.index.binding
                or receipt.get('handle')!=handle or receipt.get('method')!='freepublish.get'
                or prior.get('task')!=row.get('task') or prior.get('query_pending') is not True):
            _fail()
        try:
            task = TaskID(**row['task']); _task(task,'PUBLISH_TASK',self.index.account,handle)
        except Exception:
            _fail()
        expected = json.dumps({'publish_id':task.digits},sort_keys=True,
                              separators=(',',':'),ensure_ascii=True).encode('ascii')
        if receipt.get('request_sha') != sha256(expected).hexdigest():
            _fail()
        return receipt, prior, entry['receipt_sha']

    def _query_outcome(self, handle, prior, receipt):
        from .publication_wire import article_url_supported
        updated = dict(prior,query_pending=False,last_query={
            'reason':receipt['reason'], 'error_code':receipt['error_code'],
            'http_status':receipt['http_status'], 'response_sha256':receipt['response_sha']})
        result = receipt.get('result')
        if result is not None:
            if (receipt.get('reason')!='PARSED_SUCCESS' or receipt.get('http_status')!=200
                    or type(result) is not dict or result.get('task')!=prior['task']
                    or type(result.get('platform_status')) is not int
                    or not 0 <= result['platform_status'] <= 6):
                _fail()
            status = result['platform_status']
            if prior['state']=='PUBLISHED_URLS_INCOMPLETE' and status != 0:
                _fail()
            urls = result.get('article_urls',[])
            if (type(urls) is not list or any(type(item) is not list or len(item)!=2
                    or type(item[0]) is not int or not article_url_supported(item[1]) for item in urls)):
                _fail()
            article = result.get('article_id')
            complete = result.get('url_evidence') == 'COMPLETE'
            if complete and (type(article) is not dict or article.get('account_key')!=self.index.account
                    or article.get('intent_id')!=handle or type(article.get('value')) is not str
                    or not article['value'] or len(urls)!=prior.get('article_count')
                    or [i[0] for i in urls]!=list(range(1,prior['article_count']+1))
                    or len({i[1] for i in urls})!=len(urls)):
                _fail()
            projection = {k:v for k,v in result.items() if k not in {'task','observed_task','article_id'}}
            if article is not None:
                if type(article) is not dict or article.get('account_key')!=self.index.account or article.get('intent_id')!=handle:
                    _fail()
                projection['article_id']=article['value']
            projection.update(reason=receipt['reason'],error_code=receipt['error_code'],
                              api_method='freepublish.get',request_sha256=receipt['request_sha'],
                              response_sha256=receipt['response_sha'],http_status=receipt['http_status'])
            updated.update(state=('PUBLISHED' if complete else 'PUBLISHED_URLS_INCOMPLETE') if status==0
                           else 'PROCESSING' if status==1 else 'PLATFORM_FAILED',reply=projection)
        return updated

    def apply_staged_query(self, handle, *, fault=lambda phase: None):
        row = self._row(handle)
        self._guard('query_recover',row)
        if row.get('query_pending') is not True:
            _fail()
        seq = row.get('query_claim_seq')
        receipt, prior, receipt_sha = self._query_receipt(handle,row,seq)
        if receipt is None:
            return {'state':'ORIGINAL_RECEIPT_NOT_FOUND'}
        if prior != row:
            _fail()
        updated = self._query_outcome(handle,prior,receipt)
        updated.update(applied_query_seq=seq,applied_query_receipt_sha=receipt_sha)
        entry = self.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
        return self._save(handle,updated,entry['origin'],'QUERY_APPLIED',
                          check_action='query_recover',check_row=row,fault=fault)


def guard_external_held(old_store, *, reference=None, claims=(), task=None):
    """Reverse conflict check; caller owns the existing stable account lock.

    This checks indexes only, does not establish authorization, and does not
    instantiate or activate a missing continuation. Partial presence is HOLD.
    """
    index = ContinuationIndex(old_store)
    paths = (index.enrollment_path,index.marker_path,index.db_path,index.head_path)
    present = [os.path.lexists(path) for path in paths]
    if not any(present):
        return
    if not all(present):
        _fail()
    wanted = list(claims)
    if reference is not None:
        if type(reference) is not str or not reference:
            _fail()
        wanted.append(('DRAFT_REF',digest(reference)))
    if task is not None:
        from .publication_wire import TaskID, _task
        if type(task) is not TaskID:
            _fail()
        try:
            _task(task,'PUBLISH_TASK',index.account,task.intent_id)
        except Exception:
            _fail()
        wanted.append(('TASK',digest([task.kind,task.digits])))
    if any(type(pair) not in (list,tuple) or len(pair)!=2
           or any(type(value) is not str or not value for value in pair) for pair in wanted):
        _fail()
    with index._db() as (db,identity):
        index._head(db,identity,recover=True)
        index._check_old_index(db,index._meta(db,identity))
        for kind,fingerprint in wanted:
            if (db.execute('SELECT 1 FROM target_claims WHERE kind=? AND fingerprint=? LIMIT 1',
                           (kind,fingerprint)).fetchone()
                    or (kind == 'TASK' and db.execute('SELECT 1 FROM old_claims WHERE kind=? AND fingerprint=? LIMIT 1',
                                                     (kind,fingerprint)).fetchone())):
                _fail()
        index._guard()
