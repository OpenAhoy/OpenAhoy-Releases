"""Durable offline state. Each mutation obtains a SQLite write transaction."""
from contextlib import contextmanager, closing
import os
import json
from pathlib import Path
import sqlite3
import re
from uuid import uuid4

BUSINESS_SCHEMA_VERSION = 7
BUSINESS_TABLES = ("sessions", "connections", "grants", "materials", "drafts", "versions", "intents", "operations",
                   "account_profiles", "connection_registry", "binding_transactions", "local_assets", "prepared_versions",
                   "upload_attempts", "prepared_draft_attempts", "host_input_operations")


def register_legacy_profile(db, conn, owner=None):
    """Local v2 identity only; no inferred external account or grant owner."""
    profile = uuid4().hex
    available = sorted(k for k, v in json.loads(conn["capabilities"]).items() if v == "available")
    caps = json.dumps(available, separators=(",", ":"))
    db.execute("INSERT INTO account_profiles VALUES(?,?,?,?,?,?,0)",
               (profile, conn["tenant"], "legacy.local", conn["id"], conn["id"], owner))
    db.execute("INSERT INTO connection_registry VALUES(?,?,0,?,?,0,?,?)",
               (conn["id"], profile, "active" if conn["active"] else "revoked", conn["expires"], caps, caps))

SCHEMA = """
CREATE TABLE IF NOT EXISTS service_config (id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
 client TEXT NOT NULL, expires REAL NOT NULL, active INTEGER NOT NULL,
 connections TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS connections (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, account_type TEXT NOT NULL,
 qualification TEXT NOT NULL, secret_ref TEXT NOT NULL, capabilities TEXT NOT NULL,
 expires REAL NOT NULL, generation INTEGER NOT NULL, active INTEGER NOT NULL,
 evidence TEXT NOT NULL, preview_targets TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS grants (
 connection TEXT NOT NULL, principal TEXT NOT NULL, capabilities TEXT NOT NULL,
 expires REAL NOT NULL, PRIMARY KEY(connection, principal));
CREATE TABLE IF NOT EXISTS materials (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, connection TEXT NOT NULL,
 digest TEXT NOT NULL, expires REAL NOT NULL, platform_ref TEXT);
CREATE TABLE IF NOT EXISTS drafts (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, connection TEXT NOT NULL,
 current_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (
 id TEXT PRIMARY KEY, draft TEXT NOT NULL, content TEXT NOT NULL,
 digest TEXT NOT NULL, platform_ref TEXT);
CREATE TABLE IF NOT EXISTS intents (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
 client TEXT NOT NULL, session TEXT NOT NULL, connection TEXT NOT NULL,
 generation INTEGER NOT NULL, kind TEXT NOT NULL, draft TEXT NOT NULL,
 version TEXT NOT NULL, targets TEXT NOT NULL, expires REAL NOT NULL,
 binding TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0, operation_id TEXT);
CREATE TABLE IF NOT EXISTS operations (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
 connection TEXT NOT NULL, kind TEXT NOT NULL, request_key TEXT NOT NULL,
 fingerprint TEXT NOT NULL, version TEXT, targets TEXT NOT NULL,
 generation INTEGER NOT NULL, state TEXT NOT NULL, platform_ref TEXT,
 result TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL,
 UNIQUE(tenant, principal, connection, request_key));
CREATE UNIQUE INDEX IF NOT EXISTS one_publication_per_version
 ON operations(tenant, connection, version) WHERE kind='publication.submit';
CREATE TABLE IF NOT EXISTS account_profiles (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, namespace TEXT NOT NULL,
 account TEXT NOT NULL, resource TEXT NOT NULL, owner TEXT, epoch INTEGER NOT NULL,
 UNIQUE(tenant,namespace,account), UNIQUE(tenant,resource));
CREATE TABLE IF NOT EXISTS connection_registry (
 connection TEXT PRIMARY KEY, profile TEXT NOT NULL, managed INTEGER NOT NULL,
 state TEXT NOT NULL, token_expires REAL NOT NULL, token_revision INTEGER NOT NULL,
 account_caps TEXT NOT NULL, authorized_caps TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS binding_transactions (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
 client TEXT NOT NULL, session TEXT NOT NULL, nonce TEXT NOT NULL,
 expires REAL NOT NULL, connection TEXT NOT NULL, profile TEXT NOT NULL,
 expected_generation INTEGER NOT NULL, expected_epoch INTEGER NOT NULL,
 guard_digest TEXT NOT NULL, payload TEXT NOT NULL, used INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS local_assets (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
 connection TEXT NOT NULL, resource TEXT NOT NULL, generation INTEGER NOT NULL,
 epoch INTEGER NOT NULL, role TEXT NOT NULL, declared_type TEXT NOT NULL,
 size INTEGER NOT NULL, digest TEXT NOT NULL, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS prepared_versions (
 version TEXT PRIMARY KEY, bundle TEXT NOT NULL, revision INTEGER NOT NULL,
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL,
 resource TEXT NOT NULL, generation INTEGER NOT NULL, epoch INTEGER NOT NULL,
 manifest TEXT NOT NULL, digest TEXT NOT NULL,
 UNIQUE(bundle,revision));
CREATE TABLE IF NOT EXISTS upload_attempts (
 id TEXT PRIMARY KEY, mode TEXT NOT NULL CHECK(mode='test'),
 provenance TEXT NOT NULL CHECK(provenance='LOCAL_FIXED_FIXTURE'),
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL,
 resource TEXT NOT NULL, request_key TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose IN ('permanent_cover','article_body')),
 selector TEXT NOT NULL, intent TEXT NOT NULL, fingerprint TEXT NOT NULL,
 target TEXT NOT NULL, fence TEXT NOT NULL,
 token_revision INTEGER NOT NULL CHECK(token_revision>=0), owner TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','FIXTURE_SUCCEEDED')),
 created REAL NOT NULL, completed REAL,
 cover_media_id TEXT, cover_url TEXT, body_url TEXT,
 UNIQUE(mode,tenant,principal,connection,request_key), UNIQUE(target),
 CHECK((state='RESULT_UNKNOWN' AND completed IS NULL AND cover_media_id IS NULL
         AND cover_url IS NULL AND body_url IS NULL)
    OR (state='FIXTURE_SUCCEEDED' AND completed IS NOT NULL
        AND ((purpose='permanent_cover' AND cover_media_id IS NOT NULL AND cover_url IS NOT NULL AND body_url IS NULL)
          OR (purpose='article_body' AND body_url IS NOT NULL AND cover_media_id IS NULL AND cover_url IS NULL)))));
CREATE UNIQUE INDEX IF NOT EXISTS one_unknown_upload_per_resource
 ON upload_attempts(mode,tenant,resource,purpose) WHERE state='RESULT_UNKNOWN';
CREATE TABLE IF NOT EXISTS prepared_draft_attempts (
 id TEXT PRIMARY KEY, mode TEXT NOT NULL CHECK(mode='test'),
 provenance TEXT NOT NULL CHECK(provenance='LOCAL_FIXED_FIXTURE'),
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL,
 resource TEXT NOT NULL, request_key TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose='prepared-draft-create'),
 selector TEXT NOT NULL, intent TEXT NOT NULL, fingerprint TEXT NOT NULL,
 target TEXT NOT NULL, fence TEXT NOT NULL,
 token_revision INTEGER NOT NULL CHECK(token_revision>=0), owner TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','FIXTURE_SAVED')),
 created REAL NOT NULL, completed REAL,
 renderer_version INTEGER NOT NULL CHECK(renderer_version=1),
 protocol_version INTEGER NOT NULL CHECK(protocol_version=1),
 projection_digest TEXT NOT NULL, uploads TEXT NOT NULL, reference TEXT,
 UNIQUE(mode,tenant,principal,connection,request_key), UNIQUE(target),
 CHECK((state='RESULT_UNKNOWN' AND completed IS NULL AND reference IS NULL)
    OR (state='FIXTURE_SAVED' AND completed IS NOT NULL AND reference IS NOT NULL)));
CREATE UNIQUE INDEX IF NOT EXISTS one_unknown_prepared_draft_per_resource
 ON prepared_draft_attempts(mode,tenant,resource,purpose) WHERE state='RESULT_UNKNOWN';
CREATE TABLE IF NOT EXISTS host_input_operations (
 id TEXT PRIMARY KEY, mode TEXT NOT NULL CHECK(mode='test'),
 provenance TEXT NOT NULL CHECK(provenance='LOCAL_HOST_INPUT'),
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL,
 resource TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation>=0),
 epoch INTEGER NOT NULL CHECK(epoch>=0),
 kind TEXT NOT NULL CHECK(kind IN ('asset','prepare')),
 request_key TEXT NOT NULL, intent TEXT NOT NULL, fingerprint TEXT NOT NULL,
 result TEXT NOT NULL, result_digest TEXT NOT NULL, created REAL NOT NULL,
 UNIQUE(mode,tenant,principal,connection,kind,request_key));
"""


def _normalized_sql(value):
    # Preserve quoted literals: CHECKs and partial predicates are semantic.
    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|[^\s]", value)
    tokens = [t if t.startswith(("'", '"')) else t.lower() for t in tokens]
    return re.sub(r'^(create(?:table|uniqueindex|index))ifnotexists', r'\1', ''.join(tokens))


def _structure(db, table):
    row = db.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (table,)).fetchone()
    if row is None or row[0] != 'table':
        raise ValueError('Incomplete business state')
    columns = [tuple(r) for r in db.execute(f'PRAGMA table_info({table})')]
    indexes = []
    for index in db.execute(f'PRAGMA index_list({table})'):
        name = index[1]
        # Names are database data; quote them, never interpolate executable SQL.
        quoted = '"' + name.replace('"', '""') + '"'
        fields = tuple(r[2] for r in db.execute(f'PRAGMA index_info({quoted})'))
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name=? AND type='index'", (name,)).fetchone()
        indexes.append((index[2], index[3], index[4], fields,
                        _normalized_sql(sql[0]) if sql and sql[0] else ''))
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)).fetchone():
        raise ValueError('Unexpected business trigger')
    return columns, sorted(indexes), _normalized_sql(row[1])


def _check_business_schema(db, version):
    # Historical required tables are checked BEFORE CREATE IF NOT EXISTS.
    counts = {3: 11, 4: 13, 5: 14, 6: 15, 7: 16}
    required = ('service_config',) + BUSINESS_TABLES[:counts[version]]
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(SCHEMA)
        for table in ('service_config',) + BUSINESS_TABLES:
            if table in required or table in names:
                if _structure(db, table) != _structure(expected, table):
                    raise ValueError('Invalid business state structure')


class Database:
    def __init__(self, path: str | Path, schema: str = SCHEMA, application_id: int = 0x57434531):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError("State must not be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                app_id = db.execute("PRAGMA application_id").fetchone()[0]
                tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if app_id != application_id and (app_id != 0 or tables):
                    raise ValueError("Refusing unrelated database")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                target_version = BUSINESS_SCHEMA_VERSION if application_id == 0x57434531 else 2
                if version not in range(target_version + 1):
                    raise ValueError("Unsupported state schema")
                self.previous_version = version
                if application_id == 0x57434531 and version >= 3:
                    _check_business_schema(db, version)
                db.execute(f"PRAGMA application_id={application_id}")
                # Initial candidate state v0 may exist from an earlier offline run.
                if application_id == 0x57434531 and any(row[0] == "intents" for row in tables):
                    columns = {row[1] for row in db.execute("PRAGMA table_info(intents)")}
                    if "operation_id" not in columns:
                        db.execute("ALTER TABLE intents ADD COLUMN operation_id TEXT")
                        db.execute("UPDATE intents SET confirmed=0")
                if application_id == 0x57434531 and any(row[0] == "operations" for row in tables):
                    operation_sql = db.execute("SELECT sql FROM sqlite_master WHERE name='operations'").fetchone()[0]
                    if "UNIQUE(tenant, principal, request_key)" in operation_sql:
                        db.execute("ALTER TABLE operations RENAME TO operations_legacy")
                        db.execute("DROP INDEX IF EXISTS one_publication_per_version")
                        create_operations = next(s for s in schema.split(";") if "CREATE TABLE IF NOT EXISTS operations (" in s)
                        db.execute(create_operations)
                        db.execute("INSERT INTO operations SELECT * FROM operations_legacy")
                        db.execute("DROP TABLE operations_legacy")
                for statement in schema.split(";"):
                    if statement.strip():
                        db.execute(statement)
                if application_id == 0x57434531 and version < 3:
                    missing = db.execute("SELECT c.* FROM connections c LEFT JOIN connection_registry r "
                                         "ON r.connection=c.id WHERE r.connection IS NULL").fetchall()
                    for conn in missing:
                        register_legacy_profile(db, conn)
                if application_id == 0x57434531:
                    _check_business_schema(db, BUSINESS_SCHEMA_VERSION)
                db.execute(f"PRAGMA user_version={target_version}")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self, write: bool = False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
