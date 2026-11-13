"""Own resources and admissions in one independent schema4 database.

Only exact older own schemas are migrated transactionally. Business/transport and
different-provenance fixture databases are never promoted.
"""
from contextlib import contextmanager, closing
import os
from pathlib import Path
import sqlite3

from .contracts import WCEError
from .own_auth import SOURCES
from .storage import Database, _structure
from .own_validation_scope import OwnedConnection, content_scope

APP_ID = 0x57434f31
VERSION = 4
SCHEMA_V1 = "CREATE TABLE own_config(id INTEGER PRIMARY KEY CHECK(id=1), source_kind TEXT NOT NULL CHECK(source_kind IN ('SYNTHETIC_SETUP','OPERATOR_ATTESTED')));\nCREATE TABLE own_resources(tenant TEXT NOT NULL, account TEXT NOT NULL, resource TEXT NOT NULL, source_kind TEXT NOT NULL CHECK(source_kind IN ('SYNTHETIC_SETUP','OPERATOR_ATTESTED')), PRIMARY KEY(tenant,resource), UNIQUE(tenant,account));\nCREATE TABLE own_assets(id TEXT PRIMARY KEY, binding TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('cover','body')), mime TEXT NOT NULL CHECK(mime IN ('image/png','image/jpeg')), size INTEGER NOT NULL CHECK(typeof(size)='integer' AND size>0 AND size<=2097152), sha256 TEXT NOT NULL, data BLOB NOT NULL CHECK(typeof(data)='blob' AND length(data)=size));\nCREATE TABLE own_articles(version TEXT PRIMARY KEY, bundle TEXT NOT NULL, revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0), binding TEXT NOT NULL, manifest TEXT NOT NULL, digest TEXT NOT NULL, UNIQUE(bundle,revision));\nCREATE TABLE own_inputs(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('asset','prepare')), request_key TEXT NOT NULL, parameters TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, result_digest TEXT NOT NULL, UNIQUE(tenant,principal,connection,kind,request_key));\nCREATE TABLE own_approvals(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL, resource TEXT NOT NULL, binding_fence TEXT NOT NULL, manifest_digest TEXT NOT NULL, body TEXT NOT NULL, body_digest TEXT NOT NULL, expires REAL NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0 CHECK(typeof(cancelled)='integer' AND cancelled IN (0,1)), FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource));\nCREATE TABLE own_steps(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL, resource TEXT NOT NULL, request_key TEXT NOT NULL, operation TEXT NOT NULL CHECK(operation IN ('cover','body','add')), slot TEXT NOT NULL, manifest_digest TEXT NOT NULL, target TEXT NOT NULL UNIQUE, approval_id TEXT NOT NULL REFERENCES own_approvals(id), approval_digest TEXT NOT NULL, intent TEXT NOT NULL, intent_digest TEXT NOT NULL, owner TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','SUCCEEDED')), result TEXT NOT NULL DEFAULT '{}', result_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a', created REAL NOT NULL, completed REAL, readback TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK(readback IN ('UNVERIFIED','MATCHED')), UNIQUE(tenant,principal,connection,request_key), FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource), CHECK((state='RESULT_UNKNOWN' AND result='{}' AND result_digest='44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a' AND completed IS NULL AND readback='UNVERIFIED') OR (state='SUCCEEDED' AND result!='{}' AND completed IS NOT NULL)), CHECK(operation='add' OR readback='UNVERIFIED'));\nCREATE UNIQUE INDEX one_unknown_own_resource ON own_steps(tenant,resource) WHERE state='RESULT_UNKNOWN';\n"


EXTRA_SCHEMA = """
CREATE TABLE own_body_recoveries(
 id TEXT PRIMARY KEY, original_step_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id),
 tenant TEXT NOT NULL, resource TEXT NOT NULL, owner TEXT NOT NULL,
 approval_id TEXT NOT NULL REFERENCES own_approvals(id), approval_digest TEXT NOT NULL,
 intent TEXT NOT NULL, intent_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','SUCCEEDED')),
 result TEXT NOT NULL DEFAULT '{}', result_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 diagnostic TEXT NOT NULL DEFAULT '{}', diagnostic_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 created REAL NOT NULL, completed REAL,
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource),
 CHECK((state='RESULT_UNKNOWN' AND result='{}' AND completed IS NULL) OR
       (state='SUCCEEDED' AND result!='{}' AND completed IS NOT NULL)));
CREATE TABLE own_step_diagnostics(
 step_id TEXT PRIMARY KEY REFERENCES own_steps(id), owner TEXT NOT NULL,
 intent_digest TEXT NOT NULL, payload TEXT NOT NULL, payload_digest TEXT NOT NULL);
CREATE TABLE own_resource_locks(
 tenant TEXT NOT NULL, resource TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('step','recovery')), owner_id TEXT NOT NULL UNIQUE,
 PRIMARY KEY(tenant,resource), FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource));
"""
OLD_INDEX = "CREATE UNIQUE INDEX one_unknown_own_resource ON own_steps(tenant,resource) WHERE state='RESULT_UNKNOWN';"
SCHEMA_V2 = SCHEMA_V1.replace(OLD_INDEX, '') + EXTRA_SCHEMA
FOLLOWUP_SCHEMA = """
CREATE TABLE own_body_followups(
 id TEXT PRIMARY KEY, original_step_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id),
 prior_recovery_id TEXT NOT NULL UNIQUE REFERENCES own_body_recoveries(id),
 tenant TEXT NOT NULL, resource TEXT NOT NULL, owner TEXT NOT NULL,
 approval_id TEXT NOT NULL REFERENCES own_approvals(id), approval_digest TEXT NOT NULL,
 intent TEXT NOT NULL, intent_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','SUCCEEDED')),
 result TEXT NOT NULL DEFAULT '{}', result_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 created REAL NOT NULL, completed REAL,
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource),
 CHECK((state='RESULT_UNKNOWN' AND result='{}' AND completed IS NULL) OR
       (state='SUCCEEDED' AND result!='{}' AND completed IS NOT NULL)));
CREATE TABLE own_body_observations(
 followup_id TEXT PRIMARY KEY REFERENCES own_body_followups(id), owner TEXT NOT NULL,
 intent_digest TEXT NOT NULL, payload TEXT NOT NULL, payload_digest TEXT NOT NULL,
 observed_at REAL NOT NULL);
"""
SCHEMA_V3 = SCHEMA_V2.replace("kind IN ('step','recovery')", "kind IN ('step','recovery','body_followup')") + FOLLOWUP_SCHEMA


ATTEMPT_SCHEMA = """
CREATE TABLE own_body_attempts(
 id TEXT PRIMARY KEY, original_step_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id),
 ordinal INTEGER NOT NULL CHECK(typeof(ordinal)='integer' AND ordinal=4),
 tenant TEXT NOT NULL, resource TEXT NOT NULL, owner TEXT NOT NULL,
 approval_id TEXT NOT NULL REFERENCES own_approvals(id), approval_digest TEXT NOT NULL,
 intent TEXT NOT NULL, intent_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','SUCCEEDED')),
 observation TEXT NOT NULL DEFAULT '{}', observation_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 result TEXT NOT NULL DEFAULT '{}', result_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 created REAL NOT NULL, completed REAL,
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource),
 CHECK((state='RESULT_UNKNOWN' AND result='{}' AND completed IS NULL) OR
       (state='SUCCEEDED' AND result!='{}' AND completed IS NOT NULL)));
"""
SCHEMA = SCHEMA_V3.replace("kind IN ('step','recovery','body_followup')",
    "kind IN ('step','recovery','body_followup','body_attempt')") + ATTEMPT_SCHEMA


class OwnStore(Database):
    def __init__(self, path, source_kind, persistent=False, *, history_policy=None, physical_resources=None):
        self.path = Path(path)
        self.history_policy = history_policy
        if source_kind not in SOURCES or self.path.is_symlink():
            raise WCEError('OWN_STATE_UNVERIFIED')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    from .own_history_locators import history_scope
                    from .draft_group_history_context import physical_material_scope
                    with physical_material_scope(db,self.history_policy,physical_resources), history_scope(self.history_policy, db) as history:
                        app = db.execute('PRAGMA application_id').fetchone()[0]
                        version = db.execute('PRAGMA user_version').fetchone()[0]
                        objects = db.execute('SELECT name FROM sqlite_master').fetchall()
                        if app == 0 and version == 0 and not objects:
                            for statement in SCHEMA.split(';'):
                                if statement.strip():
                                    db.execute(statement)
                            db.execute('INSERT INTO own_config VALUES(1,?)', (source_kind,))
                            db.execute(f'PRAGMA application_id={APP_ID}')
                            db.execute(f'PRAGMA user_version={VERSION}')
                        elif app == APP_ID and version == 1:
                            self._check_schema(db, source_kind, 1)
                            self._check_legacy_history(db, source_kind, history=history)
                            for statement in EXTRA_SCHEMA.split(';'):
                                if statement.strip():
                                    db.execute(statement)
                            db.execute("INSERT INTO own_resource_locks SELECT tenant,resource,'step',id "
                                       "FROM own_steps WHERE state='RESULT_UNKNOWN'")
                            db.execute('DROP INDEX one_unknown_own_resource')
                            db.execute('PRAGMA user_version=2')
                            version = 2
                        elif app != APP_ID or version not in (2, 3, VERSION, 5, 6, 7, 8, 9):
                            raise ValueError()
                        if version == 2:
                            self._check_records(db, source_kind, 2, self.history_policy, history=history)
                            self._check_legacy_history(db, source_kind, history=history)
                            for statement in FOLLOWUP_SCHEMA.split(';'):
                                if statement.strip():
                                    db.execute(statement)
                            db.execute('ALTER TABLE own_resource_locks RENAME TO own_resource_locks_v2')
                            db.execute(EXTRA_SCHEMA[EXTRA_SCHEMA.index('CREATE TABLE own_resource_locks'):].strip().replace(
                                "kind IN ('step','recovery')", "kind IN ('step','recovery','body_followup')"))
                            db.execute('INSERT INTO own_resource_locks SELECT * FROM own_resource_locks_v2')
                            db.execute('DROP TABLE own_resource_locks_v2')
                            db.execute('PRAGMA user_version=3')
                            version = 3
                        if version == 3:
                            self._check_records(db, source_kind, 3, self.history_policy, history=history)
                            self._check_legacy_history(db, source_kind, history=history)
                            for statement in ATTEMPT_SCHEMA.split(';'):
                                if statement.strip():
                                    db.execute(statement)
                            db.execute('ALTER TABLE own_resource_locks RENAME TO own_resource_locks_v3')
                            db.execute(EXTRA_SCHEMA[EXTRA_SCHEMA.index('CREATE TABLE own_resource_locks'):].strip().replace(
                                "kind IN ('step','recovery')", "kind IN ('step','recovery','body_followup','body_attempt')"))
                            db.execute('INSERT INTO own_resource_locks SELECT * FROM own_resource_locks_v3')
                            db.execute('DROP TABLE own_resource_locks_v3')
                            db.execute(f'PRAGMA user_version={VERSION}')
                        if persistent and db.execute('PRAGMA user_version').fetchone()[0] == 4:
                            self._check_records(db, source_kind, 4, self.history_policy, history=history)
                            self._check_legacy_history(db, source_kind, history=history)
                            from .own_lineage import SCHEMA as LINEAGE_SCHEMA, register, manifest
                            for statement in LINEAGE_SCHEMA.split(';'):
                                if statement.strip():
                                    db.execute(statement)
                            for row in db.execute('SELECT * FROM own_articles ORDER BY rowid').fetchall():
                                register(db, manifest(row), legacy=True)
                            db.execute('PRAGMA user_version=5')
                        self.check(db, source_kind, self.history_policy, history=history)
                        self._check_legacy_history(db, source_kind, history=history)
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
        except Exception:
            raise WCEError('OWN_STATE_UNVERIFIED') from None

    def _check_legacy_history(self, db, source_kind, *, history=None):
        return _check_legacy_history_in(db, source_kind, self, history=history)

    @staticmethod
    def check(db, source_kind, history_policy=None, *, history=None):
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (4, 5, 6, 7, 8, 9):
            raise WCEError('OWN_STATE_UNVERIFIED')
        OwnStore._check_records(db, source_kind, version, history_policy, history=history)

    @staticmethod
    def _check_records(db, source_kind, version, history_policy=None, *, history=None):
        from .own_history_locators import history_scope
        with history_scope(history_policy, db, history) as scope:
            return OwnStore._records_impl(db, source_kind, version, history_policy, history=scope)

    @staticmethod
    def _check_layout(db, source_kind, version):
        from .own_group_prerequisite import check_pending as prerequisite_pending
        prerequisite_pending(db)
        from .own_group_schema import check_pending
        check_pending(db)
        from .own_draft_restore_schema import check_marker
        check_marker(db)
        OwnStore._check_schema(db, source_kind, version)

    @staticmethod
    def _records_impl(db, source_kind, version, history_policy=None, *, history=None):
        OwnStore._check_layout(db, source_kind, version)
        if version == 5:
            from .own_lineage_replacement import check_account_claims
            check_account_claims(db, source_kind, history_policy, history=history)
        from .own_draft_restore_store import check_external as check_restore_spent
        check_restore_spent(db)
        from .own_body_spent import check as check_spent
        check_spent(db)
        from .own_body_recovery import validate_record
        from .own_diagnostics import read
        recoveries = {}
        for row in db.execute('SELECT * FROM own_body_recoveries'):
            original, _, _, _ = validate_record(db, row, source_kind)
            recoveries[original['id']] = row
        followups = {}
        if version >= 3:
            from .own_body_followup import validate_record as validate_followup
            for row in db.execute('SELECT * FROM own_body_followups'):
                original, _, _, _ = validate_followup(db, row, source_kind)
                followups[original['id']] = row
            # Every observation belongs to an independently validated followup.
            if db.execute('SELECT 1 FROM own_body_observations o LEFT JOIN own_body_followups f '
                          'ON f.id=o.followup_id WHERE f.id IS NULL').fetchone():
                raise WCEError('OWN_STATE_UNVERIFIED')
        attempts = {}
        if version >= 4:
            from .own_body_attempt import validate_record as validate_attempt
            for row in db.execute('SELECT * FROM own_body_attempts'):
                original, _, _, _ = validate_attempt(db, row, source_kind)
                attempts[original['id']] = row
        expected = {}
        lineage_maps, scoped_expected = {}, {}
        if version in (5, 6, 7, 8, 9):
            from .own_lineage_validation import validate
            lineage_maps = validate(db)
        replacement_successes = {}
        if version in (6, 7, 8, 9):
            from .own_lineage_replacement import validate_all
            replacement_successes = validate_all(db, source_kind, history_policy, history=history, history_locators=history)
        for row in db.execute("SELECT * FROM own_steps WHERE state='RESULT_UNKNOWN'"):
            if row['id'] in replacement_successes:
                continue  # Fully validated new origin; original row is unchanged.
            recovery = recoveries.get(row['id'])
            followup = followups.get(row['id'])
            attempt = attempts.get(row['id'])
            if attempt is not None and attempt['state'] == 'SUCCEEDED':
                continue
            if followup is not None and followup['state'] == 'SUCCEEDED':
                continue
            if recovery is not None and recovery['state'] == 'SUCCEEDED':
                continue
            key = (row['tenant'], row['resource'])
            if version in (5, 6, 7, 8, 9):
                import json
                m = lineage_maps[json.loads(row['intent'])['selector']['version']]
                if not m['legacy']:
                    if recovery is not None or followup is not None or attempt is not None:
                        raise WCEError('OWN_STATE_UNVERIFIED')
                    scoped_key = key + (m['lineage'],)
                    if scoped_key in scoped_expected:
                        raise WCEError('OWN_STATE_UNVERIFIED')
                    scoped_expected[scoped_key] = row['id']
                    continue
            if key in expected:
                raise WCEError('OWN_STATE_UNVERIFIED')
            expected[key] = (('body_attempt', attempt['id']) if attempt is not None else
                ('body_followup', followup['id']) if followup is not None else
                ('step', row['id']) if recovery is None else ('recovery', recovery['id']))
        actual = {(row['tenant'], row['resource']): (row['kind'], row['owner_id'])
                  for row in db.execute('SELECT * FROM own_resource_locks')}
        if actual != expected:
            raise WCEError('OWN_STATE_UNVERIFIED')
        if version in (5, 6, 7, 8, 9):
            actual_scoped = {(r['tenant'], r['resource'], r['lineage']): r['owner_id']
                for r in db.execute('SELECT * FROM own_lineage_locks')}
            if actual_scoped != scoped_expected:
                raise WCEError('OWN_STATE_UNVERIFIED')
        if version in (8, 9):
            from .own_draft_restore_store import validate as validate_restores
            validate_restores(db, source_kind, history_policy)
        from .own_group_prerequisite import check_ancestry as prerequisite_ancestry
        prerequisite_ancestry(db, source_kind, history_policy)
        if version == 9:
            from .own_group_schema import check_ancestry
            from .draft_group_store import check_records9
            check_ancestry(db, source_kind, history_policy, history=history)
            check_records9(db, source_kind, history_policy, history_locators=history)
        for row in db.execute('SELECT s.* FROM own_steps s JOIN own_step_diagnostics d ON s.id=d.step_id'):
            read(db, row)

    @staticmethod
    def _check_schema(db, source_kind, version):
        if type(version) is not int or db.execute('PRAGMA user_version').fetchone()[0] != version:
            raise WCEError('OWN_STATE_UNVERIFIED')
        if version in (6, 7, 8, 9):
            from .own_lineage_replacement import schema_check
            return schema_check(db, source_kind)
        if (db.execute('PRAGMA application_id').fetchone()[0] != APP_ID
                or db.execute('PRAGMA user_version').fetchone()[0] != version):
            raise WCEError('OWN_STATE_UNVERIFIED')
        with closing(sqlite3.connect(':memory:')) as expected:
            from .own_lineage import SCHEMA as LINEAGE_SCHEMA
            expected.executescript({1: SCHEMA_V1, 2: SCHEMA_V2, 3: SCHEMA_V3,
                                   4: SCHEMA, 5: SCHEMA + LINEAGE_SCHEMA}[version])
            names = {r[0] for r in expected.execute('SELECT name FROM sqlite_master')}
            if {r[0] for r in db.execute('SELECT name FROM sqlite_master')} != names:
                raise WCEError('OWN_STATE_UNVERIFIED')
            for r in expected.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                if _structure(db, r[0]) != _structure(expected, r[0]):
                    raise WCEError('OWN_STATE_UNVERIFIED')
        rows = db.execute('SELECT * FROM own_config').fetchall()
        if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['source_kind'] != source_kind:
            raise WCEError('OWN_STATE_UNVERIFIED')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise WCEError('OWN_STATE_UNVERIFIED')

    @contextmanager
    def connect(self):
        from .own_history_source import owned_connection
        with owned_connection(self.path) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            from .draft_group_history_context import history_policy_context
            with history_policy_context(self.path, db, self.history_policy):
                yield db

    @contextmanager
    def transaction_with_history(self, write: bool = False, *, physical_resources=None):
        """One original transaction and H through all readers and final fences."""
        from .own_history_locators import history_scope
        scope=(self.transaction(write=write) if physical_resources is None else
               self.transaction(write=write,physical_resources=physical_resources))
        with scope as db:
            with history_scope(self.history_policy, db) as history_locators:
                yield db, history_locators

    @contextmanager
    def transaction(self, write: bool = False, *, physical_resources=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                from .draft_group_history_context import physical_material_scope
                with physical_material_scope(db,self.history_policy,physical_resources), content_scope(self, db):
                    yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise


def _check_legacy_history_in(db, source_kind, history_store, *, history=None):
    """Validate durable history without inventing a live grant or lease.
    Reuse the workflow's historical validators before adopting any old
    admission. This also verifies linked assets, approvals and cover proof
    files. No current profile, sender or token broker is constructed.
    """
    from types import SimpleNamespace
    from .contracts import Actor
    from .own_workflow import OwnWorkflow, binding_validate, stored
    evidence_scope = history
    history = object.__new__(OwnWorkflow)
    history.db = history_store
    history.history_locators = evidence_scope
    if getattr(history_store, "history_policy", None) is not None:
        history.policy = history_store.history_policy
    # Reuse only validated immutable bundle content in this exact owned SQL
    # lifetime; every row, approval, proof and dynamic check still runs.
    with content_scope(history_store, db):
        for row in db.execute('SELECT * FROM own_steps ORDER BY rowid'):
            intent = stored(row['intent'], row['intent_digest'])
            binding = intent['binding']
            binding_validate(binding)
            if binding['source_kind'] != source_kind:
                raise WCEError('OWN_STATE_UNVERIFIED')
            resource = db.execute('SELECT * FROM own_resources WHERE tenant=? AND resource=?',
                (binding['tenant'], binding['resource'])).fetchone()
            if (resource is None or resource['account'] != binding['account']
                    or resource['source_kind'] != source_kind):
                raise WCEError('OWN_STATE_UNVERIFIED')
            # This identity is used only by _step(..., active=False) history
            # checks. It has no runtime fence, credentials or network methods.
            profile = SimpleNamespace(actor=Actor(binding['tenant'], binding['principal'],
                binding['client'], binding['session']), connection_id=binding['connection'],
                account_id=binding['account'], resource_id=binding['resource'],
                source_kind=source_kind, binding=lambda b=binding: dict(b))
            history._step(db, profile, row, history_locators=evidence_scope)
