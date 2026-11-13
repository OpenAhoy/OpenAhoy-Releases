"""Persistent public intent journal; default reads never migrate or connect."""
from .own_history_source import owned_connection
from contextlib import contextmanager, closing
import os
import re
from pathlib import Path
import sqlite3
import stat
import time

from .contracts import WCEError
from .bounded_file import file_state
from .service import canonical, digest
from .own_connection_policy import locked, atomic_write
from .own_bootstrap_security import path_check
from .publication_contract import (CONTRACT_SHA, POLICY, ROUTE_POLICY, binding,
    stable_account, strict_json, exact, fail)

SCHEMA = "CREATE TABLE publication_policy(\n account_key TEXT NOT NULL, policy_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),\n activation_epoch INTEGER NOT NULL CHECK(activation_epoch>=0),\n enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN(0,1)),\n retired INTEGER NOT NULL DEFAULT 0 CHECK(retired IN(0,1)),\n contract_sha TEXT NOT NULL CHECK(length(contract_sha)=64),\n identity_json TEXT NOT NULL, policy_json TEXT NOT NULL, policy_sha TEXT NOT NULL,\n trusted_source_sha TEXT NOT NULL, created_ms INTEGER NOT NULL, expires_ms INTEGER,\n PRIMARY KEY(account_key,policy_id), UNIQUE(account_key,revision));\nCREATE UNIQUE INDEX one_current_publication_policy ON publication_policy(account_key) WHERE retired=0;\nCREATE TABLE publication_channels(\n account_key TEXT NOT NULL, channel_id TEXT NOT NULL, policy_id TEXT NOT NULL,\n root_identity_json TEXT NOT NULL, manifest_schema TEXT NOT NULL,\n owner_epoch INTEGER NOT NULL CHECK(owner_epoch>=0),\n baseline_sha TEXT NOT NULL, activation_seq INTEGER NOT NULL CHECK(activation_seq>=0),\n state TEXT NOT NULL CHECK(state IN('REGISTERED','RELEASED','EDIT_HOLD')),\n PRIMARY KEY(account_key,channel_id),\n FOREIGN KEY(account_key,policy_id) REFERENCES publication_policy(account_key,policy_id));\nCREATE TABLE publication_baseline_members(\n account_key TEXT NOT NULL, channel_id TEXT NOT NULL, kind TEXT NOT NULL, fingerprint TEXT NOT NULL,\n PRIMARY KEY(account_key,channel_id,kind,fingerprint),\n FOREIGN KEY(account_key,channel_id) REFERENCES publication_channels(account_key,channel_id));\nCREATE TABLE publication_candidates(\n account_key TEXT NOT NULL, artifact_id TEXT NOT NULL, channel_id TEXT NOT NULL,\n policy_id TEXT NOT NULL, activation_epoch INTEGER NOT NULL, owner_epoch INTEGER NOT NULL,\n event_seq INTEGER NOT NULL CHECK(event_seq>0), input_sha TEXT NOT NULL,\n bundle_id TEXT NOT NULL, version TEXT NOT NULL REFERENCES own_articles(version),\n lineage_root TEXT NOT NULL, draft_step_id TEXT NOT NULL REFERENCES own_steps(id),\n draft_media_id TEXT NOT NULL, route_intent TEXT NOT NULL CHECK(route_intent IN('FREEPUBLISH','HUMAN_EXPLICIT_MASS')),\n human_intent_id TEXT, frozen_manifest_json TEXT NOT NULL, frozen_sha TEXT NOT NULL,\n registered_ms INTEGER NOT NULL, state TEXT NOT NULL,\n PRIMARY KEY(account_key,artifact_id), UNIQUE(account_key,event_seq),\n FOREIGN KEY(account_key,channel_id) REFERENCES publication_channels(account_key,channel_id),\n FOREIGN KEY(account_key,policy_id) REFERENCES publication_policy(account_key,policy_id),\n CHECK((route_intent='FREEPUBLISH' AND human_intent_id IS NULL) OR\n       (route_intent='HUMAN_EXPLICIT_MASS' AND human_intent_id IS NOT NULL)));\nCREATE TABLE publication_human_intents(\n account_key TEXT NOT NULL, human_intent_id TEXT NOT NULL, source_id TEXT NOT NULL,\n source_type TEXT NOT NULL CHECK(source_type IN('TRUSTED_UI','VERIFIED_HOST_HUMAN_EVENT')),\n source_sha TEXT NOT NULL, scope_json TEXT NOT NULL, scope_sha TEXT NOT NULL,\n expires_ms INTEGER NOT NULL, consumed_intent_id TEXT,\n PRIMARY KEY(account_key,human_intent_id), UNIQUE(account_key,source_type,source_id,scope_sha));\nCREATE TABLE publication_admission(\n account_key TEXT NOT NULL, route TEXT NOT NULL CHECK(route IN('FREEPUBLISH','MASS_ALL')),\n field TEXT NOT NULL, generation INTEGER NOT NULL, state TEXT NOT NULL,\n source_type TEXT NOT NULL, source_sha TEXT NOT NULL, value_json TEXT NOT NULL,\n observed_ms INTEGER NOT NULL, not_after_ms INTEGER NOT NULL,\n PRIMARY KEY(account_key,route,field,generation));\nCREATE TABLE publication_reviews(\n account_key TEXT NOT NULL, review_id TEXT NOT NULL, artifact_id TEXT NOT NULL,\n profile_sha TEXT NOT NULL, input_sha TEXT NOT NULL, current_draft_sha TEXT NOT NULL,\n owner_epoch INTEGER NOT NULL, runtime_receipt_sha TEXT NOT NULL,\n verdict TEXT NOT NULL CHECK(verdict IN('PASS','HOLD','FAIL','RUNTIME_UNAVAILABLE')),\n receipt_json TEXT NOT NULL, receipt_sha TEXT NOT NULL,\n created_ms INTEGER NOT NULL, expires_ms INTEGER NOT NULL,\n PRIMARY KEY(account_key,review_id),\n FOREIGN KEY(account_key,artifact_id) REFERENCES publication_candidates(account_key,artifact_id));\nCREATE TABLE publication_intents(\n account_key TEXT NOT NULL, intent_id TEXT NOT NULL, intent_key TEXT NOT NULL,\n artifact_id TEXT NOT NULL, policy_id TEXT NOT NULL, policy_revision INTEGER NOT NULL,\n route TEXT NOT NULL CHECK(route IN('FREEPUBLISH','MASS_ALL')),\n audience TEXT NOT NULL CHECK(audience IN('NO_PUSH','ALL_TARGETED_FOLLOWERS')),\n draft_media_id TEXT NOT NULL, lineage_root TEXT NOT NULL, payload_sha TEXT NOT NULL,\n review_id TEXT NOT NULL, snapshot_sha TEXT NOT NULL, state TEXT NOT NULL,\n submit_count INTEGER NOT NULL DEFAULT 0 CHECK(submit_count IN(0,1)),\n submit_claim_seq INTEGER, submit_ms INTEGER,\n task_kind TEXT CHECK(task_kind IN('PUBLISH_TASK','MASS_TASK')),\n task_digits TEXT, task_wire_type TEXT, task_raw_token TEXT,\n platform_status TEXT, effect TEXT, url_evidence TEXT,\n query_used INTEGER NOT NULL DEFAULT 0 CHECK(query_used>=0),\n query_seq INTEGER NOT NULL DEFAULT 0 CHECK(query_seq>=0),\n last_proof_sha TEXT,\n PRIMARY KEY(account_key,intent_id), UNIQUE(account_key,intent_key),\n UNIQUE(account_key,artifact_id), UNIQUE(account_key,draft_media_id),\n FOREIGN KEY(account_key,artifact_id) REFERENCES publication_candidates(account_key,artifact_id),\n FOREIGN KEY(account_key,policy_id) REFERENCES publication_policy(account_key,policy_id),\n FOREIGN KEY(account_key,review_id) REFERENCES publication_reviews(account_key,review_id),\n CHECK((route='FREEPUBLISH' AND audience='NO_PUSH') OR\n       (route='MASS_ALL' AND audience='ALL_TARGETED_FOLLOWERS')),\n CHECK((task_kind IS NULL AND task_digits IS NULL AND task_wire_type IS NULL AND task_raw_token IS NULL) OR\n       (task_kind IS NOT NULL AND task_digits IS NOT NULL AND task_wire_type IS NOT NULL AND task_raw_token IS NOT NULL)),\n CHECK(task_digits IS NULL OR (length(task_digits) BETWEEN 1 AND 128 AND\n       task_digits NOT GLOB '*[^0-9]*' AND substr(task_digits,1,1)<>'0')),\n CHECK(submit_count=0 OR submit_claim_seq IS NOT NULL));\nCREATE UNIQUE INDEX one_publication_task ON publication_intents(account_key,task_kind,task_digits)\n WHERE task_digits IS NOT NULL;\nCREATE TABLE publication_claims(\n account_key TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN('EVENT','ROOT','BODY','VISUAL','MEMBER_FULL')),\n fingerprint TEXT NOT NULL, intent_id TEXT NOT NULL,\n PRIMARY KEY(account_key,kind,fingerprint),\n FOREIGN KEY(account_key,intent_id) REFERENCES publication_intents(account_key,intent_id));\nCREATE TABLE publication_query_claims(\n account_key TEXT NOT NULL, intent_id TEXT NOT NULL, seq INTEGER NOT NULL,\n state TEXT NOT NULL CHECK(state IN('ACTIVE','DONE','UNKNOWN')),\n started_ms INTEGER NOT NULL, proof_sha TEXT,\n PRIMARY KEY(account_key,intent_id,seq),\n FOREIGN KEY(account_key,intent_id) REFERENCES publication_intents(account_key,intent_id));\nCREATE UNIQUE INDEX one_active_publication_get ON publication_query_claims(account_key,intent_id) WHERE state='ACTIVE';\nCREATE TABLE publication_reservations(\n account_key TEXT NOT NULL, intent_id TEXT NOT NULL, api_path TEXT NOT NULL, ordinal INTEGER NOT NULL,\n quota_observation_sha TEXT NOT NULL, bucket_id TEXT NOT NULL, state TEXT NOT NULL,\n PRIMARY KEY(account_key,intent_id,api_path,ordinal),\n FOREIGN KEY(account_key,intent_id) REFERENCES publication_intents(account_key,intent_id));\nCREATE TABLE publication_events(\n account_key TEXT NOT NULL, seq INTEGER NOT NULL CHECK(seq>0), event_type TEXT NOT NULL,\n intent_id TEXT, previous_sha TEXT NOT NULL, event_json TEXT NOT NULL, event_sha TEXT NOT NULL,\n PRIMARY KEY(account_key,seq));\nCREATE TABLE publication_articles(\n account_key TEXT NOT NULL, intent_id TEXT NOT NULL, article_index INTEGER NOT NULL CHECK(article_index BETWEEN 1 AND 8),\n article_id TEXT, official_url TEXT, url_proof_sha TEXT, state TEXT NOT NULL,\n PRIMARY KEY(account_key,intent_id,article_index),\n FOREIGN KEY(account_key,intent_id) REFERENCES publication_intents(account_key,intent_id));"

TRIGGERS = """
CREATE TRIGGER public_claims_no_delete BEFORE DELETE ON publication_claims BEGIN SELECT RAISE(ABORT,'PUBLICATION_SPENT_IMMUTABLE'); END;
CREATE TRIGGER public_claims_no_update BEFORE UPDATE ON publication_claims BEGIN SELECT RAISE(ABORT,'PUBLICATION_SPENT_IMMUTABLE'); END;
CREATE TRIGGER public_events_no_delete BEFORE DELETE ON publication_events BEGIN SELECT RAISE(ABORT,'PUBLICATION_HISTORY_IMMUTABLE'); END;
CREATE TRIGGER public_events_no_update BEFORE UPDATE ON publication_events BEGIN SELECT RAISE(ABORT,'PUBLICATION_HISTORY_IMMUTABLE'); END;
CREATE TRIGGER public_submit_no_reset BEFORE UPDATE OF submit_count ON publication_intents WHEN OLD.submit_count=1 AND NEW.submit_count<>1 BEGIN SELECT RAISE(ABORT,'PUBLICATION_SPENT_IMMUTABLE'); END;
CREATE TRIGGER public_intent_pins BEFORE UPDATE ON publication_intents WHEN OLD.submit_count=1 AND
 (NEW.account_key<>OLD.account_key OR NEW.intent_id<>OLD.intent_id OR NEW.intent_key<>OLD.intent_key OR
 NEW.artifact_id<>OLD.artifact_id OR NEW.policy_id<>OLD.policy_id OR NEW.policy_revision<>OLD.policy_revision OR
 NEW.route<>OLD.route OR NEW.audience<>OLD.audience OR NEW.draft_media_id<>OLD.draft_media_id OR
 NEW.lineage_root<>OLD.lineage_root OR NEW.payload_sha<>OLD.payload_sha)
 BEGIN SELECT RAISE(ABORT,'PUBLICATION_INTENT_IMMUTABLE'); END;
CREATE TRIGGER public_intent_no_delete BEFORE DELETE ON publication_intents WHEN OLD.submit_count=1
 BEGIN SELECT RAISE(ABORT,'PUBLICATION_SPENT_IMMUTABLE'); END;
CREATE TRIGGER public_human_no_delete BEFORE DELETE ON publication_human_intents WHEN OLD.consumed_intent_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'PUBLICATION_HUMAN_INTENT_SPENT'); END;
CREATE TRIGGER public_human_pins BEFORE UPDATE ON publication_human_intents WHEN OLD.consumed_intent_id IS NOT NULL AND
 (NEW.account_key<>OLD.account_key OR NEW.human_intent_id<>OLD.human_intent_id OR NEW.source_id<>OLD.source_id OR
 NEW.source_type<>OLD.source_type OR NEW.source_sha<>OLD.source_sha OR NEW.scope_json<>OLD.scope_json OR
 NEW.scope_sha<>OLD.scope_sha OR NEW.expires_ms<>OLD.expires_ms)
 BEGIN SELECT RAISE(ABORT,'PUBLICATION_HUMAN_INTENT_SPENT'); END;
CREATE TRIGGER public_human_no_reset BEFORE UPDATE ON publication_human_intents WHEN OLD.consumed_intent_id IS NOT NULL AND
 (NEW.consumed_intent_id IS NULL OR NEW.consumed_intent_id<>OLD.consumed_intent_id)
 BEGIN SELECT RAISE(ABORT,'PUBLICATION_HUMAN_INTENT_SPENT'); END;
"""
from .publication_quota import SCHEMA as QUOTA_SCHEMA
ALL_SCHEMA = SCHEMA + TRIGGERS + QUOTA_SCHEMA
ZERO = '0' * 64
_UNSET = object()


def sync_directory(path):
    """Make a newly created child directory durable in its own parent too."""
    pin = path_check(path, True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != pin:
            fail('PUBLICATION_INPUT_CHANGED')
        os.fsync(fd)
        if path_check(path, True) != pin:
            fail('PUBLICATION_INPUT_CHANGED')
    finally:
        os.close(fd)


def read_file(path, maximum=512 * 1024):
    path = Path(path)
    parent_pin = path_check(path.parent, True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 0 < before.st_size <= maximum):
            fail()
        raw = b''
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk: break
            raw += chunk
        after = os.fstat(fd)
        if (len(raw) != before.st_size or file_state(before) != file_state(after)
                or file_state(path.lstat()) != file_state(after)
                or path_check(path.parent, True) != parent_pin):
            fail('PUBLICATION_INPUT_CHANGED')
        return strict_json(raw, maximum)
    finally:
        os.close(fd)


class PublicationStore:
    def __init__(self, policy, registry, wall=time.time, fault=lambda phase: None):
        self.policy, self.wall, self.fault = policy, wall, fault
        self.key, self.binding_sha = stable_account(policy.data), binding(policy.data)
        self.path = policy.root / 'state.sqlite3'
        self.anchor_root = Path(registry).parent / 'publication-anchors'
        self.anchor = self.anchor_root / self.key
        self.head_path = self.anchor / 'head.json'
        self._registered_drafts = None

    def bind_registered_drafts(self, authority):
        from .saved_groups_publication_source import is_registered_saved_groups
        if (not is_registered_saved_groups(authority) or authority.policy is not self.policy
                or authority.policy_binding != self.binding_sha
                or authority.registry.parent / 'publication-anchors' != self.anchor_root):
            fail('CURRENT_PUBLICATION_HUMAN_SCOPE_REQUIRED')
        self._registered_drafts = authority

    @contextmanager
    def connection(self, write=False):
        path_check(self.policy.root, True)
        path_check(self.path)
        mode = 'rw' if write else 'ro'
        with owned_connection(self.path, readonly=not write, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            if write: db.execute('PRAGMA synchronous=FULL')
            try:
                if write: db.execute('BEGIN IMMEDIATE')
                from .draft_group_history_context import history_policy_context
                with history_policy_context(self.path, db, self.policy):
                    yield db
                if write:
                    self.fault('before_db_commit')
                    db.commit()
                    self.fault('after_db_commit')
            except BaseException:
                if write: db.rollback()
                raise

    def exists(self, db, *, history_locators=None):
        # Validate 5 / formal-6 / composite-7 rather than treating any unknown
        # version or old experimental-6 database as an OFF publication state.
        from .publication_schema import classify_read_only
        row=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
        if row is None: fail('PUBLICATION_RECOVERY_HOLD')
        if self._registered_drafts is not None:
            from .draft_group_history_context import require_history
            from .own_store import OwnStore
            require_history(self.policy, db, history_locators)
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (5, 6, 7, 8, 9):
                fail('PUBLICATION_RECOVERY_HOLD')
            OwnStore._check_layout(db, row[0], version)
            return version >= 7
        return classify_read_only(db, row[0], self.policy, history_locators=history_locators) in (7, 8, 9)


    def _head(self, allow_pending=False):
        value = read_file(self.head_path, 16384)
        exact(value, 'schema account_key binding_sha contract_sha activation_epoch seq event_sha confirmed_seq')
        if (type(value['schema']) is not int or value['schema'] != 1 or value['account_key'] != self.key
                or value['contract_sha'] != CONTRACT_SHA
                or type(value['seq']) is not int or value['seq'] < 0
                or type(value['confirmed_seq']) is not int
                or value['confirmed_seq'] not in ({value['seq'], value['seq'] - 1} if allow_pending and value['seq'] else {value['seq']})
                or type(value['activation_epoch']) is not int or value['activation_epoch'] < 0
                or type(value['event_sha']) is not str or re.fullmatch('[a-f0-9]{64}', value['event_sha']) is None):
            fail('PUBLICATION_RECOVERY_HOLD')
        if value['binding_sha'] != self.binding_sha:
            fail('PUBLICATION_REASSIGNMENT_HOLD')
        return value

    def _verify(self, db, allow_pending=False, *, history_locators=None):
        from .publication_lock import verify_pin
        verify_pin(self, required=self.exists(db, history_locators=history_locators))
        return self._verify_records_in(db, allow_pending=allow_pending)

    def _verify_records_in(self, db, allow_pending=False):
        # Exact record/anchor leaf; caller already verified complete layout and
        # fixed pin. Kept separate to avoid OwnStore ancestor recursion.
        head = self._head(allow_pending=allow_pending)
        from .publication_quota import TABLES, replay_event, verify_replay, QuotaHold
        quota_replay = {table: [] for table in TABLES}
        previous, seq = ZERO, 0
        for row in db.execute('SELECT * FROM publication_events WHERE account_key=? ORDER BY seq', (self.key,)):
            event = strict_json(row['event_json'].encode())
            exact(event, 'schema account_key seq previous_sha event_type binding_sha data created_ms')
            if (type(event['schema']) is not int or event['schema'] != 1
                    or type(event['seq']) is not int or type(event['created_ms']) is not int
                    or type(event['data']) is not dict or type(event['event_type']) is not str):
                fail('PUBLICATION_RECOVERY_HOLD')
            seq += 1
            if (row['seq'] != seq or row['previous_sha'] != previous
                    or digest(event) != row['event_sha'] or event['seq'] != seq
                    or event['previous_sha'] != previous or event['account_key'] != self.key
                    or event.get('binding_sha') != self.binding_sha
                    or row['event_type'] != event.get('event_type')
                    or row['intent_id'] != event.get('data', {}).get('intent_id')):
                fail('PUBLICATION_RECOVERY_HOLD')
            file_event = read_file(self.anchor / (str(seq).zfill(16) + '.json'))
            if file_event != event:
                fail('PUBLICATION_RECOVERY_HOLD')
            try: replay_event(event['data'], quota_replay)
            except QuotaHold: fail('PUBLICATION_RECOVERY_HOLD')
            if event['event_type'] == 'SUBMIT_CLAIM':
                data = event['data']
                claims = data.get('claims')
                intent = db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',
                                    (self.key, data.get('intent_id'))).fetchone()
                if (intent is None or intent['submit_count'] != 1 or intent['submit_claim_seq'] != seq
                        or intent['payload_sha'] != data.get('payload_sha')
                        or data.get('binding_sha') != self.binding_sha
                        or type(claims) is not list or not claims):
                    fail('PUBLICATION_RECOVERY_HOLD')
                seen = set()
                for pair in claims:
                    if (type(pair) not in (list, tuple) or len(pair) != 2
                            or type(pair[0]) is not str or type(pair[1]) is not str
                            or tuple(pair) in seen):
                        fail('PUBLICATION_RECOVERY_HOLD')
                    seen.add(tuple(pair))
                    claimed = db.execute('SELECT intent_id FROM publication_claims WHERE account_key=? AND kind=? AND fingerprint=?',
                                         (self.key, pair[0], pair[1])).fetchone()
                    if claimed is None or claimed['intent_id'] != data['intent_id']:
                        fail('PUBLICATION_RECOVERY_HOLD')
            previous = row['event_sha']
        try: verify_replay(db, self.key, quota_replay)
        except QuotaHold: fail('PUBLICATION_RECOVERY_HOLD')
        if head['seq'] != seq or head['event_sha'] != previous:
            fail('PUBLICATION_RECOVERY_HOLD')
        # An orphan append before a failed head write is also a high-water
        # uncertainty. A matching old head alone must not authorize new HTTP.
        actual = {p.name for p in self.anchor.iterdir()
                  if re.fullmatch('[0-9]{16}\\.json', p.name)}
        expected = {str(i).zfill(16) + '.json' for i in range(1, seq + 1)}
        if actual != expected:
            fail('PUBLICATION_RECOVERY_HOLD')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            fail()
        return head

    def state(self):
        # Pure local reads: no create/migration, token, transport or broker start.
        with self.connection() as db, _history_scope(self.policy,db) as history_locators:
            if not self.exists(db, history_locators=history_locators):
                if os.path.lexists(self.head_path):
                    fail('PUBLICATION_RECOVERY_HOLD')
                return {'enabled': False, 'state': 'OFF', 'admission': 'UNKNOWN',
                        'contract_sha256': CONTRACT_SHA, 'route_policy': ROUTE_POLICY}
            self._verify(db, history_locators=history_locators)
            row = db.execute('SELECT * FROM publication_policy WHERE account_key=? AND retired=0', (self.key,)).fetchone()
            if row is None:
                return {'enabled': False, 'state': 'OFF', 'admission': 'UNKNOWN',
                        'contract_sha256': CONTRACT_SHA, 'route_policy': ROUTE_POLICY}
            value = strict_json(row['policy_json'].encode())
            if digest(value) != row['policy_sha'] or value.get('binding_sha') != self.binding_sha:
                fail()
            enabled = bool(row['enabled'])
            return {'enabled': enabled, 'state': 'ON' if enabled else 'OFF',
                    'admission': 'CHECK_BEFORE_EACH_SUBMIT', 'contract_sha256': CONTRACT_SHA,
                    'route_policy': ROUTE_POLICY, 'revision': row['revision']}

    def _make_anchor(self):
        # Called only by the trusted setup/enable path, never a status request.
        base = self.anchor_root.parent
        path_check(base, True)
        for path in (self.anchor_root, self.anchor):
            try: path.mkdir(mode=0o700)
            except FileExistsError: pass
            path_check(path, True)
            sync_directory(path.parent)
        if not os.path.lexists(self.head_path):
            atomic_write(self.head_path, {'schema': 1, 'account_key': self.key,
                'binding_sha': self.binding_sha, 'contract_sha': CONTRACT_SHA,
                'activation_epoch': 0, 'seq': 0, 'event_sha': ZERO, 'confirmed_seq': 0})

    def migrate(self, trusted_guard):
        trusted_guard()
        self.policy.check()
        self._make_anchor()
        with self.connection(write=True) as db, _history_scope(self.policy,db) as history_locators:
            from .publication_schema import classify_read_only, migrate_to_7
            row=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
            if row is None: fail('PUBLICATION_RECOVERY_HOLD')
            source=row[0]
            version=classify_read_only(db, source, self.policy, history_locators=history_locators)
            if version in (7, 8, 9):
                self._verify(db, history_locators=history_locators)
                return
            if self._head()['seq'] != 0:
                fail('PUBLICATION_RECOVERY_HOLD')
            migrate_to_7(db, source, trusted_guard, history_policy=self.policy, fault=self.fault, history_locators=history_locators)
            trusted_guard()
            self.fault('before_migration_commit')


    @contextmanager
    def dispatch_lock(self):
        # Keep each historical qualification in its own real read snapshot.
        # The pre-lock snapshot closes before locking; the post-lock snapshot
        # is independent and cannot reuse content across either boundary.
        from .publication_lock import verify_pin
        from .draft_group_history_context import readonly_history_snapshot
        with readonly_history_snapshot(self.policy, self.path, timeout=10) as (db, history_locators):
            verify_pin(self, required=self.exists(db, history_locators=history_locators))
        with locked(self.anchor / 'publication.lock', nonblocking=True):
            with locked(self.policy.root / 'publication-dispatch.lock', nonblocking=True):
                # Disconnect/revoke commits under this same policy lock. If it
                # wins, the next guard rejects; an already admitted request owns
                # the lock until its bounded send finishes and cannot be undone.
                with locked(self.policy.root / 'connection-policy.lock', nonblocking=True):
                    with readonly_history_snapshot(self.policy, self.path, timeout=10) as (db, history_locators):
                        verify_pin(self, required=self.exists(db, history_locators=history_locators))
                    yield

    def event(self, db, event_type, data, apply, before_anchor=lambda db: None, *, history_locators=None):
        """Validate SQL once, then anchor before durable DB commit.

        apply is trusted SQL-only code: no files/network/token/outside effects.
        Its writes remain uncommitted in this same BEGIN IMMEDIATE transaction.
        A known SQL constraint/guard failure therefore publishes no anchor.
        """
        head = self._verify(db, history_locators=history_locators)
        event = {'schema': 1, 'account_key': self.key, 'seq': head['seq'] + 1,
                 'previous_sha': head['event_sha'], 'event_type': event_type,
                 'binding_sha': self.binding_sha, 'data': data,
                 'created_ms': int(self.wall() * 1000)}
        name = self.anchor / (str(event['seq']).zfill(16) + '.json')
        if os.path.lexists(name): fail('PUBLICATION_RECOVERY_HOLD')
        epoch = head['activation_epoch']
        if event_type == 'ENABLE':
            epoch = data.get('activation_epoch')
            if type(epoch) is not int or epoch <= head['activation_epoch']:
                fail('PUBLICATION_RECOVERY_HOLD')
        from .publication_quota import snapshot as quota_snapshot, append_event_data
        quota_before = quota_snapshot(db, self.key)
        apply(event['seq'])
        append_event_data(db, self.key, data, quota_before)
        db.execute('INSERT INTO publication_events VALUES(?,?,?,?,?,?,?)',
            (self.key, event['seq'], event_type, data.get('intent_id'),
             event['previous_sha'], canonical(event), digest(event)))
        self.fault('sql_before_anchor')
        before_anchor(db)
        atomic_write(name, event, maximum=512 * 1024)
        pending = dict(head, seq=event['seq'], event_sha=digest(event), confirmed_seq=head['seq'])
        pending['activation_epoch'] = epoch
        atomic_write(self.head_path, pending)
        self.fault('anchor_before_db')
        return pending

    def confirm(self, pending):
        # Caller has committed the matching DB transaction while holding the lock.
        self.fault('db_before_anchor_confirm')
        with self.connection() as db, _history_scope(self.policy,db) as history_locators:
            if self._verify(db, allow_pending=True, history_locators=history_locators) != pending:
                fail('PUBLICATION_RECOVERY_HOLD')
        atomic_write(self.head_path, dict(pending, confirmed_seq=pending['seq']))
        with self.connection() as db, _history_scope(self.policy,db) as history_locators: self._verify(db, history_locators=history_locators)

    def recover_committed_head(self):
        """Caller holds dispatch_lock. Local confirmation only; never replay SQL.

        The complete DB chain, external event files and pending head must match.
        An ahead anchor, missing event or restored old DB remains HOLD.
        """
        with self.connection() as db, _history_scope(self.policy,db) as history_locators:
            if not self.exists(db, history_locators=history_locators): fail('PUBLICATION_RECOVERY_HOLD')
            head = self._verify(db, allow_pending=True, history_locators=history_locators)
        if head['confirmed_seq'] == head['seq']:
            return {'state': 'HEAD_ALREADY_CONFIRMED'}
        atomic_write(self.head_path, dict(head, confirmed_seq=head['seq']))
        with self.connection() as db, _history_scope(self.policy,db) as history_locators: self._verify(db, history_locators=history_locators)
        return {'state': 'HEAD_CONFIRMED_LOCAL_ONLY'}

    def current(self, db, *, history_locators=None):
        self._verify(db, history_locators=history_locators)
        row = db.execute('SELECT * FROM publication_policy WHERE account_key=? AND retired=0', (self.key,)).fetchone()
        if row is None or not row['enabled']:
            fail('PUBLICATION_OFF')
        value = strict_json(row['policy_json'].encode())
        if (row['contract_sha'] != CONTRACT_SHA or digest(value) != row['policy_sha']
                or value['binding_sha'] != self.binding_sha
                or (row['expires_ms'] is not None and self.wall() * 1000 >= row['expires_ms'])):
            fail('PUBLICATION_AUTHORITY_INVALID')
        self.policy.check()
        return dict(row), value

    def admission(self, db, route='FREEPUBLISH', *, history_locators=None):
        self.current(db, history_locators=history_locators)
        needed = {'permission', 'platform_condition'}
        rows = db.execute('SELECT * FROM publication_admission WHERE account_key=? AND route=? '
            'ORDER BY generation DESC', (self.key, route)).fetchall()
        latest = {}
        for r in rows: latest.setdefault(r['field'], r)
        for field in needed:
            r = latest.get(field)
            if (r is None or r['state'] != 'VERIFIED_AVAILABLE'
                    or not r['observed_ms'] <= self.wall() * 1000 < r['not_after_ms']
                    or r['source_type'] not in {'TRUSTED_HUMAN_SETTINGS', 'OFFICIAL_READ'}):
                fail('PUBLICATION_ADMISSION_UNKNOWN')
        return latest

    def local_intent(self, intent_id):
        with self.connection() as db, _history_scope(self.policy,db) as history_locators:
            if not self.exists(db, history_locators=history_locators): return {'state': 'OFF', 'enabled': False}
            self._verify(db, history_locators=history_locators)
            row = db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',
                             (self.key, intent_id)).fetchone()
            if row is None: fail('PUBLICATION_INTENT_NOT_FOUND')
            value = {k: row[k] for k in ('intent_id', 'route', 'audience', 'state',
                        'submit_count', 'platform_status', 'effect', 'url_evidence', 'query_used')}
            value['articles'] = self._article_urls(db, row)
            return value

    def _article_urls(self, db, row):
        # A mutable projection table is not independent publication evidence.
        # Expose only URLs in the exact anchored official terminal response.
        if row['state'] != 'PUBLISHED':
            return []
        event_row = db.execute("SELECT event_json FROM publication_events WHERE account_key=? AND intent_id=? AND event_type='QUERY_RESULT' ORDER BY seq DESC LIMIT 1",
                               (self.key, row['intent_id'])).fetchone()
        if event_row is None:
            fail('PUBLICATION_URL_PROOF_REQUIRED')
        event = strict_json(event_row['event_json'].encode())
        data = event['data']
        name = data.get('proof_name')
        if type(name) is not str or re.fullmatch(r'proof-[a-f0-9]{32}\.json', name) is None:
            fail('PUBLICATION_URL_PROOF_REQUIRED')
        proof = read_file(self.anchor / 'proofs' / name)
        pins = ('policy_id', 'policy_revision', 'artifact_id', 'review_id', 'snapshot_sha',
                'route', 'audience', 'draft_media_id', 'lineage_root', 'payload_sha', 'submit_claim_seq')
        source = db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
        origin = 'OWN_OFFICIAL_WIRE' if source == 'OPERATOR_ATTESTED' else 'SYNTHETIC_PUBLICATION'
        if (digest(proof) != data.get('proof_sha') or digest(proof) != row['last_proof_sha']
                or proof.get('schema') != 'PUBLICATION_PROOF_V1' or proof.get('origin') != origin
                or proof.get('account_key') != self.key or proof.get('binding_sha') != self.binding_sha
                or proof.get('contract_sha') != CONTRACT_SHA or proof.get('intent_id') != row['intent_id']
                or proof.get('query_seq') != row['query_seq']
                or proof.get('pins') != {key: row[key] for key in pins}):
            fail('PUBLICATION_URL_PROOF_REQUIRED')
        result = proof.get('result')
        if (type(result) is not dict or type(result.get('platform_status')) is not int
                or result['platform_status'] != 0 or type(result.get('article_urls')) is not list
                or result.get('url_evidence') != row['url_evidence']):
            fail('PUBLICATION_URL_PROOF_REQUIRED')
        from .publication_wire import article_url_supported
        urls, seen = [], set()
        for pair in result['article_urls']:
            if (type(pair) is not list or len(pair) != 2 or type(pair[0]) is not int
                    or not 1 <= pair[0] <= 8 or pair[0] in seen
                    or type(pair[1]) is not str or not article_url_supported(pair[1])):
                fail('PUBLICATION_URL_PROOF_REQUIRED')
            seen.add(pair[0])
            urls.append({'article_index': pair[0], 'url': pair[1],
                         'evidence_origin': origin, 'proof_sha256': data['proof_sha']})
        return urls

    def operation_result(self, operation_id):
        _operation_id(operation_id)
        with self.connection() as db, _history_scope(self.policy,db) as history_locators:
            if self.exists(db, history_locators=history_locators):
                self._verify(db, history_locators=history_locators)
                for row in db.execute("SELECT event_json FROM publication_events WHERE account_key=? AND event_type='DISABLE' ORDER BY seq DESC", (self.key,)):
                    event = strict_json(row['event_json'].encode())
                    if event['data'].get('operation_id') == operation_id:
                        return {'operation_id': operation_id, 'state': 'COMMITTED', 'operation': 'DISABLE'}
        return {'operation_id': operation_id, 'state': 'NOT_FOUND_NOT_RETRYABLE', 'operation': 'DISABLE'}

    def _setting_policy(self, db, *, history_locators=None):
        if not self.exists(db, history_locators=history_locators):
            return None
        self._verify(db, history_locators=history_locators)
        row = db.execute('SELECT * FROM publication_policy WHERE account_key=? AND retired=0', (self.key,)).fetchone()
        if row is None:
            return None
        return {key: (bool(row[key]) if key == 'enabled' else row[key])
                for key in ('policy_id', 'revision', 'policy_sha', 'contract_sha', 'enabled')}

    def setting_policy(self):
        with self.connection() as db, _history_scope(self.policy,db) as history_locators:
            return self._setting_policy(db, history_locators=history_locators)


def validate_schema(db):
    """The enclosing OwnStore checks exact object names and table structure."""
    if db.execute('PRAGMA foreign_key_check').fetchone(): fail()
    for row in db.execute('SELECT * FROM publication_policy'):
        value = strict_json(row['policy_json'].encode())
        if digest(value) != row['policy_sha'] or row['contract_sha'] != CONTRACT_SHA:
            fail()
    for row in db.execute('SELECT * FROM publication_reviews'):
        value = strict_json(row['receipt_json'].encode())
        if digest(value) != row['receipt_sha']:
            fail()
    for row in db.execute('SELECT * FROM publication_intents'):
        if row['submit_count'] == 1 and row['state'] in {'PREPARED', 'HOLD', 'CANCELLED_BEFORE_SUBMIT'}:
            fail()


def insert(db, table, values):
    allowed = {'publication_policy','publication_channels','publication_baseline_members',
        'publication_candidates','publication_human_intents','publication_admission',
        'publication_reviews','publication_intents','publication_claims',
        'publication_query_claims','publication_reservations','publication_articles'}
    if table not in allowed or not values:
        fail()
    columns = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
    if not set(values) <= columns:
        fail()
    keys = list(values)
    db.execute('INSERT INTO ' + table + '(' + ','.join(keys) + ') VALUES('
        + ','.join('?' for _ in keys) + ')', tuple(values[k] for k in keys))


def commit_event(store, event_type, data, apply, *, before_anchor=lambda db: None,
                 before_commit=lambda db: None):
    """Caller holds dispatch_lock; an uncertain commit never becomes a retry."""
    with store.connection(write=True) as db, _history_scope(store.policy,db) as history_locators:
        pending = store.event(db, event_type, data, lambda seq: apply(db, seq), before_anchor,history_locators=history_locators)
        # Must inspect the same transaction view, never a fresh read connection
        # whose old DB head would correctly disagree with the pending anchor.
        before_commit(db)
    store.confirm(pending)

def commit_event_with_history(store, event_type, data, apply, *, before_anchor=lambda db: None,
                 before_commit=lambda db: None):
    """Caller holds dispatch_lock; an uncertain commit never becomes a retry."""
    with store.connection(write=True) as db, _history_scope(store.policy,db) as history_locators:
        pending = store.event(db, event_type, data, lambda seq: apply(db, seq, history_locators=history_locators), before_anchor,history_locators=history_locators)
        # Must inspect the same transaction view, never a fresh read connection
        # whose old DB head would correctly disagree with the pending anchor.
        before_commit(db)
    store.confirm(pending)


def enable(store, reviewed, root_baseline, guard):
    """Trusted settings backend only. No MCP route reaches this function."""
    from uuid import uuid4
    from .publication_contract import CONTRACT_SHA
    exact(reviewed, 'human_source_sha producer_root summary_mode originality permission_observed_ms permission_not_after_ms permission_source_sha runtime_receipt_sha runtime_expires_ms')
    now = int(store.wall() * 1000)
    if (reviewed['summary_mode'] not in {'PLATFORM_AUTO_ACCEPTED', 'CUSTOM_REQUIRED', 'EMPTY_REQUIRED'}
            or reviewed['originality'] not in {'not_requested','required'}
            or type(reviewed['permission_observed_ms']) is not int
            or type(reviewed['permission_not_after_ms']) is not int
            or type(reviewed['runtime_expires_ms']) is not int
            or not reviewed['permission_observed_ms'] <= now < reviewed['permission_not_after_ms']
            or now >= reviewed['runtime_expires_ms']
            or any(type(reviewed[key]) is not str or re.fullmatch('[a-f0-9]{64}', reviewed[key]) is None
                   for key in ('human_source_sha', 'permission_source_sha', 'runtime_receipt_sha'))):
        fail('PUBLICATION_ENABLE_REQUIREMENTS_MISSING')
    caller_guard = guard
    def guard():
        caller_guard()
        observed_now = int(store.wall() * 1000)
        if (not reviewed['permission_observed_ms'] <= observed_now < reviewed['permission_not_after_ms']
                or observed_now >= reviewed['runtime_expires_ms']):
            fail('PUBLICATION_ENABLE_EVIDENCE_EXPIRED')
    guard(); store.policy.check()
    # Creation of the stable account anchor is serialized with enrollment.
    with locked(Path(store.anchor_root).parent / 'connection-setup.lock', nonblocking=True):
      store._make_anchor()
      with store.dispatch_lock():
        from .publication_producer import baseline, BASELINE_PROFILE
        if (type(root_baseline) is not dict or root_baseline.get('schema') != BASELINE_PROFILE
                or root_baseline.get('account_key') != store.key
                or root_baseline.get('root_identity', {}).get('path') != reviewed['producer_root']):
            fail('PUBLICATION_BASELINE_INCOMPLETE')
        with store.connection() as db:
            db.execute('BEGIN')
            measured = baseline(reviewed['producer_root'], db=db,
                account=store.policy.data['resource_id'], expected_root=root_baseline['root_identity'])
            if digest(measured) != digest(root_baseline):
                fail('PUBLICATION_BASELINE_CHANGED')
            db.rollback()
        from .publication_lock import install_pin
        install_pin(store)
        store.migrate(guard)
        with store.connection() as db:
            head = store._verify(db)
            revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM publication_policy WHERE account_key=?', (store.key,)).fetchone()[0]
            activation = db.execute('SELECT COALESCE(MAX(event_seq),0) FROM publication_candidates WHERE account_key=?', (store.key,)).fetchone()[0]
        policy_id, channel_id = 'pub-policy-' + uuid4().hex, 'pub-channel-' + uuid4().hex
        epoch = head['activation_epoch'] + 1
        value = {'schema': 1, 'policy': POLICY, 'route_policy': ROUTE_POLICY,
            'account_key': store.key, 'binding_sha': store.binding_sha,
            'contract_sha': CONTRACT_SHA, 'summary_mode': reviewed['summary_mode'],
            'originality': reviewed['originality'], 'snapshot': 'BOUNDED_DRAFT_SNAPSHOT_V1',
            'channel_id': channel_id, 'human_source_sha': reviewed['human_source_sha'],
            'runtime_receipt_sha': reviewed['runtime_receipt_sha'], 'activation_epoch': epoch,
            'runtime_expires_ms': reviewed['runtime_expires_ms'],
            'baseline_profile': BASELINE_PROFILE, 'baseline_history': measured['history'],
            'baseline_tree_sha': measured['tree_sha'],
            'baseline_claims_sha': digest(measured['claims']),
            'baseline_claims_count': len(measured['claims'])}
        def apply(db, seq):
            guard()
            final = baseline(reviewed['producer_root'], db=db,
                account=store.policy.data['resource_id'], expected_root=measured['root_identity'])
            if digest(final) != digest(measured):
                fail('PUBLICATION_BASELINE_CHANGED')
            db.execute('UPDATE publication_policy SET enabled=0,retired=1 WHERE account_key=? AND retired=0', (store.key,))
            insert(db, 'publication_policy', {'account_key': store.key, 'policy_id': policy_id,
                'revision': revision, 'activation_epoch': epoch, 'enabled': 1, 'retired': 0,
                'contract_sha': CONTRACT_SHA, 'identity_json': canonical(store.policy.data),
                'policy_json': canonical(value), 'policy_sha': digest(value),
                'trusted_source_sha': reviewed['human_source_sha'], 'created_ms': int(store.wall()*1000)})
            insert(db,'publication_channels',{'account_key':store.key,'channel_id':channel_id,
                'policy_id':policy_id,'root_identity_json':canonical(root_baseline['root_identity']),
                'manifest_schema':'WCE_LOCAL_PUBLISH_CANDIDATE_V1','owner_epoch':1,
                'baseline_sha':digest(root_baseline),'activation_seq':activation,'state':'REGISTERED'})
            for kind, fingerprint in root_baseline['claims']:
                insert(db,'publication_baseline_members',{'account_key':store.key,'channel_id':channel_id,
                    'kind':kind,'fingerprint':fingerprint})
            for field in ('permission','platform_condition'):
                insert(db,'publication_admission',{'account_key':store.key,'route':'FREEPUBLISH',
                    'field':field,'generation':revision,'state':'VERIFIED_AVAILABLE',
                    'source_type':'TRUSTED_HUMAN_SETTINGS','source_sha':reviewed['permission_source_sha'],
                    'value_json':canonical({'human_attested':True,'not_platform_read':True}),
                    'observed_ms':reviewed['permission_observed_ms'],
                    'not_after_ms':reviewed['permission_not_after_ms']})
        commit_event(store,'ENABLE',{'policy_id':policy_id,'activation_epoch':epoch,
            'source_sha':reviewed['human_source_sha'],'baseline_sha':digest(root_baseline)},apply,
            before_anchor=lambda db: guard(), before_commit=lambda db: guard())
        # Epoch is also anchored independently of the restorable account DB.
        current = store._head()
        atomic_write(store.head_path,dict(current,activation_epoch=epoch))
        return store.state()


def _operation_id(value):
    if type(value) is not str or re.fullmatch(r'pub-setting-[a-f0-9]{32}', value) is None:
        fail('PUBLICATION_SETTING_OPERATION_INVALID')


def disable(store, guard=lambda: None, *, operation_id=None, expected_policy=_UNSET):
    if operation_id is not None:
        _operation_id(operation_id)
    guard()
    from .publication_lock import draft_writer
    # Serialize even an uninitialized OFF account with first enablement. Do not
    # create an authorization anchor or migrate a database merely to close it.
    with locked(store.anchor_root.parent / 'connection-setup.lock', nonblocking=True), \
            draft_writer(store.policy.root, store.policy.data['appid']):
        guard()
        with store.connection() as db:
            if expected_policy is not _UNSET and store._setting_policy(db) != expected_policy:
                fail('PUBLICATION_AUTHORITY_CHANGED')
        state = store.state()
        if not state['enabled']:
            return state if operation_id is None else state | {'operation_id': operation_id,
                'durable': {'state': 'NO_CHANGE', 'publication': 'DISABLE'}}
        def apply(db, seq):
            guard()
            if expected_policy is not _UNSET and store._setting_policy(db) != expected_policy:
                fail('PUBLICATION_AUTHORITY_CHANGED')
            db.execute('UPDATE publication_policy SET enabled=0 WHERE account_key=? AND retired=0',(store.key,))
            db.execute("UPDATE publication_intents SET state='CANCELLED_BEFORE_SUBMIT' WHERE account_key=? AND submit_count=0 AND state IN ('PREPARED','HOLD')",(store.key,))
        data = {} if operation_id is None else {'operation_id': operation_id}
        commit_event(store,'DISABLE',data,apply)
        result = store.state()
        return result if operation_id is None else result | {'operation_id': operation_id,
            'durable': {'state': 'COMMITTED', 'publication': 'DISABLE'}}


from .draft_group_history_context import locator_scope as _history_scope
