"""Private local production preferences. Never an account grant or business DB.

Text and immutable history are incremental SQLite rows. Per-call chunk bounds
are transport resources, never a total preference/history/production quota.
"""
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import sys

from .contracts import WCEError
from .own_connection_policy import locked, registry_path, load_policy, read_registry
from .own_bootstrap_security import path_check
from .service import canonical, digest
from .own_production_rules_legacy import snapshot as legacy_snapshot, PREFIX as LEGACY_PREFIX
from .own_history_source import owned_connection, connection_source

FIELDS = ('audience_topics', 'author', 'voice', 'image_preferences',
          'visual_layout', 'content_qa', 'delivery_publication', 'additional_notes')
CHUNK_CHARACTERS = 8192
CHUNK_UTF8_BYTES = 32768
DATABASE = 'production-rules.sqlite3'
LOCK = 'production-rules.lock'
OP = re.compile(r'rules-[a-f0-9]{32}')
HASH = re.compile(r'[a-f0-9]{64}')
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
SECRET = re.compile(r'(?i)(?:appsecret|access[_ -]?token|api[_ -]?key|password|密码|密钥)\s*[:=：]\s*\S+')


def need(value, code='RULES_INVALID_REQUEST'):
    if value is not True:
        raise WCEError(code)


def integer(value):
    need(type(value) is int and 0 <= value <= 2**53 - 1)
    return value


def text_chunk(value):
    need(type(value) is str and len(value) <= CHUNK_CHARACTERS
         and CONTROL.search(value) is None)
    try:
        raw = value.encode('utf-8')
    except UnicodeError:
        raise WCEError('RULES_INVALID_UNICODE') from None
    need(len(raw) <= CHUNK_UTF8_BYTES)
    need(SECRET.search(value) is None, 'RULES_SECRET_NOT_ALLOWED')
    return raw


def fields_manifest(value):
    need(type(value) is list and len(value) <= len(FIELDS))
    result = {}
    for item in value:
        need(type(item) is dict and set(item) == {'name', 'chunks', 'unicode_length', 'utf8_bytes', 'sha256'})
        name = item['name']
        need(name in FIELDS and name not in result)
        for key in ('chunks', 'unicode_length', 'utf8_bytes'): integer(item[key])
        need(type(item['sha256']) is str and HASH.fullmatch(item['sha256']) is not None)
        result[name] = {k: item[k] for k in ('chunks', 'unicode_length', 'utf8_bytes', 'sha256')}
    return result


def identity(connection_id, registry):
    """Existing non-secret owner/member projection; never a broker or token."""
    from .own_connection_registry import metadata, validate_owner, OWNER
    from .own_connection_registry import check_member
    with locked(registry.parent/'connections.lock', nonblocking=True, shared=True,
                existing=True, readonly=True):
        owner = metadata(registry.parent/OWNER)
        validate_owner(registry, owner)
        owner_binding = digest(owner)
        binding = owner_binding
        if connection_id:
            current = read_registry(registry)
            path = current['connections'].get(connection_id)
            if path is None:
                from .wechat_component_binding import configuration_account
                row = configuration_account(registry, connection_id)
                need(row is not None, 'RULES_ACCOUNT_UNAVAILABLE')
                binding = digest({'owner': owner_binding, 'provider': 'WECHAT_THIRD_PARTY',
                                  'appid': row['account_id'],
                                  'original_id': row['official_profile']['original_id']})
                return {'owner': owner_binding, 'binding': binding}
            need(path is not None, 'RULES_ACCOUNT_UNAVAILABLE')
            policy = load_policy(path, active=False)
            need(policy.data['connection_id'] == connection_id and policy.value['schema'] == 2, 'RULES_ACCOUNT_UNAVAILABLE')
            check_member(policy, revocation=False, readonly=True)
            binding = digest({'registry': str(registry), 'identity': policy.data,
                              'owner_digest': policy.value.get('owner_digest')})
        return {'owner': owner_binding, 'binding': binding}


SCHEMA = '''
CREATE TABLE meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), owner TEXT NOT NULL, revision INTEGER NOT NULL);
CREATE TABLE operations (id TEXT PRIMARY KEY, scope TEXT NOT NULL, binding TEXT NOT NULL,
 expected_store INTEGER NOT NULL, expected_scope INTEGER NOT NULL, fields TEXT NOT NULL,
 state TEXT NOT NULL, revision INTEGER, scope_revision INTEGER, restore_from TEXT, created REAL NOT NULL);
CREATE TABLE chunks (operation TEXT NOT NULL, field TEXT NOT NULL, position INTEGER NOT NULL,
 text TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(operation,field,position));
CREATE TABLE heads (scope TEXT PRIMARY KEY, binding TEXT NOT NULL, operation TEXT NOT NULL,
 revision INTEGER NOT NULL);
CREATE INDEX operation_history ON operations(scope,binding,revision);
'''


class RulesStore:
    def __init__(self, registry=None, *, identity_resolver=identity, legacy_resolver=legacy_snapshot):
        self.registry = Path(registry) if registry is not None else registry_path()
        self.root = self.registry.parent
        self.path = self.root/DATABASE
        self.lock = self.root/LOCK
        self.legacy = legacy_resolver
        self.resolve = identity_resolver  # Trusted synthetic dependency, never tool input.

    def _who(self, connection_id):
        need(type(connection_id) is str)
        value = self.resolve(connection_id, self.registry)
        need(type(value) is dict and set(value) == {'owner', 'binding'}
             and all(type(v) is str and HASH.fullmatch(v) for v in value.values()), 'RULES_IDENTITY_CHANGED')
        return value

    def _file(self):
        info = self.path.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
             and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
             'RULES_INVALID_STORE')
        return info.st_dev, info.st_ino

    @contextmanager
    def _transaction(self, connection_id, *, write=False):
        parent = path_check(self.root, True)
        setup = (locked(self.root/'connection-setup.lock', nonblocking=True, existing=True)
                 if write else nullcontext())
        with setup:
            who = self._who(connection_id)
            if not os.path.lexists(self.path) and not write:
                need(path_check(self.root, True) == parent, 'RULES_IDENTITY_CHANGED')
                yield None, who
                return
            with locked(self.lock, nonblocking=True, shared=not write,
                        existing=not write, readonly=not write):
                fresh = not os.path.lexists(self.path)
                if fresh:
                    fd = os.open(self.path, os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
                    os.fsync(fd); os.close(fd)
                pin = self._file()
                connection = None
                manager = None
                committed = False
                try:
                    manager = owned_connection(self.path, readonly=not write, timeout=0, isolation_level=None)
                    connection = manager.__enter__()
                    connection.row_factory = sqlite3.Row
                    need(self._file() == pin and path_check(self.root, True) == parent, 'RULES_IDENTITY_CHANGED')
                    connection.execute('PRAGMA trusted_schema=OFF')
                    if write:
                        connection.execute('PRAGMA journal_mode=DELETE')
                        connection.execute('PRAGMA synchronous=FULL')
                    else:
                        connection.execute('PRAGMA query_only=ON')
                    version = connection.execute('PRAGMA user_version').fetchone()[0]
                    # An interrupted first open/schema transaction can leave an
                    # owned, zero-byte target. This exact empty state has no
                    # user data and is recoverable without truncating/replacing
                    # any existing database. Nonempty or unknown stores remain
                    # protected, even when somebody set user_version to zero.
                    empty_initialization = (self.path.stat().st_size == 0 and version == 0
                        and connection.execute('SELECT name FROM sqlite_master').fetchall() == [])
                    if empty_initialization and not write:
                        connection_source(connection).guard()
                        yield None, who
                        need(self._who(connection_id) == who and self._file() == pin
                             and path_check(self.root, True) == parent, 'RULES_IDENTITY_CHANGED')
                        connection_source(connection).guard()
                        return
                    if empty_initialization:
                        connection.executescript('BEGIN IMMEDIATE;'+SCHEMA)
                        connection.execute('INSERT INTO meta VALUES(1,?,0)', (who['owner'],))
                        connection.execute('PRAGMA user_version=1')
                        connection.commit()
                    need(connection.execute('PRAGMA user_version').fetchone()[0] == 1, 'RULES_SCHEMA_UNSUPPORTED')
                    expected_schema = {re.search(r'CREATE (?:TABLE|INDEX) ([a-z_]+)', part).group(1): part.strip()
                                       for part in SCHEMA.strip().split(';') if part.strip()}
                    actual_schema = {row['name']: row['sql'] for row in connection.execute(
                        'SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL')}
                    need(actual_schema == expected_schema, 'RULES_SCHEMA_UNSUPPORTED')
                    connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                    row = connection.execute('SELECT owner FROM meta WHERE singleton=1').fetchone()
                    need(row is not None and row['owner'] == who['owner'], 'RULES_IDENTITY_CHANGED')
                    yield connection, who
                    connection_source(connection).guard()
                    need(self._who(connection_id) == who and self._file() == pin
                         and path_check(self.root, True) == parent, 'RULES_IDENTITY_CHANGED')
                    if write:
                        committed = True
                        connection.commit()
                        directory = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                        try: os.fsync(directory)
                        finally: os.close(directory)
                    else: connection.rollback()
                    need(self._file() == pin, 'RULES_IDENTITY_CHANGED')
                except WCEError:
                    if committed: raise WCEError('RULES_WRITE_RESULT_UNKNOWN') from None
                    raise
                except (sqlite3.Error, OSError):
                    raise WCEError('RULES_WRITE_RESULT_UNKNOWN' if committed else 'RULES_IO_UNAVAILABLE') from None
                finally:
                    if connection is not None:
                        try:
                            if connection.in_transaction: connection.rollback()
                        finally:
                            manager.__exit__(*sys.exc_info())

    @staticmethod
    def _scope(scope, connection_id):
        need(scope in ('global', 'account') and (bool(connection_id) if scope == 'account' else connection_id == ''))
        return 'global' if scope == 'global' else 'account:'+connection_id

    @staticmethod
    def _head(db, scope, binding):
        if db is None: return None
        row = db.execute('SELECT * FROM heads WHERE scope=?', (scope,)).fetchone()
        need(row is None or row['binding'] == binding, 'RULES_IDENTITY_CHANGED')
        return row

    @staticmethod
    def _operation(db, operation_id, scope, binding):
        need(type(operation_id) is str and OP.fullmatch(operation_id) is not None)
        row = db.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone() if db is not None else None
        need(row is not None and row['scope'] == scope and row['binding'] == binding, 'RULES_OPERATION_UNAVAILABLE')
        return row

    @staticmethod
    def _revision(db):
        return db.execute('SELECT revision FROM meta WHERE singleton=1').fetchone()[0] if db is not None else 0

    @staticmethod
    def _result(row):
        return {'operation_id': row['id'], 'state': row['state'], 'store_revision': row['revision'],
                'scope_revision': row['scope_revision']}

    def begin(self, connection_id, scope, operation_id, expected_store_revision, expected_scope_revision, fields):
        target = self._scope(scope, connection_id)
        integer(expected_store_revision); integer(expected_scope_revision)
        need(type(operation_id) is str and OP.fullmatch(operation_id) is not None)
        fields = fields_manifest(fields)
        with self._transaction(connection_id, write=True) as (db, who):
            head = self._head(db, target, who['binding'])
            current = db.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone()
            if current is not None:
                need((current['scope'], current['binding'], current['expected_store'], current['expected_scope'], current['fields'])
                     == (target, who['binding'], expected_store_revision, expected_scope_revision, canonical(fields)),
                     'RULES_OPERATION_CONFLICT')
                return self._result(current)
            need(self._revision(db) == expected_store_revision and (head['revision'] if head else 0) == expected_scope_revision,
                 'RULES_VERSION_CONFLICT')
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,?)',
                       (operation_id, target, who['binding'], expected_store_revision, expected_scope_revision,
                        canonical(fields), 'STAGED', time.time()))
        return {'operation_id': operation_id, 'state': 'STAGED', 'store_revision': None, 'scope_revision': None}

    def chunk(self, connection_id, scope, operation_id, field, index, text):
        target = self._scope(scope, connection_id)
        integer(index); raw = text_chunk(text)
        with self._transaction(connection_id, write=True) as (db, who):
            row = self._operation(db, operation_id, target, who['binding'])
            declared = json.loads(row['fields'])
            need(field in declared and index < declared[field]['chunks'])
            old = db.execute('SELECT text,sha256 FROM chunks WHERE operation=? AND field=? AND position=?',
                             (operation_id, field, index)).fetchone()
            if old is not None:
                need(old['text'] == text and old['sha256'] == sha256(raw).hexdigest(), 'RULES_CHUNK_CONFLICT')
            else:
                need(row['state'] == 'STAGED', 'RULES_OPERATION_COMMITTED')
                db.execute('INSERT INTO chunks VALUES(?,?,?,?,?)', (operation_id, field, index, text, sha256(raw).hexdigest()))
        return {'operation_id': operation_id, 'state': 'CHUNK_STORED', 'field': field, 'index': index}

    @staticmethod
    def _complete(db, row):
        for field, expected in json.loads(row['fields']).items():
            hasher = sha256(); count = characters = size = 0; carry = ''
            # Streaming cursor: never concatenate a whole field or its history.
            for chunk in db.execute('SELECT position,text,sha256 FROM chunks WHERE operation=? AND field=? ORDER BY position', (row['id'], field)):
                raw = text_chunk(chunk['text'])
                need(chunk['position'] == count and sha256(raw).hexdigest() == chunk['sha256'], 'RULES_INCOMPLETE')
                need(SECRET.search(carry + chunk['text']) is None, 'RULES_SECRET_NOT_ALLOWED')
                carry = (carry + chunk['text'])[-256:]
                hasher.update(raw); count += 1; characters += len(chunk['text']); size += len(raw)
            need((count, characters, size, hasher.hexdigest()) ==
                 (expected['chunks'], expected['unicode_length'], expected['utf8_bytes'], expected['sha256']), 'RULES_INCOMPLETE')

    def commit(self, connection_id, scope, operation_id):
        target = self._scope(scope, connection_id)
        with self._transaction(connection_id, write=True) as (db, who):
            row = self._operation(db, operation_id, target, who['binding'])
            if row['state'] == 'STAGED':
                head = self._head(db, target, who['binding'])
                need(self._revision(db) == row['expected_store'] and (head['revision'] if head else 0) == row['expected_scope'],
                     'RULES_VERSION_CONFLICT')
                self._complete(db, row)
                revision, scope_revision = self._revision(db)+1, row['expected_scope']+1
                integer(revision); integer(scope_revision)
                db.execute('UPDATE operations SET state=?,revision=?,scope_revision=? WHERE id=?', ('COMMITTED', revision, scope_revision, operation_id))
                db.execute('INSERT INTO heads VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET operation=excluded.operation,revision=excluded.revision',
                           (target, who['binding'], operation_id, scope_revision))
                db.execute('UPDATE meta SET revision=? WHERE singleton=1', (revision,))
            else: need(row['state'] == 'COMMITTED', 'RULES_INVALID_STORE')
        # Independent handle after writer close; original operation resolves an unknown result.
        try:
            return self.operation(connection_id, scope, operation_id)
        except (WCEError, OSError, sqlite3.Error):
            raise WCEError('RULES_WRITE_RESULT_UNKNOWN') from None

    def operation(self, connection_id, scope, operation_id):
        target = self._scope(scope, connection_id)
        with self._transaction(connection_id) as (db, who):
            return self._result(self._operation(db, operation_id, target, who['binding']))

    def summary(self, connection_id='', scope='global', *, effective=False):
        target = self._scope(scope, connection_id)
        # A completely absent installation has no owner/preferences to inherit.
        # Return data only; do not manufacture owner identity or create files.
        from .own_settings_readonly import _fresh_empty
        if connection_id == '' and scope == 'global' and _fresh_empty(self.registry):
            fields = ({name: {'chunks': 0, 'unicode_length': 0, 'utf8_bytes': 0,
                'sha256': sha256(b'').hexdigest(), 'source': 'default', 'version_id': ''}
                for name in FIELDS} if effective else {})
            return {'state': 'RULES_READ', 'store_revision': 0, 'scope_revision': 0,
                'global_revision': 0, 'fields': fields, 'effective_sha256': digest(fields),
                'scope': scope, 'connection_id': connection_id, 'preferences_only': True}
        with self._transaction(connection_id) as (db, who):
            global_head = self._head(db, 'global', who['owner'])
            account_head = self._head(db, target, who['binding']) if scope == 'account' else None
            legacy = self.legacy(connection_id,self.registry) if effective and connection_id else None
            heads = [('global', global_head)]
            if scope == 'account': heads.append(('account', account_head))
            fields = {}
            scoped_fields = {}
            for label, head in heads:
                if label == 'account' and legacy is not None:
                    for name,text in legacy['fields'].items():
                        raw=text.encode('utf-8')
                        fields[name]={'chunks':1 if text else 0,'unicode_length':len(text),'utf8_bytes':len(raw),
                                      'sha256':sha256(raw).hexdigest(),'source':'legacy-editor','version_id':legacy['version_id']}
                if head:
                    row = db.execute('SELECT * FROM operations WHERE id=?', (head['operation'],)).fetchone()
                    need(row is not None and row['state'] == 'COMMITTED', 'RULES_INVALID_STORE')
                    declared = json.loads(row['fields'])
                    if label == scope: scoped_fields = declared
                    for name, item in declared.items(): fields[name] = item | {'source': label, 'version_id': row['id']}
            if not effective:
                head = account_head if scope == 'account' else global_head
                fields = {name: item | {'source': scope, 'version_id': head['operation']} for name,item in scoped_fields.items()}
            empty = {'chunks': 0, 'unicode_length': 0, 'utf8_bytes': 0, 'sha256': sha256(b'').hexdigest(), 'source': 'default', 'version_id': ''}
            if effective: fields = {name: fields.get(name, empty.copy()) for name in FIELDS}
            head = account_head if scope == 'account' else global_head
            if legacy is not None:
                need(self.legacy(connection_id,self.registry)==legacy,'RULES_LEGACY_CHANGED')
            return {'state': 'RULES_READ', 'store_revision': self._revision(db),
                    'scope_revision': head['revision'] if head else 0,
                    'global_revision': global_head['revision'] if global_head else 0,
                    'fields': fields, 'effective_sha256': digest(fields), 'scope': scope,
                    'connection_id': connection_id, 'preferences_only': True}

    def read_chunk(self, connection_id, scope, version_id, field, index):
        target = self._scope(scope, connection_id); integer(index); need(field in FIELDS)
        with self._transaction(connection_id) as (db, who):
            if type(version_id) is str and version_id.startswith(LEGACY_PREFIX):
                legacy=self.legacy(connection_id,self.registry)
                need(legacy is not None and legacy['version_id']==version_id and field in legacy['fields']
                     and index==0 and legacy['fields'][field]!='','RULES_LEGACY_CHANGED')
                text=legacy['fields'][field]
                return {'version_id':version_id,'field':field,'index':index,'text':text,'sha256':sha256(text.encode('utf-8')).hexdigest()}
            need(db is not None, 'RULES_VERSION_UNAVAILABLE')
            row = db.execute('SELECT * FROM operations WHERE id=?', (version_id,)).fetchone()
            need(row is not None and row['state'] == 'COMMITTED' and
                 ((row['scope'] == target and row['binding'] == who['binding']) or
                  (row['scope'] == 'global' and row['binding'] == who['owner'])), 'RULES_VERSION_UNAVAILABLE')
            declared = json.loads(row['fields']); need(field in declared and index < declared[field]['chunks'])
            chunk = db.execute('SELECT text,sha256 FROM chunks WHERE operation=? AND field=? AND position=?', (version_id,field,index)).fetchone()
            need(chunk is not None and sha256(text_chunk(chunk['text'])).hexdigest() == chunk['sha256'], 'RULES_INVALID_STORE')
            return {'version_id': version_id, 'field': field, 'index': index, 'text': chunk['text'], 'sha256': chunk['sha256']}

    def version(self, connection_id, scope, version_id):
        target = self._scope(scope, connection_id)
        with self._transaction(connection_id) as (db, who):
            row = self._operation(db, version_id, target, who['binding'])
            need(row['state'] == 'COMMITTED', 'RULES_VERSION_UNAVAILABLE')
            return {'version_id': version_id, 'scope_revision': row['scope_revision'],
                    'fields': {name: item | {'source': scope, 'version_id': version_id}
                               for name,item in json.loads(row['fields']).items()}}

    def history(self, connection_id='', scope='global', before=2**53-1):
        target = self._scope(scope, connection_id); integer(before)
        with self._transaction(connection_id) as (db, who):
            rows = list(db.execute('SELECT id,revision,scope_revision,restore_from FROM operations WHERE scope=? AND binding=? AND state=? AND revision<? ORDER BY revision DESC LIMIT 21',
                                  (target,who['binding'],'COMMITTED',before))) if db else []
            items = [dict(row) for row in rows[:20]]
            return {'items': items, 'next_before': items[-1]['revision'] if len(rows)>20 else None}

    def restore(self, connection_id, scope, operation_id, version_id, expected_store_revision, expected_scope_revision):
        target = self._scope(scope, connection_id)
        integer(expected_store_revision); integer(expected_scope_revision)
        need(type(operation_id) is str and OP.fullmatch(operation_id) is not None)
        with self._transaction(connection_id, write=True) as (db, who):
            original = self._operation(db, version_id, target, who['binding'])
            need(original['state'] == 'COMMITTED', 'RULES_VERSION_UNAVAILABLE')
            previous = db.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone()
            if previous:
                need(previous['scope'] == target and previous['binding'] == who['binding']
                     and previous['restore_from'] == version_id
                     and previous['expected_store'] == expected_store_revision
                     and previous['expected_scope'] == expected_scope_revision, 'RULES_OPERATION_CONFLICT')
            else:
                head = self._head(db, target, who['binding'])
                need(self._revision(db) == expected_store_revision and (head['revision'] if head else 0) == expected_scope_revision,
                     'RULES_VERSION_CONFLICT')
                self._complete(db, original)
                revision, scope_revision = self._revision(db)+1, expected_scope_revision+1
                db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?,?)', (operation_id,target,who['binding'],expected_store_revision,
                    expected_scope_revision,original['fields'],'COMMITTED',revision,scope_revision,version_id,time.time()))
                db.execute('INSERT INTO chunks SELECT ?,field,position,text,sha256 FROM chunks WHERE operation=?', (operation_id,version_id))
                db.execute('INSERT INTO heads VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET operation=excluded.operation,revision=excluded.revision', (target,who['binding'],operation_id,scope_revision))
                db.execute('UPDATE meta SET revision=? WHERE singleton=1', (revision,))
        try:
            return self.operation(connection_id, scope, operation_id)
        except (WCEError, OSError, sqlite3.Error):
            raise WCEError('RULES_WRITE_RESULT_UNKNOWN') from None
